# The enclosure generator

There is no CAD file. The penguin is
[`hardware/generate.py`](../../hardware/generate.py) — about 1,800 lines of
Python that build six meshes from a pixel map and a page of named dimensions,
then measure what they built.

You do not have to run it. `hardware/stl/` is committed, so
[printing](printing.md) needs nothing installed. Run it when you want a
different LED, a different insert, a different shape, or a different penguin.

```bash
pip install trimesh manifold3d shapely numpy
cd hardware
python3 generate.py                    # rewrites stl/
```

---

## The shape is a pixel map

`PIXELS` at the top of the file *is* the penguin, one character per voxel,
row 0 at the top:

```python
PIXELS = [
    "..####..",   # 0   crown
    ".######.",   # 1   eyes
    ".######.",   # 2   beak
    ".######.",   # 3   neck -- the black band above the belly
    "########",   # 4   shoulders, window top
    "########",   # 5   flippers
    ...
```

`PITCH` is the voxel size, 10 mm, so the eight columns and twelve rows come
out as an 80 × 120 mm silhouette. Edit the map and the whole enclosure
follows: the window, the eyes, the beak and the feet are all addressed by
grid coordinates rather than millimetres, and the engraved pixel grid
regenerates to match.

The one rule the map has to obey is written next to it: **rows 3–8 stay at
least six voxels wide.** That is the band the chassis occupies, and it has to
fit inside the body wall there.

## Six parts, two colours

| Part | Colour | Prints | What it is |
|---|---|---|---|
| `body` | black | open-side-down | The voxel penguin. Head, flippers, feet, and the window |
| `belly` | white | face-down | The panel the LEDs come through, and the plate the loom is built on |
| `chassis` | white | face-down | The box behind it: dev board, shelf, snap tongues |
| `back` | black | flat | Rear cover, four screws, four pillars |
| `eyes` | white | flat | Two plugs on a bar |
| `beak` | black | face-down | One wedge with a tang |

Both large parts print open-side-down, so the voxel silhouette lies flat in
the plate's XY plane and the pixel steps never become overhangs. The chassis
and the belly print face-down as well, which means every mount inside them
grows *upward* off the face you see — which is why nothing in the file ever
stands on the front of the shelf.

## The numbers you are most likely to change

All of these are module-level constants near the top of the file. The ones
with a command-line flag are marked.

| Constant | Default | What it sets |
|---|---|---|
| `PITCH` | 10.0 mm | Voxel size. Everything else is a multiple of it |
| `DEPTH` | 50.0 mm | Back plane to front face, five voxels |
| `WALL` / `CH_WALL` | 2.4 / 1.8 mm | Body wall, chassis wall |
| `WINDOW` | `(2, 5, 4, 9)` | The belly window in grid coordinates — 40 × 60 mm |
| `WINDOW_CLEAR` / `LIP_CLEAR` | 0.2 mm | Belly to window; belly lip to chassis wall. Loosen these if it binds |
| `BOARD_L` / `BOARD_W` | 63.5 / 25.5 mm | **Measure yours.** ESP32-S3-DevKitC-1 |
| `BOARD_Y` | 32.0 mm | Front face of the board, back from the belly face |
| `PLUG_W/T/L` | 13 / 9 / 22 mm | The USB-C plug that has to fit past the shelf |
| `LED_D` | 5.0 mm | LED body diameter — `--led-d 3.0` for 3 mm parts |
| `LED_PROUD` | 3.0 mm | How much dome stands out of the belly — `--led-proud` |
| `LED_CIRCLE_D` | 17.0 mm | Diameter of the ring the six sit on |
| `LED_FLANGE_D` | 5.9 mm | The rim that stops each LED going out the front |
| `LED_LEAD` | 4.0 mm | Straight lead behind each flange. Nothing may occupy it |
| `INSERT_OD` | 4.0 mm | **Measure yours** — `--insert-od 4.2` |
| `INSERT_GRIP` | 0.15 mm | How much *under* the insert the hole is cut, so there is material to melt |
| `SCREW_LEN` | 6.35 mm | M3 × 1/4", under-head |
| `RES_SLOT_W/D` | 3.0 / 3.4 mm | The channel an axial resistor presses into |
| `PLATE` | 180.0 mm | Build plate — `--plate 256` for an A1 / P1 / X1 |

## Command line

Everything here is an override of a constant above; nothing here is a
different code path except `--leds` and `--face`.

| Flag | Default | |
|---|---|---|
| `--out DIR` | `stl` | Where to write |
| `--insert-od MM` | 4.0 | Heat-set insert outer diameter |
| `--led-d MM` | 5.0 | 5.0 or 3.0. A 3 mm LED is a shorter LED, and the seat depth follows |
| `--led-proud MM` | 3.0 | Dome standing out of the belly |
| `--leds discrete\|ring` | `discrete` | Six through-hole LEDs, or one WS2812B ring |
| `--ring-od` / `--ring-id` | 37 / 23 mm | **Measure yours.** 12-LED rings are commonly 37 mm across, but not universally |
| `--face blank\|smiley\|chick\|text` | `blank` | Engrave a glyph into the belly |
| `--text STR` | `AFK` | With `--face text`. Four characters or fewer fit cleanly |
| `--plate MM` | 180 | Build plate size |
| `--no-check` | off | Skip the swept-insertion and interference checks. They are the slow ones |

## What every run checks

A bad parameter should fail here, not at the printer. The script prints a
row per part and **exits non-zero** if any of this is wrong:

- **Manifold after welding at the precision the file is written at.** A mesh
  that only holds together at full float precision will fail in someone
  else's slicer.
- **No zero-thickness sheets.** Two surfaces on one plane facing opposite
  ways, covering the same ground. Two booleans landing on exactly the same
  plane leave one, and it is invisible to every other test here: the mesh is
  still watertight, still winds consistently, still has the right volume and
  is still one lump. It just flickers in a viewer and slices into a membrane
  that should not be there.
- **Every part is a single connected lump of plastic.** Anything else means a
  feature is floating in mid-air, attached to nothing, which a slicer will
  happily print as a blob on the plate.
- **Every part fits the plate**, in its print orientation.
- **No unsupported downward-facing area** — more than 40 mm² of it fails.
  Faces under 1 mm² are ignored: those are the voxel staircase, which the
  slicer quantises to the same layers anyway. Flat ceilings are split off and
  judged on span instead, because that is what a bridge is judged on.
- **The shelf's bridge span**, which has to stay under 46 mm. It is the only
  ceiling in the build.
- **The screw arithmetic** — thread engagement and clearance past the tip.
- **The LED seat arithmetic** — how much plastic is left in front of each
  flange, how much dome that leaves proud of the belly, how much ledge is
  left to stop the flange, and whether the cluster still fits inside the
  window it pokes through.
- **A swept insertion test**: that the belly can actually be *pushed* into
  the chassis, rather than merely fitting once it is there.
- **Interference.** The six LEDs, the dev board and a USB-C plug are modelled
  as solids and boolean-tested against every printed part, and the assembled
  parts against each other. Nothing can end up parked in an LED's well, in
  front of a dome, or in the way of a connector.

## What it writes

Six STLs and the per-colour plates, into `--out` (default `hardware/stl/`):

```
body.stl  belly.stl  chassis.stl  back.stl  eyes.stl  beak.stl
plate1_black.3mf   body, back, beak
plate2_white.3mf   belly, chassis, eyes
```

The plates are packed from whatever parts exist in each colour, so a
`--plate 256` run produces the same six parts in a different arrangement.

---

## Next

- Print what it wrote: [printing.md](printing.md).
- Put the electronics in it: [assembly.md](assembly.md).
- Add something of your own to the head or base cavity: [motion.md](motion.md).
