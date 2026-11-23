# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "tools/sanitize/sensitive_scan.py")
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)

FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"  # split so this file itself is clean


def test_clean_repo_is_green():
    assert ss.scan(ROOT, {"secrets", "public", "env", "spdx", "exif"}, denylist=[]) == []


def test_planted_fake_secret_fails(tmp_path):
    (tmp_path / "leak.py").write_text(f"# SPDX-License-Identifier: Apache-2.0\nKEY = '{FAKE_AWS}'\n")
    f = ss.scan(tmp_path, {"secrets"}, denylist=[])
    assert any("aws_access_key" in x for x in f)


def test_denylist_terms_are_not_echoed(tmp_path):
    (tmp_path / "notes.md").write_text("mentions example-codename-alpha here")
    f = ss.scan(tmp_path, {"terms"}, denylist=["example-codename-alpha"])
    assert f and "example-codename-alpha" not in f[0]


def test_public_artifact_rules(tmp_path):
    home = "/" + "home/alice/proj"
    mail = "bob" + "@" + "corp-mail.com"
    (tmp_path / "a.md").write_text(f"see {home} and mail {mail}")
    (tmp_path / ".env.example").write_text("API_KEY=abc123\n")
    f = ss.scan(tmp_path, {"public", "env"}, denylist=[])
    assert any("abs_unix_home" in x for x in f) and any("email" in x for x in f) and any(".env" in x for x in f)
