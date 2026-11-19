# tvOS, watchOS and visionOS: Linux builds against Xcode 27.2

Date: 2026-11-18. Linux: x86_64 Arch, Swift 6.4.2, xtool `x86sim/xtool@2c545ff`
(branch `omarchy-platforms`), SDK built by that xtool from an Xcode 27.2 (27B52)
`Xcode.app`, stamp `epoch=5,darwinTools=1.1.0,oam=1.4.1`.
Reference: Xcode 27.2 on macOS 27.0 (26A428), same source, `xcodebuild -configuration
Release CODE_SIGNING_ALLOWED=NO` for `generic/platform=iOS|tvOS|watchOS|visionOS`.

The app: one SwiftUI file (`@main App`, `WindowGroup`, `VStack`, `Text`, a `Button`
with `@State`), deployment targets iOS 18.0, tvOS 18.0, watchOS 11.0, visionOS 2.0.
Linux command: `xtool dev build -c release --triple <triple>` with
`arm64-apple-ios`, `arm64-apple-tvos`, `arm64_32-apple-watchos`, `arm64-apple-xros`.

Compared: the bundle file list, every Info.plist key, and the Mach-O load commands
(`llvm-objdump --macho --private-headers`; for watchOS both slices).

## Identical

- Bundle layout on all four (`Hello`, `Info.plist`, `PkgInfo`, `_CodeSignature` absent on both).
- Info.plist: every key and value, including `CFBundleSupportedPlatforms`,
  `UIDeviceFamily`, `MinimumOSVersion`, `DTPlatformName`, `DTSDKName`, `DTSDKBuild`
  (24B8118, 24K122, 24S118, 24N120), `DTXcode` 2720, `DTXcodeBuild` 27B52, and the
  watchOS `WKApplication`, `WKRunsIndependentlyOfCompanionApp`, `MinimumOSVersion~ipad`.
- `LC_BUILD_VERSION` platform, minos and sdk (27.2) on all four.
- `LC_RPATH /usr/lib/swift`, dylib list, segments and sections on iOS, tvOS, visionOS
  and the watchOS arm64 slice (minos 26.0 on both).
- watchOS binary is universal arm64_32 + arm64 on both.

## Still different

| What | Mac | Linux | Why |
|---|---|---|---|
| watchOS arm64_32 fixups | `LC_DYLD_CHAINED_FIXUPS`, `LC_DYLD_EXPORTS_TRIE` | `LC_DYLD_INFO_ONLY`, plus `__stub_helper`/`__la_symbol_ptr` | `ld64.lld` 21: "-fixup_chains is only supported on x86_64 and arm64 targets". watchOS loads the opcode format. |
| Linker identity in `LC_BUILD_VERSION` | `ld 27106.1` | `lld 21.1.6` | different linker |
| `LC_SOURCE_VERSION 0.0` | present | absent | lld does not write it |
| `BuildMachineOSBuild` | `26A428` | absent | no macOS host; set `BUILD_MACHINE_OS_BUILD` to copy it |
| `LC_RPATH @executable_path/Frameworks` | absent | present | xtool sets it for embedded frameworks; Xcode's app templates set it too, the bare reference project did not |
| iOS orientation keys | absent | present | xtool defaults; Xcode templates set them, the bare reference project did not |

## Signing

`xtool dev build --sign --triple arm64-apple-tvos` on Linux with a free team created
`XTL tvOS profile <id>`, Platform `tvOS`, listing the registered Apple TV. Getting a
development certificate for Linux revoked the Mac's (free-team limit).

## Not run

No install or launch on an Apple TV, Apple Watch or Vision Pro; no asset catalog,
storyboard or extension in the test app; no App Store validation for the new platforms.
