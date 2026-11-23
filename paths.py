"""Walk routes over open ground, the way a player who knows the town walks to the docks: straight at the goal when
that line is open, else round the buildings. LAUNCH1 walked straight from its spawn at Port Royal towards the nearest
dinghy and hit a building after 75 ft; a player goes round it.
plan_g() is pure geometry (A* on a GRID ft grid, then straightened) and takes the checks as functions, so
test_paths.py runs it offline on a made-up town. live() gives the in-game checks: collision probes on the masks the
pirate's own collisions use (as s_control does), batched so one search step is three collision passes: walls on the
straight line, the ground, then walls again along the ground (a hill between the ends hides a wall from the straight line).
walk_route() walks the best plan with H.walk_to and plans again from where it stopped when a leg gets stuck.
Events: route (one per plan), then the walk-leg events of each leg."""
import heapq, math, os, time

GRID = 20.0             # grid spacing (ft) of the search
MARGIN = 150.0          # the grid covers the box round start and goal plus this much
LINK = 45.0             # the start joins grid points this close; grid points this close (+ the use radius) join the goal
TURN_ARRIVE = 4.0       # a turn point counts as reached within this many ft
LINE_UP = 1.2           # on a deck, how close to a turn point he closes in when the next leg is not open from where he stopped
PLAN_PAD = 1.0          # on a deck, ft of room each side the plan keeps from walls beyond the pirate's width, where there is room
MAX_EXPAND = 4000       # grid points expanded per goal before giving up
FAR, WIDE = 300.0, 3    # a goal farther than FAR ft with no route in the box is planned once more in a box WIDE x the margin
SHIFTS = ((0.0, 0.0), (0.5, 0.0), (0.0, 0.5), (0.5, 0.5))     # grid shifts (in GRID steps) tried in turn while no goal has a route
SLICE = 0.15            # seconds of probing before letting the game draw a frame
MAX_GOALS = 4           # plan to at most this many of the nearest goals (dinghies), keep the shortest route
WATER_Z = -3.0          # ground lower than this is the sea, never walked on (BATTLE1 swam and stuck there). The game swims
                        # only with the ground 5 ft under the sea (MotionFSM: avZ + 5 <= waterZ, the sea at 0): DF1 waded
                        # on ground at -3.9. At 1.0 the Port Royal beach read as sea and IND11 found no way off it
SAMPLE = 4.0            # ground is probed every this many ft along a leg
# DOLL11 (11-21): every Port Royal pitch barrel is on the Fort Charles plateau (z 193-225) and each search ran dry
# 36 ft under it. PATHS_SAMPLE (one run only) measures whether finer land samples find the way up (stairs steeper than
# MAX_RISE per 4 ft, as on the War Galleon's deck) or the plateau is really cut off in the route data.
SAMPLE = float(os.environ.get('PATHS_SAMPLE') or SAMPLE)
DECK_UP = 3.5          # on a ship's deck, arrived also means within this many ft of the goal's height
DECK_SAMPLE = 2.0       # on a ship's deck: the War Galleon's stairs rise 0.78 ft per ft (3.1 ft per 4 ft sample > MAX_RISE)
ESCAPE = {}             # the last best_route_g's pocket escape (frm, to, legs), empty when none was needed
WALKED = []             # where walk_route's last walk that reached its goal began, then each point it stood on
LAST = {}               # how the last plan_g search ended: points expanded, the one nearest the goal, ran dry or out of budget
MAX_RISE, MAX_DROP = 2.5, 10.0      # a step up / a drop between two samples that a pirate cannot walk
FOLLOW = (1.5, 4.0)     # heights (ft) of the wall probes laid on the ground between each two samples
# ISLANDTOUR2 (11-19) landed at the burned north end of Padres Del Fuego (8679, -23440.5): a walled pocket whose
# only way out is a gap past the burned gate a few ft wide, which the 20 ft grid steps over (10 searches ran dry,
# 38-72 points). When no shift and no wide box finds a route, an ESC_GRID ft search within ESC_MARGIN ft walks to
# the point nearest the goal it can reach (out of the pocket), and the normal search goes on from there.
ESC_GRID, ESC_MARGIN, ESC_EXPAND = 4.0, 200.0, 6000
ESC_GAIN = 40.0         # the escape is used only when it ends at least this much nearer the goal than the start
# MAIN21 (11-21) fishRum: from Gunner's door on Padres to the treasure DF_CHEST_1, 876 ft: the escape ended 279 ft
# nearer (the corner of its box) and no 20 ft leg was open there either (21 legs, none open). The escape goes on from
# where it ended, hop after hop, while each hop gains ESC_GAIN ft, ESC_HOPS hops at most.
ESC_HOPS = 5


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def length(a, path):
    tot, p = 0.0, a
    for q in path:
        tot, p = tot + dist(p, q), q
    return tot


def plan_g(a, b, legs_ok, ground, avoid=(), short=0.0, margin=MARGIN, max_expand=MAX_EXPAND, offset=(0.0, 0.0),
           grid=GRID, box=None, partial=False, near_z=False):
    """Generator (yield from; yields 0 = let a frame run every SLICE s of probing) -> (route, checks): route =
    [turn points..., b] for a walk a -> b where every leg passes legs_ok([(p, q, last)]) -> [bool] (last = the leg
    into b, which only has to be open up to `short` ft before b), or None. Straight when that is open; else A* over a
    GRID ft grid of points with ground under them (8 neighbours), then straightened: each turn point skips ahead to
    the farthest later one it has an open leg to. Points are (x, y, z). ground([(x, y, zNear)]) -> [z or None]; a
    ground.floors([(x, y, zNear)]) -> [[z, ...]] (every floor under the point) gives a grid point one node per floor.
    grid: the spacing; box: limit the grid to this many ft round a (else the box round a and b); partial: with no
    route, return the route to the point nearest b that was reached instead of None; near_z: nearest counts the height
    too (boats 05:39 11-21: on the War Galleon the point nearest the wheel on the map was in the hold 27 ft under it)."""
    GRID = grid
    memo, n, t = {}, [0], [time.time()]

    def key(pql):
        p, q, last = pql
        return (round(p[0], 1), round(p[1], 1), round(p[2], 1), round(q[0], 1), round(q[1], 1), round(q[2], 1), last)

    def check(pqls):
        need = [x for x in pqls if key(x) not in memo]
        if need:
            n[0] += len(need)
            for x, r in zip(need, legs_ok(need)):
                memo[key(x)] = bool(r)
        return [memo[key(x)] for x in pqls]

    def slice_up():
        # the next slice starts when the planner is back after the frame (t[0] is reset AFTER each yield): reset
        # before it, the frame's own length counted against the slice, and a 5 fps body (0.2 s frames) got a handful of
        # probes a frame: pbots run 4, 4333 probes in 161 s against 93 in 0.2 s in a 30 fps game
        return time.time() - t[0] > SLICE

    LAST.clear()
    if check([(a, b, True)])[0]:
        return [b], n[0]
    # the grid's lines run through the goal: TALK1 (11-16) planned no route from the mansion yard to Darby, who is
    # reached only straight up the narrow way into his booth; a grid laid from the start put its lines 10 ft either
    # side of that way (DF1: from a start whose grid lined up with him, the same search found it at once)
    if box is None:
        x0 = b[0] - math.ceil((b[0] - min(a[0], b[0]) + margin) / GRID) * GRID + offset[0]
        y0 = b[1] - math.ceil((b[1] - min(a[1], b[1]) + margin) / GRID) * GRID + offset[1]
        nx = int((max(a[0], b[0]) + margin - x0) / GRID) + 1
        ny = int((max(a[1], b[1]) + margin - y0) / GRID) + 1
    else:
        x0, y0 = a[0] - box + offset[0], a[1] - box + offset[1]
        nx = ny = int(2 * box / GRID) + 1
    ok = {(i, j) for i in range(nx) for j in range(ny)
          if not any(dist((x0 + i * GRID, y0 + j * GRID), v) < GRID for v in avoid)}
    S, G = 's', 'g'
    pt, cell, seen = {S: a, G: b}, {}, set()
    floors = getattr(ground, 'floors', None) or (lambda ps: [[] if z is None else [z] for z in ground(ps)])

    def probe(cs, zn):
        """Grid points for the cells cs not probed yet, one per floor under the cell (a bridge deck over the bank under
        it is two), looked for round zn, the height of the point the search comes from: a window round the start's
        height never sees a hill or a bridge 30 ft off it, and one height per cell follows the bank under the deck."""
        cs = [c for c in cs if c in ok and c not in seen]
        seen.update(cs)
        for c, zs in zip(cs, floors([(x0 + c[0] * GRID, y0 + c[1] * GRID, zn) for c in cs]) if cs else ()):
            for k, z in enumerate(z for z in zs if z >= WATER_Z):
                pt[c + (k,)] = (x0 + c[0] * GRID, y0 + c[1] * GRID, z)
                cell.setdefault(c, []).append(c + (k,))

    probe([(i, j) for i, j in ok if dist(a, (x0 + i * GRID, y0 + j * GRID)) <= LINK], a[2])
    near_a = [u for us in cell.values() for u in us if dist(a, pt[u]) <= LINK]
    yield 0
    t[0] = time.time()

    def nbrs(u):
        if u == S:
            out = [(v, False) for v in near_a]
        else:
            i, j = u[:2]
            probe([(i + di, j + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj], pt[u][2])
            out = [(v, False) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj
                   for v in cell.get((i + di, j + dj), ())]
        if dist(pt[u], b) <= LINK + short:
            out.append((G, True))
        return out

    g, parent, closed, heap, tie = {S: 0.0}, {S: None}, set(), [(dist(a, b), 0.0, 0, S)], 0
    start_legs = None

    def left(p):
        return math.hypot(dist(p, b), p[2] - b[2]) if near_z else dist(p, b)

    nearest = [S, left(a)]
    while heap and len(closed) < max_expand:
        f, gc, _, u = heapq.heappop(heap)
        if u in closed:
            continue
        closed.add(u)
        if left(pt[u]) < nearest[1]:
            nearest[:] = [u, left(pt[u])]
        if u == G:
            break
        nb = [(v, last) for v, last in nbrs(u) if v not in closed]
        rs = check([(pt[u], pt[v], last) for v, last in nb])
        if u == S:      # boats 05:06 11-21: the Frigate's wheel search ran dry after the start alone; say why
            start_legs = [len(nb), sum(1 for r in rs if r), len(cell)]
        for (v, last), r in zip(nb, rs):
            ng = gc + dist(pt[u], pt[v])
            if r and ng < g.get(v, 1e18):
                g[v], parent[v], tie = ng, u, tie + 1
                heapq.heappush(heap, (ng + dist(pt[v], b), ng, tie, v))
        if slice_up():
            yield 0
            t[0] = time.time()
    LAST.update(expanded=len(closed), nearest=[round(v, 1) for v in pt[nearest[0]]], nearestLeft=round(nearest[1], 1),
                dry=not heap, startLegs=start_legs)     # [legs from the start, open ones, grid cells with floor]
    if G not in closed:
        if not partial or nearest[0] == S:
            return None, n[0]
    reached = G in closed
    chain, u = [], (G if reached else nearest[0])
    while u is not None:
        chain.append(pt[u])
        u = parent[u]
    chain.reverse()
    out, k = [], 0
    while k < len(chain) - 1:
        far = list(range(len(chain) - 1, k + 1, -1))
        res = check([(chain[k], chain[m], reached and m == len(chain) - 1) for m in far])
        k = next((m for m, r in zip(far, res) if r), k + 1)   # (far is empty for the last step: k + 1)
        out.append(chain[k])
        if slice_up():
            yield 0
            t[0] = time.time()
    return out, n[0]


def best_route_g(a, goals, legs_ok, ground, avoid=(), short=0.0, max_goals=MAX_GOALS, escape=ESC_HOPS, top=True):
    """Generator (yield from) -> (goal, route, checks) for the goal with the shortest route, trying the nearest
    max_goals by straight line and stopping once no farther one could beat the best; (None, None, checks) when none
    has a route. escape: the pocket escape hops left (0 / False = none)."""
    best, checks = (None, None), 0
    # IND6 from the beach by the Port Royal docks (523, 101) to Darby's: the grid lines fell either side of a narrow way
    # off the beach and the search ran dry at (266, 37); the same search on a grid shifted 10 ft found 908-949 ft
    # routes. When no goal has a route, the grid is shifted half a step (SHIFTS) and searched again.
    # IND4 from the east bank to the governor's hill, 1020 ft: everything open inside the box was searched and none of
    # it led there; the way round leaves the box. When no shift finds a route, the goals farther than FAR get one more
    # search in a box (and budget) WIDE times as big. Only then: a dinghy out on the water is skipped, not searched wide.
    ESCAPE.clear() if top else None
    for wide, s in [(False, s) for s in SHIFTS] + [(True, (0.0, 0.0))]:
        for g in sorted(goals, key=lambda g: dist(a, g))[:max_goals]:
            if best[1] is not None and length(a, best[1]) <= dist(a, g):
                break
            if wide and dist(a, g) <= FAR:
                continue
            r, c = yield from plan_g(a, g, legs_ok, ground, avoid, short, WIDE * MARGIN if wide else MARGIN,
                                     WIDE * MAX_EXPAND if wide else MAX_EXPAND, (s[0] * GRID, s[1] * GRID))
            checks += c
            if r is not None and (best[1] is None or length(a, r) < length(a, best[1])):
                best = (g, r)
        if best[1] is not None:
            break
    if best[1] is None and goals and escape:
        g0 = min(goals, key=lambda g: dist(a, g))
        e, c = yield from plan_g(a, g0, legs_ok, ground, avoid, short, 0.0, ESC_EXPAND, (0.0, 0.0),
                                 ESC_GRID, ESC_MARGIN, True)
        checks += c
        if e and dist(e[-1], g0) < 0.1:         # the goal was inside the escape's box
            ESCAPE.update(frm=[round(v, 1) for v in a], to=[round(v, 1) for v in e[-1]], legs=len(e),
                          hops=ESCAPE.get('hops', 0) + 1)
            return g0, e, checks
        if e and dist(e[-1], g0) <= dist(a, g0) - ESC_GAIN:
            g, r, c = yield from best_route_g(e[-1], goals, legs_ok, ground, avoid, short, max_goals, int(escape) - 1,
                                              False)
            checks += c
            if r is not None:
                ESCAPE.update(frm=[round(v, 1) for v in a], to=[round(v, 1) for v in e[-1]], legs=len(e),
                              hops=ESCAPE.get('hops', 0) + 1)
                return g, e + r, checks
    return best[0], best[1], checks


def run_now(gen):
    """Drive a *_g generator to the end without frames (offline tests) -> its return value."""
    while True:
        try:
            next(gen)
        except StopIteration as e:
            return e.value


def plan(a, b, legs_ok, ground, avoid=(), short=0.0):
    return run_now(plan_g(a, b, legs_ok, ground, avoid, short))


def best_route(a, goals, legs_ok, ground, avoid=(), short=0.0, max_goals=MAX_GOALS):
    return run_now(best_route_g(a, goals, legs_ok, ground, avoid, short, max_goals))


def live(H, short=0.0, follow=None, ref=None):
    """(legs_ok, ground) for plan_g(), in render space, from collision probes. The last leg is checked only up to
    `short` ft before the goal (the dinghy itself is solid and sits on the water). follow: the ground-following probe
    heights (FOLLOW; () = none). ref: plan in this node's frame instead (a ship's deck, which bobs)."""
    follow = FOLLOW if follow is None else follow
    from panda3d.core import BitMask32, CollisionPlane, Point3
    from otp.otpbase import OTPGlobals
    from s_control import _hits
    R = H.render
    F = R if ref is None else ref
    # LIVE-every-13 (11-21 06:35): aboard, a ship's real decks and stairs are on PiratesGlobals.ShipFloorBitmask (bit 7;
    # the game swaps the pirate's floor ray to it), and the only FloorBitmask solid is the hull's flat collision_deck
    # plane at main-deck height, unstashed while the pirate is aboard. Probing FloorBitmask alone, the planner saw one
    # endless main deck, routed under the cabin stairs and never reached the War Galleon's wheel. On a deck: both
    # masks, planes skipped, and ground every DECK_SAMPLE ft so the steep stairs read as walkable.
    floor_mask = OTPGlobals.FloorBitmask if ref is None else OTPGlobals.FloorBitmask | BitMask32.bit(7)
    sample = SAMPLE if ref is None else DECK_SAMPLE

    def P(x, y, z):
        """A point in F's frame -> render, where the probes run (one collision pass sees the ship where it is now)."""
        return Point3(x, y, z) if ref is None else R.getRelativePoint(F, Point3(x, y, z))

    def k3(p):
        return round(p[0], 1), round(p[1], 1), round(p[2], 1)

    def floors(pts):
        """Every floor under each (x, y, zNear), low to high: [[z, ...]]; [] = no floor within 30 ft of zNear."""
        segs, keys = [], []
        for x, y, zn in pts:
            top = P(x, y, zn + 30)
            segs.append((top, P(x, y, zn - 30)))
            keys.append(k3(top))
        found = {}
        for e in _hits(H, segs, floor_mask):
            if ref is not None and type(e.getInto()) is CollisionPlane:     # not isinstance: a polygon is a plane too
                continue
            found.setdefault(k3(e.getFrom().getPointA()), []).append(e.getSurfacePoint(F)[2])
        return [sorted(found.get(k, ())) for k in keys]

    def ground(pts):
        return [min(zs, key=lambda z: abs(z - p[2])) if zs else None for p, zs in zip(pts, floors(pts))]

    ground.floors = floors

    def hit_legs(segs, owner):
        """The leg indexes (owner maps a segment's end points to them) with a segment in a wall: one collision pass."""
        out = set()
        for e in _hits(H, segs, OTPGlobals.WallBitmask) if segs else ():
            s = e.getFrom()
            out.update(owner.get(k3(s.getPointA()) + k3(s.getPointB()), ()))
        return out

    def widths():
        w = 1.2 + legs_ok.pad
        return (-1.2, 0.0, 1.2) if w <= 1.2 else (-w, -1.2, 0.0, 1.2, w)

    def legs_ok(pqls):
        res, legs, segs, owner = [True] * len(pqls), [], [], {}
        for idx, (p, q, last) in enumerate(pqls):
            L = dist(p, q)
            if last and short:
                if L <= short:
                    continue
                f = (L - short) / L
                q = (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f, p[2])
                L = dist(p, q)
            if L < 0.5:
                # boats 07:40 11-21: on a deck, a leg straight up from under the Frigate's wheel deck to the wheel (9 ft,
                # no length on the map) read as open, so the plan stood him under it; up or down more than a step is shut
                if ref is not None and abs(q[2] - p[2]) > MAX_RISE:
                    res[idx] = False
                continue
            legs.append((idx, p, q, L))
            sx, sy = -(q[1] - p[1]) / L, (q[0] - p[0]) / L
            for h in (1.5, 4.0):                    # knee and chest height, the pirate's width
                for o in widths():
                    A = P(p[0] + sx * o, p[1] + sy * o, p[2] + h)
                    B = P(q[0] + sx * o, q[1] + sy * o, q[2] + h)
                    segs.append((A, B))
                    owner.setdefault(k3(A) + k3(B), []).append(idx)
        for i in hit_legs(segs, owner):
            res[i] = False
        samples, spans = [], []
        for idx, p, q, L in legs:
            if not res[idx]:
                continue
            m = max(1, int(L / sample))
            spans.append((idx, len(samples), m + 1))
            samples += [(p[0] + (q[0] - p[0]) * i / m, p[1] + (q[1] - p[1]) * i / m, p[2] + (q[2] - p[2]) * i / m)
                        for i in range(m + 1)]
        zs = ground(samples) if samples else []
        segs, owner = [], {}
        for idx, s0, cnt in spans:
            prev = None
            for z in zs[s0:s0 + cnt]:
                if z is None or z < WATER_Z or (prev is not None and (z - prev > MAX_RISE or prev - z > MAX_DROP)):
                    res[idx] = False
                    break
                prev = z
            else:
                # IND10 at Port Royal, 540 ft to Darby: the ground rises to 15.8 ft in the middle and the line between the
                # two ends passed 5 ft under it, so the leg looked open and the bot got stuck three times on the same
                # buildings. The same knee and chest probes, laid on the ground between each two samples, see them.
                (px, py, _), (qx, qy, _) = samples[s0], samples[s0 + cnt - 1]
                L = dist((px, py), (qx, qy))
                sx, sy = -(qy - py) / L, (qx - px) / L
                for i in range(cnt - 1):
                    (x0, y0, _), (x1, y1, _) = samples[s0 + i], samples[s0 + i + 1]
                    for h in follow:
                        for o in widths():
                            A = P(x0 + sx * o, y0 + sy * o, zs[s0 + i] + h)
                            B = P(x1 + sx * o, y1 + sy * o, zs[s0 + i + 1] + h)
                            segs.append((A, B))
                            owner.setdefault(k3(A) + k3(B), []).append(idx)
        for i in hit_legs(segs, owner):
            res[i] = False
        return res

    legs_ok.pad = 0.0       # extra room each side of the pirate's width the legs must have (walk_room plans with PLAN_PAD)
    return legs_ok, ground


SHORE_R = 60.0          # ft: a goal with no floor (a ship on the water) is walked to the nearest floor this close to it
SHORE_STEP = 2.0        # ft between the rings looked at round such a goal
SHORE_IN = 3.0          # ft: the shore point is pulled this far back onto the floor from its edge


def land_goal(b, ground, toward=None, max_r=SHORE_R, step=SHORE_STEP):
    """(point, r): b itself (r 0) when there is walkable floor under it; else the floor point nearest b, looked for on
    rings round b, pulled SHORE_IN ft back from the edge, the one nearest `toward` (the start) on the first ring with
    floor; (None, None) when there is none within max_r. TUT15/TUT16: the bot aimed at Bo Beck's boat, which floats
    22 ft past the dock end; every leg into it ran over the sea, so the search always ran dry ('path null')."""
    z = ground([b])[0]
    if z is not None and z >= WATER_Z:
        return (b[0], b[1], z), 0.0
    r = step
    while r <= max_r + 1e-6:
        n = max(8, int(2 * math.pi * r / step))
        dirs = [(math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n)) for k in range(n)]
        zs = ground([(b[0] + r * c, b[1] + r * s, b[2]) for c, s in dirs])
        hits = [(d, z) for d, z in zip(dirs, zs) if z is not None and z >= WATER_Z]
        if hits:
            ins = ground([(b[0] + (r + SHORE_IN) * c, b[1] + (r + SHORE_IN) * s, z) for (c, s), z in hits])
            pts = []
            for ((c, s), z), zi in zip(hits, ins):
                if zi is not None and zi >= WATER_Z and abs(zi - z) <= MAX_RISE:
                    pts.append((b[0] + (r + SHORE_IN) * c, b[1] + (r + SHORE_IN) * s, zi))
                else:
                    pts.append((b[0] + r * c, b[1] + r * s, z))
            ref = toward or b
            return min(pts, key=lambda p: dist(p, ref)), r
        r += step
    return None, None


SHORE_DEPTH = 12.0      # ft past the first ring with floor that shore goals are still looked for
SHORE_CLEAR = 3.0       # ft of floor a shore goal needs on all four sides (a narrow dock's edge point fails this)


def land_goals(b, ground, toward=None, k=MAX_GOALS, max_r=SHORE_R, step=SHORE_STEP):
    """([points], r): like land_goal, but up to k shore goals for walk_route, each with floor SHORE_CLEAR ft on all four
    sides, from the first ring with floor (r) out to SHORE_DEPTH ft past it, nearest b first. Offline on the real
    Rambleshack pier: the dock edge point 23 ft from Bo Beck's boat had no route (the last leg from the 20 ft grid
    slid off the 10 ft wide dock), while points on the dock's middle had one. ([b], 0) when there is floor under b;
    ([], None) when there is none within max_r."""
    p0, r0 = land_goal(b, ground, toward, max_r, step)
    if p0 is None or not r0:
        return ([p0] if p0 is not None else []), r0
    cands = []
    r = r0
    while r <= min(max_r, r0 + SHORE_DEPTH) + 1e-6:
        n = max(8, int(2 * math.pi * r / step))
        pts = [(b[0] + r * math.cos(2 * math.pi * i / n), b[1] + r * math.sin(2 * math.pi * i / n), b[2])
               for i in range(n)]
        zs = ground(pts)
        for p, z in zip(pts, zs):
            if z is None or z < WATER_Z:
                continue
            c = SHORE_CLEAR
            side = ground([(p[0] + c, p[1], z), (p[0] - c, p[1], z), (p[0], p[1] + c, z), (p[0], p[1] - c, z)])
            if all(s is not None and s >= WATER_Z and abs(s - z) <= MAX_RISE for s in side):
                cands.append((p[0], p[1], z))
        r += step
    if not cands:
        return [p0], r0
    cands.sort(key=lambda p: dist(p, b))
    out = []
    for p in cands:   # spread them: no two within SHORE_CLEAR*2 of each other
        if all(dist(p, q) > 2 * SHORE_CLEAR for q in out):
            out.append(p)
        if len(out) >= k:
            break
    return out, r0


# PAGES4 (11-20) in the Port Royal tailor: the shop floor is a step below the landing at the door (z 5) and the room
# has no world data waypoints, so the straight walk back to the door stuck on the landing's edge 27 ft short, 25
# times. Inside a building the same probes plan on a ROOM_GRID ft grid within ROOM_BOX ft of the pirate.
ROOM_GRID, ROOM_BOX, ROOM_EXPAND = 3.0, 80.0, 6000


def walk_room(H, goal, arrive, tag='room', tries=3, ref=None):
    """Generator (yield from). walk_route for one goal inside a building: the fine grid, re-planned from where a leg
    stuck. -> True when within `arrive` ft of goal, else False. ref: goal and plan in this node's frame (a ship's
    deck: boats 05:06 11-21, the Frigate bobbed 4 ft while the render-space search probed, and it ran dry at once)."""
    la, R = H.la, (H.render if ref is None else ref)
    legs_ok, ground = live(H, 0.0, ref=ref)
    avoid = []

    def there(p):
        # boats 07:20 11-21 (Frigate 05:06): on a deck, 5 ft from the wheel on the map is not there when it is 9 ft
        # below, under the wheel deck's edge; walk_to's arrive is horizontal only
        return dist(p[:2], goal[:2]) <= arrive and (ref is None or abs(p[2] - goal[2]) <= DECK_UP)

    for k in range(tries):
        p = la.getPos(R)
        a = (p[0], p[1], p[2])
        if there(a):
            return True
        t0 = time.time()
        # partial: with no way all the way (the door's own frame may read as wall), as near as the floor goes; the
        # caller's straight walk does the last few ft
        # boats 11-21 (Frigate 07:41): on a deck the shortest plan hugged the Frigate's side-stair handrail 0.1 ft off,
        # so any drift off the line shut the stairs. Plan with PLAN_PAD ft of room first, the bare width if that does not
        # go all the way (a partial plan ends short of the goal).
        for legs_ok.pad in ((PLAN_PAD, 0.0) if ref is not None else (0.0,)):
            r, checks = yield from plan_g(a, goal, legs_ok, ground, avoid, 0.0, 0.0, ROOM_EXPAND, (0.0, 0.0),
                                          ROOM_GRID, ROOM_BOX, True, ref is not None)
            if r and dist(r[-1], goal) < 0.1 and abs(r[-1][2] - goal[2]) < 0.1:
                break
        pad, legs_ok.pad = legs_ok.pad, 0.0
        H.ev('route', tag=tag, room=True, attempt=k + 1, pad=pad, frm=[round(v, 1) for v in a],
             goal=[round(v, 1) for v in goal], path=[[round(v, 1) for v in w] for w in r] if r else None,
             length=round(length(a, r), 1) if r else None, checks=checks, secs=round(time.time() - t0, 2),
             **({} if r else {'search': dict(LAST)}))
        if r is None:
            return False
        for i, w in enumerate(r):
            last = i == len(r) - 1
            ok = yield from H.walk_to(w, ref=ref, arrive=arrive if last else TURN_ARRIVE,
                                      tag='%s %s' % (tag, 'goal' if last else 'turn %d' % (i + 1)))
            if ok and not last and ref is not None:
                # boats 11-21 (Frigate 07:41): a turn point counts as reached within TURN_ARRIVE ft, and at the foot of
                # the Frigate's side stairs that stopped him on the far side of the stairs' own side wall (the channel
                # is x 22.4-33.6, the turn point 2.6 ft inside it), so he walked up beside the stairs, under them, and
                # stuck 3 times. When the next leg is not open from where he really stands, close in on the turn point.
                p = la.getPos(R)
                if not legs_ok([((p[0], p[1], p[2]), r[i + 1], i + 1 == len(r) - 1)])[0]:
                    H.ev('route-line-up', tag=tag, at=[round(v, 1) for v in p], turn=[round(v, 1) for v in w])
                    ok = yield from H.walk_to(w, ref=ref, arrive=LINE_UP, tag='%s line up %d' % (tag, i + 1))
            if not ok:
                if not last:
                    avoid.append(w)
                break
        else:
            p = la.getPos(R)
            if there((p[0], p[1], p[2])):      # every leg walked can still leave him under the deck he planned onto
                return True
    p = la.getPos(R)
    return there((p[0], p[1], p[2]))


def walk_route(H, goals, arrive, short=0.0, tag='route', tries=3, max_goals=MAX_GOALS):
    """Generator (yield from). Walk (held keys, H.walk_to) to within `arrive` ft of the goal (render points) with the
    shortest open route (planning to the nearest max_goals goals); when a leg gets stuck, plan again from where the
    pirate stopped, never through that turn point again. -> the goal reached, or None."""
    la, R = H.la, H.render
    legs_ok, ground = live(H, short)
    avoid = []
    p = la.getPos(R)
    walked = [(p[0], p[1], p[2])]
    for k in range(tries):
        p = la.getPos(R)
        a = (p[0], p[1], p[2])
        near = [g for g in goals if dist(a, g) <= arrive]
        if near:
            WALKED[:] = walked
            return near[0]
        t0 = time.time()
        g, r, checks = yield from best_route_g(a, goals, legs_ok, ground, avoid, short, max_goals)
        H.ev('route', tag=tag, attempt=k + 1, frm=[round(v, 1) for v in a],
             goal=[round(v, 1) for v in g] if g else None,
             path=[[round(v, 1) for v in w] for w in r] if r else None,
             length=round(length(a, r), 1) if r else None, checks=checks, secs=round(time.time() - t0, 2),
             **({} if r else {'search': dict(LAST)}), **({'escape': dict(ESCAPE)} if ESCAPE else {}))
        if r is None:
            return None
        for i, w in enumerate(r):
            last = i == len(r) - 1
            # a player stops once there. IND7 (arrive 110 ft) was 47 ft from Darby after the first turn point, walked on
            # to a turn point on Darby himself and stuck 6 ft from him, inside the 30 ft where the game drops the beam
            if i and dist(la.getPos(R), g) <= arrive:
                WALKED[:] = walked
                return g
            ok = yield from H.walk_to(w, arrive=arrive if last else TURN_ARRIVE,
                                      tag='%s %s' % (tag, 'goal' if last else 'turn %d' % (i + 1)))
            q = la.getPos(R)
            walked.append((q[0], q[1], q[2]))
            if not ok:
                if not last:
                    avoid.append(w)
                break
        else:
            WALKED[:] = walked
            return g
    p = la.getPos(R)
    near = [g for g in goals if dist((p[0], p[1]), g) <= arrive]
    return near[0] if near else None
