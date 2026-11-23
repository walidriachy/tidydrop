"""Reading details about a downloaded file: which website it came from and
what's inside it (document text, photo date, video resolution and length)."""
from __future__ import annotations

import html
import json
import logging
import os
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .naming import split_name

log = logging.getLogger(__name__)
logging.getLogger("pypdf").setLevel(logging.ERROR)

# Browsers write to these while a download is still running.
TEMP_EXTENSIONS = (
    "crdownload", "part", "partial", "download", "opdownload", "tmp", "filepart",
    "aria2", "!ut", "!qb", "bc!", "td", "adadownload",
)
IGNORED_NAMES = {"desktop.ini", "thumbs.db", ".ds_store", ".localized", "icon\r"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif", "avif", "bmp", "tif", "tiff"}
VIDEO_EXTS = {"mp4", "mov", "mkv", "avi", "webm", "m4v", "wmv", "flv"}
TEXT_EXTS = {"txt", "md", "csv", "tsv", "json", "xml", "html", "htm", "log", "yaml", "yml", "rtf", "eml"}
MAX_TEXT = 4000
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW

_TAG = re.compile(r"<[^>]+>")


def is_temp_name(name: str) -> bool:
    lower = name.lower()
    if lower.startswith(("~$", ".~lock")):  # Office lock files
        return True
    return any(lower.endswith("." + ext) for ext in TEMP_EXTENSIONS)


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


@dataclass
class FileInfo:
    path: Path
    size: int
    mtime: float
    category: str
    sources: list[str] = field(default_factory=list)  # page URL first, then file URL
    text: str = ""
    doc_title: str = ""
    taken: datetime | None = None
    extra: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return split_name(self.path.name)[0]

    @property
    def ext(self) -> str:
        return split_name(self.path.name)[1]

    @property
    def source_domain(self) -> str:
        return domain_of(self.sources[0]) if self.sources else ""

    @property
    def date(self) -> datetime:
        return self.taken or datetime.fromtimestamp(self.mtime)


def read_sources(path: Path) -> list[str]:
    """The web addresses the OS recorded for a download.

    Windows keeps them in the file's hidden "Zone.Identifier" stream,
    macOS in the "kMDItemWhereFroms" extended attribute.
    """
    urls: list[str] = []
    try:
        if sys.platform == "win32":
            with open(f"{path}:Zone.Identifier", encoding="utf-8", errors="ignore") as handle:
                found = {}
                for line in handle:
                    key, _, value = line.strip().partition("=")
                    if key in ("ReferrerUrl", "HostUrl") and value:
                        found[key] = value
                urls = [found[k] for k in ("ReferrerUrl", "HostUrl") if k in found]
        elif sys.platform == "darwin":
            out = subprocess.run(
                ["xattr", "-px", "com.apple.metadata:kMDItemWhereFroms", str(path)],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                data = plistlib.loads(bytes.fromhex("".join(out.stdout.split())))
                urls = [u for u in data if isinstance(u, str)][::-1]  # macOS lists the file URL first
    except (OSError, ValueError, subprocess.SubprocessError, plistlib.InvalidFileException):
        pass
    return [u for u in urls if u.startswith(("http://", "https://"))]


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _pdf_text(path: Path) -> tuple[str, str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                return "", ""
        except Exception:
            return "", ""
    title = ""
    try:
        if reader.metadata and reader.metadata.title:
            title = str(reader.metadata.title)
    except Exception:
        pass
    parts: list[str] = []
    for page in reader.pages[:2]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
        if sum(map(len, parts)) >= MAX_TEXT:
            break
    return _tidy("\n".join(parts))[:MAX_TEXT], title


def _xml_to_text(xml: str) -> str:
    xml = re.sub(r"</(?:w:p|a:p)>", "\n", xml)
    return html.unescape(_TAG.sub("", xml))


def _core_title(archive: zipfile.ZipFile) -> str:
    try:
        core = archive.read("docProps/core.xml").decode("utf-8", "ignore")
    except KeyError:
        return ""
    match = re.search(r"<dc:title>(.*?)</dc:title>", core, re.S)
    return html.unescape(match.group(1)).strip() if match else ""


def _docx_text(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")[:2_000_000].decode("utf-8", "ignore")
        return _tidy(_xml_to_text(xml))[:MAX_TEXT], _core_title(archive)


def _pptx_text(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        slides = [n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        slides.sort(key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        parts = [_xml_to_text(archive.read(n)[:500_000].decode("utf-8", "ignore")) for n in slides[:3]]
        return _tidy("\n".join(parts))[:MAX_TEXT], _core_title(archive)


def _plain_text(path: Path, ext: str) -> str:
    with open(path, "rb") as handle:
        text = handle.read(16384).decode("utf-8", "ignore")
    if ext in ("html", "htm"):
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = html.unescape(_TAG.sub(" ", text))
    return _tidy(text)[:MAX_TEXT]


def _image_taken(path: Path) -> datetime | None:
    from PIL import Image

    with Image.open(path) as image:
        exif = image.getexif()
        raw = None
        try:
            raw = exif.get_ifd(0x8769).get(36867)  # DateTimeOriginal
        except Exception:
            raw = None
        raw = raw or exif.get(306)  # DateTime
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip("\x00 ")[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _find_ffprobe() -> str | None:
    found = shutil.which("ffprobe")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe"):  # GUI apps on macOS have a short PATH
        if os.path.exists(candidate):
            return candidate
    return None


def resolution_label(width: int, height: int) -> str:
    side = min(width, height)  # portrait 1080x1920 is still "1080p"
    if side <= 0:
        return ""
    for limit, label in ((2160, "4K"), (1440, "1440p"), (1080, "1080p"), (720, "720p"), (480, "480p")):
        if side >= limit:
            return label
    return f"{side}p"


def duration_label(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{round(seconds / 60)}min"
    hours, rest = divmod(seconds, 3600)
    return f"{hours}h{rest // 60:02d}m"


def _video_extra(path: Path) -> str:
    exe = _find_ffprobe()
    if not exe:
        return ""
    out = subprocess.run(
        [exe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW,
    )
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams") or [{}]
    width, height = int(streams[0].get("width") or 0), int(streams[0].get("height") or 0)
    duration = float((data.get("format") or {}).get("duration") or 0)
    return " ".join(p for p in (resolution_label(width, height), duration_label(duration)) if p)


def gather(path: Path, cfg) -> FileInfo:
    """Collect everything the rules and the renamer may need. Never raises
    for unreadable content - you just get fewer details."""
    st = path.stat()
    ext = split_name(path.name)[1].lower()
    info = FileInfo(
        path=path,
        size=st.st_size,
        mtime=st.st_mtime,
        category=cfg.category_for(ext) if ext else cfg.fallback_category,
    )
    info.sources = read_sources(path)
    kind = ext.rsplit(".", 1)[-1]
    try:
        if kind == "pdf":
            info.text, info.doc_title = _pdf_text(path)
        elif kind == "docx":
            info.text, info.doc_title = _docx_text(path)
        elif kind == "pptx":
            info.text, info.doc_title = _pptx_text(path)
        elif kind in TEXT_EXTS and st.st_size <= 5 * 1024 * 1024:
            info.text = _plain_text(path, kind)
        elif kind in IMAGE_EXTS:
            info.taken = _image_taken(path)
        elif kind in VIDEO_EXTS:
            info.extra = _video_extra(path)
    except Exception as exc:  # a broken file must never stop the organizer
        log.debug("Could not read details of %s: %s", path.name, exc)
    return info
