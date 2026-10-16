"""Virtuoso diagnostics and controlled battery queries."""

import argparse
import signal
import sys
import time

from .battery import read_battery
from .device import VirtuosoDevice
from .led import probe_led_endpoint, send_logo_off
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


def battery_direct():
    """Experimental battery query without entering software mode."""
    store = RecoveryStore.default()

    with ControllerLock():
        marker_before = store.read()

        if marker_before is not None:
            print(f"Existing recovery marker: {marker_before}")

        with VirtuosoDevice() as device:
            print(f"HID interface: {device.interface}", flush=True)
            level = read_battery(device.device)

        marker_after = store.read()

        if marker_after != marker_before:
            raise RuntimeError(
                "Recovery marker changed unexpectedly"
            )

        print(f"Battery: {level}%")
        print(f"Recovery marker: {marker_after or 'none'}")
        print("Firmware mode not independently verified")


def _terminate(_signum, _frame):
    raise KeyboardInterrupt("Interrupted by termination signal")


def led_probe():
    store = RecoveryStore.default()

    with ControllerLock():
        marker = store.read()

        if marker is not None:
            print(f"Existing recovery marker: {marker}")
            print("No software-mode transition will be attempted")

        with VirtuosoDevice() as device:
            print(f"Connected via HID interface {device.interface}")
            probe_led_endpoint(device.device)

        print("LED initialization report sent")
        print("Firmware mode and LED state not verified")


def led_test():
    store = RecoveryStore.default()

    with ControllerLock():
        marker = store.read()

        if marker:
            print(f"Recovery marker: {marker}")

        with VirtuosoDevice() as device:
            print(f"HID interface: {device.interface}")
            send_logo_off(device.device)

        print("RGB commands sent; firmware state unverified")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "command",
        choices=[
            "status",
            "probe",
            "recover",
            "battery",
            "battery-direct",
            "led-probe",
            "led-test",
        ],
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
        elif args.command == "led-probe":
            led_probe()
        elif args.command == "led-test":
            led_test()
        elif args.command == "battery-direct":
            battery_direct()

    except BaseException as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _terminate)
    sys.exit(main())
