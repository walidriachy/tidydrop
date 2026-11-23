"""The icon by the clock (Windows) / in the menu bar (macOS) and its menu."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from pathlib import Path

from . import APP_NAME, autostart
from .config import load_settings, rules_path, save_settings, ensure_rules_file
from .icons import make_icon
from .organizer import Organizer
from .paths import launch_self, open_in_system
from .watcher import Watcher

log = logging.getLogger(__name__)


def _mac_notify(title: str, message: str) -> None:
    script = (f"display notification {json.dumps(message, ensure_ascii=False)} "
              f"with title {json.dumps(title, ensure_ascii=False)}")
    subprocess.run(["osascript", "-e", script], capture_output=True)


def run_tray(org: Organizer, watcher: Watcher, config_folder: Path, startup_problem: str | None = None,
             quit_hooks: list | None = None) -> None:
    import pystray
    from pystray import Menu, MenuItem as Item

    icon = pystray.Icon("tidydrop", make_icon(64), APP_NAME)
    if quit_hooks is not None:
        quit_hooks.append(icon.stop)  # lets the installer close the app before an update

    def notify(title: str, message: str) -> None:
        if not org.cfg.settings.get("notifications", True):
            return
        try:
            if sys.platform == "darwin":
                _mac_notify(title, message)
            else:
                icon.notify(message, title)
        except Exception:
            log.debug("Notification failed", exc_info=True)

    org.notifier = notify
    watcher.notify = notify

    def refresh() -> None:
        icon.icon = make_icon(64, paused=watcher.paused)
        state = "paused" if watcher.paused else f"watching {org.cfg.watch_folder.name}"
        icon.title = f"{APP_NAME} - {state}"
        icon.update_menu()

    def toggle_pause(_icon, _item) -> None:
        watcher.paused = not watcher.paused
        refresh()

    def toggle_preview(_icon, _item) -> None:
        settings = load_settings(config_folder)
        settings["dry_run"] = not settings.get("dry_run")
        save_settings(settings, config_folder)
        org.cfg.settings["dry_run"] = settings["dry_run"]
        notify(APP_NAME, "Preview mode on - files will NOT be moved. See Settings > Activity log."
               if settings["dry_run"] else "Preview mode off - files are organized again.")

    def organize_now(_icon, _item) -> None:
        def work() -> None:
            messages = org.organize_existing()
            notify(APP_NAME, f"Organized {len(messages)} file(s)." if messages else "Nothing to organize.")
        threading.Thread(target=work, daemon=True).start()

    def undo_last(_icon, _item) -> None:
        notify("Undo", org.undo())

    def open_downloads(_icon, _item) -> None:
        open_in_system(org.cfg.organize_root)

    def open_settings(_icon, _item) -> None:
        launch_self("--settings", "--config-dir", str(config_folder))

    def edit_rules(_icon, _item) -> None:
        ensure_rules_file(config_folder)
        open_in_system(rules_path(config_folder))

    def toggle_autostart(_icon, _item) -> None:
        try:
            if autostart.is_enabled():
                autostart.disable()
            else:
                autostart.enable()
        except OSError as exc:
            notify(APP_NAME, f"Could not change start at login: {exc}")
        icon.update_menu()

    def quit_app(_icon, _item) -> None:
        icon.stop()

    icon.menu = Menu(
        Item(lambda _item: f"Watching: {org.cfg.watch_folder}", None, enabled=False),
        Menu.SEPARATOR,
        Item("Settings and activity log...", open_settings, default=True),
        Item("Organize files already in Downloads", organize_now),
        Item("Undo last action", undo_last),
        Item("Open Downloads", open_downloads),
        Item("Edit rules...", edit_rules),
        Menu.SEPARATOR,
        Item("Pause", toggle_pause, checked=lambda _item: watcher.paused),
        Item("Preview mode (don't move anything)", toggle_preview,
             checked=lambda _item: bool(org.cfg.settings.get("dry_run"))),
        Item("Start at login", toggle_autostart, checked=lambda _item: autostart.is_enabled(),
             visible=autostart.is_supported()),
        Menu.SEPARATOR,
        Item("Quit", quit_app),
    )

    first_run = org.state.last_run == 0

    def setup(_icon) -> None:
        _icon.visible = True
        refresh()
        if startup_problem:
            notify("Rules file has a mistake", f"Using the built-in rules for now. {startup_problem}"[:250])
        elif first_run:
            where = "menu bar" if sys.platform == "darwin" else "icon by the clock"
            notify(APP_NAME, f"Running. New downloads will be sorted automatically. Click the {where} for options.")

    icon.run(setup=setup)
