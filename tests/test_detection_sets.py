"""analyze_laps(sets=...) — the set count I declare, not one the detector guesses.

4x4x400 and 16x400 are the same lap table: every rep the same distance, so their order
says nothing, and the only hint of a break is a longer recovery lap — which is also what
stopping to retie a lace looks like. So the count is an argument, and these cases pin
both halves: that declaring it works, and that a declaration the reps disagree with is
refused out loud rather than fudged.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runlog.detection import _split_sets, analyze_laps  # noqa: E402


def _lap(distance, seconds):
    return {"distance": distance, "moving_time": seconds, "elapsed_time": seconds,
            "total_elevation_gain": 0}


def _session(reps, rest_m=250, rest_s=60, breaks=(), break_m=260, break_s=180):
    """Warm-up, alternating reps and jog recoveries, cool-down. Reps run at 200 s/km.

    Recovery distances deliberately miss the standard menu, so rests read as a
    clocked duration rather than snapping to "r:200m".

    `breaks` holds 0-based rep positions after which the recovery is a longer break."""
    laps = [_lap(3000, 900)]
    for i, d in enumerate(reps):
        laps.append(_lap(d, d * 0.2))
        if i in breaks:
            laps.append(_lap(break_m, break_s))
        else:
            laps.append(_lap(rest_m, rest_s))
    laps.append(_lap(3000, 960))
    return laps


# ── declaring a set count ──────────────────────────────

def test_uniform_reps_read_as_nxmxd():
    laps = _session([400] * 16, breaks=(3, 7, 11))
    assert analyze_laps(laps, sets=4)["notation"].startswith("4x4x400m")

def test_the_same_laps_without_the_argument_stay_flat():
    laps = _session([400] * 16, breaks=(3, 7, 11))
    assert analyze_laps(laps)["notation"].startswith("16x400m")

def test_a_repeating_ladder_keeps_its_order():
    laps = _session([800, 400] * 5, breaks=(1, 3, 5, 7))
    assert analyze_laps(laps, sets=5)["notation"].startswith("5x(800m + 400m)")

def test_the_applied_count_is_reported():
    laps = _session([400] * 12, breaks=(3, 7))
    assert analyze_laps(laps, sets=3)["sets"] == 3
    assert analyze_laps(laps)["sets"] is None


# ── the break lap stops dragging r: ────────────────────

def test_rest_excludes_the_between_set_break():
    # Rep rest 60 s throughout, one 180 s break: the flat reading averages them.
    laps = _session([400] * 8, rest_s=60, breaks=(3,), break_s=180)
    assert "r:60\"" in analyze_laps(laps, sets=2)["notation"]
    assert "r:60\"" not in analyze_laps(laps)["notation"]

def test_the_break_is_reported_separately():
    laps = _session([400] * 8, rest_s=60, breaks=(3,), break_s=180)
    assert "(3' between sets)" in analyze_laps(laps, sets=2)["notation"]

def test_no_between_clause_when_nothing_separates_the_sets():
    laps = _session([400] * 8, rest_s=60)          # every recovery identical
    assert "between sets" not in analyze_laps(laps, sets=2)["notation"]


# ── a declaration the reps refuse ──────────────────────

def test_a_count_that_does_not_divide_is_refused_out_loud():
    result = analyze_laps(_session([400] * 10), sets=4)
    assert result["notation"].startswith("10x400m")
    assert result["sets"] is None
    assert any("sets=4 not applied" in w for w in result["warnings"])

def test_sets_that_are_not_identical_are_refused():
    blocks, why = _split_sets([800, 400, 400, 800], sets=2)
    assert blocks is None and "aren't identical" in why

def test_one_rep_per_set_is_not_a_set_structure():
    blocks, why = _split_sets([400] * 4, sets=4)
    assert blocks is None and "one rep" in why

def test_fewer_than_two_sets_is_refused():
    blocks, why = _split_sets([400] * 4, sets=1)
    assert blocks is None and "at least 2" in why

def test_unsnapped_reps_cannot_be_split():
    blocks, why = _split_sets([400, None, 400, 400], sets=2)
    assert blocks is None and "rep distance" in why
