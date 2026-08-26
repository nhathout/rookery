"""USB-serial link to the beacon, with port auto-detection and reconnect."""

from __future__ import annotations

import logging
import threading
import time

import serial
from serial.tools import list_ports

log = logging.getLogger("rookery.serial")

# USB vendor IDs that show up on ESP32 dev boards.
KNOWN_VIDS = {
    0x10C4,  # Silicon Labs CP210x
    0x1A86,  # WCH CH340 / CH9102
    0x0403,  # FTDI
    0x303A,  # Espressif native USB (S2/S3/C3/C6)
}


def list_candidate_ports() -> list:
    """Every serial port, most-likely-ESP32 first."""
    ports = list(list_ports.comports())
    ports.sort(key=lambda p: (p.vid not in KNOWN_VIDS, p.device))
    return ports


def describe_ports() -> str:
    lines = []
    for p in list_candidate_ports():
        vid = f"{p.vid:04X}" if p.vid is not None else "----"
        pid = f"{p.pid:04X}" if p.pid is not None else "----"
        mark = "*" if p.vid in KNOWN_VIDS else " "
        lines.append(f" {mark} {p.device:<24} {vid}:{pid}  {p.description}")
    return "\n".join(lines) or " (no serial ports found)"


def probe(device: str, baud: int = 115200, timeout: float = 2.5) -> bool:
    """Open a port and check that something answers PING with PONG."""
    try:
        with serial.Serial(device, baud, timeout=0.4) as ser:
            # Many boards reset when the port opens; give the bootloader a
            # moment before we expect it to answer.
            time.sleep(2.0)
            ser.reset_input_buffer()
            ser.write(b"PING\n")
            ser.flush()
            deadline = time.time() + timeout
            while time.time() < deadline:
                line = ser.readline().decode("utf-8", "replace").strip()
                if not line:
                    continue
                if line.startswith("PONG") or line.startswith("READY"):
                    return True
    except (OSError, serial.SerialException):
        return False
    return False


def autodetect(baud: int = 115200) -> str | None:
    ports = list_candidate_ports()

    # Known USB-serial chips first...
    for p in ports:
        if p.vid in KNOWN_VIDS:
            log.info("probing %s (%s)", p.device, p.description)
            if probe(p.device, baud):
                return p.device

    # ...then anything else. Plenty of boards use a chip we don't recognise,
    # and a PING/PONG handshake is the real test anyway.
    for p in ports:
        if p.vid in KNOWN_VIDS:
            continue
        log.info("probing %s (%s)", p.device, p.description)
        if probe(p.device, baud):
            return p.device
    return None


class SerialLink:
    """Owns the serial port. Reconnects on its own if the device is unplugged.

    Only this object writes to the port, so hook events arriving in parallel
    can never interleave half-written commands.
    """

    def __init__(self, port: str | None, baud: int = 115200):
        self.port = port
        self.baud = baud
        self._ser: serial.Serial | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.write(b"OFF\n")
                    self._ser.flush()
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None

    @property
    def connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # -- io ----------------------------------------------------------------

    def _ensure_open(self) -> bool:
        if self.connected:
            return True
        device = self.port or autodetect(self.baud)
        if not device:
            return False
        try:
            ser = serial.Serial(device, self.baud, timeout=0.5)
            time.sleep(2.0)  # let the board finish resetting
            ser.reset_input_buffer()
            with self._lock:
                self._ser = ser
            self.port = device
            log.info("connected to %s", device)
            return True
        except (OSError, serial.SerialException) as exc:
            log.debug("open %s failed: %s", device, exc)
            return False

    def send(self, line: str) -> bool:
        if not self._ensure_open():
            return False
        data = (line.rstrip("\n") + "\n").encode("ascii", "ignore")
        with self._lock:
            ser = self._ser
            if ser is None:
                return False
            try:
                ser.write(data)
                ser.flush()
                return True
            except (OSError, serial.SerialException) as exc:
                log.warning("write failed (%s); will reconnect", exc)
                try:
                    ser.close()
                except Exception:
                    pass
                self._ser = None
                return False

    def _read_loop(self) -> None:
        """Drain device output so the buffer never fills, and log it at debug
        level -- useful when you're bringing the hardware up."""
        while not self._stop.is_set():
            if not self.connected:
                time.sleep(1.0)
                self._ensure_open()
                continue
            try:
                raw = self._ser.readline()
            except (OSError, serial.SerialException):
                with self._lock:
                    self._ser = None
                continue
            if raw:
                log.debug("dev> %s", raw.decode("utf-8", "replace").strip())
