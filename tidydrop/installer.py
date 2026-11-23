"""Windows installer and uninstaller, built into the app itself.

Double-clicking "TidyDrop Setup.exe" shows a small Install window.
It installs for the current user only (no administrator password):
  - the app     -> %LOCALAPPDATA%\\Programs\\TidyDrop\\TidyDrop.exe
  - Start menu shortcut (and optionally a desktop shortcut)
  - "Start at login" (optional)
  - an entry in Settings > Apps > Installed apps, with Uninstall
Running a newer Setup updates the installed copy in place.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import APP_NAME, __version__, autostart
from .paths import INSTANCE_PORT, NO_WINDOW, app_data_dir, same_path

INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Programs" / APP_NAME
INSTALLED_EXE = INSTALL_DIR / f"{APP_NAME}.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TidyDrop"
CSIDL_PROGRAMS = 0x02            # Start menu > Programs (this user)
CSIDL_DESKTOPDIRECTORY = 0x10    # Desktop (follows OneDrive redirection)
DETACHED = 0x00000008            # DETACHED_PROCESS


def _special_folder(csidl: int) -> Path:
    import ctypes

    buffer = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer)
    return Path(buffer.value)


def shortcut_paths() -> list[Path]:
    return [
        _special_folder(CSIDL_PROGRAMS) / f"{APP_NAME}.lnk",
        _special_folder(CSIDL_DESKTOPDIRECTORY) / f"{APP_NAME}.lnk",
    ]


def running_installed_copy() -> bool:
    return same_path(sys.executable, INSTALLED_EXE)


def _make_shortcut(link: Path, target: Path) -> None:
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:DO_LINK);"
        "$s.TargetPath=$env:DO_TARGET;$s.WorkingDirectory=$env:DO_DIR;"
        "$s.IconLocation=$env:DO_TARGET+',0';$s.Description='Keeps your Downloads folder tidy';$s.Save()"
    )
    env = {**os.environ, "DO_LINK": str(link), "DO_TARGET": str(target), "DO_DIR": str(target.parent)}
    link.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   env=env, check=True, capture_output=True, creationflags=NO_WINDOW, timeout=60)


def _exe_unlocked(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        with open(path, "r+b"):
            return True
    except OSError:
        return False


def stop_running_app(timeout: float = 10) -> None:
    """Ask a running copy to quit (it listens on a local-only port)."""
    try:
        with socket.create_connection(("127.0.0.1", INSTANCE_PORT), timeout=2) as conn:
            conn.sendall(b"quit")
    except OSError:
        return  # not running
    deadline = time.time() + timeout
    while time.time() < deadline and not _exe_unlocked(INSTALLED_EXE):
        time.sleep(0.3)
    time.sleep(0.5)


def _register_uninstall(exe: Path) -> None:
    import winreg

    size_kb = max(1, exe.stat().st_size // 1024)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        for name, value in {
            "DisplayName": APP_NAME,
            "DisplayVersion": __version__,
            "Publisher": APP_NAME,
            "DisplayIcon": f'"{exe}",0',
            "InstallLocation": str(exe.parent),
            "UninstallString": f'"{exe}" --uninstall',
            "QuietUninstallString": f'"{exe}" --uninstall --quiet',
        }.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name, value in {"NoModify": 1, "NoRepair": 1, "EstimatedSize": size_kb}.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def install(start_at_login: bool, desktop_shortcut: bool) -> Path:
    source = Path(sys.executable)
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    if not same_path(source, INSTALLED_EXE):
        stop_running_app()
        if INSTALLED_EXE.exists():
            try:
                INSTALLED_EXE.unlink()
            except PermissionError:  # still running - Windows allows renaming it out of the way
                old = INSTALLED_EXE.with_suffix(".old")
                old.unlink(missing_ok=True)
                INSTALLED_EXE.rename(old)
        shutil.copy2(source, INSTALLED_EXE)
    start_menu, desktop = shortcut_paths()
    _make_shortcut(start_menu, INSTALLED_EXE)
    if desktop_shortcut:
        _make_shortcut(desktop, INSTALLED_EXE)
    else:
        desktop.unlink(missing_ok=True)
    _register_uninstall(INSTALLED_EXE)
    autostart.set_enabled(start_at_login, command=[str(INSTALLED_EXE)])
    return INSTALLED_EXE


def cleanup_after_update() -> None:
    try:
        INSTALLED_EXE.with_suffix(".old").unlink(missing_ok=True)
    except OSError:
        pass


def uninstall(remove_settings: bool = False) -> None:
    import winreg

    stop_running_app()
    autostart.disable()
    for link in shortcut_paths():
        link.unlink(missing_ok=True)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        pass
    if remove_settings:
        shutil.rmtree(app_data_dir(), ignore_errors=True)
    if INSTALL_DIR.name == APP_NAME and INSTALL_DIR.parent.name == "Programs":
        # This program may be running from that folder - remove it a few seconds after we exit.
        subprocess.Popen(
            f'cmd /c ping 127.0.0.1 -n 4 >nul & rmdir /s /q "{INSTALL_DIR}"',
            cwd=os.environ.get("TEMP") or str(Path.home()),
            creationflags=DETACHED | NO_WINDOW,
        )


def _window(title: str):
    import tkinter as tk

    root = tk.Tk()
    root.title(title)
    try:
        from PIL import ImageTk

        from .icons import make_icon

        root._icon = ImageTk.PhotoImage(make_icon(64))
        root.iconphoto(True, root._icon)
    except Exception:
        pass
    return root


def run_installer() -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    updating = INSTALLED_EXE.exists()
    verb = "Update" if updating else "Install"
    root = _window(f"{verb} {APP_NAME}")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=f"{APP_NAME} {__version__}", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    ttk.Label(
        frame, justify="left", wraplength=440,
        text=("Sorts every new download into the right folder and gives it a clear name.\n\n"
              "Installs just for you - no administrator password needed.\n"
              f"Location: {INSTALL_DIR}"),
    ).pack(anchor="w", pady=(8, 14))

    v_login = tk.BooleanVar(value=True)
    v_desktop = tk.BooleanVar(value=shortcut_paths()[1].exists())
    v_open = tk.BooleanVar(value=True)
    ttk.Checkbutton(frame, text="Start automatically when I log in (recommended)", variable=v_login).pack(anchor="w")
    ttk.Checkbutton(frame, text="Add a desktop shortcut", variable=v_desktop).pack(anchor="w")
    ttk.Checkbutton(frame, text=f"Open {APP_NAME} when done", variable=v_open).pack(anchor="w")

    result = {"code": 1}

    def do_install() -> None:
        root.config(cursor="watch")
        root.update()
        try:
            exe = install(bool(v_login.get()), bool(v_desktop.get()))
        except Exception as exc:
            root.config(cursor="")
            messagebox.showerror(APP_NAME, f"Installation failed:\n{exc}")
            return
        if v_open.get():
            subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=DETACHED)
        messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME} is {'updated' if updating else 'installed'}.\n\n"
            "- It's in the Start menu.\n"
            "- Its icon sits by the clock (click ^ if hidden). Right-click it for options.\n"
            "- To remove it: Settings > Apps > Installed apps.",
        )
        result["code"] = 0
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(18, 0))
    ttk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right")
    install_button = ttk.Button(buttons, text=verb, command=do_install)
    install_button.pack(side="right", padx=8)
    install_button.focus_set()
    root.bind("<Return>", lambda _e: do_install())
    root.lift()
    root.attributes("-topmost", True)
    root.after(400, lambda: root.attributes("-topmost", False))
    root.mainloop()
    return result["code"]


def run_uninstaller(quiet: bool = False) -> int:
    if quiet:
        uninstall(remove_settings=False)
        return 0
    from tkinter import messagebox

    root = _window(f"Uninstall {APP_NAME}")
    root.withdraw()
    if not messagebox.askyesno(APP_NAME, f"Remove {APP_NAME} from this computer?\n\n"
                                         "Files it already organized stay where they are."):
        return 1
    remove_settings = messagebox.askyesno(
        APP_NAME, "Also delete your settings, rules and activity log?\n\nChoose No to keep them for a later reinstall.",
        default="no")
    uninstall(remove_settings)
    messagebox.showinfo(APP_NAME, f"{APP_NAME} has been removed.")
    root.destroy()
    return 0
