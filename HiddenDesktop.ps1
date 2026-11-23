# Starts a program on its own Windows desktop, which is never shown: its windows never appear on Host's screens or
# taskbar and never take focus (2026-11-16 "it's popping right up on my main screen"). The game insists on a real
# window (PiratesBase sets base.windowType = 'onscreen' and calls getPointer/requestProperties on it), so an
# offscreen buffer is not an option. The desktop stays alive while this PowerShell process or the program runs.
# The program runs at Idle priority with no console window; stdout/stderr go to files.
if (-not ('HiddenDesk' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

public static class HiddenDesk {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct STARTUPINFO {
        public int cb; public string lpReserved; public string lpDesktop; public string lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2; public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct PROCESS_INFORMATION { public IntPtr hProcess, hThread; public int dwProcessId, dwThreadId; }
    [StructLayout(LayoutKind.Sequential)]
    struct SECURITY_ATTRIBUTES { public int nLength; public IntPtr lpSecurityDescriptor; public int bInheritHandle; }

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern IntPtr CreateDesktopW(string name, IntPtr device, IntPtr devmode, int flags, uint access, IntPtr sa);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool CreateProcessW(string app, StringBuilder cmd, IntPtr pa, IntPtr ta, bool inherit, uint flags,
        IntPtr env, string cwd, ref STARTUPINFO si, out PROCESS_INFORMATION pi);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern IntPtr CreateFileW(string name, uint access, uint share, ref SECURITY_ATTRIBUTES sa, uint disp,
        uint flags, IntPtr template);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);

    static IntPtr desk = IntPtr.Zero;

    // Inheritable write handle; shared read+write so the log can be read while the program runs.
    static IntPtr OutFile(string path) {
        var sa = new SECURITY_ATTRIBUTES();
        sa.nLength = Marshal.SizeOf(sa); sa.bInheritHandle = 1;
        IntPtr h = CreateFileW(path, 0x40000000, 3, ref sa, 2, 0x80, IntPtr.Zero);   // GENERIC_WRITE, CREATE_ALWAYS
        if (h == new IntPtr(-1)) throw new Win32Exception(Marshal.GetLastWin32Error(), path);
        return h;
    }

    public static Process Start(string desktop, string exe, string args, string cwd, string stdout, string stderr) {
        if (desk == IntPtr.Zero) {
            desk = CreateDesktopW(desktop, IntPtr.Zero, IntPtr.Zero, 0, 0x10000000, IntPtr.Zero);   // GENERIC_ALL
            if (desk == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "CreateDesktop");
        }
        IntPtr o = OutFile(stdout), e = OutFile(stderr);
        var si = new STARTUPINFO();
        si.cb = Marshal.SizeOf(si);
        si.lpDesktop = @"WinSta0\" + desktop;
        si.dwFlags = 0x101;                  // STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW
        si.wShowWindow = 0;                  // SW_HIDE
        si.hStdOutput = o; si.hStdError = e;
        PROCESS_INFORMATION pi;
        var cmd = new StringBuilder("\"" + exe + "\" " + args);
        // CREATE_NO_WINDOW | IDLE_PRIORITY_CLASS; the environment is this process's
        bool ok = CreateProcessW(null, cmd, IntPtr.Zero, IntPtr.Zero, true, 0x08000040, IntPtr.Zero, cwd, ref si, out pi);
        int err = Marshal.GetLastWin32Error();
        CloseHandle(o); CloseHandle(e);
        if (!ok) throw new Win32Exception(err, "CreateProcess");
        Process p = Process.GetProcessById(pi.dwProcessId);
        IntPtr keep = p.Handle;              // open before closing ours, so ExitCode works after it exits
        CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
        return p;
    }
}
'@
}

# Bug reporter (PLAYERBOTS, 11-22): every bot run makes sure the one bugreport.py watcher is up (a second copy exits at
# once when bugreport.pid is alive) and leaves walk-<run>.acct so its bug files name the test pirate.
# pythonw = no console window ever; the watcher sets itself to Idle priority.
function Start-BugReport($logBase, $acct) {
  try {
    Set-Content -Encoding ascii "$logBase.acct" $acct
    # pbots' low-memory settings page (BOT_PRC, e.g. pbot\prc\strip-gl.prc): its client errors are filed BOT
    if ($env:BOT_PRC) { Set-Content -Encoding ascii "$logBase.prc" $env:BOT_PRC } else { Remove-Item "$logBase.prc" -ErrorAction SilentlyContinue }
    Start-Process 'C:\Panda3D-1.11.0-x64\python\pythonw.exe' -ArgumentList "`"$PSScriptRoot\bugreport.py`"" `
      -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
  } catch { "bug reporter not started: $_" }
}
