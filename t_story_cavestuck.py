"""Offline test of s_cavewalk.walk after a stuck (MAIN48, 11-22, Queen's Nest, visitMary): the planned leg passed a
wall corner closer than the pirate drifts, he stuck, and every re-plan drew a new leg past the same corner (the grid
search and the corner cutting never saw the closed legs) until the straight leg to Mary was closed too and the graph
(no waypoint near Mary) had nothing left: CAVE-NO-ROUTE. Now no leg is planned within STUCK_R of a spot he stuck at,
and with no chain left the grid is searched round the whole way.
Fake cave: flat floor, a wall along y = -25 from x = -100 to the corner at x = -195, the pirate north of it, Mary far
south-west, the waypoints all east (none near Mary). The fake walk sticks on any leg passing within DRIFT ft of the
corner (the planner's probes clear 1.2 ft). Run: python3 t_story_cavestuck.py <dir holding s_cavewalk.py>"""
import math, os, sys, types

D = os.path.abspath(sys.argv[1])
sys.path.insert(0, D)
import s_cavewalk as C     # noqa: E402

Z = 13.5
WALLS = [((-100.0, -25.0), (-195.0, -25.0))]
CORNER = (-195.0, -25.0)
DRIFT = 2.6
START, MARY = (-170.4, -13.4, Z), (-450.6, -409.0, 2.5)
NODES = {1: (-80.0, 0.0, Z), 2: (-80.0, -100.0, Z), 3: (0.0, 0.0, Z), 4: (-60.0, 60.0, Z)}


def seg_pt(p, q, s):
    dx, dy = q[0] - p[0], q[1] - p[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((s[0] - p[0]) * dx + (s[1] - p[1]) * dy) / L2))
    return (p[0] + dx * t, p[1] + dy * t), t


def cross(p, q, a, b):
    def o(u, v, w):
        return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
    return o(p, q, a) * o(p, q, b) < 0 and o(a, b, p) * o(a, b, q) < 0


def clear(p, q, pad):
    """The leg keeps pad ft from every wall (and never crosses one)."""
    for a, b in WALLS:
        if cross(p, q, a, b):
            return False
        for s in (a, b):
            if math.dist(seg_pt(p, q, s)[0], s) < pad:
                return False
        for s in (p, q):
            if math.dist(seg_pt(a, b, s)[0], s[:2]) < pad:
                return False
    return True


def legs_ok(pqls):
    return [clear(p, q, 1.2) for p, q, last in pqls]


legs_ok.pad = 0.0


def ground(pts):
    return [Z if p[0] > -600 else None for p in pts]


class La:
    pos = list(START)

    def getPos(self, R):
        return list(self.pos)


H = types.SimpleNamespace(la=La(), render='R', area=lambda: ('GA', 'qn'), P=lambda la: [round(v, 1) for v in la.pos])
EV = []
H.ev = lambda ev, **kw: EV.append(dict(kw, ev=ev))


def fake_leg(H, w, **kw):
    """Sticks where the leg first comes within DRIFT ft of the corner, else arrives."""
    p = H.la.pos
    s, t = seg_pt(p, w, CORNER)
    if math.dist(s, CORNER) < DRIFT and t > 0.0:
        H.la.pos = [s[0], s[1], Z]
        return False, None
    if False:
        yield 0
    H.la.pos = [w[0], w[1], w[2]]
    return True, None


def fake_back_up(H, tag, secs=1.0):
    """7 ft back the way he came (MAIN48: (-176.2, -17.2) -> (-170.4, -13.4))."""
    p = H.la.pos
    H.la.pos = [p[0] + 5.0, p[1] + 5.0, Z]
    if False:
        yield 0
    return p


C.load = lambda uid, wd=None: (NODES, [], 'fake_qn')
C.area_points = lambda H, uid, data: dict(data[0])
C.other_areas = lambda H, uid: []
C.own_area = lambda H, uid: None
C.area_probe = lambda H, uid, others=None, own=None: (legs_ok, ground, types.SimpleNamespace(
    mode='others', prune=lambda: True, skipped=0))
C.in_tunnel = lambda H: None
C._leg = fake_leg
C.back_up = fake_back_up

fails = []
g = C.walk(H, MARY, 5.0, 'visitMary')
try:
    while True:
        next(g)
except StopIteration as e:
    got = e.value
routes = [e for e in EV if e['ev'] == 'CAVE-ROUTE']
backs = [e for e in EV if e['ev'] == 'CAVE-BACKUP']
print('result', got, 'plans', len(routes), 'stucks', len(backs), 'end', H.P(H.la))
for e in routes:
    print('  ', e['attempt'], e['how'], e['path'][:4] if e['path'] else None)
if got is not True:
    fails.append('never reached Mary: %s, %d stucks' % (got, len(backs)))
if any(e['ev'] == 'CAVE-NO-ROUTE' for e in EV):
    fails.append('CAVE-NO-ROUTE logged')

# the wrapper alone: a closed leg and a leg past a stuck spot are shut, a leg heading away from it is open
ok = C.avoid_stuck(lambda pq: [True] * len(pq), [((0.0, 0.0, 0.0), (9.0, 9.0, 0.0))], {C.lkey((50, 50, 0), (60, 50, 0))})
r = ok([((-10, 3, 0), (10, 3, 0), False), ((-10, 5, 0), (10, 5, 0), False), ((50, 50, 0), (60, 50, 0), False),
        ((2, 0, 0), (-5, 0, 0), False), ((2, 0, 0), (9, 0, 0), False)])
if r != [False, True, False, False, True]:
    fails.append('avoid_stuck %s' % r)
print('FAIL: ' + '; '.join(fails) if fails else 'ALL PASS')
