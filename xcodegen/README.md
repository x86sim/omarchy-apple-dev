# XcodeGen on Linux

[XcodeGen](https://github.com/yonaskolb/XcodeGen) is a Swift package that builds and runs on Linux unchanged:
`install.sh` builds a pinned release (2.49.0) with the Linux Swift toolchain, and `xcodegen generate` turns a
`project.yml` into the `.xcodeproj` that `linux-bin/xcodebuild` (Swift Build) then builds.

```
xcodegen/install.sh                       # once: ~1 min, keeps 30 MB
cd MyApp && ../xcodegen/bin/xcodegen generate
../linux-bin/xcodebuild -project MyApp.xcodeproj -scheme MyApp -destination 'generic/platform=iOS Simulator' build
```

In x86Sim, `x86sim dev setup xcodegen` installs it, and `x86sim dev build` / `run` on a directory with a project.yml
generate the project (after `carthage bootstrap` when there is also a Cartfile: XcodeGen's `carthage:` dependencies
read Carthage/Build) and build it.

The setting presets ship as the binary's resource bundle (`XcodeGen_XcodeGenKit.bundle`, next to it), so
`settingPresets` work as on a Mac. Local and remote Swift packages in `packages:` are resolved by Swift Build.

## Verified

[HelioMesquita/Swiftmazing](https://github.com/HelioMesquita/Swiftmazing) (MIT): a project.yml with two local
packages and a remote one (combine-schedulers); generated, built and run on an x86Sim iPhone.
