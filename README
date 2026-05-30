# SCC Robot Arm Project (Tic Tac Toe)

1. A Raspberry Pi 3B+ runs the game server and camera overlay
2. An Arduino UNO R4 WiFi reads two joysticks and streams data to the Pi over TCP
3. The Freenove FNK0036 robot arm (3× stepper motors + A4988 drivers) physically draws on paper with a pencil
4. A USB camera overlays the live 3×3 grid on screen so you can see the game state in real time

You are O (drawn as an octagon)
The robot is X (two diagonal strokes)
The AI picks randomly from empty cells — keeping the game fair and fun

arm.py, stepmotor.py, sensor.py, and messageThread.py are part of the [Freenove FNK0036 official codebase](https://github.com/Freenove/Freenove_Robot_Arm_Kit_for_Raspberry_Pi)

Clone that repo to your Pi and run `tictactoe_pi.py` from inside `Server/Code/`.
Upload Joystick_Control.ino to the Arduino

### Components Required (Alternatives are possible except for the Arm)

| Robot Arm | Freenove FNK0036 |
| :--- | :--- |
| Pi | Raspberry Pi 3B+ |
| Microcontroller | Arduino UNO R4 WiFi |
| Joysticks | 2× standard KY-023 analog joysticks |
| Camera | Pi Camera Module 2 or USB webcam |
| Connection | Wi-Fi TCP socket (Pi acts as server) |

### Joystick 1 — Cursor (XY navigation)

| Joystick Pin | Arduino Pin |
| :--- | :--- |
| VCC | 5V |
| GND | GND |
| VRX | A0 |
| VRY | A1 |
| SW | D2 |

### Joystick 2 — Cursor (Z navigation) / Confirm move

| Joystick Pin | Arduino Pin |
| :--- | :--- |
| VCC | 5V |
| GND | GND |
| VRZ | A2 |
| SW | D3 |

See [`docs/wiring.md`](docs/wiring.md) for the full robot arm wiring reference.

## Setup & Running

### 1. Arduino

1. Open `arduino/tictactoe_arduino/tictactoe_arduino.ino` in the Arduino IDE
2. Install the WiFiS3 and Arduino_LED_Matrix libraries via Library Manager
3. Edit the top of the file:
   ```cpp
   #define WIFI_SSID   "your-network"
   #define WIFI_PASS   "your-password"
   #define PI_ADDRESS  "192.168.x.x"   // Pi's IP
