"""Persistent recovery state for the Virtuoso controller.

This module performs filesystem operations only.
It never communicates with HID hardware.
"""

import json
import os
import tempfile
from pathlib import Path


class RecoveryError(RuntimeError):
    """Persistent recovery state could not be maintained."""


class RecoveryStore:
    VALID_STATES = {
        "recovery_required",
        "restore_commands_sent",
    }

    def __init__(self, path: Path):
        self.path = Path(path)

    @classmethod
    def default(cls):
        state_home = Path(
            os.environ.get(
                "XDG_STATE_HOME",
                str(Path.home() / ".local/state"),
            )
        )
        return cls(
            state_home
            / "virtuoso-daemon"
            / "recovery.json"
        )

    def read(self):
        if not self.path.exists():
            return None

        try:
            data = json.loads(
                self.path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise RecoveryError(
                "Cannot read recovery marker"
            ) from exc

        if (
            not isinstance(data, dict)
            or data.get("version") != 1
            or data.get("state") not in self.VALID_STATES
        ):
            raise RecoveryError(
                "Invalid recovery marker"
            )

        return data["state"]

    def _sync_directory(self):
        fd = os.open(
            self.path.parent,
            os.O_RDONLY | os.O_DIRECTORY,
        )
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def write(self, state: str):
        if state not in self.VALID_STATES:
            raise RecoveryError(
                f"Invalid recovery state: {state}"
            )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        fd = None
        temporary = None

        try:
            fd, name = tempfile.mkstemp(
                prefix=".recovery-",
                dir=self.path.parent,
            )
            temporary = Path(name)

            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = None
                json.dump(
                    {"version": 1, "state": state},
                    f,
                )
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())

            os.replace(temporary, self.path)
            temporary = None
            self._sync_directory()

        except OSError as exc:
            raise RecoveryError(
                "Cannot persist recovery marker"
            ) from exc

        finally:
            if fd is not None:
                os.close(fd)
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def mark_required(self):
        self.write("recovery_required")

    def mark_restore_sent(self):
        self.write("restore_commands_sent")

    def clear(self):
        """Clear only after explicitly verified recovery."""
        if self.path.exists():
            self.path.unlink()
            self._sync_directory()
