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
