"""Offline check of paths.plan / best_route on a made-up harbour town (no game): buildings are boxes, the sea is y > 60.
Every route it returns is re-checked here on a 1 ft walk with the pirate's width, so a pass means the route really
goes round the buildings and stays out of the water. Run: python test_paths.py  -> ALL PASS or the failures."""
import math, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths   # noqa: E402

SEA_Y = 60.0
BUILDINGS = [(-200, -140, 150, -60),      # (x0, y0, x1, y1): a long block between the spawn and the harbour
             (-260, -40, -120, 30),
             (40, -260, 120, -170)]
SHORT = 16.0


def inside(x, y, pad=0.0):
    return any(x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad for x0, y0, x1, y1 in BUILDINGS)


def ground(pts):
    return [None if y > SEA_Y else 3.0 for x, y, z in pts]


def leg_ok(p, q, last):
    L = paths.dist(p, q)
    if last and L > SHORT:
        f = (L - SHORT) / L
        q = (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f, p[2])
    elif last:
        return True
    n = max(1, int(paths.dist(p, q) / 2))
    for i in range(n + 1):
        x, y = p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n
        if y > SEA_Y or inside(x, y, 1.2):
            return False
    return True


def walked_clear(a, route):
    """1 ft steps along the route: never inside a building (with the pirate's width), never in the sea before the
    last SHORT ft."""
    pts = [a] + route
    for j in range(len(pts) - 1):
        p, q = pts[j], pts[j + 1]
        L = paths.dist(p, q)
        stop = L - SHORT if j == len(pts) - 2 else L
        s = 0.0
        while s <= stop:
            x, y = p[0] + (q[0] - p[0]) * s / L, p[1] + (q[1] - p[1]) * s / L
            if inside(x, y, 1.0) or y > SEA_Y:
                return 'blocked at %.1f, %.1f' % (x, y)
            s += 1.0
    return None


def legs_ok(pqls):
    return [leg_ok(p, q, last) for p, q, last in pqls]


fails = []


def check(name, cond, info=''):
    print('%-4s %s %s' % ('PASS' if cond else 'FAIL', name, info))
    if not cond:
        fails.append(name)


# 1. LAUNCH1 shape: spawn south of a long block, the nearest dinghy straight through it.
a = (20.0, -200.0, 3.0)
dinghies = [(-20.0, 75.0, 0.0), (400.0, 75.0, 0.0), (-400.0, 75.0, 0.0)]
check('straight line to the nearest dinghy is blocked (like LAUNCH1)', not leg_ok(a, dinghies[0], True))
g, r, c = paths.best_route(a, dinghies, legs_ok, ground, short=SHORT)
check('finds a route round the block', r is not None, 'goal=%s route=%s checks=%d' % (g, r and [[round(v) for v in w[:2]] for w in r], c))
if r:
    check('the route really is clear (1 ft walk)', walked_clear(a, r) is None, walked_clear(a, r) or '')
    check('no turn point in the water', all(w[1] <= SEA_Y for w in r[:-1]))
    check('route is not silly long', paths.length(a, r) < 2.0 * paths.dist(a, g), '%.0f ft vs straight %.0f' % (paths.length(a, r), paths.dist(a, g)))

# 2. Open ground: straight at it, no turn points.
a2 = (300.0, -50.0, 3.0)
r2, c2 = paths.plan(a2, (320.0, 75.0, 0.0), legs_ok, ground, short=SHORT)
check('open ground walks straight', r2 is not None and len(r2) == 1, 'route=%s checks=%d' % (r2, c2))

# 3. Behind two buildings (needs two turn points or a long way round).
a3 = (-190.0, -50.0, 3.0)
g3, r3, c3 = paths.best_route(a3, [(-190.0, 75.0, 0.0)], legs_ok, ground, short=SHORT)
check('gets out from between two blocks', r3 is not None and walked_clear(a3, r3) is None,
      'route=%s checks=%d' % (r3 and [[round(v) for v in w[:2]] for w in r3], c3))

# 4. Walled in on every side: says no instead of walking into a wall, inside its check budget.
BUILDINGS.extend([(500, -100, 600, -95), (500, 5, 600, 10), (495, -100, 500, 10), (600, -100, 605, 10)])
r4, c4 = paths.plan((550.0, -45.0, 3.0), (550.0, 75.0, 0.0), legs_ok, ground, short=SHORT)
check("walled in -> no route", r4 is None, 'checks=%d' % c4)

# 5. A turn point that got stuck is not used again.
if r and len(r) > 1:
    r5, c5 = paths.plan(a, g, legs_ok, ground, avoid=[r[0]], short=SHORT)
    check('re-plan avoids the stuck turn point', r5 is not None and all(paths.dist(w, r[0]) >= paths.GRID for w in r5[:-1]),
          'route=%s' % (r5 and [[round(v) for v in w[:2]] for w in r5]))

# 6. LAUNCH4 shape: the spawn is on the bank of a channel and the way out is a bridge. The deck is not the ground nearest
#    the pirate under it: a shelf of the bank runs on below the ramp (1 ft under the pirate, the deck 2.8 ft over it), then
#    drops into the water. A planner that gives every grid point the one ground nearest the point it comes from follows
#    the shelf into the sea and finds no route; it has to see both floors and let the leg checks choose the deck.
BY, DECK_W = 0.0, 14.0                 # the bridge runs along x, centred on y = BY, 28 ft wide between its rails


def terrain(x):
    x = abs(x)
    return 5.0 if x >= 100 else 4.0 + (x - 80) * 0.05 if x >= 80 else max(-6.0, 4.0 - (80 - x) * 0.175)   # swim-deep mid-channel


def deck(x, y):
    return None if abs(x) >= 100 or abs(y - BY) > DECK_W else min(13.4, 5.0 + 0.14 * (100 - abs(x)))


def bridge_floors(pts):
    return [sorted(z for z in (terrain(x), deck(x, y)) if z is not None) for x, y, zn in pts]


def bridge_ground(pts):
    return [min(zs, key=lambda z: abs(z - p[2])) for p, zs in zip(pts, bridge_floors(pts))]


bridge_ground.floors = bridge_floors


def bridge_leg_ok(p, q, last):
    L = paths.dist(p, q)
    if last and L > SHORT:
        f = (L - SHORT) / L
        q = (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f, p[2])
    elif last:
        return True
    n, prev = max(1, int(paths.dist(p, q) / 2)), None
    for i in range(n + 1):
        x, y, zl = [p[k] + (q[k] - p[k]) * i / n for k in range(3)]
        z = bridge_ground([(x, y, zl)])[0]
        d = deck(x, y)
        if z < paths.WATER_Z or (prev is not None and (z - prev > paths.MAX_RISE or prev - z > paths.MAX_DROP)):
            return False
        if abs(x) < 100 and abs(zl - terrain(x)) > 1.5 and abs(y - BY) > DECK_W - 1.2:   # on the deck: the rails
            return False
        prev = z
    return True


a6, b6 = (250.0, 0.0, 5.0), (-250.0, 10.0, 5.0)
check('the straight line to the far bank is not open', not bridge_leg_ok(a6, b6, True))
g6, r6, c6 = paths.best_route(a6, [b6], lambda pqls: [bridge_leg_ok(*x) for x in pqls], bridge_ground, short=SHORT)
check('finds the way over the bridge', r6 is not None, 'route=%s checks=%d' % (r6 and [[round(v) for v in w] for w in r6], c6))
if r6:
    check('the route goes over the deck, not along the shelf', any(w[2] > 8 for w in r6[:-1]))
    check('the bridge route is not silly long', paths.length(a6, r6) < 1.3 * paths.dist(a6, b6), '%.0f ft' % paths.length(a6, r6))

# 7. IND4 shape: a far goal (500 ft) behind a wall wider than the search box; the only way round is past the wall's
#    end, outside the box round start and goal. The first search runs dry; the wide retry finds the way round.
BUILDINGS.append((700, -305, 1300, -295))
a7, b7 = (1000.0, -100.0, 3.0), (1000.0, -600.0, 3.0)
check('the first box has no way round the wall', paths.plan(a7, b7, legs_ok, ground)[0] is None)
g7, r7, c7 = paths.best_route(a7, [b7], legs_ok, ground)
check('the wide retry goes round the wall end', r7 is not None and walked_clear(a7, r7) is None,
      'route=%s checks=%d' % (r7 and [[round(v) for v in w[:2]] for w in r7], c7))
#    with a farther goal that has a route inside its own box, the wall goal is never searched wide (dinghies out on the
#    water)
b7n, margins, plan_g0 = (300.0, -150.0, 3.0), [], paths.plan_g
paths.plan_g = lambda *x: (margins.append(x[6] if len(x) > 6 else paths.MARGIN), plan_g0(*x))[1]
g7n, r7n, c7n = paths.best_route(a7, [b7, b7n], legs_ok, ground)
paths.plan_g = plan_g0
check('no wide search when a goal has a route', g7n == b7n and margins == [paths.MARGIN] * 2,
      'goal=%s margins=%s' % (g7n, margins))

# 8. IND6 shape: a 50 ft thick wall across the whole box with one 8 ft gap that falls between the lines of the
#    goal-aligned grid (they run at x = 3000 and 3020, the gap is 3006-3014). The half-step shifted grid runs through it.
BUILDINGS += [(2500, -900, 3006, -850), (3014, -900, 3500, -850)]
a8, b8 = (3080.0, -950.0, 3.0), (3000.0, -800.0, 3.0)
check('the goal-aligned grid misses the gap', paths.plan(a8, b8, legs_ok, ground)[0] is None)
g8, r8, c8 = paths.best_route(a8, [b8], legs_ok, ground)
check('the shifted grid goes through the gap', r8 is not None and walked_clear(a8, r8) is None,
      'route=%s checks=%d' % (r8 and [[round(v) for v in w[:2]] for w in r8], c8))

# 9. IND7 shape: walk_route told to stop 110 ft from the goal; the plan's first turn point is already 47 ft from it and
#    the next turn point is the goal itself. The walk stops after the first turn point.
class FakeH:
    render = None

    def __init__(self, p):
        self.p, self.walked, self.la = p, [], self

    def getPos(self, R):
        return self.p

    def walk_to(self, w, arrive, tag):
        self.walked.append(w)
        self.p = w
        return True
        yield

    def ev(self, *x, **k):
        pass


def fake_route(a, goals, *x):
    return goals[0], [t9, goals[0], goals[0]], 0
    yield


g9, t9, H9 = (-274.3, 57.3, 2.7), (-294.3, 17.3, 4.5), FakeH((-438.4, -77.3, 14.1))
live0, best0 = paths.live, paths.best_route_g
paths.live, paths.best_route_g = (lambda H, short: (legs_ok, ground)), fake_route
got9 = paths.run_now(paths.walk_route(H9, [g9], 110.0))
paths.live, paths.best_route_g = live0, best0
check('the walk stops once within the stop distance', got9 == g9 and H9.walked == [t9], 'walked=%s' % H9.walked)

# 10. MAIN21 shape (Padres, 11-21): the start and the goal (750 ft off) are in a boulder field where no leg longer than
#     8 ft is open, so the 20 ft grid never gets off the start. One 4 ft escape hop ends at the corner of its box, still in
#     the field; the escape goes on hop after hop to the goal.
ROUGH = (-100.0, -300.0, 1200.0, 300.0)


def rough_leg_ok(p, q, last):
    if paths.dist(p, q) <= 8.0:
        return True
    return not any(ROUGH[0] <= x <= ROUGH[2] and ROUGH[1] <= y <= ROUGH[3]
                   for x, y in ((p[0] + (q[0] - p[0]) * i / 20, p[1] + (q[1] - p[1]) * i / 20) for i in range(21)))


a10, b10 = (50.0, 0.0, 3.0), (800.0, 0.0, 3.0)
rough = lambda pqls: [rough_leg_ok(p, q, last) for p, q, last in pqls]
g10, r10, c10 = paths.best_route(a10, [b10], rough, lambda pts: [3.0 for _ in pts])
check('hop after hop through the boulder field', r10 is not None and r10[-1] == b10
      and all(rough_leg_ok(p, q, False) for p, q in zip([a10] + r10, r10)),
      'checks=%d hops=%s legs=%s' % (c10, paths.ESCAPE.get('hops'), r10 and len(r10)))

print('ALL PASS' if not fails else 'FAILED: %s' % ', '.join(fails))
sys.exit(1 if fails else 0)
