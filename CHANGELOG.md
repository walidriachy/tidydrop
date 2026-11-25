# Changelog

All notable changes to TidyDrop are documented in this file.

## [1.0.0] - 2026

### Added
- Initial public release for **macOS** (`TidyDrop.dmg`) and **Windows** (`TidyDrop.Setup.exe`).
- Background Downloads watcher with download-settle detection and menu bar / system tray controls.
- Source-URL detection (macOS quarantine metadata and Windows `Zone.Identifier`) for site-based rules such as WeTransfer.
- Metadata-driven renaming using PDF/Office text, photo EXIF capture dates, and `ffprobe` video resolution & length.
- Optional 100% local Ollama AI document titling (`Settings → AI renaming`) with built-in sample invoice tester.
- Safe archive auto-extraction with zip-slip & zip-bomb protection and preserved OS security marks.
- Exact duplicate removal and 14-day old installer expiration sending files exclusively to OS Trash / Recycle Bin.
- Full Activity Log, one-click Undo, Preview mode (dry run), custom `rules.yaml` hot-reloading, and CLI options.
