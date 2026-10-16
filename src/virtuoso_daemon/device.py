"""HID connection management for Corsair Virtuoso Wireless.

Based on protocol research from VirtuosoControl
by Alejandro Socas (MIT License).

No headset software-mode commands are issued here.
"""

import time

import hid

from .protocol import (
    CMD_SET,
    EP_RECEIVER,
    DeviceState,
    build_packet,
)


VENDOR_ID = 0x1B1C
PRODUCT_ID = 0x0A42


class DeviceError(RuntimeError):
    """HID connection or communication failure."""


class VirtuosoDevice:
    def __init__(self):
        self.device = None
        self.interface = None
        self.state = DeviceState.DISCONNECTED
        self.last_connect_error = None

    @property
    def connected(self):
        return self.device is not None

    def _write(self, device, endpoint, command, payload):
        packet = build_packet(endpoint, command, payload)
        written = device.write(packet)

        if written != len(packet):
            raise DeviceError(
                f"Short HID write: {written}/{len(packet)}"
            )

    def _probe(self, device):
        """Probe the receiver without enabling software mode."""
        self._write(
            device,
            EP_RECEIVER,
            CMD_SET,
            [0x13],
        )

        for _ in range(10):
            time.sleep(0.02)

            response = device.read(64)

            if response:
                return True

        return False

    def connect(self):
        if self.state == DeviceState.RECOVERY_REQUIRED:
            raise DeviceError(
                "Recovery required before reconnecting"
            )

        if self.connected:
            return True

        if self.state != DeviceState.DISCONNECTED:
            raise DeviceError(
                f"Invalid connection state: {self.state.name}"
            )

        self.last_connect_error = None
        self.interface = None

        try:
            candidates = hid.enumerate(
                VENDOR_ID,
                PRODUCT_ID,
            )
        except Exception as exc:
            raise DeviceError(
                "HID enumeration failed"
            ) from exc

        for interface in (4, 3):
            for candidate in candidates:
                if candidate["interface_number"] != interface:
                    continue

                handle = None

                try:
                    handle = hid.device()
                    handle.open_path(candidate["path"])
                    handle.set_nonblocking(True)

                    if not self._probe(handle):
                        self.last_connect_error = (
                            f"Interface {interface}: firmware probe unanswered"
                        )
                        continue

                    self.device = handle
                    self.interface = interface
                    self.state = DeviceState.CONNECTED

                    handle = None
                    return True

                except Exception as exc:
                    self.last_connect_error = (
                        f"Interface {interface}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    continue

                finally:
                    if handle is not None:
                        try:
                            handle.close()
                        except Exception:
                            pass

        return False

    def close(self):
        """Release HID resources without masking recovery state."""
        handle = self.device

        self.device = None
        self.interface = None

        if handle is not None:
            try:
                handle.close()
            except Exception as exc:
                self.state = DeviceState.RECOVERY_REQUIRED
                raise DeviceError(
                    "Failed to close HID connection"
                ) from exc

        if self.state != DeviceState.RECOVERY_REQUIRED:
            self.state = DeviceState.DISCONNECTED

    def __enter__(self):
        if not self.connect():
            raise DeviceError(
                "Corsair Virtuoso connection failed"
                + (
                    f": {self.last_connect_error}"
                    if self.last_connect_error
                    else ""
                )
            )

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
