"""The heart of the app: decides what to do with one downloaded file and does it."""
from __future__ import annotations

import logging
import shutil
import tarfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Callable

from send2trash import send2trash

from . import APP_NAME
from .ai import OllamaClient
from .archive import ArchiveError, can_extract, extract_archive
from .classify import decide
from .config import Config
from .dupes import DuplicateFinder
from .journal import Journal
from .metadata import IGNORED_NAMES, TEMP_EXTENSIONS, FileInfo, gather, is_temp_name
from .naming import build_filename, clean_title, sanitize_component, sanitize_filename, unique_path
from .paths import TRASH_NAME, same_path
from .state import State

log = logging.getLogger(__name__)
Notifier = Callable[[str, str], None]


def send_to_trash(path: Path) -> None:
    """Recycle Bin / Trash - never a permanent delete."""
    send2trash(str(path))


class Organizer:
    def __init__(self, cfg: Config, journal: Journal, state: State, notifier: Notifier | None = None):
        self.cfg = cfg
        self.journal = journal
        self.state = state
        self.notifier = notifier
        self.lock = threading.RLock()
        self.dupes = self._make_dupes(cfg)

    # ----------------------------------------------------------- setup
    @staticmethod
    def _make_dupes(cfg: Config) -> DuplicateFinder:
        limit = int(cfg.settings.get("duplicate_max_mb", 2048)) * 1024 * 1024
        return DuplicateFinder(cfg.organize_root, cfg.watch_folder, limit)

    def set_config(self, cfg: Config) -> None:
        with self.lock:
            root_changed = not same_path(cfg.organize_root, self.cfg.organize_root)
            self.cfg = cfg
            if root_changed:
                self.dupes = self._make_dupes(cfg)
                threading.Thread(target=self.dupes.build, daemon=True).start()

    # ----------------------------------------------------------- which files
    def is_candidate(self, path: Path) -> bool:
        name = path.name
        if name.startswith(".") or name.lower() in IGNORED_NAMES or is_temp_name(name):
            return False
        if not same_path(path.parent, self.cfg.watch_folder):
            return False
        try:
            if not path.is_file():
                return False
        except OSError:
            return False
        return not self.state.is_ignored(path)

    @staticmethod
    def has_pending_sibling(path: Path) -> bool:
        """Firefox creates 'file.zip' AND 'file.zip.part' while downloading."""
        return any(Path(f"{path}.{ext}").exists() for ext in TEMP_EXTENSIONS)

    # ----------------------------------------------------------- helpers
    def _rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.cfg.organize_root).as_posix()
        except ValueError:
            return str(path)

    @staticmethod
    def _preview(message: str) -> str:
        log.info("[preview] %s", message)
        return message

    def _done(self, message: str, quiet: bool) -> str:
        log.info(message)
        if not quiet and self.notifier and self.cfg.settings.get("notifications", True):
            try:
                self.notifier(APP_NAME, message)
            except Exception:
                log.debug("Notification failed", exc_info=True)
        return message

    def _ai_title(self, info: FileInfo) -> str | None:
        ai = self.cfg.settings.get("ai") or {}
        if not ai.get("enabled") or not info.text.strip():
            return None
        client = OllamaClient(
            str(ai.get("url") or "http://127.0.0.1:11434"),
            str(ai.get("model") or "llama3.2"),
            float(ai.get("timeout_seconds") or 60),
        )
        return client.suggest_title(info.name, info.source_domain, info.category, info.text)

    # ----------------------------------------------------------- the pipeline
    def process(self, path: Path, quiet: bool = False) -> str | None:
        """Organize one file. Returns a short description, or None if the file
        isn't ours to touch. A locked file raises PermissionError (retry later)."""
        with self.lock:
            if not self.is_candidate(path):
                return None
            settings = self.cfg.settings
            dry = bool(settings.get("dry_run"))
            info = gather(path, self.cfg)
            decision = decide(info, self.cfg)
            dest_dir = self.cfg.organize_root / decision.dest

            if settings.get("duplicates", "trash") == "trash":
                original = self.dupes.find(path, info.size)
                if original is not None:
                    where = self._rel(original)
                    if dry:
                        return self._preview(f"Would remove '{path.name}' - it's a copy of {where}")
                    send_to_trash(path)
                    self.journal.add({
                        "file": path.name, "rule": "Duplicate",
                        "summary": f"Copy of {where} - moved to {TRASH_NAME}",
                        "ops": [{"op": "trash", "path": str(path)}],
                    })
                    return self._done(f"Removed duplicate '{path.name}' (already in {where})", quiet)

            if settings.get("auto_extract", True) and can_extract(path):
                message = self._extract(path, info, dest_dir, dry, quiet)
                if message:
                    return message

            if decision.rename:
                new_name = build_filename(info, decision.template, settings.get("date_format") or "%Y-%m-%d",
                                          self._ai_title(info))
            else:
                new_name = sanitize_filename(path.name)
            target = unique_path(dest_dir, new_name)
            reason = decision.rule or f"category {info.category}"
            if dry:
                return self._preview(f"Would move '{path.name}' -> {self._rel(target)}  [{reason}]")

            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
            self.dupes.add(target, info.size)
            action = {
                "file": path.name,
                "rule": decision.rule or f"Category: {info.category}",
                "summary": f"-> {self._rel(target)}",
                "ops": [{"op": "move", "src": str(path), "dst": str(target)}],
            }
            if decision.expire_days:
                action["expire_at"] = time.time() + decision.expire_days * 86400
            self.journal.add(action)
            return self._done(f"'{path.name}' -> {self._rel(target)}", quiet)

    def _extract(self, path: Path, info: FileInfo, dest_dir: Path, dry: bool, quiet: bool) -> str | None:
        settings = self.cfg.settings
        folder_name = sanitize_component(clean_title(info.stem)) or "Extracted"
        if dry:
            return self._preview(f"Would unzip '{path.name}' into {self._rel(dest_dir / folder_name)}")
        try:
            out = extract_archive(path, dest_dir, folder_name, int(settings.get("max_extract_mb", 4096)) * 1024 * 1024)
        except (ArchiveError, zipfile.BadZipFile, tarfile.TarError, OSError, RuntimeError, EOFError) as exc:
            log.warning("Could not unzip %s (%s) - moving it instead", path.name, exc)
            return None
        ops = [{"op": "extract", "src": str(path), "dst": str(out)}]
        if settings.get("trash_archive_after_extract", True):
            send_to_trash(path)
            ops.append({"op": "trash", "path": str(path)})
            kept = f"zip moved to {TRASH_NAME}"
        else:
            target = unique_path(dest_dir, sanitize_filename(path.name))
            shutil.move(str(path), str(target))
            ops.append({"op": "move", "src": str(path), "dst": str(target)})
            kept = f"zip kept in {self._rel(dest_dir)}"
        self.journal.add({
            "file": path.name, "rule": "Unzipped",
            "summary": f"Unzipped -> {self._rel(out)} ({kept})", "ops": ops,
        })
        return self._done(f"Unzipped '{path.name}' -> {self._rel(out)}", quiet)

    # ----------------------------------------------------------- bulk jobs
    def organize_existing(self, newer_than: float | None = None) -> list[str]:
        """Organize files already lying in the watched folder."""
        messages: list[str] = []
        try:
            entries = sorted(self.cfg.watch_folder.iterdir(), key=lambda p: p.name.lower())
        except OSError as exc:
            log.error("Cannot read %s: %s", self.cfg.watch_folder, exc)
            return messages
        for path in entries:
            try:
                if newer_than is not None and path.stat().st_mtime <= newer_than:
                    continue
                if not self.is_candidate(path) or self.has_pending_sibling(path):
                    continue
                message = self.process(path, quiet=True)
            except Exception as exc:
                log.warning("Skipped %s: %s", path.name, exc)
                continue
            if message:
                messages.append(message)
        return messages

    def sweep_expired(self) -> list[str]:
        """Send files whose time limit has passed (e.g. old installers) to the bin."""
        removed: list[str] = []
        now = time.time()
        with self.lock:
            if self.cfg.settings.get("dry_run"):
                return removed
            actions = self.journal.actions()
            already = {a.get("expired_of") for a in actions if a.get("expired_of")}
            for action in actions:
                expire_at = action.get("expire_at")
                if action.get("undone") or not expire_at or expire_at > now or action["id"] in already:
                    continue
                for op in action.get("ops", []):
                    if op.get("op") != "move":
                        continue
                    path = Path(op["dst"])
                    if not path.exists():
                        continue
                    try:
                        send_to_trash(path)
                    except OSError as exc:
                        log.warning("Could not remove expired %s: %s", path.name, exc)
                        continue
                    self.dupes.remove(path)
                    self.journal.add({
                        "file": path.name, "rule": "Expired", "expired_of": action["id"],
                        "summary": f"Time limit reached - moved to {TRASH_NAME}",
                        "ops": [{"op": "trash", "path": str(path)}],
                    })
                    removed.append(path.name)
        if removed:
            log.info("Expired: %s", ", ".join(removed))
        return removed

    def undo(self, action_id: str | None = None) -> str:
        """Undo the newest action (or a specific one)."""
        with self.lock:
            actions = [a for a in self.journal.actions() if not a.get("undone") and a.get("ops")]
            if action_id:
                actions = [a for a in actions if a["id"] == action_id]
            if not actions:
                return "Nothing to undo."
            action = actions[-1]
            notes: list[str] = []
            for op in reversed(action["ops"]):
                kind = op.get("op")
                if kind == "move":
                    dst, src = Path(op["dst"]), Path(op["src"])
                    if not dst.exists():
                        notes.append(f"'{dst.name}' is no longer where it was put")
                        continue
                    back = src if not src.exists() else unique_path(src.parent, src.name)
                    back.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(back))
                    self.state.ignore(back)  # don't organize it straight away again
                    self.dupes.remove(dst)
                    notes.append(f"Put '{back.name}' back in {back.parent.name}")
                elif kind == "extract":
                    out = Path(op["dst"])
                    if out.exists():
                        send_to_trash(out)
                        notes.append(f"Removed unzipped folder '{out.name}'")
                elif kind == "trash":
                    gone = Path(op["path"])
                    if not gone.exists():
                        notes.append(f"Restore '{gone.name}' from the {TRASH_NAME} to get it back")
            self.journal.mark_undone(action["id"])
            message = "; ".join(notes) or "Undone."
            log.info("Undo %s: %s", action.get("file"), message)
            return message
