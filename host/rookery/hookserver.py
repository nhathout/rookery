"""Tiny localhost HTTP endpoint that Claude Code hooks POST to.

Claude Code supports `"type": "http"` hooks, which means we get the full event
JSON with zero process spawns per hook. That keeps the beacon from adding any
noticeable latency to your agent loop.

Endpoints:
    POST /hook     -- a Claude Code hook event (returns 204, no decision)
    GET  /status   -- JSON dump of tracked sessions, for debugging
    GET  /health   -- 200 if the daemon is alive
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("rookery.http")

MAX_BODY = 1 << 20  # 1 MiB; hook payloads are tiny, this is just a guard


def make_server(host: str, port: int, registry, on_event=None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

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
            if self.path.rstrip("/") not in ("/hook", ""):
                self._send(404)
                return

            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._send(413)
                return
            raw = self.rfile.read(length) if length else b"{}"

            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                log.warning("bad hook payload")
                # Still 2xx: a malformed body is our problem, and returning a
                # non-2xx would surface a hook error inside Claude Code.
                self._send(204)
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

        def do_GET(self):
            path = self.path.rstrip("/") or "/"
            if path == "/health":
                self._send(200, b'{"ok":true}')
            elif path == "/status":
                body = json.dumps(registry.snapshot(), indent=2).encode()
                self._send(200, body)
            else:
                self._send(404)

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    log.info("hook endpoint listening on http://%s:%d/hook", host, port)
    return httpd
