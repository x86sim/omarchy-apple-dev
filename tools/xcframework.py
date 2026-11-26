#!/usr/bin/env python3
"""xcodebuild -create-xcframework on Linux: an .xcframework from frameworks or libraries built for several platforms,
laid out as Xcode's xcodebuild lays it out (linux-bin/xcodebuild runs this for -create-xcframework).

    xcframework.py -create-xcframework (-framework F [-debug-symbols D]... | -library L [-headers H]
                   [-debug-symbols D]...)... -output OUT.xcframework [-allow-internal-distribution]

Each binary's platform and variant come from its Mach-O LC_BUILD_VERSION (llvm-otool), its architectures from
llvm-lipo, so a slice's library identifier (ios-arm64, ios-arm64_x86_64-simulator, ...) matches Xcode's.
"""
import os
import plistlib
import re
import shutil
import subprocess
import sys

# LC_BUILD_VERSION platform -> (SupportedPlatform, SupportedPlatformVariant)
PLATFORMS = {1: ("macos", None), 2: ("ios", None), 3: ("tvos", None), 4: ("watchos", None), 6: ("ios", "maccatalyst"),
             7: ("ios", "simulator"), 8: ("tvos", "simulator"), 9: ("watchos", "simulator"), 11: ("xros", None),
             12: ("xros", "simulator")}
# older binaries: LC_VERSION_MIN_* -> platform (simulator slices of those are told by their x86_64 / i386 arch)
VERSION_MIN = {"LC_VERSION_MIN_MACOSX": "macos", "LC_VERSION_MIN_IPHONEOS": "ios", "LC_VERSION_MIN_TVOS": "tvos",
               "LC_VERSION_MIN_WATCHOS": "watchos"}


def die(msg):
    sys.stderr.write(f"error: {msg}\n")
    sys.exit(64)


def tool(name):
    for c in (f"llvm-{name}", name):
        p = shutil.which(c)
        if p:
            return p
    die(f"{name} not found (LLVM's llvm-{name})")


def archs(binary):
    r = subprocess.run([tool("lipo"), "-archs", binary], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"{binary}: not a Mach-O binary ({r.stderr.strip()})")
    return sorted(r.stdout.split(), key=lambda a: (a != "arm64", a))


def platform(binary, arch):
    r = subprocess.run([tool("otool"), "-arch", arch, "-l", binary], capture_output=True, text=True)
    text = r.stdout
    m = re.search(r"cmd LC_BUILD_VERSION\s.*?\n\s*platform (\S+)", text, re.S)
    if m:
        p = m.group(1)
        num = int(p) if p.isdigit() else {"MACOS": 1, "IOS": 2, "TVOS": 3, "WATCHOS": 4, "MACCATALYST": 6,
                                          "IOSSIMULATOR": 7, "TVOSSIMULATOR": 8, "WATCHOSSIMULATOR": 9, "XROS": 11,
                                          "XROSSIMULATOR": 12}.get(p.upper(), 0)
        if num in PLATFORMS:
            return PLATFORMS[num]
    for cmd, plat in VERSION_MIN.items():
        if f"cmd {cmd}" in text:
            return plat, ("simulator" if plat != "macos" and arch in ("x86_64", "i386") else None)
    die(f"{binary}: no platform in its load commands")


def framework_binary(fw):
    name = os.path.splitext(os.path.basename(fw.rstrip("/")))[0]
    info = None
    for p in (os.path.join(fw, "Info.plist"), os.path.join(fw, "Resources/Info.plist"),
              os.path.join(fw, "Versions/A/Resources/Info.plist")):
        if os.path.isfile(p):
            with open(p, "rb") as f:
                info = plistlib.load(f)
            break
    exe = (info or {}).get("CFBundleExecutable", name)
    for rel in (exe, f"Versions/A/{exe}"):
        if os.path.isfile(os.path.join(fw, rel)):
            return rel
    die(f"{fw}: no executable {exe}")


def main(argv):
    items, out = [], None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-framework", "-library"):
            items.append({"kind": a[1:], "path": os.path.abspath(argv[i + 1]), "symbols": [], "headers": None})
            i += 2
        elif a == "-debug-symbols":
            if not items:
                die("-debug-symbols must follow a -framework or -library")
            items[-1]["symbols"].append(os.path.abspath(argv[i + 1]))
            i += 2
        elif a == "-headers":
            if not items or items[-1]["kind"] != "library":
                die("-headers must follow a -library")
            items[-1]["headers"] = os.path.abspath(argv[i + 1])
            i += 2
        elif a == "-output":
            out = os.path.abspath(argv[i + 1])
            i += 2
        elif a in ("-create-xcframework", "-allow-internal-distribution"):
            i += 1
        else:
            die(f"unknown argument {a}")
    if not items or not out:
        die("-create-xcframework needs at least one -framework or -library and -output")
    if not out.endswith(".xcframework"):
        die("the -output path must end in .xcframework")
    if os.path.exists(out):
        die(f"the path does not point to a valid location: {out} already exists")
    os.makedirs(out)
    libs = []
    for it in items:
        src = it["path"].rstrip("/")
        rel_bin = framework_binary(src) if it["kind"] == "framework" else ""
        binary = os.path.join(src, rel_bin) if rel_bin else src
        arch_list = archs(binary)
        plat, variant = platform(binary, arch_list[0])
        ident = f"{plat}-{'_'.join(arch_list)}" + (f"-{variant}" if variant else "")
        if any(l["LibraryIdentifier"] == ident for l in libs):
            die(f"both {src} and another item represent two equivalent library definitions ({ident})")
        dest = os.path.join(out, ident)
        os.makedirs(dest)
        name = os.path.basename(src)
        shutil.copytree(src, os.path.join(dest, name), symlinks=True) if os.path.isdir(src) else \
            shutil.copy2(src, os.path.join(dest, name))
        lib = {"LibraryIdentifier": ident, "LibraryPath": name, "SupportedArchitectures": arch_list,
               "SupportedPlatform": plat}
        lib["BinaryPath"] = f"{name}/{rel_bin}" if rel_bin else name
        if variant:
            lib["SupportedPlatformVariant"] = variant
        if it["headers"]:
            shutil.copytree(it["headers"], os.path.join(dest, "Headers"), symlinks=True)
            lib["HeadersPath"] = "Headers"
        for sym in it["symbols"]:
            if sym.endswith(".dSYM"):
                sub = "dSYMs"
            elif sym.endswith(".bcsymbolmap"):
                sub = "BCSymbolMaps"
            else:
                die(f"{sym}: debug symbols must be a .dSYM or a .bcsymbolmap")
            os.makedirs(os.path.join(dest, sub), exist_ok=True)
            target = os.path.join(dest, sub, os.path.basename(sym))
            shutil.copytree(sym, target, symlinks=True) if os.path.isdir(sym) else shutil.copy2(sym, target)
            lib.setdefault("DebugSymbolsPath" if sub == "dSYMs" else "BitcodeSymbolMapsPath", sub)
        libs.append(lib)
    with open(os.path.join(out, "Info.plist"), "wb") as f:
        plistlib.dump({"AvailableLibraries": sorted(libs, key=lambda l: l["LibraryIdentifier"]),
                       "CFBundlePackageType": "XFWK", "XCFrameworkFormatVersion": "1.0"}, f)
    print(f"xcframework successfully written out to: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
