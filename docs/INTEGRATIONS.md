# Driving the light from something other than Claude Code

The beacon started out showing Claude Code sessions. It now shows anything
you point at it — a training run, a policy server, a queue on a cluster you
are not sitting at.

Two kinds of thing drive it:

| | What it is | Fed by |
|---|---|---|
| **session** | One Claude Code session, one per terminal | hooks → `POST /hook` |
| **source** | Anything else, named by you | `POST /state`, or the verbs below |

They are equals. The light shows the **most urgent state across all of
them** — `needs_you` beats `working` beats `idle` — so a training job that
died still turns the penguin red while an agent is busy elsewhere.

Sources carry a **TTL** that sessions do not. Claude Code always sends
`SessionEnd`; a reporter on another machine can lose its network, get
killed, or have its laptop shut. Without an expiry the light would sit green
forever on the strength of a job that died an hour ago, which is worse than
showing nothing at all.

---

## The three verbs

### `rookery notify` — one-shot

```bash
rookery notify working   --source scc --detail "train_baseline 30k" --ttl 300
rookery notify needs_you --source scc --detail "exit 1 at step 12000"
rookery notify clear     --source scc
```

The whole API from a shell script. `clear` removes the source entirely.

### `rookery watch` — wrap a long job

```bash
rookery watch --source train -- python scripts/train.py --steps 30000
```

- **green** while it runs, re-reporting every 30 s so the TTL never lapses
- **red, and it stays red** if it exits non-zero — a run that died at 03:00
  is exactly the thing you want to walk in and see
- **yellow for five minutes** if it succeeds, then the source clears itself
- the command's output, and its exit code, pass straight through

Tune with `--hold-ok`, `--hold-fail`, `--heartbeat`.

### `rookery poll` — ask a machine you aren't sitting at

```bash
rookery poll --source scc --every 60 --preset sge \
  --command 'ssh scc "qstat -u nhathout"'
```

A login node behind a university firewall cannot open a connection to your
desk. It can always answer a question, so the daemon asks.

`--preset sge` reads a `qstat -u $USER` listing; `--preset slurm` reads
`squeue -u $USER`. Both match on the **state column** of a per-user listing,
not on loose words, so a job named `error-analysis` does not turn your light
red. Override any of them with `--needs-you-re`, `--working-re`, `--idle-re`,
or write your own from scratch.

| Queue says | Light |
|---|---|
| a job running (`r`, `t` / `R`, `CG`) | green |
| everything queued (`qw` / `PD`) | yellow |
| a job in error (`Eqw` / `F`, `TO`, `CA`, `NF`) | **red** |
| nothing listed | source clears |

If the command itself fails — VPN dropped, SSH died — `poll` says so and
**leaves the light alone** by default. A flaky network is not a failed job.
`--on-error needs_you` if you would rather know.

---

## Recipes

### A. A long job on this machine

```bash
rookery watch --source train -- python train.py
```

That is the whole recipe. Anything that exits non-zero when it fails works.

### B. A cluster queue, from your desk

The reliable shape is **one SSH session, one 2FA prompt**, with the far end
reporting back through a reverse tunnel:

```bash
ssh -R 8787:localhost:8787 scc \
  'while true; do
     s=clear
     q=$(qstat -u $USER)
     echo "$q" | grep -qE "^ *[0-9]+ +\S+ +\S+ +\S+ +E"      && s=needs_you
     [ "$s" = clear ] && echo "$q" | grep -qE "^ *[0-9]+ +\S+ +\S+ +\S+ +[rt]\b" && s=working
     [ "$s" = clear ] && echo "$q" | grep -qE "^ *[0-9]+ +\S+ +\S+ +\S+ +\S*qw"  && s=idle
     curl -s -X POST -H "Content-Type: application/json" \
       -d "{\"source\":\"scc\",\"state\":\"$s\",\"ttl\":180}" \
       http://localhost:8787/state >/dev/null
     sleep 60
   done'
```

`-R 8787:localhost:8787` makes *your* daemon reachable as `localhost:8787`
**on the cluster**, for as long as that SSH session is open. Nothing is
exposed to the network.

If you would rather poll from this side, that works too and needs nothing on
the far end:

```bash
rookery poll --source scc --every 60 --preset sge \
  --command 'ssh scc "qstat -u $USER"'
```

…but give SSH a shared connection first, or you will hit 2FA every minute.
In `~/.ssh/config`:

```
Host scc
    HostName scc1.bu.edu
    User <your-username>
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 8h
    ServerAliveInterval 60
```

Then `ssh scc` once by hand, authenticate, and every poll for the next eight
hours reuses that connection.

### C. Another machine on your LAN, pushing

The daemon binds to localhost by default and **refuses to bind anywhere else
without a token** — an open endpoint that anything on the network can drive
is not a thing to hand out by accident.

On the machine with the penguin:

```bash
rookery run --http-host 0.0.0.0 --token "$(python -c 'import secrets;print(secrets.token_urlsafe(16))')"
```

On the other machine:

```bash
rookery notify working --source gpu-box \
  --http-host 192.168.1.42 --token <that-token> --detail "serving policy"
```

or without rookery installed there at all:

```bash
curl -s -X POST http://192.168.1.42:8787/state \
  -H 'Authorization: Bearer <that-token>' \
  -H 'Content-Type: application/json' \
  -d '{"source":"gpu-box","state":"working","detail":"serving policy","ttl":120}'
```

### D. A batch job reporting its own start and finish

Put it in the job script, so it reports even when you are asleep. With the
reverse tunnel from recipe B open:

```bash
report() {
  curl -s -X POST -H 'Content-Type: application/json' \
    -d "{\"source\":\"$JOB_NAME\",\"state\":\"$1\",\"detail\":\"$2\",\"ttl\":0}" \
    http://localhost:8787/state >/dev/null || true
}
report working "started on $(hostname)"
trap 'report needs_you "killed or crashed"' ERR
python train.py "$@" && report idle "finished" || report needs_you "exit $?"
```

`"ttl":0` means never expire — right for something that reports its own end.
The `|| true` matters: **the light must never be able to fail your job.**

---

## When several things are lit

The light shows one colour, so it shows the most urgent. `rookery status`
tells you what is actually behind it:

```json
{
  "aggregate": "needs_you",
  "sessions": { "abc": { "state": "working", "cwd": "D:/dev/rookery" } },
  "sources":  { "scc": { "state": "needs_you", "detail": "job 123458 Eqw" } }
}
```

Green with a six-hour training job running means green for six hours, and a
Claude Code session going idle underneath it will not show. That is correct
— the most urgent thing is still true — but it does mean **green is
ambiguous between "an agent is thinking" and "a job is running"**. `rookery
status` is the disambiguator; there is no spare colour on a six-LED beacon.

---

## HTTP API

Everything above is a wrapper around this.

### `POST /state`

```json
{ "source": "scc", "state": "working", "detail": "train_baseline", "ttl": 180 }
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
