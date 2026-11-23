"""Spotting a download that's an exact copy of something already organized.

Files are first compared by size (cheap); only same-size files get hashed."""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from pathlib import Path

from .paths import same_path

log = logging.getLogger(__name__)


class DuplicateFinder:
    def __init__(self, root: Path, incoming_folder: Path, max_bytes: int):
        self.root = root
        self.incoming = incoming_folder  # files lying directly here are new downloads, not "originals"
        self.max_bytes = max_bytes
        self._by_size: dict[int, set[str]] = {}
        self._hashes: dict[str, tuple[float, int, str]] = {}
        self._lock = threading.Lock()

    def build(self) -> None:
        count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                if same_path(dirpath, self.incoming):
                    continue
                for filename in filenames:
                    if filename.startswith("."):
                        continue
                    full = os.path.join(dirpath, filename)
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        continue
                    self.add(Path(full), size)
                    count += 1
        except Exception:
            log.exception("Could not index %s for duplicates", self.root)
        log.info("Duplicate check ready (%d files indexed)", count)

    def add(self, path: Path, size: int) -> None:
        if 0 < size <= self.max_bytes:
            with self._lock:
                self._by_size.setdefault(size, set()).add(str(path))

    def remove(self, path: Path) -> None:
        with self._lock:
            for paths in self._by_size.values():
                paths.discard(str(path))

    def find(self, path: Path, size: int) -> Path | None:
        """An existing file with exactly the same content, or None."""
        if not 0 < size <= self.max_bytes:
            return None
        with self._lock:
            candidates = [Path(p) for p in self._by_size.get(size, ()) if not same_path(p, path)]
        if not candidates:
            return None
        digest = self._hash(path)
        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.stat().st_size == size and self._hash(candidate) == digest:
                    return candidate
            except OSError:
                continue
        return None

    def _hash(self, path: Path) -> str:
        st = path.stat()
        key = str(path)
        cached = self._hashes.get(key)
        if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
            return cached[2]
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        value = digest.hexdigest()
        self._hashes[key] = (st.st_mtime, st.st_size, value)
        return value
