// Preloaded into Node (NODE_OPTIONS=--require) by shells/nativescript/ns: the NativeScript CLI's iOS steps on Linux.
// What they need exists here (the Darwin SDK, Swift Build, the xcodebuild stand-in, CocoaPods' Ruby), but the CLI
// gates them on macOS in three places:
//
// - ios-project-service.js: the iOS platform targets only "darwin" (`ns prepare ios`: "cannot be executed"), and its
//   validate() returns nothing off macOS, which the command base reads as "cannot execute".
// - @nativescript/doctor's sys-info.js: the Xcode version is read only on macOS; prepare's Podfile step then fails
//   with "xcodebuild execution failed". linux-bin/xcodebuild answers -version.
'use strict';
const Module = require('module');
const path = require('path');

const origCompile = Module.prototype._compile;
Module.prototype._compile = function (content, filename) {
  if (typeof content === 'string' && filename.endsWith(path.join('lib', 'services', 'ios-project-service.js'))) {
    content = content.replace('targetedOS: ["darwin"]', 'targetedOS: ["darwin", "linux"]');
    content = content.replace(
      /(async validate\(projectData, options, notConfiguredEnvOptions\) \{\s*if \(!this\.\$hostInfo\.isDarwin\) \{\s*)return;/,
      '$1return { checkEnvironmentRequirementsOutput: { canExecute: true } };'
    );
  }
  if (typeof content === 'string' && filename.endsWith(path.join('@nativescript', 'doctor', 'dist', 'sys-info.js'))) {
    content = content.replace(
      /(getXcodeVersion\(\) \{\s*return this\.getValueForProperty\(\(\) => this\.xCodeVerCache, async \(\) => \{\s*if \()this\.hostInfo\.isDarwin\)/,
      '$1this.hostInfo.isDarwin || process.platform === "linux")'
    );
  }
  return origCompile.call(this, content, filename);
};
