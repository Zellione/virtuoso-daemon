import pytest

from virtuoso_daemon.led import (
    LedError,
    LedZone,
    build_led_init_packet,
    build_led_rgb_packet,
)


def test_led_init_packet():
    packet = build_led_init_packet()

    assert len(packet) == 65
    assert packet[:6] == bytes(
        (0x00, 0x02, 0x09, 0x0D, 0x00, 0x01)
    )


def test_led_rgb_packet_layout():
    packet = build_led_rgb_packet(
        logo=LedZone(10, 20, 30),
        battery=LedZone(40, 50, 60),
        microphone=LedZone(70, 80, 90),
    )

    assert len(packet) == 65
    assert packet[:9] == bytes(
        (0x00, 0x02, 0x09, 0x06, 0, 9, 0, 0, 0)
    )
    assert packet[9:18] == bytes(
        (10, 40, 70, 20, 50, 80, 30, 60, 90)
    )
    assert packet[18:] == bytes(47)


def test_led_off():
    zone = LedZone(255, 255, 255, brightness=0)
    assert zone.scaled() == (0, 0, 0)


def test_brightness_scaling():
    zone = LedZone(200, 100, 40, brightness=50)
    assert zone.scaled() == (50, 25, 10)


@pytest.mark.parametrize(
    "zone",
    [
        LedZone(-1, 0, 0),
        LedZone(256, 0, 0),
        LedZone(0, 0, 0, brightness=-1),
        LedZone(0, 0, 0, brightness=101),
    ],
)
def test_invalid_led_values(zone):
    with pytest.raises(LedError):
        zone.scaled()


from virtuoso_daemon.led import probe_led_endpoint


class FakeHid:
    def __init__(self, written=None):
        self.packets = []
        self.written = written

    def write(self, packet):
        self.packets.append(packet)
        return len(packet) if self.written is None else self.written


def test_led_probe_sends_only_initialization():
    device = FakeHid()

    probe_led_endpoint(device)

    assert device.packets == [build_led_init_packet()]
    assert len(device.packets[0]) == 65


def test_led_probe_rejects_short_write():
    device = FakeHid(written=12)

    with pytest.raises(RuntimeError, match="LED initialization"):
        probe_led_endpoint(device)

    assert len(device.packets) == 1


from virtuoso_daemon.led import send_logo_off


def test_logo_off_sends_expected_packets():
    device = FakeHid()

    send_logo_off(device)

    assert len(device.packets) == 2
    assert device.packets[0] == build_led_init_packet()
    assert device.packets[1] == build_led_rgb_packet(
        logo=LedZone(0, 0, 0),
        battery=LedZone(0, 0, 0),
        microphone=LedZone(255, 0, 0),
    )


def test_logo_off_stops_after_failed_initialization():
    device = FakeHid(written=12)

    with pytest.raises(RuntimeError, match="LED write failed"):
        send_logo_off(device)

    assert device.packets == [build_led_init_packet()]
