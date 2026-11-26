"""React Native and Expo apps: the iOS project from `expo prebuild` (or the app's own ios/), its pods from
`pod install` (cocoapods/install.sh), the build from tools/xcbuild.py (the CocoaPods workspace built on Linux)."""
import os
from pathlib import Path

from . import detect
from .common import FORK, env_with, fail, pod, say, setup_hint, step, stream


def package_manager(d):
    """The JavaScript package manager the app uses (its lock file)"""
    d = Path(d)
    if (d / "yarn.lock").exists():
        return "yarn"
    if (d / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (d / "bun.lock").exists() or (d / "bun.lockb").exists():
        return "bun"
    return "npm"


def workspace(d):
    """The ios/ workspace pod install made: (ios dir, workspace, scheme)"""
    ios = Path(d) / "ios"
    ws = next((p for p in detect._entries(ios) if p.suffix == ".xcworkspace"), None)
    return (ios, ws, ws.stem) if ws else None


def _bytes(p):
    try:
        return Path(p).read_bytes()
    except OSError:
        return None


def prepare(d, kind):
    """node_modules, ios/ (expo prebuild), pods: what the build needs, done when missing or out of date"""
    d = Path(d)
    if not (d / "node_modules").is_dir():
        pm = package_manager(d)
        step([pm, "install"], d, f"{pm} install")
    if kind == "expo" and not (d / "ios").is_dir():
        step(["npx", "expo", "prebuild", "--platform", "ios", "--no-install"], d, "expo prebuild --platform ios",
             env=env_with(CI="1"))
    ios = d / "ios"
    if not (ios / "Podfile").exists():
        fail(f"{d}: no ios/Podfile (a React Native app has one; Expo makes one with expo prebuild)")
    lock = _bytes(ios / "Podfile.lock")
    manifest = _bytes(ios / "Pods/Manifest.lock")
    stale = (lock is None or lock != manifest
             or detect._mtime(ios / "Podfile") > detect._mtime(ios / "Pods/Manifest.lock") or workspace(d) is None)
    if stale:
        p = pod()
        if not p:
            fail(f"CocoaPods is not installed: {setup_hint('cocoapods')}")
        step([p, "install"], ios, "pod install")


def build(d, kind, device, release):
    """Simulator (or device: sdk iphoneos) build of a React Native / Expo app: the .app"""
    prepare(d, kind)
    w = workspace(d)
    if not w:
        fail("no .xcworkspace in ios/ after pod install")
    ios, ws, scheme = w
    sdk = "iphoneos" if device else "iphonesimulator"
    cfg = "Release" if release else "Debug"
    cmd = ["python3", FORK / "tools/xcbuild.py", "-workspace", ws, "-scheme", scheme, "-sdk", sdk, "-configuration", cfg]
    if "XCBUILD_JOBS" not in os.environ:
        cmd += ["-jobs", "4"]
    say(f"== build {scheme} ({sdk}, {cfg})")
    apps = []

    def line(l):
        if l.startswith("app: "):
            apps.append(Path(l[len("app: "):].strip()))
        # ld64.lld says this for every image; it is not news
        return "does not support linking for platform" not in l

    rc = stream(cmd, ios, None, line)
    if rc != 0:
        fail(f"the build failed (exit {rc})")
    if not apps:
        fail("the build named no .app")
    return apps[-1]
