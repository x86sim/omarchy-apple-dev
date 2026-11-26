#!/usr/bin/env bash
# Rust for iOS on Linux: adds the two iOS targets to the rustup toolchain and checks that a crate links with the
# Darwin SDK install-toolchain.sh registered. install-toolchain.sh runs it when rustup is installed; run it again
# after a rustup toolchain change (`rustup default ...`).
#
#   rust/setup.sh [--check]     --check: report only, add nothing (exit 1 when something is missing)
#
# Nothing global changes: builds take the linker and SDK from rust/ios-env.sh (rust/build.py sources it), not from
# ~/.cargo/config.toml.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
check=0
[ "${1:-}" = --check ] && check=1
targets=(aarch64-apple-ios-sim aarch64-apple-ios)

if ! command -v rustup >/dev/null; then
  if command -v cargo >/dev/null; then
    echo "rust: cargo without rustup ($(command -v cargo)): add the iOS standard libraries yourself (${targets[*]})" >&2
  else
    echo "rust: no Rust toolchain; install rustup (https://rustup.rs or your package manager), then re-run $0" >&2
  fi
  exit 1
fi

installed=$(rustup target list --installed)
missing=()
for t in "${targets[@]}"; do
  grep -qx "$t" <<<"$installed" || missing+=("$t")
done
if [ ${#missing[@]} -gt 0 ]; then
  if [ $check = 1 ]; then
    echo "rust: missing targets: ${missing[*]} (rustup target add ${missing[*]})" >&2
    exit 1
  fi
  echo "rust: rustup target add ${missing[*]}"
  rustup target add "${missing[@]}"
fi

# a link check: C through the wrapper, for both platforms (rustc links the same way)
. "$here/ios-sdk.sh"
work=$(mktemp -d "${XDG_CACHE_HOME:-$HOME/.cache}/rust-ios-check.XXXXXX")
trap 'rm -rf "$work"' EXIT
printf 'int main(void){return 0;}\n' >"$work/t.c"
for k in sim device; do
  ios_sdk_paths "$k"
  "$here/$IOS_RUST_TARGET-cc" "$work/t.c" -o "$work/t-$k" || { echo "rust: linking for $IOS_RUST_TARGET failed" >&2; exit 1; }
done
echo "rust: ready ($(rustc --version | cut -d' ' -f2), ${targets[*]}, SDK $(grep -o '"Version": *"[0-9.]*"' "$IOS_SDK/SDKSettings.json" | grep -o '[0-9][0-9.]*'))"
echo "rust: build an app with $here/build.py [--device] [--release] <crate dir>"
