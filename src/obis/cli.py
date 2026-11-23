"""Quick checks of OBIS lasers from the command line."""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Sequence

from .discovery import discover
from .errors import ObisError
from .laser import ObisLaser


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="obis-laser", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    list_command = commands.add_parser("list", help="find OBIS devices by probing serial ports")
    list_command.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PORT",
        help="port not to probe (can be repeated), e.g. --exclude COM1 --exclude COM11",
    )

    def add_laser_command(name: str, help: str) -> argparse.ArgumentParser:
        command = commands.add_parser(name, help=help)
        command.add_argument("port", help="serial port, e.g. COM3 or /dev/ttyACM0")
        command.add_argument("--channel", type=int, default=0, help="laser behind a controller")
        return command

    add_laser_command("info", "print static laser information")
    add_laser_command("state", "print the current laser state")
    add_laser_command("on", "turn emission on")
    add_laser_command("off", "turn emission off")
    power = add_laser_command("power", "set the output power")
    power.add_argument("watts", type=float, help="output power in watts")

    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            return _list(args.exclude)
        with ObisLaser.open(args.port, channel=args.channel) as laser:
            if args.command == "info":
                _print(dataclasses.asdict(laser.get_info()))
            elif args.command == "state":
                _print(dataclasses.asdict(laser.get_state()))
            elif args.command in ("on", "off"):
                laser.set_emission(args.command == "on")
            elif args.command == "power":
                laser.set_power(args.watts)
    except ObisError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def _list(exclude: list[str]) -> int:
    devices = discover(exclude=exclude)
    if not devices:
        print("no OBIS device found")
        return 1
    for device in devices:
        print(
            f"{device.port}  channel {device.channel}  {device.device_type.value:<6}"
            f"  {device.model}  (S/N {device.serial_number})"
        )
    return 0


def _print(values: dict[str, object]) -> None:
    width = max(len(name) for name in values)
    for name, value in values.items():
        print(f"{name:<{width}}  {value}")


if __name__ == "__main__":
    sys.exit(main())
