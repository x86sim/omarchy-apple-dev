"""Projects built by one of the fork's own build scripts, which end with "simulator app ready: <app>":
  xtool   ship.sh --simulator (TRIPLE, CONFIGURATION); a Kotlin Multiplatform app (xtool.env: KMP_GRADLE_ROOT) with
          kmp/build-app.sh --simulator, which builds its shared framework first
  dotnet  dotnet/build.sh --simulator -c Debug|Release DIR (NativeAOT, iossimulator-arm64)
  rust    rust/build.py --simulator [--release] DIR (cargo for aarch64-apple-ios-sim)"""
from pathlib import Path

from . import detect
from .common import FORK, env_with, fail, say, stream


def triple(platform):
    if platform in ("tvos", "watchos", "xros"):
        return f"arm64-apple-{platform}-simulator"
    return "arm64-apple-ios-simulator"


def sim_script(d):
    """kmp/build-app.sh for a KMP app (xtool.env names KMP_GRADLE_ROOT), else ship.sh"""
    text = (Path(d) / "xtool.env").read_text(errors="replace") if (Path(d) / "xtool.env").is_file() else ""
    return FORK / ("kmp/build-app.sh" if detect.env_value(text, "KMP_GRADLE_ROOT") else "ship.sh")


def build(d, kind, platform, release):
    d = Path(d)
    if kind == "dotnet" and platform != "ios":
        fail(f"{d}: .NET for iOS apps build for iOS phones only")
    if kind == "rust" and platform != "ios":
        fail(f"{d}: Rust apps build for iOS phones here (aarch64-apple-ios-sim); this phone runs {platform}")
    info = detect.describe(d)
    t = triple(platform)
    say(f"== build {info['name']} for {t} ({'release' if release else 'debug'})")
    env = env_with(TRIPLE=t, CONFIGURATION="release" if release else "debug")
    if kind == "dotnet":
        cmd = ["bash", FORK / "dotnet/build.sh", "--simulator", "-c", "Release" if release else "Debug", d]
    elif kind == "rust":
        # rust/build.py takes its target from the command itself
        cmd = ["python3", "-I", FORK / "rust/build.py", "--simulator"] + (["--release"] if release else []) + [d]
        env = None
    else:
        cmd = ["bash", sim_script(d), "--simulator"]
    ready = []

    def line(l):
        if l.startswith("simulator app ready: "):
            ready.append(l[len("simulator app ready: "):].strip())

    rc = stream(cmd, d, env, line)
    if rc != 0:
        fail(f"build failed (exit {rc})")
    if ready:
        return d / ready[-1]
    app = detect.describe(d)["app"]
    if not app:
        fail("the build wrote no .app")
    return Path(app)
