"""Writes assets/icon.ico (Windows), icon.icns (macOS) and icon.png for the builds."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tidydrop.icons import make_icon  # noqa: E402

assets = ROOT / "assets"
assets.mkdir(exist_ok=True)
big = make_icon(1024)
big.save(assets / "icon.png")
big.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
try:
    big.save(assets / "icon.icns")
except Exception as exc:  # only needed on the Mac
    print(f"(skipped icon.icns: {exc})")
print(f"Icons written to {assets}")
