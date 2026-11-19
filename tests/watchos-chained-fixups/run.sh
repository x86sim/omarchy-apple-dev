#!/usr/bin/env bash
# arm64_32 (watchOS) chained fixups from the Darwin SDK's ld64.lld, checked against
# Apple's ld64.
#
# gap.c has two pairs of pointers 200 bytes apart (one gap of small values, one of
# floats and all-ones words), so a 32-bit chain (at most 31 * 4 bytes per link) must
# start again within the page, plus imports with an inline (+8), a large (+200) and
# a negative (-4) addend. pages.c spreads pointers over five 16 KiB pages: links of
# exactly 124 bytes, gaps of 128 (pages with many starts in the overflow list), and
# pointers on both sides of page boundaries. <name>.golden-ld64-27106.txt is
# chain32.py's decoding of the same program linked by ld64 27106.1 (Xcode 27.2,
# macOS 27.0):
#   xcrun -sdk watchos clang -target arm64_32-apple-watchos11.0 -O1 <name>.c -o <name>
# Apple's `dyld_info -fixups` reads the lld output identically.
#
# SKIPs without a WatchOS platform in the SDK or with a toolset whose lld has no
# arm64_32 chained fixups (darwinTools before 1.1.0-x86sim.2).
set -uo pipefail
here=$(dirname "$(readlink -f "$0")")
sdk_bundle="${XDG_CONFIG_HOME:+$XDG_CONFIG_HOME/swiftpm}"
sdk_bundle="${sdk_bundle:-$HOME/.swiftpm}/swift-sdks/darwin.artifactbundle"
watch_sdk="$sdk_bundle/Developer/Platforms/WatchOS.platform/Developer/SDKs/WatchOS.sdk"
lld="${LD64_LLD:-$sdk_bundle/toolset/bin/orig/ld64.lld}"
swift_bin=$(command -v swift || true)
clang="$(dirname "$(readlink -f "${swift_bin:-/nonexistent}")")/clang"

if [ ! -d "$watch_sdk" ] || [ ! -x "$lld" ] || [ ! -x "$clang" ]; then
  echo "SKIP  watchos-chained-fixups: needs the WatchOS platform in the Darwin SDK, its ld64.lld and the Swift toolchain's clang"
  exit 0
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0
for t in gap pages; do
  if ! "$clang" -target arm64_32-apple-watchos11.0 -isysroot "$watch_sdk" -O1 -mlinker-version=705 \
       --ld-path="$lld" -Wl,-fixup_chains "$here/$t.c" -o "$tmp/$t" 2>"$tmp/link.log"; then
    if grep -q "only supported on x86_64 and arm64 targets" "$tmp/link.log"; then
      echo "SKIP  watchos-chained-fixups: this ld64.lld has no arm64_32 chained fixups (toolset older than 1.1.0-x86sim.2)"
      exit 0
    fi
    echo "FAIL  link $t.c"; sed 's/^/  /' "$tmp/link.log"; fail=1; continue
  fi
  if ! python3 -I "$here/chain32.py" "$tmp/$t" > "$tmp/$t.txt"; then
    echo "FAIL  chain32.py could not decode $t"; sed 's/^/  /' "$tmp/$t.txt"; fail=1; continue
  fi
  if diff -u "$here/$t.golden-ld64-27106.txt" "$tmp/$t.txt" > "$tmp/diff"; then
    echo "ok   $t.c: arm64_32 chained fixups match ld64 27106.1 ($(grep -vc '^#' "$tmp/$t.txt") fixups)"
  else
    echo "FAIL  $t.c: arm64_32 chained fixups differ from ld64:"; head -40 "$tmp/diff" | sed 's/^/  /'; fail=1
  fi
done
exit "$fail"
