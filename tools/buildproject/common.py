"""Shared pieces of tools/build-project: output (stdout, and the --log file), running a step with its output passed
through line by line, the one-line error, where the optional tools are installed."""
import os
import subprocess
import sys
from pathlib import Path

FORK = Path(__file__).resolve().parents[2]

_log = None


class BuildError(Exception):
    """A failed step: its message is the one-line error build-project ends with"""


def open_log(path):
    global _log
    _log = open(path, "w", encoding="utf-8", errors="replace")


def say(line):
    print(line, flush=True)
    if _log:
        _log.write(line + "\n")
        _log.flush()


def error(msg):
    """The one-line error, last, on stderr (and in the log)"""
    sys.stdout.flush()
    print(f"error: {msg}", file=sys.stderr, flush=True)
    if _log:
        _log.write(f"error: {msg}\n")
        _log.flush()


def fail(msg):
    raise BuildError(msg)


def data_home():
    x = os.environ.get("XDG_DATA_HOME")
    return Path(x) if x else Path(os.environ.get("HOME", "/")) / ".local/share"


def pod_home():
    """Where cocoapods/install.sh puts Ruby and the gems (its POD_HOME default)"""
    p = os.environ.get("POD_HOME")
    return Path(p) if p else data_home() / "omarchy-apple-dev/cocoapods"


def pod():
    """The `pod` wrapper cocoapods/install.sh wrote, if it is installed"""
    p = pod_home() / "bin/pod"
    return p if p.is_file() else None


def swiftbuild_dir():
    """Where swiftbuild/install.sh puts sweetpad + Swift Build (its OAD_SWIFTBUILD_DIR default)"""
    p = os.environ.get("OAD_SWIFTBUILD_DIR")
    return Path(p) if p else data_home() / "omarchy-apple-dev/swiftbuild"


def setup_hint(tool):
    """How to install an optional tool: $OAD_SETUP_HINT with {} for the tool's id (a front end's own command, e.g.
    "x86sim dev setup {}"), else the fork's install script"""
    h = os.environ.get("OAD_SETUP_HINT")
    if h:
        return h.replace("{}", tool)
    return str(FORK / tool / "install.sh")


def stream(cmd, cwd, env=None, on_line=None):
    """Runs CMD with stdout and stderr passed to say() line by line (on_line(line) -> False drops one). Exit code."""
    try:
        p = subprocess.Popen([str(c) for c in cmd], cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
    except OSError as e:
        fail(f"running {cmd[0]}: {e.strerror}")
    for raw in p.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        if on_line is None or on_line(line) is not False:
            say(line)
    return p.wait()


def step(cmd, cwd, what, env=None, err=None):
    """A "== WHAT" heading, then CMD; a failure ends the build ("WHAT failed (exit N)", or ERR with {rc})"""
    say(f"== {what}")
    rc = stream(cmd, cwd, env)
    if rc != 0:
        fail(err.format(rc=rc) if err else f"{what} failed (exit {rc})")


def env_with(**kv):
    e = dict(os.environ)
    e.update({k: str(v) for k, v in kv.items()})
    return e


def env_with_pod():
    """The environment with the CocoaPods wrapper first on PATH, for CLIs that run `pod install`"""
    p = pod()
    if not p:
        return None
    return env_with(PATH=f"{p.parent}:{os.environ.get('PATH', '')}")
