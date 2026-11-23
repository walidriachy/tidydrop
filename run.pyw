"""Double-click to start TidyDrop (no console window on Windows)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tidydrop.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
