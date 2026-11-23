param([string]$Account = '', [int]$Legs = 8, [int]$LegSecs = 3600, [int]$NewSecs = 1500, [string]$Tag = 'CHAIN',
      [string]$AvId = '')
# STORY CHAIN (pir-bot, 11-17, job 4): Chapter 1 to the end of Chapter 3 over several runs, one leg per run.
# Leg 0 = s_newplayer.py (a new pirate on $Account: random pirate maker, the tutorial = Chapter 1, logout), unless
# -AvId names a test pirate that already has one (or newplayer-last.json has one for $Account).
# Legs 1..$Legs = s_storychain.py as that pirate: resume from story-checkpoint-<avId>.json, play on for $LegSecs.
# Every leg goes through run_walk.ps1, so it takes run.lock (one hidden game at a time) and counts for the two-strike
# rule. The chain stops at the first leg without PASS (run_walk wrote its strike), or when the checkpoint says the
# end of Chapter 3 (c3.8visitJack) is done.
# Needs, in the harness folder beside run_walk.ps1: this file, the pir-bot job 4 walker.py copy, s_newplayer.py,
# s_relog.py, s_storychain.py (plus the s_story / s_tutorial / sailing / paths files they import).
# Test accounts only: never Host's pirate 100000170.
$S = $PSScriptRoot
$np = "$S\newplayer-last.json"
if (-not $Account -and -not $AvId) { "NEED: -Account <a fresh test account> (or -AvId <a test pirate past the tutorial>)"; exit 3 }
if ($AvId -eq '100000170') { "REFUSED: 100000170 is the pirate of Host"; exit 3 }

function LegPassed($t) {
  $f = "$S\walk-$t-events.jsonl"
  return (Test-Path $f) -and [bool](Get-Content $f | Select-String -SimpleMatch '"PASS"' -Quiet)
}

if ($Account) { $env:BOT_ACCOUNT = $Account }
if (-not $AvId -and (Test-Path $np)) {
  $rec = Get-Content $np -Raw | ConvertFrom-Json
  if ($rec.account -eq $Account) { $AvId = "$($rec.avId)"; "pirate $AvId ($($rec.name)) from newplayer-last.json" }
}
if (-not $AvId) {
  "leg 0: a new pirate on $Account (pirate maker + tutorial)"
  $env:BOT_NEW_PIRATE = '1'
  & "$S\run_walk.ps1" -Tag "$Tag-L0" -Script 's_newplayer.py' -Secs $NewSecs
  Remove-Item Env:BOT_NEW_PIRATE -ErrorAction SilentlyContinue
  if (-not (LegPassed "$Tag-L0")) { "CHAIN STOPPED at leg 0 (no PASS; see walk-$Tag-L0-events.jsonl)"; exit 1 }
  $rec = Get-Content $np -Raw | ConvertFrom-Json
  $AvId = "$($rec.avId)"
  "leg 0 made pirate $AvId ($($rec.name))"
}
if ($AvId -eq '100000170') { "REFUSED: 100000170 is the pirate of Host"; exit 3 }
$env:BOT_AVID = $AvId
$ck = "$S\story-checkpoint-$AvId.json"
for ($i = 1; $i -le $Legs; $i++) {
  $env:STORYCHAIN_LEG = "$i"
  $from = if (Test-Path $ck) { (Get-Content $ck -Raw | ConvertFrom-Json).quest } else { '(none)' }
  "leg $i of $Legs : pirate $AvId from $from"
  & "$S\run_walk.ps1" -Tag "$Tag-L$i" -Script 's_storychain.py' -Secs $LegSecs
  $c = if (Test-Path $ck) { Get-Content $ck -Raw | ConvertFrom-Json } else { $null }
  if ($c -and $c.end) { "CHAIN DONE after leg $i : the end of Chapter 3 is in the history of $AvId"; exit 0 }
  if (-not (LegPassed "$Tag-L$i")) { "CHAIN STOPPED at leg $i (no PASS; see walk-$Tag-L$i-events.jsonl)"; exit 1 }
  "leg $i ended at $($c.quest) (ladder $($c.index))"
}
"CHAIN PAUSED after $Legs legs (not at the end yet): run again with -AvId $AvId to go on from the checkpoint"
