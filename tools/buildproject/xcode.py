"""Xcode projects (.xcodeproj / .xcworkspace): built with Swift Build through linux-bin/xcodebuild
(swiftbuild/install.sh), products in DIR/build/x86sim (the derived data dir)."""
import json
import os
import subprocess
from pathlib import Path

from . import detect
from .common import FORK, fail, say, setup_hint, stream, swiftbuild_dir

XCODEBUILD = FORK / "linux-bin/xcodebuild"

OS_NAME = {"tvos": "tvOS", "watchos": "watchOS", "xros": "visionOS"}


def container(d):
    """The workspace or project in D, as xcodebuild picks it: the .xcworkspace (a CocoaPods workspace sits next to its
    project: the workspace wins), else the .xcodeproj. (flag, path) or None"""
    entries = detect._entries(d)
    ws = [p for p in entries if p.suffix == ".xcworkspace"]
    pj = [p for p in entries if p.suffix == ".xcodeproj"]
    if ws:
        return "-workspace", ws[0]
    if pj:
        return "-project", pj[0]
    return None


def scheme(d):
    """The scheme to build: $XCODE_SCHEME, else the one named like the project / workspace, else the first"""
    if os.environ.get("XCODE_SCHEME"):
        return os.environ["XCODE_SCHEME"]
    c = container(d)
    if not c:
        fail("no .xcodeproj or .xcworkspace")
    flag, path = c
    out = subprocess.run(["python3", str(XCODEBUILD), flag, str(path), "-list", "-json"], cwd=d, stdin=subprocess.DEVNULL,
                         capture_output=True)
    try:
        v = json.loads(out.stdout)
    except ValueError:
        fail(f"xcodebuild -list: {out.stderr.decode(errors='replace').strip()}")
    schemes = [s for k in ("project", "workspace") for s in ((v.get(k) or {}).get("schemes") or []) if isinstance(s, str)]
    if not schemes:
        fail("the project has no scheme")
    return path.stem if path.stem in schemes else schemes[0]


def _xcodebuild(cmd, d):
    products = []

    def line(l):
        if l.startswith("product: "):
            products.append(Path(l[len("product: "):].strip()))

    rc = stream(cmd, d, None, line)
    if rc != 0:
        fail(f"the build failed (exit {rc})")
    return products[-1] if products and products[-1].suffix == ".app" else None


def build(d, platform, release):
    """A simulator build of the project's app for PLATFORM (ios, tvos, watchos, xros): the .app"""
    d = Path(d)
    c = container(d)
    if not c:
        fail("no .xcodeproj or .xcworkspace")
    if not (swiftbuild_dir() / "current/sweetpad").exists():
        fail(f"Swift Build is not installed: {setup_hint('swiftbuild')}")
    s = scheme(d)
    dest = f"generic/platform={OS_NAME.get(platform, 'iOS')} Simulator"
    cfg = "Release" if release else "Debug"
    say(f"== build {s} ({dest}, {cfg})")
    app = _xcodebuild(["python3", XCODEBUILD, c[0], c[1], "-scheme", s, "-configuration", cfg, "-destination", dest,
                       "-derivedDataPath", d / "build/x86sim", "build"], d)
    app = app or detect.xcode_last_app(d)
    if not app:
        fail("the build named no .app (is the scheme an app?)")
    return app


def device_build(d, platform, release):
    """An unsigned device build of the project in D (a simulator front end converts a device app at install)"""
    d = Path(d)
    c = container(d)
    if not c:
        fail("no Xcode project")
    s = scheme(d)
    cfg = "Release" if release else "Debug"
    dest = f"generic/platform={OS_NAME.get(platform, 'iOS')}"
    say(f"== build {s} ({dest}, {cfg}, unsigned: converted for the simulator at install)")
    app = _xcodebuild(["python3", XCODEBUILD, c[0], c[1], "-scheme", s, "-configuration", cfg, "-destination", dest,
                       "-derivedDataPath", d / "build/x86sim", "CODE_SIGNING_ALLOWED=NO", "build"], d)
    if not app:
        fail("the build named no .app")
    return app
