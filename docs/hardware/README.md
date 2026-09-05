# Hardware

A dev board, six LEDs, six resistors and a USB cable, inside a printed
penguin. That is the entire electrical design, and keeping it that small is
the point: no bus, no regulator, no capacitor, no level shifter, no radio.

```
  USB (power + data)
        │
        ▼
  ESP32-S3 dev board ──── 6 GPIO ──[ R ]──▶|── 6 LEDs ──┬── GND
        │                                                │
   115200 8N1                                     one lit at a time
   to the host daemon
```

Six discrete single-colour LEDs, one GPIO each, sharing a common ground,
poking straight out through the penguin's belly.

---

## The whole power story

| Draw | Current |
|---|---|
| Dev board, radio never initialised | ~50–70 mA |
| USB-UART chip + power LED | ~15–25 mA |
| Status LEDs, one lit at a time, ≤63% duty | ≤7 mA |

A USB 2.0 port gives **500 mA at 5 V** after enumeration. This uses under a
fifth of that with the light on, and the peak draw is a single LED — 7 mA,
well under the 20 mA-per-pin figure you would design an indicator against.

So: **no capacitor, no level shifter, no external supply, no regulator.** The
whole thing runs off the USB port that is already carrying the serial data.
That constraint is what makes the "only one LED lit at a time" rule a design
decision rather than a limitation.

The radio is never brought up. Not out of caution about power — an ESP32 is
happy to do Wi-Fi on USB — but because a status light that reports what your
agent sessions are doing has no business being reachable from the network,
and because it keeps the device an unintentional radiator if anyone ever
builds these to sell. See [../production.md](../production.md).

If you add anything that moves, the arithmetic stops being trivial:
[motion.md](motion.md).

## The pages

| You want to… | Read |
|---|---|
| Know what to buy, and what each part's limits are | [components.md](components.md) |
| Know which GPIO drives which colour, on which board | [pinout.md](pinout.md) |
| Build the circuit — resistors, ground bus, where the LEDs sit | [wiring.md](wiring.md) |
| Print the enclosure | [printing.md](printing.md) |
| Put it together | [assembly.md](assembly.md) |
| Change the shape, the LED size, the insert diameter | [enclosure.md](enclosure.md) |
| Add a servo or a motor, and not brown out the board | [motion.md](motion.md) |

## Source of truth

Where two documents disagree, believe them in this order:

1. **`firmware/platformio.ini`** — every pin number is a build flag there.
2. **`hardware/generate.py`** — every dimension in the printed parts is a
   named constant there, and every run measures what it built.
3. These pages.
4. Anything else.

Nothing in `hardware/stl/` is hand-edited; it is all output. If a mesh and
this documentation disagree, regenerate and see which one moved.

---

## Next

Start at [components.md](components.md) if you are sourcing parts, or at
[../getting-started.md](../getting-started.md) if you want the end-to-end
build in order.
