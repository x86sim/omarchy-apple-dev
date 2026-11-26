#!/usr/bin/env bash
# Install the Xcode-project build engine: Apple's open-source Swift Build (Xcode's own build system), driven by
# sweetpad's Linux CLI, which turns an .xcodeproj / .xcworkspace into Swift Build's project model and stands in for the
# Xcode tools Linux lacks. Both are open source (Swift Build: Apache 2.0, sweetpad: MIT) and the release archive is
# built on Linux by sweetpad's CI; this pins one version by its SHA-256.
#
#   swiftbuild/install.sh            install (idempotent) and complete the darwin SDK bundle for it
#   swiftbuild/install.sh --check    print the installed sweetpad and exit 0 when it is ready
#
# Where: $OAD_SWIFTBUILD_DIR (default ~/.local/share/omarchy-apple-dev/swiftbuild)/sweetpad-<version>, with `current`
# pointing at it. linux-bin/xcodebuild and x86Sim's `x86sim dev` find it there.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
VERSION=0.1.29
case $(uname -m) in
  x86_64) arch=x64; sha=98a79be69c11670fc5ed053e5f6ea8cfbd52d0a0e44666309b9661bfdc3b2b96 ;;
  aarch64 | arm64) arch=arm64; sha=6dcd20f8d021fc52c490b8f5a6da804cf1e696219eed1206d511b0704135ff86 ;;
  *) echo "swiftbuild: no sweetpad build for $(uname -m)" >&2; exit 1 ;;
esac
root=${OAD_SWIFTBUILD_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/swiftbuild}
dest=$root/sweetpad-$VERSION
bundle=${DARWIN_SDK_BUNDLE:-}
if [ -z "$bundle" ]; then
  for b in "${XDG_CONFIG_HOME:-$HOME/.config}/swiftpm/swift-sdks/darwin.artifactbundle" "$HOME/.swiftpm/swift-sdks/darwin.artifactbundle"; do
    [ -d "$b" ] && { bundle=$b; break; }
  done
fi

if [ "${1:-}" = --check ]; then
  [ -x "$root/current/sweetpad" ] || { echo "swiftbuild: not installed (swiftbuild/install.sh)"; exit 1; }
  "$root/current/sweetpad" --version
  exit 0
fi

if [ ! -x "$dest/sweetpad" ]; then
  url=https://github.com/sweetpad-dev/sweetpad/releases/download/cli-v$VERSION/sweetpad-cli-$VERSION-linux-$arch.tar.gz
  mkdir -p "$root"
  tmp=$(mktemp -d "$root/.download.XXXXXX")
  trap 'rm -rf "$tmp"' EXIT
  echo "== download sweetpad $VERSION for linux-$arch"
  curl -fL --retry 3 -o "$tmp/sp.tgz" "$url"
  echo "$sha  $tmp/sp.tgz" | sha256sum -c - >/dev/null || { echo "swiftbuild: checksum mismatch for $url" >&2; exit 1; }
  mkdir "$tmp/x"
  tar -xzf "$tmp/sp.tgz" -C "$tmp/x"
  rm -rf "$dest"
  mv "$tmp/x" "$dest"
fi
ln -sfn "sweetpad-$VERSION" "$root/current"
# problem reports to sweetpad's maintainer go out only on an explicit `sweetpad feedback`; switch them off anyway
"$dest/sweetpad" feedback off >/dev/null 2>&1 || true

# What Swift Build looks for in the SDK bundle besides what xtool puts there: Xcode's version.plist, the Swift
# toolchain's <swift/bridging> headers, and lib/swift/clang (the resource dir Xcode's swiftc uses for clang headers).
if [ -n "$bundle" ] && [ -d "$bundle/Developer" ]; then
  tc=$bundle/Developer/Toolchains/XcodeDefault.xctoolchain
  if [ ! -e "$bundle/version.plist" ]; then
    v=$(ls "$HOME"/.cache/xtool/darwin-*.xtoolsdk.version.plist 2>/dev/null | tail -n1 || true)
    if [ -n "$v" ]; then cp "$v" "$bundle/version.plist"; fi
  fi
  swift_inc=$(dirname "$(readlink -f "$(command -v swift)")")/../include/swift
  if [ ! -e "$tc/usr/include/swift/bridging" ] && [ -e "$swift_inc/bridging" ]; then
    mkdir -p "$tc/usr/include"
    [ -e "$tc/usr/include/swift" ] || ln -s "$(readlink -f "$swift_inc")" "$tc/usr/include/swift"
  fi
  if [ ! -e "$tc/usr/lib/swift/clang" ]; then
    clangv=$(ls -d "$tc"/usr/lib/clang/[0-9]* 2>/dev/null | sort -V | head -n1 || true)
    [ -n "$clangv" ] && ln -s "../clang/$(basename "$clangv")" "$tc/usr/lib/swift/clang"
  fi
fi
# The SDK's ibtool (install-toolchain.sh copies the fork's tools/ibtool into every platform) sends what it refuses to
# sweetpad's ibtool; Swift Build runs it without our environment, so it finds sweetpad through a link next to it.
# A copy older than this checkout's (no fallback) is replaced.
if [ -n "$bundle" ] && [ -d "$bundle/Developer/Platforms" ]; then
  for pbin in "$bundle"/Developer/Platforms/*.platform/Developer/usr/bin; do
    [ -f "$pbin/ibtool" ] || continue
    if ! cmp -s "$here/../tools/ibtool" "$pbin/ibtool"; then
      install -m755 "$here/../tools/ibtool" "$pbin/ibtool"
      install -m644 "$here/../tools/nibarchive.py" "$here/../tools/keyorder.py" "$pbin/"
      [ ! -f "$pbin/ibmac.py" ] || install -m644 "$here/../tools/ibmac.py" "$pbin/"
    fi
    ln -sfn "$root/current/sweetpad" "$pbin/sweetpad"
  done
fi
SWEETPAD_DARWIN_SDK=${bundle:-} "$dest/sweetpad" doctor 2>&1 | grep -E '^\[(ok|fail)\] (Swift Build|Darwin SDK|arm64-apple-ios)' || true
echo "swiftbuild: $dest (linux-bin/xcodebuild uses it)"
