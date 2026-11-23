"""CAVE WALK (pir-bot, 11-17, job 8): walk across a jungle or cave area (a DistributedGAInterior) the way a player does:
along the trail, round the walls, and when something blocks the way, back up and take another way.

Why: TUNNEL2 (11-17) failed links 4-11 inside King's Run, Wicked Thicket, Wildwoods and Tortuga Graveyard with 370
stuck events and no game bug. s_story.go() planned routes only on an island (DistributedIsland); in a jungle or cave
it walked a straight line at the target (King's Run: 1,260 ft from the south mouth straight at the north-east one,
through the jungle wall), stuck, sidestepped, jumped in place, gave up, and s_tunnels asked for the same straight
walk again from the same spot (39 + 20 times at one Wildwoods spot).

How: the world data (pirates/leveleditor/worldData/<area>.py, the level editor's own file for that area) has the
spots the designers put on the walkable trail: enemy Movement Nodes (with their 'Node Links' patrol paths), Spawn
Nodes, the 12 Player Spawn Nodes that line the whole trail, Object Spawn Nodes and the portal_interior Locator Nodes
at each mouth. They are the waypoints. A graph joins each one to its nearest ones (and to its patrol links); the
walk takes the shortest chain from the pirate to the target, and every leg of that chain is checked against the
real collision walls and floors first (paths.live: the same knee / chest wall probes and ground probes as the island
routes). A closed leg is dropped and the chain planned again, so the walk only starts on an open route. A leg with
no open way round in the graph gets a short grid search (paths.plan_g) of its own.

Stuck while walking (a tree, a rock, another pirate): back up 1 s (the reverse key), then plan again from where he
stands without that leg. Stuck twice going to the same turn point from about the same spot: that point is left out
from there on. Never a jump in place, never a teleport.

Lines: CAVE-ROUTE (tag, attempt, frm, goal, path, nodes, length, checks, closed, secs), CAVE-BACKUP (tag, la,
to, n), CAVE-NO-ROUTE (why), CAVE-END (reached, left, legs, backups), CAVE-PROBE (job 12: mode own / others, why, own,
others). CAVE-ROUTE also has skipped, probe and ignoredBy. env: CAVE_WALK=0 turns it off (the old straight walk);
CAVE_OWN=0 goes back to job 9's other-area skip.

Job 17 (SMOKE-tunnel8, 11-18): in Murky Hollow every plan to the jungle_a tunnel read path=null (graph+grid, closed
43-48) with mode=own and skipped=0, while the same cave built offline routes from the same spots. The offline route
turns at Spawn Nodes (295,88), (215,-128), (37,-153), (-150,-35): live, a skeleton or bat stands on each, and every
avatar carries a solid 2 ft battle tube on the wall mask (DistributedBattleAvatar.initializeBattleCollisions, tag
objType=COLL_AV). So every leg into those waypoints read closed, and the grid hop round a closed leg fails too, since it
must end on the waypoint the enemy stands on. Enemies move and a player walks past or fights them: the probes now
ignore avatar tubes (CAVE-ROUTE avatars = how many hits were ignored). A walk that bumps one still backs up and plans
again. A plan with no route logs hitBy: the solids that closed its legs. env: CAVE_AV_SOLID=1 counts avatars again.

Job 17b (SMOKE-tunnel9, 11-18): King's Run's 6 turns all arrived, and the last leg reached the tunnel to the cave. On its
floor the game takes the pirate (DistributedGATunnel.__handleOnFloor: motion off, TFInTunnel, EnterTunnel walks him 40
ft and fades out, the loading screen, then LeaveTunnel walks him 30 ft into the next area). The walker does not count
EnterTunnel / LeaveTunnel as the game's turn (walker.NOWALK), so it read the trip as stuck: 2 stuck tries (la jumped 557
ft in one beat, to (1021, 670, 2)), a timeout, a CAVE-BACKUP (the reverse key held during LeaveTunnel), then a replan
over King's Run's node, already unloaded: AssertionError !a.is_empty() in _Own.isAncestorOf. Now: every leg and every
replan first asks in_tunnel() (EnterTunnel / LeaveTunnel / TFInTunnel / parent is the tunnel). When the game has him,
the leg is let go (every key up), CAVE-TUNNEL is logged and nothing is pressed until he is in LandRoam in an area that
is not the tunnel (CAVE-TUNNEL-END secs, to); walk() returns 'area', like any tunnel taken on the way. The probes skip
empty nodes, and an own area that was unloaded is looked up again before the next plan (CAVE-PROBE why='own area node
gone').

Job 23 (SMOKE-tunnel10, 11-19): the cave walker failed 3 runs in a row (tunnel8 Murky Hollow, tunnel9, tunnel10 Royal
Caverns: CAVE-NO-ROUTE to both goals, closed 28/39 and 15/24). hitBy named floors and enemy bubbles: Grid-693Node/
Collision, group47/floor_interior, CaveA/floor_interior, ceiling collision_floor, Sergeant/AggroSphere. The probe took
every hit on the wall mask as a wall, and the cave floors carry the wall bit too (Royal Caverns' floor polySurface17:
mask 7 = wall+floor+camera, normal z 1.00, offline job23/diag_hits2.py), so knee probes over a sloped cave floor read
closed. Now a whitelist (wall_hit): a hit blocks only when its node has the wall mask, it is tangible, its face is
sideways (|normal z| < CAVE_WALL_NZ, 0.5) and it is not an inverse sphere, a trigger / AggroSphere, or under a Grid-<n>Node (a
prop the game files under a grid zone; CAVE_GRID_SOLID=1 counts their sideways faces). CAVE-ROUTE notWalls = the hits
let through, by reason. env: CAVE_WHITELIST=0 goes back to every wall-mask hit."""
import os, re, sys, math, time, heapq

NODE_TYPES = ('Movement Node', 'Spawn Node', 'Player Spawn Node', 'Object Spawn Node', 'Locator Node',
              'Dormant NPC Spawn Node', 'Cutscene Origin Node')
NEAR_K = 8              # each waypoint joins this many of its nearest waypoints ...
NEAR_R = 220.0          # ... that are this close (ft)
ATTACH_K = 6            # the pirate and the target join this many of the nearest waypoints
ATTACH_R = 320.0        # ... within this many ft
LINK_BONUS = 0.9        # a designer's patrol link costs 0.9 of its length (it is a known walkable way)
ROUNDS = 40             # graph re-plans (closed legs dropped) before the grid search fills the gaps
TURN_ARRIVE = 4.0       # a turn point counts as reached within this many ft
BACK_SECS = 1.0         # backing up after a stuck leg (reverse key)
REPLANS = 6             # plans from where he stands, per walk
SAME_SPOT = 10.0        # ft: stuck twice this close, going to the same turn point = leave that point out from here
HOP_MARGIN = 60.0       # the grid search for one closed leg covers its box plus this much
HOP_EXPAND = 2500
STUCK_R = 4.0           # ft: once he has stuck somewhere, no leg is planned this close to that spot (MAIN48)
CACHE = {}              # area uid -> (nodes {id: (x, y, z)}, links [(id, id)], file) or None
INDEX = {}              # area uid -> world data file name
KEY_SRC = 'harness-bot'
AV_TAG, AV_VAL = 'objType', '1'     # PiratesGlobals.COLL_AV on every avatar's battle tube (job 17)
TUNNEL_STATES = ('EnterTunnel', 'LeaveTunnel')
TUNNEL_WAIT = 120.0     # s: the longest a tunnel trip (walk in, load, walk out) is waited for
TUNNEL_SETTLE = 1.0     # s: out of the tunnel this long before the walk goes on


def _empty(np_):
    try:
        return np_ is None or np_.isEmpty()
    except Exception:
        return True


def in_tunnel(H):
    """Job 17b: the game has the pirate in a tunnel trip -> 'EnterTunnel' / 'LeaveTunnel' / 'TFInTunnel' / 'tunnel-parent',
    else None. Never imports a game module: PiratesGlobals is read only when the game already loaded it."""
    try:
        gs = H.la.getGameState()
    except Exception:
        gs = None
    if gs in TUNNEL_STATES:
        return gs
    PG = sys.modules.get('pirates.piratesbase.PiratesGlobals')
    try:
        if PG is not None and H.la.testTeleportFlag(PG.TFInTunnel):
            return 'TFInTunnel'
    except Exception:
        pass
    try:
        a = H.area()
        if a and a[0] == 'DistributedGATunnel':
            return 'tunnel-parent'
    except Exception:
        pass
    return None


def ride_tunnel(H, tag, area0, how):
    """Generator, job 17b: the game is taking him through a tunnel. Press nothing (the caller has let every key go) until
    he is out: LandRoam, not in_tunnel, in an area, for TUNNEL_SETTLE s. -> True when out, False after TUNNEL_WAIT."""
    t0 = time.time()
    try:
        gs = H.la.getGameState()
    except Exception:
        gs = None
    H.ev('CAVE-TUNNEL', tag=tag, how=how, gs=gs, la=H.P(H.la), frm=area0)
    out_since, done = None, False
    while time.time() - t0 < TUNNEL_WAIT:
        try:
            gs = H.la.getGameState()
        except Exception:
            gs = None
        if gs == 'LandRoam' and in_tunnel(H) is None and H.area() is not None:
            out_since = out_since or time.time()
            if time.time() - out_since >= TUNNEL_SETTLE:
                done = True
                break
        else:
            out_since = None
        yield 0.1
    H.ev('CAVE-TUNNEL-END', tag=tag, done=done, secs=round(time.time() - t0, 1), to=H.area(), gs=gs, la=H.P(H.la))
    return done


def _leg(H, w, **kw):
    """Generator, job 17b: H.walk_to, let go (every key up: walk_to's finally) the moment a tunnel trip starts.
    -> (walk_to's result, None) or (None, in_tunnel's reason)."""
    g = H.walk_to(w, **kw)
    try:
        y = next(g)
        while True:
            how = in_tunnel(H)
            if how:
                return None, how
            v = yield y
            y = g.send(v)
    except StopIteration as e:
        return e.value, None
    finally:
        g.close()


def _is_avatar(np_):
    """An avatar's battle tube (an enemy, an NPC, another pirate): tag objType = COLL_AV on it or above it."""
    if os.environ.get('CAVE_AV_SOLID', '0') == '1':
        return False
    try:
        return np_.getNetTag(AV_TAG) == AV_VAL
    except Exception:
        return False


def _hit_name(np_):
    try:
        par = np_.getParent()
        return '%s/%s' % (par.getName() if not par.isEmpty() else '', np_.getName())
    except Exception:
        return '?'


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------- world data (pure but for the file reads)

def worlddata_dir():
    try:
        import pirates.leveleditor.worldData as W
        return os.path.dirname(os.path.abspath(W.__file__))
    except Exception:
        return os.environ.get('CAVE_WORLDDATA',
                              'C:/PiratesOnline/pirates-online-classic/pirates/leveleditor/worldData')


AREA_RE = re.compile(r"'([0-9.]+[A-Za-z]+)':\s*\{\s*'Type':\s*'(?:Island Game Area|Cave|Jungle|Swamp)")


def find_file(uid, wd=None):
    """The world data file (name, no .py) whose first object is area `uid`: files with _area_ / cave / jungle /
    swamp in their name first, then all of them. -> name or None."""
    if uid in INDEX:
        return INDEX[uid]
    wd = wd or worlddata_dir()
    try:
        names = sorted(n for n in os.listdir(wd) if n.endswith('.py') and not n.startswith('__'))
    except Exception:
        return None
    first = [n for n in names if any(k in n for k in ('_area_', 'cave', 'jungle', 'swamp'))]
    for n in first + [n for n in names if n not in first]:
        try:
            with open(os.path.join(wd, n), encoding='latin-1') as f:
                head = f.read(200000)
        except Exception:
            continue
        m = AREA_RE.search(head)
        if m:
            INDEX.setdefault(m.group(1), n[:-3])
            if m.group(1) == uid:
                return n[:-3]
    return None


def nodes_of(struct):
    """Pure: (area uid, {id: (x, y, z)} waypoints in the area's own frame, [(id, id)] patrol / interact links between
    two of them) from a world data objectStruct. Only the area's own objects (their Pos is in the area frame)."""
    uid, area = next(iter(struct['Objects'].items()))
    nodes = {}
    for k, o in (area.get('Objects') or {}).items():
        if o.get('Type') in NODE_TYPES and 'Pos' in o:
            p = o['Pos']
            nodes[k] = (float(p[0]), float(p[1]), float(p[2]))
    links = []
    for key in ('Node Links', 'Interact Links'):
        for l in struct.get(key) or ():
            if len(l) >= 2 and l[0] in nodes and l[1] in nodes and l[0] != l[1]:
                links.append((l[0], l[1]))
    return uid, nodes, links


def load(uid, wd=None):
    """(nodes, links, file) for area uid from its world data, cached; None when it has no file or no waypoints."""
    if uid in CACHE:
        return CACHE[uid]
    out = None
    name = find_file(uid, wd)
    if name:
        import runpy
        try:
            s = runpy.run_path(os.path.join(wd or worlddata_dir(), name + '.py'))['objectStruct']
            u, nodes, links = nodes_of(s)
            if u == uid and len(nodes) >= 2:
                out = (nodes, links, name)
        except Exception:
            out = None
    CACHE[uid] = out
    return out


# ---------------------------------------------------------------- graph and plan (pure)

def graph(nodes, links, k=NEAR_K, r=NEAR_R):
    """Pure: {id: {id: cost}}: each waypoint to its k nearest within r ft, both ways, plus every link (LINK_BONUS)."""
    ids = list(nodes)
    adj = {i: {} for i in ids}
    for i in ids:
        near = sorted((dist(nodes[i], nodes[j]), j) for j in ids if j != i)
        for d, j in near[:k]:
            if d <= r:
                adj[i][j] = adj[j][i] = d
    for i, j in links:
        d = dist(nodes[i], nodes[j]) * LINK_BONUS
        adj[i][j] = adj[j][i] = min(adj[i].get(j, 1e18), d)
    return adj


def lkey(p, q):
    return (round(p[0], 1), round(p[1], 1), round(p[2], 1), round(q[0], 1), round(q[1], 1), round(q[2], 1))


def chain(a, b, nodes, adj, closed, skip=()):
    """Pure: the cheapest [point, ...] from a to b (a not included, b last) over the waypoints, joining a and b to their
    ATTACH_K nearest waypoints (and to each other), never over a leg in `closed` (lkey set) or through a waypoint in
    skip. -> ([points], [ids]) or (None, None)."""
    A, B = '@a', '@b'
    pts = dict(nodes)
    pts[A], pts[B] = a, b
    ok = [i for i in nodes if i not in skip]

    def att(p):
        return [i for d, i in sorted((dist(p, nodes[i]), i) for i in ok)[:ATTACH_K] if d <= ATTACH_R]

    edges = {A: {i: dist(a, nodes[i]) for i in att(a)}}
    toB = {i: dist(nodes[i], b) for i in att(b)}
    edges[A][B] = dist(a, b)
    g, par, heap, done = {A: 0.0}, {A: None}, [(dist(a, b), 0.0, A)], set()
    while heap:
        f, c, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        if u == B:
            break
        out = edges[A] if u == A else dict(adj.get(u, {}))
        if u in toB:
            out[B] = toB[u]
        for v, w in out.items():
            if v in skip or v in done:
                continue
            if lkey(pts[u], pts[v]) in closed:
                continue
            nc = c + w
            if nc < g.get(v, 1e18):
                g[v], par[v] = nc, u
                heapq.heappush(heap, (nc + dist(pts[v], b), nc, v))
    if B not in done:
        return None, None
    ids, u = [], B
    while u is not None:
        ids.append(u)
        u = par[u]
    ids.reverse()
    return [pts[i] for i in ids[1:]], ids[1:-1]


def plan(a, b, nodes, adj, legs_ok, closed=None, skip=(), rounds=ROUNDS):
    """Pure but for legs_ok (paths.live's probe: [(p, q, last)] -> [bool]): the shortest waypoint chain a -> b whose every
    leg is open. Closed legs found are added to `closed` and the chain planned again. -> (route, ids, checks, closed
    legs of the last chain tried (for the grid fallback)) - route None when the graph has no open chain."""
    closed = set() if closed is None else closed
    opened, checks, last = set(), 0, None
    for _ in range(rounds):
        r, ids = chain(a, b, nodes, adj, closed, skip)
        if r is None:
            break
        legs = list(zip([a] + r[:-1], r))
        need = [(p, q) for p, q in legs if lkey(p, q) not in opened]
        res = legs_ok([(p, q, False) for p, q in need]) if need else []
        checks += len(need)
        shut = []
        for (p, q), good in zip(need, res):
            (opened.add if good else closed.add)(lkey(p, q))
            if not good:
                shut.append((p, q))
        last = (r, ids, shut)
        if not shut:
            return r, ids, checks, []
    if last is None:
        return None, None, checks, []
    return None, last[1], checks, last


MOUTH_R = 120.0         # a waypoint this close to a target with no open leg into it is the mouth to walk to first


def avoid_stuck(legs_ok, stuck, closed, r=STUCK_R):
    """Pure but for legs_ok: legs_ok that also shuts every leg in `closed` and every leg passing within r ft of a spot
    he stuck at (stuck: [(spot, turn point)]); a leg that starts that close is shut only when it heads at the spot.
    MAIN48 (11-22, Queen's Nest, visitMary): the planned leg passed 2.4 ft from the corner of col_wall_4 (open to the
    1.2 ft probes), he drifted into the corner and stuck. Each re-plan from where he backed off to drew a new leg past
    the same corner (the grid search and the corner cutting never saw the closed legs) until the straight leg to Mary
    was closed too, which left the graph nothing to try: CAVE-NO-ROUTE, though offline the way round it is open."""
    spots = [s for s, _ in stuck]

    def near(p, q, s):
        dx, dy = q[0] - p[0], q[1] - p[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((s[0] - p[0]) * dx + (s[1] - p[1]) * dy) / L2))
        return dist((p[0] + dx * t, p[1] + dy * t), s)

    def ok(pqls):
        res = list(legs_ok(pqls)) if pqls else []
        for i, (p, q, last) in enumerate(pqls):
            if not res[i]:
                continue
            if lkey(p, q) in closed:
                res[i] = False
                continue
            for s in spots:
                if dist(p, s) <= r:
                    heads = (q[0] - p[0]) * (s[0] - p[0]) + (q[1] - p[1]) * (s[1] - p[1]) > 0
                else:
                    heads = near(p, q, s) <= r
                if heads:
                    res[i] = False
                    break
        return res
    ok.pad = getattr(legs_ok, 'pad', 0.0)
    return ok


def mouth(b, nodes, r=MOUTH_R):
    """Pure: the waypoint nearest b within r ft (the tunnel / door mouth in front of a target inside it), or None."""
    near = min(((dist(p, b), p) for p in nodes.values()), default=None)
    return near[1] if near and near[0] <= r else None


def smooth(a, route, legs_ok):
    """Pure but for legs_ok: skip turn points like a player cutting a corner: from each point go to the farthest later
    point with an open straight leg. -> route."""
    pts = [a] + list(route)
    out, k = [], 0
    while k < len(pts) - 1:
        far = list(range(len(pts) - 1, k + 1, -1))
        res = legs_ok([(pts[k], pts[m], False) for m in far]) if far else []
        k = next((m for m, r in zip(far, res) if r), k + 1)
        out.append(pts[k])
    return out


# ---------------------------------------------------------------- live

def area_points(H, uid, data):
    """The waypoints in render space (the world data is in the area's frame)."""
    nodes, links, name = data
    org = None
    try:
        org = next((o for o in list(H.cr.doId2do.values()) if getattr(o, 'uniqueId', None) == uid and hasattr(o, 'getPos')), None)
    except Exception:
        org = None
    if org is None or getattr(org, 'isEmpty', lambda: False)():
        return dict(nodes)
    from panda3d.core import Point3
    out = {}
    for k, p in nodes.items():
        q = H.render.getRelativePoint(org, Point3(*p))
        out[k] = (q[0], q[1], q[2])
    return out


class _Skip:
    """Stands in for H.la in s_control._hits, which skips any hit under H.la (the pirate himself). This one also skips
    hits under another game area still in the scene. SMOKE-tunnel5 (11-17): back in Murky Hollow from King's Run,
    every plan read 'no open way', but offline Murky Hollow alone routes fine. Offline, King's Run laid over it at
    the same origin closes the same legs (job8/repro_overlay.py). The tunnels are not game areas, so they still count."""

    def __init__(self, la, others):
        self.la, self.others, self.skipped = la, others, 0
        self.avatars, self.hits = 0, {}

    def prune(self):
        self.others = [o for o in self.others if not _empty(o)]
        return True

    def isAncestorOf(self, np_):
        if _empty(np_):
            self.skipped += 1
            return True
        if not _empty(self.la) and self.la.isAncestorOf(np_):
            return True
        if _is_avatar(np_):
            self.avatars += 1
            return True
        if any(not _empty(o) and o.isAncestorOf(np_) for o in self.others):
            self.skipped += 1
            return True
        if getattr(self, 'counting', True):     # job 23: hitBy = wall-pass hits only
            k = _hit_name(np_)
            self.hits[k] = self.hits.get(k, 0) + 1
        return False


WALL_NZ = float(os.environ.get('CAVE_WALL_NZ', '0.5'))   # job 23: a face this flat or flatter is a floor / ceiling
GRID_RE = re.compile(r'^Grid-\d+Node$')
SOFT_RE = re.compile(r'aggro|trigger', re.I)   # not 'sphere': Murky Hollow's rocks are col_rock_caveB_sphere


def wall_why(e, top=None):
    """Job 23, pure on a CollisionEntry: None = a real wall (it blocks), else why it is not one: 'mask', 'intangible',
    'sphere' (an inverse sphere), 'trigger' (AggroSphere / trigger by name), 'grid' or 'flat' (a floor or ceiling face, |normal z| >= WALL_NZ)."""
    from panda3d.core import BitMask32
    try:
        node = e.getIntoNode()
        if (node.getIntoCollideMask() & BitMask32(1)).isZero():
            return 'mask'
        solid = e.getInto()
        if not solid.isTangible():
            return 'intangible'
        if solid.getClassType().getName() == 'CollisionInvSphere':
            return 'sphere'             # an inside-out bubble (a zone), never a wall; a plain sphere is a rock
        np_ = e.getIntoNodePath()
        if SOFT_RE.search(np_.getName() or ''):
            return 'trigger'
        if os.environ.get('CAVE_GRID_SOLID', '0') != '1':
            p = np_
            while not p.isEmpty() and (top is None or p != top):
                if GRID_RE.match(p.getName() or ''):
                    return 'grid'
                p = p.getParent()
        if e.hasSurfaceNormal():
            nz = e.getSurfaceNormal(top if top is not None else np_.getTop()).getZ()
            if abs(nz) >= WALL_NZ:
                return 'flat'
    except Exception:
        return None
    return None


def wall_hits(skip, render):
    """Job 23: s_control._hits with the whitelist on the wall mask: -> hits(H, segs, mask). The floor mask is unchanged.
    skip.notWalls counts the hits let through, by wall_why()."""
    from panda3d.core import CollisionNode, CollisionSegment, CollisionHandlerQueue, CollisionTraverser, BitMask32
    skip.notWalls = {}

    def hits(H, segs, mask):
        R = H.render
        cn = CollisionNode('ctrl-probe')
        for a, b in segs:
            cn.addSolid(CollisionSegment(a, b))
        cn.setFromCollideMask(mask)
        cn.setIntoCollideMask(BitMask32.allOff())
        np_ = R.attachNewNode(cn)
        q = CollisionHandlerQueue()
        t = CollisionTraverser('ctrl-probe')
        t.addCollider(np_, q)
        t.traverse(R)
        np_.removeNode()
        q.sortEntries()
        wall = mask == BitMask32(1)
        skip.counting = wall        # job 23: hitBy = wall-pass hits only (tunnel10's hitBy was mostly floor probes)
        out = []
        for i in range(q.getNumEntries()):
            e = q.getEntry(i)
            if not e.getInto().isTangible():
                continue
            if wall:
                why = wall_why(e, R)
                if why:
                    skip.notWalls[why] = skip.notWalls.get(why, 0) + 1
                    continue
            if H.la.isAncestorOf(e.getIntoNodePath()):
                continue
            out.append(e)
        return out
    return hits


def other_areas(H, uid):
    """The game areas (islands, jungles, caves) in the scene that are not this one, and not stashed: [(name, node)]."""
    try:
        from pirates.world.DistributedGameArea import DistributedGameArea
        objs = list(H.cr.doId2do.values())
    except Exception:
        return []
    areas = [o for o in objs if isinstance(o, DistributedGameArea)]
    here = [o for o in areas if getattr(o, 'uniqueId', None) == uid]
    out = []
    for o in areas:
        try:
            if getattr(o, 'uniqueId', None) == uid or o.isEmpty() or o.isStashed():
                continue
            if any(o.isAncestorOf(h) for h in here if not h.isEmpty()):
                continue          # an area this one sits under (the island over its cave): skipping it would skip all
            out.append((getattr(o, 'name', None) or o.__class__.__name__, o))
        except Exception:
            pass
    return out


class _Own:
    """pir-bot job 12. Stands in for H.la in s_control._hits like _Skip, the other way round: only hits under this
    area's own node count (its terrain, walls, props, and the tunnel connectors the game reparents under it). Any other
    hit is ignored. SMOKE-tunnel6 (11-18): back in Murky Hollow, every plan to the jungle_a tunnel read 'no open way'
    (closed 43-50 legs) with no other game area in doId2do (no CAVE-OTHER-AREAS, skipped=0), so job 9's skip had
    nothing to skip, yet Murky Hollow alone routes from the same spots offline. The foreign solids are not under any
    live game area; this probe does not need to know whose they are. by: ignored hits per top node under render."""

    def __init__(self, la, own, render=None):
        self.la, self.own, self.render, self.skipped, self.by = la, own, render, 0, {}
        self.avatars, self.hits = 0, {}

    def prune(self):
        """Job 17b: drop own nodes that were unloaded. -> False when none is left (the probe must be built again)."""
        self.own = [o for o in self.own if not _empty(o)]
        return bool(self.own)

    def isAncestorOf(self, np_):
        if _empty(np_):
            self.skipped += 1
            return True
        if not _empty(self.la) and self.la.isAncestorOf(np_):
            return True
        if _is_avatar(np_):
            self.avatars += 1
            return True
        if any(not _empty(o) and o.isAncestorOf(np_) for o in self.own):
            if getattr(self, 'counting', True):     # job 23: hitBy = wall-pass hits only
                k = _hit_name(np_)
                self.hits[k] = self.hits.get(k, 0) + 1
            return False
        self.skipped += 1
        try:
            top = np_
            while not top.getParent().isEmpty() and top.getParent() != self.render:
                top = top.getParent()
            k = top.getName() or '?'
        except Exception:
            k = '?'
        self.by[k] = self.by.get(k, 0) + 1
        return True


def own_area(H, uid):
    """This area's node: the game area in doId2do with this uniqueId, else the nearest game area above the pirate
    (the game wrtReparents localAvatar to the area he is in). None: not found (area_probe then uses job 9's skip)."""
    try:
        from pirates.world.DistributedGameArea import DistributedGameArea
        objs = list(H.cr.doId2do.values())
    except Exception:
        return None
    for o in objs:
        try:
            if isinstance(o, DistributedGameArea) and getattr(o, 'uniqueId', None) == uid and not o.isEmpty():
                return o
        except Exception:
            pass
    areas = []
    for o in objs:
        try:
            if isinstance(o, DistributedGameArea) and not o.isEmpty():
                areas.append(o)
        except Exception:
            pass
    try:
        p = H.la.getParent()
        while not p.isEmpty():
            for o in areas:
                if o.node() == p.node():
                    return o
            p = p.getParent()
    except Exception:
        pass
    return None


def area_probe(H, uid, others=None, own=None):
    """paths.live's (legs_ok, ground) for this area. With its own node (job 12): only its own solids count. Without:
    blind to every other game area in the scene (job 9). -> (legs_ok, ground, skip); skip.mode = 'own' / 'others'."""
    import paths
    import types
    if own is not None:
        skip = _Own(H.la, [own], H.render)
        skip.mode = 'own'
    else:
        others = other_areas(H, uid) if others is None else others
        skip = _Skip(H.la, [n for _, n in others])
        skip.mode = 'others'
    skip.notWalls = None
    if os.environ.get('CAVE_WHITELIST', '1') == '0':
        legs_ok, ground = paths.live(types.SimpleNamespace(render=H.render, la=skip), 0.0)
        return legs_ok, ground, skip
    # job 23: paths.live takes s_control._hits by name when it is called; hand it the whitelisted one for this probe only
    import s_control
    old = s_control._hits
    s_control._hits = wall_hits(skip, H.render)
    try:
        legs_ok, ground = paths.live(types.SimpleNamespace(render=H.render, la=skip), 0.0)
    finally:
        s_control._hits = old
    return legs_ok, ground, skip


def back_up(H, tag, secs=BACK_SECS):
    """Generator: hold the reverse key for secs (a player backing off what he walked into), then let go."""
    from direct.showbase.InputStateGlobal import inputState
    p0 = H.P(H.la)
    t0 = time.time()
    try:
        inputState.set('reverse', True, inputSource=KEY_SRC)
        while time.time() - t0 < secs and in_tunnel(H) is None:     # job 17b: never against the game's tunnel walk
            yield 0.02
    finally:
        inputState.set('reverse', False, inputSource=KEY_SRC)
    return p0


def _through(H, tag, area0, how, legs, backups):
    """Generator, job 17b: a tunnel trip started on the way: ride it out, then 'area' (act() plans from the new area)."""
    done = yield from ride_tunnel(H, tag, area0, how)
    if H.area() != area0:
        H.ev('AREA-CHANGED', tag=tag, frm=area0, to=H.area())
    H.ev('CAVE-END', tag=tag, reached='area' if done else 'tunnel', legs=legs, backups=backups)
    return 'area'


def walk(H, target, arrive, tag):
    """Generator: walk to target (render point) inside this jungle / cave. -> True (there), 'area' (a tunnel / door on
    the way took him to another area), False (no open route, or stuck after REPLANS plans), None (no world data for
    this area or CAVE_WALK=0: the caller walks the old way)."""
    import paths
    if os.environ.get('CAVE_WALK', '1') == '0':
        return None
    area0 = H.area()
    uid = area0[1] if area0 else None
    data = load(uid) if uid else None
    if not data:
        H.ev('CAVE-NO-ROUTE', tag=tag, why='no world data waypoints for area %s' % uid)
        return None
    nodes = area_points(H, uid, data)
    adj = graph(nodes, data[1])
    others = other_areas(H, uid)
    own = own_area(H, uid) if os.environ.get('CAVE_OWN', '1') != '0' else None
    legs_ok, ground, skip_ = area_probe(H, uid, others, own)
    why = 'own area node' if own is not None else (
        'CAVE_OWN=0' if os.environ.get('CAVE_OWN', '1') == '0' else 'no own area node found')
    if skip_.mode == 'own':
        lp0 = H.la.getPos(H.render)
        if ground([(lp0[0], lp0[1], lp0[2])])[0] is None:
            # this area's own solids have no floor under his feet: its geometry is not under its node here. Fall back
            legs_ok, ground, skip_ = area_probe(H, uid, others, None)
            why = 'own area has no floor under him'
    H.ev('CAVE-PROBE', tag=tag, here=uid, mode=skip_.mode, why=why,
         own=(getattr(own, 'name', None) or own.getName()) if own is not None else None, others=len(others))
    if others:
        H.ev('CAVE-OTHER-AREAS', tag=tag, here=uid,
             others=[n for n, _ in others][:8], n=len(others))
    b = (target[0], target[1], target[2])
    closed, stuck, backups, legs, skip = set(), [], 0, 0, set()
    R = H.render
    for attempt in range(REPLANS):
        how = in_tunnel(H)
        if how:
            return (yield from _through(H, tag, area0, how, legs, backups))
        if not skip_.prune():
            # job 17b: this area's node was unloaded (tunnel9: King's Run, mid tunnel trip): look it up again
            own = own_area(H, uid) if os.environ.get('CAVE_OWN', '1') != '0' else None
            others = other_areas(H, uid)
            legs_ok, ground, skip_ = area_probe(H, uid, others, own)
            H.ev('CAVE-PROBE', tag=tag, here=uid, mode=skip_.mode, why='own area node gone',
                 own=(getattr(own, 'name', None) or own.getName()) if own is not None else None, others=len(others))
        lp = H.la.getPos(R)
        a = (lp[0], lp[1], lp[2])
        if dist(a, b) <= arrive:
            break
        t0 = time.time()
        lok = avoid_stuck(legs_ok, stuck, closed)
        route, ids, checks, gap = plan(a, b, nodes, adj, lok, closed, skip)
        how, tail = 'graph', []
        m = mouth(b, nodes) if route is None else None
        if m is not None:
            # the target is inside the tunnel / door past the mouth (useTunnel walks to the tunnel floor's centre): no
            # leg into it reads open from the jungle side (the tunnel is its own model: floor and walls end at the seam).
            # Like a player: walk the trail to the mouth (the portal waypoint), then straight in
            r2, ids2, n2, gap2 = plan(a, m, nodes, adj, lok, closed, skip)
            checks += n2
            if r2 is not None:
                route, ids, gap, how, tail = r2, ids2, None, 'graph+mouth', [b]
        if route is None and gap:
            # no open chain: walk the last one tried, with a short grid search round each closed leg of it
            r, gids, shut = gap
            route, how = [], 'graph+grid'
            prev = a
            for q in r:
                if (prev, q) in shut:
                    sub, n = yield from paths.plan_g(prev, q, lok, ground, margin=HOP_MARGIN,
                                                     max_expand=HOP_EXPAND)
                    checks += n
                    if sub is None:
                        route = None
                        break
                    route += sub
                else:
                    route.append(q)
                prev = q
            ids = gids
        elif route is None:
            # MAIN48: no chain left at all (the target has no waypoint near it and the straight leg to it is closed):
            # search the grid round the whole way rather than give up where he stands
            route, n = yield from paths.plan_g(a, b, lok, ground, margin=HOP_MARGIN, max_expand=HOP_EXPAND)
            checks += n
            how, ids = 'grid', []
        if route:
            route = smooth(a, route, lok) + tail
        H.ev('CAVE-ROUTE', tag=tag, attempt=attempt + 1, how=how, frm=[round(v, 1) for v in a],
             goal=[round(v, 1) for v in b], path=[[round(v, 1) for v in w] for w in route] if route else None,
             nodes=len(ids or ()), length=round(sum(dist(p, q) for p, q in zip([a] + route[:-1], route)), 1) if route else None,
             checks=checks, closed=len(closed), stuckSpots=len(stuck), skipped=skip_.skipped, probe=skip_.mode,
             ignoredBy=dict(sorted(getattr(skip_, 'by', {}).items(), key=lambda kv: -kv[1])[:5]),
             avatars=getattr(skip_, 'avatars', 0), notWalls=getattr(skip_, 'notWalls', None), secs=round(time.time() - t0, 2), file=data[2])
        if not route:
            H.ev('CAVE-NO-ROUTE', tag=tag, why='no open way from %s' % [round(v, 1) for v in a], closed=len(closed),
                 hitBy=dict(sorted(getattr(skip_, 'hits', {}).items(), key=lambda kv: -kv[1])[:6]))
            break
        prev = a
        for i, w in enumerate(route):
            last = i == len(route) - 1
            if i and dist(H.la.getPos(R), b) <= arrive:
                break
            ok, how = yield from _leg(H, w, arrive=arrive if last else TURN_ARRIVE,
                                      timeout=20.0 + dist(prev, w) / 8.0,
                                      tag='%s cave %s' % (tag, 'goal' if last else 'turn %d' % (i + 1)))
            legs += 1
            how = how or in_tunnel(H)
            if how:
                return (yield from _through(H, tag, area0, how, legs, backups))
            if H.area() != area0:
                H.ev('AREA-CHANGED', tag=tag, frm=area0, to=H.area())
                H.ev('CAVE-END', tag=tag, reached='area', legs=legs, backups=backups)
                return 'area'
            if ok:
                prev = w
                continue
            # stuck: back off it, then plan again from here without this leg
            here = H.la.getPos(R)
            here = (here[0], here[1], here[2])
            yield from back_up(H, tag)
            backups += 1
            how = in_tunnel(H)
            if how:
                return (yield from _through(H, tag, area0, how, legs, backups))
            closed.add(lkey(prev, w))
            again = [s for s in stuck if s[1] == w and dist(s[0], here) <= SAME_SPOT]
            stuck.append((here, w))
            if again and not last:
                skip.update(k for k, p in nodes.items() if dist(p, w) < 1.0)
            H.ev('CAVE-BACKUP', tag=tag, la=H.P(H.la), stuckAt=[round(v, 1) for v in here],
                 to=[round(v, 1) for v in w], n=backups, skipTurn=bool(again and not last))
            break
        else:
            break
    left = dist(H.la.getPos(R), b)
    H.ev('CAVE-END', tag=tag, reached=left <= arrive, left=round(left, 1), legs=legs, backups=backups)
    return left <= arrive
