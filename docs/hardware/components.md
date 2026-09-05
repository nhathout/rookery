# Components

Everything that goes into one penguin, with the numbers you need when you are
holding the part.

If you own a 3D printer and a parts drawer, you probably have all of this
already. There is nothing exotic here and nothing that has to come from one
supplier — the only genuinely fussy item is the USB cable, and only because
half the ones in a drawer are power-only.

| Item | Qty | Notes |
|---|---|---|
| ESP32-S3 dev board | 1 | Classic ESP32, C3 and C6 also supported |
| LEDs — red, green, blue, yellow, orange, white | 1 each | 5 mm or 3 mm through-hole |
| Resistors, 100–330 Ω | 6 | Values vary by colour |
| M3 heat-set inserts | 4 | 4.0 mm OD, 5 mm long |
| M3 × 1/4" screws | 4 | Standard PC case screws |
| Hookup wire | — | Stranded, 26–28 AWG |
| **USB cable that carries data** | 1 | Not a charge-only cable |
| Zip ties, small | 2 | One on the loom, one on the cable |
| Black filament | ~105 g | Body, back cover, beak |
| White or natural filament | ~57 g | Belly, chassis, eyes |
| *Optional:* rubber feet | 4 | |

Substituting anything below means checking it against
[wiring.md](wiring.md) and [pinout.md](pinout.md) as well as this page — and
if it changes a dimension, [enclosure.md](enclosure.md), because the printed
parts are built around these numbers.

---

## ESP32-S3 dev board

| | |
|---|---|
| **Exact model** | Espressif ESP32-S3-DevKitC-1 (`board = esp32-s3-devkitc-1`) |
| **Quantity** | 1 |
| **Purpose** | Runs the firmware, holds one GPIO per LED, and is the USB serial device the daemon talks to |
| **Operating voltage** | 3.3 V logic. Powered entirely from the USB port that also carries the serial data |
| **Interface** | USB CDC at 115200 8N1. The default build routes Serial to the **native USB** port |
| **Board size** | 63.5 × 25.5 mm — `BOARD_L` / `BOARD_W`. **Measure yours** if it is not this board |
| **Mounting** | Four printed posts and four snap tabs. The DevKitC-1 has no mounting holes |
| **Limits** | A GPIO's absolute maximum is 40 mA and the recommended continuous figure is 12 mA. This design runs one LED at ~7 mA, so it is nowhere near either. Do not hang a motor off a pin |

**Which socket.** A DevKitC-1 has two USB-C sockets: `USB` (native, wired
straight to the chip) and `UART` (the CP2102/CH343 bridge). The default env
sets `ARDUINO_USB_CDC_ON_BOOT=1`, which routes Serial to the **native** one.
If your board has only one socket, that's the native one and you're already
correct. To use the bridge instead, build `esp32s3-uart` and plug into `UART`.

**Other boards.** All of these have a build env in
[`platformio.ini`](../../firmware/platformio.ini):

| Board | Env | Note |
|---|---|---|
| ESP32-S3-DevKitC-1 | `esp32s3` | Default. 8 LEDC channels — room for six LEDs plus a servo |
| Classic ESP32 / WROOM-32 / NodeMCU-32S | `esp32dev` | Also has room for a servo |
| ESP32-C3 | `esp32c3` | Exactly 6 LEDC channels; the LEDs use all of them. **No servo** |
| ESP32-C6 | `esp32c6` | Same |

Pin numbers for each: [pinout.md](pinout.md).

## LEDs

| | |
|---|---|
| **Exact part** | Six 5 mm through-hole LEDs, one each in red, green, blue, yellow, orange and white. Clear or diffused |
| **Quantity** | 6 |
| **Purpose** | One colour per state. Only ever one is lit |
| **Forward voltage** | Red 2.0 V · Yellow 2.1 V · Orange 2.0 V · Green 2.2 V · **Blue 3.0–3.2 V** · **White 3.0–3.4 V** |
| **Current, as built** | ~5–7 mA on red/yellow/orange/green; **~2 mA** on blue and white |
| **Interface** | One ESP32 GPIO each, through a resistor. Common cathode bus to GND |
| **Body length** | 8.6 mm dome tip to flange (5 mm LEDs); 5.8 mm for 3 mm LEDs |
| **Flange diameter** | 5.9 mm. This is the only thing stopping an LED going out the front of the belly, so it has to be wider than the 5.4 mm bore |
| **How it sits** | Pushed in from the back until the flange lands: 5.6 mm inside the plate, **3.0 mm of dome proud** of the belly |
| **Limits** | Blue and white cannot get more than ~2 mA from a 3.3 V pin — their forward voltage is nearly the whole supply. That is physics, not a fault; the firmware compensates with duty. See [wiring.md](wiring.md) for the two stronger fixes |

3 mm LEDs work: `python3 generate.py --led-d 3.0` reprints the belly with the
right bore and seat depth. Anything else — different flange, different body
length — means measuring yours and editing `LED_BODY` and `LED_FLANGE_D`.

> **Sand the domes.** A clear 5 mm LED throws a ~20° beam: hard and bright
> head-on, nearly gone from the side. Rub each one flat on 400-grit until it
> is frosted and it reads the same from anywhere in the room. Two minutes, no
> cost, and it is the single biggest improvement you can make to how this
> looks.

## Resistors

| | |
|---|---|
| **Exact part** | Axial 1/4 W carbon or metal film, 100–330 Ω |
| **Quantity** | 6 — one per LED |
| **Values** | 220 Ω red / yellow / orange · 150 Ω green · 100 Ω blue / white |
| **Purpose** | Set the current per colour. Different forward voltages mean equal resistors give unequal brightness |
| **Fit** | Presses into a 3.0 × 3.4 mm channel on the back of the belly, 32 mm long — three axial resistors end to end in each of two channels |
| **Limits** | Anything in the 100–330 Ω band works. This runs dim on purpose. Dropping blue and white to 47 Ω, or shorting them, is a documented option |

Full table with the resulting current per colour: [wiring.md](wiring.md).

## M3 heat-set inserts

| | |
|---|---|
| **Exact part** | Brass knurled heat-set insert for M3, **4.0 mm OD × 5.0 mm long** |
| **Quantity** | 4 — all in the body, all for the back cover |
| **Pocket** | Cut **3.85 mm**: 0.15 mm under the insert, which is the material the iron melts and the knurls bite into. A pocket at nominal OD leaves nothing to grip and the insert spins the first time you tighten a screw |
| **Lead-in** | 0.8 mm at 45°, so a straight start is easy |
| **Install** | Iron at ~200 °C for PLA. Let its own weight carry the insert in; stop flush |
| **Limits** | 3.0 mm and 5.7 mm lengths also fit the pocket depth. A different **diameter** does not — measure yours and reprint with `--insert-od` |

## M3 × 1/4" screws

| | |
|---|---|
| **Exact part** | M3 × 1/4" (6.35 mm under-head) pan or button head — the standard PC case screw, e.g. Micro Connectors `SCW-50M3`. M3 × 6 mm is the same thing |
| **Quantity** | 4 |
| **Purpose** | Back cover into the body's inserts. The only fasteners in the build |
| **Clearance hole** | 3.4 mm through the 3.0 mm cover |
| **Limits** | Snug, not tight — you are clamping a printed part. There is 2 mm of empty bore past the insert for the tip, so a slightly longer screw will not bottom out, but it will not gain you engagement either |

## USB cable

| | |
|---|---|
| **Exact part** | A USB-A or USB-C to USB-C cable **that carries data** |
| **Quantity** | 1 |
| **Purpose** | Power, serial, and flashing. There is no other supply |
| **Limits** | Plenty of cables in a drawer are power-only with no data lines. If the board never shows up in `rookery ports`, swap the cable before debugging anything else. It is the single most common failure in this build |

## Hookup wire and zip ties

| | |
|---|---|
| **Wire** | Stranded, 26–28 AWG. Seven conductors from the belly to the board: six anodes and the ground bus |
| **Zip ties** | Small. One through a cable-tie arch on the belly to hold the loom; one at the back cover for strain relief on the USB cable |
| **Arch tunnel** | 6 mm wide × 3.2 mm of headroom. Four arches, one above and one below each resistor channel |
| **Limits** | Keep the loom **inboard of the lip**. The lip is what the two white halves close on, and a wire lying across it holds them apart |

## Filament

| | |
|---|---|
| **Black** | ~105 g — body, back cover, beak |
| **White or natural** | ~57 g — belly, chassis, eyes |
| **Material** | PLA. Settings and plates: [printing.md](printing.md) |
| **Limits** | **The belly is the part that has to be white** — it is the panel you see through the window. The chassis behind it is never visible once the thing is shut, so print it in whatever you have most of |

---

## Optional

### Micro servo

Not part of the shipped build — **the enclosure has no servo mount**. The
firmware still carries the support, and the head and base cavities are empty
on purpose.

| | |
|---|---|
| **Part** | SG90-class 9 g micro servo |
| **Power** | The board's **5V / VIN** pin, never `3V3` |
| **Signal** | 3.3 V PWM straight from a GPIO — no level shifter |
| **Current** | ~150–250 mA moving under light load; **~650–750 mA stalled** |
| **Also needs** | 470–1000 µF electrolytic across its supply, physically close to the servo |
| **Limits** | Needs an S3 or a classic ESP32 — the C3 and C6 have exactly six LEDC channels and the LEDs use all of them. A stalled servo will trip a PC's port current limit |

The arithmetic, the circuit and the calibration: [motion.md](motion.md).

### WS2812B ring

The alternative to six discrete LEDs: one addressable ring behind a thinned
belly. Three wires instead of thirteen, no resistors, no per-colour trim.

| | |
|---|---|
| **Part** | 12-LED WS2812B / SK6812 ring module |
| **Size** | 37 mm OD, 23 mm ID, 2.2 mm thick — **measure yours**, 12-LED rings are commonly 37 mm but not universally |
| **Power** | 5 V from the board's `5V` pin |
| **Interface** | One data GPIO |
| **Build** | Firmware `env:esp32s3-neopixel`; enclosure `python3 generate.py --leds ring --ring-od 37 --ring-id 23` |
| **Limits** | Twelve WS2812Bs at full white are **700 mA**. That is a real change to the power story — the discrete build's whole claim is one LED at a few milliamps with no capacitor. Cap the brightness in firmware |

Why it exists, and what it costs: [../production.md](../production.md).

---

## Next

- Where each one goes on the board: [pinout.md](pinout.md)
- The circuit: [wiring.md](wiring.md)
- Print the parts: [printing.md](printing.md)
- Build it: [assembly.md](assembly.md)
