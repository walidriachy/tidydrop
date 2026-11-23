import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tidydrop import organizer as organizer_mod  # noqa: E402
from tidydrop.config import DEFAULT_RULES_YAML, load_config, load_settings, save_settings  # noqa: E402

# A custom rule like the ones users add themselves.
ACME_RULE = """
  - name: Acme
    when:
      any_contains: [acme]
    move_to: Acme
"""


def write_rules_with_custom_rule(folder: Path) -> None:
    (folder / "rules.yaml").write_text(DEFAULT_RULES_YAML + ACME_RULE, encoding="utf-8")
from tidydrop.journal import Journal  # noqa: E402
from tidydrop.organizer import Organizer  # noqa: E402
from tidydrop.state import State  # noqa: E402


class Env:
    def __init__(self, root: Path):
        self.config_dir = root / "config"
        self.downloads = root / "Downloads"
        self.config_dir.mkdir()
        self.downloads.mkdir()
        write_rules_with_custom_rule(self.config_dir)
        self.trashed: list[str] = []

    def settings(self, **overrides) -> None:
        settings = load_settings(self.config_dir)
        settings.update(watch_folder=str(self.downloads), notifications=False, settle_seconds=1)
        settings.update(overrides)
        save_settings(settings, self.config_dir)

    def organizer(self, **overrides) -> Organizer:
        self.settings(**overrides)
        org = Organizer(
            load_config(self.config_dir),
            Journal(self.config_dir / "activity.jsonl"),
            State(self.config_dir / "state.json"),
        )
        org.dupes.build()
        return org

    def write(self, name: str, content: bytes | str = b"hello") -> Path:
        path = self.downloads / name
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        return path

    def files(self) -> list[str]:
        return sorted(p.relative_to(self.downloads).as_posix() for p in self.downloads.rglob("*") if p.is_file())


@pytest.fixture
def env(tmp_path, monkeypatch) -> Env:
    e = Env(tmp_path)

    def fake_trash(path):
        path = Path(path)
        e.trashed.append(path.name)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    monkeypatch.setattr(organizer_mod, "send_to_trash", fake_trash)
    return e
