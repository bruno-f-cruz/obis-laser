"""Asynchronous (asyncio) client.

The serial port is driven by one dedicated worker thread, so requests run in the order
they are awaited and never block the event loop. The API mirrors :class:`obis.ObisLaser`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from types import TracebackType
from typing import Self, TypeVar

from . import protocol
from .connection import DEFAULT_TIMEOUT, ObisConnection
from .models import (
    AnalogImpedance,
    DeviceInfo,
    ErrorRecord,
    FaultFlags,
    LaserState,
    OperatingMode,
    StatusFlags,
    TemperatureLimits,
)
from .protocol import Request

T = TypeVar("T")
R = TypeVar("R")


class AsyncObisConnection:
    """Asynchronous counterpart of :class:`obis.ObisConnection`.

    Example::

        async with await AsyncObisConnection.open("COM3") as connection:
            laser = connection.laser()
            await laser.set_power(0.02)
    """

    def __init__(self, connection: ObisConnection) -> None:
        """Wrap a synchronous connection. Most users should call :meth:`open` instead."""
        self.connection = connection
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="obis")

    @classmethod
    async def open(cls, port: str, *, timeout: float = DEFAULT_TIMEOUT) -> Self:
        """Open a serial port (e.g. ``"COM3"`` or ``"/dev/ttyACM0"``) and connect."""
        return cls(await asyncio.to_thread(ObisConnection.open, port, timeout=timeout))

    def laser(self, channel: int = 0) -> AsyncObisLaser:
        """Get a laser on this connection (see :meth:`obis.ObisConnection.laser`)."""
        return AsyncObisLaser(self, channel)

    async def execute(self, request: Request[T], channel: int = 0) -> T:
        """Send a request to the device on ``channel`` and return its parsed reply."""
        return await self._run(self.connection.execute, request, channel)

    async def query(self, command: str, channel: int = 0) -> list[str]:
        """Send any raw command or query and return the reply lines (without ``OK``)."""
        return await self._run(self.connection.query, command, channel)

    async def broadcast(self, command: str) -> None:
        """Send a command to every laser connected to a controller."""
        await self._run(self.connection.broadcast, command)

    async def close(self) -> None:
        """Close the serial port after pending requests complete."""
        await self._run(self.connection.close)
        self._executor.shutdown()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def _run(self, function: Callable[..., R], *args: object) -> R:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, function, *args)


class AsyncObisLaser:
    """Asynchronous counterpart of :class:`obis.ObisLaser`; see it for documentation.

    Example::

        async with await AsyncObisLaser.open("COM3") as laser:
            await laser.set_power(0.010)
            await laser.set_emission(True)
    """

    def __init__(self, connection: AsyncObisConnection, channel: int = 0) -> None:
        self.connection = connection
        self.channel = channel
        self._owns_connection = False

    @classmethod
    async def open(cls, port: str, *, channel: int = 0, timeout: float = DEFAULT_TIMEOUT) -> Self:
        """Open a serial port and control the laser on it. :meth:`close` closes the port."""
        laser = cls(await AsyncObisConnection.open(port, timeout=timeout), channel)
        laser._owns_connection = True
        return laser

    async def close(self) -> None:
        """Close the connection, if it was opened by :meth:`open`. Emission is not changed."""
        if self._owns_connection:
            await self.connection.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(channel={self.channel})"

    async def execute(self, request: Request[T]) -> T:
        """Execute any request from :mod:`obis.protocol` on this laser."""
        return await self.connection.execute(request, self.channel)

    async def query(self, command: str) -> list[str]:
        """Send a raw command or query and return the reply lines."""
        return await self.connection.query(command, self.channel)

    # --- Information -----------------------------------------------------------------

    async def identify(self) -> str:
        """Identification string (``*IDN?``)."""
        return await self.execute(protocol.identify())

    async def get_info(self) -> DeviceInfo:
        """Model, serial number, firmware, wavelength, power limits and other static data."""
        values = {
            name: await self.execute(r) for name, r in protocol.device_info_requests().items()
        }
        return DeviceInfo(**values)

    async def get_user_info(self, index: int) -> str:
        """User-defined text stored at ``index`` (0 to 3)."""
        return await self.execute(protocol.get_user_info(index))

    async def set_user_info(self, index: int, text: str) -> None:
        """Persistent. Store up to 31 characters of user-defined text at ``index`` (0 to 3)."""
        await self.execute(protocol.set_user_info(index, text))

    async def get_field_calibration_date(self) -> str:
        return await self.execute(protocol.get_field_calibration_date())

    async def set_field_calibration_date(self, text: str) -> None:
        """Persistent. Store the date of the last field calibration (up to 31 characters)."""
        await self.execute(protocol.set_field_calibration_date(text))

    # --- Control ---------------------------------------------------------------------

    async def get_emission(self) -> bool:
        """Whether emission is turned on."""
        return await self.execute(protocol.get_emission())

    async def set_emission(self, enabled: bool) -> None:
        """Turn emission on or off. Emission may be delayed by warm-up and the CDRH delay."""
        await self.execute(protocol.set_emission(enabled))

    async def get_power_setpoint(self) -> float:
        """Requested output power in watts."""
        return await self.execute(protocol.get_power_setpoint())

    async def set_power(self, watts: float) -> None:
        """Set the output power in watts. Does not turn emission on."""
        await self.execute(protocol.set_power(watts))

    async def get_power(self) -> float:
        """Measured output power in watts."""
        return await self.execute(protocol.get_power())

    async def get_current(self) -> float:
        """Laser diode current in amperes."""
        return await self.execute(protocol.get_current())

    async def get_operating_mode(self) -> OperatingMode:
        return await self.execute(protocol.get_operating_mode())

    async def set_operating_mode(self, mode: OperatingMode) -> None:
        """Persistent. External modes require the laser to be connected to an OBIS Remote."""
        await self.execute(protocol.set_operating_mode(mode))

    # --- State -----------------------------------------------------------------------

    async def get_state(self) -> LaserState:
        """Emission, mode, power, current, base plate temperature, status and faults."""
        values = {
            name: await self.execute(r) for name, r in protocol.laser_state_requests().items()
        }
        return LaserState(**values)

    async def get_status(self) -> StatusFlags:
        return await self.execute(protocol.get_status())

    async def get_faults(self) -> FaultFlags:
        """Active faults. A reset (:meth:`reset`) or power cycle is needed to clear them."""
        return await self.execute(protocol.get_faults())

    async def get_baseplate_temperature(self) -> float:
        return await self.execute(protocol.get_baseplate_temperature())

    async def get_diode_temperature(self) -> float:
        """Laser diode temperature (OBIS LX)."""
        return await self.execute(protocol.get_diode_temperature())

    async def get_diode_temperature_setpoint(self) -> float:
        """TEC set point for the laser diode (OBIS LX)."""
        return await self.execute(protocol.get_diode_temperature_setpoint())

    async def get_internal_temperature(self) -> float:
        """Internal (microprocessor) temperature (OBIS LX)."""
        return await self.execute(protocol.get_internal_temperature())

    async def get_baseplate_temperature_limits(self) -> TemperatureLimits:
        return TemperatureLimits(
            await self.execute(protocol.get_baseplate_temperature_low_limit()),
            await self.execute(protocol.get_baseplate_temperature_high_limit()),
        )

    async def get_diode_temperature_limits(self) -> TemperatureLimits:
        """Diode temperature limits (OBIS LX)."""
        return TemperatureLimits(
            await self.execute(protocol.get_diode_temperature_low_limit()),
            await self.execute(protocol.get_diode_temperature_high_limit()),
        )

    async def get_internal_temperature_limits(self) -> TemperatureLimits:
        """Internal temperature limits (OBIS LX)."""
        return TemperatureLimits(
            await self.execute(protocol.get_internal_temperature_low_limit()),
            await self.execute(protocol.get_internal_temperature_high_limit()),
        )

    async def get_threshold_current(self) -> float:
        """Laser diode threshold current in amperes."""
        return await self.execute(protocol.get_threshold_current())

    async def get_max_current(self) -> float:
        """Laser diode upper current limit in amperes (OBIS LX, firmware 2.x or later)."""
        return await self.execute(protocol.get_max_current())

    async def get_interlock(self) -> bool:
        """OBIS Remote interlock state: ``True`` when closed (emission allowed)."""
        return await self.execute(protocol.get_interlock())

    async def get_noise(self) -> int:
        """Relative power noise level (constant power mode). Above 30 is considered noisy."""
        return await self.execute(protocol.get_noise())

    async def get_power_cycles(self) -> int:
        return await self.execute(protocol.get_power_cycles())

    async def get_hours(self) -> float:
        """Hours the device has been powered on."""
        return await self.execute(protocol.get_hours())

    async def get_diode_hours(self) -> float:
        """Hours the laser diode has been emitting."""
        return await self.execute(protocol.get_diode_hours())

    # --- Error queue -----------------------------------------------------------------

    async def get_errors(self) -> list[ErrorRecord]:
        """Read and remove every record from the device error queue (oldest first)."""
        count = await self.execute(protocol.get_error_count())
        return [await self.execute(protocol.get_next_error()) for _ in range(count)]

    async def clear_errors(self) -> None:
        await self.execute(protocol.clear_errors())

    # --- Persistent settings ---------------------------------------------------------

    async def get_auto_start(self) -> bool:
        return await self.execute(protocol.get_auto_start())

    async def set_auto_start(self, enabled: bool) -> None:
        """Persistent. When enabled, the laser starts emitting at power-up."""
        await self.execute(protocol.set_auto_start(enabled))

    async def get_cdrh_delay(self) -> bool:
        return await self.execute(protocol.get_cdrh_delay())

    async def set_cdrh_delay(self, enabled: bool) -> None:
        """Persistent. Disabling the 5 s emission delay makes the system non-CDRH compliant."""
        await self.execute(protocol.set_cdrh_delay(enabled))

    async def get_tec_enabled(self) -> bool:
        return await self.execute(protocol.get_tec_enabled())

    async def set_tec_enabled(self, enabled: bool) -> None:
        """Enable the TEC (LX) or thermal stabilization (LS). Off puts an LX in sleep mode."""
        await self.execute(protocol.set_tec_enabled(enabled))

    async def get_diode_warmup(self) -> bool:
        return await self.execute(protocol.get_diode_warmup())

    async def set_diode_warmup(self, enabled: bool) -> None:
        """Persistent (OBIS LX). When enabled, emission waits for the diode warm-up."""
        await self.execute(protocol.set_diode_warmup(enabled))

    async def get_status_indicator(self) -> bool:
        return await self.execute(protocol.get_status_indicator())

    async def set_status_indicator(self, enabled: bool) -> None:
        """Persistent. Turn the status LED on or off; status bits are not affected."""
        await self.execute(protocol.set_status_indicator(enabled))

    async def get_analog_blanking(self) -> bool:
        return await self.execute(protocol.get_analog_blanking())

    async def set_analog_blanking(self, enabled: bool) -> None:
        """Enable blanking in analog modulation modes."""
        await self.execute(protocol.set_analog_blanking(enabled))

    async def get_analog_impedance(self) -> AnalogImpedance:
        """OBIS Remote analog input impedance."""
        return await self.execute(protocol.get_analog_impedance())

    async def set_analog_impedance(self, impedance: AnalogImpedance) -> None:
        """Persistent (OBIS Remote). Select the analog input impedance."""
        await self.execute(protocol.set_analog_impedance(impedance))

    # --- Maintenance -----------------------------------------------------------------

    async def reset(self) -> None:
        """Warm-boot the device. Clears fault conditions."""
        await self.execute(protocol.reset())

    async def self_test(self) -> FaultFlags:
        """Run the self-test; ``0xFFFFFFFF`` means the self-test is not implemented."""
        return await self.execute(protocol.self_test())

    async def start_field_calibration(self) -> None:
        """Start a power field calibration (OBIS LX). Takes minutes; do not cut power.

        Progress is reported by :attr:`StatusFlags.FIELD_CALIBRATION`.
        """
        await self.execute(protocol.start_field_calibration())

    async def undo_field_calibration(self) -> None:
        """Undo the last field calibration (OBIS LX)."""
        await self.execute(protocol.undo_field_calibration())

    async def recover(self) -> None:
        """Recover from a checksum error, restoring factory defaults. Ask Coherent first."""
        await self.execute(protocol.recover())
