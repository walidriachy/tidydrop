import time
from datetime import datetime

from tidydrop.config import load_config
from tidydrop.watcher import Watcher

TODAY = datetime.now().strftime("%Y-%m-%d")


def wait_for(check, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if check():
            return True
        time.sleep(0.2)
    return False


def test_new_download_is_organized(env):
    org = env.organizer()
    watcher = Watcher(org, env.config_dir)
    watcher.start()
    try:
        # simulate a browser: write a temp file, then rename it when done
        temp = env.downloads / "Unconfirmed 1234.crdownload"
        temp.write_text("Acme order")
        time.sleep(1.5)
        assert (env.downloads / "Unconfirmed 1234.crdownload").exists()  # in-progress file untouched
        temp.rename(env.downloads / "order.txt")
        assert wait_for(lambda: env.files() == [f"Acme/{TODAY} order.txt"]), env.files()
    finally:
        watcher.stop()


def test_rules_reload_and_bad_rules_keep_old(env):
    org = env.organizer()
    watcher = Watcher(org, env.config_dir)
    notes = []
    watcher.notify = lambda title, message: notes.append(title)
    watcher.start()
    try:
        rules = env.config_dir / "rules.yaml"
        rules.write_text(rules.read_text(encoding="utf-8").replace("move_to: Acme", "move_to: Brand/Acme"),
                         encoding="utf-8")
        assert wait_for(lambda: any(r.move_to == "Brand/Acme" for r in org.cfg.rules), 10)
        rules.write_text("rules: [broken", encoding="utf-8")
        assert wait_for(lambda: notes, 10)
        assert any(r.move_to == "Brand/Acme" for r in org.cfg.rules)  # old rules still active
    finally:
        watcher.stop()
