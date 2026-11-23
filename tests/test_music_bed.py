# SPDX-License-Identifier: Apache-2.0
"""The music bed is deterministic, bounded, and keeps the loudness and low end of the previous bed."""
import numpy as np

from motionbrief.audio.sfx import SR, music_bed

# Measured on the previous (pad-based) bed, 60 s renders: RMS dBFS.
OLD_RMS_DB_GROOVE = -18.76
OLD_RMS_DB_PLAIN = -20.75


def _rms_db(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)))


def _low_share(x: np.ndarray, cut_hz: float = 100.0) -> float:
    spec = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    return float(spec[freqs < cut_hz].sum() / spec.sum())


def test_music_bed_is_deterministic():
    a = music_bed(6.0, groove=True)
    b = music_bed(6.0, groove=True)
    assert np.array_equal(a, b)


def test_music_bed_length_matches_seconds():
    assert len(music_bed(7.5)) == int(SR * 7.5)
    assert len(music_bed(7.5, groove=True)) == int(SR * 7.5)


def test_music_bed_peak_below_one():
    for groove in (False, True):
        assert np.max(np.abs(music_bed(60.0, groove=groove))) <= 1.0


def test_music_bed_rms_matches_previous_bed():
    assert abs(_rms_db(music_bed(60.0, groove=True)) - OLD_RMS_DB_GROOVE) <= 1.5
    assert abs(_rms_db(music_bed(60.0, groove=False)) - OLD_RMS_DB_PLAIN) <= 1.5


def test_music_bed_low_end_is_clean_without_groove():
    assert _low_share(music_bed(30.0, groove=False)) < 0.05


def test_no_pitch_sweeps_on_cuts():
    """Cuts get short struck sounds only: glides, swells and risers read as a 'woo' on every slide change."""
    from motionbrief.audio.sound_design import resolve
    from motionbrief.ir.models import load

    cues = resolve(load("fixtures/isp_v01.json"))
    assert not [c for c in cues if c.sfx in ("glide", "swell", "riser")]
