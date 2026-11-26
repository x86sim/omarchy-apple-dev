#!/usr/bin/env bash
# A Unity project's iOS Xcode project (IL2CPP), exported by the Unity editor for Linux and made buildable on Linux:
#
#   shells/unity/build.sh PROJECT_DIR OUT_DIR [--device]
#
# Then: linux-bin/xcodebuild -project OUT_DIR/Unity-iPhone.xcodeproj -scheme Unity-iPhone \
#         -destination 'generic/platform=iOS Simulator' build        (or x86Sim's `x86sim dev build PROJECT_DIR`)
#
# Needs the Unity editor for Linux with iOS Build Support, and an activated license. Both come from Unity's CLI
# (https://unity.com/install.sh, no root): `unity install <version> -m ios --accept-eula`, then `unity auth login` (a
# browser sign-in: Unity activates Personal licenses only after one) and `unity license activate --personal`.
# UNITY_EDITOR names the editor binary; else ~/Unity/Hub/Editor/<the project's version>/Editor/Unity (where the CLI
# and Unity Hub install it). UNITY_HOME: the home directory the editor runs with (its license and settings), when that
# is not $HOME (an isolated install: HOME=DIR unity install / auth login / license activate).
#
# X86SimBuild.cs (copied into Assets/Editor for the run, removed after) exports the build settings' scenes for the
# arm64 simulator (--device: devices). fix-project.py swaps the export's macOS IL2CPP for the editor's Linux one and
# gives its script phases a libtool stand-in and llvm-nm.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
[ $# -ge 2 ] || { echo "usage: $0 PROJECT_DIR OUT_DIR [--device]" >&2; exit 2; }
proj=$(cd "$1" && pwd)
mkdir -p "$2"
out=$(cd "$2" && pwd)
dev=; [ "${3:-}" = --device ] && dev=-device
ver=$(sed -n 's/^m_EditorVersion: *//p' "$proj/ProjectSettings/ProjectVersion.txt" 2>/dev/null | head -n1)
uhome=${UNITY_HOME:-$HOME}
editor=${UNITY_EDITOR:-$uhome/Unity/Hub/Editor/$ver/Editor/Unity}
[ -x "$editor" ] || { echo "unity: no editor at $editor (unity install $ver -m ios --accept-eula, or set UNITY_EDITOR)" >&2; exit 1; }
edir=$(dirname "$editor")
[ -d "$edir/Data/PlaybackEngines/iOSSupport" ] || [ -d "$edir/../../PlaybackEngines/iOSSupport" ] ||
  ls -d "$edir"/Data/PlaybackEngines/*[Ii][Oo][Ss]* >/dev/null 2>&1 ||
  { echo "unity: the editor has no iOS Build Support (unity install-modules -v $ver -m ios)" >&2; exit 1; }
added=
if [ ! -f "$proj/Assets/Editor/X86SimBuild.cs" ]; then
  mkdir -p "$proj/Assets/Editor"
  cp "$here/X86SimBuild.cs" "$proj/Assets/Editor/X86SimBuild.cs"
  added=1
fi
cleanup() { [ -n "$added" ] && rm -f "$proj/Assets/Editor/X86SimBuild.cs" "$proj/Assets/Editor/X86SimBuild.cs.meta"; true; }
trap cleanup EXIT
log=$out.unity.log
echo "== Unity $ver: export $proj for iOS (IL2CPP${dev:+, devices}) -> $out"
rc=0
HOME=$uhome "$editor" -batchmode -quit -nographics -projectPath "$proj" -executeMethod X86SimBuild.IOS -buildOutput "$out" $dev \
  -logFile "$log" || rc=$?
if [ $rc != 0 ] || ! grep -q "x86sim: build Succeeded" "$log"; then
  grep -E "x86sim:|[Ll]icense|error CS|Error" "$log" | grep -v "^\s*$" | tail -15 >&2
  echo "unity: the export failed (log: $log)" >&2
  exit 1
fi
python3 -I "$here/fix-project.py" "$out" "$edir"
echo "xcodeproj: $out/Unity-iPhone.xcodeproj"
