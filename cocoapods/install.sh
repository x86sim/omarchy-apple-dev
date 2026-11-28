#!/usr/bin/env bash
# CocoaPods on Linux, user-local and pinned: Homebrew's portable Ruby (a relocatable build that runs on any glibc
# Linux, checksummed below), the gems in gems.lock at their exact versions, and a `pod` wrapper in ~/.local/bin that
# answers what Podfiles and podspec hooks ask of a Mac (cocoapods/linux.rb, cocoapods/shims, flutter/shims: xcrun,
# xcodebuild -version, codesign, the SDK paths of the Darwin SDK install-toolchain.sh registered).
#
#   cocoapods/install.sh            install or update (re-runs change nothing when everything is in place)
#   cocoapods/install.sh --check    exit 0 when the pinned set is installed, 1 when not
#
# POD_HOME (default ~/.local/share/omarchy-apple-dev/cocoapods) holds ruby/ and gems/; POD_BIN (default ~/.local/bin)
# gets the wrapper. A `pod` there that this script did not write is left alone (the wrapper goes to POD_HOME/bin).
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
fork=$(dirname "$here")
POD_HOME=${POD_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/cocoapods}
POD_BIN=${POD_BIN:-$HOME/.local/bin}

RUBY_VERSION=3.4.6
case "$(uname -m)" in
  x86_64) ruby_arch=x86_64_linux; ruby_sha=40932a3950ccc8bf9d13d98e692e5518427cc66b4f9520956cec349629d25259 ;;
  aarch64 | arm64) ruby_arch=arm64_linux; ruby_sha=8e99050efd36456f4740f1c5f048b75290dd646554b0c1b153eb831a9ae1e3e8 ;;
  *) echo "cocoapods: no portable Ruby for $(uname -m)" >&2; exit 1 ;;
esac
COCOAPODS_VERSION=$(awk '$1 == "cocoapods" {print $2}' "$here/gems.lock")
stamp="ruby $RUBY_VERSION, $(grep -v '^#' "$here/gems.lock" | sha256sum | cut -c1-16)"

installed() {
  [ -x "$POD_HOME/ruby/bin/ruby" ] && [ "$(cat "$POD_HOME/stamp" 2>/dev/null)" = "$stamp" ] &&
    [ -x "$POD_HOME/bin/pod" ]
}

if [ "${1:-}" = --check ]; then
  installed
  exit
fi

if installed; then
  echo "CocoaPods $COCOAPODS_VERSION (Ruby $RUBY_VERSION) already installed in $POD_HOME"
else
  mkdir -p "$POD_HOME"
  if [ "$("$POD_HOME/ruby/bin/ruby" -e 'print RUBY_VERSION' 2>/dev/null)" != "$RUBY_VERSION" ]; then
    echo "== Ruby $RUBY_VERSION (Homebrew portable Ruby, $ruby_arch)"
    tmp=$(mktemp -d "$POD_HOME/.dl.XXXXXX")
    trap 'rm -rf "$tmp"' EXIT
    curl -fsSL -o "$tmp/ruby.tar.gz" \
      "https://github.com/Homebrew/homebrew-portable-ruby/releases/download/$RUBY_VERSION/portable-ruby-$RUBY_VERSION.$ruby_arch.bottle.tar.gz"
    echo "$ruby_sha  $tmp/ruby.tar.gz" | sha256sum -c --quiet
    tar xzf "$tmp/ruby.tar.gz" -C "$tmp"
    rm -rf "$POD_HOME/ruby" "$POD_HOME/gems"
    mv "$tmp/portable-ruby/$RUBY_VERSION" "$POD_HOME/ruby"
    rm -rf "$tmp"
    trap - EXIT
  fi
  echo "== CocoaPods $COCOAPODS_VERSION and its gems (gems.lock)"
  export GEM_HOME="$POD_HOME/gems" GEM_PATH="$POD_HOME/gems"
  unset RUBYOPT RUBYLIB
  # bigdecimal and nkf build a native extension: cc and make (base-devel / build-essential)
  grep -v '^#' "$here/gems.lock" | while read -r name version; do
    [ -n "$name" ] || continue
    if ! "$POD_HOME/ruby/bin/gem" list -i "^$name\$" -v "$version" >/dev/null 2>&1; then
      "$POD_HOME/ruby/bin/gem" install --no-document --ignore-dependencies -v "$version" "$name" >/dev/null
      echo "   $name $version"
    fi
  done
  echo "$stamp" >"$POD_HOME/stamp"
fi
# The wrapper names this tree (linux.rb, node-linux.js): written on every run, so a re-run from a moved or another
# checkout points it there (an installed CocoaPods kept the tree it was first installed from, which then went away).
mkdir -p "$POD_HOME/bin"
sed -e "s|@POD_HOME@|$POD_HOME|g" -e "s|@FORK@|$fork|g" "$here/pod.in" >"$POD_HOME/bin/pod.new"
chmod +x "$POD_HOME/bin/pod.new"
mv -f "$POD_HOME/bin/pod.new" "$POD_HOME/bin/pod"

# The wrapper on PATH: ours (it names POD_HOME) or none at all
mkdir -p "$POD_BIN"
if [ ! -e "$POD_BIN/pod" ] || grep -q 'omarchy-apple-dev cocoapods wrapper' "$POD_BIN/pod" 2>/dev/null; then
  ln -sf "$POD_HOME/bin/pod" "$POD_BIN/pod"
  echo "pod: $POD_BIN/pod -> $POD_HOME/bin/pod"
else
  echo "pod: $POD_BIN/pod is not this install's; use $POD_HOME/bin/pod"
fi
"$POD_HOME/bin/pod" --version
