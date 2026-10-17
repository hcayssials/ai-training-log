"""Deterministic interval notation from raw laps (e.g. 10x400m, r:1'30 · 4x1km, r:1km).

This part of the code was a lot of iteration with AI.

Pure math, stdlib only. No LLM anywhere in this file, on purpose: a model that guesses
a rep scheme is worse than useless in a training log, so structure detection stays
deterministic and testable. analyze_laps() takes laps shaped {distance (m), moving_time
(s), elapsed_time (s), total_elevation_gain (m)}, which is exactly what fit_io.read_laps
returns.

The steps: label each lap effort/recovery by pace, trim warm-up/cool-down from the
edges, check the labels actually form a rep pattern, decide whether reps are measured by
distance or clocked by time, snap them to standard distances or clean durations, and
render the notation string.

Every threshold below is a named constant because each one was tuned against a real run
of mine that the detector misread; the comments next to them keep those stories short.
"""
import statistics
from typing import Optional

STANDARD_DISTANCES_M = [200, 400, 600, 800, 1000, 1200, 1500, 1609, 1800, 2000, 3000]
SNAP_TOLERANCE = 0.10
GPS_ARTIFACT_THRESHOLD = 50  # meters; sub-50m "laps" are GPS noise that once made phantom reps
EFFORT_THRESHOLD = 0.85
RECOVERY_THRESHOLD = 1.15
MIN_EFFORT_LAPS = 3
MAX_AMBIGUOUS_RATIO = 0.30
WEAK_GAP_MIN = 8  # s/km; below this a pace split reads as noise even if laps alternate

# Time-based sessions (6x3min, 8x90s, 5x7min) describe efforts by the clock rather
# than by distance. I don't enumerate "valid" durations; the check is that the reps
# were clocked to a consistent length, so any interval works.
EFFORT_MODE_SNAP_FRACTION = 0.70  # share of efforts that must snap to standard distances
DISTANCE_SNAP_RESIDUAL = 0.04  # how tightly efforts must hit a standard distance to trust it
TIME_CONSISTENCY_CV = 0.12  # max spread (stdev/mean) in rep duration to call it time-based
TIME_NOTATION_BREAK = 80  # below this, seconds ('75"'); at or above, minutes ("1'20")
LOOP_CONSISTENCY_CV = 0.02  # reps within ~2% of each other are the same (non-track) loop


def _pace_seconds_per_km(lap: dict) -> Optional[float]:
    """Lap pace in s/km; None for GPS-artifact laps (sub-50m) or zero moving time."""
    dist = lap.get("distance", 0)
    if dist < GPS_ARTIFACT_THRESHOLD:
        return None
    moving = lap.get("moving_time", 0)
    if moving <= 0:
        return None
    return moving / (dist / 1000)


def _snap_distance(meters: float, extra: tuple[int, ...] = ()) -> Optional[int]:
    """Nearest standard rep distance within 10%, else None (not a measured rep).

    `extra` adds distances for one call only (see analyze_laps)."""
    best, best_diff = None, float("inf")
    for std in sorted(STANDARD_DISTANCES_M + list(extra)):
        diff = abs(meters - std)
        if diff < best_diff:
            best, best_diff = std, diff
    if best is not None and best_diff / best <= SNAP_TOLERANCE:
        return best
    return None


def _coefficient_of_variation(values: list[float]) -> Optional[float]:
    """Relative spread (stdev / mean). A low value means the reps were tightly controlled."""
    clean = [v for v in values if v and v > 0]
    if len(clean) < 2:
        return None
    mean = statistics.mean(clean)
    if mean <= 0:
        return None
    return statistics.pstdev(clean) / mean


def _round_duration(seconds: float) -> int:
    """Round a rep's clocked duration to a clean target: a whole minute when within a
    few seconds, else the nearest 5 seconds. Works for any interval length, not a
    fixed menu."""
    minute_target = round(seconds / 60) * 60
    if minute_target > 0 and abs(seconds - minute_target) <= 4:
        return minute_target
    return int(round(seconds / 5) * 5)


def _find_bimodal_boundary(paces: list[Optional[float]]) -> Optional[float]:
    """
    Split efforts from recoveries at the clearest pace gap (> 30 sec/km), returning its
    midpoint.

    The largest gap usually *is* the divide — but a single near-standstill recovery (a
    standing rest at 10:00/km+) sits so far above the running paces that the biggest gap
    can land in that slow tail, *above* the true effort/recovery line, sweeping the
    warm-up, cool-down and real jog recoveries in as "efforts" (the 2026-07-12 run that
    misread as "3x3km + 1x2km + 1x1km"). So among the qualifying gaps, prefer the one
    whose split makes the trimmed laps strictly alternate effort/recovery — unmistakable
    rep structure — and fall back to the largest gap only when none does.
    """
    valid = sorted(p for p in paces if p is not None)
    if len(valid) < 4:
        return None
    candidates = [((lo + hi) / 2, hi - lo) for lo, hi in zip(valid, valid[1:]) if hi - lo > 30]
    if not candidates:
        return None

    def yields_alternation(mid: float) -> bool:
        labels = _labels_for_boundary(paces, mid)
        start, end = _strip_warmup_cooldown(labels)
        core = labels[start:end]
        return core.count("effort") >= MIN_EFFORT_LAPS and _strictly_alternating(core)

    alternating = [c for c in candidates if yields_alternation(c[0])]
    return max(alternating or candidates, key=lambda c: c[1])[0]


def _labels_for_boundary(paces: list[Optional[float]], boundary: float) -> list[str]:
    """Label every lap against a pace boundary: faster is effort, slower is recovery."""
    return ["ambiguous" if p is None else ("effort" if p < boundary else "recovery")
            for p in paces]


def _strictly_alternating(core: list[str]) -> bool:
    """True when a (warmup/cooldown-trimmed) label sequence reads effort, recovery,
    effort, ending on an effort: the unambiguous shape of a rep session."""
    return bool(core) and all(
        lab == ("effort" if i % 2 == 0 else "recovery") for i, lab in enumerate(core)
    )


def _alternation_boundary(paces: list[Optional[float]]) -> Optional[float]:
    """
    Fallback split for sessions whose effort/recovery gap is deliberately small, e.g.
    tempo reps with float-km recoveries, where the gap sits well under the 30 s/km
    bimodal bar. A modest gap counts as real structure only if splitting there makes
    the laps strictly alternate effort/recovery (warm-up/cool-down trimmed); natural
    pace drift on an easy run doesn't produce that pattern.
    """
    valid = sorted(p for p in paces if p is not None)
    if len(valid) < 2 * MIN_EFFORT_LAPS - 1:
        return None
    best_gap, best_mid = 0.0, None
    for lo, hi in zip(valid, valid[1:]):
        gap = hi - lo
        if gap < WEAK_GAP_MIN or gap <= best_gap:
            continue
        mid = (lo + hi) / 2
        labels = _labels_for_boundary(paces, mid)
        start, end = _strip_warmup_cooldown(labels)
        core = labels[start:end]
        if core.count("effort") < MIN_EFFORT_LAPS:
            continue
        if _strictly_alternating(core):
            best_gap, best_mid = gap, mid
    return best_mid


def _classify_laps(laps: list[dict], paces: list[Optional[float]]) -> list[str]:
    valid_paces = [p for p in paces if p is not None]
    if not valid_paces:
        return ["ambiguous"] * len(laps)

    boundary = _find_bimodal_boundary(paces)
    if boundary is None:
        boundary = _alternation_boundary(paces)

    if boundary is not None:
        return _labels_for_boundary(paces, boundary)

    # Fallback: median-relative thresholds
    median = statistics.median(valid_paces)
    labels = []
    for pace in paces:
        if pace is None:
            labels.append("ambiguous")
        elif pace < median * EFFORT_THRESHOLD:
            labels.append("effort")
        elif pace > median * RECOVERY_THRESHOLD:
            labels.append("recovery")
        else:
            labels.append("ambiguous")
    return labels


def _has_alternating_pattern(labels: list[str]) -> bool:
    effort_count = labels.count("effort")
    total = len(labels)
    ambiguous_count = labels.count("ambiguous")

    if effort_count < MIN_EFFORT_LAPS:
        return False
    if total > 0 and ambiguous_count / total > MAX_AMBIGUOUS_RATIO:
        return False

    # Check for alternating effort/recovery sequence (at least 3 effort+recovery pairs)
    pairs = 0
    i = 0
    while i < len(labels) - 1:
        if labels[i] == "effort" and labels[i + 1] == "recovery":
            pairs += 1
            i += 2
        else:
            i += 1
    if pairs >= 3:
        return True

    # Short rep sessions (3 reps: e,r,e,r,e) yield only N-1 pairs once the
    # cooldown is trimmed, but a strictly alternating core is unambiguous structure.
    if _strictly_alternating(labels):
        return True

    # Also accept: 3+ consecutive efforts (e.g., back-to-back intervals no recovery lap)
    consecutive = 0
    for label in labels:
        if label == "effort":
            consecutive += 1
            if consecutive >= 3:
                return True
        else:
            consecutive = 0

    return False


def _strip_warmup_cooldown(labels: list[str]) -> tuple[int, int]:
    """
    Trim leading and trailing non-effort laps (ambiguous or recovery) to exclude
    warm-up and cool-down segments. Returns (start_idx, end_idx) spanning
    [first_effort, last_effort] inclusive.
    """
    start = 0
    while start < len(labels) and labels[start] != "effort":
        start += 1
    end = len(labels)
    while end > start and labels[end - 1] != "effort":
        end -= 1
    return start, end


def _format_duration(seconds: int) -> str:
    """Running notation for a span of time. Below TIME_NOTATION_BREAK it reads in
    seconds ('45"'); at or above it reads in minutes ("1'20", "2'", "3'20")."""
    if seconds < TIME_NOTATION_BREAK:
        return f'{seconds}"'
    minutes, remaining = divmod(seconds, 60)
    if remaining == 0:
        return f"{minutes}'"
    return f"{minutes}'{remaining:02d}"


def _format_effort(value: int, mode: str) -> str:
    if mode == "time":
        return _format_duration(value)
    unit = "m" if value < 1000 else "km"
    scaled = value if value < 1000 else value / 1000
    scaled_str = str(int(scaled)) if scaled == int(scaled) else str(scaled)
    return f"{scaled_str}{unit}"


def _mean_snap_residual(effort_laps: list[dict], extra: tuple[int, ...] = ()) -> Optional[float]:
    """Average relative distance from each effort to its nearest standard distance.
    Small means I was really running measured distances; large means they only
    snapped incidentally (e.g. a 7min rep landing near a mile)."""
    residuals = []
    for lap in effort_laps:
        d = lap.get("distance", 0)
        snapped = _snap_distance(d, extra)
        if snapped:
            residuals.append(abs(d - snapped) / snapped)
    return statistics.mean(residuals) if residuals else None


def _choose_effort_mode(effort_laps: list[dict], extra: tuple[int, ...] = ()) -> str:
    """Decide whether efforts are best described by distance or by time.

    Distance is the canonical description, so a measured 400m never gets mislabeled
    as a time rep, but only when the reps hit standard distances *tightly*. If the
    distance snap is loose and the reps were instead clocked to a consistent duration
    (low spread, tighter than the distance spread), it is a time-based session; any
    interval length works."""
    if not effort_laps:
        return "distance"
    n = len(effort_laps)
    dist_frac = sum(1 for lap in effort_laps
                    if _snap_distance(lap.get("distance", 0), extra) is not None) / n
    residual = _mean_snap_residual(effort_laps, extra)

    # Genuinely measured distances (tight snap) are definitive, mixed sets included.
    if dist_frac >= EFFORT_MODE_SNAP_FRACTION and residual is not None and residual <= DISTANCE_SNAP_RESIDUAL:
        return "distance"

    # Otherwise, reps clocked to a consistent duration read as time-based.
    cv_time = _coefficient_of_variation([lap.get("elapsed_time", 0) for lap in effort_laps])
    cv_dist = _coefficient_of_variation([lap.get("distance", 0) for lap in effort_laps])
    if cv_time is not None and cv_time <= TIME_CONSISTENCY_CV and (cv_dist is None or cv_time <= cv_dist):
        return "time"

    return "distance"


def _format_rest(recovery_laps: list[dict]) -> Optional[str]:
    """Recoveries measured in distance (float kilometres, e.g. all ~1000m) read as a
    distance; anything else reads as the mean clocked duration.

    Rests are snapped on the standard distances only, never on analyze_laps' `extra`:
    a 90-second jog recovery covers about 300 m, and letting a short rep distance in
    here turns correctly-timed sessions into "14x400m, r:300m"."""
    if not recovery_laps:
        return None
    snaps = {_snap_distance(lap.get("distance", 0)) for lap in recovery_laps}
    residual = _mean_snap_residual(recovery_laps)
    if len(snaps) == 1 and None not in snaps and residual is not None \
            and residual <= DISTANCE_SNAP_RESIDUAL:
        return _format_effort(snaps.pop(), "distance")
    mean_rest = round(statistics.mean(lap["elapsed_time"] for lap in recovery_laps) / 5) * 5
    return _format_duration(mean_rest) if mean_rest > 0 else None


def _split_sets(effort_values: list[Optional[int]],
                sets: int) -> tuple[Optional[list[list[int]]], Optional[str]]:
    """Partition the reps into `sets` identical sets, or (None, why it doesn't fit).

    No thresholds in here, on purpose. `sets` is something I declare, so the only job
    is to check the reps agree with what I said — and to say plainly when they don't,
    because a silent fall back to the flat notation looks exactly like the argument
    was ignored."""
    if sets < 2:
        return None, f"sets={sets} is not a set structure (needs at least 2)"
    if any(v is None for v in effort_values):
        return None, "some reps didn't land on a rep distance, so they can't be split"
    n = len(effort_values)
    if n % sets:
        return None, f"{n} reps don't divide into {sets} sets"
    per = n // sets
    if per < 2:
        return None, f"{sets} sets of one rep isn't a set structure"
    blocks = [effort_values[i * per:(i + 1) * per] for i in range(sets)]
    if any(b != blocks[0] for b in blocks[1:]):
        return None, f"the {sets} sets aren't identical, so they can't share one notation"
    return blocks, None


def _build_notation(effort_values: list[Optional[int]], mode: str, rest: Optional[str],
                    sets: Optional[int] = None, between: Optional[str] = None) -> str:
    snapped = [v for v in effort_values if v is not None]
    if not snapped:
        return ""

    if sets:
        # _split_sets has already checked the sets are identical, so one block speaks
        # for all of them: 4x400m repeated four times is "4x4x400m", and a repeating
        # ladder keeps its order inside the brackets ("5x(800m + 400m)").
        block = snapped[:len(snapped) // sets]
        notation = (f"{sets}x{len(block)}x{_format_effort(block[0], mode)}"
                    if len(set(block)) == 1
                    else f'{sets}x({" + ".join(_format_effort(v, mode) for v in block)})')
    else:
        # Group by value preserving order of first appearance
        groups: dict[int, int] = {}
        for v in snapped:
            groups[v] = groups.get(v, 0) + 1
        parts = [f"{count}x{_format_effort(value, mode)}" for value, count in groups.items()]
        notation = " + ".join(parts)

    if rest:
        notation += f", r:{rest}"
    if between and between != rest:
        # Only worth saying when the break actually differs; "r:60\" (60\" between sets)"
        # is noise, and that is what a set I declared but ran straight through looks like.
        notation += f" ({between} between sets)"

    return notation


def analyze_laps(laps: list[dict], extra_distances: tuple[int, ...] = (),
                 sets: Optional[int] = None) -> dict:
    """Rep scheme from a lap table. `extra_distances` adds rep distances for this run
    only — 150 and 300 on a speed-maintenance day, say; `sets` says how many sets the
    reps were run in, turning "16x400m" into "4x4x400m".

    `sets` is declared for the same reason `extra_distances` is. 4x4x400 and 16x400 are
    the same lap table — every rep the same distance, so their order carries nothing —
    and the only evidence of a set break is a longer recovery lap, which is exactly what
    stopping to retie a lace also looks like. Declaring it also fixes the rest: the
    between-set break stops being averaged into r:, because we now know which lap it is.

    They are not in STANDARD_DISTANCES_M and shouldn't be: 300 sits in the gap between
    200 and 400, and that gap is where jog fragments and lap-button fumbles land, so
    naming it globally bolts a phantom "1x300m" onto 59 sessions that already read
    correctly. Nor can the gap be closed automatically — 5x150m of strides on an easy
    run and 5x150m of work on a Friday are the same lap table, and the run I know is a
    session has the *lower* share of time at hard pace. Which it was is mine to say."""
    if not laps:
        return {
            "has_structure": False,
            "notation": None,
            "effort_laps": [],
            "recovery_laps": [],
            "warnings": ["No lap data available"],
        }

    paces = [_pace_seconds_per_km(lap) for lap in laps]
    labels = _classify_laps(laps, paces)

    # Trim warm-up/cool-down ambiguous laps from the edges
    start, end = _strip_warmup_cooldown(labels)
    trimmed_labels = labels[start:end]
    trimmed_laps = laps[start:end]

    warnings = []
    gps_artifacts = sum(1 for p in paces if p is None)
    if gps_artifacts > 0:
        warnings.append(f"{gps_artifacts} lap(s) excluded due to GPS noise")

    if not _has_alternating_pattern(trimmed_labels):
        return {
            "has_structure": False,
            "notation": None,
            "effort_laps": [],
            "recovery_laps": [],
            "warnings": warnings,
        }

    effort_indices = [i for i, l in enumerate(trimmed_labels) if l == "effort"]
    recovery_indices = [i for i, l in enumerate(trimmed_labels) if l == "recovery"]

    effort_laps = [trimmed_laps[i] for i in effort_indices]
    mode = _choose_effort_mode(effort_laps, extra_distances)

    if mode == "time":
        effort_values = [_round_duration(lap.get("elapsed_time", 0)) for lap in effort_laps]
    else:
        dists = [lap.get("distance", 0) for lap in effort_laps]
        cv = _coefficient_of_variation(dists)
        if cv is not None and cv <= LOOP_CONSISTENCY_CV:
            # Reps within ~2% of each other are one set (e.g. 3x a 2.7km bridle-path
            # lap): snap their mean once, to a track distance when genuinely close and
            # the nearest 50m otherwise, rather than letting laps that straddle the
            # snap tolerance split the set (2695/2702/2683 must not read "1x3km").
            mean_d = statistics.mean(dists)
            common = _snap_distance(mean_d, extra_distances) or int(round(mean_d / 50) * 50)
            effort_values = [common] * len(effort_laps)
        else:
            snapped = [_snap_distance(lap["distance"], extra_distances) for lap in effort_laps]
            unsnapped = sum(1 for v in snapped if v is None)
            effort_values = snapped
            # Rescue the LAST effort lap only, and only once the rest already form a rep
            # scheme: a trailing odd lap is a rep I let run long (4 Aug 2026 ran five, the
            # fifth 1326 m, and shipped as "4x1.2km" with four splits). Leading and middle
            # ones stay dropped on purpose — my warm-up tempo lands there, and rescuing it
            # would re-create the "1x3km +" prefix this guard exists to prevent.
            if (snapped and snapped[-1] is None
                    and sum(1 for v in snapped[:-1] if v is not None) >= MIN_EFFORT_LAPS):
                effort_values = snapped[:-1] + [int(round(effort_laps[-1]["distance"] / 50) * 50)]
                unsnapped -= 1
                warnings.append("last effort lap ran off the standard distances and is shown "
                                "at the nearest 50 m")
            if unsnapped > 0:
                warnings.append(f"{unsnapped} effort lap(s) had non-standard distances (GPS noise?)")

    # Labeling needed enough efforts, but efforts that don't snap are dropped from
    # the notation, so re-check the bar on what survives; without this, an easy run
    # with one stride-y 800m shipped as "1x800m".
    reps_in_notation = sum(1 for v in effort_values if v is not None)
    if reps_in_notation < MIN_EFFORT_LAPS:
        warnings.append(
            f"only {reps_in_notation} of {len(effort_laps)} effort lap(s) survived into a "
            "rep scheme — too few to call it interval structure")
        return {
            "has_structure": False,
            "notation": None,
            "effort_laps": [],
            "recovery_laps": [],
            "warnings": warnings,
        }

    # A declared set count names the break laps: the recovery immediately after each
    # set's last rep. Splitting them out keeps r: to the rep rest and reports the break
    # separately, which is how I write it by hand ("r:1'30, 2' between sets").
    sets_applied, breaks = None, []
    if sets is not None:
        blocks, why_not = _split_sets(effort_values, sets)
        if blocks is None:
            warnings.append(f"sets={sets} not applied: {why_not}")
        else:
            sets_applied = sets
            per = len(effort_values) // sets
            for k in range(1, sets):
                after = effort_indices[k * per - 1] + 1
                if after in recovery_indices:
                    breaks.append(after)

    rest = _format_rest([trimmed_laps[i] for i in recovery_indices if i not in breaks])
    between = _format_rest([trimmed_laps[i] for i in breaks]) if breaks else None
    notation = _build_notation(effort_values, mode, rest, sets_applied, between)

    # Global lap indices (relative to original laps list, not trimmed)
    global_effort = [start + i for i in effort_indices]
    global_recovery = [start + i for i in recovery_indices]

    return {
        "has_structure": bool(notation),
        "notation": notation or None,
        "effort_laps": global_effort,
        "effort_values": effort_values,  # parallel to effort_laps; None = not in notation
        "mode": mode,  # "distance" or "time" — how the reps were clocked
        "sets": sets_applied,  # the declared set count, once the reps agreed with it
        "recovery_laps": global_recovery,
        "warnings": warnings,
    }
