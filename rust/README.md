# Rust iOS apps, built on Linux

cargo builds for `aarch64-apple-ios-sim` (the simulator, x86Sim phones) and `aarch64-apple-ios` (iPhone) with the
Darwin SDK `install-toolchain.sh` registers and its `ld64.lld`. `build.py` then puts the binary in an `.app` the way
Xcode lays one out. No Mac, no Xcode install, no `xcodebuild`.

| Setup | Status | Sample |
|-------|--------|--------|
| Plain Rust (UIKit through objc2) | runs on an x86Sim phone, snapshot + tap checked | `samples/hello-uikit` |
| Tauri 2 (tao + WKWebView) | runs on an x86Sim phone, snapshot + tap (a Rust command) checked | `samples/tauri-hello` |
| Dioxus 0.7 mobile (tao + WKWebView) | runs on an x86Sim phone, snapshot + tap checked | `samples/dioxus-hello` |

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

Windowing libraries name or get one from `build.py` when the Info.plist has none:

- tao 0.37 and later (Tauri 2.12) has a scene delegate: `TaoSceneDelegate` goes in the Info.plist.
- Older tao (Dioxus 0.7 uses 0.34) and winit before 0.31 (Bevy 0.20 uses 0.30) make their windows the pre-scene way.
  `build.py` links `scene-adapter.m` (compiled with clang here) and names its `RustSceneAdapter`: windows made before
  the scene connects are attached to it when it does, later ones at once, and the scene's activation callbacks go on
  to the app delegate's `applicationDidBecomeActive:` & co., which UIKit stops calling under scenes.
  `scene-adapter = true | false` in `[package.metadata.ios]` overrides the choice.

## Tauri 2

`tauri ios init | build` (tauri-cli's iOS commands, and the Xcode project they write) run only on macOS. `build.py`
does what they do, directly:

```
rust/build.py path/to/app          # the folder with src-tauri/ (or src-tauri itself)
x86sim dev run path/to/app         # build, install and launch on an x86Sim phone
```

- The app is the crate's library (Tauri's mobile layout, `crate-type = ["staticlib", "cdylib", "rlib"]`): cargo
  builds its staticlib (`cargo rustc --crate-type staticlib`, so the cdylib is not linked), and a generated `main()`
  calls `start_app` (`#[tauri::mobile_entry_point]`).
- The frontend (`build.frontendDist`) is built into the binary with the `tauri/custom-protocol` feature, as
  `tauri build` does. Build it first (`npm run build`, or whatever `beforeBuildCommand` says); `build.py` does not run
  `beforeBuildCommand`. `TAURI_DEV=1` leaves the feature off, for a `devUrl` server the phone can reach.
- tauri links its Swift half (the `Tauri` package in tauri's `mobile/ios-api`: plugin bridge, IPC, logging) only on a
  Mac. Here it is built with Linux Swift (`swift build --swift-sdk darwin --triple arm64-apple-ios-simulator`, in
  `<target dir>/tauri-ios-api`) and linked in with the Swift runtime's search paths.
- Name and bundle id come from `tauri.conf.json` (`productName`, `identifier`); `[package.metadata.ios]` overrides.
- The Info.plist names tao's scene delegate (`TaoSceneDelegate`), as Tauri's iOS template does: iOS 27 needs the
  scene life cycle.

Not covered yet: Tauri plugins with Swift code of their own (their `ios/` packages expect the project tauri-cli
generates); plugins without Swift code work.

## Dioxus mobile

A Dioxus app with the `mobile` feature is a plain binary crate: `rust/build.py <crate dir>` (or `x86sim dev run`)
builds it, no `dx`. Name and bundle id from `[package.metadata.ios]`, else `Dioxus.toml`
(`application.name`, `bundle.identifier`). Leave out the `devtools` feature (on by default: `dx serve`'s hot-reload
channel) for builds without `dx`.

Not covered: `asset!()` files. `dx` collects them into the bundle; `build.py` copies only `resources` (default
`assets/`), so an app that uses `asset!()` needs `dx bundle` for now.

## Devices

`--device` builds for `aarch64-apple-ios`, signed ad hoc by the linker. Sign it for your iPhone with
`tools/provision-dev.py --bundle-id <id>` and `tools/sign-dev.sh <App>.app out.ipa`, then install the `.ipa` (e.g.
`xtool install out.ipa`).
