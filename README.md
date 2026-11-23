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

for device in obis.discover(exclude=["COM1"]):
    print(device.port, device.channel, device.model, device.serial_number)
```

OBIS lasers and controllers connected over USB are recognized by Coherent's USB vendor ID
(`0x0D4D`) without opening any port: `obis.candidate_ports()` lists them. `discover()` probes
these ports, or every serial port if there are none, for example when the laser is connected
over RS-232 through a USB adapter.

Probing sends `*IDN?` to each port, so it may disturb other serial devices (it does not change
any setting on them). Pass `ports=[...]` to choose the ports to probe, `all_ports=True` to probe
every serial port, or `exclude=[...]` to skip ports.

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
obis-laser list --all-ports      # ... probing every serial port, not only Coherent USB ports
obis-laser list --exclude COM1   # ... without probing COM1
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

## License

MIT
