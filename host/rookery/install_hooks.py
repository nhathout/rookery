"""Install / remove the beacon's hooks in a Claude Code settings file.

Every entry we add is tagged with a `statusMessage` of ROOKERY_TAG so we
can find and remove exactly our own entries later without disturbing yours.

Reference: https://code.claude.com/docs/en/hooks
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

ROOKERY_TAG = "rookery"

DEFAULT_SETTINGS = Path.home() / ".claude" / "settings.json"


def build_hooks(url: str) -> dict:
    """The hook block we inject.

    Event choices, and why:
      SessionStart        a session exists now -> idle
      UserPromptSubmit    you asked for something -> working
      PreToolUse          tool activity -> working (also recovers from
                          needs_you once you answer a permission prompt)
      PostToolUse         tool finished -> still working
      Notification        permission prompt / idle nudge -> needs you
      Stop                turn finished -> idle
      StopFailure         turn died on an API error -> needs you
      SessionEnd          forget this session
    """

    def http(timeout: int = 5) -> dict:
        return {
            "type": "http",
            "url": url,
            "timeout": timeout,
            "statusMessage": ROOKERY_TAG,
        }

    return {
        "SessionStart": [
            {"matcher": "startup|resume|clear|fork", "hooks": [http()]}
        ],
        "UserPromptSubmit": [{"hooks": [http()]}],
        "PreToolUse": [{"matcher": "*", "hooks": [http()]}],
        "PostToolUse": [{"matcher": "*", "hooks": [http()]}],
        "Notification": [
            {
                "matcher": "permission_prompt|idle_prompt|agent_needs_input",
                "hooks": [http()],
            }
        ],
        "Stop": [{"hooks": [http()]}],
        "StopFailure": [
            {
                "matcher": "rate_limit|overloaded|authentication_failed"
                "|billing_error|invalid_request|server_error|unknown",
                "hooks": [http()],
            }
        ],
        # SessionEnd hooks share a 1.5 s budget across all of them -- keep the
        # timeout small so we never hold up a quit.
        "SessionEnd": [
            {
                "matcher": "clear|resume|logout|prompt_input_exit|other",
                "hooks": [http(timeout=1)],
            }
        ],
    }


def _is_ours(group: dict) -> bool:
    hooks = group.get("hooks") or []
    return bool(hooks) and all(
        h.get("statusMessage") == ROOKERY_TAG for h in hooks
    )


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return json.loads(text)


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def install(path: Path, url: str) -> str:
    settings = _load(path)

    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)

    hooks = settings.setdefault("hooks", {})
    added = 0
    for event, groups in build_hooks(url).items():
        existing = hooks.setdefault(event, [])
        # Drop any previous rookery groups so re-running is idempotent.
        existing[:] = [g for g in existing if not _is_ours(g)]
        existing.extend(groups)
        added += len(groups)

    _save(path, settings)
    return f"installed {added} hook groups into {path}"


def uninstall(path: Path) -> str:
    if not path.exists():
        return f"{path} does not exist; nothing to do"

    settings = _load(path)
    hooks = settings.get("hooks") or {}
    removed = 0
    for event in list(hooks.keys()):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        before = len(groups)
        groups[:] = [g for g in groups if not _is_ours(g)]
        removed += before - len(groups)
        if not groups:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)

    _save(path, settings)
    return f"removed {removed} hook groups from {path}"
