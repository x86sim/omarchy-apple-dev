# .NET for iOS apps, built on Linux

Microsoft builds .NET for iOS apps on a Mac only: the iOS workload does not
install on Linux, and on Windows it hands the build to a "Mac build host".
Nothing in the build really needs macOS, though. The workload's MSBuild tasks
are managed code, the iOS runtime packs are files, and the native steps are
Xcode's tools, which the Darwin SDK of `install-toolchain.sh` already has
on Linux. `dotnet/setup.sh` makes the workload install and run here, and
`dotnet/build.sh` builds an app for the iOS Simulator (an x86Sim phone) or an
iPhone.

Verified 2026-11-25 on x86_64 (Arch, .NET SDK 10.0.404, iOS workload
27.2.10000, iPhoneSimulator 27.2 SDK): the `dotnet new ios` template (Release)
and a UIKit counter (x86Sim's `tests/dev/dotnet/HelloCounter`, Debug), built
for `iossimulator-arm64` and run on an x86Sim iPhone 17 (iOS 27.2). Their UI
was in the accessibility snapshot, and a tap on the counter's button updated it.

## Use

```
./install-toolchain.sh          # once: the Darwin SDK from the Xcode .xip, rcodesign
dotnet/setup.sh                 # once: .NET SDK, iOS workload, the pieces below (~1.5 GB)
cd MyApp                        # dotnet new ios, or an existing net*-ios project
../omarchy-apple-dev/dotnet/build.sh --simulator          # -> simulator app ready: bin/Debug/net10.0-ios/iossimulator-arm64/MyApp.app
../omarchy-apple-dev/dotnet/build.sh --device -c Release  # ios-arm64, unsigned (see below)
```

`x86sim dev build` / `dev run` in x86Sim take a directory with a `net*-ios`
`.csproj` as it is: it builds with `dotnet/build.sh --simulator`, then installs
and launches the app on a phone.

Everything lives in `~/.local/share/omarchy-apple-dev/dotnet` (`OAD_DOTNET`):
a .NET SDK of its own, the startup hook, and the Xcode.app stand-in. NuGet
packages go to `~/.nuget/packages` as usual. Delete the directory to remove it.

## What needed a Mac, and what stands in for it

| Mac part | Where it bites | On Linux |
| --- | --- | --- |
| Workload host list | `dotnet workload install ios`: "not supported on this platform"; the mono toolchain manifests list only `win-*`/`osx-*` for the iOS runtime packs | `setup.sh` adds `linux-x64`/`linux-arm64` to those lists in its own SDK, then installs the iOS workload manifest matching the Darwin SDK's version (from NuGet, checked against NuGet's SHA-512) |
| `/usr/lib/libc.dylib`, `/usr/lib/libSystem.dylib` | The tasks P/Invoke them by path: `realpath` (FindItemWithLogicalName), `sysctlbyname("sysctl.proc_translated")` (the Rosetta check of ACTool), `stat$INODE64` (ComputeCodesignItems) | A .NET startup hook (`hook/StartupHook.cs`, `DOTNET_STARTUP_HOOKS`) resolves both paths to `hook/macshim.c`: glibc plus `sysctlbyname` (no such name) and `stat`/`lstat`/`fstat$INODE64`, filling macOS's 144-byte `struct stat` |
| Xcode.app | "A valid Xcode installation was not found"; the custom linker checks `Contents/MacOS/Xcode` (MT0057); the SDK version pins the Xcode version | A directory: `Contents/Info.plist` and `version.plist` with the Darwin SDK's version, a `MacOS/Xcode` stub, `Contents/Developer/{Platforms,Toolchains}` linked to the Darwin SDK; `build.sh` passes it as `XcodeLocation` |
| `xcrun` | actool, ibtool, clang, install_name_tool, simctl, mdimport, codesign, `--show-sdk-path` | `bin/xcrun`: the SDK's actool and this repo's `tools/ibtool` (their text answer turned into the `xml1` plist the tasks parse), Linux clang with an Apple `-target` made from `-arch` / `-m<os>-version-min` and the toolset's `ld64.lld`, LLVM's binutils, an iOS runtime list for `simctl list runtimes`, nothing for Spotlight's `mdimport` |
| `codesign` | Ad-hoc signing of the app and its dylibs | `bin/codesign`: `rcodesign sign` with the entitlements the tasks write |
| Mono's AOT compiler | Every arm64 iOS target runs it, the simulator included (`_RunAotCompiler`). Microsoft publishes it (`Microsoft.NETCore.App.Runtime.AOT.osx-*.Cross.*`) for macOS hosts only | Not available. **NativeAOT** compiles the app instead: its compiler (ILCompiler) is published for Linux (`runtime.linux-x64.Microsoft.DotNet.ILCompiler`) and targets iOS. `build.sh` builds with `PublishAot=true` (and `_IsPublishing`, which is how the iOS SDK enables it) |

Mono's JIT is no way around the AOT compiler: a simulator app built for the
JIT (AOT turned off, the generated `main` set to `MONO_AOT_MODE_NONE`) aborts in
`mono_jit_init` on Apple's own simulator (checked on a Mac: an assertion in
`mono_global_codeman_reserve`), as it fails on x86Sim.

## Limits

- **NativeAOT only.** No Mono: features that need it (the interpreter, Hot
  Reload, the Mono debugger) are out, and the app must be trimming- and
  AOT-compatible, as for any NativeAOT app. Building Mono's AOT cross compiler for
  a Linux host from dotnet/runtime's sources (it is built for Linux hosts
  for Android targets) would bring back the Mono path. Not attempted.
- **Device builds are unsigned.** `--device` builds `ios-arm64` with
  `EnableCodeSigning=false`. Sign the `.app` with your identity
  (`tools/sign-dev.sh`) and install it (`xtool install`). Not yet verified on
  an iPhone.
- **.NET MAUI** apps use the same workload plus the `maui-ios` workload. See
  "MAUI" below for how far it got.
- iOS only. tvOS and Mac Catalyst workloads would take the same steps, but
  were not tried.
- `ibtool` compiles the storyboards and xibs `tools/ibtool` supports (the
  template's `LaunchScreen.storyboard` included); others fail with its error.
