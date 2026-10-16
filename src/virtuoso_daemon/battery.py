"""Battery queries for Corsair Virtuoso Wireless.

Protocol behavior based on VirtuosoControl by Alejandro Socas
(MIT License).

Requires an already established software-mode session.
"""

import time

from .protocol import CMD_SET, EP_HEADSET, build_packet
from .transport import HidTransport, ReportKind


class BatteryError(RuntimeError):
    """Battery query failed."""


def parse_battery_response(response) -> int | None:
    """Parse a battery query reply.

    Returns a percentage or None for unsupported or invalid data.
    """
    if not response or len(response) < 6:
        return None

    # V2W query replies use report type 0x01.
    # Asynchronous notifications use a different structure.
    if response[0] != 0x01:
        return None

    raw = (response[5] << 8) | response[4]

    if not 1 <= raw <= 1000:
        return None

    return raw // 10


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

            level = parse_battery_response(response)

            if level is None:
                continue

            valid.append(level)
            break

    if not valid:
        raise BatteryError("No valid battery response")

    return valid[-1]


def read_battery_with_transport(
    transport: HidTransport,
    *,
    attempts: int = 3,
    wait=time.sleep,
) -> int:
    """Read battery while preserving unrelated HID reports.

    A reply is eligible only if received after the current
    request boundary. This cannot identify delayed replies
    from an earlier request without a protocol request ID.
    """
    if attempts < 1:
        raise ValueError("attempts must be positive")

    request = build_packet(EP_HEADSET, CMD_SET, [0x0F])

    for _ in range(attempts):
        transport.poll()
        boundary = transport.last_sequence

        written = transport.handle.write(request)

        if written != len(request):
            raise BatteryError("Battery request write failed")

        for _ in range(5):
            wait(0.05)
            transport.poll()

            for report in tuple(transport.pending):
                if report.sequence <= boundary:
                    continue

                if report.kind != ReportKind.QUERY_REPLY:
                    continue

                level = parse_battery_response(report.data)

                if level is None:
                    continue

                transport.pending.remove(report)
                return level

    raise BatteryError("No valid battery response")
