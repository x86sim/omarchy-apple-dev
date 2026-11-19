// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "DeviceTest",
    platforms: [.iOS(.v18), .tvOS(.v18), .watchOS(.v11), .visionOS(.v2)],
    products: [.library(name: "DeviceTest", targets: ["DeviceTest"])],
    targets: [.target(name: "DeviceTest")]
)
