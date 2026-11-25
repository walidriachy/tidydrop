# Contributing to TidyDrop

Thanks for helping keep Downloads folders clean! Bug reports, rule suggestions, documentation improvements, and pull requests are all welcome.

## Ground rules

* **Never permanently delete user files.** Any removal (duplicates, extracted archives, expired installers) must go through `Send2Trash` so files land in the OS Recycle Bin / Trash.
* **Every action must be reversible.** Moves and renames must be written to `Journal` (`activity.jsonl`) so one-click Undo always works.
* **Archives are untrusted input.** Extraction in `tidydrop/archive.py` must enforce path traversal (zip-slip) checks, zip-bomb size/ratio limits, and preserve macOS quarantine / Windows Mark of the Web (`Zone.Identifier`) security marks.
* **100% local privacy.** Never send filenames, file contents, or telemetry to any external server. Local AI calls stay strictly on the user's configured local Ollama endpoint (`127.0.0.1` by default).
* **Plain English first.** Every setting label, notification, and error message should make sense to a non-technical user.
* **Keep docs current.** If a PR adds a rule option, CLI flag, or major feature, update `README.md`, `docs/RULES.md`, and `ROADMAP.md` in the same PR.

## Setup

Requirements: Python 3.12+ (with Tk support for the Settings window).

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .\.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
```

## Run tests (same as CI)

```bash
python -m pytest -q
```

Run the app or Settings window locally:

```bash
python -m tidydrop --no-tray --dry-run
python -m tidydrop --settings
```

## Where things go

| Area | File | Tests |
|---|---|---|
| Core organization pipeline & Undo | `tidydrop/organizer.py` | `tests/test_organizer.py` |
| Folder watcher & download settle check | `tidydrop/watcher.py` | `tests/test_watcher.py` |
| File classification & custom YAML rules | `tidydrop/classify.py` | `tests/test_rules.py` |
| Smart filename templates & cleanup | `tidydrop/naming.py` | `tests/test_naming.py` |
| Safe zip/tar extraction & security marks | `tidydrop/archive.py` | `tests/test_archive.py` |
| Local Ollama AI title suggestions | `tidydrop/ai.py` | `tests/test_naming.py` |
| PDF, EXIF, Office & video metadata | `tidydrop/metadata.py` | `tests/test_naming.py` |
| Exact SHA-256 duplicate detection | `tidydrop/dupes.py` | `tests/test_organizer.py` |
| Reversible activity journal | `tidydrop/journal.py` | `tests/test_organizer.py` |
| Settings & Activity UI (`--settings`) | `tidydrop/settings_ui.py` | Manual + UI smoke test |
| Menu bar / System tray icon & menu | `tidydrop/tray.py`, `tidydrop/icons.py` | Manual |
| Packaging scripts | `scripts/build_mac.sh`, `scripts/build_windows.ps1` | GitHub Actions `build.yml` |
