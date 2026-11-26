#!/usr/bin/env bash
# A Godot 4 project exported for iOS on Linux: the official Linux editor, headless, with the official iOS export
# template, writes the Xcode project (its "export project only" mode: building the .ipa is the only step Godot keeps
# for macOS). The Xcode project then builds with Swift Build (linux-bin/xcodebuild).
#
#   shells/godot/export.sh PROJECT_DIR OUT_DIR [PRESET]     export PRESET (default: the project's iOS preset) into OUT_DIR
#   shells/godot/export.sh --install                        only download the editor and the iOS template
#
# The editor and templates are Godot's own release files (no account), checked against the release's SHA512-SUMS:
# $OAD_GODOT_DIR (default ~/.local/share/omarchy-apple-dev/godot)/<version>/: the editor in self-contained mode
# (its settings stay there) and templates/ios.zip only (the 1.2 GB template archive is deleted after). GODOT_VERSION
# picks the release (default below); it must match the project's 4.x minor closely enough to open it.
#
# The template's iOS-simulator library is x86_64 only (Godot 4.7.2: 2292 x86_64 objects, no arm64), which no arm64
# simulator runs (Apple's iOS 27 simulator refuses x86_64 apps). Build the exported project for iOS devices (arm64,
# unsigned): x86Sim converts a device app for its simulator at install. Godot's Metal renderers need Apple3-family GPU
# features that the simulator's Metal (Apple's, and x86Sim's, which mirrors it) does not have: use the Compatibility
# renderer (rendering/renderer/rendering_method.mobile="gl_compatibility") for simulator runs.
set -euo pipefail
VERSION=${GODOT_VERSION:-4.7.2}
root=${OAD_GODOT_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/godot}/$VERSION
case $(uname -m) in x86_64) arch=x86_64 ;; arm64 | aarch64) arch=arm64 ;; *) echo "godot: no Linux editor for $(uname -m)" >&2; exit 1 ;; esac
editor=$root/Godot_v$VERSION-stable_linux.$arch
templates=$root/editor_data/export_templates/$VERSION.stable

install() {
  [ -x "$editor" ] && [ -f "$templates/ios.zip" ] && return 0
  local url=https://github.com/godotengine/godot/releases/download/$VERSION-stable
  mkdir -p "$root"
  local tmp; tmp=$(mktemp -d "$root/.download.XXXXXX")
  trap 'rm -rf "$tmp"' RETURN
  echo "== Godot $VERSION: editor and iOS export template (about 1.3 GB download, 350 MB kept)"
  curl -fsSL --retry 3 -o "$tmp/SHA512-SUMS.txt" "$url/SHA512-SUMS.txt"
  for f in "Godot_v$VERSION-stable_linux.$arch.zip" "Godot_v$VERSION-stable_export_templates.tpz"; do
    curl -fL --retry 3 -o "$tmp/$f" "$url/$f"
    (cd "$tmp" && grep " $f\$" SHA512-SUMS.txt | sha512sum -c - >/dev/null) || { echo "godot: checksum mismatch for $f" >&2; exit 1; }
  done
  unzip -q -o "$tmp/Godot_v$VERSION-stable_linux.$arch.zip" -d "$root"
  touch "$root/._sc_" # self-contained: editor settings and templates under $root
  mkdir -p "$templates"
  unzip -q -o -j "$tmp/Godot_v$VERSION-stable_export_templates.tpz" templates/ios.zip templates/version.txt -d "$templates"
}

install
[ "${1:-}" = --install ] && { echo "$editor"; exit 0; }
[ $# -ge 2 ] || { echo "usage: $0 PROJECT_DIR OUT_DIR [PRESET] | --install" >&2; exit 2; }
proj=$(cd "$1" && pwd)
mkdir -p "$2"
out=$(cd "$2" && pwd)
[ -f "$proj/project.godot" ] || { echo "godot: no project.godot in $proj" >&2; exit 1; }
preset=${3:-}
if [ -z "$preset" ]; then
  # the first preset whose platform is iOS
  preset=$(awk -F'"' '/^name=/{n=$2} /^platform="iOS"/{print n; exit}' "$proj/export_presets.cfg" 2>/dev/null || true)
fi
[ -n "$preset" ] || { echo "godot: no iOS export preset in $proj/export_presets.cfg (add one in the editor: Project > Export > iOS)" >&2; exit 1; }
name=$(sed -n 's/^config\/name="\(.*\)"/\1/p' "$proj/project.godot" | head -n1 | tr -c 'A-Za-z0-9_\n' '_')
name=${name:-app}
# an export dir inside the project must not be imported as project files
case "$out/" in "$proj"/*) touch "$out/.gdignore" ;; esac
echo "== Godot $VERSION: import $proj"
"$editor" --headless --path "$proj" --import >/dev/null 2>&1 || true
echo "== Godot $VERSION: export \"$preset\" to $out (Xcode project)"
log=$out/export.log
# Godot returns non-zero when only the .ipa step (macOS) was skipped; the Xcode project is what counts
"$editor" --headless --path "$proj" --export-debug "$preset" "$out/$name.ipa" >"$log" 2>&1 || true
grep -E '^(ERROR|WARNING)' "$log" | grep -v '\.ipa can only be built on macOS' >&2 || true
ls -d "$out"/*.xcodeproj >/dev/null 2>&1 || { echo "godot: the export wrote no Xcode project (log: $log)" >&2; exit 1; }
echo "xcodeproj: $(ls -d "$out"/*.xcodeproj | head -n1)"
