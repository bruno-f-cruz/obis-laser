import pytest
from fakes import FakeObisDevice

from obis import DeviceType, discover
from obis.cli import main

IDN = "Coherent, Inc-OBIS LaserBox-V1.0-20200101"


def _controller_with_two_lasers() -> FakeObisDevice:
    return FakeObisDevice(
        {
            "*IDN?": IDN,
            "SYST:INF:TYP?": "MASTER",
            "SYST:INF:MOD?": "OBIS LaserBox",
            "SYST:INF:SNUM?": "B1",
            "SYST1:INF:TYP?": "DDL",
            "SYST1:INF:MOD?": "OBIS 405nm LX 100mW",
            "SYST1:INF:SNUM?": "L1",
            "SYST2:INF:TYP?": "OPSL",
            "SYST2:INF:MOD?": "OBIS 561nm LS 50mW",
            "SYST2:INF:SNUM?": "L2",
        }
    )


@pytest.fixture
def ports(monkeypatch: pytest.MonkeyPatch) -> dict[str, FakeObisDevice]:
    """COM1 has a LaserBox with two lasers; COM2 has an unrelated, silent device."""
    other = FakeObisDevice()
    other.silent = True
    devices = {"COM1": _controller_with_two_lasers(), "COM2": other}

    def open_port(port: str, *args: object, **kwargs: object) -> FakeObisDevice:
        return devices[port]

    monkeypatch.setattr("obis.discovery.serial.Serial", open_port)
    monkeypatch.setattr("obis.connection.serial.Serial", open_port)
    return devices


def test_discover_finds_lasers_behind_a_controller(ports: dict[str, FakeObisDevice]) -> None:
    found = discover(["COM1", "COM2"], timeout=0.05)
    assert [(d.port, d.channel, d.device_type, d.serial_number) for d in found] == [
        ("COM1", 0, DeviceType.MASTER, "B1"),
        ("COM1", 1, DeviceType.DDL, "L1"),
        ("COM1", 2, DeviceType.OPSL, "L2"),
    ]
    assert ports["COM2"].written == ["*IDN?"]


def test_excluded_ports_are_not_probed(ports: dict[str, FakeObisDevice]) -> None:
    found = discover(["COM1", "COM2"], exclude=["com1"], timeout=0.05)
    assert found == []
    assert ports["COM1"].written == []
    assert ports["COM2"].written == ["*IDN?"]


def test_cli_excludes_ports(
    ports: dict[str, FakeObisDevice],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ports_found = [type("Port", (), {"device": name})() for name in ("COM1", "COM2")]
    monkeypatch.setattr("obis.discovery.list_ports.comports", lambda: ports_found)
    assert main(["list", "--exclude", "COM2"]) == 0
    assert "COM1  channel 0" in capsys.readouterr().out
    assert ports["COM2"].written == []


def test_cli_lists_devices(
    ports: dict[str, FakeObisDevice],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("obis.discovery.list_ports.comports", lambda: [])
    assert main(["list"]) == 1
    assert "no OBIS device found" in capsys.readouterr().out
