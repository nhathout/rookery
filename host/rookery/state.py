"""Session registry and state aggregation.

Two kinds of thing drive the light:

  * SESSIONS  -- Claude Code sessions, fed by hook events. One per terminal.
  * SOURCES   -- anything else that wants a say: a training job, a policy
                 server, a poller watching a cluster queue. Named, and fed by
                 POST /state or the `rookery notify` / `watch` / `poll` verbs.

Both land in the same registry and the beacon shows the most urgent state
across all of them: needs_you beats working beats idle.

Sources carry a TTL, which sessions do not. A hook always sends SessionEnd,
but a reporter on another machine can lose its network, get killed, or have
its laptop shut. Without an expiry the light would sit green forever on the
strength of a job that died an hour ago, which is worse than showing nothing.
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


# A source that stops reporting is assumed dead after this long, unless it
# asked for something different.
DEFAULT_TTL = 180.0


@dataclass
class Session:
    state: str
    updated: float = field(default_factory=time.time)
    cwd: str = ""


@dataclass
class Source:
    """Something other than a Claude Code session driving the light."""

    state: str
    detail: str = ""
    ttl: float = DEFAULT_TTL
    updated: float = field(default_factory=time.time)

    def expired(self, now: float) -> bool:
        return self.ttl > 0 and (now - self.updated) > self.ttl


class Registry:
    """Thread-safe map of session_id -> Session."""

    def __init__(self, stale_after: float = 8 * 3600):
        self._sessions: dict[str, Session] = {}
        self._sources: dict[str, Source] = {}
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

    def set_source(self, name: str, state: str | None,
                   detail: str = "", ttl: float = DEFAULT_TTL) -> str | None:
        """Point a named source at a state. `state=None` removes it.

        Anything can be a source: a wrapper around a training run, a poller
        asking a cluster what is queued, a policy server reporting that it
        came up. They are equals with Claude Code sessions -- most urgent
        wins -- so a failed job still beats a session that is merely busy.
        """
        if not name:
            return None
        with self._lock:
            if state is None or state == ASLEEP:
                self._sources.pop(name, None)
                return None
            if state not in PRIORITY:
                return None
            self._sources[name] = Source(state=state, detail=detail,
                                         ttl=max(0.0, ttl))
            return state

    def forget(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
            self._sources.clear()

    # -- readout -----------------------------------------------------------

    def sweep(self) -> None:
        """Drop sessions we haven't heard from in a long time. SessionEnd is
        usually delivered, but a hard kill -9 on a terminal will skip it."""
        now = time.time()
        cutoff = now - self._stale_after
        with self._lock:
            for k in [k for k, v in self._sessions.items() if v.updated < cutoff]:
                del self._sessions[k]
            for k in [k for k, v in self._sources.items() if v.expired(now)]:
                del self._sources[k]

    def aggregate(self) -> str:
        now = time.time()
        with self._lock:
            states = [s.state for s in self._sessions.values()]
            states += [s.state for s in self._sources.values()
                       if not s.expired(now)]
            if not states:
                return ASLEEP
            return max(states, key=lambda s: PRIORITY.get(s, 0))

    def snapshot(self) -> dict:
        now = time.time()
        with self._lock:
            live = {n: s for n, s in self._sources.items() if not s.expired(now)}
            return {
                "aggregate": self.aggregate(),
                "count": len(self._sessions) + len(live),
                "sessions": {
                    sid: {
                        "state": s.state,
                        "age": round(now - s.updated, 1),
                        "cwd": s.cwd,
                    }
                    for sid, s in self._sessions.items()
                },
                "sources": {
                    name: {
                        "state": s.state,
                        "age": round(now - s.updated, 1),
                        "ttl": s.ttl,
                        "detail": s.detail,
                    }
                    for name, s in live.items()
                },
            }
