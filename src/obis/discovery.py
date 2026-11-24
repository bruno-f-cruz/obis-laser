"""Find OBIS devices connected to serial ports."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import serial
from serial.tools import list_ports

from . import protocol
from .connection import BAUD_RATE, ObisConnection
from .errors import ObisDeviceError, ObisError
from .models import DeviceType

logger = logging.getLogger(__name__)

DEFAULT_PROBE_TIMEOUT = 0.3

#: Maximum number of lasers searched for behind a controller.
MAX_CHANNELS = 8

#: USB vendor ID of Coherent, which identifies OBIS lasers and controllers connected over USB.
COHERENT_VENDOR_ID = 0x0D4D


@dataclass(frozen=True)
class DiscoveredDevice:
    """An OBIS device found by :func:`discover`."""

    port: str
    channel: int
    """Channel to pass to :class:`obis.ObisLaser` (0 for the device on the port itself)."""
    device_type: DeviceType
    model: str
    serial_number: str


def candidate_ports() -> list[str]:
    """List the serial ports of OBIS lasers and controllers connected over USB.

    Ports are recognized by Coherent's USB vendor ID, without opening them. Devices
    connected over RS-232, for example through a USB adapter, are not listed: probe
    them with :func:`discover`.
    """
    return sorted(port.device for port in list_ports.comports() if port.vid == COHERENT_VENDOR_ID)


def discover(
    ports: Iterable[str] | None = None,
    *,
    all_ports: bool = False,
    exclude: Iterable[str] = (),
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> list[DiscoveredDevice]:
    """Find OBIS lasers and controllers by probing serial ports.

    Each port is opened and sent an identification query (``*IDN?``); ports that reply
    like a Coherent device are then queried for their type, model and serial number.
    Lasers behind a controller (OBIS Remote, LaserBox) are listed with their channel.

    By default, only the ports of Coherent USB devices are probed (see
    :func:`candidate_ports`), or every serial port if there are none.

    Warning:
        Probing writes to every port probed, which may disturb other devices. Use
        ``ports`` or ``exclude`` to limit this. Ports that are already in use are skipped.

    Args:
        ports: Ports to probe. Defaults to the ports of Coherent USB devices, or to
            every serial port if there are none.
        all_ports: Probe every serial port, for example to also find devices connected
            over RS-232 while a Coherent USB device is connected. Ignored if ``ports``
            is given.
        exclude: Ports never to probe, e.g. ``["COM1", "COM11"]`` (case-insensitive).
        timeout: Time, in seconds, to wait for each reply.
    """
    if ports is None:
        every_port = sorted(port.device for port in list_ports.comports())
        ports = every_port if all_ports else (candidate_ports() or every_port)
    excluded = {port.casefold() for port in exclude}
    devices: list[DiscoveredDevice] = []
    for port in ports:
        if port.casefold() in excluded:
            continue
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
        # Lasers behind a controller are numbered from 1. An empty slot replies with an error
        # (an OBIS 5-Laser Box replies ERR-241), and a laser may follow it, so every slot is
        # queried; only a slot that does not reply at all ends the search.
        for channel in range(1, MAX_CHANNELS + 1):
            try:
                devices.append(_describe_channel(connection, port, channel))
            except ObisDeviceError:
                continue
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
