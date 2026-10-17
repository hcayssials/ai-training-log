"""Where things live.

A *log folder* is any folder you choose (e.g. in Google Drive). It holds exactly
two things: your training log, and one hidden folder for settings.

    Running/
      Training log.csv     one row per run, newest first; opens in Excel/Numbers/Sheets
      .runlog/             config.json (units, which activities), style.md

Your Garmin login never goes in the log folder (it's usually inside a synced
Drive). It lives in ~/.config/runlog/garmin/.
"""

import json
import os
import sys

STATE_DIRNAME = ".runlog"
USER_DIR = os.path.join(os.path.expanduser("~"), ".config", "runlog")
# RUNLOG_GARMIN_TOKENS points at an existing session folder instead (use it in
# place: Garmin swaps the session on every use, so a copy would go stale).
GARMIN_TOKENS = os.path.expanduser(os.environ.get("RUNLOG_GARMIN_TOKENS")
                                   or os.path.join(USER_DIR, "garmin"))
LOG_NAME = "Training log.csv"

DEFAULT_CONFIG = {
    "units": "km",           # "km" or "mi"
    "activity_type": "running",  # Garmin's filter; None = every activity
    "first_sync_days": 90,
}


class LogFolder:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.state = os.path.join(self.root, STATE_DIRNAME)
        self.config_file = os.path.join(self.state, "config.json")
        self.style_file = os.path.join(self.state, "style.md")
        self.log_file = os.path.join(self.root, LOG_NAME)
        self._config = None

    @classmethod
    def find(cls, start=None):
        """Walk up from `start` (default: cwd) to the folder holding .runlog/."""
        here = os.path.abspath(start or os.getcwd())
        while True:
            if os.path.isdir(os.path.join(here, STATE_DIRNAME)):
                return cls(here)
            parent = os.path.dirname(here)
            if parent == here:
                sys.exit("Not inside a training-log folder. Run `runlog init` in the folder "
                         "you want the log in, or pass --root <folder>.")
            here = parent

    @classmethod
    def create(cls, root):
        lf = cls(root)
        os.makedirs(lf.state, exist_ok=True)
        if not os.path.exists(lf.config_file):
            save_json(lf.config_file, DEFAULT_CONFIG)
        return lf

    @property
    def config(self):
        if self._config is None:
            self._config = {**DEFAULT_CONFIG, **load_json(self.config_file, {})}
        return self._config

    def save_config(self):
        save_json(self.config_file, self.config)


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True, ensure_ascii=False)
    os.replace(tmp, path)
