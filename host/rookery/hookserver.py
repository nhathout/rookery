"""The HTTP endpoint everything talks to.

Claude Code supports `"type": "http"` hooks, which means we get the full event
JSON with zero process spawns per hook. That keeps the beacon from adding any
noticeable latency to your agent loop.

Anything else that wants a say drives a named SOURCE instead -- a training
run, a policy server, a poller watching a cluster queue. Same registry, same
priority: most urgent wins.

Endpoints:
    POST /hook     -- a Claude Code hook event (returns 204, no decision)
    POST /state    -- a named source reports in (returns the new aggregate)
    GET  /status   -- JSON dump of everything tracked, for debugging
    GET  /health   -- 200 if the daemon is alive
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .state import ASLEEP, DEFAULT_TTL, IDLE, NEEDS_YOU, WORKING

VALID_STATES = {WORKING, IDLE, NEEDS_YOU, ASLEEP}

log = logging.getLogger("rookery.http")

MAX_BODY = 1 << 20  # 1 MiB; hook payloads are tiny, this is just a guard


def make_server(host: str, port: int, registry, on_event=None, token=None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _authorised(self) -> bool:
            if not token:
                return True
            got = self.headers.get("Authorization", "")
            if got.startswith("Bearer "):
                got = got[7:]
            return hmac.compare_digest(got, token)

        # Silence the default one-line-per-request stderr logging.
        def log_message(self, fmt, *args):
            log.debug("%s - %s", self.address_string(), fmt % args)

        def _send(self, code: int, body: bytes = b"", ctype="application/json"):
            self.send_response(code)
            if body:
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
            elif code not in (204, 304):
                # 204/304 are defined to have no body; sending Content-Length
                # on them makes strict clients unhappy about framing.
                self.send_header("Content-Length", "0")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_POST(self):
            path = self.path.split("?", 1)[0].rstrip("/")
            if path not in ("/hook", "/state", ""):
                self._send(404)
                return
            if not self._authorised():
                self._send(401, b'{"error":"bad token"}')
                return

            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._send(413)
                return
            raw = self.rfile.read(length) if length else b"{}"

            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                log.warning("bad payload on %s", path or "/hook")
                if path == "/state":
                    self._send(400, b'{"error":"body is not JSON"}')
                    return
                # Still 2xx for hooks: a malformed body is our problem, and a
                # non-2xx would surface a hook error inside Claude Code.
                self._send(204)
                return

            if path == "/state":
                self._do_state(payload)
                return

            try:
                registry.apply_event(payload)
                if on_event:
                    on_event()
            except Exception:
                log.exception("failed to apply hook event")

            # 204 with an empty body = "success, no decision". Claude Code
            # carries on exactly as if the hook weren't there.
            self._send(204)

        def _do_state(self, payload):
            """A named source reporting in.

            Unlike /hook this answers properly: whatever posted here is a
            script that can act on an error, and silently ignoring a typo in
            a state name would be a horrible thing to debug.
            """
            name = str(payload.get("source") or "").strip()
            if not name:
                self._send(400, b'{"error":"source is required"}')
                return

            state = payload.get("state")
            if isinstance(state, str):
                state = state.strip().lower()
            if state in ("", "clear", "none", "off"):
                state = None
            if state is not None and state not in VALID_STATES:
                body = json.dumps({
                    "error": f"unknown state {state!r}",
                    "valid": sorted(VALID_STATES) + ["clear"],
                }).encode()
                self._send(400, body)
                return

            try:
                ttl = float(payload.get("ttl", DEFAULT_TTL))
            except (TypeError, ValueError):
                self._send(400, b'{"error":"ttl must be a number"}')
                return

            try:
                registry.set_source(name, state,
                                    str(payload.get("detail") or "")[:200], ttl)
                if on_event:
                    on_event()
            except Exception:
                log.exception("failed to apply source state")
                self._send(500, b'{"error":"internal"}')
                return

            body = json.dumps({
                "source": name,
                "state": state,
                "aggregate": registry.aggregate(),
            }).encode()
            self._send(200, body)

        def do_GET(self):
            path = self.path.rstrip("/") or "/"
            if path == "/health":
                self._send(200, b'{"ok":true}')
            elif path == "/status":
                body = json.dumps(registry.snapshot(), indent=2).encode()
                self._send(200, body)
            else:
                self._send(404)

    class Server(ThreadingHTTPServer):
        # On Windows SO_REUSEADDR does not mean "reuse a port in TIME_WAIT",
        # it means "let a second socket bind a port someone is already
        # listening on". Leaving it on there lets a second `rookery run`
        # start quietly beside the first: half your reports reach a daemon
        # that is not the one driving your light, and nothing says so.
        # Elsewhere it is still wanted, so a restart does not have to wait
        # out TIME_WAIT.
        allow_reuse_address = os.name != "nt"

    try:
        httpd = Server((host, port), Handler)
    except OSError as exc:
        raise SystemExit(
            f"rookery: cannot listen on {host}:{port} ({exc}).\n"
            "  Something is already there -- most likely another `rookery run`.\n"
            "  Stop it, or pass --http-port to run a second one on purpose."
        ) from exc
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    log.info("hook endpoint listening on http://%s:%d/hook", host, port)
    return httpd
