# Serial protocol

115200 baud, 8N1, newline-terminated ASCII. Deliberately human-readable so you
can drive the light from a serial monitor, a shell script, or anything else —
the daemon has no privileged access.

## Host → device

| Command | Effect | Reply |
|---|---|---|
| `PING` | Liveness / identification probe | `PONG rookery 0.2.0` |
| `STATE working` | Green LED, slow breathe | `OK state working` |
| `STATE idle` | Yellow LED, steady dim | `OK state idle` |
| `STATE needs_you` | Red LED, fast pulse | `OK state needs_you` |
| `STATE asleep` | Blue LED, very dim | `OK state asleep` |
| `LED <colour> <0-255>` | Drive one LED directly | `OK led <colour>` |
| `GAIN <colour> <0-255>` | Per-channel brightness trim | `OK gain <colour> <n>` |
| `BRIGHT <0-255>` | Master brightness scale | `OK bright <n>` |
| `WAG` | Run the penguin's attention wiggle | `OK wag` |
| `IDENT` | Blink white for 2 s | `OK ident` |
| `OFF` | Same as `STATE asleep` | `OK off` |

Valid colours: `red`, `green`, `blue`, `yellow`, `orange`, `white` (or the
bare index `0`–`5`).

`GAIN` is how you balance six mismatched LEDs without reflashing. It's a
runtime trim only — set it, find values you like, then move them into
`build_flags`.

`WAG` replies `OK wag ignored` on firmware built without `-DENABLE_SERVO`, so
it's always safe to send. The penguin also wags on its own, but only on the
*transition* into `needs_you` — the daemon re-sends the current state every
8 seconds as a heartbeat, so reacting to the value rather than the change
would make it wag forever.

Unknown commands return `ERR unknown`. Malformed arguments return `ERR <cmd>`.

## Device → host

On boot: `READY rookery 0.2.0 channels=6`

Before that banner the firmware walks all six LEDs in sequence as a self-test.

Nothing else is emitted unsolicited. The daemon drains and debug-logs whatever
arrives, so extra chatter is harmless if you add your own.

## Link watchdog

If the device receives nothing for `LINK_TIMEOUT_MS` (30 s default) *after
having heard from a host at least once*, it drops to a slow orange blink: the
"link lost" state.

This exists because the alternative failure mode is worse: if the daemon dies
mid-turn while the light is green, you'd have a light on your desk confidently
telling you a session is running when nothing is. The orange blink means
"don't trust me." It's a blink rather than a steady colour so it can't be
mistaken for the steady yellow idle state at a glance.

The daemon re-sends the current state every 8 seconds, which doubles as the
heartbeat that keeps the watchdog fed.

## Testing without the daemon

```bash
# Linux/macOS
printf 'STATE needs_you\n' > /dev/ttyUSB0

# Or interactively
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Then type `PING`, `STATE working`, `IDENT`, `LED orange 255`, and so on. If
this works but the daemon doesn't, the problem is in the hook wiring, not the
hardware.

---

## Next

- Which GPIO each colour lives on: [hardware/pinout.md](hardware/pinout.md)
- Balancing six mismatched LEDs: [hardware/wiring.md](hardware/wiring.md)
- The host side of this conversation: [cli.md](cli.md)
