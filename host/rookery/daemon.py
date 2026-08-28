"""The daemon: hook events in, serial commands out."""

from __future__ import annotations

import logging
import signal
import threading
import time

from .hookserver import make_server
from .serial_link import SerialLink
from .state import Registry

log = logging.getLogger("rookery")

# Resend the current state at least this often. The firmware treats silence
# longer than its LINK_TIMEOUT_MS as "host died" and dims itself, so this
# doubles as a heartbeat.
HEARTBEAT_SECONDS = 8.0

# Coalesce bursts of hook events (a batch of parallel tool calls fires several
# at once) into a single serial write.
DEBOUNCE_SECONDS = 0.05


class Daemon:
    def __init__(
        self,
        port: str | None = None,
        baud: int = 115200,
        http_host: str = "127.0.0.1",
        http_port: int = 8787,
        brightness: int | None = None,
        simulate: bool = False,
        token: str | None = None,
    ):
        self.registry = Registry()
        self.simulate = simulate
        self.brightness = brightness
        self.link = None if simulate else SerialLink(port, baud)
        self.http_host = http_host
        self.http_port = http_port
        self.token = token
        self._httpd = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._last_sent: str | None = None
        self._last_sent_at = 0.0
        self._brightness_sent = False

    # -- plumbing ----------------------------------------------------------

    def _on_event(self):
        self._wake.set()

    def _push(self, state: str, force: bool = False) -> None:
        now = time.time()
        if not force and state == self._last_sent:
            if now - self._last_sent_at < HEARTBEAT_SECONDS:
                return

        if self.simulate:
            if state != self._last_sent:
                log.info("[simulate] STATE %s", state)
            self._last_sent = state
            self._last_sent_at = now
            return

        # Push brightness once per connection.
        if self.brightness is not None and not self._brightness_sent:
            if self.link.send(f"BRIGHT {self.brightness}"):
                self._brightness_sent = True

        ok = self.link.send(f"STATE {state}")
        if ok:
            if state != self._last_sent:
                log.info("-> %s", state)
            self._last_sent = state
            self._last_sent_at = now
        else:
            # Failed write means we dropped the port; re-send brightness after
            # the reconnect.
            self._brightness_sent = False

    # -- lifecycle ---------------------------------------------------------

    def run(self) -> int:
        if not self.simulate:
            self.link.start()

        self._httpd = make_server(
            self.http_host, self.http_port, self.registry, self._on_event,
            token=self.token,
        )

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_: self._stop.set())
            except (ValueError, OSError):
                pass  # not on the main thread, or unsupported platform

        log.info("rookery running. Ctrl-C to stop.")
        last_sweep = 0.0

        try:
            while not self._stop.is_set():
                # Wait for a hook event, but wake up regularly to heartbeat.
                self._wake.wait(timeout=1.0)
                if self._wake.is_set():
                    self._wake.clear()
                    time.sleep(DEBOUNCE_SECONDS)
                    self._wake.clear()

                now = time.time()
                if now - last_sweep > 60:
                    self.registry.sweep()
                    last_sweep = now

                self._push(self.registry.aggregate())
        finally:
            self.shutdown()
        return 0

    def shutdown(self) -> None:
        log.info("shutting down")
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
        if self.link is not None:
            self.link.stop()
