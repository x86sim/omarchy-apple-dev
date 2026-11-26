#!/usr/bin/env python3
"""After `ns prepare ios` on Linux: make platforms/ios build with Swift Build and run on an arm64 simulator.

  fix-project.py PLATFORMS_IOS_DIR GENERATOR_BIN_DIR

- The metadata generator: internal/metadata-generator-<uname -m>/bin (what internal/nsld.sh runs at link time) becomes
  the Linux build (build-metadata-generator.sh), in place of the macOS binary the runtime package ships.
- The project file: the CLI's pbxproj writer (the `xcode` npm package) leaves `explicitFileType = undefined;`,
  `fileEncoding = undefined;` and `lastKnownFileType = unknown;` on the files it adds (plugin sources, xcframeworks,
  the launch storyboard). Xcode ignores an unknown explicit type and goes by the extension; sweetpad's project reader
  takes it literally (sources not compiled, an .xcframework copied whole), so the types are spelled out.
- internal/nativescript-build.xcconfig excludes arm64 from simulator builds on x86_64 hosts (an Intel Mac's
  simulator runs x86_64 apps); x86Sim's simulator, like Apple's on Apple silicon, runs arm64: x86_64 is excluded
  instead.
"""
import glob
import os
import platform
import re
import shutil
import sys

TYPES = {"xcframework": "wrapper.xcframework", "framework": "wrapper.framework", "a": "archive.ar",
         "bundle": "wrapper.plug-in", "m": "sourcecode.c.objc", "mm": "sourcecode.cpp.objcpp",
         "swift": "sourcecode.swift", "c": "sourcecode.c.c", "cpp": "sourcecode.cpp.cpp", "h": "sourcecode.c.h",
         "modulemap": "sourcecode.module-map", "storyboard": "file.storyboard", "xib": "file.xib",
         "xcassets": "folder.assetcatalog", "strings": "text.plist.strings", "plist": "text.plist.xml",
         "json": "text.json", "xcprivacy": "text.xml", "png": "image.png"}


def fix_pbxproj(path):
    s = open(path).read()

    def fix(m):
        line = m.group(0).replace(" explicitFileType = undefined;", "").replace(" fileEncoding = undefined;", "")
        if "lastKnownFileType = unknown;" in line:
            p = re.search(r'path = "?([^";]+)"?;', line)
            ext = p.group(1).rsplit(".", 1)[-1] if p else ""
            if ext in TYPES:
                line = line.replace("lastKnownFileType = unknown;", "lastKnownFileType = %s;" % TYPES[ext])
        return line

    s2, n = re.subn(r'^.*isa = PBXFileReference;.*(?:= undefined;|lastKnownFileType = unknown;).*$', fix, s, flags=re.M)
    if s2 != s:
        open(path + ".tmp", "w").write(s2)
        os.replace(path + ".tmp", path)
    return n


def fix_xcconfig(path):
    s = open(path).read()
    s2 = s.replace("EXCLUDED_ARCHS[sdk=iphonesimulator*] = i386 armv6 armv7 armv7s armv8 $(EXCLUDED_ARCHS_$(NATIVE_ARCH_64_BIT))",
                   "EXCLUDED_ARCHS[sdk=iphonesimulator*] = i386 armv6 armv7 armv7s armv8 x86_64")
    if s2 != s:
        open(path, "w").write(s2)
    return s2 != s


def main():
    ios, gen = sys.argv[1], sys.argv[2]
    internal = os.path.join(ios, "internal")
    dst = os.path.join(internal, "metadata-generator-%s" % platform.machine(), "bin")
    if os.path.realpath(dst) != os.path.realpath(gen):
        shutil.rmtree(os.path.dirname(dst), ignore_errors=True)
        os.makedirs(os.path.dirname(dst))
        os.symlink(gen, dst)
    n = sum(fix_pbxproj(p) for p in glob.glob(os.path.join(ios, "*.xcodeproj", "project.pbxproj")))
    x = os.path.join(internal, "nativescript-build.xcconfig")
    arch = os.path.isfile(x) and fix_xcconfig(x)
    print("nativescript: Linux metadata generator in %s; %d file references typed; %s" % (
        os.path.relpath(dst, ios), n, "simulator builds arm64" if arch else "architectures unchanged"))


if __name__ == "__main__":
    main()
