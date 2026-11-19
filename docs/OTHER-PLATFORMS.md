# tvOS, watchOS and visionOS

Full mode (Xcode download) builds and signs apps for Apple TV, Apple Watch and
Apple Vision Pro on Linux with the same xtool project as an iPhone app. The SDK
step copies the `AppleTVOS`, `WatchOS` and `XROS` platforms out of Xcode along with
iPhoneOS; an SDK built before this (stamp `epoch=4`) is rebuilt by the installer.

| Target | Triple | Output |
|---|---|---|
| Apple TV | `arm64-apple-tvos` | `Release-appletvos` |
| Apple Watch | `arm64_32-apple-watchos` | universal arm64_32 + arm64, like Xcode; `XTOOL_WATCHOS_ARM64=0` keeps arm64_32 only |
| Vision Pro | `arm64-apple-xros` | `Release-xros` |

Declare the platform in `Package.swift` and build with its triple:

```swift
platforms: [.iOS(.v18), .tvOS(.v18), .watchOS(.v11), .visionOS(.v2)],
```

```bash
xtool dev build --triple arm64-apple-tvos            # build
xtool dev build --sign --triple arm64-apple-tvos     # build and sign for development
```

xtool writes the Info.plist keys Xcode 27 writes for each platform
(`CFBundleSupportedPlatforms`, `UIDeviceFamily`, `MinimumOSVersion` from the
package's platform version, the `DT*` keys, and for watchOS a standalone app:
`WKApplication`, `WKRunsIndependentlyOfCompanionApp`). Keys in your own Info.plist
win. Signing makes a `TVOS_APP_DEVELOPMENT` profile for Apple TV apps; watch and
Vision Pro devices go into the usual iOS development profile.

How close the output is to Xcode's, and what is still different (watchOS arm64_32
uses classic dyld fixups because `ld64.lld` has no chained fixups for that
architecture): [receipts/2026-11-18-tvos-watchos-visionos-parity.md](../receipts/2026-11-18-tvos-watchos-visionos-parity.md).

Not done yet: installing on the devices (Apple TV and Vision Pro pair over the
network, a watch app installs through its paired iPhone), watch apps embedded in an
iPhone app, simulators for these platforms, and no-Xcode mode.
