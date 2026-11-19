#!/usr/bin/env bash
# SwiftBuild passes --leaderboard-identifier-prefix and --leaderboard-set-identifier-prefix to
# actool for tvOS targets (Game Center identifiers). The Linux actool must take each as a
# flag with a value; it used to read the prefix as a catalog path and fail the build.
set -uo pipefail
here=$(dirname "$(readlink -f "$0")")
repo=$here/../..
actool="${ACTOOL:-$repo/tools/darwin-tools/.build/release/actool}"
if [ ! -x "$actool" ]; then
  echo "SKIP  actool-tvos-flags: build tools/darwin-tools first (swift build -c release --product actool)"
  exit 0
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/Assets.xcassets" "$tmp/out"
printf '{"info":{"author":"xcode","version":1}}' > "$tmp/Assets.xcassets/Contents.json"
if "$actool" "$tmp/Assets.xcassets" --compile "$tmp/out" --platform appletvos \
     --minimum-deployment-target 18.0 --target-device tv \
     --leaderboard-identifier-prefix com.example.app \
     --leaderboard-set-identifier-prefix com.example.app \
     --output-partial-info-plist "$tmp/out/partial.plist" > "$tmp/log" 2>&1; then
  echo "ok   actool takes the tvOS leaderboard prefix flags"
else
  echo "FAIL actool rejected the tvOS leaderboard prefix flags"; sed 's/^/  /' "$tmp/log"; exit 1
fi
