# Wiring & assembly

Six discrete single-colour LEDs, one GPIO each, sharing a common ground, behind
a backlit plaque. Nothing to buy — this is a parts-drawer build.

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
   maximum. Behind the diffuser plaque this is usually fine, and blue only
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

## The printed parts

| Part | Qty | Material | Settings |
|---|---|---|---|
| `case` | 1 | Any opaque PLA/PETG | 3 walls, 15% infill, **no supports** |
| `lid` | 1 | Same | 3 walls, 15% |
| `holder` | 1 | Anything | 3 walls, 20% |
| `plaque_*` | 1 | **White or natural PLA** | 3 walls, 15% |

Everything is pre-oriented in the files — **don't rotate anything**. The lid
and plaques are already flipped so their visible faces print against the build
plate, which gives the best finish and means the plaque's thin glow layer is
laid down first with no bridging at all.

**The plaque must be white or natural PLA.** Its glyph is thinned to 0.8 mm so
light passes through it while the surrounding 2.6 mm stays opaque. A dark
filament gives you a dim brown rectangle.

Print the case in white too if you can — the chamber walls reflect, and it
noticeably evens out the glow. Otherwise a strip of white tape or foil inside
the chamber does the same job.

### Regenerating the meshes

`stl/` is committed, so you can print without running anything. To change
dimensions:

```bash
pip install trimesh manifold3d shapely numpy
python3 generate.py                      # rewrites stl/
python3 generate.py --insert-od 4.2      # if your inserts are fatter
python3 generate.py --led-d 3.0          # 3mm LEDs instead of 5mm
python3 generate.py --text "BUSY"        # your own plaque wording
```

Every part is validated as manifold before it's written.

## Assembly

1. **Breadboard and flash first.** On boot the firmware walks all six LEDs in
   order. Any LED that stays dark is a wiring fault you want to find now, not
   after soldering. Then run `rookery test`.

2. **Fit the six M3 heat-set inserts** — four in the corner bosses of the case,
   two in the shorter posts at the front. Set the iron to about 200 °C for PLA,
   rest the insert on the hole, and let the iron's own weight carry it in.
   Pushing hard squeezes molten plastic up around the flange and leaves it
   proud. Stop when the top is flush, and let it cool before touching it.

3. **Push the six LEDs up through the holder** from underneath. The small
   flange at the base of each stops it at the right height. Keep the colour
   order consistent so you can trace wires later.

4. **Bend all six cathodes together** into a ring under the plate and solder —
   that's your ground bus. Solder each anode to its resistor, then a wire from
   each resistor back toward the board. Leave the wires long; you'll regret a
   tight loom the first time you open it.

5. **Drop the dev board** into its pocket. It sits on four posts and snaps
   under the four retention tabs — press it down until it clicks. The USB
   sockets line up with the cutout in the left wall.

6. **Solder the LED wires to the board** per the channel map above.

7. **Screw the holder down** with 2× M3 × 6 mm into the front posts.

8. **Drop a plaque into the lid** from underneath — it sits against the
   internal ledge — then place the lid and fasten with 4× M3 × 8 mm. The screw
   heads sit in counterbores below the lid surface.

A scrap of perfboard makes step 4 much easier than free-wiring it.

## Swapping plaques

Four ship in the box: `smiley`, `penguin`, `text` (reads AFK) and `blank`.
Undo the four lid screws, swap, put it back. That's the only reason you'll ever
need to open it, which is why the lid screws are the only fasteners on the
outside.

If you design your own, keep the lit graphic **small and central**. The six
LEDs sit in a 14 mm cluster about 10 mm below the plaque, so a compact centred
icon lights evenly while text spanning the full window is noticeably brighter
in the middle. That's also why the shipped text plaque is three characters.

## Bill of materials

| Item | Qty | Notes |
|---|---|---|
| ESP32-S3 dev board | 1 | Classic ESP32, C3 and C6 also supported |
| LEDs — red, green, blue, yellow, orange, white | 1 each | 5 mm (or 3 mm, see `--led-d`) |
| Resistors, 100–330 Ω | 6 | Values per the table above |
| M3 heat-set inserts | 6 | 3 mm long, ~4.0 mm OD |
| M3 × 8 mm screws | 4 | Lid |
| M3 × 6 mm screws | 2 | LED holder |
| Hookup wire | — | |
| **USB cable that carries data** | 1 | Not a charge-only cable |
| White or natural PLA | — | For the plaque |
| *Optional:* rubber feet, 11 mm | 4 | Recesses are in the base |

The thing that still trips people up: **the cable**. Plenty of USB cables in a
drawer are power-only with no data lines. If the board never shows up in
`rookery ports`, swap the cable before debugging anything else.
