"""Garmin Connect: sign in once, then read activities and their laps.

Uses the unofficial `garminconnect` library (Garmin has no free official API for
individuals). Read-only: nothing here changes anything on your Garmin account.

The first `runlog login` asks for your Garmin email, password and, if your account
uses it, a two-factor code. The session it gets is saved in ~/.config/runlog/garmin/
and reused, so you aren't asked again until Garmin expires it (months, typically).
"""

import getpass
import os
import sys
import time

from .workspace import GARMIN_TOKENS


def _lib():
    try:
        import garminconnect
    except ImportError:
        sys.exit("The `garminconnect` package isn't installed. Run the installer again:\n"
                 "  python3 install.py   (Windows: py install.py)")
    return garminconnect


class NeedLogin(Exception):
    pass


def connect():
    """Resume the saved session. Raises NeedLogin if there isn't a usable one."""
    gc = _lib()
    if not os.path.isdir(GARMIN_TOKENS) or not os.listdir(GARMIN_TOKENS):
        raise NeedLogin("not signed in to Garmin yet")
    try:
        g = gc.Garmin()
        g.login(GARMIN_TOKENS)
        return g
    except (gc.GarminConnectAuthenticationError, FileNotFoundError, ValueError) as e:
        raise NeedLogin(f"the saved Garmin session has expired ({e.__class__.__name__})")


def login_interactive(tries=3):
    """Ask for email, password (hidden) and a 2FA code if needed; save the session.

    A wrong password, or a paste that picked up an invisible character, just asks
    again instead of quitting."""
    gc = _lib()
    os.makedirs(GARMIN_TOKENS, exist_ok=True)
    print("Sign in to Garmin Connect. Your password isn't shown as you type or paste it.")
    email = input("Garmin email: ").strip()
    for attempt in range(tries):
        password = getpass.getpass("Garmin password: ").strip()
        try:
            g = gc.Garmin(email, password, prompt_mfa=lambda: input(
                "Garmin sent you a code (email or app). Enter it: ").strip())
            g.login(GARMIN_TOKENS)
            print("Signed in. The session is saved, so you won't be asked again for a while.")
            return g
        except gc.GarminConnectAuthenticationError:
            left = tries - attempt - 1
            print("  Garmin didn't accept that email/password." + (" Try again:" if left else ""))
        except gc.GarminConnectTooManyRequestsError:
            sys.exit("Garmin says too many sign-in attempts. Wait 15 minutes and try again.")
    sys.exit("Not signed in. Check your email and password on connect.garmin.com, then "
             "run `runlog login` again.")


def activities_since(g, start_date, activity_type):
    """Summaries of every activity from start_date (YYYY-MM-DD) to today, newest first."""
    return g.get_activities_by_date(start_date, None, activity_type)


def laps(g, activity_id, pause=0.3):
    """Laps in the shape detection.analyze_laps() expects, plus HR and speed for display."""
    time.sleep(pause)  # be polite: one call per run
    try:
        dtos = (g.get_activity_splits(activity_id) or {}).get("lapDTOs") or []
    except Exception:
        return []
    out = []
    for lap in dtos:
        dur = lap.get("duration") or 0
        out.append({
            "distance": lap.get("distance") or 0,
            "moving_time": lap.get("movingDuration") or dur,
            "elapsed_time": lap.get("elapsedDuration") or dur,
            "total_elevation_gain": lap.get("elevationGain") or 0,
            "avg_hr": int(round(lap["averageHR"])) if lap.get("averageHR") else None,
        })
    return out
