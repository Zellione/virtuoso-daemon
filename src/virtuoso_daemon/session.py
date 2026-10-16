"""Software-mode session management for Corsair Virtuoso.

Protocol sequence derived from VirtuosoControl by Alejandro Socas,
licensed under MIT.

A successful HID write is not proof of firmware state.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from .protocol import (
    CMD_GET,
    CMD_SET,
    EP_HEADSET,
    EP_RECEIVER,
    DeviceState,
)

from .recovery import RecoveryStore


class SessionError(RuntimeError):
    """A software-mode transition failed."""


@dataclass
class SoftwareSession:
    send: Callable[[int, int, list[int]], bool]
    pause: Callable[[float], None]
    recovery: RecoveryStore

    state: DeviceState = field(
        default=DeviceState.CONNECTED,
        init=False,
    )

    flush: Callable[[], None] = lambda: None

    def __post_init__(self) -> None:
        marker = self.recovery.read()

        if marker is not None:
            self.state = DeviceState.RECOVERY_REQUIRED

    def _command(
        self,
        endpoint: int,
        command: int,
        payload: list[int],
    ) -> None:
        if not self.send(endpoint, command, payload):
            raise SessionError("HID command failed")

    def enter(self) -> None:
        if self.state != DeviceState.CONNECTED:
            raise SessionError(
                f"Cannot enter from {self.state.name}"
            )

        # Persist recovery intent before any device write.
        self.recovery.mark_required()
        self.state = DeviceState.RECOVERY_REQUIRED

        try:
            self._command(
                EP_RECEIVER, CMD_SET, [0x13]
            )
            self._command(
                EP_RECEIVER, CMD_SET, [0x12]
            )
            self._command(
                EP_HEADSET,
                CMD_GET,
                [0x03, 0x00, 0x02],
            )
            self.flush()
            self._command(
                EP_HEADSET, CMD_SET, [0x12]
            )
        except Exception as exc:
            raise SessionError(
                "Software-mode entry incomplete; "
                "recovery required"
            ) from exc

        # Requested, not independently firmware-verified.
        self.state = DeviceState.SOFTWARE_MODE

    def leave(self) -> None:
        if self.state == DeviceState.CONNECTED:
            return

        if self.state not in (
            DeviceState.SOFTWARE_MODE,
            DeviceState.RECOVERY_REQUIRED,
        ):
            raise SessionError(
                f"Cannot leave from {self.state.name}"
            )

        self.recovery.mark_required()
        self.state = DeviceState.RECOVERY_REQUIRED

        try:
            # Attempt both recovery commands, even when
            # the first command reports failure.
            results = []

            for endpoint in (EP_RECEIVER, EP_HEADSET):
                try:
                    results.append(
                        self.send(
                            endpoint,
                            CMD_GET,
                            [0x03, 0x00, 0x01],
                        )
                    )
                except Exception:
                    results.append(False)

                self.pause(0.05)

            if not all(results):
                raise SessionError(
                    "One or more recovery writes failed"
                )

        except Exception as exc:
            raise SessionError(
                "Firmware-mode restoration not confirmed"
            ) from exc

        # Writes succeeded, but the actual firmware mode
        # has not been independently verified.
        self.recovery.mark_restore_sent()
        self.state = DeviceState.RECOVERY_REQUIRED
