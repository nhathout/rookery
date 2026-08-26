# Wiring & assembly

Six discrete single-colour LEDs, one GPIO each, sharing a common ground, behind
a backlit belly. Nothing to buy — this is a parts-drawer build.

## Channel map

| Colour | State | Behaviour | ESP32-S3 | Classic ESP32 |
|---|---|---|---|---|
| Green | working | Slow breathe | GPIO5 | GPIO26 |
| Yellow | idle | Steady, dim | GPIO7 | GPIO32 |
| Red | needs you | Fast pulse | GPIO4 | GPIO25 |
| Blue | asleep | Steady, very dim | GPIO6 | GPIO27 |
| Orange | link lost | Slow blink | GPIO15 | GPIO33 |
| White | ident / self-test | Blink on request | GPIO16 | GPIO13 |

The S3 pins are audited against everything that chip reserves: strapping pins
(0, 3, 45, 46), native USB (19, 20), SPI flash (26–32), octal PSRAM (33–37),
UART0 (43, 44), and the onboard RGB LED (38 on DevKitC-1 v1.0, 48 on v1.1).

> **Which USB socket?** An S3 DevKitC-1 has two. The default build routes
> Serial to the **native USB** port (marked `USB`). If your board has only one
> socket, that's it. To use the `UART` bridge instead, build `esp32s3-uart`.

## The circuit

Six copies of the same thing. All cathodes to one ground rail.

```
  ESP32-S3

  GPIO4  ──[ 220Ω ]──▶|── RED     ─┐
  GPIO5  ──[ 150Ω ]──▶|── GREEN   ─┤
  GPIO6  ──[ 100Ω ]──▶|── BLUE    ─┤
  GPIO7  ──[ 220Ω ]──▶|── YELLOW  ─┼── GND
  GPIO15 ──[ 220Ω ]──▶|── ORANGE  ─┤
  GPIO16 ──[ 100Ω ]──▶|── WHITE   ─┘

  ▶|  = LED, arrow points anode → cathode.
        The LONG leg is the anode (resistor / GPIO side).
        The flat spot on the rim marks the cathode.
```

## Resistor values, and why they differ

Different colours have different forward voltages, so equal resistors give
unequal brightness. Targeting roughly 7 mA:

| Colour | Typical Vf | Resistor | Result |
|---|---|---|---|
| Red | 2.0 V | 220 Ω | ~6 mA |
| Yellow | 2.1 V | 220 Ω | ~5 mA |
| Orange | 2.0 V | 220 Ω | ~6 mA |
| Green (standard) | 2.2 V | 150 Ω | ~7 mA |
| Blue | 3.0–3.2 V | 100 Ω | ~2 mA ⚠ |
| White | 3.0–3.4 V | 100 Ω | ~2 mA ⚠ |

Anything in the 100–330 Ω range works. This runs dim on purpose.

### ⚠ The blue and white problem

**Blue and white LEDs have a forward voltage of about 3.0–3.4 V, and an ESP32
GPIO only puts out 3.3 V** — less under load. There's almost no headroom to
push current through a resistor, so those two channels get ~2 mA instead of
~7 mA and look weak next to the others.

Three ways to handle it, easiest first:

1. **Do nothing.** The firmware compensates: blue and white run at higher PWM
   duty (22% and 63%) than yellow (11%), and their `GAIN` trims ship at
   maximum. Behind the diffuser belly this is usually fine, and blue only
   signals "nothing is running".
2. **Drop the resistor** to 47 Ω, or short it, on blue and white only.
   Slightly naughty, entirely normal for indicators, and PWM keeps average
   current low.
3. **Drive them from 5 V through a transistor** — see [MOTOR.md](MOTOR.md) for
   the circuit. Worth doing if you have transistors around.

If green looks dim too, you have a "pure green" InGaN LED (Vf ≈ 3.2 V) rather
than a standard one — same problem, same fixes.

### Trimming brightness without reflashing

```
GAIN blue 255
GAIN red 120
BRIGHT 200
```

Sit in a serial monitor, run `rookery test` in another terminal, and tweak
until the six colours read evenly. Then bake the values into `build_flags` —
`env:esp32s3-tuned` in `platformio.ini` exists for that.

## Current budget

Only one LED is lit at a time, always under 63% duty, so peak draw is a single
LED — call it 7 mA. Well under the 20 mA-per-pin recommendation. No capacitor,
no level shifter, no external supply.

## The printed parts and how it goes together

That's a separate document, because it's a separate job:
**[`stl/README.md`](stl/README.md)** covers what to print, in which filament,
on which plate, and in what order to bolt it together.

The short version: five printed parts, four M3 heat-set inserts, and four
M3 × 1/4" screws that are all the same screw. Everything electrical mounts
inside the `chassis` — the white box whose front face is the penguin's belly
— so the whole loom is built on one part, on the bench, and drops into the
body in a single move.

## Where the LEDs sit

```
       back                                                  front
     y = 0            y = 14       y = 30..33              y = 48
       |                |              |                      |
  [ back cover ]   [ chassis rear ] [ LED shelf ]        [ belly face ]
       |                               | 6 LEDs               |
       |                          [ dev board ]     40 x 64 mm of glow
       |                          on posts behind
       |                          the shelf
```

Six LEDs in a 17 mm circle, 9.4 mm behind a 40 × 64 mm panel, one lit at a
time. Three things stop that reading as six bright spots:

1. **The box.** The chassis is white on all six inside faces, so the light
   chamber is its own diffuser: what does not go straight out the front
   bounces around until it does.
2. **The pixel grid.** The same 8 mm grid as the body is engraved 0.6 mm
   into the belly face, which breaks the panel into 5 × 8 lit squares. It
   hides the fall-off between LEDs by giving the eye something deliberate to
   read instead.
3. **Sanding the LEDs.** Rub the dome of each one flat on 400-grit until
   it's frosted. A clear 5 mm LED throws a ~20° beam; a frosted one
   scatters far wider. Two minutes, no cost, and it makes more difference
   than either of the other two.

The LEDs go in from the back, dome first: the little flange at the base of a
5 mm LED catches on the shelf and sets the height for you, and nothing
protrudes behind it to foul the dev board 3.5 mm further back.

The head is part of the same cavity, so spill light reaches the two
translucent eye plugs and they glow faintly in whatever colour is currently
showing. It's subtle — best in a dim room — and it's a bonus rather than a
feature. Printing the eyes in natural or clear filament rather than white
makes it noticeably stronger.

## Bill of materials

| Item | Qty | Notes |
|---|---|---|
| ESP32-S3 dev board | 1 | Classic ESP32, C3 and C6 also supported |
| LEDs — red, green, blue, yellow, orange, white | 1 each | 5 mm (or 3 mm, see `--led-d`) |
| Resistors, 100–330 Ω | 6 | Values per the table above |
| M3 heat-set inserts | 4 | 4.0 mm OD × 5 mm long |
| M3 × 1/4" screws | 4 | PC case screws — e.g. Micro Connectors `SCW-50M3`. M3 × 6 mm pan head is the same thing. |
| Hookup wire | — | Stranded, 26–28 AWG |
| **USB cable that carries data** | 1 | Not a charge-only cable |
| Zip tie, small | 1 | Strain relief on the cable |
| Black filament | ~83 g | Body, back cover, beak |
| White or natural filament | ~56 g | Chassis and eyes |
| *Optional:* rubber feet | 4 | |

The thing that still trips people up: **the cable**. Plenty of USB cables in
a drawer are power-only with no data lines. If the board never shows up in
`rookery ports`, swap the cable before debugging anything else.
