import pytest

from virtuoso_daemon.protocol import (
    CMD_GET,
    EP_HEADSET,
    EP_RECEIVER,
    DeviceState,
)
from virtuoso_daemon.recovery import RecoveryError, RecoveryStore
from virtuoso_daemon.session import (
    SessionError,
    SoftwareSession,
)


class FakeTransport:
    def __init__(self, fail_at=None):
        self.commands = []
        self.fail_at = fail_at

    def send(self, endpoint, command, payload):
        self.commands.append(
            (endpoint, command, list(payload))
        )
        return len(self.commands) != self.fail_at


def make_session(transport, tmp_path):
    return SoftwareSession(
        send=transport.send,
        pause=lambda _: None,
        recovery=RecoveryStore(
            tmp_path / "recovery.json"
        ),
    )


def test_initial_state(tmp_path):
    transport = FakeTransport()
    session = make_session(transport, tmp_path)

    assert session.state == DeviceState.CONNECTED
    assert session.recovery.read() is None
    assert transport.commands == []


def test_enter_software_mode(tmp_path):
    transport = FakeTransport()
    session = make_session(transport, tmp_path)

    session.enter()

    assert session.state == DeviceState.SOFTWARE_MODE
    assert session.recovery.read() == "recovery_required"
    assert len(transport.commands) == 4


@pytest.mark.parametrize("failure", [1, 2, 3, 4])
def test_partial_entry_requires_recovery(failure, tmp_path):
    transport = FakeTransport(fail_at=failure)
    session = make_session(transport, tmp_path)

    with pytest.raises(SessionError):
        session.enter()

    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert session.recovery.read() == "recovery_required"
    assert len(transport.commands) == failure


def test_repeated_enter_is_rejected(tmp_path):
    transport = FakeTransport()
    session = make_session(transport, tmp_path)

    session.enter()

    with pytest.raises(SessionError):
        session.enter()

    assert session.state == DeviceState.SOFTWARE_MODE
    assert session.recovery.read() == "recovery_required"
    assert len(transport.commands) == 4


def test_successful_exit(tmp_path):
    transport = FakeTransport()
    session = make_session(transport, tmp_path)

    session.enter()
    session.leave()

    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert session.recovery.read() == "restore_commands_sent"

    assert transport.commands[-2:] == [
        (EP_RECEIVER, CMD_GET, [0x03, 0x00, 0x01]),
        (EP_HEADSET, CMD_GET, [0x03, 0x00, 0x01]),
    ]


@pytest.mark.parametrize("failure", [5, 6])
def test_failed_exit_preserves_recovery(failure, tmp_path):
    transport = FakeTransport(fail_at=failure)
    session = make_session(transport, tmp_path)

    session.enter()

    with pytest.raises(SessionError):
        session.leave()

    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert session.recovery.read() == "recovery_required"
    assert len(transport.commands) == 6


def test_recovery_after_partial_entry(tmp_path):
    transport = FakeTransport(fail_at=3)
    session = make_session(transport, tmp_path)

    with pytest.raises(SessionError):
        session.enter()

    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert session.recovery.read() == "recovery_required"

    session.leave()

    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert session.recovery.read() == "restore_commands_sent"

    assert transport.commands[-2:] == [
        (EP_RECEIVER, CMD_GET, [0x03, 0x00, 0x01]),
        (EP_HEADSET, CMD_GET, [0x03, 0x00, 0x01]),
    ]


def test_leave_when_already_connected(tmp_path):
    transport = FakeTransport()
    session = make_session(transport, tmp_path)

    session.leave()

    assert session.state == DeviceState.CONNECTED
    assert session.recovery.read() is None
    assert transport.commands == []


def test_recovery_can_be_retried(tmp_path):
    transport = FakeTransport(fail_at=5)
    session = make_session(transport, tmp_path)

    session.enter()

    with pytest.raises(SessionError):
        session.leave()

    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert session.recovery.read() == "recovery_required"

    transport.fail_at = None
    session.leave()

    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert session.recovery.read() == "restore_commands_sent"
    assert len(transport.commands) == 8


def test_marker_failure_prevents_hid_writes(tmp_path):
    transport = FakeTransport()
    session = make_session(transport, tmp_path)

    def fail_marker():
        raise OSError("Simulated filesystem failure")

    session.recovery.mark_required = fail_marker

    with pytest.raises(OSError):
        session.enter()

    assert transport.commands == []
    assert session.state == DeviceState.CONNECTED
    assert session.recovery.read() is None


def test_recovery_marker_survives_new_store(tmp_path):
    transport = FakeTransport()
    session = make_session(transport, tmp_path)

    session.enter()

    new_store = RecoveryStore(
        tmp_path / "recovery.json"
    )

    assert new_store.read() == "recovery_required"

    session.leave()

    assert new_store.read() == "restore_commands_sent"


def test_failed_recovery_marker_write_blocks_exit(tmp_path):
    transport = FakeTransport()
    session = make_session(transport, tmp_path)

    session.enter()
    commands_before = len(transport.commands)

    def fail_marker():
        raise OSError("Simulated filesystem failure")

    session.recovery.mark_required = fail_marker

    with pytest.raises(OSError):
        session.leave()

    assert len(transport.commands) == commands_before
    assert session.state == DeviceState.SOFTWARE_MODE
    assert session.recovery.read() == "recovery_required"


def test_restart_detects_pending_recovery(tmp_path):
    transport = FakeTransport()
    store = RecoveryStore(tmp_path / "recovery.json")

    store.mark_required()

    session = SoftwareSession(
        send=transport.send,
        pause=lambda _: None,
        recovery=store,
    )

    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert store.read() == "recovery_required"
    assert transport.commands == []


def test_restart_blocks_software_mode_entry(tmp_path):
    transport = FakeTransport()
    store = RecoveryStore(tmp_path / "recovery.json")

    store.mark_required()

    session = SoftwareSession(
        send=transport.send,
        pause=lambda _: None,
        recovery=store,
    )

    with pytest.raises(SessionError, match="Cannot enter"):
        session.enter()

    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert store.read() == "recovery_required"
    assert transport.commands == []


def test_restart_allows_recovery_attempt(tmp_path):
    transport = FakeTransport()
    store = RecoveryStore(tmp_path / "recovery.json")

    store.mark_required()

    session = SoftwareSession(
        send=transport.send,
        pause=lambda _: None,
        recovery=store,
    )

    session.leave()

    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert store.read() == "restore_commands_sent"

    assert transport.commands == [
        (EP_RECEIVER, CMD_GET, [0x03, 0x00, 0x01]),
        (EP_HEADSET, CMD_GET, [0x03, 0x00, 0x01]),
    ]


def test_restart_preserves_unverified_restore(tmp_path):
    transport = FakeTransport()
    store = RecoveryStore(tmp_path / "recovery.json")

    store.mark_restore_sent()

    session = SoftwareSession(
        send=transport.send,
        pause=lambda _: None,
        recovery=store,
    )

    assert session.state == DeviceState.RECOVERY_REQUIRED

    with pytest.raises(SessionError, match="Cannot enter"):
        session.enter()

    assert store.read() == "restore_commands_sent"
    assert transport.commands == []


def test_corrupt_marker_blocks_session_creation(tmp_path):
    store = RecoveryStore(tmp_path / "recovery.json")
    store.path.write_text(
        "{invalid json",
        encoding="utf-8",
    )

    transport = FakeTransport()

    with pytest.raises(RecoveryError):
        SoftwareSession(
            send=transport.send,
            pause=lambda _: None,
            recovery=store,
        )

    assert transport.commands == []
