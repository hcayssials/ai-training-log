"""analyze_laps(extra_distances=...) — rep distances named for one run only.

150 and 300 are deliberately absent from STANDARD_DISTANCES_M: 300 sits in the gap
between 200 and 400, and that gap is what keeps jog fragments out of the notation.
These cases pin both halves — that naming a distance works, and that not naming one
leaves every other run exactly as it was.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runlog import detection  # noqa: E402
from runlog.detection import _snap_distance, analyze_laps  # noqa: E402


def _lap(distance, seconds):
    return {"distance": distance, "moving_time": seconds, "elapsed_time": seconds,
            "total_elevation_gain": 0}


def _session(reps, rest_m=200, rest_s=120):
    """Warm-up, alternating reps and jog recoveries, cool-down. Reps run at 200 s/km."""
    laps = [_lap(3000, 900)]
    for d in reps:
        laps.append(_lap(d, d * 0.2))
        laps.append(_lap(rest_m, rest_s))
    laps.append(_lap(3000, 960))
    return laps


# ── the distances stay out of the global menu ──────────

def test_150_and_300_are_not_standard():
    assert 150 not in detection.STANDARD_DISTANCES_M
    assert 300 not in detection.STANDARD_DISTANCES_M

def test_an_unnamed_short_rep_does_not_snap():
    assert _snap_distance(296) is None
    assert _snap_distance(141) is None

def test_naming_the_distance_snaps_it():
    assert _snap_distance(296, (300,)) == 300
    assert _snap_distance(141, (150,)) == 150

def test_naming_a_distance_does_not_move_laps_that_already_snapped():
    for metres in (196, 205, 385, 403, 995, 1609, 2980):
        assert _snap_distance(metres, (150, 300)) == _snap_distance(metres)

def test_naming_a_distance_does_not_widen_its_band():
    # 340 is 13% off 300 — outside SNAP_TOLERANCE either way.
    assert _snap_distance(340, (300,)) is None


# ── end to end ─────────────────────────────────────────

def test_a_short_rep_session_is_dropped_when_unnamed():
    result = analyze_laps(_session([138, 137, 141, 140, 143, 294, 301, 295]))
    assert not result["has_structure"]
    assert result["notation"] is None

def test_the_same_session_reads_once_the_distances_are_named():
    laps = _session([138, 137, 141, 140, 143, 294, 301, 295])
    result = analyze_laps(laps, (150, 300))
    assert result["has_structure"]
    assert result["notation"].startswith("5x150m + 3x300m")
    assert result["mode"] == "distance"

def test_short_reps_mixed_with_a_standard_distance():
    # The Friday shape no automatic fallback can reach: the 200s snap on their own, so
    # there is no failure to retry from, and the 150s are mangled — the trailing-rep
    # rescue reports one of the three and the other two vanish.
    laps = _session([198, 201, 196, 141, 138, 143])
    unnamed = analyze_laps(laps)
    assert unnamed["notation"].startswith("3x200m + 1x150m")
    assert sum(1 for v in unnamed["effort_values"] if v is not None) == 4  # 6 were run

    named = analyze_laps(laps, (150,))
    assert named["notation"].startswith("3x200m + 3x150m")
    assert all(v is not None for v in named["effort_values"])

def test_rests_are_never_snapped_to_a_named_distance():
    # A 90-second jog covers about 300 m; it is a rest, not a measured float.
    laps = _session([294, 301, 295, 298], rest_m=300, rest_s=90)
    result = analyze_laps(laps, (300,))
    assert result["has_structure"]
    assert "r:300m" not in result["notation"]
    assert result["notation"].endswith("r:1'30")

def test_naming_nothing_leaves_a_normal_session_untouched():
    laps = _session([403, 398, 401, 399])
    assert analyze_laps(laps)["notation"] == analyze_laps(laps, ())["notation"]
    assert analyze_laps(laps)["notation"].startswith("4x400m")
