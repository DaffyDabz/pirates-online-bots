param([string]$Tag = 'MEAS', [int]$Secs = 300, [int]$Grace = 300, [switch]$NoStrip, [string]$Prc = 'strip.prc', [int]$Fps = 10, [int]$MinFreeGB = 10, [switch]$Resize, [switch]$EarlyOff)
# pbots (11-22): one hidden bot game that measures its own memory (m_measure.py), with pbot/prc/strip.prc joined to
# the walker's MUTE page (-NoStrip = the plain game, for a baseline). Copy of run_walk.ps1's slot rules:
#  - takes run.lock (ONE hidden game at a time) and waits for the slot like every other run
#  - respects the two-strike stop (2 strikes = exit, never relaunch) but NEVER WRITES A STRIKE: this is a measurement,
#    not a bot game test, so a failed run here never stops the bot for the other lanes
#  - waits until at least -MinFreeGB of RAM is free before starting the game (the strip may not hold on the first try)
# Needs: BOT_ACCOUNT + BOT_AVID = a free test pirate (never Host's 100000170, never claude1's 100000001: another
# lane may be using it). The game's stdout/err and events land beside walker.py as walk-<Tag>.*; the numbers in
# C:\PiratesBots\out\pbots\measure-<Tag>.json (inside) and measure-<Tag>-ext.csv (outside, every 10 s).
$P = $PSScriptRoot; $S = Split-Path $P
$acct = $env:BOT_ACCOUNT; $avid = $env:BOT_AVID
if (-not $acct -or -not $avid) { "NEED: set BOT_ACCOUNT and BOT_AVID (a free test pirate)"; exit 3 }
if ($avid -eq '100000170') { "REFUSED: 100000170 is the pirate of Host"; exit 3 }
if ($avid -eq '100000001' -or $acct -eq 'claude1') { "REFUSED: claude1 / 100000001 may be in use by another lane; use another test pirate"; exit 3 }
$out = 'C:\PiratesBots\out\pbots'; if (-not (Test-Path $out)) { New-Item -ItemType Directory -Force $out | Out-Null }
$csv = "$out\measure-$Tag-ext.csv"

$lock = $null
while (-not $lock) {
  try { $lock = [IO.File]::Open("$S\run.lock", 'OpenOrCreate', 'ReadWrite', 'None') }
  catch { "$(Get-Date -Format HH:mm:ss) waiting for the bot game slot (another run holds run.lock)"; Start-Sleep 20 }
}
$Strikes = "$S\bot-strikes.txt"
$n = 0; if (Test-Path $Strikes) { $n = @(Get-Content $Strikes | Where-Object { $_ -match '^STRIKE' }).Count }
if ($n -ge 2) {
  "BOT STOPPED: $n failed runs in a row (see $Strikes). Not launching a measurement either."
  $lock.Close(); exit 2
}
while ($true) {
  $freeGB = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
  if ($freeGB -ge $MinFreeGB) { break }
  "$(Get-Date -Format HH:mm:ss) waiting for $MinFreeGB GB free (now $freeGB GB)"; Start-Sleep 30
}
"$(Get-Date -Format HH:mm:ss) slot taken, $freeGB GB free, strikes=$n (this run never adds one)"

Set-Location C:\PiratesOnline\pirates-online-classic
. "$S\HiddenDesktop.ps1"
$env:POC_TOKEN = $acct; $env:pocUsername = $acct
$env:POC_GAMESERVER = '127.0.0.1'; $env:GAME_ENVIRONMENT = 'DEV'
$env:PROOF_SECS = "$Secs"; $env:PROOF_SCRIPT = "$P\m_measure.py"; $env:PROOF_EVOUT = "$S\walk-$Tag-events.jsonl"
$env:BOT_FPS = "$Fps"; $env:MEASURE_TAG = $Tag; $env:MEASURE_INACTIVE = '1'; $env:MEASURE_SECS = '20'
if ($NoStrip) { Remove-Item Env:\BOT_PRC -ErrorAction SilentlyContinue } else { $env:BOT_PRC = "$P\prc\$Prc" }
$env:MEASURE_RESIZE = $(if ($Resize) { '1' } else { '0' })
$env:MEASURE_EARLY_OFF = $(if ($EarlyOff) { '1' } else { '0' })   # window off at the chooser: nothing ever drawn
Remove-Item "$S\walk-$Tag-events.jsonl" -ErrorAction SilentlyContinue
Start-BugReport "$S\walk-$Tag" $acct
$p = [HiddenDesk]::Start('PiratesBot', 'C:\Panda3D-1.11.0-x64\python\ppython.exe', "`"$S\walker.py`"",
  'C:\PiratesOnline\pirates-online-classic', "$S\walk-$Tag.log", "$S\walk-$Tag.err")
Write-Host "measure game (pirate $avid, prc=$(if ($NoStrip) { 'none' } else { $Prc }), fps=$Fps, resize=$Resize, earlyOff=$EarlyOff) pid $($p.Id) on hidden desktop PiratesBot"
"time,ws_mb,private_mb,peak_ws_mb,free_gb" | Set-Content -Encoding ascii $csv
$deadline = (Get-Date).AddSeconds($Secs + $Grace)
while (-not $p.WaitForExit(10000)) {
  try {
    $p.Refresh()
    $fg = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
    Add-Content -Encoding ascii $csv ("{0},{1},{2},{3},{4}" -f (Get-Date -Format HH:mm:ss), [int]($p.WorkingSet64 / 1MB), [int]($p.PrivateMemorySize64 / 1MB), [int]($p.PeakWorkingSet64 / 1MB), $fg)
  } catch { }
  if ((Get-Date) -gt $deadline) { "TIMEOUT: stopping measure game pid $($p.Id)"; $p.Kill(); $p.WaitForExit(); break }
}
"pid $($p.Id) exit $($p.ExitCode)"
$evs = @(); if (Test-Path "$S\walk-$Tag-events.jsonl") { $evs = @(Get-Content "$S\walk-$Tag-events.jsonl") }
if ($evs | Select-String -SimpleMatch '"PASS"' -Quiet) { "MEASURE PASSED (no strike touched)" } else { "MEASURE FAILED: no PASS (no strike written: not a bot game test); last=$(if ($evs.Count) { $evs[-1] } else { '(no events)' })" }
"ext samples: $csv"; Get-Content $csv | Select-Object -Last 3
$lock.Close()
