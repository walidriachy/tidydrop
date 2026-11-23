"""Matching a file against the rules to decide where it goes."""
from __future__ import annotations

from dataclasses import dataclass

from .config import Config, Rule
from .metadata import FileInfo
from .naming import _Blank, sanitize_component, short_source

_MB = 1024 * 1024


@dataclass
class Decision:
    rule: str | None        # None = no rule matched, sorted by category
    dest: str               # folder relative to the organize root, e.g. "Documents/Invoices"
    rename: bool
    template: str
    expire_days: int | None = None


def _lower_list(value) -> list[str]:
    items = value if isinstance(value, (list, tuple, set)) else [value]
    return [str(v).lower() for v in items if str(v)]


def rule_matches(rule: Rule, info: FileInfo) -> bool:
    when = rule.when
    name = info.name.lower()
    sources = " ".join(info.sources).lower()
    text = info.text.lower()

    if "extensions" in when:
        wanted = {e.lstrip(".") for e in _lower_list(when["extensions"])}
        ext = info.ext.lower()
        if ext not in wanted and ext.rsplit(".", 1)[-1] not in wanted:
            return False
    if "category" in when and info.category.lower() not in _lower_list(when["category"]):
        return False
    if "name_matches" in when and not (rule.regex and rule.regex.search(info.name)):
        return False
    if "name_contains_any" in when and not any(k in name for k in _lower_list(when["name_contains_any"])):
        return False
    if "source_contains" in when and not any(k in sources for k in _lower_list(when["source_contains"])):
        return False
    if "text_contains_any" in when and not any(k in text for k in _lower_list(when["text_contains_any"])):
        return False
    if "any_contains" in when and not any(
        k in name or k in sources or k in text for k in _lower_list(when["any_contains"])
    ):
        return False
    if "min_size_mb" in when and info.size < float(when["min_size_mb"]) * _MB:
        return False
    if "max_size_mb" in when and info.size > float(when["max_size_mb"]) * _MB:
        return False
    return True


def render_folder(pattern: str, info: FileInfo) -> str:
    when = info.date
    values = _Blank(
        category=info.category,
        year=when.strftime("%Y"),
        month=when.strftime("%m"),
        source=short_source(info.source_domain) or "Unknown site",
    )
    try:
        text = pattern.format_map(values)
    except (ValueError, IndexError, AttributeError, KeyError):
        text = pattern
    parts = [sanitize_component(p) for p in text.replace("\\", "/").split("/")]
    parts = [p for p in parts if p]
    return "/".join(parts) or sanitize_component(info.category) or "Other"


def decide(info: FileInfo, cfg: Config) -> Decision:
    settings = cfg.settings
    rename_on = bool(settings.get("rename", True))
    template = str(settings.get("name_template") or "{date} {title} {extra}")

    for rule in cfg.rules:
        if not rule_matches(rule, info):
            continue
        if rule.rename is False:
            rename = False
        elif isinstance(rule.rename, str):
            rename, template = rename_on, rule.rename
        else:
            rename = rename_on and info.category not in cfg.keep_original_names
        return Decision(rule.name, render_folder(rule.move_to or "{category}", info), rename, template, rule.expire_days)

    expire = None
    days = int(settings.get("installer_expire_days") or 0)
    if info.category == "Installers" and days > 0:
        expire = days
    rename = rename_on and info.category not in cfg.keep_original_names
    return Decision(None, render_folder("{category}", info), rename, template, expire)
