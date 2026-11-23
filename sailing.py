"""Sail from the island you are standing on to another island, the way a kid does it (item 7).
Walk to this island's dinghy, launch the ship, take the wheel, tap W for full sail, steer with A / D round any island
in the way, turn in at the target's shore, tap S, wait for the anchor button, click it, land.
Reuses s_dock.py's Keys / anchorShown / near. Use from a step script:  yield from sailing.sail_to(H, uid)
Events: SAIL-START, sail-route, s2 (every 2 s at sea), sail-arrive, SAILED ok=True/False, SAIL-FAIL why=..."""
import os, sys, time, math
from panda3d.core import Point3, Vec3

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT', __file__))))
from s_dock import Keys, anchorShown, near, cls   # noqa: E402
import paths   # noqa: E402

_ISL = None
OBST_R = float(os.environ.get('SAIL_OBST_R', '3300'))     # keep this far from any island we are not landing at
# pir-test 11-18: SAIL_VIA="x,y" steers the sail through one waypoint first (q_sail2632: proves 0165 in cell 2632)
VIA = tuple(float(v) for v in os.environ['SAIL_VIA'].split(',')) if os.environ.get('SAIL_VIA') else None
VIA_R = float(os.environ.get('SAIL_VIA_R', '400'))
VIA_SECS = 60.0     # a per-call via (the retreat round foes) is given up after this, so it can never strand the sail
ARRIVE_R = 7000.0                                          # look for the target's deployer inside this range
LEG_SECS = float(os.environ.get('SAIL_LEG_SECS', '900'))
# ISLANDTOUR3 / STORY6 / STORY8 (11-19): the game caps a frame at 0.2 s (PiratesBase pirates-max-dt), so a hidden bot game
# under 5 fps sails in slow motion (33-40 ft/s real at 80 ft/s full sail) and a wall-clock LEG_SECS ran out 22k ft short.
# The leg limit counts game seconds; LEG_WALL_X * LEG_SECS of wall time still ends a frozen game.
LEG_WALL_X = float(os.environ.get('SAIL_LEG_WALL_X', '4'))


def legOver(g0, gnow, t0, tnow):
    """Pure: -> why the sail's time is up, or None. g = game seconds (globalClock frame time), t = wall seconds."""
    if gnow - g0 >= LEG_SECS:
        return 'never reached the shore in %ds' % LEG_SECS
    if tnow - t0 >= LEG_SECS * LEG_WALL_X:
        return 'never reached the shore in %ds wall (%ds game)' % (LEG_SECS * LEG_WALL_X, gnow - g0)
    return None


def hookWarnings(H, warns):
    """Point the game's warning popups at this sail's warns list [(t, text)]. One hook per game: before, the hook went
    in once and kept appending to the FIRST sail_to's list, so every later sail's warns stayed empty and shoreGrow /
    freshReef never saw a shore warning (DOLL16 sails 3 and 5, every island tour leg after the first)."""
    H._sailWarns = warns
    if getattr(H, '_sailWarnHook', False):
        return
    gm = H.la.guiMgr
    orig = gm.createWarning

    def cw(text, *a, **k):
        w = getattr(H, '_sailWarns', None)
        if w is not None:
            w.append((time.time(), str(text)[:80]))
        H.ev('warning', text=str(text)[:120])
        return orig(text, *a, **k)
    cw._sailHook = True
    gm.createWarning = cw
    H._sailWarnHook = True


def islands():
    """uid -> (name, x, y, worldDataFile) for every island in the main world (worldData/piratesWorld.py)."""
    global _ISL
    if _ISL is None:
        from pirates.leveleditor.worldData import piratesWorld as W
        _ISL = {}
        for w in W.objectStruct['Objects'].values():
            for uid, o in w.get('Objects', {}).items():
                if o.get('Type') == 'Island':
                    p = o.get('Pos')
                    _ISL[uid] = (o.get('Name', ''), float(p[0]), float(p[1]), o.get('File', ''))
    return _ISL


def _islandChildren(uid):
    """(world-data uid, object) for every object placed straight on the island (its world data file)."""
    f = islands().get(uid, (None, 0, 0, ''))[3]
    if not f:
        return []
    try:
        mod = __import__('pirates.leveleditor.worldData.%s' % f, fromlist=['objectStruct'])
    except Exception:
        return []
    return [(k, o) for isl in mod.objectStruct['Objects'].values() for k, o in isl.get('Objects', {}).items()]


def _pos(o):
    p = o['Pos']
    return (float(p[0]), float(p[1]), float(p[2]))


def dinghySpots(uid):
    """Island-relative positions of the island's dinghies (its world data file)."""
    return [_pos(o) for k, o in _islandChildren(uid) if o.get('Type') == 'Dinghy']


def shipwrightSpots(uid):
    """Island-relative positions of the island's shipwrights (its world data file)."""
    return [_pos(o) for k, o in _islandChildren(uid)
            if o.get('Type') == 'Townsperson' and o.get('Category') == 'Shipwright']


def islandObj(H, uid):
    for o in list(H.cr.doId2do.values()):
        if cls(o) == 'DistributedIsland' and getattr(o, 'uniqueId', None) == uid:
            return o
    return None


def hereUid(H):
    a = H.area()
    return a[1] if a and a[0] == 'DistributedIsland' else None


_TEXT = None


def _worldTexts():
    """{file stem: source text} for every world data file (read once)."""
    global _TEXT
    if _TEXT is None:
        import glob
        from pirates.leveleditor import worldData
        d = os.path.dirname(worldData.__file__)
        _TEXT = {}
        for f in glob.glob(os.path.join(d, '*.py')):
            try:
                _TEXT[os.path.basename(f)[:-3]] = open(f, encoding='utf-8', errors='replace').read()
            except Exception:
                pass
    return _TEXT


def islandOfUid(uid, depth=0):
    """The island (uid) a world-data object or area belongs to: its island file mentions it, or it sits in a
    cave / jungle file whose top area an island file mentions (Barbossa's cave -> Devil's Anvil)."""
    if not uid or depth > 3:
        return None
    if uid in islands():
        return uid
    texts = _worldTexts()
    for iu, (n, x, y, f) in islands().items():
        if f and uid in texts.get(f, ''):
            return iu
    for stem, t in texts.items():
        if uid in t and stem != 'piratesWorld':
            import re
            m = re.search(r"'Objects': \{\s*'([^']+)': \{", t)
            if m and m.group(1) != uid:
                r = islandOfUid(m.group(1), depth + 1)
                if r:
                    return r
    return None


def areaIsland(H, area):
    """Island uid for a (non-island) area object from the quest step, if it is not where we are."""
    uid = getattr(area, 'uniqueId', None) if area is not None else None
    isl = islandOfUid(uid)
    return isl if isl and isl != hereUid(H) else None


def onShip(H):
    """True when the pirate is aboard their own ship (deck or wheel)."""
    try:
        ships = list(H.la.getInventory().getShipDoIdList())
    except Exception:
        return False
    p = H.la.getParentObj()
    return p is not None and getattr(p, 'doId', None) in ships


def route(p, goal, obstacles):
    """Reactive way-point: if the straight line p->goal passes within R of an obstacle centre, aim at a point
    beside that obstacle (on the side the ship is already on); if inside one, aim straight out of it."""
    best = None
    for (cx, cy, R) in obstacles:
        c = Vec3(cx, cy, 0)
        pc = c - Vec3(p[0], p[1], 0)
        if pc.length() < R:                               # inside the circle: leave it on the goal side
            out = Vec3(p[0] - cx, p[1] - cy, 0)
            if out.length() < 1:
                out = Vec3(1, 0, 0)
            out.normalize()
            g = Vec3(goal[0] - cx, goal[1] - cy, 0)
            g.normalize()
            d = out + g * 0.5
            d.normalize()
            return Point3(cx + d[0] * (R + 1500), cy + d[1] * (R + 1500), 0), 'leave'
        seg = Vec3(goal[0] - p[0], goal[1] - p[1], 0)
        L = seg.length()
        if L < 1:
            continue
        u = seg / L
        t = pc.dot(u)
        if t <= 0 or t >= L:
            continue
        closest = Vec3(p[0], p[1], 0) + u * t
        off = Vec3(closest[0] - cx, closest[1] - cy, 0)
        if off.length() >= R:
            continue
        if best is None or t < best[0]:
            if off.length() < 1:
                off = Vec3(-u[1], u[0], 0)
            off.normalize()
            best = (t, Point3(cx + off[0] * (R + 1200), cy + off[1] * (R + 1200), 0))
    if best:
        return best[1], 'round'
    return Point3(goal[0], goal[1], 0), 'direct'


# The game offers "deploy ship" within this many ft of a dinghy (DistributedDinghy.interactRadius = 25), from the dock
# or the water. Walk to within DINGHY_REACH of the boat itself: a spot past it can be open sea (BATTLE1 swam into
# Port Royal's harbour aiming 12 ft past the boat and stuck 14 ft from it). The walk goes round buildings
# (paths.walk_route; LAUNCH1 walked straight at the nearest dinghy and hit a building after 75 ft); its last leg only
# has to be open ground up to DINGHY_SHORT ft before the boat.
DINGHY_USE_R = 25.0
DINGHY_REACH = 18.0
DINGHY_SHORT = DINGHY_REACH - 2.0


def live_dinghies(H):
    """The DistributedDinghy objects in interest that still have a node (one leaving interest is an empty NodePath:
    LAUNCH2 asserted on d.getPos of one)."""
    out = []
    for o in list(H.cr.doId2do.values()):
        if cls(o) == 'DistributedDinghy':
            try:
                if not o.isEmpty():
                    out.append(o)
            except Exception:
                pass
    return out


def dinghy_in_reach(H):
    """The nearest live dinghy within DINGHY_USE_R of the pirate, or None."""
    p = H.la.getPos(H.render)
    ds = [(paths.dist(p, o.getPos(H.render)), o) for o in live_dinghies(H)]
    ds = [x for x in ds if x[0] <= DINGHY_USE_R]
    return min(ds, key=lambda x: x[0])[1] if ds else None


def to_dinghy(H, here):
    """Generator (yield from). Walk (held keys, no setPos) round buildings to within DINGHY_REACH of whichever of the
    island's dinghies (world data spots, plus any live one not on a spot) has the shortest open route, then wait for
    that dinghy to come into interest. A dinghy out on the water with no pier near it has no route and is skipped;
    there is never a blind walk at it (LAUNCH2 planned to the one live dinghy only, found no route, walked straight
    at it into the harbour). -> the live dinghy within DINGHY_USE_R, or None."""
    la, R = H.la, H.render
    d = dinghy_in_reach(H)
    if d is not None:
        return d
    isl = islandObj(H, here)
    goals = [tuple(R.getRelativePoint(isl, Point3(*s))) for s in dinghySpots(here)] if isl is not None else []
    for o in live_dinghies(H):
        p = o.getPos(R)
        if all(paths.dist(p, g) > 10.0 for g in goals):
            goals.append((p[0], p[1], p[2]))
    if not goals:
        H.ev('walk-to-dinghy', island=here, ok=False, why='no dinghy spots', la=H.P(la))
        return None
    g = yield from paths.walk_route(H, goals, DINGHY_REACH, DINGHY_SHORT, tag='to-dinghy', max_goals=len(goals))
    if g is not None:
        yield ('until', lambda: dinghy_in_reach(H) is not None, 15, 'dinghy in reach')
    d = dinghy_in_reach(H)
    p = la.getPos(R)
    H.ev('walk-to-dinghy', island=here, goals=len(goals), spot=[round(v, 1) for v in g] if g else None,
         ok=d is not None, dinghy=d.doId if d is not None else None,
         left=round(min(paths.dist(p, s) for s in goals), 1), gs=la.getGameState(), la=H.P(la))
    return d


# MAIN52 / MAIN57 (11-22): out of Tortuga tavern_2's door (uid 1156279370.48dzlu) the pirate stands at (10819.8,
# 16860.9) in a pocket the route grid has no way out of (search dry at 89 points, the pocket escape too), so no dinghy,
# shipwright or door was reachable and the capturePenrod ship quest failed 'no open route to any dinghy' 3 times. A
# teleport out to another island and back lands him at the arrival spot by the docks, once per launch. MAIN59: a
# teleport to the island he stands on is turned away (DistributedTeleportMgrAI.d_initiateTeleport 'already there',
# teleportDenied -1), so the word answered 'Teleporting...' and he never moved, 3 times.
POCKET_HOP_MOVED = 30.0     # ft he must end up from where he stood for the hop to count
POCKET_HOP_SECS = 90.0      # per leg: a hidden game at 5 fps sits a while on the loading screen
POCKET_AWAY = ('1150922126.8dzlu', '1156207188.95dzlu')    # Port Royal, or Tortuga when he is on Port Royal


def _hopLeg(H, uid):
    """Generator (yield from). One island teleport: the story run's areaTeleport word, a player bot (STORY_PLAYER=1)
    the map's island teleport like a kid. -> True once he stands on uid, None if asking failed."""
    if os.environ.get('STORY_PLAYER') == '1':
        try:
            H.cr.teleportMgr.requestTeleportToIsland(uid)
        except Exception as e:
            H.ev('POCKET-HOP', island=uid, ok=False, err=str(e), la=H.P(H.la))
            return None
    else:
        H.mw('areaTeleport %s' % uid)
    landed = lambda: H.la.getGameState() == 'LandRoam' and hereUid(H) == uid
    yield ('until', landed, POCKET_HOP_SECS, 'pocket hop')
    return landed()


def pocketHop(H, here):
    """Generator (yield from). Teleport to another island and back to the one he stands on.
    -> True if he is back on here, POCKET_HOP_MOVED ft or more from where he stood."""
    la, R = H.la, H.render
    if not here or la.getGameState() != 'LandRoam':
        return False
    p0 = la.getPos(R)
    away = POCKET_AWAY[1] if here == POCKET_AWAY[0] else POCKET_AWAY[0]
    out = yield from _hopLeg(H, away)
    back = (yield from _hopLeg(H, here)) if out else False
    moved = bool(back) and paths.dist(la.getPos(R), p0) >= POCKET_HOP_MOVED
    H.ev('POCKET-HOP', island=here, away=away, out=out, back=back, ok=moved, frm=[round(p0[i], 1) for i in range(3)],
         la=H.P(la))
    return moved


def dinghyOrHop(H, here, st):
    """Generator (yield from). to_dinghy; when no dinghy has a route, one pocketHop per st (one launch) and to_dinghy
    again from where he lands. -> the live dinghy in reach, or None."""
    d = yield from to_dinghy(H, here)
    if d is None and not st.get('hopped'):
        st['hopped'] = True
        if (yield from pocketHop(H, here)):
            d = yield from to_dinghy(H, here)
    return d


# Every townsperson is a shop (DistributedNPCTownfolk inherits DistributedShopKeeper), so no object's class is ever
# 'DistributedShopKeeper' itself: REPAIR1 (11-16) looked for that, found none and never sent a repair. The shipwright
# is the townsperson whose avatarType is AvatarTypes.Shipwright; pay him from his counter, like a player.
SHIPWRIGHT_REACH = 12.0


def shipwrights(H):
    """The shipwright townsfolk in interest that still have a node."""
    from pirates.pirate import AvatarTypes
    out = []
    for o in list(H.cr.doId2do.values()):
        if cls(o) != 'DistributedNPCTownfolk':
            continue
        try:
            if o.avatarType.isA(AvatarTypes.Shipwright) and not o.isEmpty():
                out.append(o)
        except Exception:
            pass
    return out


def visProbe(ship):
    # Where the ocean grid's sight is centred vs the ship's own cell. A visZone frozen at the launch cell while the
    # ship sails on would explain the ship deleted 4 columns out (STORY19/27). Never throws; missing parts log None.
    out = {'shipZone': getattr(ship, 'zoneId', None), 'visZone': None, 'visAv': None, 'visTask': None, 'gs': None}
    try:
        import builtins
        av = getattr(builtins, 'localAvatar', None)
        out['gs'] = av.gameFSM.state if av is not None and getattr(av, 'gameFSM', None) else None
        grid = ship.getParentObj() if ship is not None else None
        if grid is not None and hasattr(grid, 'visZone'):
            out['visZone'] = grid.visZone
            out['visAv'] = getattr(grid, 'visAvatar', None) is not None
            tm = getattr(builtins, 'taskMgr', None)
            out['visTask'] = bool(tm.hasTaskNamed(grid.taskName('processVisibility'))) if tm is not None else None
    except Exception as e:
        out['err'] = repr(e)[:80]
    return out


def repair(H, here, sid):
    """Generator (yield from). Walk (held keys, round buildings) to this island's shipwright and pay him to mend ship
    sid with the game's own repair button code (sendRequestRepairShip: checks the gold, then requestPurchaseRepair).
    -> (hp, paid)"""
    la, R = H.la, H.render
    inv = la.getInventory()
    gold0 = inv.getGoldInPocket()
    sw = shipwrights(H)
    if sw:
        goals = [tuple(o.getPos(R)) for o in sw]
    else:
        isl = islandObj(H, here)
        goals = [tuple(R.getRelativePoint(isl, Point3(*s))) for s in shipwrightSpots(here)] if isl is not None else []
    g = None
    if goals:
        g = yield from paths.walk_route(H, goals, SHIPWRIGHT_REACH, SHIPWRIGHT_REACH - 2, tag='to-shipwright',
                                        max_goals=len(goals))
        if g is not None:
            yield ('until', lambda: shipwrights(H), 15, 'shipwright in interest')
    p = la.getPos(R)
    sw = sorted(shipwrights(H), key=lambda o: paths.dist(p, o.getPos(R)))
    npc = sw[0] if sw else None
    sent = False
    if npc is not None and paths.dist(p, npc.getPos(R)) <= SHIPWRIGHT_REACH + 15 and (yield from near(H, npc, SHIPWRIGHT_REACH)):
        npc.sendRequestRepairShip(sid, 1)
        # the game's own call returns before sending anything when the client has no owner view of the ship
        # (STORY26: a sunk ship, hp=None, nothing reached the server)
        sent = H.cr.getOwnerView(sid) is not None
        # a paid repair takes gold at once; the owner view's Hp may or may not follow
        yield ('until', lambda: inv.getGoldInPocket() != gold0 or
               (getattr(H.cr.getOwnerView(sid), 'Hp', 0) or 0) > 0, 10, 'repair')
    ov = H.cr.getOwnerView(sid)
    hp = getattr(ov, 'Hp', None)
    paid = inv.getGoldInPocket() < gold0
    H.ev('repair', ship=sid, hp=hp, maxHp=getattr(ov, 'maxHp', None), gold0=gold0, gold=inv.getGoldInPocket(),
         paid=paid, sent=sent, goals=len(goals), walked=g is not None,
         shipwright=None if npc is None else (npc.doId, getattr(npc, 'name', ''), round(paths.dist(la.getPos(R), npc.getPos(R)), 1)),
         la=H.P(la))
    return hp, paid


def launch(H, here, aboard):
    """Generator (yield from). Repair, walk to this island's dinghy, launch the pirate's first ship and walk to its
    wheel (held keys, no setPos). -> the ship with the pirate steering, or None after a SAIL-FAIL event."""
    la = H.la
    ships = list(la.getInventory().getShipDoIdList())
    if not ships:
        H.ev('SAIL-FAIL', why='no ship'); return None
    sid = ships[0]
    ov = H.cr.getOwnerView(sid)
    hp, maxHp = getattr(ov, 'Hp', None), getattr(ov, 'maxHp', None)
    if not aboard and hp is not None and maxHp and hp < maxHp:
        # a sunk ship and too little gold for its repair is a dead end (the repair button only warns "not enough
        # money"): end the run with that reason instead of asking the shipwright again until time runs out (STORY18)
        from pirates.ship import ShipGlobals
        cost, gold = ShipGlobals.getRepairCost(ov), la.getInventory().getGoldInPocket()
        # server-tree 0156 (11-18): a pirate whose gold is below the cost is repaired free -> not a dead end
        free = hasattr(ShipGlobals, 'getRepairPrice') and ShipGlobals.getRepairPrice(cost, gold) == 0 and cost > 0
        if free:
            H.ev('REPAIR-FREE', ship=sid, gold=gold, cost=cost)
        if hp <= 0 and gold < cost and not free:
            H.ev('SAIL-FAIL', why='the ship is sunk and the pirate cannot pay its repair', ship=sid, gold=gold, cost=cost)
            raise RuntimeError('sunk ship %s needs %s gold to repair, the pirate has %s' % (sid, cost, gold))
        # mend a damaged ship first. The launch panel greys out a sunk one ("You must repair this ship before sailing
        # it again"); BATTLE2 (11-16) sailed one at 0 hp and it went down at once
        hp, paid = yield from repair(H, here, sid)
        if hp is not None and hp <= 0 and not paid:
            H.ev('SAIL-FAIL', why='the ship is sunk and the repair did not go through', ship=sid); return None
    # 1. launch at this island's dinghy (unless already aboard, e.g. right after the deploy-ship quest)
    hop = {}
    for tries in range(3):
        if sid in H.cr.doId2do:
            break
        d = yield from dinghyOrHop(H, here, hop)
        if d is None:
            H.ev('SAIL-FAIL', why='no open route to any dinghy', island=here, la=H.P(la)); return None
        d.requestInteraction(la.doId)
        yield 3
        try:
            d.ownShipSelected(sid)
        except Exception as e:
            H.ev('ownShipSelected-err', err=str(e))
        H.ev('launch', dinghy=d.doId, ship=sid, island=here)
        _t = time.time()
        yield ('upto', lambda: time.time() - _t >= 2.0 and sid in H.cr.doId2do, 20, 'ship arrives at the dinghy')
    ship = H.cr.doId2do.get(sid)
    if ship is None:
        H.ev('SAIL-FAIL', why='ship never arrived'); return None
    yield ('until', lambda: la.getGameState() != 'Cutscene', 40, 'launch cutscene')
    if getattr(ship, 'steeringAvId', None) != la.doId:
        wheels = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedSteeringWheel' and getattr(o, 'shipId', None) == sid]
        if not wheels:
            yield ('upto', lambda: any(cls(o) == 'DistributedSteeringWheel' and getattr(o, 'shipId', None) == sid for o in list(H.cr.doId2do.values())), 20, 'wheel generated')
            wheels = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedSteeringWheel' and getattr(o, 'shipId', None) == sid]
        if not wheels:
            # 11-20 21:10: a zone bounce can rebuild the client's ship copy; say whether the one held here is stale
            # DOLL2 11-20 23:18: aboard (the AI logged the boarding) and no wheel for 18 min; the wheel lives in the
            # ship's on-deck zone, so say which ship zones the client holds and which ship parts it has
            from direct.distributed.DoInterestManager import DoInterestManager
            H.ev('SAIL-FAIL', why='no wheel', ship=sid, laShipIsOurs=getattr(la, 'ship', None) is ship,
                 doId2doIsOurs=H.cr.doId2do.get(sid) is ship, inDoId2do=sid in H.cr.doId2do,
                 shipLoc=(getattr(ship, 'parentId', None), getattr(ship, 'zoneId', None)),
                 laLoc=(getattr(la, 'parentId', None), getattr(la, 'zoneId', None)),
                 shipState=getattr(ship, 'queryGameState', lambda: None)(),
                 parts=sorted('%s@%s' % (cls(o), getattr(o, 'zoneId', None)) for o in list(H.cr.doId2do.values())
                              if getattr(o, 'parentId', None) == sid or getattr(o, 'shipId', None) == sid),
                 otherWheels=[(o.doId, getattr(o, 'shipId', None)) for o in list(H.cr.doId2do.values())
                              if cls(o) == 'DistributedSteeringWheel'],
                 interests=[(getattr(st, 'desc', None), getattr(st, 'zoneIdList', None))
                            for st in list(getattr(DoInterestManager, '_interests', {}).values())
                            if getattr(st, 'parentId', None) == sid]); return None
        # the wheel DO itself sits at the ship's origin (LAUNCH3 walked to 0,0,0); its model is put on this locator
        spot = ship.locators.find('**/location_wheel;+s') if getattr(ship, 'locators', None) else None
        if spot is None or spot.isEmpty():
            spot = wheels[0].prop.geom_High
        # boats 04:45 11-21: the Sloop's wheel stand stopped him 3.1 ft from its locator (class 2), and a near of 3 ft
        # failed; the game's own wheel prompt (DistributedSteeringWheel sphereScale 6) reaches 6 ft, so 5 ft is a player's reach
        # boats 05:06 11-21: the Frigate's wheel stands 9 ft up; the straight walk jammed him under that deck's edge and
        # the search from there ran dry. A player who sees the wheel up there heads for the stairs from the open deck
        up = lambda: spot.getZ(H.render) - la.getZ(H.render) > paths.MAX_RISE + 1.0
        raised = up()
        if raised:
            yield from wheel_route(H, spot, 'to-wheel')
        # boats 07:20 11-21: near() counts the map distance only, so under the Frigate's wheel deck 9 ft below the wheel
        # read as there; still below it -> the deck route again
        if not (yield from near(H, spot, WHEEL_REACH)) or up():
            # boats 01:06 11-21: the Light Galleon's wheel stands on the raised stern deck and the straight walk stuck
            # 8 ft below it (z 28 vs 33). A player takes the stairs: plan the way over the deck's floors, then walk in
            yield from wheel_route(H, spot, 'to-wheel-2' if raised else 'to-wheel')
            if not (yield from near(H, spot, WHEEL_REACH)) or up():
                H.ev('SAIL-FAIL', why='could not walk up to the wheel', la=H.P(la), wheel=H.P(spot)); return None
        wheels[0].requestInteraction(la.doId)
        yield ('until', lambda: getattr(ship, 'steeringAvId', None) == la.doId, 20, 'take wheel')
    if getattr(ship, 'steeringAvId', None) != la.doId:
        w = wheels[0] if wheels else None
        H.ev('SAIL-FAIL', why='could not take the wheel', shipState=getattr(ship, 'queryGameState', lambda: None)(),
             wheels=len(wheels), wheelUser=getattr(w, 'userId', None), wheelState=getattr(getattr(w, 'state', None), '__str__', lambda: None)(),
             captain=getattr(ship, 'captainId', None), canTake=ship.canTakeWheel(w, la) if w is not None and hasattr(ship, 'canTakeWheel') else None,
             laParent=getattr(la, 'parentId', None), laZone=getattr(la, 'zoneId', None), ship=sid); return None
    for k in range(10):
        if getattr(ship, 'sailsReady', True):
            break
        yield 1
    return ship


WHEEL_REACH = 5            # ft; inside the wheel's 6 ft use sphere


def wheel_route(H, spot, tag, arrive=WHEEL_REACH):
    """Generator (yield from): plan the way over the deck's floors to the wheel's locator `spot` and walk it. Planned on
    the deck's own frame (boats 05:06 11-21: the Frigate bobs 4 ft): a node riding with the locator, in feet (scale 1
    to render) and level with the sea, so the search's sea check still holds. -> True when within `arrive` (the repair
    spots use it too, boats 11-21)."""
    deck = spot.getParent().attachNewNode('to-wheel-deck')
    deck.setScale(H.render, 1)
    deck.setZ(H.render, 0)
    w = spot.getPos(deck)
    H.ev('WHEEL-ROUTE', tag=tag, la=H.P(H.la), wheel=H.P(spot), up=round(spot.getZ(H.render) - H.la.getZ(H.render), 1))
    try:
        return (yield from paths.walk_room(H, (w[0], w[1], w[2]), arrive, tag=tag, ref=deck))
    finally:
        deck.removeNode()
DOCK_LAPS = int(os.environ.get('SAIL_DOCK_LAPS', '2'))
REEF_FRESH = 4.0          # a shore warning older than this (s) is not "at the reef now" (STORY28 stopped on a 140 s old one)


# MAIN22-24 (11-21): every Port Royal -> Padres sail ran aground on Port Royal's north coast (one 'too close to shore'
# warning, then 5 min sliding east at 7-17 ft/s): the island's circle is smaller than its coast there. Aground = a shore
# warning in the last SHORE_WARN s and the ship below SHORE_VEL; the nearest island's circle then grows by SHORE_STEP
# (every SHORE_EVERY s at most, SHORE_MAX in all, for this sail only), so the route aims further out and leaves the coast.
SHORE_WARN = 60.0
SHORE_VEL = 30.0
SHORE_STEP = 500.0
SHORE_EVERY = 6.0
SHORE_MAX = 2500.0


def shoreGrow(obst, p, warns, vel, now, st):
    """Pure. obst = [(x, y, R)] (changed in place), p = ship (x, y), warns = [(t, text)], st = this sail's state.
    -> the index of the island circle grown, or None."""
    if vel >= SHORE_VEL or now - st.get('shoreT', -1e9) < SHORE_EVERY:
        return None
    if not any(now - t <= SHORE_WARN and ('reef' in w.lower() or 'close' in w.lower()) for t, w in warns[-3:]):
        return None
    best = None
    for i, (cx, cy, R) in enumerate(obst):
        e = math.hypot(p[0] - cx, p[1] - cy) - R
        if best is None or e < best[0]:
            best = (e, i)
    if best is None or best[0] > 1500:
        return None
    i = best[1]
    cx, cy, R = obst[i]
    if R - st.setdefault('shoreR0', {}).setdefault(i, R) >= SHORE_MAX:
        return None
    obst[i] = (cx, cy, R + SHORE_STEP)
    st['shoreT'] = now
    return i


def freshReef(warns, now=None):
    """Pure: did a 'too close to shore' / reef warning come in the last REEF_FRESH s? warns = [(t, text)]."""
    now = time.time() if now is None else now
    return any(now - t <= REEF_FRESH and ('reef' in w.lower() or 'close' in w.lower()) for t, w in warns[-3:])


def lapPoints(c, p, R, lap):
    """Pure: (out, side) for docking lap n. out = straight back out from the shore point p, R past the centre c;
    side = the same ring turned 60 deg (lap 1 one way, lap 2 the other way, ...), where the next run-in starts."""
    dx, dy = p[0] - c[0], p[1] - c[1]
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    a = math.radians(60.0 * (1 if lap % 2 else -1) * ((lap + 1) // 2))
    sx, sy = ux * math.cos(a) - uy * math.sin(a), ux * math.sin(a) + uy * math.cos(a)
    return (c[0] + ux * R, c[1] + uy * R), (c[0] + sx * R, c[1] + sy * R)


def dockLap(H, ship, keys, c, dep, warns, lap):
    """Generator: no anchor where the ship stopped. Sail back out, round to a point 60 deg along the ring, and run in
    at the centre again; stop when the anchor shows (-> True), at a fresh reef warning or when slow (-> False).
    Lines: DOCK-RETRY lap side, DOCK-IN lap, then ANCHOR-SHOWN or DOCK-LAP-END."""
    la = H.la
    R = dep.minRadius + 1500.0
    p = ship.getPos(H.render)
    out, side = lapPoints(c, p, R, lap)
    H.ev('DOCK-RETRY', lap=lap, frm=[round(p[0]), round(p[1])], out=[round(v) for v in out], side=[round(v) for v in side],
         port=la.getPort())
    messenger.send('w'); messenger.send('w-up')      # full sail again
    for leg, aim in (('out', out), ('side', side)):
        t0 = time.time()
        while time.time() - t0 < 150:
            if H.cr.doId2do.get(ship.doId) is None or la.getGameState() != 'ShipPilot':
                keys.release(); return False
            q = ship.getPos(H.render)
            if math.hypot(q[0] - aim[0], q[1] - aim[1]) < 300:
                break
            keys.steer(ship, Point3(aim[0], aim[1], 0))
            yield 0.5
        H.ev('dock-leg', lap=lap, leg=leg, pos=H.P(ship), secs=round(time.time() - t0))
    H.ev('DOCK-IN', lap=lap, pos=H.P(ship))
    t0 = time.time()
    slow = 0
    while time.time() - t0 < 150:
        if H.cr.doId2do.get(ship.doId) is None or la.getGameState() != 'ShipPilot':
            keys.release(); return False
        if anchorShown(ship) and la.getPort():
            keys.release()
            messenger.send('s'); messenger.send('s-up')
            H.ev('ANCHOR-SHOWN', lap=lap, port=la.getPort(), pos=H.P(ship), secs=round(time.time() - t0))
            return True
        keys.steer(ship, Point3(c[0], c[1], 0))
        try:
            vel = ship.node().getPhysicsObject().getVelocity().length()
        except Exception:
            vel = 0
        slow = slow + 1 if vel < 5 else 0
        if freshReef(warns) or slow >= 6:
            break
        yield 0.5
    keys.release()
    messenger.send('s'); messenger.send('s-up')
    t1 = time.time()
    while time.time() - t1 < 15 and not anchorShown(ship):
        yield 0.5
    H.ev('DOCK-LAP-END', lap=lap, anchor=anchorShown(ship), port=la.getPort(), reef=freshReef(warns), pos=H.P(ship))
    return anchorShown(ship)


def sail_to(H, uid, why='', via=None):
    """Generator. Leaves H.sailResult = True when the pirate is standing (LandRoam) on island uid. via = (x, y): sail
    through that point first (dropped after VIA_SECS), else the SAIL_VIA env point."""
    VIA = globals()['VIA'] if via is None else tuple(via)
    la = H.la
    H.sailResult = False
    H.walk_cancel()         # a background walk from the story beat must not keep holding keys while we sail
    tbl = islands()
    here = hereUid(H)
    if uid not in tbl:
        H.ev('SAIL-FAIL', why='unknown island', to=uid); return
    name, tx, ty, _ = tbl[uid]
    aboard = onShip(H)
    H.ev('SAIL-START', frm=here, to=uid, isl=name, why=why, la=H.P(la), gs=la.getGameState(), aboard=aboard)
    if here == uid:
        H.sailResult = True; return
    if here is None and not aboard:
        H.ev('SAIL-FAIL', why='not standing on an island', area=H.area()); return
    ship = yield from launch(H, here, aboard)
    if ship is None:
        return
    sid = ship.doId
    keys = Keys(H)
    try:
        oDel = H.cr.deleteObject
        if not getattr(oDel, '_sailHook', False):
            def delHook(doId, *a, **k):
                o = H.cr.doId2do.get(doId)
                if doId in list(la.getInventory().getShipDoIdList()):
                    H.ev('SHIP-DELETED', doId=doId, cls=cls(o) if o is not None else None, zone=getattr(o, 'zoneId', None),
                         parent=getattr(o, 'parentId', None), pos=H.P(o) if o is not None else None, hp=getattr(o, 'Hp', None))
                return oDel(doId, *a, **k)
            delHook._sailHook = True
            H.cr.deleteObject = delHook
    except Exception as e:
        H.ev('del-hook-err', err=str(e))
    messenger.send('w'); messenger.send('w-up')      # tap W: full sail
    # obstacles: every island but the target (the one we leave included: we start at its shore)
    # (unnamed entries are the small pvp rocks)
    obst = [(x, y, OBST_R if n else 900) for u, (n, x, y, f) in tbl.items() if u != uid]
    t0 = time.time()
    lastLog = 0
    lastMode = None
    dep = None
    depPos = None
    stopped = False
    st = {'slow': 0, 'hpMin': getattr(ship, 'Hp', None), 'z0': ship.getZ(H.render), 'minZ': ship.getZ(H.render)}
    warns = []
    try:
        hookWarnings(H, warns)
    except Exception as e:
        H.ev('warn-hook-err', err=str(e))
    g0 = globalClock.getFrameTime()
    over = None
    while True:
        over = legOver(g0, globalClock.getFrameTime(), t0, time.time())
        if over:
            break
        if H.cr.doId2do.get(sid) is None or la.getGameState() not in ('ShipPilot',):
            H.ev('SAIL-FAIL', why='left the wheel / ship gone', gs=la.getGameState(), area=H.area(), hp=getattr(ship, 'Hp', None))
            keys.release(); return
        p = ship.getPos(H.render)
        dist = (Vec3(p[0] - tx, p[1] - ty, 0)).length()
        if dist < ARRIVE_R and dep is None:
            isl = islandObj(H, uid)
            if isl is not None:
                deps = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedShipDeployer' and o.getParentObj() is isl]
                if deps:
                    dep = deps[0]
                    depPos = dep.getPos(H.render)
                    H.ev('sail-arrive', dist=round(dist), deployer=dep.doId, depMin=dep.minRadius, depPos=H.P(dep), secs=round(time.time() - t0))
        if VIA is not None and not st.get('viaDone'):
            vd = (Vec3(p[0] - VIA[0], p[1] - VIA[1], 0)).length()
            vz = getattr(ship, 'zoneId', None)
            if vd < VIA_R or (via is not None and time.time() - t0 > VIA_SECS):
                st['viaDone'] = True
                H.ev('SAIL-VIA', via=list(VIA), dist=round(vd), zone=vz, pos=H.P(ship), hp=getattr(ship, 'Hp', None),
                     secs=round(time.time() - t0))
        if VIA is not None and not st.get('viaDone') and depPos is None:
            goal = Point3(VIA[0], VIA[1], 0)
            dd = None
        elif depPos is not None:
            goal = depPos
            dd = (Vec3(p[0] - depPos[0], p[1] - depPos[1], 0)).length()
        else:
            goal = Point3(tx, ty, 0)
            dd = None
        # islands only: a moving enemy ship as an obstacle moved the aim point every sample (STORY12: round / leave /
        # direct flipping, 'leave' aimed behind the ship) and the ship chased it in circles. A tester holds the course.
        if dep is None:
            try:
                vel0 = ship.node().getPhysicsObject().getVelocity().length()
            except Exception:
                vel0 = SHORE_VEL
            gi = shoreGrow(obst, (p[0], p[1]), warns, vel0, time.time(), st)
            if gi is not None:
                H.ev('SAIL-SHORE', isl=[round(v) for v in obst[gi]], pos=[round(p[0]), round(p[1])], vel=round(vel0, 1))
        tgt, mode = route(p, goal, obst)
        brg = keys.steer(ship, tgt)
        try:
            vel = ship.node().getPhysicsObject().getVelocity().length()
        except Exception:
            vel = 0
        hp = getattr(ship, 'Hp', None)
        H.ev('h', pos=[round(p[0]), round(p[1])], hdg=round(ship.getH(H.render)), brg=round(brg), mode=mode,
             tgt=[round(tgt[0]), round(tgt[1])], vel=round(vel, 1), hp=hp)
        if hp is not None and st['hpMin'] is not None:
            st['hpMin'] = min(st['hpMin'], hp)
        st['minZ'] = min(st['minZ'], ship.getZ(H.render))
        if getattr(ship, 'zoneId', None) != st.get('visShipZone'):
            st['visShipZone'] = getattr(ship, 'zoneId', None)
            H.ev('vis', **visProbe(ship))
        if mode != lastMode or time.time() - lastLog > 10:
            lastLog = time.time()
            lastMode = mode
            foes = []
            for o in list(H.cr.doId2do.values()):
                if o is ship or not hasattr(o, 'shipClass') or not hasattr(o, 'getPos'):
                    continue
                try:
                    fd = (o.getPos(H.render) - p).length()
                except Exception:
                    continue
                if fd < 4000:
                    foes.append((round(fd), cls(o), getattr(o, 'name', ''), getattr(o, 'level', None), o.doId))
            foes.sort()
            H.ev('near-ships', n=len(foes), ships=foes[:4], hp=getattr(ship, 'Hp', None))
            H.ev('s2', d=round(dist), dd=None if dd is None else round(dd), mode=mode, tgt=[round(tgt[0]), round(tgt[1])],
                 pos=[round(p[0]), round(p[1])], brg=round(brg), vel=round(vel, 1), hp=hp, anchor=anchorShown(ship), port=la.getPort(),
                 zone=getattr(ship, 'zoneId', None), parent=getattr(ship, 'parentId', None), vis=visProbe(ship),
                 wall=round(time.time() - t0), game=round(globalClock.getFrameTime() - g0))
        if dep is not None and anchorShown(ship) and la.getPort():
            keys.release()
            messenger.send('s'); messenger.send('s-up')     # tap S: drop sail
            H.ev('ANCHOR-SHOWN', dd=round(dd), dist=round(dist), depMin=dep.minRadius, vel=round(vel, 1), port=la.getPort(),
                 secs=round(time.time() - t0))
            stopped = True
            break
        if dep is not None:
            reef = freshReef(warns)
            st['slow'] = st['slow'] + 1 if (dd < dep.minRadius + 300 and vel < 5) else 0
            if reef or st['slow'] >= 4 or dd < dep.minRadius + 60:
                keys.release()
                messenger.send('s'); messenger.send('s-up')     # tap S: drop sail
                H.ev('at-shore', dd=round(dd), depMin=dep.minRadius, vel=round(vel, 1), reef=reef, anchor=anchorShown(ship), port=la.getPort())
                stopped = True
                break
        yield 0.5
    keys.release()
    if not stopped:
        H.ev('SAIL-FAIL', why=over or 'never reached the shore', dist=round(dist), wallSecs=round(time.time() - t0),
             gameSecs=round(globalClock.getFrameTime() - g0)); return
    # the anchor must show (we are inside the port sphere); give it up to 30 s
    t1 = time.time()
    while time.time() - t1 < 30 and not anchorShown(ship):
        yield 0.5
    lap = 0
    while not anchorShown(ship) and lap < DOCK_LAPS:
        lap += 1
        if H.cr.doId2do.get(sid) is None or la.getGameState() != 'ShipPilot':
            break
        ok = yield from dockLap(H, ship, keys, (tx, ty), dep, warns, lap)
        if ok:
            break
    if not anchorShown(ship):
        H.ev('SAIL-FAIL', why='no anchor button at the shore', port=la.getPort(), laps=lap); return
    H.ev('ANCHOR-DROP', port=la.getPort(), laps=lap, pos=H.P(ship))
    ship.shipStatusDisplay.handleAnchorButton()
    yield ('until', lambda: hereUid(H) == uid and la.getGameState() == 'LandRoam', 90, 'land at %s' % name)
    ok = hereUid(H) == uid
    H.ev('SAILED', ok=ok, to=uid, isl=name, secs=round(time.time() - t0), hpMin=st['hpMin'],
         zOk=st['minZ'] >= st['z0'] - 1, area=H.area(), la=H.P(la))
    H.sailResult = ok
