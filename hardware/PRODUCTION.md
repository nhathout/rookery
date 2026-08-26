# What it costs to build, and what it would take to sell

This is a parts-drawer project. It is also, with a few changes, a product.
This document is the arithmetic for both, and the honest version of what
stands between them.

Prices are indicative — check them, they move. Everything below assumes PLA,
one Bambu A1 mini, and hand assembly.

---

## Cost of one unit

| Item | Qty | 1-off | @100 |
|---|---|---|---|
| ESP32-S3 DevKitC-1 | 1 | $9.00 | $5.50 |
| LEDs, 5 mm, six colours | 6 | $0.40 | $0.15 |
| Resistors | 6 | $0.06 | $0.02 |
| M3 heat-set inserts | 6 | $0.36 | $0.12 |
| M3 × 1/4" screws | 6 | $0.12 | $0.04 |
| Hookup wire, zip tie | — | $0.25 | $0.10 |
| Rubber feet | 4 | $0.20 | $0.08 |
| USB-A/C data cable, 1 m | 1 | $2.50 | $1.10 |
| Filament — 95 g black | — | $1.90 | $1.60 |
| Filament — 25 g white | — | $0.50 | $0.42 |
| Box, insert, printed card | — | — | $2.20 |
| **Materials** | | **$15.29** | **$11.33** |

**Machine time.** About 12 hours across four plates, or roughly one unit per
A1 mini per day allowing for plate changes. That is not labour, but it is
capital and floor space: **one printer supports about 20 units a month.** Any
real volume means more printers, and printers are the cheapest thing on this
list to add.

**Labour**, which is where this actually gets expensive:

| Step | Time |
|---|---|
| Six heat-set inserts | 3 min |
| Sand six LEDs, load the nest | 4 min |
| Solder the ground bus and six resistors | 14 min |
| Solder seven wires to the board | 8 min |
| Fit board, belly, eyes, close up | 6 min |
| Flash, run `rookery test`, pack | 7 min |
| **Total** | **~42 min** |

At $25/hour that is **$17.50 a unit**, more than the materials. Add a
plausible 8% for scrap and rework and one unit lands at roughly **$30 all-in
at 100 units**.

At a 3× multiple over landed cost — which is thin for hardware once you carry
returns, support and a warranty — that is a **$89 product**. It is not a $39
product, and pretending otherwise is how hardware projects lose money
politely.

---

## The one change that matters

**Thirty of those forty-two minutes are the LED loom.** Six LEDs, six
resistors, a hand-twisted ground bus and thirteen solder joints, done by a
person, every single time. It is also where every unit-to-unit inconsistency
comes from: six LEDs from a parts drawer are never balanced, which is exactly
why `GAIN` exists.

Two ways out, in increasing order of commitment:

### 1. A WS2812B ring — the cheap fix

The firmware already supports this. `-DLED_BACKEND_NEOPIXEL` is in
`platformio.ini` today, as `env:esp32s3-neopixel`.

A 12-LED WS2812B ring module is about $1.50 and has **three wires**. No
resistors, no ground bus, no per-colour trim, no thirteen joints. Assembly
drops from 42 minutes to roughly **15**, and every unit comes out the same
colour as every other unit because the colour is now a number in firmware
rather than a property of whichever LEDs were in the bag.

| | Discrete | WS2812B ring |
|---|---|---|
| Parts | 12 | 1 |
| Solder joints | 13 | 3 |
| Assembly | 42 min | ~15 min |
| Labour @ $25/h | $17.50 | $6.25 |
| BOM change | — | +$1.35, −$0.17 |
| Colour consistency | trim each unit | identical |

That is **$10 a unit** for a $1.35 part, and it pays back on the first one.

The nest needs a ring seat instead of six bores:

```bash
python3 generate.py --leds ring --ring-od 37 --ring-id 23
```

Measure your ring — 12-LED rings are commonly 37 mm across but not
universally. The generator checks the seat against the reflector cone and the
board and fails if it doesn't fit.

The one thing you give up is the constraint that made this design what it is:
one colour at a time, at a few milliamps, off a USB port with no capacitor.
Twelve WS2812Bs at full white are 700 mA. Cap the brightness in firmware and
that is a non-issue, but it is a real change to the power story — see
[MOTOR.md](MOTOR.md).

### 2. A carrier PCB — the right fix at volume

A 40 × 40 mm two-layer board carrying six LEDs, six resistors and one header,
assembled by the fab: roughly $1.50 in boards plus $2–3 in assembly at 50
units, with a one-off setup of about $30–60. Snaps onto the nest's two screw
posts, one connector to the dev board.

It keeps the discrete-LED design exactly as it is — the low current, the one
lit at a time, the honest little indicator — and removes the same 25 minutes.
It costs more per unit than the ring and pays back somewhere around **15–25
units**, so it is the answer if you have decided the six discrete LEDs are the
product rather than an implementation detail.

Beyond a few hundred units, the dev board is the next thing to go: an ESP32-S3
module soldered onto that same PCB removes $3–4 and another connector, at the
cost of needing to care about USB, regulation and certification yourself.

---

## What ships in the box

- Assembled penguin, one belly fitted
- The other three bellies, loose — they are the demo, and they cost 40 g of
  filament and no labour
- USB data cable
- Four rubber feet
- A card with the one-line install and a link

The bellies matter more than they look like they do. They are the thing
someone shows a colleague, they cost almost nothing, and they turn "a light"
into "a light that's mine".

---

## Before you sell one

Not optional, roughly in order of how much they will hurt if skipped:

**The cable.** Half the support load on a project like this is someone using
a charge-only USB cable. Ship a known-good data cable in the box and the
problem disappears. It is the highest-value $1.10 on the BOM.

**Flash and test every unit.** `rookery test` cycles all six colours in about
ten seconds. It catches a cold joint, a backwards LED and a dead channel
before the box is sealed, which is the only place catching them is cheap.

**Regulatory.** In the US, a USB-powered device with no intentional radiator
is subject to FCC Part 15 Subpart B as an unintentional radiator; if you sell
into the EU you need CE/UKCA marking and a declaration of conformity. This is
survivable — a compliance lab will test a unit for a four-figure sum — but it
is a real cost that arrives before revenue, and it is much worse if the
firmware ever brings up WiFi. **Keep the radio off.** The current firmware
never initialises it, and that is worth defending as a design decision rather
than an accident.

**Say what it is.** This talks to Claude Code over local hooks and is not
affiliated with Anthropic. Do not imply otherwise on the box, the listing or
the site. Trademark trouble is cheap to avoid and expensive to fix.

**Firmware version in the greeting.** It is already there — `READY rookery
0.2.0 channels=6` — and it is what makes a support conversation take two
minutes instead of twenty. Bump it on every change that ships.

**Print consistency.** Colour lots vary, and the belly is a diffuser: a
"white" from a different batch changes how the finished thing looks. Buy the
white in quantity from one lot and keep a printed reference belly to compare
against.

---

## What this is worth as a product

Honestly: the enclosure is the product. The firmware and daemon are a
weekend; the thing that makes someone want one is that it is a penguin whose
belly glows, that it comes with four faces, and that swapping one takes four
screws and no soldering.

Which is also the risk. Anyone can print the enclosure — the meshes are MIT
and committed. What is actually being sold is *not having to*: the print
time, the 42 minutes of soldering, the sourcing, the tested unit, the cable
that works. Price it as assembly and support, not as a design people cannot
get, because they can.

The margin is in the assembly time. That is why the ring is the first change
to make, and why the honest answer to "can this be profitable" is: yes, at
around $89, once the LED loom stops being something a person does with their
hands.
