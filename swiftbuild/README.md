# Xcode projects on Linux: Swift Build

Xcode projects and workspaces (`.xcodeproj`, `.xcworkspace`, CocoaPods workspaces) build here with **Swift Build**,
Apple's open-source build engine: the same engine Xcode uses, with Xcode's own build-setting specs (every product
type, settings defaults, embedding of extensions / watch apps / App Clips, signing, Info.plist processing, Swift
packages). It is driven by [sweetpad](https://github.com/sweetpad-dev/sweetpad)'s Linux CLI (MIT), which turns the
workspace into Swift Build's project model and stands in for the Xcode tools Linux does not have. Both are built on
Linux by their projects; `install.sh` pins one release by its SHA-256.

```
swiftbuild/install.sh                     # once: ~220 MB under ~/.local/share/omarchy-apple-dev/swiftbuild
linux-bin/xcodebuild -workspace App.xcworkspace -scheme App -destination 'generic/platform=iOS Simulator' build
```

`linux-bin/xcodebuild` is the xcodebuild command line on top of it (build, test, archive, -exportArchive,
-showBuildSettings, -list, -version, -showsdks), so CI scripts, Makefiles and fastlane run unchanged; put
`linux-bin` on PATH. Tests run on an x86Sim phone (`x86sim test`). In x86Sim, `x86sim dev build` / `run` use it for
any Xcode project.

`install.sh` also adds three things Swift Build reads to the darwin SDK bundle: Xcode's `version.plist` (from
xtool's SDK stamp), the Swift toolchain's `<swift/bridging>` headers and `usr/lib/swift/clang`.

## Why Swift Build and not tools/xcbuild.py

Decided 2026-11-25 (x86Sim's at2-xcode round), by building the same real projects with both:

| Project | Shape | Swift Build | xcbuild.py |
|---|---|---|---|
| NextSunnyDay | SwiftUI app, widget, watch app with its own widget, 19 local packages | every product, 15 s | per-target SDKs, watch embedding, packages missing |
| Cronica | app + single-target watch app + widget + share extension, local + 4 remote packages (Sentry) | 2081/2169 tasks in 64 s before the App Intents step (see gaps) | same as above |
| WordOfTheDay | workspace: app project + framework project, Alamofire, widget, watchapp2 + extension | every product (the repo itself lacks a source file) | same |
| Shimmer | Objective-C workspace: static library + framework + app | stops in a script phase (`/bin/ln -h`, see gaps) | fails at the first copy phase |

xcbuild.py (written for CocoaPods workspaces) would have to re-implement Xcode's build system to reach that:
per-target platforms, schemes, package resolution, product embedding, signing. Swift Build already is that system and
Apple maintains it. xcbuild.py stays, frozen except for fixes, as the fallback (`XCODEBUILD_ENGINE=xcbuild`) and for
`xcodebuild build` in a Swift package directory (Expo's scripts). `tools/xcodeproj2xtool.py` stays for turning a
project into an xtool package (editing, SourceKit-LSP), not for building one.

## Known gaps (sweetpad 0.1.29, Swift Build 6.4.0)

- **App Intents metadata**: the Linux App Intents processor refuses some constructs Apple's accepts
  (`AppIntentsPackage` registration; `\(\.$param)` in App Shortcut phrases for non-entity parameters). The
  xcodebuild stand-in then builds with `LM_SKIP_METADATA_EXTRACTION=YES` and says so: the app runs, its App
  Shortcuts are not registered. Xcode 27.2 builds both (checked on a Mac).
- **Script phases with BSD-only flags at absolute paths** (`/bin/ln -sfh`): script phases run in a sandbox with the
  host's GNU tools; Xcode runs them with macOS's. Fix: `ln -sfn` (same meaning) in the project.
- **Deployment targets below the SDK's range** are errors, as in Xcode 27.2 (checked on a Mac). The stand-in retries
  with the SDK minimum when no target of the project sets a higher one, and says so (`XCODEBUILD_STRICT=1`: stop).
- **Schemes Xcode generates** (a project with no shared schemes): sweetpad's do not include the app's test target, so
  `xcodebuild test` finds no tests there; share the scheme in Xcode or use one that lists them.
- **UI-test targets** need Xcode's XCTRunner.app, which xtool's SDK does not carry: a scheme with a UI-test target
  fails build-for-testing. Unit tests (XCTest and Swift Testing) run.
- **Embedded static frameworks** (Sentry's static xcframework): Swift Build links a stub binary with clang and no
  `-fuse-ld`; `swiftbuild/bin/ld` sends that link to ld64.lld (the stand-in puts it first on PATH).
- **Interface Builder files**: compiled by the fork's Linux `ibtool` (the SDK bundle's), which writes only what is
  byte-identical to Apple's ibtool and refuses the rest; see docs/PROJECT-SHAPES.md for what it refuses.
