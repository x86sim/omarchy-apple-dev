# Loaded into fastlane on Linux (linux-bin/fastlane puts it in RUBYOPT): fastlane looks for Xcode only on a Mac;
# here "Xcode" is the dev toolchain's linux-bin/xcodebuild (Swift Build + x86Sim), so gym, scan and the other
# xcodebuild-driven actions run their usual commands.
module OADFastlaneLinux
  BIN = File.expand_path('../linux-bin', __dir__)

  def self.version
    @version ||= begin
      out = `"#{BIN}/xcodebuild" -version 2>/dev/null`
      out[/Xcode (\d+(?:\.\d+)*)/, 1]
    end
  end

  # fastlane defines these in FastlaneCore::Helper's module body; replace them once that body has run
  def self.patch(helper)
    helper.define_singleton_method(:xcode_path) { File.expand_path('../fastlane/Developer', BIN) + '/' }
    helper.define_singleton_method(:xcode_version) { OADFastlaneLinux.version }
  end
end

TracePoint.new(:end) do |tp|
  if defined?(FastlaneCore::Helper) && tp.self.equal?(FastlaneCore::Helper)
    OADFastlaneLinux.patch(FastlaneCore::Helper)
  end
end.enable
