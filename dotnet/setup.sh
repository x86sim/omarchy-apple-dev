#!/usr/bin/env bash
# Set up .NET for iOS on Linux (dotnet/README.md): a .NET SDK of its own, the iOS workload, and what the workload's
# MSBuild tasks expect of a Mac.
#   dotnet/setup.sh            once, after install-toolchain.sh (the Darwin SDK from the Xcode .xip)
# Env: OAD_DOTNET (default ~/.local/share/omarchy-apple-dev/dotnet: the SDK, the hook, the Xcode.app stand-in),
#      DOTNET_CHANNEL (10.0), IOS_MANIFEST_VERSION (default: the newest iOS workload of the Darwin SDK's version).
#
# What it does, and why:
#   1. The .NET SDK, user-local, with Microsoft's dotnet-install.sh: its workload manifests are changed (step 2), so
#      never a system SDK.
#   2. `dotnet workload install ios` refuses Linux: the Mono runtime packs of the iOS workload list Windows and macOS
#      hosts only ("platforms" in the mono toolchain manifests). Linux is added to those lists. The packs themselves
#      are host-independent (managed MSBuild tasks, the iOS runtime packs); the one host-specific piece, Mono's AOT
#      compiler, is published for macOS only and stays unavailable: apps build with NativeAOT (dotnet/build.sh),
#      whose compiler, ILCompiler, is published for Linux.
#   3. The iOS workload manifest matching the Darwin SDK (an SDK version needs that Xcode version), from NuGet,
#      checked against the SHA-512 NuGet publishes for it.
#   4. The startup hook (hook/): the tasks P/Invoke /usr/lib/libc.dylib and /usr/lib/libSystem.dylib by path;
#      it maps them to hook/macshim.c, which is glibc plus the few macOS functions glibc lacks (sysctlbyname,
#      stat$INODE64 & co with macOS's struct stat).
#   5. Xcode.app: the tasks validate an Xcode bundle (Contents/Info.plist, version.plist, MacOS/Xcode) and read the
#      platforms and toolchains under Contents/Developer: a directory of plists and links to the Darwin SDK.
set -euo pipefail

here=$(dirname "$(readlink -f "$0")")
OAD_DOTNET="${OAD_DOTNET:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/dotnet}"
DOTNET_CHANNEL="${DOTNET_CHANNEL:-10.0}"
B="${DARWIN_BUNDLE:-${XDG_CONFIG_HOME:-$HOME/.config}/swiftpm/swift-sdks/darwin.artifactbundle}"
log() { printf '\033[1m[dotnet]\033[0m %s\n' "$*"; }
die() { echo "dotnet: $*" >&2; exit 1; }

case "$(uname -m)" in x86_64) host=linux-x64 ;; aarch64) host=linux-arm64 ;; *) die "Linux x86_64 or aarch64 only" ;; esac
sdk_settings="$B/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk/SDKSettings.plist"
[ -f "$sdk_settings" ] || die "no Darwin SDK in $B: install-toolchain.sh first"
ios_version=$(python3 -I -c 'import plistlib,sys; print(plistlib.load(open(sys.argv[1],"rb"))["Version"])' "$sdk_settings")
command -v cc >/dev/null || die "a C compiler (cc) is needed for the hook's native part"

# 1. the SDK
dotnet="$OAD_DOTNET/sdk/dotnet"
if [ ! -x "$dotnet" ]; then
  log ".NET SDK $DOTNET_CHANNEL into $OAD_DOTNET/sdk (dotnet-install.sh)"
  mkdir -p "$OAD_DOTNET/download"
  curl -fsSL -o "$OAD_DOTNET/download/dotnet-install.sh" https://dot.net/v1/dotnet-install.sh
  bash "$OAD_DOTNET/download/dotnet-install.sh" --channel "$DOTNET_CHANNEL" --install-dir "$OAD_DOTNET/sdk" --no-path
fi
export DOTNET_ROOT="$OAD_DOTNET/sdk" DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
log "$("$dotnet" --version) in $DOTNET_ROOT"

# 2. Linux in the platform lists of the mono toolchain manifests
band_dir=$(find "$DOTNET_ROOT/sdk-manifests" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*' | sort -V | tail -n 1)
[ -n "$band_dir" ] || die "no workload manifests in $DOTNET_ROOT/sdk-manifests"
band=$(basename "$band_dir")
for m in "$band_dir"/microsoft.net.workload.mono.toolchain.*/*/WorkloadManifest.json; do
  python3 -I - "$m" "$host" <<'PY'
import re, sys
path, host = sys.argv[1:]
text = open(path).read()
def widen(m):
    items = m.group(1)
    return m.group(0) if host in items or "osx-" not in items else m.group(0).replace("]", f', "{host}" ]', 1)
new = re.sub(r'"platforms"\s*:\s*\[([^\]]*)\]', widen, text)
if new != text:
    open(path, "w").write(new)
PY
done
log "mono toolchain manifests of band $band: $host added to their platforms"

# 3. the iOS workload manifest of the Darwin SDK's version
id="microsoft.net.sdk.ios.manifest-$band"
ver="${IOS_MANIFEST_VERSION:-$(curl -fsSL "https://api.nuget.org/v3-flatcontainer/$id/index.json" | python3 -I -c '
import json, sys
want = sys.argv[1]
vs = [v for v in json.load(sys.stdin)["versions"] if v.split("-")[0].rsplit(".", 1)[0] == want and "-" not in v]
print(vs[-1] if vs else "")' "$ios_version")}"
[ -n "$ver" ] || die "no iOS workload for iOS $ios_version in NuGet's $id (set IOS_MANIFEST_VERSION)"
mdir="$band_dir/microsoft.net.sdk.ios/$ver"
if [ ! -f "$mdir/WorkloadManifest.json" ]; then
  log "iOS workload manifest $ver (iOS $ios_version) from NuGet"
  pkg="$OAD_DOTNET/download/$id.$ver.nupkg"
  curl -fsSL -o "$pkg" "https://api.nuget.org/v3-flatcontainer/$id/$ver/$id.$ver.nupkg"
  # NuGet's catalog entry carries the package's SHA-512
  want=$(curl -fsSL "https://api.nuget.org/v3/registration5-semver1/$id/$ver.json" | python3 -I -c '
import json, sys, urllib.request
entry = json.load(sys.stdin)["catalogEntry"]
print(json.load(urllib.request.urlopen(entry))["packageHash"])')
  got=$(openssl dgst -sha512 -binary "$pkg" | base64 -w0)
  [ "$want" = "$got" ] || { rm -f "$pkg"; die "$pkg: SHA-512 does not match NuGet's catalog"; }
  rm -rf "$band_dir/microsoft.net.sdk.ios" && mkdir -p "$mdir"
  python3 -I -c 'import zipfile,sys
z = zipfile.ZipFile(sys.argv[1])
for n in z.namelist():
    if n.startswith("data/") and not n.endswith("/"):
        open(sys.argv[2] + "/" + n[5:], "wb").write(z.read(n))' "$pkg" "$mdir"
  rm -f "$pkg"
fi
log "dotnet workload install ios ($ver)"
"$dotnet" workload install ios --skip-manifest-update

# 4. the startup hook and its native library
log "startup hook: $OAD_DOTNET/linuxhost"
mkdir -p "$OAD_DOTNET/linuxhost" "$OAD_DOTNET/hook-build"
cp "$here/hook/LinuxHostHook.csproj" "$here/hook/StartupHook.cs" "$OAD_DOTNET/hook-build/"
"$dotnet" build "$OAD_DOTNET/hook-build/LinuxHostHook.csproj" -c Release -o "$OAD_DOTNET/linuxhost" -nologo -v:q
cc -shared -fPIC -O2 -Wall -o "$OAD_DOTNET/linuxhost/libmacshim.so" "$here/hook/macshim.c"

# 5. the Xcode.app stand-in
x="$OAD_DOTNET/Xcode.app"
log "Xcode.app stand-in: $x (Xcode $ios_version: the Darwin SDK's)"
rm -rf "$x" && mkdir -p "$x/Contents/MacOS" "$x/Contents/Developer"
ln -s "$B/Developer/Platforms" "$x/Contents/Developer/Platforms"
ln -s "$B/Developer/Toolchains" "$x/Contents/Developer/Toolchains"
printf '#!/bin/sh\necho "Xcode does not run on Linux: this Xcode.app is the Darwin SDK, for .NET for iOS (omarchy-apple-dev dotnet/)" >&2\nexit 1\n' >"$x/Contents/MacOS/Xcode"
chmod +x "$x/Contents/MacOS/Xcode"
python3 -I - "$x" "$ios_version" <<'PY'
import plistlib, sys
x, v = sys.argv[1:]
xcode = v.replace(".", "") + "0" * (4 - len(v.replace(".", "")))
plistlib.dump({"CFBundleIdentifier": "com.apple.dt.Xcode", "CFBundleName": "Xcode", "CFBundleShortVersionString": v,
               "DTXcode": xcode}, open(f"{x}/Contents/Info.plist", "wb"))
plistlib.dump({"CFBundleShortVersionString": v, "ProductBuildVersion": "linux", "ProjectName": "IDEFrameworks"},
              open(f"{x}/Contents/version.plist", "wb"))
PY
echo "$ver" >"$OAD_DOTNET/ios-workload-version"
log "ready: dotnet/build.sh in a .NET for iOS project"
