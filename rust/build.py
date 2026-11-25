#!/usr/bin/env python3
"""Build a Rust iOS app on Linux: cargo for aarch64-apple-ios-sim / aarch64-apple-ios with the Darwin SDK
(rust/ios-env.sh), then the .app around the binary, as Xcode would lay it out.

  rust/build.py [--simulator | --device] [--release] [--target-dir DIR] [--bin NAME] [PROJECT]

PROJECT (default .) is a cargo package: Cargo.toml in it, or in src-tauri/ (a Tauri app). The app's settings come
from [package.metadata.ios] in Cargo.toml, else from what the framework already has (tauri.conf.json, Dioxus.toml):

  [package.metadata.ios]
  bundle-id = "com.example.app"      # CFBundleIdentifier
  display-name = "My App"            # the name under the icon
  version = "1.0"                    # CFBundleShortVersionString (default: the package version)
  min-os = "17.0"                    # MinimumOSVersion, IPHONEOS_DEPLOYMENT_TARGET
  entry = "main_rs"                  # a library app: link its staticlib with a main() that calls this C function
  resources = ["assets"]             # files and folders copied into the .app (default: assets/ when there is one)
  features = ["..."]                 # cargo features for the iOS build
  info-plist = { UIStatusBarHidden = true }   # extra Info.plist keys

The app: <target dir>/ios-sim/<Name>.app (simulator) or ios/<Name>.app (device). The last line says where:
"simulator app ready: PATH" or "device app ready: PATH". Device apps are signed ad hoc by the linker; sign them for a
phone with tools/sign-dev.sh, or install with xtool.
"""
import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))


def die(msg):
    print(f"rust/build: {msg}", file=sys.stderr)
    sys.exit(1)


def ios_env(kind):
    """os.environ plus what ios-env.sh exports for this platform"""
    out = subprocess.run(["bash", "-c", '. "$1" >&2 && env -0', "_", os.path.join(HERE, "ios-env.sh")],
                         env={**os.environ, "IOS_ENV_TARGET": kind}, capture_output=True, check=False)
    if out.returncode != 0 or b"SDKROOT=" not in out.stdout:
        die("the Darwin SDK is not set up: " + out.stderr.decode(errors="replace").strip())
    env = dict(kv.split("=", 1) for kv in out.stdout.decode().split("\0") if "=" in kv)
    return env


def find_manifest(project):
    for d in (project, os.path.join(project, "src-tauri")):
        if os.path.isfile(os.path.join(d, "Cargo.toml")):
            return os.path.abspath(d)
    die(f"{project}: no Cargo.toml (nor src-tauri/Cargo.toml)")


def flavor(pkg, crate_dir):
    deps = {**pkg.get("dependencies", {}), **pkg.get("target", {}).get("cfg(target_os = \"ios\")", {}).get("dependencies", {})}
    if "tauri" in deps or os.path.isfile(os.path.join(crate_dir, "tauri.conf.json")):
        return "tauri"
    if "dioxus" in deps:
        return "dioxus"
    if "bevy" in deps:
        return "bevy"
    return "rust"


def app_settings(manifest, crate_dir, fl):
    p = manifest["package"]
    meta = p.get("metadata", {}).get("ios", {})
    s = {"name": p["name"], "version": str(p.get("version", "1.0")), "bundle_id": None, "display": None}
    if fl == "tauri":
        import json
        conf = json.load(open(os.path.join(crate_dir, "tauri.conf.json")))
        s["bundle_id"] = conf.get("identifier")
        s["display"] = conf.get("productName")
        s["version"] = str(conf.get("version") or s["version"])
    if fl == "dioxus":
        for d in (crate_dir, os.path.dirname(crate_dir)):
            f = os.path.join(d, "Dioxus.toml")
            if os.path.isfile(f):
                dx = tomllib.load(open(f, "rb"))
                s["display"] = dx.get("application", {}).get("name") or s["display"]
                s["bundle_id"] = dx.get("bundle", {}).get("identifier") or s["bundle_id"]
    s["bundle_id"] = meta.get("bundle-id") or s["bundle_id"] or "com.example." + p["name"].replace("_", "-")
    s["display"] = meta.get("display-name") or s["display"] or p["name"]
    s["version"] = str(meta.get("version") or s["version"])
    s["min_os"] = str(meta.get("min-os") or os.environ.get("IPHONEOS_DEPLOYMENT_TARGET") or "17.0")
    s["entry"] = meta.get("entry")
    s["features"] = meta.get("features", [])
    s["info"] = meta.get("info-plist", {})
    res = meta.get("resources")
    if res is None:
        res = [r for r in ("assets",) if os.path.isdir(os.path.join(crate_dir, r))]
    s["resources"] = res
    return s


def run(cmd, env, cwd):
    print("+ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, env=env, cwd=cwd)
    if r.returncode != 0:
        die(f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''} failed (exit {r.returncode})")


def link_entry(lib, entry, out, env, extra, target):
    """A library app (Bevy's #[bevy_main], Tauri's mobile_entry_point): main() calls the crate's entry function"""
    main_c = out + "-main.c"
    with open(main_c, "w") as f:
        f.write(f"extern void {entry}(void);\nint main(int argc, char **argv) {{ (void)argc; (void)argv; {entry}(); return 0; }}\n")
    cc = env["CC_" + target.replace("-", "_")]
    cmd = [cc, main_c, lib, "-o", out, "-lobjc", "-lc++", "-Wl,-dead_strip", "-framework", "Foundation", "-framework", "UIKit"] + extra
    run(cmd, env, os.path.dirname(out))


def info_plist(s, exe, sim, sdk):
    sdk_ver = plistlib.load(open(os.path.join(sdk, "SDKSettings.plist"), "rb")).get("Version", "")
    plat = "iPhoneSimulator" if sim else "iPhoneOS"
    d = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleExecutable": exe,
        "CFBundleIdentifier": s["bundle_id"],
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": s["display"],
        "CFBundleDisplayName": s["display"],
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": s["version"],
        "CFBundleVersion": s["version"],
        "CFBundleSupportedPlatforms": [plat],
        "DTPlatformName": plat.lower(),
        "DTPlatformVersion": sdk_ver,
        "DTSDKName": plat.lower() + sdk_ver,
        "LSRequiresIPhoneOS": True,
        "MinimumOSVersion": s["min_os"],
        "UIDeviceFamily": [1, 2],
        # a launch screen, or iOS runs the app letterboxed at an old phone's size
        "UILaunchScreen": {},
        "UIRequiredDeviceCapabilities": ["arm64"],
        "UISupportedInterfaceOrientations": ["UIInterfaceOrientationPortrait", "UIInterfaceOrientationLandscapeLeft",
                                             "UIInterfaceOrientationLandscapeRight"],
    }
    d.update(s["info"])
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--simulator", action="store_true", help="aarch64-apple-ios-sim (default)")
    g.add_argument("--device", action="store_true", help="aarch64-apple-ios")
    ap.add_argument("--release", action="store_true")
    ap.add_argument("--target-dir")
    ap.add_argument("--bin")
    ap.add_argument("project", nargs="?", default=".")
    a = ap.parse_args()
    if os.environ.get("CONFIGURATION", "").lower() == "release":
        a.release = True
    sim = not a.device
    kind = "sim" if sim else "device"
    target = "aarch64-apple-ios-sim" if sim else "aarch64-apple-ios"

    crate_dir = find_manifest(os.path.abspath(a.project))
    manifest = tomllib.load(open(os.path.join(crate_dir, "Cargo.toml"), "rb"))
    if "package" not in manifest:
        die(f"{crate_dir}/Cargo.toml is a workspace without a package: pass the app's crate directory")
    fl = flavor(manifest, crate_dir)
    s = app_settings(manifest, crate_dir, fl)
    env = ios_env(kind)
    env["IPHONEOS_DEPLOYMENT_TARGET"] = s["min_os"]
    target_dir = os.path.abspath(a.target_dir or env.get("CARGO_TARGET_DIR") or os.path.join(crate_dir, "target"))
    env["CARGO_TARGET_DIR"] = target_dir
    profile = "release" if a.release else "debug"
    print(f"== {s['display']} ({fl}, {s['bundle_id']}) for {target}, {profile}", flush=True)

    flavor_mod = None
    if fl == "tauri":
        sys.path.insert(0, HERE)
        import tauri_ios as flavor_mod  # noqa: E402
        s = flavor_mod.prepare(s, crate_dir, env, target)

    cargo = ["cargo", "build", "--target", target] + (["--release"] if a.release else [])
    if s["features"]:
        cargo += ["--features", ",".join(s["features"])]
    if s["entry"]:
        cargo += ["--lib"]
    elif a.bin:
        cargo += ["--bin", a.bin]
    run(cargo, env, crate_dir)

    out_dir = os.path.join(target_dir, target, profile)
    app_dir = os.path.join(target_dir, "ios-sim" if sim else "ios", s["display"].replace("/", "_") + ".app")
    if os.path.isdir(app_dir):
        shutil.rmtree(app_dir)
    os.makedirs(app_dir)
    exe = (a.bin or s["name"]).replace("/", "_")
    if s["entry"]:
        lib_name = manifest.get("lib", {}).get("name") or s["name"]
        lib = os.path.join(out_dir, "lib" + lib_name.replace("-", "_") + ".a")
        if not os.path.isfile(lib):
            die(f"{lib} is missing: the crate needs crate-type = [\"staticlib\", ...] in [lib]")
        extra = flavor_mod.link_args(s, crate_dir, env, target, a.release) if flavor_mod else []
        link_entry(lib, s["entry"], os.path.join(app_dir, exe), env, extra, target)
    else:
        built = os.path.join(out_dir, a.bin or s["name"])
        if not os.path.isfile(built):
            die(f"{built} is missing: the package has no binary of that name (pass --bin, or set entry for a library app)")
        shutil.copy2(built, os.path.join(app_dir, exe))
    for r in s["resources"]:
        src = os.path.join(crate_dir, r)
        dst = os.path.join(app_dir, os.path.basename(r.rstrip("/")))
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        elif os.path.isfile(src):
            shutil.copy2(src, dst)
        else:
            die(f"resource {r} not found in {crate_dir}")
    if flavor_mod:
        flavor_mod.finish(s, crate_dir, app_dir, env)
    with open(os.path.join(app_dir, "Info.plist"), "wb") as f:
        plistlib.dump(info_plist(s, exe, sim, env["SDKROOT"]), f)
    with open(os.path.join(app_dir, "PkgInfo"), "w") as f:
        f.write("APPL????")
    print(f"{'simulator' if sim else 'device'} app ready: {app_dir}", flush=True)


if __name__ == "__main__":
    main()
