// x86Sim (omarchy-apple-dev shells/unity/build.sh): an iOS Xcode project export in batchmode on Linux.
//   Unity -batchmode -quit -projectPath DIR -executeMethod X86SimBuild.IOS -buildOutput OUT [-device]
// The scenes are the build settings' enabled ones, else every scene under Assets. IL2CPP (the only iOS backend),
// for the arm64 simulator, or for devices with -device. build.sh puts this file into Assets/Editor for the run only.
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEngine;

public static class X86SimBuild
{
    public static void IOS()
    {
        var args = Environment.GetCommandLineArgs();
        string output = "build/unity-ios";
        bool device = false;
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "-buildOutput" && i + 1 < args.Length) output = args[i + 1];
            if (args[i] == "-device") device = true;
        }
        var scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
        if (scenes.Length == 0)
            scenes = Directory.GetFiles("Assets", "*.unity", SearchOption.AllDirectories).Select(p => p.Replace('\\', '/')).OrderBy(p => p).ToArray();
        if (scenes.Length == 0)
        {
            Debug.LogError("x86sim: no scene to build");
            EditorApplication.Exit(1);
        }
        PlayerSettings.SetScriptingBackend(NamedBuildTarget.iOS, ScriptingImplementation.IL2CPP);
        PlayerSettings.iOS.sdkVersion = device ? iOSSdkVersion.DeviceSDK : iOSSdkVersion.SimulatorSDK;
        PlayerSettings.iOS.simulatorSdkArchitecture = AppleMobileArchitectureSimulator.ARM64;
        var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
        {
            scenes = scenes,
            locationPathName = output,
            target = BuildTarget.iOS,
            options = BuildOptions.None,
        });
        Debug.Log("x86sim: build " + report.summary.result + " (" + string.Join(", ", scenes) + ") -> " + output);
        EditorApplication.Exit(report.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded ? 0 : 1);
    }
}
