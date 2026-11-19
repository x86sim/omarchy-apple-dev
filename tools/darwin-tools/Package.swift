// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "darwin-tools",
    platforms: [.macOS(.v13)],
    dependencies: [
        // AssetKit 1.0.0 plus actool 27.0 parity fixes: named colors in every Xcode color space
        // (FINDINGS.md 24, 27), per-size icon renditions (26), actool's BOM layout and
        // single-size icon form (37), the Liquid Glass pre-render of Icon Composer icons, HEIC images,
        // alternate app icons, gray and opacity encoding, Display P3 wide-gamut renditions, and actool's
        // BITMAPKEYS descriptors as value masks, the exact TVL row stride, and symbol templates with relative
        // paths, arcs and weight layers (FINDINGS.md, "Assets.car files that Apple's assetutil rejects"). The
        // macosx platform compiles with macOS 26's 13-attribute
        // rendition-key schema so AppKit resolves symbols and images (60).
        // Icon Composer automatic-gradient background fills as actool 27.2 (AssetKit PR #6).
        // tvOS .brandassets: layered App Icon image stacks (flattened and radiosity images,
        // App Store icon) and Top Shelf images, as actool 27.2 (x86sim/AssetKit
        // omarchy/tvos-brandassets, on top of the revision above).
        .package(url: "https://github.com/x86sim/AssetKit", revision: "c1b180cf6004302f5337dfc3f6f9bdd2680e7ea7"),
        .package(url: "https://github.com/tayloraswift/swift-png", from: "4.5.0"),
    ],
    targets: [
        .target(
            name: "DarwinAssets",
            dependencies: [
                .product(name: "AssetKit", package: "AssetKit"),
                .product(name: "PNG", package: "swift-png"),
            ]
        ),
        // Linux stand-in for Apple's actool: SwiftBuild under xtool, and ship.sh for the app icon.
        .executableTarget(name: "actool", dependencies: ["DarwinAssets", .product(name: "AssetKit", package: "AssetKit")]),
    ]
)
