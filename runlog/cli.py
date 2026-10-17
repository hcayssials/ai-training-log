"""runlog: a Garmin training log that Claude keeps for you.

  runlog init [folder]            set up a log folder (asks km or miles)
  runlog login                    sign in to Garmin once (in a terminal: it asks your password)
  runlog sync                     add new runs from Garmin; safe to run any time
  runlog pending                  runs that don't have a description yet, with their laps
  runlog describe <id> "text"     save a description for a run
  runlog laps <id> "notation"     correct a run's lap notation (kept on later syncs)
  runlog show <id|date>           one run in detail, lap by lap
  runlog weeks [--weeks 8]        weekly totals: runs, distance, time, longest, workouts
"""

import argparse
import os
import sys
from datetime import date, timedelta

from . import garmin, logbook
from .workspace import LogFolder


def get_lf(args):
    return LogFolder.find(args.root)


def _connect_or_explain():
    try:
        return garmin.connect()
    except garmin.NeedLogin as e:
        sys.exit(f"Can't read Garmin: {e}. Run `runlog login` in a terminal "
                 f"(it asks for your Garmin password, so it has to be you typing).")


# -----------------------------------------------------------------------------

def cmd_init(args):
    lf = LogFolder.create(args.folder or os.getcwd())
    if args.units:
        lf.config["units"] = args.units
    if args.all_activities:
        lf.config["activity_type"] = None
    if args.days:
        lf.config["first_sync_days"] = args.days
    lf.save_config()
    c = lf.config
    print(f"Training-log folder: {lf.root}")
    print(f"  units: {c['units']}   activities: {c['activity_type'] or 'all'}   "
          f"first sync goes back {c['first_sync_days']} days")
    print("Next: `runlog login` (once), then `runlog sync`.")


def cmd_login(args):
    garmin.login_interactive()


def cmd_sync(args):
    lf = get_lf(args)
    units = lf.config["units"]
    rows = logbook.read(lf.log_file, units)
    known = {r.get("activity_id") for r in rows}
    if args.days:
        since = date.today() - timedelta(days=args.days)
    elif rows:
        # Re-read the last two weeks too: Garmin sometimes adds a note or fixes a
        # distance after the fact.
        since = min(date.fromisoformat(max(r["date"] for r in rows if r.get("date"))),
                    date.today()) - timedelta(days=14)
    else:
        since = date.today() - timedelta(days=lf.config["first_sync_days"])

    g = _connect_or_explain()
    acts = garmin.activities_since(g, since.isoformat(), lf.config["activity_type"])
    new_rows = []
    for a in acts:
        aid = str(a.get("activityId"))
        cached = logbook.load_laps(lf.state, aid)
        laps = cached if (cached and aid in known) else garmin.laps(g, aid)
        if laps:
            logbook.save_laps(lf.state, aid, laps)
        new_rows.append(logbook.row_from(a, laps, units))
    rows, added = logbook.upsert(rows, new_rows, logbook.load_overrides(lf.state))
    logbook.write(lf.log_file, rows, units)
    todo = sum(1 for r in rows if not r.get("description"))
    print(f"{added} new run(s) added, {len(new_rows) - added} refreshed. "
          f"{len(rows)} runs in {os.path.basename(lf.log_file)}.")
    if todo:
        print(f"{todo} run(s) without a description: `runlog pending` lists them.")


def _laps_table(lf, r, units):
    laps = logbook.load_laps(lf.state, r.get("activity_id"))
    if len(laps) < 2:
        return []
    d = "mi" if units == "mi" else "km"
    out = [f"    lap  {'dist':>7}  {'time':>7}  {'pace':>6}  hr"]
    for i, lap in enumerate(laps, 1):
        out.append(f"    {i:>3}  {logbook.distance(lap['distance'], units):>5.2f}{d}  "
                   f"{logbook.clock(lap['moving_time']):>7}  "
                   f"{logbook.pace(lap['moving_time'], lap['distance'], units):>6}  "
                   f"{int(lap['avg_hr']) if lap.get('avg_hr') else ''}")
    return out


def _run_block(lf, r, units):
    d = "mi" if units == "mi" else "km"
    lines = [f"{r['date']} {r.get('start', '')} · {r.get('name', '')} · {r['distance']} {d} in "
             f"{r['time']} ({r['pace']}/{d}) · HR {r.get('avg_hr') or '?'}/{r.get('max_hr') or '?'}"
             f" · elev {r.get('elevation') or 0} · id {r['activity_id']}"]
    for k, lab in (("laps", "laps"), ("training_effect", "Garmin training effect"),
                   ("garmin_note", "note on the watch"), ("my_notes", "my notes"),
                   ("description", "description")):
        if r.get(k):
            lines.append(f"  {lab}: {r[k]}")
    return lines + _laps_table(lf, r, units)


def cmd_pending(args):
    lf = get_lf(args)
    units = lf.config["units"]
    rows = [r for r in logbook.read(lf.log_file, units) if not r.get("description")]
    if not rows:
        print("Every run has a description.")
        return
    if os.path.exists(lf.style_file):
        with open(lf.style_file, encoding="utf-8") as fh:
            print("STYLE (from .runlog/style.md):\n" + fh.read().strip() + "\n")
    print(f"{len(rows)} run(s) without a description"
          + (f", newest {args.limit} shown" if len(rows) > args.limit else "") + ":\n")
    for r in rows[:args.limit]:
        print("\n".join(_run_block(lf, r, units)) + "\n")


def cmd_describe(args):
    lf = get_lf(args)
    units = lf.config["units"]
    rows = logbook.read(lf.log_file, units)
    hit = [r for r in rows if r.get("activity_id") == args.activity_id]
    if not hit:
        sys.exit(f"No run with id {args.activity_id} in the log.")
    hit[0]["description"] = " ".join(args.text.split())
    logbook.write(lf.log_file, rows, units)
    print(f"Saved the description for {hit[0]['date']} ({hit[0]['name']}).")


def cmd_laps(args):
    """Correct the lap notation for a run. Kept on every later sync."""
    lf = get_lf(args)
    units = lf.config["units"]
    rows = logbook.read(lf.log_file, units)
    hit = [r for r in rows if r.get("activity_id") == args.activity_id]
    if not hit:
        sys.exit(f"No run with id {args.activity_id} in the log.")
    before = hit[0].get("laps") or "(none)"
    hit[0]["laps"] = args.notation.strip()
    logbook.save_override(lf.state, args.activity_id, hit[0]["laps"])
    logbook.write(lf.log_file, rows, units)
    print(f"Laps for {hit[0]['date']}: {before}  →  {hit[0]['laps']}")


def cmd_show(args):
    lf = get_lf(args)
    units = lf.config["units"]
    rows = [r for r in logbook.read(lf.log_file, units)
            if args.which in (r.get("activity_id"), r.get("date"))]
    if not rows:
        sys.exit(f"No run matching '{args.which}' (use an activity id or a date like 2026-10-17).")
    for r in rows:
        print("\n".join(_run_block(lf, r, units)) + "\n")


def cmd_weeks(args):
    lf = get_lf(args)
    units = lf.config["units"]
    d = "mi" if units == "mi" else "km"
    print(f"{'week of':<11} {'runs':>4} {d:>7} {'time':>8} {'longest':>8} {'workouts':>8}")
    for w in logbook.weekly(logbook.read(lf.log_file, units), args.weeks):
        print(f"{w['week']:<11} {w['runs']:>4} {w['distance']:>7.1f} {w['time']:>8} "
              f"{w['longest']:>8.1f} {w['workouts']:>8}")
    print("\n'workouts' = runs whose laps form a rep pattern (e.g. 6x800m).")


# -----------------------------------------------------------------------------

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to an old code page
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="runlog", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="the log folder (default: found from where you are)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="set up a log folder")
    p.add_argument("folder", nargs="?")
    p.add_argument("--units", choices=["km", "mi"])
    p.add_argument("--days", type=int, help="how far back the first sync goes (default 90)")
    p.add_argument("--all-activities", action="store_true", help="not just runs")
    p.set_defaults(fn=cmd_init)

    sub.add_parser("login", help="sign in to Garmin (asks your password)").set_defaults(fn=cmd_login)

    p = sub.add_parser("sync", help="add new runs from Garmin")
    p.add_argument("--days", type=int, help="re-read this many days back")
    p.set_defaults(fn=cmd_sync)

    p = sub.add_parser("pending", help="runs without a description")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(fn=cmd_pending)

    p = sub.add_parser("describe", help="save a run's description")
    p.add_argument("activity_id")
    p.add_argument("text")
    p.set_defaults(fn=cmd_describe)

    p = sub.add_parser("laps", help="correct a run's lap notation (kept on later syncs)")
    p.add_argument("activity_id")
    p.add_argument("notation", help='e.g. "4xmile, r:1.85km float"')
    p.set_defaults(fn=cmd_laps)

    p = sub.add_parser("show", help="one run, lap by lap")
    p.add_argument("which", help="activity id or date (YYYY-MM-DD)")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("weeks", help="weekly totals")
    p.add_argument("--weeks", type=int, default=8)
    p.set_defaults(fn=cmd_weeks)

    args = ap.parse_args(argv)
    args.fn(args)
