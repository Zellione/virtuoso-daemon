"""Exclusive process lock for Virtuoso hardware access."""
import fcntl
import os
from pathlib import Path


class LockError(RuntimeError):
    pass


class ControllerLock:
    def __init__(self, path=None):
        if path is None:
            runtime = os.environ.get("XDG_RUNTIME_DIR")
            if not runtime:
                raise LockError("XDG_RUNTIME_DIR is not set")
            path = Path(runtime) / "virtuoso-daemon" / "controller.lock"

        self.path = Path(path)
        self.fd = None

    def __enter__(self):
        if self.fd is not None:
            raise LockError("Lock already acquired")

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        fd = os.open(
            self.path,
            os.O_CREAT | os.O_RDWR | os.O_CLOEXEC,
            0o600,
        )

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise LockError(
                "Another Virtuoso controller is running"
            ) from exc

        self.fd = fd
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None
