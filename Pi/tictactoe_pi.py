#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tic-Tac-GO - game brain for the Freenove Robot Arm
=====================================================

This script is the "brain" of the game. It runs on the Raspberry Pi
alongside the arm kit's own, UNMODIFIED control server (main.py, which
ships with the kit and listens on port 5000). This script:

  1. Listens for the Arduino joystick controller on GAME_PORT and
     receives the player's confirmed moves.
  2. Owns the 3x3 board, turn order, win/draw checking, and the random
     AI move.
  3. Talks to the arm's existing main.py server using the documented
     G-code-style text protocol (G0/S1/S2/...) to physically move the
     arm, beep the buzzer, and flash the RGB LED ring.
  4. Draws a live 3x3 grid + X/O overlay on the Pi camera feed.

WHY GO THROUGH main.py INSTEAD OF stepMotor.py DIRECTLY?
----------------------------------------------------------
stepMotor.py is the lowest-level interface: raw step pulses to the
A4988 drivers. The kit's own docs warn that once the steppers are
mounted in the assembled arm, sending it raw/parameterised pulse
commands can cause "mechanical structural conflicts" (i.e. crash the
arm into its own joint limits), because that layer has no idea where
the arm currently is or what its physical limits are. arm.py / main.py
sit on top of stepMotor.py specifically to add joint-limit checking
and smooth interpolation, and main.py exposes that safely over a
socket using the simple "G0 X Y Z" protocol documented in the kit's
Chapter 6 (Communication Instructions). Going through that existing,
already-debugged layer is the safer choice, so this script is a CLIENT
of main.py rather than a replacement for it.

ONE-TIME PREREQUISITE
------------------------
Before running this for the first time, complete the normal one-time
setup with the official Freenove control software (Chapter 4 of the
docs): enable the motors, run sensor/home-point calibration, and set
the ground height + end-effector length for whatever you've clamped
into the arm (pen, gripper, etc). Those values are saved to a local
JSON file by the kit's own code and are reused automatically and you do
NOT need to redo that setup just because this script connects instead
of the official app.

CALIBRATING THE PHYSICAL GRID
--------------------------------
The CELL_POSITIONS below are placeholders. Run this script once with
--calibrate: it will hover (pen up, nothing drawn) over each of the 9
cells in turn so you can check the hover point lines up with a real
3x3 grid placed under the arm, and adjust GRID_CENTER_X/Y, CELL_PITCH
and HOVER_Z/DRAW_Z below until it does. Go slowly and watch the arm
the first few times as these are reasonable starting numbers, not
verified measurements for your specific build.
"""

import argparse
import logging
import math
import random
import socket
import threading
import time

# =======================================================================
# CONFIGURATION - edit these for your setup
# =======================================================================

# The arm's OWN control server (main.py, unmodified, ships with the kit).
# main.py binds to the Pi's WiFi interface address specifically, NOT
# 127.0.0.1/localhost - use the same IP the Freenove app/software uses.
ARM_HOST = "PI_WLAN_IP_HERE"
ARM_PORT = 5000

# This script's own server, for the Arduino joystick controller.
# Must match GAME_PORT in the Arduino sketch.
GAME_HOST = "0.0.0.0"
GAME_PORT = 9000

# --- physical grid calibration (placeholders, see --calibrate) ---
GRID_CENTER_X = 0.0     # mm, X of the middle cell's centre
GRID_CENTER_Y = 200.0   # mm, Y of the middle cell's centre (docs' sample
                        # home position uses Y=200, so this is a sane start)
CELL_PITCH = 50.0       # mm between adjacent cell centres
HOVER_Z = 90.0          # mm, safe pen-up travel height
DRAW_Z = 60.0           # mm, pen-down height (lower than HOVER_Z).
                        # Raise this gradually from something clearly too
                        # high until the pen just touches the surface.

MARK_RADIUS = 10.0       # mm, radius of the AI's drawn 'O'
MARK_HALF_WIDTH = 10.0   # mm, half-width of the player's drawn 'X'

# Should the arm also physically draw the player's X (in addition to
# the AI's O)? Turn off if you'd rather the player's mark stay purely
# virtual (camera-overlay only) and only the AI draws on the board.
DRAW_PLAYER_MARK_WITH_ARM = True

# Soft safety bounds - refuse to send any target outside this box,
# independent of whatever limits main.py/arm.py enforce internally.
SAFE_XY_RADIUS = 260.0
SAFE_Z_MIN = 20.0
SAFE_Z_MAX = 120.0

PLAYER_LED_COLOR = (0, 255, 0)   # green flash when the player moves
AI_LED_COLOR = (0, 0, 255)       # blue flash when the AI moves
MOVE_BEEP_FREQ = 2000
MOVE_BEEP_MS = 120

CELL_POSITIONS = {}
for _r in range(3):
    for _c in range(3):
        _x = GRID_CENTER_X + (_c - 1) * CELL_PITCH
        _y = GRID_CENTER_Y - (_r - 1) * CELL_PITCH  # row 0 = farthest row
        CELL_POSITIONS[(_r, _c)] = (_x, _y)

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]


# =======================================================================
# Board helpers
# =======================================================================
def check_winner(board):
    for a, b, c in WIN_LINES:
        if board[a] is not None and board[a] == board[b] == board[c]:
            return board[a]
    return None


def is_full(board):
    return all(cell is not None for cell in board)


def circle_path(cx, cy, z_draw, z_hover, radius=MARK_RADIUS, segments=10):
    """Waypoints to draw a small circle (the AI's 'O')."""
    start_x, start_y = cx + radius, cy
    pts = [(start_x, start_y, z_hover), (start_x, start_y, z_draw)]
    for i in range(1, segments + 1):
        theta = 2 * math.pi * i / segments
        pts.append((cx + radius * math.cos(theta), cy + radius * math.sin(theta), z_draw))
    pts.append((start_x, start_y, z_hover))
    return pts


def x_path(cx, cy, z_draw, z_hover, half=MARK_HALF_WIDTH):
    """Waypoints to draw two crossing diagonal strokes (the player's 'X')."""
    p1 = (cx - half, cy - half)
    p2 = (cx + half, cy + half)
    p3 = (cx - half, cy + half)
    p4 = (cx + half, cy - half)
    return [
        (p1[0], p1[1], z_hover), (p1[0], p1[1], z_draw),
        (p2[0], p2[1], z_draw), (p2[0], p2[1], z_hover),
        (p3[0], p3[1], z_hover), (p3[0], p3[1], z_draw),
        (p4[0], p4[1], z_draw), (p4[0], p4[1], z_hover),
    ]


# =======================================================================
# ArmLink - client of the kit's own, unmodified main.py control server
# =======================================================================
class ArmLink:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.send_lock = threading.Lock()
        self.remaining_commands = 0
        self._stop = threading.Event()

    def connect(self, retries=10, delay=2.0):
        for attempt in range(retries):
            try:
                self.sock = socket.create_connection((self.host, self.port), timeout=5)
                self.sock.settimeout(None)
                logging.info("Connected to the arm's main.py server at %s:%s", self.host, self.port)
                threading.Thread(target=self._read_loop, daemon=True).start()
                self._send_raw("S8 E0")   # make sure motor torque is on
                self._send_raw("S12 K1")  # ask for motion-queue feedback
                return
            except OSError as exc:
                logging.warning("Arm connect attempt %d/%d failed: %s", attempt + 1, retries, exc)
                time.sleep(delay)
        raise ConnectionError(
            f"Could not reach the arm's main.py server at {self.host}:{self.port}. "
            "Is main.py running on the Pi, and is --arm-host its WiFi IP (not 127.0.0.1)?"
        )

    def _send_raw(self, cmd):
        line = (cmd + "\r\n").encode("utf-8")
        with self.send_lock:
            self.sock.sendall(line)

    def _read_loop(self):
        buf = ""
        while not self._stop.is_set():
            try:
                data = self.sock.recv(256)
            except OSError:
                break
            if not data:
                break
            buf += data.decode("utf-8", errors="ignore")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if line.startswith("S12") and "K" in line:
                    try:
                        self.remaining_commands = int(line.split("K")[-1])
                    except ValueError:
                        pass

    def _validate(self, x, y, z):
        if math.hypot(x, y) > SAFE_XY_RADIUS:
            raise ValueError(f"Refusing out-of-range XY target ({x:.1f}, {y:.1f})")
        if not (SAFE_Z_MIN <= z <= SAFE_Z_MAX):
            raise ValueError(f"Refusing out-of-range Z target ({z:.1f})")

    def move(self, x, y, z):
        self._validate(x, y, z)
        self._send_raw(f"G0 X{x:.2f} Y{y:.2f} Z{z:.2f}")
        self.remaining_commands += 1  # optimistic; corrected by feedback

    def led(self, mode, r, g, b):
        self._send_raw(f"S1 M{mode} R{r} G{g} B{b}")

    def buzzer(self, freq):
        self._send_raw(f"S2 D{int(freq)}")

    def beep(self, freq, ms):
        self.buzzer(freq)
        time.sleep(ms / 1000.0)
        self.buzzer(0)

    def execute_path(self, points):
        for (x, y, z) in points:
            self.move(x, y, z)
        self.wait_idle()

    def wait_idle(self, timeout=20.0, poll=0.1):
        deadline = time.time() + timeout
        time.sleep(0.3)  # give the feedback thread a moment to catch up
        while time.time() < deadline:
            if self.remaining_commands <= 0:
                return
            time.sleep(poll)
        logging.warning("wait_idle timed out after %.1fs; continuing anyway", timeout)

    def emergency_stop(self):
        """Real emergency stop only, releases motor torque and kills
        main.py's own threads. Not used on normal shutdown."""
        self._send_raw("S13 N1")

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


# =======================================================================
# Shared game state (read by the camera overlay thread)
# =======================================================================
class GameState:
    def __init__(self):
        self.lock = threading.Lock()
        self.board = [None] * 9
        self.turn = "X"
        self.cursor = (1, 1)
        self.last_event = "Game starting..."
        self.game_over = False

    def snapshot(self):
        with self.lock:
            return list(self.board), self.turn, self.cursor, self.last_event, self.game_over


# =======================================================================
# GameServer - talks to the Arduino, drives the round, drives the arm
# =======================================================================
class GameServer:
    def __init__(self, arm, state, host=GAME_HOST, port=GAME_PORT):
        self.arm = arm
        self.state = state
        self.host = host
        self.port = port
        self.conn = None
        self.server_sock = None

    def start(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(1)
        logging.info("Waiting for the Arduino controller on %s:%s", self.host, self.port)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while True:
            conn, addr = self.server_sock.accept()
            logging.info("Arduino connected from %s", addr)
            self.conn = conn
            self._reset_round(announce=False)
            self._send("TURN")
            self._serve(conn)

    def _serve(self, conn):
        buf = ""
        try:
            while True:
                data = conn.recv(256)
                if not data:
                    break
                buf += data.decode("utf-8", errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    self._handle_line(line.strip())
        except OSError:
            pass
        logging.info("Arduino disconnected")
        self.conn = None

    def _send(self, msg):
        if self.conn:
            try:
                self.conn.sendall((msg + "\n").encode("utf-8"))
            except OSError:
                pass

    def _handle_line(self, line):
        if not line:
            return
        if line.startswith("CURSOR,"):
            r, c = (int(v) for v in line[7:].split(","))
            with self.state.lock:
                self.state.cursor = (r, c)
        elif line.startswith("MOVE,"):
            r, c = (int(v) for v in line[5:].split(","))
            self._handle_player_move(r, c)

    # -------------------------------------------------------------
    def _handle_player_move(self, r, c):
        idx = r * 3 + c
        with self.state.lock:
            if self.state.game_over or self.state.turn != "X":
                self._send("WAIT")
                return
            # --- safety feature: refuse a move onto an occupied cell ---
            if self.state.board[idx] is not None:
                self.state.last_event = "That cell is taken so pick another."
                self._send("INVALID")
                return
            self.state.board[idx] = "X"
            self.state.last_event = f"Player marked cell {r},{c}"
            self.state.turn = None  # locked while the arm/buzzer/LED react
        self._send("WAIT")
        self._on_move_completed("X", r, c)
        self._after_move("X")

    def _do_ai_turn(self):
        with self.state.lock:
            empties = [i for i, v in enumerate(self.state.board) if v is None]
        # --- safety feature: the AI only ever samples currently-empty cells ---
        if not empties:
            return
        idx = random.choice(empties)
        r, c = divmod(idx, 3)
        with self.state.lock:
            self.state.board[idx] = "O"
            self.state.last_event = f"AI (O) chose cell {r},{c}"
        self._on_move_completed("O", r, c)
        self._send(f"AIMOVE,{r},{c}")
        self._after_move("O")

    def _on_move_completed(self, who, r, c):
        cx, cy = CELL_POSITIONS[(r, c)]
        if who == "X" and DRAW_PLAYER_MARK_WITH_ARM:
            self.arm.execute_path(x_path(cx, cy, DRAW_Z, HOVER_Z))
        elif who == "O":
            self.arm.execute_path(circle_path(cx, cy, DRAW_Z, HOVER_Z))
        color = PLAYER_LED_COLOR if who == "X" else AI_LED_COLOR
        self.arm.led(3, *color)  # mode 3 = blink
        self.arm.beep(MOVE_BEEP_FREQ, MOVE_BEEP_MS)

    def _after_move(self, who):
        with self.state.lock:
            board = list(self.state.board)
        winner = check_winner(board)
        if winner == "X":
            self._finish_round("WIN")
        elif winner == "O":
            self._finish_round("LOSE")
        elif is_full(board):
            self._finish_round("DRAW")
        elif who == "X":
            # Player just moved and the round continues -> AI's turn.
            with self.state.lock:
                self.state.turn = "O"
            self._do_ai_turn()
        else:
            # AI just moved and the round continues -> back to the player.
            with self.state.lock:
                self.state.turn = "X"
            self._send("TURN")

    def _finish_round(self, result):
        with self.state.lock:
            self.state.game_over = True
            self.state.last_event = {
                "WIN": "Player wins!",
                "LOSE": "AI wins!",
                "DRAW": "It's a draw.",
            }[result]
        self._send(result)
        if result == "WIN":
            self.arm.led(5, 0, 255, 0)
            self.arm.beep(2600, 150)
            self.arm.beep(3000, 150)
        elif result == "LOSE":
            self.arm.led(3, 255, 0, 0)
            self.arm.beep(300, 400)
        else:
            self.arm.led(4, 255, 200, 0)
            self.arm.beep(800, 200)
        threading.Timer(4.0, self._reset_round).start()

    def _reset_round(self, announce=True):
        with self.state.lock:
            self.state.board = [None] * 9
            self.state.turn = "X"
            self.state.game_over = False
            self.state.last_event = "New round! Your move."
        self.arm.led(0, 0, 0, 0)
        if announce:
            self._send("RESET")
            self._send("TURN")


# =======================================================================
# Camera overlay (optional - degrades gracefully if cv2/picamera2 missing)
# =======================================================================
class CameraOverlay:
    def __init__(self, state):
        self.state = state
        self.stop_event = threading.Event()
        self.available = False
        self.picam = None
        self.cap = None
        self.cv2 = None
        self._setup_camera()

    def _setup_camera(self):
        try:
            import cv2  # noqa: local import, optional dependency
            self.cv2 = cv2
        except ImportError:
            logging.warning("opencv-python not installed; camera overlay disabled.")
            return
        try:
            from picamera2 import Picamera2
            self.picam = Picamera2()
            config = self.picam.create_preview_configuration(
                main={"format": "RGB888", "size": (640, 480)}
            )
            self.picam.configure(config)
            self.picam.start()
            self.available = True
            logging.info("Using picamera2 for the camera feed.")
            return
        except Exception as exc:
            logging.info("picamera2 unavailable (%s); trying a plain webcam instead.", exc)
        self.cap = self.cv2.VideoCapture(0)
        self.available = self.cap.isOpened()
        if not self.available:
            logging.warning("No camera found; camera overlay disabled.")

    def _grab_frame(self):
        if self.picam is not None:
            return self.picam.capture_array()
        if self.cap is not None:
            ok, frame = self.cap.read()
            return frame if ok else None
        return None

    def run(self):
        if not self.available:
            return
        cv2 = self.cv2
        headless = False
        while not self.stop_event.is_set():
            frame = self._grab_frame()
            if frame is None:
                time.sleep(0.05)
                continue
            annotated = self._annotate(frame)
            if not headless:
                try:
                    cv2.imshow("Tic-Tac-GO", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        self.stop_event.set()
                except cv2.error:
                    headless = True
                    logging.info("No display available; writing frames to /tmp/tictactoe_overlay.jpg instead.")
            if headless:
                cv2.imwrite("/tmp/tictactoe_overlay.jpg", annotated)
                time.sleep(0.5)

    def _annotate(self, frame):
        cv2 = self.cv2
        h, w = frame.shape[:2]
        board, turn, cursor, last_event, game_over = self.state.snapshot()
        for i in range(1, 3):
            cv2.line(frame, (w * i // 3, 0), (w * i // 3, h), (255, 255, 255), 2)
            cv2.line(frame, (0, h * i // 3), (w, h * i // 3), (255, 255, 255), 2)
        cell_w, cell_h = w // 3, h // 3
        for idx, mark in enumerate(board):
            if mark is None:
                continue
            r, c = divmod(idx, 3)
            cx, cy = c * cell_w + cell_w // 2, r * cell_h + cell_h // 2
            color = (0, 200, 0) if mark == "X" else (0, 0, 220)
            cv2.putText(frame, mark, (cx - 20, cy + 20), cv2.FONT_HERSHEY_SIMPLEX, 1.6, color, 4)
        if turn == "X" and not game_over:
            r, c = cursor
            x0, y0 = c * cell_w, r * cell_h
            cv2.rectangle(frame, (x0 + 4, y0 + 4), (x0 + cell_w - 4, y0 + cell_h - 4), (0, 255, 255), 3)
        cv2.putText(frame, last_event, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        return frame

    def stop(self):
        self.stop_event.set()
        if self.picam is not None:
            try:
                self.picam.stop()
            except Exception:
                pass
        if self.cap is not None:
            self.cap.release()


# =======================================================================
def main():
    parser = argparse.ArgumentParser(description="Tic-Tac-GO: robot arm tic-tac-toe game server")
    parser.add_argument("--arm-host", default=ARM_HOST,
                         help="WiFi IP of the Pi running main.py (NOT 127.0.0.1).")
    parser.add_argument("--arm-port", type=int, default=ARM_PORT)
    parser.add_argument("--game-port", type=int, default=GAME_PORT)
    parser.add_argument("--calibrate", action="store_true",
                         help="Hover over each of the 9 cells (no drawing) then exit, "
                              "so you can check the grid alignment.")
    parser.add_argument("--no-camera", action="store_true", help="Skip the camera overlay.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.arm_host in ("PI_WLAN_IP_HERE", "", "127.0.0.1", "localhost"):
        logging.warning(
            "arm-host is set to %r. main.py binds to the Pi's WiFi interface address, "
            "not localhost, so this will likely fail to connect. Pass --arm-host <pi-ip> "
            "(the same IP the Freenove app/software uses).",
            args.arm_host,
        )

    arm = ArmLink(args.arm_host, args.arm_port)
    arm.connect()

    if args.calibrate:
        logging.info("Calibration sweep: hovering over each cell (Ctrl+C to stop early).")
        try:
            for r in range(3):
                for c in range(3):
                    x, y = CELL_POSITIONS[(r, c)]
                    logging.info("Cell (%d,%d) -> X%.1f Y%.1f", r, c, x, y)
                    arm.move(x, y, HOVER_Z)
                    arm.wait_idle()
                    time.sleep(1.0)
            arm.move(GRID_CENTER_X, GRID_CENTER_Y, HOVER_Z)
            arm.wait_idle()
        except KeyboardInterrupt:
            pass
        logging.info("Calibration sweep done.")
        arm.close()
        return

    state = GameState()
    server = GameServer(arm, state, port=args.game_port)
    server.start()

    overlay = None
    if not args.no_camera:
        overlay = CameraOverlay(state)
        threading.Thread(target=overlay.run, daemon=True).start()

    logging.info("Tic-Tac-GO is ready. Waiting for the Arduino joystick controller...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    finally:
        if overlay:
            overlay.stop()
        arm.close()


if __name__ == "__main__":
    main()
