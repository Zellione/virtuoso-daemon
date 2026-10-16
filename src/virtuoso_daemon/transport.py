"""HID report classification and buffering.

Protocol based on VirtuosoControl by Alejandro Socas (MIT).
No hardware writes or firmware-mode transitions.
"""

from collections import deque
from dataclasses import dataclass, replace
from enum import Enum, auto


class ReportKind(Enum):
    QUERY_REPLY = auto()
    MIC_BUTTON = auto()
    NOTIFICATION = auto()
    UNKNOWN = auto()


class TransportOverflowError(RuntimeError):
    """Pending HID reports must be consumed before reading more."""


@dataclass(frozen=True)
class HidReport:
    kind: ReportKind
    data: bytes
    sequence: int = 0


def classify_report(data: bytes | list[int]) -> HidReport:
    data = bytes(data)

    if len(data) != 64:
        return HidReport(ReportKind.UNKNOWN, data)

    if data[:3] == b"\x03\x01\x02":
        return HidReport(ReportKind.MIC_BUTTON, data)

    if data[:3] == b"\x03\x01\x01":
        return HidReport(ReportKind.NOTIFICATION, data)

    if data[0] == 0x01:
        return HidReport(ReportKind.QUERY_REPLY, data)

    return HidReport(ReportKind.UNKNOWN, data)


class HidTransport:
    """Single-reader HID transport with monotonic report sequencing."""

    def __init__(self, handle, *, max_pending=256):
        if max_pending < 1:
            raise ValueError("max_pending must be positive")

        self.handle = handle
        self.max_pending = max_pending
        self.pending = deque()
        self._sequence = 0

    @property
    def last_sequence(self) -> int:
        return self._sequence

    @property
    def pending_count(self) -> int:
        return len(self.pending)

    def poll(self, *, max_reads=20) -> int:
        """Read nonblocking HID reports without dropping data."""
        if max_reads < 0:
            raise ValueError("max_reads must not be negative")

        count = 0

        for _ in range(max_reads):
            if self.pending_count >= self.max_pending:
                if count == 0:
                    raise TransportOverflowError(
                        "HID report buffer full; consumer must drain"
                    )
                break

            data = self.handle.read(64)

            if not data:
                break

            self._sequence += 1

            report = replace(
                classify_report(data),
                sequence=self._sequence,
            )

            self.pending.append(report)
            count += 1

        return count

    def take(self, kind: ReportKind) -> HidReport | None:
        for report in self.pending:
            if report.kind == kind:
                self.pending.remove(report)
                return report

        return None

    def take_after(
        self,
        kind: ReportKind,
        sequence: int,
    ) -> HidReport | None:
        """Consume the oldest matching report newer than sequence."""
        for report in self.pending:
            if report.sequence <= sequence:
                continue

            if report.kind == kind:
                self.pending.remove(report)
                return report

        return None

    def drain(self) -> list[HidReport]:
        reports = list(self.pending)
        self.pending.clear()
        return reports
