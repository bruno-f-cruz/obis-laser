"""Tests against a real OBIS laser.

Skipped unless ``OBIS_PORT`` is set, and always skipped in CI (``CI`` is set).

    OBIS_PORT=COM3 uv run pytest tests/test_hardware.py -v -s

Optional environment variables:

- ``OBIS_CHANNEL``: channel of the laser behind an OBIS Remote / LaserBox (default 0).
- ``OBIS_TEST_EMISSION=1``: also run the tests that turn emission ON, at 5 % of the
  maximum power. Make sure the beam is safely blocked first.

Only settings that are restored to their original value are written.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterator

import pytest

from obis import (
    AsyncObisLaser,
    DeviceType,
    ObisDeviceError,
    ObisLaser,
    OperatingMode,
    StatusFlags,
    discover,
)

PORT = os.environ.get("OBIS_PORT", "")
CHANNEL = int(os.environ.get("OBIS_CHANNEL", "0"))
TEST_EMISSION = os.environ.get("OBIS_TEST_EMISSION") == "1"

pytestmark = [
    pytest.mark.skipif(bool(os.environ.get("CI")), reason="hardware tests never run in CI"),
    pytest.mark.skipif(not PORT, reason="set OBIS_PORT to test with a real laser"),
]

requires_emission = pytest.mark.skipif(
    not TEST_EMISSION, reason="set OBIS_TEST_EMISSION=1 to run tests that turn emission on"
)


@pytest.fixture
def laser() -> Iterator[ObisLaser]:
    with ObisLaser.open(PORT, channel=CHANNEL) as laser:
        yield laser


def test_identify(laser: ObisLaser) -> None:
    identity = laser.identify()
    print(identity)
    assert identity.startswith("Coherent")


def test_info_is_consistent(laser: ObisLaser) -> None:
    info = laser.get_info()
    print(info)
    assert info.device_type in (DeviceType.DDL, DeviceType.OPSL)
    assert 200 < info.wavelength < 2000
    assert 0 <= info.min_power <= info.nominal_power <= info.max_power
    assert info.serial_number


def test_state_is_readable(laser: ObisLaser) -> None:
    state = laser.get_state()
    print(state)
    assert 0 < state.baseplate_temperature < 60
    assert state.power >= 0
    assert state.current >= 0


def test_settings_are_readable(laser: ObisLaser) -> None:
    values = {
        "auto_start": laser.get_auto_start(),
        "cdrh_delay": laser.get_cdrh_delay(),
        "tec_enabled": laser.get_tec_enabled(),
        "status_indicator": laser.get_status_indicator(),
        "power_cycles": laser.get_power_cycles(),
        "hours": laser.get_hours(),
        "baseplate_limits": laser.get_baseplate_temperature_limits(),
    }
    print(values)
    assert values["power_cycles"] > 0


def test_device_errors_are_reported(laser: ObisLaser) -> None:
    laser.clear_errors()
    with pytest.raises(ObisDeviceError):
        laser.query("NOT:A:REAL:COMMAND?")
    assert laser.get_emission() in (True, False)  # the connection is still in sync
    laser.clear_errors()
    assert laser.get_errors() == []


def test_power_setpoint_round_trip(laser: ObisLaser) -> None:
    original = laser.get_power_setpoint()
    target = laser.get_info().max_power * 0.05
    try:
        laser.set_power(target)
        assert laser.get_power_setpoint() == pytest.approx(target, rel=0.01, abs=1e-4)
    finally:
        laser.set_power(original)
    assert laser.get_power_setpoint() == pytest.approx(original, rel=0.01, abs=1e-4)


def test_operating_mode_round_trip(laser: ObisLaser) -> None:
    mode = laser.get_operating_mode()
    laser.set_operating_mode(mode)
    assert laser.get_operating_mode() is mode


def test_exchange_latency(laser: ObisLaser) -> None:
    count = 50
    start = time.perf_counter()
    for _ in range(count):
        laser.get_power()
    elapsed = (time.perf_counter() - start) / count
    print(f"average exchange: {elapsed * 1000:.2f} ms")
    assert elapsed < 0.1


def test_async_client() -> None:
    async def run() -> None:
        async with await AsyncObisLaser.open(PORT, channel=CHANNEL) as laser:
            state, info = await asyncio.gather(laser.get_state(), laser.get_info())
            assert info.max_power > 0
            assert state.power >= 0

    asyncio.run(run())


def test_discover_finds_the_laser() -> None:
    devices = discover([PORT])
    print(devices)
    assert any(device.channel == CHANNEL for device in devices)


@requires_emission
def test_emission(laser: ObisLaser) -> None:
    original_mode = laser.get_operating_mode()
    original_power = laser.get_power_setpoint()
    target = laser.get_info().max_power * 0.05
    try:
        laser.set_operating_mode(OperatingMode.CWP)
        laser.set_power(target)
        laser.set_emission(True)
        assert laser.get_emission()

        # Emission can be delayed by warm-up and the 5 s CDRH delay.
        deadline = time.monotonic() + 30
        while StatusFlags.LASER_READY not in laser.get_status():
            assert time.monotonic() < deadline, "laser did not become ready within 30 s"
            time.sleep(0.2)
        time.sleep(1)

        power = laser.get_power()
        print(f"set {target * 1000:.2f} mW, measured {power * 1000:.2f} mW")
        assert power == pytest.approx(target, rel=0.1, abs=1e-3)
    finally:
        laser.set_emission(False)
        laser.set_power(original_power)
        laser.set_operating_mode(original_mode)
    assert not laser.get_emission()
