"""Tauri 2 apps for rust/build.py: what `tauri ios build` and its Xcode project do, without either.

- The app is the crate's library (Tauri's mobile layout): its staticlib is linked with a main() that calls
  start_app (tauri::mobile_entry_point).
- tauri's build script links its Swift half (the `Tauri` package in tauri's mobile/ios-api: plugin bridge, IPC,
  logging) only on a Mac, through xcodebuild / swift build. Here it is built with Linux Swift and the Darwin SDK
  (swift build --swift-sdk darwin) and linked in, with the Swift runtime's search paths.
- The frontend (build.frontendDist) is built into the binary and served over tauri:// (the tauri/custom-protocol
  feature, as `tauri build`); TAURI_DEV=1 leaves it off, for a devUrl server the phone can reach.
- tao (Tauri's windowing) adopts the scene life cycle when the Info.plist names its scene delegate (iOS 27 requires
  that of apps built with its SDK): build.py names TaoSceneDelegate for any app on tao, as Tauri's iOS template does.

Not covered: Tauri plugins with Swift code of their own (their ios/ packages expect the tauri-cli generated project);
a plugin without Swift code works.
"""
import glob
import json
import os
import shutil
import subprocess
import sys


def _die(msg):
    print(f"rust/build (tauri): {msg}", file=sys.stderr)
    sys.exit(1)


def prepare(s, crate_dir, env, target):
    s["entry"] = s["entry"] or "start_app"
    # the frontend built into the app, served over tauri:// (what `tauri build` turns on); without it a debug build
    # loads devUrl, the `tauri dev` server
    if not os.environ.get("TAURI_DEV") and "tauri/custom-protocol" not in s["features"]:
        s["features"].append("tauri/custom-protocol")
    return s


def _tauri_dir(crate_dir, env, target):
    out = subprocess.run(["cargo", "metadata", "--format-version", "1", "--filter-platform", target],
                         cwd=crate_dir, env=env, capture_output=True, text=True)
    if out.returncode != 0:
        _die("cargo metadata failed: " + out.stderr.strip()[-500:])
    for p in json.loads(out.stdout)["packages"]:
        if p["name"] == "tauri":
            return os.path.dirname(p["manifest_path"])
    _die("the crate does not depend on tauri")


def _swift_lib(crate_dir, env, target, release):
    """libTauri.a for the target: the Tauri Swift package, built with Linux Swift for the iOS triple"""
    api = os.path.join(_tauri_dir(crate_dir, env, target), "mobile/ios-api")
    if not os.path.isfile(os.path.join(api, "Package.swift")):
        _die(f"{api}: no Package.swift (a tauri without its iOS API?)")
    triple = "arm64-apple-ios-simulator" if target.endswith("-sim") else "arm64-apple-ios"
    conf = "release" if release else "debug"
    work = os.path.join(env["CARGO_TARGET_DIR"], "tauri-ios-api", os.path.basename(os.path.dirname(os.path.dirname(api))))
    src = os.path.join(work, "src")
    # a writable copy: SwiftPM writes Package.resolved next to the manifest, the cargo registry is not ours to change
    if not os.path.isdir(src):
        shutil.copytree(api, src)
    swift_env = {k: v for k, v in env.items() if k != "SDKROOT"}
    cmd = ["swift", "build", "--build-system", "native", "--swift-sdk", "darwin", "--triple", triple, "-c", conf,
           "--target", "Tauri", "--scratch-path", os.path.join(work, "build"),
           "-j", os.environ.get("CARGO_BUILD_JOBS", "2")]
    print("+ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=src, env=swift_env, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-4000:] + r.stderr[-4000:], file=sys.stderr)
        _die("building the Tauri Swift package failed")
    objs = sorted(glob.glob(os.path.join(work, "build", triple, conf, "Tauri.build", "*.o")) +
                  glob.glob(os.path.join(work, "build", triple, conf, "SwiftRs.build", "*.o")))
    if not objs:
        _die("the Tauri Swift package built no objects")
    lib = os.path.join(work, f"libTauri-{triple}-{conf}.a")
    if os.path.exists(lib):
        os.remove(lib)
    subprocess.run([env.get("AR_" + target.replace("-", "_"), "ar"), "rcs", lib] + objs, check=True)
    return lib


def link_args(s, crate_dir, env, target, release):
    lib = _swift_lib(crate_dir, env, target, release)
    plat = "iphonesimulator" if target.endswith("-sim") else "iphoneos"
    # <bundle>/Developer/Platforms/<P>.platform/Developer/SDKs/<P>.sdk -> <bundle>/Developer/Toolchains/...
    toolchain = os.path.normpath(os.path.join(env["SDKROOT"], "../../../../../Toolchains/XcodeDefault.xctoolchain/usr/lib/swift", plat))
    return ["-Wl,-force_load," + lib, "-L" + toolchain, "-L" + os.path.join(env["SDKROOT"], "usr/lib/swift"),
            "-Wl,-rpath,/usr/lib/swift", "-framework", "WebKit"]


def finish(s, crate_dir, app_dir, env):
    pass
