import json
import threading
import time
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from PIL import Image

from tidydrop import organizer as organizer_mod

TODAY = datetime.now().strftime("%Y-%m-%d")


def test_text_mentioning_acme(env):
    org = env.organizer()
    path = env.write("notes.txt", "Acme pricing for the RS5 bodykit")
    message = org.process(path)
    assert env.files() == [f"Acme/{TODAY} notes.txt"]
    assert "Acme" in message


def test_screenshot(env):
    org = env.organizer()
    path = env.downloads / f"Screenshot {TODAY} 101010.png"
    Image.new("RGB", (4, 4)).save(path)
    org.process(path)
    assert env.files() == [f"Images/Screenshots/Screenshot {TODAY} 101010.png"]  # date not doubled


def test_installer_keeps_name_and_expires(env, monkeypatch):
    org = env.organizer(installer_expire_days=14)
    org.process(env.write("GoogleDriveSetup (1).exe", b"MZ..."))
    assert env.files() == ["Installers/GoogleDriveSetup (1).exe"]
    assert org.sweep_expired() == []  # not yet
    future = time.time() + 15 * 86400
    monkeypatch.setattr(organizer_mod.time, "time", lambda: future)
    assert org.sweep_expired() == ["GoogleDriveSetup (1).exe"]
    assert env.files() == [] and env.trashed == ["GoogleDriveSetup (1).exe"]
    assert org.sweep_expired() == []  # only once


def test_duplicate_goes_to_bin(env):
    org = env.organizer()
    org.process(env.write("report.txt", "same content"))
    message = org.process(env.write("report (1).txt", "same content"))
    assert "duplicate" in message.lower()
    assert env.files() == [f"Documents/{TODAY} report.txt"]
    assert env.trashed == ["report (1).txt"]


def test_duplicates_can_be_kept(env):
    org = env.organizer(duplicates="keep")
    org.process(env.write("report.txt", "same"))
    org.process(env.write("report (1).txt", "same"))
    assert env.files() == [f"Documents/{TODAY} report (2).txt", f"Documents/{TODAY} report.txt"]


def test_zip_is_unzipped_and_binned(env):
    org = env.organizer()
    zpath = env.downloads / "Audi-RS (1).zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("Audi-RS/front.txt", "x")
    org.process(zpath)
    assert env.files() == ["Archives/Audi-RS/front.txt"]
    assert env.trashed == ["Audi-RS (1).zip"]


def test_broken_zip_is_just_moved(env):
    org = env.organizer()
    org.process(env.write("broken.zip", b"not a zip"))
    assert env.files() == ["Archives/broken.zip"]


def test_preview_mode_moves_nothing(env):
    org = env.organizer(dry_run=True)
    path = env.write("notes.txt", "hello")
    message = org.process(path)
    assert message.startswith("Would move")
    assert env.files() == ["notes.txt"]


def test_undo_puts_file_back_and_leaves_it_alone(env):
    org = env.organizer()
    path = env.write("notes.txt", "hello")
    org.process(path)
    assert "back" in org.undo()
    assert env.files() == ["notes.txt"]
    assert org.process(path) is None  # the user put it back on purpose
    assert org.undo() == "Nothing to undo."


def test_undo_unzip(env):
    org = env.organizer()
    zpath = env.downloads / "pics.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.txt", "1")
    org.process(zpath)
    message = org.undo()
    assert "Recycle Bin" in message or "Trash" in message
    assert env.files() == []


def test_temp_files_ignored(env):
    org = env.organizer()
    assert org.process(env.write("movie.mp4.crdownload")) is None
    partial = env.write("big.zip", b"")
    env.write("big.zip.part", b"...")
    assert org.has_pending_sibling(partial)
    assert org.process(env.write("desktop.ini")) is None
    assert org.process(env.write("~$report.docx")) is None


def test_files_in_subfolders_are_left_alone(env):
    org = env.organizer()
    (env.downloads / "Mine").mkdir()
    path = env.downloads / "Mine" / "keep.txt"
    path.write_text("x")
    assert org.process(path) is None


def test_organize_existing(env):
    org = env.organizer()
    env.write("a.txt", "1")
    env.write("b.csv", "2")
    env.write("c.part", "3")
    messages = org.organize_existing()
    assert len(messages) == 2
    assert env.files() == [f"Documents/{TODAY} a.txt", f"Spreadsheets/{TODAY} b.csv", "c.part"]


def test_journal_records_actions(env):
    org = env.organizer()
    org.process(env.write("a.txt", "1"))
    actions = org.journal.actions()
    assert actions[-1]["file"] == "a.txt" and actions[-1]["ops"][0]["op"] == "move"


class _FakeOllama(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert "Adobe" in body["prompt"]
        reply = {"response": json.dumps({"title": "Adobe Creative Cloud Invoice November"})}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def test_ai_renaming(env):
    server = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        org = env.organizer(ai={"enabled": True, "url": f"http://127.0.0.1:{server.server_port}",
                                "model": "test", "timeout_seconds": 10})
        org.process(env.write("scan0001.txt", "Adobe Inc. Invoice IN-58213 total $54.99"))
        assert env.files() == [f"Documents/{TODAY} Adobe Creative Cloud Invoice November.txt"]
    finally:
        server.shutdown()


def test_ai_unreachable_falls_back(env):
    org = env.organizer(ai={"enabled": True, "url": "http://127.0.0.1:9", "model": "x", "timeout_seconds": 2})
    org.process(env.write("scan0001.txt", "some text"))
    assert env.files() == [f"Documents/{TODAY} scan0001.txt"]
