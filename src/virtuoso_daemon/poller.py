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
from .charging import read_charging_with_transport


class BatteryPoller:
    def __init__(
        self,
        handle,
        *,
        interval=300,
        state_path=None,
        battery_reader=read_battery_with_transport,
        charging_reader=read_charging_with_transport,
        sleep=time.sleep,
        notifier=None,
        clock=time.monotonic,
    ):
        if interval <= 0:
            raise ValueError("interval must be positive")

        self.transport = HidTransport(handle)
        self.interval = interval
        self.battery_reader = battery_reader
        self.charging_reader = charging_reader
        self.sleep = sleep
        self.state_path = Path(
            state_path
            or Path(os.environ.get(
                "XDG_RUNTIME_DIR", "/tmp"
            )) / "virtuoso-daemon" / "battery.json"
        )
        self.last_level = None
        self.last_charging = None
        self.notifier = notifier
        self.clock = clock

    def _publish(self, level, charging=None):
        self.state_path.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        payload = {
            "battery_percent": level,
            "charging": charging,
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

        self.threshold_notified = False
        try:
            charging = self.charging_reader(self.transport)
        except Exception as exc:
            charging = None
            print(f"Charging status unavailable: {exc}", flush=True)

        reports = self.transport.drain()

        self.last_level = level
        self.last_charging = charging
        self._publish(level, charging)

        if self.notifier is not None:
            try:
                self.notifier.update(level)
            except Exception as exc:
                print(
                    f"Battery notification failed: {exc}",
                    flush=True,
                )

        return level, reports

    def run(self, *, max_samples=None):
        if max_samples is not None and max_samples < 1:
            raise ValueError("max_samples must be positive")

        completed = 0
        next_reminder = self.clock() + 60

        while max_samples is None or completed < max_samples:
            try:
                level, reports = self.sample()

                print(
                    f"Battery: {level}% "
                    f"charging={self.last_charging} "
                    f"(other reports: {len(reports)})",
                    flush=True,
                )

            except (BatteryError, TransportOverflowError) as exc:
                print(
                    f"Battery polling stopped: {exc}",
                    flush=True,
                )
                raise

            now = self.clock()

            if now >= next_reminder:
                if self.notifier is not None:
                    try:
                        self.notifier.remind(
                            level,
                            self.last_charging,
                        )
                    except Exception as exc:
                        print(
                            f"Battery reminder failed: {exc}",
                            flush=True,
                        )

                next_reminder = now + 60

            completed += 1

            if max_samples is None or completed < max_samples:
                self.sleep(self.interval)
