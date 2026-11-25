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
  scene-adapter = true               # attach old-style windows to the scene (default: when winit < 0.31 is used)
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
    s["scene_adapter"] = meta.get("scene-adapter")
    s["features"] = meta.get("features", [])
    s["info"] = meta.get("info-plist", {})
    res = meta.get("resources")
    if res is None:
        res = [r for r in ("assets",) if os.path.isdir(os.path.join(crate_dir, r))]
    s["resources"] = res
    return s


def dep_versions(crate_dir, env, target):
    """{package name: [versions]} of everything the crate builds with for the target"""
    out = subprocess.run(["cargo", "metadata", "--format-version", "1", "--filter-platform", target],
                         cwd=crate_dir, env=env, capture_output=True, text=True)
    if out.returncode != 0:
        die("cargo metadata failed: " + out.stderr.strip()[-800:])
    import json
    d = {}
    for p in json.loads(out.stdout)["packages"]:
        d.setdefault(p["name"], []).append((p["version"], os.path.dirname(p["manifest_path"])))
    return d


def tao_has_scenes(tao_dir):
    """tao 0.37 and later define TaoSceneDelegate (src/platform_impl/ios/scene.rs)"""
    f = os.path.join(tao_dir, "src/platform_impl/ios/scene.rs")
    return os.path.isfile(f) and "TaoSceneDelegate" in open(f, errors="replace").read()


def scene_manifest(delegate):
    return {"UIApplicationSupportsMultipleScenes": False,
            "UISceneConfigurations": {"UIWindowSceneSessionRoleApplication": [
                {"UISceneConfigurationName": "Default Configuration", "UISceneDelegateClassName": delegate}]}}


def scenes(s, crate_dir, env, target, target_dir):
    """iOS 27 launches apps built with its SDK only with the scene life cycle. An app that names its own scene
    delegate (info-plist UIApplicationSceneManifest) has it; tao 0.37+ (Tauri 2.12) has a scene delegate to name;
    older tao (Dioxus 0.7) and winit before 0.31 (Bevy) make windows the old way: RustSceneAdapter (scene-adapter.m)
    attaches them to the scene. Returns objects to link into the app."""
    if "UIApplicationSceneManifest" in s["info"]:
        return []
    deps = dep_versions(crate_dir, env, target)
    adapter = s.get("scene_adapter")
    tao = deps.get("tao", [])
    if adapter is None and tao and all(tao_has_scenes(d) for _, d in tao):
        s["info"]["UIApplicationSceneManifest"] = scene_manifest("TaoSceneDelegate")
        return []
    old_winit = any(tuple(int(x) for x in v.split("-")[0].split(".")[:2]) < (0, 31) for v, _ in deps.get("winit", []))
    if adapter is None:
        adapter = old_winit or bool(tao)
    if not adapter:
        print("warning: no scene delegate (UIApplicationSceneManifest): iOS 27 refuses to launch an app built with "
              "its SDK without the scene life cycle; name yours in [package.metadata.ios.info-plist] or set "
              "scene-adapter = true", file=sys.stderr)
        return []
    obj = os.path.join(target_dir, target, f"rust-scene-adapter-{target}.o")
    os.makedirs(os.path.dirname(obj), exist_ok=True)
    run([env["CC_" + target.replace("-", "_")], "-fobjc-arc", "-c", os.path.join(HERE, "scene-adapter.m"), "-o", obj],
        env, crate_dir)
    s["info"]["UIApplicationSceneManifest"] = scene_manifest("RustSceneAdapter")
    return [obj]


def run(cmd, env, cwd):
    print("+ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, env=env, cwd=cwd)
    if r.returncode != 0:
        die(f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''} failed (exit {r.returncode})")


def link_entry(lib, entry, out, env, extra, target):
    """A library app (Bevy's #[bevy_main], Tauri's mobile_entry_point): main() calls the crate's entry function"""
    main_c = os.path.join(os.path.dirname(lib), f"ios-main-{entry}.c")
    with open(main_c, "w") as f:
        f.write(f"extern void {entry}(void);\nint main(int argc, char **argv) {{ (void)argc; (void)argv; {entry}(); return 0; }}\n")
    cc = env["CC_" + target.replace("-", "_")]
    cmd = [cc, main_c, lib, "-o", out, "-lobjc", "-lc++", "-Wl,-dead_strip", "-framework", "Foundation", "-framework", "UIKit"] + extra
    run(cmd, env, os.path.dirname(lib))


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

    scene_objs = scenes(s, crate_dir, env, target, target_dir)
    bin_name = a.bin or s["name"]
    if s["entry"]:
        # only the staticlib: a cdylib in the crate's crate-type would be linked too, and fail without the app's
        # other parts (Tauri's Swift library)
        cargo = ["cargo", "rustc", "--lib", "--crate-type", "staticlib", "--target", target]
    elif scene_objs:
        cargo = ["cargo", "rustc", "--bin", bin_name, "--target", target]
    else:
        cargo = ["cargo", "build", "--target", target]
    cargo += ["--release"] if a.release else []
    if s["features"]:
        cargo += ["--features", ",".join(s["features"])]
    if not s["entry"] and not scene_objs and a.bin:
        cargo += ["--bin", a.bin]
    if not s["entry"] and scene_objs:
        cargo += ["--"] + [x for o in scene_objs for x in ("-C", "link-arg=" + o)]
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
        extra = scene_objs + (flavor_mod.link_args(s, crate_dir, env, target, a.release) if flavor_mod else [])
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
