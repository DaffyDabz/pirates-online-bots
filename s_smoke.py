"""SMOKE CHECKS (pir-bot, 11-17, job 5): one short check per patch, a few minutes each, so a patch is checked in under
10 minutes (boot ~1-2 min + the check + SMOKE-END) instead of a 30-40 min full run.

Run it with run_smoke.ps1 (sets SMOKE=1, FAST_START=1, SMOKE_CHECK and -Secs from this table), or by hand:
  $env:SMOKE='1'; $env:FAST_START='1'; $env:SMOKE_CHECK='0102'; .\run_walk.ps1 -Tag SMOKE-0102 -Script s_smoke.py -Secs 360
SMOKE_CHECK is a patch number (0102) or a check name (shop). `python s_smoke.py --list` prints the table;
`python s_smoke.py --secs 0102` prints the seconds for run_smoke.ps1.

What each check does: sets its env presets (only the ones the env does not set already), installs s_fast (warp to the
test spot, logged SETUP-WARP; ROUTE_TEST=1 turns that off), then runs the lane step that already proves that thing
(s_shop, s_parlor, s_relog, s_shipfight, s_launch, s_landfight, s_story, s_flagship) with a short time limit. The step's own
PASS / FAIL line is the verdict; with SMOKE=1 the walker ends the run 3 s later (SMOKE-END), and the first STALL is a
FAIL. Events: SMOKE-CHECK (check, patches, step, env, secs, proves) first, then the step's own lines.

A smoke PASS says "this patch's one thing works". It never replaces the full runs: the route, the long story chain
and the two-bot crew checks stay full runs (see README section 12)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__', '.'))))  # exec'd by the walker: no __file__

PR = 'port-royal'       # display names only; the steps hold the real uids
TORTUGA = '1156207188.95dzlu'

# job 8: TUNNEL2's links 4-11 (failed) and 12-15 (never reached), by via uid (walk-TUNNEL2-events.jsonl TUNNELS-START)
TUNNEL_FAILED = ('1164951373.09sdnaik', '1164951656.91sdnaik', '1164951887.34sdnaik', '1169593382.95sdnaik',
                 '1157132484.23sdnaik', '1157133806.45sdnaik', '1169179942.28sdnaik', '1157132912.58sdnaik',
                 '1169179178.34sdnaik', '1169179649.25sdnaik', '1169797457.36sdnaik', '1203997191.31dxschafe')

# name -> (patches, step module, env presets, run secs (PROOF_SECS), what its PASS proves)
CHECKS = {
    'friends': (('0132',), 's_kidfriends', {}, 360,
                'presses every friends button that used to drop a kid to the login screen; he stays in (0132)'),
    'dig': (('0133',), 's_kiddig', {}, 420,
            'digs the same treasure spot twice and a second spot; the chest shows every time (0133)'),
    'shop': (('0102', '0112'), 's_shop', {'SHOP_AT': 'gunsmith', 'SHOP_GOLD': '1'}, 360,
             'buys one item at a Port Royal shop: gold goes down, the stack goes up (0102 buy, 0112 sell guard)'),
    'clothes': (('0103',), 's_shop', {'SHOP_AT': 'tgypsy', 'SHOP_GOLD': '1'}, 360,
                'buys at the tattoo / jewelry / clothing seller (0103)'),
    'blackjack': (('0105', '0107'), 's_parlor', {'PARLOR_KIND': 'Blackjack', 'PARLOR_GOLD': '1', 'PARLOR_SECS': '180'},
                  420, 'sits at a blackjack table and plays a hand (0105 blackjack, 0107 table seat)'),
    'poker': (('0104', '0106'), 's_parlor', {'PARLOR_KIND': 'Holdem', 'PARLOR_GOLD': '1', 'PARLOR_SECS': '180'}, 420,
              "sits at a poker table and plays a hand (0104 poker, 0106 bishop's hand)"),
    'relog': (('0101', '0116'), 's_relog', {'RELOG_SECS': '200'}, 420,
              'logs out and back in: inventory, gold and island are the same after (0101 saves, 0116 return location)'),
    'shipfight': (('0091', '0093', '0094', '0095', '0096', '0114', '0142'), 's_shipfight',
                  {'SHIPFIGHT_SECS': '400', 'SHIPFIGHT_PICKY_SECS': '200'}, 480,
                  'launches, picks a foe near his level (passes far higher ones by), holds it on the beam, breaks off '
                  'under 40% hp to repair, sinks one, gets rep and gold (0093 pay, 0094 level, 0096 plunder, 0114 diag; '
                  '0142 starter waters: every ship-lv line under 9000 ft from Port Royal is level 12 or lower)'),
    'launch': (('0097', '0111', '0110', '0092'), 's_launch', {'LAUNCH_SECS': '25'}, 300,
               'launches his own ship, takes the wheel and sails 150 ft (0097 fresh ship, 0111 repair reply)'),
    'landfight': (('0099', '0108'), 's_landfight', {'LANDFIGHT_SECS': '240', 'LANDFIGHT_KILLS': '1'}, 360,
                  'kills one enemy on land and gets weapon rep (0099 weapon level, 0108 island cannon area)'),
    'quest': (('0098', '0100', '0113'), 's_story',
              {'STORY_START': 'c2_visit_will_turner', 'STORY_STOP': 'c2_visit_will_turner', 'STORY_LIMIT': '300'}, 420,
              'does one story quest start to hand-in (0098 notoriety, 0100 return to the NPC, 0113 choice quests)'),
    'tprefuse': (('0115',), None, {}, 240,
                 'a refused teleport (to where he already is) does not lock him out: the next teleport works'),
    'flagship': (('0135', '0136', '0137', '0138'), 's_flagship', {'SHIP_PATROL_R': '4500', 'FLAGSHIP_SECS': '440', 'FLAGSHIP_NEED_CHEST': '1'}, 480,
                 'cripples a flagship with broadsides, grapples it with a deck cannon, boards it, beats its deck crew '
                 'and captain, swings back paid (0135-0138 boarding steps 1-4; needs the 0122 test knobs on the AI)'),
    # job 8: the TUNNEL2 links that failed (4-11) or were never reached (12-15), walked the whole way (ROUTE_TEST=1: no
    # SETUP-WARP; the warp would skip the very walk this tests). Not a patch check: the walker's own jungle / cave walk
    # (s_cavewalk). Longer than MAX_SECS on purpose (12 links through and back); tunnel-pr / tunnel-tt are the halves
    'tunnel': ((), 's_tunnels', {'ROUTE_TEST': '1', 'TUNNEL_SECS': '240', 'TUNNEL_ONLY': ','.join(TUNNEL_FAILED)}, 3000,
               'walks through and back every TUNNEL2 link that failed (Kings Run, Wicked Thicket, Wildwoods, Tortuga '
               'Graveyard caves and jungles) on foot, along the trail, backing up and re-routing when blocked'),
    'tunnel-pr': ((), 's_tunnels', {'ROUTE_TEST': '1', 'TUNNEL_SECS': '240', 'TUNNEL_ISLANDS': '1150922126.8dzlu',
                                    'TUNNEL_ONLY': ','.join(TUNNEL_FAILED[:4])}, 1500,
                  'the Port Royal half of tunnel: links 4-7 (Kings Run, Wicked Thicket, the two Port Royal caves)'),
    'tunnel-tt': ((), 's_tunnels', {'ROUTE_TEST': '1', 'TUNNEL_SECS': '240', 'TUNNEL_ISLANDS': TORTUGA,
                                    'TUNNEL_ONLY': ','.join(TUNNEL_FAILED[4:])}, 2100,
                  'the Tortuga half of tunnel: links 8-15 (Wildwoods, Graveyard, the swamp, Tortuga cave and its door)'),
}
# patches with no smoke check (on purpose): crew chat 0109 (two bots: s_crew2 full run), ship name 0117 (needs a new
# ship bought: no free test pirate slot for it), 0117 is checked by hand in the full shipwright run.
NOCHECK = {'0109': 'two bots (s_crew2), full run only', '0117': 'needs a fresh ship purchase, full run only'}

MAX_SECS = 480        # boot (<=2 min) + check + 3 s linger + the walker's own end < 10 min


def lookup(key):
    """Pure: SMOKE_CHECK (a check name or a patch number, '115' or '0115') -> (name, entry) or (None, why)."""
    k = str(key or '').strip().lower()
    if k in CHECKS:
        return k, CHECKS[k]
    if k.isdigit():
        k = k.zfill(4)
        for name, e in CHECKS.items():
            if k in e[0]:
                return name, e
        if k in NOCHECK:
            return None, 'patch %s has no smoke check: %s' % (k, NOCHECK[k])
    return None, 'no smoke check called %r (python s_smoke.py --list)' % key


def presets(entry, env):
    """Pure: the env vars this check sets: its presets, minus any the env already sets (a caller's value wins)."""
    return {k: v for k, v in entry[2].items() if k not in env}


def tprefuse(H):
    """0115: ask to teleport to the island he stands on (the server refuses: 'there already'), then to another island.
    Before 0115 the refusal left the teleport lock set, so the second teleport never happened. PASS = he arrives."""
    import s_lanes
    yield ('until', lambda: H.la.getGameState() == 'LandRoam' and H.area() is not None, 90, 'LandRoam')
    here = H.area()
    there = TORTUGA if (here and here[1] != TORTUGA) else s_lanes.PR
    H.ev('TP-REFUSE-1', ask=here and here[1], why='to where he already is')
    H.mw('areaTeleport %s' % (here and here[1]))
    yield ('upto', lambda: False, 4, 'refusal answer')
    H.ev('TP-REFUSE-2', ask=there, gs=H.la.getGameState())
    H.mw('areaTeleport %s' % there)
    t0 = time.time()
    yield ('upto', lambda: H.area() is not None and H.area()[1] == there and H.la.getGameState() == 'LandRoam', 90,
           'the second teleport lands')
    if H.area() is not None and H.area()[1] == there:
        H.ev('PASS', what='a refused teleport left the next one free', to=there, secs=round(time.time() - t0, 1))
    else:
        H.ev('FAIL', why='after a refused teleport the next one did not land in 90 s', area=H.area(),
             gs=H.la.getGameState())


def run(H):
    name, e = lookup(os.environ.get('SMOKE_CHECK'))
    if name is None:
        H.ev('FAIL', why=e)
        return
    patches, mod, _, secs, proves = e
    pre = presets(e, os.environ)
    os.environ.update(pre)                 # before the step's module is imported: its env reads happen at import
    H.ev('SMOKE-CHECK', check=name, patches=list(patches), step=mod or 's_smoke.tprefuse', env=pre, secs=secs,
         proves=proves, smoke=os.environ.get('SMOKE') == '1', fast=os.environ.get('FAST_START') == '1',
         routeTest=os.environ.get('ROUTE_TEST') == '1')
    import s_fast
    s_fast.install(H)
    if mod is None:
        yield from tprefuse(H)
        return
    step = __import__(mod)
    yield from step.run(H)


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['--secs'] and len(a) > 1:
        n, e = lookup(a[1])
        print(e[3] if n else 0)
        sys.exit(0 if n else 1)
    for n, e in CHECKS.items():
        print('%-10s %4d s  patches %-28s %s  %s' % (n, e[3], ','.join(e[0]), e[1] or 's_smoke.tprefuse', e[4]))
    for p, why in NOCHECK.items():
        print('%-10s        patch %s: %s' % ('(none)', p, why))
