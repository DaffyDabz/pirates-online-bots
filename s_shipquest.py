"""Ship quest steps for the story bot (s_story): sink ships for a quest and dock at a quest's port, played like a player.
No teleport, no setPos: the ship is launched at a dinghy (sailing.launch), steered with the A / D keys (s_dock.Keys),
the broadsides fired with the number keys the combat tray binds while steering (CombatTray.initCombatTray:
key str(i + 1) = RadialMenu.getAllSkills(SailingRep, 2)[i]), docked with the anchor button (sailing.sail_to).

SHIP_TYPES (DefeatShip, RecoverShipItem, CaptureShipNPC): the server credits these when a matching NPC ship sinks
near us (QuestManagerAI.shipDefeated -> QuestTaskDNA.handleShipDefeat: faction isA, hull in getShipList(hull),
level, flagship, location). hunt() roams round the island it set out from, picks the nearest matching ship in view,
puts it abeam and fires the broadside that the game's own aim check (DistributedShip.checkBroadsideAlignment) says is
lined up. No broadside skill (a low-level pirate) = it rams instead (a ram sink credits too). Ends on a credit, when
our ship sinks, or after secs.
DOCK_TYPES (MaroonNPC, SmuggleItem): credited when we drop anchor at a port in the task's location list
(DistributedShipAI.dropAnchor -> QuestEvent.DockedAtPort, location = the island's uid). dock() sails to the nearest
such island, or, standing on one already, sails out past its port and docks again (smuggleRum x10 at Port Royal).

The only magic word: 'gold' when our ship is sunk and the pirate cannot pay its repair (a player would have quest
gold by now; the test pirate has none). It is logged (MW-GOLD) with the cost.
Events: SHIP-HUNT, ship-seen (faction / hull / match), SHIP-TARGET, BROADSIDE, NO-BROADSIDE, RAM, FOE-SUNK,
FOE-LOST, SHIP-CREDIT, OUR-SHIP-SUNK, SHIP-HUNT-END; DOCK-START, DOCK-OUT, DOCK-END."""
import os, sys, time, math
from panda3d.core import Point3, Vec3

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402
from s_dock import Keys, cls, anchorShown   # noqa: E402

SHIP_TYPES = ('DefeatShipTaskDNA', 'RecoverShipItemTaskDNA', 'CaptureShipNPCTaskDNA')
DOCK_TYPES = ('MaroonNPCTaskDNA', 'SmuggleItemTaskDNA')
SEE_R = 6000.0          # NPC ships farther than this are ignored
FIRE_R = 1900.0         # broadsides auto-aim inside ShipGlobals.BROADSIDE_MAX_AUTOAIM_DIST (2000)
# pir-bot job 15 (11-18): a caller may set LOST = fn(foe doId) -> falsy, or what it last knew of a target that left
# the client's view only by sailing off (s_shipfight: last seen out of broadside range). Such a target is FOE-LOST, not
# sunk, so SHIP-HUNT-END's sunk and the caller's count agree (shipfight9 said sunk=1 here and sunk=0 in SHIPFIGHT-END).
LOST = None
PATROL_R = float(os.environ.get('SHIP_PATROL_R', '8000'))    # ft from the home island's centre while looking
# pir-bot job 43 (GROG2): a caller may set PATROL_PTS = [(x, y, label)], a search route sailed in turn (nearest point
# first, then on round) while no ship worth sinking is in view, in place of the ring round the home island.
PATROL_PTS = None
LEG_R = 1500.0          # a patrol point this close counts as reached
DOCK_OUT = float(os.environ.get('SHIP_DOCK_OUT', '4500'))     # past the port sphere (3200-3700) before a redock


def factionOf(o):
    """The AvatarType the server puts in the ship-defeat event for this ship (QuestManagerAI.shipDefeated)."""
    from pirates.ship import ShipGlobals as SG
    from pirates.pirate import AvatarTypes as AT
    team = SG.getShipTeam(getattr(o, 'shipClass', 0))
    return {SG.UNDEAD_TEAM: AT.Undead, SG.FRENCH_UNDEAD_TEAM: AT.French, SG.SPANISH_UNDEAD_TEAM: AT.Spanish,
            SG.NAVY_TEAM: AT.Navy, SG.TRADING_CO_TEAM: AT.TradingCo}.get(team)


def hpOf(o):
    try:
        return o.getHp()
    except Exception:
        return getattr(o, 'Hp', None)


def levelOf(o):
    try:
        return o.getLevel()
    except Exception:
        return getattr(o, 'level', 0) or 0


STICK_R = 2600.0        # a target this close is fought on (beyond it the hunt sails a route to it, not broadsides)


def pickTarget(good, tgt):
    """Pure. (dist, ship) to fight from good [(dist, ship)] nearest first: the current target while it is still a
    match within STICK_R, else the nearest. FLAGSHIP1 (11-22): a nearer flagship (Navy Kingfisher, 1200 hp) took the
    target for one broadside while the French Shadow Crow sat at 600/2500, one broadside from crippled; 15 s later
    the bot swung back and our sloop sank 3 s after."""
    for d, o in good:
        if o.doId == tgt and d <= STICK_R:
            return d, o
    return good[0]


def matches(task, o):
    """(ok, why): would sinking ship o credit this task? The server's own tests, in its order."""
    from pirates.quest.QuestConstants import getShipList
    f = factionOf(o)
    if f is None:
        return False, 'no faction (team %s)' % getattr(o, 'shipClass', None)
    tf = getattr(task, 'faction', None)
    if tf is not None and not f.isA(tf):
        return False, 'faction'
    hull = getattr(task, 'hull', None)
    if hull is not None:
        lst = getShipList(hull)
        if lst and getattr(o, 'shipClass', None) not in lst:
            return False, 'hull %s not in %s' % (getattr(o, 'shipClass', None), hull)
    lvl = getattr(task, 'level', 0) or 0
    if lvl > 0 and levelOf(o) < lvl:
        return False, 'level %s < %s' % (levelOf(o), lvl)
    if getattr(task, 'isFlagship', False) and not getattr(o, 'isFlagship', False):
        return False, 'not a flagship'
    return True, 'ok'


def npcShips(H, ship):
    """[(dist, ship)] nearest first: every NPC ship within SEE_R that is still afloat."""
    p = ship.getPos(H.render)
    out = []
    for o in list(H.cr.doId2do.values()):
        if o is ship or 'NPCShip' not in cls(o) or not hasattr(o, 'getPos'):
            continue
        try:
            d = (o.getPos(H.render) - p).length()
        except Exception:
            continue
        h = hpOf(o)
        if d < SEE_R and (h is None or h > 0):
            out.append((d, o))
    out.sort(key=lambda t: t[0])
    return out


def prog(H, qid):
    """[(progress, attempts)] of quest qid's tasks, or None once the quest is gone (handed in / skipped)."""
    for q in H.la.getQuests():
        if q.getQuestId() == qid:
            try:
                return [(getattr(s, 'progress', None), getattr(s, 'attempts', None)) for s in q.getTaskStates()]
            except Exception:
                return []
    return None


def bearing(H, ship, target):
    """Degrees of target off our bow, + = starboard (right, +x in the ship's frame)."""
    rel = ship.getRelativePoint(H.render, target)
    return math.degrees(math.atan2(rel[0], rel[1]))


def broadsideKeys():
    """{skillId: key} for the broadsides the combat tray binds while steering (available = rank >= 2)."""
    from pirates.uberdog.UberDogGlobals import InventoryType
    from pirates.piratesgui import RadialMenu
    out = {}
    try:
        skills = RadialMenu.getAllSkills(InventoryType.SailingRep, 2)
    except Exception:
        return out
    for i, s in enumerate(skills):
        if s[0] in (InventoryType.SailBroadsideLeft, InventoryType.SailBroadsideRight) and s[1]:
            out[s[0]] = '%d' % (i + 1)
    return out


def recharging(H, skillId):
    try:
        t = H.la.skillDiary.getTimeRemaining(skillId)
    except Exception:
        return False
    return bool(t)


def linedUp(H, ship, foe, brg):
    """Which broadside skill the game would aim at foe now: the game's own check (side 1 = right broadside,
    side 0 = left, DistributedShip.useSkill), else from our bearing when the check cannot run."""
    from pirates.uberdog.UberDogGlobals import InventoryType as IT
    try:
        if getattr(ship, 'lookAtDummy', None) is not None:
            if ship.checkBroadsideAlignment(foe, 1):
                return IT.SailBroadsideRight
            if ship.checkBroadsideAlignment(foe, 0):
                return IT.SailBroadsideLeft
            return None
    except Exception:
        pass
    if 65 < abs(brg) < 115:
        return IT.SailBroadsideRight if brg > 0 else IT.SailBroadsideLeft
    return None


def sideName(skillId):
    from pirates.uberdog.UberDogGlobals import InventoryType as IT
    return 'right' if skillId == IT.SailBroadsideRight else 'left'


def wantBearing(d, brg):
    """Bearing to hold the foe at: abeam (90) on the side it is on, closing in from far (60) and opening out when
    too close (120)."""
    k = max(-30.0, min(30.0, (d - 900.0) / 20.0))
    return math.copysign(90.0 - k, brg if brg else 1.0)


def turnKeys(keys, brg, want, dead=8.0):
    """Hold A / D so the foe's bearing moves toward want. Turning right (D) makes every bearing smaller, turning left
    (A) larger: a foe at +60 that we want at +90 needs A."""
    keys.set('a', brg < want - dead)
    keys.set('d', brg > want + dead)


def obstacles(skip=()):
    return [(x, y, sailing.OBST_R if n else 900) for u, (n, x, y, f) in sailing.islands().items() if u not in skip]


def payRepair(H):
    """Generator. Our ship is sunk and the pirate cannot pay the shipwright: the one place a magic word stands in
    (a player this far into the story has quest gold). Logged MW-GOLD."""
    la = H.la
    try:
        sid = list(la.getInventory().getShipDoIdList())[0]
    except Exception:
        return
    ov = H.cr.getOwnerView(sid)
    hp = getattr(ov, 'Hp', None)
    if hp is None or hp > 0:
        return
    from pirates.ship import ShipGlobals
    cost, gold = ShipGlobals.getRepairCost(ov), la.getInventory().getGoldInPocket()
    if gold >= cost:
        return
    if hasattr(ShipGlobals, 'getRepairPrice') and ShipGlobals.getRepairPrice(cost, gold) == 0:
        # server-tree 0156 (11-18): the shipwright repairs a broke pirate free; no magic word
        H.ev('REPAIR-FREE', ship=sid, gold=gold, cost=cost)
        return
    if os.environ.get('STORY_PLAYER') == '1':
        H.ev('REPAIR-SHORT', ship=sid, gold=gold, cost=cost, why='a player bot never uses the gold magic word')
        return
    H.ev('MW-GOLD', why='our ship is sunk and the test pirate cannot pay its repair', ship=sid, gold=gold, cost=cost)
    H.mw('gold %d' % (gold + cost + 500))
    yield ('until', lambda: la.getInventory().getGoldInPocket() >= cost, 10, 'repair gold')


def launchShip(H):
    """Generator: the ship with the pirate at the wheel (launching it at this island's dinghy first), or None."""
    aboard = sailing.onShip(H)
    here = sailing.hereUid(H)
    if not aboard and here is None:
        H.ev('SAIL-FAIL', why='not on an open island or aboard', area=H.area())
        return None
    if not aboard:
        yield from payRepair(H)
    try:
        ship = yield from sailing.launch(H, here, aboard)
    except RuntimeError as e:
        H.ev('SAIL-FAIL', why=str(e))
        return None
    return ship


def hunt(H, qid, task, secs):
    """Generator. Sail out and sink ships that match task until the quest's progress changes, our ship sinks, or
    secs pass. -> 'credit' / 'complete' / 'our-ship-sunk' / 'timeout' / 'launch-failed' / 'left-ship'."""
    la, R = H.la, H.render
    home = sailing.hereUid(H)
    ship = yield from launchShip(H)
    if ship is None:
        return 'launch-failed'
    sid = ship.doId
    keys = Keys(H)
    tbl = sailing.islands()
    obst = obstacles()
    if home is None or home not in tbl:      # set out from the sea: patrol round the nearest island
        p = ship.getPos(R)
        home = min(tbl, key=lambda u: (tbl[u][1] - p[0]) ** 2 + (tbl[u][2] - p[1]) ** 2)
    hx, hy = tbl[home][1], tbl[home][2]
    bkeys = broadsideKeys()
    p0 = prog(H, qid)
    H.ev('SHIP-HUNT', q=qid, task=type(task).__name__, faction=str(getattr(task, 'faction', None)),
         hull=getattr(task, 'hull', None), level=getattr(task, 'level', 0), home=home, ship=sid,
         hp=getattr(ship, 'Hp', None), broadsides=bkeys, prog=p0)
    if not bkeys:
        H.ev('NO-BROADSIDE', why='the pirate has no broadside skill at rank 2+: it rams instead')
    messenger.send('w'); messenger.send('w-up')      # tap W: full sail
    t0 = time.time()
    seen, tgt, fired, sunk, lost = {}, None, 0, 0, 0
    pi = None               # job 43: index into PATROL_PTS
    leg = math.atan2(ship.getPos(R)[1] - hy, ship.getPos(R)[0] - hx)
    why = 'timeout'
    try:
        while time.time() - t0 < secs:
            if H.cr.doId2do.get(sid) is None or la.getGameState() != 'ShipPilot':
                why = 'our-ship-sunk' if (hpOf(ship) or 0) <= 0 else 'left-ship'
                H.ev('OUR-SHIP-SUNK' if why == 'our-ship-sunk' else 'left-ship', q=qid, gs=la.getGameState(),
                     hp=hpOf(ship), area=H.area())
                break
            pn = prog(H, qid)
            if pn != p0:
                why = 'complete' if pn is None else 'credit'
                H.ev('SHIP-CREDIT', q=qid, before=p0, after=pn, sunk=sunk, fired=fired, secs=round(time.time() - t0))
                break
            p = ship.getPos(R)
            fl = npcShips(H, ship)
            good = []
            for d, o in fl:
                ok, w = matches(task, o)
                if o.doId not in seen:
                    seen[o.doId] = ok
                    H.ev('ship-seen', doId=o.doId, foeName=getattr(o, 'name', ''), shipClass=getattr(o, 'shipClass', None),
                         faction=str(factionOf(o)), level=levelOf(o), match=ok, why=w, dist=round(d))
                if ok:
                    good.append((d, o))
            if tgt is not None and (H.cr.doId2do.get(tgt) is None or (hpOf(H.cr.doId2do[tgt]) or 0) <= 0):
                gone = H.cr.doId2do.get(tgt) is None
                off = sailedOff(LOST, tgt, gone)
                if off:
                    lost += 1
                    H.ev('FOE-LOST', foe=tgt, gone=gone, fired=fired, last=None if off is True else off, prog=prog(H, qid))
                else:
                    sunk += 1
                    H.ev('FOE-SUNK', foe=tgt, gone=gone, fired=fired, prog=prog(H, qid))
                tgt = None
            if good:
                d, foe = pickTarget(good, tgt)
                if foe.doId != tgt:
                    tgt = foe.doId
                    H.ev('SHIP-TARGET', foe=tgt, foeName=getattr(foe, 'name', ''), dist=round(d), hp=hpOf(foe))
                fp = foe.getPos(R)
                brg = bearing(H, ship, fp)
                if not bkeys:      # ram: straight at it at full sail
                    keys.steer(ship, fp)
                    if d < 300 and time.time() - seenT(seen, 'ramT') > 10:
                        seen['ramT'] = time.time()
                        H.ev('RAM', foe=tgt, dist=round(d), hp=hpOf(foe), ourHp=hpOf(ship))
                elif d > 2600:
                    tp, mode = sailing.route(p, fp, obst)
                    keys.steer(ship, tp)
                else:
                    turnKeys(keys, brg, wantBearing(d, brg))
                    sk = linedUp(H, ship, foe, brg) if d < FIRE_R else None
                    if sk in bkeys and not recharging(H, sk) and time.time() - seenT(seen, ('fireT', sk)) > 3:
                        seen[('fireT', sk)] = time.time()      # one press per side per 3 s, even if the game ignores it
                        k = bkeys[sk]
                        messenger.send(k); messenger.send(k + '-up')
                        fired += 1
                        H.ev('BROADSIDE', foe=tgt, side=sideName(sk), key=k, dist=round(d),
                             brg=round(brg), foeHp=hpOf(foe), ourHp=hpOf(ship))
            elif PATROL_PTS:
                # job 43: nobody worth sinking in view: sail the caller's search route, one point after another
                if pi is None:
                    pi = nearestPt(PATROL_PTS, p)
                    H.ev('SEARCH-ROUTE', q=qid, pts=len(PATROL_PTS), first=list(PATROL_PTS[pi]))
                pi = nextPt(PATROL_PTS, pi, p, LEG_R)
                if pi != seen.get('legPi'):
                    seen['legPi'] = pi
                    H.ev('SEARCH-LEG', q=qid, n=pi, to=list(PATROL_PTS[pi]), at=[round(p[0]), round(p[1])])
                gp = Point3(PATROL_PTS[pi][0], PATROL_PTS[pi][1], 0)
                tp, mode = sailing.route(p, gp, obst)
                keys.steer(ship, tp)
            else:
                # nobody worth sinking in view: patrol a ring round the home island, 45 degrees a leg
                gp = Point3(hx + PATROL_R * math.cos(leg), hy + PATROL_R * math.sin(leg), 0)
                if (Vec3(p[0] - gp[0], p[1] - gp[1], 0)).length() < 1500:
                    leg += math.pi / 4
                    gp = Point3(hx + PATROL_R * math.cos(leg), hy + PATROL_R * math.sin(leg), 0)
                tp, mode = sailing.route(p, gp, obst)
                keys.steer(ship, tp)
            if time.time() - seen.get('beatT', t0) >= 60:
                # DOLL7 (11-21): the patrol ring logs nothing, so 240 s of quiet sailing tripped the walker's HANG kill.
                # One line a minute; 'moved' shows a ship stuck on a rock (a real hang) apart from a long search
                b0 = seen.get('beatP')
                seen['beatT'], seen['beatP'] = time.time(), (p[0], p[1])
                H.ev('hunt-beat', q=qid, at=[round(p[0]), round(p[1])], tgt=tgt, seen=len([k for k in seen if isinstance(k, int)]),
                     moved=None if b0 is None else round(math.hypot(p[0] - b0[0], p[1] - b0[1])),
                     leg=round(math.degrees(leg)) if not PATROL_PTS else pi, secs=round(time.time() - t0))
            yield 0.5 if tgt is not None else 1.0
    except GeneratorExit:
        why = 'stopped'      # the caller (SHIPFIGHT) stopped it, e.g. after FOE-SUNK: still say what it counted
        raise
    finally:
        keys.release()
        H.ev('SHIP-HUNT-END', q=qid, why=why, seen=len([k for k in seen if isinstance(k, int)]),
             matching=sum(1 for k, v in seen.items() if isinstance(k, int) and v), sunk=sunk, lost=lost, fired=fired,
             secs=round(time.time() - t0), prog=prog(H, qid))
    return why


def nearestPt(pts, p):
    """Pure, job 43: the index of the point in pts [(x, y, ...)] nearest p."""
    return min(range(len(pts)), key=lambda i: (pts[i][0] - p[0]) ** 2 + (pts[i][1] - p[1]) ** 2)


def nextPt(pts, i, p, r):
    """Pure, job 43: i, or the next point round once p is within r ft of point i."""
    if math.hypot(pts[i][0] - p[0], pts[i][1] - p[1]) < r:
        return (i + 1) % len(pts)
    return i


def sailedOff(lostFn, foe, gone):
    """Pure. A target that left the client's view (gone) and that lostFn says only sailed off -> what lostFn knew
    (truthy), else False (it sank: at 0 hp, or gone with no reason to think otherwise)."""
    if not gone or lostFn is None:
        return False
    try:
        return lostFn(foe) or False
    except Exception:
        return False


def seenT(seen, k):
    return seen.get(k, 0)


def dockTarget(H, task):
    """(island uid, how) for a dock task: 'redock' when standing on (or sailing at) a port in the task's location
    list, else the nearest one by sea. (None, why) when no listed port is in the world."""
    from pirates.quest.QuestConstants import getLocationList
    loc = task.getLocation() if hasattr(task, 'getLocation') else getattr(task, 'location', None)
    tbl = sailing.islands()
    ports = [u for u in (getLocationList(loc) or (loc,)) if u in tbl]
    if not ports:
        return None, 'no island of %s in the world' % loc
    here = sailing.hereUid(H)
    if here in ports:
        return here, 'redock'
    obj = H.la.getParentObj() if sailing.onShip(H) else H.la
    p = obj.getPos(H.render)
    u = min(ports, key=lambda u: (tbl[u][1] - p[0]) ** 2 + (tbl[u][2] - p[1]) ** 2)
    return u, 'nearest of %d' % len(ports)


def dock(H, uid, qid):
    """Generator. Drop anchor at island uid like a player. Standing on it already: launch, sail out past its port
    sphere (the anchor button goes away), then come back and dock. -> True when docked (LandRoam on uid)."""
    la, R = H.la, H.render
    tbl = sailing.islands()
    p0 = prog(H, qid)
    H.ev('DOCK-START', q=qid, to=uid, isl=tbl.get(uid, ('?',))[0], here=sailing.hereUid(H), aboard=sailing.onShip(H), prog=p0)
    if sailing.hereUid(H) == uid:
        ship = yield from launchShip(H)
        if ship is None:
            H.ev('DOCK-END', q=qid, ok=False, why='launch failed'); return False
        keys = Keys(H)
        messenger.send('w'); messenger.send('w-up')
        cx, cy = tbl[uid][1], tbl[uid][2]
        t0 = time.time()
        while time.time() - t0 < 240:
            if H.cr.doId2do.get(ship.doId) is None or la.getGameState() != 'ShipPilot':
                keys.release()
                H.ev('DOCK-END', q=qid, ok=False, why='left the ship on the way out', gs=la.getGameState()); return False
            p = ship.getPos(R)
            out = Vec3(p[0] - cx, p[1] - cy, 0)
            if out.length() > DOCK_OUT and not anchorShown(ship):
                break
            if out.length() < 1:
                out = Vec3(0, 1, 0)
            out.normalize()
            tp, mode = sailing.route(p, Point3(cx + out[0] * (DOCK_OUT + 2000), cy + out[1] * (DOCK_OUT + 2000), 0),
                                     obstacles(skip=(uid,)))
            keys.steer(ship, tp)
            yield 1.0
        keys.release()
        p = ship.getPos(R)
        H.ev('DOCK-OUT', q=qid, dist=round((Vec3(p[0] - cx, p[1] - cy, 0)).length()), anchor=anchorShown(ship),
             secs=round(time.time() - t0))
    elif not sailing.onShip(H):
        yield from payRepair(H)
    yield from sailing.sail_to(H, uid, why=qid)
    ok = bool(H.sailResult)
    H.ev('DOCK-END', q=qid, ok=ok, here=sailing.hereUid(H), before=p0, after=prog(H, qid))
    return ok
