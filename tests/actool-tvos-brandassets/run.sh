#!/usr/bin/env bash
# tvOS .brandassets (layered App Icon + Top Shelf) through the Linux actool, against
# Apple's actool 27.2.
#
# mkstack.py writes a catalog whose brandassets set "Icon" holds an image stack "App Icon":
# a 400x240 back layer and a smaller 200x120 front layer (so the layer frame offset is
# exercised). two.golden-actool-27.2.txt is normalize.py's text of the car Apple's actool
# 27.2 (Xcode 27.2, macOS 27.0) wrote for it:
#   actool Assets.xcassets --compile out --platform appletvos --minimum-deployment-target 18.0
#          --target-device tv --app-icon Icon --output-partial-info-plist out/p.plist
# and two.partial-actool-27.2.plist its partial Info.plist. The comparison covers every
# rendition's name, key, CSI header and TVL blocks (the image stack's layer references,
# flattened and radiosity images); pixel bodies and identifier values are left out.
set -uo pipefail
here=$(dirname "$(readlink -f "$0")")
repo=$here/../..
actool="${ACTOOL:-$repo/tools/darwin-tools/.build/release/actool}"
if [ ! -x "$actool" ]; then
  echo "SKIP  actool-tvos-brandassets: build tools/darwin-tools first (swift build -c release --product actool)"
  exit 0
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 -I "$here/mkstack.py" "$tmp" >/dev/null
mkdir -p "$tmp/out"
if ! "$actool" "$tmp/two/Assets.xcassets" --compile "$tmp/out" --platform appletvos \
     --minimum-deployment-target 18.0 --target-device tv --app-icon Icon \
     --output-partial-info-plist "$tmp/out/p.plist" > "$tmp/log" 2>&1; then
  echo "FAIL actool"; sed 's/^/  /' "$tmp/log"; exit 1
fi
fail=0
if grep -qi "not supported\|skipp" "$tmp/log"; then
  echo "FAIL actool skipped part of the catalog:"; sed 's/^/  /' "$tmp/log"; fail=1
fi
if python3 -I - "$here/two.partial-actool-27.2.plist" "$tmp/out/p.plist" <<'PY'
import plistlib, sys
want, got = (plistlib.load(open(p, "rb")) for p in sys.argv[1:3])
sys.exit(0 if want == got else 1)
PY
then
  echo "ok   partial Info.plist matches actool 27.2 (CFBundlePrimaryIcon)"
else
  echo "FAIL partial Info.plist differs from actool 27.2"; fail=1
fi
python3 -I "$here/normalize.py" "$tmp/out/Assets.car" > "$tmp/ours.txt"
if diff -u "$here/two.golden-actool-27.2.txt" "$tmp/ours.txt" > "$tmp/diff"; then
  echo "ok   image stack, flattened, radiosity and layer renditions match actool 27.2 ($(grep -vc '^ ' "$tmp/ours.txt") renditions)"
else
  echo "FAIL renditions differ from actool 27.2:"; head -40 "$tmp/diff" | sed 's/^/  /'; fail=1
fi
if problems=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import car_check; p = car_check.check_car(open(sys.argv[2], "rb").read()); print("\n".join(p)); sys.exit(1 if p else 0)' \
     "$repo/tools" "$tmp/out/Assets.car"); then
  echo "ok   car_check: BITMAPKEYS and image blocks"
else
  echo "FAIL car_check:"; echo "$problems" | sed 's/^/  /'; fail=1
fi
exit "$fail"
