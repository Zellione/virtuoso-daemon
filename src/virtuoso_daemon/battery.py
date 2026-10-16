"""Battery queries for Corsair Virtuoso Wireless.

Protocol behavior based on VirtuosoControl by Alejandro Socas
(MIT License).

Requires an already established software-mode session.
"""

import time

from .protocol import CMD_SET, EP_HEADSET, build_packet


class BatteryError(RuntimeError):
    """Battery query failed."""


def read_battery(handle, *, attempts=3):
    """Read battery percentage over an existing HID connection.

    Does not enter or leave software mode.
    """

    valid = []

    for _ in range(attempts):
        # Drain stale responses before requesting a new reading.
        for _ in range(20):
            packet = handle.read(64)
            if not packet:
                break

        request = build_packet(
            EP_HEADSET,
            CMD_SET,
            [0x0F],
        )

        written = handle.write(request)

        if written != len(request):
            raise BatteryError("Battery request write failed")

        for _ in range(5):
            time.sleep(0.05)
            response = handle.read(64)

            if not response or len(response) < 6:
                continue

            raw = (response[5] << 8) | response[4]

            # Firmware reports battery level in tenths
            # of a percent. Reject empty or stale values.
            if not 1 <= raw <= 1000:
                continue

            valid.append(raw // 10)
            break

    if not valid:
        raise BatteryError("No valid battery response")

    return valid[-1]
