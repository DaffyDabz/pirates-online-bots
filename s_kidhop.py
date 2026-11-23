"""KIDHOP (pir-test, 11-18, brain's order): the published kid client (a v456 kid tree) does a player's short
session against the live server: log in, walk in Port Royal, one map hop, log out.

  - logged in and standing on an island (LandRoam)
  - not on Port Royal: one map hop to Port Royal (teleportMgr.requestTeleportToIsland, the map's own call), then walk
  - on Port Royal: walk first, then one map hop to Padres del Fuego
  - the walk: to the nearest Port Royal shipwright spot (round the buildings, like s_island's buy walk);
    passes when he walked at least WALK_MIN ft
  - log out the player's way (the logout hotkey, s_relog.logout) -> the avatar list

No magic words, no fallbacks: a refused map teleport is a FAIL. Lines: KIDHOP-START, HOP-GO, HOP, WALK, LOGOUT,
then PASS or FAIL. Never runs on pirate 100000170."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__', '.'))))
import sailing   # noqa: E402
import s_story   # noqa: E402
import s_lanes   # noqa: E402
import s_relog   # noqa: E402

PR = s_lanes.PR
PADRES = '1142018473.22dxschafe'
NAMES = {PR: 'Port Royal', s_lanes.TORTUGA: 'Tortuga', PADRES: 'Padres Del Fuego'}
BANNED = (100000170,)
HOP_SECS = float(os.environ.get('KIDHOP_HOP_SECS', '120'))
WALK_MIN = 25.0


def run(H):
    from panda3d.core import Point3
    la, cr = H.la, H.cr
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if la.doId in BANNED:
        H.ev('FAIL', why='KIDHOP never runs on this pirate (his own)', pirate=la.doId); return
    start = s_lanes.islandOf(H)
    H.ev('KIDHOP-START', pirate=la.doId, island=NAMES.get(start, start), gs=la.getGameState(), area=H.area(),
         gold=s_lanes.gold(H))
    if la.getGameState() != 'LandRoam' or start is None:
        H.ev('FAIL', why='not standing on an island after login', gs=la.getGameState(), area=H.area()); return

    warnings = []
    origWarn = la.guiMgr.createWarning

    def warn(msg, *a, **k):
        warnings.append(str(msg)[:120])
        return origWarn(msg, *a, **k)
    la.guiMgr.createWarning = warn

    def hop(tgt):
        frm = sailing.hereUid(H)
        yield 3
        t0 = time.time()
        H.ev('HOP-GO', frm=NAMES.get(frm, frm), to=NAMES[tgt], canTeleport=la.canTeleport())
        cr.teleportMgr.requestTeleportToIsland(tgt)
        landed = False
        while time.time() - t0 < HOP_SECS:
            if sailing.hereUid(H) == tgt and la.getGameState() == 'LandRoam':
                landed = True
                break
            yield 0.5
        H.ev('HOP', frm=NAMES.get(frm, frm), to=NAMES[tgt], ok=landed, secs=round(time.time() - t0, 1),
             gs=la.getGameState(), area=H.area(), said=warnings)
        return landed

    def walk():
        spots = sailing.shipwrightSpots(PR)
        if not spots:
            H.ev('WALK', ok=False, why='no shipwright in Port Royal world data'); return False
        org = s_story.areaObj(H, PR)
        me = la.getPos(H.render)
        pts = [H.render.getRelativePoint(org, Point3(*p)) if org is not None else Point3(*p) for p in spots]
        k = min(range(len(spots)), key=lambda i: (pts[i] - me).length())
        p0 = la.getPos(H.render)
        r = yield from s_lanes.walkTo(H, 'kidhop', lambda st: s_story.goto(H, st, PR, pos=spots[k], arrive=8.0,
                                                                            tag='pr-walk'), 240, 'Port Royal shipwright')
        walked = round((la.getPos(H.render) - p0).length(), 1)
        ok = r is not None and walked >= WALK_MIN
        H.ev('WALK', ok=ok, walked=walked, la=H.P(la), area=H.area())
        return ok

    if start == PR:
        walked = yield from walk()
        hopped = yield from hop(PADRES)
    else:
        hopped = yield from hop(PR)
        walked = (yield from walk()) if hopped else False
    old = la
    out = yield from s_relog.logout(H)
    H.ev('LOGOUT', ok=bool(out))
    bad = [w for w, ok in (('the map hop', hopped), ('the walk in Port Royal', walked), ('the logout', out)) if not ok]
    if bad:
        H.ev('FAIL', why='failed: ' + ', '.join(bad), pirate=old.doId)
    else:
        H.ev('PASS', what='kid client: logged in, walked in Port Royal, one map hop, logged out', pirate=old.doId)
