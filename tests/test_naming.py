from datetime import datetime
from pathlib import Path

import pytest

from tidydrop.metadata import FileInfo
from tidydrop.naming import (
    build_filename,
    clean_title,
    is_good_doc_title,
    is_meaningless,
    sanitize_filename,
    short_source,
    split_name,
    unique_path,
)


def make_info(name, category="Documents", **kw):
    info = FileInfo(path=Path(name), size=10, mtime=datetime(2026, 11, 23, 9, 0).timestamp(), category=category)
    for key, value in kw.items():
        setattr(info, key, value)
    return info


@pytest.mark.parametrize("name,expected", [
    ("a.tar.gz", ("a", "tar.gz")),
    ("report.final.PDF", ("report.final", "PDF")),
    ("README", ("README", "")),
    (".hidden", (".hidden", "")),
    ("weird.name with space", ("weird.name with space", "")),
])
def test_split_name(name, expected):
    assert split_name(name) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Untitled video (2)", "Untitled video"),
    ("Creed.III.2023.1080p.WEB.H264-NAISU[rarbg]", "Creed III 2023 1080p WEB H264-NAISU"),
    ("GoogleDriveSetup (1)", "GoogleDriveSetup"),
    ("2025-10-12 Landscape video", "Landscape video"),
    ("20251012_holiday", "holiday"),
    ("my_holiday_photo", "my holiday photo"),
    ("Report - Copy", "Report"),
    ("Acme Install (1080p, h264, youtube)", "Acme Install (1080p, h264, youtube)"),
    ("2023 Annual Report", "2023 Annual Report"),
])
def test_clean_title(raw, expected):
    assert clean_title(raw) == expected


@pytest.mark.parametrize("title", ["download", "IMG_1234", "Untitled", "12345", "file (3)",
                                   "3f2a9c1e-8b7d-4c2e-9f1a-0b1c2d3e4f5a",
                                   "WhatsApp Image 2025-01-02 at 10.11.12", ""])
def test_meaningless(title):
    assert is_meaningless(title)


@pytest.mark.parametrize("title", ["Acme catalogue", "Untitled video", "Invoice 1234", "Audi RS5"])
def test_meaningful(title):
    assert not is_meaningless(title)


def test_doc_titles():
    assert is_good_doc_title("Acme Product Catalogue 2026")
    assert not is_good_doc_title("Microsoft Word - draft.docx")
    assert not is_good_doc_title("untitled")
    assert not is_good_doc_title("report.pdf")
    assert not is_good_doc_title("C:/Users/x/file")


def test_sanitize():
    assert sanitize_filename('a<b>:c?.pdf') == "a b c.pdf"
    assert sanitize_filename("CON.txt") == "CON_.txt"
    assert sanitize_filename("name. ") == "name"
    long = sanitize_filename("x" * 300 + ".pdf")
    assert long.endswith(".pdf") and len(long) <= 150


def test_unique_path(tmp_path):
    (tmp_path / "a.pdf").write_text("1")
    (tmp_path / "a (2).pdf").write_text("2")
    assert unique_path(tmp_path, "a.pdf").name == "a (3).pdf"
    assert unique_path(tmp_path, "b.pdf").name == "b.pdf"


@pytest.mark.parametrize("domain,expected", [
    ("download.wetransfer.com", "wetransfer"),
    ("www.bbc.co.uk", "bbc"),
    ("github.com", "github"),
    ("localhost", "localhost"),
    ("192.168.1.5", "192.168.1.5"),
    ("", ""),
])
def test_short_source(domain, expected):
    assert short_source(domain) == expected


def test_build_video_name():
    info = make_info("Untitled video (2).mp4", "Videos", extra="1080p 3min")
    assert build_filename(info, "{date} {title} {extra}") == "2026-11-23 Untitled video 1080p 3min.mp4"


def test_extra_not_repeated():
    info = make_info("A.Working.Man.2025.1080p.WEB-DL.mkv", "Videos", extra="1080p 2h01m")
    assert build_filename(info, "{date} {title} {extra}") == "2026-11-23 A Working Man 2025 1080p WEB-DL 2h01m.mkv"


def test_doc_title_used():
    info = make_info("scan0001.pdf", doc_title="Acme Product Catalogue")
    assert build_filename(info, "{date} {title} {extra}") == "2026-11-23 Acme Product Catalogue.pdf"


def test_meaningless_name_gets_website():
    info = make_info("download.pdf", sources=["https://wetransfer.com/downloads/abc"])
    assert build_filename(info, "{date} {title}") == "2026-11-23 download from wetransfer.pdf"


def test_ai_title_wins():
    info = make_info("scan0001.pdf", doc_title="Something")
    assert build_filename(info, "{date} {title}", ai_title="Adobe Invoice November") == "2026-11-23 Adobe Invoice November.pdf"


def test_date_not_doubled():
    info = make_info("Screenshot 2026-11-23 101010.png", "Images")
    assert build_filename(info, "{date} {title}") == "Screenshot 2026-11-23 101010.png"


def test_photo_uses_taken_date():
    info = make_info("IMG_1234.jpg", "Images", taken=datetime(2024, 7, 1, 12, 0))
    assert build_filename(info, "{date} {title}") == "2024-07-01 IMG 1234.jpg"


def test_bad_template_falls_back():
    info = make_info("notes.txt")
    assert build_filename(info, "{date:%Y} {title}") == "2026-11-23 notes.txt"
