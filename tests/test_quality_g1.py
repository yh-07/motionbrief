# SPDX-License-Identifier: Apache-2.0
import copy

from motionbrief.quality.deterministic import check_ir


def failed(rep):
    return {c.name for c in rep.checks if not c.passed}


def test_fixture_passes_ir_g1(isp_raw):
    ir, rep = check_ir(isp_raw)
    assert rep.passed, rep.summary()


def test_forbidden_transition(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][4]["transitionIn"]["type"] = "whip"   # legal in IR schema, illegal in cartoon-tech-v1
    assert "style_profile" in failed(check_ir(bad)[1])


def test_safe_area_violation(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][0]["typography"][0]["text"] = "这是一个非常非常长的标题会超出安全区"
    bad["scenes"][0]["typography"][0]["style"] = "headline"
    assert "safe_area" in failed(check_ir(bad)[1])


def test_cta_ending_rejected(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][-2]["narration"] = "喜欢的话记得点赞关注。"
    assert "no_cta_ending" in failed(check_ir(bad)[1])


def test_hook_must_land_in_3s(isp_raw):
    bad = copy.deepcopy(isp_raw)
    for m in bad["scenes"][0]["motionGrammar"]:
        if m["grammar"] in ("impact", "reveal"):
            m["at"] = 3.6
    bad["scenes"][0]["soundCues"] = [c for c in bad["scenes"][0]["soundCues"] if c["sfx"] != "bass_hit"]
    assert "cadence_hook" in failed(check_ir(bad)[1])


def test_bass_hit_must_align(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][2]["soundCues"][1]["at"] = 12.0
    assert "sound_beat_alignment" in failed(check_ir(bad)[1])


def test_emoji_rejected(isp_raw):
    bad = copy.deepcopy(isp_raw)
    bad["scenes"][1]["typography"][0]["text"] = "RAW\U0001F525"
    assert "style_profile" in failed(check_ir(bad)[1])
