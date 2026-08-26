# rookery

**A desk light that tells you what your Claude Code sessions are doing.**

Green while it's working. Red when it wants you. Yellow when it's done. Glance
at the corner of your desk instead of cycling through terminal tabs.

A *rookery* is a penguin colony — which is roughly what a few concurrent agent
sessions feel like, and why one lives on the base.

```
Claude Code ──hooks──▶ localhost:8787 ──▶ daemon ──USB serial──▶ ESP32 ──▶ LEDs
```

No network. No telemetry. No cloud. Your session state never leaves the machine
it's running on.

---

## What it looks like

| LED | State | Meaning |
|---|---|---|
| 🟢 Green, slow breathe | `working` | At least one session is running |
| 🟡 Yellow, steady | `idle` | Sessions open, nothing running |
| 🔴 Red, fast pulse | `needs_you` | A session is waiting on your input |
| 🔵 Blue, very dim | `asleep` | No sessions at all |
| 🟠 Orange, slow blink | `link lost` | The daemon stopped talking — don't trust the light |
| ⚪ White, blink | `ident` | Boot self-test, or you asked it to identify itself |

Sessions are tracked individually and the most urgent one wins, so five
terminals and three worktrees still collapse into one colour.

The enclosure is a **penguin**, 91 × 55 × 117 mm, in two colours: a black
shell and a **white belly that the LEDs light from behind**. The belly is a
swappable panel — a smiley, a chick, a word, or your own — and it's the only
part you ever need to take out. Its glyph is thinned to 0.9 mm so it glows
while the rest of the panel stays opaque.

The eyes are translucent plugs that pick up spill light from inside, so they
glow faintly in whatever colour is currently showing.

---

## Bill of materials

If you own a 3D printer and a parts drawer, you probably have all of this.

| Item | Qty | Notes |
|---|---|---|
| ESP32-S3 dev board | 1 | Classic ESP32, C3 and C6 also supported |
| LEDs — red, green, blue, yellow, orange, white | 1 each | 3 mm or 5 mm through-hole |
| Resistors, 100–330 Ω | 6 | Values vary by colour — see [WIRING.md](hardware/WIRING.md) |
| M3 heat-set inserts | 6 | 4.0 mm OD, 5 mm long |
| M3 × 1/4" screws | 6 | Standard PC case screws — Micro Connectors `SCW-50M3` or any M3 × 6 mm pan head |
| **USB cable that carries data** | 1 | Not a charge-only cable |
| Zip tie, small | 1 | Strain relief on the cable |
| Black filament | ~95 g | Shell and backplate |
| White or natural filament | ~25 g | Nest, eyes, and one belly |
| *Optional:* rubber feet, 11 mm | 4 | Recesses are in the base |

Every screw in the build is the same one: **M3 × 1/4"**, six of them, into six
M3 heat-set inserts. There is nothing else to source.

Only one LED is ever lit at a time, so there's no capacitor, no level shifter
and no external power supply. The whole thing runs off the USB port that's
already carrying the serial data.

---

## Build

### 1. Flash the firmware

```bash
pip install platformio
cd firmware
pio run -e esp32s3 -t upload
pio device monitor              # expect: READY rookery 0.2.0 channels=6
```

On boot the firmware walks all six LEDs in order as a self-test. If one stays
dark, that's a wiring fault — find it now, before anything is soldered.

> **ESP32-S3 users:** a DevKitC-1 has two USB-C sockets. The default build
> routes Serial to the **native USB** port (marked `USB`). If your board has
> only one socket, that's the one. To use the `UART` bridge instead, build
> `esp32s3-uart`.

Other targets: `esp32dev`, `esp32c3`, `esp32c6`, `esp32s3-penguin` (adds the
servo), `esp32s3-neopixel` / `esp32s3-rgb` (alternate LED hardware).

### 2. Install the daemon

```bash
cd host
pip install -e .

rookery ports     # find your board (* marks likely candidates)
rookery probe     # confirm it answers
rookery test      # cycle green → yellow → red → blue
```

If `test` cycles the colours, the hardware is finished. Everything after this
is software.

**Linux:** for serial permissions, either `sudo usermod -aG dialout $USER`
(then log out and back in), or install
[`scripts/99-rookery.rules`](scripts/99-rookery.rules) for a stable
`/dev/rookery` symlink that survives replugging.

### 3. Wire it to Claude Code

```bash
rookery install-hooks
```

Merges the hook entries into `~/.claude/settings.json`, backing up the original
to `settings.json.bak` first. It only ever touches its own entries — your
existing hooks are preserved — and re-running it is idempotent.

Prefer to do it by hand? Paste [`claude/hooks.http.json`](claude/hooks.http.json)
into your settings yourself. To undo: `rookery uninstall-hooks`.

### 4. Run it

```bash
rookery run
```

Open Claude Code in another terminal and ask it something.

Autostart on Linux:

```bash
mkdir -p ~/.config/systemd/user
cp scripts/rookery.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rookery
sudo loginctl enable-linger $USER    # survive logout
```

macOS: [`scripts/com.rookery.daemon.plist`](scripts/com.rookery.daemon.plist).

### 5. Print the enclosure

**The meshes are committed — you don't need to run anything.** The `.3mf`
files in [`hardware/stl/`](hardware/stl/) are pre-arranged plates: open one in
Bambu Studio and every part arrives laid out and correctly oriented.

Five printed parts, in two colours:

| Part | Filament | What it is |
|---|---|---|
| `shell` | **Black** | The body — head, flippers, beak, belly window, eye sockets |
| `backplate` | **Black** | Rear panel; the board and the nest mount on it |
| `nest` | **White** | Holds the six LEDs and reflects their light into the belly |
| `eyes` | **White / natural** | Two plugs on a bridge |
| `belly_*` | **White / natural** | The diffuser. Pick one — this is the swappable bit. |

Plates are grouped by filament colour, so a single-extruder machine never
needs a mid-print swap:

| Plate | Filament | Parts |
|---|---|---|
| `plate1_black.3mf` | Black | `shell` |
| `plate2_black.3mf` | Black | `backplate` |
| `plate3_white.3mf` | White | `nest`, `eyes`, `belly_blank`, `belly_smiley` |
| `plate4_white.3mf` | White | `belly_chick`, `belly_text` |

Everything fits a **Bambu A1 mini** (180 × 180 × 180). If you have a 256 mm
machine, `python3 generate.py --plate 256` re-packs the set onto two plates.

3 walls, 15–20% infill, 0.2 mm layers, and **no supports on any part** —
nothing in the design overhangs past 45°, and `generate.py` measures that
rather than assuming it.

**The belly must be white or natural filament.** Its glyph is thinned to
0.9 mm while the panel around it is 2.6 mm, so light passes through the glyph
and not the frame. A dark filament gives you a dim brown oval. The `nest` is a
reflector, so print that in white too.

To change dimensions, edit the parameters at the top of
[`hardware/generate.py`](hardware/generate.py) and re-run it:

```bash
pip install trimesh manifold3d shapely numpy
cd hardware
python3 generate.py                    # rewrites stl/
python3 generate.py --insert-od 4.2    # if your inserts are fatter
python3 generate.py --led-d 3.0        # 3 mm LEDs instead of 5 mm
python3 generate.py --text "BUSY"      # your own wording
```

Every run checks itself: manifoldness after welding, plate fit, unsupported
overhang area, bridge spans, screw thread engagement, and a boolean
interference test of the assembled parts against each other and against a
solid standing in for the dev board. A bad parameter fails loudly instead of
at the printer.

### 6. Bellies

Four ship ready to print:

| Belly | What it shows |
|---|---|
| `belly_blank` | Plain glow — the whole oval lights up |
| `belly_smiley` | A smiley face — the most legible of the four |
| `belly_chick` | A pixel penguin chick, on a penguin's belly |
| `belly_text` | Reads `AFK`; change it with `--text` |

Swapping one is four screws, all on the back. The whole electrical assembly
stays on the backplate as one piece — nothing gets unsoldered.

If you design your own, keep the lit graphic **small and central**. The six
LEDs sit in a 15 mm circle about 18 mm behind a 48 × 54 mm window, so a
compact centred icon lights evenly while a graphic that reaches the rim falls
off at the edges. The text belly uses a built-in 5 × 7 bitmap font covering
A–Z, 0–9 and a few symbols, auto-scaled to fit.

Full print-and-assemble walkthrough, including the heat-set insert technique
and the order to do things in: [`hardware/stl/README.md`](hardware/stl/README.md).
Circuit and resistor values: [`hardware/WIRING.md`](hardware/WIRING.md).

---

## Usage

```bash
rookery run --brightness 90    # dimmer, for a dark room
rookery run --simulate         # log state changes, no hardware needed
rookery status                 # which sessions does it think are live?
rookery set needs_you          # force a state (stop the daemon first)
rookery print-hooks            # dump the hook JSON to stdout
```

`--simulate` is genuinely useful: you can verify the whole hook pipeline before
the hardware exists.

Six LEDs from a parts drawer will never be balanced. Trim them live over serial
with `GAIN <colour> <0-255>`, then bake the values you settle on into
`build_flags` — `env:esp32s3-tuned` in `platformio.ini` exists for that.
`WAG` triggers the penguin manually.

Full serial reference: [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

---

## Troubleshooting

**Board doesn't appear in `rookery ports`** — 90% of the time it's a
charge-only USB cable. Then it's the wrong socket on an S3 (native vs UART).
Then it's a missing CP210x/CH340 driver on macOS or Windows.

**Light never changes** — run `rookery status` while a session is live. If
sessions are listed, the problem is the serial link; if not, it's the hooks.
Run `/hooks` inside Claude Code to confirm they registered.

**Light stuck on green** — the daemon died. The firmware notices after 30 s and
switches to the orange blink.

**One LED never lights during the boot self-test** — that channel is miswired,
or the LED is in backwards. The long leg is the anode and goes to the resistor.

**Blue or white looks dead or very faint** — expected, not a fault. Their
forward voltage is nearly the full 3.3 V a GPIO can supply, so they only get
about 2 mA where the others get 7. The firmware already compensates with higher
PWM duty; [`hardware/WIRING.md`](hardware/WIRING.md) has two stronger fixes.

**The belly glows brightest in the middle** — six LEDs in a 15 mm circle
lighting a 48 × 54 mm window will always fall off toward the edges. The
reflector cone and the lens boss on the back of the belly are there to fight
that, but the cheapest fix by far is to **sand the dome of each LED flat on
400-grit** until it's frosted. That turns a ~20° beam into a wide scatter and
does more than either of the other two.

**Belly is dim overall** — wrong filament. It needs white or natural PLA.
Print the `nest` in white too; it's a reflector. Also check `BRIGHT` isn't
turned down.

**Eyes barely glow** — expected. They're lit by spill light through a gap in
the crown of the reflector, so they're subtle by design and best seen in a dim
room. Printing them in natural or clear filament rather than white helps a
lot.

**Hook errors in the transcript** — the daemon isn't running. HTTP hooks report
a connection failure as a non-blocking error: visible, harmless, and it won't
interrupt your work. Switch to the command-hook variant if it bothers you; that
one exits 0 silently.

---

## Extending it

Nothing below the hook layer is Claude Code-specific. The daemon accepts any
POST to `/hook` carrying a `hook_event_name` and a `session_id`, so pointing
another tool at it is a matter of mapping that tool's events onto the four
states in [`host/rookery/state.py`](host/rookery/state.py).

The serial protocol is plain text, so you can drive the light from a shell
script, a CI webhook, or a build system without going near the daemon:

```bash
printf 'STATE needs_you\n' > /dev/rookery
```

`LED <colour> <0-255>` addresses any single LED directly if you want to invent
your own signals.

---

## Repository layout

```
firmware/         ESP32 firmware (PlatformIO)
host/rookery/     the daemon: hook endpoint, session registry, serial link
claude/           hook configuration for Claude Code
hardware/
  generate.py     parametric model generator -> STL + per-colour 3MF plates
  stl/            printable meshes, plates, and the assembly guide
  WIRING.md       circuit, resistor values, where the LEDs sit
  MOTOR.md        power budget, and adding a motor
  PRODUCTION.md   what it costs to build, and to sell
scripts/          systemd unit, launchd plist, udev rules
docs/             serial protocol reference
```

---

## Credit

The idea of a physical desk light for agent sessions isn't mine — I saw
[clawlight.dev](https://clawlight.dev), wanted one, and decided building it
would be more fun than buying it.

This is an independent implementation: its own firmware, daemon and enclosure,
six discrete LEDs instead of a diffused RGB beacon, a penguin-shaped
two-colour enclosure with a swappable backlit belly that isn't in their
product at all, and a hook-driven approach rather than session-file
watching. If you'd rather have a finished product in a nice case than a weekend
of soldering, go buy theirs.

Not affiliated with Anthropic, or with Claw Light.

## License

MIT — see [LICENSE](LICENSE).
