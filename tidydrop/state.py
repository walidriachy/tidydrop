"""Small bits of memory shared between the background app and the Settings
window: when the app last ran, and files the user put back on purpose
(after an Undo) that must be left alone."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path


def _key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


class State:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("last_run", 0.0)
        data.setdefault("ignored", {})
        return data

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    @property
    def last_run(self) -> float:
        return float(self._read().get("last_run") or 0)

    def set_last_run(self, ts: float) -> None:
        with self._lock:
            data = self._read()
            data["last_run"] = ts
            self._write(data)

    def ignore(self, path: Path) -> None:
        with self._lock:
            data = self._read()
            data["ignored"] = {k: v for k, v in data["ignored"].items() if os.path.exists(k)}
            try:
                data["ignored"][_key(path)] = path.stat().st_mtime
            except OSError:
                return
            self._write(data)

    def is_ignored(self, path: Path) -> bool:
        mtime = self._read()["ignored"].get(_key(path))
        if mtime is None:
            return False
        try:
            return abs(path.stat().st_mtime - float(mtime)) < 2  # changed since? then it's fair game again
        except OSError:
            return False
