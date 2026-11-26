#!/usr/bin/env bash
# Build XcodeGen (project.yml -> .xcodeproj) on Linux with the Linux Swift toolchain: XcodeGen is a Swift package that
# builds and runs here unchanged. Pinned by its release commit.
#
#   xcodegen/install.sh            build and install (idempotent; ~1 min, ~500 MB while building, 30 MB kept)
#   xcodegen/install.sh --check    print the installed version and exit 0 when it is ready
#
# Where: $OAD_XCODEGEN_DIR (default ~/.local/share/omarchy-apple-dev/xcodegen)/xcodegen-<version>/ (the binary and
# its SettingPresets resource bundle), with `current` pointing at it; xcodegen/bin/xcodegen runs it.
set -euo pipefail
VERSION=2.49.0
COMMIT=45ad520d50c26f42b0f4e823e8dd5e18e3ae27c9
root=${OAD_XCODEGEN_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/xcodegen}
dest=$root/xcodegen-$VERSION

if [ "${1:-}" = --check ]; then
  [ -x "$root/current/xcodegen" ] || { echo "xcodegen: not installed (xcodegen/install.sh)"; exit 1; }
  echo "xcodegen $("$root/current/xcodegen" version 2>/dev/null | sed 's/^Version: //')"
  exit 0
fi
command -v swift >/dev/null || { echo "xcodegen: needs the Linux Swift toolchain (install-toolchain.sh)" >&2; exit 1; }

if [ ! -x "$dest/xcodegen" ]; then
  mkdir -p "$root"
  src=$(mktemp -d "$root/.build.XXXXXX")
  trap 'rm -rf "$src"' EXIT
  echo "== xcodegen: fetch $VERSION"
  git -c advice.detachedHead=false clone -q --depth 1 -b "$VERSION" https://github.com/yonaskolb/XcodeGen "$src/XcodeGen"
  [ "$(git -C "$src/XcodeGen" rev-parse HEAD)" = "$COMMIT" ] || { echo "xcodegen: $VERSION is not commit $COMMIT" >&2; exit 1; }
  cd "$src/XcodeGen"
  echo "== xcodegen: build"
  nice swift build -c release -j "${OAD_JOBS:-4}" --product xcodegen
  bin=$(swift build -c release --show-bin-path)
  mkdir -p "$dest.tmp"
  cp "$bin/xcodegen" "$dest.tmp/"
  cp -R "$bin"/XcodeGen_*.bundle "$dest.tmp/"
  rm -rf "$dest"
  mv "$dest.tmp" "$dest"
fi
ln -sfn "xcodegen-$VERSION" "$root/current"
echo "xcodegen: $dest/xcodegen $("$dest/xcodegen" version) (xcodegen/bin/xcodegen runs it)"
