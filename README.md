<div align="center">
   
# Tic-Tac-Toe using Freenove Robot Arm (0036)

**A physical Tic-Tac-Toe game where a Freenove FNK0036 robot arm draws X's and O's on paper  controlled by an Arduino R4 WiFi joystick and a Raspberry Pi 3B+**

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Arduino](https://img.shields.io/badge/Arduino-R4_WiFi-00979D?style=for-the-badge&logo=arduino&logoColor=white)
![Raspberry Pi](https://img.shields.io/badge/Raspberry_Pi-3B+-A22846?style=for-the-badge&logo=raspberrypi&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Camera-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)

---

</div>

## How It Works

1. A **Raspberry Pi 3B+** runs the game server and camera overlay
2. An **Arduino UNO R4 WiFi** reads two joysticks and streams data to the Pi over TCP
3. The **Freenove FNK0036** robot arm (3× stepper motors + A4988 drivers) physically draws on paper with a pencil
4. A **USB camera** overlays the live 3×3 grid on screen so you can see the game state in real time

**You are O** (drawn as an octagon)
**The robot is X** (two diagonal strokes)
The AI picks randomly from empty cells keeping the game fair and fun

---

## Repository Structure

```
SSCRobotArm/
│
├── pi/
│   └── tictactoe.py          # Main game run this on the Pi in Freenove_Robot_Arm_Kit_for_Raspberry_Pi/Server/Code
│
├── arduino/
│   └── joystick.ino  # Upload this to Arduino R4 WiFi
│
├── docs/
│   ├── demo
│       └──
│       └──
│       └──
│       └──            
│   ├── wiring.md                # Wiring reference
│   └── calibration.md           # Arm calibration guide
│
├── .gitignore
├── LICENSE
└── README.md
```

> **Note:** `arm.py`, `stepmotor.py`, `sensor.py`, and `messageThread.py` are part of the [Freenove FNK0036 official codebase](https://github.com/Freenove/Freenove_Robot_Arm_Kit_for_Raspberry_Pi)  
> Clone that repo to your Pi and run `tictactoe_pi.py` from inside `Server/Code/`

---

## Hardware

Every component here is changable except for the Robot Arm

| Type of Component | Actual Component |
|---|---|
| Robot Arm | Freenove FNK0036 (3× stepper + A4988 + servo clamp) |
| Pi | Raspberry Pi 3B+ |
| Microcontroller | Arduino UNO R4 WiFi |
| Joysticks | 2× standard KY-023 analog joysticks |
| Camera | Pi Camera Module 2 or USB webcam |

---

##  Wiring

### Joystick 1  Cursor (XY Navigation)
| Joystick Pin | Arduino Pin |
|---|---|
| VCC | 5V |
| GND | GND |
| VRX | A0 |
| VRY | A1 |
| SW  | D2 |

### Joystick 2  (Z Navigation) / Confirm Move
| Joystick Pin | Arduino Pin |
|---|---|
| VCC | 5V |
| GND | GND |
| VRX | A2 |
| VRY | A3 |
| SW  | D3 |

See [`docs/wiring.md`](docs/wiring.md) for the full robot arm wiring reference

---

## Setup & Running

### 1. Arduino

1. Open `arduino/tictactoe_arduino/tictactoe_arduino.ino` in the Arduino IDE
2. Install the **WiFiS3** and **Arduino_LED_Matrix** libraries via Library Manager
3. Edit the top of the file:
   ```cpp
   #define WIFI_SSID   "your-network"
   #define WIFI_PASS   "your-password"
   #define PI_ADDRESS  "192.168.x.x"   // Pi's IP  printed at startup
   ```
4. Upload to the Arduino R4 WiFi

### 2. Raspberry Pi

   1. Clone the Freenove repo (if not already done):
   ```bash
   git clone https://github.com/Freenove/Freenove_Robot_Arm_Kit_for_Raspberry_Pi.git
   cd Freenove_Robot_Arm_Kit_for_Raspberry_Pi/Server/Code
   ```
   
   2. Copy `tictactoe_pi.py` into that directory, then install dependencies:
   ```bash
   pip3 install opencv-python
   ```
   
   3. Run the game:
   ```bash
   sudo python3 tictactoe_pi.py
   ```
   
   The Pi will print its IP addresses at startup enter the correct one into the Arduino sketch

### 3. Calibration

   Before playing, you **must** calibrate `GRID_XY` in `tictactoe_pi.py`:
   
   1. Run your working arm-control script to jog the arm manually
   2. Hover the pencil tip over each of the 9 box centres on your paper
   3. Note the X/Y mm coordinates at each position
   4. Update `GRID_XY` in `tictactoe_pi.py` accordingly
   
   See [`docs/calibration.md`](docs/calibration.md) for full details

---

## Controls

| Input | Action |
|---|---|
| Joystick 1 (any direction) | Move cursor between grid cells |
| Joystick 2 button (press) | Confirm your move (place O) |
| `R` key on Pi keyboard | Reset the game |
| `Q` key on Pi keyboard | Quit |

The LED matrix on the Arduino shows your current cursor position as a dot on a 3×3 grid

---

## Game Logic

- **Player** = O drawn as an octagon (8-segment polygon)
- **Robot AI** = X drawn as two diagonal strokes
- AI selects randomly from remaining empty cells
- Player **cannot** select an already-filled cell
- Win detection checks all 8 lines after every move
- Camera overlay shows live grid + symbols + status bar

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Arduino can't connect to Pi | Check `PI_ADDRESS` matches the IP printed at Pi startup |
| Arm moves to wrong position | Recalibrate `GRID_XY`  see `docs/calibration.md` |
| Pencil doesn't touch paper | Lower `PEN_DOWN_Z` in `tictactoe_pi.py` (try `0`) |
| Camera not found | Run `ls /dev/video*` and update `VideoCapture(0, ...)` index |
| `from arm import Arm` fails | Must run from `Freenove_Robot_Arm_Kit_for_Raspberry_Pi/Server/Code/` |
| Joystick drift / phantom moves | Increase `DEADZONE` constant in `tictactoe_pi.py` |

---

## License

This project is licensed under the **MIT License**  see [`LICENSE`](LICENSE) for details

Freenove arm firmware (`arm.py`, `stepmotor.py`, etc.) is licensed separately under [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) by Freenove Creative Technology Co., Ltd

---

Made with Python, C++, stepper motors and a pencil
