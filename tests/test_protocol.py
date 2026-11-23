import pytest

from obis import FaultFlags, ObisProtocolError, OperatingMode, StatusFlags, protocol


@pytest.mark.parametrize(
    ("command", "channel", "expected"),
    [
        ("SOUR:AM:STAT ON", 0, "SOUR:AM:STAT ON"),
        ("SOUR:AM:STAT ON", 2, "SOUR2:AM:STAT ON"),
        ("*IDN?", 1, "*IDN1?"),
        ("SYST:INF:USER? 0", 3, "SYST3:INF:USER? 0"),
        ("*RST", 1, "*RST1"),
        ("SOUR:AM:STAT OFF", 255, "SOUR255:AM:STAT OFF"),
    ],
)
def test_address_appends_channel_to_first_word(command: str, channel: int, expected: str) -> None:
    assert protocol.address(command, channel) == expected


@pytest.mark.parametrize("channel", [-1, 256])
def test_address_rejects_invalid_channel(channel: int) -> None:
    with pytest.raises(ValueError):
        protocol.address("*IDN?", channel)


def test_set_power_formats_watts() -> None:
    assert protocol.set_power(0.025).command == "SOUR:POW:LEV:IMM:AMPL 0.025000"


@pytest.mark.parametrize("watts", [-0.001, float("nan"), float("inf")])
def test_set_power_rejects_invalid_values(watts: float) -> None:
    with pytest.raises(ValueError):
        protocol.set_power(watts)


@pytest.mark.parametrize(
    ("mode", "command"),
    [
        (OperatingMode.CWP, "SOUR:AM:INT CWP"),
        (OperatingMode.CWC, "SOUR:AM:INT CWC"),
        (OperatingMode.DIGITAL, "SOUR:AM:EXT DIGITAL"),
        (OperatingMode.MIXSO, "SOUR:AM:EXT MIXSO"),
    ],
)
def test_set_operating_mode_selects_internal_or_external(mode: OperatingMode, command: str) -> None:
    assert protocol.set_operating_mode(mode).command == command


@pytest.mark.parametrize(
    ("reply", "celsius"), [("25.1C", 25.1), ("25.1", 25.1), ("77.0F", 25.0), ("-3.5c", -3.5)]
)
def test_temperatures_are_parsed_to_celsius(reply: str, celsius: float) -> None:
    assert protocol.get_baseplate_temperature().parse([reply]) == pytest.approx(celsius)


def test_status_word_is_parsed_from_hex() -> None:
    status = protocol.get_status().parse(["00000012"])
    assert status == StatusFlags.LASER_EMISSION | StatusFlags.CDRH_DELAY


def test_unknown_fault_bits_are_kept() -> None:
    faults = protocol.get_faults().parse(["0x00080003"])
    assert FaultFlags.BASEPLATE_TEMPERATURE in faults
    assert int(faults) == 0x00080003


def test_error_record_is_parsed() -> None:
    record = protocol.get_next_error().parse(['-220,"Invalid parameter"'])
    assert (record.code, record.message) == (-220, "Invalid parameter")


def test_on_off_rejects_other_values() -> None:
    with pytest.raises(ObisProtocolError):
        protocol.get_emission().parse(["MAYBE"])


def test_single_line_replies_reject_extra_lines() -> None:
    with pytest.raises(ObisProtocolError):
        protocol.get_model().parse(["a", "b"])


@pytest.mark.parametrize(("index", "text"), [(4, "ok"), (0, "x" * 32), (0, "two\nlines")])
def test_user_info_is_validated(index: int, text: str) -> None:
    with pytest.raises(ValueError):
        protocol.set_user_info(index, text)
