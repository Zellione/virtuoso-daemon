import pytest

from virtuoso_daemon.battery import BatteryError
from virtuoso_daemon import __main__ as cli
from virtuoso_daemon.locking import ControllerLock, LockError
from virtuoso_daemon.recovery import RecoveryStore


def test_exclusive_lock(tmp_path):
    path = tmp_path / "controller.lock"

    with ControllerLock(path):
        with pytest.raises(LockError):
            with ControllerLock(path):
                pass

    with ControllerLock(path):
        pass


def test_lock_released_on_exception(tmp_path):
    path = tmp_path / "controller.lock"

    with pytest.raises(ValueError):
        with ControllerLock(path):
            raise ValueError("test")

    with ControllerLock(path):
        pass


def test_status_without_marker(tmp_path, monkeypatch, capsys):
    store = RecoveryStore(tmp_path / "recovery.json")

    monkeypatch.setattr(
        cli.RecoveryStore,
        "default",
        lambda: store,
    )

    cli.status()

    assert "Recovery: none" in capsys.readouterr().out


def test_status_with_marker(tmp_path, monkeypatch, capsys):
    store = RecoveryStore(tmp_path / "recovery.json")
    store.mark_required()

    monkeypatch.setattr(
        cli.RecoveryStore,
        "default",
        lambda: store,
    )

    cli.status()

    assert "recovery_required" in capsys.readouterr().out


def test_recover_without_marker_sends_nothing(
    tmp_path, monkeypatch
):
    store = RecoveryStore(tmp_path / "recovery.json")
    monkeypatch.setattr(
        cli.RecoveryStore,
        "default",
        lambda: store,
    )
    monkeypatch.setattr(
        cli,
        "ControllerLock",
        lambda: ControllerLock(tmp_path / "controller.lock"),
    )

    class ForbiddenDevice:
        def __enter__(self):
            raise AssertionError("Unexpected HID access")

    monkeypatch.setattr(
        cli, "VirtuosoDevice", ForbiddenDevice
    )

    cli.recover()
    assert store.read() is None


from unittest.mock import MagicMock

from virtuoso_daemon import __main__ as cli


def test_led_probe_cli_without_software_session(monkeypatch):
    device = MagicMock()
    device.interface = 4
    device.device.write.return_value = 65

    context = MagicMock()
    context.__enter__.return_value = device

    marker = MagicMock()
    marker.read.return_value = "restore_commands_sent"

    monkeypatch.setattr(cli, "VirtuosoDevice", lambda: context)
    monkeypatch.setattr(cli, "ControllerLock", lambda: MagicMock())
    monkeypatch.setattr(cli.RecoveryStore, "default", lambda: marker)

    session = MagicMock()
    monkeypatch.setattr(cli, "make_session", session)

    cli.led_probe()

    session.assert_not_called()
    marker.clear.assert_not_called()
    marker.write.assert_not_called()

    device.device.write.assert_called_once_with(
        cli.probe_led_endpoint.__globals__[
            "build_led_init_packet"
        ]()
    )


def test_led_test_cli_dispatch(monkeypatch):
    called = []

    monkeypatch.setattr(
        cli,
        "led_test",
        lambda: called.append("led-test"),
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["virtuoso-daemon", "led-test"],
    )

    assert cli.main() == 0
    assert called == ["led-test"]


def test_battery_direct_without_software_mode(monkeypatch):
    from unittest.mock import MagicMock

    device = MagicMock()
    device.interface = 4

    context = MagicMock()
    context.__enter__.return_value = device

    store = MagicMock()
    store.read.return_value = "restore_commands_sent"

    session = MagicMock()
    battery_reader = MagicMock(return_value=85)

    monkeypatch.setattr(cli, "VirtuosoDevice", lambda: context)
    monkeypatch.setattr(cli, "ControllerLock", lambda: MagicMock())
    monkeypatch.setattr(cli.RecoveryStore, "default", lambda: store)
    monkeypatch.setattr(cli, "make_session", session)
    monkeypatch.setattr(cli, "read_battery", battery_reader)

    cli.battery_direct()

    battery_reader.assert_called_once_with(device.device)
    session.assert_not_called()
    store.mark_required.assert_not_called()
    store.mark_restore_sent.assert_not_called()
    store.clear.assert_not_called()
    store.write.assert_not_called()
    assert store.read.call_count == 2


def test_battery_direct_cli_dispatch(monkeypatch):
    called = []

    monkeypatch.setattr(
        cli,
        "battery_direct",
        lambda: called.append("battery-direct"),
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["virtuoso-daemon", "battery-direct"],
    )

    assert cli.main() == 0
    assert called == ["battery-direct"]


def test_battery_watch_cli_dispatch(monkeypatch):
    called = []

    monkeypatch.setattr(
        cli,
        "battery_watch",
        lambda **kwargs: called.append(kwargs),
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["virtuoso-daemon", "battery-watch"],
    )

    assert cli.main() == 0
    assert called == [
        {"interval": 300, "samples": None}
    ]


def test_battery_watch_cli_options(monkeypatch):
    called = []

    monkeypatch.setattr(
        cli,
        "battery_watch",
        lambda **kwargs: called.append(kwargs),
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "virtuoso-daemon",
            "battery-watch",
            "--interval",
            "30",
            "--samples",
            "3",
        ],
    )

    assert cli.main() == 0
    assert called == [
        {"interval": 30.0, "samples": 3}
    ]


def test_battery_watch_uses_single_connection(monkeypatch):
    from unittest.mock import MagicMock

    device = MagicMock()
    device.interface = 4

    context = MagicMock()
    context.__enter__.return_value = device

    poller = MagicMock()
    poller_factory = MagicMock(return_value=poller)

    store = MagicMock()
    store.read.return_value = "restore_commands_sent"

    monkeypatch.setattr(cli, "VirtuosoDevice", lambda: context)
    monkeypatch.setattr(cli, "ControllerLock", lambda: MagicMock())
    monkeypatch.setattr(cli.RecoveryStore, "default", lambda: store)
    monkeypatch.setattr(cli, "BatteryPoller", poller_factory)

    cli.battery_watch()

    from unittest.mock import ANY

    poller_factory.assert_called_once_with(
        device.device,
        interval=300,
        notifier=ANY,
    )

    notifier = poller_factory.call_args.kwargs["notifier"]
    assert isinstance(notifier, cli.BatteryNotifier)

    from unittest.mock import ANY

    poller_factory.assert_called_once_with(
        device.device,
        interval=300,
        notifier=ANY,
    )

    notifier = poller_factory.call_args.kwargs["notifier"]
    assert isinstance(notifier, cli.BatteryNotifier)
    store.clear.assert_not_called()
    store.write.assert_not_called()


def test_battery_watch_reconnects_after_failure(monkeypatch):
    from unittest.mock import MagicMock

    devices = []
    pollers = []

    def make_device():
        context = MagicMock()
        device = MagicMock()
        device.interface = 4
        context.__enter__.return_value = device
        devices.append(context)
        return context

    def make_poller(handle, *, interval, notifier):
        poller = MagicMock()

        if not pollers:
            poller.run.side_effect = BatteryError(
                "Device disconnected"
            )

        pollers.append(poller)
        return poller

    sleep = MagicMock()
    store = MagicMock()
    store.read.return_value = "restore_commands_sent"

    monkeypatch.setattr(cli, "VirtuosoDevice", make_device)
    monkeypatch.setattr(cli, "BatteryPoller", make_poller)
    monkeypatch.setattr(cli, "ControllerLock", lambda: MagicMock())
    monkeypatch.setattr(cli.RecoveryStore, "default", lambda: store)
    monkeypatch.setattr(cli.time, "sleep", sleep)

    cli.battery_watch(interval=30, samples=3)

    assert len(devices) == 2
    assert len(pollers) == 2

    sleep.assert_called_once_with(15)

    for context in devices:
        context.__exit__.assert_called_once()

    store.clear.assert_not_called()
    store.write.assert_not_called()


def test_battery_watch_does_not_retry_interrupt(monkeypatch):
    from unittest.mock import MagicMock

    context = MagicMock()
    context.__enter__.return_value = MagicMock(interface=4)

    poller = MagicMock()
    poller.run.side_effect = KeyboardInterrupt

    sleep = MagicMock()

    monkeypatch.setattr(cli, "VirtuosoDevice", lambda: context)
    monkeypatch.setattr(
        cli, "BatteryPoller", lambda *a, **kw: poller
    )
    monkeypatch.setattr(cli, "ControllerLock", lambda: MagicMock())
    monkeypatch.setattr(
        cli.RecoveryStore, "default", lambda: MagicMock()
    )
    monkeypatch.setattr(cli.time, "sleep", sleep)

    with pytest.raises(KeyboardInterrupt):
        cli.battery_watch()

    sleep.assert_not_called()
    context.__exit__.assert_called_once()


def test_battery_watch_retries_initial_connection_failure(monkeypatch):
    from unittest.mock import MagicMock
    from virtuoso_daemon.device import DeviceError

    attempts = 0
    poller = MagicMock()
    sleep = MagicMock()

    def make_device():
        nonlocal attempts
        attempts += 1

        context = MagicMock()

        if attempts == 1:
            context.__enter__.side_effect = DeviceError(
                "Headset unavailable"
            )
        else:
            context.__enter__.return_value.device = MagicMock()
            context.__enter__.return_value.interface = 4

        return context

    monkeypatch.setattr(cli, "VirtuosoDevice", make_device)
    monkeypatch.setattr(
        cli, "BatteryPoller", lambda *args, **kwargs: poller
    )
    monkeypatch.setattr(
        cli, "ControllerLock", lambda: MagicMock()
    )
    monkeypatch.setattr(
        cli.RecoveryStore, "default", lambda: MagicMock(read=lambda: None)
    )
    monkeypatch.setattr(cli.time, "sleep", sleep)

    cli.battery_watch(samples=1)

    assert attempts == 2
    sleep.assert_called_once_with(15)
    poller.run.assert_called_once_with(max_samples=1)


def test_battery_watch_interrupts_during_retry(monkeypatch):
    from unittest.mock import MagicMock
    from virtuoso_daemon.device import DeviceError

    context = MagicMock()
    context.__enter__.side_effect = DeviceError("Disconnected")

    sleep = MagicMock(side_effect=KeyboardInterrupt)

    monkeypatch.setattr(cli, "VirtuosoDevice", lambda: context)
    monkeypatch.setattr(
        cli, "ControllerLock", lambda: MagicMock()
    )
    monkeypatch.setattr(
        cli.RecoveryStore, "default", lambda: MagicMock(read=lambda: None)
    )
    monkeypatch.setattr(cli.time, "sleep", sleep)

    with pytest.raises(KeyboardInterrupt):
        cli.battery_watch()

    sleep.assert_called_once_with(15)


def test_cli_keyboard_interrupt_exits_cleanly(monkeypatch):
    monkeypatch.setattr(
        cli,
        "battery_watch",
        lambda **kwargs: (_ for _ in ()).throw(
            KeyboardInterrupt()
        ),
    )

    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["virtuoso-daemon", "battery-watch"],
    )

    assert cli.main() == 0


def test_battery_watch_initial_connection_retries(monkeypatch):
    from unittest.mock import MagicMock
    from virtuoso_daemon.device import DeviceError

    attempts = 0
    delays = []

    def make_device():
        nonlocal attempts
        attempts += 1

        context = MagicMock()

        if attempts <= 3:
            context.__enter__.side_effect = DeviceError(
                "Connection unavailable"
            )
        else:
            context.__enter__.return_value.interface = 4

        return context

    poller = MagicMock()

    monkeypatch.setattr(cli, "VirtuosoDevice", make_device)
    monkeypatch.setattr(
        cli, "BatteryPoller", lambda *args, **kwargs: poller
    )
    monkeypatch.setattr(
        cli, "ControllerLock", lambda: MagicMock()
    )
    monkeypatch.setattr(
        cli.RecoveryStore,
        "default",
        lambda: MagicMock(read=lambda: None),
    )
    monkeypatch.setattr(
        cli.time, "sleep", lambda seconds: delays.append(seconds)
    )

    cli.battery_watch(samples=1)

    assert attempts == 4
    assert delays == [15, 15, 15]
    poller.run.assert_called_once_with(max_samples=1)


def test_battery_watch_resets_retry_after_success(monkeypatch):
    from unittest.mock import MagicMock
    from virtuoso_daemon.device import DeviceError

    attempts = 0
    delays = []

    def make_device():
        nonlocal attempts
        attempts += 1
        context = MagicMock()

        if attempts <= 3:
            context.__enter__.side_effect = DeviceError(
                "Headset unavailable"
            )
        else:
            context.__enter__.return_value.interface = 4

        return context

    pollers = []

    def make_poller(*args, **kwargs):
        poller = MagicMock()
        poller.last_level = None

        if not pollers:
            poller.last_level = 50
            poller.run.side_effect = BatteryError(
                "Connection lost after sample"
            )

        pollers.append(poller)
        return poller

    monkeypatch.setattr(cli, "VirtuosoDevice", make_device)
    monkeypatch.setattr(cli, "BatteryPoller", make_poller)
    monkeypatch.setattr(cli, "ControllerLock", lambda: MagicMock())
    monkeypatch.setattr(
        cli.RecoveryStore,
        "default",
        lambda: MagicMock(read=lambda: None),
    )
    monkeypatch.setattr(
        cli.time,
        "sleep",
        lambda seconds: delays.append(seconds),
    )

    cli.battery_watch(samples=1)

    assert attempts == 5
    assert delays == [15, 15, 15, 15]
    assert len(pollers) == 2


def test_charging_probe_dispatch(monkeypatch):
    called = []

    monkeypatch.setattr(
        cli,
        "charging_probe",
        lambda: called.append(True),
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["virtuoso-daemon", "charging-probe"],
    )

    assert cli.main() == 0
    assert called == [True]


def test_notifications_test_cli_dispatch(monkeypatch):
    called = []

    monkeypatch.setattr(
        cli,
        "notifications_test",
        lambda: called.append(True),
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["virtuoso-daemon", "notifications-test"],
    )

    assert cli.main() == 0
    assert called == [True]
