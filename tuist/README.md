# Tuist projects on Linux

[Tuist](https://github.com/tuist/tuist) runs on macOS only, but a Tuist project is Swift manifests (Project.swift,
Workspace.swift, Tuist/ProjectDescriptionHelpers) written against one plain-Swift library, ProjectDescription.
`tuist/install.sh` builds that library from the pinned Tuist release (4.218.5) with the Linux Swift toolchain, and
`tuist/bin/tuist generate` does what Tuist does with it: compiles each manifest against it (helpers as their own
module), runs it with `--tuist-dump`, and reads the project from the JSON it prints. The project is then written by
XcodeGen (`xcodegen/install.sh`) as `<Name>.xcodeproj`, inside `<Name>.xcworkspace`, and `linux-bin/xcodebuild`
(Swift Build) builds it.

```
xcodegen/install.sh && tuist/install.sh          # once (~1 min; 40 MB kept)
cd MyApp && ../tuist/bin/tuist generate          # MyApp.xcworkspace
../linux-bin/xcodebuild -workspace MyApp.xcworkspace -scheme MyApp -destination 'generic/platform=iOS Simulator' build
```

In x86Sim, `x86sim dev setup xcodegen` and `x86sim dev setup tuist` install it; `x86sim dev build` / `run` on a
directory with a Tuist Project.swift generate the project (after `carthage bootstrap` when there is a Cartfile) and
build it.

## What it carries over

Targets (products, destinations, deployment targets, Info.plist files and Tuist's default / extended Info.plist, its
default content taken from Tuist's InfoPlistContentProvider, entitlements, source and resource globs with excludes,
asset catalogs, Icon Composer icons, localized resources, settings, configurations and xcconfigs, pre / post build
scripts, a literal PRODUCT_NAME as the product name), dependencies on targets, Swift packages (the project's
`packages:` and Tuist/Package.swift's), frameworks, xcframeworks, libraries and SDKs, the manifest's schemes and
Tuist's automatic ones. A package product's package is found from the packages' own manifests (`swift package
resolve` once, cached in Derived/x86sim).

Not carried over yet: Tuist plugins, a workspace with several projects, dependencies on other projects' targets,
resource synthesizers, Tuist's server features (cache, selective testing, previews). Settings defaults are XcodeGen's
presets (close to Tuist's `.recommended`, not byte-equal).

## Why not Tuist itself

Tuist's Package.swift builds its project generation (TuistLoader, TuistGenerator, TuistKit, ~700 files) for macOS
only. Enabled on Linux (tried with 4.218.5), SwiftPM cannot load the package graph: Tuist builds its macOS binary
through its own Xcode project, and its SwiftPM graph has the same package under two identities (Mockable 0.6.4 needs
`pointfreeco.xctest-dynamic-overlay`, swift-custom-dump needs its renamed `pointfreeco.swift-issue-reporting`, which
declare the same targets), plus a Linux-only target that overlaps TuistCore's sources. Past that, about 30 of those
files use AppKit / Darwin / Security / xcrun. The manifest library is the part that defines what a project is, and it
builds unchanged.

## Verified

[kiliankoe/MensaDresden](https://github.com/kiliankoe/MensaDresden) (MIT): an iOS app that embeds a watchOS app,
seven remote Swift packages, an Icon Composer icon, explicit schemes; generated, built, and run on an x86Sim iPhone.
