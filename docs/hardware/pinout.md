# Pinout

**Source of truth:** the `build_flags` in
[`firmware/platformio.ini`](../../firmware/platformio.ini). Nothing here is
compiled into the firmware — every pin is a `-D` on the build env, and
[`main.cpp`](../../firmware/src/main.cpp) only supplies a fallback if you
build without one. If this page and that file ever disagree, that file wins.

Six GPIOs, one per LED, plus one optional servo pin. There is no bus, no
address, no shared line — just six outputs and a common ground.

---

## By board

| Colour | State | `esp32s3` | `esp32dev` | `esp32c3` | `esp32c6` |
|---|---|---|---|---|---|
| Red | needs you | **4** | **25** | **0** | **0** |
| Green | working | **5** | **26** | **1** | **1** |
| Blue | asleep | **6** | **27** | **3** | **2** |
| Yellow | idle | **7** | **32** | **4** | **3** |
| Orange | link lost | **15** | **33** | **5** | **10** |
| White | ident / self-test | **16** | **13** | **6** | **11** |
| *Servo (optional)* | | **17** | **14** | — | — |

The servo envs are `esp32s3-penguin` and `esp32dev-penguin`. There is no C3
or C6 servo env, and that is not an oversight — see the channel budget below.

Build the one you want:

```bash
pio run -e esp32s3 -t upload        # the default
pio run -e esp32c6 -t upload
pio run -e esp32s3-penguin -t upload
```

Build with no `-e` at all and PlatformIO builds every env in the file. The
fallback pins compiled into `main.cpp` are the classic ESP32 map (25, 26, 27,
32, 33, 13; servo 14), so an env that defines nothing still produces a
working classic-ESP32 binary.

## What each chip reserves

The S3 and classic ESP32 maps are audited against everything their chip takes
for itself. That audit is a comment in `platformio.ini`, and it is the reason
the pin numbers look arbitrary:

| Chip | Do not use | Why |
|---|---|---|
| **ESP32-S3** | 0, 3, 45, 46 | Strapping pins — held at boot to select boot mode |
| | 19, 20 | Native USB D− / D+ |
| | 26–32 | SPI flash |
| | 33–37 | Octal PSRAM |
| | 43, 44 | UART0 |
| | 38 or 48 | Onboard RGB LED — 38 on DevKitC-1 v1.0, 48 on v1.1 |
| **Classic ESP32** | 0, 2, 12, 15 | Strapping pins |
| | 6–11 | SPI flash |
| | 34–39 | Input-only — they cannot drive an LED at all |

If you move a pin on a C3 or C6, check that chip's own reserved list first.
The maps in the file work; they have not been written up here the way the
other two have.

## The LEDC channel budget

Every LED is driven by `analogWrite`, which on ESP32 means an LEDC PWM
channel. That is a finite resource and it is the whole reason the servo is
board-dependent:

| Chip | LEDC channels | Six LEDs | Servo |
|---|---|---|---|
| ESP32-S3 | 8 | 6 | fits — 7 of 8 |
| Classic ESP32 | 16 (8 high-speed + 8 low-speed) | 6 | fits easily |
| ESP32-C3 | 6 | 6 | **no room** |
| ESP32-C6 | 6 | 6 | **no room** |

If the servo jitters or the LEDs flicker when it moves on an S3, the
peripheral is being asked to serve two very different clock configurations at
once — the LEDs at ~1 kHz / 8-bit, the servo at 50 Hz / 16-bit. See
[motion.md](motion.md).

## Alternate LED backends

Two other envs exist for people who want to swap the six discrete LEDs for
something else. Both fold the six logical channels down to one RGB colour in
firmware, so the animations are unchanged.

| Env | Backend | Pins |
|---|---|---|
| `esp32s3-neopixel` | `-DLED_BACKEND_NEOPIXEL` | `LED_PIN=4`, `LED_COUNT=12` |
| `esp32s3-rgb` | `-DLED_BACKEND_RGB` | `PIN_R=4`, `PIN_G=5`, `PIN_B=6`. Add `-DRGB_COMMON_ANODE=1` for a common-anode part |

`GAIN` is a no-op on both — it replies `OK gain ignored`, because per-channel
trim only means something when the channels are physically different LEDs.

## Serial

| | |
|---|---|
| Baud | 115200, 8N1 |
| Port | Native USB by default (`ARDUINO_USB_CDC_ON_BOOT=1`); `esp32s3-uart` uses the bridge instead |
| Protocol | Newline-terminated ASCII — [../protocol.md](../protocol.md) |

## Moving a pin

1. Change the `-DPIN_<COLOUR>=` flag in the right env in
   [`platformio.ini`](../../firmware/platformio.ini). Do not edit
   `main.cpp` — its defines are fallbacks, and editing them changes every
   board at once.
2. Check the new pin against the reserved table above for that chip.
3. Update the channel map in [wiring.md](wiring.md) and the table on this
   page in the same change.
4. Reflash and watch the boot self-test. The firmware walks all six channels
   in order on every boot, so a pin that went to the wrong place shows up in
   the first two seconds.

---

## Next

- The circuit those pins drive: [wiring.md](wiring.md)
- What is on the other end: [components.md](components.md)
- What the host sends down the wire: [../protocol.md](../protocol.md)
