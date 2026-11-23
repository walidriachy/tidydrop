"""The Settings window. It runs as its own small process (`--settings`) so it
works the same on Windows and macOS; the background app picks up saved
changes within a couple of seconds."""
from __future__ import annotations

import copy
import threading
from datetime import datetime
from pathlib import Path

from . import APP_NAME, __version__, autostart
from .ai import OllamaClient
from .config import DEFAULT_SETTINGS, ConfigError, ensure_rules_file, load_config, load_settings, save_settings
from .journal import Journal
from .paths import TRASH_NAME, app_data_dir, default_downloads_dir, open_in_system
from .state import State

DUPLICATE_CHOICES = {"trash": f"Move exact copies to the {TRASH_NAME}", "keep": "Keep copies (rename them)"}


def run_settings(folder: Path | None = None) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    folder = folder or app_data_dir()
    journal = Journal(folder / "activity.jsonl")
    state = State(folder / "state.json")

    root = tk.Tk()
    root.title(f"{APP_NAME} {__version__} - Settings")
    root.geometry("820x620")
    root.minsize(700, 540)
    try:
        from PIL import ImageTk

        from .icons import make_icon

        root._icon = ImageTk.PhotoImage(make_icon(64))  # keep a reference
        root.iconphoto(True, root._icon)
    except Exception:
        pass

    try:
        settings = load_settings(folder)
    except ConfigError as exc:
        messagebox.showwarning(APP_NAME, f"settings.yaml has a mistake, showing defaults:\n{exc}")
        settings = copy.deepcopy(DEFAULT_SETTINGS)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))

    def hint(parent, text, row, col=1, span=2):
        ttk.Label(parent, text=text, foreground="#666").grid(row=row, column=col, columnspan=span, sticky="w", pady=(0, 6))

    # ================================================================ General
    general = ttk.Frame(notebook, padding=14)
    notebook.add(general, text="General")
    general.columnconfigure(1, weight=1)

    v_watch = tk.StringVar(value=settings["watch_folder"])
    v_into = tk.StringVar(value=settings["organize_into"])
    v_settle = tk.IntVar(value=settings["settle_seconds"])
    v_rename = tk.BooleanVar(value=settings["rename"])
    v_template = tk.StringVar(value=settings["name_template"])
    v_datefmt = tk.StringVar(value=settings["date_format"])
    v_extract = tk.BooleanVar(value=settings["auto_extract"])
    v_trash_zip = tk.BooleanVar(value=settings["trash_archive_after_extract"])
    v_expire = tk.IntVar(value=settings["installer_expire_days"])
    v_dupes = tk.StringVar(value=DUPLICATE_CHOICES.get(settings["duplicates"], DUPLICATE_CHOICES["trash"]))
    v_notify = tk.BooleanVar(value=settings["notifications"])
    v_missed = tk.BooleanVar(value=settings["process_missed_on_start"])
    v_dry = tk.BooleanVar(value=settings["dry_run"])
    v_login = tk.BooleanVar(value=autostart.is_enabled())

    def browse(var: tk.StringVar) -> None:
        chosen = filedialog.askdirectory(initialdir=var.get() or str(default_downloads_dir()))
        if chosen:
            var.set(chosen)

    row = 0
    for label, var, help_text in (
        ("Folder to watch", v_watch, f"Empty = your Downloads folder ({default_downloads_dir()})"),
        ("Sort into", v_into, "Empty = sub-folders inside the watched folder"),
    ):
        ttk.Label(general, text=label).grid(row=row, column=0, sticky="w")
        ttk.Entry(general, textvariable=var).grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(general, text="Browse...", command=lambda v=var: browse(v)).grid(row=row, column=2)
        hint(general, help_text, row + 1)
        row += 2

    ttk.Checkbutton(general, text="Rename files", variable=v_rename).grid(row=row, column=0, sticky="w")
    ttk.Entry(general, textvariable=v_template).grid(row=row, column=1, sticky="ew", padx=6)
    ttk.Entry(general, textvariable=v_datefmt, width=12).grid(row=row, column=2, sticky="w")
    hint(general, "Name template: {date} {title} {extra} {source} {original} {category}  |  right: date format", row + 1)
    row += 2

    ttk.Checkbutton(general, text="Unzip .zip / .tar files automatically", variable=v_extract).grid(
        row=row, column=0, columnspan=2, sticky="w")
    row += 1
    ttk.Checkbutton(general, text=f"...then move the zip to the {TRASH_NAME}", variable=v_trash_zip).grid(
        row=row, column=0, columnspan=2, sticky="w", padx=(20, 0))
    row += 1

    ttk.Label(general, text="Delete installers after").grid(row=row, column=0, sticky="w", pady=(8, 0))
    expire_box = ttk.Frame(general)
    expire_box.grid(row=row, column=1, sticky="w", padx=6, pady=(8, 0))
    ttk.Spinbox(expire_box, from_=0, to=365, width=6, textvariable=v_expire).pack(side="left")
    ttk.Label(expire_box, text=f"days (.exe .msi .dmg .pkg...)  0 = never.  They go to the {TRASH_NAME}.").pack(side="left", padx=6)
    row += 1

    ttk.Label(general, text="Duplicates").grid(row=row, column=0, sticky="w", pady=(8, 0))
    ttk.Combobox(general, textvariable=v_dupes, values=list(DUPLICATE_CHOICES.values()), state="readonly").grid(
        row=row, column=1, sticky="ew", padx=6, pady=(8, 0))
    row += 1

    ttk.Label(general, text="Wait before touching a file").grid(row=row, column=0, sticky="w", pady=(8, 0))
    settle_box = ttk.Frame(general)
    settle_box.grid(row=row, column=1, sticky="w", padx=6, pady=(8, 0))
    ttk.Spinbox(settle_box, from_=1, to=120, width=6, textvariable=v_settle).pack(side="left")
    ttk.Label(settle_box, text="seconds after the download stops growing").pack(side="left", padx=6)
    row += 1

    ttk.Separator(general).grid(row=row, column=0, columnspan=3, sticky="ew", pady=10)
    row += 1
    for text, var in (
        ("Show a notification for each organized file", v_notify),
        ("Sort downloads that arrived while the app was closed", v_missed),
        ("Preview mode - only log what would happen, don't move anything", v_dry),
    ):
        ttk.Checkbutton(general, text=text, variable=var).grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1
    login_check = ttk.Checkbutton(general, text="Start automatically when I log in", variable=v_login)
    login_check.grid(row=row, column=0, columnspan=3, sticky="w")
    if not autostart.is_supported():
        login_check.state(["disabled"])

    # ================================================================ AI
    ai_tab = ttk.Frame(notebook, padding=14)
    notebook.add(ai_tab, text="AI renaming")
    ai_tab.columnconfigure(1, weight=1)
    ai = settings["ai"]
    v_ai_on = tk.BooleanVar(value=ai["enabled"])
    v_ai_url = tk.StringVar(value=ai["url"])
    v_ai_model = tk.StringVar(value=ai["model"])
    v_ai_timeout = tk.IntVar(value=int(ai.get("timeout_seconds", 60)))
    v_ai_status = tk.StringVar(value="")

    ttk.Label(
        ai_tab, wraplength=740, justify="left",
        text=("Lets a local AI model (Ollama) read PDFs, Word, PowerPoint and text files and give them a "
              "clear name, e.g. 'scan0001.pdf' -> '2026-11-20 Adobe Creative Cloud Invoice November.pdf'.\n"
              "Everything stays on this computer. If Ollama isn't running, normal renaming is used.\n\n"
              "Setup: install Ollama from ollama.com, then run:   ollama pull llama3.2"),
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
    ttk.Checkbutton(ai_tab, text="Use AI to name documents", variable=v_ai_on).grid(row=1, column=0, columnspan=3, sticky="w")
    ttk.Label(ai_tab, text="Ollama address").grid(row=2, column=0, sticky="w", pady=4)
    ttk.Entry(ai_tab, textvariable=v_ai_url).grid(row=2, column=1, columnspan=2, sticky="ew", padx=6)
    ttk.Label(ai_tab, text="Model").grid(row=3, column=0, sticky="w", pady=4)
    model_box = ttk.Combobox(ai_tab, textvariable=v_ai_model)
    model_box.grid(row=3, column=1, sticky="ew", padx=6)
    ttk.Label(ai_tab, text="Timeout (seconds)").grid(row=4, column=0, sticky="w", pady=4)
    ttk.Spinbox(ai_tab, from_=5, to=600, width=6, textvariable=v_ai_timeout).grid(row=4, column=1, sticky="w", padx=6)

    def client() -> OllamaClient:
        return OllamaClient(v_ai_url.get().strip() or DEFAULT_SETTINGS["ai"]["url"], v_ai_model.get().strip(),
                            max(5, v_ai_timeout.get()))

    def in_background(work, done) -> None:
        def runner():
            try:
                result = work()
            except Exception as exc:  # shown to the user
                result = exc
            root.after(0, lambda: done(result))
        threading.Thread(target=runner, daemon=True).start()

    def refresh_models() -> None:
        v_ai_status.set("Looking for installed models...")

        def done(result):
            if isinstance(result, Exception):
                v_ai_status.set(f"Can't reach Ollama at {v_ai_url.get()} - is it running? ({result})")
            elif not result:
                v_ai_status.set("Ollama is running but has no models. Run:  ollama pull llama3.2")
            else:
                model_box["values"] = result
                if v_ai_model.get() not in result:
                    v_ai_model.set(result[0])
                v_ai_status.set(f"Found {len(result)} model(s).")
        in_background(lambda: client().list_models(), done)

    def test_ai() -> None:
        v_ai_status.set("Asking the model to name a sample invoice...")
        sample = ("Adobe Inc. INVOICE  Invoice number: IN-58213  Date: 20 Nov 2026  Bill to: Acme Ltd  "
                  "Creative Cloud All Apps - monthly plan  Total: $54.99  Amount paid: $54.99")

        def done(result):
            if isinstance(result, Exception) or not result:
                v_ai_status.set("No answer - check that Ollama is running and the model is downloaded.")
            else:
                v_ai_status.set(f"The model suggested:  {result}")
        in_background(lambda: client().suggest_title("scan0001.pdf", "adobe.com", "Documents", sample), done)

    ttk.Button(ai_tab, text="Find models", command=refresh_models).grid(row=3, column=2, sticky="w")
    ttk.Button(ai_tab, text="Test with a sample invoice", command=test_ai).grid(row=5, column=0, columnspan=2, sticky="w", pady=10)
    ttk.Label(ai_tab, textvariable=v_ai_status, wraplength=740, foreground="#1d4ed8").grid(row=6, column=0, columnspan=3, sticky="w")

    # ================================================================ Activity
    activity = ttk.Frame(notebook, padding=10)
    notebook.add(activity, text="Activity log")
    activity.columnconfigure(0, weight=1)
    activity.rowconfigure(0, weight=1)
    columns = ("when", "file", "rule", "result")
    tree = ttk.Treeview(activity, columns=columns, show="headings", selectmode="extended")
    for col, title, width in (("when", "When", 110), ("file", "Original file", 230),
                              ("rule", "Why", 150), ("result", "What happened", 330)):
        tree.heading(col, text=title)
        tree.column(col, width=width, anchor="w")
    tree.tag_configure("undone", foreground="#999")
    scroll = ttk.Scrollbar(activity, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")

    def refresh_activity() -> None:
        tree.delete(*tree.get_children())
        for action in reversed(journal.actions()[-500:]):
            when = datetime.fromtimestamp(action.get("ts", 0)).strftime("%d %b %H:%M")
            result = action.get("summary", "") + ("   (undone)" if action.get("undone") else "")
            tree.insert("", "end", iid=action["id"], values=(when, action.get("file", ""), action.get("rule", ""), result),
                        tags=("undone",) if action.get("undone") else ())

    def undo_selected() -> None:
        chosen = tree.selection()
        if not chosen:
            messagebox.showinfo(APP_NAME, "Select one or more lines first.")
            return
        try:
            cfg = load_config(folder)
        except ConfigError as exc:
            messagebox.showerror(APP_NAME, f"Fix rules.yaml first:\n{exc}")
            return
        from .organizer import Organizer

        organizer = Organizer(cfg, journal, state)
        notes = [organizer.undo(action_id) for action_id in chosen]
        refresh_activity()
        messagebox.showinfo("Undo", "\n".join(notes))

    buttons = ttk.Frame(activity)
    buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
    ttk.Button(buttons, text="Refresh", command=refresh_activity).pack(side="left")
    ttk.Button(buttons, text="Undo selected", command=undo_selected).pack(side="left", padx=6)
    ttk.Button(buttons, text="Open log file", command=lambda: open_in_system(folder / "organizer.log")
               if (folder / "organizer.log").exists() else None).pack(side="left")
    refresh_activity()

    # ================================================================ bottom bar
    bar = ttk.Frame(root, padding=10)
    bar.pack(fill="x")
    v_saved = tk.StringVar(value="")

    def edit_rules() -> None:
        open_in_system(ensure_rules_file(folder))

    def save() -> None:
        try:
            new = copy.deepcopy(settings)
            new.update({
                "watch_folder": v_watch.get().strip(),
                "organize_into": v_into.get().strip(),
                "settle_seconds": max(1, int(v_settle.get())),
                "rename": bool(v_rename.get()),
                "name_template": v_template.get().strip() or DEFAULT_SETTINGS["name_template"],
                "date_format": v_datefmt.get().strip() or DEFAULT_SETTINGS["date_format"],
                "auto_extract": bool(v_extract.get()),
                "trash_archive_after_extract": bool(v_trash_zip.get()),
                "installer_expire_days": max(0, int(v_expire.get())),
                "duplicates": next((k for k, v in DUPLICATE_CHOICES.items() if v == v_dupes.get()), "trash"),
                "notifications": bool(v_notify.get()),
                "process_missed_on_start": bool(v_missed.get()),
                "dry_run": bool(v_dry.get()),
            })
            new["ai"] = {
                "enabled": bool(v_ai_on.get()),
                "url": v_ai_url.get().strip() or DEFAULT_SETTINGS["ai"]["url"],
                "model": v_ai_model.get().strip() or DEFAULT_SETTINGS["ai"]["model"],
                "timeout_seconds": max(5, int(v_ai_timeout.get())),
            }
        except (tk.TclError, ValueError):
            messagebox.showerror(APP_NAME, "Please enter whole numbers in the number boxes.")
            return
        for key in ("watch_folder", "organize_into"):
            if new[key] and not Path(new[key]).expanduser().is_dir():
                messagebox.showerror(APP_NAME, f"This folder doesn't exist:\n{new[key]}")
                return
        save_settings(new, folder)
        settings.clear()
        settings.update(new)
        if autostart.is_supported():
            try:
                autostart.set_enabled(bool(v_login.get()))
            except OSError as exc:
                messagebox.showwarning(APP_NAME, f"Could not change 'start at login': {exc}")
        v_saved.set("Saved - the app uses the new settings within a few seconds.")
        root.after(5000, lambda: v_saved.set(""))

    ttk.Button(bar, text="Edit rules...", command=edit_rules).pack(side="left")
    ttk.Button(bar, text="Open app folder", command=lambda: open_in_system(folder)).pack(side="left", padx=6)
    ttk.Label(bar, textvariable=v_saved, foreground="#15803d").pack(side="left", padx=10)
    ttk.Button(bar, text="Close", command=root.destroy).pack(side="right")
    ttk.Button(bar, text="Save", command=save).pack(side="right", padx=6)

    # A menu-bar-only Mac app opens windows behind others - bring it to the front.
    root.lift()
    root.attributes("-topmost", True)
    root.after(400, lambda: root.attributes("-topmost", False))
    root.focus_force()
    root.mainloop()
