# Mechanics checks (pirates-bulbs, 11-21): the one-game checks for the gaps in C:\PiratesBots\out\mechanics\MECHANICS.md,
# one at a time, through run_walk.ps1 (run.lock, Idle, hidden desktop, sound off, two-strike stop). claude2 /
# 100000004 only. Before each item: wait until 20 GB is free (checked every 60 s). Stops when the bot is stopped.
# No args = every item below. Name items to run only those: run_mech.ps1 stores   /   run_mech.ps1 weapons buttons
# Gap 9 (Sea Battle, two games) is NOT here: run_two.ps1 with s_seabattle2.py, only with Host's OK. Start lines: RUN.md
$H = $PSScriptRoot
$items = @(
  @('stores', 1200, 's_mech.py', 'MECH_ITEM', 'stores'),          # gap 1
  @('weapons', 1800, 's_mech.py', 'MECH_ITEM', 'weapons'),        # gap 6
  @('buttons', 1200, 's_mech.py', 'MECH_ITEM', 'buttons'),        # gap 10
  @('vitae', 600, 's_mech.py', 'MECH_ITEM', 'vitae'),             # gap 10
  @('bpfort', 1500, 's_mech.py', 'MECH_ITEM', 'bpfort'),          # gap 8 recheck
  @('guild', 480, 's_activities.py', 'ACT_STEPS', 'guild'),       # gap 3 recheck (0301)
  @('titles', 300, 's_activities.py', 'ACT_STEPS', 'titles'),     # gap 4 recheck (0285)
  @('tablefind', 480, 's_activities.py', 'ACT_STEPS', 'tablefind'))  # gap 7: the Lookout table search
$want = @($args)
if ($want.Count) { $items = @($items | Where-Object { $_[0] -in $want }) }
foreach ($it in $items) {
  $name, $secs, $script, $var, $val = $it[0..4]
  while ($true) {
    $free = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
    if ($free -ge 20) { break }
    "$(Get-Date -Format HH:mm:ss) waiting: $free GB free (need 20) before $name"
    Start-Sleep 60
  }
  "$(Get-Date -Format HH:mm:ss) START $name (claude2 100000004, $script $var=$val, $secs s)"
  $env:BOT_ACCOUNT = 'claude2'; $env:BOT_AVID = '100000004'
  $env:MECH_ITEM = ''; $env:ACT_STEPS = ''
  Set-Item "env:$var" $val
  $out = & "$H\run_walk.ps1" -Tag "MECH-$name" -Script $script -Secs $secs -Grace 90 2>&1 | Out-String
  $out.Trim().Split("`n") | Select-Object -Last 4 | ForEach-Object { "  $_" }
  $ev = "$H\walk-MECH-$name-events.jsonl"
  $v = if (Test-Path $ev) { @(Get-Content $ev | Select-String '"(PASS|FAIL)"' | Select-Object -Last 1) } else { @() }
  "$(Get-Date -Format HH:mm:ss) END $name : $(if ($v.Count) { $v[0].Line.Substring(0, [math]::Min(400, $v[0].Line.Length)) } else { '(no verdict)' })"
  if ($out -match 'BOT STOPPED|BOT IS NOW STOPPED') { 'MECH STOPPED: two strikes'; break }
}
"$(Get-Date -Format HH:mm:ss) MECH DONE"
