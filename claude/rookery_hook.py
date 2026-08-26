#!/usr/bin/env python3
"""Command-hook fallback client for rookery.

Use this instead of the HTTP hooks if you'd rather not have Claude Code make
localhost HTTP calls, or if you want the hook to fail *completely* silently
when the daemon isn't running.

Trade-off: this spawns a Python process per hook event, so it's slower than the
HTTP path. Pair it with "async": true in your settings so it never blocks the
agent loop.

Install: copy to ~/.claude/hooks/rookery_hook.py, chmod +x, and use
claude/hooks.command.json as your settings block.
"""

import json
import sys
import urllib.error
import urllib.request

ENDPOINT = "http://127.0.0.1:8787/hook"
TIMEOUT = 2.0


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0

    if not raw.strip():
        return 0

    try:
        req = urllib.request.Request(
            ENDPOINT,
            data=raw.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=TIMEOUT).close()
    except (urllib.error.URLError, OSError, ValueError):
        # Daemon not running, light unplugged, whatever. A status light is
        # never a good reason to interrupt your work: exit 0 regardless.
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
