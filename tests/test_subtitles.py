# SPDX-License-Identifier: Apache-2.0
from motionbrief.audio.mix import VoiceSeg, build_subtitles, chunk_text, parse_srt, write_srt


def test_chunking_respects_max_and_numbers():
    for t in ["拍30帧视频时，这整条流水线每帧只有约33毫秒。", "第四步，色调映射，把亮部和暗部压进屏幕能显示的范围。"]:
        chunks = chunk_text(t, 13)
        assert all(len(c) <= 13 for c in chunks)
        assert not any(c.startswith("毫秒") or c.endswith("约3") for c in chunks)


def test_srt_roundtrip_no_overlap(tmp_path):
    segs = [VoiceSeg("s01", 0.15, 2.7, "四个摄像头，拍下的其实都不是照片。", tmp_path / "a.wav"),
            VoiceSeg("s02", 4.15, 3.9, "传感器给出的只是RAW数据，每个像素只记一种颜色。", tmp_path / "b.wav")]
    cues = build_subtitles(segs)
    write_srt(cues, tmp_path / "x.srt")
    back = parse_srt(tmp_path / "x.srt")
    assert [c[2] for c in back] == [c[2] for c in cues]
    assert all(a[1] <= b[0] for a, b in zip(back, back[1:]))
