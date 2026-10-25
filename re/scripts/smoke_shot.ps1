param([string]$Exe, [string[]]$ExeArgs, [int[]]$ShotsAt = @(8, 20, 35), [string]$OutPrefix = "$PSScriptRoot\..\shots\smoke")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public struct RECT { public int L, T, R, B; }
public static class W {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[W]::SetProcessDPIAware() | Out-Null
New-Item -ItemType Directory -Force (Split-Path $OutPrefix) | Out-Null
$p = Start-Process -FilePath $Exe -ArgumentList $ExeArgs -WorkingDirectory (Split-Path $Exe) -PassThru
$t0 = Get-Date
foreach ($s in $ShotsAt) {
  while (((Get-Date) - $t0).TotalSeconds -lt $s) { Start-Sleep -Milliseconds 250 }
  $p.Refresh()
  if ($p.HasExited) { "process exited with code $($p.ExitCode) before t=$s"; break }
  $h = $p.MainWindowHandle
  if ($h -eq [IntPtr]::Zero) { "t=${s}: no main window yet"; continue }
  [W]::SetForegroundWindow($h) | Out-Null
  Start-Sleep -Milliseconds 300
  $r = New-Object RECT; [W]::GetWindowRect($h, [ref]$r) | Out-Null
  $w = $r.R - $r.L; $hh = $r.B - $r.T
  $bmp = New-Object System.Drawing.Bitmap $w, $hh
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
  $f = "${OutPrefix}_t$s.png"; $bmp.Save($f); $g.Dispose(); $bmp.Dispose()
  "t=${s}: saved $f (${w}x${hh}) title='$($p.MainWindowTitle)'"
}
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force; "stopped" }
