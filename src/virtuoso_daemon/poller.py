"""Persistent battery polling over one HID connection.

No firmware-mode transitions or microphone control.
"""

import json
import os
import tempfile
import time
from pathlib import Path

from .battery import BatteryError, read_battery_with_transport
from .transport import HidTransport, TransportOverflowError


class BatteryPoller:
    def __init__(
        self,
        handle,
        *,
        interval=300,
        state_path=None,
        battery_reader=read_battery_with_transport,
        sleep=time.sleep,
    ):
        if interval <= 0:
            raise ValueError("interval must be positive")

        self.transport = HidTransport(handle)
        self.interval = interval
        self.battery_reader = battery_reader
        self.sleep = sleep
        self.state_path = Path(
            state_path
            or Path(os.environ.get(
                "XDG_RUNTIME_DIR", "/tmp"
            )) / "virtuoso-daemon" / "battery.json"
        )
        self.last_level = None

    def _publish(self, level):
        self.state_path.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        payload = {
            "battery_percent": level,
            "timestamp": int(time.time()),
        }

        fd, name = tempfile.mkstemp(
            dir=self.state_path.parent,
            prefix=".battery-",
        )

        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())

            os.replace(name, self.state_path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def sample(self):
        level = self.battery_reader(self.transport)

        # Reports unrelated to the battery query are consumed
        # without issuing any microphone-control commands.
        # The firmware remains responsible for physical mute.
        reports = self.transport.drain()

        self.last_level = level
        self._publish(level)

        return level, reports

    def run(self, *, max_samples=None):
        if max_samples is not None and max_samples < 1:
            raise ValueError("max_samples must be positive")
    
        completed = 0
    
        while max_samples is None or completed < max_samples:
            try:
                level, reports = self.sample()
                print(
                    f"Battery: {level}% "
                    f"(other reports: {len(reports)})",
                    flush=True,
                )
            except (BatteryError, TransportOverflowError) as exc:
                print(
                    f"Battery polling stopped: {exc}",
                    flush=True,
                )
                raise
    
            completed += 1
    
            if max_samples is None or completed < max_samples:
                self.sleep(self.interval)
