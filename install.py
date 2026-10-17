"""One-time setup, on Mac, Windows or Linux. Safe to re-run (e.g. after an update).

    Mac / Linux:   python3 install.py
    Windows:       py install.py                 (or: python install.py)

It installs one Python package (garminconnect), a `runlog` command and the Claude
skill, then prints the exact command to run the tool with on this computer.
"""

import os
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
WINDOWS = sys.platform == "win32"
BIN = os.path.join(HOME, ".local", "bin")
USER_DIR = os.path.join(HOME, ".config", "runlog")


def posix(p):
    """Forward slashes work everywhere: Python, Git Bash (which Claude Code uses on
    Windows), PowerShell and cmd."""
    return p.replace("\\", "/")


def pip_install(req):
    base = [sys.executable, "-m", "pip", "install", "--quiet", "-r", req]
    # --user first; Homebrew and some Linux Pythons refuse that unless told it's fine.
    for extra in (["--user"], ["--user", "--break-system-packages"], []):
        if subprocess.run(base + extra, capture_output=True).returncode == 0:
            return
    sys.exit(f"Couldn't install the Python packages in {os.path.basename(req)}. "
             f"Try:  {sys.executable} -m pip install -r \"{req}\"")


def main():
    if sys.version_info < (3, 9):
        sys.exit(f"Python 3.9 or newer is needed; this is {sys.version.split()[0]}.")

    print("1/3  Python package: garminconnect")
    try:
        import garminconnect  # noqa: F401
    except ImportError:
        pip_install(os.path.join(REPO, "requirements.txt"))

    print("2/3  The `runlog` command")
    launcher = os.path.join(REPO, "bin", "runlog")
    cmd = f'"{posix(sys.executable)}" "{posix(launcher)}"'
    os.makedirs(BIN, exist_ok=True)
    if WINDOWS:
        # For PowerShell/cmd, and for Git Bash. Both pin this exact Python.
        with open(os.path.join(BIN, "runlog.cmd"), "w", encoding="utf-8") as fh:
            fh.write(f'@"{sys.executable}" "{launcher}" %*\r\n')
        with open(os.path.join(BIN, "runlog"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f'#!/bin/sh\nexec {cmd} "$@"\n')
    else:
        link = os.path.join(BIN, "runlog")
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(launcher, link)
    on_path = os.path.normcase(BIN) in [os.path.normcase(p) for p in os.environ.get("PATH", "").split(os.pathsep)]
    print("     ok: `runlog` works from anywhere" if on_path else
          f"     Not on your PATH, so use the full command below (or add {posix(BIN)} to PATH).")

    print("3/3  Claude Code skill -> ~/.claude/skills/training-log")
    dest = os.path.join(HOME, ".claude", "skills", "training-log")
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(REPO, "skills", "training-log", "SKILL.md"), encoding="utf-8") as fh:
        text = fh.read().replace("{{REPO}}", posix(REPO)).replace("{{CMD}}", cmd)
    with open(os.path.join(dest, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(text)

    os.makedirs(USER_DIR, exist_ok=True)
    with open(os.path.join(USER_DIR, "command.txt"), "w", encoding="utf-8") as fh:
        fh.write(cmd + "\n")
    print("\nDone. The command for this computer (also saved in ~/.config/runlog/command.txt):")
    print(f"  {'runlog' if on_path else cmd}")
    print("Next, in the folder you want your log in:  runlog init")


if __name__ == "__main__":
    main()
