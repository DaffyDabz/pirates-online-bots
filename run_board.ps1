param([string]$Tag = 'BOARD', [int]$Secs = 420, [switch]$Mini, [string]$Script = 's_board.py', [string]$RoleA = 'A', [string]$RoleB = 'B')
# LIVE CHECK ITEM 7 (11-20): s_board.py in two hidden games at once, A (launches, the light game) and B (boards).
# TWO HIDDEN GAMES AT ONCE breaks the "one hidden game at a time" rule: run it only with Host's OK, passed on by the
# brain. Host's OK (11-20) is for ONE run of about 6 minutes, both games tiny; a rerun needs a new OK. Copy of run_two.ps1's pattern: run.lock is taken ONCE for both games and the same two-strike file is used.
# Refuses to start with under 20 GB free or while Host is in a game. Both 320x240; A 5-10 fps, B 15 fps.
# -Script/-RoleA/-RoleB: another two-game check on the same terms (Sea Battle: s_seabattle2.py captain mate).
# -Mini: A minimizes at the wheel (no picture); pass it only after LIVE_ITEM=mini passed.
# Needs: BOT_ACCOUNT + BOT_AVID (A), BOT_ACCOUNT2 + BOT_AVID2 (B). Never Host's or the boys' pirates.
$S = $PSScriptRoot
$a = $env:BOT_AVID; $aAcct = $env:BOT_ACCOUNT; $b = $env:BOT_AVID2; $bAcct = $env:BOT_ACCOUNT2
if (-not $a -or -not $aAcct -or -not $b -or -not $bAcct) { "NEED: BOT_ACCOUNT/BOT_AVID (A) and BOT_ACCOUNT2/BOT_AVID2 (B)"; exit 3 }
if (@($a, $b) | Where-Object { $_ -in '100000170', '100000656', '100000665' }) { "REFUSED: a real player's pirate"; exit 3 }
if ($a -eq $b -or $aAcct -eq $bAcct) { "REFUSED: A and B must be two pirates on two accounts"; exit 3 }

function Gate {
  $free = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
  $games = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(Wow|WowClassic|WowB|cs2|csgo|RocketLeague|iw4l|iw4x|t6mp|t6zm|t6mpv43|bo2|javaw|Minecraft|FortniteClient.*|GTA5|eldenring|Overwatch|RobloxPlayerBeta|Pirates.*)$' })
  # 11-20: Roblox's own hidden tray copy (--launch-to-tray, no window) relaunches itself every 4 hours; nobody is playing
  $games = @($games | Where-Object { -not ($_.ProcessName -eq 'RobloxPlayerBeta' -and $_.MainWindowHandle -eq 0 -and
    (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -match '--launch-to-tray') })
  $ours = @(Get-CimInstance Win32_Process -Filter "Name='ppython.exe'" | Where-Object { $_.CommandLine -notmatch 'pirates-harness' })
  return @{ free = $free; games = (@($games | ForEach-Object { $_.ProcessName }) + @($ours | ForEach-Object { 'ppython ' + $_.ProcessId })) }
}
$g = Gate
if ($g.free -lt 20 -or $g.games.Count) { "NOT STARTED: free $($g.free) GB (need 20), games running: $($g.games -join ', ')"; exit 4 }

$lock = $null
while (-not $lock) {
  try { $lock = [IO.File]::Open("$S\run.lock", 'OpenOrCreate', 'ReadWrite', 'None') }
  catch { if ((Get-Date).Second -lt 2) { "waiting for the bot game slot (another run holds run.lock)" }; Start-Sleep 2 }
}
$Strikes = "$S\bot-strikes.txt"
$n = 0; if (Test-Path $Strikes) { $n = @(Get-Content $Strikes | Where-Object { $_ -match '^STRIKE' }).Count }
if ($n -ge 2) {
  "BOT STOPPED: $n failed runs in a row (see $Strikes). Do not relaunch. Report to Host and wait for his call."
  $lock.Close(); exit 2
}
$g = Gate     # again, after any wait for the slot
if ($g.free -lt 20 -or $g.games.Count) { "NOT STARTED: free $($g.free) GB (need 20), games running: $($g.games -join ', ')"; $lock.Close(); exit 4 }

$dir = 'C:\PiratesBots\out\live\board'
New-Item -ItemType Directory -Force $dir | Out-Null
Get-ChildItem $dir -File | Remove-Item     # the last run's hand-over files only (this folder holds nothing else)
Set-Location C:\PiratesOnline\pirates-online-classic
. "$S\HiddenDesktop.ps1"
$env:POC_GAMESERVER = '127.0.0.1'; $env:GAME_ENVIRONMENT = 'DEV'
$env:PROOF_SECS = "$Secs"; $env:PROOF_SCRIPT = "$S\$Script"
$env:BOARD_A = $a; $env:BOARD_B = $b; $env:BOARD_DIR = $dir; $env:BOARD_SECS = "$($Secs - 60)"
$env:BOARD_MINI = $(if ($Mini) { '1' } else { '' })

function StartOne($role, $acct, $avid, $light) {
  $env:POC_TOKEN = $acct; $env:pocUsername = $acct; $env:BOT_AVID = $avid; $env:BOARD_ROLE = $role; $env:CREW_ROLE = $role
  $env:BOT_LIGHT = $light
  $env:PROOF_EVOUT = "$S\walk-$Tag-$role-events.jsonl"
  Start-BugReport "$S\walk-$Tag-$role" $acct
  $p = [HiddenDesk]::Start('PiratesBot', 'C:\Panda3D-1.11.0-x64\python\ppython.exe', "`"$S\walker.py`"",
    'C:\PiratesOnline\pirates-online-classic', "$S\walk-$Tag-$role.log", "$S\walk-$Tag-$role.err")
  Write-Host "bot game ($role, pirate $avid, light=$light) pid $($p.Id) on hidden desktop PiratesBot"
  return $p
}
$pa = StartOne $RoleA $aAcct $a '1'
Start-Sleep 20          # A logs in first; B's game loads while A waits for B's list
$pb = StartOne $RoleB $bAcct $b '0'
$env:BOT_LIGHT = ''; $env:BOT_AVID = $a

# Close both the moment item 7 is done: when one game ends, the other gets 60 s to finish, then it is stopped.
$end = (Get-Date).AddSeconds($Secs + 30)
while ((Get-Date) -lt $end -and -not ($pa.HasExited -and $pb.HasExited)) {
  if ($pa.HasExited -xor $pb.HasExited) {
    $left = @($pa, $pb) | Where-Object { -not $_.HasExited }
    if (-not $left.WaitForExit(60000)) { "STOPPING pid $($left.Id): the other game already ended"; $left.Kill(); $left.WaitForExit() }
  } else { Start-Sleep 5 }
}
foreach ($p in @($pa, $pb)) {
  if (-not $p.HasExited) { "TIMEOUT: stopping bot game pid $($p.Id)"; $p.Kill(); $p.WaitForExit() }
  "pid $($p.Id) exit $($p.ExitCode)"
}
$ok = $true; $lastAll = @()
foreach ($role in $RoleA, $RoleB) {
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
