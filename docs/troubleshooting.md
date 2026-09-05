# Troubleshooting

Roughly in the order things go wrong: the cable, then the wiring, then the
hooks, then the things that are working correctly and only look broken.

---

## The board

**Board doesn't appear in `rookery ports`** — 90% of the time it's a
charge-only USB cable. Then it's the wrong socket on an S3 (native vs UART).
Then it's a missing CP210x/CH340 driver on macOS or Windows.

**`rookery ports` lists it but `rookery probe` finds nothing** — the port is
right and the firmware isn't. Flash it: `pio run -e esp32s3 -t upload`, then
`pio device monitor` and look for `READY rookery 0.2.0 channels=6`. If the
monitor is silent on an S3, you are on the other socket — the default build
routes Serial to the **native USB** port, not the `UART` bridge.

**`rookery probe` finds it but the daemon doesn't** — something else has the
port open. Only one process can. Stop the daemon before running `test` or
`set`, and stop any serial monitor before running the daemon.

**Serial permissions on Linux** — `sudo usermod -aG dialout $USER`, then log
out and back in. Or install [`scripts/99-rookery.rules`](../scripts/99-rookery.rules)
for a stable `/dev/rookery` symlink and pass `--port /dev/rookery`.

## The lights

**One LED never lights during the boot self-test** — that channel is miswired,
or the LED is in backwards. The long leg is the anode and goes to the resistor.

**Blue or white looks dead or very faint** — expected, not a fault. Their
forward voltage is nearly the full 3.3 V a GPIO can supply, so they only get
about 2 mA where the others get 7. The firmware already compensates with
higher PWM duty; [hardware/wiring.md](hardware/wiring.md) has two stronger
fixes.

**Bright head-on, gone from the side** — that's a clear 5 mm LED's ~20°
beam. **Sand the dome of each one flat on 400-grit** until it's frosted and
it reads the same from anywhere in the room. Two minutes, no cost, and it is
the single biggest improvement you can make to how this looks.

**The whole thing looks dim** — check `BRIGHT` isn't turned down, and see
the blue/white note above. The LEDs face you directly, so filament colour has
nothing to do with it.

**The colours don't read evenly against each other** — six LEDs from a parts
drawer never will. Trim them live over serial with `GAIN <colour> <0-255>`,
then bake the values into `build_flags` — `env:esp32s3-tuned` in
`platformio.ini` exists for that.
[hardware/wiring.md](hardware/wiring.md#trimming-brightness-without-reflashing).

**The eyes don't glow** — they can't. They used to pick up spill light from
inside the chassis; the LEDs point out the front now, so there is none. The
pupils go right through and read dark against the inside of the head.

## The daemon

**`rookery: cannot listen on 127.0.0.1:8787`** — something is already there,
almost always another `rookery run`. Stop it, or pass `--http-port` to run a
second one on purpose. This is deliberately fatal: a second daemon that binds
quietly beside the first means half your reports reach one that isn't driving
the light.

**`rookery: refusing to listen on … without a token`** — you asked it to bind
off localhost. Pass `--token <secret>` and give that token to whatever reports
in, or `--insecure` if you really mean it.

**Light stuck on green** — the daemon died. The firmware notices after 30 s and
switches to the orange blink.

**Orange, slow blink** — that is the link-lost state: the daemon stopped
talking. Don't trust the colour that was there before it. Restart the daemon.

## The hooks

**Light never changes** — run `rookery status` while a session is live. If
sessions are listed, the problem is the serial link; if not, it's the hooks.
Run `/hooks` inside Claude Code to confirm they registered.

**Hook errors in the transcript** — the daemon isn't running. HTTP hooks report
a connection failure as a non-blocking error: visible, harmless, and it won't
interrupt your work. Switch to the command-hook variant if it bothers you; that
one exits 0 silently.

**Hooks installed but nothing fires** — restart the Claude Code sessions that
were already open. They read settings at startup.

## Something else is driving it

**The light is green but no agent is running** — something else is holding
it. `rookery status` lists every session and source behind the current
colour, with a `detail` line saying what each one is.

**A source is stuck on** — sources expire on their own (180 s by default,
`--ttl` to change), but a job that reported `needs_you` deliberately holds
for an hour so you actually see it. `rookery notify clear --source <name>`
to drop it now.

**`rookery poll` prints "output was not JSON"** — the command printed a
traceback or a "not found" instead of a snapshot. That is a broken reporter,
not a state, so the light is deliberately left alone. Run the command by hand
and see what it says. Note that `--json` reads **stdout only**, so a warning
on stderr is not the cause; check what the command actually prints on stdout
with `your-command 2>/dev/null`.

**`rookery poll` prints "command failed … leaving the light alone"** — the
command itself exited non-zero. A dropped VPN is not a failed job, so the
default is to say nothing. `--on-error needs_you` if you would rather know.

**`rookery poll` asks for a password every minute** — give SSH a shared
connection: `ControlMaster auto` + `ControlPersist 8h` in `~/.ssh/config`,
then authenticate once by hand. Details in
[integrations.md](integrations.md).

---

## Still stuck?

Take the daemon out of it. The serial protocol is plain text, so you can drive
the light by hand:

```bash
printf 'STATE needs_you\n' > /dev/ttyUSB0
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Then type `PING`, `STATE working`, `IDENT`, `LED orange 255`. If that works
and the daemon doesn't, the problem is in the hook wiring, not the hardware.
Full command list: [protocol.md](protocol.md).
