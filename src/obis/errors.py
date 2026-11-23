"""Exceptions raised by the OBIS client."""

from __future__ import annotations

#: Error codes and descriptions from the OBIS manual (Table 9-7).
ERROR_DESCRIPTIONS: dict[int, str] = {
    -400: "Query unavailable (queries cannot be broadcast)",
    -350: "Queue overflow",
    -321: "Out of memory",
    -310: "System error",
    -257: "File to open not named",
    -256: "File does not exist",
    -241: "Device unavailable",
    -221: "Settings conflict (command not allowed in the current device state)",
    -220: "Invalid parameter",
    -203: "Command protected",
    -200: "Execution error (command out of order)",
    -109: "Parameter missing",
    -102: "Syntax error",
    -100: "Unrecognized command or query",
    0: "No error",
    500: "Coherent Connection bus (CCB) fault",
    510: "I2C bus fault",
    520: "Controller time out",
    900: "CCB message timed out",
}


class ObisError(Exception):
    """Base class for every error raised by this package."""


class ObisDeviceError(ObisError):
    """The device rejected a command or query with an ``ERR<n>`` reply."""

    def __init__(self, code: int, command: str) -> None:
        self.code = code
        self.command = command
        self.description = ERROR_DESCRIPTIONS.get(code, "Unknown error")
        super().__init__(f"{command!r} failed with ERR{code}: {self.description}")


class ObisTimeoutError(ObisError):
    """The device did not complete its reply within the timeout."""


class ObisProtocolError(ObisError):
    """The device sent a reply that does not match the expected format."""
