"""Find OBIS devices connected to serial ports."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import serial
from serial.tools import list_ports

from . import protocol
from .connection import BAUD_RATE, ObisConnection
from .errors import ObisError
from .models import DeviceType

logger = logging.getLogger(__name__)

DEFAULT_PROBE_TIMEOUT = 0.3

#: Maximum number of lasers searched for behind a controller.
MAX_CHANNELS = 8


@dataclass(frozen=True)
class DiscoveredDevice:
    """An OBIS device found by :func:`discover`."""

    port: str
    channel: int
    """Channel to pass to :class:`obis.ObisLaser` (0 for the device on the port itself)."""
    device_type: DeviceType
    model: str
    serial_number: str


def discover(
    ports: Iterable[str] | None = None, *, timeout: float = DEFAULT_PROBE_TIMEOUT
) -> list[DiscoveredDevice]:
    """Find OBIS lasers and controllers by probing serial ports.

    Each port is opened and sent an identification query (``*IDN?``); ports that reply
    like a Coherent device are then queried for their type, model and serial number.
    Lasers behind a controller (OBIS Remote, LaserBox) are listed with their channel.

    Warning:
        Probing writes to every port in ``ports`` (all serial ports by default), which
        may disturb other devices. Pass an explicit list of ports to limit this.
        Ports that are already in use are skipped.

    Args:
        ports: Ports to probe. Defaults to every serial port on the computer.
        timeout: Time, in seconds, to wait for each reply.
    """
    if ports is None:
        ports = sorted(port.device for port in list_ports.comports())
    devices: list[DiscoveredDevice] = []
    for port in ports:
        if not _replies_like_obis(port, timeout):
            continue
        try:
            with ObisConnection.open(port, timeout=timeout) as connection:
                devices.extend(_describe(connection, port))
        except (ObisError, serial.SerialException) as error:
            logger.warning("could not query OBIS device on %s: %s", port, error)
    return devices


def _replies_like_obis(port: str, timeout: float) -> bool:
    """Send ``*IDN?`` without changing any device setting and check the reply."""
    try:
        with serial.Serial(port, BAUD_RATE, timeout=timeout, write_timeout=timeout) as stream:
            stream.reset_input_buffer()
            stream.write(b"*IDN?\r")
            reply = stream.readline().decode("ascii", errors="replace")
    except (serial.SerialException, OSError) as error:
        logger.debug("skipping %s: %s", port, error)
        return False
    return reply.strip().removeprefix(">").strip().startswith("Coherent")


def _describe(connection: ObisConnection, port: str) -> list[DiscoveredDevice]:
    root = _describe_channel(connection, port, 0)
    devices = [root]
    if root.device_type.is_controller:
        # Lasers behind a controller are numbered from 1; stop at the first missing one.
        for channel in range(1, MAX_CHANNELS + 1):
            try:
                devices.append(_describe_channel(connection, port, channel))
            except ObisError:
                break
    return devices


def _describe_channel(connection: ObisConnection, port: str, channel: int) -> DiscoveredDevice:
    return DiscoveredDevice(
        port=port,
        channel=channel,
        device_type=connection.execute(protocol.get_device_type(), channel),
        model=connection.execute(protocol.get_model(), channel),
        serial_number=connection.execute(protocol.get_serial_number(), channel),
    )
