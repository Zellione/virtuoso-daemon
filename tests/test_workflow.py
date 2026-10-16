import pytest

from virtuoso_daemon.protocol import DeviceState
from virtuoso_daemon.recovery import RecoveryStore
from virtuoso_daemon.session import SoftwareSession
from virtuoso_daemon.workflow import run_battery_workflow


class FakeHid:
    def __init__(self, fail_at=None):
        self.commands = []
        self.fail_at = fail_at
        self.flushed = False

    def send(self, endpoint, command, payload):
        self.commands.append(
            (endpoint, command, tuple(payload))
        )
        return len(self.commands) != self.fail_at

    def flush(self):
        self.flushed = True


def make_session(fake, tmp_path):
    return SoftwareSession(
        send=fake.send,
        pause=lambda _: None,
        recovery=RecoveryStore(
            tmp_path / "recovery.json"
        ),
        flush=fake.flush,
    )


def test_complete_battery_workflow(tmp_path):
    fake = FakeHid()
    session = make_session(fake, tmp_path)

    result = run_battery_workflow(
        session,
        lambda: "73% [Discharging]",
    )

    assert result == "73% [Discharging]"
    assert fake.flushed
    assert len(fake.commands) == 6
    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert session.recovery.read() == "restore_commands_sent"


def test_battery_failure_attempts_recovery(tmp_path):
    fake = FakeHid()
    session = make_session(fake, tmp_path)

    def failed_battery():
        raise RuntimeError("Battery read failed")

    with pytest.raises(RuntimeError, match="Battery read failed"):
        run_battery_workflow(session, failed_battery)

    assert len(fake.commands) == 6
    assert session.recovery.read() == "restore_commands_sent"


def test_partial_handshake_attempts_recovery(tmp_path):
    fake = FakeHid(fail_at=3)
    session = make_session(fake, tmp_path)
    battery_called = False

    def read_battery():
        nonlocal battery_called
        battery_called = True
        return "73%"

    with pytest.raises(Exception):
        run_battery_workflow(session, read_battery)

    assert not battery_called
    assert len(fake.commands) == 5
    assert session.recovery.read() == "restore_commands_sent"


def test_recovery_failure_preserves_marker(tmp_path):
    fake = FakeHid(fail_at=5)
    session = make_session(fake, tmp_path)

    with pytest.raises(Exception):
        run_battery_workflow(
            session,
            lambda: "73%",
        )

    assert len(fake.commands) == 6
    assert session.state == DeviceState.RECOVERY_REQUIRED
    assert session.recovery.read() == "recovery_required"


def test_double_failure_reports_both(tmp_path):
    fake = FakeHid(fail_at=5)
    session = make_session(fake, tmp_path)

    def failed_battery():
        raise ValueError("Invalid battery response")

    with pytest.raises(BaseExceptionGroup) as exc:
        run_battery_workflow(
            session,
            failed_battery,
        )

    messages = [
        str(error)
        for error in exc.value.exceptions
    ]

    assert any("Invalid battery response" in m for m in messages)
    assert any(
        "Firmware-mode restoration not confirmed" in m
        for m in messages
    )
    assert session.recovery.read() == "recovery_required"


def test_existing_recovery_blocks_new_workflow(tmp_path):
    fake = FakeHid()
    store = RecoveryStore(tmp_path / "recovery.json")
    store.mark_required()

    session = make_session(fake, tmp_path)

    with pytest.raises(Exception):
        run_battery_workflow(
            session,
            lambda: "73%",
        )

    assert len(fake.commands) == 2
    assert store.read() == "restore_commands_sent"
