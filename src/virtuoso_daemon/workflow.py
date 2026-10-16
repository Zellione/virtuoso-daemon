"""One-shot battery workflow with mandatory recovery attempt.

Hardware-independent orchestration.
No direct HID communication occurs in this module.
"""

from collections.abc import Callable
from typing import TypeVar

from .protocol import DeviceState
from .session import SoftwareSession


T = TypeVar("T")


def run_battery_workflow(
    session: SoftwareSession,
    read_battery: Callable[[], T],
) -> T:
    """Enter software mode, read battery, attempt restoration.

    A successful return does not prove firmware-mode restoration.
    The persistent recovery marker remains until independently cleared.
    """

    result = None
    operation_error = None

    try:
        session.enter()
        result = read_battery()
    except BaseException as exc:
        operation_error = exc

    recovery_error = None

    if session.state in (
        DeviceState.SOFTWARE_MODE,
        DeviceState.RECOVERY_REQUIRED,
    ):
        try:
            session.leave()
        except BaseException as exc:
            recovery_error = exc

    if operation_error is not None and recovery_error is not None:
        raise BaseExceptionGroup(
            "Battery operation and recovery both failed",
            [operation_error, recovery_error],
        )

    if recovery_error is not None:
        raise recovery_error

    if operation_error is not None:
        raise operation_error

    return result
