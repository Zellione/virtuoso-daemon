import pytest

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
