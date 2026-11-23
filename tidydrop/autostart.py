"""Start at login: a 'Run' entry for the current user on Windows, a
LaunchAgent on macOS. Nothing here needs administrator rights."""
from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

from . import APP_NAME
from .paths import FROZEN, PROJECT_ROOT

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AGENT_LABEL = "com.tidydrop.agent"
LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"


def is_supported() -> bool:
    return sys.platform in ("win32", "darwin")


def launch_command() -> list[str]:
    if FROZEN:
        return [sys.executable]
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.with_name("pythonw.exe").exists():
        exe = exe.with_name("pythonw.exe")
    return [str(exe), str(PROJECT_ROOT / "run.pyw")]


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_NAME)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return LAUNCH_AGENT.exists()
    return False


def enable(command: list[str] | None = None) -> None:
    command = command or launch_command()
    if sys.platform == "win32":
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
    elif sys.platform == "darwin":
        LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
        with open(LAUNCH_AGENT, "wb") as handle:
            plistlib.dump(
                {"Label": AGENT_LABEL, "ProgramArguments": command, "RunAtLoad": True, "ProcessType": "Interactive"},
                handle,
            )
    else:
        raise OSError("Start at login is only available on Windows and macOS")


def disable() -> None:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
    elif sys.platform == "darwin":
        LAUNCH_AGENT.unlink(missing_ok=True)


def set_enabled(on: bool, command: list[str] | None = None) -> None:
    if on:
        enable(command)  # always rewrite, so the path stays correct after an update
    elif is_enabled():
        disable()
