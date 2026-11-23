param([string]$Tag = 'CREW', [string]$Script = 's_crew2.py', [int]$Secs = 1000)
# TWO-BOT RUN (pir-bot, 11-17, job 3): the captain and the mate, two hidden games at once, for s_crew2.py.
# Copy of run_walk.ps1's pattern. It takes run.lock ONCE for both games and keeps the same two-strike file.
# TWO HIDDEN GAMES AT ONCE breaks the "one hidden game at a time" rule: run it only when the brain says so.
# Needs: BOT_ACCOUNT2 + BOT_AVID2 = the second test pirate's account and avId (never Host's 100000170).
# Optional: BOT_ACCOUNT (claude1) + BOT_AVID (100000001) = the captain.
# Both games use THIS folder's walker.py copy (it logs in BOT_AVID, refuses 100000170). Put this file, walker.py
# and s_crew2.py in the harness folder first (the steps import s_lanes / sailing from beside PROOF_SCRIPT).
$S = $PSScriptRoot
$cap = if ($env:BOT_AVID) { $env:BOT_AVID } else { '100000001' }
$capAcct = if ($env:BOT_ACCOUNT) { $env:BOT_ACCOUNT } else { 'claude1' }
$mate = $env:BOT_AVID2; $mateAcct = $env:BOT_ACCOUNT2
if (-not $mate -or -not $mateAcct) { "NEED: set BOT_ACCOUNT2 and BOT_AVID2 (the second test pirate)"; exit 3 }
if ('100000170' -in @($cap, $mate)) { "REFUSED: 100000170 is the pirate of Host"; exit 3 }
if ($cap -eq $mate -or $capAcct -eq $mateAcct) { "REFUSED: the captain and the mate must be two pirates on two accounts"; exit 3 }

$lock = $null
while (-not $lock) {
  try { $lock = [IO.File]::Open("$S\run.lock", 'OpenOrCreate', 'ReadWrite', 'None') }
  catch { "waiting for the bot game slot (another run holds run.lock)"; Start-Sleep 20 }
}
$Strikes = "$S\bot-strikes.txt"
$n = 0; if (Test-Path $Strikes) { $n = @(Get-Content $Strikes | Where-Object { $_ -match '^STRIKE' }).Count }
if ($n -ge 2) {
  "BOT STOPPED: $n failed runs in a row (see $Strikes). Do not relaunch. Report to Host and wait for his call."
  $lock.Close(); exit 2
}
Set-Location C:\PiratesOnline\pirates-online-classic
. "$S\HiddenDesktop.ps1"
$env:POC_GAMESERVER = '127.0.0.1'; $env:GAME_ENVIRONMENT = 'DEV'
$env:PROOF_SECS = "$Secs"; $env:PROOF_SCRIPT = "$S\$Script"
$env:CREW_CAPTAIN = $cap; $env:CREW_MATE = $mate

function StartOne($role, $acct, $avid) {
  # the child takes the env at start, so set it just before each start
  $env:POC_TOKEN = $acct; $env:pocUsername = $acct; $env:BOT_AVID = $avid; $env:CREW_ROLE = $role
  $env:PROOF_EVOUT = "$S\walk-$Tag-$role-events.jsonl"
  Start-BugReport "$S\walk-$Tag-$role" $acct
  $p = [HiddenDesk]::Start('PiratesBot', 'C:\Panda3D-1.11.0-x64\python\ppython.exe', "`"$S\walker.py`"",
    'C:\PiratesOnline\pirates-online-classic', "$S\walk-$Tag-$role.log", "$S\walk-$Tag-$role.err")
  # Write-Host, not output: a bare string here made the return value an array, so WaitForExit never waited (11-17 CREW1)
  Write-Host "bot game ($role, pirate $avid) pid $($p.Id) on hidden desktop PiratesBot"
  return $p
}
$pc = StartOne 'captain' $capAcct $cap
Start-Sleep 30          # the captain logs in first; the mate's game then loads while the captain walks
$pm = StartOne 'mate' $mateAcct $mate
$env:BOT_AVID = $cap

$end = (Get-Date).AddSeconds($Secs + 300)
foreach ($p in @($pc, $pm)) {
  $left = [int][Math]::Max(1000, ($end - (Get-Date)).TotalMilliseconds)
  if (-not $p.WaitForExit($left)) { "TIMEOUT: stopping bot game pid $($p.Id)"; $p.Kill(); $p.WaitForExit() }
  "pid $($p.Id) exit $($p.ExitCode)"
}
$ok = $true; $lastAll = @()
foreach ($role in 'captain', 'mate') {
  $f = "$S\walk-$Tag-$role-events.jsonl"
  $evs = @(); if (Test-Path $f) { $evs = @(Get-Content $f) }
  $pass = [bool]($evs | Select-String -SimpleMatch '"PASS"' -Quiet)
  "$role : $(if ($pass) { 'PASS' } else { 'no PASS' })"
  if (-not $pass) { $ok = $false; $lastAll += "$role=$(if ($evs.Count) { $evs[-1] } else { '(no events)' })" }
}
if ($ok) {
  if (Test-Path $Strikes) { Remove-Item $Strikes }
  "RUN PASSED (both): strikes reset"
} else {
  Add-Content $Strikes "STRIKE $(Get-Date -Format s) tag=$Tag script=$Script two-bot last=$($lastAll -join ' | ')"
  "RUN FAILED: strike $($n + 1) of 2" + $(if ($n + 1 -ge 2) { ' - BOT IS NOW STOPPED, report to Host' } else { '' })
}
$lock.Close()
