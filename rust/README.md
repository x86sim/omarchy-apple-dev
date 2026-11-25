# Rust iOS apps, built on Linux

cargo builds for `aarch64-apple-ios-sim` (the simulator, x86Sim phones) and `aarch64-apple-ios` (iPhone) with the
Darwin SDK `install-toolchain.sh` registers and its `ld64.lld`. `build.py` then puts the binary in an `.app` the way
Xcode lays one out. No Mac, no Xcode install, no `xcodebuild`.

| Setup | Status | Sample |
|-------|--------|--------|
| Plain Rust (UIKit through objc2) | runs on an x86Sim phone, snapshot + tap checked | `samples/hello-uikit` |

## Setup

```
./install-toolchain.sh     # the Darwin SDK (once, as for any app in this repo); runs rust/setup.sh when rustup is there
rust/setup.sh              # or by hand: rustup target add aarch64-apple-ios-sim aarch64-apple-ios, and a link check
```

Nothing global changes (no `~/.cargo/config.toml` edits). The pieces:

- `ios-cc` (called as `aarch64-apple-ios-sim-cc` / `aarch64-apple-ios-cc`): clang for the target with the SDK as
  sysroot and the SDK bundle's `ld64.lld`. cargo links with it; cc-rs compiles C / C++ / Objective-C with it.
  It tells clang the linker is a current ld64 (`-mlinker-version`): without that clang drives ld64 with 2011's flags
  and `ld64.lld` refuses them.
- `ios-env.sh`: source it to use plain cargo (or a tool that runs cargo):
  `CARGO_TARGET_<T>_LINKER`, `CC_<t>`, `CXX_<t>`, `AR_<t>`, `CFLAGS_<t>`, bindgen's clang arguments for both
  targets, `SDKROOT` for one (`IOS_ENV_TARGET=sim|device`, default sim), and an `xcrun` on `PATH` that answers SDK
  queries (`flutter/shims/xcrun`): rustc, cc-rs and build scripts ask it as on a Mac.

  ```
  . rust/ios-env.sh
  cargo build --target aarch64-apple-ios-sim
  ```
- `build.py`: cargo, then the `.app`.

## Build an app

```
rust/build.py [--simulator | --device] [--release] [--target-dir DIR] [--bin NAME] <crate dir>
```

The app is `<target dir>/ios-sim/<Name>.app` (simulator) or `ios/<Name>.app` (device); the last line of the output
says where. `x86sim dev build | run` recognise a cargo package and run this for you (`x86sim dev run <crate dir>`
builds, installs and launches on a phone).

Its settings come from `Cargo.toml`:

```toml
[package.metadata.ios]
bundle-id = "com.example.app"      # CFBundleIdentifier (default com.example.<package>)
display-name = "My App"            # the name under the icon (default: the package name)
version = "1.0"                    # default: the package version
min-os = "17.0"                    # MinimumOSVersion and IPHONEOS_DEPLOYMENT_TARGET
entry = "main_rs"                  # a library app: its staticlib linked with a main() that calls this function
resources = ["assets"]             # copied into the .app (default: assets/ when the crate has one)
features = ["..."]                 # cargo features for the iOS build

[package.metadata.ios.info-plist]  # any extra Info.plist keys
UIStatusBarHidden = true
```

The Info.plist has what Xcode writes for an app target (platform, SDK, `UILaunchScreen` so the app is not
letterboxed, device families, orientations).

### The scene life cycle (iOS 27)

iOS 27 refuses to launch an app built with its SDK that does not use the scene life cycle ("UIScene life cycle is
required for apps built with this SDK"), on Apple's simulator and devices as on x86Sim. An app makes its window in a
`UIWindowSceneDelegate` named in the Info.plist; `samples/hello-uikit` shows it:

```toml
[package.metadata.ios.info-plist.UIApplicationSceneManifest]
UIApplicationSupportsMultipleScenes = false
[[package.metadata.ios.info-plist.UIApplicationSceneManifest.UISceneConfigurations.UIWindowSceneSessionRoleApplication]]
UISceneConfigurationName = "Default Configuration"
UISceneDelegateClassName = "RustHelloSceneDelegate"
```

## Devices

`--device` builds for `aarch64-apple-ios`, signed ad hoc by the linker. Sign it for your iPhone with
`tools/provision-dev.py --bundle-id <id>` and `tools/sign-dev.sh <App>.app out.ipa`, then install the `.ipa` (e.g.
`xtool install out.ipa`).
