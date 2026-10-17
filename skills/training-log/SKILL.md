---
name: training-log
description: Keep the user's Garmin training log with the `runlog` tool — sync new runs, write a short description for each, correct lap notation, and answer questions about their training (weekly volume, recent workouts, trends). Use whenever the user asks to update or sync their training log, log or describe a run, "how was my week/month", what their recent workouts were, mileage, pace or heart-rate trends, or to set up the training log. Do NOT use for medical advice or for writing a training plan from scratch.
---

# Training log

The tool is `runlog`. If that command isn't found, run it as `{{CMD}}` (this
computer's exact command, also in `~/.config/runlog/command.txt`). It works on a **log
folder**, recognised by the hidden `.runlog/` inside it; pass `--root "<folder>"` when
running from elsewhere.

## Hard rules

1. **Never handle the Garmin password.** If a command says it can't read Garmin, the user
   runs `runlog login` themselves in a terminal (email, hidden password, maybe a code
   Garmin sends them). Open a terminal tab for them if you can; never ask for the
   password in chat.
2. **Never edit `Training log.csv` directly.** Use `runlog describe` and `runlog laps`, so
   later syncs keep the changes. Never touch the "My notes" column.
3. **Don't invent facts.** A description says only what the numbers, the laps and the
   user's own notes show. No guessing about weather, how they felt or why a run went
   slow. Ask instead.
4. **Not a doctor.** If heart-rate or pace patterns look worrying, say what the numbers
   show and suggest they ask a professional. Don't diagnose.

## Updating the log

```
runlog sync         # pull new runs
runlog pending      # runs with no description, each with its lap table
```

For each pending run, write a description and save it:

```
runlog describe <activity_id> "Easy 10.8 km, HR steady around 131 throughout."
```

How to write them:
- **One or two sentences.** What the run was (easy, long, tempo, intervals, race), the
  numbers that matter for that kind of run, and anything notable in the laps (negative
  split, faded on the last rep, very even).
- **Use the lap table, not just the summary.** "4x1 mile at about 3:35/km with 1.85 km
  floats" says more than an average pace across reps and recoveries.
- **Their style first.** `pending` prints `.runlog/style.md` if it exists. The first time,
  write 2–3 descriptions, show them, ask what to change (length, units, tone, emoji or
  none), and save their answer to `.runlog/style.md` so it sticks.
- **Show before saving** when you're doing several at once: list them, get an OK, then save.

### Lap notation

The **Laps** column is worked out automatically (e.g. `6x800m, r:2'00`). It reads paces,
so it can go wrong when recoveries are fast (floats) or reps vary. If the lap table
plainly says something different, propose the right notation, ask, then save it:

```
runlog laps <activity_id> "4xmile + 1x500m, r:1.85km float"
```

It stays corrected on every later sync. Never change it without asking.

## Answering questions

```
runlog weeks --weeks 8        # weekly runs, distance, time, longest run, workouts
runlog show 2026-10-17        # one run (by date or id), lap by lap
```

- Use `weeks` for totals rather than adding up rows yourself.
- For anything else ("my last three workouts", "pace trend on easy runs"), read
  `Training log.csv` in the log folder. Newest runs are at the top.
- Give the numbers, then one line on what they mean. Say which weeks or runs you used.

## Setting it up

If there's no `.runlog/` yet, follow `{{REPO}}/Set up with Claude.md`.
