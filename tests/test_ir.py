# SPDX-License-Identifier: Apache-2.0
import copy
import json

from motionbrief.ir.models import SCHEMA_PATH, export_json_schema, migrate, validate


def codes(issues):
    return {i.code for i in issues}


def test_fixture_valid(isp_raw):
    ir, issues = validate(isp_raw)
    assert ir is not None and not [i for i in issues if i.severity == "error"], issues
    assert ir.duration == 70 and ir.video.durationTier == "core"
    assert all(s.citations for s in ir.scenes if s.isFactual and s.narration)


def test_committed_schema_matches_models():
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == json.loads(json.dumps(export_json_schema()))


def test_fact_scene_without_citation_fails(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][2]["citations"] = []
    assert "CITATION_MISSING" in codes(validate(bad)[1])


def test_unknown_component_fails(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][0]["visualObjects"][0]["component"] = "InventedThing"
    assert "COMPONENT_UNKNOWN" in codes(validate(bad)[1])


def test_blender_cel_requires_hero(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][1]["assetStyle"] = "blender_cel"
    assert "BLENDER_NON_HERO" in codes(validate(bad)[1])


def test_bands_range(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][2]["visualObjects"][1]["materialStyle"]["bands"] = 7
    assert "TOON_BANDS" in codes(validate(bad)[1])


def test_duration_not_hard_locked(isp_raw):
    """Tier mismatch is advisory (warning), only absurd lengths are errors (R-18)."""
    raw = copy.deepcopy(isp_raw)
    raw["video"]["durationTier"] = "micro"
    ir, issues = validate(raw)
    tier = [i for i in issues if i.code == "DURATION_TIER"]
    assert ir is not None and tier and tier[0].severity == "warning"
    assert not [i for i in issues if i.severity == "error"]


def test_timeline_gap_is_error(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][3]["tStart"] = 15.5
    assert "TIMELINE_GAP" in codes(validate(bad)[1])


def test_enum_violation_is_schema_error(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][0]["camera"]["move"] = "dolly_zoom"
    ir, issues = validate(bad)
    assert ir is None and "SCHEMA" in codes(issues)


def test_migrate_v11_snippet(legacy_raw):
    m = migrate(legacy_raw)
    assert m["irVersion"] == "1.2.0" and "palette" in m and m["video"]["durationTier"] == "core"
    ir, issues = validate(legacy_raw)
    assert ir is not None  # structurally valid after migration (fragment => duration errors expected)
    assert "SCHEMA" not in codes(issues)
