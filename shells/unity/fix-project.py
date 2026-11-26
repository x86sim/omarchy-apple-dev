#!/usr/bin/env python3
"""After a Unity editor on Linux exported an iOS Xcode project: make its IL2CPP step run on Linux.

  fix-project.py XCODE_PROJECT_DIR UNITY_EDITOR_DIR

The export carries IL2CPP for macOS (Il2CppOutputProject/IL2CPP/build/deploy_<arch>: Mach-O il2cpp and bee_backend),
which the GameAssembly target's script phase runs at build time. The Linux editor has the same IL2CPP built for Linux
(Editor/Data/il2cpp/build/deploy, with its iOS toolchain): deploy_<uname -m> becomes a link to it. IL2CPP then
compiles the game's C++ with the build's toolchain and archives it with Apple's `libtool -static`, which Linux has
not: the script phase gets a toolchain overlay (the build's toolchain, plus shells/unity/libtool). The "Check Unity
Framework ABI" phase (validate-tbd.sh) lists the framework's symbols with Apple's `nm -arch`; GNU nm has no -arch, so
on Linux it uses llvm-nm, which takes the same options. That phase declares no inputs, so Swift Build may run it
before UnityFramework is linked ("Framework binary not found"): the framework binary becomes its input.
"""
import os
import platform
import re
import shutil
import sys

ANCHOR = '    if [ -n \\"$SDKROOT\\" ] && [ -d \\"$SDKROOT\\" ]; then'
OVERLAY = ('    # x86Sim (shells/unity/fix-project.py): on Linux, the toolchain plus a libtool stand-in\\n'
           '    if [ \\"$(uname -s)\\" = Linux ]; then\\n'
           '        LINUX_TC=\\"$PROJECT_DIR/Il2CppOutputProject/linux-toolchain\\"\\n'
           '        mkdir -p \\"$LINUX_TC/usr/bin\\"\\n'
           '        for t in \\"$UNITY_TOOLCHAIN_DIR\\"/usr/bin/*; do ln -sfn \\"$t\\" \\"$LINUX_TC/usr/bin/\\"; done\\n'
           '        cp -f \\"$PROJECT_DIR/Il2CppOutputProject/linux-libtool\\" \\"$LINUX_TC/usr/bin/libtool\\"\\n'
           '        UNITY_TOOLCHAIN_DIR=\\"$LINUX_TC\\"\\n'
           '    fi\\n')


def main():
    proj, editor = sys.argv[1], sys.argv[2]
    il2cpp = os.path.join(editor, "Data/il2cpp/build/deploy")
    if not os.path.isfile(os.path.join(il2cpp, "il2cpp")):
        sys.exit("unity: no Linux IL2CPP in %s" % il2cpp)
    build = os.path.join(proj, "Il2CppOutputProject/IL2CPP/build")
    dst = os.path.join(build, "deploy_%s" % platform.machine())
    if os.path.islink(dst) or os.path.exists(dst):
        shutil.rmtree(dst) if not os.path.islink(dst) else os.remove(dst)
    os.symlink(il2cpp, dst)
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), "libtool"),
                os.path.join(proj, "Il2CppOutputProject/linux-libtool"))
    pbx = os.path.join(proj, "Unity-iPhone.xcodeproj/project.pbxproj")
    s = open(pbx).read()
    # the ABI check reads the linked framework: say so, for Swift Build's ordering
    abi = re.search(r'(isa = PBXShellScriptBuildPhase;\s*buildActionMask = \d+;\s*files = \(\s*\);)(\s*name = "Check Unity Framework ABI";)', s)
    if abi and "inputPaths" not in s[abi.start():abi.end() + 200]:
        s = s[:abi.end(1)] + '\n\t\t\tinputPaths = (\n\t\t\t\t"$(BUILT_PRODUCTS_DIR)/UnityFramework.framework/UnityFramework",\n\t\t\t);' + s[abi.end(1):]
        open(pbx + ".tmp", "w").write(s)
        os.replace(pbx + ".tmp", pbx)
    if "shells/unity/fix-project.py" not in s:
        if ANCHOR not in s:
            sys.exit("unity: the GameAssembly script phase is not the one this knows (no SDKROOT check)")
        s = s.replace(ANCHOR, OVERLAY + ANCHOR, 1)
        open(pbx + ".tmp", "w").write(s)
        os.replace(pbx + ".tmp", pbx)
    tbd = os.path.join(proj, "validate-tbd.sh")
    if os.path.isfile(tbd):
        t = open(tbd).read()
        old = 'FRAMEWORK_SYMBOLS=$(nm -arch'
        if old in t:
            t = t.replace(old, 'NM=nm; [ "$(uname -s)" = Linux ] && NM=$(command -v llvm-nm || echo /usr/lib/swift/usr/bin/llvm-nm)\n'
                          'FRAMEWORK_SYMBOLS=$($NM -arch', 1)
            open(tbd, "w").write(t)
    print("unity: IL2CPP for Linux in %s; libtool stand-in in the IL2CPP script phase" % os.path.relpath(dst, proj))


if __name__ == "__main__":
    main()
