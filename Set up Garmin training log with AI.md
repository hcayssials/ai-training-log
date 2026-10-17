# Set up Garmin training log with AI

**For you:** put this file in an empty folder where you want your training log (for
example `My Drive/Running`). Open that folder in an **AI coding assistant**, one that can
run commands on your computer, and say:

> Set up my training log using "Set up Garmin training log with AI.md".

Any of these work, on Mac or Windows: the Claude desktop app's **Code** tab (or Claude
Code), ChatGPT's **Codex**, **Cursor**, **GitHub Copilot** in agent mode, or **Gemini CLI**.
A plain chat window (chatgpt.com, claude.ai) can't: it has no access to your computer.

It takes about 5 minutes. You'll need your Garmin Connect email and password.

---

## Instructions for the AI assistant

You are setting up the `runlog` tool so this folder holds the user's **training log**:
one CSV with a row per run from Garmin Connect, which you'll then keep up to date and
describe. Talk in plain language; assume they've never used a terminal. Summarise
command output rather than pasting it.

**This folder** (the one with this file) is the log folder. The tool's code goes in
`~/ai-training-log`, never here.

### Rules

1. **Never handle the Garmin password.** The user types it into a terminal (Step 3).
   If they paste it in the chat anyway, don't repeat or use it, and suggest they change
   it on connect.garmin.com.
2. **Read-only.** The tool never changes anything on their Garmin account. Don't try to.
3. Ask before editing any file outside this folder and `~/ai-training-log`.

### Step 1: Check the computer

It needs **Python 3.12 or newer** (the Garmin library requires it) and git. Macs ship
with an older Python (3.9), so many people need to install a newer one. That's normal.

**Mac:** `git --version` (if missing, run `xcode-select --install`; they click
**Install**, then wait). Then look for a new enough Python:

```bash
for p in python3.13 python3.12 python3; do $p -c 'import sys; assert sys.version_info >= (3,12)' 2>/dev/null && { echo $p; break; }; done
```

If that prints nothing, ask them to install Python from
https://www.python.org/downloads/ (the big yellow button, then open the downloaded
installer and click through). Wait for them, then run the check again.

**Windows** (commands run in Git Bash, so git is there):

```bash
py -3.13 --version || py -3.12 --version
```

If neither works (or `python` opens the Microsoft Store), they need Python 3.12+: let
you run `winget install -e --id Python.Python.3.12`, or download it from python.org and
tick **"Add python.exe to PATH"**. Then check again.

Below, `PY` is the command that worked: `python3.13`, `python3.12` or `python3` on a
Mac; `py -3.13` or `py -3.12` on Windows.

### Step 2: Get the tool

```bash
git -C ~/ai-training-log pull --ff-only 2>/dev/null || git clone https://github.com/hcayssials/ai-training-log.git ~/ai-training-log
```

Tell them first: *"I'm about to run the installer. Your AI app may ask you to approve
it, because it runs code that was just downloaded."* Then:

```bash
PY ~/ai-training-log/install.py
```

It ends by printing **the exact command for this computer** (also saved in
`~/.config/runlog/command.txt`). From here on, `runlog` means that command.

### Step 3: Set up the folder, then sign in to Garmin (they type, you don't see it)

Ask: **kilometres or miles?** and **how far back to start** (default 90 days). Then:

```bash
runlog init --units km --days 90
```

Open a terminal tab for them in this folder, running the login. Use the app's
run-in-terminal tool if you have one; otherwise they open Terminal (Mac) or PowerShell
(Windows) and paste it:

- Mac / Linux, or Git Bash on Windows: `~/.local/bin/runlog login`
- Windows PowerShell: `& "$env:USERPROFILE\.local\bin\runlog.cmd" login`

Tell them: *"Enter your Garmin email, then your password. Nothing appears as you type
it, that's normal. If Garmin sends you a code, enter that too."* A wrong password just
asks again. Wait until they say it's signed in.

### Step 4: First sync

```bash
runlog sync
runlog weeks --weeks 4
```

Tell them how many runs landed and show the last 4 weeks in a small table.

### Step 5: Their first descriptions

```bash
runlog pending --limit 3
```

Write descriptions for the 3 newest runs, following the usage instructions the installer
wrote (`~/.config/runlog/AGENTS.md`; read them now if you haven't): one or two sentences, only what the numbers and laps show. Show them, ask what
to change (length, tone, units, emoji or none), and save their preferences to
`.runlog/style.md`. Then save the three with `runlog describe <id> "…"`. Offer to do
the rest of the backlog the same way.

If a **Laps** value looks wrong next to its lap table (fast float recoveries confuse
it), propose the right notation and, if they agree, `runlog laps <id> "…"`.

### Step 6: Tell them what they have

- `Training log.csv` in this folder (opens in Excel, Numbers or Google Sheets). The
  "My notes" column is theirs: the tool never overwrites it.
- From now on, in their AI assistant, they can say: **"update my training log"**,
  **"how was my week?"**, **"what were my last three workouts?"**,
  **"how's my mileage trending?"**

So their assistant knows how next time:
- **Claude Code / Claude app:** nothing to do. The installer added a skill it finds by itself.
- **Any other assistant:** ask, then copy `~/.config/runlog/AGENTS.md` into this folder as
  `AGENTS.md` (Codex, Cursor and Copilot read that file; for Gemini CLI name it
  `GEMINI.md`). It's the only extra file the folder gets.

### If something goes wrong

| Symptom | Fix |
|---|---|
| `command not found: runlog` | Use the command in `~/.config/runlog/command.txt` |
| `Can't read Garmin … runlog login` | Their session expired: Step 3's login again |
| `too many sign-in attempts` | Garmin's limit: wait 15 minutes |
| A run is missing | It isn't a run on Garmin (e.g. logged as "cardio"): `runlog init --all-activities`, then `runlog sync --days 30` |
