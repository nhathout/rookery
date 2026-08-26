# Power budget & adding a motor

> **The shipped enclosure has no servo mount.** The current design is
> deliberately static — shell, backplate, nest, eyes, belly. This document
> stays because the power arithmetic matters for any expansion, and because
> the firmware still carries optional servo support if you want to add a
> moving part of your own.

## Short answer

**No regulator, no external supply.** The light itself draws almost nothing,
and even one micro servo doing brief moves fits inside a USB port's budget with
room to spare. You need one capacitor and one rule about which pin to tap.

The rule: **take servo power from the `5V` / `VIN` pin, never from `3V3`.**

## The budget

A USB 2.0 port gives you **500 mA at 5 V** after enumeration (USB 3.0 gives
900 mA). Most desktop ports will quietly supply more, but 500 mA is the number
to design against.

| Draw | Current |
|---|---|
| ESP32 dev board (WiFi never initialised) | ~50–70 mA |
| USB-UART chip + power LED | ~15–25 mA |
| Status LEDs (one lit at a time, ≤63% duty) | ≤7 mA |
| SG90 servo, moving under light load | ~150–250 mA |
| **Total during a wag** | **~300 mA** ✅ |
| SG90 servo, **stalled** | ~650–750 mA |
| **Total if it stalls** | **~800 mA** ❌ |

So the whole design hinges on one thing: **never let the servo stall.** A
stalled servo will trip your PC's port current limit, and Windows in particular
will disable the port and pop a "USB device drew too much power" notification.

Two defences, both already in the firmware:

- Travel is limited to `SERVO_REST ± SERVO_SWING` (90° ± 28°). Set these so the
  penguin never drives into a hard stop.
- The servo is **detached** 700 ms after a move finishes. A servo that's still
  being commanded holds torque, hunts, and buzzes audibly on a quiet desk.
  Released, an SG90 draws essentially nothing.

## Why not the 3V3 pin

The `3V3` pin comes off the board's onboard linear regulator (usually an
AMS1117). Three problems:

1. A servo wants 5 V. At 3.3 V it's weak and jittery.
2. The regulator is linear, so every milliamp the servo pulls burns
   `(5 − 3.3) × I` watts as heat in a tiny SOT-223 package.
3. Servo inrush yanks the rail down. The ESP32's brownout detector trips
   around 2.6 V on the 3.3 V rail and **resets the chip**.

That third one is the single most common failure in projects like this. The
symptom is a board that reboots every time the motor moves.

## The capacitor

```
  5V (VIN) ──┬──────────────── servo red
             │
          ╔══╧══╗
          ║ 470µF║  electrolytic, 6.3 V or higher
          ╚══╤══╝   stripe = negative = GND side
             │
  GND ───────┴──────────────── servo brown/black
```

470–1000 µF across the servo's supply, physically **close to the servo**, not
next to the ESP32. It absorbs the inrush spike locally so the dip never reaches
the regulator. This is a $0.20 part that prevents the most annoying failure mode
in the build. Fit it.

## Wiring

```
  ESP32                          SG90 servo
  ─────                          ──────────
  5V / VIN ──┬───────────────── red     (power)
          [470µF]
  GND ───────┴───────────────── brown   (ground)

  GPIO17 ───────────────────── orange  (signal)   [S3; GPIO14 on classic]
```

3.3 V PWM into an SG90 works fine — no level shifter needed. If your servo's
wires are a different colour scheme, the order at the connector is almost always
**ground, power, signal** with ground on the outside edge.

Build with the servo enabled:

```bash
pio run -e esp32s3-penguin -t upload      # or esp32dev-penguin
```

That env adds `-DENABLE_SERVO` and pulls in the `ESP32Servo` library.

> **Board note:** the servo needs an **ESP32-S3 or a classic ESP32**. The S3
> has 8 LEDC channels — six LEDs plus one servo is seven, which fits. The C3
> and C6 have exactly six, and the LEDs use all of them.

**If the servo jitters or the LEDs flicker when it moves**, the LEDC peripheral
is being asked to serve two very different clock configurations (the LEDs run
at ~1 kHz / 8-bit, the servo at 50 Hz / 16-bit). The S3's four LEDC timers are
enough for both, but if your core version allocates them awkwardly, moving one
LED to a different GPIO or dropping `analogWriteFrequency` usually settles it.

## Calibration

Assemble loosely first, then in a serial monitor:

```
WAG                 # run the full attention wiggle
LED white 255       # (unrelated, but handy for checking the loom)
```

Adjust in `platformio.ini` and reflash:

- `SERVO_REST` — the neutral angle. Start at 90 and adjust.
- `SERVO_SWING` — how far it turns each way. **Reduce this if the servo grinds
  or buzzes at the extremes** — that's it hitting a mechanical stop, which is
  the stall condition you're trying to avoid.
- `SERVO_STEP_MS` — pace of the wiggle. Higher is calmer.

Get the horn position roughly right *mechanically* before fine-tuning in
software: pull the horn off the spline, centre the servo with `WAG`, and press
the horn back on pointing where you want.

You'll need to make room for it yourself — add a pocket to `build_backplate()`
in `generate.py`, or mount the servo outside the shell. There is room: the
cavity is 46 mm deep and the dev board only uses the bottom 13 mm of it. The
interference check in `generate.py` will tell you straight away if whatever
you add collides with the nest, the belly, or the board.

## What the firmware does with a servo

If you build with `-DENABLE_SERVO`, the servo wags on the **transition into
`needs_you`**, then settles. It deliberately does *not* react to `working` or
`idle` — a desk ornament that moves constantly stops being charming after about
an hour. `WAG` triggers it manually over serial.

The firmware only reacts to the state *change*, not the state value, because
the daemon re-sends the current state every 8 seconds as a heartbeat. Wagging
on the value would mean wagging forever.

## If you'd rather use a different motor

### DC motor

You cannot drive a motor from a GPIO pin. The absolute maximum is 40 mA and the
recommended continuous figure is 12 mA; a motor will pull ten to fifty times
that and take the pin (or the chip) with it.

```
  GPIO ──[ 1kΩ ]── gate/base ┐
                             │  logic-level N-MOSFET (IRLZ44N, 2N7000)
                             │  or NPN (2N2222) for small motors
              source/emitter ┴── GND

  5V ──┬──── motor ──┬── drain/collector
       │             │
       └──|◀── 1N4001 flyback diode, cathode (stripe) to 5V
```

The flyback diode is not optional. Collapsing the motor's magnetic field
generates a reverse spike that will destroy the transistor without it.

Budget-wise: a small hobby DC motor stalls at 0.5–1 A, which blows past your
USB allowance. Fine for brief pulses, not for continuous running.

### 28BYJ-48 stepper + ULN2003

Draws roughly **240 mA continuously while energised** — it fits in the budget,
but it holds that current even when stopped, gets warm, and wastes power. Drive
all four ULN2003 inputs LOW between moves to de-energise it. Uses four GPIOs.

### When you genuinely need external power

More than one servo, any continuous-duty motor, or anything above ~300 mA.

Then: a 5 V 2 A USB wall adapter powering the motor directly, with **grounds
tied together** between the adapter and the ESP32. Keep the ESP32 on the PC's
USB cable for data. Don't feed external 5 V into the board's `5V` pin while
USB is also connected unless you're sure your board has proper diode isolation
— it usually does, but "usually" isn't a thing to bet a motherboard on.

For this project, none of that applies. One servo, one USB cable, one
capacitor.
