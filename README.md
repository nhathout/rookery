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

**[Build one](docs/getting-started.md) · [Parts](docs/hardware/components.md) · [Drive it from anything](docs/integrations.md) · [All the docs](docs/README.md)**

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

**It isn't only Claude Code.** Anything can drive the light — a training run,
a policy server, a job queue on a cluster you aren't sitting at. Wrap a
command in `rookery watch`, poll a machine with `rookery poll`, or POST a
state from a shell script. Sessions and those sources are equals, and the
most urgent still wins, so a job that died at 03:00 turns the penguin red
while an agent is busy elsewhere. See
[docs/integrations.md](docs/integrations.md).

## The penguin

The enclosure is built on a 10 mm voxel grid and stands 80 × 60 × 120 mm on
your desk. Black shell, white belly, two cubes for feet. The belly is a
40 × 60 mm panel divided by an engraved grid into **4 × 6 pixels**, and **the
six LEDs come through it** — a ring of domes standing 3 mm proud of the white,
which you can read from across the room without looking for a small light.

That white panel is its own printed part, and it is where the whole LED loom
gets built — flat on the bench, with both ends of every hole in reach. The box
behind it carries the dev board and snaps on. Neither takes a screw: the back
cover clamps the pair into the window.

The shape is not a CAD file. `PIXELS` at the top of
[`hardware/generate.py`](hardware/generate.py) *is* the penguin, one character
per voxel — edit it and the window, the eyes, the beak and the feet all
follow. Every run measures what it built: manifoldness, plate fit, overhangs,
bridge spans, thread engagement, and a boolean interference test against
solids standing in for the dev board, a USB plug and the six LEDs.
[docs/hardware/enclosure.md](docs/hardware/enclosure.md).

## The hardware

If you own a 3D printer and a parts drawer, you probably have all of this.

| Role | Part | Qty |
|---|---|---|
| Controller | ESP32-S3 dev board — classic ESP32, C3 and C6 also supported | 1 |
| Indicators | 5 mm through-hole LEDs: red, green, blue, yellow, orange, white | 6 |
| Current limiting | Resistors, 100–330 Ω | 6 |
| Fasteners | M3 heat-set inserts + M3 × 1/4" screws | 4 + 4 |
| Power and data | **A USB cable that carries data** | 1 |
| Structure | Six printed parts, ~105 g black and ~57 g white | — |

Only one LED is ever lit at a time, so there's no capacitor, no level shifter
and no external power supply. The whole thing runs off the USB port that's
already carrying the serial data.

Exact parts, voltages and limits: [docs/hardware/components.md](docs/hardware/components.md).

## Quick start

Firmware is Arduino on [PlatformIO](https://platformio.org/); the host daemon
is Python.

```bash
cd firmware && pio run -e esp32s3 -t upload   # flash
cd ../host   && pip install -e .              # install the daemon

rookery test              # cycle green → yellow → red → blue
rookery install-hooks     # merge hooks into ~/.claude/settings.json
rookery run               # leave it running
```

Then open Claude Code in another terminal and ask it something.

No hardware yet? `rookery run --simulate` logs state changes instead of
driving a board, so you can verify the whole hook pipeline before anything is
soldered.

Full path — parts, print, wire, flash, hooks, assemble:
**[docs/getting-started.md](docs/getting-started.md)**.

## Driving it from something else

Nothing below the hook layer is Claude Code-specific. Three ways in, in
increasing order of effort:

```bash
# 1. wrap a command
rookery watch --source train -- python train.py

# 2. report from a script
rookery notify needs_you --source deploy --detail "smoke test failed"

# 3. POST it yourself, from anywhere that can reach the daemon
curl -s -X POST http://localhost:8787/state \
  -H 'Content-Type: application/json' \
  -d '{"source":"ci","state":"working","detail":"build 4412","ttl":600}'
```

The daemon also still accepts any POST to `/hook` carrying a
`hook_event_name` and a `session_id`, so pointing another agent tool at it is
a matter of mapping that tool's events onto the four states in
[`host/rookery/state.py`](host/rookery/state.py).

Below that, the serial protocol is plain text, so you can drive the light from
a shell script, a CI webhook, or a build system without going near the daemon
at all. Recipes: [docs/integrations.md](docs/integrations.md). Serial
reference: [docs/protocol.md](docs/protocol.md).

## Documentation

| Goal | Doc |
|---|---|
| Build end-to-end | [docs/getting-started.md](docs/getting-started.md) |
| Parts and limits | [docs/hardware/components.md](docs/hardware/components.md) |
| Pin map, per board | [docs/hardware/pinout.md](docs/hardware/pinout.md) |
| Circuit and resistor values | [docs/hardware/wiring.md](docs/hardware/wiring.md) |
| What to print, and how | [docs/hardware/printing.md](docs/hardware/printing.md) |
| How it goes together | [docs/hardware/assembly.md](docs/hardware/assembly.md) |
| Changing the model | [docs/hardware/enclosure.md](docs/hardware/enclosure.md) |
| Every command and flag | [docs/cli.md](docs/cli.md) |
| Driving it from anything | [docs/integrations.md](docs/integrations.md) |
| Serial protocol | [docs/protocol.md](docs/protocol.md) |
| When it misbehaves | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Adding a servo or motor | [docs/hardware/motion.md](docs/hardware/motion.md) |
| Cost, and what selling one would take | [docs/production.md](docs/production.md) |
| Full index | [docs/README.md](docs/README.md) |

## Repository layout

```
firmware/         ESP32 firmware (PlatformIO)
host/rookery/     the daemon: hook endpoint, session registry, serial link
claude/           hook configuration for Claude Code
hardware/
  generate.py     parametric model generator -> STL + per-colour 3MF plates
  stl/            printable meshes and plates, all committed
scripts/          systemd unit, launchd plist, udev rules, poll-sunny.ps1
docs/             everything above, and the index at docs/README.md
```

## Credit

The idea of a physical desk light for agent sessions isn't mine — I saw
[clawlight.dev](https://clawlight.dev), wanted one, and decided building it
would be more fun than buying it.

This is an independent implementation: its own firmware, daemon and enclosure,
six discrete LEDs instead of a diffused RGB beacon, a penguin-shaped
two-colour voxel enclosure whose whole front is a pixelated panel with the
LEDs coming through it, and a hook-driven approach rather than session-file
watching. If you'd rather have a finished product in a nice case than a weekend
of soldering, go buy theirs.

Not affiliated with Anthropic, or with Claw Light.

## License

MIT — see [LICENSE](LICENSE). That covers the firmware, the daemon, the
documentation, and the generated meshes in `hardware/stl/`.
