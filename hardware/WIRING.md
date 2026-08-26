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

The short version: five printed parts, six M3 heat-set inserts, and six
M3 × 1/4" screws that are all the same screw. The LEDs live in the `nest`, a
white reflector cone that bolts to the backplate and lights the penguin's
belly from behind.

## Where the LEDs sit

```
        back                                              front
      y = 0                y = 22..25                   y = 46
        |                       |                          |
   [ backplate ]           [ nest plate ]            [ belly ]
        |    \__ post __/        | 6 LEDs                 |
   [ dev board ]                 \____ reflector cone ____/
                                        flares to 48 mm
```

Six LEDs in a 15 mm circle, 18 mm behind a 48 × 54 mm window, one lit at a
time. Three things stop that reading as a bright spot with a dim rim:

1. **The cone.** It flares from the LED plate out to the full width of the
   window, in white filament, and bounces the spill into the edges.
2. **The lens boss** on the back of the belly: a faceted cone of extra
   material right where the beam is strongest, tapering to nothing at the
   rim. Thicker plastic in the middle, thinner at the edge, so what comes
   out the front is even.
3. **Sanding the LEDs.** Rub the dome of each one flat on 400-grit until
   it's frosted. A clear 5 mm LED throws a ~20° beam; a frosted one
   scatters far wider. Two minutes, no cost, and it makes more difference
   than either of the other two.

There's a deliberate gap in the crown of the cone. Spill light goes up
through the body and reaches the two translucent eye plugs, which glow
faintly in whatever colour is currently showing. It's subtle — best in a
dim room — and it's a bonus rather than a feature. Printing the eyes in
natural or clear filament rather than white makes it noticeably stronger.

## Bill of materials

| Item | Qty | Notes |
|---|---|---|
| ESP32-S3 dev board | 1 | Classic ESP32, C3 and C6 also supported |
| LEDs — red, green, blue, yellow, orange, white | 1 each | 5 mm (or 3 mm, see `--led-d`) |
| Resistors, 100–330 Ω | 6 | Values per the table above |
| M3 heat-set inserts | 6 | 4.0 mm OD × 5 mm long |
| M3 × 1/4" screws | 6 | PC case screws — e.g. Micro Connectors `SCW-50M3`. M3 × 6 mm pan head is the same thing. |
| Hookup wire | — | Stranded, 26–28 AWG |
| **USB cable that carries data** | 1 | Not a charge-only cable |
| Zip tie, small | 1 | Strain relief on the cable |
| Black filament | ~95 g | Shell and backplate |
| White or natural filament | ~25 g | Nest, eyes, and one belly |
| *Optional:* rubber feet, 11 mm | 4 | Recesses are in the base |

The thing that still trips people up: **the cable**. Plenty of USB cables in
a drawer are power-only with no data lines. If the board never shows up in
`rookery ports`, swap the cable before debugging anything else.
