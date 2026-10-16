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
        sleep=sleep,
    )

    poller.run(max_samples=3)

    assert reader.call_count == 3
    assert sleep.call_count == 2
