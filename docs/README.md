# Documentation

Pick a path. Depth lives in the linked pages.

| You want to… | Start here |
|---|---|
| **Build one, start to finish** | [getting-started.md](getting-started.md) |
| **Buy the parts** | [hardware/components.md](hardware/components.md) |
| **Print the enclosure** | [hardware/printing.md](hardware/printing.md) |
| **Solder it and put it together** | [hardware/wiring.md](hardware/wiring.md) → [hardware/assembly.md](hardware/assembly.md) |
| **Flash and configure only** (you have the hardware) | [getting-started.md](getting-started.md#2-flash-the-firmware) |
| **Drive it from Claude Code** | [getting-started.md](getting-started.md#6-wire-it-to-claude-code) |
| **Drive it from anything else** | [integrations.md](integrations.md) |
| **Look up a command or a flag** | [cli.md](cli.md) |
| **Talk to the board without the daemon** | [protocol.md](protocol.md) |
| **Change the penguin's shape or dimensions** | [hardware/enclosure.md](hardware/enclosure.md) |
| **Add a servo or a motor** | [hardware/motion.md](hardware/motion.md) |
| **Work out what it costs, or what selling one would take** | [production.md](production.md) |
| **Fix something** | [troubleshooting.md](troubleshooting.md) |

## By area

**Software**

| | |
|---|---|
| [getting-started.md](getting-started.md) | The end-to-end build, in order |
| [cli.md](cli.md) | Every `rookery` subcommand and flag |
| [integrations.md](integrations.md) | Sessions, sources, the HTTP API, and recipes for driving the light from anything |
| [protocol.md](protocol.md) | The serial protocol, and the link watchdog |
| [troubleshooting.md](troubleshooting.md) | Symptoms, in the order they happen |

**Hardware** — index at [hardware/README.md](hardware/README.md)

| | |
|---|---|
| [hardware/components.md](hardware/components.md) | Every part, with its voltage, interface and limits |
| [hardware/pinout.md](hardware/pinout.md) | Which GPIO drives which colour, on each supported board |
| [hardware/wiring.md](hardware/wiring.md) | The circuit, the resistor values, where the LEDs sit |
| [hardware/printing.md](hardware/printing.md) | Plates, filament, settings, and choosing a face |
| [hardware/assembly.md](hardware/assembly.md) | Inserts, loom, snap fit, closing it up |
| [hardware/enclosure.md](hardware/enclosure.md) | `generate.py`: the pixel map, the parameters, the self-checks |
| [hardware/motion.md](hardware/motion.md) | Power budget, and adding a servo or a motor |

**Project**

| | |
|---|---|
| [production.md](production.md) | What one costs to build, and what selling one would take |

## Source of truth

Facts in these pages are meant to match the code, not the other way round.
Where they disagree, believe:

1. `firmware/platformio.ini` and `firmware/src/main.cpp` — pin numbers, PWM
   levels, the serial command set
2. `host/rookery/` — every CLI flag, every default, every HTTP shape
3. `hardware/generate.py` — every dimension in the printed parts
4. These pages

If you find a page that has drifted, the fix is to change the page.
