"""Safe unzipping: never writes outside the target folder, refuses zip bombs,
and keeps the "downloaded from the internet" mark on extracted files so
Windows SmartScreen / macOS Gatekeeper still warn about them."""
from __future__ import annotations

import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from .naming import unique_path

ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")


class ArchiveError(Exception):
    pass


def can_extract(path: Path) -> bool:
    return path.name.lower().endswith(ARCHIVE_SUFFIXES)


def _extract_zip(archive: Path, dest: Path, max_bytes: int, max_members: int) -> None:
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > max_members:
            raise ArchiveError(f"too many files inside ({len(infos)})")
        if sum(i.file_size for i in infos) > max_bytes:
            raise ArchiveError("too big once unpacked")
        root = dest.resolve()
        for info in infos:
            if info.flag_bits & 0x1:
                raise ArchiveError("password protected")
            if stat.S_ISLNK(info.external_attr >> 16):
                continue  # never create links
            target = (dest / info.filename).resolve()
            if target != root and not target.is_relative_to(root):
                raise ArchiveError(f"unsafe path inside: {info.filename}")
        for info in infos:
            if not stat.S_ISLNK(info.external_attr >> 16):
                zf.extract(info, dest)


def _extract_tar(archive: Path, dest: Path, max_bytes: int, max_members: int) -> None:
    if not hasattr(tarfile, "data_filter"):
        raise ArchiveError("this Python is too old to unpack tar files safely")
    with tarfile.open(archive) as tf:
        members = tf.getmembers()
        if len(members) > max_members:
            raise ArchiveError(f"too many files inside ({len(members)})")
        if sum(m.size for m in members if m.isfile()) > max_bytes:
            raise ArchiveError("too big once unpacked")
        try:
            tf.extractall(dest, filter="data")
        except tarfile.FilterError as exc:
            raise ArchiveError(f"unsafe content: {exc}") from exc


def _keep_download_mark(archive: Path, folder: Path) -> None:
    if sys.platform == "win32":
        try:
            with open(f"{archive}:Zone.Identifier", "rb") as handle:
                mark = handle.read()
        except OSError:
            return
        for path in folder.rglob("*"):
            if path.is_file():
                try:
                    with open(f"{path}:Zone.Identifier", "wb") as handle:
                        handle.write(mark)
                except OSError:
                    pass
    elif sys.platform == "darwin":
        out = subprocess.run(["xattr", "-p", "com.apple.quarantine", str(archive)], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            subprocess.run(["xattr", "-r", "-w", "com.apple.quarantine", out.stdout.strip(), str(folder)],
                           capture_output=True)


def extract_archive(archive: Path, dest_parent: Path, folder_name: str,
                    max_bytes: int, max_members: int = 20000) -> Path:
    """Unpack `archive` into dest_parent/folder_name and return that folder.
    If everything inside sits in one top folder, that folder is not nested again."""
    dest_parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".extracting-", dir=dest_parent))
    try:
        if archive.name.lower().endswith(".zip"):
            _extract_zip(archive, tmp, max_bytes, max_members)
        else:
            _extract_tar(archive, tmp, max_bytes, max_members)
        children = list(tmp.iterdir())
        final = unique_path(dest_parent, folder_name)
        if len(children) == 1 and children[0].is_dir():
            shutil.move(str(children[0]), str(final))
            tmp.rmdir()
        else:
            tmp.rename(final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    _keep_download_mark(archive, final)
    return final
