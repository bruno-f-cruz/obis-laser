from types import SimpleNamespace

import pytest
from fakes import FakeObisDevice

from obis import DeviceType, candidate_ports, discover
from obis.cli import main
from obis.discovery import COHERENT_VENDOR_ID, MAX_CHANNELS

IDN = "Coherent, Inc-OBIS LaserBox-V1.0-20200101"
PROLIFIC_VENDOR_ID = 0x067B


def _port(name: str, vid: int | None = None) -> SimpleNamespace:
    """A serial port as listed by pyserial."""
    return SimpleNamespace(device=name, vid=vid)


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


def test_discover_finds_lasers_behind_a_multi_laser_box_across_empty_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Replies of an OBIS 5-Laser Box (TYP? MULTI): slot 2 is empty and replies ERR-241,
    # slot 3 has a laser.
    box = FakeObisDevice(
        {
            "*IDN?": "Coherent, Inc. - OBIS 5-LASER BOX - v1.0.5 - 20130109",
            "SYST:INF:TYP?": "MULTI",
            "SYST:INF:MOD?": "OBIS 5-LASER BOX",
            "SYST:INF:SNUM?": "C230823001",
            "SYST1:INF:TYP?": "OPSL",
            "SYST1:INF:MOD?": "OBIS LS 561-150",
            "SYST1:INF:SNUM?": "466789",
            "SYST3:INF:TYP?": "DDL",
            "SYST3:INF:MOD?": "514-50FP",
            "SYST3:INF:SNUM?": "FS230321024",
        }
    )
    for channel in [2, *range(4, MAX_CHANNELS + 1)]:
        for query in ("TYP", "MOD", "SNUM"):
            box.errors[f"SYST{channel}:INF:{query}?"] = -241
    monkeypatch.setattr("obis.discovery.serial.Serial", lambda *args, **kwargs: box)
    monkeypatch.setattr("obis.connection.serial.Serial", lambda *args, **kwargs: box)

    found = discover(["COM6"], timeout=0.05)

    assert [(d.port, d.channel, d.device_type, d.serial_number) for d in found] == [
        ("COM6", 0, DeviceType.MULTI, "C230823001"),
        ("COM6", 1, DeviceType.OPSL, "466789"),
        ("COM6", 3, DeviceType.DDL, "FS230321024"),
    ]


def test_discover_stops_at_a_slot_that_does_not_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    # A controller that stops replying at slot 2: the search ends there instead of waiting
    # on every slot.
    controller = FakeObisDevice(
        {
            "*IDN?": "Coherent, Inc-OBIS Remote-V1.0-20200101",
            "SYST:INF:TYP?": "MINI",
            "SYST:INF:MOD?": "OBIS Remote",
            "SYST:INF:SNUM?": "R1",
            "SYST1:INF:TYP?": "DDL",
            "SYST1:INF:MOD?": "OBIS 405nm LX 100mW",
            "SYST1:INF:SNUM?": "L1",
        }
    )
    controller.silent_from = "SYST2:INF:TYP?"
    monkeypatch.setattr("obis.discovery.serial.Serial", lambda *args, **kwargs: controller)
    monkeypatch.setattr("obis.connection.serial.Serial", lambda *args, **kwargs: controller)

    found = discover(["COM1"], timeout=0.05)

    assert [d.channel for d in found] == [0, 1]
    assert not any(command.startswith("SYST3") for command in controller.written)


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
    ports_found = [_port("COM1"), _port("COM2")]
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


def test_candidate_ports_are_coherent_usb_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    listed = [_port("COM12", COHERENT_VENDOR_ID), _port("COM10", PROLIFIC_VENDOR_ID), _port("COM1")]
    monkeypatch.setattr("obis.discovery.list_ports.comports", lambda: listed)
    assert candidate_ports() == ["COM12"]


def test_discover_probes_only_coherent_usb_ports_by_default(
    ports: dict[str, FakeObisDevice], monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = [_port("COM1", COHERENT_VENDOR_ID), _port("COM2", PROLIFIC_VENDOR_ID)]
    monkeypatch.setattr("obis.discovery.list_ports.comports", lambda: listed)
    assert [d.port for d in discover(timeout=0.05)] == ["COM1", "COM1", "COM1"]
    assert ports["COM2"].written == []


def test_discover_probes_every_port_without_coherent_usb_ports(
    ports: dict[str, FakeObisDevice], monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = [_port("COM1", PROLIFIC_VENDOR_ID), _port("COM2")]
    monkeypatch.setattr("obis.discovery.list_ports.comports", lambda: listed)
    assert len(discover(timeout=0.05)) == 3
    assert ports["COM2"].written == ["*IDN?"]


def test_discover_can_probe_every_port(
    ports: dict[str, FakeObisDevice], monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = [_port("COM1", PROLIFIC_VENDOR_ID), _port("COM2", COHERENT_VENDOR_ID)]
    monkeypatch.setattr("obis.discovery.list_ports.comports", lambda: listed)
    assert len(discover(all_ports=True, timeout=0.05)) == 3
    assert ports["COM2"].written == ["*IDN?"]


def test_cli_can_probe_every_port(
    ports: dict[str, FakeObisDevice],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    listed = [_port("COM1", PROLIFIC_VENDOR_ID), _port("COM2", COHERENT_VENDOR_ID)]
    monkeypatch.setattr("obis.discovery.list_ports.comports", lambda: listed)
    assert main(["list", "--all-ports"]) == 0
    assert "COM1  channel 0" in capsys.readouterr().out
