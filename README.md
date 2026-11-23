# TidyDrop

A small background app for **Windows and macOS** that keeps your Downloads
folder tidy. Every new download is checked, renamed clearly, and moved into
the right sub-folder automatically.

**Download:** [Windows (TidyDrop Setup.exe)](https://github.com/walidriachy/tidydrop/releases/latest/download/TidyDrop.Setup.exe) ·
[Mac (TidyDrop.dmg)](https://github.com/walidriachy/tidydrop/releases/latest/download/TidyDrop.dmg) ·
[All releases](https://github.com/walidriachy/tidydrop/releases)

```
Downloads/
├── Documents/        Invoices/ goes inside here
├── Spreadsheets/
├── Images/           Screenshots/ goes inside here
├── Videos/
├── Installers/       removed after 14 days (to the Recycle Bin / Trash)
├── Archives/         zips are unzipped here automatically
├── Code/
├── Acme/           your own rule, e.g. anything mentioning your company
├── Transfers/2026-11/  WeTransfer downloads by month
└── Other/
```

## What it does

| | |
|---|---|
| **Waits for downloads to finish** | Ignores `.crdownload`, `.part` and other in-progress files. It only moves a file after it has stopped growing and nothing has it open. |
| **Knows the website** | Reads the address Windows/macOS stores with each download, so rules like "everything from wetransfer.com goes to Transfers" work. |
| **Reads the file** | PDF, Word and PowerPoint text and titles, photo dates (EXIF), video resolution and length (via `ffprobe` if installed). |
| **Renames** | `Untitled video (2).mp4` → `2025-10-12 Untitled video 1080p 3min.mp4`, `Creed.III.2023.1080p.WEB[rarbg].mkv` → `2023-04-27 Creed III 2023 1080p WEB.mkv`. Installers, code and fonts keep their names. |
| **AI renaming (optional)** | A local Ollama model reads documents and names them, e.g. `scan0001.pdf` → `2026-11-20 Adobe Creative Cloud Invoice.pdf`. Nothing leaves your computer. |
| **Unzips** | `.zip` / `.tar.gz` are extracted safely (no writing outside the folder, no zip bombs). The zip goes to the Recycle Bin, and extracted files keep the "downloaded from the internet" warning mark. |
| **Removes exact duplicates** | Those `file (1).pdf` copies go to the Recycle Bin when an identical file is already organized. |
| **Cleans up installers** | `.exe .msi .dmg .pkg` are moved to the Recycle Bin / Trash 14 days after they were sorted (adjustable, 0 = never). |
| **Undo** | Everything is logged. Undo from the tray menu or the Activity log tab. |
| **Never deletes permanently** | Anything removed goes to the Recycle Bin / Trash. |

## Install on Windows

Double-click **`TidyDrop Setup.exe`** and click **Install**. No
administrator password is needed. It:

- installs to `%LOCALAPPDATA%\Programs\TidyDrop`
- adds it to the **Start menu** (and the desktop, if you tick that box)
- starts it automatically when you log in (you can untick that)
- lists it in **Settings → Apps → Installed apps**, where **Uninstall** removes it

A blue icon appears by the clock (click `^` if it's hidden). Right-click it for
**Settings and activity log**, **Pause**, **Preview mode**, **Undo**, **Start at login**
and **Quit**. To update, run a newer Setup: it closes the running app, replaces
it and starts it again.

Windows may show "Windows protected your PC" the first time, because the
app isn't signed with a paid certificate. Click **More info → Run anyway**.

**Making the Setup:** `.\scripts\build_windows.ps1` → `dist\TidyDrop Setup.exe`

## Install on Mac

Open **`TidyDrop.dmg`**, drag **TidyDrop** onto
**Applications**, then open it once with **right-click → Open** (it isn't
signed with a paid Apple certificate). On first start it asks whether to
start at login. The icon lives in the **menu bar**. macOS asks to let it
access the Downloads folder: click **Allow**. To remove it, quit it from the
menu bar and drag it from Applications to the Trash.

**Making the .dmg** must be done on a Mac. Copy this whole folder there, then in Terminal:

```bash
cd "path/to/TidyDrop"
bash scripts/build_mac.sh          # makes dist/TidyDrop.dmg
```

## Run from source (developers)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\pythonw run.pyw
```

## Try it safely first

Turn on **Preview mode** in the tray menu. The app then only writes what it
*would* do to the Activity log and moves nothing. From a terminal:

```powershell
.\.venv\Scripts\python -m tidydrop --once --dry-run
```

## Your rules

**Edit rules...** in the tray menu opens `rules.yaml`. It's commented and
reloads automatically when saved. Example:

```yaml
rules:
  - name: Bank statements
    when:
      extensions: [pdf]
      text_contains_any: [statement, "account number"]
    move_to: Documents/Bank/{year}

  - name: Big videos
    when:
      category: Videos
      min_size_mb: 2000
    move_to: Videos/Large
    expire_days: 60
```

If the file has a mistake, the app keeps using the last working rules and
shows a notification explaining what's wrong.

## AI renaming setup

1. Install Ollama from ollama.com.
2. In a terminal: `ollama pull llama3.2`
3. Open **Settings → AI renaming**, tick **Use AI to name documents**, click
   **Find models**, then **Test with a sample invoice**.

## Where things are kept

| | Windows | macOS |
|---|---|---|
| Settings, rules, activity log | `%APPDATA%\TidyDrop` | `~/Library/Application Support/TidyDrop` |

## Command line

```
python -m tidydrop               start with tray icon
python -m tidydrop --settings    open the Settings window
python -m tidydrop --once        organize what's in Downloads now, then exit
python -m tidydrop --once --dry-run   show what would happen
python -m tidydrop --undo        undo the last action
python -m tidydrop --no-tray     run in a terminal (Ctrl+C to stop)
python -m tidydrop --config-dir PATH  use a separate settings folder
```

## Tests

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest
```
