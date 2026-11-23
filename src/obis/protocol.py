"""The OBIS host protocol, independent of any I/O.

Every operation is a function returning a :class:`Request`: the command text sent
to the device, paired with a parser that turns the reply lines into a typed value.
The synchronous (:class:`obis.ObisLaser`) and asynchronous (:class:`obis.AsyncObisLaser`)
clients both execute these same requests, so the protocol knowledge lives here only.

Requests can also be executed directly, for example::

    connection.execute(protocol.get_wavelength())

Command syntax follows chapter 9 ("Host Interface") of the OBIS LX/LS Operator's Manual.
Some commands only exist on some device types (LX, LS or OBIS Remote); sending them to
other devices makes the device reply with an error, raised as :class:`obis.ObisDeviceError`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from .errors import ObisProtocolError
from .models import (
    AnalogImpedance,
    DeviceType,
    ErrorRecord,
    FaultFlags,
    OperatingMode,
    StatusFlags,
)

T = TypeVar("T")

#: Channel number used to broadcast a command to every device on the bus.
BROADCAST_CHANNEL = 255

#: Maximum number of characters stored by the user information and field calibration date.
MAX_USER_TEXT_LENGTH = 31


@dataclass(frozen=True)
class Request(Generic[T]):
    """A single command or query, and how to interpret its reply."""

    command: str
    parse: Callable[[Sequence[str]], T]


def address(command: str, channel: int) -> str:
    """Route a command to a device by appending ``channel`` to its first word.

    Channel 0 is the first connected device: the laser itself when connected directly,
    or the controller (OBIS Remote, LaserBox) otherwise. Lasers behind a controller are
    numbered from 1 (manual section 9.2.5). For example, ``SOUR:AM:STAT ON`` on channel 2
    becomes ``SOUR2:AM:STAT ON``.
    """
    if not 0 <= channel <= BROADCAST_CHANNEL:
        raise ValueError(f"channel must be between 0 and {BROADCAST_CHANNEL}, got {channel}")
    if channel == 0:
        return command
    end = next((i for i, c in enumerate(command) if c in ":? "), len(command))
    return f"{command[:end]}{channel}{command[end:]}"


# --- Reply parsers -------------------------------------------------------------------


def _ignore(lines: Sequence[str]) -> None:
    return None


def _text(lines: Sequence[str]) -> str:
    if len(lines) != 1:
        raise ObisProtocolError(f"expected a single reply line, got {list(lines)!r}")
    return lines[0]


def _float(lines: Sequence[str]) -> float:
    return float(_text(lines))


def _int(lines: Sequence[str]) -> int:
    return int(_text(lines))


def _hex(lines: Sequence[str]) -> int:
    return int(_text(lines), 16)


def _on_off(lines: Sequence[str]) -> bool:
    value = _text(lines).upper()
    if value not in ("ON", "OFF"):
        raise ObisProtocolError(f"expected ON or OFF, got {value!r}")
    return value == "ON"


def _celsius(lines: Sequence[str]) -> float:
    """Parse a temperature such as ``25.1C`` (or ``77.2F``) into degrees Celsius."""
    value = _text(lines).strip()
    unit = value[-1:].upper()
    if unit == "F":
        return (float(value[:-1]) - 32.0) * 5.0 / 9.0
    if unit == "C":
        return float(value[:-1])
    return float(value)


def _error_record(lines: Sequence[str]) -> ErrorRecord:
    code, _, message = _text(lines).partition(",")
    return ErrorRecord(code=int(code), message=message.strip().strip('"'))


def _on_off_arg(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


def _query(command: str, parse: Callable[[Sequence[str]], T]) -> Request[T]:
    return Request(command, parse)


def _command(command: str) -> Request[None]:
    return Request(command, _ignore)


# --- IEEE-488.2 ----------------------------------------------------------------------


def identify() -> Request[str]:
    """Identification string, e.g. ``Coherent, Inc-OBIS 405nm 50mW C-V1.3-20090630``."""
    return _query("*IDN?", _text)


def reset() -> Request[None]:
    """Warm-boot the device. Clears fault conditions."""
    return _command("*RST")


def self_test() -> Request[FaultFlags]:
    """Run the self-test. Returns ``0xFFFFFFFF`` if the device does not implement it."""
    return _query("*TST?", lambda lines: FaultFlags(_hex(lines)))


# --- Session control -----------------------------------------------------------------


def get_handshaking() -> Request[bool]:
    return _query("SYST:COMM:HAND?", _on_off)


def set_handshaking(enabled: bool) -> Request[None]:
    """Persistent. The clients in this package require handshaking to be enabled."""
    return _command(f"SYST:COMM:HAND {_on_off_arg(enabled)}")


def get_prompt() -> Request[bool]:
    return _query("SYST:COMM:PROM?", _on_off)


def set_prompt(enabled: bool) -> Request[None]:
    """Persistent. Enables the ``>`` command prompt used by terminal programs."""
    return _command(f"SYST:COMM:PROM {_on_off_arg(enabled)}")


# --- System information --------------------------------------------------------------


def get_model() -> Request[str]:
    return _query("SYST:INF:MOD?", _text)


def get_manufacture_date() -> Request[str]:
    return _query("SYST:INF:MDAT?", _text)


def get_calibration_date() -> Request[str]:
    return _query("SYST:INF:CDAT?", _text)


def get_serial_number() -> Request[str]:
    return _query("SYST:INF:SNUM?", _text)


def get_part_number() -> Request[str]:
    return _query("SYST:INF:PNUM?", _text)


def get_firmware_version() -> Request[str]:
    return _query("SYST:INF:FVER?", _text)


def get_protocol_version() -> Request[str]:
    return _query("SYST:INF:PVER?", _text)


def get_wavelength() -> Request[float]:
    """Nominal wavelength in nanometers."""
    return _query("SYST:INF:WAV?", _float)


def get_power_rating() -> Request[float]:
    """Power rating in watts."""
    return _query("SYST:INF:POW?", _float)


def get_device_type() -> Request[DeviceType]:
    return _query("SYST:INF:TYP?", lambda lines: DeviceType(_text(lines).upper()))


def get_nominal_power() -> Request[float]:
    """Nominal CW output power in watts."""
    return _query("SOUR:POW:NOM?", _float)


def get_min_power() -> Request[float]:
    """Minimum CW output power in watts."""
    return _query("SOUR:POW:LIM:LOW?", _float)


def get_max_power() -> Request[float]:
    """Maximum CW output power in watts."""
    return _query("SOUR:POW:LIM:HIGH?", _float)


def get_user_info(index: int) -> Request[str]:
    """User-defined text stored at ``index`` (0 to 3)."""
    _check_user_index(index)
    return _query(f"SYST:INF:USER? {index}", _text)


def set_user_info(index: int, text: str) -> Request[None]:
    """Persistently store up to 31 characters of user-defined text at ``index`` (0 to 3)."""
    _check_user_index(index)
    _check_user_text(text)
    return _command(f"SYST:INF:USER {index},{text}")


def get_field_calibration_date() -> Request[str]:
    return _query("SYST:INF:FCD?", _text)


def set_field_calibration_date(text: str) -> Request[None]:
    """Persistently store the date of the last field calibration (up to 31 characters)."""
    _check_user_text(text)
    return _command(f"SYST:INF:FCD {text}")


def _check_user_index(index: int) -> None:
    if not 0 <= index <= 3:
        raise ValueError(f"user information index must be between 0 and 3, got {index}")


def _check_user_text(text: str) -> None:
    if len(text) > MAX_USER_TEXT_LENGTH or not text.isascii() or "\r" in text or "\n" in text:
        raise ValueError(
            f"text must be a single line of at most {MAX_USER_TEXT_LENGTH} ASCII characters"
        )


def device_info_requests() -> dict[str, Request[Any]]:
    """The requests needed to build a :class:`obis.DeviceInfo`, keyed by field name."""
    return {
        "model": get_model(),
        "serial_number": get_serial_number(),
        "part_number": get_part_number(),
        "firmware_version": get_firmware_version(),
        "protocol_version": get_protocol_version(),
        "device_type": get_device_type(),
        "wavelength": get_wavelength(),
        "power_rating": get_power_rating(),
        "nominal_power": get_nominal_power(),
        "min_power": get_min_power(),
        "max_power": get_max_power(),
        "manufacture_date": get_manufacture_date(),
        "calibration_date": get_calibration_date(),
    }


# --- System state --------------------------------------------------------------------


def get_status() -> Request[StatusFlags]:
    return _query("SYST:STAT?", lambda lines: StatusFlags(_hex(lines)))


def get_faults() -> Request[FaultFlags]:
    return _query("SYST:FAUL?", lambda lines: FaultFlags(_hex(lines)))


def get_power_cycles() -> Request[int]:
    """Number of times the device has been powered on."""
    return _query("SYST:CYCL?", _int)


def get_hours() -> Request[float]:
    """Hours the device has been powered on."""
    return _query("SYST:HOUR?", _float)


def get_diode_hours() -> Request[float]:
    """Hours the laser diode has been emitting."""
    return _query("SYST:DIOD:HOUR?", _float)


def get_power() -> Request[float]:
    """Measured output power in watts."""
    return _query("SOUR:POW:LEV?", _float)


def get_current() -> Request[float]:
    """Laser diode current in amperes."""
    return _query("SOUR:POW:CURR?", _float)


def get_baseplate_temperature() -> Request[float]:
    """Base plate temperature in degrees Celsius."""
    return _query("SOUR:TEMP:BAS?", _celsius)


def get_interlock() -> Request[bool]:
    """OBIS Remote interlock state: ``True`` when closed (emission allowed)."""
    return _query("SYST:LOCK?", _on_off)


def get_noise() -> Request[int]:
    """Relative power noise level (constant power mode). Above 30 is considered noisy."""
    return _query("SYST:NOIS?", _int)


def get_threshold_current() -> Request[float]:
    """Laser diode threshold current in amperes."""
    return _query("SOUR:CURR:LIM:LOW?", _float)


def get_max_current() -> Request[float]:
    """Laser diode upper current limit in amperes (OBIS LX, firmware 2.x or later)."""
    return _query("SOUR:CURR:LIM:HIGH?", _float)


def get_baseplate_temperature_low_limit() -> Request[float]:
    return _query("SOUR:TEMP:PROT:BAS:LOW?", _celsius)


def get_baseplate_temperature_high_limit() -> Request[float]:
    return _query("SOUR:TEMP:PROT:BAS:HIGH?", _celsius)


def get_diode_temperature_low_limit() -> Request[float]:
    return _query("SOUR:TEMP:PROT:DIOD:LOW?", _celsius)


def get_diode_temperature_high_limit() -> Request[float]:
    return _query("SOUR:TEMP:PROT:DIOD:HIGH?", _celsius)


def get_internal_temperature_low_limit() -> Request[float]:
    return _query("SOUR:TEMP:PROT:INT:LOW?", _celsius)


def get_internal_temperature_high_limit() -> Request[float]:
    return _query("SOUR:TEMP:PROT:INT:HIGH?", _celsius)


def get_diode_temperature() -> Request[float]:
    """Laser diode temperature in degrees Celsius (OBIS LX)."""
    return _query("SOUR:TEMP:DIOD?", _celsius)


def get_diode_temperature_setpoint() -> Request[float]:
    """TEC set point for the laser diode in degrees Celsius (OBIS LX).

    The manual lists both ``SOURce:TEMPerature:DSETpoint?`` and
    ``SOURce:TEMPerature:DIODe:DSETpoint?``; the former is used here.
    """
    return _query("SOUR:TEMP:DSET?", _celsius)


def get_internal_temperature() -> Request[float]:
    """Internal (microprocessor) temperature in degrees Celsius (OBIS LX)."""
    return _query("SOUR:TEMP:INT?", _celsius)


# --- Error queue ---------------------------------------------------------------------


def get_error_count() -> Request[int]:
    return _query("SYST:ERR:COUN?", _int)


def get_next_error() -> Request[ErrorRecord]:
    """Pop the oldest record from the error queue. Only valid if the queue is not empty."""
    return _query("SYST:ERR:NEXT?", _error_record)


def clear_errors() -> Request[None]:
    return _command("SYST:ERR:CLE")


# --- Operation -----------------------------------------------------------------------


def get_operating_mode() -> Request[OperatingMode]:
    return _query("SOUR:AM:SOUR?", lambda lines: OperatingMode(_text(lines).upper()))


def set_operating_mode(mode: OperatingMode) -> Request[None]:
    """Persistent. External modes require the laser to be connected to an OBIS Remote."""
    mode = OperatingMode(mode)
    selector = "EXT" if mode.is_external else "INT"
    return _command(f"SOUR:AM:{selector} {mode.value}")


def get_power_setpoint() -> Request[float]:
    """Requested output power in watts."""
    return _query("SOUR:POW:LEV:IMM:AMPL?", _float)


def set_power(watts: float) -> Request[None]:
    """Set the output power in watts. Does not turn emission on."""
    if not math.isfinite(watts) or watts < 0:
        raise ValueError(f"power must be a finite, non-negative number of watts, got {watts}")
    return _command(f"SOUR:POW:LEV:IMM:AMPL {watts:.6f}")


def get_emission() -> Request[bool]:
    return _query("SOUR:AM:STAT?", _on_off)


def set_emission(enabled: bool) -> Request[None]:
    """Turn emission on or off. Emission may be delayed by warm-up and the CDRH delay."""
    return _command(f"SOUR:AM:STAT {_on_off_arg(enabled)}")


def laser_state_requests() -> dict[str, Request[Any]]:
    """The requests needed to build a :class:`obis.LaserState`, keyed by field name."""
    return {
        "emission": get_emission(),
        "operating_mode": get_operating_mode(),
        "power_setpoint": get_power_setpoint(),
        "power": get_power(),
        "current": get_current(),
        "baseplate_temperature": get_baseplate_temperature(),
        "status": get_status(),
        "faults": get_faults(),
    }


# --- Persistent settings -------------------------------------------------------------


def get_auto_start() -> Request[bool]:
    return _query("SYST:AUT?", _on_off)


def set_auto_start(enabled: bool) -> Request[None]:
    """Persistent. When enabled, the laser starts emitting at power-up."""
    return _command(f"SYST:AUT {_on_off_arg(enabled)}")


def get_cdrh_delay() -> Request[bool]:
    return _query("SYST:CDRH?", _on_off)


def set_cdrh_delay(enabled: bool) -> Request[None]:
    """Persistent. Disabling the 5 s emission delay makes the system non-CDRH compliant."""
    return _command(f"SYST:CDRH {_on_off_arg(enabled)}")


def get_tec_enabled() -> Request[bool]:
    return _query("SOUR:TEMP:APR?", _on_off)


def set_tec_enabled(enabled: bool) -> Request[None]:
    """Enable the TEC (LX) or thermal stabilization (LS). Off puts an LX in sleep mode."""
    return _command(f"SOUR:TEMP:APR {_on_off_arg(enabled)}")


def get_diode_warmup() -> Request[bool]:
    return _query("SYST:DIOD:WARM?", _on_off)


def set_diode_warmup(enabled: bool) -> Request[None]:
    """Persistent (OBIS LX). When enabled, emission waits for the diode warm-up."""
    return _command(f"SYST:DIOD:WARM {_on_off_arg(enabled)}")


def get_status_indicator() -> Request[bool]:
    return _query("SYST:IND:LAS?", _on_off)


def set_status_indicator(enabled: bool) -> Request[None]:
    """Persistent. Turn the status LED on or off; status bits are not affected."""
    return _command(f"SYST:IND:LAS {_on_off_arg(enabled)}")


def get_analog_blanking() -> Request[bool]:
    return _query("SOUR:AM:BLAN?", _on_off)


def set_analog_blanking(enabled: bool) -> Request[None]:
    """Enable blanking in analog modulation modes."""
    return _command(f"SOUR:AM:BLAN {_on_off_arg(enabled)}")


def get_analog_impedance() -> Request[AnalogImpedance]:
    """OBIS Remote analog input impedance."""
    return _query("SYST:INF:AMOD:TYP?", lambda lines: AnalogImpedance(_int(lines)))


def set_analog_impedance(impedance: AnalogImpedance) -> Request[None]:
    """Persistent (OBIS Remote). Select the analog input impedance."""
    return _command(f"SYST:INF:AMOD:TYP {AnalogImpedance(impedance).value}")


# --- Maintenance ---------------------------------------------------------------------


def start_field_calibration() -> Request[None]:
    """Start a laser power field calibration (OBIS LX). Takes minutes; do not cut power.

    Progress is reported by :attr:`obis.StatusFlags.FIELD_CALIBRATION`.
    """
    return _command("SOUR:POW:CAL")


def undo_field_calibration() -> Request[None]:
    """Undo the last field calibration (OBIS LX)."""
    return _command("SOUR:POW:UNC")


def recover() -> Request[None]:
    """Recover from a persistent checksum error, restoring factory default settings.

    The manual advises contacting Coherent before using this command.
    """
    return _command("SYST:REC")
