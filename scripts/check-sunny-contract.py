#!/usr/bin/env python3
r"""Check that a Thousand Sunny snapshot still answers every rule the light asks.

The failure this exists to catch is quiet. `rookery poll` evaluates dotted
paths against sunny's JSON, and a rule whose path has been renamed away
returns "false" -- exactly like a rule that is legitimately false. Nothing
errors, no test goes red, and the light simply stops telling the truth.

So this separates the two: for every rule the light uses, it reports whether
the *path* resolves at all, and only then what the rule currently evaluates
to. A missing path is a failure; a false rule is just Tuesday.

    python scripts/check-sunny-contract.py
    python scripts/check-sunny-contract.py --sunny-root D:\dev\sunny --probe

Exit 0 if every path resolves, 1 if any is missing or the snapshot is
unreadable -- so it can sit in a pre-commit hook or CI on either repo.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "host"))

from rookery.__main__ import _walk, check_rule  # noqa: E402

# Kept in step with scripts/poll-sunny.ps1 and docs/integrations.md recipe A.
RULES = [
    ("needs_you", "crew[*].state==failed"),
    ("needs_you", "last_run.failed>0"),
    ("needs_you", "budget.cap_reached"),
    ("needs_you", "briefs.open>0"),
    ("working", "queue.running>0"),
    ("idle", "crew[*].state==has_news"),
    ("idle", "queue.queued>0"),
    ("idle", "blockers"),
]


def rule_path(rule: str) -> str:
    """The dotted path of a rule, with any comparison stripped off."""
    for op in ("==", "!=", ">=", "<=", ">", "<"):
        if op in rule:
            return rule.split(op)[0]
    return rule


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sunny-root", default=r"C:\dev\sunny")
    ap.add_argument("--probe", action="store_true",
                    help="take the full snapshot instead of --no-probe")
    args = ap.parse_args()

    root = Path(args.sunny_root)
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.exists():                      # not Windows, or a bare checkout
        python = root / ".venv" / "bin" / "python"
    if not python.exists():
        print(f"no venv under {root}; pass --sunny-root", file=sys.stderr)
        return 1

    cmd = [str(python), "-m", "jobs.status"] + ([] if args.probe else ["--no-probe"])
    out = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)

    # stdout only, deliberately: sunny logs to stderr, and folding that in is
    # what used to make a good snapshot look unparseable.
    try:
        data = json.loads(out.stdout)
    except ValueError:
        print("snapshot did not parse as JSON. stdout must be JSON only.",
              file=sys.stderr)
        print(f"  exit {out.returncode}", file=sys.stderr)
        if out.stdout.strip():
            print(f"  stdout starts: {out.stdout[:200]!r}", file=sys.stderr)
        if out.stderr.strip():
            print(f"  stderr starts: {out.stderr[:200]!r}", file=sys.stderr)
        return 1

    print(f"schema {data.get('schema')}  probed={data.get('probed')}\n")
    print(f"{'':<4}{'STATE':<10}{'RULE':<28}{'NOW':<7}VALUE")

    missing = []
    for state, rule in RULES:
        path = rule_path(rule)
        values = list(_walk(data, path.split(".")))
        hit, _ = check_rule(data, rule)
        if values:
            mark, shown = "ok", str(values[0] if len(values) == 1 else values)[:40]
        else:
            mark, shown = "GONE", "path does not resolve"
            missing.append((rule, path))
        print(f"{mark:<4}{state:<10}{rule:<28}{str(hit):<7}{shown}")

    if missing:
        print(f"\n{len(missing)} rule(s) reference fields the snapshot no longer has:")
        for rule, path in missing:
            print(f"  {rule}   (missing: {path})")
        print("\nThe light would read these as 'false' and never fire. Either the")
        print("field moved -- update scripts/poll-sunny.ps1 and docs/integrations.md")
        print("-- or it was dropped, and sunny's docs/status-light.md needs to say so.")
        return 1

    print(f"\nall {len(RULES)} rules resolve against the snapshot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
