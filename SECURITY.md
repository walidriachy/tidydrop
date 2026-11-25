# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security vulnerabilities. Use GitHub's private reporting instead: **Security → Report a vulnerability** on this repository. We aim to respond within 7 days.

Please include clear reproduction steps, the platform (macOS or Windows), and the version of TidyDrop involved.

## Supported versions

| Version | Supported |
|---|---|
| latest release (`1.x`) | ✅ |
| older releases | ❌ (please upgrade) |

## Security & privacy model

TidyDrop inspects and organizes files inside your `Downloads` folder, so the design prioritizes **local-only processing**, **safe archive handling**, and **zero permanent data loss**.

| Layer | Protection |
|---|---|
| Network & telemetry | TidyDrop makes **zero outbound internet requests**. No analytics, no crash uploads, no accounts. Optional AI renaming communicates only with the user's configured local Ollama endpoint (default `http://127.0.0.1:11434`) |
| Safe file deletion | TidyDrop never calls permanent delete (`unlink` / `rmtree`) on user downloads. Duplicates, extracted archives, and expired installers are sent exclusively to the OS Trash / Recycle Bin via `Send2Trash` |
| Archive extraction (Zip-Slip & Zip-Bomb) | `tidydrop/archive.py` resolves every member path before extracting and refuses any `..`, absolute path, or symlink escape outside the target directory, while enforcing decompression size/file-count caps |
| OS internet warning marks | When extracting downloaded archives, TidyDrop preserves macOS `com.apple.quarantine` and Windows `Zone.Identifier` (Mark of the Web) metadata so Gatekeeper and SmartScreen protections remain active on extracted files |
| File stability guard | Files are never touched while actively downloading (`.crdownload`, `.part`, `.download`) or still changing size |
| Reversibility | Every move and rename is appended to `activity.jsonl` so accidental rule matches can be reversed cleanly via Undo |

### Things to know

* **Unsigned indie releases:** Release builds (`TidyDrop.dmg` and `TidyDrop.Setup.exe`) are compiled directly by GitHub Actions (`.github/workflows/build.yml`) from this public repository, but are not yet signed with a paid Apple Developer or Windows Authenticode certificate. Download installers only from this repository's official [Releases](https://github.com/walidriachy/tidydrop/releases) page or [appx.ae/downloads/tidydrop](https://www.appx.ae/downloads/tidydrop).
* **Custom rules (`rules.yaml`):** Rules run locally under your normal user account permissions and never execute arbitrary shell commands.
