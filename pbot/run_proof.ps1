param([int]$Slot = 1, [string]$Tag = 'PROOF', [int]$Secs = 1500, [int]$MinFreeGB = 20, [string]$From = '',
      [switch]$WindowOn, [string]$Prc = 'strip-gl.prc', [switch]$NoStrip, [switch]$Tele, [string]$To = '')
# pbots (11-22): the player-bot v1 PROOF = two hidden games under ONE run.lock:
#   captain  claude2 / pirate 100000004 running pbot\c_captain.py (invites the bot, launches, hunts a ship, docks, fights)
#   bot      slot $Slot of pbot\accounts.local.json running pbot\b_brain.py through run_bot.ps1 -Proof -NoLock -Once
# Verdict: both events files end with a PASS line (the bot's after CREW-JOINED, ABOARD, CANNON-SHOT, LAND-FIGHT; the
# captain's when it read those four in the bot's file). The bot's pictures: C:\PiratesBots\out\pbots\shots\PBOT<Slot>-*.
# A proof without a PASS is a strike for the bot (run_bot.ps1 writes it); a crash exit too. Needs $MinFreeGB free.
# -Tele (11-22, the crew.py teleport proof, row 32): the same crew-up and meet, then the captain goes to -To (default
#   Tortuga) with no ship and the bot must come to him by the game's own crewmate teleport. The bot runs the PLAIN brain
#   (no -Proof: the brain's PASS needs the four v1 milestones, which this proof never reaches, so -Proof would strike it
#   for 'no PASS'); the bot's verdict here is a CREW-TELE line with out and landed true, the captain's its PASS. The
#   captain writes the bot's stop file (STOP-PBOT<Slot>) when its verdict is in, so the slot frees at once (no strike).
$P = $PSScriptRoot; $S = Split-Path $P
$out = 'C:\PiratesBots\out\pbots'; if (-not (Test-Path $out)) { New-Item -ItemType Directory -Force $out | Out-Null }
$acc = Get-Content "$P\accounts.local.json" -Raw | ConvertFrom-Json
$bot = @($acc.bots | Where-Object { $_.slot -eq $Slot })
if (-not $bot) { "NEED: no bot in slot $Slot of accounts.local.json"; exit 3 }
$mate = "$($bot[0].pirate)"
if (-not $mate -or $mate -eq '' -or $mate -eq '0') { "NEED: slot $Slot has no pirate yet (run_bot.ps1 -Slot $Slot -NewPirate first)"; exit 3 }
if ($mate -in '100000170', '100000656', '100000665', '100000001', '100000004') { "REFUSED: $mate is not a bot pirate"; exit 3 }
$Strikes = "$S\bot-strikes.txt"
function StrikeCount { $n = 0; if (Test-Path $Strikes) { $n = @(Get-Content $Strikes | Where-Object { $_ -match '^STRIKE' }).Count }; $n }

$lock = $null
while (-not $lock) {
  try { $lock = [IO.File]::Open("$S\run.lock", 'OpenOrCreate', 'ReadWrite', 'None') }
  catch { "$(Get-Date -Format HH:mm:ss) waiting for the bot game slot (another run holds run.lock)"; Start-Sleep 20 }
}
$n = StrikeCount
if ($n -ge 2) { "BOT STOPPED: $n failed runs in a row (see $Strikes). Not launching the proof."; $lock.Close(); exit 2 }
while ($true) {
  $freeGB = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
  if ($freeGB -ge $MinFreeGB) { break }
  "$(Get-Date -Format HH:mm:ss) waiting for $MinFreeGB GB free for two games (now $freeGB GB)"; Start-Sleep 30
}

Set-Location C:\PiratesOnline\pirates-online-classic
. "$S\HiddenDesktop.ps1"
$botTag = "PBOT$Slot"
$botEvents = "$S\walk-$botTag-events.jsonl"
Remove-Item $botEvents -ErrorAction SilentlyContinue      # the captain paces itself on this file: never a stale one
Remove-Item Env:\BOT_PRC, Env:\BOT_NEW_PIRATE, Env:\BOT_FPS, Env:\CREW_ROLE, Env:\MEASURE_TAG, Env:\MEASURE_INACTIVE,
  Env:\MEASURE_EARLY_OFF, Env:\PBOT_PROOF, Env:\PBOT_WINDOW_OFF, Env:\PBOT_CAPTAINS, Env:\PBOT_HOME, Env:\BOT_ACCOUNT -ErrorAction SilentlyContinue
# the captain: claude2, the plain proven game (s_shipfight / s_fighter drive it), on the hidden desktop
$env:POC_TOKEN = 'claude2'; $env:pocUsername = 'claude2'; $env:BOT_AVID = '100000004'
$env:POC_GAMESERVER = '127.0.0.1'; $env:GAME_ENVIRONMENT = 'DEV'
# the walker's own watchdog (PROOF_SECS, os._exit at once) gets 200 s past the captain's script budget (CAPTAIN_SECS): the
# script puts its ship away after every exit path (run 7 logged out with the ship launched and Player1 aboard: kicked)
$env:PROOF_SECS = "$($Secs + 200)"; $env:PROOF_SCRIPT = "$P\c_captain.py"
$env:PROOF_EVOUT = "$S\walk-$Tag-captain-events.jsonl"
$capEvents = $env:PROOF_EVOUT   # kept apart: run_bot.ps1 runs in this process and points $env:PROOF_EVOUT at the bot's file
$env:PBOT_MATE = $mate; $env:PBOT_MATE_EVENTS = $botEvents
$env:CAPTAIN_SECS = "$Secs"
if ($From) { $env:CAPTAIN_FROM = $From } else { Remove-Item Env:\CAPTAIN_FROM -ErrorAction SilentlyContinue }
if ($Tele) {
  $env:CAPTAIN_MODE = 'tele'
  if ($To) { $env:CAPTAIN_TO = $To } else { Remove-Item Env:\CAPTAIN_TO -ErrorAction SilentlyContinue }
} else { Remove-Item Env:\CAPTAIN_MODE, Env:\CAPTAIN_TO -ErrorAction SilentlyContinue }
Remove-Item $env:PROOF_EVOUT -ErrorAction SilentlyContinue
"$(Get-Date -Format HH:mm:ss) PROOF$(if ($Tele) { ' (tele)' }): captain claude2/100000004 + bot slot $Slot pirate $mate $($bot[0].name), $freeGB GB free, $Secs s, strikes=$n"
Start-BugReport "$S\walk-$Tag-captain" 'claude2'
$pc = [HiddenDesk]::Start('PiratesBot', 'C:\Panda3D-1.11.0-x64\python\ppython.exe', "`"$S\walker.py`"",
  'C:\PiratesOnline\pirates-online-classic', "$S\walk-$Tag-captain.log", "$S\walk-$Tag-captain.err")
Write-Host "captain game pid $($pc.Id) on hidden desktop PiratesBot"
Start-Sleep 30

# the bot: its own runner, same lock (-NoLock), once, proof mode; it accepts the test captain's invite; it starts on the
# captain's island (PBOT_HOME: a setup teleport, logged SETUP-TP, before anything else)
$botArgs = @{ Slot = $Slot; Proof = (-not $Tele); Captains = '100000004'; NoLock = $true; Once = $true; Secs = $Secs; MinFreeGB = 5 }
if ($From) { $botArgs.Island = $From } else { $botArgs.Island = '1150922126.8dzlu' }
if ($WindowOn) { $botArgs.WindowOn = $true }
if ($NoStrip) { $botArgs.NoStrip = $true } else { $botArgs.Prc = $Prc }
$env:BOT_ACCOUNT = $null; Remove-Item Env:\BOT_ACCOUNT -ErrorAction SilentlyContinue   # run_bot reads the slot file
& "$P\run_bot.ps1" @botArgs

# the bot's run is over: give the captain 4 minutes to write its verdict and put its ship away, then stop it (it is mine: exact pid)
if (-not $pc.WaitForExit(240000)) { "$(Get-Date -Format HH:mm:ss) captain still up after the bot's run: stopping pid $($pc.Id)"; $pc.Kill(); $pc.WaitForExit() }
"captain pid $($pc.Id) exit $($pc.ExitCode)"
$ok = $true
$roles = @(); $roles += ,@('captain', $capEvents); $roles += ,@('bot', $botEvents)   # the unary comma keeps the pairs: @(@(a,b),@(c,d)) flattens
# (run 6 printed the bot's events for both roles: $env:PROOF_EVOUT was the bot's by then, so the captain's own verdict went unread)
foreach ($role in $roles) {
  $f = $role[1]; $evs = @(); if (Test-Path $f) { $evs = @(Get-Content $f) }
  if ($Tele -and $role[0] -eq 'bot') {
    # the plain brain gives no PASS: the bot's proof line is crew.py's CREW-TELE with out and landed true
    $hit = @($evs | Where-Object { $_ -match '"ev": "CREW-TELE"' -and $_ -match '"out": true' -and $_ -match '"landed": true' })
    $pass = [bool]$hit.Count
    $tl = @($evs | Where-Object { $_ -match '"ev": "CREW-TELE' })
    $verdLine = if ($hit.Count) { $hit[0] } elseif ($tl.Count) { $tl[-1] } else { $null }
  } else {
    $pass = [bool]($evs | Select-String -SimpleMatch '"PASS"' -Quiet)
    $verd = @($evs | Select-String -SimpleMatch '"ev": "PASS"', '"ev": "FAIL"' | Select-Object -First 1)
    $verdLine = if ($verd) { $verd[0].Line } else { $null }
  }
  $last = if ($evs.Count) { $evs[-1] } else { '(no events)' }
  "$($role[0]): pass=$pass events=$($evs.Count) verdict=$(if ($verdLine) { $verdLine.Substring(0, [math]::Min(300, $verdLine.Length)) } else { 'none' })"
  if (-not $pass) { $ok = $false; "$($role[0]) last: $($last.Substring(0, [math]::Min(300, $last.Length)))" }
}
$shots = @(Get-ChildItem "$out\shots\$botTag-*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -ExpandProperty Name)
"bot pictures: $($shots.Count) in $out\shots ($($shots -join ', '))"
$bugs = @(Get-ChildItem 'C:\PiratesBots\out\bugs\inbox\BUG-*.md' -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt (Get-Date).AddSeconds(-$Secs - 600) })
"bug files written during the run: $($bugs.Count) $($bugs.Name -join ', ')"
"$(Get-Date -Format HH:mm:ss) PROOF $(if ($ok) { 'PASS' } else { 'FAIL' })"
$lock.Close()
if ($ok) { exit 0 } else { exit 1 }
