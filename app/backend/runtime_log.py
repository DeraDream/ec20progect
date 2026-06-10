import os
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path


class RuntimeLog:
    def __init__(self, path=None, max_lines=1000, max_bytes=5 * 1024 * 1024):
        self.path = Path(path) if path else None
        self.max_bytes = max_bytes
        self._lines = deque(maxlen=max_lines)
        self._sequence = 0
        self._condition = threading.Condition()
        self._file_lock = threading.Lock()

    def write(self, source, message, level="INFO"):
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        clean = str(message).replace("\r", "").rstrip("\n")
        for part in clean.split("\n") or [""]:
            line = f"{timestamp} [{level}] [{source}] {part}"
            print(line, file=sys.stdout, flush=True)
            self._write_file(line)
            with self._condition:
                self._sequence += 1
                self._lines.append((self._sequence, line))
                self._condition.notify_all()

    def snapshot(self, limit=300):
        with self._condition:
            return [line for _, line in list(self._lines)[-limit:]]

    def wait(self, after, timeout=15):
        with self._condition:
            if self._sequence <= after:
                self._condition.wait(timeout)
            return [(sequence, line) for sequence, line in self._lines if sequence > after]

    def latest_sequence(self):
        with self._condition:
            return self._sequence

    def _write_file(self, line):
        if not self.path:
            return
        try:
            with self._file_lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if self.path.exists() and self.path.stat().st_size >= self.max_bytes:
                    backup = self.path.with_suffix(self.path.suffix + ".1")
                    if backup.exists():
                        backup.unlink()
                    os.replace(self.path, backup)
                with self.path.open("a", encoding="utf-8") as output:
                    output.write(line + "\n")
        except OSError as exc:
            print(f"runtime log file error: {exc}", file=sys.stderr, flush=True)
