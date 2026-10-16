from unittest.mock import MagicMock, patch

import pytest

from virtuoso_daemon.device import (
    DeviceError,
    VirtuosoDevice,
)
from virtuoso_daemon.protocol import DeviceState


def make_hid_handle(*, response=True, write_length=65):
    handle = MagicMock()
    handle.write.return_value = write_length
    handle.read.return_value = (
        [0x01, 0x02] if response else []
    )
    return handle


def test_initial_state():
    device = VirtuosoDevice()

    assert device.state == DeviceState.DISCONNECTED
    assert not device.connected
    assert device.interface is None


@patch("virtuoso_daemon.device.time.sleep")
@patch("virtuoso_daemon.device.hid")
def test_connect_and_close(mock_hid, _sleep):
    handle = make_hid_handle()

    mock_hid.enumerate.return_value = [
        {"interface_number": 4, "path": b"test4"},
    ]
    mock_hid.device.return_value = handle

    device = VirtuosoDevice()

    assert device.connect()
    assert device.connected
    assert device.interface == 4
    assert device.state == DeviceState.CONNECTED

    device.close()

    assert not device.connected
    assert device.interface is None
    assert device.state == DeviceState.DISCONNECTED
    handle.close.assert_called_once()


@patch("virtuoso_daemon.device.time.sleep")
@patch("virtuoso_daemon.device.hid")
def test_probe_failure_closes_handle(mock_hid, _sleep):
    handle = make_hid_handle(response=False)

    mock_hid.enumerate.return_value = [
        {"interface_number": 4, "path": b"test4"},
    ]
    mock_hid.device.return_value = handle

    device = VirtuosoDevice()

    assert not device.connect()
    assert not device.connected
    assert device.state == DeviceState.DISCONNECTED

    handle.close.assert_called_once()


@patch("virtuoso_daemon.device.time.sleep")
@patch("virtuoso_daemon.device.hid")
def test_short_write_rejects_probe(mock_hid, _sleep):
    handle = make_hid_handle(write_length=10)

    mock_hid.enumerate.return_value = [
        {"interface_number": 4, "path": b"test4"},
    ]
    mock_hid.device.return_value = handle

    device = VirtuosoDevice()

    assert not device.connect()
    assert device.state == DeviceState.DISCONNECTED

    handle.close.assert_called_once()


def test_recovery_state_blocks_connection():
    device = VirtuosoDevice()
    device.state = DeviceState.RECOVERY_REQUIRED

    with pytest.raises(DeviceError, match="Recovery required"):
        device.connect()


def test_close_preserves_recovery_state():
    device = VirtuosoDevice()
    device.state = DeviceState.RECOVERY_REQUIRED

    device.close()

    assert device.state == DeviceState.RECOVERY_REQUIRED


def test_close_failure_requires_recovery():
    device = VirtuosoDevice()
    handle = MagicMock()
    handle.close.side_effect = OSError("HID close failed")

    device.device = handle
    device.interface = 4
    device.state = DeviceState.CONNECTED

    with pytest.raises(DeviceError, match="Failed to close"):
        device.close()

    assert device.state == DeviceState.RECOVERY_REQUIRED
    assert not device.connected


def test_connection_failure_reports_probe_error(monkeypatch):
    from unittest.mock import MagicMock
    import pytest

    from virtuoso_daemon import device as device_module
    from virtuoso_daemon.device import DeviceError, VirtuosoDevice

    monkeypatch.setattr(
        device_module.hid,
        "enumerate",
        lambda vendor, product: [
            {"interface_number": 4, "path": b"fake-interface"}
        ],
    )

    handle = MagicMock()
    handle.write.return_value = 65
    handle.read.return_value = []

    monkeypatch.setattr(
        device_module.hid,
        "device",
        lambda: handle,
    )
    monkeypatch.setattr(
        device_module.time,
        "sleep",
        lambda _: None,
    )

    with pytest.raises(
        DeviceError,
        match="Interface 4: firmware probe unanswered",
    ):
        with VirtuosoDevice():
            pass

    handle.close.assert_called_once()
