# Project shapes and how each builds on Linux

What kind of iOS project builds here, with what, and how far it was checked. "Phone" means installed and launched on
an x86Sim phone (Apple's iOS 27.2 simulator runtime on Linux) and checked through x86Sim's MCP tools (snapshot, tap):
x86Sim's `tests/dev/xcode_e2e.py` for Xcode projects. Status as of 2026-11-25 (sweetpad 0.1.29, Swift Build 6.4.0,
Swift 6.4.2, SDK 27.2).

## Builders

`tools/build-project DIR` picks the builder below for a project and runs every step before it (README: "Any project").

| Project | Builder | Entry points |
|---|---|---|
| `.xcodeproj` / `.xcworkspace` (any shape below) | Swift Build ([swiftbuild/](../swiftbuild/README.md)) | `linux-bin/xcodebuild`, `x86sim dev build/run` |
| CocoaPods workspace (React Native, Expo, Flutter plugins) | `tools/xcbuild.py` today (x86Sim's `dev run`); Swift Build via `linux-bin/xcodebuild` after `pod install` | `cocoapods/`, `linux-bin/xcodebuild` |
| xtool package (Package.swift + xtool.yml) | xtool / SwiftPM | `xtool dev`, `ship.sh` |
| Swift package directory, `xcodebuild build` in it | `tools/xcbuild.py` (Expo's scripts) | `linux-bin/xcodebuild` |
| Xcode project to edit as a package | `tools/xcodeproj2xtool.py` (SourceKit-LSP, xtool); not needed for building | |
| App shells and engine exports (Capacitor, ...): the shell's CLI writes an Xcode project | Swift Build ([shells/](../shells/README.md)) | `x86sim dev build/run`, `linux-bin/xcodebuild` |

## Xcode project shapes

| Shape | Status | Checked with |
|---|---|---|
| Swift / SwiftUI app | builds, runs | NextSunnyDay, Cronica (phone) |
| Objective-C-only app | builds; app runs as on Apple's simulator | RDVTabBarController (phone: iOS 27 stops pre-scene apps after launch, SIGTRAP in UIKit's no-scene-lifecycle check, same on Apple's simulator with Xcode 27.2) |
| Mixed Objective-C / Swift app target (bridging header, generated `-Swift.h`) | builds | Charts' iOS demo (phone: pre-scene, as above), Overland (stops in its storyboard, see IB below) |
| Objective-C++ / C / C++ sources | builds (Swift Build's clang rules) | Sentry's package in Cronica |
| `.xcworkspace` with several projects | builds | Charts (framework project + demo project), WordOfTheDay |
| Framework targets (dynamic, static), embedded | builds, embeds | DGCharts in Charts, NetworkKit in WordOfTheDay, Sentry's static xcframework in Cronica |
| Swift packages: local | builds | NextSunnyDay (19 local packages), Cronica (CronicaCore) |
| Swift packages: remote (resolved on Linux) | builds | Cronica (Sentry, Nuke, Pow, YouTubePlayerKit), WordOfTheDay (Alamofire) |
| Widget extension | builds, embedded in PlugIns | NextSunnyDay, Cronica |
| Share extension | builds, embedded | Cronica |
| Single-target watch app (watchOS 7+) | builds for watchsimulator, embedded in Watch/ (with its own widget) | NextSunnyDay, Cronica |
| WatchKit 2 app + extension (watchapp2) | builds, embedded | WordOfTheDay (the repository misses one source file of its own) |
| App Clip, iMessage, other extension types | Swift Build's product types; not checked with a real project yet | |
| Run-script phases | run on Linux in a sandbox with GNU tools | Shimmer: `/bin/ln -sfh` (BSD flag) fails; `ln -sfn` means the same |
| Asset catalogs, Icon Composer `.icon` | compiled (sweetpad's actool) | NextSunnyDay and Cronica's AppIcon.icon -> app icons |
| Storyboards / xibs | this repository's ibtool (byte-identical to Apple's) first, sweetpad's for what it refuses | Charts (26 xibs), Shimmer, RDVTabBarController |
| Localized storyboards (`--companion-strings-file`) | sweetpad's ibtool | EspBlufi |
| App Intents | metadata when the Linux processor handles them; else built without it (said) | NextSunnyDay (`AppIntentsPackage`), Cronica (phrase parameters) |
| Unit tests (XCTest, Swift Testing) | `xcodebuild test` / fastlane scan run them on a phone | clean-architecture-swiftui: 76 tests, per-test results |
| UI-test targets (XCUITest) | built (the `<Target>-Runner.app` from the SDK's XCTRunner.app); `xcodebuild test` runs them on a phone, every simulator platform | x86Sim's XCTestDemo: iOS, tvOS, watchOS, visionOS |
| Archive (`xcodebuild archive`, fastlane gym) | unsigned archive; `-exportArchive` through sweetpad | NextSunnyDay, clean-architecture-swiftui |

## App shells and game engines

Each was built only on Linux, installed and launched on an x86Sim phone, and checked through MCP (snapshot shows its
UI, one tap changes it): x86Sim's `tests/dev/shells_e2e.py`.

### Capacitor 8 (and Ionic on Capacitor)

**Builds, runs.** Capacitor 8.6.3's iOS template uses Swift packages (capacitor-swift-pm: Capacitor and Cordova as
binary xcframeworks), and its CLI is plain Node: `npx cap add ios` and `npx cap sync ios` write `ios/App` on Linux
with no Mac checks. Swift Build resolves the package and builds `App.xcodeproj`. The template's storyboards
(`Main.storyboard`: a `CAPBridgeViewController` with no view; `LaunchScreen.storyboard`: an image view) go to
sweetpad's ibtool. Sample: [shells/samples/capacitor-hello](../shells/samples/capacitor-hello).

- **Ionic** (Ionic 9 React starter from `ionic start --type=react --capacitor`, Vite): a Capacitor app whose web
  assets come from `npm run build`, and which has no `@capacitor/ios` until `ionic capacitor add ios`. x86Sim adds
  `@capacitor/ios` at the app's `@capacitor/core` version, runs the web build and `cap add ios`; the four plugins of
  the starter (app, haptics, keyboard, status-bar) are Swift packages. Builds, runs. Sample:
  [shells/samples/ionic-hello](../shells/samples/ionic-hello) (the starter, its home page a counter). Ionic's
  `<ion-button>` renders in a shadow root, which WebKit's accessibility tree folds into its parent region: x86Sim's
  check taps it by its OCR text.

- Capacitor apps on CocoaPods (`npx cap add ios --packagemanager CocoaPods`, older apps): `cap add` / `cap sync` run
  `pod install` with [cocoapods/](../cocoapods/README.md)'s `pod` on PATH (x86Sim puts it there), and Swift Build
  builds `App.xcworkspace`, embedding the pods' frameworks (checked with @capacitor/haptics 8.0.2: builds; `cap` warns
  it found no `xcodebuild` for its clean step, which changes nothing).

### Cordova (cordova-ios 8)

**Builds, runs.** cordova-ios 8.2.0 (Cordova CLI 13) writes `platforms/ios` on Linux: `cordova platform add ios` and
`cordova prepare ios` have no Mac checks (only `cordova build` / `run` call `xcodebuild`, which x86Sim replaces with
Swift Build). CordovaLib and plugins come as Swift packages (`packages/cordova-ios`, `packages/cordova-ios-plugins`),
and the template has a scene delegate. Swift Build builds `App.xcworkspace`; `CDVLaunchScreen.storyboard`
(`contentMode="scaleAspectFill"`) goes to sweetpad's ibtool. On the phone, cordova.js fires `deviceready` (the native
bridge answers). Sample: [shells/samples/cordova-hello](../shells/samples/cordova-hello).

### NativeScript 9

**Builds, runs.** NativeScript CLI 9.1.2, iOS runtime 9.1.1, hello-world-ts template. What needed Linux paths, all in
[shells/nativescript/](../shells/nativescript):

- **The CLI** refuses iOS off macOS in three places ([ns-linux.js](../shells/nativescript/ns-linux.js), preloaded by
  the [ns](../shells/nativescript/ns) wrapper): the iOS platform's `targetedOS` is only `darwin` (`ns prepare ios`:
  "cannot be executed"), its `validate()` returns nothing off macOS, and @nativescript/doctor reads the Xcode version
  only on macOS (prepare's Podfile step: "xcodebuild execution failed"; `linux-bin/xcodebuild -version` answers).
  The CLI also runs `ruby -e "require 'xcodeproj'"` to merge xcconfigs: CocoaPods' Ruby has that gem.
- **The metadata generator.** The app's link step (`internal/nsld.sh`) runs `objc-metadata-generator`, which turns the
  SDK's headers into the metadata the JavaScript calls native code through; the runtime package ships it as a macOS
  binary only. [build-metadata-generator.sh](../shells/nativescript/build-metadata-generator.sh) builds it from
  NativeScript/ios's source against the system's clang 23 libraries
  ([metadata-generator-clang22.patch](../shells/nativescript/metadata-generator-clang22.patch): clang 22 removed
  `ElaboratedType`; module headers, `StringRef::endswith` and `ObjCMethodDecl::ImplementationControl` moved). It
  writes 11 MB of metadata for the iOS 27.2 SDK in a few seconds.
- **The project** ([fix-project.py](../shells/nativescript/fix-project.py), after prepare): the CLI's pbxproj writer
  leaves `explicitFileType = undefined` / `lastKnownFileType = unknown` on the files it adds (plugin sources,
  xcframeworks, the launch storyboard). Xcode goes by the extension; sweetpad takes them literally (sources not
  compiled, xcframeworks copied whole), so they are typed. The runtime's xcconfig excludes arm64 from simulator builds
  on x86_64 hosts (Intel Macs); the simulator here runs arm64, so x86_64 is excluded instead.

`ns build ios` / `ns run ios` call xcodebuild before the fix: use `shells/nativescript/ns prepare ios`, then
`linux-bin/xcodebuild` (or `x86sim dev build`). Checked against Apple's simulator: the app built here before the
prepare fix stopped the same way there ("Cannot find module '~/package.json'"); once fixed it runs on x86Sim.
Sample: [shells/samples/nativescript-hello](../shells/samples/nativescript-hello).

### Godot 4.7

**Builds, runs (device build, converted).** Godot 4.7.2's official Linux editor exports an iOS Xcode project
headless with the official iOS export template ([shells/godot/export.sh](../shells/godot/export.sh) downloads both,
checked against the release's SHA512-SUMS, no account): with `application/export_project_only` the only macOS step,
building the .ipa, is skipped ("Leaving Xcode project without building the package"). Swift Build builds the project.
What differs from a Mac:

- **No arm64 simulator library.** The template's `ios-arm64_x86_64-simulator` slice holds x86_64 objects only (2292,
  no arm64). Apple's iOS 27 simulator refuses x86_64 apps ("does not contain code for any platform", checked on a
  Mac), so a Godot 4.7.2 export runs on no iOS 27 simulator as shipped. Built for iOS devices instead (arm64,
  unsigned), the app runs on x86Sim, which converts device apps at install.
- **Renderer.** The Mobile / Forward+ renderers (Metal) need Apple3-family GPU features (image cube arrays); the
  simulator's Metal device, Apple's and x86Sim's alike, reports only Mac2 / Common1-3, and Godot stops with "Your Apple
  GPU does not support ... image cube arrays". The Compatibility renderer (`rendering_method.mobile =
  "gl_compatibility"`) runs.
- An app icon is required by the exporter (`config/icon`); `export_presets.cfg` needs an App Store team ID (any value
  for unsigned builds).

Sample: [shells/samples/godot-hello](../shells/samples/godot-hello) (a label and a button; Godot draws its own UI, so
x86Sim's check reads it by OCR).

### Unity 6.3 (IL2CPP)

**Builds, runs.** Unity 6000.3.29f1 LTS for Linux with its iOS Build Support module exports an iOS Xcode project in
batchmode ([shells/unity/build.sh](../shells/unity/build.sh), with
[X86SimBuild.cs](../shells/unity/X86SimBuild.cs): the build settings' scenes, IL2CPP, arm64 simulator or devices).
Both come from Unity's CLI without an account (`unity install 6000.3.29f1 -m ios --accept-eula`, 4.9 GB); the editor
needs an activated license, and Unity activates a Personal license only after a browser sign-in (`unity auth login`:
a URL to approve; `unity license activate --personal`). Username / password batchmode activation is for paid
licenses; service accounts cannot activate.

The exported project assumes a Mac in three places, which
[fix-project.py](../shells/unity/fix-project.py) changes:

- **IL2CPP runs at build time** (the GameAssembly target's script phase) from `Il2CppOutputProject/IL2CPP/build/
  deploy_<arch>`, which the export fills with IL2CPP for macOS (Mach-O). The Linux editor carries the same IL2CPP
  built for Linux, with its iOS toolchain: `deploy_<uname -m>` links to it. It compiles the game's C++ (466 steps for
  the sample) with the build's clang and the SDK.
- **`libtool -static`** archives the result: Linux has none, so the script phase gets a toolchain overlay with
  [libtool](../shells/unity/libtool) (`llvm-ar` with a Darwin symbol table).
- **"Check Unity Framework ABI"** runs `nm -arch`: GNU nm has no `-arch`, every symbol looked missing; on Linux
  `llvm-nm`. The phase declares no inputs, so Swift Build could run it before UnityFramework was linked: the
  framework binary becomes its input.

The app builds with Swift Build for the arm64 simulator (no device conversion needed). On x86Sim the game runs and
its uGUI controls are read through IL2CPP (x86Sim's Unity reader; x86Sim's `tests/ax/games_e2e.py` unity check: elements,
tap, typing). Sample: [shells/samples/unity-hello](../shells/samples/unity-hello) (a button, a score, an input
field, built at run time by `Game.cs`).

### Unreal Engine 5 (researched, not built)

**Does not build on Linux; not attempted beyond research** (2026-11-25, from Epic's documentation; the engine was
not downloaded). What blocks it, in order:

1. **No iOS target on a Linux host.** Epic documents iOS packaging as needing a Mac: the Windows editor builds iOS
   only by Remote Build, UnrealBuildTool driving Xcode on up to two Macs over SSH (Project Settings > Platforms > iOS
   > Remote Build). There is no Linux equivalent: the Linux editor and Linux binary engine builds offer Linux and
   Android targets, not iOS.
2. **The engine's iOS libraries.** An iOS app links the engine compiled for iOS. Installed (binary) engines carry
   them only for macOS hosts (Epic Launcher), and a source build compiles them with UnrealBuildTool's iOS / Apple
   toolchain, which finds its compiler, linker and SDK through Xcode (xcode-select, xcrun). Engine source also needs
   a GitHub account linked to an Epic account (a credential, not needed for the answer).
3. **The Xcode project would not be the problem.** Since UE 5.3 ("Modern Xcode", on by default) the generated
   project (`Intermediate/ProjectFilesIOS/*.xcodeproj`) is a wrapper whose build phase runs
   `Engine/Build/BatchFiles/Mac/XcodeBuild.sh`, i.e. UnrealBuildTool; Swift Build runs such script phases on Linux
   (as for Unity's IL2CPP step). The compile and link work is UnrealBuildTool's, for an iOS target it only drives from
   a Mac.

A Linux path would mean porting UnrealBuildTool's Apple toolchain to Linux (clang with the Darwin SDK and ld64.lld, as
the other shapes here use; its xcode-select / xcrun lookups answered by `linux-bin/`), then building the engine for
iOS from source (hundreds of GB, hours of compiling) — the same kind of work as the .NET and Kotlin/Native toolchains
needed, at much larger scale. Not done in this round.

Sources: Epic, "Creating Remote Builds of Unreal Engine projects for iOS"
(dev.epicgames.com/documentation/en-us/unreal-engine/creating-remote-builds-of-unreal-engine-projects-for-ios),
"Building iOS Projects on Windows" (UE 5.2), "Using Modern Xcode in Unreal Engine"
(dev.epicgames.com/documentation/en-us/unreal-engine/using-modern-xcode-in-unreal-engine).

## React Native on Swift Build (in progress)

A React Native 0.88.1 app with Stripe (0.85, Swift packages, dynamic frameworks as Stripe requires), Skia 2.14,
Reanimated 4.8 and MMKV 4.3: `pod install` on Linux completes and links Stripe's six package products
(cocoapods/linux.rb); `linux-bin/xcodebuild` then compiles most of the 94 pods and stops linking
ReactAppDependencyProvider before ReactCodegen's framework exists (its dependency is declared in Pods.xcodeproj); an
incremental rebuild needed more than 6 GB. React Native and Expo apps in x86Sim's `dev run` still build with
tools/xcbuild.py, which runs them on phones today.

## What is missing, precisely

- **Interface Builder**: neither ibtool compiles a storyboard `<mapView>` with `<standardMapConfiguration>`
  (Overland's Main.storyboard). This repository's ibtool, byte-identical only, refuses view-controller xibs with
  File's Owner outlets / actions, legacy (pre-Xcode 5) xibs, and orders the top-level objects of a xib with labels
  and constraints differently from Apple's (BLKFlexibleHeightBar's LaunchScreen.xib): those go to sweetpad's ibtool,
  whose nibs load in UIKit but are not byte-identical.
- **App Intents metadata**: `AppIntentsPackage` registration, `\(\.$param)` phrases with non-entity parameters,
  string/property queries.
- **Schemes Xcode would generate**: without shared schemes, the app's scheme has no test action here.
- **Vendored binaries without an arm64-simulator slice** (EspBlufi's OpenSSL: x86_64 simulator only) cannot run on
  arm64 simulators, Apple's included; not a Linux gap.
- **Deployment targets below the SDK's range** stop Xcode 27 as they stop Swift Build; the stand-in raises them (said).
