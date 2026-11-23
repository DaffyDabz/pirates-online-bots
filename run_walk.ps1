param([string]$Tag = 'A', [string]$Script = 's_orders.py', [int]$Secs = 400, [int]$Grace = 300)
# pir-bot job 5: -Grace (default 300, as before) = how long past -Secs the hidden game may run before it is stopped.
# Smoke checks pass a short -Grace (90): the walker ends a smoke run itself 3 s after its verdict (SMOKE-END).
$S = $PSScriptRoot
# ONE HIDDEN GAME AT A TIME: every run logs in the same test pirate and Host's PC takes one game only, so runs
# from several chats take turns on run.lock (an open file handle). Closed by hand at every way out: called with &
# from a longer script, the PowerShell process lives on and kept the slot locked for every chat (11-16 15:28-15:35).
$lock = $null
while (-not $lock) {
  try { $lock = [IO.File]::Open("$S\run.lock", 'OpenOrCreate', 'ReadWrite', 'None') }
  catch { "waiting for the bot game slot (another run holds run.lock)"; Start-Sleep 20 }
}
# TWO-STRIKE RULE (Host, 2026-09-22): a run counts only if the script emits a PASS event (mission done).
# Two runs in a row without PASS = the bot is stopped. Only Host clears bot-strikes.txt; never delete it yourself.
$Strikes = "$S\bot-strikes.txt"
$n = 0; if (Test-Path $Strikes) { $n = @(Get-Content $Strikes | Where-Object { $_ -match '^STRIKE' }).Count }
if ($n -ge 2) {
  "BOT STOPPED: $n failed runs in a row (see $Strikes). Do not relaunch. Report to Host and wait for his call."
  $lock.Close()
  exit 2
}
$acct = if ($env:BOT_ACCOUNT) { $env:BOT_ACCOUNT } else { 'claude1' }; $env:POC_TOKEN = $acct; $env:pocUsername = $acct
$env:POC_GAMESERVER = '127.0.0.1'; $env:GAME_ENVIRONMENT = 'DEV'
$env:PROOF_SECS = "$Secs"
$env:PROOF_SCRIPT = "$S\$Script"
$env:PROOF_EVOUT = "$S\walk-$Tag-events.jsonl"
Set-Location C:\PiratesOnline\pirates-online-classic
# The game window goes on a hidden desktop (never on Host's screens), Idle priority, no console.
. "$S\HiddenDesktop.ps1"
Start-BugReport "$S\walk-$Tag" $acct
$p = [HiddenDesk]::Start('PiratesBot', 'C:\Panda3D-1.11.0-x64\python\ppython.exe', "`"$S\walker.py`"",
  'C:\PiratesOnline\pirates-online-classic', "$S\walk-$Tag.log", "$S\walk-$Tag.err")
"bot game pid $($p.Id) on hidden desktop PiratesBot"
# Nobody can see or close it there, so stop it if the walker's own watchdog (PROOF_SECS) never ends it.
if (-not $p.WaitForExit(($Secs + $Grace) * 1000)) { "TIMEOUT: stopping bot game pid $($p.Id)"; $p.Kill(); $p.WaitForExit() }
"exit $($p.ExitCode)"
$evs = @(); if (Test-Path $env:PROOF_EVOUT) { $evs = @(Get-Content $env:PROOF_EVOUT) }
if ($evs | Select-String -SimpleMatch '"PASS"' -Quiet) {
  if (Test-Path $Strikes) { Remove-Item $Strikes }
  "RUN PASSED: strikes reset"
} else {
  $last = if ($evs.Count) { $evs[-1] } else { '(no events)' }
  Add-Content $Strikes "STRIKE $(Get-Date -Format s) tag=$Tag script=$Script exit=$($p.ExitCode) last=$last"
  "RUN FAILED: strike $($n + 1) of 2" + $(if ($n + 1 -ge 2) { ' - BOT IS NOW STOPPED, report to Host' } else { '' })
}
$lock.Close()
Set-Location C:\PiratesOnline\pirates-online-classic
