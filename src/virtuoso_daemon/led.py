"""Corsair Virtuoso LED packet construction.

Protocol derived from VirtuosoControl by Alejandro Socas (MIT).

Pure packet construction only:
- no HID access
- no software-mode transition
- no changes to microphone mute
"""

from dataclasses import dataclass

from .protocol import EP_HEADSET, REPORT_SIZE, V2W_MARKER


class LedError(ValueError):
    """Invalid LED configuration."""


@dataclass(frozen=True)
class LedZone:
    red: int
    green: int
    blue: int
    brightness: int = 100

    def scaled(self) -> tuple[int, int, int]:
        values = (self.red, self.green, self.blue)

        if any(
            not isinstance(v, int) or not 0 <= v <= 255
            for v in values
        ):
            raise LedError("RGB values must be integers 0..255")

        if (
            not isinstance(self.brightness, int)
            or not 0 <= self.brightness <= 100
        ):
            raise LedError("Brightness must be 0..100")

        scale = (self.brightness / 100.0) ** 2

        return tuple(int(v * scale) for v in values)


def _packet(opcode: int, payload: bytes) -> bytes:
    data = bytes((0x00, V2W_MARKER, EP_HEADSET, opcode))
    data += payload

    if len(data) > REPORT_SIZE:
        raise LedError("LED packet exceeds report size")

    return data.ljust(REPORT_SIZE, b"\x00")


def build_led_init_packet() -> bytes:
    """Initialize the headset LED endpoint."""
    return _packet(0x0D, bytes((0x00, 0x01)))


def build_led_rgb_packet(
    *,
    logo: LedZone,
    battery: LedZone,
    microphone: LedZone,
) -> bytes:
    """Set all three LED zones in a single V2W report.

    Zone order:
        0: Corsair logo
        1: Battery indicator
        2: Microphone LED

    Firmware data layout:
        R0 R1 R2 G0 G1 G2 B0 B1 B2
    """
    zones = (
        logo.scaled(),
        battery.scaled(),
        microphone.scaled(),
    )

    rgb = bytes(
        channel
        for color_index in range(3)
        for zone in zones
        for channel in (zone[color_index],)
    )

    payload = bytes((0x00, 0x09, 0x00, 0x00, 0x00)) + rgb

    return _packet(0x06, payload)
