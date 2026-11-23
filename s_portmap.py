"""Map run: measure Port Royal's walkable ground round the spawn and every dinghy with the route planner's own
in-game probes (paths.live), so routes can be planned and tested offline on the real town. LAUNCH2 found no route
from the spawn to the one live dinghy (338 checks) and fell back to a blind walk into the harbour.
Saves maps/portroyal.json: grid (STEP ft) of ground z (None = no floor), open legs to the E / N / NE / NW neighbour
(paths.live legs_ok), the world-data dinghy spots and the live dinghies in render space, and the spawn.
Events: MAP-START, map-ground, map-edges (progress), PASS when the file is saved, FAIL says why."""
import os, sys, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
from panda3d.core import Point3   # noqa: E402
import sailing, paths   # noqa: E402
from s_dock import cls   # noqa: E402

PR = '1150922126.8dzlu'
STEP = 10.0
PAD = 60.0
BATCH = 800         # legs per collision pass


def run(H):
    la, R = H.la, H.render
    yield ('until', lambda: la.getGameState() in ('LandRoam', 'ShipPilot', 'WaterRoam'), 60, 'LandRoam')
    if sailing.hereUid(H) != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
    isl = sailing.islandObj(H, PR)
    if isl is None:
        H.ev('FAIL', why='no Port Royal island object'); return
    a = la.getPos(R)
    spots = [tuple(round(v, 1) for v in R.getRelativePoint(isl, Point3(*s))) for s in sailing.dinghySpots(PR)]
    live = [{'doId': o.doId, 'pos': H.P(o)} for o in H.cr.doId2do.values() if cls(o) == 'DistributedDinghy']
    H.ev('MAP-START', la=H.P(la), spots=spots, live=live)
    xs = [a[0]] + [s[0] for s in spots]
    ys = [a[1]] + [s[1] for s in spots]
    x0, y0 = min(xs) - PAD, min(ys) - PAD
    nx = int((max(xs) + PAD - x0) / STEP) + 1
    ny = int((max(ys) + PAD - y0) / STEP) + 1
    legs_ok, ground = paths.live(H, 0.0)
    cells = [(i, j) for j in range(ny) for i in range(nx)]
    zs = []
    t0 = time.time()
    for k in range(0, len(cells), 2000):
        zs += ground([(x0 + i * STEP, y0 + j * STEP, a[2]) for i, j in cells[k:k + 2000]])
        yield 0
    z = {c: v for c, v in zip(cells, zs)}
    land = sum(1 for v in zs if v is not None and v >= paths.WATER_Z)
    H.ev('map-ground', nx=nx, ny=ny, cells=len(cells), land=land, secs=round(time.time() - t0, 1))
    dirs = ((1, 0), (0, 1), (1, 1), (-1, 1))
    todo = []
    for (i, j) in cells:
        if z[(i, j)] is None or z[(i, j)] < paths.WATER_Z:
            continue
        for d, (di, dj) in enumerate(dirs):
            c2 = (i + di, j + dj)
            if z.get(c2) is not None and z[c2] >= paths.WATER_Z:
                todo.append(((i, j), d, c2))
    edges = {}
    t0 = time.time()
    for k in range(0, len(todo), BATCH):
        chunk = todo[k:k + BATCH]
        res = legs_ok([((x0 + c[0] * STEP, y0 + c[1] * STEP, z[c]), (x0 + c2[0] * STEP, y0 + c2[1] * STEP, z[c2]), False)
                       for c, d, c2 in chunk])
        for (c, d, c2), r in zip(chunk, res):
            if r:
                edges[c] = edges.get(c, 0) | (1 << d)
        if (k // BATCH) % 10 == 0:
            H.ev('map-edges', done=k + len(chunk), of=len(todo), secs=round(time.time() - t0, 1))
        yield 0
    out = {'island': PR, 'step': STEP, 'x0': x0, 'y0': y0, 'nx': nx, 'ny': ny, 'waterZ': paths.WATER_Z,
           'start': [round(v, 1) for v in a], 'spots': spots, 'live': live,
           'z': [None if v is None else round(v, 2) for v in zs],
           'edges': {'%d,%d' % c: b for c, b in edges.items()}, 'dirs': dirs}
    d = os.path.join(os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])), 'maps')
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, 'portroyal.json')
    with open(f, 'w') as fh:
        json.dump(out, fh)
    H.ev('PASS', what='Port Royal walk map saved', file=f, cells=len(cells), land=land, legs=len(todo),
         open=sum(bin(b).count('1') for b in edges.values()), edgeSecs=round(time.time() - t0, 1))
