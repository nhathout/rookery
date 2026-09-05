# Getting started

Parts → firmware → circuit → daemon → hooks → enclosure. Skip whatever you
have already done; every step below stands on its own and says what it
expects to find.

The order is deliberate. The enclosure takes about thirteen hours to print,
so the electronics come first: you can have the whole thing working on a
breadboard before a single part comes off the plate, and you want to find a
backwards LED then rather than after it is inside a penguin.

If you have no hardware at all yet, jump to
[5](#5-run-the-daemon) and run `rookery run --simulate`. The entire hook
pipeline works without a board.

---

## 1. Get the parts

Full list with limits and part numbers: [hardware/components.md](hardware/components.md).

The minimum to get to step 5:

- An ESP32-S3 dev board (classic ESP32, C3 and C6 also work)
- Six through-hole LEDs — red, green, blue, yellow, orange, white
- Six resistors, 100–330 Ω
- **A USB cable that carries data.** Not a charge-only cable

Everything else — inserts, screws, filament, zip ties — is for the enclosure
and can wait.

## 2. Flash the firmware

Firmware is Arduino on [PlatformIO](https://platformio.org/).

```bash
pip install platformio
cd firmware
pio run -e esp32s3 -t upload
pio device monitor              # expect: READY rookery 0.2.0 channels=6
```

That banner is the whole test at this stage: if you see it, the board is
flashed and the serial link works. On boot the firmware also walks all six
LEDs in order as a self-test — which does nothing visible yet, but will in
step 3.

> **ESP32-S3 users:** a DevKitC-1 has two USB-C sockets. The default build
> routes Serial to the **native USB** port (marked `USB`). If your board has
> only one socket, that's the one. To use the `UART` bridge instead, build
> `esp32s3-uart`.

Other targets: `esp32dev`, `esp32c3`, `esp32c6`, `esp32s3-penguin` (adds the
servo), `esp32s3-neopixel` / `esp32s3-rgb` (alternate LED hardware). Pin maps
for all of them: [hardware/pinout.md](hardware/pinout.md).

## 3. Build the circuit

Six copies of the same thing — GPIO, resistor, LED, common ground — on a
breadboard for now. Which GPIO drives which colour, and why the resistors
differ by colour: [hardware/wiring.md](hardware/wiring.md).

Power-cycle the board when it's built. The boot self-test walks all six
channels in order, so **any LED that stays dark is a wiring fault**, and you
now know exactly which channel to look at. The long leg is the anode and goes
to the resistor.

## 4. Install the daemon

```bash
cd host
pip install -e .

rookery ports     # find your board (* marks likely candidates)
rookery probe     # confirm it answers
rookery test      # cycle green → yellow → red → blue
```

If `test` cycles the colours, **the hardware is finished.** Everything after
this is software.

**Linux:** for serial permissions, either `sudo usermod -aG dialout $USER`
(then log out and back in), or install
[`scripts/99-rookery.rules`](../scripts/99-rookery.rules) for a stable
`/dev/rookery` symlink that survives replugging.

Six LEDs from a parts drawer will never be balanced. This is the point to
trim them: [hardware/wiring.md](hardware/wiring.md#trimming-brightness-without-reflashing).

## 5. Run the daemon

```bash
rookery run
```

It binds `127.0.0.1:8787`, finds the board on its own, and re-sends the
current state every 8 seconds as a heartbeat. Leave it running.

```bash
rookery run --brightness 90    # dimmer, for a dark room
rookery run --simulate         # log state changes, no hardware needed
```

Every flag: [cli.md](cli.md).

**Autostart on Linux:**

```bash
mkdir -p ~/.config/systemd/user
cp scripts/rookery.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rookery
sudo loginctl enable-linger $USER    # survive logout
```

macOS: [`scripts/com.rookery.daemon.plist`](../scripts/com.rookery.daemon.plist).

## 6. Wire it to Claude Code

```bash
rookery install-hooks
```

Merges the hook entries into `~/.claude/settings.json`, backing up the
original to `settings.json.bak` first. It only ever touches its own entries —
your existing hooks are preserved — and re-running it is idempotent.

Restart any running Claude Code sessions to pick up the change, then ask one
of them something. `/hooks` inside Claude Code confirms they registered.

Prefer to do it by hand? Paste [`claude/hooks.http.json`](../claude/hooks.http.json)
into your settings yourself, or dump the same block with `rookery print-hooks`.
To undo: `rookery uninstall-hooks`.

**If you'd rather Claude Code not make localhost HTTP calls**, there is a
command-hook variant: copy [`claude/rookery_hook.py`](../claude/rookery_hook.py)
to `~/.claude/hooks/`, chmod +x, and use
[`claude/hooks.command.json`](../claude/hooks.command.json) as your settings
block instead. It spawns a Python process per event, so it is slower — but it
fails completely silently when the daemon isn't running, which the HTTP path
does not.

Which event becomes which colour: [integrations.md](integrations.md).

## 7. Print and assemble the enclosure

The meshes are committed — you don't need to run anything.

- What to print, on which plate, in which filament:
  [hardware/printing.md](hardware/printing.md)
- Inserts, loom, snap, close it up:
  [hardware/assembly.md](hardware/assembly.md)
- Change a dimension or the penguin's shape:
  [hardware/enclosure.md](hardware/enclosure.md)

Two plates, one filament change, four screws that are all the same screw.

## 8. Point it at your other work

Claude Code is wired up by now, but the light is more useful when it also
knows about the long-running things you actually wait on. Anything can drive
it — a training run, a job queue, a machine you aren't sitting at:

```bash
# wrap a command: green while it runs, red if it fails, yellow when it's done
rookery watch --source bench -- python -m tools.bench_tools --runs 3

# ask something that prints JSON what it's doing, once a minute
rookery poll --source ci --every 60 --json \
  --command 'gh run list --json status' --working-if 'status==in_progress'

# report from a shell script, anywhere
rookery notify needs_you --source deploy --detail 'smoke test failed'
```

Sessions and sources are equals, and the most urgent one wins. The full set
of recipes — including machines that can't reach you, and how to give a LAN
machine a token: [integrations.md](integrations.md).

---

## Stuck?

| Symptom | Look at |
|---|---|
| Board doesn't appear in `rookery ports` | The cable, then the socket — [troubleshooting.md](troubleshooting.md) |
| One LED never lights in the boot self-test | That channel is miswired — [hardware/wiring.md](hardware/wiring.md) |
| Blue or white look dead or very faint | Expected, not a fault — [hardware/wiring.md](hardware/wiring.md) |
| Light never changes | `rookery status` — [troubleshooting.md](troubleshooting.md) |
| Light is green but no agent is running | Something else is holding it — [integrations.md](integrations.md) |
| Something else | [troubleshooting.md](troubleshooting.md) |
