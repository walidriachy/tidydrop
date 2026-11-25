# Roadmap

## Shipped (`v1.0.0`)

- [x] Background folder watcher for macOS menu bar & Windows system tray
- [x] Download settle detection (ignores `.crdownload`, `.part`, and open files)
- [x] Source-URL inspection (macOS quarantine & Windows `Zone.Identifier`)
- [x] Deep metadata extraction (PDF/Office text, photo EXIF dates, `ffprobe` video dimensions & duration)
- [x] Smart filename templates (`{date} {title} {extra} {source} {original} {category}`)
- [x] Optional 100% local Ollama AI renaming for unclear documents (`scan0001.pdf`)
- [x] Safe zip/tar extraction (zip-slip & zip-bomb guards + preserved OS security marks)
- [x] Exact duplicate cleanup & configurable 14-day old installer expiration (Trash / Recycle Bin only)
- [x] Reversible Activity Log & one-click Undo + Preview mode (dry run)
- [x] Automated macOS `.dmg` and Windows `Setup.exe` GitHub Actions release builds

## Planned

- [ ] **v1.1 · Flagship Obsidian Desktop UI Redesign:** Native dark obsidian & emerald-teal Settings + Activity window matching [appx.ae/downloads/tidydrop](https://www.appx.ae/downloads/tidydrop), with live filename template preview and sleek timeline undo rows
- [ ] **v1.1 · Visual Rule Builder:** Add and test custom `rules.yaml` rules directly inside Settings without editing YAML by hand
- [ ] **v1.2 · Multiple Watched Folders:** Watch Desktop or client transfer folders alongside Downloads with per-folder rule sets
- [ ] **v1.2 · Signed & Notarized Installers:** Apple Developer notarization and Windows code signing for zero first-run Gatekeeper / SmartScreen prompts
