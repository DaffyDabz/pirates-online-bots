param([string]$Check = '', [switch]$List, [switch]$RouteTest)
# pir-bot job 5: one smoke check (one patch, a few minutes). Uses this folder's run_walk.ps1 (the -Grace copy), so the
# lock, the two-strike rule and the hidden desktop are all the same as a full run.
#   .\run_smoke.ps1 -List              the checks and their patches
#   .\run_smoke.ps1 -Check 0102        the check for patch 0102 (or a name: shop, relog, quest ...)
#   .\run_smoke.ps1 -Check shop -RouteTest   same check, but walks the whole way (no SETUP-WARP)
$S = $PSScriptRoot
$py = 'C:\Panda3D-1.11.0-x64\python\python.exe'
if ($List -or -not $Check) { & $py "$S\s_smoke.py" --list; exit 0 }
$secs = [int](& $py "$S\s_smoke.py" --secs $Check)
if ($secs -le 0) { "no smoke check for '$Check' (see .\run_smoke.ps1 -List)"; exit 1 }
$env:SMOKE = '1'
$env:SMOKE_CHECK = $Check
$env:FAST_START = '1'
if ($RouteTest) { $env:ROUTE_TEST = '1' } else { Remove-Item Env:ROUTE_TEST -ErrorAction SilentlyContinue }
$tag = "SMOKE-$Check"
"smoke check $Check : $secs s + 90 s grace (events: walk-$tag-events.jsonl)"
& "$S\run_walk.ps1" -Tag $tag -Script 's_smoke.py' -Secs $secs -Grace 90
Remove-Item Env:SMOKE, Env:SMOKE_CHECK, Env:FAST_START, Env:ROUTE_TEST -ErrorAction SilentlyContinue
