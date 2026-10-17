# Claude training log

[![tests on Windows, Mac and Linux](https://github.com/hcayssials/claude-training-log/actions/workflows/test.yml/badge.svg)](https://github.com/hcayssials/claude-training-log/actions/workflows/test.yml)

A training log that Claude keeps for you. Your runs come from Garmin Connect into one
spreadsheet, each with a short description Claude writes in your style, and you can ask
Claude about your training in plain English.

```
Date        Distance  Time     Pace  Laps            Description
2026-03-14  18.02 km  1:29:40  4:59  4x2km, r:3'00   Long run with 4 x 2 km at ~4:10/km; the last rep was the fastest.
2026-03-13   8.10 km  44:15    5:28                  Easy, HR steady around 138.
```

> **You:** how was my week?
> **Claude:** 5 runs, 52 km (up from 45), 2 workouts. The longest was Saturday's 18 km
> with 4 x 2 km. Easy-run heart rate held at ~138, so the extra volume isn't costing you.

## Setup (5 minutes, Mac or Windows)

Easiest: put [`Set up with Claude.md`](Set%20up%20with%20Claude.md) in an empty folder,
open that folder in the Claude desktop app's **Code** tab, and say *"Set up my training
log using Set up with Claude.md"*.

Or by hand:

```bash
git clone https://github.com/hcayssials/claude-training-log.git ~/claude-training-log
python3 ~/claude-training-log/install.py        # Windows: py ~/claude-training-log/install.py
cd "<your log folder>"
runlog init --units km                           # or --units mi
runlog login                                     # Garmin email + password, once
runlog sync
```

## Using it

Mostly you'll just talk to Claude: *"update my training log"*, *"how was my week?"*,
*"what were my last three workouts?"*. Underneath:

| | |
|---|---|
| `runlog sync` | add new runs from Garmin (safe any time) |
| `runlog pending` | runs without a description, with their lap tables |
| `runlog describe <id> "text"` | save a description |
| `runlog laps <id> "notation"` | correct the lap notation (kept on later syncs) |
| `runlog show <id or date>` | one run, lap by lap |
| `runlog weeks [--weeks 8]` | weekly runs, distance, time, longest run, workouts |

## What's in the log

One row per run, newest first: date, distance, time, pace, average and max heart rate,
elevation, **laps** (worked out from your lap splits, e.g. `6x800m, r:400m`), Garmin's
training-effect label, the note from your watch, **Description** (Claude's) and
**My notes** (yours). Sync refreshes Garmin's numbers but never touches Description, My
notes or a lap notation you've corrected.

Your folder holds just `Training log.csv` and a hidden `.runlog/` (settings, your style
notes, cached laps). Kilometres or miles, your choice.

## Honest caveats

- **Garmin has no free official API for individuals**, so this uses the community
  `garminconnect` library. It's widely used and read-only, but could break if Garmin
  changes its login.
- Your password is typed into a terminal and never stored. What's saved is a session
  token in `~/.config/runlog/garmin/`, readable only by you, outside your Drive.
- Lap notation reads paces, so it can misread sessions with fast recoveries (floats).
  Claude spots those and asks before correcting them.
- Descriptions are written by Claude in your session, so there's no API key or extra cost.

## Developing

```bash
python -m pytest -q tests     # an end-to-end test against a fake Garmin
```

CI runs it on Windows, Mac and Linux with Python 3.9 and 3.13.
