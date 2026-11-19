#!/usr/bin/env bash
# One SwiftUI app (DeviceTest: platform, model, OS version, a tap counter) built for every
# simulator target, and optionally run in x86Sim's simulators.
#
# Always: `xtool dev build` for arm64-apple-{ios,tvos,watchos,xros}-simulator, then checks
# CFBundleSupportedPlatforms / DTPlatformName and the binary's LC_BUILD_VERSION platform.
# The watchOS build must be watch-only (WKWatchOnly): installd refuses a watch app with
# neither WKWatchOnly nor WKCompanionAppBundleIdentifier.
#
# With X86SIM_ROOT (an x86sim checkout) and X86SIM_DEVICES ("ios=var/device-a64
# tvos=var/device-a64-apple-tv watchos=var/device-a64-watch xros=var/device-a64-vision",
# any subset), each device is booted, the build installed and launched, a screenshot
# written to $OUT_DIR (default ./sim-screens), the app uninstalled and the device stopped.
# Checked 2026-11-19 with x86sim on iOS, iPadOS, tvOS and watchOS 27.2; the visionOS 27.2
# simulator did not reach its home screen in x86Sim (backboardd and wakeboardd crashing).
set -uo pipefail
here=$(dirname "$(readlink -f "$0")")
sdk_bundle="${XDG_CONFIG_HOME:+$XDG_CONFIG_HOME/swiftpm}"
sdk_bundle="${sdk_bundle:-$HOME/.swiftpm}/swift-sdks/darwin.artifactbundle"
if ! command -v xtool >/dev/null || ! grep -q '"arm64-apple-xros-simulator"' "$sdk_bundle/swift-sdk.json" 2>/dev/null; then
  echo "SKIP  simulators: needs xtool and a Darwin SDK with the simulator platforms (epoch 6)"
  exit 0
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -r "$here/DeviceTest" "$tmp/"
cd "$tmp/DeviceTest" || exit 1
declare -A want=(
  [ios]="iPhoneSimulator iphonesimulator iossimulator"
  [tvos]="AppleTVSimulator appletvsimulator tvossimulator"
  [watchos]="WatchSimulator watchsimulator watchossimulator"
  [xros]="XRSimulator xrsimulator xrsimulator"
)
fail=0
for os in ios tvos watchos xros; do
  triple=arm64-apple-$os-simulator
  rm -rf xtool/DeviceTest.app
  if ! xtool dev build -c release --triple "$triple" > "$tmp/$os.log" 2>&1; then
    echo "FAIL $triple build"; grep -i error "$tmp/$os.log" | head -5 | sed 's/^/  /'; fail=1; continue
  fi
  mkdir -p "$tmp/out/$os"
  cp -r xtool/DeviceTest.app "$tmp/out/$os/"
  app=$tmp/out/$os/DeviceTest.app
  read -r plat dt lc <<< "${want[$os]}"
  got=$(python3 -I - "$app/Info.plist" <<'PY'
import plistlib, sys
d = plistlib.load(open(sys.argv[1], "rb"))
print(d["CFBundleSupportedPlatforms"][0], d.get("DTPlatformName"), d.get("WKWatchOnly", "-"))
PY
)
  binplat=$(llvm-objdump --macho --private-headers "$app/DeviceTest" 2>/dev/null | awk '/LC_BUILD_VERSION/{f=1} f&&/platform/{print $2; exit}')
  read -r gplat gdt gwatch <<< "$got"
  if [ "$gplat $gdt" != "$plat $dt" ] || { command -v llvm-objdump >/dev/null && [ "$binplat" != "$lc" ]; }; then
    echo "FAIL $triple: Info.plist $gplat $gdt, binary $binplat (want $plat $dt $lc)"; fail=1; continue
  fi
  if [ "$os" = watchos ] && [ "$gwatch" != True ]; then
    echo "FAIL $triple: no WKWatchOnly (installd refuses a watch app without a companion)"; fail=1; continue
  fi
  echo "ok   $triple: $gplat, $gdt, binary $binplat"
done
if [ -n "${X86SIM_ROOT:-}" ] && [ -n "${X86SIM_DEVICES:-}" ]; then
  out=${OUT_DIR:-$PWD/sim-screens}
  mkdir -p "$out"
  for pair in $X86SIM_DEVICES; do
    os=${pair%%=*} dev=${pair#*=}
    [ -d "$tmp/out/$os" ] || continue
    UNINSTALL=1 bash "$here/sim-run.sh" "$dev" "$tmp/out/$os/DeviceTest.app" com.designgears.devicetest \
      "$out/$os-$(basename "$dev").png" 2 | sed 's/^/  /'
    [ -f "$out/$os-$(basename "$dev").png" ] || fail=1
  done
fi
exit "$fail"
