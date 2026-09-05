"""rookery command line interface."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

from . import install_hooks as hooks_mod
from .daemon import Daemon
from .serial_link import SerialLink, describe_ports, probe
from .state import ASLEEP, IDLE, NEEDS_YOU, WORKING


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_ports(args) -> int:
    print("Serial ports (* = likely an ESP32):")
    print(describe_ports())
    return 0


def cmd_probe(args) -> int:
    if args.port:
        ok = probe(args.port, args.baud)
        print(f"{args.port}: {'beacon found' if ok else 'no response'}")
        return 0 if ok else 1
    from .serial_link import autodetect

    found = autodetect(args.baud)
    if found:
        print(f"beacon found on {found}")
        return 0
    print("no beacon found; is it plugged in and flashed?")
    return 1


def cmd_run(args) -> int:
    _setup_logging(args.verbose)
    local = args.http_host in ("127.0.0.1", "localhost", "::1")
    if not local and not args.token and not args.insecure:
        print(
            f"rookery: refusing to listen on {args.http_host} without a token.\n"
            "  Anything on the network could drive your light. Either pass\n"
            "  --token <secret> (and give it to whatever reports in), or\n"
            "  --insecure if you really mean it.",
            file=sys.stderr,
        )
        return 2
    daemon = Daemon(
        port=args.port,
        baud=args.baud,
        http_host=args.http_host,
        http_port=args.http_port,
        brightness=args.brightness,
        simulate=args.simulate,
        token=args.token,
    )
    return daemon.run()


def cmd_test(args) -> int:
    """Cycle the light through every state so you can check the wiring."""
    _setup_logging(args.verbose)
    link = SerialLink(args.port, args.baud)
    link.start()
    if args.brightness is not None:
        link.send(f"BRIGHT {args.brightness}")
    try:
        for state in (WORKING, IDLE, NEEDS_YOU, ASLEEP):
            print(f"  -> {state}")
            if not link.send(f"STATE {state}"):
                print("  !! write failed -- check the port")
                return 1
            time.sleep(args.dwell)
    finally:
        link.stop()
    return 0


def cmd_set(args) -> int:
    link = SerialLink(args.port, args.baud)
    link.start()
    try:
        ok = link.send(f"STATE {args.state}")
        return 0 if ok else 1
    finally:
        link.stop()


# ---------------------------------------------------------------------------
# Sources: anything that is not a Claude Code session driving the light.
# ---------------------------------------------------------------------------

# Queue listings are the common case for "a machine I am not sitting at", and
# the regexes to read one are fiddly enough to get wrong silently. Both of
# these match on the STATE COLUMN of a per-user listing, not on loose words,
# so a job named "error-analysis" does not turn your light red.
PRESETS = {
    # Grid Engine / SGE: `qstat -u $USER`. States r, t, qw, hqw, Eqw, dr...
    "sge": {
        "needs_you": r"(?m)^\s*\d+\s+\S+\s+\S+\s+\S+\s+E",
        "working": r"(?m)^\s*\d+\s+\S+\s+\S+\s+\S+\s+[rt]\b",
        "idle": r"(?m)^\s*\d+\s+\S+\s+\S+\s+\S+\s+\S*qw",
    },
    # Slurm: `squeue -u $USER`. States R, PD, CG, F, TO, CA, NF.
    "slurm": {
        "needs_you": r"(?m)^\s*\d+\s+\S+\s+\S+\s+\S+\s+(F|NF|TO|CA)\b",
        "working": r"(?m)^\s*\d+\s+\S+\s+\S+\s+\S+\s+(R|CG)\b",
        "idle": r"(?m)^\s*\d+\s+\S+\s+\S+\s+\S+\s+PD\b",
    },
}

def _post_state(args, state, detail="", ttl=None) -> dict | None:
    """Report a named source. Returns the daemon's reply, or None if it could
    not be reached -- callers decide whether that is fatal."""
    url = f"http://{args.http_host}:{args.http_port}/state"
    body = json.dumps({
        "source": args.source,
        "state": state,
        "detail": detail,
        "ttl": args.ttl if ttl is None else ttl,
    }).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    if getattr(args, "token", None):
        req.add_header("Authorization", f"Bearer {args.token}")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())
    except Exception as exc:
        print(f"rookery: could not reach the daemon: {exc}", file=sys.stderr)
        return None


def cmd_notify(args) -> int:
    state = None if args.state == "clear" else args.state
    reply = _post_state(args, state, args.detail)
    if reply is None:
        return 1
    if not args.quiet:
        print(f"{args.source}: {reply['state']} -> light is {reply['aggregate']}")
    return 0


def cmd_watch(args) -> int:
    """Run a command with the light following it.

    Green while it runs. Red and STAYS red if it fails, because a training run
    that died at 03:00 is exactly the thing you want to walk in and see.
    Yellow for a while if it succeeds, then the source clears itself.
    """
    import subprocess

    # argparse.REMAINDER hands us the "--" separator as well; it is a
    # separator, not a program.
    argv = list(args.argv)
    while argv and argv[0] == "--":
        argv.pop(0)
    if not argv:
        print("rookery watch: give me a command after --", file=sys.stderr)
        return 2
    args.argv = argv

    started = time.time()
    label = " ".join(args.argv)[:120]
    _post_state(args, WORKING, f"running: {label}", ttl=args.heartbeat * 3)

    stop = threading.Event()

    def beat():
        # Re-report on a timer so the source's TTL never lapses mid-run, and
        # so a daemon restart picks the job back up instead of losing it.
        while not stop.wait(args.heartbeat):
            mins = (time.time() - started) / 60
            _post_state(args, WORKING, f"running {mins:.0f}m: {label}",
                        ttl=args.heartbeat * 3)

    beater = threading.Thread(target=beat, daemon=True)
    beater.start()

    code = 1
    try:
        code = subprocess.call(args.argv)
    except KeyboardInterrupt:
        code = 130
    except OSError as exc:
        print(f"rookery watch: {exc}", file=sys.stderr)
        code = 127
    finally:
        stop.set()

    mins = (time.time() - started) / 60
    if code == 0:
        _post_state(args, IDLE, f"finished in {mins:.0f}m: {label}",
                    ttl=args.hold_ok)
    elif code == 130:
        _post_state(args, None)
    else:
        _post_state(args, NEEDS_YOU, f"exit {code} after {mins:.0f}m: {label}",
                    ttl=args.hold_fail)
    return code


_RULE = re.compile(r"^\s*([A-Za-z_][\w.\[\]*]*)\s*(==|!=|>=|<=|>|<)?\s*(.*?)\s*$")


def _walk(node, parts):
    """Yield every value at a dotted path. `[*]` means 'any element'."""
    if not parts:
        yield node
        return
    head, rest = parts[0], parts[1:]
    if head.endswith("[*]"):
        node = node.get(head[:-3]) if isinstance(node, dict) else None
        for item in node or ():
            yield from _walk(item, rest)
    elif isinstance(node, dict) and head in node:
        yield from _walk(node[head], rest)


def _truthy(value) -> bool:
    # An empty list is the interesting case: `blockers` with nothing in it
    # should read as false, not as "a list exists".
    return bool(value)


def check_rule(data, rule: str) -> tuple[bool, str]:
    """Evaluate one `path`, `path==value` or `path>number` rule against JSON.

    Deliberately not eval(): these come off a command line and end up driving
    a light, and a rule language you cannot read at a glance is one you will
    mis-write at 2am. Paths, one comparison, no expressions.
    """
    m = _RULE.match(rule)
    if not m:
        return False, ""
    path, op, wanted = m.group(1), m.group(2), m.group(3)
    values = list(_walk(data, path.split(".")))
    if not values:
        return False, ""

    for value in values:
        if op is None:
            if _truthy(value):
                got = value[0] if isinstance(value, list) and value else value
                return True, f"{path}={str(got)[:60]}"
            continue
        try:
            if op in (">", "<", ">=", "<="):
                a, b = float(value), float(wanted)
                hit = (a > b if op == ">" else a < b if op == "<"
                       else a >= b if op == ">=" else a <= b)
            else:
                hit = (str(value) == wanted) if op == "==" else (str(value) != wanted)
        except (TypeError, ValueError):
            continue
        if hit:
            return True, f"{path}{op}{wanted}"
    return False, ""


def cmd_poll(args) -> int:
    """Run a shell command on a timer and map its output onto a state.

    This is how a machine you are NOT sitting at gets onto the light: the
    daemon asks, rather than the far end pushing. A cluster behind a login
    node cannot open a connection to your desk, but you can always ask it
    what is queued.
    """
    import subprocess

    preset = PRESETS.get(args.preset or "", {})
    fallback = None if args.otherwise == "clear" else args.otherwise

    if args.json:
        json_rules = [(NEEDS_YOU, args.needs_you_if), (WORKING, args.working_if),
                      (IDLE, args.idle_if)]

        def classify(text):
            try:
                data = json.loads(text)
            except ValueError:
                # The command printed something that is not JSON -- a traceback,
                # a "not found". That is a broken reporter, not a state.
                return "__unparseable__", ""
            for state, rules in json_rules:
                for rule in rules or ():
                    hit, why = check_rule(data, rule)
                    if hit:
                        return state, why
            return fallback, ""
    else:
        rules = [
            (NEEDS_YOU, args.needs_you_re or preset.get("needs_you")),
            (WORKING, args.working_re or preset.get("working")),
            (IDLE, args.idle_re or preset.get("idle")),
        ]
        rules = [(s, re.compile(p, re.M)) for s, p in rules if p]

        def classify(text):
            for state, pattern in rules:
                m = pattern.search(text)
                if m:
                    return state, m.group(0).strip()[:80]
            return fallback, ""

    print(f"polling every {args.every}s: {args.command}")
    last = object()
    try:
        while True:
            try:
                out = subprocess.run(args.command, shell=True, timeout=args.timeout,
                                     capture_output=True, text=True)
                # In --json mode the snapshot is stdout and stderr is noise. One
                # deprecation warning concatenated onto a perfectly good snapshot
                # makes it unparseable, and the light goes quiet for a reason you
                # cannot see from looking at it. Fall back to the combined output
                # only when stdout is empty, so a command that merely failed still
                # gets reported rather than silently classified as nothing.
                text = (out.stdout if args.json and out.stdout.strip()
                        else out.stdout + out.stderr)
                code = out.returncode
            except subprocess.TimeoutExpired:
                text, code = "", -1

            if code != 0 and args.on_error == "skip":
                # A dropped VPN should not turn the light red. Say nothing and
                # let the source's TTL decide if we have been quiet too long.
                print(f"  (command failed, exit {code}; leaving the light alone)")
            else:
                state, detail = classify(text)
                if state == "__unparseable__":
                    print("  (output was not JSON; leaving the light alone)")
                    time.sleep(args.every)
                    continue
                if code != 0 and args.on_error != "skip":
                    state, detail = args.on_error, f"command exit {code}"
                if state != last:
                    print(f"  -> {state or 'clear'} {detail}")
                    last = state
                _post_state(args, state, detail, ttl=args.every * 3 + 30)

            time.sleep(args.every)
    except KeyboardInterrupt:
        _post_state(args, None)
        print("\nstopped; source cleared")
    return 0


def cmd_status(args) -> int:
    url = f"http://{args.http_host}:{args.http_port}/status"
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            print(json.dumps(json.loads(r.read()), indent=2))
        return 0
    except Exception as exc:
        print(f"could not reach the daemon at {url}: {exc}", file=sys.stderr)
        return 1


def cmd_install_hooks(args) -> int:
    path = Path(args.settings).expanduser()
    url = f"http://{args.http_host}:{args.http_port}/hook"
    print(hooks_mod.install(path, url))
    print("Restart any running Claude Code sessions to pick up the change.")
    return 0


def cmd_uninstall_hooks(args) -> int:
    path = Path(args.settings).expanduser()
    print(hooks_mod.uninstall(path))
    return 0


def cmd_print_hooks(args) -> int:
    url = f"http://{args.http_host}:{args.http_port}/hook"
    print(json.dumps({"hooks": hooks_mod.build_hooks(url)}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rookery",
        description="Drive a USB status light from your coding-agent sessions.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    def add_verbose(sp):
        # Also accept -v AFTER the subcommand, which is what everyone types.
        # SUPPRESS keeps it from clobbering a top-level -v with its default.
        sp.add_argument("-v", "--verbose", action="store_true",
                        default=argparse.SUPPRESS)

    def add_serial(sp):
        sp.add_argument("--port", help="serial device (default: autodetect)")
        sp.add_argument("--baud", type=int, default=115200)

    def add_http(sp):
        sp.add_argument("--http-host", default="127.0.0.1")
        sp.add_argument("--http-port", type=int, default=8787)

    def add_source(sp, default_ttl=180.0):
        sp.add_argument("--source", required=True,
                        help="name for this reporter, e.g. scc or policy-server")
        sp.add_argument("--ttl", type=float, default=default_ttl,
                        help="seconds before the daemon assumes this reporter "
                             "died and stops listening to it (0 = never)")
        sp.add_argument("--token", help="shared token, if the daemon needs one")

    sp = sub.add_parser("run", help="run the daemon")
    add_verbose(sp)
    add_serial(sp)
    add_http(sp)
    sp.add_argument("--brightness", type=int, help="0-255 master brightness")
    sp.add_argument("--token",
                    help="require this bearer token on POSTs; needed if you "
                         "bind anywhere but localhost")
    sp.add_argument("--insecure", action="store_true",
                    help="allow binding off-localhost without a token")
    sp.add_argument(
        "--simulate",
        action="store_true",
        help="log state changes instead of driving hardware",
    )
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("ports", help="list serial ports")
    sp.set_defaults(func=cmd_ports)

    sp = sub.add_parser("probe", help="find a beacon on the bus")
    add_serial(sp)
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("test", help="cycle through every state")
    add_verbose(sp)
    add_serial(sp)
    sp.add_argument("--dwell", type=float, default=2.5)
    sp.add_argument("--brightness", type=int)
    sp.set_defaults(func=cmd_test)

    sp = sub.add_parser("set", help="force one state (daemon must be stopped)")
    add_serial(sp)
    sp.add_argument("state", choices=[WORKING, IDLE, NEEDS_YOU, ASLEEP])
    sp.set_defaults(func=cmd_set)

    sp = sub.add_parser(
        "notify", help="report a state from anything that is not Claude Code")
    add_http(sp)
    add_source(sp)
    sp.add_argument("state",
                    choices=[WORKING, IDLE, NEEDS_YOU, ASLEEP, "clear"])
    sp.add_argument("--detail", default="", help="shown by `rookery status`")
    sp.add_argument("--quiet", action="store_true")
    sp.set_defaults(func=cmd_notify)

    sp = sub.add_parser(
        "watch",
        help="run a command with the light following it: green while it runs, "
             "red if it fails")
    add_http(sp)
    add_source(sp)
    sp.add_argument("--heartbeat", type=float, default=30.0,
                    help="re-report this often so the TTL never lapses mid-run")
    sp.add_argument("--hold-ok", type=float, default=300.0,
                    help="seconds to stay yellow after it succeeds")
    sp.add_argument("--hold-fail", type=float, default=3600.0,
                    help="seconds to stay red after it fails")
    sp.add_argument("argv", nargs=argparse.REMAINDER,
                    help="-- then the command to run")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser(
        "poll",
        help="ask a machine what it is doing on a timer, and light accordingly")
    add_http(sp)
    add_source(sp)
    sp.add_argument("--command", required=True,
                    help="shell command to run, e.g. 'ssh scc qstat -u me'")
    sp.add_argument("--every", type=float, default=60.0, help="seconds")
    sp.add_argument("--timeout", type=float, default=30.0,
                    help="give up on the command after this long")
    sp.add_argument("--json", action="store_true",
                    help="the command prints JSON; select on fields with the "
                         "--*-if rules below instead of regexes")
    sp.add_argument("--needs-you-if", action="append", metavar="RULE",
                    help="JSON rule, repeatable: a dotted path (true when "
                         "non-empty), or path==value / path>number. "
                         "[*] means any element, e.g. crew[*].state==failed")
    sp.add_argument("--working-if", action="append", metavar="RULE")
    sp.add_argument("--idle-if", action="append", metavar="RULE")
    sp.add_argument("--preset", choices=sorted(PRESETS),
                    help="ready-made regexes for a queue listing: sge reads "
                         "`qstat -u $USER`, slurm reads `squeue -u $USER`")
    sp.add_argument("--needs-you-re", help="regex; overrides the preset")
    sp.add_argument("--working-re", help="regex")
    sp.add_argument("--idle-re", help="regex")
    sp.add_argument("--otherwise", default="clear",
                    choices=[WORKING, IDLE, NEEDS_YOU, "clear"],
                    help="state when nothing matched (default: clear)")
    sp.add_argument("--on-error", default="skip",
                    choices=["skip", IDLE, NEEDS_YOU],
                    help="what to do when the command itself fails; skip means "
                         "leave the light alone, which is usually right for a "
                         "flaky network")
    sp.set_defaults(func=cmd_poll)

    sp = sub.add_parser("status", help="show what is driving the light")
    add_http(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("install-hooks", help="add hooks to Claude Code")
    add_http(sp)
    sp.add_argument("--settings", default=str(hooks_mod.DEFAULT_SETTINGS))
    sp.set_defaults(func=cmd_install_hooks)

    sp = sub.add_parser("uninstall-hooks", help="remove our hooks again")
    sp.add_argument("--settings", default=str(hooks_mod.DEFAULT_SETTINGS))
    sp.set_defaults(func=cmd_uninstall_hooks)

    sp = sub.add_parser("print-hooks", help="dump the hook JSON to stdout")
    add_http(sp)
    sp.set_defaults(func=cmd_print_hooks)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not hasattr(args, "verbose"):
        args.verbose = False
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
