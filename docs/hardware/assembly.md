# Assembling the penguin

Six printed parts, four screws, four heat-set inserts, and about forty
minutes. Print them first: [printing.md](printing.md).

The whole electrical build happens on **two loose parts, on the bench, with
nothing in the way**. Then they snap together and drop into the body. That is
the reason the enclosure is shaped the way it is, so it is worth reading the
next two sections before you pick up an iron.

Parts and quantities: [components.md](components.md). The circuit:
[wiring.md](wiring.md).

Four screws, all the same, all on the back. The belly and the chassis take
none: they snap to each other, and the pair is captured between the window
they sit in and the cover's pillars. The eyes and the beak are press fits.

---

## Why the belly is its own part

Because loading six LEDs and soldering thirteen joints at the bottom of a
45 mm box is a miserable job, and doing the same thing on a flat plate lying
on your bench is an easy one.

So the white box is cut in two, on the plane where its front wall ends:

- **`belly`** — the front wall and everything the LEDs need. Both ends of
  every bore are in reach, the resistor channels and the tie arches are on
  it, and you can turn it over. The whole optical assembly gets built here,
  and it is a thing you can pick up and look at when it's done.
- **`chassis`** — the box behind it. Four walls, a shelf, and the dev board.

They locate on a lip and hold each other with two snap tongues, so the
sub-assembly stays together while you work. Then the back cover's pillars
clamp the pair forward into the body's window, which is what held the
one-piece version too. **Still no screws in either of them.**

### Which way up they go — nothing gets flipped

Both parts come off the plate already facing each other, and the whole
build happens in that orientation:

| On the plate | `chassis` (36.8 mm tall) | `belly` (17.2 mm tall) |
|---|---|---|
| **0 mm** | the open end that mates — face down on the plate | the LED face, the bit you see |
| **7.3 – 9.5** | the snap windows | |
| **8.2** | | **the mating face — *not* the top of the part** |
| **14.8 – 17.8** | the shelf; board posts stand above it | |
| **15.6 – 17.2** | | the snap barbs, at the top of the lip |
| **36.8** | the rear opening — board and cable go in here | |

So the chassis sits on the bench exactly as it printed, you drop the dev
board in through the opening at the top, and then you **lower it straight
down onto the belly.** Nothing is turned over at any point.

The thing that catches people is the belly: it is 17.2 mm tall on the
plate, but its mating face is at **8.2 mm — the middle**. The bottom 8.2 mm
is the panel that ends up *outside* the box, filling the body's window; the
9 mm of lip above it is what goes inside. Measure the barb from the bottom
of the part and it looks 8 mm out of place; measure it from the mating face
and it lands in the window.

The seam is entirely inside the black body. From the front the belly is one
unbroken panel, exactly as before.

## Where the hardware goes, and why there are only four inserts

| | |
|---|---|
| **6 LEDs** | Through the belly itself, in a 17 mm circle. Flanges rest on the back of a 5.6 mm plate; 3 mm of dome sticks out the front, 4 mm of straight lead behind before you bend them. |
| **6 resistors** | A channel down each side of the LED well, 3 × 3.4 mm, 32 mm long: three axial resistors end to end in each. |
| **The loom** | Four cable-tie arches, one above and one below each channel (6 × 3.2 mm tunnels), then back through a 7 × 21 mm window in the shelf, one each side, to the board. |
| **Dev board** | Upright on four posts in the chassis, under four snap tabs. Longer than the box is tall — its top goes out through the roof slot. |
| **USB plug** | Straight down out of the connector, past the shelf, through the floor slot, into the base of the penguin. 22.9 mm of clear drop. |
| **Slack wire** | The 22 mm of empty box between the LED leads and the front of the board. It used to be a light chamber that had to stay clear; now it's just space. |
| **Anything you add later** | The base cavity (~55 × 18 × 48 mm, less the plug) and the head cavity (~55 × 38 × 48 mm, less the top of the board). Both are empty and reachable with the cover off. |

**Only the body takes heat-set inserts — four of them, for the back cover.**
Nothing else in the build needs one:

- The **belly** and the **chassis** are captured, not bolted. The belly
  cannot go forward through the window (its flare is wider than the
  opening), the pocket locates it sideways, the chassis snaps to it, and
  four pillars on the back cover press the pair home from behind.
- The **board** is held by printed posts and snap tabs. An
  ESP32-S3-DevKitC-1 has no mounting holes to screw through in the first
  place.
- The **eyes** and the **beak** are press fits.

If the belly ever feels loose in the window, the thing to adjust is
`WINDOW_CLEAR`, not to add screws. If the two white parts feel loose on each
other, it's `LIP_CLEAR`. Both live in
[`generate.py`](../../hardware/generate.py) — see [enclosure.md](enclosure.md).

---

## Assembly

### 0. Get the electronics working first

On a breadboard, before anything is soldered short:

```bash
cd firmware && pio run -e esp32s3 -t upload
cd ../host && pip install -e . && rookery test
```

On boot the firmware walks all six LEDs in order. Any LED that stays dark is
a wiring fault, and you want to find it now rather than after it's inside a
penguin. Full circuit in [wiring.md](wiring.md).

### 1. Four heat-set inserts, into the body

Lay the body face down, open back up. Four round bosses sit against the
inside wall — two at shoulder height, two low. Their pockets face straight
up at you.

Set the iron to about **200 °C** for PLA, sit the insert on the hole, and let
the iron's own weight carry it in. The pockets have a 45° lead-in, so a
straight start is easy. Pushing hard squeezes molten plastic up around the
flange and leaves the insert proud. Stop when the top is flush and let it
cool before touching it.

The pockets are cut **3.85 mm** across for a **4.0 mm** insert. That 0.15 mm
is deliberate — it's the material the insert melts into and grips. If yours
measure differently, `python3 generate.py --insert-od 4.2` and reprint.

### 2. Build the LED loom on the belly

Put the `belly` on the bench, face down, lip up. Everything in this step
happens on that one flat plate, with both ends of every hole in reach.

**The LEDs.** Six bores go straight through the panel; behind them the wall
is cut away to a 27 mm well, so you can see and reach every one. Push each
LED in **from the back, dome first**, until the flange at its base lands on
the back of the plate. That sets everything for you: 5.6 mm of the LED is
inside the plate, **3 mm of dome stands out of the front**, and it sits dead
straight. Turn the plate over and check the ring looks even before you
solder anything. Keep the colour order consistent so you can trace the loom
later.

> **Worth doing:** rub the dome of each LED flat on 400-grit sandpaper until
> it's frosted. A clear 5 mm LED throws a narrow ~20° beam — hard and bright
> straight on, nearly gone from the side. A sanded one reads the same from
> anywhere in the room. Two minutes, no cost, and it is still the single
> biggest improvement you can make to how this looks.

**The resistors.** A channel runs down each side of the well, 3 mm wide and
3.4 mm deep, long enough for three axial resistors end to end. Press them
in from the back — bare, or in thin heat-shrink.

**The loom.** There is **4 mm of straight lead** behind each flange before
anything is in the way; bend them outward there. Bend all six cathodes
together into a ring and solder — that's your ground bus. Solder each anode
to a resistor sitting in its channel, then run a wire from each resistor
toward where the board will be. **Leave the wires long**, and keep them
**inboard of the lip** — the lip is the sealing face, and a wire lying
across it stops the two halves closing.

Tie the bundle down with a small cable tie through one of the **four
arches**, one above and one below each channel: 6 mm wide, 3.2 mm of
headroom.

### 3. Clip the dev board into the chassis

Four posts stand on the **back** of the shelf — two low, two high. Press the
board down onto them and it clicks under four retention tabs: columns just
outboard of the board with a lip that reaches back over its edge.

It sits **upright, USB connector pointing down**. Three things about that:

- The board is **longer than the box is tall**, on purpose. Its top passes
  out through a slot in the chassis roof into the head.
- Its connector sits low enough that a plug has **22.9 mm of clear drop**
  below it. The shelf stops short above the connector and a slot in the
  chassis floor lets the plug through into the base of the penguin.
- There is **6 mm** between the board and the back of the shelf.

### 4. Solder the belly to the board, then snap them together

Bring the two halves together far enough to reach, and solder the seven
wires — six anodes and the ground bus — to the board per the channel map in
[wiring.md](wiring.md). Both parts are still loose in your hands, which is
the whole reason for splitting them.

Then lower the chassis straight down onto the belly — same way up as they
both printed — until the **two snap tongues click** into the windows in its
side walls. There is one
window in each side wall, 11 × 2.2 mm, about halfway up — you can see the
barbs sitting in them once they are home. Run the loom down through the
shelf windows on the way in; check it is inboard of the lip and not
pinched, and that the two faces have closed flat all the way round.

That pair is now the whole electrical assembly: one object you can pick up
and test.

> **To get them apart again**, push both barbs in through the windows in the
> chassis's side walls with a small screwdriver and pull. There is nothing
> else holding them once the back cover is off.

### 5. Eyes and beak

Press the **eyes** into the head from **inside** the body — the bar behind
them stops them going out the front. The **beak** goes in from the front;
its tang presses into the socket below the eyes.

Both are 0.18 mm interference fits. A dab of glue if you want to be sure.

### 6. Thread the cable

Feed the USB cable through the slot in the bottom of the back cover
**before** plugging it into the board, then zip-tie it to the two posts
either side of the slot. A tug on the cable then pulls on the enclosure and
not on the board's USB connector.

### 7. Close it up

Drop the pair into the body from behind — **LEDs first, they fit through
the window with 8 mm to spare on every side.** The belly's 45° flare seats
against the back of the window and its face comes out flush with the black
skin, with the six domes standing 3 mm proud of it. It cannot go forward
through the window, and the pocket it sits in locates it sideways.

Then the back cover. The four pillars on it land on the chassis's rear rim
and press the whole stack forward into its seat — cover, box, belly, window
— which is what takes the rattle out. **4 × M3 × 1/4"** through into the
body's inserts. Snug, not tight — you're clamping a printed part.

Rubber feet underneath if you have them.

---

## Next

Plug it in and run the daemon:
[getting-started.md](../getting-started.md#5-run-the-daemon). If a colour
looks wrong or one channel is dead, [troubleshooting.md](../troubleshooting.md).

Want a different face on the belly, or a glowing panel instead of six domes?
[printing.md](printing.md#choosing-the-face).
