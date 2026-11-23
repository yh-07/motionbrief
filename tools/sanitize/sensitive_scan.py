# SPDX-License-Identifier: Apache-2.0
"""Clean-room sanitizer: blocks secrets, sensitive terms, private paths/emails/URLs,
non-placeholder .env values, missing SPDX headers and image metadata (EXIF).

The REAL denylist is never committed. It is read from (first match):
  1. $MB_DENYLIST            (newline-separated terms, injected as a CI secret)
  2. $MB_DENYLIST_FILE       (path to a local, gitignored file)
  3. tools/sanitize/denylist.local.txt  (gitignored)
`denylist.example.txt` contains only harmless example terms and is used by tests.

Usage:  python tools/sanitize/sensitive_scan.py [--root .] [--checks all|secrets,terms,...]
Exit 1 on any finding (fail-fast in release-guard.yml).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".md", ".yml", ".yaml", ".toml", ".txt", ".cfg",
            ".ini", ".sh", ".srt", ".example", ".html", ".css"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
SKIP_DIRS = {".git", "node_modules", "work", "outbox", "_processed", "_processing", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "build",
             ".mypy_cache", ".ruff_cache"}
SPDX_EXT = {".py", ".ts", ".tsx", ".mjs", ".js"}

SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "generic_sk_key": re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "bearer_literal": re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=]{24,}"),
}
PUBLIC_ARTIFACT_PATTERNS = {
    "abs_unix_home": re.compile(r"(?<![\w.])/(?:home|Users)/[A-Za-z0-9_.\-]+/"),
    "abs_windows_user": re.compile(r"[A-Za-z]:\\\\?Users\\\\?[A-Za-z0-9_.\-]+"),
    "email": re.compile(r"\b[A-Za-z0-9._%+\-]+@(?!example\.(?:com|org)\b|users\.noreply\.github\.com\b)"
                        r"[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "private_url": re.compile(r"https?://(?:[a-z0-9\-]+\.)*(?:corp|internal|intranet|local|lan)(?:[:/]|\b)", re.I),
    "rfc1918_ip": re.compile(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?:\.\d{1,3})?\b"),
}
# Allow-list for this file's own pattern literals and the env example.
SELF = Path(__file__).resolve()


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            yield Path(dirpath) / f


def load_denylist(root: Path) -> list[str]:
    if os.environ.get("MB_DENYLIST"):
        raw = os.environ["MB_DENYLIST"]
    elif os.environ.get("MB_DENYLIST_FILE") and Path(os.environ["MB_DENYLIST_FILE"]).exists():
        raw = Path(os.environ["MB_DENYLIST_FILE"]).read_text(encoding="utf-8")
    elif (root / "tools/sanitize/denylist.local.txt").exists():
        raw = (root / "tools/sanitize/denylist.local.txt").read_text(encoding="utf-8")
    else:
        return []
    return [t.strip() for t in raw.splitlines() if t.strip() and not t.startswith("#")]


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def scan(root: Path, checks: set[str], denylist: list[str] | None = None) -> list[str]:
    findings: list[str] = []
    deny = [d.lower() for d in (denylist if denylist is not None else load_denylist(root))]
    if "terms" in checks and not deny:
        print("note: no sensitive-term denylist provided (MB_DENYLIST / MB_DENYLIST_FILE); term scan skipped",
              file=sys.stderr)
    for p in iter_files(root):
        rel = p.relative_to(root)
        if p.resolve() == SELF or rel.name == "denylist.example.txt":
            continue
        ext = p.suffix.lower()
        if ext in IMG_EXT and "exif" in checks:
            findings += [f"{rel}: {m}" for m in image_metadata(p)]
            continue
        if ext not in TEXT_EXT and p.name not in (".env.example", ".gitignore", "LICENSE"):
            continue
        txt = _read(p)
        if txt is None:
            continue
        low = txt.lower()
        if "secrets" in checks:
            for name, rx in SECRET_PATTERNS.items():
                for m in rx.finditer(txt):
                    findings.append(f"{rel}:{txt[:m.start()].count(chr(10)) + 1}: secret[{name}]")
        if "terms" in checks:
            for term in deny:
                if term in low:
                    findings.append(f"{rel}: sensitive term (#{deny.index(term)})")  # never echo the term
        if "public" in checks:
            for name, rx in PUBLIC_ARTIFACT_PATTERNS.items():
                for m in rx.finditer(txt):
                    findings.append(f"{rel}:{txt[:m.start()].count(chr(10)) + 1}: {name}: {m.group(0)[:40]}")
        if "env" in checks and p.name.startswith(".env"):
            for i, line in enumerate(txt.splitlines(), 1):
                if "=" in line and not line.lstrip().startswith("#"):
                    v = line.split("=", 1)[1].strip()
                    if v and v != "REPLACE_ME" and not v.startswith("http://127.0.0.1"):
                        findings.append(f"{rel}:{i}: .env value must be REPLACE_ME")
        if "spdx" in checks and ext in SPDX_EXT and "SPDX-License-Identifier" not in txt[:300]:
            findings.append(f"{rel}: missing SPDX-License-Identifier header")
    return findings


def image_metadata(p: Path) -> list[str]:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return []
    out = []
    try:
        with Image.open(p) as im:
            if im.getexif():
                out.append("EXIF metadata present (scrub with exiftool -all=)")
            for k in ("Author", "Software", "Comment", "Description", "Copyright", "Creation Time"):
                if k in getattr(im, "text", {}) or k in im.info:
                    out.append(f"metadata field {k!r} present")
    except Exception:
        pass
    return out


def git_history_secrets(root: Path) -> list[str]:
    """Cheap history scan for environments without gitleaks (CI uses gitleaks too)."""
    try:
        log = subprocess.run(["git", "-C", str(root), "log", "-p", "--all"], capture_output=True, text=True,
                             timeout=120).stdout
    except Exception:
        return []
    return [f"git history: secret[{n}]" for n, rx in SECRET_PATTERNS.items() if rx.search(log)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--checks", default="all")
    ap.add_argument("--history", action="store_true")
    a = ap.parse_args(argv)
    allc = {"secrets", "terms", "public", "env", "spdx", "exif"}
    checks = allc if a.checks == "all" else set(a.checks.split(","))
    root = Path(a.root).resolve()
    f = scan(root, checks)
    if a.history:
        f += git_history_secrets(root)
    for x in f:
        print("FINDING", x)
    print(f"sanitize: {len(f)} finding(s) [{','.join(sorted(checks))}]")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
