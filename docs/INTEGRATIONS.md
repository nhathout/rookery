# Driving the light from something other than Claude Code

The beacon started out showing Claude Code sessions. It now shows anything
you point at it — an agent crew running on a schedule, a training job, a
queue on a machine you are not sitting at.

Two kinds of thing drive it:

| | What it is | Fed by |
|---|---|---|
| **session** | One Claude Code session, one per terminal | hooks → `POST /hook` |
| **source** | Anything else, named by you | `POST /state`, or the verbs below |

They are equals. The light shows the **most urgent state across all of
them** — `needs_you` beats `working` beats `idle` — so a crewmate that failed
still turns the penguin red while an agent is busy elsewhere.

Sources carry a **TTL** that sessions do not. Claude Code always sends
`SessionEnd`; a reporter on another machine can lose its network, get
killed, or have its laptop shut. Without an expiry the light would sit green
forever on the strength of a job that died an hour ago, which is worse than
showing nothing at all.

---

## The three verbs

### `rookery notify` — one-shot

```bash
rookery notify working   --source crew --detail "weekly_run started" --ttl 900
rookery notify needs_you --source crew --detail "franky failed"
rookery notify clear     --source crew
```

The whole API from a shell script. `clear` removes the source entirely.

### `rookery watch` — wrap a long job

```bash
rookery watch --source weekly -- python -m jobs.weekly_run
```

- **green** while it runs, re-reporting every 30 s so the TTL never lapses
- **red, and it stays red** if it exits non-zero — a run that died at 03:00
  is exactly the thing you want to walk in and see
- **yellow for five minutes** if it succeeds, then the source clears itself
- the command's output, and its exit code, pass straight through

Tune with `--hold-ok`, `--hold-fail`, `--heartbeat`.

### `rookery poll` — ask something what it is doing

```bash
rookery poll --source crew --every 60 --json --command '...' \
  --needs-you-if 'crew[*].state==failed' --working-if 'queue.running>0'
```

For anything that already knows its own state and will tell you when asked —
a `status` subcommand, a queue listing, an HTTP endpoint behind a `curl`. It
classifies the output two ways.

**By field**, for anything that prints JSON — which most tools with a
`status` command already do. Pass `--json` and give rules. A rule is a dotted
path, optionally with one comparison:

| Rule | True when |
|---|---|
| `blockers` | the path exists and is non-empty / non-zero |
| `queue.running>0` | numeric comparison — `>` `<` `>=` `<=` |
| `crew[*].state==failed` | `[*]` means **any element** of a list |
| `budget.mode!=normal` | `!=` as well |

Rules are repeatable and evaluated `needs_you` → `working` → `idle`, first
match wins. It is deliberately not `eval`: these come off a command line and
end up driving a light, and a rule language you cannot read at a glance is
one you will mis-write at 2 a.m.

If the output is not JSON at all — a traceback, a "command not found" —
`poll` says so and leaves the light alone rather than inventing a state.

**By regex**, for anything that prints text. `--preset sge` reads a
`qstat -u $USER` listing; `--preset slurm` reads `squeue -u $USER`:

| Queue says | Light |
|---|---|
| a job running (`r`, `t` / `R`, `CG`) | green |
| everything queued (`qw` / `PD`) | yellow |
| a job in error (`Eqw` / `F`, `TO`, `CA`, `NF`) | **red** |
| nothing listed | source clears |

Both presets match on the **state column** of a per-user listing, not on
loose words, so a job named `error-analysis` does not turn your light red.
Override with `--needs-you-re`, `--working-re`, `--idle-re`.

If the command itself fails — VPN dropped, SSH died — `poll` says so and
**leaves the light alone** by default. A flaky network is not a failed job.
`--on-error needs_you` if you would rather know.

---

## Recipes

### A. Thousand Sunny — a local agent crew

[Thousand Sunny](https://github.com/nhathout/sunny) already prints
everything the light needs: `python -m jobs.status` emits one JSON snapshot
with the queue, every crewmate's state, open briefs and blockers. So this
needs **no changes to sunny at all**:

```powershell
rookery poll --source sunny --every 60 --json `
  --command 'cd /d C:\dev\sunny && .venv\Scripts\python.exe -m jobs.status' `
  --needs-you-if 'crew[*].state==failed' `
  --needs-you-if 'last_run.failed>0' `
  --needs-you-if 'budget.cap_reached' `
  --needs-you-if 'briefs.open>0' `
  --working-if   'queue.running>0' `
  --idle-if      'crew[*].state==has_news' `
  --idle-if      'queue.queued>0' `
  --idle-if      'blockers'
```

`scripts/poll-sunny.ps1` is that command in a file, so you can just run it.

What each colour means:

| Light | Because |
|---|---|
| 🔴 **red** | a crewmate failed, the last run had failures, the budget cap is hit, or a brief is open waiting for you to run it |
| 🟢 **green** | a task is running right now |
| 🟡 **yellow** | there is something to read — a crewmate has news, work is queued, or a blocker is listed |
| clears | nothing to say; the light falls back to whatever else is going on |

Two judgement calls worth knowing about, because they are the difference
between a useful light and one you learn to ignore:

- **`blockers` is yellow, not red.** It is non-empty on a healthy system —
  `ANTHROPIC_API_KEY not set` is a deliberate choice, not a fault, and
  mapping it to red would leave the penguin permanently on.
- **`has_news` is yellow, not red.** A crewmate with an action for you is
  worth seeing, but red is for things that are broken or blocking. If red
  means "sometime this week" you will stop believing it.

A run takes about 3 seconds to answer, so a 60-second poll costs ~5% of one
core. Sunny's own UI refreshes every 20 s, so this is well inside what the
project already does to itself.

For instant response instead of up-to-60-seconds, sunny can push at run
start and finish as well — see the end of this file.

### B. A long job on this machine

```bash
rookery watch --source bench -- python -m tools.bench_tools --runs 3
```

That is the whole recipe. Anything that exits non-zero when it fails works.

### C. A queue on a machine you aren't sitting at

The reliable shape is **one SSH session, one 2FA prompt**, with the far end
reporting back through a reverse tunnel:

```bash
ssh -R 8787:localhost:8787 <host> 'while true; do
     s=clear
     q=$(qstat -u $USER)
     echo "$q" | grep -qE "^ *[0-9]+ +\S+ +\S+ +\S+ +E" && s=needs_you
     [ "$s" = clear ] && echo "$q" | grep -qE "^ *[0-9]+ +\S+ +\S+ +\S+ +[rt]\b" && s=working
     [ "$s" = clear ] && echo "$q" | grep -qE "^ *[0-9]+ +\S+ +\S+ +\S+ +\S*qw" && s=idle
     curl -s -X POST -H "Content-Type: application/json" \
       -d "{\"source\":\"cluster\",\"state\":\"$s\",\"ttl\":180}" \
       http://localhost:8787/state >/dev/null
     sleep 60
   done'
```

`-R 8787:localhost:8787` makes *your* daemon reachable as `localhost:8787`
**on the far machine**, for as long as that SSH session is open. Nothing is
exposed to the network.

If you would rather poll from this side, that needs nothing on the far end:

```bash
rookery poll --source cluster --every 60 --preset sge \
  --command 'ssh <host> "qstat -u $USER"'
```

…but give SSH a shared connection first, or you will re-authenticate every
minute. In `~/.ssh/config`:

```
Host <host>
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 8h
    ServerAliveInterval 60
```

Then connect once by hand and every poll for the next eight hours reuses it.

### D. Another machine on your LAN, pushing

The daemon binds to localhost by default and **refuses to bind anywhere else
without a token** — an open endpoint that anything on the network can drive
is not a thing to hand out by accident.

On the machine with the penguin:

```bash
rookery run --http-host 0.0.0.0 --token "$(python -c 'import secrets;print(secrets.token_urlsafe(16))')"
```

On the other machine, with rookery installed:

```bash
rookery notify working --source gpu-box \
  --http-host 192.168.1.42 --token <that-token> --detail "serving"
```

or without it:

```bash
curl -s -X POST http://192.168.1.42:8787/state \
  -H 'Authorization: Bearer <that-token>' \
  -H 'Content-Type: application/json' \
  -d '{"source":"gpu-box","state":"working","detail":"serving","ttl":120}'
```

### E. A scheduled job reporting its own start and finish

Put it in the job itself, so it reports even when you are asleep:

```bash
report() {
  curl -s --max-time 2 -X POST -H 'Content-Type: application/json' \
    -d "{\"source\":\"$1\",\"state\":\"$2\",\"detail\":\"$3\",\"ttl\":0}" \
    http://localhost:8787/state >/dev/null 2>&1 || true
}
report weekly working "started on $(hostname)"
python -m jobs.weekly_run && report weekly idle "finished" || report weekly needs_you "exit $?"
```

`"ttl":0` means never expire — right for something that reports its own end.
The `|| true` and `--max-time` matter: **the light must never be able to
fail, block, or slow the job it is reporting on.**

---

## When several things are lit

The light shows one colour, so it shows the most urgent. `rookery status`
tells you what is actually behind it:

```json
{
  "aggregate": "needs_you",
  "sessions": { "abc": { "state": "working", "cwd": "C:/dev/sunny" } },
  "sources":  { "sunny": { "state": "needs_you", "detail": "crew[*].state==failed" } }
}
```

Green with a long job running means green for as long as it runs, and a
Claude Code session going idle underneath it will not show. That is correct
— the most urgent thing is still true — but it does mean **green is
ambiguous between "an agent is thinking" and "a job is running"**. `rookery
status` is the disambiguator; there is no spare colour on a six-LED beacon.

---

## HTTP API

Everything above is a wrapper around this.

### `POST /state`

```json
{ "source": "sunny", "state": "working", "detail": "weekly_run", "ttl": 180 }
```

| Field | | |
|---|---|---|
| `source` | required | Name. Reporting again replaces the previous value. |
| `state` | required | `working`, `idle`, `needs_you`, `asleep`, or `clear`/`null` to remove |
| `detail` | optional | Free text, ≤200 chars, shown by `rookery status` |
| `ttl` | optional | Seconds until assumed dead. Default 180, `0` = never |

Replies `200` with the new aggregate, or `400` with an explanation. Unlike
`/hook` it answers properly on bad input: whatever posted here is a script
that can act on an error, and silently swallowing a typo in a state name
would be horrible to debug.

### `POST /hook`

A Claude Code hook event. Always `204`, never a decision, never blocks your
agent — including on a malformed body.

### `GET /status`, `GET /health`

JSON dump of everything tracked; `200 {"ok":true}`.

Authentication is off for localhost. With `--token`, every POST needs
`Authorization: Bearer <token>`.

One daemon per port: on Windows a second `rookery run` used to bind the same
port quietly and shadow the first, so half your reports reached a daemon
that was not driving the light. It now refuses and says so.
