"""Synchronous serial connection to an OBIS device."""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, Self, TypeVar

import serial

from . import protocol
from .errors import ObisDeviceError, ObisProtocolError, ObisTimeoutError
from .protocol import Request

if TYPE_CHECKING:
    from .laser import ObisLaser

T = TypeVar("T")

logger = logging.getLogger(__name__)

#: Serial settings from the OBIS manual (Table 9-12): 115200 baud, 8N1, no flow control.
BAUD_RATE = 115200
DEFAULT_TIMEOUT = 1.0


class SerialStream(Protocol):
    """The subset of :class:`serial.Serial` used by :class:`ObisConnection`."""

    def write(self, data: bytes, /) -> int | None: ...
    def readline(self) -> bytes: ...
    def reset_input_buffer(self) -> None: ...
    def close(self) -> None: ...


class ObisConnection:
    """A serial connection to an OBIS laser or controller (OBIS Remote, LaserBox).

    Each command waits for the device to acknowledge it (``OK`` or ``ERR<n>``) before the
    next one is sent. Exchanges are serialized with a lock, so a connection can be shared
    between threads.

    Use :meth:`open` to connect to a serial port, then :meth:`laser` to control a laser::

        with ObisConnection.open("COM3") as connection:
            laser = connection.laser()
            laser.set_power(0.02)
    """

    def __init__(self, stream: SerialStream, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Wrap an already open stream. Most users should call :meth:`open` instead.

        Args:
            stream: An open serial stream whose ``readline`` returns within the timeout.
            timeout: Maximum time, in seconds, to wait for a complete reply.
        """
        self._stream = stream
        self._lock = threading.Lock()
        self.timeout = timeout
        self._enable_handshaking()

    @classmethod
    def open(cls, port: str, *, timeout: float = DEFAULT_TIMEOUT) -> Self:
        """Open a serial port (e.g. ``"COM3"`` or ``"/dev/ttyACM0"``) and connect."""
        stream = serial.Serial(port, BAUD_RATE, timeout=timeout, write_timeout=timeout)
        try:
            return cls(stream, timeout=timeout)
        except BaseException:
            stream.close()
            raise

    def laser(self, channel: int = 0) -> ObisLaser:
        """Get a laser on this connection.

        Args:
            channel: 0 for a laser connected directly; 1, 2, ... for the lasers
                connected to an OBIS Remote or LaserBox.
        """
        from .laser import ObisLaser

        return ObisLaser(self, channel)

    def execute(self, request: Request[T], channel: int = 0) -> T:
        """Send a request to the device on ``channel`` and return its parsed reply."""
        if channel == protocol.BROADCAST_CHANNEL:
            raise ValueError("use broadcast() to send a command to every device")
        lines = self._exchange(protocol.address(request.command, channel))
        return request.parse(lines)

    def query(self, command: str, channel: int = 0) -> list[str]:
        """Send any raw command or query and return the reply lines (without ``OK``)."""
        return self._exchange(protocol.address(command, channel))

    def broadcast(self, command: str) -> None:
        """Send a command to every laser connected to a controller (OBIS Remote, LaserBox).

        Useful to switch several lasers at once, e.g. ``broadcast("SOUR:AM:STAT ON")``.
        Queries cannot be broadcast. Lasers connected directly do not acknowledge
        broadcasts, so this only works through a controller.
        """
        if "?" in command:
            raise ValueError("queries cannot be broadcast")
        self._exchange(protocol.address(command, protocol.BROADCAST_CHANNEL))

    def close(self) -> None:
        """Close the serial port."""
        with self._lock:
            self._stream.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # --- Internals -------------------------------------------------------------------

    def _exchange(self, command: str) -> list[str]:
        with self._lock:
            self._write(command)
            return self._read_reply(command)

    def _write(self, command: str) -> None:
        # Drop anything left over (late replies, command prompts) so replies stay in sync.
        self._stream.reset_input_buffer()
        logger.debug("-> %s", command)
        self._stream.write(command.encode("ascii") + b"\r")

    def _read_reply(self, command: str) -> list[str]:
        """Read reply lines until the ``OK`` / ``ERR<n>`` handshake."""
        deadline = time.monotonic() + self.timeout
        lines: list[str] = []
        while True:
            line = self._read_line(command, deadline)
            if line == "OK":
                return lines
            if line.startswith("ERR"):
                try:
                    code = int(line[3:])
                except ValueError:
                    raise ObisProtocolError(f"malformed error reply {line!r}") from None
                raise ObisDeviceError(code, command)
            lines.append(line)

    def _read_line(self, command: str, deadline: float) -> str:
        """Read the next non-empty line, ignoring the optional ``>`` command prompt."""
        while True:
            raw = self._stream.readline()
            if not raw.endswith(b"\n") or time.monotonic() > deadline:
                raise ObisTimeoutError(f"no complete reply to {command!r} within {self.timeout}s")
            line = raw.decode("ascii", errors="replace").strip().removeprefix(">").strip()
            logger.debug("<- %s", line)
            if line:
                return line

    def _enable_handshaking(self) -> None:
        """Make sure the device acknowledges every message, which this client relies on.

        The setting is persistent, so it is only written when it is off.
        """
        command = protocol.get_handshaking().command
        with self._lock:
            self._write(command)
            reply = self._read_line(command, time.monotonic() + self.timeout)
            if reply.upper() == "ON":
                self._read_reply(command)
                return
            logger.info("enabling message handshaking on the device")
            enable = protocol.set_handshaking(True).command
            self._write(enable)
            # The manual does not say whether this very command is acknowledged.
            with contextlib.suppress(ObisTimeoutError):
                self._read_reply(enable)
