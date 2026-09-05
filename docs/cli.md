# `rookery` command reference

Twelve subcommands. Some talk to the board over serial, some talk to a running
daemon over HTTP, and three deal with Claude Code's settings file.

```bash
cd host && pip install -e .
rookery --help
```

`-v` / `--verbose` turns on debug logging, including everything the device
says back. It works before or after the subcommand on `run` and `test`.

---

## Shared options

Whichever group a command falls into, these are the flags it takes.

**Serial** — `probe`, `test`, `set`, `run`

| Flag | Default | |
|---|---|---|
| `--port` | autodetect | Serial device. Autodetect probes every port for a `PING`/`PONG` answer, known USB-serial chips first |
| `--baud` | 115200 | |

**HTTP** — `run`, `notify`, `watch`, `poll`, `status`, `install-hooks`, `print-hooks`

| Flag | Default | |
|---|---|---|
| `--http-host` | `127.0.0.1` | |
| `--http-port` | `8787` | |

**Source** — `notify`, `watch`, `poll`

| Flag | Default | |
|---|---|---|
| `--source` | *required* | Name for this reporter, e.g. `bench` or `policy-server` |
| `--ttl` | 180 | Seconds before the daemon assumes this reporter died and stops listening to it. `0` = never |
| `--token` | — | Shared token, if the daemon needs one |

---

## Running the light

### `rookery run`

The daemon. Hook events in, serial commands out.

| Flag | Default | |
|---|---|---|
| `--brightness N` | unset | 0–255 master scale, sent once per connection. Unset leaves the firmware at its own default of 160 |
| `--simulate` | off | Log state changes instead of driving hardware |
| `--token SECRET` | — | Require `Authorization: Bearer SECRET` on every POST |
| `--insecure` | off | Allow binding off-localhost **without** a token |

It binds the HTTP endpoint, opens the serial port, and re-sends the current
state every 8 seconds — which doubles as the heartbeat that keeps the
firmware's link watchdog fed. It reconnects on its own if the board is
unplugged, and it tolerates the board being absent entirely.

Binding anywhere but localhost without `--token` is **refused**, with exit
code 2. An open endpoint that anything on the network can drive is not a
thing to hand out by accident.

Two daemons on one port is also refused: on Windows a second `rookery run`
used to bind the same port quietly and shadow the first, so half your reports
reached a daemon that was not driving the light.

### `rookery status`

What is actually behind the current colour — every session and every source,
with ages, TTLs and detail lines. JSON on stdout. Exit 1 if the daemon isn't
reachable.

This is the disambiguator. The light shows one colour, so it shows the most
urgent thing; `status` tells you which thing that was.

---

## Talking to the board directly

These bypass the daemon entirely. **Stop the daemon first** — two processes
writing the same serial port is not a thing either of them handles.

### `rookery ports`

Every serial port, most-likely-ESP32 first, with VID:PID. `*` marks a known
USB-serial chip: Silicon Labs CP210x, WCH CH340/CH9102, FTDI, or Espressif
native USB.

### `rookery probe`

Open the port and check something answers `PING` with `PONG` or `READY`. Exit
0 if found, 1 if not. With no `--port`, tries every candidate.

### `rookery test`

Cycle green → yellow → red → blue so you can check the wiring.

| Flag | Default | |
|---|---|---|
| `--dwell N` | 2.5 | Seconds per colour |
| `--brightness N` | — | Sent once before the cycle |

### `rookery set <state>`

Force one state and exit: `working`, `idle`, `needs_you` or `asleep`.

---

## Driving it from something else

Sessions and sources are equals in the registry, and the most urgent state
across all of them wins. Recipes and worked examples:
[integrations.md](integrations.md).

### `rookery notify <state>`

One-shot report from anything that can run a command.

```bash
rookery notify working   --source deploy --detail "build 4412" --ttl 900
rookery notify needs_you --source deploy --detail "smoke test failed"
rookery notify clear     --source deploy
```

`clear` removes the source entirely. States: `working`, `idle`, `needs_you`,
`asleep`, `clear`. `--detail` is free text shown by `rookery status`;
`--quiet` suppresses the confirmation line. Exit 1 if the daemon can't be
reached.

### `rookery watch -- <command>`

Run a command with the light following it.

```bash
rookery watch --source weekly -- python -m jobs.weekly_run
```

| Flag | Default | |
|---|---|---|
| `--heartbeat N` | 30 | Re-report this often so the TTL never lapses mid-run |
| `--hold-ok N` | 300 | Seconds to stay yellow after it succeeds |
| `--hold-fail N` | 3600 | Seconds to stay **red** after it fails |

Green while it runs. Red and staying red if it exits non-zero — a run that
died at 03:00 is exactly the thing you want to walk in and see. Yellow for
five minutes if it succeeds, then the source clears itself. Ctrl-C clears the
source rather than reporting a failure. The command's output and exit code
pass straight through.

### `rookery poll --command '...'`

Ask something what it is doing on a timer, and map the answer onto a state.
This is how a machine you are **not** sitting at gets onto the light: the
daemon asks, rather than the far end pushing.

| Flag | Default | |
|---|---|---|
| `--command` | *required* | Shell command to run |
| `--every N` | 60 | Seconds between polls |
| `--timeout N` | 30 | Give up on the command after this long |
| `--json` | off | The command prints JSON — select on fields instead of regexes |
| `--needs-you-if RULE` | — | JSON rule. Repeatable |
| `--working-if RULE` | — | " |
| `--idle-if RULE` | — | " |
| `--preset sge\|slurm` | — | Ready-made regexes for a queue listing |
| `--needs-you-re RE` | — | Regex; overrides the preset |
| `--working-re RE` | — | " |
| `--idle-re RE` | — | " |
| `--otherwise STATE` | `clear` | State when nothing matched |
| `--on-error STATE` | `skip` | What to do when the command itself fails. `skip` leaves the light alone |

Rules are evaluated `needs_you` → `working` → `idle`, first match wins. A
rule is a dotted path, optionally with one comparison:

| Rule | True when |
|---|---|
| `blockers` | the path exists and is non-empty / non-zero |
| `queue.running>0` | numeric comparison — `>` `<` `>=` `<=` |
| `crew[*].state==failed` | `[*]` means **any element** of a list |
| `budget.mode!=normal` | `!=` as well |

Deliberately not `eval`. If `--json` output doesn't parse, or if the command
itself fails and `--on-error skip` is in effect, `poll` says so on stdout and
leaves the light alone rather than inventing a state. Ctrl-C clears the
source.

With `--json`, the snapshot is read from **stdout only**. A tool that writes a
deprecation warning to stderr while printing a perfectly good snapshot should
not put the light out, and diagnosing that from across the room is impossible.
stderr is still read when stdout is empty, so a command that only fails is
still reported.

---

## Hooks

### `rookery install-hooks`

Merge the hook entries into `~/.claude/settings.json` (`--settings PATH` for
somewhere else). Backs the original up to `settings.json.bak` first, touches
only its own entries, and is idempotent — every group it writes is tagged, and
re-running drops the old tagged groups before adding new ones.

The URL written into the hooks comes from `--http-host` / `--http-port`, so
install against the daemon you actually intend to run.

### `rookery uninstall-hooks`

Remove exactly those tagged groups again. Takes `--settings`, nothing else.

### `rookery print-hooks`

Dump the same JSON to stdout without touching any file. For pasting into a
settings file by hand, or for diffing against what is already there.

---

## Next

- What each hook event means: [integrations.md](integrations.md)
- What goes down the serial wire: [protocol.md](protocol.md)
- When something isn't behaving: [troubleshooting.md](troubleshooting.md)
