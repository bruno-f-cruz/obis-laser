"""A scripted stand-in for the serial port of an OBIS device."""

from __future__ import annotations

from typing import Self


class FakeObisDevice:
    """Replies to commands like an OBIS device, from a table of canned query replies.

    - Queries listed in ``replies`` return those lines followed by ``OK``.
    - Unknown queries, and commands listed in ``errors``, return ``ERR<code>``.
    - Other commands return ``OK``.
    """

    def __init__(self, replies: dict[str, str] | None = None) -> None:
        self.replies: dict[str, str] = {"SYST:COMM:HAND?": "ON", **(replies or {})}
        self.errors: dict[str, int] = {}
        self.written: list[str] = []
        self.handshaking = True
        self.silent = False
        self.silent_from: str | None = None
        """A command from which the device stops replying, e.g. to simulate a controller hanging."""
        self.prompt = False
        self.closed = False
        self._buffer = bytearray()

    # --- SerialStream ----------------------------------------------------------------

    def write(self, data: bytes) -> int:
        assert data.endswith(b"\r"), "commands must be terminated by a carriage return"
        command = data.decode("ascii").removesuffix("\r")
        self.written.append(command)
        if command == self.silent_from:
            self.silent = True
        if not self.silent:
            self._respond(command)
        return len(data)

    def readline(self) -> bytes:
        end = self._buffer.find(b"\n")
        if end < 0:  # nothing complete: behave like a serial read timing out
            line, self._buffer = bytes(self._buffer), bytearray()
            return line
        line, self._buffer = bytes(self._buffer[: end + 1]), self._buffer[end + 1 :]
        return line

    def reset_input_buffer(self) -> None:
        self._buffer.clear()

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # --- Behaviour -------------------------------------------------------------------

    def _respond(self, command: str) -> None:
        if command in self.errors:
            self._send(f"ERR{self.errors[command]}")
        elif "?" in command:
            if command not in self.replies:
                self._send("ERR-100")
                return
            self._send(self.replies[command])
            if self.handshaking:
                self._send("OK")
        else:
            if command == "SYST:COMM:HAND ON":
                self.handshaking = True
            if self.handshaking:
                self._send("OK")
        if self.prompt:
            self._buffer += b"\r\n> "

    def _send(self, line: str) -> None:
        self._buffer += line.encode("ascii") + b"\r\n"
