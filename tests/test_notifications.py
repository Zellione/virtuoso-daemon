import pytest
from virtuoso_daemon.notifications import BatteryNotifier


def test_warn_once_and_escalate(tmp_path):
    sent = []
    notifier = BatteryNotifier(
        path=tmp_path / "state.json",
        send=lambda level, urgency: sent.append((level, urgency)),
    )

    for level in (80, 20, 19, 15, 10, 9):
        notifier.update(level)

    assert sent == [(20, "normal"), (10, "critical")]


def test_restart_does_not_duplicate(tmp_path):
    path = tmp_path / "state.json"
    sent = []

    first = BatteryNotifier(
        path=path,
        send=lambda level, urgency: sent.append((level, urgency)),
    )
    first.update(18)

    second = BatteryNotifier(
        path=path,
        send=lambda level, urgency: sent.append((level, urgency)),
    )
    second.update(17)

    assert sent == [(18, "normal")]


def test_warning_resets_after_charging(tmp_path):
    sent = []
    notifier = BatteryNotifier(
        path=tmp_path / "state.json",
        send=lambda level, urgency: sent.append((level, urgency)),
    )

    for level in (20, 21, 24, 26, 20):
        notifier.update(level)

    assert sent == [(20, "normal"), (20, "normal")]


def test_critical_can_be_first_warning(tmp_path):
    sent = []
    notifier = BatteryNotifier(
        path=tmp_path / "state.json",
        send=lambda level, urgency: sent.append((level, urgency)),
    )

    notifier.update(8)
    notifier.update(7)

    assert sent == [(8, "critical")]


def test_failed_notification_does_not_advance_state(tmp_path):
    path = tmp_path / "state.json"

    def fail(*args):
        raise RuntimeError("Notification unavailable")

    with pytest.raises(RuntimeError, match="Notification unavailable"):
        BatteryNotifier(path=path, send=fail).update(20)

    assert not path.exists()

    sent = []
    notifier = BatteryNotifier(
        path=path,
        send=lambda level, urgency: sent.append((level, urgency)),
    )

    assert notifier.update(20) is True
    assert sent == [(20, "normal")]


import pytest


@pytest.mark.parametrize(
    ("level", "charging", "expected"),
    [
        (20, False, False),
        (16, False, False),
        (15, False, True),
        (10, False, True),
        (5, False, True),
        (15, True, False),
        (15, None, False),
        (10, True, False),
        (10, None, False),
    ],
)
def test_repeating_battery_warning(
    tmp_path, level, charging, expected
):
    sent = []

    notifier = BatteryNotifier(
        path=tmp_path / "notifications.json",
        send=lambda value, urgency: sent.append(
            (value, urgency)
        ),
    )

    result = notifier.remind(level, charging)

    assert result is expected
    assert bool(sent) is expected

    if expected:
        assert sent == [
            (
                level,
                "critical" if level <= 10 else "normal",
            )
        ]
