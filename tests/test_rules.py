from datetime import datetime
from pathlib import Path

import pytest
import yaml

from tidydrop.classify import decide
from tidydrop.config import DEFAULT_RULES_YAML, ConfigError, default_config, load_config, parse_rules
from tidydrop.metadata import FileInfo


@pytest.fixture
def cfg(tmp_path):
    from conftest import write_rules_with_custom_rule

    write_rules_with_custom_rule(tmp_path)
    return load_config(tmp_path)


def test_builtin_rules_have_no_personal_rule(tmp_path):
    assert [r.name for r in default_config(tmp_path).rules] == ["Screenshots", "Invoices and receipts", "WeTransfer"]


def info(cfg, name, text="", sources=(), size=1000):
    ext = name.rsplit(".", 1)[-1]
    return FileInfo(path=Path(name), size=size, mtime=datetime(2026, 1, 20).timestamp(),
                    category=cfg.category_for(ext), text=text, sources=list(sources))


def test_default_rules_parse():
    ext_map, fallback, keep, rules = parse_rules(yaml.safe_load(DEFAULT_RULES_YAML))
    assert ext_map["pdf"] == "Documents"
    assert ext_map["exe"] == "Installers"
    assert fallback == "Other"
    assert "Installers" in keep
    assert [r.name for r in rules][:2] == ["Screenshots", "Invoices and receipts"]


def test_unknown_condition_is_reported():
    data = {"rules": [{"name": "Oops", "when": {"extention": ["pdf"]}}]}
    with pytest.raises(ConfigError, match="extention"):
        parse_rules(data)


def test_bad_regex_is_reported():
    with pytest.raises(ConfigError, match="name_matches"):
        parse_rules({"rules": [{"name": "R", "when": {"name_matches": "(unclosed"}}]})


def test_broken_yaml_is_reported(tmp_path):
    (tmp_path / "rules.yaml").write_text("rules: [this is: broken", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_screenshot(cfg):
    d = decide(info(cfg, "Screenshot 2026-01-20 101010.png"), cfg)
    assert d.dest == "Images/Screenshots" and d.rule == "Screenshots"


def test_invoice_needs_pdf_text(cfg):
    assert decide(info(cfg, "scan.pdf", text="TAX INVOICE  amount due 54.99"), cfg).dest == "Documents/Invoices"
    assert decide(info(cfg, "scan.pdf", text="holiday plans"), cfg).dest == "Documents"


def test_acme_by_text_or_name(cfg):
    assert decide(info(cfg, "catalogue.pdf", text="Acme carbon fiber"), cfg).dest == "Acme"
    assert decide(info(cfg, "acme-logo.png"), cfg).dest == "Acme"


def test_wetransfer_by_website(cfg):
    d = decide(info(cfg, "bp001.zip", sources=["https://wetransfer.com/downloads/x"]), cfg)
    assert d.dest == "Transfers/2026-01"


def test_installers_keep_name_and_expire(cfg):
    d = decide(info(cfg, "Setup (1).exe"), cfg)
    assert d.dest == "Installers" and d.rename is False and d.expire_days == 14


def test_code_keeps_name(cfg):
    assert decide(info(cfg, "script.py"), cfg).rename is False


def test_unknown_type_goes_to_other(cfg):
    assert decide(info(cfg, "thing.xyz"), cfg).dest == "Other"


def test_rule_rename_template_and_size(tmp_path):
    (tmp_path / "rules.yaml").write_text(
        "categories: {Videos: [mp4]}\n"
        "rules:\n"
        "  - name: Big\n"
        "    when: {category: Videos, min_size_mb: 1}\n"
        "    move_to: '{category}/Large/../{year}'\n"
        "    rename: '{source} {title}'\n"
        "    expire_days: 30\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    small = decide(info(cfg, "a.mp4", size=10), cfg)
    big = decide(info(cfg, "a.mp4", size=5 * 1024 * 1024), cfg)
    assert small.rule is None
    assert big.dest == "Videos/Large/2026"  # ".." is never allowed to climb out
    assert big.template == "{source} {title}" and big.expire_days == 30
