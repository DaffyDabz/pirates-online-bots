param([int]$Slot = 1, [string]$Tag = '', [int]$Secs = 28800, [string]$Prc = 'strip-gl.prc', [int]$Fps = 5,
      [switch]$NoStrip, [switch]$WindowOn, [switch]$Proof, [string]$Captains = '', [int]$MinFreeGB = 10,
      [switch]$Once, [switch]$NewPirate, [switch]$NoLock, [string]$Island = '', [string]$Script = '')
# pbots (11-22): ONE player bot = one hidden stripped game running pbot\b_brain.py (the brain), relaunched when the
# server kicks it (a restart kick is never a strike: the bot logs back in by itself, 60 s later) until -Secs are up,
# the stop file C:\PiratesBots\out\pbots\STOP-<Tag> appears, or the two-strike stop is on.
#  -Slot N      which bot of pbot\accounts.local.json (its login is the credential: it stays in that file, never on a
#               command line or in a chat). BOT_ACCOUNT + BOT_AVID in the env override the file (a test pirate).
#  -NewPirate   the one-time run that MAKES the bot's pirate: BOT_NEW_PIRATE=1 (the walker takes the first empty slot)
#               + s_kidmaker.py on the kids' path (pbot\prc\newpirate.prc: skip-tutorial #t). Plain, window on, once.
#               Afterwards fill the pirate id and name from walk-<Tag>-events.jsonl (KM-INWORLD) into the accounts file.
#  -Proof       PBOT_PROOF=1: the brain ends with PASS after CREW-JOINED, ABOARD, CANNON-SHOT, LAND-FIGHT (a picture
#               each in C:\PiratesBots\out\pbots\shots). No PASS by the end = a strike; a crash exit = a strike. A kick
#               (exit 3) is never one. A plain run (no -Proof) writes a strike only on a crash exit.
#  -Captains    extra captain ids the bot may accept a crew invite from (test only, e.g. 100000004); the family's
#               three are always in.
#  -NoLock      the caller holds run.lock (run_proof.ps1 runs the captain's game and this bot's under one lock).
#  -Island uid  PBOT_HOME: the bot starts on that island when it is not in a crew (a setup teleport, SETUP-TP).
#  -Script path a skill's own step script (pbot\skills\<area>.py with a run(H)) in place of the brain: the same stripped
#               game, slot, lock and strike rules (skills\INTERFACE.md section 9). Tag defaults to PBOT<Slot>-<leaf>.
# Memory rules (PLAYERBOTS.md): the stripped client (strip-gl.prc: tiny textures, no reflections/shadows) with the
# window off from the avatar chooser (PBOT_WINDOW_OFF=1, nothing ever drawn) and 5 fps, Idle priority, on the hidden
# desktop PiratesBot; waits for -MinFreeGB free before every launch.
$P = $PSScriptRoot; $S = Split-Path $P
$out = 'C:\PiratesBots\out\pbots'; if (-not (Test-Path $out)) { New-Item -ItemType Directory -Force $out | Out-Null }
$acct = $env:BOT_ACCOUNT; $avid = $env:BOT_AVID; $botName = ''
if (-not $acct) {
  $acc = Get-Content "$P\accounts.local.json" -Raw | ConvertFrom-Json
  $bot = @($acc.bots | Where-Object { $_.slot -eq $Slot })
  if (-not $bot) { "NEED: no bot in slot $Slot of accounts.local.json"; exit 3 }
  $acct = $bot[0].login; $avid = "$($bot[0].pirate)"; $botName = $bot[0].name
}
if ($Script -and -not (Test-Path $Script)) { "NEED: -Script $Script does not exist"; exit 3 }
if (-not $Tag) { $Tag = $(if ($NewPirate) { "PBMAKE$Slot" } elseif ($Script) { "PBOT$Slot-$([IO.Path]::GetFileNameWithoutExtension($Script))" } else { "PBOT$Slot" }) }
if (-not $NewPirate -and (-not $avid -or $avid -eq '' -or $avid -eq '0')) { "NEED: slot $Slot has no pirate yet: run with -NewPirate first"; exit 3 }
if ($avid -eq '100000170' -or $acct -eq 'host') { "REFUSED: 100000170 is the pirate of Host"; exit 3 }
if ($avid -eq '100000001' -or $acct -eq 'claude1') { "REFUSED: claude1 / 100000001 may be in use by another lane"; exit 3 }
$stop = "$out\STOP-$Tag"; Remove-Item $stop -ErrorAction SilentlyContinue
$Strikes = "$S\bot-strikes.txt"
function StrikeCount { $n = 0; if (Test-Path $Strikes) { $n = @(Get-Content $Strikes | Where-Object { $_ -match '^STRIKE' }).Count }; $n }

$lock = $null
if (-not $NoLock) {
  while (-not $lock) {
    try { $lock = [IO.File]::Open("$S\run.lock", 'OpenOrCreate', 'ReadWrite', 'None') }
    catch { "$(Get-Date -Format HH:mm:ss) waiting for the bot game slot (another run holds run.lock)"; Start-Sleep 20 }
  }
}
$n = StrikeCount
if ($n -ge 2) { "BOT STOPPED: $n failed runs in a row (see $Strikes). Not launching the player bot."; if ($lock) { $lock.Close() }; exit 2 }

Set-Location C:\PiratesOnline\pirates-online-classic
. "$S\HiddenDesktop.ps1"
$env:POC_TOKEN = $acct; $env:pocUsername = $acct
$env:POC_GAMESERVER = '127.0.0.1'; $env:GAME_ENVIRONMENT = 'DEV'
$env:PROOF_EVOUT = "$S\walk-$Tag-events.jsonl"
$env:BOT_FPS = "$Fps"
$env:PBOT_TAG = $Tag
$env:PBOT_PROOF = $(if ($Proof) { '1' } else { '0' })
$env:PBOT_WINDOW_OFF = $(if ($WindowOn -or $NewPirate) { '0' } else { '1' })
if ($Captains) { $env:PBOT_CAPTAINS = $Captains } else { Remove-Item Env:\PBOT_CAPTAINS -ErrorAction SilentlyContinue }
if ($Island) { $env:PBOT_HOME = $Island } else { Remove-Item Env:\PBOT_HOME -ErrorAction SilentlyContinue }
Remove-Item Env:\MEASURE_TAG, Env:\MEASURE_INACTIVE, Env:\MEASURE_EARLY_OFF, Env:\CREW_ROLE -ErrorAction SilentlyContinue
if ($NewPirate) {
  $env:BOT_NEW_PIRATE = '1'; $env:PROOF_SCRIPT = "$S\s_kidmaker.py"; $env:BOT_PRC = "$P\prc\newpirate.prc"
  $env:BOT_AVID = '0'; $env:BOT_FPS = '10'; $Once = $true; if ($Secs -gt 400) { $Secs = 400 }
} else {
  Remove-Item Env:\BOT_NEW_PIRATE -ErrorAction SilentlyContinue
  $env:BOT_AVID = "$avid"; $env:PROOF_SCRIPT = $(if ($Script) { (Resolve-Path $Script).Path } else { "$P\b_brain.py" })
  if ($NoStrip) { Remove-Item Env:\BOT_PRC -ErrorAction SilentlyContinue } else { $env:BOT_PRC = "$P\prc\$Prc" }
}
$deadline = (Get-Date).AddSeconds($Secs)
"$(Get-Date -Format HH:mm:ss) player bot slot $Slot pirate $avid $botName tag=$Tag mode=$(if ($NewPirate) { 'NEW PIRATE' } elseif ($Proof) { 'PROOF' } else { 'PLAY' }) prc=$(if ($NewPirate) { 'newpirate.prc' } elseif ($NoStrip) { 'none' } else { $Prc }) window=$(if ($env:PBOT_WINDOW_OFF -eq '1') { 'off' } else { 'on' }) fps=$($env:BOT_FPS) script=$(Split-Path -Leaf $env:PROOF_SCRIPT) until $($deadline.ToString('HH:mm:ss')) strikes=$n"
$launch = 0; $verdict = 'none'
while ($true) {
  $left = [int](($deadline - (Get-Date)).TotalSeconds)
  if ($left -lt 60) { $verdict = 'time up'; break }
  if (Test-Path $stop) { $verdict = 'stop file'; break }
  if ((StrikeCount) -ge 2) { $verdict = 'bot stopped (2 strikes)'; break }
  while ($true) {
    $freeGB = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
    if ($freeGB -ge $MinFreeGB) { break }
    "$(Get-Date -Format HH:mm:ss) waiting for $MinFreeGB GB free (now $freeGB GB)"; Start-Sleep 30
    if (Test-Path $stop) { break }
  }
  if (Test-Path $stop) { $verdict = 'stop file'; break }
  $launch++
  $env:PROOF_SECS = "$left"
  Remove-Item $env:PROOF_EVOUT -ErrorAction SilentlyContinue
  # the watcher names the bot's PIRATE in its bug files (id + name), never the account login: the login is the credential
  Start-BugReport "$S\walk-$Tag" $(if ($avid -and $avid -ne '0') { "$avid $botName".Trim() } else { "bot slot $Slot" })
  $p = [HiddenDesk]::Start('PiratesBot', 'C:\Panda3D-1.11.0-x64\python\ppython.exe', "`"$S\walker.py`"",
    'C:\PiratesOnline\pirates-online-classic', "$S\walk-$Tag.log", "$S\walk-$Tag.err")
  "$(Get-Date -Format HH:mm:ss) launch $launch pid $($p.Id) on hidden desktop PiratesBot, $freeGB GB free, $left s left"
  $stopped = $false; $timedOut = $false
  while (-not $p.WaitForExit(20000)) {
    if (Test-Path $stop) { "$(Get-Date -Format HH:mm:ss) stop file: stopping bot game pid $($p.Id)"; $stopped = $true; $p.Kill(); $p.WaitForExit(); break }
    if ((Get-Date) -gt $deadline.AddSeconds(300)) { "$(Get-Date -Format HH:mm:ss) TIMEOUT: stopping bot game pid $($p.Id)"; $timedOut = $true; $p.Kill(); $p.WaitForExit(); break }
  }
  $code = $p.ExitCode
  $evs = @(); if (Test-Path $env:PROOF_EVOUT) { $evs = @(Get-Content $env:PROOF_EVOUT) }
  $pass = [bool]($evs | Select-String -SimpleMatch '"PASS"' -Quiet)
  $last = if ($evs.Count) { $evs[-1] } else { '(no events)' }
  "$(Get-Date -Format HH:mm:ss) launch $launch pid $($p.Id) exit $code pass=$pass events=$($evs.Count) last=$($last.Substring(0, [math]::Min(200, $last.Length)))"
  if ($code -eq 3) {
    "$(Get-Date -Format HH:mm:ss) kicked before play (a server restart?): no strike, back in 60 s"
    if ($Once) { $verdict = 'kicked (once)'; break }
    Start-Sleep 60; continue
  }
  # my own kill on the stop file is never the bot's fault (it exits -1): no strike, whatever the mode (the tele proof's
  # captain stops the bot this way once its verdict is in)
  if ($stopped) { $verdict = "stopped by the stop file (exit $code, pass=$pass): no strike"; $verdict; break }
  $strike = $false
  if ($timedOut) { $strike = $true; $why = "timeout: the game outlived its deadline by 300 s (killed, exit $code)" }
  elseif ($code -ne 0 -and $code -ne $null) { $strike = $true; $why = "crash exit $code" }
  elseif ($Proof -and -not $pass) { $strike = $true; $why = 'no PASS' }
  if ($NewPirate -and -not $pass) { $verdict = "maker run failed (exit $code, no PASS): no strike, a setup run"; $verdict; break }
  if ($strike) {
    Add-Content $Strikes "STRIKE $(Get-Date -Format s) tag=$Tag script=$(Split-Path -Leaf $env:PROOF_SCRIPT) exit=$code last=$last"
    "RUN FAILED ($why): strike $((StrikeCount)) of 2"
    $verdict = "failed: $why"
    if ($Once -or $Proof -or (StrikeCount) -ge 2) { break }
    Start-Sleep 60; continue
  }
  if ($pass -and ($Proof -or $NewPirate)) {
    if (Test-Path $Strikes) { Remove-Item $Strikes }
    "RUN PASSED: strikes reset"; $verdict = 'PASS'
    break
  }
  if ($Once) { $verdict = "ended (exit $code)"; break }
  "$(Get-Date -Format HH:mm:ss) game ended (exit $code) with time left: back in 30 s"; Start-Sleep 30
}
"$(Get-Date -Format HH:mm:ss) player bot $Tag done: $verdict after $launch launch(es)"
if ($lock) { $lock.Close() }
