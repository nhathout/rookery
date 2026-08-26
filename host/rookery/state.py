"""Session registry and state aggregation.

Every Claude Code session is tracked independently. The beacon shows the most
urgent state across all of them: needs_you beats working beats idle.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

# Logical states, in ascending order of urgency.
ASLEEP = "asleep"
IDLE = "idle"
WORKING = "working"
NEEDS_YOU = "needs_you"

PRIORITY = {IDLE: 1, WORKING: 2, NEEDS_YOU: 3}

# Which Claude Code hook event maps to which session state.
# None means "forget this session entirely".
EVENT_STATE = {
    "SessionStart": IDLE,
    "UserPromptSubmit": WORKING,
    "PreToolUse": WORKING,
    "PostToolUse": WORKING,
    "PostToolUseFailure": WORKING,
    "PostToolBatch": WORKING,
    "Notification": NEEDS_YOU,
    "StopFailure": NEEDS_YOU,
    "Stop": IDLE,
    "SessionEnd": None,
}

# Notification is a broad event. Only these subtypes actually mean
# "a human needs to look at this"; anything else is treated as working.
ATTENTION_NOTIFICATIONS = {
    "permission_prompt",
    "idle_prompt",
    "agent_needs_input",
    "elicitation_dialog",
    "elicitation_url_dialog",
}


@dataclass
class Session:
    state: str
    updated: float = field(default_factory=time.time)
    cwd: str = ""


class Registry:
    """Thread-safe map of session_id -> Session."""

    def __init__(self, stale_after: float = 8 * 3600):
        self._sessions: dict[str, Session] = {}
        # Reentrant: snapshot() calls aggregate() while already holding it.
        self._lock = threading.RLock()
        self._stale_after = stale_after

    # -- ingestion ---------------------------------------------------------

    def apply_event(self, payload: dict) -> str | None:
        """Feed one hook payload in. Returns the new session state, or None
        if the event was ignored or ended the session."""
        event = payload.get("hook_event_name")
        session_id = payload.get("session_id")
        if not event or not session_id:
            return None

        if event not in EVENT_STATE:
            return None

        new_state = EVENT_STATE[event]

        if event == "Notification":
            # Claude Code puts the subtype in different places depending on
            # version; check the obvious ones and fall back to "attention".
            subtype = (
                payload.get("notification_type")
                or payload.get("type")
                or ""
            )
            if subtype and subtype not in ATTENTION_NOTIFICATIONS:
                return None

        with self._lock:
            if new_state is None:
                self._sessions.pop(session_id, None)
                return None

            existing = self._sessions.get(session_id)
            if existing is None:
                self._sessions[session_id] = Session(
                    state=new_state, cwd=payload.get("cwd", "")
                )
            else:
                existing.state = new_state
                existing.updated = time.time()
                if payload.get("cwd"):
                    existing.cwd = payload["cwd"]
            return new_state

    def forget(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    # -- readout -----------------------------------------------------------

    def sweep(self) -> None:
        """Drop sessions we haven't heard from in a long time. SessionEnd is
        usually delivered, but a hard kill -9 on a terminal will skip it."""
        cutoff = time.time() - self._stale_after
        with self._lock:
            dead = [k for k, v in self._sessions.items() if v.updated < cutoff]
            for k in dead:
                del self._sessions[k]

    def aggregate(self) -> str:
        with self._lock:
            if not self._sessions:
                return ASLEEP
            return max(
                (s.state for s in self._sessions.values()),
                key=lambda s: PRIORITY.get(s, 0),
            )

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "aggregate": self.aggregate() if self._sessions else ASLEEP,
                "count": len(self._sessions),
                "sessions": {
                    sid: {
                        "state": s.state,
                        "age": round(time.time() - s.updated, 1),
                        "cwd": s.cwd,
                    }
                    for sid, s in self._sessions.items()
                },
            }
