"""HID report classification and buffering.

Based on VirtuosoControl by Alejandro Socas (MIT License).

This module does not open devices, write HID commands,
or change firmware modes.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto


class ReportKind(Enum):
    QUERY_REPLY = auto()
    MIC_BUTTON = auto()
    NOTIFICATION = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class HidReport:
    kind: ReportKind
    data: bytes


def classify_report(data: bytes | list[int]) -> HidReport:
    """Classify one incoming 64-byte HID input report."""
    data = bytes(data)

    if len(data) != 64:
        return HidReport(ReportKind.UNKNOWN, data)

    # Physical microphone button notification.
    if data[:3] == b"\x03\x01\x02":
        return HidReport(ReportKind.MIC_BUTTON, data)

    # Other asynchronous headset notifications.
    if data[:3] == b"\x03\x01\x01":
        return HidReport(ReportKind.NOTIFICATION, data)

    # Query response. This does not prove which query
    # produced the response.
    if data[0] == 0x01:
        return HidReport(ReportKind.QUERY_REPLY, data)

    return HidReport(ReportKind.UNKNOWN, data)


class HidTransport:
    """Read and buffer reports without silently discarding them."""

    def __init__(self, handle, *, max_pending=256):
        if max_pending < 1:
            raise ValueError("max_pending must be positive")

        self.handle = handle
        self.max_pending = max_pending
        self.pending = deque()

    def poll(self, *, max_reads=20) -> int:
        """Read available reports into the pending queue.

        Assumes the HID handle is in nonblocking mode.
        Stops rather than silently dropping buffered reports.
        """
        count = 0

        for _ in range(max_reads):
            if len(self.pending) >= self.max_pending:
                break

            data = self.handle.read(64)

            if not data:
                break

            self.pending.append(classify_report(data))
            count += 1

        return count

    def take(self, kind: ReportKind) -> HidReport | None:
        """Remove the oldest matching report, preserving others."""
        for report in self.pending:
            if report.kind == kind:
                self.pending.remove(report)
                return report

        return None

    def drain(self) -> list[HidReport]:
        """Return all buffered reports in arrival order."""
        reports = list(self.pending)
        self.pending.clear()
        return reports

    @property
    def pending_count(self) -> int:
        return len(self.pending)
