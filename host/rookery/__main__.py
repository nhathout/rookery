"""rookery command line interface."""

from __future__ import annotations

import argparse
import json
import logging
import sys
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
    daemon = Daemon(
        port=args.port,
        baud=args.baud,
        http_host=args.http_host,
        http_port=args.http_port,
        brightness=args.brightness,
        simulate=args.simulate,
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

    def add_serial(sp):
        sp.add_argument("--port", help="serial device (default: autodetect)")
        sp.add_argument("--baud", type=int, default=115200)

    def add_http(sp):
        sp.add_argument("--http-host", default="127.0.0.1")
        sp.add_argument("--http-port", type=int, default=8787)

    sp = sub.add_parser("run", help="run the daemon")
    add_serial(sp)
    add_http(sp)
    sp.add_argument("--brightness", type=int, help="0-255 master brightness")
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
    add_serial(sp)
    sp.add_argument("--dwell", type=float, default=2.5)
    sp.add_argument("--brightness", type=int)
    sp.set_defaults(func=cmd_test)

    sp = sub.add_parser("set", help="force one state (daemon must be stopped)")
    add_serial(sp)
    sp.add_argument("state", choices=[WORKING, IDLE, NEEDS_YOU, ASLEEP])
    sp.set_defaults(func=cmd_set)

    sp = sub.add_parser("status", help="show tracked sessions")
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
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
