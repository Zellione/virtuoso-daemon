from unittest.mock import MagicMock

from virtuoso_daemon.transport import (
    HidTransport,
    ReportKind,
    classify_report,
)


def packet(*values):
    return bytes(values).ljust(64, b"\x00")


def test_classify_query_reply():
    report = classify_report(packet(0x01, 0x01, 0x02))

    assert report.kind == ReportKind.QUERY_REPLY


def test_classify_mic_button():
    report = classify_report(packet(0x03, 0x01, 0x02, 0x01))

    assert report.kind == ReportKind.MIC_BUTTON


def test_classify_notification():
    report = classify_report(packet(0x03, 0x01, 0x01, 0x0F))

    assert report.kind == ReportKind.NOTIFICATION


def test_classify_unknown():
    report = classify_report(packet(0xFF))

    assert report.kind == ReportKind.UNKNOWN


def test_reject_short_report():
    report = classify_report([0x01, 0x01])

    assert report.kind == ReportKind.UNKNOWN


def test_preserve_unrelated_reports():
    handle = MagicMock()
    handle.read.side_effect = [
        packet(0x03, 0x01, 0x02, 0x01),
        packet(0x01, 0x01, 0x02),
        packet(0x03, 0x01, 0x01, 0x10),
        [],
    ]

    transport = HidTransport(handle)

    assert transport.poll() == 3

    reply = transport.take(ReportKind.QUERY_REPLY)

    assert reply is not None
    assert transport.pending_count == 2

    remaining = transport.drain()

    assert [item.kind for item in remaining] == [
        ReportKind.MIC_BUTTON,
        ReportKind.NOTIFICATION,
    ]


def test_preserve_arrival_order():
    handle = MagicMock()
    handle.read.side_effect = [
        packet(0x03, 0x01, 0x02, 0x01),
        packet(0x03, 0x01, 0x02, 0x00),
        [],
    ]

    transport = HidTransport(handle)
    transport.poll()

    reports = transport.drain()

    assert reports[0].data[3] == 1
    assert reports[1].data[3] == 0


def test_buffer_limit_does_not_discard():
    handle = MagicMock()
    handle.read.return_value = packet(0x01)

    transport = HidTransport(handle, max_pending=2)

    assert transport.poll(max_reads=10) == 2
    assert transport.pending_count == 2
    assert handle.read.call_count == 2


import pytest

from virtuoso_daemon.transport import TransportOverflowError


def test_monotonic_sequences():
    handle = MagicMock()
    handle.read.side_effect = [
        packet(0x03, 0x01, 0x02, 0x01),
        packet(0x01, 0x01, 0x02),
        [],
        packet(0x03, 0x01, 0x01, 0x10),
        [],
    ]

    transport = HidTransport(handle)

    assert transport.poll() == 2
    assert transport.last_sequence == 2

    first = transport.take(ReportKind.MIC_BUTTON)
    assert first.sequence == 1

    assert transport.poll() == 1
    assert transport.last_sequence == 3

    assert [r.sequence for r in transport.pending] == [2, 3]


def test_take_after_preserves_old_reports():
    handle = MagicMock()
    handle.read.side_effect = [
        packet(0x01, 0x01, 0x02),
        [],
        packet(0x01, 0x01, 0x02),
        [],
    ]

    transport = HidTransport(handle)

    transport.poll()
    boundary = transport.last_sequence
    transport.poll()

    new = transport.take_after(
        ReportKind.QUERY_REPLY,
        boundary,
    )

    assert new.sequence == 2
    assert [r.sequence for r in transport.pending] == [1]


def test_overflow_is_explicit():
    handle = MagicMock()
    handle.read.return_value = packet(0x03, 0x01, 0x02)

    transport = HidTransport(handle, max_pending=2)

    assert transport.poll(max_reads=2) == 2

    with pytest.raises(TransportOverflowError):
        transport.poll(max_reads=1)

    assert transport.pending_count == 2
    assert transport.last_sequence == 2

    assert len(transport.drain()) == 2
    assert transport.pending_count == 0
