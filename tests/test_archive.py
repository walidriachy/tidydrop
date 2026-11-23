import io
import tarfile
import zipfile

import pytest

from tidydrop.archive import ArchiveError, can_extract, extract_archive

LIMIT = 50 * 1024 * 1024


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def test_can_extract(tmp_path):
    assert can_extract(tmp_path / "a.zip")
    assert can_extract(tmp_path / "a.TAR.GZ")
    assert not can_extract(tmp_path / "a.rar")


def test_single_top_folder_not_nested(tmp_path):
    archive = make_zip(tmp_path / "Audi-RS.zip", {"Audi-RS/a.txt": "1", "Audi-RS/sub/b.txt": "2"})
    out = extract_archive(archive, tmp_path / "Archives", "Audi-RS", LIMIT)
    assert out == tmp_path / "Archives" / "Audi-RS"
    assert (out / "a.txt").read_text() == "1"
    assert (out / "sub" / "b.txt").exists()


def test_loose_files_get_a_folder(tmp_path):
    archive = make_zip(tmp_path / "pics.zip", {"a.txt": "1", "b.txt": "2"})
    out = extract_archive(archive, tmp_path / "Archives", "pics", LIMIT)
    assert sorted(p.name for p in out.iterdir()) == ["a.txt", "b.txt"]


def test_name_taken_gets_number(tmp_path):
    (tmp_path / "Archives" / "pics").mkdir(parents=True)
    archive = make_zip(tmp_path / "pics.zip", {"a.txt": "1"})
    assert extract_archive(archive, tmp_path / "Archives", "pics", LIMIT).name == "pics (2)"


def test_zip_slip_refused_and_nothing_left_behind(tmp_path):
    archive = make_zip(tmp_path / "evil.zip", {"ok.txt": "1", "../../evil.txt": "x"})
    dest = tmp_path / "Archives"
    with pytest.raises(ArchiveError):
        extract_archive(archive, dest, "evil", LIMIT)
    assert not (tmp_path / "evil.txt").exists()
    assert list(dest.iterdir()) == []  # temp folder cleaned up


def test_zip_bomb_refused(tmp_path):
    archive = make_zip(tmp_path / "big.zip", {"zeros.bin": b"\0" * 2_000_000})
    with pytest.raises(ArchiveError, match="too big"):
        extract_archive(archive, tmp_path / "Archives", "big", 1_000_000)


def test_tar_gz(tmp_path):
    archive = tmp_path / "logs.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        data = b"hello"
        member = tarfile.TarInfo("logs/one.txt")
        member.size = len(data)
        tf.addfile(member, io.BytesIO(data))
    out = extract_archive(archive, tmp_path / "Archives", "logs", LIMIT)
    assert (out / "one.txt").read_bytes() == b"hello"


def test_tar_escape_refused(tmp_path):
    archive = tmp_path / "evil.tar"
    with tarfile.open(archive, "w") as tf:
        member = tarfile.TarInfo("../escape.txt")
        member.size = 1
        tf.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ArchiveError):
        extract_archive(archive, tmp_path / "Archives", "evil", LIMIT)
    assert not (tmp_path / "escape.txt").exists()
