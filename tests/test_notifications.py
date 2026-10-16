import pytest
from virtuoso_daemon.notifications import BatteryNotifier


def test_warn_once_and_escalate(tmp_path):
    now = [1000.0]
    sent = []

    notifier = BatteryNotifier(
        path=tmp_path / "state.json",
        clock=lambda: now[0],
        send=lambda level, urgency: sent.append(
            (level, urgency)
        ),
    )

    for level in (80, 20, 19, 15):
        notifier.update(level)

    now[0] += 60
    notifier.update(10)
    notifier.update(9)

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
    now = [1000.0]
    sent = []

    notifier = BatteryNotifier(
        path=tmp_path / "state.json",
        clock=lambda: now[0],
        send=lambda level, urgency: sent.append(
            (level, urgency)
        ),
    )

    for level in (20, 21, 24, 26):
        notifier.update(level)

    now[0] += 60
    notifier.update(20)

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


def test_threshold_and_reminder_share_cooldown(tmp_path):
    now = [1000.0]
    sent = []

    notifier = BatteryNotifier(
        path=tmp_path / "state.json",
        clock=lambda: now[0],
        send=lambda level, urgency: sent.append(
            (level, urgency)
        ),
    )

    assert notifier.update(15) is True
    assert notifier.remind(15, False) is False

    now[0] += 59
    assert notifier.remind(15, False) is False

    now[0] += 1
    assert notifier.remind(15, False) is True

    assert sent == [
        (15, "normal"),
        (15, "normal"),
    ]


def test_cooldown_survives_restart(tmp_path):
    now = [1000.0]
    sent = []
    path = tmp_path / "state.json"

    def make_notifier():
        return BatteryNotifier(
            path=path,
            clock=lambda: now[0],
            send=lambda level, urgency: sent.append(
                (level, urgency)
            ),
        )

    first = make_notifier()
    first.update(15)

    now[0] += 30
    second = make_notifier()

    assert second.remind(15, False) is False

    now[0] += 30
    assert second.remind(15, False) is True
    assert len(sent) == 2


def test_charging_does_not_send_reminder(tmp_path):
    now = [1000.0]
    sent = []

    notifier = BatteryNotifier(
        path=tmp_path / "state.json",
        clock=lambda: now[0],
        send=lambda level, urgency: sent.append(
            (level, urgency)
        ),
    )

    notifier.update(15)
    now[0] += 120

    assert notifier.remind(15, True) is False
    assert notifier.remind(15, None) is False
    assert len(sent) == 1
