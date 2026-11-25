// Preloaded into Node (NODE_OPTIONS=--require) by the `pod` wrapper and the Linux Xcode-project build, for the npm
// packages whose iOS steps assume a Mac although what they need exists on Linux.
//
// expo-modules-autolinking skips its @ExpoModule class scan unless process.platform is 'darwin' ("the scanner is a
// macOS binary"), but expo-modules-macros ships the scanner for Linux too (@expo/modules-macros-linux-*). Without
// the scan, every module class that is not listed in an expo-module.config.json is missing from the app's
// ExpoModulesProvider.swift, and the build stops. The check is rewritten to ask whether the scanner loads.
'use strict';
const Module = require('module');
const path = require('path');

const origCompile = Module.prototype._compile;
Module.prototype._compile = function (content, filename) {
  if (
    typeof content === 'string' &&
    filename.endsWith(path.join('expo-modules-autolinking', 'build', 'platforms', 'apple', 'apple.js'))
  ) {
    content = content.replace(
      /\/\/ The scanner is a macOS binary\.\s*\n(\s*)if \(process\.platform !== 'darwin'\) \{/,
      "// The scanner ships for macOS, Linux and Windows (Linux: the omarchy-apple-dev preload).\n$1if (false) {"
    );
  }
  return origCompile.call(this, content, filename);
};
