# Working on this repo

For agents changing the code. Agents *using* the tool follow
`skills/training-log/SKILL.md`.

- Layout: `bin/runlog` → `runlog/cli.py` (commands) → `garmin.py` (sign-in, activities,
  laps; read-only), `logbook.py` (the CSV, formatting, weekly totals), `detection.py`
  (lap notation: pure stdlib, deterministic, no LLM on purpose), `workspace.py` (paths).
- One dependency: `garminconnect`. Keep it that way.
- Never store or print the Garmin password. The session token lives in
  `~/.config/runlog/garmin/`, never in the log folder (usually a synced Drive).
- Sync must never overwrite `Description`, `My notes`, or a corrected lap notation
  (`.runlog/laps_overrides.json`).
- Windows: text files as UTF-8 (the CSV as `utf-8-sig` so Excel reads it), no
  `%-d`-style strftime. Python 3.12+ (garminconnect requires it).
- `python -m pytest -q tests` must pass; CI runs it on Windows, Mac and Linux.
