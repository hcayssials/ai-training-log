"""End-to-end test of `runlog` against a fake Garmin: no network, no account.

Runs what a new user does (init, sync, pending, describe, correct laps, re-sync,
weeks, show, miles) plus the sign-in retry, on every OS in CI.

    python -m pytest -q tests
"""

import contextlib
import csv
import io
import os
import shutil
import sys
import tempfile
import types
import unittest
from datetime import date, timedelta

HOME = tempfile.mkdtemp(prefix="rl-home-")
os.environ["HOME"] = os.environ["USERPROFILE"] = HOME
os.environ.pop("RUNLOG_GARMIN_TOKENS", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runlog import cli, garmin  # noqa: E402

TODAY = date.today()


def day(n, hhmm="07:00"):
    return f"{(TODAY - timedelta(days=n)).isoformat()} {hhmm}:00"


def lap(dist, secs, hr=150):
    return {"distance": dist, "duration": secs, "movingDuration": secs, "elapsedDuration": secs,
            "elevationGain": 2, "averageHR": float(hr)}


# 6x800m at ~3:30/km with 400m jog recoveries, plus warm-up and cool-down.
INTERVAL_LAPS = [lap(2000, 600, 130)] + sum(([lap(800, 168, 170), lap(400, 150, 140)] for _ in range(6)), []) \
    + [lap(1500, 450, 135)]
ACTS = [
    {"activityId": 111, "activityName": "Track 6x800", "startTimeLocal": day(1),
     "activityType": {"typeKey": "running"}, "distance": 9800.0, "duration": 2900.0,
     "averageHR": 152.4, "maxHR": 181.0, "elevationGain": 20.0,
     "trainingEffectLabel": "VO2MAX", "description": "felt strong"},
    {"activityId": 222, "activityName": "Café run ✓", "startTimeLocal": day(2, "18:30"),
     "activityType": {"typeKey": "running"}, "distance": 10000.0, "duration": 3000.0,
     "averageHR": 135.0, "maxHR": 150.0, "elevationGain": 55.0,
     "trainingEffectLabel": "AEROBIC_BASE", "description": None},
    {"activityId": 333, "activityName": "Treadmill", "startTimeLocal": day(9),
     "activityType": {"typeKey": "treadmill_running"}, "distance": 5000.0, "duration": 1500.0,
     "averageHR": None, "maxHR": None, "elevationGain": None, "trainingEffectLabel": None},
]
SPLITS = {"111": INTERVAL_LAPS, "222": [lap(5000, 1500, 133), lap(5000, 1500, 137)], "333": []}


class FakeGarmin:
    def get_activities_by_date(self, start, end=None, activity_type=None):
        return [dict(a) for a in ACTS if a["startTimeLocal"][:10] >= start]

    def get_activity_splits(self, aid):
        return {"lapDTOs": SPLITS[str(aid)]}


garmin.connect = lambda: FakeGarmin()
garmin.time.sleep = lambda s: None


def run(*argv, stdin=None):
    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            cli.main(list(argv))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            if e.code and not isinstance(e.code, int):
                print(e.code)
    return code, out.getvalue()


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(tempfile.mkdtemp(prefix="rl-"), "My Drive", "Running")

    def tearDown(self):
        shutil.rmtree(os.path.dirname(os.path.dirname(self.root)), ignore_errors=True)

    def rows(self):
        with open(os.path.join(self.root, "Training log.csv"), encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    def test_full_flow_km(self):
        code, out = run("init", self.root, "--units", "km")
        self.assertEqual(code, 0, out)
        code, out = run("--root", self.root, "sync")
        self.assertEqual(code, 0, out)
        self.assertIn("3 new run(s)", out)
        self.assertEqual(sorted(os.listdir(self.root)), [".runlog", "Training log.csv"])

        rows = self.rows()
        self.assertEqual([r["Activity ID"] for r in rows], ["111", "222", "333"])  # newest first
        track = rows[0]
        self.assertEqual(track["Laps"], "6x800m, r:400m")
        self.assertEqual(track["Distance (km)"], "9.8")
        self.assertEqual(track["Pace (/km)"], "4:56")
        self.assertEqual(track["Avg HR"], "152")
        self.assertEqual(track["Training effect"], "Vo2Max")
        self.assertEqual(track["Garmin note"], "felt strong")
        self.assertEqual(rows[1]["Name"], "Café run ✓")
        self.assertEqual(rows[2]["Laps"], "")

        code, out = run("--root", self.root, "pending")
        self.assertIn("3 run(s) without a description", out)
        self.assertIn("6x800m", out)
        self.assertIn("lap", out)

        run("--root", self.root, "describe", "111", "6x800m at 3:30/km, last one the fastest.")
        run("--root", self.root, "laps", "222", "2x5km steady")
        code, out = run("--root", self.root, "sync")  # Garmin's numbers refresh...
        self.assertIn("0 new run(s)", out)
        rows = self.rows()  # ...but the description and corrected laps survive
        self.assertEqual(rows[0]["Description"], "6x800m at 3:30/km, last one the fastest.")
        self.assertEqual(rows[1]["Laps"], "2x5km steady")

        code, out = run("--root", self.root, "weeks", "--weeks", "3")
        self.assertEqual(code, 0, out)
        self.assertIn("week of", out)
        total = sum(float(line.split()[2]) for line in out.splitlines()[1:4])
        self.assertAlmostEqual(total, 24.8, places=1)

        code, out = run("--root", self.root, "show", (TODAY - timedelta(days=1)).isoformat())
        self.assertIn("Track 6x800", out)
        self.assertIn("3:30", out)  # lap pace in the table

        code, out = run("--root", self.root, "describe", "999", "x")
        self.assertNotEqual(code, 0)

    def test_miles(self):
        run("init", self.root, "--units", "mi")
        run("--root", self.root, "sync")
        r = self.rows()[1]
        self.assertEqual(r["Distance (mi)"], "6.21")
        self.assertEqual(r["Pace (/mi)"], "8:03")
        self.assertEqual(r["Elevation (ft)"], "180")

    def test_not_signed_in_explains_what_to_do(self):
        run("init", self.root)
        saved = garmin.connect

        def nope():
            raise garmin.NeedLogin("not signed in to Garmin yet")
        garmin.connect = nope
        try:
            code, out = run("--root", self.root, "sync")
        finally:
            garmin.connect = saved
        self.assertNotEqual(code, 0)
        self.assertIn("runlog login", out)

    def test_login_asks_again_after_a_wrong_password(self):
        class AuthError(Exception):
            pass

        class Garmin:
            def __init__(self, email=None, password=None, prompt_mfa=None):
                self.password = password

            def login(self, store):
                if self.password != "right":
                    raise AuthError()
                os.makedirs(store, exist_ok=True)
                open(os.path.join(store, "garmin_tokens.json"), "w").close()

        fake = types.SimpleNamespace(Garmin=Garmin, GarminConnectAuthenticationError=AuthError,
                                     GarminConnectTooManyRequestsError=RuntimeError)
        saved = garmin._lib
        garmin._lib = lambda: fake
        answers = iter(["wrong", "right"])
        garmin.getpass.getpass = lambda prompt="": next(answers)
        garmin.input = lambda prompt="": "me@example.com"
        try:
            code, out = run("login")
        finally:
            garmin._lib = saved
        self.assertEqual(code, 0, out)
        self.assertIn("didn't accept", out)
        self.assertIn("Signed in", out)


if __name__ == "__main__":
    unittest.main()
