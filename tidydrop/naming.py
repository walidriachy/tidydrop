"""Turning messy download names into clean, readable ones."""
from __future__ import annotations

import re
from pathlib import Path

COMPOUND_EXTS = ("tar.gz", "tar.bz2", "tar.xz")

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
# "(1)", "[2]", " - Copy", " copy 3" at the end of a name
_COPY_SUFFIX = re.compile(r"(?:\s*(?:\(\d{1,3}\)|\[\d{1,3}\])|[\s_-]+copy(?:\s*\(?\d{1,3}\)?)?)+\s*$", re.I)
# release-group tags like "[rarbg]" at the very end
_TRAILING_TAG = re.compile(r"\s*\[[^\[\]]{1,40}\]\s*$")
# a date (and maybe time) at the start: 2025-10-12, 20251012, 2025_10_12 14-03-22
LEADING_DATE = re.compile(
    r"^\s*(?:19|20)\d{2}[-_. ]?[01]\d[-_. ]?[0-3]\d"
    r"(?:[ _T-]?[0-2]\d[-_.:]?[0-5]\d(?:[-_.:]?[0-5]\d)?)?"
    r"(?=$|[\s_\-.])[\s_\-.]*"
)
_MEANINGLESS = re.compile(
    r"(?:downloads?|file|untitled|document|doc|image|img|photo|pic|picture|video|vid|scan"
    r"|new|attachment|unnamed|output|export|temp|tmp)?[\s_-]*\d*"
    r"|(?:img|dsc|dscn|dcim|pxl|vid|mvimg|wp|signal|whatsapp image|whatsapp video)[\s_-]*[\d_\s-]+(?:at[\s\d._-]+)?"
    r"|[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}"
    r"|[0-9a-f]{16,}",
    re.I,
)
_JUNK_TITLE = re.compile(
    r"^(?:microsoft (?:word|powerpoint|excel)\s*-|untitled|document\s*\d*$|presentation\s*\d*$"
    r"|powerpoint presentation|slide \d+|title$|pdf$|print$|none$)",
    re.I,
)


def split_name(name: str) -> tuple[str, str]:
    """'report.final.pdf' -> ('report.final', 'pdf'); 'a.tar.gz' -> ('a', 'tar.gz')."""
    lower = name.lower()
    for ext in COMPOUND_EXTS:
        if lower.endswith("." + ext) and len(name) > len(ext) + 1:
            return name[: -len(ext) - 1], name[-len(ext):]
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem or " " in ext or len(ext) > 10:
        return name, ""
    return stem, ext


def clean_title(stem: str) -> str:
    s = _TRAILING_TAG.sub("", stem)
    s = _COPY_SUFFIX.sub("", s)
    if " " not in s.strip() and (s.count(".") >= 2 or "_" in s):
        s = re.sub(r"[._]+", " ", s)  # Some.Movie.2023.1080p -> Some Movie 2023 1080p
    else:
        s = s.replace("_", " ")
    s = LEADING_DATE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" .-_")
    return s or stem.strip()


def is_meaningless(title: str) -> bool:
    title = _COPY_SUFFIX.sub("", (title or "").strip()).strip()
    return not title or bool(_MEANINGLESS.fullmatch(title))


def is_good_doc_title(title: str) -> bool:
    """Is a title stored inside a PDF/Word file worth using as the file name?"""
    t = (title or "").strip()
    if not 4 <= len(t) <= 100:
        return False
    if _JUNK_TITLE.match(t):
        return False
    if re.search(r"\.(?:docx?|pdf|pptx?|xlsx?|indd|ai|psd|txt|html?|rtf)$", t, re.I):
        return False
    if re.search(r"[\\/]", t) or not re.search(r"[A-Za-z]{3}", t):
        return False
    return not is_meaningless(t)


def short_source(domain: str) -> str:
    """'download.wetransfer.com' -> 'wetransfer', 'www.bbc.co.uk' -> 'bbc'."""
    domain = (domain or "").lower().strip(".")
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain or re.fullmatch(r"[\d.:]+", domain):
        return domain
    parts = [p for p in domain.split(".") if p]
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gov", "ac", "edu"} and len(parts[-1]) == 2:
        return parts[-3]
    if len(parts) >= 2:
        return parts[-2]
    return domain


def sanitize_filename(name: str, max_len: int = 150) -> str:
    name = _INVALID.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    stem, ext = split_name(name)
    stem = stem.rstrip(" .")
    if len(name) > max_len:
        keep = max_len - (len(ext) + 1 if ext else 0)
        stem = stem[: max(keep, 1)].rstrip(" .")
    if stem.lower() in _RESERVED:
        stem += "_"
    if not stem.strip():
        stem = "file"
    return f"{stem}.{ext}" if ext else stem


def sanitize_component(name: str) -> str:
    """One folder name (no slashes)."""
    name = _INVALID.sub(" ", str(name))
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if name in ("", ".", ".."):
        return ""
    if name.lower() in _RESERVED:
        name += "_"
    return name[:100]


def unique_path(folder: Path, filename: str) -> Path:
    """folder/filename, or folder/'filename (2)' etc. if that's taken."""
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem, ext = split_name(filename)
    suffix = f".{ext}" if ext else ""
    for i in range(2, 100000):
        candidate = folder / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"No free name for {filename} in {folder}")


class _Blank(dict):
    def __missing__(self, key):  # unknown {fields} in a template become empty
        return ""


def build_filename(info, template: str, date_format: str = "%Y-%m-%d", ai_title: str | None = None) -> str:
    """New file name for a download. `info` is a metadata.FileInfo."""
    title = (ai_title or "").strip()
    if not title:
        title = info.doc_title.strip() if is_good_doc_title(info.doc_title) else clean_title(info.stem)
    title = LEADING_DATE.sub("", title).strip() or title

    source = short_source(info.source_domain)
    if is_meaningless(title) and source:
        title = f"{title} from {source}" if title else f"Download from {source}"

    extra = " ".join(tok for tok in (info.extra or "").split() if tok.lower() not in title.lower())
    when = info.date
    date_text = when.strftime(date_format)
    if date_text and date_text in title:
        date_text = ""  # the name already carries this date
    values = _Blank(
        date=date_text,
        title=title,
        original=info.stem,
        extra=extra,
        source=source,
        category=info.category,
        year=when.strftime("%Y"),
        month=when.strftime("%m"),
    )
    try:
        stem = template.format_map(values)
    except (ValueError, IndexError, AttributeError, KeyError):
        stem = f"{date_text} {title} {extra}"
    stem = re.sub(r"\s+", " ", stem).strip(" -_.") or info.stem
    return sanitize_filename(f"{stem}.{info.ext}" if info.ext else stem)
