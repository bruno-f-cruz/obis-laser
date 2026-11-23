import threading

import pytest
from fakes import FakeObisDevice

from obis import (
    DeviceType,
    FaultFlags,
    ObisConnection,
    ObisDeviceError,
    ObisLaser,
    ObisTimeoutError,
    OperatingMode,
    StatusFlags,
)

INFO_REPLIES = {
    "SYST:INF:MOD?": "OBIS 488nm LX 50mW",
    "SYST:INF:SNUM?": "123456",
    "SYST:INF:PNUM?": "1234567",
    "SYST:INF:FVER?": "V3.0.5",
    "SYST:INF:PVER?": "P1.0a",
    "SYST:INF:TYP?": "DDL",
    "SYST:INF:WAV?": "488",
    "SYST:INF:POW?": "0.050",
    "SOUR:POW:NOM?": "0.05000",
    "SOUR:POW:LIM:LOW?": "0.00000",
    "SOUR:POW:LIM:HIGH?": "0.05500",
    "SYST:INF:MDAT?": "20200102",
    "SYST:INF:CDAT?": "20200103",
}

STATE_REPLIES = {
    "SOUR:AM:STAT?": "ON",
    "SOUR:AM:SOUR?": "CWP",
    "SOUR:POW:LEV:IMM:AMPL?": "0.02000",
    "SOUR:POW:LEV?": "0.01998",
    "SOUR:POW:CURR?": "0.06100",
    "SOUR:TEMP:BAS?": "28.4C",
    "SYST:STAT?": "00000006",
    "SYST:FAUL?": "00000000",
}


@pytest.fixture
def device() -> FakeObisDevice:
    return FakeObisDevice({**INFO_REPLIES, **STATE_REPLIES})


@pytest.fixture
def laser(device: FakeObisDevice) -> ObisLaser:
    return ObisConnection(device, timeout=0.1).laser()


def test_connecting_does_not_rewrite_handshaking_when_on(device: FakeObisDevice) -> None:
    ObisConnection(device)
    assert device.written == ["SYST:COMM:HAND?"]


def test_connecting_enables_handshaking_when_off() -> None:
    device = FakeObisDevice({"SYST:COMM:HAND?": "OFF"})
    device.handshaking = False
    ObisConnection(device, timeout=0.1)
    assert device.written == ["SYST:COMM:HAND?", "SYST:COMM:HAND ON"]
    assert device.handshaking


def test_get_info(laser: ObisLaser) -> None:
    info = laser.get_info()
    assert info.model == "OBIS 488nm LX 50mW"
    assert info.device_type is DeviceType.DDL
    assert info.wavelength == 488
    assert info.max_power == pytest.approx(0.055)
    assert info.calibration_date == "20200103"


def test_get_state(laser: ObisLaser) -> None:
    state = laser.get_state()
    assert state.emission
    assert state.operating_mode is OperatingMode.CWP
    assert state.power == pytest.approx(0.01998)
    assert state.baseplate_temperature == pytest.approx(28.4)
    assert state.status == StatusFlags.LASER_EMISSION | StatusFlags.LASER_READY
    assert state.faults == FaultFlags.NONE


def test_set_power_and_emission(laser: ObisLaser, device: FakeObisDevice) -> None:
    laser.set_power(0.02)
    laser.set_emission(True)
    assert device.written[-2:] == ["SOUR:POW:LEV:IMM:AMPL 0.020000", "SOUR:AM:STAT ON"]


def test_invalid_power_is_not_sent(laser: ObisLaser, device: FakeObisDevice) -> None:
    sent = len(device.written)
    with pytest.raises(ValueError):
        laser.set_power(-1)
    assert len(device.written) == sent


def test_laser_behind_controller_uses_its_channel(device: FakeObisDevice) -> None:
    device.replies["SOUR2:AM:STAT?"] = "OFF"
    laser = ObisConnection(device).laser(channel=2)
    assert laser.get_emission() is False
    laser.set_emission(True)
    assert device.written[-1] == "SOUR2:AM:STAT ON"


def test_device_errors_are_raised(laser: ObisLaser, device: FakeObisDevice) -> None:
    device.errors["SOUR:POW:LEV:IMM:AMPL 1.000000"] = -220
    with pytest.raises(ObisDeviceError) as error:
        laser.set_power(1.0)
    assert error.value.code == -220
    assert error.value.description == "Invalid parameter"


def test_unsupported_query_raises(laser: ObisLaser) -> None:
    with pytest.raises(ObisDeviceError) as error:
        laser.get_diode_temperature()
    assert error.value.code == -100


def test_missing_reply_times_out(laser: ObisLaser, device: FakeObisDevice) -> None:
    device.silent = True
    with pytest.raises(ObisTimeoutError):
        laser.get_emission()


def test_late_command_prompt_is_ignored(laser: ObisLaser, device: FakeObisDevice) -> None:
    device.prompt = True
    device.reset_input_buffer = lambda: None  # the prompt arrives after the buffer reset
    assert laser.get_emission() is True
    assert laser.get_operating_mode() is OperatingMode.CWP


def test_get_errors_reads_the_whole_queue(laser: ObisLaser, device: FakeObisDevice) -> None:
    device.replies["SYST:ERR:COUN?"] = "2"
    device.replies["SYST:ERR:NEXT?"] = '-102,"Syntax error"'
    errors = laser.get_errors()
    assert [e.code for e in errors] == [-102, -102]


def test_temperature_limits(laser: ObisLaser, device: FakeObisDevice) -> None:
    device.replies["SOUR:TEMP:PROT:BAS:LOW?"] = "10.0C"
    device.replies["SOUR:TEMP:PROT:BAS:HIGH?"] = "50.0C"
    assert laser.get_baseplate_temperature_limits() == (10.0, 50.0)


def test_open_owns_the_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    device = FakeObisDevice()
    monkeypatch.setattr("obis.connection.serial.Serial", lambda *args, **kwargs: device)
    with ObisLaser.open("COM9"):
        pass
    assert device.closed


def test_connection_is_thread_safe(laser: ObisLaser) -> None:
    results: list[bool] = []

    def poll() -> None:
        for _ in range(50):
            results.append(laser.get_emission())
            laser.set_power(0.01)

    threads = [threading.Thread(target=poll) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [True] * 200
