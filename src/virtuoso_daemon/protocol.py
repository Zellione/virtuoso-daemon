"""Corsair Virtuoso V2W protocol primitives.

Protocol information based on VirtuosoControl
by Alejandro Socas (MIT License).

This module only constructs and validates packets.
It performs no hardware I/O.
"""

from enum import Enum, auto


REPORT_SIZE = 65
REPORT_ID = 0x00
V2W_MARKER = 0x02

EP_RECEIVER = 0x08
EP_HEADSET = 0x09

CMD_GET = 0x01
CMD_SET = 0x02


class DeviceState(Enum):
    DISCONNECTED = auto()
    CONNECTED = auto()
    SOFTWARE_MODE = auto()
    RECOVERY_REQUIRED = auto()


class ProtocolError(Exception):
    """Invalid protocol operation or packet."""


def build_packet(
    endpoint: int,
    command: int,
    payload: bytes | list[int],
) -> bytes:
    """Construct a 65-byte HID output report."""

    if endpoint not in (EP_RECEIVER, EP_HEADSET):
        raise ProtocolError(
            f"Invalid endpoint: {endpoint:#x}"
        )

    if command not in (CMD_GET, CMD_SET):
        raise ProtocolError(
            f"Invalid command: {command:#x}"
        )

    payload = bytes(payload)

    header = bytes((
        REPORT_ID,
        V2W_MARKER,
        endpoint,
        command,
    ))

    packet = header + payload

    if len(packet) > REPORT_SIZE:
        raise ProtocolError(
            f"Packet too large: {len(packet)} bytes"
        )

    return packet.ljust(REPORT_SIZE, b"\x00")
