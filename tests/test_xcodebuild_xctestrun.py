"""linux-bin/xcodebuild: the .xctestrun build-for-testing writes for a tvOS / watchOS / visionOS simulator build, which
sweetpad's generator (iOS only) does not write. Offline: sweetpad's settings are stubbed, the products are made here.

Rows (expected results written before the code):
  1  logic tests (Debug-watchsimulator/L.xctest) -> TestHostPath is WatchSimulator.platform's Agents/xctest, the
     bundle under __TESTROOT__/Debug-watchsimulator, libRPAC inserted
  2  hosted unit tests (App.app/PlugIns/U.xctest) -> IsAppHostedTestBundle, TestHostPath the app,
     TestHostBundleIdentifier the app's CFBundleIdentifier, libXCTestBundleInject inserted
  3  UI tests (UI-Runner.app/PlugIns/UI.xctest) -> IsUITestBundle, the runner as host, UITargetAppPath the
     FULL_PRODUCT_NAME of the target's TEST_TARGET_NAME (not the other app)
  4  UI tests without TEST_TARGET_NAME and one app -> that app is the app under test
  5  UI tests without TEST_TARGET_NAME and two apps -> left out (no guess), the other targets kept
  6  every platform: appletvsimulator / xrsimulator -> AppleTVSimulator / XRSimulator paths, the file named
     <Scheme>-<Configuration>-<platform>.xctestrun next to the configuration's products
  7  no test bundle built -> no .xctestrun (None)
Mutants (each must fail its row; checked by hand when the test was written):
  M1  TestHostPath of logic tests from iPhoneSimulator.platform -> rows 1, 6
  M2  UITargetAppPath = the first app in the products -> row 3
  M3  guess the first app when several and no TEST_TARGET_NAME -> row 5
"""
import importlib.machinery
import importlib.util
import os
import plistlib
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "linux-bin/xcodebuild"


def load():
    loader = importlib.machinery.SourceFileLoader("xcodebuild_standin", str(TOOL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


def bundle(path, bid=None):
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "Info.plist"), "wb") as f:
        plistlib.dump({"CFBundleIdentifier": bid or Path(path).stem}, f)


class WriteXctestrun(unittest.TestCase):
    def setUp(self):
        self.x = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.x.say = lambda msg: None

    def tearDown(self):
        self.tmp.cleanup()

    def run_for(self, sdk, settings, make):
        sub = f"Debug-{sdk}"
        built = self.root / "Build/Products" / sub
        built.mkdir(parents=True)
        make(built)
        scheme = {"App": {"BUILT_PRODUCTS_DIR": str(built), "CONFIGURATION": "Debug",
                          "EFFECTIVE_PLATFORM_NAME": f"-{sdk}"}}
        self.x.sweetpad_settings = lambda a, target=None: scheme if target is None else (
            {target: settings[target]} if target in settings else {})
        a = self.x.parse(["-project", str(self.root / "Demo.xcodeproj"), "-scheme", "Demo", "-sdk", sdk,
                          "build-for-testing"])
        out = self.x.write_xctestrun(a)
        if out is None:
            return None, None
        with open(out, "rb") as f:
            d = plistlib.load(f)
        return out, {t["BlueprintName"]: t for t in d["TestConfigurations"][0]["TestTargets"]}

    def full(self, built, apps=("App.app",)):
        for app in apps:
            bundle(built / app, "com.example." + app[:-4])
        bundle(built / "App.app/PlugIns/U.xctest")
        bundle(built / "L.xctest")
        bundle(built / "UI-Runner.app", "com.example.UI.xctrunner")
        bundle(built / "UI-Runner.app/PlugIns/UI.xctest")

    def test_row1_logic(self):
        _, t = self.run_for("watchsimulator", {"UI": {"TEST_TARGET_NAME": "App"}, "App": {"FULL_PRODUCT_NAME": "App.app"}},
                            self.full)
        L = t["L"]
        self.assertEqual(L["TestHostPath"], "__PLATFORMS__/WatchSimulator.platform/Developer/Library/Xcode/Agents/xctest")
        self.assertEqual(L["TestBundlePath"], "__TESTROOT__/Debug-watchsimulator/L.xctest")
        self.assertEqual(L["TestingEnvironmentVariables"]["DYLD_INSERT_LIBRARIES"], "/usr/lib/libRPAC.dylib")
        self.assertNotIn("IsUITestBundle", L)

    def test_row2_hosted(self):
        _, t = self.run_for("watchsimulator", {"UI": {"TEST_TARGET_NAME": "App"}, "App": {"FULL_PRODUCT_NAME": "App.app"}},
                            self.full)
        U = t["U"]
        self.assertTrue(U["IsAppHostedTestBundle"])
        self.assertEqual(U["TestHostPath"], "__TESTROOT__/Debug-watchsimulator/App.app")
        self.assertEqual(U["TestHostBundleIdentifier"], "com.example.App")
        self.assertEqual(U["TestBundlePath"], "__TESTHOST__/PlugIns/U.xctest")
        self.assertIn("libXCTestBundleInject.dylib", U["TestingEnvironmentVariables"]["DYLD_INSERT_LIBRARIES"])

    def test_row3_ui(self):
        st = {"UI": {"TEST_TARGET_NAME": "App"}, "App": {"FULL_PRODUCT_NAME": "App.app"}}
        _, t = self.run_for("watchsimulator", st, lambda b: self.full(b, apps=("Aaa.app", "App.app")))
        UI = t["UI"]
        self.assertTrue(UI["IsUITestBundle"] and UI["IsXCTRunnerHostedTestBundle"])
        self.assertEqual(UI["TestHostPath"], "__TESTROOT__/Debug-watchsimulator/UI-Runner.app")
        self.assertEqual(UI["TestHostBundleIdentifier"], "com.example.UI.xctrunner")
        self.assertEqual(UI["UITargetAppPath"], "__TESTROOT__/Debug-watchsimulator/App.app")

    def test_row4_ui_one_app(self):
        _, t = self.run_for("watchsimulator", {}, self.full)
        self.assertEqual(t["UI"]["UITargetAppPath"], "__TESTROOT__/Debug-watchsimulator/App.app")

    def test_row5_ui_two_apps_no_target(self):
        _, t = self.run_for("watchsimulator", {}, lambda b: self.full(b, apps=("App.app", "Other.app")))
        self.assertNotIn("UI", t)
        self.assertIn("U", t)
        self.assertIn("L", t)

    def test_row6_platforms(self):
        for sdk, plat in (("appletvsimulator", "AppleTVSimulator"), ("xrsimulator", "XRSimulator")):
            with self.subTest(sdk=sdk):
                self.tearDown()
                self.setUp()
                out, t = self.run_for(sdk, {}, self.full)
                self.assertEqual(os.path.basename(out), f"Demo-Debug-{sdk}.xctestrun")
                self.assertEqual(os.path.dirname(out), str(self.root / "Build/Products"))
                self.assertTrue(t["L"]["TestHostPath"].startswith(f"__PLATFORMS__/{plat}.platform/"))
                self.assertIn(f"{plat}.platform", t["UI"]["TestingEnvironmentVariables"]["DYLD_FRAMEWORK_PATH"])

    def test_row7_nothing_built(self):
        out, _ = self.run_for("watchsimulator", {}, lambda b: bundle(b / "App.app"))
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
