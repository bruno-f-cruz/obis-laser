"""Print laser information, then emit at 10% of the maximum power for two seconds.

Usage: uv run examples/basic.py COM3
"""

import sys
import time

from obis import ObisLaser, OperatingMode

with ObisLaser.open(sys.argv[1]) as laser:
    info = laser.get_info()
    print(f"{info.model} (S/N {info.serial_number}), {info.wavelength:g} nm")

    laser.set_operating_mode(OperatingMode.CWP)
    laser.set_power(0.1 * info.max_power)
    laser.set_emission(True)
    try:
        time.sleep(2)
        print(laser.get_state())
    finally:
        laser.set_emission(False)
