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
