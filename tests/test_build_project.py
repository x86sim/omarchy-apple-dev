"""tools/build-project --detect / --describe on small fixture projects, one per kind (and the ones that must lose)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools/build-project"

PJ = lambda deps: json.dumps({"dependencies": deps})

# kind -> {relative path: contents}; a path ending in / is a directory
FIXTURES = {
    "xtool": {"Package.swift": "", "xtool.yml": "version: 1\nbundleID: com.example.Hello\nproduct: Hello\n"},
    "flutter": {"pubspec.yaml": "name: hello\n"},
    "godot": {"project.godot": "", "package.json": PJ({"@capacitor/ios": "^7"})},
    "unity": {"ProjectSettings/ProjectVersion.txt": "m_EditorVersion: 6000.0\n", "Assets/": None},
    "capacitor": {"package.json": PJ({"@capacitor/core": "^7", "react-native": "1"}), "capacitor.config.ts": ""},
    "cordova": {"package.json": json.dumps({"devDependencies": {"cordova-ios": "^7"}}), "config.xml": "<widget/>"},
    "nativescript": {"package.json": PJ({"@nativescript/core": "8"}), "nativescript.config.ts": ""},
    "expo": {"package.json": PJ({"expo": "54", "react-native": "0.81"})},
    "reactnative": {"package.json": PJ({"react-native": "0.81"}), "Cartfile": "", "App.xcodeproj/": None},
    "rust": {"src-tauri/Cargo.toml": '[package]\nname = "hello"\n[package.metadata.ios]\nbundle-id = "com.example.rs"\n',
             "project.yml": "targets:\n"},
    "bazel": {"MODULE.bazel": 'bazel_dep(name = "rules_apple")\n', "Project.swift": "import ProjectDescription\n"},
    "tuist": {"Project.swift": "import ProjectDescription\n", "project.yml": "targets:\n"},
    "xcodegen": {"project.yml": "name: X\ntargets:\n  X: {}\n", "Cartfile": ""},
    "carthage": {"Cartfile": 'github "a/b"\n', "App.xcworkspace/": None, "App.csproj": "<TargetFramework>net10.0-ios</TargetFramework>"},
    "dotnet": {"App.csproj": "<Project><PropertyGroup><TargetFrameworks>net10.0-android;net10.0-ios</TargetFrameworks>"
                             "<ApplicationId>com.example.net</ApplicationId></PropertyGroup></Project>",
               "App.xcodeproj/": None},
    "xcodeproj": {"Demo.xcodeproj/": None, "Package.swift": ""},
    "swiftpm": {"Package.swift": ""},
    # not projects: a Cartfile alone, a non-iOS csproj, an empty project.yml, a Cargo.toml without a name
    None: {"Cartfile": "", "Lib.csproj": "<TargetFramework>net10.0</TargetFramework>", "project.yml": "name: X\n",
           "Cargo.toml": "[workspace]\n", "package.json": PJ({"left-pad": "1"})},
}


def make(root, files):
    root.mkdir(parents=True)
    for rel, text in files.items():
        p = root / rel
        if rel.endswith("/"):
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)


def run(*args, env=None):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True, env=env)


class DetectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for k, files in FIXTURES.items():
            make(self.root / (k or "none"), files)

    def tearDown(self):
        self.tmp.cleanup()

    def test_detect_each_kind(self):
        for k in FIXTURES:
            with self.subTest(kind=k):
                r = run("--detect", self.root / (k or "none"))
                self.assertEqual(r.stdout.strip(), k or "")
                self.assertEqual(r.returncode, 0 if k else 1)

    def test_describe(self):
        env = dict(os.environ, CARGO_TARGET_DIR=str(self.root / "target"))
        (self.root / "target/ios-sim/hello.app").mkdir(parents=True)
        dirs = [self.root / k for k in ("xtool", "rust", "dotnet")] + [self.root / "none"]
        lines = [json.loads(l) for l in run("--describe", *dirs, env=env).stdout.splitlines()]
        self.assertEqual([l.get("kind") for l in lines], ["xtool", "rust", "dotnet", None])
        self.assertEqual((lines[0]["name"], lines[0]["bundle_id"], lines[0]["app"]), ("Hello", "com.example.Hello", None))
        self.assertEqual((lines[1]["name"], lines[1]["bundle_id"]), ("hello", "com.example.rs"))
        self.assertEqual(lines[1]["app"], str(self.root / "target/ios-sim/hello.app"))
        self.assertEqual((lines[2]["name"], lines[2]["bundle_id"]), ("App", "com.example.net"))
        self.assertIn("not an app project", lines[3]["error"])

    def test_last_xcode_app(self):
        d = self.root / "xcodeproj"
        old = d / "build/x86sim/Build/Products/Debug-iphonesimulator/Old.app"
        new = d / "build/x86sim/Build/Products/Release-iphonesimulator/New.app"
        old.mkdir(parents=True)
        new.mkdir(parents=True)
        os.utime(old, (1, 1))
        self.assertEqual(json.loads(run("--describe", d).stdout)["app"], str(new.resolve()))

    def test_refusals_are_one_line_errors(self):
        for k, why in (("bazel", "rules_apple"), ("swiftpm", "without xtool.yml"), ("none", "not an app project")):
            with self.subTest(kind=k):
                r = run(self.root / k)
                self.assertEqual(r.returncode, 1)
                last = r.stderr.strip().splitlines()[-1]
                self.assertTrue(last.startswith("error: ") and why in last, last)
        r = run(self.root / "rust", "--platform", "tvos")
        self.assertIn("this phone runs tvos", r.stderr)


if __name__ == "__main__":
    unittest.main()
