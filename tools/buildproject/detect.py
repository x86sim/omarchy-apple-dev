"""What kind of app project a directory is, and what it is called and last built.

Kinds, in the order they are tried (the first that matches wins):
  xtool        Package.swift + xtool.yml (ship.sh; a Kotlin Multiplatform app is one whose xtool.env names
               KMP_GRADLE_ROOT: kmp/build-app.sh)
  flutter      pubspec.yaml
  godot        project.godot
  unity        ProjectSettings/ProjectVersion.txt + Assets/
  capacitor    package.json with @capacitor/ios, or @capacitor/core and a capacitor.config.*
  cordova      package.json with cordova-ios, and config.xml
  nativescript package.json with @nativescript/ios, or @nativescript/core and a nativescript.config.*
  expo         package.json with expo
  reactnative  package.json with react-native
  rust         Cargo.toml (or src-tauri/Cargo.toml) with a [package] name
  bazel        MODULE.bazel / WORKSPACE / WORKSPACE.bazel naming rules_apple (does not build on Linux yet)
  tuist        Project.swift importing ProjectDescription
  xcodegen     project.yml with targets: or include:
  carthage     Cartfile next to an .xcodeproj / .xcworkspace
  dotnet       a .csproj whose target frameworks include net*-ios
  xcodeproj    an .xcodeproj / .xcworkspace
  swiftpm      Package.swift without xtool.yml (not buildable as an app)
"""
import json
import os
import plistlib
from pathlib import Path

SHELLS = ("capacitor", "cordova", "nativescript", "godot", "unity")
XCODE = ("xcodeproj", "carthage", "xcodegen", "tuist")


def _read(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _entries(d):
    try:
        return sorted(Path(d).iterdir())
    except OSError:
        return []


def _mtime(p):
    try:
        return os.stat(p).st_mtime
    except OSError:
        return float("-inf")


def package_json(d):
    t = _read(Path(d) / "package.json")
    if t is None:
        return None
    try:
        return json.loads(t)
    except ValueError:
        return None


def has_dep(pj, name):
    return isinstance(pj, dict) and any(isinstance(pj.get(k), dict) and name in pj[k] for k in ("dependencies", "devDependencies"))


def shell_kind(d):
    """The cross-platform shell / engine kind of the app in D, if it is one"""
    d = Path(d)
    if (d / "project.godot").is_file():
        return "godot"
    if (d / "ProjectSettings/ProjectVersion.txt").is_file() and (d / "Assets").is_dir():
        return "unity"
    pj = package_json(d)
    if pj is None:
        return None
    cap_config = any((d / f).exists() for f in ("capacitor.config.ts", "capacitor.config.js", "capacitor.config.json"))
    if has_dep(pj, "@capacitor/ios") or (has_dep(pj, "@capacitor/core") and cap_config):
        return "capacitor"
    if has_dep(pj, "cordova-ios") and (d / "config.xml").exists():
        return "cordova"
    ns_config = any((d / f).exists() for f in ("nativescript.config.ts", "nativescript.config.js"))
    if has_dep(pj, "@nativescript/ios") or (has_dep(pj, "@nativescript/core") and ns_config):
        return "nativescript"
    return None


def js_kind(d):
    """expo or reactnative, from D/package.json"""
    pj = package_json(d)
    if pj is None:
        return None
    if has_dep(pj, "expo"):
        return "expo"
    if has_dep(pj, "react-native"):
        return "reactnative"
    return None


# --- Rust ---------------------------------------------------------------------------------------------------------

def toml_table(text, table):
    """`key = "value"` lines of one TOML table (enough for the plain string keys read here)"""
    cur, out = "", []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            cur = line.strip("[]").strip()
            continue
        if cur != table or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if v.startswith('"'):
            out.append((k.strip(), v[1:].split('"')[0]))
    return out


def toml_get(t, key):
    for k, v in t:
        if k == key:
            return v or None
    return None


def rust_project(d):
    """(crate dir, name, bundle id, last simulator .app) of a Rust app project, as rust/build.py takes them"""
    d = Path(d)
    crate = next((c for c in (d, d / "src-tauri") if (c / "Cargo.toml").is_file()), None)
    if crate is None:
        return None
    text = _read(crate / "Cargo.toml")
    if text is None:
        return None
    name = toml_get(toml_table(text, "package"), "name")
    if not name:
        return None
    meta = toml_table(text, "package.metadata.ios")
    bundle = ""
    t = _read(crate / "tauri.conf.json")
    if t is not None:
        try:
            j = json.loads(t)
            bundle = j.get("identifier") if isinstance(j.get("identifier"), str) else ""
            name = j["productName"] if isinstance(j.get("productName"), str) else name
        except (ValueError, AttributeError):
            pass
    for dd in (crate, d):
        t = _read(dd / "Dioxus.toml")
        if t is not None:
            name = toml_get(toml_table(t, "application"), "name") or name
            bundle = toml_get(toml_table(t, "bundle"), "identifier") or bundle
    name = toml_get(meta, "display-name") or name
    bundle = toml_get(meta, "bundle-id") or bundle
    target = Path(os.environ["CARGO_TARGET_DIR"]) if os.environ.get("CARGO_TARGET_DIR") else crate / "target"
    app = target / "ios-sim" / (name.replace("/", "_") + ".app")
    return crate, name, bundle, (app if app.is_dir() else None)


# --- generators, .NET ---------------------------------------------------------------------------------------------

def is_bazel_apple(d):
    return any("rules_apple" in (_read(Path(d) / f) or "") for f in ("MODULE.bazel", "WORKSPACE", "WORKSPACE.bazel"))


def is_tuist(d):
    return "import ProjectDescription" in (_read(Path(d) / "Project.swift") or "")


def is_xcodegen(d):
    y = _read(Path(d) / "project.yml")
    return y is not None and any(l.startswith("targets:") or l.startswith("include:") for l in y.splitlines())


def has_xcode(d):
    return any(e.name.endswith(".xcodeproj") or e.name.endswith(".xcworkspace") for e in _entries(d))


def gen_kind(d):
    """bazel, tuist, xcodegen or carthage"""
    if is_bazel_apple(d):
        return "bazel"
    if is_tuist(d):
        return "tuist"
    if is_xcodegen(d):
        return "xcodegen"
    if (Path(d) / "Cartfile").is_file() and has_xcode(d):
        return "carthage"
    return None


def msbuild_tag(text, key):
    """The text of the first <KEY>...</KEY> (MSBuild properties: no nesting)"""
    s = text.find(f"<{key}>")
    if s < 0:
        return None
    s += len(key) + 2
    e = text.find(f"</{key}>", s)
    if e < 0:
        return None
    return text[s:e].strip() or None


def targets_ios(text):
    for k in ("TargetFramework", "TargetFrameworks"):
        v = msbuild_tag(text, k)
        if v and any(f.strip().startswith("net") and "-ios" in f.strip() for f in v.split(";")):
            return True
    return False


def csproj(d):
    """The .csproj of a .NET for iOS app in D (one whose target frameworks include net*-ios)"""
    for p in _entries(d):
        if p.suffix == ".csproj" and targets_ios(_read(p) or ""):
            return p
    return None


def info_bundle_id(d):
    try:
        with open(Path(d) / "Info.plist", "rb") as f:
            return plistlib.load(f)["CFBundleIdentifier"]
    except Exception:
        return None


def dotnet_describe(d):
    p = csproj(d)
    text = _read(p) or ""
    name = msbuild_tag(text, "AssemblyName") or p.stem
    bundle = msbuild_tag(text, "ApplicationId") or info_bundle_id(d) or ""
    # bin/<Configuration>/<tfm>/iossimulator-arm64/<Name>.app, the newest
    apps = [t / "iossimulator-arm64" / f"{name}.app" for c in _entries(Path(d) / "bin") for t in _entries(c)]
    apps = [a for a in apps if a.is_dir()]
    return name, bundle, (max(apps, key=_mtime) if apps else None)


# --- kind and last build ------------------------------------------------------------------------------------------

def kind(d):
    """The project kind of D, or None"""
    d = Path(d)
    if (d / "xtool.yml").is_file() and (d / "Package.swift").exists():
        return "xtool"
    if (d / "pubspec.yaml").exists():
        return "flutter"
    k = shell_kind(d) or js_kind(d)
    if k:
        return k
    if rust_project(d):
        return "rust"
    k = gen_kind(d)
    if k:
        return k
    if csproj(d):
        return "dotnet"
    # before a bare Package.swift: libraries ship one next to the Xcode project of their demo app
    if has_xcode(d):
        return "xcodeproj"
    if (d / "Package.swift").exists():
        return "swiftpm"
    return None


def newest_app(products, suffix):
    """The newest .app in PRODUCTS/*SUFFIX/"""
    apps = [a for e in _entries(products) if e.name.endswith(suffix) for a in _entries(e) if a.suffix == ".app"]
    return max(apps, key=_mtime) if apps else None


def xcode_last_app(d):
    """The last simulator build of the Xcode project in D (derived data in D/build/x86sim)"""
    return newest_app(Path(d) / "build/x86sim/Build/Products", "simulator")


def pods_last_app(d):
    """The last simulator build of a React Native / Expo app (tools/xcbuild.py's derived data)"""
    return newest_app(Path(d) / "ios/build/xcbuild/Build/Products", "-iphonesimulator")


def shell_native_dir(d, k):
    """The Xcode project a shell / engine writes (where its .xcodeproj / .xcworkspace is)"""
    d = Path(d)
    if k == "godot":
        return d / "build/godot-ios"
    if k == "unity":
        return d / "build/unity-ios"
    if k in ("cordova", "nativescript"):
        return d / "platforms/ios"
    # capacitor.config.json's ios.path moves ios/ (capacitor.config.ts: the default)
    ios = "ios"
    try:
        cfg = json.loads(_read(d / "capacitor.config.json") or "")
        if isinstance(cfg.get("ios"), dict) and isinstance(cfg["ios"].get("path"), str):
            ios = cfg["ios"]["path"]
    except (ValueError, AttributeError):
        pass
    return d / ios / "App"


def shell_last_app(d, k):
    native = shell_native_dir(d, k)
    if k == "godot":
        # an iOS device build (converted for the simulator at install)
        products = native / "build/x86sim/Build/Products"
        return next((a for e in _entries(products) if e.name.endswith("-iphoneos") for a in _entries(e) if a.suffix == ".app"), None)
    return xcode_last_app(native)


def yml_value(text, key):
    for l in text.splitlines():
        if l.startswith(f"{key}:"):
            return l[len(key) + 1:].strip().strip('"').strip("'") or None
    return None


def env_value(text, key):
    """The value of KEY in an xtool.env (shell assignments: KEY=value, optionally quoted, # comments)"""
    v = None
    for l in text.splitlines():
        l = l.strip()
        l = l[len("export "):] if l.startswith("export ") else l
        if l.startswith(f"{key}="):
            v = l[len(key) + 1:]
    if v is None:
        return None
    return v.split(" #")[0].strip().strip('"').strip("'") or None


def describe(d):
    """{dir, kind, name, bundle_id, app} of the project in D; ValueError when it is none"""
    d = Path(os.path.realpath(d))
    k = kind(d)
    if k is None:
        raise ValueError(f"{d}: not an app project (no xtool.yml + Package.swift, pubspec.yaml, net*-ios .csproj, Cargo.toml, Cartfile, project.yml, Project.swift or .xcodeproj)")
    out = {"dir": str(d), "kind": k}
    if k == "rust":
        _, name, bundle, app = rust_project(d)
    elif k == "dotnet":
        name, bundle, app = dotnet_describe(d)
    else:
        y = _read(d / "xtool.yml") or ""
        name = yml_value(y, "product") or d.name
        bundle = yml_value(y, "bundleID") or ""
        if k in ("expo", "reactnative"):
            app = pods_last_app(d)
        elif k in XCODE:
            app = xcode_last_app(d)
        elif k in SHELLS:
            app = shell_last_app(d, k)
        else:
            app = next((a for a in _entries(d / "xtool") if a.suffix == ".app"), None)
    out.update(name=name, bundle_id=bundle, app=str(app) if app else None)
    return out
