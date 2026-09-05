// rookery firmware
// A USB-serial status light for coding-agent sessions.
//
// Default build drives SIX discrete single-colour LEDs, one per state:
//
//   green   working     slow breathe
//   yellow  idle        steady, dim
//   red     needs you   fast pulse
//   blue    asleep      steady, very dim
//   orange  link lost   slow blink  (the host daemon stopped talking)
//   white   ident       blink on request / boot self-test
//
// Protocol (newline-terminated ASCII, 115200 8N1) -- see docs/protocol.md
//   ->  PING                 <-  PONG rookery <fw>
//   ->  STATE working        <-  OK state working
//   ->  BRIGHT 120           <-  OK bright 120
//   ->  GAIN blue 255        <-  OK gain blue 255
//   ->  IDENT                <-  OK ident
//   ->  OFF                  <-  OK off
//
// Alternate backends (see platformio.ini):
//   -DLED_BACKEND_NEOPIXEL    addressable WS2812B/SK6812 ring
//   -DLED_BACKEND_RGB         single 4-pin common-cathode RGB LED

#include <Arduino.h>

#define FW_VERSION "0.2.0"
#define DEVICE_NAME "rookery"

#if !defined(LED_BACKEND_NEOPIXEL) && !defined(LED_BACKEND_RGB)
#define LED_BACKEND_DISCRETE 1
#endif

#ifndef SERIAL_BAUD
#define SERIAL_BAUD 115200
#endif

// How long without a host message before we assume the link is dead.
#ifndef LINK_TIMEOUT_MS
#define LINK_TIMEOUT_MS 30000UL
#endif

// ---------------------------------------------------------------------------
// State model
// ---------------------------------------------------------------------------

enum State : uint8_t {
  ST_ASLEEP = 0,   // no live sessions
  ST_IDLE,         // sessions open, nothing running
  ST_WORKING,      // at least one session is running
  ST_NEEDS_YOU,    // a session wants your input
  ST_LINK_LOST,    // host daemon stopped talking to us
  ST_MANUAL        // host drove the channels directly
};

static State g_state = ST_ASLEEP;
static uint8_t g_brightness = 160;      // 0..255 master scale
static unsigned long g_lastHostMs = 0;
static bool g_everHeardHost = false;
static unsigned long g_identUntilMs = 0;

// ---------------------------------------------------------------------------
// Channels
// ---------------------------------------------------------------------------

enum Ch : uint8_t {
  CH_RED = 0, CH_GREEN, CH_BLUE, CH_YELLOW, CH_ORANGE, CH_WHITE, CH_COUNT
};

static const char *kChNames[CH_COUNT] = {
  "red", "green", "blue", "yellow", "orange", "white"
};

#if defined(LED_BACKEND_DISCRETE)

// Pins. Defaults are for a classic ESP32 DevKitC and deliberately avoid the
// strapping pins (0, 2, 12, 15), the flash pins (6-11) and the input-only
// pins (34-39). Override any of them in platformio.ini.
#ifndef PIN_RED
#define PIN_RED 25
#endif
#ifndef PIN_GREEN
#define PIN_GREEN 26
#endif
#ifndef PIN_BLUE
#define PIN_BLUE 27
#endif
#ifndef PIN_YELLOW
#define PIN_YELLOW 32
#endif
#ifndef PIN_ORANGE
#define PIN_ORANGE 33
#endif
#ifndef PIN_WHITE
#define PIN_WHITE 13
#endif

static const uint8_t kPins[CH_COUNT] = {
  PIN_RED, PIN_GREEN, PIN_BLUE, PIN_YELLOW, PIN_ORANGE, PIN_WHITE
};

// Per-channel trim, 0..255.
//
// Six LEDs from a parts bin will never be balanced. Red and yellow read much
// brighter to the eye than blue at the same current, and blue/white are
// current-starved on a 3.3 V pin to begin with (their forward voltage is
// close to the supply). So: knock the bright ones down, leave the dim ones
// wide open. Trim to taste at runtime with `GAIN <colour> <0-255>`, then bake
// the values you like into build_flags.
#ifndef GAIN_RED
#define GAIN_RED 150
#endif
#ifndef GAIN_GREEN
#define GAIN_GREEN 200
#endif
#ifndef GAIN_BLUE
#define GAIN_BLUE 255
#endif
#ifndef GAIN_YELLOW
#define GAIN_YELLOW 175
#endif
#ifndef GAIN_ORANGE
#define GAIN_ORANGE 175
#endif
#ifndef GAIN_WHITE
#define GAIN_WHITE 255
#endif

static uint8_t g_gain[CH_COUNT] = {
  GAIN_RED, GAIN_GREEN, GAIN_BLUE, GAIN_YELLOW, GAIN_ORANGE, GAIN_WHITE
};

#elif defined(LED_BACKEND_NEOPIXEL)
#include <Adafruit_NeoPixel.h>
#ifndef LED_PIN
#define LED_PIN 5
#endif
#ifndef LED_COUNT
#define LED_COUNT 12
#endif
static Adafruit_NeoPixel strip(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);

#else  // LED_BACKEND_RGB
#ifndef PIN_R
#define PIN_R 25
#endif
#ifndef PIN_G
#define PIN_G 26
#endif
#ifndef PIN_B
#define PIN_B 27
#endif
#ifndef RGB_COMMON_ANODE
#define RGB_COMMON_ANODE 0
#endif
#endif

// ---------------------------------------------------------------------------
// Optional servo: the penguin turns to look at you when a session needs input
// ---------------------------------------------------------------------------
// Build with -DENABLE_SERVO. Needs a classic ESP32 or an S3: the C3 and C6
// only have six LEDC channels total and the six LEDs already use all of them.

#ifdef ENABLE_SERVO
#include <ESP32Servo.h>

#ifndef PIN_SERVO
#define PIN_SERVO 14
#endif
#ifndef SERVO_REST
#define SERVO_REST 90        // degrees, penguin facing forward
#endif
#ifndef SERVO_SWING
#define SERVO_SWING 28       // how far it turns each way
#endif
#ifndef SERVO_STEP_MS
#define SERVO_STEP_MS 260    // time per swing
#endif
#ifndef SERVO_SETTLE_MS
#define SERVO_SETTLE_MS 700  // hold power this long after a move, then release
#endif

static Servo g_servo;
static bool g_servoAttached = false;
static unsigned long g_detachAt = 0;
static int8_t g_wagLeft = 0;
static unsigned long g_wagNext = 0;

static void servoGo(int deg, unsigned long now) {
  if (!g_servoAttached) {
    g_servo.setPeriodHertz(50);
    g_servo.attach(PIN_SERVO, 500, 2400);
    g_servoAttached = true;
  }
  g_servo.write(constrain(deg, 0, 180));
  g_detachAt = now + SERVO_SETTLE_MS;
}

static void startWag() {
  g_wagLeft = 7;   // six swings, then a settle back to rest
  g_wagNext = 0;   // fire on the next tick
}

static void servoTick(unsigned long now) {
  if (g_wagLeft > 0 && now >= g_wagNext) {
    g_wagLeft--;
    int deg = (g_wagLeft == 0)
                ? SERVO_REST
                : ((g_wagLeft % 2) ? SERVO_REST - SERVO_SWING
                                   : SERVO_REST + SERVO_SWING);
    servoGo(deg, now);
    g_wagNext = now + SERVO_STEP_MS;
  }

  // Detaching stops the PWM once the move is done. Two reasons: a servo that
  // is still being commanded holds torque, hunts, and buzzes audibly on a
  // quiet desk; and it keeps drawing current we'd rather not pull from a USB
  // port. Released, an SG90 draws essentially nothing.
  if (g_servoAttached && g_detachAt && now > g_detachAt && g_wagLeft == 0) {
    g_servo.detach();
    g_servoAttached = false;
    g_detachAt = 0;
  }
}

#define SERVO_TICK(now) servoTick(now)
#define SERVO_ON_NEEDS_YOU() startWag()
#else
#define SERVO_TICK(now) ((void)0)
#define SERVO_ON_NEEDS_YOU() ((void)0)
#endif

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static inline uint8_t scale8(uint8_t v, uint8_t s) {
  return (uint8_t)(((uint16_t)v * (uint16_t)s) / 255);
}

// Cheap gamma. LED brightness is linear in current but the eye is not, so a
// linear PWM ramp looks like it slams to full and then crawls. Squaring gets
// most of the way to a perceptually even fade for one line of code.
static inline uint8_t gamma8(uint8_t v) {
  return (uint8_t)(((uint16_t)v * (uint16_t)v) / 255);
}

static inline uint8_t clamp255(uint16_t v) {
  return v > 255 ? 255 : (uint8_t)v;
}

// Triangle wave 0..255 over `periodMs`.
static uint8_t triWave(unsigned long now, unsigned long periodMs) {
  unsigned long t = now % periodMs;
  unsigned long half = periodMs / 2;
  if (t < half) return (uint8_t)((t * 255UL) / half);
  return (uint8_t)(((periodMs - t) * 255UL) / half);
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

// One brightness per logical colour channel, before gamma/gain/master.
struct Lamp {
  uint8_t v[CH_COUNT];
};

static Lamp lampOff() {
  Lamp l;
  for (uint8_t i = 0; i < CH_COUNT; i++) l.v[i] = 0;
  return l;
}

static void writeLamp(const Lamp &l) {
#if defined(LED_BACKEND_DISCRETE)
  for (uint8_t i = 0; i < CH_COUNT; i++) {
    uint8_t v = gamma8(l.v[i]);
    v = scale8(v, g_gain[i]);
    v = scale8(v, g_brightness);
    analogWrite(kPins[i], v);
  }
#else
  // Fold the six logical channels down to one RGB colour so the alternate
  // backends can share the same animation code.
  uint16_t r = l.v[CH_RED] + l.v[CH_YELLOW] + l.v[CH_ORANGE] + l.v[CH_WHITE];
  uint16_t g = l.v[CH_GREEN] + l.v[CH_YELLOW]
             + (uint16_t)(l.v[CH_ORANGE] * 65 / 255) + l.v[CH_WHITE];
  uint16_t b = l.v[CH_BLUE] + l.v[CH_WHITE];
  uint8_t R = scale8(clamp255(r), g_brightness);
  uint8_t G = scale8(clamp255(g), g_brightness);
  uint8_t B = scale8(clamp255(b), g_brightness);
  R = gamma8(R); G = gamma8(G); B = gamma8(B);
#if defined(LED_BACKEND_NEOPIXEL)
  uint32_t packed = strip.Color(R, G, B);
  for (uint16_t i = 0; i < LED_COUNT; i++) strip.setPixelColor(i, packed);
  strip.show();
#else
#if RGB_COMMON_ANODE
  R = 255 - R; G = 255 - G; B = 255 - B;
#endif
  analogWrite(PIN_R, R);
  analogWrite(PIN_G, G);
  analogWrite(PIN_B, B);
#endif
#endif
}

// ---------------------------------------------------------------------------
// Animation
// ---------------------------------------------------------------------------

static Lamp g_manual = lampOff();

// Animation levels, 0..255, before gamma/gain/master brightness.
//
// These are NOT balanced by eye across colours on purpose -- they compensate
// for physics. Blue and white sit at 24-40% duty while yellow sits at 11%,
// because a blue LED on a 3.3 V pin only gets a couple of milliamps (its
// forward voltage is nearly the supply) while yellow gets a comfortable
// seven. Equal duty would make blue invisible. If your blue is still too
// faint, raise LVL_ASLEEP or see docs/hardware/wiring.md for the transistor fix.
#ifndef LVL_WORK_MIN
#define LVL_WORK_MIN 115
#endif
#ifndef LVL_WORK_SPAN
#define LVL_WORK_SPAN 140
#endif
#ifndef LVL_NEEDS_MIN
#define LVL_NEEDS_MIN 100
#endif
#ifndef LVL_NEEDS_SPAN
#define LVL_NEEDS_SPAN 155
#endif
#ifndef LVL_IDLE
#define LVL_IDLE 130
#endif
#ifndef LVL_LOST
#define LVL_LOST 210
#endif
#ifndef LVL_ASLEEP
#define LVL_ASLEEP 150
#endif

static Lamp renderState(unsigned long now) {
  Lamp l = lampOff();

  // IDENT overrides everything: white blink so you can find the device.
  if (now < g_identUntilMs) {
    l.v[CH_WHITE] = (((now / 120) % 2) == 0) ? 255 : 0;
    return l;
  }

  switch (g_state) {
    case ST_MANUAL:
      return g_manual;

    case ST_WORKING:
      // Calm breathe.
      l.v[CH_GREEN] = LVL_WORK_MIN + scale8(LVL_WORK_SPAN, triWave(now, 2600));
      break;

    case ST_NEEDS_YOU:
      // Faster and more insistent.
      l.v[CH_RED] = LVL_NEEDS_MIN + scale8(LVL_NEEDS_SPAN, triWave(now, 900));
      break;

    case ST_IDLE:
      l.v[CH_YELLOW] = LVL_IDLE;
      break;

    case ST_LINK_LOST:
      // Short blink on a long cycle: present, obviously not a normal state,
      // and easy to tell apart from steady yellow at a glance.
      l.v[CH_ORANGE] = ((now % 4000) < 260) ? LVL_LOST : 0;
      break;

    case ST_ASLEEP:
    default:
      l.v[CH_BLUE] = LVL_ASLEEP;
      break;
  }
  return l;
}

// ---------------------------------------------------------------------------
// Command parsing
// ---------------------------------------------------------------------------

static bool parseState(const char *name, State &out) {
  if (!strcasecmp(name, "working")) { out = ST_WORKING; return true; }
  if (!strcasecmp(name, "idle")) { out = ST_IDLE; return true; }
  if (!strcasecmp(name, "needs_you") || !strcasecmp(name, "needs")) {
    out = ST_NEEDS_YOU; return true;
  }
  if (!strcasecmp(name, "asleep") || !strcasecmp(name, "off")) {
    out = ST_ASLEEP; return true;
  }
  return false;
}

static int parseChannel(const char *name) {
  for (uint8_t i = 0; i < CH_COUNT; i++) {
    if (!strcasecmp(name, kChNames[i])) return i;
  }
  // Also accept a bare index.
  if (name[0] >= '0' && name[0] <= '5' && name[1] == '\0') return name[0] - '0';
  return -1;
}

static void handleLine(char *line) {
  size_t n = strlen(line);
  while (n > 0 && (line[n - 1] == '\r' || line[n - 1] == ' ' ||
                   line[n - 1] == '\t')) {
    line[--n] = '\0';
  }
  if (n == 0) return;

  g_lastHostMs = millis();
  g_everHeardHost = true;
  if (g_state == ST_LINK_LOST) g_state = ST_ASLEEP;

  char *cmd = strtok(line, " ");
  if (!cmd) return;

  if (!strcasecmp(cmd, "PING")) {
    Serial.printf("PONG %s %s\n", DEVICE_NAME, FW_VERSION);
    return;
  }

  if (!strcasecmp(cmd, "STATE")) {
    char *arg = strtok(nullptr, " ");
    State s;
    if (arg && parseState(arg, s)) {
      // Only on the TRANSITION into needs_you. The daemon re-sends the
      // current state every 8 s as a heartbeat, so reacting to the value
      // rather than the change would make the penguin wag forever.
      if (s == ST_NEEDS_YOU && g_state != ST_NEEDS_YOU) SERVO_ON_NEEDS_YOU();
      g_state = s;
      Serial.printf("OK state %s\n", arg);
    } else {
      Serial.println("ERR state");
    }
    return;
  }

  if (!strcasecmp(cmd, "LED")) {
    // LED <colour> <0-255> -- light one channel directly.
    char *cs = strtok(nullptr, " ");
    char *vs = strtok(nullptr, " ");
    int ch = cs ? parseChannel(cs) : -1;
    if (ch >= 0 && vs) {
      g_manual = lampOff();
      g_manual.v[ch] = (uint8_t)constrain(atoi(vs), 0, 255);
      g_state = ST_MANUAL;
      Serial.printf("OK led %s\n", kChNames[ch]);
    } else {
      Serial.println("ERR led");
    }
    return;
  }

  if (!strcasecmp(cmd, "GAIN")) {
    char *cs = strtok(nullptr, " ");
    char *vs = strtok(nullptr, " ");
    int ch = cs ? parseChannel(cs) : -1;
    if (ch >= 0 && vs) {
#if defined(LED_BACKEND_DISCRETE)
      g_gain[ch] = (uint8_t)constrain(atoi(vs), 0, 255);
      Serial.printf("OK gain %s %u\n", kChNames[ch], g_gain[ch]);
#else
      Serial.println("OK gain ignored");
#endif
    } else {
      Serial.println("ERR gain");
    }
    return;
  }

  if (!strcasecmp(cmd, "BRIGHT")) {
    char *arg = strtok(nullptr, " ");
    if (arg) {
      g_brightness = (uint8_t)constrain(atoi(arg), 0, 255);
      Serial.printf("OK bright %u\n", g_brightness);
    } else {
      Serial.println("ERR bright");
    }
    return;
  }

  if (!strcasecmp(cmd, "WAG")) {
#ifdef ENABLE_SERVO
    startWag();
    Serial.println("OK wag");
#else
    Serial.println("OK wag ignored");
#endif
    return;
  }

  if (!strcasecmp(cmd, "IDENT")) {
    g_identUntilMs = millis() + 2000;
    Serial.println("OK ident");
    return;
  }

  if (!strcasecmp(cmd, "OFF")) {
    g_state = ST_ASLEEP;
    Serial.println("OK off");
    return;
  }

  Serial.println("ERR unknown");
}

static void pumpSerial() {
  static char buf[96];
  static size_t len = 0;

  while (Serial.available() > 0) {
    int ch = Serial.read();
    if (ch < 0) break;
    if (ch == '\n') {
      buf[len] = '\0';
      handleLine(buf);
      len = 0;
    } else if (len < sizeof(buf) - 1) {
      buf[len++] = (char)ch;
    } else {
      len = 0;  // overlong line: discard rather than run a truncated command
    }
  }
}

// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(SERIAL_BAUD);

#if defined(LED_BACKEND_DISCRETE)
  for (uint8_t i = 0; i < CH_COUNT; i++) {
    pinMode(kPins[i], OUTPUT);
    analogWrite(kPins[i], 0);
  }
#elif defined(LED_BACKEND_NEOPIXEL)
  strip.begin();
  strip.setBrightness(255);
  strip.clear();
  strip.show();
#else
  pinMode(PIN_R, OUTPUT);
  pinMode(PIN_G, OUTPUT);
  pinMode(PIN_B, OUTPUT);
#endif

  // Boot self-test: walk every channel in order. If one never lights, you
  // know which LED or solder joint to look at before you write any software.
  for (uint8_t i = 0; i < CH_COUNT; i++) {
    Lamp l = lampOff();
    l.v[i] = 255;
    writeLamp(l);
    delay(180);
  }
  writeLamp(lampOff());

  g_lastHostMs = millis();
  Serial.printf("READY %s %s channels=%d\n", DEVICE_NAME, FW_VERSION, CH_COUNT);
}

void loop() {
  pumpSerial();

  unsigned long now = millis();

  // Link watchdog. Only engages once we've actually heard from a host, so a
  // board sitting on the bench without a daemon just stays asleep.
  if (g_everHeardHost && g_state != ST_LINK_LOST &&
      (now - g_lastHostMs) > LINK_TIMEOUT_MS) {
    g_state = ST_LINK_LOST;
  }

  SERVO_TICK(now);
  writeLamp(renderState(now));
  delay(16);  // ~60 Hz
}
