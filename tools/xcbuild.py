#!/usr/bin/env python3
"""xcbuild.py: build an Xcode workspace or project on Linux, the way xcodebuild does, with the Swift toolchain's
clang and swiftc, the darwin SDK bundle's ld64.lld, and the Linux actool / ibtool.

Made for what CocoaPods generates (Pods.xcodeproj plus the app's project in an .xcworkspace: React Native, Expo,
Flutter plugins with a Podfile), so it covers what those use: static libraries, frameworks and resource bundles,
ObjC / ObjC++ / C / C++ / Swift sources (mixed in one target too), build settings from xcconfigs with
$(inherited), conditional settings and the usual modifiers, header maps, module maps, the Swift compatibility header,
shell script phases (run with the build settings in the environment, as Xcode does), vendored and prebuilt
xcframeworks (through CocoaPods' own copy scripts), resources, asset catalogs and storyboards, Info.plist.

    xcbuild.py -workspace App.xcworkspace -scheme App [-configuration Debug] [-sdk iphonesimulator]
               [-derivedDataPath DIR] [-jobs N] [SETTING=VALUE ...] [build | clean | -showBuildSettings]
    xcbuild.py -project App.xcodeproj -target App ...

It writes a ninja file (DIR/xcbuild/build.ninja) and runs ninja, so rebuilds only redo what changed. The last line
is `app: <path to the .app>` (or the product). SDKs: iphonesimulator (x86Sim), iphoneos (devices: sign the result
with tools/sign-dev.sh or ship.sh), and the tvOS, watchOS and visionOS ones. Default configuration: Debug.
"""
import hashlib
import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FORK = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from xcodeproj2xtool import parse_pbxproj  # noqa: E402  (the converter's pbxproj parser)


def die(msg):
    sys.stderr.write(f"xcbuild: error: {msg}\n")
    sys.exit(1)


def sdk_bundle():
    b = os.environ.get("DARWIN_SDK_BUNDLE")
    if b:
        return b
    for base in (os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), os.path.expanduser("~")):
        for sub in ("swiftpm/swift-sdks/darwin.artifactbundle", ".swiftpm/swift-sdks/darwin.artifactbundle"):
            p = os.path.join(base, sub)
            if os.path.isdir(p):
                return p
    die("no darwin SDK bundle (install-toolchain.sh registers it in ~/.config/swiftpm/swift-sdks)")


# sdk name -> (platform dir name, triple os, deployment target setting, family)
SDKS = {
    "iphonesimulator": ("iPhoneSimulator", "ios", "simulator", "IPHONEOS_DEPLOYMENT_TARGET"),
    "iphoneos": ("iPhoneOS", "ios", "", "IPHONEOS_DEPLOYMENT_TARGET"),
    "appletvsimulator": ("AppleTVSimulator", "tvos", "simulator", "TVOS_DEPLOYMENT_TARGET"),
    "appletvos": ("AppleTVOS", "tvos", "", "TVOS_DEPLOYMENT_TARGET"),
    "watchsimulator": ("WatchSimulator", "watchos", "simulator", "WATCHOS_DEPLOYMENT_TARGET"),
    "watchos": ("WatchOS", "watchos", "", "WATCHOS_DEPLOYMENT_TARGET"),
    "xrsimulator": ("XRSimulator", "xros", "simulator", "XROS_DEPLOYMENT_TARGET"),
    "xros": ("XROS", "xros", "", "XROS_DEPLOYMENT_TARGET"),
}
DEFAULT_DT = {"ios": "15.0", "tvos": "15.0", "watchos": "8.0", "xros": "1.0"}

PRODUCT_TYPES = {
    "com.apple.product-type.application": "app",
    "com.apple.product-type.framework": "framework",
    "com.apple.product-type.library.static": "static",
    "com.apple.product-type.library.dynamic": "dylib",
    "com.apple.product-type.bundle": "bundle",
    "com.apple.product-type.app-extension": "appex",
    "com.apple.product-type.tool": "tool",
}

SOURCE_LANG = {
    ".m": "objective-c", ".mm": "objective-c++", ".c": "c", ".cc": "c++", ".cpp": "c++", ".cxx": "c++",
    ".c++": "c++", ".s": "assembler", ".S": "assembler-with-cpp", ".swift": "swift", ".metal": "metal",
}

# ---------------------------------------------------------------------------------------------- settings


def c99ext(s):
    s = re.sub(r"[^A-Za-z0-9_]", "_", s)
    return "_" + s if s[:1].isdigit() else s


MODIFIERS = {
    "c99extidentifier": c99ext,
    "identifier": c99ext,
    "rfc1034identifier": lambda s: re.sub(r"[^A-Za-z0-9.-]", "-", s),
    "lower": str.lower,
    "upper": str.upper,
    "quote": lambda s: shlex.quote(s),
    "dir": lambda s: os.path.dirname(s) or ".",
    "file": os.path.basename,
    "base": lambda s: os.path.splitext(os.path.basename(s))[0],
    "suffix": lambda s: os.path.splitext(s)[1],
    "standardizepath": os.path.normpath,
    "absolutepath": os.path.abspath,
}

VAR = re.compile(r"\$\(([^()]*(?:\([^()]*\)[^()]*)*)\)|\$\{([^{}]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def cond_match(cond, ctx):
    """[sdk=iphonesimulator*][arch=arm64][config=Debug] against ctx"""
    import fnmatch

    for k, v in re.findall(r"\[(\w+)=([^\]]*)\]", cond):
        have = ctx.get(k)
        if have is None or not fnmatch.fnmatchcase(have, v):
            return False
    return True


def layer(d, ctx):
    """Settings dict with conditional keys folded in (a matching KEY[cond] wins over KEY)"""
    out = {}
    cond = []
    for k, v in d.items():
        if not isinstance(v, str):
            v = " ".join(x for x in v) if isinstance(v, list) else str(v)
        if "[" in k:
            base, c = k.split("[", 1)
            if cond_match("[" + c, ctx):
                cond.append((base.strip(), v))
        else:
            out[k.strip()] = v
    for k, v in cond:
        out[k] = v
    return out


class Settings:
    """Xcode's settings levels, lowest first; $(inherited) is the value one level down"""

    def __init__(self, layers):
        self.layers = layers
        self.cache = {}

    def raw(self, key, below=None):
        top = len(self.layers) if below is None else below
        for i in range(top - 1, -1, -1):
            if key in self.layers[i]:
                return self.layers[i][key], i
        return None, -1

    def get(self, key, below=None, _stack=()):
        ck = (key, below)
        if ck in self.cache:
            return self.cache[ck]
        if key in _stack:
            return ""
        v, lvl = self.raw(key, below)
        if v is None:
            r = os.environ.get(key, "") if key in ("HOME", "USER", "PATH", "TMPDIR") else ""
        else:
            r = self.expand(v, key, lvl, _stack + (key,))
        self.cache[ck] = r
        return r

    def expand(self, value, key=None, lvl=None, _stack=()):
        def sub(m):
            expr = m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3)
            parts = expr.split(":")
            name = self.expand(parts[0], key, lvl, _stack) if "$" in parts[0] else parts[0]
            if name == "inherited":
                val = self.get(key, lvl, _stack[:-1]) if key is not None and lvl is not None and lvl >= 0 else ""
            else:
                val = self.get(name, None, _stack)
            for mod in parts[1:]:
                if mod.startswith("default="):
                    if not val:
                        val = self.expand(mod[8:], key, lvl, _stack)
                elif mod in MODIFIERS:
                    val = MODIFIERS[mod](val)
            return val

        for _ in range(8):
            new = VAR.sub(sub, value)
            if new == value:
                break
            value = new
        return value

    def list(self, key):
        v = self.get(key).strip()
        if not v:
            return []
        try:
            return shlex.split(v)
        except ValueError:
            return v.split()

    def yes(self, key, default=False):
        v = self.get(key).strip().upper()
        return default if not v else v in ("YES", "TRUE", "1")

    def keys(self):
        ks = set()
        for l in self.layers:
            ks.update(l)
        return ks


def load_xcconfig(path, ctx, _seen=None):
    """(KEY, VALUE) assignments of an xcconfig in order (#include / #include? followed), conditional keys as written"""
    _seen = _seen or set()
    path = os.path.normpath(path)
    out = []
    if path in _seen or not os.path.isfile(path):
        return out
    _seen.add(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            m = re.match(r'#include\??\s+"([^"]+)"', line)
            if m:
                inc = m.group(1)
                inc = inc if os.path.isabs(inc) else os.path.join(os.path.dirname(path), inc)
                out += load_xcconfig(inc, ctx, _seen)
                continue
            if line.startswith("//") or line.startswith("#") or "=" not in line:
                continue
            # a // comment ends the line, except inside a quoted value or a URL's ://
            line = re.sub(r"(?<!:)//.*$", "", line)
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])*)\s*=\s*(.*)$", line)
            if m:
                out.append((m.group(1), m.group(2).rstrip(";").strip()))
    return out


def xcconfig_layers(assignments, ctx):
    """An xcconfig's assignments as settings levels: a key set again (or set for a matching condition) gets a new
    level, so its $(inherited) is the earlier assignment, as in Xcode"""
    layers = [{}]
    for k, v in assignments:
        base, _, cond = k.partition("[")
        if cond and not cond_match("[" + cond, ctx):
            continue
        if base in layers[-1]:
            layers.append({})
        layers[-1][base] = v
    return layers


# ---------------------------------------------------------------------------------------------- projects


class Project:
    def __init__(self, path):
        self.path = os.path.abspath(path.rstrip("/"))
        self.dir = os.path.dirname(self.path)
        self.name = os.path.splitext(os.path.basename(self.path))[0]
        data = parse_pbxproj(os.path.join(self.path, "project.pbxproj"))
        self.o = data["objects"]
        self.root = self.o[data["rootObject"]]
        self.parent = {}
        for k, v in self.o.items():
            for c in v.get("children", []) if isinstance(v, dict) else []:
                self.parent[c] = k
        self.src_root = os.path.normpath(os.path.join(self.dir, self.root.get("projectDirPath", "") or ""))
        self.targets = [Target(self, tid) for tid in self.root.get("targets", [])]

    def ref_path(self, rid, built_products=None, sdkroot=None):
        """A PBXFileReference / group's absolute path (None for an unknown sourceTree)"""
        r = self.o.get(rid, {})
        tree = r.get("sourceTree", "<group>")
        p = r.get("path", "")
        if tree == "<absolute>":
            return p
        if tree == "SOURCE_ROOT":
            return os.path.normpath(os.path.join(self.src_root, p))
        if tree == "BUILT_PRODUCTS_DIR":
            return os.path.join(built_products, p) if built_products else None
        if tree == "SDKROOT":
            return os.path.join(sdkroot, p) if sdkroot else None
        if tree == "DEVELOPER_DIR":
            return os.path.join(sdk_bundle(), "Developer", p)
        if tree == "<group>":
            par = self.parent.get(rid)
            if par is None or par == self.root.get("mainGroup"):
                base = self.src_root
                if par == self.root.get("mainGroup"):
                    mg = self.o[par]
                    base = os.path.normpath(os.path.join(self.src_root, mg.get("path", "") or ""))
            else:
                base = self.ref_path(par, built_products, sdkroot)
                if base is None:
                    return None
            return os.path.normpath(os.path.join(base, p)) if p else base
        # a setting name: resolved by the caller (rare in CocoaPods projects)
        return None

    def config(self, list_id, name):
        cl = self.o[list_id]
        for cid in cl.get("buildConfigurations", []):
            c = self.o[cid]
            if c.get("name") == name:
                return c
        default = cl.get("defaultConfigurationName")
        for cid in cl.get("buildConfigurations", []):
            if self.o[cid].get("name") == default:
                return self.o[cid]
        return self.o[cl["buildConfigurations"][0]]


class Target:
    def __init__(self, proj, tid):
        self.proj = proj
        self.id = tid
        self.t = proj.o[tid]
        self.name = self.t.get("name", tid)
        self.isa = self.t.get("isa")
        self.kind = PRODUCT_TYPES.get(self.t.get("productType", ""), "aggregate" if self.isa == "PBXAggregateTarget" else "other")
        self.deps = []  # Target objects
        self.s = None

    def __repr__(self):
        return f"<{self.proj.name}:{self.name}>"

    def phases(self):
        return [self.proj.o[p] for p in self.t.get("buildPhases", [])]


class Workspace:
    def __init__(self, ws=None, proj=None):
        self.projects = []
        if ws:
            ws = os.path.abspath(ws.rstrip("/"))
            text = open(os.path.join(ws, "contents.xcworkspacedata"), encoding="utf-8").read()
            for loc in re.findall(r'location\s*=\s*"([^"]+)"', text):
                kind, _, rel = loc.partition(":")
                base = os.path.dirname(ws) if kind in ("group", "container") else ""
                p = os.path.normpath(os.path.join(base, rel)) if kind != "absolute" else rel
                if p.endswith(".xcodeproj") and os.path.isdir(p):
                    self.projects.append(Project(p))
        if proj:
            self.projects.append(Project(proj))
        self.by_id = {}
        for p in self.projects:
            for t in p.targets:
                self.by_id[(p.path, t.id)] = t

    def all_targets(self):
        return [t for p in self.projects for t in p.targets]

    def find(self, name):
        hits = [t for t in self.all_targets() if t.name == name]
        if not hits:
            die(f"no target {name!r} (targets: {', '.join(sorted(t.name for t in self.all_targets() if t.kind == 'app')) or 'none'})")
        return hits[0]


# ---------------------------------------------------------------------------------------------- the build


class Build:
    def __init__(self, a):
        self.a = a
        self.sdk = a.sdk
        if self.sdk not in SDKS:
            die(f"unknown sdk {self.sdk} ({', '.join(SDKS)})")
        self.platform, self.os, self.env, self.dt_key = SDKS[self.sdk]
        self.bundle = sdk_bundle()
        self.platform_dir = os.path.join(self.bundle, "Developer/Platforms", self.platform + ".platform")
        self.sdkroot = os.path.join(self.platform_dir, "Developer/SDKs", self.platform + ".sdk")
        if not os.path.isdir(self.sdkroot):
            die(f"the darwin SDK has no {self.platform} SDK ({self.sdkroot})")
        try:
            self.sdk_version = json.load(open(os.path.join(self.sdkroot, "SDKSettings.json")))["Version"]
        except (OSError, KeyError, ValueError):
            self.sdk_version = "27.0"
        self.toolchain = os.path.join(self.bundle, "Developer/Toolchains/XcodeDefault.xctoolchain")
        swift = shutil.which("swift") or "/usr/bin/swift"
        self.tc = os.path.dirname(os.path.realpath(swift))
        self.clang = os.path.join(self.tc, "clang")
        self.swiftc = os.path.join(self.tc, "swiftc")
        self.ld = os.path.join(self.bundle, "toolset/bin/ld64.lld")
        self.ar = shutil.which("llvm-ar", path=self.tc) or shutil.which("llvm-ar") or "ar"
        self.dd = os.path.abspath(a.derivedDataPath)
        self.cfg = a.configuration
        self.arch = "arm64"
        self.shims = [os.path.join(FORK, "cocoapods/shims"), os.path.join(FORK, "flutter/shims"),
                      os.path.join(self.platform_dir, "Developer/usr/bin")]
        self.ws = Workspace(a.workspace, a.project) if (a.workspace or a.project) else None
        if self.ws is None:
            return
        self.overrides = dict(kv.split("=", 1) for kv in a.settings)
        # one build location for every project, as Xcode's workspace builds (CocoaPods sets SYMROOT in Pods.xcodeproj)
        self.overrides.setdefault("SYMROOT", os.path.join(self.dd, "Build/Products"))
        self.overrides.setdefault("OBJROOT", os.path.join(self.dd, "Build/Intermediates.noindex"))
        # projects name the SDK (SDKROOT = iphoneos); the build uses the one -sdk picked, by its path
        self.overrides["SDKROOT"] = self.sdkroot
        self.ctx = {"sdk": self.sdk + self.sdk_version, "arch": self.arch, "config": self.cfg, "variant": "normal"}
        self.product_owner = {}
        for t in self.ws.all_targets():
            t.s = self.settings_for(t)
            if t.kind not in ("aggregate", "other"):
                self.product_owner[t.s.get("FULL_PRODUCT_NAME")] = t
        for t in self.ws.all_targets():
            self.link_deps(t)

    def toolchain_include(self):
        """<swift/bridging> (C++ interop annotations): Xcode's clang finds it in its toolchain's usr/include, the Linux
        clang does not; a directory with just that, for -isystem"""
        d = os.path.join(self.dd, "xcbuild", "toolchain-include")
        src = os.path.normpath(os.path.join(self.tc, "../include/swift"))
        if os.path.isdir(src) and not os.path.exists(os.path.join(d, "swift", "bridging")):
            os.makedirs(os.path.join(d, "swift"), exist_ok=True)
            for n in ("bridging", "bridging.modulemap"):
                if os.path.exists(os.path.join(src, n)):
                    os.symlink(os.path.join(src, n), os.path.join(d, "swift", n))
        return d

    # --- settings

    def defaults(self, t):
        p = t.proj
        d = {
            "ACTION": "build", "ARCHS": self.arch, "ARCHS_STANDARD": self.arch, "CURRENT_ARCH": self.arch,
            "NATIVE_ARCH": self.arch, "NATIVE_ARCH_ACTUAL": "x86_64", "arch": self.arch, "VALID_ARCHS": "arm64 arm64e x86_64",
            "ONLY_ACTIVE_ARCH": "YES", "CONFIGURATION": self.cfg, "PLATFORM_NAME": self.sdk,
            "EFFECTIVE_PLATFORM_NAME": "-" + self.sdk, "SDK_NAME": self.sdk + self.sdk_version,
            "SDKROOT": self.sdkroot, "SDK_DIR": self.sdkroot, "SDK_VERSION": self.sdk_version,
            "SDK_VERSION_MAJOR": self.sdk_version.split(".")[0], "SDK_NAMES": self.sdk + self.sdk_version,
            "PLATFORM_DIR": self.platform_dir, "PLATFORM_DEVELOPER_DIR": os.path.join(self.platform_dir, "Developer"),
            "PLATFORM_DISPLAY_NAME": {"iphonesimulator": "iOS Simulator", "iphoneos": "iOS"}.get(self.sdk, self.platform),
            "PLATFORM_FAMILY_NAME": self.os, "DEVELOPER_DIR": os.path.join(self.bundle, "Developer"),
            "TOOLCHAIN_DIR": self.toolchain, "DT_TOOLCHAIN_DIR": self.toolchain, "TOOLCHAINS": "com.apple.dt.toolchain.XcodeDefault",
            "SWIFT_PLATFORM_TARGET_PREFIX": self.os, "LLVM_TARGET_TRIPLE_SUFFIX": "-" + self.env if self.env else "",
            "LLVM_TARGET_TRIPLE_OS_VERSION": f"{self.os}$({self.dt_key})", "DEPLOYMENT_TARGET_SETTING_NAME": self.dt_key,
            self.dt_key: DEFAULT_DT[self.os], "PROJECT_DIR": p.src_root, "SRCROOT": p.src_root, "SOURCE_ROOT": p.src_root,
            "PROJECT_NAME": p.name, "PROJECT": p.name, "PROJECT_FILE_PATH": p.path, "TARGET_NAME": t.name,
            "TARGETNAME": t.name, "PRODUCT_NAME": "$(TARGET_NAME)", "PRODUCT_MODULE_NAME": "$(PRODUCT_NAME:c99extidentifier)",
            "SWIFT_MODULE_NAME": "$(PRODUCT_MODULE_NAME)", "SYMROOT": os.path.join(self.dd, "Build/Products"),
            "BUILD_DIR": "$(SYMROOT)", "BUILD_ROOT": "$(SYMROOT)", "OBJROOT": os.path.join(self.dd, "Build/Intermediates.noindex"),
            "PROJECT_TEMP_ROOT": "$(OBJROOT)", "PROJECT_TEMP_DIR": "$(OBJROOT)/$(PROJECT_NAME).build",
            "CONFIGURATION_BUILD_DIR": "$(BUILD_DIR)/$(CONFIGURATION)$(EFFECTIVE_PLATFORM_NAME)",
            "BUILT_PRODUCTS_DIR": "$(CONFIGURATION_BUILD_DIR)", "TARGET_BUILD_DIR": "$(CONFIGURATION_BUILD_DIR)",
            "CONFIGURATION_TEMP_DIR": "$(PROJECT_TEMP_DIR)/$(CONFIGURATION)$(EFFECTIVE_PLATFORM_NAME)",
            "TARGET_TEMP_DIR": "$(CONFIGURATION_TEMP_DIR)/$(TARGET_NAME).build", "TEMP_DIR": "$(TARGET_TEMP_DIR)",
            "TEMP_FILES_DIR": "$(TARGET_TEMP_DIR)", "TEMP_FILE_DIR": "$(TARGET_TEMP_DIR)",
            "DERIVED_FILE_DIR": "$(TARGET_TEMP_DIR)/DerivedSources", "DERIVED_FILES_DIR": "$(DERIVED_FILE_DIR)",
            "DERIVED_SOURCES_DIR": "$(DERIVED_FILE_DIR)", "OBJECT_FILE_DIR": "$(TARGET_TEMP_DIR)/Objects",
            "OBJECT_FILE_DIR_normal": "$(OBJECT_FILE_DIR)-normal", "MODULE_CACHE_DIR": os.path.join(self.dd, "ModuleCache.noindex"),
            "SHARED_DERIVED_FILE_DIR": "$(BUILT_PRODUCTS_DIR)/DerivedSources", "DWARF_DSYM_FOLDER_PATH": "$(CONFIGURATION_BUILD_DIR)",
            "DWARF_DSYM_FILE_NAME": "$(FULL_PRODUCT_NAME).dSYM", "SWIFT_OBJC_INTERFACE_HEADER_NAME": "$(SWIFT_MODULE_NAME)-Swift.h",
            "OTHER_CPLUSPLUSFLAGS": "$(OTHER_CFLAGS)", "USE_HEADERMAP": "YES", "CLANG_CXX_LIBRARY": "libc++",
            "ENABLE_BITCODE": "NO", "TARGETED_DEVICE_FAMILY": "1", "CODE_SIGNING_ALLOWED": "NO" if self.env else "YES",
            "CODE_SIGNING_REQUIRED": "NO", "CODE_SIGN_IDENTITY": "", "EXPANDED_CODE_SIGN_IDENTITY": "",
            "INSTALL_PATH": "", "SKIP_INSTALL": "NO", "PODS_PARALLEL_CODE_SIGN": "NO", "DEBUG_INFORMATION_FORMAT": "dwarf",
            "GCC_GENERATE_DEBUGGING_SYMBOLS": "YES", "XCODE_VERSION_MAJOR": "2700", "XCODE_VERSION_ACTUAL": "2700",
            "XCODE_PRODUCT_BUILD_VERSION": "27A0", "MAC_OS_X_VERSION_MAJOR": "260000", "USER": os.environ.get("USER", "user"),
            "HOME": os.environ.get("HOME", "/"), "SWIFT_RESPONSE_FILE_PATH_normal_arm64": "",
            "CORRESPONDING_SIMULATOR_SDK_NAME": "", "BUILD_STYLE": self.cfg, "SCRIPT_OUTPUT_STREAM_FILE": "/dev/stdout",
            "INFOPLIST_OUTPUT_FORMAT": "binary", "PLIST_FILE_OUTPUT_FORMAT": "binary", "BUNDLE_FORMAT": "shallow",
            "SHALLOW_BUNDLE": "YES", "DEVELOPMENT_LANGUAGE": "en",
            "PRODUCT_BUNDLE_PACKAGE_TYPE": {"app": "APPL", "appex": "XPC!", "framework": "FMWK"}.get(t.kind, "BNDL"), "TARGET_DEVICE_OS_VERSION": "", "ENABLE_PREVIEWS": "NO", "ENABLE_USER_SCRIPT_SANDBOXING": "NO",
            "VALIDATE_PRODUCT": "NO", "STRIP_INSTALLED_PRODUCT": "NO", "DEPLOYMENT_POSTPROCESSING": "NO", "COPY_PHASE_STRIP": "NO",
            "LOCALIZED_RESOURCES_FOLDER_PATH": "$(UNLOCALIZED_RESOURCES_FOLDER_PATH)/Base.lproj", "JAVA_FOLDER_PATH": "",
        }
        k = t.kind
        if k in ("app", "appex"):
            ext = "app" if k == "app" else "appex"
            d.update({"WRAPPER_EXTENSION": ext, "WRAPPER_SUFFIX": "." + ext, "WRAPPER_NAME": "$(PRODUCT_NAME).$(WRAPPER_EXTENSION)",
                      "FULL_PRODUCT_NAME": "$(WRAPPER_NAME)", "CONTENTS_FOLDER_PATH": "$(WRAPPER_NAME)",
                      "EXECUTABLE_FOLDER_PATH": "$(WRAPPER_NAME)", "EXECUTABLE_NAME": "$(PRODUCT_NAME)",
                      "EXECUTABLE_PATH": "$(EXECUTABLE_FOLDER_PATH)/$(EXECUTABLE_NAME)", "UNLOCALIZED_RESOURCES_FOLDER_PATH": "$(WRAPPER_NAME)",
                      "FRAMEWORKS_FOLDER_PATH": "$(WRAPPER_NAME)/Frameworks", "PLUGINS_FOLDER_PATH": "$(WRAPPER_NAME)/PlugIns",
                      "INFOPLIST_PATH": "$(WRAPPER_NAME)/Info.plist", "PKGINFO_PATH": "$(WRAPPER_NAME)/PkgInfo", "MACH_O_TYPE": "mh_execute",
                      "PRODUCT_TYPE": t.t.get("productType", ""), "SHARED_FRAMEWORKS_FOLDER_PATH": "$(WRAPPER_NAME)/SharedFrameworks"})
        elif k == "framework":
            d.update({"WRAPPER_EXTENSION": "framework", "WRAPPER_NAME": "$(PRODUCT_NAME).framework", "FULL_PRODUCT_NAME": "$(WRAPPER_NAME)",
                      "CONTENTS_FOLDER_PATH": "$(WRAPPER_NAME)", "EXECUTABLE_FOLDER_PATH": "$(WRAPPER_NAME)",
                      "EXECUTABLE_NAME": "$(PRODUCT_NAME)", "EXECUTABLE_PATH": "$(EXECUTABLE_FOLDER_PATH)/$(EXECUTABLE_NAME)",
                      "PUBLIC_HEADERS_FOLDER_PATH": "$(WRAPPER_NAME)/Headers", "PRIVATE_HEADERS_FOLDER_PATH": "$(WRAPPER_NAME)/PrivateHeaders",
                      "MODULES_FOLDER_PATH": "$(WRAPPER_NAME)/Modules", "UNLOCALIZED_RESOURCES_FOLDER_PATH": "$(WRAPPER_NAME)",
                      "INFOPLIST_PATH": "$(WRAPPER_NAME)/Info.plist", "MACH_O_TYPE": "mh_dylib", "DYLIB_INSTALL_NAME_BASE": "@rpath",
                      "LD_DYLIB_INSTALL_NAME": "$(DYLIB_INSTALL_NAME_BASE:standardizepath)/$(EXECUTABLE_PATH)", "DEFINES_MODULE": "NO",
                      "FRAMEWORKS_FOLDER_PATH": "$(WRAPPER_NAME)/Frameworks"})
        elif k in ("static", "dylib"):
            suf = ".a" if k == "static" else ".dylib"
            d.update({"EXECUTABLE_PREFIX": "lib", "EXECUTABLE_SUFFIX": suf, "EXECUTABLE_NAME": "lib$(PRODUCT_NAME)" + suf,
                      "FULL_PRODUCT_NAME": "$(EXECUTABLE_NAME)", "EXECUTABLE_PATH": "$(EXECUTABLE_NAME)",
                      "PUBLIC_HEADERS_FOLDER_PATH": "/usr/local/include", "PRIVATE_HEADERS_FOLDER_PATH": "/usr/local/include",
                      "MACH_O_TYPE": "staticlib" if k == "static" else "mh_dylib", "LD_DYLIB_INSTALL_NAME": "@rpath/$(EXECUTABLE_PATH)"})
        elif k == "bundle":
            d.update({"WRAPPER_EXTENSION": "bundle", "WRAPPER_NAME": "$(PRODUCT_NAME).bundle", "FULL_PRODUCT_NAME": "$(WRAPPER_NAME)",
                      "CONTENTS_FOLDER_PATH": "$(WRAPPER_NAME)", "UNLOCALIZED_RESOURCES_FOLDER_PATH": "$(WRAPPER_NAME)",
                      "EXECUTABLE_FOLDER_PATH": "$(WRAPPER_NAME)", "EXECUTABLE_NAME": "$(PRODUCT_NAME)",
                      "INFOPLIST_PATH": "$(WRAPPER_NAME)/Info.plist", "MACH_O_TYPE": "mh_bundle"})
        return d

    def settings_for(self, t):
        p = t.proj
        layers = [self.defaults(t)]
        pc = p.config(p.root["buildConfigurationList"], self.cfg)
        tc = p.config(t.t["buildConfigurationList"], self.cfg)
        for c in (pc, tc):
            base = c.get("baseConfigurationReference")
            if base:
                path = p.ref_path(base)
                layers += xcconfig_layers(load_xcconfig(path, self.ctx), self.ctx) if path else [{}]
            layers.append(layer(c.get("buildSettings", {}), self.ctx))
        layers.append(dict(self.overrides))
        return Settings(layers)

    # --- dependencies

    def link_deps(self, t):
        deps = []
        for did in t.t.get("dependencies", []):
            d = t.proj.o.get(did, {})
            tid = d.get("target")
            if tid and (t.proj.path, tid) in self.ws.by_id:
                deps.append(self.ws.by_id[(t.proj.path, tid)])
                continue
            proxy = t.proj.o.get(d.get("targetProxy", ""), {})
            remote = proxy.get("remoteGlobalIDString")
            portal = t.proj.o.get(proxy.get("containerPortal", ""), {})
            if remote and portal.get("isa") == "PBXFileReference":
                pp = t.proj.ref_path(proxy["containerPortal"])
                key = (os.path.abspath(pp), remote) if pp else None
                if key in self.ws.by_id:
                    deps.append(self.ws.by_id[key])
            elif remote and (t.proj.path, remote) in self.ws.by_id:
                deps.append(self.ws.by_id[(t.proj.path, remote)])
            elif d.get("name"):
                hit = [x for x in self.ws.all_targets() if x.name == d["name"]]
                deps.extend(hit[:1])
        # implicit: built products in the Frameworks phase (libPods-App.a, a framework another target makes)
        for ph in t.phases():
            if ph.get("isa") != "PBXFrameworksBuildPhase":
                continue
            for bf in ph.get("files", []):
                ref = t.proj.o.get(t.proj.o.get(bf, {}).get("fileRef", ""), {})
                name = os.path.basename(ref.get("path", ""))
                owner = self.product_owner.get(name)
                if owner and owner is not t and owner not in deps:
                    deps.append(owner)
        t.deps = deps

    def closure(self, root):
        order, seen = [], set()

        def visit(t, stack=()):
            if id(t) in seen:
                return
            seen.add(id(t))
            for d in t.deps:
                if d not in stack:
                    visit(d, stack + (t,))
            order.append(t)

        visit(root)
        return order

    # --- files of a target

    def phase_files(self, t, ph):
        """(absolute path, build file settings, file ref, lproj) for each file of a phase; variant groups expanded
        (lproj: the localization a variant group's child goes to, '' for the rest)"""
        p = t.proj
        bp = t.s.get("BUILT_PRODUCTS_DIR")
        out = []
        for bf in ph.get("files", []):
            b = p.o.get(bf, {})
            rid = b.get("fileRef") or b.get("productRef")
            ref = p.o.get(rid, {})
            if ref.get("isa") == "PBXVariantGroup":
                for c in ref.get("children", []):
                    path = p.ref_path(c, bp, self.sdkroot)
                    m = re.search(r"([^/]+)\.lproj/[^/]+$", path or "")
                    if path:
                        out.append((path, b.get("settings", {}), p.o[c], m.group(1) if m else p.o[c].get("name", "")))
                continue
            if ref.get("isa") == "PBXReferenceProxy":
                rp = os.path.join(bp, ref.get("path", ""))
                out.append((rp, b.get("settings", {}), ref, ""))
                continue
            path = p.ref_path(rid, bp, self.sdkroot)
            if path:
                out.append((path, b.get("settings", {}), ref, ""))
        return out

    # --- flags

    def search(self, s, key, flag):
        out = []
        for v in s.list(key):
            rec = v.endswith("/**")
            v = v[:-3] if rec else v
            if not v:
                continue
            if not os.path.isabs(v):
                v = os.path.join(s.get("SRCROOT"), v)
            out += [flag, v]
            if rec and os.path.isdir(v):
                for root, dirs, _ in os.walk(v):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and not d.endswith((".xcassets", ".lproj"))]
                    for d in dirs:
                        out += [flag, os.path.join(root, d)]
        return out

    def triple(self, s):
        dt = s.get(self.dt_key) or DEFAULT_DT[self.os]
        return f"{self.arch}-apple-{self.os}{dt}" + (f"-{self.env}" if self.env else "")

    def clang_flags(self, t, lang, hmaps):
        s = t.s
        f = ["-x", lang, "-target", self.triple(s), "-isysroot", self.sdkroot, "-fmessage-length=0",
             "-fdiagnostics-show-note-include-stack", "-fmacro-backtrace-limit=0", "-Wno-error"]
        objc = lang.startswith("objective-c")
        cxx = lang.endswith("++")
        # CLANG_ENABLE_MODULES is "Enable Modules (C and Objective-C)": C++ and Objective-C++ include headers textually
        if s.yes("CLANG_ENABLE_MODULES") and lang in ("c", "objective-c"):
            f += ["-fmodules", "-fmodules-cache-path=" + s.get("MODULE_CACHE_DIR"),
                  "-fbuild-session-file=" + os.path.join(self.dd, "xcbuild/session"), "-fmodules-validate-once-per-build-session"]
        if objc and s.yes("CLANG_ENABLE_OBJC_ARC"):
            f.append("-fobjc-arc")
        if objc and s.yes("CLANG_ENABLE_OBJC_WEAK"):
            f.append("-fobjc-weak")
        if cxx:
            std = s.get("CLANG_CXX_LANGUAGE_STANDARD")
            if std and std != "compiler-default":
                f.append("-std=" + std.replace("c++0x", "c++11").replace("gnu++0x", "gnu++11"))
            lib = s.get("CLANG_CXX_LIBRARY") or "libc++"
            f.append("-stdlib=" + lib)
        elif lang in ("c", "objective-c"):
            std = s.get("GCC_C_LANGUAGE_STANDARD")
            if std and std != "compiler-default":
                f.append("-std=" + std.replace("ansi", "c89"))
        opt = s.get("GCC_OPTIMIZATION_LEVEL") or ("0" if self.cfg.lower().startswith("debug") else "s")
        f.append("-O" + opt)
        if s.yes("GCC_GENERATE_DEBUGGING_SYMBOLS", True) and opt == "0":
            f.append("-g")
        if s.yes("GCC_NO_COMMON_BLOCKS"):
            f.append("-fno-common")
        if not s.yes("GCC_ENABLE_CPP_EXCEPTIONS", True) and cxx:
            f.append("-fno-exceptions")
        if not s.yes("GCC_ENABLE_CPP_RTTI", True) and cxx:
            f.append("-fno-rtti")
        if s.yes("GCC_SYMBOLS_PRIVATE_EXTERN"):
            f.append("-fvisibility=hidden")
        if s.yes("GCC_INLINES_ARE_PRIVATE_EXTERN") and cxx:
            f.append("-fvisibility-inlines-hidden")
        if s.yes("APPLICATION_EXTENSION_API_ONLY"):
            f.append("-fapplication-extension")
        for d in s.list("GCC_PREPROCESSOR_DEFINITIONS") + s.list("GCC_PREPROCESSOR_DEFINITIONS_NOT_USED_IN_PRECOMPS"):
            f.append("-D" + d)
        if s.get("PRODUCT_MODULE_NAME") and lang != "assembler":
            f.append("-fmodule-name=" + s.get("PRODUCT_MODULE_NAME"))
        f += hmaps
        f += ["-I", s.get("BUILT_PRODUCTS_DIR") + "/include"]
        if cxx:
            f += ["-isystem", self.toolchain_include()]
        f += self.search(s, "SYSTEM_HEADER_SEARCH_PATHS", "-isystem")
        f += self.search(s, "HEADER_SEARCH_PATHS", "-I")
        f += self.search(s, "USER_HEADER_SEARCH_PATHS", "-iquote")
        f += ["-I", s.get("DERIVED_FILE_DIR") + "/" + self.arch, "-I", s.get("DERIVED_FILE_DIR")]
        f += ["-F", s.get("BUILT_PRODUCTS_DIR")]
        f += self.search(s, "SYSTEM_FRAMEWORK_SEARCH_PATHS", "-iframework")
        f += self.search(s, "FRAMEWORK_SEARCH_PATHS", "-F")
        pch = s.get("GCC_PREFIX_HEADER")
        if pch and lang != "assembler":
            pch = pch if os.path.isabs(pch) else os.path.join(s.get("SRCROOT"), pch)
            f += ["-include", pch]
        f += s.list("WARNING_CFLAGS")
        f += s.list("OTHER_CPLUSPLUSFLAGS" if cxx else "OTHER_CFLAGS")
        if "-fmodules" not in f:
            # Apple's clang ignores -fmodule-map-file when modules are off; clang 21 then wants every header of
            # that map as a prebuilt module ("is needed but has not been provided")
            f = [x for x in f if not x.startswith("-fmodule-map-file=")]
        return f

    def swift_plugin(self, path):
        """A macro plugin executable built for macOS (CocoaPods takes the npm package's universal binary) -> the
        package's Linux build next to it (@scope/<name>-linux-<arch>/<binary>)"""
        if not os.path.isfile(path):
            return path
        with open(path, "rb") as f:
            magic = f.read(4)
        if magic == b"\x7fELF":
            return path
        arch = {"x86_64": "x64", "aarch64": "arm64"}.get(os.uname().machine, os.uname().machine)
        d = os.path.dirname(path)
        while d and os.path.basename(os.path.dirname(d)) != "node_modules" and d != "/":
            d = os.path.dirname(d)
        nm = os.path.dirname(d)
        name = os.path.basename(path)
        for cand in sorted(__import__("glob").glob(os.path.join(nm, "@*", f"*-linux-{arch}", name))):
            if os.access(cand, os.X_OK):
                return cand
        return path

    def swift_flags(self, t, hmaps, has_objc_module):
        s = t.s
        f = ["-target", self.triple(s), "-sdk", self.sdkroot, "-resource-dir", os.path.join(self.toolchain, "usr/lib/swift"),
             "-module-name", s.get("SWIFT_MODULE_NAME"),
             "-module-cache-path", s.get("MODULE_CACHE_DIR"), "-Xfrontend", "-enable-cross-import-overlays",
             "-Xfrontend", "-disable-autolink-framework", "-Xfrontend", "XCTest"]
        ver = s.get("SWIFT_VERSION") or "5"
        f += ["-swift-version", ver.split(".")[0] if ver.split(".")[0] in ("4", "5", "6") else "5"]
        opt = s.get("SWIFT_OPTIMIZATION_LEVEL") or ("-Onone" if self.cfg.lower().startswith("debug") else "-O")
        f.append(opt)
        if opt == "-Onone" and s.yes("GCC_GENERATE_DEBUGGING_SYMBOLS", True):
            f.append("-g")
        for c in s.list("SWIFT_ACTIVE_COMPILATION_CONDITIONS"):
            f += ["-D", c]
        if s.yes("APPLICATION_EXTENSION_API_ONLY"):
            f.append("-application-extension")
        if s.get("SWIFT_STRICT_CONCURRENCY") in ("complete", "targeted"):
            f += ["-strict-concurrency=" + s.get("SWIFT_STRICT_CONCURRENCY")]
        if s.yes("SWIFT_ENABLE_BARE_SLASH_REGEX"):
            f += ["-enable-bare-slash-regex"]
        for feat in s.list("SWIFT_UPCOMING_FEATURE_FLAGS"):
            f += ["-enable-upcoming-feature", feat]
        f += ["-I", s.get("BUILT_PRODUCTS_DIR")]
        f += self.search(s, "SWIFT_INCLUDE_PATHS", "-I")
        f += ["-F", s.get("BUILT_PRODUCTS_DIR")]
        f += self.search(s, "FRAMEWORK_SEARCH_PATHS", "-F")
        f += self.search(s, "SYSTEM_FRAMEWORK_SEARCH_PATHS", "-Fsystem")
        for x in hmaps:
            f += ["-Xcc", x]
        f += ["-Xcc", "-I", "-Xcc", s.get("BUILT_PRODUCTS_DIR") + "/include", "-Xcc", "-isystem", "-Xcc", self.toolchain_include()]
        for flag, key in (("-I", "HEADER_SEARCH_PATHS"), ("-iquote", "USER_HEADER_SEARCH_PATHS"), ("-isystem", "SYSTEM_HEADER_SEARCH_PATHS")):
            sp = self.search(s, key, flag)
            for i in range(0, len(sp), 2):
                f += ["-Xcc", sp[i], "-Xcc", sp[i + 1]]
        f += ["-Xcc", "-I", "-Xcc", s.get("DERIVED_FILE_DIR")]
        for d in s.list("GCC_PREPROCESSOR_DEFINITIONS"):
            f += ["-Xcc", "-D" + d]
        if has_objc_module:
            f += ["-import-underlying-module", "-Xcc", "-fmodule-map-file=" + has_objc_module]
        bh = s.get("SWIFT_OBJC_BRIDGING_HEADER")
        if bh:
            f += ["-import-objc-header", bh if os.path.isabs(bh) else os.path.join(s.get("SRCROOT"), bh)]
        other = s.list("OTHER_SWIFT_FLAGS")
        i = 0
        while i < len(other):
            x = other[i]
            if x in ("-load-plugin-executable",) and i + 1 < len(other):
                path, _, mod = other[i + 1].partition("#")
                f += [x, self.swift_plugin(path) + ("#" + mod if mod else "")]
                i += 2
                continue
            f.append(x)
            i += 1
        return f

    def link_flags(self, t, s):
        f = ["-target", self.triple(s), "-isysroot", self.sdkroot, "-fuse-ld=" + self.ld, "-mlinker-version=1200",
             "-L" + s.get("BUILT_PRODUCTS_DIR"), "-F" + s.get("BUILT_PRODUCTS_DIR")]
        f += [x for p in self.search(s, "LIBRARY_SEARCH_PATHS", "-L")[1::2] for x in ("-L" + p,)]
        f += [x for p in self.search(s, "FRAMEWORK_SEARCH_PATHS", "-F")[1::2] for x in ("-F" + p,)]
        # the Swift runtime: the SDK's /usr/lib/swift and the toolchain's compatibility libraries
        f += ["-L" + os.path.join(self.sdkroot, "usr/lib/swift"), "-L" + os.path.join(self.toolchain, "usr/lib/swift", self.sdk)]
        for r in s.list("LD_RUNPATH_SEARCH_PATHS"):
            f += ["-Xlinker", "-rpath", "-Xlinker", r]
        if s.yes("DEAD_CODE_STRIPPING"):
            f += ["-Xlinker", "-dead_strip"]
        if s.yes("APPLICATION_EXTENSION_API_ONLY"):
            f.append("-fapplication-extension")
        f += ["-fobjc-link-runtime"]
        # compiler-rt's builtins (__isPlatformVersionAtLeast for @available): Apple's clang links them by itself
        import glob

        rt = sorted(glob.glob(os.path.join(self.toolchain, "usr/lib/clang/*/lib/darwin", f"libclang_rt.{self.os}{'sim' if self.env else ''}.a")))
        if rt:
            f.append(rt[-1])
        other = s.list("OTHER_LDFLAGS")
        f += other
        return f


# ---------------------------------------------------------------------------------------------- header maps


def write_hmap(path, entries):
    """Clang header map: name -> (prefix, suffix). Format: clang/lib/Lex/HeaderMap.cpp"""
    import struct

    n = 1
    while n < max(len(entries), 1) * 2:
        n <<= 1
    strings = bytearray(b"\0")
    index = {}

    def s(x):
        if x not in index:
            index[x] = len(strings)
            strings.extend(x.encode() + b"\0")
        return index[x]

    buckets = [(0, 0, 0)] * n
    maxlen = 0
    for key, (prefix, suffix) in sorted(entries.items()):
        h = sum(ord(c.lower()) * 13 for c in key) & (n - 1)
        while buckets[h][0]:
            h = (h + 1) & (n - 1)
        buckets[h] = (s(key), s(prefix), s(suffix))
        maxlen = max(maxlen, len(prefix) + len(suffix))
    header = 24
    off = header + 12 * n
    data = struct.pack("<4sHHIIII", b"pamh", 1, 0, off, len(entries), n, maxlen)
    data += b"".join(struct.pack("<III", *b) for b in buckets)
    data += bytes(strings)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    if not (os.path.exists(path) and open(path, "rb").read() == data):
        os.replace(tmp, path)
    else:
        os.remove(tmp)


HEADER_EXTS = (".h", ".hh", ".hpp", ".hxx", ".pch", ".inc", ".ipp", ".tcc")


# ---------------------------------------------------------------------------------------------- ninja


def nesc(p):
    return p.replace("$", "$$").replace(" ", "$ ").replace(":", "$:")


def sq(args):
    return " ".join(shlex.quote(a) for a in args)


class Gen:
    def __init__(self, b, root):
        self.b = b
        self.root = root
        self.out = os.path.join(b.dd, "xcbuild")
        os.makedirs(self.out, exist_ok=True)
        self.lines = []
        self.steps = 0
        self.done = {}  # target -> its final stamp
        self.products = set()  # files a rule makes

    def step(self, t, kind, data):
        self.steps += 1
        p = os.path.join(self.out, "steps", f"{self.steps:04d}-{kind}-{c99ext(t.name)}.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        data = dict(data, kind=kind, target=t.name)
        text = json.dumps(data, indent=1, sort_keys=True)
        if not (os.path.exists(p) and open(p).read() == text):
            with open(p, "w") as f:
                f.write(text)
        return p

    def env_file(self, t):
        """The target's build settings as `export K=V` lines, for its script phases"""
        s = t.s
        b = self.b
        env = {}
        for k in sorted(s.keys()):
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
                env[k] = s.get(k)
        for k in ("PATH",):
            env.pop(k, None)
        env.update({
            "PATH": os.pathsep.join(b.shims + [b.tc, os.environ.get("PATH", "/usr/bin:/bin")]),
            "NODE_OPTIONS": f'--require "{os.path.join(FORK, "cocoapods/node-linux.js")}"'
                            + (" " + os.environ["NODE_OPTIONS"] if os.environ.get("NODE_OPTIONS") else ""),
            "RUBYOPT": "-r" + os.path.join(FORK, "cocoapods/linux.rb"),
            "DARWIN_SDK_BUNDLE": b.bundle, "LANG": os.environ.get("LANG", "C.UTF-8"),
        })
        for k in ("HOME", "USER", "TERM", "TMPDIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "OAD_DIR"):
            if os.environ.get(k) and k not in ("HOME", "USER"):
                env[k] = os.environ[k]
        p = os.path.join(s.get("TARGET_TEMP_DIR"), "xcbuild-env.sh")
        text = "".join(f"export {k}={shlex.quote(v)}\n" for k, v in env.items())
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if not (os.path.exists(p) and open(p).read() == text):
            with open(p, "w") as f:
                f.write(text)
        return p

    def hmaps(self, t):
        """Xcode's header maps: the target's own headers (-iquote) and every target's headers in the project (-I)"""
        s = t.s
        if not s.yes("USE_HEADERMAP", True):
            return []
        own = {}
        for ph in t.phases():
            if ph.get("isa") in ("PBXHeadersBuildPhase", "PBXSourcesBuildPhase"):
                for path, _, _, _ in self.b.phase_files(t, ph):
                    if path.endswith(HEADER_EXTS):
                        own[os.path.basename(path)] = (os.path.dirname(path) + "/", os.path.basename(path))
        # headers of the target's group folders that no phase lists (CocoaPods puts private headers in no phase)
        allh = {}
        for o in t.proj.targets:
            for ph in o.phases():
                if ph.get("isa") == "PBXHeadersBuildPhase":
                    mod = o.s.get("PRODUCT_MODULE_NAME")
                    for path, _, _, _ in self.b.phase_files(o, ph):
                        if path.endswith(HEADER_EXTS):
                            base = os.path.basename(path)
                            allh.setdefault(base, (os.path.dirname(path) + "/", base))
                            allh.setdefault(f"{mod}/{base}", (os.path.dirname(path) + "/", base))
        tmp = s.get("TARGET_TEMP_DIR")
        a = os.path.join(tmp, f"{t.name}-own-target-headers.hmap")
        b = os.path.join(tmp, f"{t.name}-all-target-headers.hmap")
        own_full = dict(own)
        mod = s.get("PRODUCT_MODULE_NAME")
        for k, v in own.items():
            own_full[f"{mod}/{k}"] = v
        write_hmap(a, own_full)
        write_hmap(b, allh)
        return ["-iquote", a, "-I", b]

    def target(self, t):
        b = self.b
        s = t.s
        deps_done = [self.done[d] for d in t.deps if d in self.done]
        tmp = s.get("TARGET_TEMP_DIR")
        stamps = os.path.join(tmp, "xcbuild")
        os.makedirs(stamps, exist_ok=True)
        prev = deps_done[:]  # order-only inputs of the next phase
        products_dir = s.get("BUILT_PRODUCTS_DIR")
        cbd = s.get("CONFIGURATION_BUILD_DIR")
        objs = []
        product = None
        swiftmodule = None
        L = self.lines
        envf = self.env_file(t) if any(p.get("isa") == "PBXShellScriptBuildPhase" for p in t.phases()) else None
        hm = None
        kind = t.kind
        exe_path = os.path.join(s.get("TARGET_BUILD_DIR"), s.get("EXECUTABLE_PATH")) if s.get("EXECUTABLE_PATH") else None
        prep = os.path.join(stamps, "prepare.stamp")
        L.append(f"build {nesc(prep)}: step {nesc(self.step(t, 'prepare', {'dirs': [tmp, cbd, s.get('DERIVED_FILE_DIR'), s.get('OBJECT_FILE_DIR_normal') + '/' + b.arch] + ([os.path.join(s.get('TARGET_BUILD_DIR'), s.get('CONTENTS_FOLDER_PATH'))] if s.get('CONTENTS_FOLDER_PATH') else []), 'stamp': prep}))}" + (" || " + " ".join(nesc(x) for x in prev) if prev else ""))
        L.append(f"  desc = Prepare {t.name}")
        prev = [prep]
        link_inputs = []
        phase_i = 0
        for ph in t.phases():
            phase_i += 1
            isa = ph.get("isa")
            if isa == "PBXShellScriptBuildPhase":
                if ph.get("runOnlyForDeploymentPostprocessing") in ("1", 1):
                    continue
                name = ph.get("name") or "Run Script"
                script = ph.get("shellScript", "")
                sp = os.path.join(tmp, f"Script-{ph_id(t, ph)}.sh")
                os.makedirs(os.path.dirname(sp), exist_ok=True)
                shell = ph.get("shellPath", "/bin/sh")
                ins = [s.expand(x) for x in ph.get("inputPaths", [])]
                outs = [s.expand(x) for x in ph.get("outputPaths", [])]
                inlists = [s.expand(x) for x in ph.get("inputFileListPaths", [])]
                outlists = [s.expand(x) for x in ph.get("outputFileListPaths", [])]
                stamp = os.path.join(stamps, f"script-{phase_i}.stamp")
                data = {"script": script, "script_path": sp, "shell": shell, "env": envf, "cwd": s.get("SRCROOT"),
                        "inputs": ins, "outputs": outs, "input_lists": inlists, "output_lists": outlists, "stamp": stamp,
                        "name": name}
                st = self.step(t, "script", data)
                always = ph.get("alwaysOutOfDate") in ("1", 1) or not outs
                real_in = [x for x in ins + inlists if os.path.exists(x) and not x.endswith("/")]
                L.append(f"build {nesc(stamp)}: step {nesc(st)}" + (" | " + " ".join(nesc(x) for x in real_in) if real_in else "")
                         + (" " + nesc(os.path.join(self.out, 'always')) if always else "") + " || " + " ".join(nesc(x) for x in prev))
                L.append(f"  desc = Script {t.name}: {name}")
                prev = [stamp]
            elif isa == "PBXHeadersBuildPhase":
                if kind != "framework":
                    continue
                copies = []
                for path, st_, _, _ in b.phase_files(t, ph):
                    attrs = st_.get("ATTRIBUTES", []) if isinstance(st_, dict) else []
                    if "Public" in attrs:
                        copies.append((path, os.path.join(s.get("TARGET_BUILD_DIR"), s.get("PUBLIC_HEADERS_FOLDER_PATH"), os.path.basename(path))))
                    elif "Private" in attrs:
                        copies.append((path, os.path.join(s.get("TARGET_BUILD_DIR"), s.get("PRIVATE_HEADERS_FOLDER_PATH"), os.path.basename(path))))
                stamp = os.path.join(stamps, f"headers-{phase_i}.stamp")
                mm = s.get("MODULEMAP_FILE")
                mmdst = os.path.join(s.get("TARGET_BUILD_DIR"), s.get("MODULES_FOLDER_PATH"), "module.modulemap") if s.yes("DEFINES_MODULE") else ""
                st = self.step(t, "copy", {"copies": copies, "stamp": stamp,
                                           "modulemap": [(mm if os.path.isabs(mm) else os.path.join(s.get("SRCROOT"), mm)) if mm else "", mmdst]})
                L.append(f"build {nesc(stamp)}: step {nesc(st)} | " + " ".join(nesc(c[0]) for c in copies if os.path.exists(c[0])) + " || " + " ".join(nesc(x) for x in prev))
                L.append(f"  desc = Headers {t.name}")
                prev = [stamp]
            elif isa == "PBXSourcesBuildPhase":
                files = b.phase_files(t, ph)
                if hm is None:
                    hm = self.hmaps(t)
                objdir = os.path.join(s.get("OBJECT_FILE_DIR_normal"), b.arch)
                swift = [p for p, _, _, _ in files if p.endswith(".swift")]
                gen_header = ""
                swift_stamp = None
                if swift:
                    mod = s.get("SWIFT_MODULE_NAME")
                    mm = ""
                    has_c = any(SOURCE_LANG.get(os.path.splitext(p)[1], "").startswith(("objective", "c")) for p, _, _, _ in files) \
                        or any(ph2.get("isa") == "PBXHeadersBuildPhase" and ph2.get("files") for ph2 in t.phases())
                    if s.yes("DEFINES_MODULE") and has_c:
                        mm = s.get("MODULEMAP_FILE")
                        mm = (mm if os.path.isabs(mm) else os.path.join(s.get("SRCROOT"), mm)) if mm else ""
                    sdir = os.path.join(cbd if kind != "framework" else os.path.join(s.get("TARGET_BUILD_DIR"), s.get("MODULES_FOLDER_PATH")), f"{mod}.swiftmodule")
                    swiftmodule = os.path.join(sdir, f"{b.arch}-apple-{b.os}" + (f"-{b.env}" if b.env else "") + ".swiftmodule")
                    gen_header = os.path.join(s.get("DERIVED_SOURCES_DIR"), s.get("SWIFT_OBJC_INTERFACE_HEADER_NAME"))
                    obj = os.path.join(objdir, f"{mod}-swift.o")
                    flags = b.swift_flags(t, hm, mm or None)
                    parse_lib = not any(os.path.basename(p) == "main.swift" for p in swift)
                    st = self.step(t, "swiftc", {"swiftc": b.swiftc, "flags": flags, "files": swift, "obj": obj,
                                                 "module": swiftmodule, "header": gen_header, "parse_as_library": parse_lib,
                                                 "install_header": kind == "framework" and s.yes("SWIFT_INSTALL_OBJC_HEADER", True),
                                                 "public_headers": os.path.join(s.get("TARGET_BUILD_DIR"), s.get("PUBLIC_HEADERS_FOLDER_PATH") or "")})
                    dep_modules = [x for d in t.deps for x in [getattr(d, "swiftmodule", None)] if x]
                    L.append(f"build {nesc(obj)} {nesc(swiftmodule)} {nesc(gen_header)}: step {nesc(st)} | " + " ".join(nesc(x) for x in swift + dep_modules) + " || " + " ".join(nesc(x) for x in prev))
                    L.append(f"  desc = Swift {t.name} ({len(swift)} files)")
                    L.append("  restat = 1")
                    objs.append(obj)
                    swift_stamp = gen_header
                used = set()
                for path, fs, ref, _ in files:
                    ext = os.path.splitext(path)[1]
                    lang = SOURCE_LANG.get(ext)
                    if ext in (".swift",) or not lang or lang == "metal":
                        continue
                    base = os.path.splitext(os.path.basename(path))[0]
                    on = base
                    i = 1
                    while on in used:
                        i += 1
                        on = f"{base}-{i}"
                    used.add(on)
                    obj = os.path.join(objdir, on + ".o")
                    flags = b.clang_flags(t, lang, hm)
                    cf = fs.get("COMPILER_FLAGS", "") if isinstance(fs, dict) else ""
                    if cf:
                        flags += shlex.split(s.expand(cf))
                    L.append(f"build {nesc(obj)}: cc {nesc(path)} || " + " ".join(nesc(x) for x in prev + ([swift_stamp] if swift_stamp else [])))
                    L.append(f"  flags = {nesc_flags(flags)}")
                    L.append(f"  desc = {t.name}/{os.path.basename(path)}")
                    objs.append(obj)
                srcs_stamp = os.path.join(stamps, f"sources-{phase_i}.stamp")
                L.append(f"build {nesc(srcs_stamp)}: stamp " + " ".join(nesc(o) for o in objs) + " || " + " ".join(nesc(x) for x in prev))
                prev = [srcs_stamp]
            elif isa == "PBXFrameworksBuildPhase":
                for path, fs, ref, _ in b.phase_files(t, ph):
                    # a product of another target: where that target puts it (CocoaPods gives each pod its own dir)
                    owner = b.product_owner.get(os.path.basename(path))
                    if owner is not None and owner is not t and getattr(owner, "product_path", None):
                        path = owner.product_path
                    link_inputs.append(path)
                if kind in ("static",) and objs:
                    product = os.path.join(s.get("TARGET_BUILD_DIR"), s.get("EXECUTABLE_PATH"))
                    st = self.step(t, "archive", {"ar": b.ar, "objs": objs, "out": product})
                    L.append(f"build {nesc(product)}: step {nesc(st)} " + " ".join(nesc(o) for o in objs) + " || " + " ".join(nesc(x) for x in prev))
                    L.append(f"  desc = Archive {s.get('EXECUTABLE_NAME')}")
                    prev = [product]
                elif kind in ("app", "appex", "framework", "dylib", "tool", "bundle") and (objs or kind in ("app", "appex")):
                    if kind == "framework" and s.get("MACH_O_TYPE") == "staticlib":
                        product = exe_path
                        st = self.step(t, "archive", {"ar": b.ar, "objs": objs, "out": product})
                        L.append(f"build {nesc(product)}: step {nesc(st)} " + " ".join(nesc(o) for o in objs) + " || " + " ".join(nesc(x) for x in prev))
                        L.append(f"  desc = Archive {s.get('FULL_PRODUCT_NAME')}")
                    else:
                        product = exe_path
                        flags = b.link_flags(t, s)
                        mach = s.get("MACH_O_TYPE")
                        if kind in ("framework", "dylib") or mach == "mh_dylib":
                            flags += ["-dynamiclib", "-install_name", s.get("LD_DYLIB_INSTALL_NAME")]
                        elif kind == "bundle" or mach == "mh_bundle":
                            flags += ["-bundle"]
                        if kind == "appex":
                            flags += ["-e", "_NSExtensionMain", "-fapplication-extension"]
                        libs = [p for p in link_inputs]
                        flags += sorted({"-L" + os.path.dirname(p) for p in libs if p.endswith((".a", ".dylib")) and p.startswith(b.dd)})
                        flags += sorted({"-F" + os.path.dirname(p) for p in libs if p.endswith(".framework") and p.startswith(b.dd)})
                        st = self.step(t, "link", {"clang": b.clang, "flags": flags, "objs": objs, "libs": libs, "out": product,
                                                   "filelist": os.path.join(tmp, "link.filelist")})
                        ldeps = [p for p in libs if p.endswith((".a", ".dylib", ".tbd")) and (os.path.exists(p) or p in self.products)]
                        L.append(f"build {nesc(product)}: step {nesc(st)} " + " ".join(nesc(o) for o in objs) + (" | " + " ".join(nesc(x) for x in ldeps) if ldeps else "") + " || " + " ".join(nesc(x) for x in prev))
                        L.append(f"  desc = Link {s.get('FULL_PRODUCT_NAME') or s.get('EXECUTABLE_NAME')}")
                    prev = [product]
            elif isa == "PBXResourcesBuildPhase":
                res = [(p, (r.get("lastKnownFileType") or r.get("explicitFileType") or ""), lp) for p, _, r, lp in b.phase_files(t, ph)]
                if not res and kind not in ("bundle",):
                    continue
                stamp = os.path.join(stamps, f"resources-{phase_i}.stamp")
                dst = os.path.join(s.get("TARGET_BUILD_DIR"), s.get("UNLOCALIZED_RESOURCES_FOLDER_PATH") or "")
                st = self.step(t, "resources", {"files": res, "dest": dst, "stamp": stamp, "sdk": b.sdk, "platform_dir": b.platform_dir,
                                                "appicon": s.get("ASSETCATALOG_COMPILER_APPICON_NAME"),
                                                "accent": s.get("ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME"),
                                                "min": s.get(b.dt_key), "family": s.get("TARGETED_DEVICE_FAMILY"),
                                                "partial": os.path.join(tmp, "assetcatalog_generated_info.plist"),
                                                "ibtool_tmp": os.path.join(tmp, "ib")})
                ins = [p for p, _, _ in res if os.path.isfile(p)]
                L.append(f"build {nesc(stamp)}: step {nesc(st)}" + (" | " + " ".join(nesc(x) for x in ins) if ins else "") + " || " + " ".join(nesc(x) for x in prev))
                L.append(f"  desc = Resources {t.name}")
                prev = [stamp]
            elif isa == "PBXCopyFilesBuildPhase":
                dst_sub = {"1": "", "6": s.get("EXECUTABLE_FOLDER_PATH"), "7": s.get("UNLOCALIZED_RESOURCES_FOLDER_PATH"),
                           "10": s.get("FRAMEWORKS_FOLDER_PATH"), "11": s.get("SHARED_FRAMEWORKS_FOLDER_PATH"),
                           "13": s.get("PLUGINS_FOLDER_PATH"), "16": s.get("CONTENTS_FOLDER_PATH") + "/Extensions"}.get(str(ph.get("dstSubfolderSpec")), "")
                dst = os.path.join(s.get("TARGET_BUILD_DIR") if str(ph.get("dstSubfolderSpec")) != "16" else s.get("TARGET_BUILD_DIR"), dst_sub or "", s.expand(ph.get("dstPath", "")))
                copies = [(p, os.path.join(dst, os.path.basename(p))) for p, _, _, _ in b.phase_files(t, ph)]
                if not copies:
                    continue
                stamp = os.path.join(stamps, f"copy-{phase_i}.stamp")
                st = self.step(t, "copy", {"copies": copies, "stamp": stamp})
                L.append(f"build {nesc(stamp)}: step {nesc(st)} || " + " ".join(nesc(x) for x in prev + [c[0] for c in copies if c[0].startswith(b.dd)]))
                L.append(f"  desc = Copy {t.name}")
                prev = [stamp]
        # Info.plist and PkgInfo (bundles), then the target is done
        final = os.path.join(stamps, "done.stamp")
        if kind in ("app", "appex", "framework", "bundle"):
            info = os.path.join(s.get("TARGET_BUILD_DIR"), s.get("INFOPLIST_PATH"))
            ip = s.get("INFOPLIST_FILE")
            ip = (ip if os.path.isabs(ip) else os.path.join(s.get("SRCROOT"), ip)) if ip else ""
            env_all = {k: s.get(k) for k in s.keys() if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k)}
            for k in ("PRODUCT_BUNDLE_IDENTIFIER", "EXECUTABLE_NAME", "PRODUCT_NAME", "DEVELOPMENT_LANGUAGE", "MARKETING_VERSION",
                      "CURRENT_PROJECT_VERSION", "PRODUCT_BUNDLE_PACKAGE_TYPE", "PRODUCT_MODULE_NAME"):
                env_all.setdefault(k, s.get(k))
            st = self.step(t, "infoplist", {"src": ip, "dst": info, "settings": env_all, "product_kind": kind, "sdk": b.sdk,
                                            "platform": b.platform, "sdk_version": b.sdk_version, "min_key": b.dt_key,
                                            "partial": os.path.join(tmp, "assetcatalog_generated_info.plist"),
                                            "pkginfo": os.path.join(s.get("TARGET_BUILD_DIR"), s.get("PKGINFO_PATH")) if kind == "app" else ""})
            L.append(f"build {nesc(info)}: step {nesc(st)}" + (" | " + nesc(ip) if ip and os.path.exists(ip) else "") + " || " + " ".join(nesc(x) for x in prev))
            L.append(f"  desc = Info.plist {s.get('FULL_PRODUCT_NAME')}")
            prev.append(info)
        L.append(f"build {nesc(final)}: stamp || " + " ".join(nesc(x) for x in prev))
        self.done[t] = final
        if product:
            self.products.add(product)
        t.swiftmodule = swiftmodule
        t.product_path = os.path.join(s.get("TARGET_BUILD_DIR"), s.get("FULL_PRODUCT_NAME")) if s.get("FULL_PRODUCT_NAME") else None
        return final

    def write(self, order):
        b = self.b
        head = [
            "ninja_required_version = 1.7",
            f"rule cc\n  command = {sq([b.clang])} $flags -MMD -MF $obj.d -c $src -o $obj\n  depfile = $out.d\n  deps = gcc\n  description = CC $desc",
            f"rule step\n  command = {sq([sys.executable, os.path.abspath(__file__), 'step'])} $file\n  description = $desc",
            "rule stamp\n  command = touch $out\n  description = stamp",
            f"build {nesc(os.path.join(self.out, 'always'))}: phony",
        ]
        for t in order:
            self.target(t)
        # $in / $out are not shell-quoted: give the commands their paths as quoted variables
        lines = []
        for l in self.lines:
            lines.append(l)
            m = re.match(r"build ((?:[^:$]|\$.)+?): (step|cc) ((?:[^ $]|\$.)+)", l)
            if m:
                first_out = unesc(re.match(r"((?:[^ $]|\$.)+)", m.group(1)).group(1))
                src = unesc(m.group(3))
                if m.group(2) == "step":
                    lines.append(f"  file = {shlex.quote(src).replace('$', '$$')}")
                else:
                    lines.append(f"  src = {shlex.quote(src).replace('$', '$$')}")
                    lines.append(f"  obj = {shlex.quote(first_out).replace('$', '$$')}")
        text = "\n".join(head + lines) + "\n"
        path = os.path.join(self.out, "build.ninja")
        if not (os.path.exists(path) and open(path).read() == text):
            with open(path, "w") as f:
                f.write(text)
        return path


def unesc(p):
    return re.sub(r"\$(.)", r"\1", p)


def nesc_flags(flags):
    return " ".join(shlex.quote(f).replace("$", "$$") for f in flags)


def ph_id(t, ph):
    return hashlib.sha1(json.dumps(ph, sort_keys=True).encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------------------------- steps (run by ninja)


def touch(p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a"):
        os.utime(p, None)


def read_filelist(p):
    try:
        return [l.strip() for l in open(p) if l.strip()]
    except OSError:
        return []


def run_step(path):
    d = json.load(open(path))
    k = d["kind"]
    if k == "prepare":
        for x in d["dirs"]:
            os.makedirs(x, exist_ok=True)
        touch(d["stamp"])
    elif k == "script":
        os.makedirs(os.path.dirname(d["script_path"]), exist_ok=True)
        with open(d["script_path"], "w") as f:
            f.write(d["script"])
        env_lines = []
        for i, x in enumerate(d["inputs"]):
            env_lines.append(f"export SCRIPT_INPUT_FILE_{i}={shlex.quote(x)}")
        env_lines.append(f"export SCRIPT_INPUT_FILE_COUNT={len(d['inputs'])}")
        for i, x in enumerate(d["outputs"]):
            env_lines.append(f"export SCRIPT_OUTPUT_FILE_{i}={shlex.quote(x)}")
            os.makedirs(os.path.dirname(x) or ".", exist_ok=True)
        env_lines.append(f"export SCRIPT_OUTPUT_FILE_COUNT={len(d['outputs'])}")
        for i, x in enumerate(d["input_lists"]):
            env_lines.append(f"export SCRIPT_INPUT_FILE_LIST_{i}={shlex.quote(x)}")
        env_lines.append(f"export SCRIPT_INPUT_FILE_LIST_COUNT={len(d['input_lists'])}")
        for i, x in enumerate(d["output_lists"]):
            env_lines.append(f"export SCRIPT_OUTPUT_FILE_LIST_{i}={shlex.quote(x)}")
        env_lines.append(f"export SCRIPT_OUTPUT_FILE_LIST_COUNT={len(d['output_lists'])}")
        shell = d["shell"]
        # /bin/sh is bash on macOS; scripts written there use bash features
        if shell in ("/bin/sh", "sh", "/bin/bash"):
            shell = shutil.which("bash") or "/bin/bash"
        cmd = f". {shlex.quote(d['env'])}\n" + "\n".join(env_lines) + f"\nexec {shlex.quote(shell)} {shlex.quote(d['script_path'])}\n"
        r = subprocess.run(["bash", "-c", cmd], cwd=d["cwd"])
        if r.returncode != 0:
            sys.stderr.write(f"xcbuild: error: script phase '{d['name']}' of {d['target']} failed (exit {r.returncode})\n")
            sys.exit(r.returncode)
        touch(d["stamp"])
    elif k == "copy":
        for src, dst in d["copies"]:
            if not os.path.exists(src):
                sys.stderr.write(f"xcbuild: warning: {src} does not exist (copy to {dst})\n")
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.isdir(src):
                shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        mm = d.get("modulemap")
        if mm and mm[0] and mm[1]:
            os.makedirs(os.path.dirname(mm[1]), exist_ok=True)
            shutil.copy2(mm[0], mm[1])
        touch(d["stamp"])
    elif k == "swiftc":
        os.makedirs(os.path.dirname(d["obj"]), exist_ok=True)
        os.makedirs(os.path.dirname(d["module"]), exist_ok=True)
        os.makedirs(os.path.dirname(d["header"]), exist_ok=True)
        rsp = d["obj"] + ".rsp"
        args = d["flags"] + (["-parse-as-library"] if d["parse_as_library"] else []) + [
            "-wmo", "-c", "-o", d["obj"], "-emit-module", "-emit-module-path", d["module"],
            "-emit-objc-header", "-emit-objc-header-path", d["header"]] + d["files"]
        with open(rsp, "w") as f:
            f.write("\n".join(shlex.quote(a) for a in args))
        r = subprocess.run([d["swiftc"], "@" + rsp])
        if r.returncode != 0:
            sys.exit(r.returncode)
        if d.get("install_header") and d.get("public_headers"):
            os.makedirs(d["public_headers"], exist_ok=True)
            shutil.copy2(d["header"], os.path.join(d["public_headers"], os.path.basename(d["header"])))
    elif k == "archive":
        os.makedirs(os.path.dirname(d["out"]), exist_ok=True)
        if os.path.exists(d["out"]):
            os.remove(d["out"])
        rsp = d["out"] + ".rsp"
        with open(rsp, "w") as f:
            f.write("\n".join(shlex.quote(o) for o in d["objs"]))
        r = subprocess.run([d["ar"], "crs", "--format=darwin", d["out"], "@" + rsp])
        sys.exit(r.returncode) if r.returncode else None
    elif k == "link":
        os.makedirs(os.path.dirname(d["out"]), exist_ok=True)
        with open(d["filelist"], "w") as f:
            f.write("\n".join(d["objs"]) + "\n")
        libs = []
        for p in d["libs"]:
            base = os.path.basename(p)
            if p.endswith(".framework"):
                libs += ["-framework", os.path.splitext(base)[0]]
            elif base.startswith("lib") and p.endswith((".a", ".dylib", ".tbd")):
                libs.append("-l" + os.path.splitext(base[3:])[0])
            elif p.endswith(".xcframework"):
                continue
            else:
                libs.append(p)
        args = [d["clang"]] + d["flags"] + ["-Xlinker", "-filelist", "-Xlinker", d["filelist"]] + libs + ["-o", d["out"]]
        r = subprocess.run(args)
        if r.returncode != 0:
            sys.exit(r.returncode)
    elif k == "resources":
        resources(d)
        touch(d["stamp"])
    elif k == "infoplist":
        infoplist(d)
    else:
        die(f"unknown step {k}")


def resources(d):
    dst = d["dest"]
    os.makedirs(dst, exist_ok=True)
    catalogs = []
    bindir = os.path.join(d["platform_dir"], "Developer/usr/bin")
    for path, ftype, lproj in d["files"]:
        if not os.path.exists(path):
            sys.stderr.write(f"xcbuild: warning: resource {path} does not exist\n")
            continue
        name = os.path.basename(path)
        out_dir = os.path.join(dst, f"{lproj}.lproj") if lproj else dst
        os.makedirs(out_dir, exist_ok=True)
        ext = os.path.splitext(name)[1]
        if ext == ".xcassets":
            catalogs.append(path)
        elif ext in (".storyboard", ".xib"):
            out = os.path.join(out_dir, os.path.splitext(name)[0] + (".storyboardc" if ext == ".storyboard" else ".nib"))
            r = subprocess.run([os.path.join(bindir, "ibtool"), "--compile", out, path, "--target-device", "iphone",
                                "--minimum-deployment-target", d["min"] or "15.0"], capture_output=True, text=True)
            if r.returncode != 0:
                sys.stderr.write(f"xcbuild: warning: ibtool could not compile {name}; it is left out ({(r.stderr or r.stdout).strip()[-300:]})\n")
        elif ext == ".xcdatamodeld" or ext == ".xcdatamodel":
            out = os.path.join(out_dir, os.path.splitext(name)[0] + (".momd" if ext == ".xcdatamodeld" else ".mom"))
            subprocess.run([os.path.join(bindir, "momc"), path, out])
        elif os.path.isdir(path):
            shutil.copytree(path, os.path.join(out_dir, name), symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(path, os.path.join(out_dir, name))
    if catalogs:
        cmd = [os.path.join(bindir, "actool"), "--compile", dst, "--platform", d["sdk"], "--minimum-deployment-target",
               d["min"] or "15.0", "--output-partial-info-plist", d["partial"], "--output-format", "human-readable-text"]
        if d.get("appicon"):
            cmd += ["--app-icon", d["appicon"]]
        if d.get("accent"):
            cmd += ["--accent-color", d["accent"]]
        for fam in (d.get("family") or "1").replace(",", " ").split():
            cmd += ["--target-device", {"1": "iphone", "2": "ipad", "3": "tv", "4": "watch", "7": "vision"}.get(fam, "iphone")]
        r = subprocess.run(cmd + catalogs, capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stdout + r.stderr)
            die("actool failed for " + ", ".join(catalogs))


def plist_expand(v, settings):
    if isinstance(v, str):
        def sub(m):
            expr = m.group(1) or m.group(2) or ""
            name, _, mod = expr.partition(":")
            val = settings.get(name, "")
            for mm in mod.split(":") if mod else []:
                if mm in MODIFIERS:
                    val = MODIFIERS[mm](val)
            return val

        return re.sub(r"\$\(([^)]*)\)|\$\{([^}]*)\}", sub, v)
    if isinstance(v, list):
        return [plist_expand(x, settings) for x in v]
    if isinstance(v, dict):
        return {k: plist_expand(x, settings) for k, x in v.items()}
    return v


def infoplist(d):
    st = d["settings"]
    info = {}
    if d["src"] and os.path.exists(d["src"]):
        with open(d["src"], "rb") as f:
            data = f.read()
        try:
            info = plistlib.loads(data)
        except Exception:
            # an OpenStep / JSON plist: the shim plutil reads JSON; leave others empty
            info = json.loads(data) if data.lstrip()[:1] == b"{" else {}
        info = plist_expand(info, st)
    if st.get("GENERATE_INFOPLIST_FILE", "").upper() == "YES":
        for k, v in st.items():
            if k.startswith("INFOPLIST_KEY_") and v != "":
                key = k[len("INFOPLIST_KEY_"):]
                if v.upper() in ("YES", "NO"):
                    info.setdefault(key, v.upper() == "YES")
                else:
                    info.setdefault(key, v)
        info.setdefault("CFBundleIdentifier", st.get("PRODUCT_BUNDLE_IDENTIFIER", ""))
        info.setdefault("CFBundleExecutable", st.get("EXECUTABLE_NAME", ""))
        info.setdefault("CFBundleName", st.get("PRODUCT_NAME", ""))
        info.setdefault("CFBundleShortVersionString", st.get("MARKETING_VERSION", "1.0"))
        info.setdefault("CFBundleVersion", st.get("CURRENT_PROJECT_VERSION", "1"))
        info.setdefault("CFBundleInfoDictionaryVersion", "6.0")
        info.setdefault("CFBundleDevelopmentRegion", st.get("DEVELOPMENT_LANGUAGE", "en") or "en")
    kind = d["product_kind"]
    if not info.get("CFBundlePackageType"):
        info.pop("CFBundlePackageType", None)
    info.setdefault("CFBundlePackageType", {"app": "APPL", "appex": "XPC!", "framework": "FMWK", "bundle": "BNDL"}.get(kind, "BNDL"))
    if kind in ("app", "appex", "framework"):
        info["CFBundleSupportedPlatforms"] = [d["platform"]]
        info["DTPlatformName"] = d["sdk"]
        info["DTPlatformVersion"] = d["sdk_version"]
        info["DTSDKName"] = d["sdk"] + d["sdk_version"]
        info.setdefault("DTPlatformBuild", "")
        info.setdefault("DTSDKBuild", "")
        info.setdefault("DTXcode", "2700")
        info.setdefault("DTCompiler", "com.apple.compilers.llvm.clang.1_0")
        if st.get(d["min_key"]):
            info["MinimumOSVersion"] = st[d["min_key"]]
        fam = [int(x) for x in re.split(r"[ ,]+", st.get("TARGETED_DEVICE_FAMILY", "1").strip()) if x.isdigit()]
        if fam and kind in ("app", "appex"):
            info["UIDeviceFamily"] = fam
    if os.path.exists(d.get("partial", "")) and kind in ("app", "appex"):
        try:
            info.update(plistlib.load(open(d["partial"], "rb")))
        except Exception:
            pass
    os.makedirs(os.path.dirname(d["dst"]), exist_ok=True)
    with open(d["dst"], "wb") as f:
        plistlib.dump(info, f, fmt=plistlib.FMT_BINARY)
    if d.get("pkginfo"):
        with open(d["pkginfo"], "w") as f:
            f.write("APPL????")


# ---------------------------------------------------------------------------------------------- Swift packages


def build_package(a):
    """`xcodebuild build -scheme PRODUCT` in a Swift package's directory (Expo builds ExpoModulesJSI.xcframework this
    way): swift build for the SDK, laid out as Xcode lays out a package's dynamic library product:
    <products>/PackageFrameworks/<P>.framework, <products>/<P>.swiftmodule/<triple>.*, and the generated ObjC header
    in <OBJROOT>/GeneratedModuleMaps-<platform>/<P>-Swift.h"""
    b = Build(a)
    name = a.scheme or a.target
    if not name:
        die("say -scheme PRODUCT")
    st = dict(kv.split("=", 1) for kv in a.settings)
    effective = "" if b.sdk == "macosx" else "-" + b.sdk
    symroot = st.get("SYMROOT") or os.path.join(b.dd, "Build/Products")
    objroot = st.get("OBJROOT") or os.path.join(b.dd, "Build/Intermediates.noindex")
    products = os.path.join(symroot, f"{a.configuration}{effective}")
    triple = f"{b.arch}-apple-{b.os}" + (f"-{b.env}" if b.env else "")
    scratch = os.path.join(b.dd, "SourcePackages", "swiftpm-build")
    cfg = "release" if a.configuration.lower().startswith("release") else "debug"
    inc = b.toolchain_include()
    cmd = [os.path.join(b.tc, "swift"), "build", "--build-system", "native", "--swift-sdks-path", os.path.dirname(b.bundle),
           "--swift-sdk", triple, "-c", cfg,
           "--product", name, "--scratch-path", scratch, "-j", str(a.jobs or os.environ.get("XCBUILD_JOBS") or 4),
           "-Xcxx", "-isystem", "-Xcxx", inc, "-Xcc", "-isystem", "-Xcc", inc,
           "-Xlinker", "-install_name", "-Xlinker", f"@rpath/{name}.framework/{name}"]
    if st.get("BUILD_LIBRARY_FOR_DISTRIBUTION", "").upper() == "YES":
        # Apple's Swift 6.4 lets a library-evolution module extend C++ types from an implementation-only import;
        # swift.org's needs the feature that says so
        cmd += ["-Xswiftc", "-enable-library-evolution", "-Xswiftc", "-emit-module-interface",
                "-Xswiftc", "-enable-experimental-feature", "-Xswiftc", "AssumeResilientCxxTypes"]
    ld = st.get("OTHER_LDFLAGS", "").replace("$(inherited)", "")
    for x in shlex.split(ld):
        if x != "-Xlinker":
            cmd += ["-Xlinker", x]
    print("== swift build " + name + " for " + triple, flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("** BUILD FAILED **")
        return 1
    bin_dir = os.path.join(scratch, triple, cfg)
    dylib = os.path.join(bin_dir, f"lib{name}.dylib")
    if not os.path.exists(dylib):
        die(f"swift build made no lib{name}.dylib (is {name} a .dynamic library product?)")
    fw = os.path.join(products, "PackageFrameworks", f"{name}.framework")
    shutil.rmtree(fw, ignore_errors=True)
    os.makedirs(fw)
    shutil.copy2(dylib, os.path.join(fw, name))
    dt = DEFAULT_DT[b.os]
    with open(os.path.join(fw, "Info.plist"), "wb") as f:
        plistlib.dump({"CFBundleExecutable": name, "CFBundleIdentifier": name, "CFBundleName": name,
                       "CFBundlePackageType": "FMWK", "CFBundleShortVersionString": "1.0", "CFBundleVersion": "1",
                       "CFBundleSupportedPlatforms": [b.platform], "MinimumOSVersion": dt,
                       "CFBundleInfoDictionaryVersion": "6.0"}, f, fmt=plistlib.FMT_BINARY)
    if os.path.isdir(dylib + ".dSYM"):
        shutil.rmtree(fw + ".dSYM", ignore_errors=True)
        shutil.copytree(dylib + ".dSYM", os.path.join(products, f"{name}.framework.dSYM"), dirs_exist_ok=True)
    sm = os.path.join(products, f"{name}.swiftmodule")
    shutil.rmtree(sm, ignore_errors=True)
    os.makedirs(sm)
    mods = os.path.join(bin_dir, "Modules")
    for f in os.listdir(mods):
        if f.startswith(name + "."):
            ext = f[len(name):]  # .swiftmodule, .swiftinterface, .private.swiftinterface, ...
            shutil.copy2(os.path.join(mods, f), os.path.join(sm, triple + ext))
    hdr = os.path.join(bin_dir, f"{name}.build", "include", f"{name}-Swift.h")
    gm = os.path.join(objroot, f"GeneratedModuleMaps{effective}")
    os.makedirs(gm, exist_ok=True)
    if os.path.exists(hdr):
        shutil.copy2(hdr, os.path.join(gm, f"{name}-Swift.h"))
        with open(os.path.join(gm, f"{name}.modulemap"), "w") as f:
            f.write(f'module {name} {{\n  header "{name}-Swift.h"\n  export *\n}}\n')
    print("** BUILD SUCCEEDED **")
    print(f"product: {fw}")
    return 0


# ---------------------------------------------------------------------------------------------- main


def parse_args(argv):
    class A:
        workspace = project = scheme = target = None
        configuration = "Debug"
        sdk = "iphonesimulator"
        derivedDataPath = None
        jobs = None
        settings = []
        action = "build"
        show = False
        quiet = False

    a = A()
    a.settings = []
    i = 0
    while i < len(argv):
        x = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if x in ("-workspace", "-project", "-scheme", "-target", "-configuration", "-sdk", "-derivedDataPath", "-jobs", "-destination", "-arch"):
            if nxt is None:
                die(f"{x} needs a value")
            if x == "-destination":
                m = re.search(r"platform=([^,]+)", nxt)
                if m and a.sdk == "iphonesimulator" and "Simulator" not in m.group(1) and "generic" not in nxt.split(",")[0]:
                    a.sdk = {"iOS": "iphoneos", "tvOS": "appletvos", "watchOS": "watchos", "visionOS": "xros"}.get(m.group(1), a.sdk)
                elif m:
                    a.sdk = {"iOS Simulator": "iphonesimulator", "tvOS Simulator": "appletvsimulator", "watchOS Simulator": "watchsimulator",
                             "visionOS Simulator": "xrsimulator", "iOS": "iphoneos", "tvOS": "appletvos", "watchOS": "watchos", "visionOS": "xros"}.get(m.group(1), a.sdk)
            elif x != "-arch":
                setattr(a, x[1:], nxt)
            i += 2
        elif x in ("build", "clean"):
            a.action = x
            i += 1
        elif x == "-showBuildSettings":
            a.show = True
            i += 1
        elif x in ("-quiet", "-q"):
            a.quiet = True
            i += 1
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])*=", x):
            a.settings.append(x)
            i += 1
        elif x.startswith("-"):
            i += 1  # options xcodebuild has and this does not need (-allowProvisioningUpdates, ...)
        else:
            die(f"unexpected argument {x}")
    a.package = False
    if not a.workspace and not a.project:
        here = os.getcwd()
        ws = [f for f in os.listdir(here) if f.endswith(".xcworkspace")]
        pj = [f for f in os.listdir(here) if f.endswith(".xcodeproj")]
        if ws:
            a.workspace = ws[0]
        elif pj:
            a.project = pj[0]
        elif os.path.exists(os.path.join(here, "Package.swift")):
            a.package = True
        else:
            die("no -workspace or -project, and none in the current directory")
    if not a.derivedDataPath:
        base = os.getcwd() if a.package else os.path.dirname(os.path.abspath(a.workspace or a.project))
        a.derivedDataPath = os.path.join(base, ".build" if a.package else "build", "xcbuild")
    return a


def main(argv):
    if argv[:1] == ["step"]:
        run_step(argv[1])
        return 0
    if not argv or argv[0] in ("-h", "--help", "-help"):
        print(__doc__)
        return 0
    a = parse_args(argv)
    if a.package:
        return build_package(a)
    b = Build(a)
    name = a.scheme or a.target
    if not name:
        apps = [t for t in b.ws.all_targets() if t.kind == "app"]
        if len(apps) != 1:
            die("say -scheme NAME (apps: " + ", ".join(t.name for t in apps) + ")")
        name = apps[0].name
    root = b.ws.find(name)
    if a.scheme and root.kind == "other":
        die(f"{name} builds nothing here")
    if a.show:
        for k in sorted(root.s.keys() | {"BUILT_PRODUCTS_DIR", "TARGET_BUILD_DIR", "FULL_PRODUCT_NAME", "PRODUCT_NAME", "EXECUTABLE_PATH"}):
            print(f"    {k} = {root.s.get(k)}")
        return 0
    if a.action == "clean":
        shutil.rmtree(os.path.join(b.dd, "Build"), ignore_errors=True)
        shutil.rmtree(os.path.join(b.dd, "xcbuild"), ignore_errors=True)
        print("** CLEAN SUCCEEDED **")
        return 0
    order = b.closure(root)
    g = Gen(b, root)
    touch(os.path.join(g.out, "session"))
    nf = g.write(order)
    ninja = shutil.which("ninja") or shutil.which("samu")
    if not ninja:
        die("ninja is not installed (Arch: pacman -S ninja; Debian/Ubuntu/Fedora: ninja-build)")
    jobs = a.jobs or os.environ.get("XCBUILD_JOBS") or str(max(1, min(os.cpu_count() or 2, 8)))
    print(f"== {name}: {len(order)} targets, {b.cfg}, {b.sdk} ({b.triple(root.s)})", flush=True)
    r = subprocess.run([ninja, "-f", nf, "-j", str(jobs)] + ([] if not a.quiet else ["--quiet"]) + [os.path.relpath(g.done[root], os.getcwd()) if False else g.done[root]])
    if r.returncode != 0:
        print("** BUILD FAILED **")
        return 1
    print("** BUILD SUCCEEDED **")
    if root.product_path:
        print(f"app: {root.product_path}" if root.kind == "app" else f"product: {root.product_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
