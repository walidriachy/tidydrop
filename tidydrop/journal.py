"""The activity log: every move, unzip and delete is written down so it can be
shown in the Settings window and undone."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path


class Journal:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _append(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def add(self, action: dict) -> dict:
        """action: {"file", "rule", "summary", "ops": [...], optional "expire_at"}"""
        record = {"id": uuid.uuid4().hex[:12], "ts": time.time(), **action}
        self._append(record)
        return record

    def mark_undone(self, action_id: str) -> None:
        self._append({"undo": action_id, "ts": time.time()})

    def actions(self) -> list[dict]:
        if not self.path.exists():
            return []
        records: list[dict] = []
        undone: set[str] = set()
        with self._lock, open(self.path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if "undo" in record:
                    undone.add(record["undo"])
                elif "id" in record:
                    records.append(record)
        for record in records:
            record["undone"] = record["id"] in undone
        return records
