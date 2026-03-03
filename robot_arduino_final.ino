// ============================================================
// ROBOT CAPIT - ARDUINO UNO (FINAL MERGE)
// Pin dari kode kedua yang terbukti gerak:
//   Stepper XY : STEP1=4, DIR1=5, STEP2=3, DIR2=2
//   Enable     : EN_PIN1=8, EN_PIN2=9
// Tambahan dari kode pertama:
//   Stepper Z  : STEP_PIN2=4, DIR_PIN2=5  (sesuaikan jika beda)
// ============================================================

// --- STEPPER X (kiri-kanan frame) --- dari kode kedua yg terbukti jalan
#define STEP1     4
#define DIR1      5

// --- STEPPER Y (maju-mundur) --- dari kode kedua
#define STEP2     3
#define DIR2      2

// --- ENABLE PIN ---
#define EN_PIN1   8
#define EN_PIN2   9

// --- STEPPER Z (lengan naik-turun) + CAPIT --- SESUAIKAN PIN INI
#define STEP_Z    6
#define DIR_Z     7
#define EN_PINZ   10

// --- STEPPER CONFIG ---
#define STEPS_XY      500     // langkah per command X/Y (dari kode kedua)
#define STEPS_Z       400     // langkah per command naik/turun lengan
#define DELAY_US      500     // jeda antar pulse (us)

// ============================================================
String inputBuffer = "";
bool   messageReady = false;

void setup() {
  Serial.begin(9600);

  pinMode(STEP1,   OUTPUT); pinMode(DIR1,   OUTPUT);
  pinMode(STEP2,   OUTPUT); pinMode(DIR2,   OUTPUT);
  pinMode(STEP_Z,  OUTPUT); pinMode(DIR_Z,  OUTPUT);

  pinMode(EN_PIN1, OUTPUT); pinMode(EN_PIN2, OUTPUT); pinMode(EN_PINZ, OUTPUT);

  // LOW = aktifkan driver A4988
  digitalWrite(EN_PIN1, LOW);
  digitalWrite(EN_PIN2, LOW);
  digitalWrite(EN_PINZ, LOW);

  Serial.println("ARDUINO SIAP, KETUA!");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') messageReady = true;
    else           inputBuffer += c;
  }

  if (messageReady) {
    inputBuffer.trim();
    // Buang tanda < dan >
    if (inputBuffer.startsWith("<")) inputBuffer = inputBuffer.substring(1);
    if (inputBuffer.endsWith(">"))   inputBuffer = inputBuffer.substring(0, inputBuffer.length() - 1);

    prosesCommand(inputBuffer);
    inputBuffer  = "";
    messageReady = false;
  }
}

// ============================================================
void prosesCommand(String cmd) {
  Serial.print("CMD: "); Serial.println(cmd);

  // --- GERAK X & Y (2 stepper jalan barengan) ---
  if      (cmd == "MAJU")         jalaninMotor(HIGH, HIGH);
  else if (cmd == "MUNDUR")       jalaninMotor(LOW,  LOW);
  else if (cmd == "KIRI")         jalaninMotor(LOW,  HIGH);
  else if (cmd == "KANAN")        jalaninMotor(HIGH, LOW);

  // --- GERAK Z (lengan) ---
  else if (cmd == "LENGAN_TURUN") stepperZ(HIGH, STEPS_Z);
  else if (cmd == "LENGAN_NAIK")  stepperZ(LOW,  STEPS_Z);

  // --- CAPIT ---
  else if (cmd == "CAPIT_CLOSE")  stepperZ(HIGH, STEPS_Z);  // samain arah turun, sesuaikan kalau perlu
  else if (cmd == "CAPIT_OPEN")   stepperZ(LOW,  STEPS_Z);

  // STOP tidak perlu aksi karena stepper non-blocking tidak ada yang perlu dihentikan
  else if (cmd == "STOP") { /* diam */ }
}

// ============================================================
// Gerak 2 stepper XY barengan — logika dari kode kedua yg terbukti jalan
// ============================================================
void jalaninMotor(int arah1, int arah2) {
  digitalWrite(DIR1, arah1);
  digitalWrite(DIR2, arah2);
  for (int x = 0; x < STEPS_XY; x++) {
    digitalWrite(STEP1, LOW);
    digitalWrite(STEP2, LOW);
    delayMicroseconds(DELAY_US);
    digitalWrite(STEP1, HIGH);
    digitalWrite(STEP2, HIGH);
    delayMicroseconds(DELAY_US);
  }
}

// ============================================================
// Gerak stepper Z (lengan / capit)
// ============================================================
void stepperZ(int arah, int steps) {
  digitalWrite(DIR_Z, arah);
  delayMicroseconds(5);
  for (int i = 0; i < steps; i++) {
    digitalWrite(STEP_Z, HIGH);
    delayMicroseconds(DELAY_US);
    digitalWrite(STEP_Z, LOW);
    delayMicroseconds(DELAY_US);
  }
}
