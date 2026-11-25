# Sourced by the rust/ scripts: where the Darwin SDK and its linker are.
# ios_sdk_paths sim|device sets IOS_BUNDLE, IOS_SDK (the iPhoneSimulator / iPhoneOS SDK), IOS_LD (the bundle's
# ld64.lld, which records the SDK version as Xcode does), IOS_TRIPLE (clang's) and IOS_RUST_TARGET (rustc's).
# DARWIN_SDK_BUNDLE, IOS_SIM_SDK / IOS_DEVICE_SDK and IPHONEOS_DEPLOYMENT_TARGET override.

ios_sdk_bundle() {
  _ios_b=${DARWIN_SDK_BUNDLE:-${XDG_CONFIG_HOME:-$HOME/.config}/swiftpm/swift-sdks/darwin.artifactbundle}
  [ -d "$_ios_b" ] || _ios_b=$HOME/.swiftpm/swift-sdks/darwin.artifactbundle
  [ -d "$_ios_b" ] || _ios_b=$HOME/.config/swiftpm/swift-sdks/darwin.artifactbundle
  [ -d "$_ios_b" ] || { echo "rust/ios: no Darwin SDK (darwin.artifactbundle): run install-toolchain.sh first" >&2; return 1; }
  IOS_BUNDLE=$_ios_b
}

ios_sdk_paths() {
  ios_sdk_bundle || return 1
  _ios_min=${IPHONEOS_DEPLOYMENT_TARGET:-17.0}
  case "$1" in
    sim)
      IOS_SDK=${IOS_SIM_SDK:-$IOS_BUNDLE/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk}
      IOS_TRIPLE=arm64-apple-ios$_ios_min-simulator
      IOS_RUST_TARGET=aarch64-apple-ios-sim ;;
    device)
      IOS_SDK=${IOS_DEVICE_SDK:-$IOS_BUNDLE/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk}
      IOS_TRIPLE=arm64-apple-ios$_ios_min
      IOS_RUST_TARGET=aarch64-apple-ios ;;
    *) echo "ios_sdk_paths: sim or device, not $1" >&2; return 1 ;;
  esac
  [ -d "$IOS_SDK" ] || { echo "rust/ios: $IOS_SDK is missing: re-run install-toolchain.sh" >&2; return 1; }
  IOS_LD=$IOS_BUNDLE/toolset/bin/ld64.lld
  [ -x "$IOS_LD" ] || IOS_LD=$(command -v ld64.lld) || { echo "rust/ios: no ld64.lld" >&2; return 1; }
  export IPHONEOS_DEPLOYMENT_TARGET=$_ios_min
}
