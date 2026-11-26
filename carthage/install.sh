#!/usr/bin/env bash
# Build Carthage on Linux with the Linux Swift toolchain: Carthage 0.40.0 (pinned by its commit) and its pinned
# dependencies, with carthage/patches/ (macOS-only APIs: Launch Services type identifiers, copyfile, CommonCrypto,
# MachO headers, KVC, atexit_b, FoundationNetworking imports; a URLSession that lives for the whole run; Linux
# `swift --version` output). carthage/bin/carthage runs it with Linux stand-ins for the Xcode tools it calls.
#
#   carthage/install.sh            build and install (idempotent; ~2 min, ~600 MB while building, 12 MB kept)
#   carthage/install.sh --check    print the installed version and exit 0 when it is ready
#
# Where: $OAD_CARTHAGE_DIR (default ~/.local/share/omarchy-apple-dev/carthage)/carthage-<version>/carthage, with
# `current` pointing at it.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
VERSION=0.40.0
COMMIT=e33e133a5427129b38bfb1ae18d8f56b29a93204
root=${OAD_CARTHAGE_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/carthage}
dest=$root/carthage-$VERSION

if [ "${1:-}" = --check ]; then
  [ -x "$root/current/carthage" ] || { echo "carthage: not installed (carthage/install.sh)"; exit 1; }
  echo "carthage $("$root/current/carthage" version 2>/dev/null)"
  exit 0
fi
command -v swift >/dev/null || { echo "carthage: needs the Linux Swift toolchain (install-toolchain.sh)" >&2; exit 1; }

if [ ! -x "$dest/carthage" ]; then
  mkdir -p "$root"
  src=$(mktemp -d "$root/.build.XXXXXX")
  trap 'rm -rf "$src"' EXIT
  echo "== carthage: fetch $VERSION"
  git -c advice.detachedHead=false clone -q --depth 1 -b "$VERSION" https://github.com/Carthage/Carthage "$src/Carthage"
  [ "$(git -C "$src/Carthage" rev-parse HEAD)" = "$COMMIT" ] || { echo "carthage: $VERSION is not commit $COMMIT" >&2; exit 1; }
  cd "$src/Carthage"
  swift package resolve
  echo "== carthage: patch for Linux"
  git apply "$here/patches/Carthage.patch"
  chmod -R u+w .build/checkouts
  for dep in ReactiveSwift ReactiveTask Tentacle; do
    git -C ".build/checkouts/$dep" apply "$here/patches/$dep.patch"
  done
  echo "== carthage: build"
  nice swift build -c release -j "${OAD_JOBS:-4}" --product carthage
  mkdir -p "$dest.tmp"
  cp "$(swift build -c release --show-bin-path)/carthage" "$dest.tmp/carthage"
  rm -rf "$dest"
  mv "$dest.tmp" "$dest"
fi
ln -sfn "carthage-$VERSION" "$root/current"
echo "carthage: $dest/carthage $("$dest/carthage" version) (carthage/bin/carthage runs it)"
