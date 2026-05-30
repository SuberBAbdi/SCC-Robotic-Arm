# Wiring Reference

## Joystick → Arduino R4 WiFi

| Signal | Joystick 1 (cursor) | Joystick 2 (confirm) |
|---|---|---|
| VCC | 5V | 5V |
| GND | GND | GND |
| VRX | A0 | A2 |
| VRY | A1 | A3 |
| SW (button) | D2 | D3 |

Both button pins use `INPUT_PULLUP` — pressing reads `LOW` (0), released reads `HIGH` (1).

## Robot Arm → Raspberry Pi

The FNK0036 connects to the Pi via its dedicated Robot Arm Board.
Refer to the [official Freenove assembly guide](https://docs.freenove.com/projects/fnk0036) for the full GPIO pinout.

Key Pi GPIO pins used by `stepmotor.py`:

| Signal | GPIO (BCM) |
|---|---|
| A4988 EN | 9 |
| MS1 / MS2 / MS3 | 10 / 24 / 23 |
| DIR 1 / 2 / 3 | 14 / 15 / 27 |
| STEP 1 / 2 / 3 | 4 / 17 / 22 |

## Camera

Connect the Pi Camera Module 2 to the CSI port, or plug in a USB webcam.
If the camera index is not `0`, update `cv2.VideoCapture(0, ...)` in `tictactoe_pi.py`.
