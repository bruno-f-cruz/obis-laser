"""Synchronous client for a single OBIS laser."""

from __future__ import annotations

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


class ObisLaser:
    """Controls one OBIS laser.

    Power is in watts, current in amperes and temperatures in degrees Celsius.
    Settings documented as *persistent* are saved in the laser's non-volatile memory.

    Example::

        with ObisLaser.open("COM3") as laser:
            print(laser.get_info())
            laser.set_power(0.010)
            laser.set_emission(True)
    """

    def __init__(self, connection: ObisConnection, channel: int = 0) -> None:
        """Control the laser on ``channel`` of an existing connection.

        Args:
            connection: The connection to the laser or to its controller.
            channel: 0 for a laser connected directly; 1, 2, ... for the lasers
                connected to an OBIS Remote or LaserBox.
        """
        self.connection = connection
        self.channel = channel
        self._owns_connection = False

    @classmethod
    def open(cls, port: str, *, channel: int = 0, timeout: float = DEFAULT_TIMEOUT) -> Self:
        """Open a serial port and control the laser on it. :meth:`close` closes the port."""
        laser = cls(ObisConnection.open(port, timeout=timeout), channel)
        laser._owns_connection = True
        return laser

    def close(self) -> None:
        """Close the connection, if it was opened by :meth:`open`. Emission is not changed."""
        if self._owns_connection:
            self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(channel={self.channel})"

    def execute(self, request: Request[T]) -> T:
        """Execute any request from :mod:`obis.protocol` on this laser."""
        return self.connection.execute(request, self.channel)

    def query(self, command: str) -> list[str]:
        """Send a raw command or query and return the reply lines."""
        return self.connection.query(command, self.channel)

    # --- Information -----------------------------------------------------------------

    def identify(self) -> str:
        """Identification string (``*IDN?``)."""
        return self.execute(protocol.identify())

    def get_info(self) -> DeviceInfo:
        """Model, serial number, firmware, wavelength, power limits and other static data."""
        values = {name: self.execute(r) for name, r in protocol.device_info_requests().items()}
        return DeviceInfo(**values)

    def get_user_info(self, index: int) -> str:
        """User-defined text stored at ``index`` (0 to 3)."""
        return self.execute(protocol.get_user_info(index))

    def set_user_info(self, index: int, text: str) -> None:
        """Persistent. Store up to 31 characters of user-defined text at ``index`` (0 to 3)."""
        self.execute(protocol.set_user_info(index, text))

    def get_field_calibration_date(self) -> str:
        return self.execute(protocol.get_field_calibration_date())

    def set_field_calibration_date(self, text: str) -> None:
        """Persistent. Store the date of the last field calibration (up to 31 characters)."""
        self.execute(protocol.set_field_calibration_date(text))

    # --- Control ---------------------------------------------------------------------

    def get_emission(self) -> bool:
        """Whether emission is turned on."""
        return self.execute(protocol.get_emission())

    def set_emission(self, enabled: bool) -> None:
        """Turn emission on or off. Emission may be delayed by warm-up and the CDRH delay."""
        self.execute(protocol.set_emission(enabled))

    def get_power_setpoint(self) -> float:
        """Requested output power in watts."""
        return self.execute(protocol.get_power_setpoint())

    def set_power(self, watts: float) -> None:
        """Set the output power in watts. Does not turn emission on."""
        self.execute(protocol.set_power(watts))

    def get_power(self) -> float:
        """Measured output power in watts."""
        return self.execute(protocol.get_power())

    def get_current(self) -> float:
        """Laser diode current in amperes."""
        return self.execute(protocol.get_current())

    def get_operating_mode(self) -> OperatingMode:
        return self.execute(protocol.get_operating_mode())

    def set_operating_mode(self, mode: OperatingMode) -> None:
        """Persistent. External modes require the laser to be connected to an OBIS Remote."""
        self.execute(protocol.set_operating_mode(mode))

    # --- State -----------------------------------------------------------------------

    def get_state(self) -> LaserState:
        """Emission, mode, power, current, base plate temperature, status and faults."""
        values = {name: self.execute(r) for name, r in protocol.laser_state_requests().items()}
        return LaserState(**values)

    def get_status(self) -> StatusFlags:
        return self.execute(protocol.get_status())

    def get_faults(self) -> FaultFlags:
        """Active faults. A reset (:meth:`reset`) or power cycle is needed to clear them."""
        return self.execute(protocol.get_faults())

    def get_baseplate_temperature(self) -> float:
        return self.execute(protocol.get_baseplate_temperature())

    def get_diode_temperature(self) -> float:
        """Laser diode temperature (OBIS LX)."""
        return self.execute(protocol.get_diode_temperature())

    def get_diode_temperature_setpoint(self) -> float:
        """TEC set point for the laser diode (OBIS LX)."""
        return self.execute(protocol.get_diode_temperature_setpoint())

    def get_internal_temperature(self) -> float:
        """Internal (microprocessor) temperature (OBIS LX)."""
        return self.execute(protocol.get_internal_temperature())

    def get_baseplate_temperature_limits(self) -> TemperatureLimits:
        return TemperatureLimits(
            self.execute(protocol.get_baseplate_temperature_low_limit()),
            self.execute(protocol.get_baseplate_temperature_high_limit()),
        )

    def get_diode_temperature_limits(self) -> TemperatureLimits:
        """Diode temperature limits (OBIS LX)."""
        return TemperatureLimits(
            self.execute(protocol.get_diode_temperature_low_limit()),
            self.execute(protocol.get_diode_temperature_high_limit()),
        )

    def get_internal_temperature_limits(self) -> TemperatureLimits:
        """Internal temperature limits (OBIS LX)."""
        return TemperatureLimits(
            self.execute(protocol.get_internal_temperature_low_limit()),
            self.execute(protocol.get_internal_temperature_high_limit()),
        )

    def get_threshold_current(self) -> float:
        """Laser diode threshold current in amperes."""
        return self.execute(protocol.get_threshold_current())

    def get_max_current(self) -> float:
        """Laser diode upper current limit in amperes (OBIS LX, firmware 2.x or later)."""
        return self.execute(protocol.get_max_current())

    def get_interlock(self) -> bool:
        """OBIS Remote interlock state: ``True`` when closed (emission allowed)."""
        return self.execute(protocol.get_interlock())

    def get_noise(self) -> int:
        """Relative power noise level (constant power mode). Above 30 is considered noisy."""
        return self.execute(protocol.get_noise())

    def get_power_cycles(self) -> int:
        return self.execute(protocol.get_power_cycles())

    def get_hours(self) -> float:
        """Hours the device has been powered on."""
        return self.execute(protocol.get_hours())

    def get_diode_hours(self) -> float:
        """Hours the laser diode has been emitting."""
        return self.execute(protocol.get_diode_hours())

    # --- Error queue -----------------------------------------------------------------

    def get_errors(self) -> list[ErrorRecord]:
        """Read and remove every record from the device error queue (oldest first)."""
        count = self.execute(protocol.get_error_count())
        return [self.execute(protocol.get_next_error()) for _ in range(count)]

    def clear_errors(self) -> None:
        self.execute(protocol.clear_errors())

    # --- Persistent settings ---------------------------------------------------------

    def get_auto_start(self) -> bool:
        return self.execute(protocol.get_auto_start())

    def set_auto_start(self, enabled: bool) -> None:
        """Persistent. When enabled, the laser starts emitting at power-up."""
        self.execute(protocol.set_auto_start(enabled))

    def get_cdrh_delay(self) -> bool:
        return self.execute(protocol.get_cdrh_delay())

    def set_cdrh_delay(self, enabled: bool) -> None:
        """Persistent. Disabling the 5 s emission delay makes the system non-CDRH compliant."""
        self.execute(protocol.set_cdrh_delay(enabled))

    def get_tec_enabled(self) -> bool:
        return self.execute(protocol.get_tec_enabled())

    def set_tec_enabled(self, enabled: bool) -> None:
        """Enable the TEC (LX) or thermal stabilization (LS). Off puts an LX in sleep mode."""
        self.execute(protocol.set_tec_enabled(enabled))

    def get_diode_warmup(self) -> bool:
        return self.execute(protocol.get_diode_warmup())

    def set_diode_warmup(self, enabled: bool) -> None:
        """Persistent (OBIS LX). When enabled, emission waits for the diode warm-up."""
        self.execute(protocol.set_diode_warmup(enabled))

    def get_status_indicator(self) -> bool:
        return self.execute(protocol.get_status_indicator())

    def set_status_indicator(self, enabled: bool) -> None:
        """Persistent. Turn the status LED on or off; status bits are not affected."""
        self.execute(protocol.set_status_indicator(enabled))

    def get_analog_blanking(self) -> bool:
        return self.execute(protocol.get_analog_blanking())

    def set_analog_blanking(self, enabled: bool) -> None:
        """Enable blanking in analog modulation modes."""
        self.execute(protocol.set_analog_blanking(enabled))

    def get_analog_impedance(self) -> AnalogImpedance:
        """OBIS Remote analog input impedance."""
        return self.execute(protocol.get_analog_impedance())

    def set_analog_impedance(self, impedance: AnalogImpedance) -> None:
        """Persistent (OBIS Remote). Select the analog input impedance."""
        self.execute(protocol.set_analog_impedance(impedance))

    # --- Maintenance -----------------------------------------------------------------

    def reset(self) -> None:
        """Warm-boot the device. Clears fault conditions."""
        self.execute(protocol.reset())

    def self_test(self) -> FaultFlags:
        """Run the self-test; ``0xFFFFFFFF`` means the self-test is not implemented."""
        return self.execute(protocol.self_test())

    def start_field_calibration(self) -> None:
        """Start a power field calibration (OBIS LX). Takes minutes; do not cut power.

        Progress is reported by :attr:`StatusFlags.FIELD_CALIBRATION`.
        """
        self.execute(protocol.start_field_calibration())

    def undo_field_calibration(self) -> None:
        """Undo the last field calibration (OBIS LX)."""
        self.execute(protocol.undo_field_calibration())

    def recover(self) -> None:
        """Recover from a checksum error, restoring factory defaults. Ask Coherent first."""
        self.execute(protocol.recover())
