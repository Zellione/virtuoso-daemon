import pytest

from virtuoso_daemon.protocol import (
    CMD_GET,
    CMD_SET,
    EP_HEADSET,
    EP_RECEIVER,
    DeviceState,
    ProtocolError,
    build_packet,
)


def test_firmware_request():
    packet = build_packet(
        EP_RECEIVER,
        CMD_SET,
        [0x13],
    )

    assert len(packet) == 65
    assert packet[:5] == bytes([
        0x00, 0x02, 0x08, 0x02, 0x13
    ])
    assert packet[5:] == bytes(60)


def test_software_mode_packet():
    packet = build_packet(
        EP_HEADSET,
        CMD_GET,
        [0x03, 0x00, 0x02],
    )

    assert packet[:7] == bytes([
        0x00, 0x02, 0x09, 0x01,
        0x03, 0x00, 0x02,
    ])


def test_firmware_mode_packet():
    packet = build_packet(
        EP_HEADSET,
        CMD_GET,
        [0x03, 0x00, 0x01],
    )

    assert packet[4:7] == bytes([
        0x03, 0x00, 0x01
    ])


def test_invalid_endpoint():
    with pytest.raises(ProtocolError):
        build_packet(0xFF, CMD_SET, [])


def test_invalid_command():
    with pytest.raises(ProtocolError):
        build_packet(EP_HEADSET, 0xFF, [])


def test_payload_size():
    with pytest.raises(ProtocolError):
        build_packet(
            EP_HEADSET,
            CMD_SET,
            bytes(62),
        )


def test_max_payload():
    packet = build_packet(
        EP_HEADSET,
        CMD_SET,
        bytes(61),
    )

    assert len(packet) == 65


def test_device_states():
    assert DeviceState.CONNECTED != DeviceState.SOFTWARE_MODE
    assert DeviceState.RECOVERY_REQUIRED != DeviceState.DISCONNECTED
