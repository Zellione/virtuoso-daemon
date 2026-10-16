from unittest.mock import MagicMock, patch

import pytest

from virtuoso_daemon.battery import BatteryError, read_battery
from virtuoso_daemon.transport import (
    ReportKind,
    classify_report,
)


def battery_response(raw):
    return [
        0x01, 0x01, 0x02, 0x00,
        raw & 0xFF,
        (raw >> 8) & 0xFF,
    ]


def make_handle(raw):
    handle = MagicMock()
    handle.write.return_value = 65
    handle.read.side_effect = [
        [],
        battery_response(raw),
    ] * 3
    return handle


@patch("virtuoso_daemon.battery.time.sleep")
def test_battery_percentage(_sleep):
    handle = make_handle(735)
    assert read_battery(handle) == 73


@patch("virtuoso_daemon.battery.time.sleep")
def test_full_battery(_sleep):
    handle = make_handle(1000)
    assert read_battery(handle) == 100


@patch("virtuoso_daemon.battery.time.sleep")
def test_invalid_response(_sleep):
    handle = MagicMock()
    handle.write.return_value = 65
    handle.read.return_value = []

    with pytest.raises(BatteryError):
        read_battery(handle)


def test_short_write():
    handle = MagicMock()
    handle.read.return_value = []
    handle.write.return_value = 10

    with pytest.raises(BatteryError, match="write failed"):
        read_battery(handle)


import pytest

from virtuoso_daemon.battery import parse_battery_response


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (bytes([0x01, 0, 0, 0, 0xF8, 0x02]), 76),
        (bytes([0x01, 0, 0, 0, 0xE8, 0x03]), 100),
        (bytes([0x01, 0, 0, 0, 0, 0]), None),
        (bytes([0x01, 0, 0, 0, 0xE9, 0x03]), None),
        (bytes([0x03, 1, 1, 0x0F, 0xF8, 0x02]), None),
        (bytes([0x01, 0, 0]), None),
        (b"", None),
    ],
)
def test_parse_battery_response(response, expected):
    assert parse_battery_response(response) == expected


from virtuoso_daemon.battery import read_battery_with_transport
from virtuoso_daemon.transport import HidTransport


def full_report(*values):
    return list(bytes(values).ljust(64, b"\x00"))


def test_transport_battery_preserves_mic_reports():
    handle = MagicMock()
    handle.write.return_value = 65
    handle.read.side_effect = [
        [],
        full_report(0x03, 0x01, 0x02, 0x01),
        full_report(0x01, 0x01, 0x02, 0, 0xF8, 0x02),
        [],
    ]

    transport = HidTransport(handle)

    level = read_battery_with_transport(
        transport,
        attempts=1,
        wait=lambda _: None,
    )

    assert level == 76
    assert any(
        report.kind == ReportKind.MIC_BUTTON
        for report in transport.pending
    )


def test_transport_battery_ignores_old_pending_reply():
    handle = MagicMock()
    handle.write.return_value = 65
    handle.read.return_value = []

    transport = HidTransport(handle)
    transport.pending.append(
        classify_report(
            full_report(0x01, 0x01, 0x02, 0, 0xE8, 0x03)
        )
    )

    with pytest.raises(BatteryError):
        read_battery_with_transport(
            transport,
            attempts=1,
            wait=lambda _: None,
        )


def test_transport_battery_does_not_reuse_old_reply():
    handle = MagicMock()
    handle.write.return_value = 65
    handle.read.side_effect = [
        [],
        full_report(0x01, 0x01, 0x02, 0, 0xF8, 0x02),
        [],
    ]

    transport = HidTransport(handle)

    first = read_battery_with_transport(
        transport,
        attempts=1,
        wait=lambda _: None,
    )

    assert first == 76

    handle.read.return_value = []
    handle.read.side_effect = None

    with pytest.raises(BatteryError):
        read_battery_with_transport(
            transport,
            attempts=1,
            wait=lambda _: None,
        )


def test_transport_battery_consumes_completed_replies():
    handle = MagicMock()
    handle.write.return_value = 65
    handle.read.side_effect = [
        [],
        full_report(0x01, 0x01, 0x02, 0, 0xF8, 0x02),
        [],
    ]

    transport = HidTransport(handle)

    assert read_battery_with_transport(
        transport,
        attempts=1,
        wait=lambda _: None,
    ) == 76

    assert transport.pending_count == 0
