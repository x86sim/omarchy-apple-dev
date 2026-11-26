"""Dependency managers and project generators before the Xcode build: Carthage (a Cartfile), Tuist (Project.swift:
its manifests evaluated with ProjectDescription built for Linux, the project written by XcodeGen), XcodeGen
(project.yml). Bazel rules_apple workspaces are recognised and refused with the reason (bazel/README.md)."""
import subprocess
from pathlib import Path

from . import detect
from .common import FORK, fail, setup_hint, step

TOOLS = {
    "carthage": ("Carthage", "carthage/bin/carthage"),
    "xcodegen": ("XcodeGen", "xcodegen/bin/xcodegen"),
    "tuist": ("Tuist", "tuist/bin/tuist"),
}

CARTHAGE_PLATFORM = {"tvos": "tvOS", "watchos": "watchOS", "xros": "visionOS"}


def bazel_blocker():
    return ("Bazel rules_apple apps do not build on Linux yet: apple_support registers its Apple C/Swift toolchains for "
            "macOS hosts only and its tools run /usr/bin/xcrun; where it stops and what a Linux path needs: "
            f"{FORK / 'bazel/README.md'}")


def runner(tool):
    """The tool's runner; an error when its install.sh --check says it is not installed"""
    title, rel = TOOLS[tool]
    ok = subprocess.run(["bash", str(FORK / tool / "install.sh"), "--check"], stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not ok:
        fail(f"{title} is not installed: {setup_hint(tool)}")
    return FORK / rel


def prepare(d, platform):
    """`carthage bootstrap` when there is a Cartfile (xcframeworks, cached builds: a dependency is built again only when
    its version changes), then `tuist generate` / `xcodegen generate` (after Carthage: XcodeGen's Carthage
    dependencies look at Carthage/Build)"""
    d = Path(d)
    if (d / "Cartfile").is_file():
        carthage = runner("carthage")
        plat = CARTHAGE_PLATFORM.get(platform, "iOS")
        step(["bash", carthage, "bootstrap", "--use-xcframeworks", "--cache-builds", "--platform", plat], d,
             f"carthage bootstrap ({plat})", err="carthage bootstrap failed (exit {rc}; its xcodebuild log is named above)")
    if detect.is_tuist(d):
        tuist = runner("tuist")
        runner("xcodegen")
        step(["bash", tuist, "generate", "--no-open"], d, "tuist generate")
    elif detect.is_xcodegen(d):
        step(["bash", runner("xcodegen"), "generate"], d, "xcodegen generate")
