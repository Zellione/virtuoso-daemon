import json

import pytest

from virtuoso_daemon.recovery import (
    RecoveryError,
    RecoveryStore,
)


@pytest.fixture
def store(tmp_path):
    return RecoveryStore(
        tmp_path / "state" / "recovery.json"
    )


def test_initially_no_marker(store):
    assert store.read() is None


def test_recovery_required_persists(store):
    store.mark_required()

    assert store.read() == "recovery_required"
    assert store.path.exists()


def test_state_survives_new_instance(store):
    store.mark_required()

    another = RecoveryStore(store.path)

    assert another.read() == "recovery_required"


def test_restore_commands_remain_recorded(store):
    store.mark_required()
    store.mark_restore_sent()

    assert store.read() == "restore_commands_sent"


def test_marker_permissions(store):
    store.mark_required()

    assert store.path.stat().st_mode & 0o777 == 0o600
    assert (
        store.path.parent.stat().st_mode & 0o777
        == 0o700
    )


def test_invalid_state_rejected(store):
    with pytest.raises(RecoveryError):
        store.write("firmware_verified")

    assert store.read() is None


def test_corrupt_marker_rejected(store):
    store.path.parent.mkdir(parents=True)
    store.path.write_text("{broken", encoding="utf-8")

    with pytest.raises(RecoveryError):
        store.read()


def test_unknown_marker_version_rejected(store):
    store.path.parent.mkdir(parents=True)
    store.path.write_text(
        json.dumps({
            "version": 2,
            "state": "recovery_required",
        }),
        encoding="utf-8",
    )

    with pytest.raises(RecoveryError):
        store.read()


def test_clear_marker(store):
    store.mark_required()
    store.clear()

    assert store.read() is None


def test_clear_missing_marker(store):
    store.clear()
    assert store.read() is None
