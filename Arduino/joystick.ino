/*
  Tic-Tac-GO - Joystick Controller for the Freenove Robot Arm
  =============================================================
  Board: Arduino UNO R4 WiFi
  Input: ONE analog joystick (X axis, Y axis, push button)
  Output: the board's built-in 12x8 LED matrix + WiFi link to the Pi

  WHAT THIS SKETCH DOES
  ----------------------
  - Lets the player move a cursor around a 3x3 grid using a single
    joystick (tilt = move one cell, return to centre before the next
    move registers, so it doesn't "machine-gun" across the grid).
  - Pressing the joystick button CONFIRMS the highlighted cell as the
    player's move and sends it to the Raspberry Pi.
  - Shows the cursor / occupied cells / game results on the LED matrix.

  IMPORTANT - this sketch does NOT talk to the robot arm directly.
  It talks to a small Python "game brain" script running on the
  Raspberry Pi (tictactoe_arm_game.py). That script is the one that
  talks to the arm's own existing control server (main.py, which
  listens on port 5000) using the robot's documented G-code-style
  commands. Keep GAME_PORT below pointed at the Python game script,
  *not* at port 5000.

  WIRE PROTOCOL (plain text lines, each ending in '\n')
  -------------------------------------------------------
  Arduino -> Pi
    "MOVE,<row>,<col>"     sent once when the button confirms a cell
    "CURSOR,<row>,<col>"   sent whenever the highlighted cell changes
                            (used to draw a live cursor on the camera
                            overlay)
  Pi -> Arduino
    "TURN"                  it's the player's turn, joystick is live
    "WAIT"                  not the player's turn, joystick is ignored
    "INVALID"               last move was rejected (cell was occupied)
    "AIMOVE,<row>,<col>"    tells us which cell the arm just chose
    "WIN" / "LOSE" / "DRAW" end of round result
    "RESET"                 start a new round
*/

#include "WiFiS3.h"
#include "ArduinoGraphics.h"
#include "Arduino_LED_Matrix.h"

// ---------------- Wi-Fi / Pi connection ----------------
#define WIFI_NETWORK_NAME ""
#define WIFI_PASSWORD     ""
#define PI_ADDRESS  "0.0.0.0"   // <-- set this to your Raspberry Pi's IP
#define GAME_PORT   9000        // <-- tictactoe_arm_game.py's port
                                 //     (NOT the arm's own main.py port, 5000!)

char SSID[]   = WIFI_NETWORK_NAME;
char pass[]   = WIFI_PASSWORD;
char server[] = PI_ADDRESS;
int  port     = GAME_PORT;
int  wifiStatus = WL_IDLE_STATUS;

WiFiClient client;

// ---------------- Joystick ----------------
const int PIN_X  = A2;
const int PIN_Y  = A3;
const int PIN_SW = 2;

const int JOY_LOW          = 300;  // tilted toward 0
const int JOY_HIGH         = 700;  // tilted toward max
const int JOY_NEUTRAL_LOW  = 400;  // must return inside this band...
const int JOY_NEUTRAL_HIGH = 600;  // ...before another move is allowed

bool xAxisReady = true;
bool yAxisReady = true;

int cursorRow = 1;  // 0..2, start in the centre cell
int cursorCol = 1;
int lastSentCursorRow = -1;
int lastSentCursorCol = -1;

bool occupied[3][3] = { {false, false, false},
                        {false, false, false},
                        {false, false, false} };

// ---------------- Button ----------------
bool lastButtonState = HIGH;  // HIGH = not pressed (INPUT_PULLUP)
unsigned long lastButtonChangeMs = 0;
const unsigned long BUTTON_DEBOUNCE_MS = 40;

// ---------------- Game state ----------------
enum GameState { GS_DISCONNECTED, GS_MY_TURN, GS_WAITING, GS_GAME_OVER };
GameState gameState = GS_DISCONNECTED;

// ---------------- LED matrix ----------------
ArduinoLEDMatrix matrix;
const int MATRIX_W = 12;
const int MATRIX_H = 8;
uint8_t frame[MATRIX_H][MATRIX_W];

// Top-left corner of the 2x2 pixel block used for each grid cell
const int ROW_POS[3] = {0, 3, 6};
const int COL_POS[3] = {0, 4, 8};

bool blinkOn = false;
unsigned long lastBlinkMs = 0;
const unsigned long BLINK_PERIOD_MS = 300;

String incomingLine = "";

// =======================================================================
void setup() {
  Serial.begin(9600);
  while (!Serial);

  matrix.begin();
  pinMode(PIN_SW, INPUT_PULLUP);

  while (wifiStatus != WL_CONNECTED) {
    Serial.println("Connecting to WiFi...");
    wifiStatus = WiFi.begin(SSID, pass);
    delay(10000);
  }
  Serial.println("WiFi connected.");
}

// =======================================================================
void loop() {
  maintainPiConnection();
  readIncomingFromPi();

  if (gameState == GS_MY_TURN) {
    updateCursorFromJoystick();
    checkButtonPress();
  }

  updateMatrixDisplay();
  delay(20);
}

// ---------------------------------------------------------------------
void maintainPiConnection() {
  if (!client.connected()) {
    gameState = GS_DISCONNECTED;
    Serial.println("Connecting to Pi game server...");
    if (client.connect(server, port)) {
      Serial.println("Connected to Pi.");
      gameState = GS_WAITING;  // wait for the Pi to say it's our turn
    } else {
      Serial.println("Connection failed, retrying...");
      delay(2000);
    }
  }
}

// ---------------------------------------------------------------------
void readIncomingFromPi() {
  while (client.available()) {
    char c = client.read();
    if (c == '\n') {
      incomingLine.trim();
      if (incomingLine.length() > 0) handlePiMessage(incomingLine);
      incomingLine = "";
    } else if (c != '\r') {
      incomingLine += c;
    }
  }
}

void handlePiMessage(String msg) {
  if (msg == "TURN") {
    gameState = GS_MY_TURN;
  } else if (msg == "WAIT") {
    gameState = GS_WAITING;
  } else if (msg == "INVALID") {
    showMessage("NO");
    gameState = GS_MY_TURN;  // still the player's turn, try another cell
  } else if (msg.startsWith("AIMOVE,")) {
    int r, c;
    if (parsePair(msg.substring(7), r, c)) {
      occupied[r][c] = true;
      flashCell();
    }
  } else if (msg == "WIN") {
    gameState = GS_GAME_OVER;
    showMessage("YOU WIN");
  } else if (msg == "LOSE") {
    gameState = GS_GAME_OVER;
    showMessage("AI WINS");
  } else if (msg == "DRAW") {
    gameState = GS_GAME_OVER;
    showMessage("DRAW");
  } else if (msg == "RESET") {
    for (int r = 0; r < 3; r++)
      for (int c = 0; c < 3; c++)
        occupied[r][c] = false;
    cursorRow = 1;
    cursorCol = 1;
    lastSentCursorRow = -1;
    lastSentCursorCol = -1;
    gameState = GS_WAITING;
  }
}

bool parsePair(String csv, int &a, int &b) {
  int commaIdx = csv.indexOf(',');
  if (commaIdx < 0) return false;
  a = csv.substring(0, commaIdx).toInt();
  b = csv.substring(commaIdx + 1).toInt();
  return true;
}

// ---------------------------------------------------------------------
void updateCursorFromJoystick() {
  int xValue = analogRead(PIN_X);
  int yValue = analogRead(PIN_Y);

  if (xAxisReady) {
    if (xValue < JOY_LOW && cursorCol > 0) {
      cursorCol--;
      xAxisReady = false;
      sendCursorIfChanged();
    } else if (xValue > JOY_HIGH && cursorCol < 2) {
      cursorCol++;
      xAxisReady = false;
      sendCursorIfChanged();
    }
  } else if (xValue > JOY_NEUTRAL_LOW && xValue < JOY_NEUTRAL_HIGH) {
    xAxisReady = true;
  }

  if (yAxisReady) {
    if (yValue < JOY_LOW && cursorRow > 0) {
      cursorRow--;
      yAxisReady = false;
      sendCursorIfChanged();
    } else if (yValue > JOY_HIGH && cursorRow < 2) {
      cursorRow++;
      yAxisReady = false;
      sendCursorIfChanged();
    }
  } else if (yValue > JOY_NEUTRAL_LOW && yValue < JOY_NEUTRAL_HIGH) {
    yAxisReady = true;
  }
}

void sendCursorIfChanged() {
  if (cursorRow != lastSentCursorRow || cursorCol != lastSentCursorCol) {
    lastSentCursorRow = cursorRow;
    lastSentCursorCol = cursorCol;
    client.print("CURSOR,");
    client.print(cursorRow);
    client.print(",");
    client.println(cursorCol);
  }
}

void checkButtonPress() {
  bool buttonState = digitalRead(PIN_SW);
  unsigned long now = millis();
  if (buttonState != lastButtonState && (now - lastButtonChangeMs) > BUTTON_DEBOUNCE_MS) {
    lastButtonChangeMs = now;
    lastButtonState = buttonState;
    if (buttonState == LOW) {  // press (active LOW, INPUT_PULLUP)
      client.print("MOVE,");
      client.print(cursorRow);
      client.print(",");
      client.println(cursorCol);
      gameState = GS_WAITING;  // wait for the Pi to confirm / reject
    }
  }
}

// ---------------------------------------------------------------------
void updateMatrixDisplay() {
  unsigned long now = millis();
  if (now - lastBlinkMs > BLINK_PERIOD_MS) {
    lastBlinkMs = now;
    blinkOn = !blinkOn;
  }

  for (int y = 0; y < MATRIX_H; y++)
    for (int x = 0; x < MATRIX_W; x++)
      frame[y][x] = 0;

  for (int r = 0; r < 3; r++) {
    for (int c = 0; c < 3; c++) {
      bool isCursor = (gameState == GS_MY_TURN && r == cursorRow && c == cursorCol);
      bool lit = isCursor ? blinkOn : occupied[r][c];
      if (lit) {
        for (int dy = 0; dy < 2; dy++)
          for (int dx = 0; dx < 2; dx++)
            frame[ROW_POS[r] + dy][COL_POS[c] + dx] = 1;
      }
    }
  }

  matrix.renderBitmap(frame, MATRIX_H, MATRIX_W);
}

void flashCell() {
  // quick whole-matrix double-flash to draw attention to the AI's move
  for (int i = 0; i < 3; i++) {
    uint8_t v = (i % 2 == 0) ? 1 : 0;
    for (int y = 0; y < MATRIX_H; y++)
      for (int x = 0; x < MATRIX_W; x++)
        frame[y][x] = v;
    matrix.renderBitmap(frame, MATRIX_H, MATRIX_W);
    delay(120);
  }
}

// Short scrolling-text status message. This call is blocking for the
// ~1-2s it takes to scroll, which is fine since it is only used for
// infrequent end-of-turn / end-of-round events.
void showMessage(const char *msg) {
  matrix.beginDraw();
  matrix.stroke(0xFFFFFFFF);
  matrix.textFont(Font_4x6);
  matrix.beginText(0, 1, 0xFFFFFF);
  matrix.println(msg);
  matrix.endText(SCROLL_LEFT);
  matrix.endDraw();
}
