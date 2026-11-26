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

# After a successful `pod install` / `pod update`: what Xcode does with the workspace that Swift Build (the engine
# behind linux-bin/xcodebuild) needs spelled out in the project. Each fix is idempotent.
module OADCocoaPodsLinux
  def self.after_install(dir)
    require 'xcodeproj'
    projects = Dir.glob(File.join(dir, '*.xcodeproj')) + Dir.glob(File.join(dir, 'Pods', 'Pods.xcodeproj'))
    projects.each do |path|
      project = Xcodeproj::Project.open(path)
      changed = false
      project.native_targets.each do |target|
        # Swift package products in packageProductDependencies: Xcode links them even with no Frameworks build
        # file (React Native's spm_dependency only adds the dependency); Swift Build links only what the phase lists
        deps = target.package_product_dependencies
        next if deps.empty?
        phase = target.frameworks_build_phase
        linked = phase.files.map(&:product_ref).compact
        (deps - linked).each do |dep|
          bf = project.new(Xcodeproj::Project::Object::PBXBuildFile)
          bf.product_ref = dep
          phase.files << bf
          changed = true
          puts "[linux] #{target.name}: link package product #{dep.product_name}"
        end
      end
      # Icon Composer .icon folders `expo prebuild` adds with lastKnownFileType "unknown": Xcode still hands them to
      # actool, Swift Build only by their type
      project.files.each do |f|
        next unless f.path.to_s.end_with?('.icon') && f.last_known_file_type != 'folder.iconcomposer.icon'
        f.last_known_file_type = 'folder.iconcomposer.icon'
        f.explicit_file_type = nil
        changed = true
        puts "[linux] #{File.basename(path)}: #{f.path} is an Icon Composer icon"
      end
      project.save if changed
    end
    # CocoaPods' embed and strip scripts call /usr/bin/codesign; on Linux codesign is on PATH (cocoapods/shims)
    Dir.glob(File.join(dir, 'Pods', 'Target Support Files', '**', '*.sh')).each do |script|
      text = File.read(script)
      next unless text.include?('/usr/bin/codesign')
      File.write(script, text.gsub('/usr/bin/codesign', 'codesign'))
    end
  rescue StandardError => e
    warn "[linux] could not adjust the workspace for Swift Build: #{e.message}"
  end
end

if %w[install update].include?(ARGV[0]) && File.basename($PROGRAM_NAME) == 'pod'
  at_exit { OADCocoaPodsLinux.after_install(Dir.pwd) if $!.nil? || ($!.is_a?(SystemExit) && $!.success?) }
end
