"""Charging status queries for Corsair Virtuoso.

Protocol based on VirtuosoControl by Alejandro Socas (MIT).
Does not activate headset software mode.
"""

import time

from .protocol import CMD_SET, EP_HEADSET, build_packet
from .transport import HidTransport, ReportKind


class ChargingError(RuntimeError):
    """Charging query failed."""


def parse_charging_response(response) -> bool | None:
    """Return True=charging, False=discharging, None=unknown."""
    if not response or len(response) < 6:
        return None

    if response[0] != 0x01:
        return None

    raw = response[4] | (response[5] << 8)

    if raw == 1:
        return True
    if raw == 2:
        return False

    return None


def read_charging_with_transport(
    transport: HidTransport,
    *,
    attempts: int = 3,
    wait=time.sleep,
) -> bool | None:
    """Query charging state without discarding other HID events."""
    if attempts < 1:
        raise ValueError("attempts must be positive")

    request = build_packet(EP_HEADSET, CMD_SET, [0x10])

    for _ in range(attempts):
        transport.poll()
        boundary = transport.last_sequence

        written = transport.handle.write(request)
        if written != len(request):
            raise ChargingError("Charging request write failed")

        for _ in range(8):
            wait(0.05)
            transport.poll()

            for report in tuple(transport.pending):
                if report.sequence <= boundary:
                    continue
                if report.kind != ReportKind.QUERY_REPLY:
                    continue

                state = parse_charging_response(report.data)
                if state is None:
                    continue

                transport.pending.remove(report)
                return state

    return None
