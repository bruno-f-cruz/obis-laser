import asyncio

from fakes import FakeObisDevice

from obis import AsyncObisConnection, ObisConnection, OperatingMode


def test_async_laser_mirrors_sync_api() -> None:
    device = FakeObisDevice({"SOUR:AM:SOUR?": "ANALOG", "SOUR:TEMP:BAS?": "30.0C"})

    async def run() -> None:
        async with AsyncObisConnection(ObisConnection(device)) as connection:
            laser = connection.laser()
            assert await laser.get_operating_mode() is OperatingMode.ANALOG
            assert await laser.get_baseplate_temperature() == 30.0
            await laser.set_emission(False)

    asyncio.run(run())
    assert device.written[-1] == "SOUR:AM:STAT OFF"
    assert device.closed


def test_concurrent_requests_run_in_order() -> None:
    device = FakeObisDevice()

    async def run() -> None:
        async with AsyncObisConnection(ObisConnection(device)) as connection:
            laser = connection.laser()
            await asyncio.gather(*(laser.set_power(i / 1000) for i in range(20)))

    asyncio.run(run())
    expected = [f"SOUR:POW:LEV:IMM:AMPL {i / 1000:.6f}" for i in range(20)]
    assert device.written[1:] == expected
