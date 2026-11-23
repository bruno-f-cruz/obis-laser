# obis-laser

Python client for Coherent OBIS LX/LS lasers, over USB or RS-232. It covers the whole
host command set from the OBIS LX/LS Operator's Manual: device metadata, emission and
power control, operating modes, temperatures, status and fault words, the error queue
and persistent settings. Synchronous and `asyncio` APIs are provided.

> OBIS and Coherent are trademarks of Coherent Corp. This project is not affiliated
> with or endorsed by Coherent.

## Install

```sh
uv add obis-laser            # in a project
uv tool install obis-laser   # just the command line tool
```

Requires Python 3.11+. The only dependency is [pyserial](https://github.com/pyserial/pyserial).

## Quick start

```python
from obis import ObisLaser, OperatingMode

with ObisLaser.open("COM3") as laser:  # "/dev/ttyACM0" on Linux
    info = laser.get_info()
    print(info.model, info.serial_number, info.wavelength, "nm")

    laser.set_operating_mode(OperatingMode.CWP)
    laser.set_power(0.010)  # watts
    laser.set_emission(True)
    print(laser.get_state())
    laser.set_emission(False)
```

Units are SI as used by the device: power in **watts**, current in **amperes**,
temperatures in **degrees Celsius**.

### Several lasers behind an OBIS Remote or LaserBox

Channel 0 is the controller; lasers are numbered from 1.

```python
from obis import ObisConnection

with ObisConnection.open("COM3") as connection:
    blue, green = connection.laser(1), connection.laser(2)
    blue.set_power(0.02)
    connection.broadcast("SOUR:AM:STAT ON")  # every laser at once
```

### asyncio

```python
from obis import AsyncObisLaser

async with await AsyncObisLaser.open("COM3") as laser:
    await laser.set_power(0.010)
    state = await laser.get_state()
```

### Finding lasers

```python
import obis

for device in obis.discover():
    print(device.port, device.channel, device.model, device.serial_number)
```

`discover()` sends `*IDN?` to every serial port (or only to the ports you pass), so it
may disturb other serial devices; it does not change any setting on non-OBIS devices.

### Anything else

Every command is available as a request in `obis.protocol`, and raw commands can be sent:

```python
from obis import protocol

laser.execute(protocol.get_wavelength())
laser.query("SYST:INF:FVER?")  # -> ["V3.0.5"]
```

## Command line

```sh
obis-laser list                  # find devices
obis-laser info COM3             # static information
obis-laser state COM3 --channel 1
obis-laser power COM3 0.02
obis-laser on COM3
obis-laser off COM3
```

## Online control

- Each call is a single request/reply exchange (a few milliseconds at 115200 baud).
  `get_info()` and `get_state()` combine several exchanges; for fast loops, call the
  specific getters you need, e.g. `get_power()` or `get_status()`.
- Connections are thread-safe: exchanges are serialized with a lock. The async client
  runs them on a single worker thread, in the order they are awaited.
- Device errors raise `ObisDeviceError` (with `code` and `description`), missing replies
  raise `ObisTimeoutError`. All exceptions derive from `ObisError`.
- On connection, the client enables message handshaking (`OK`/`ERR` replies) if it is off.
  This setting is stored in the laser.

## Development

```sh
uv sync
uv run pytest
uv run ruff check && uv run ruff format --check
uv run pyright
```

Tests use a simulated device and need no hardware.

### Testing with a real laser

`tests/test_hardware.py` runs against a real device. It is skipped unless `OBIS_PORT`
is set, and always skipped in CI (when `CI` is set). Only settings that are restored to
their original value are written.

```powershell
$env:OBIS_PORT = "COM3"
$env:OBIS_CHANNEL = "0"           # optional: laser behind an OBIS Remote / LaserBox
$env:OBIS_TEST_EMISSION = "1"     # optional: also turn emission ON (5 % of max power)
uv run pytest tests/test_hardware.py -v -s
```

Block the beam before enabling `OBIS_TEST_EMISSION`.

## Releasing

The package version comes from the release tag (with [setuptools-scm](https://setuptools-scm.readthedocs.io)).
To publish version `0.1.0`, create a GitHub release with the tag `v0.1.0`. The `obis-laser`
workflow then runs the tests, builds the distributions with that version, attaches them to
the release and publishes them to PyPI.

One-time setup:

1. Create a GitHub environment named `pypi` (Settings > Environments).
2. On PyPI, add a [trusted publisher](https://docs.pypi.org/trusted-publishers/) for the
   `obis-laser` project: this repository, workflow `obis-laser.yml`, environment `pypi`.

Local builds without a tag get a development version (e.g. `0.0.1.dev0+...`).

## License

MIT
