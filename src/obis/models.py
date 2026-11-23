"""Typed values exchanged with OBIS devices."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag, StrEnum
from typing import NamedTuple


class OperatingMode(StrEnum):
    """Laser operating mode (manual section 9.5.1)."""

    CWP = "CWP"
    """Continuous wave, constant power."""
    CWC = "CWC"
    """Continuous wave, constant current."""
    DIGITAL = "DIGITAL"
    """External digital modulation, current feedback."""
    ANALOG = "ANALOG"
    """External analog modulation, power feedback."""
    MIXED = "MIXED"
    """External digital + analog modulation, current feedback."""
    DIGSO = "DIGSO"
    """External digital modulation, power feedback (not supported by all models)."""
    MIXSO = "MIXSO"
    """External digital + analog modulation, power feedback (not supported by all models)."""

    @property
    def is_external(self) -> bool:
        """Whether the mode uses external modulation."""
        return self not in (OperatingMode.CWP, OperatingMode.CWC)


class DeviceType(StrEnum):
    """Device type reported by ``SYSTem:INFormation:TYPe?``."""

    DDL = "DDL"
    """OBIS LX (direct diode laser)."""
    OPSL = "OPSL"
    """OBIS LS (optically pumped semiconductor laser)."""
    MINI = "MINI"
    """OBIS Remote (mini controller)."""
    MASTER = "MASTER"
    """Master controller, e.g. an OBIS LaserBox."""
    OTHER = "OTHER"
    """Any other device type."""

    @classmethod
    def _missing_(cls, value: object) -> DeviceType:
        return cls.OTHER

    @property
    def is_controller(self) -> bool:
        """Whether the device is a controller that routes commands to lasers."""
        return self in (DeviceType.MINI, DeviceType.MASTER)


class AnalogImpedance(IntEnum):
    """Input impedance of the OBIS Remote analog modulation channel."""

    OHM_50 = 1
    KOHM_2 = 2


class StatusFlags(IntFlag):
    """Bits of the system status word (manual Table 9-5)."""

    NONE = 0
    LASER_FAULT = 1 << 0
    LASER_EMISSION = 1 << 1
    LASER_READY = 1 << 2
    LASER_STANDBY = 1 << 3
    CDRH_DELAY = 1 << 4
    LASER_HARDWARE_FAULT = 1 << 5
    LASER_ERROR = 1 << 6
    LASER_POWER_CALIBRATION = 1 << 7
    LASER_WARM_UP = 1 << 8
    LASER_NOISE = 1 << 9
    EXTERNAL_OPERATING_MODE = 1 << 10
    FIELD_CALIBRATION = 1 << 11
    LASER_POWER_VOLTAGE = 1 << 12
    CONTROLLER_STANDBY = 1 << 25
    CONTROLLER_INTERLOCK = 1 << 26
    CONTROLLER_ENUMERATION = 1 << 27
    CONTROLLER_ERROR = 1 << 28
    CONTROLLER_FAULT = 1 << 29
    REMOTE_ACTIVE = 1 << 30
    CONTROLLER_INDICATOR = 1 << 31


class FaultFlags(IntFlag):
    """Bits of the system fault word (manual Tables 9-4 and 9-6)."""

    NONE = 0
    BASEPLATE_TEMPERATURE = 1 << 0
    DIODE_TEMPERATURE = 1 << 1
    INTERNAL_TEMPERATURE = 1 << 2
    LASER_POWER_SUPPLY = 1 << 3
    I2C_ERROR = 1 << 4
    OVER_CURRENT = 1 << 5
    LASER_CHECKSUM = 1 << 6
    CHECKSUM_RECOVERY = 1 << 7
    BUFFER_OVERFLOW = 1 << 8
    WARM_UP_LIMIT = 1 << 9
    TEC_DRIVER = 1 << 10
    CCB_ERROR = 1 << 11
    DIODE_TEMPERATURE_LIMIT = 1 << 12
    LASER_READY = 1 << 13
    PHOTODIODE = 1 << 14
    FATAL = 1 << 15
    STARTUP = 1 << 16
    WATCHDOG_RESET = 1 << 17
    FIELD_CALIBRATION = 1 << 18
    OVER_POWER = 1 << 20
    CONTROLLER_CHECKSUM = 1 << 30
    CONTROLLER_STATUS = 1 << 31


class TemperatureLimits(NamedTuple):
    """Temperature range, in degrees Celsius, outside of which the device faults."""

    low: float
    high: float


@dataclass(frozen=True)
class ErrorRecord:
    """An entry of the device error queue."""

    code: int
    message: str


@dataclass(frozen=True)
class DeviceInfo:
    """Static information describing a laser.

    Dates are reported by the device as ``YYYYMMDD`` strings and are kept as-is.
    """

    model: str
    serial_number: str
    part_number: str
    firmware_version: str
    protocol_version: str
    device_type: DeviceType
    wavelength: float
    """Nominal wavelength, in nanometers."""
    power_rating: float
    """Power rating, in watts."""
    nominal_power: float
    """Nominal CW output power, in watts."""
    min_power: float
    """Minimum CW output power, in watts."""
    max_power: float
    """Maximum CW output power, in watts."""
    manufacture_date: str
    calibration_date: str


@dataclass(frozen=True)
class LaserState:
    """A snapshot of the dynamic state of a laser."""

    emission: bool
    operating_mode: OperatingMode
    power_setpoint: float
    """Requested output power, in watts."""
    power: float
    """Measured output power, in watts."""
    current: float
    """Laser diode current, in amperes."""
    baseplate_temperature: float
    """Base plate temperature, in degrees Celsius."""
    status: StatusFlags
    faults: FaultFlags
