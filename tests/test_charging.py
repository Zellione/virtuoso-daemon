from unittest.mock import MagicMock

import pytest

from virtuoso_daemon.charging import (
    ChargingError,
    parse_charging_response,
    read_charging_with_transport,
)
from virtuoso_daemon.transport import HidTransport, ReportKind


def report(*values):
    return bytes(values).ljust(64, b"\x00")


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (report(1, 1, 2, 0, 1, 0), True),
        (report(1, 1, 2, 0, 2, 0), False),
        (report(1, 1, 2, 0, 0, 0), None),
        (report(1, 1, 2, 0, 3, 0), None),
        (report(3, 1, 1, 0x10, 1, 0), None),
        (b"", None),
    ],
)
def test_parse_charging_response(data, expected):
    assert parse_charging_response(data) is expected


def test_charging_query_preserves_other_reports():
    handle = MagicMock()
    handle.write.return_value = 65
    handle.read.side_effect = [
        [],
        report(3, 1, 2, 1),
        report(1, 1, 2, 0, 1, 0),
        [],
    ]

    transport = HidTransport(handle)

    assert read_charging_with_transport(
        transport, attempts=1, wait=lambda _: None
    ) is True

    assert transport.pending_count == 1
    assert transport.pending[0].kind == ReportKind.MIC_BUTTON


def test_charging_unknown_without_response():
    handle = MagicMock()
    handle.write.return_value = 65
    handle.read.return_value = []

    transport = HidTransport(handle)

    assert read_charging_with_transport(
        transport, attempts=1, wait=lambda _: None
    ) is None


def test_charging_short_write():
    handle = MagicMock()
    handle.read.return_value = []
    handle.write.return_value = 12

    with pytest.raises(ChargingError, match="write failed"):
        read_charging_with_transport(
            HidTransport(handle),
            attempts=1,
            wait=lambda _: None,
        )


def test_old_charging_reply_is_not_reused():
    handle = MagicMock()
    handle.write.return_value = 65
    handle.read.return_value = []

    transport = HidTransport(handle)
    transport.poll(max_reads=0)

    from virtuoso_daemon.transport import classify_report
    transport.pending.append(
        classify_report(report(1, 1, 2, 0, 1, 0))
    )

    assert read_charging_with_transport(
        transport, attempts=1, wait=lambda _: None
    ) is None
