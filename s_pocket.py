"""Pocket check: why the route planner finds no walk out of a spot. LAUNCH4 stood at Port Royal (523.4, 101.0, 2.6)
after BULB4 and planned no route to any of the 8 dinghies (4121 checks): the open ground it could reach was a small
pocket. A player standing there walks out, so the planner is missing something; this run measures what.
At Port Royal, with a logged SETUP-POS to POCKET_AT (diagnosis only, never in play):
  pocket-ground  ground z on a 5 ft grid within RADIUS ft (None = no floor), as the planner probes it
  pocket-rays    for 16 headings, which legs out of the spot (10/20/40/60 ft) pass paths.live legs_ok, and why not
                 (wall at knee/chest height, or the ground: missing, under water, a step up or a drop)
  pocket-plan    the dinghy plan at GRID 20 (as LAUNCH4) and again at GRID 10
  shots          four views round the spot -> shots/pocket/
PASS when everything is logged (the goal is the data).
env: POCKET_AT ('x,y,z' render space, default the LAUNCH4 spot), POCKET_TAG (default 'p1')."""
import os, sys, math

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
from panda3d.core import Filename, Point3   # noqa: E402
import sailing, paths   # noqa: E402

PR = '1150922126.8dzlu'
AT = tuple(float(v) for v in os.environ.get('POCKET_AT', '523.4,101.0,2.6').split(','))
TAG = os.environ.get('POCKET_TAG', 'p1')
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])), 'shots', 'pocket')
RADIUS = 60.0
FINE = 5.0


def why_not(legs_ok, ground, p, q):
    """'open', or what stops the leg p -> q: the walls (legs_ok fails but the ground along it is fine) or the ground."""
    if legs_ok([(p, q, False)])[0]:
        return 'open'
    m = max(1, int(paths.dist(p, q) / paths.SAMPLE))
    zs = ground([(p[0] + (q[0] - p[0]) * i / m, p[1] + (q[1] - p[1]) * i / m, p[2]) for i in range(m + 1)])
    prev = None
    for i, z in enumerate(zs):
        if z is None:
            return 'no floor at %d ft' % round(i * paths.SAMPLE)
        if z < paths.WATER_Z:
            return 'water z %.1f at %d ft' % (z, round(i * paths.SAMPLE))
        if prev is not None and z - prev > paths.MAX_RISE:
            return 'step up %.1f at %d ft' % (z - prev, round(i * paths.SAMPLE))
        if prev is not None and prev - z > paths.MAX_DROP:
            return 'drop %.1f at %d ft' % (prev - z, round(i * paths.SAMPLE))
        prev = z
    return 'wall'


def run(H):
    la, R = H.la, H.render
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if sailing.hereUid(H) != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
    H.ev('SETUP-POS', to=list(AT), frm=H.P(la), why='diagnosis: put the pirate where LAUNCH4 planned no route')
    la.setPos(R, *AT)
    yield 3
    p = la.getPos(R)
    a = (p[0], p[1], p[2])
    legs_ok, ground = paths.live(H)
    n = int(RADIUS / FINE)
    cells = [(i, j) for i in range(-n, n + 1) for j in range(-n, n + 1) if math.hypot(i, j) * FINE <= RADIUS]
    zs = ground([(a[0] + i * FINE, a[1] + j * FINE, a[2]) for i, j in cells])
    rows = {}
    for (i, j), z in zip(cells, zs):
        rows.setdefault(j, {})[i] = '  .  ' if z is None else ('~%4.1f' % z if z < paths.WATER_Z else '%5.1f' % z)
    H.ev('pocket-ground', at=H.P(la), step=FINE, radius=RADIUS,
         rows=[''.join(rows[j].get(i, '     ') for i in range(-n, n + 1)) for j in range(n, -n - 1, -1)])
    yield 0
    rays = {}
    for k in range(16):
        h = k * 22.5
        dx, dy = math.cos(math.radians(h)), math.sin(math.radians(h))
        out = []
        for r in (10, 20, 40, 60):
            q = (a[0] + dx * r, a[1] + dy * r, a[2])
            gz = ground([q])[0]
            q = (q[0], q[1], gz if gz is not None else a[2])
            out.append('%d:%s' % (r, why_not(legs_ok, ground, a, q)))
        rays['%05.1f' % h] = out
        yield 0
    H.ev('pocket-rays', at=H.P(la), rays=rays)
    isl = sailing.islandObj(H, PR)
    goals = [tuple(R.getRelativePoint(isl, Point3(*s))) for s in sailing.dinghySpots(PR)] if isl is not None else []
    for grid in (20.0, 10.0):
        old = paths.GRID, paths.MAX_EXPAND
        paths.GRID, paths.MAX_EXPAND = grid, 4000 if grid == 20.0 else 16000
        try:
            g, r, checks = yield from paths.best_route_g(a, goals, legs_ok, ground, (), sailing.DINGHY_SHORT, len(goals))
        finally:
            paths.GRID, paths.MAX_EXPAND = old
        H.ev('pocket-plan', grid=grid, goal=[round(v, 1) for v in g] if g else None,
             path=[[round(v, 1) for v in w] for w in r] if r else None,
             length=round(paths.length(a, r), 1) if r else None, checks=checks)
    os.makedirs(OUTDIR, exist_ok=True)
    for k, h in enumerate((0, 90, 180, 270)):
        la.setH(h)
        yield 2
        f = os.path.join(OUTDIR, '%s-%d.png' % (TAG, h))
        ok = H.B.win.saveScreenshot(Filename.fromOsSpecific(f))
        H.ev('pocket-shot', h=h, file=f, ok=bool(ok))
    H.ev('PASS', what='pocket measured and shot')
