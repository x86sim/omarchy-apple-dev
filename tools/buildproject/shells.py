"""Cross-platform app shells and engine exports: the shell's own tool writes (or refreshes) the Xcode project on Linux,
then it builds with Swift Build like any Xcode project (xcode.py). Kinds:

  capacitor     the web build (`<pm> run build`, when the app has one), then `npx cap add ios` once and
                `npx cap sync ios`; an Ionic starter without @capacitor/ios gets it added at its @capacitor/core
                version (as `ionic capacitor add ios` does). The Xcode project is ios/App (capacitor.config.json's
                ios.path moves ios/).
  cordova       `cordova prepare ios` (the app's own cordova CLI, else npx's): adds the platform, copies www/; the
                Xcode project is platforms/ios.
  nativescript  shells/nativescript/ns prepare ios; the Xcode project is platforms/ios.
  godot         shells/godot/export.sh into build/godot-ios; an iOS device build (the template's simulator library is
                x86_64 only), converted for the simulator by the front end at install.
  unity         shells/unity/build.sh into build/unity-ios (IL2CPP, arm64 simulator).
"""
from pathlib import Path

from . import detect, xcode
from .common import FORK, env_with, env_with_pod, fail, pod, pod_home, setup_hint, step
from .pods import package_manager


def prepare(d, kind):
    """node_modules, the web build, the shell's native project: what the Xcode build needs"""
    d = Path(d)
    native = detect.shell_native_dir(d, kind)
    if kind == "godot":
        step(["bash", FORK / "shells/godot/export.sh", d, native], d, "Godot: export the iOS Xcode project (shells/godot/export.sh)")
        return
    if kind == "unity":
        step(["bash", FORK / "shells/unity/build.sh", d, native], d, "Unity: export the iOS Xcode project (shells/unity/build.sh)")
        return
    pm = package_manager(d)
    if not (d / "node_modules").is_dir():
        step([pm, "install"], d, f"{pm} install")
    pj = detect.package_json(d) or {}
    if kind == "capacitor" and not detect.has_dep(pj, "@capacitor/ios"):
        # the iOS platform package, at the version of the app's @capacitor/core (Ionic's `ionic capacitor add ios`)
        core = (pj.get("dependencies") or {}).get("@capacitor/core")
        core = (core if isinstance(core, str) else "latest").lstrip("^~")
        step([pm, "install" if pm == "npm" else "add", f"@capacitor/ios@{core}"], d,
             f"{pm} add @capacitor/ios@{core} (the app had no iOS platform package)")
        pj = detect.package_json(d) or {}
    if kind == "capacitor":
        # Ionic / Vite / Angular apps build their web assets into the web dir cap copies
        if isinstance(pj.get("scripts"), dict) and "build" in pj["scripts"]:
            step([pm, "run", "build"], d, f"{pm} run build")
        # add ios once, then sync: copies the web assets and writes the plugins' Package.swift, or runs pod install
        # for an app on CocoaPods
        verb = "sync" if native.is_dir() else "add"
        if (native / "Podfile").exists() and not pod():
            fail(f"{d}: the app uses CocoaPods, which is not installed: {setup_hint('cocoapods')}")
        step(["npx", "cap", verb, "ios"], d, f"cap {verb} ios", env=env_with_pod())
    if kind == "cordova":
        local = d / "node_modules/.bin/cordova"
        cmd = [local] if local.exists() else ["npx", "--yes", "cordova"]
        # prepare adds the platform package.json lists when it is missing, then copies www/ and config.xml
        step(cmd + ["prepare", "ios", "--no-telemetry"], d, "cordova prepare ios", env=env_with_pod())
    if kind == "nativescript":
        step([FORK / "shells/nativescript/ns", "prepare", "ios"], d, "ns prepare ios (shells/nativescript/ns)",
             env=env_with(POD_HOME=pod_home()))


def build(d, kind, platform, device, release):
    """The shell's step, then the Xcode project's build: the .app"""
    if platform != "ios":
        fail(f"{kind} apps build for iPhone and iPad devices here (not {platform})")
    prepare(d, kind)
    native = detect.shell_native_dir(d, kind)
    if not xcode.container(native):
        fail(f"{native}: no Xcode project after the {kind} step")
    if kind == "godot" or device:
        return xcode.device_build(native, platform, release)
    try:
        return xcode.build(native, platform, release)
    except Exception as e:
        fail(f"the Xcode project's build: {e}")
