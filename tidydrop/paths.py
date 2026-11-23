"""Where the app keeps its own files, where the user's Downloads folder is,
and small helpers for opening things with the operating system."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import APP_NAME

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRASH_NAME = "Recycle Bin" if sys.platform == "win32" else "Trash"
FROZEN = bool(getattr(sys, "frozen", False))
INSTANCE_PORT = 47653  # local-only socket: stops a second copy running, and lets the installer ask the app to quit
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def app_data_dir() -> Path:
    """Folder for settings, rules, the activity log and app state."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def default_downloads_dir() -> Path:
    if sys.platform == "win32":
        found = _windows_known_downloads()
        if found:
            return found
    return Path.home() / "Downloads"


def _windows_known_downloads() -> Path | None:
    """Ask Windows for the real Downloads folder (users can move it to another drive)."""
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        folder_id = GUID.from_buffer_copy(uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}").bytes_le)
        out = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(folder_id), 0, None, ctypes.byref(out)
        )
        if result != 0:
            return None
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        return None


def same_path(a: Path | str, b: Path | str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def open_in_system(path: Path) -> None:
    """Open a file or folder the way a double-click would."""
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 - opening the user's own folder/file
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def self_command(*args: str) -> list[str]:
    """Command line that starts this app again (used for the Settings window)."""
    if FROZEN:
        return [sys.executable, *args]
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.name.lower() == "python.exe" and exe.with_name("pythonw.exe").exists():
        exe = exe.with_name("pythonw.exe")  # no black console window
    return [str(exe), "-m", "tidydrop", *args]


def launch_self(*args: str) -> None:
    subprocess.Popen(self_command(*args), cwd=None if FROZEN else str(PROJECT_ROOT))
