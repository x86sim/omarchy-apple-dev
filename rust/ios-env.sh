# Source it to build Rust for iOS on Linux with plain cargo (or a tool that runs cargo: dx, tauri):
#   . rust/ios-env.sh            # both targets
#   cargo build --target aarch64-apple-ios-sim
# Sets, for aarch64-apple-ios-sim and aarch64-apple-ios: the linker (rust/ios-cc), CC / CXX / AR / CFLAGS for
# cc-rs and cmake builds, bindgen's clang arguments; puts an xcrun on PATH that answers SDK queries from the Darwin SDK
# (rustc, cc-rs and build scripts ask it, as on a Mac); and SDKROOT for IOS_ENV_TARGET=sim|device (default sim).
_ios_env_dir=$(CDPATH= cd -P "$(dirname "${BASH_SOURCE:-$0}")" && pwd -P)
. "$_ios_env_dir/ios-sdk.sh"

_ios_env_one() {  # sim|device
  ios_sdk_paths "$1" || return 1
  _ios_T=$(echo "$IOS_RUST_TARGET" | tr 'a-z-' 'A-Z_')
  _ios_u=$(echo "$IOS_RUST_TARGET" | tr '-' '_')
  export "CARGO_TARGET_${_ios_T}_LINKER=$_ios_env_dir/$IOS_RUST_TARGET-cc"
  export "CC_${_ios_u}=$_ios_env_dir/$IOS_RUST_TARGET-cc"
  export "CXX_${_ios_u}=$_ios_env_dir/$IOS_RUST_TARGET-cc"
  export "AR_${_ios_u}=$(command -v llvm-ar || echo ar)"
  export "CFLAGS_${_ios_u}=-isysroot $IOS_SDK"
  export "CXXFLAGS_${_ios_u}=-isysroot $IOS_SDK"
  # bindgen (objc / C bindings generated at build time) parses the SDK's headers with libclang
  export "BINDGEN_EXTRA_CLANG_ARGS_${_ios_u}=--target=$IOS_TRIPLE -isysroot $IOS_SDK"
  unset _ios_T _ios_u
}

if _ios_env_one device && _ios_env_one sim && ios_sdk_paths "${IOS_ENV_TARGET:-sim}"; then
  export SDKROOT=$IOS_SDK
  case ":$PATH:" in *":$_ios_env_dir/bin:"*) ;; *) export PATH=$_ios_env_dir/bin:$PATH ;; esac
else
  echo "rust/ios-env.sh: the iOS build environment is not set" >&2
fi
unset -f _ios_env_one
