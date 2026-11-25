#!/usr/bin/env bash
# Build the iOS app of a Kotlin Multiplatform project on Linux in one step: the
# shared framework (kmp/build-framework.sh), then the xtool app around it
# (ship.sh), then the Compose resources into the .app.
#
#   kmp/build-app.sh [--simulator | --device [TEAMID]] [app dir]
#
# Run in (or given) the xtool project of the app: Package.swift + xtool.yml,
# with the framework declared as a binary target
#   .binaryTarget(name: "Shared", path: "Frameworks/Shared.xcframework")
# and its xtool.env saying where the Gradle build is:
#   KMP_GRADLE_ROOT=..          the Gradle root (has gradlew), relative to the app
#   KMP_MODULE=:shared          the module declaring binaries.framework
#   KMP_FRAMEWORK=Shared        the framework's base name (default: Shared)
# --simulator (the default) builds for the iOS Simulator (an x86Sim phone),
# --device for an iPhone (ship.sh --device, then `xtool install`).
#
# The framework is linked again only when a source of the Gradle build (a .kt,
# .kts, .gradle, .properties or .toml file, or a Compose resource) is newer than
# it, as linking takes minutes; KMP_FORCE=1 always links. The rest: kmp/README.md.
set -euo pipefail

here=$(dirname "$(readlink -f "$0")")
mode=--simulator team=""
while [ "$#" -gt 0 ]; do
  case "$1" in
  --simulator) mode=--simulator; shift ;;
  --device)
    mode=--device; shift
    if [ "$#" -gt 0 ] && [[ "$1" =~ ^[A-Z0-9]{10}$ ]]; then team="$1"; shift; fi
    ;;
  -h | --help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  -*) echo "kmp: unknown option $1" >&2; exit 2 ;;
  *) cd "$1"; shift ;;
  esac
done

[ -f Package.swift ] && [ -f xtool.yml ] || { echo "kmp: $(pwd) is not an xtool project (Package.swift + xtool.yml)" >&2; exit 1; }
[ -f xtool.env ] && . ./xtool.env
: "${KMP_GRADLE_ROOT:?kmp: set KMP_GRADLE_ROOT (the Gradle root, relative to the app) in xtool.env}"
KMP_MODULE="${KMP_MODULE:-:shared}" KMP_FRAMEWORK="${KMP_FRAMEWORK:-Shared}"
root="$(cd "$KMP_GRADLE_ROOT" && pwd)"
[ -x "$root/gradlew" ] || { echo "kmp: $root has no gradlew" >&2; exit 1; }

if [ "$mode" = --simulator ]; then
  target=ios_simulator_arm64 triple="${TRIPLE:-arm64-apple-ios-simulator}"
else
  target=ios_arm64 triple="${TRIPLE:-arm64-apple-ios}"
fi
case "$triple" in
arm64-apple-ios | arm64-apple-ios-simulator) ;;
*) echo "kmp: iOS only (TRIPLE $triple): build-framework.sh links ios_arm64 and ios_simulator_arm64" >&2; exit 2 ;;
esac

# The module's build dir: <root>/<module path>/build (a project with another buildDir: --out is not read back)
module_dir="$root/$(tr ':' '/' <<<"${KMP_MODULE#:}")"
out="$module_dir/build/omarchy-kmp/$target"
xc="$out/$KMP_FRAMEWORK.xcframework"

stale=1
if [ "${KMP_FORCE:-0}" != 1 ] && [ -d "$xc" ]; then
  newer="$(find "$root" \( -name build -o -name .gradle -o -name .kotlin -o -name xtool -o -name .build -o -name Frameworks \) -prune -o \
    -type f \( -name '*.kt' -o -name '*.kts' -o -name '*.gradle' -o -name '*.properties' -o -name '*.toml' -o -path '*/composeResources/*' \) \
    -newer "$xc/Info.plist" -print -quit)"
  [ -n "$newer" ] || stale=0
fi
if [ "$stale" = 1 ]; then
  "$here/build-framework.sh" "$root" --module "$KMP_MODULE" --target "$target" --dynamic --xcframework
else
  echo "[kmp] $KMP_FRAMEWORK.xcframework for $target is up to date (KMP_FORCE=1 links it again)"
fi
[ -d "$xc" ] || { echo "kmp: no $xc after the link" >&2; exit 1; }

mkdir -p Frameworks
rm -rf "Frameworks/$KMP_FRAMEWORK.xcframework"
cp -a "$xc" Frameworks/

# ship.sh prints the .app on its last line ("simulator app ready: <app>" / "device app ready: <app>")
TRIPLE="$triple" "$here/../ship.sh" "$mode" ${team:+"$team"} | tee .kmp-ship.log
app="$(sed -n 's/^\(simulator\|device\) app ready: //p' .kmp-ship.log | tail -n 1)"
rm -f .kmp-ship.log
[ -n "$app" ] && [ -d "$app" ] || { echo "kmp: ship.sh wrote no .app" >&2; exit 1; }

# Compose Multiplatform reads its resources from compose-resources/ at the root of the .app
if [ -d "$out/compose-resources" ]; then
  rm -rf "$app/compose-resources"
  cp -a "$out/compose-resources" "$app/"
  echo "[kmp] Compose resources copied into $app/compose-resources"
fi
