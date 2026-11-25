# CocoaPods on Linux

React Native and Expo apps, and Flutter plugins that only have a Podfile, get their iOS dependencies from
CocoaPods. This directory runs `pod install` on Linux.

## Install

```
./install-toolchain.sh --cocoapods     # or cocoapods/install.sh; the full install runs it as step 6b
```

It installs, without sudo:

- Ruby 3.4.6: Homebrew's portable Ruby, a relocatable build that runs on any glibc Linux (x86_64 and aarch64),
  checked against a pinned sha256. It goes to `~/.local/share/omarchy-apple-dev/cocoapods/ruby`, and the system
  Ruby is not touched.
- CocoaPods 1.16.2 and every gem it loads, at the versions in [gems.lock](gems.lock), in `.../cocoapods/gems`.
  `bigdecimal` and `nkf` build a native extension, so `cc` and `make` must be installed.
- `~/.local/bin/pod`, a wrapper (from [pod.in](pod.in)). If `~/.local/bin/pod` already exists and was not written
  by this install, it is left alone; use `~/.local/share/omarchy-apple-dev/cocoapods/bin/pod` instead.

Re-runs change nothing when the pinned set is in place. `cocoapods/install.sh --check` exits 0 when it is.
`POD_HOME` and `POD_BIN` move the install and the wrapper.

## What the wrapper answers for a Mac

| A Podfile or podspec hook expects | Here |
|---|---|
| `xcodebuild -version` (React Native's Xcode check) | `flutter/shims/xcodebuild`: the Xcode version of the registered Darwin SDK |
| `xcrun --sdk X --show-sdk-path`, `xcrun clang ...` (Expo's stub xcframework) | `flutter/shims/xcrun`: the SDK paths in the Darwin SDK bundle; `clang` gets the SDK's `-target` and `-isysroot` when the arguments name none |
| `/usr/bin/command` (Ruby's `` `command -v ccache` ``) | `shims/command` |
| `plutil -convert json` (Expo's autolinking reads the entitlements), `-extract`, `-replace`, `-lint`, `-p` | `shims/plutil`, Python's plistlib |
| `/usr/bin/tar` is bsdtar and takes member globs (Expo's precompiled-module check) | `linux.rb` (loaded through `RUBYOPT`) adds `--wildcards` for GNU tar |
| Expo's `@ExpoModule` class scan runs only on macOS, although expo-modules-macros ships the scanner for Linux | `node-linux.js` (loaded through `NODE_OPTIONS`) lets the scan run |

`OAD_DIR` points the wrapper at this tree when it moved after the install.

Verified 2026-11-25 on x86_64 Arch: `pod install` for a fresh `create-expo-app` (Expo SDK 58, React Native 0.88,
115 pods) in 25 s: `Pod installation complete! There are 116 dependencies from the Podfile and 115 total pods
installed.`

## Building the workspace

`pod install` writes `Pods/Pods.xcodeproj` and an `.xcworkspace`. [tools/xcbuild.py](../tools/xcbuild.py) builds them
on Linux the way `xcodebuild` does, and `flutter/shims/xcodebuild` sends every non-`-version` call to it, so
`xcodebuild -workspace App.xcworkspace -scheme App -sdk iphonesimulator` works too:

```
cd ios
../path/to/omarchy-apple-dev/tools/xcbuild.py -workspace App.xcworkspace -scheme App \
  [-configuration Debug|Release] [-sdk iphonesimulator|iphoneos] [-jobs 4] [SETTING=VALUE ...]
# -> build/xcbuild/Build/Products/Debug-iphonesimulator/App.app
```

It reads the projects with the converter's pbxproj parser, resolves each target's build settings as Xcode does
(built-in defaults, project and target xcconfigs and settings, `$(inherited)` including repeated assignments in one
xcconfig, `[sdk=…][arch=…][config=…]` conditions, `:c99extidentifier`-style modifiers, one build location for every
project of the workspace), and writes a ninja file, so a rebuild redoes only what changed:

- ObjC, ObjC++, C, C++ (clang from the Swift toolchain, with header maps of the target's and the project's headers)
  and Swift (one `swiftc -wmo` per module, with `-import-underlying-module` for mixed pods and the
  `<Module>-Swift.h` compatibility header);
- static libraries (`llvm-ar --format=darwin`), frameworks, resource bundles, the app, linked with the SDK bundle's
  `ld64.lld` and compiler-rt's builtins for the platform;
- shell script phases with the target's build settings in the environment (`/bin/sh` is bash, as on macOS), so
  CocoaPods' own `[CP] Copy XCFrameworks`, `[CP] Embed Pods Frameworks` and `[CP] Copy Pods Resources`, React
  Native's codegen and Expo's scripts run as written, under Node on Linux;
- resources (`actool` and `ibtool` from the SDK bundle), Info.plist with Xcode's added keys, PkgInfo;
- `xcodebuild build -scheme P` in a Swift package's directory (how Expo builds ExpoModulesJSI.xcframework):
  `swift build` for the SDK, laid out as Xcode's `PackageFrameworks/P.framework` and `P.swiftmodule`.

Where Linux's tools differ from Apple's, it follows Apple's: clang modules only for C and ObjC sources (as
`CLANG_ENABLE_MODULES` says), `-fmodule-map-file` dropped where modules are off (clang 21 otherwise wants the
modules prebuilt), `<swift/bridging>` from the Swift toolchain, and `AssumeResilientCxxTypes` for library-evolution
packages (Apple's Swift 6.4 accepts what swift.org's needs the feature for). Macro plugins that CocoaPods points at a
macOS binary (Expo's `ExpoModulesMacros`) are swapped for the npm package's Linux build. It needs `ninja` and
`rsync`.

Verified 2026-11-25: a fresh `create-expo-app` (Expo SDK 58, React Native 0.88: 124 targets with the prebuilt React
Native core and Hermes) builds for the simulator on x86_64 Linux and runs on x86Sim with its JavaScript from Metro;
a JavaScript edit reaches the running app through Fast Refresh.
