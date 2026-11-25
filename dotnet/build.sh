#!/usr/bin/env bash
# Build a .NET for iOS app on Linux (dotnet/README.md; dotnet/setup.sh once first).
#   dotnet/build.sh [--simulator | --device] [-c Debug|Release] [PROJECT dir or .csproj] [-- msbuild args...]
# --simulator (default): iossimulator-arm64, ad-hoc signed, for the iOS Simulator (an x86Sim phone).
# --device: ios-arm64, unsigned: sign it with your identity (tools/sign-dev.sh) and install it (xtool install).
# The app is compiled with NativeAOT (PublishAot): Mono's AOT compiler, which every arm64 iOS target needs, is
# published for macOS hosts only, while NativeAOT's ILCompiler is published for Linux. The last line names the app:
#   simulator app ready: <path>.app     (device app ready: <path>.app)
set -euo pipefail

here=$(dirname "$(readlink -f "$0")")
OAD_DOTNET="${OAD_DOTNET:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/dotnet}"
mode=simulator config=Debug project=. extra=()
while [ $# -gt 0 ]; do
  case "$1" in
  --simulator) mode=simulator; shift ;;
  --device) mode=device; shift ;;
  -c | --configuration) config=$2; shift 2 ;;
  --) shift; extra=("$@"); break ;;
  -h | --help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  -*) echo "dotnet: unknown option $1 (msbuild arguments go after --)" >&2; exit 2 ;;
  *) project=$1; shift ;;
  esac
done
[ -x "$OAD_DOTNET/sdk/dotnet" ] && [ -f "$OAD_DOTNET/linuxhost/LinuxHostHook.dll" ] && [ -d "$OAD_DOTNET/Xcode.app" ] ||
  { echo "dotnet: not set up: $here/setup.sh" >&2; exit 1; }

if [ -d "$project" ]; then
  csproj=$(find "$project" -maxdepth 1 -name '*.csproj' | sort | head -n 1)
  [ -n "$csproj" ] || { echo "dotnet: no .csproj in $project" >&2; exit 1; }
else
  csproj=$project
fi
dir=$(cd "$(dirname "$csproj")" && pwd)
csproj="$dir/$(basename "$csproj")"

export DOTNET_ROOT="$OAD_DOTNET/sdk" DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export PATH="$here/bin:$DOTNET_ROOT:$PATH"
# the MSBuild tasks' P/Invokes of macOS's libc / libSystem (dotnet/hook); every MSBuild node gets it, so none is
# reused from an earlier build without it
export DOTNET_STARTUP_HOOKS="$OAD_DOTNET/linuxhost/LinuxHostHook.dll" MSBUILDDISABLENODEREUSE=1

if [ "$mode" = simulator ]; then rid=iossimulator-arm64; else rid=ios-arm64; fi
# NativeAOT is the publish path of the iOS SDK (_IsPublishing); a simulator build takes it the same way
args=(build "$csproj" -c "$config" -r "$rid" -nodeReuse:false
  -p:PublishAot=true -p:_IsPublishing=true -p:XcodeLocation="$OAD_DOTNET/Xcode.app")
[ "$mode" = device ] && args+=(-p:EnableCodeSigning=false)
stamp="$dir/obj/.oad-build-stamp"
mkdir -p "$dir/obj" && : >"$stamp"
dotnet "${args[@]}" "${extra[@]}"

app=$(find "$dir/bin/$config" -path "*/$rid/*.app" -prune -newer "$stamp" -print 2>/dev/null | head -n 1)
[ -n "$app" ] || app=$(find "$dir/bin/$config" -path "*/$rid/*.app" -prune -print 2>/dev/null | head -n 1)
[ -n "$app" ] || { echo "dotnet: the build wrote no .app under $dir/bin/$config" >&2; exit 1; }
echo "$mode app ready: $app"
