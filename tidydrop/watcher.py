"""Watches the Downloads folder and hands each file to the organizer once the
download has really finished (the file stopped growing and isn't locked)."""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import ConfigError, load_config, rules_path, settings_path
from .organizer import Organizer
from .paths import same_path

log = logging.getLogger(__name__)

GIVE_UP_AFTER = 600        # seconds a file may stay locked before we stop trying
RESCAN_EVERY = 30          # safety net for missed file-system events
SWEEP_EVERY = 3600         # expire old installers etc.


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "Watcher"):
        super().__init__()
        self.watcher = watcher

    def on_any_event(self, event) -> None:
        if getattr(event, "is_directory", False):
            return
        for attr in ("src_path", "dest_path"):
            raw = getattr(event, attr, None)
            if raw:
                self.watcher.notice(Path(os.fsdecode(raw)))


class Watcher:
    def __init__(self, organizer: Organizer, config_folder: Path,
                 notify: Callable[[str, str], None] | None = None):
        self.org = organizer
        self.folder = config_folder
        self.notify = notify or (lambda title, message: None)
        self.paused = False
        self._pending: dict[str, list] = {}   # key -> [path, last_size, last_change, first_seen]
        self._gave_up: dict[str, float] = {}  # key -> mtime we gave up on
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._observer = None
        self._thread: threading.Thread | None = None
        self._started_wall = time.time()
        self._cfg_mtimes = self._config_mtimes()

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        threading.Thread(target=self.org.dupes.build, daemon=True, name="dupes-index").start()
        self._start_observer()
        settings = self.org.cfg.settings
        last_run = self.org.state.last_run
        if settings.get("process_missed_on_start", True) and last_run > 0:
            self._queue_existing(newer_than=last_run - 5)  # downloads that arrived while the app was off
        self._thread = threading.Thread(target=self._loop, daemon=True, name="organizer")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
        if self._thread is not None:
            self._thread.join(timeout=10)
        self.org.state.set_last_run(time.time())

    def _start_observer(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        folder = self.org.cfg.watch_folder
        if not folder.is_dir():
            log.error("Watch folder %s does not exist", folder)
            self.notify("Folder not found", f"{folder} does not exist - check Settings.")
            return
        observer = Observer()
        observer.schedule(_Handler(self), str(folder), recursive=False)
        observer.start()
        self._observer = observer
        log.info("Watching %s", folder)

    # ----------------------------------------------------------- events
    @staticmethod
    def _key(path: Path) -> str:
        return os.path.normcase(os.path.abspath(path))

    def notice(self, path: Path) -> None:
        if not same_path(path.parent, self.org.cfg.watch_folder):
            return
        now = time.monotonic()
        key = self._key(path)
        with self._lock:
            entry = self._pending.get(key)
            if entry:
                entry[1], entry[2] = -1, now
            else:
                self._pending[key] = [path, -1, now, now]

    def _queue_existing(self, newer_than: float | None = None) -> None:
        try:
            entries = list(self.org.cfg.watch_folder.iterdir())
        except OSError:
            return
        for path in entries:
            try:
                if not path.is_file():
                    continue
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if newer_than is not None and mtime <= newer_than:
                continue
            if self._gave_up.get(self._key(path)) == mtime:
                continue
            if self._key(path) not in self._pending:
                self.notice(path)

    # ----------------------------------------------------------- main loop
    def _loop(self) -> None:
        last_cfg = last_scan = last_save = 0.0
        last_sweep = time.monotonic() - SWEEP_EVERY + 30  # first sweep 30 s after start
        while not self._stop.wait(1.0):
            now = time.monotonic()
            try:
                if now - last_cfg >= 2:
                    last_cfg = now
                    self._maybe_reload()
                if now - last_save >= 60:
                    last_save = now
                    self.org.state.set_last_run(time.time())
                if self.paused:
                    continue
                if now - last_scan >= RESCAN_EVERY:
                    last_scan = now
                    self._queue_existing(newer_than=max(self._started_wall, time.time() - 3600))
                self._process_ready(now)
                if now - last_sweep >= SWEEP_EVERY:
                    last_sweep = now
                    self.org.sweep_expired()
            except Exception:
                log.exception("Unexpected error in the organizer loop")

    def _drop(self, key: str) -> None:
        with self._lock:
            self._pending.pop(key, None)

    def _process_ready(self, now: float) -> None:
        with self._lock:
            items = list(self._pending.items())
        settle = max(1.0, float(self.org.cfg.settings.get("settle_seconds", 5)))
        for key, entry in items:
            path, last_size, since, first_seen = entry
            try:
                if not self.org.is_candidate(path):
                    self._drop(key)
                    continue
                if self.org.has_pending_sibling(path):
                    entry[1], entry[2] = -1, now
                    continue
                size = path.stat().st_size
            except OSError:
                self._drop(key)
                continue
            if size != last_size:
                entry[1], entry[2] = size, now
                continue
            wait = settle if size > 0 else max(settle, 30)  # empty placeholders get extra time
            if now - since < wait:
                continue
            try:
                self.org.process(path)
                self._drop(key)
            except PermissionError:
                if now - first_seen > GIVE_UP_AFTER:
                    log.warning("Giving up on %s - it stayed locked", path.name)
                    self._give_up(key, path)
                else:
                    entry[2] = now  # still in use (e.g. open in another app) - try again later
            except Exception:
                log.exception("Could not organize %s", path.name)
                self._give_up(key, path)

    def _give_up(self, key: str, path: Path) -> None:
        try:
            self._gave_up[key] = path.stat().st_mtime
        except OSError:
            pass
        self._drop(key)

    # ----------------------------------------------------------- config reload
    def _config_mtimes(self) -> tuple:
        out = []
        for path in (settings_path(self.folder), rules_path(self.folder)):
            try:
                out.append(path.stat().st_mtime)
            except OSError:
                out.append(None)
        return tuple(out)

    def _maybe_reload(self) -> None:
        mtimes = self._config_mtimes()
        if mtimes == self._cfg_mtimes:
            return
        self._cfg_mtimes = mtimes
        try:
            cfg = load_config(self.folder)
        except ConfigError as exc:
            log.error("Keeping the previous rules - %s", exc)
            self.notify("Rules file has a mistake", str(exc)[:200])
            return
        old_watch = self.org.cfg.watch_folder
        self.org.set_config(cfg)
        log.info("Settings reloaded")
        if not same_path(old_watch, cfg.watch_folder):
            self._start_observer()
