# SPDX-License-Identifier: Apache-2.0
"""Drop-folder contract: front-matter, ids, which files count as inputs, status lifecycle."""
from pathlib import Path

from motionbrief.apps import inbox


def test_front_matter_and_ids():
    meta, body = inbox.front_matter("---\nid: ISP Ep-2!\ntitle: 夜景\nproduce: auto\n---\n## 3. 完整旁白\n")
    assert meta["produce"] == "auto" and body.startswith("## 3.")
    assert inbox.video_id(meta, Path("x.md")) == "isp_ep_2"
    assert inbox.video_id({}, Path("2026 night.md")) == "v_2026_night"
    assert inbox.front_matter("no front matter")[0] == {}


def test_only_real_inputs_are_picked_up(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "INBOX", tmp_path)
    for name in ("a.md", "b.plan.json", "c.shots.md", "README.md", "TEMPLATE.md", ".hidden.md", "_x.md",
                 "d.md.tmp", "e.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert [p.name for p in inbox.pending_inputs()] == ["a.md", "b.plan.json"]


def test_status_lifecycle_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "OUTBOX", tmp_path)
    inbox._set("v1", "queued", source="a.md")
    st = inbox._set("v1", "awaiting_approval", message="review")
    assert st["source"] == "a.md" and [h[1] for h in st["history"]] == ["queued", "awaiting_approval"]
    assert inbox.status("v1")["state"] == "awaiting_approval"


def test_failed_input_is_reported_and_archived(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "INBOX", tmp_path / "in")
    monkeypatch.setattr(inbox, "OUTBOX", tmp_path / "out")
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "bad.md").write_text("---\nid: bad_one\n---\n(no sections)", encoding="utf-8")
    monkeypatch.setattr(inbox, "storyboard", lambda src: (_ for _ in ()).throw(ValueError("no sections found")))
    inbox.run_once()
    assert inbox.status("bad_one")["state"] == "failed" and "no sections" in inbox.status("bad_one")["message"]
    assert not list((tmp_path / "in").glob("*.md")) and list((tmp_path / "in" / "_processed").iterdir())
