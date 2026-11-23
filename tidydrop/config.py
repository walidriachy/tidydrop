"""Settings (settings.yaml - changed from the Settings window) and
rules (rules.yaml - written by you, with comments)."""
from __future__ import annotations

import copy
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .paths import app_data_dir, default_downloads_dir

log = logging.getLogger(__name__)

SETTINGS_FILE = "settings.yaml"
RULES_FILE = "rules.yaml"

DEFAULT_SETTINGS: dict = {
    "watch_folder": "",            # empty = the system Downloads folder
    "organize_into": "",           # empty = sort into sub-folders of the watched folder
    "dry_run": False,              # preview only: log what would happen, move nothing
    "settle_seconds": 5,           # a file must stop growing this long before it's touched
    "rename": True,
    "name_template": "{date} {title} {extra}",
    "date_format": "%Y-%m-%d",
    "auto_extract": True,
    "trash_archive_after_extract": True,
    "max_extract_mb": 4096,
    "installer_expire_days": 14,   # 0 = keep installers forever
    "duplicates": "trash",         # "trash" or "keep"
    "duplicate_max_mb": 2048,      # bigger files are not checked for duplicates
    "notifications": True,
    "process_missed_on_start": True,
    "ai": {
        "enabled": False,
        "url": "http://127.0.0.1:11434",
        "model": "llama3.2",
        "timeout_seconds": 180,  # the first request loads the model, which can take a while
    },
}

_INT_SETTINGS = ("settle_seconds", "max_extract_mb", "installer_expire_days", "duplicate_max_mb")

DEFAULT_RULES_YAML = r"""# TidyDrop - rules
# ---------------------------------------------------------------------
# This file decides WHERE each download goes. The app re-reads it a
# couple of seconds after you save it - no restart needed.
#
# 1) "categories" maps file types to a folder. Anything the rules below
#    don't catch goes to its category folder (unknown types -> Other).
# 2) "rules" are checked top to bottom. The FIRST rule whose conditions
#    ALL match wins.
#
# Conditions you can use under "when":
#   extensions:        [pdf, docx]              file type
#   category:          Images                   a category from the list below
#   name_matches:      '(?i)^screenshot'        regular expression on the file name
#   name_contains_any: [invoice, receipt]       words in the file name
#   source_contains:   [wetransfer.com]         website the file was downloaded from
#   text_contains_any: [invoice, "amount due"]  words inside PDF / Word / PowerPoint / text files
#   any_contains:      [acme]                 the name, website OR text contains the word
#   min_size_mb: 100      max_size_mb: 5
#
# What a matching rule does:
#   move_to:     Documents/Invoices    folder inside Downloads. Can use
#                                      {category} {year} {month} {source}
#   rename:      false                 keep the original name - or a template
#                                      such as "{date} {source} {title}"
#   expire_days: 30                    send to the Recycle Bin / Trash after 30 days
#
# Name template fields:
#   {date} {title} {original} {extra} {source} {category} {year} {month}
#   {extra} is e.g. "1080p 3min" for videos.

categories:
  Documents: [pdf, doc, docx, txt, rtf, odt, md, pages, epub, mobi]
  Spreadsheets: [xls, xlsx, xlsm, csv, tsv, numbers, ods]
  Presentations: [ppt, pptx, key, odp]
  Images: [jpg, jpeg, png, gif, webp, heic, heif, avif, bmp, tif, tiff, svg, ico]
  Design: [ai, psd, eps, fig, sketch, xd, indd, afdesign, afphoto, lumi]
  Videos: [mp4, mov, mkv, avi, webm, m4v, wmv, flv]
  Audio: [mp3, wav, flac, m4a, aac, ogg, opus]
  Archives: [zip, rar, 7z, tar, gz, tgz, bz2, xz]
  Installers: [exe, msi, msix, msixbundle, appx, dmg, pkg, apk, ipa, deb, rpm]
  Code: [py, js, ts, jsx, tsx, html, htm, css, json, xml, yaml, yml, cs, java, cpp, c, h, go, rs, sh, ps1, bat, ipynb, pine, mq4, mq5, ex4, ex5, set]
  3D: [stl, obj, fbx, blend, glb, gltf, 3mf, step, stp]
  Fonts: [ttf, otf, woff, woff2]
  Calendar & Mail: [ics, eml, msg, vcf]

fallback_category: Other

# Files in these categories keep their original names
# (renaming installers or code files is rarely helpful).
keep_original_names: [Installers, Code, Fonts, Archives]

rules:
  - name: Screenshots
    when:
      category: Images
      name_matches: '(?i)^(screenshot|screen shot|screen recording|capture|snip)'
    move_to: Images/Screenshots

  - name: Invoices and receipts
    when:
      extensions: [pdf]
      text_contains_any: [invoice, receipt, "amount due", "amount paid", "billing statement", "tax invoice"]
    move_to: Documents/Invoices

  - name: WeTransfer
    when:
      source_contains: [wetransfer.com, we.tl]
    move_to: Transfers/{year}-{month}

  # Example - send everything that mentions your company to its own folder.
  # Remove the "#" in front of the next four lines and change the words:
  # - name: My company
  #   when:
  #     any_contains: [acme]
  #   move_to: Acme
"""

RULE_KEYS = {"name", "when", "move_to", "rename", "expire_days"}
CONDITION_KEYS = {
    "extensions",
    "category",
    "name_matches",
    "name_contains_any",
    "source_contains",
    "text_contains_any",
    "any_contains",
    "min_size_mb",
    "max_size_mb",
}


class ConfigError(ValueError):
    """The settings or rules file contains a mistake."""


@dataclass
class Rule:
    name: str
    when: dict
    move_to: str | None = None
    rename: bool | str | None = None
    expire_days: int | None = None
    regex: re.Pattern | None = None


@dataclass
class Config:
    settings: dict
    ext_to_category: dict[str, str]
    fallback_category: str
    keep_original_names: set[str]
    rules: list[Rule]
    folder: Path
    watch_folder: Path = field(init=False)
    organize_root: Path = field(init=False)

    def __post_init__(self) -> None:
        watch = str(self.settings.get("watch_folder") or "").strip()
        self.watch_folder = Path(watch).expanduser() if watch else default_downloads_dir()
        into = str(self.settings.get("organize_into") or "").strip()
        self.organize_root = Path(into).expanduser() if into else self.watch_folder

    def category_for(self, ext: str) -> str:
        ext = ext.lower().rsplit(".", 1)[-1]
        return self.ext_to_category.get(ext, self.fallback_category)


def settings_path(folder: Path | None = None) -> Path:
    return (folder or app_data_dir()) / SETTINGS_FILE


def rules_path(folder: Path | None = None) -> Path:
    return (folder or app_data_dir()) / RULES_FILE


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings(folder: Path | None = None) -> dict:
    path = settings_path(folder)
    if not path.exists():
        save_settings(DEFAULT_SETTINGS, folder)
        return copy.deepcopy(DEFAULT_SETTINGS)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"settings.yaml: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("settings.yaml must contain 'name: value' lines")
    settings = _merge(DEFAULT_SETTINGS, data)
    for key in _INT_SETTINGS:
        try:
            settings[key] = int(settings[key])
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"settings.yaml: '{key}' must be a whole number") from exc
    return settings


def save_settings(settings: dict, folder: Path | None = None) -> None:
    path = settings_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# TidyDrop settings - normally changed from the Settings window.\n"
        "# Where files go is decided in rules.yaml.\n"
        + yaml.safe_dump(settings, sort_keys=False, allow_unicode=True)
    )
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def ensure_rules_file(folder: Path | None = None) -> Path:
    path = rules_path(folder)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_RULES_YAML, encoding="utf-8")
    return path


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    return [str(value)]


def parse_rules(data) -> tuple[dict[str, str], str, set[str], list[Rule]]:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError("rules.yaml must have 'categories:' and 'rules:' sections")
    categories = data.get("categories") or {}
    if not isinstance(categories, dict):
        raise ConfigError("'categories' must be a list of 'Folder: [ext, ext]' lines")
    ext_to_category: dict[str, str] = {}
    for category, exts in categories.items():
        for ext in _as_list(exts):
            ext_to_category[ext.lower().lstrip(".")] = str(category)
    fallback = str(data.get("fallback_category") or "Other")
    keep = set(_as_list(data.get("keep_original_names")))

    raw_rules = data.get("rules") or []
    if not isinstance(raw_rules, list):
        raise ConfigError("'rules' must be a list (each rule starts with '- name:')")
    rules: list[Rule] = []
    for number, raw in enumerate(raw_rules, 1):
        label = f"Rule #{number}"
        if not isinstance(raw, dict):
            raise ConfigError(f"{label} must be a set of 'key: value' lines")
        label = f"Rule #{number} ({raw.get('name', 'no name')})"
        unknown = set(raw) - RULE_KEYS
        if unknown:
            raise ConfigError(f"{label}: unknown setting(s) {', '.join(sorted(unknown))}")
        when = raw.get("when") or {}
        if not isinstance(when, dict):
            raise ConfigError(f"{label}: 'when' must contain conditions")
        bad = set(when) - CONDITION_KEYS
        if bad:
            raise ConfigError(f"{label}: unknown condition(s) {', '.join(sorted(bad))}")
        regex = None
        if "name_matches" in when:
            try:
                regex = re.compile(str(when["name_matches"]))
            except re.error as exc:
                raise ConfigError(f"{label}: name_matches is not a valid pattern ({exc})") from exc
        for size_key in ("min_size_mb", "max_size_mb"):
            if size_key in when:
                try:
                    float(when[size_key])
                except (TypeError, ValueError) as exc:
                    raise ConfigError(f"{label}: {size_key} must be a number") from exc
        rename = raw.get("rename")
        if rename is not None and not isinstance(rename, (bool, str)):
            raise ConfigError(f"{label}: rename must be true, false or a name template")
        expire = raw.get("expire_days")
        if expire is not None:
            try:
                expire = int(expire)
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"{label}: expire_days must be a whole number") from exc
        move_to = raw.get("move_to")
        rules.append(
            Rule(
                name=str(raw.get("name") or f"Rule {number}"),
                when=when,
                move_to=str(move_to) if move_to else None,
                rename=rename,
                expire_days=expire if expire and expire > 0 else None,
                regex=regex,
            )
        )
    return ext_to_category, fallback, keep, rules


def load_config(folder: Path | None = None) -> Config:
    folder = folder or app_data_dir()
    settings = load_settings(folder)
    path = ensure_rules_file(folder)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"rules.yaml: {exc}") from exc
    ext_map, fallback, keep, rules = parse_rules(data)
    return Config(settings, ext_map, fallback, keep, rules, folder)


def default_config(folder: Path | None = None) -> Config:
    """Built-in rules - used when the user's rules file has a mistake."""
    folder = folder or app_data_dir()
    try:
        settings = load_settings(folder)
    except ConfigError:
        settings = copy.deepcopy(DEFAULT_SETTINGS)
    ext_map, fallback, keep, rules = parse_rules(yaml.safe_load(DEFAULT_RULES_YAML))
    return Config(settings, ext_map, fallback, keep, rules, folder)
