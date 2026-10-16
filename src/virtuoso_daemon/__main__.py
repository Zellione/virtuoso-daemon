"""Virtuoso diagnostics and controlled battery queries."""

import argparse
import signal
import sys
import time

from .battery import read_battery
from .device import VirtuosoDevice
from .locking import ControllerLock
from .protocol import build_packet
from .recovery import RecoveryStore
from .session import SoftwareSession
from .workflow import run_battery_workflow


def send_command(device, endpoint, command, payload):
    packet = build_packet(endpoint, command, payload)
    return device.device.write(packet) == len(packet)


def flush_input(device):
    for _ in range(20):
        response = device.device.read(64)
        if not response:
            break


def make_session(device, store):
    return SoftwareSession(
        send=lambda endpoint, command, payload: send_command(
            device, endpoint, command, payload
        ),
        pause=time.sleep,
        recovery=store,
        flush=lambda: flush_input(device),
    )


def status():
    marker = RecoveryStore.default().read()
    print(f"Recovery: {marker or 'none'}")


def probe():
    with ControllerLock():
        with VirtuosoDevice() as device:
            print(f"Connected: {device.connected}")
            print(f"Interface: {device.interface}")
            print(f"State: {device.state.name}")


def recover():
    store = RecoveryStore.default()

    with ControllerLock():
        marker = store.read()

        if marker is None:
            print("No recovery marker; no commands sent")
            return

        print(f"Recovery marker: {marker}")

        with VirtuosoDevice() as device:
            session = make_session(device, store)
            session.leave()

        print("Restore commands sent")
        print("Firmware state is not independently verified")
        print(f"Recovery marker: {store.read()}")


def battery():
    store = RecoveryStore.default()

    with ControllerLock():
        marker = store.read()

        if marker is not None:
            raise RuntimeError(
                f"Existing recovery marker: {marker}. "
                "Resolve recovery before another battery query."
            )

        with VirtuosoDevice() as device:
            print(
                f"Connected via HID interface {device.interface}",
                flush=True,
            )

            session = make_session(device, store)

            level = run_battery_workflow(
                session,
                lambda: read_battery(device.device),
            )

        print(f"Battery: {level}%")
        print(f"Recovery marker: {store.read()}")
        print("Restore commands sent; firmware mode unverified")


def _terminate(_signum, _frame):
    raise KeyboardInterrupt("Interrupted by termination signal")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "command",
        choices=["status", "probe", "recover", "battery"],
    )

    args = parser.parse_args()

    try:
        if args.command == "status":
            status()
        elif args.command == "probe":
            probe()
        elif args.command == "recover":
            recover()
        elif args.command == "battery":
            battery()

    except BaseException as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _terminate)
    sys.exit(main())
