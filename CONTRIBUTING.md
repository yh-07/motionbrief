# Contributing

- Clean-room only: never paste code, text, assets or names from private/employer sources.
- Every source file starts with `# SPDX-License-Identifier: Apache-2.0` (or `//` for TS/JS).
- New visual component: registry entry → SVG implementation → test → only then use it in IR.
- Change IR models ⇒ run `motionbrief export-schema` and commit the schema.
- Before a PR: `pytest -q` and `python tools/sanitize/sensitive_scan.py --root .` must be green.
- Committed media must have no EXIF/metadata; use original or properly licensed assets only.
