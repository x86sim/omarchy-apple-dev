#!/usr/bin/env bash
# NativeScript's iOS metadata generator, built on Linux. The NativeScript iOS runtime ships objc-metadata-generator
# only as a macOS binary; an app's link step runs it (internal/nsld.sh) to turn the SDK's headers into the metadata
# its JavaScript calls native code through. Its source (NativeScript/ios, metadata-generator/: C++ on clang's tooling
# libraries) builds against the system's clang and LLVM with metadata-generator-clang22.patch (clang 22 removed
# ElaboratedType; Module headers, StringRef and ObjCMethodDecl APIs moved).
#
#   shells/nativescript/build-metadata-generator.sh            build once (idempotent); prints the bin directory
#   shells/nativescript/build-metadata-generator.sh --check    exit 0 when it is built
#
# Needs: git, clang++ and the clang / LLVM development files (Arch: clang, llvm; Debian/Ubuntu: libclang-dev,
# llvm-dev), libxml2. Where: $OAD_NATIVESCRIPT_DIR (default ~/.local/share/omarchy-apple-dev/nativescript)/
# metadata-generator-<commit>/bin, next to lib/clang/<version> (the system clang's built-in headers, which clang's
# libraries look for beside the binary).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
COMMIT=1947334ef7400d05eba37982ac21c50cda5e1688 # NativeScript/ios main, 2026-11-25 (runtime 9.1)
root=${OAD_NATIVESCRIPT_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/nativescript}
dest=$root/metadata-generator-${COMMIT:0:12}
if [ -x "$dest/bin/objc-metadata-generator" ]; then
  echo "$dest/bin"
  exit 0
fi
[ "${1:-}" = --check ] && { echo "nativescript: the metadata generator is not built ($0)" >&2; exit 1; }

cxx=${CXX:-clang++}
command -v "$cxx" >/dev/null || { echo "nativescript: $cxx not found (clang and the clang/LLVM development files)" >&2; exit 1; }
resource=$(clang -print-resource-dir)
inc=$(llvm-config --includedir 2>/dev/null || echo /usr/include)
libdir=$(llvm-config --libdir 2>/dev/null || echo /usr/lib)
[ -f "$inc/clang/Tooling/Tooling.h" ] ||
  { echo "nativescript: clang's development headers are missing ($inc/clang/Tooling/Tooling.h)" >&2; exit 1; }

mkdir -p "$root"
work=$(mktemp -d "$root/.build.XXXXXX")
trap 'rm -rf "$work"' EXIT
echo "== NativeScript/ios ${COMMIT:0:12}: metadata-generator"
git -C "$work" init -q src
git -C "$work/src" remote add origin https://github.com/NativeScript/ios.git
git -C "$work/src" sparse-checkout set metadata-generator
git -C "$work/src" fetch -q --depth 1 --filter=blob:none origin "$COMMIT"
git -C "$work/src" checkout -q FETCH_HEAD
git -C "$work/src" apply "$here/metadata-generator-clang22.patch"

src=$work/src/metadata-generator/src
mkdir -p "$work/obj" "$work/out/bin" "$work/out/lib/clang"
jobs=${JOBS:-4}
echo "== compile ($cxx, clang $(basename "$resource"))"
export cxx inc src work
find "$src" -name '*.cpp' | sort | xargs -P "$jobs" -I{} bash -c '
  o="$work/obj/$(echo "${1#$src/}" | tr / _).o"
  exec nice "$cxx" -std=c++17 -O2 -fno-rtti -c "$1" -I"$src" -I"$inc" -I/usr/include/libxml2 -o "$o"' _ {}
"$cxx" "$work"/obj/*.o -o "$work/out/bin/objc-metadata-generator" -L"$libdir" -Wl,-rpath,"$libdir" -lclang-cpp -lLLVM -lxml2
cp "$work/src/metadata-generator/build-step-metadata-generator.py" "$work/out/bin/"
# clang's libraries find their built-in headers at <binary>/../lib/clang/<version>; the build step passes -I. from
# bin/ too (bin/lib/clang/<version> in the macOS package)
ln -s "$resource" "$work/out/lib/clang/$(basename "$resource")"
mkdir -p "$work/out/bin/lib/clang" && ln -s "$resource" "$work/out/bin/lib/clang/$(basename "$resource")"
rm -rf "$dest"
mv "$work/out" "$dest"
echo "$dest/bin"
