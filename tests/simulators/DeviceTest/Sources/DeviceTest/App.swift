import SwiftUI

@main
struct DeviceTestApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

struct ContentView: View {
    @State private var taps = 0

    private var platform: String {
        #if os(tvOS)
        "tvOS"
        #elseif os(watchOS)
        "watchOS"
        #elseif os(visionOS)
        "visionOS"
        #else
        "iOS"
        #endif
    }

    private var model: String {
        var info = utsname()
        uname(&info)
        return withUnsafeBytes(of: &info.machine) { String(decoding: $0.prefix { $0 != 0 }, as: UTF8.self) }
    }

    var body: some View {
        VStack(spacing: 12) {
            Text("Built on Linux").font(.headline)
            Text("\(platform) · \(model)")
            Text(ProcessInfo.processInfo.operatingSystemVersionString).font(.footnote)
            Button("Taps: \(taps)") { taps += 1 }
        }
        .padding()
    }
}
