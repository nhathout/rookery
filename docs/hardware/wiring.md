# Wiring & assembly

Six discrete single-colour LEDs, one GPIO each, sharing a common ground,
poking straight out through the penguin's belly. Nothing to buy — this is a
parts-drawer build.

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
C3, C6 and the alternate LED backends have their own maps —
[pinout.md](pinout.md).

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
   maximum. The LEDs face you directly now rather than lighting a panel
   from behind, so ~2 mA reads better than it used to, and blue only
   signals "nothing is running".
2. **Drop the resistor** to 47 Ω, or short it, on blue and white only.
   Slightly naughty, entirely normal for indicators, and PWM keeps average
   current low.
3. **Drive them from 5 V through a transistor** — see [motion.md](motion.md) for
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
**[printing.md](printing.md)** covers what to print, in which filament and on
which plate; **[assembly.md](assembly.md)** covers the order to bolt it
together.

The short version: six printed parts, four M3 heat-set inserts, and four
M3 × 1/4" screws that are all the same screw.

The two white parts are the ones that matter here. The **belly** is the
panel the LEDs come through, and it is a flat plate: the six bores, the
resistor channels and the tie arches are all on it, so the entire loom gets
built on the bench with both ends of every hole in reach. The **chassis** is
the box behind it, and it carries the dev board. They snap together, and the
pair drops into the body in one move.

## Where the LEDs sit

**Through the belly, not behind it.**

```
     back                                                   front
   y = 0      y = 5      y = 8..18   y = 41.8      y = 44.4  y = 50
     |          |            |          |            |         |
[ back cover ][  chassis -- the box  ][ | ][  belly -- the panel  ]
     |        rear rim   dev board      |    LED well   plate   domes
     |                   on posts       |    27 mm dia  5.6 mm  3 mm
     |                                  |                       proud
     |                              THE JOINT
     |                          lip + 2 snap tongues
     |
     |   the board is longer than the box is tall: its top leaves
     |   through a slot in the roof, and the USB plug drops out
     |   through a slot in the floor into the base of the penguin
```

The front of the chassis is **8.2 mm of solid white PLA** — the plug that
fills the body's window, the 45° seat behind it and the box's own front
wall, stacked. Nothing shines through 8.2 mm of PLA. So the LEDs do not try
to: that wall is machined away from the back over a 28 mm circle, leaving a
**5.6 mm plate** with six 5.4 mm bores straight through it.

Each LED goes in **from the back, dome first**, until the little flange at
its base lands on the back of the plate. That flange is 5.9 mm across and
the bore is 5.4, so it stops there — and the arithmetic falls out of it:
5.6 mm of the LED is inside the plate and the remaining **3.0 mm of dome
stands proud of the belly**, in a 17 mm circle you can read from across the
room. Nothing is diffusing anything; you are looking at the LED.

The 5.6 mm of bore also holds each one dead straight, which the 3 mm shelf
they used to sit on never did.

> **Still worth sanding.** Rub each dome flat on 400-grit until it's
> frosted. A clear 5 mm LED throws a ~20° beam, so head-on it is a hard
> bright point and from the side it's nearly out. A frosted one reads the
> same from anywhere in the room. Two minutes, no cost.

The 17 mm circle is sized to the 10 mm voxel grid: at that diameter no LED
lands on an engraved groove except the two on the vertical centre line,
which read as deliberate rather than as a mistake.

### What's behind them

| | |
|---|---|
| **LED well** | 28 mm across, 2.6 mm deep, open toward the back. Room for six flanges, six pairs of leads, and your fingers. |
| **Straight lead** | 4 mm behind each flange before anything is in the way. Bend them outward there. |
| **Resistor channels** | One down each side of the well, 3 × 3.4 mm and 32 mm long: three axial resistors end to end, pressed in from the back. |
| **Cable-tie arches** | Four, one above and one below each channel. A 6 × 3.2 mm tunnel: pass a small tie through, bundle over the top. |
| **Shelf windows** | 7 x 21 mm through the shelf, one each side, so the three LEDs on each side reach the board without crossing the box. They are windows rather than slots out to the wall on purpose: the shelf has to stay attached to both side walls or it does not print. |
| **Then 22 mm of air** | Between the LED leads and the front of the dev board. There is no light chamber to keep clear any more, so this space is yours. |

Bend all six cathodes together into a ring and solder — that's your ground
bus. Solder each anode to a resistor sitting in its channel, then a wire
from each resistor back through the shelf window on its side to the
board.

All of that happens on the belly alone, flat on the bench, before it ever
meets the box. Keep the wires **inboard of the lip**: the lip is what the
two halves close on, and a wire lying across it holds them apart.

Nothing stands in front of an LED, and nothing is parked in the well behind
one. That is checked, not assumed: the six LEDs are modelled as solids —
dome, body and lead — and boolean-tested against the chassis, the body, the
board and the plug on every run.

> **The eyes no longer glow.** They used to pick up spill light from the
> chamber. The LEDs now point out the front, so no light gets into the head
> at all. The pupils still read dark against the black inside of the head,
> which is what they were doing in daylight anyway.

## What you need for this part of the build

Six LEDs, six resistors, some stranded 26–28 AWG hookup wire, and a USB cable.
Exact parts, forward voltages and limits: [components.md](components.md).

The thing that still trips people up: **the cable**. Plenty of USB cables in
a drawer are power-only with no data lines. If the board never shows up in
`rookery ports`, swap the cable before debugging anything else.

---

## Next

- Print the parts: [printing.md](printing.md)
- Put it together: [assembly.md](assembly.md)
- Pin maps for the other boards: [pinout.md](pinout.md)
- Something isn't lighting: [../troubleshooting.md](../troubleshooting.md)
