param([Parameter(Mandatory=$true)][int]$TestProcessId,
      [Parameter(Mandatory=$true)][string]$ReportPath)
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class BabelanderVisibleWindows {
    public delegate bool Visit(IntPtr window, IntPtr parameter);
    [DllImport("user32.dll")] public static extern bool EnumWindows(Visit visit, IntPtr parameter);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
    public static int Count(uint target) {
        int count = 0;
        EnumWindows((window, parameter) => {
            uint process; GetWindowThreadProcessId(window, out process);
            if (process == target && IsWindowVisible(window)) count++;
            return true;
        }, IntPtr.Zero);
        return count;
    }
}
'@
$process = Get-Process -Id $TestProcessId
$count = [BabelanderVisibleWindows]::Count($TestProcessId)
$report = [ordered]@{
    passed = ($count -eq 0)
    at = (Get-Date).ToString('o')
    test_pid = $TestProcessId
    running = (-not $process.HasExited)
    visible_top_level_windows = $count
    main_window_handle = [long]$process.MainWindowHandle
    scope = 'Read-only Win32 EnumWindows check of the test PID only. No other application names, content or screenshots read or saved. Snapshot, not every instant of the longevity test.'
}
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ReportPath -Encoding utf8
if (-not $report.passed) { throw 'Background test has visible desktop windows.' }
$report | ConvertTo-Json -Compress
