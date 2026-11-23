"""FAST START (pir-bot, 11-17, job 5): start a check at its test spot instead of walking the whole route there.
Not a step itself (no run()). s_smoke.py installs it; any step can: `import s_fast; s_fast.install(H)` first thing.

What it does, only while FAST_START=1 and ROUTE_TEST is not 1:
1. Island: the steps' own setup move, the server's areaTeleport (s_lanes.onIsland / s_story STORY_AT), as before.
   With FAST_START it also sets STORY_TP=1 (s_story's areaTeleport between islands instead of a sea crossing), unless
   the env already sets STORY_TP.
2. Spot: every walk the steps start (s_story.go, the one walk helper all of them use) that is longer than FAST_MIN
   (40 ft) is replaced by a client warp next to the target: the pirate is put ARRIVE x 0.5 ft short of it, on the line
   from where he stood, then s_story.go's own last bit (face it / step in) runs as normal. Each warp is logged
   SETUP-WARP (tag, from, to, dist, route='untested'). The walker's tripwire also logs it as a TELEPORT (s_fast.py
   file:line) and counts it in finish teleports=n: a fast run is never a route proof, and the finish line says so.
   Never warped: walks in a fight (weapon drawn, or the walk's tag matches FAST_NOWARP: foe / fight / enemy / engage /
   chase / ship / dinghy), walks while not in LandRoam, and walks shorter than FAST_MIN.
3. Doors and tunnels: s_story.goto plans them hop by hop, each hop a go() to the door or tunnel node: the warp puts
   him by the door and the door is still used the game's way (the area change is real).

ROUTE_TEST=1 turns all of it off (the runs that test the route itself: s_tutorial's walk, the route lanes, TUT*).
env: FAST_START, ROUTE_TEST, FAST_MIN (40), FAST_NOWARP (regex), FAST_MAX (0 = no cap: the most warps in one run)."""
import os, sys, re, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__', '.'))))  # exec'd by the walker: no __file__

FAST = os.environ.get('FAST_START') == '1' and os.environ.get('ROUTE_TEST') != '1'
FAST_MIN = float(os.environ.get('FAST_MIN', '40'))
NOWARP = re.compile(os.environ.get('FAST_NOWARP', r'foe|fight|enemy|engage|chase|ship|dinghy|wheel|boss'), re.I)
FAST_MAX = int(os.environ.get('FAST_MAX', '0') or 0)
STATE = {'installed': False, 'n': 0}

if FAST and 'STORY_TP' not in os.environ:
    os.environ['STORY_TP'] = '1'


def shouldWarp(dist, gs, tag, weaponDrawn, n=0, fast=None, fastMin=None, fastMax=None):
    """Pure: (yes, why) for one walk."""
    fast = FAST if fast is None else fast
    fastMin = FAST_MIN if fastMin is None else fastMin
    fastMax = FAST_MAX if fastMax is None else fastMax
    if not fast:
        return False, 'fast start off'
    if gs != 'LandRoam':
        return False, 'not LandRoam (%s)' % gs
    if weaponDrawn:
        return False, 'weapon drawn'
    if tag and NOWARP.search(str(tag)):
        return False, 'tag %s is a fight / ship walk' % tag
    if dist <= fastMin:
        return False, 'short walk (%.0f ft)' % dist
    if fastMax and n >= fastMax:
        return False, 'warp cap %d reached' % fastMax
    return True, 'walk of %.0f ft' % dist


def warpPoint(me, target, arrive):
    """Pure: the spot ARRIVE x 0.5 short of target on the line from me (x, y), at the target's height + 0.5."""
    dx, dy = me[0] - target[0], me[1] - target[1]
    d = (dx * dx + dy * dy) ** 0.5
    back = max(1.0, arrive * 0.5)
    if d < 1e-3:
        return (target[0], target[1], target[2] + 0.5)
    k = min(back, d) / d
    return (target[0] + dx * k, target[1] + dy * k, target[2] + 0.5)


def _weaponDrawn(la):
    for name in ('isWeaponDrawn', 'getWeaponDrawn'):
        f = getattr(la, name, None)
        try:
            if callable(f):
                return bool(f())
            if f is not None:
                return bool(f)
        except Exception:
            pass
    return bool(getattr(la, 'isWeaponDrawn', False))


def install(H):
    """Wrap s_story.go (once). A no-op unless FAST_START=1 and ROUTE_TEST is not 1."""
    if STATE['installed']:
        return FAST
    STATE['installed'] = True
    H.ev('FAST-START', on=FAST, routeTest=os.environ.get('ROUTE_TEST') == '1', fastMin=FAST_MIN,
         storyTp=os.environ.get('STORY_TP'))
    if not FAST:
        return False
    import s_story
    orig = s_story.go

    def go(H2, target, arrive, face, ref, tag):
        try:
            p = s_story._render_pt(H2, target, ref)
            me = H2.la.getPos(H2.render)
            dist = ((p[0] - me[0]) ** 2 + (p[1] - me[1]) ** 2) ** 0.5
            yes, why = shouldWarp(dist, H2.la.getGameState(), tag, _weaponDrawn(H2.la), STATE['n'])
        except Exception as e:
            yes, why = False, 'error %r' % e
        if yes:
            w = warpPoint((me[0], me[1], me[2]), (p[0], p[1], p[2]), arrive)
            H2.ev('SETUP-WARP', tag=tag, frm=[round(v, 1) for v in me], to=[round(v, 1) for v in w],
                  target=[round(v, 1) for v in p], dist=round(dist, 1), route='untested', why=why, area=H2.area())
            H2.walk_cancel()
            H2.la.setPos(H2.render, w[0], w[1], w[2])
            if hasattr(target, 'getPos'):
                H2.la.headsUp(target)
            STATE['n'] += 1
            yield ('upto', lambda: H2.la.getGameState() == 'LandRoam', 1.0, 'settle after warp')
        return (yield from orig(H2, target, arrive, face, ref, tag))
    s_story.go = go
    return True
