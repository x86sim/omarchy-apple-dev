# Cross-platform app shells on Linux

Frameworks that wrap a web or JavaScript app in a native iOS project write that project with their own CLI. Those
CLIs run on Linux; the Xcode project they write then builds with Swift Build ([swiftbuild/](../swiftbuild/README.md),
`linux-bin/xcodebuild`) like any other. x86Sim's `x86sim dev build` / `run` do every step for a shell app
(its `devweb.rs`); by hand:

| Shell | iOS step on Linux | Xcode project | Sample |
|---|---|---|---|
| Capacitor 8 (Ionic) | `npm run build` (when the app has one), `npx cap add ios` once, then `npx cap sync ios` | `ios/App` (`App.xcodeproj`, Capacitor and plugins as Swift packages) | [samples/capacitor-hello](samples/capacitor-hello) |

```
cd samples/capacitor-hello && npm install && npx cap add ios
../../../linux-bin/xcodebuild -project ios/App/App.xcodeproj -scheme App \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath ios/App/build/x86sim build
```

Status and details per shell: [docs/PROJECT-SHAPES.md](../docs/PROJECT-SHAPES.md).
