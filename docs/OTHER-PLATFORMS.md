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
| Simulators | `arm64-apple-{ios,tvos,watchos,xros}-simulator` | for Xcode's simulators or x86Sim (`tests/simulators/run.sh`) |

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

How close the output is to Xcode's, and what is still different: [receipts/2026-11-18-tvos-watchos-visionos-parity.md](../receipts/2026-11-18-tvos-watchos-visionos-parity.md).

## Apple TV: build, sign and install from Linux

A tvOS app's icon is a `.brandassets` set in its asset catalog (layered App Icon, App Store
icon, Top Shelf images). Name it in `xtool.env` as `APP_ICON='App Icon & Top Shelf Image'`
(the set's name). Then, in the xtool project:

```bash
TRIPLE=arm64-apple-tvos ./ship.sh --device     # build, compile the icon and resources
xtool sign "xtool/<App>.app"                    # register, fetch the tvOS profile, sign
```

`xtool sign` registers the bundle ID as written, so the app replaces one built by Xcode
with the same ID (its data stays). Free-team profiles last 7 days.

Pair the Apple TV once (Settings > Remotes and Devices > Remote App and Devices on the TV,
then `pymobiledevice3 remote pair` and the PIN it shows). Installing needs a tunnel to the
TV; pymobiledevice3's `tunneld`, run as a root service, keeps one open so installs run as
your user:

```bash
sed -e "s|@USER@|$USER|" -e "s|@UID@|$(id -u)|" -e "s|@GID@|$(id -g)|" \
    -e "s|@VENV@|$HOME/pymobile3-venv|" tools/systemd/pymobiledevice3-tunneld.service.in \
  | sudo tee /etc/systemd/system/pymobiledevice3-tunneld.service >/dev/null
sudo systemctl enable --now pymobiledevice3-tunneld
```

It listens on 127.0.0.1:49151 and reads the pairing records from your
`~/.local/share/pymobiledevice3`. Then, with the TV's hardware UDID (`curl
127.0.0.1:49151` lists the tunnels; `--tunnel` takes the UDID, not the pairing identifier):

```bash
pymobiledevice3 apps install "xtool/<App>.app" --tunnel <UDID>
pymobiledevice3 developer dvt launch <bundle id> --tunnel <UDID>
```

`developer dvt` needs only Developer Mode on the TV. `developer core-device` commands also
need the developer disk image, which `mounter auto-mount` could not mount on tvOS 27
(`cryptexd ... invalid asset: ginf`).

Not done yet: installing on a Vision Pro (pairs over the network like the Apple TV) and on a
watch (through its paired iPhone), building a watch app embedded in an iPhone app (signing one works), and no-Xcode mode.
