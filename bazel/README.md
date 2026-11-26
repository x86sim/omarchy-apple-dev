# Bazel rules_apple on Linux: not yet

Status (checked 2026-11-25): an iOS app built with [rules_apple](https://github.com/bazelbuild/rules_apple) does not
build on Linux yet. This page says exactly where it stops and what a Linux path needs; nothing here is a workaround.

Tried: Bazel 9.3.3 (bazelisk 1.30.0), rules_apple 5.4.0 with the apple_support (2.9.1+) and rules_swift (4.1.1+) it
pins, its own `examples/ios/HelloWorldSwift`:

```
bazel build //examples/ios/HelloWorldSwift:HelloWorldSwift --platforms=@apple_support//platforms:ios_sim_arm64
ERROR: While resolving toolchains for target //examples/ios/HelloWorldSwift:HelloWorldSwift:
No matching toolchains found for types: @@bazel_tools//tools/cpp:toolchain_type
```

## Where it stops, in order

1. **No Apple C / Objective-C toolchain for a Linux exec platform.** apple_support registers its rules-based Apple
   `cc_toolchain`s (`crosstool/BUILD.toolchains`) with `exec_compatible_with = ["@platforms//os:macos", ...]` only,
   so toolchain resolution finds nothing for an iOS target on a Linux host. Its tools are `wrapped_clang`, `libtool`
   and `strip` wrappers (built from `crosstool/*.cc`) that run `/usr/bin/xcrun <tool>` by absolute path.
2. **No Xcode configuration.** The Xcode version and SDK versions Bazel's `xcode_config` gives the Apple rules come
   from `@local_config_xcode`, which apple_support's `xcode_configure.bzl` fills only when the host is macOS (it runs
   `xcode-locator`, an Objective-C program).
3. **No Swift toolchain for Apple targets.** rules_swift's Apple toolchain is `xcode_swift_toolchain` (registered for
   macOS hosts); on Linux it autoconfigures a toolchain for Linux targets. Its worker (`tools/worker/swift_runner.cc`)
   puts `/usr/bin/xcrun` in front of swiftc for Apple targets, and `tools/common/bazel_substitutions.cc` runs
   `/usr/bin/xcrun --find clang`.
4. **rules_apple's actions call macOS tools by absolute path**: `/usr/bin/xcrun` (9 places: actool / ibtool / momc /
   png / texture atlases / Metal / App Intents / linking), `/usr/bin/codesign`, `/usr/bin/ditto`, `/usr/bin/derq`,
   `/usr/bin/symbolscache` (`apple/internal/*.bzl`), and mark them `requires-darwin`.

## What a Linux path needs

Everything it needs exists in this repository already; what is missing is the Bazel side:

- an apple_support patch (applied with `single_version_override(patches = ...)` in the app's MODULE.bazel) that also
  registers its Apple toolchains for `@platforms//os:linux` exec platforms and runs `xcrun` from PATH, with PATH
  holding this repository's `carthage/bin` + `dotnet/bin` xcrun (clang with an Apple `-target`, ld64.lld, LLVM tools,
  actool, ibtool, codesign);
- a `local_config_xcode` made from the darwin SDK bundle (`xcode_version` 27.2 with the SDK versions in its
  SDKSettings), passed with `--xcode_version_config`;
- a rules_swift patch registering `xcode_swift_toolchain` for Linux exec with the Linux swiftc and the SDK
  (`-sdk`, `-resource-dir`) instead of `/usr/bin/xcrun swiftc`;
- rules_apple patches replacing the absolute `/usr/bin/*` paths with PATH lookups.

`x86sim dev` recognises a rules_apple workspace (MODULE.bazel / WORKSPACE that loads rules_apple) and says this
instead of failing elsewhere.
