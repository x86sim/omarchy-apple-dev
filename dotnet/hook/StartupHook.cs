using System;
using System.Reflection;
using System.Runtime.InteropServices;

// DOTNET_STARTUP_HOOKS: native libraries of macOS that the iOS SDK's MSBuild tasks load by path, mapped to Linux ones
internal class StartupHook
{
    public static void Initialize()
    {
        AppDomain.CurrentDomain.AssemblyLoad += (_, e) => Hook(e.LoadedAssembly);
        foreach (var a in AppDomain.CurrentDomain.GetAssemblies()) Hook(a);
    }

    static void Hook(Assembly a)
    {
        // every assembly: the resolver only answers for macOS library paths, anything else loads as usual
        if (a.IsDynamic) return;
        try { NativeLibrary.SetDllImportResolver(a, Resolve); } catch (InvalidOperationException) { }
    }

    static IntPtr Resolve(string name, Assembly a, DllImportSearchPath? path)
    {
        switch (name)
        {
            case "/usr/lib/libc.dylib":
            case "/usr/lib/libSystem.dylib":
            case "libSystem.dylib":
                return NativeLibrary.Load(System.IO.Path.Combine(AppContext.GetData("LINUXHOST_DIR") as string ?? System.IO.Path.GetDirectoryName(typeof(StartupHook).Assembly.Location)!, "libmacshim.so"));
        }
        return IntPtr.Zero;
    }
}
