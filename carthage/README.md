# Carthage on Linux

[Carthage](https://github.com/Carthage/Carthage) 0.40.0, built here from source with the Linux Swift toolchain, runs
`carthage bootstrap` / `update` / `build` for an app's Cartfile on Linux: it resolves and checks out the dependencies,
installs the prebuilt xcframeworks their releases ship, and builds the others from their own Xcode projects with
`linux-bin/xcodebuild` (Apple's Swift Build), into `Carthage/Build/*.xcframework` as on a Mac. The app's Xcode
project then builds with `linux-bin/xcodebuild` too.

```
carthage/install.sh                                   # once: ~2 min, keeps 12 MB
cd MyApp                                              # a Cartfile next to MyApp.xcodeproj
../carthage/bin/carthage bootstrap --use-xcframeworks --platform iOS --cache-builds
../linux-bin/xcodebuild -project MyApp.xcodeproj -scheme MyApp -destination 'generic/platform=iOS Simulator' build
```

In x86Sim, `x86sim dev setup carthage` installs it and `x86sim dev build` / `run` on a directory with a Cartfile
runs the bootstrap (for the phone's platform) before building the app.

## What makes it run here

- `install.sh` pins Carthage 0.40.0 by its commit, resolves its pinned dependencies and applies `patches/`: Linux
  stand-ins for what Carthage takes from macOS (Launch Services type identifiers by extension, `copyfile`,
  CommonCrypto's SHA-256, `<mach-o/loader.h>` constants, KVC on `xcodebuild -showsdks -json`, `atexit_b`), the
  FoundationNetworking imports, one URLSession for the whole run (Linux Foundation crashes when a session is freed
  while its transfer handle is alive), Linux's `swift --version` output, and an empty device triple suffix read as no
  variant when an xcframework is updated in place.
- `bin/carthage` runs it with `bin/` and `linux-bin/` first on PATH and TMPDIR off `/tmp`. `bin/xcrun` sends
  `xcodebuild` to `linux-bin/xcodebuild`, `swift` to the Linux toolchain, `dwarfdump` / `lipo` to LLVM's, answers
  `simctl list` with one simulator per simulator SDK, and passes everything else to `dotnet/bin/xcrun`.
- `linux-bin/xcodebuild` (Swift Build) does what Carthage asks of xcodebuild: `-list`, `-showBuildSettings`
  (nothing for a scheme that builds no target, as with `-skipUnavailableActions`), `archive` of framework schemes
  (`SKIP_INSTALL=YES`: the products in DerivedData's `ArchiveIntermediates`, where Carthage reads them), `build` for
  the simulator, `-showsdks -json` and `-create-xcframework` (`tools/xcframework.py`).
- Dependencies whose build scripts ask for Xcode (`xcode-select -p`, `$DEVELOPER_DIR/usr/bin/xcodebuild`) get
  `linux-bin/xcode-select` and the SDK bundle's `Developer/usr/bin` (made by `swiftbuild/install.sh`).

## Prebuilt binaries

A dependency's release asset (`*.xcframework.zip`) is installed when its Swift module is usable here: a framework
built with an older Swift and no module interface is rejected and built from source instead, exactly as Carthage
does on a Mac with a newer Xcode (realm-swift 10.45's binary, built with Swift 5.9, is). `binary` entries (JSON
specs) download the same way.

## Verified

[demolaf/movies-uikit](https://github.com/demolaf/movies-uikit) (MIT, UIKit + RxSwift): Alamofire 5.8.1,
SDWebImage 5.18.7 and Realm / RealmSwift 10.45.2 built from their Xcode projects, RxSwift 6.6.0 and RiveRuntime 5.7.0
from their prebuilt xcframeworks; the app built with Swift Build and ran on an x86Sim iPhone.
