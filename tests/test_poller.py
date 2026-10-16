import json
from unittest.mock import MagicMock

import pytest

from virtuoso_daemon.battery import BatteryError
from virtuoso_daemon.poller import BatteryPoller


def test_sample_publishes_battery(tmp_path):
    path = tmp_path / "battery.json"
    reader = MagicMock(return_value=76)

    poller = BatteryPoller(
        MagicMock(),
        state_path=path,
        battery_reader=reader,
        charging_reader=lambda transport: None,
    )

    level, reports = poller.sample()

    assert level == 76
    assert reports == []
    assert poller.last_level == 76
    assert json.loads(path.read_text())[
        "battery_percent"
    ] == 76
    reader.assert_called_once_with(poller.transport)


def test_failed_read_does_not_publish(tmp_path):
    path = tmp_path / "battery.json"

    poller = BatteryPoller(
        MagicMock(),
        state_path=path,
        battery_reader=MagicMock(
            side_effect=BatteryError("No response")
        ),
    )

    with pytest.raises(BatteryError):
        poller.sample()

    assert not path.exists()


def test_repeated_samples_use_same_transport(tmp_path):
    reader = MagicMock(side_effect=[76, 75])
    handle = MagicMock()

    poller = BatteryPoller(
        handle,
        state_path=tmp_path / "battery.json",
        battery_reader=reader,
        charging_reader=lambda transport: None,
    )

    assert poller.sample()[0] == 76
    assert poller.sample()[0] == 75

    assert reader.call_count == 2
    assert all(
        call.args[0] is poller.transport
        for call in reader.call_args_list
    )


def test_invalid_interval():
    with pytest.raises(ValueError):
        BatteryPoller(MagicMock(), interval=0)


def test_poller_stops_after_read_failure(tmp_path):
    reader = MagicMock(
        side_effect=BatteryError("No response")
    )
    sleep = MagicMock()

    poller = BatteryPoller(
        MagicMock(),
        state_path=tmp_path / "battery.json",
        battery_reader=reader,
        charging_reader=lambda transport: None,
        sleep=sleep,
    )

    with pytest.raises(BatteryError):
        poller.run()

    reader.assert_called_once()
    sleep.assert_not_called()


def test_poller_reuses_connection_until_interrupted(tmp_path):
    calls = 0

    def reader(_transport):
        nonlocal calls
        calls += 1

        if calls == 3:
            raise KeyboardInterrupt

        return 76

    poller = BatteryPoller(
        MagicMock(),
        interval=1,
        state_path=tmp_path / "battery.json",
        battery_reader=reader,
        charging_reader=lambda transport: None,
        sleep=lambda _: None,
    )

    with pytest.raises(KeyboardInterrupt):
        poller.run()

    assert calls == 3
    assert poller.last_level == 76


def test_poller_stops_after_three_samples(tmp_path):
    reader = MagicMock(return_value=76)
    sleep = MagicMock()

    poller = BatteryPoller(
        MagicMock(),
        interval=30,
        state_path=tmp_path / "battery.json",
        battery_reader=reader,
        charging_reader=lambda transport: None,
        sleep=sleep,
    )

    poller.run(max_samples=3)

    assert reader.call_count == 3
    assert sleep.call_count == 2


def test_sample_reads_charging_state(tmp_path):
    battery_reader = MagicMock(return_value=76)
    charging_reader = MagicMock(return_value=True)

    poller = BatteryPoller(
        MagicMock(),
        state_path=tmp_path / "battery.json",
        battery_reader=battery_reader,
        charging_reader=charging_reader,
    )

    level, reports = poller.sample()

    assert level == 76
    assert reports == []
    assert poller.last_charging is True

    battery_reader.assert_called_once_with(poller.transport)
    charging_reader.assert_called_once_with(poller.transport)


def test_unknown_charging_state(tmp_path):
    poller = BatteryPoller(
        MagicMock(),
        state_path=tmp_path / "battery.json",
        battery_reader=MagicMock(return_value=76),
        charging_reader=MagicMock(return_value=None),
    )

    poller.sample()

    assert poller.last_charging is None


def test_charging_failure_does_not_stop_battery_polling(tmp_path):
    charging_reader = MagicMock(
        side_effect=RuntimeError("Charging unavailable")
    )

    poller = BatteryPoller(
        MagicMock(),
        state_path=tmp_path / "battery.json",
        battery_reader=MagicMock(return_value=76),
        charging_reader=charging_reader,
    )

    assert poller.sample()[0] == 76
    assert poller.last_charging is None


@pytest.mark.parametrize(
    ("charging", "expected"),
    [
        (True, True),
        (False, False),
        (None, None),
    ],
)
def test_cache_includes_charging_state(
    tmp_path, charging, expected
):
    path = tmp_path / "battery.json"

    poller = BatteryPoller(
        MagicMock(),
        state_path=path,
        battery_reader=MagicMock(return_value=66),
        charging_reader=MagicMock(return_value=charging),
    )

    poller.sample()

    data = json.loads(path.read_text())

    assert data["battery_percent"] == 66
    assert data["charging"] is expected
    assert isinstance(data["timestamp"], int)


def test_minute_reminders_only_when_discharging(tmp_path):
    now = [0.0]
    notifier = MagicMock()
    notifier.update.return_value = False

    poller = BatteryPoller(
        MagicMock(),
        interval=30,
        state_path=tmp_path / "battery.json",
        battery_reader=MagicMock(return_value=14),
        charging_reader=MagicMock(return_value=False),
        notifier=notifier,
        clock=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(
            0, now[0] + seconds
        ),
    )

    poller.run(max_samples=7)

    assert now[0] == 180
    assert notifier.update.call_count == 7
    assert notifier.remind.call_count == 3

    notifier.remind.assert_called_with(14, False)


def test_reminders_stop_while_charging(tmp_path):
    now = [0.0]
    notifier = MagicMock()
    notifier.update.return_value = False

    charging_reader = MagicMock(
        side_effect=[False, False, True, True, True]
    )

    poller = BatteryPoller(
        MagicMock(),
        interval=30,
        state_path=tmp_path / "battery.json",
        battery_reader=MagicMock(return_value=14),
        charging_reader=charging_reader,
        notifier=notifier,
        clock=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(
            0, now[0] + seconds
        ),
    )

    poller.run(max_samples=5)

    assert notifier.remind.call_count == 2
    assert notifier.remind.call_args_list[0].args == (14, True)
    assert notifier.remind.call_args_list[1].args == (14, True)


def test_unknown_charging_suppresses_reminders(tmp_path):
    now = [0.0]
    notifier = MagicMock()

    poller = BatteryPoller(
        MagicMock(),
        interval=30,
        state_path=tmp_path / "battery.json",
        battery_reader=MagicMock(return_value=9),
        charging_reader=MagicMock(return_value=None),
        notifier=notifier,
        clock=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(
            0, now[0] + seconds
        ),
    )

    poller.run(max_samples=5)

    for call in notifier.remind.call_args_list:
        assert call.args == (9, None)


def test_threshold_and_reminder_not_duplicated(tmp_path):
    from virtuoso_daemon.notifications import BatteryNotifier

    now = [1000.0]
    sent = []

    notifier = BatteryNotifier(
        path=tmp_path / "notifications.json",
        clock=lambda: now[0],
        send=lambda level, urgency: sent.append(
            (level, urgency)
        ),
    )

    poller = BatteryPoller(
        MagicMock(),
        interval=30,
        state_path=tmp_path / "battery.json",
        battery_reader=MagicMock(return_value=10),
        charging_reader=MagicMock(return_value=False),
        notifier=notifier,
        clock=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(
            0, now[0] + seconds
        ),
    )

    poller.run(max_samples=5)

    assert sent == [
        (10, "critical"),
        (10, "critical"),
        (10, "critical"),
    ]
