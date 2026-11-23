# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# tests may use host tools from .env (ffmpeg/cairo paths) but never the live LLM profile:
# set before motionbrief is imported, since .env only fills variables that are unset
os.environ["MOTIONBRIEF_CAPABILITIES"] = str(ROOT / "motionbrief/llm/capabilities.example.yaml")


@pytest.fixture
def isp_raw():
    return json.loads((ROOT / "fixtures/isp_v01.json").read_text(encoding="utf-8"))


@pytest.fixture
def legacy_raw():
    return json.loads((ROOT / "fixtures/legacy_v1_1_s03.json").read_text(encoding="utf-8"))
