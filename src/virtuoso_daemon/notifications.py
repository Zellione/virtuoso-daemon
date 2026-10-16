"""Persistent low-battery notifications via Mako."""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


class BatteryNotifier:
    COOLDOWN = 60

    def __init__(self, path=None, send=None, clock=None):
        self.path = Path(path) if path is not None else (
            Path.home() / ".local/state/virtuoso-daemon/notifications.json"
        )
        self.send = send if send is not None else self._send
        self.clock = clock if clock is not None else time.time

    @staticmethod
    def _send(level, urgency):
        summary = (
            "Virtuoso battery critical"
            if urgency == "critical"
            else "Virtuoso battery low"
        )
        subprocess.run(
            [
                "notify-send",
                "-u", urgency,
                "-a", "Corsair Virtuoso",
                summary,
                f"Headset battery: {level}%",
            ],
            check=True,
            timeout=5,
        )

    def _read(self):
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {"state": "normal", "last_sent_at": None}

        if not isinstance(data, dict):
            raise ValueError("Invalid notification state")

        if data.get("state") not in ("normal", "low", "critical"):
            raise ValueError("Invalid notification state")

        last = data.get("last_sent_at")
        if last is not None and (
            not isinstance(last, (int, float))
            or isinstance(last, bool)
        ):
            raise ValueError("Invalid notification timestamp")

        return {
            "state": data["state"],
            "last_sent_at": last,
        }

    def _write(self, data):
        self.path.parent.mkdir(
            parents=True, exist_ok=True, mode=0o700
        )

        fd, name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=".notifications-",
        )

        try:
            with os.fdopen(fd, "w") as file:
                json.dump(data, file)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _ready(self, data):
        last = data["last_sent_at"]
        now = self.clock()

        return (
            last is None
            or now - last >= self.COOLDOWN
        )

    def _notify(self, data, level, urgency, state):
        if not self._ready(data):
            return False

        self.send(level, urgency)

        self._write({
            "state": state,
            "last_sent_at": self.clock(),
        })
        return True

    @staticmethod
    def _validate(level):
        if (
            type(level) is not int
            or not 0 <= level <= 100
        ):
            raise ValueError("Battery level must be 0..100")

    def update(self, level):
        self._validate(level)
        data = self._read()
        previous = data["state"]

        if level > 25:
            if previous != "normal":
                self._write({
                    **data,
                    "state": "normal",
                })
            return False

        if level <= 10:
            if previous != "critical":
                return self._notify(
                    data, level, "critical", "critical"
                )
            return False

        if level <= 20 and previous == "normal":
            return self._notify(
                data, level, "normal", "low"
            )

        return False

    def remind(self, level, charging):
        self._validate(level)

        if charging is not False or level > 15:
            return False

        data = self._read()
        urgency = "critical" if level <= 10 else "normal"

        return self._notify(
            data,
            level,
            urgency,
            "critical" if level <= 10 else (
                "low" if data["state"] == "normal"
                else data["state"]
            ),
        )
