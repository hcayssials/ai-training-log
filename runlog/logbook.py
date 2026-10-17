"""The training log: one CSV, one row per run, newest first.

Sync refreshes Garmin's numbers on every run but never touches the two columns that
are yours: "Description" (written by Claude, with your OK) and "My notes".

Saved as UTF-8 with a byte-order mark, so Excel on Windows shows accents and "·"
correctly instead of mojibake.
"""

import csv
import json
import os
from datetime import date, datetime, timedelta

from . import detection

KM_PER_MI = 1.609344
FT_PER_M = 3.28084
YOURS = ("description", "my_notes")
OVERRIDES = "laps_overrides.json"  # notation you (or Claude, with your OK) corrected


def columns(units):
    d, e = ("mi", "ft") if units == "mi" else ("km", "m")
    return [("date", "Date"), ("start", "Start"), ("name", "Name"), ("type", "Type"),
            ("distance", f"Distance ({d})"), ("time", "Time"), ("pace", f"Pace (/{d})"),
            ("avg_hr", "Avg HR"), ("max_hr", "Max HR"), ("elevation", f"Elevation ({e})"),
            ("laps", "Laps"), ("training_effect", "Training effect"),
            ("garmin_note", "Garmin note"), ("description", "Description"),
            ("my_notes", "My notes"), ("activity_id", "Activity ID")]


# -- formatting ------------------------------------------------------------------

def clock(seconds):
    s = int(round(seconds or 0))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def seconds_of(text):
    parts = [int(p) for p in str(text or "0").split(":") if p.strip().isdigit()]
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def pace(seconds, distance_m, units):
    unit_m = KM_PER_MI * 1000 if units == "mi" else 1000
    if not seconds or not distance_m or distance_m < 50:
        return ""
    return clock(seconds / (distance_m / unit_m))


def distance(distance_m, units):
    return round((distance_m or 0) / (KM_PER_MI * 1000 if units == "mi" else 1000), 2)


def label(text):
    return (text or "").replace("_", " ").title()


def interval_notation(laps):
    if len(laps) < 3:
        return ""
    try:
        res = detection.analyze_laps(laps)
    except Exception:
        return ""
    return (res.get("notation") or "") if res.get("has_structure") else ""


def row_from(activity, laps, units):
    start = activity.get("startTimeLocal") or ""
    dist_m = activity.get("distance") or 0
    secs = activity.get("duration") or activity.get("movingDuration") or 0
    elev = activity.get("elevationGain")
    if elev is not None and units == "mi":
        elev = elev * FT_PER_M
    hr = lambda k: int(round(activity[k])) if activity.get(k) else ""
    return {
        "date": start[:10], "start": start[11:16],
        "name": activity.get("activityName") or "",
        "type": label((activity.get("activityType") or {}).get("typeKey")),
        "distance": distance(dist_m, units), "time": clock(secs),
        "pace": pace(secs, dist_m, units), "avg_hr": hr("averageHR"), "max_hr": hr("maxHR"),
        "elevation": int(round(elev)) if elev is not None else "",
        "laps": interval_notation(laps),
        "training_effect": label(activity.get("trainingEffectLabel")),
        "garmin_note": (activity.get("description") or "").strip(),
        "description": "", "my_notes": "",
        "activity_id": str(activity.get("activityId") or ""),
    }


# -- the CSV ---------------------------------------------------------------------

def read(path, units):
    if not os.path.exists(path):
        return []
    by_header = {h: k for k, h in columns(units)}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [{by_header.get(h, h): v for h, v in r.items()} for r in csv.DictReader(fh)]


def write(path, rows, units):
    cols = columns(units)
    rows = sorted(rows, key=lambda r: (r.get("date", ""), r.get("start", "")), reverse=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([h for _k, h in cols])
        for r in rows:
            w.writerow([r.get(k, "") for k, _h in cols])
    os.replace(tmp, path)


def load_overrides(state_dir):
    p = os.path.join(state_dir, OVERRIDES)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save_override(state_dir, activity_id, notation):
    o = load_overrides(state_dir)
    o[str(activity_id)] = notation
    with open(os.path.join(state_dir, OVERRIDES), "w", encoding="utf-8") as fh:
        json.dump(o, fh, indent=2, ensure_ascii=False)


def upsert(rows, new, overrides=None):
    """Replace Garmin's numbers for runs already in the log, keeping your columns
    and any lap notation you corrected."""
    overrides = overrides or {}
    for n in new:
        if n["activity_id"] in overrides:
            n["laps"] = overrides[n["activity_id"]]
    by_id = {r.get("activity_id"): r for r in rows}
    added = 0
    for n in new:
        old = by_id.get(n["activity_id"])
        if old:
            for k in YOURS:
                n[k] = old.get(k, "")
        else:
            added += 1
        by_id[n["activity_id"]] = n
    return list(by_id.values()), added


# -- laps cache (so `show` and `pending` don't call Garmin again) ------------------

def save_laps(state_dir, activity_id, laps):
    d = os.path.join(state_dir, "laps")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{activity_id}.json"), "w", encoding="utf-8") as fh:
        json.dump(laps, fh)


def load_laps(state_dir, activity_id):
    p = os.path.join(state_dir, "laps", f"{activity_id}.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


# -- weekly summary ----------------------------------------------------------------

def weekly(rows, weeks=8, today=None):
    """Monday-to-Sunday weeks, most recent first."""
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    out = []
    for i in range(weeks):
        start = monday - timedelta(weeks=i)
        end = start + timedelta(days=6)
        runs = [r for r in rows if r.get("date") and start <= datetime.strptime(r["date"], "%Y-%m-%d").date() <= end]
        dist = sum(float(r.get("distance") or 0) for r in runs)
        secs = sum(seconds_of(r.get("time")) for r in runs)
        out.append({
            "week": start.isoformat(), "runs": len(runs), "distance": round(dist, 1),
            "time": clock(secs), "longest": max([float(r.get("distance") or 0) for r in runs] or [0]),
            "workouts": sum(1 for r in runs if r.get("laps")),
        })
    return out
