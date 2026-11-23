# Builds dist\TidyDrop.exe - a single file, no Python needed to run it.
# Run from PowerShell:   .\scripts\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m venv .venv } else { python -m venv .venv }
}
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements-dev.txt --quiet
& $py tools\make_icons.py
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed - not building." }

& $py -m PyInstaller --noconfirm --clean --windowed --onefile `
    --name "TidyDrop" `
    --icon assets\icon.ico `
    --hidden-import pystray._win32 `
    run.pyw
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

# The same program is the installer: run from anywhere except its install folder,
# it shows the Install window. Name it so users know to double-click it.
$setup = "dist\TidyDrop Setup.exe"
if (Test-Path $setup) { Remove-Item $setup -Force }
Move-Item "dist\TidyDrop.exe" $setup

Write-Host ""
Write-Host "Built: $(Resolve-Path $setup)"
Write-Host "Give this one file to anyone - they double-click it and click Install."
