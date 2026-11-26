#!/usr/bin/env bash
# Tuist's manifest library on Linux: Tuist runs on macOS only, but the library its manifests (Project.swift,
# Workspace.swift) are written against, ProjectDescription, is plain Swift. This builds it from the pinned Tuist
# release with the Linux Swift toolchain as a shared library; tuist/bin/tuist compiles and runs the manifests against
# it, as Tuist does, and writes the project with XcodeGen (xcodegen/install.sh).
#
#   tuist/install.sh            build and install (idempotent; ~30 s, 10 MB kept)
#   tuist/install.sh --check    print the installed version and exit 0 when it is ready
#
# Where: $OAD_TUIST_DIR (default ~/.local/share/omarchy-apple-dev/tuist)/tuist-<version>/{lib,modules}, with `current`
# pointing at it.
set -euo pipefail
VERSION=4.218.5
COMMIT=d6ea260c244b3221900880ccfbd4a5c081c85a31
root=${OAD_TUIST_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/tuist}
dest=$root/tuist-$VERSION

if [ "${1:-}" = --check ]; then
  [ -f "$root/current/lib/libProjectDescription.so" ] || { echo "tuist: not installed (tuist/install.sh)"; exit 1; }
  echo "tuist $(cat "$root/current/version") (ProjectDescription for Linux, projects written by XcodeGen)"
  exit 0
fi
command -v swift >/dev/null || { echo "tuist: needs the Linux Swift toolchain (install-toolchain.sh)" >&2; exit 1; }

if [ ! -f "$dest/lib/libProjectDescription.so" ]; then
  mkdir -p "$root"
  src=$(mktemp -d "$root/.build.XXXXXX")
  trap 'rm -rf "$src"' EXIT
  echo "== tuist: fetch ProjectDescription $VERSION"
  git init -q "$src/tuist"
  git -C "$src/tuist" sparse-checkout set --no-cone /cli/Sources/ProjectDescription
  git -C "$src/tuist" fetch -q --depth 1 https://github.com/tuist/tuist "refs/tags/$VERSION"
  [ "$(git -C "$src/tuist" rev-parse FETCH_HEAD^{commit})" = "$COMMIT" ] || { echo "tuist: $VERSION is not $COMMIT" >&2; exit 1; }
  git -C "$src/tuist" -c advice.detachedHead=false checkout -q FETCH_HEAD
  mkdir -p "$src/pd/Sources"
  cp -a "$src/tuist/cli/Sources/ProjectDescription" "$src/pd/Sources/"
  rm -rf "$src/pd/Sources/ProjectDescription/ProjectDescription.docc" "$src/pd/Sources/ProjectDescription/AGENTS.md"
  cat >"$src/pd/Package.swift" <<'P'
// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "ProjectDescription",
    products: [.library(name: "ProjectDescription", type: .dynamic, targets: ["ProjectDescription"])],
    targets: [.target(name: "ProjectDescription")]
)
P
  echo "== tuist: build ProjectDescription"
  (cd "$src/pd" && nice swift build -c release -j "${OAD_JOBS:-4}")
  bin=$(cd "$src/pd" && swift build -c release --show-bin-path)
  mkdir -p "$dest.tmp/lib" "$dest.tmp/modules"
  cp "$bin/libProjectDescription.so" "$dest.tmp/lib/"
  # the module: next to the library (Swift Build) or in Modules/ (SwiftPM's native build)
  mod=$bin/ProjectDescription.swiftmodule
  [ -e "$mod" ] || mod=$bin/Modules/ProjectDescription.swiftmodule
  cp -R "$mod" "$dest.tmp/modules/"
  echo "$VERSION" >"$dest.tmp/version"
  rm -rf "$dest"
  mv "$dest.tmp" "$dest"
fi
ln -sfn "tuist-$VERSION" "$root/current"
echo "tuist: ProjectDescription $VERSION in $dest (tuist/bin/tuist uses it)"
