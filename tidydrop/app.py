"""Entry point: background app with tray icon, the Windows installer, and a
few command-line modes."""
from __future__ import annotations

import argparse
import logging
import socket
import subprocess
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from . import APP_NAME, __version__
from .config import ConfigError, default_config, load_config
from .journal import Journal
from .paths import FROZEN, INSTANCE_PORT, app_data_dir, launch_self
from .state import State

log = logging.getLogger("tidydrop")


def _say(text: str) -> None:
    if sys.stdout is not None:  # no console when started without one
        print(text)


def _setup_logging(folder: Path, verbose: bool) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(folder / "organizer.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    if sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        root.addHandler(stream)
    for noisy in ("watchdog", "PIL", "pypdf"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tidydrop", description=f"{APP_NAME} - keeps Downloads tidy.")
    parser.add_argument("--settings", action="store_true", help="open the Settings window")
    parser.add_argument("--once", action="store_true", help="organize files already in Downloads, then exit")
    parser.add_argument("--dry-run", action="store_true", help="with --once: only show what would happen")
    parser.add_argument("--no-tray", action="store_true", help="run without a tray icon (Ctrl+C to stop)")
    parser.add_argument("--undo", action="store_true", help="undo the last action, then exit")
    parser.add_argument("--config-dir", type=Path, help="use another folder for settings, rules and logs")
    parser.add_argument("--install", action="store_true", help="show the installer (Windows app only)")
    parser.add_argument("--uninstall", action="store_true", help="remove the installed app (Windows app only)")
    parser.add_argument("--quiet", action="store_true", help="with --uninstall: no questions")
    parser.add_argument("--verbose", action="store_true", help="more detail in the log")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser.parse_args(argv)


def _single_instance() -> socket.socket | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", INSTANCE_PORT))
        sock.listen(2)
        return sock
    except OSError:
        sock.close()
        return None


def _serve_commands(sock: socket.socket, quit_hooks: list[Callable[[], None]]) -> None:
    """The installer sends 'quit' here before replacing the app during an update."""
    while True:
        try:
            conn, _addr = sock.accept()
        except OSError:
            return  # socket closed - app is stopping
        with conn:
            try:
                conn.settimeout(2)
                data = conn.recv(16)
            except OSError:
                continue
        if data.startswith(b"quit"):
            log.info("Asked to quit (installer/uninstaller)")
            for hook in list(quit_hooks):
                try:
                    hook()
                except Exception:
                    log.debug("quit hook failed", exc_info=True)


def _mac_first_run_login_prompt(state: State) -> None:
    """Packaged Mac app, first start: offer 'start at login' (like the Windows installer does)."""
    from . import autostart

    if state.last_run or autostart.is_enabled():
        return
    script = (f'display dialog "Start {APP_NAME} automatically when you log in?\\n\\n'
              f'Its icon lives in the menu bar." buttons {{"Not now", "Start at login"}} '
              f'default button "Start at login" with title "{APP_NAME}"')
    try:
        out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=300)
        if "Start at login" in out.stdout:
            autostart.enable()
    except (OSError, subprocess.SubprocessError):
        log.debug("Login prompt failed", exc_info=True)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    folder = (args.config_dir or app_data_dir()).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    _setup_logging(folder, args.verbose)

    # ---- Windows app: install / uninstall
    if sys.platform == "win32" and FROZEN:
        from . import installer

        if args.uninstall:
            return installer.run_uninstaller(args.quiet)
        other_mode = args.once or args.undo or args.settings or args.no_tray or args.config_dir
        if args.install or (not installer.running_installed_copy() and not other_mode):
            return installer.run_installer()
        installer.cleanup_after_update()
    elif args.install or args.uninstall:
        _say("Install/uninstall is part of the packaged Windows app. On a Mac, drag the app to Applications.")
        return 1

    if args.settings:
        from .settings_ui import run_settings

        run_settings(folder)
        return 0

    problem = None
    try:
        cfg = load_config(folder)
    except ConfigError as exc:
        if args.once or args.undo or args.no_tray:
            _say(f"Problem in your settings or rules: {exc}")
            return 2
        problem = str(exc)
        log.error("Using built-in rules: %s", exc)
        cfg = default_config(folder)

    from .organizer import Organizer

    state = State(folder / "state.json")
    org = Organizer(cfg, Journal(folder / "activity.jsonl"), state)

    if args.undo:
        _say(org.undo())
        return 0

    if args.once:
        if args.dry_run:
            cfg.settings["dry_run"] = True
        org.dupes.build()
        messages = org.organize_existing()
        _say("\n".join(messages) if messages else "Nothing to organize.")
        return 0

    guard = _single_instance()
    if guard is None:
        log.info("Already running - opening Settings instead")
        if not args.no_tray:
            launch_self("--settings", "--config-dir", str(folder))
        return 0

    if sys.platform == "darwin" and FROZEN and not args.no_tray:
        _mac_first_run_login_prompt(state)

    from .watcher import Watcher

    stop = threading.Event()
    quit_hooks: list[Callable[[], None]] = [stop.set]
    threading.Thread(target=_serve_commands, args=(guard, quit_hooks), daemon=True, name="commands").start()

    watcher = Watcher(org, folder)
    watcher.start()
    log.info("%s %s started", APP_NAME, __version__)
    try:
        if args.no_tray:
            _say(f"Watching {cfg.watch_folder} - press Ctrl+C to stop.")
            while not stop.wait(1):
                pass
        else:
            from .tray import run_tray

            run_tray(org, watcher, folder, startup_problem=problem, quit_hooks=quit_hooks)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        guard.close()
        log.info("%s stopped", APP_NAME)
    return 0
