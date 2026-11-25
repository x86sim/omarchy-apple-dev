# Loaded into every `pod` run on Linux (the `pod` wrapper puts it in RUBYOPT). It answers the few things Podfiles
# and podspec helpers expect of a Mac; the SDK queries themselves (xcrun, xcodebuild -version) are answered by the
# shims in ../flutter/shims, which the wrapper puts first on PATH.
require 'open3'

module OADCocoaPodsLinux
  # bsdtar takes member globs as they are; GNU tar (Linux's /usr/bin/tar) needs --wildcards for them. Expo's
  # precompiled-module check extracts '*.xcframework/Info.plist' with /usr/bin/tar and, with GNU tar, finds nothing.
  def self.tar_args(args)
    return args unless args[0].is_a?(String) && File.basename(args[0]) == 'tar'
    return args if args.include?('--wildcards')
    i = args.index.with_index { |a, n| n > 1 && a.is_a?(String) && !a.start_with?('-') && a.match?(/[*?\[]/) }
    return args unless i
    [*args[0...i], '--wildcards', *args[i..]]
  end
end

module Open3
  class << self
    %i[capture2 capture2e capture3 popen3 popen2 popen2e].each do |m|
      orig = instance_method(m)
      define_method(m) do |*args, **kw, &blk|
        env = args.first.is_a?(Hash) ? [args.shift] : []
        orig.bind(self).call(*env, *OADCocoaPodsLinux.tar_args(args), **kw, &blk)
      end
    end
  end
end
