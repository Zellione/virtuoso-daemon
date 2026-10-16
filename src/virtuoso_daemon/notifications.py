"""Persistent low-battery notifications via the desktop notification system."""

import json
import os
import subprocess
import tempfile
from pathlib import Path


class BatteryNotifier:
    def __init__(self, path=None, send=None):
        self.path = Path(path) if path is not None else (
            Path.home() / ".local/state/virtuoso-daemon/notifications.json"
        )
        self.send = send if send is not None else self._send

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
            return "normal"
        if not isinstance(data, dict):
            raise ValueError("Invalid notification state")
        state = data.get("state")
        if state not in ("normal", "low", "critical"):
            raise ValueError("Invalid notification state")
        return state

    def _write(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as file:
                json.dump({"state": state}, file)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def update(self, level):
        if not isinstance(level, int) or not 0 <= level <= 100:
            raise ValueError("Battery level must be 0..100")

        previous = self._read()

        if level <= 10:
            current = "critical"
        elif level <= 20:
            current = "low"
        elif level > 25:
            current = "normal"
        else:
            current = previous

        if current == previous:
            return False

        if current == "critical":
            self.send(level, "critical")
        elif current == "low" and previous == "normal":
            self.send(level, "normal")

        self._write(current)
        return current in ("low", "critical")

    def remind(self, level: int, charging: bool | None) -> bool:
        """Send a reminder only when discharge is confirmed."""
        if not isinstance(level, int) or not 0 <= level <= 100:
            raise ValueError("Battery level must be 0..100")

        if charging is not False or level > 15:
            return False

        urgency = "critical" if level <= 10 else "normal"
        self.send(level, urgency)
        return True
