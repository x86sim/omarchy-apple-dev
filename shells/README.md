# Cross-platform app shells on Linux

Frameworks that wrap a web or JavaScript app in a native iOS project write that project with their own CLI. Those
CLIs run on Linux; the Xcode project they write then builds with Swift Build ([swiftbuild/](../swiftbuild/README.md),
`linux-bin/xcodebuild`) like any other. x86Sim's `x86sim dev build` / `run` do every step for a shell app
(its `devweb.rs`); by hand:

| Shell | iOS step on Linux | Xcode project | Sample |
|---|---|---|---|
| Capacitor 8 (Ionic) | `npm run build` (when the app has one), `npx cap add ios` once, then `npx cap sync ios` | `ios/App` (`App.xcodeproj`, Capacitor and plugins as Swift packages) | [samples/capacitor-hello](samples/capacitor-hello), [samples/ionic-hello](samples/ionic-hello) |
| NativeScript 9 | [nativescript/ns](nativescript/ns) `prepare ios`: the CLI with its macOS gates lifted, then the Linux metadata generator put in | `platforms/ios` (`<app>.xcodeproj`, the runtime as a Swift package) | [samples/nativescript-hello](samples/nativescript-hello) |
| Godot 4.7 | [godot/export.sh](godot/export.sh): Godot's Linux editor, headless, with its iOS template ("export project only") | `build/godot-ios` (`<name>.xcodeproj`, the engine as a static xcframework); build for iOS devices | [samples/godot-hello](samples/godot-hello) |
| Cordova (cordova-ios 8) | `cordova prepare ios` (adds the platform package.json lists, copies `www/`) | `platforms/ios` (`App.xcworkspace`, CordovaLib and plugins as Swift packages) | [samples/cordova-hello](samples/cordova-hello) |

```
cd samples/capacitor-hello && npm install && npx cap add ios
../../../linux-bin/xcodebuild -project ios/App/App.xcodeproj -scheme App \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath ios/App/build/x86sim build
```

Status and details per shell: [docs/PROJECT-SHAPES.md](../docs/PROJECT-SHAPES.md).
