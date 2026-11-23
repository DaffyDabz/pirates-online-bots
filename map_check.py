"""Offline route check on a measured walk map (s_portmap.py -> maps/portroyal.json): which dinghies the spawn can
walk to, and the route paths.best_route plans to them, with checks answered from the map instead of the game.
Run: ppython map_check.py [maps/portroyal.json]. Exit 0 when at least one dinghy has a route that ends in reach."""
import os, sys, json
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths   # noqa: E402

REACH, SHORT, USE_R = 18.0, 16.0, 25.0
f = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'maps', 'portroyal.json')
M = json.load(open(f))
S, X0, Y0, NX, NY = M['step'], M['x0'], M['y0'], M['nx'], M['ny']
Z = {(k % NX, k // NX): v for k, v in enumerate(M['z'])}
E = {tuple(int(v) for v in k.split(',')): b for k, b in M['edges'].items()}
DIRS = [tuple(d) for d in M['dirs']]
WZ = M['waterZ']


def cell(x, y):
    return int(round((x - X0) / S)), int(round((y - Y0) / S))


def is_land(c):
    z = Z.get(c)
    return z is not None and z >= WZ


def open_edge(c1, c2):
    d = (c2[0] - c1[0], c2[1] - c1[1])
    if d in DIRS:
        return bool(E.get(c1, 0) >> DIRS.index(d) & 1)
    d = (-d[0], -d[1])
    if d in DIRS:
        return bool(E.get(c2, 0) >> DIRS.index(d) & 1)
    return False


def ground(pts):
    return [Z.get(cell(x, y)) for x, y, _ in pts]


def legs_ok(pqls):
    out = []
    for p, q, last in pqls:
        L = paths.dist(p, q)
        if last and SHORT:
            if L <= SHORT:
                out.append(True); continue
            fr = (L - SHORT) / L
            q = (p[0] + (q[0] - p[0]) * fr, p[1] + (q[1] - p[1]) * fr, p[2])
            L = paths.dist(p, q)
        n = max(1, int(L / (S / 2)))
        prev, ok = cell(p[0], p[1]), is_land(cell(p[0], p[1]))
        for i in range(1, n + 1):
            c = cell(p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n)
            if c != prev:
                if not (is_land(c) and open_edge(prev, c)):
                    ok = False; break
                prev = c
        out.append(ok)
    return out


start = tuple(M['start'])
c0 = cell(start[0], start[1])
seen, dq = {c0}, deque([c0])
while dq:
    u = dq.popleft()
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            v = (u[0] + di, u[1] + dj)
            if (di or dj) and v not in seen and is_land(v) and open_edge(u, v):
                seen.add(v); dq.append(v)
land = sum(1 for c in Z if is_land(c))
print('map %dx%d step %g: land cells %d, reachable from spawn %s: %d' % (NX, NY, S, land, start[:2], len(seen)))
print('live dinghies:', [(d['doId'], d['pos']) for d in M['live']])
for s in M['spots']:
    best = min((paths.dist((X0 + c[0] * S, Y0 + c[1] * S), s), c) for c in seen)
    print('spot %-22s nearest reachable ground %5.1f ft  z_here=%s  %s' % (
        [round(v) for v in s[:2]], best[0], Z.get(cell(s[0], s[1])),
        'IN REACH' if best[0] <= REACH else ('in use radius' if best[0] <= USE_R else 'out of reach')))
spots = [tuple(s) for s in M['spots']]
g, r, checks = paths.best_route(start, spots, legs_ok, ground, short=SHORT, max_goals=len(spots))
print('best_route: goal=%s length=%s checks=%d' % (g and [round(v) for v in g[:2]],
                                                  r and round(paths.length(start, r)), checks))
print('route:', r and [[round(v) for v in w[:2]] for w in r])
sys.exit(0 if r else 1)
