"""ISLAND1 (pir-quests, 11-17): one ship and three islands, like a player, logging each hop.

  hop 1, the sea: walk to the Port Royal shipwright and buy his cheapest ship (Ships button -> the Pirate Sloop ->
    Purchase -> the name panel's own pick), or use the ship he has; then sailing.sail_to(Tortuga) (pir-bot's
    sail: dinghy, wheel, full sail, dock lap, anchor) across the x=6000 line where ships used to be deleted
    (pir-ships diff 02 / patch 0076), dock, and walk ashore to Tortuga's open ground.
  hop 2, the map: Tortuga -> Port Royal with the map's own call (teleportMgr.requestTeleportToIsland).
  hop 3, the map: Port Royal -> Padres del Fuego, the same way.
  A refused map teleport falls back to the server message the map sends for islands the client lacks
  (sendUpdate('requestTeleportToIsland')), then to the areaTeleport magic word so the next hop can still run; each
  fallback is logged and the run is then a FAIL (it shows which way got him there).

After each hop: HOP n= how= frm= to= ok= secs= area= gs= npcs= npcsAll= byClass= wdTownsfolk= stall=, with
the NPC count taken on landing and again SETTLE s later (interest fills in as he stands there).
A STALL line is written when a leg makes no progress (no TeleportOut in 30 s, no landing in HOP_SECS, the walk
ashore stuck), with the last game state and area.

Lines: ISLAND1-START, STAGE step=island1 what=at-port-royal / at-shipwright / menu / ship-store / name-panel /
bought / have-ship / sailing / docked / ashore, SHIP-BUY, SHIP-RESPONSE result=, SHIP-BOUGHT, CROSS-X6000,
CROSSED-X6000 ok=, sailing's own lines (SAIL-START ... SAILED ok=), ASHORE, HOP-GO, HOP-REFUSED, HOP-FALLBACK,
hop-tick (every 10 s while waiting), STALL, HOP, ISLAND1-SUMMARY, then PASS or FAIL.

env: ISLAND1_BUY (auto: buy only when he has no ship; 1: always try; 0: never), ISLAND1_GOLD=1 (the one magic word
'gold <n>' when he cannot pay 100 gold, logged MW-GOLD), ISLAND1_HOPS (default PR,PADRES: the teleports after the
sail), ISLAND1_HOP_SECS (120), ISLAND1_SETTLE (20), ISLAND1_PAST (120: s to watch past x=6000).
Never runs on pirate 100000170. Run with ROUTE_TEST=1 so FAST_START does not warp the walks or skip the sail."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__', '.'))))
import sailing   # noqa: E402
import s_story   # noqa: E402
import s_lanes   # noqa: E402

PR, TORTUGA = s_lanes.PR, s_lanes.TORTUGA
PADRES = '1142018473.22dxschafe'
NAMES = {PR: 'Port Royal', TORTUGA: 'Tortuga', PADRES: 'Padres Del Fuego'}
BY_KEY = {'PR': PR, 'TORTUGA': TORTUGA, 'PADRES': PADRES}
BANNED = (100000170,)                 # his own pirate: never
CROSS_X = 6000.0
ASHORE_POS = (-90.7, 4.1, 11.6)       # Tortuga's open ground (the gypsy's spot, s_shop 'tgypsy'), Tortuga's frame
ASHORE_MIN = 25.0                     # ft walked from where he landed: "ashore", off the dock
ASHORE_ARRIVE = 8.0                   # goto's arrive radius at ASHORE_POS
ASHORE_NEAR = 12.0                    # within this of ASHORE_POS (arrive + 4 ft) counts as ashore however short the walk:
                                      # NEWP9-NP3 docked only 29 ft away, so 25 ft walked was impossible (job 13)


def ashoreJudge(r, walked, left):
    """Pure: (ok, why) for the walk ashore. r = walkTo's result (None = it stalled), walked = ft from where he landed,
    left = ft still to ASHORE_POS in Tortuga's frame (None when Tortuga's area node is not found)."""
    if r is None:
        return False, 'stalled'
    if left is not None and left <= ASHORE_NEAR:
        return True, 'reached'
    if walked >= ASHORE_MIN:
        return True, 'walked'
    return False, 'short'

BUY = os.environ.get('ISLAND1_BUY', 'auto').lower()
WANT_GOLD = os.environ.get('ISLAND1_GOLD', '0') == '1'
HOPS = [BY_KEY[k.strip().upper()] for k in os.environ.get('ISLAND1_HOPS', 'PR,PADRES').split(',') if k.strip()]
HOP_SECS = float(os.environ.get('ISLAND1_HOP_SECS', '120'))
SETTLE = float(os.environ.get('ISLAND1_SETTLE', '20'))
PAST = float(os.environ.get('ISLAND1_PAST', '120'))
TALK = 8.0                            # ft: inside the townfolk's 12 ft interact sphere
FIND_R = 40.0                         # ft round his world-data spot: the live shipwright


# ---- pure helpers (tested offline by test_island1.py) ----

class CrossWatch:
    """The x=6000 line: feed(x, t) each tick while sailing; deleted(t) when the ship is deleted. A crossing is the
    first tick on the other side of CROSS_X from the first tick seen."""

    def __init__(self, line=CROSS_X):
        self.line, self.side0, self.tCross, self.xCross, self.tLast, self.tDel = line, None, None, None, None, None

    def feed(self, x, t):
        """-> True on the tick that crosses the line (once)."""
        side = x >= self.line
        self.tLast = t
        if self.side0 is None:
            self.side0 = side
            return False
        if self.tCross is None and side != self.side0:
            self.tCross, self.xCross = t, x
            return True
        return False

    def deleted(self, t, docked=False):
        # docked: the anchor was down at a port (dropping anchor puts the ship away; ISLAND1 11-17 read that as a loss)
        if self.tDel is None:
            self.tDel, self.docked = t, docked

    def past(self):
        """s sailed past the line (to the last tick, or to the delete), or None before the crossing."""
        if self.tCross is None:
            return None
        end = self.tDel if self.tDel is not None else self.tLast
        return round(end - self.tCross, 1)

    def verdict(self, arrived, need=PAST):
        """(ok, why): crossed, no ship delete after it, and either PAST s beyond the line or docked at the far side."""
        if self.tCross is None:
            return False, 'never crossed x=%d' % self.line
        if self.tDel is not None and self.tDel >= self.tCross and getattr(self, 'docked', False):
            return True, 'crossed, %.1f s past the line, ship put away at the dock' % self.past()
        if self.tDel is not None and self.tDel >= self.tCross:
            return False, 'ship deleted %.1f s past x=%d' % (self.tDel - self.tCross, self.line)
        if self.past() >= need or arrived:
            return True, 'crossed, %.1f s past the line, ship kept' % self.past()
        return False, 'crossed but only %.1f s past the line (want %d, or the dock)' % (self.past(), need)


NPC_PREFIX = ('DistributedNPC', 'DistributedBoss', 'DistributedAnimal', 'DistributedCreature', 'DistributedKillerGhost',
              'DistributedGhost')


def isNpcClass(name):
    return bool(name) and name.startswith(NPC_PREFIX) and 'Manager' not in name


def census(rows):
    """rows = [(class name, under this island)] -> (npcs under the island, all npcs in interest, {class: n under})."""
    under, every, by = 0, 0, {}
    for c, u in rows:
        if not isNpcClass(c):
            continue
        every += 1
        if u:
            under += 1
            by[c] = by.get(c, 0) + 1
    return under, every, by


def hopVerdict(h):
    """(ok, why) for one HOP record: landed on the right island by the way asked, no stall, NPCs there."""
    if h.get('stall'):
        return False, 'stall: %s' % h['stall']
    if not h.get('ok'):
        return False, 'did not land on %s' % h.get('to')
    if h.get('how') not in ('sail', 'map'):
        return False, 'got there only by %s (the map teleport was refused)' % h.get('how')
    if not h.get('npcs'):
        return False, 'no NPCs on %s after %d s' % (h.get('to'), SETTLE)
    return True, 'ok'


# ---- the run ----

def run(H):
    from pirates.piratesgui import PiratesGuiGlobals
    from pirates.distributed import InteractGlobals
    from pirates.uberdog.UberDogGlobals import InventoryCategory
    from pirates.piratesbase import PiratesGlobals
    from pirates.economy import EconomyGlobals
    la, cr = H.la, H.cr
    SLOOP = EconomyGlobals.ItemId.INTERCEPTOR_L1     # the Pirate Sloop, 100 gold: one of the two a non-payer may buy

    yield ('until', lambda: la.getGameState() in ('LandRoam', 'ShipPilot', 'WaterRoam'), 60, 'LandRoam')
    if la.doId in BANNED:
        H.ev('FAIL', why='ISLAND1 never runs on this pirate (his own)', pirate=la.doId); return

    warnings = []
    origWarn = la.guiMgr.createWarning

    def warn(msg, *a, **k):
        warnings.append(str(msg)[:120])
        return origWarn(msg, *a, **k)
    la.guiMgr.createWarning = warn

    def tokens():
        out = {}
        for u in NAMES:
            try:
                out[NAMES[u]] = bool(la.hasIslandTeleportToken(u))
            except Exception:
                out[NAMES[u]] = None
        return out

    def ships():
        try:
            return list(la.getInventory().getShipDoIdList())
        except Exception:
            return []

    def under(o, isl):
        p = o
        for _ in range(8):
            try:
                p = p.getParentObj()
            except Exception:
                return False
            if p is None:
                return False
            if p is isl:
                return True
        return False

    def npcCount(uid):
        isl = sailing.islandObj(H, uid)
        rows = [(type(o).__name__, isl is not None and under(o, isl)) for o in list(cr.doId2do.values())]
        n, every, by = census(rows)
        try:
            wd = len([1 for k, o in sailing._islandChildren(uid) if o.get('Type') == 'Townsperson'])
        except Exception:
            wd = None
        return dict(npcs=n, npcsAll=every, byClass=by, wdTownsfolk=wd)

    hops = []

    def hopLine(n, how, frm, to, ok, t0, stall=None, **kw):
        """Generator: the NPC census on landing and SETTLE s later, then the HOP line. -> the record."""
        rec = dict(n=n, how=how, frm=NAMES.get(frm, frm), to=NAMES.get(to, to), ok=ok, secs=round(time.time() - t0, 1),
                   stall=stall, **kw)
        if ok:
            first = npcCount(to)
            yield SETTLE
            rec.update(npcCount(to))
            rec['npcsAtLanding'] = first['npcs']
        rec.update(area=H.area(), gs=la.getGameState(), tokens=tokens())
        H.ev('HOP', **rec)
        hops.append(rec)
        return rec

    def waitFor(n, cond, secs, what):
        """Generator: poll cond every 0.5 s for secs, a hop-tick every 10 s. -> True when it held."""
        t0 = time.time()
        tick = t0
        while time.time() - t0 < secs:
            if cond():
                return True
            if time.time() - tick >= 10:
                tick = time.time()
                H.ev('hop-tick', n=n, waiting=what, secs=round(tick - t0), gs=la.getGameState(), area=H.area(),
                     inTeleport=_inTp())
            yield 0.5
        return cond()

    def _inTp():
        try:
            return bool(cr.teleportMgr.amInTeleport())
        except Exception:
            return None

    H.ev('ISLAND1-START', pirate=la.doId, gold=s_lanes.gold(H), ships=ships(), buy=BUY, hops=[NAMES[u] for u in HOPS],
         tokens=tokens(), area=H.area(), gs=la.getGameState(), tut=la.style.getTutorial())

    # ---- hop 1: the shipwright, the sea, Tortuga ----
    t1 = time.time()
    if not (yield from s_lanes.onIsland(H, 'island1', PR)):
        H.ev('FAIL', why='could not get to Port Royal to start', area=H.area()); return
    s_lanes.stage(H, 'island1', 'at-port-royal')

    want = BUY == '1' or (BUY == 'auto' and not ships())
    if not want:
        if not ships():
            H.ev('FAIL', why='ISLAND1_BUY=0 and he has no ship'); return
        s_lanes.stage(H, 'island1', 'have-ship', ships=ships())
    else:
        bought = yield from buyShip(H, la, cr, SLOOP, ships, warnings, PiratesGuiGlobals, InteractGlobals,
                                    InventoryCategory, PiratesGlobals, EconomyGlobals)
        if not bought:
            return

    # sail, watching the x=6000 line on the side
    cw = CrossWatch()
    oDel = cr.deleteObject

    def delHook(doId, *a, **k):
        if doId in ships():
            port = la.getPort()
            cw.deleted(time.time(), docked=bool(port))
            o = cr.doId2do.get(doId)
            H.ev('CROSS-SHIP-DELETED', doId=doId, pos=H.P(o) if o is not None else None, past=cw.past(), port=port)
        return oDel(doId, *a, **k)
    cr.deleteObject = delHook
    sense = s_story.SeaSense(H, 'island1')       # pir-bot's steering round enemy ships, as s_story's sails use
    sailing.route = sense.route
    s_lanes.stage(H, 'island1', 'sailing', to=NAMES[TORTUGA])
    gen = sailing.sail_to(H, TORTUGA, why='island1')
    try:
        while True:
            shp = la.getParentObj() if sailing.onShip(H) else None     # the ship he stands on (the one sailing)
            if shp is not None and la.getGameState() == 'ShipPilot':
                p = shp.getPos(H.render)
                if cw.feed(p[0], time.time()):
                    H.ev('CROSS-X6000', x=round(p[0], 1), y=round(p[1], 1), zone=getattr(shp, 'zoneId', None),
                         parent=getattr(shp, 'parentId', None), hp=getattr(shp, 'Hp', None))
            try:
                y = next(gen)
            except StopIteration:
                break
            yield y
    finally:
        sailing.route = sense.orig
        cr.deleteObject = oDel
    arrived = bool(H.sailResult)
    cok, cwhy = cw.verdict(arrived)
    H.ev('CROSSED-X6000', ok=cok, why=cwhy, xAt=cw.xCross, past=cw.past(), deleted=cw.tDel is not None)
    stall = None
    if not arrived:
        stall = 'the sail to Tortuga did not end on Tortuga (see SAIL-FAIL)'
        H.ev('STALL', n=1, what=stall, gs=la.getGameState(), area=H.area())
    else:
        s_lanes.stage(H, 'island1', 'docked', at=NAMES[TORTUGA])
        p0 = la.getPos(H.render)
        r = yield from s_lanes.walkTo(H, 'island1', lambda st: s_story.goto(H, st, TORTUGA, pos=ASHORE_POS,
                                                                             arrive=ASHORE_ARRIVE, tag='ashore'),
                                      150, 'Tortuga open ground')
        walked = round((la.getPos(H.render) - p0).length(), 1)
        from panda3d.core import Point3
        ao = s_story.areaObj(H, TORTUGA)
        left = None if ao is None else round((la.getPos(ao) - Point3(*ASHORE_POS)).length(), 1)
        aok, awhy = ashoreJudge(r, walked, left)
        H.ev('ASHORE', ok=aok, why=awhy, walked=walked, left=left, la=H.P(la), area=H.area())
        if not aok:
            stall = 'walk ashore at Tortuga stuck after %.1f ft (%s ft left, %s)' % (walked, left, awhy)
        else:
            s_lanes.stage(H, 'island1', 'ashore', walked=walked)
    yield from hopLine(1, 'sail', PR, TORTUGA, arrived and sailing.hereUid(H) == TORTUGA, t1, stall=stall,
                       cross=cwhy, crossOk=cok)

    # ---- hops 2..: the map ----
    for i, tgt in enumerate(HOPS):
        n = i + 2
        frm = sailing.hereUid(H)
        t0 = time.time()
        if la.getGameState() != 'LandRoam' or frm is None:
            H.ev('STALL', n=n, what='not standing on an island before the teleport', gs=la.getGameState(), area=H.area())
            yield from hopLine(n, 'none', frm, tgt, False, t0, stall='not on an island before the teleport')
            break
        if frm == tgt:
            H.ev('HOP-SKIP', n=n, why='already on %s' % NAMES[tgt]); continue
        yield 3                                   # a player looks at the map before he clicks
        isl = None
        try:
            isl = cr.getDo(cr.uidMgr.getDoId(tgt))
        except Exception:
            pass
        allows = None
        try:
            allows = bool(la.confirmIslandTeleport('from', islandUid=tgt))
        except Exception as e:
            allows = 'err %s' % e
        k = len(warnings)
        how = 'map'
        H.ev('HOP-GO', n=n, how=how, frm=NAMES.get(frm, frm), to=NAMES[tgt], uid=tgt, mapAllows=allows,
             path='local' if isl is not None and isl.getParentObj() is cr.activeWorld else 'server',
             canTeleport=la.canTeleport(), tokens=tokens())
        cr.teleportMgr.requestTeleportToIsland(tgt)

        def going():
            return la.getGameState() == 'TeleportOut' or _inTp() or sailing.hereUid(H) == tgt
        started = yield from waitFor(n, going, 30, 'TeleportOut (%s)' % how)
        if not started:
            H.ev('HOP-REFUSED', n=n, how=how, said=warnings[k:], canTeleport=la.canTeleport(), gs=la.getGameState())
            how = 'server'
            H.ev('HOP-FALLBACK', n=n, how=how, to=NAMES[tgt])
            cr.teleportMgr.sendUpdate('requestTeleportToIsland', [tgt])
            started = yield from waitFor(n, going, 30, 'TeleportOut (%s)' % how)
        if not started:
            H.ev('HOP-REFUSED', n=n, how=how, said=warnings[k:], gs=la.getGameState())
            how = 'mw'
            H.ev('HOP-FALLBACK', n=n, how=how, to=NAMES[tgt], why='areaTeleport so the next hop can still run')
            H.mw('areaTeleport %s' % tgt)
        landed = yield from waitFor(n, lambda: sailing.hereUid(H) == tgt and la.getGameState() == 'LandRoam', HOP_SECS,
                                    'landing on %s (%s)' % (NAMES[tgt], how))
        stall = None
        if not landed:
            stall = 'no landing on %s in %d s (%s)' % (NAMES[tgt], HOP_SECS, how)
            H.ev('STALL', n=n, what=stall, gs=la.getGameState(), area=H.area(), here=sailing.hereUid(H),
                 inTeleport=_inTp(), said=warnings[k:])
        yield from hopLine(n, how, frm, tgt, landed, t0, stall=stall, said=warnings[k:])
        if not landed:
            break

    # ---- verdict ----
    bad = []
    for h in hops:
        ok, why = hopVerdict(h)
        if not ok:
            bad.append('hop %d %s->%s: %s' % (h['n'], h['frm'], h['to'], why))
    if not cok:
        bad.append('x=6000: ' + cwhy)
    if len(hops) < 1 + len(HOPS):
        bad.append('only %d of %d hops ran' % (len(hops), 1 + len(HOPS)))
    H.ev('ISLAND1-SUMMARY', hops=[dict((k, h.get(k)) for k in ('n', 'how', 'frm', 'to', 'ok', 'secs', 'npcs', 'npcsAll',
                                                                  'wdTownsfolk', 'stall')) for h in hops],
         cross=cwhy, ships=ships(), gold=s_lanes.gold(H))
    if bad:
        H.ev('FAIL', why='; '.join(bad))
    else:
        H.ev('PASS', what='ship from the Port Royal shipwright, sailed past x=6000 to Tortuga, ashore, then the map to '
             + ', '.join(NAMES[u] for u in HOPS), hops=len(hops))


def buyShip(H, la, cr, SLOOP, ships, warnings, PiratesGuiGlobals, InteractGlobals, InventoryCategory, PiratesGlobals,
            EconomyGlobals):
    """Generator: walk to the Port Royal shipwright, Ships, the sloop, Purchase, the name panel's pick. -> True."""
    from panda3d.core import Point3
    spots = sailing.shipwrightSpots(PR)
    if not spots:
        H.ev('FAIL', why='no shipwright in Port Royal world data'); return False
    inv = la.getInventory()
    limit = inv.getCategoryLimit(InventoryCategory.SHIPS)
    tut = la.style.getTutorial()
    if len(ships()) >= limit or tut < PiratesGlobals.TUT_GOT_SHIP:
        H.ev('FAIL', why='the shipwright\'s Ships button is greyed out for him', ships=len(ships()), limit=limit,
             tut=tut, needTut=PiratesGlobals.TUT_GOT_SHIP); return False
    cost = EconomyGlobals.getItemCost(SLOOP)
    if s_lanes.gold(H) < cost:
        if not WANT_GOLD:
            H.ev('FAIL', why='he cannot pay %d gold for the sloop (ISLAND1_GOLD=1 gives it)' % cost, gold=s_lanes.gold(H))
            return False
        H.ev('MW-GOLD', why='the test pirate cannot pay %d for the sloop' % cost, gold=s_lanes.gold(H))
        H.mw('gold %d' % (s_lanes.gold(H) + cost + 10))
        yield ('until', lambda: s_lanes.gold(H) >= cost, 10, 'gold')
    org = s_story.areaObj(H, PR)
    me = la.getPos(H.render)
    pts = [H.render.getRelativePoint(org, Point3(*p)) if org is not None else Point3(*p) for p in spots]
    k = min(range(len(spots)), key=lambda i: (pts[i] - me).length())
    spot, pt = spots[k], pts[k]
    H.ev('SHIPWRIGHT-SPOT', spot=[round(v, 1) for v in spot], d=round((pt - me).length(), 1), of=len(spots))
    r = yield from s_lanes.walkTo(H, 'island1', lambda st: s_story.goto(H, st, PR, pos=spot, arrive=TALK,
                                                                         tag='to-shipwright'), 300, 'the shipwright')
    if r is None:
        H.ev('FAIL', why='could not walk to the shipwright', la=H.P(la), area=H.area()); return False

    def wright():
        live = [o for o in sailing.shipwrights(H) if hasattr(o, 'getPos')]
        live = [o for o in live if (o.getPos(H.render) - pt).length() < FIND_R]
        return min(live, key=lambda o: (o.getPos(H.render) - pt).length()) if live else None
    yield ('until', lambda: wright() is not None, 20, 'shipwright in view')
    npc = wright()
    if npc is None:
        H.ev('FAIL', why='no live shipwright within %d ft of his spot' % FIND_R, la=H.P(la)); return False
    r = yield from s_lanes.walkTo(H, 'island1', lambda st: True if s_story.near(H, npc, TALK, st, tag='shipwright')
                                  else 'walk-to-shipwright', 60, 'the shipwright')
    if r is None:
        H.ev('FAIL', why='could not reach the shipwright', npc=npc.doId, d=round(s_story.hdist(H, npc), 1)); return False
    H.walk_cancel()
    s_lanes.stage(H, 'island1', 'at-shipwright', npc=npc.doId, name=getattr(npc, 'name', ''),
                  d=round(s_story.hdist(H, npc), 1))

    s0, g0 = ships(), s_lanes.gold(H)
    resp = {}
    orig = npc.makeSaleResponse

    def msr(result, *a):
        resp['r'] = result
        H.ev('SHIP-RESPONSE', result=result, sold=result == 2)
        return orig(result, *a)
    npc.makeSaleResponse = msr
    k = len(warnings)
    try:
        npc.requestInteraction(la.doId)
        yield ('until', lambda: la.getGameState() == 'NPCInteract' and getattr(npc, 'interactGUI', None) is not None,
               20, 'shipwright menu')
        if getattr(npc, 'interactGUI', None) is None:
            H.ev('FAIL', why='no menu after the interact (20 s)', gs=la.getGameState()); return False
        s_lanes.stage(H, 'island1', 'menu', npc=npc.doId)
        yield 1.5
        npc.selectOptionConfirm(InteractGlobals.SHIPS)
        yield ('until', lambda: getattr(npc, 'storeMenuGUI', None) is not None, 10, 'ship store')
        gui = getattr(npc, 'storeMenuGUI', None)
        if gui is None:
            H.ev('FAIL', why='Ships pressed, no ship store', gs=la.getGameState(), said=warnings[k:]); return False
        s_lanes.stage(H, 'island1', 'ship-store', store=type(gui).__name__)
        yield 1
        gui.handleBuyItem([SLOOP, 1], PiratesGuiGlobals.InventoryAdd)
        H.ev('SHIP-BUY', item=SLOOP, cost=EconomyGlobals.getItemCost(SLOOP), gold=g0,
             cart=list(gui.purchaseInventory or []))
        yield 1
        gui.handleCommitPurchase()
        yield ('until', lambda: getattr(gui, 'namePanel', None) is not None, 5, 'name panel')
        panel = getattr(gui, 'namePanel', None)
        if panel is None:
            H.ev('FAIL', why='Purchase pressed, no name panel (a warning says why)', said=warnings[k:]); return False
        s_lanes.stage(H, 'island1', 'name-panel')
        yield 2
        panel.handleCommit()                      # the panel's own pick of prefix + suffix, as a player who clicks OK
        yield ('until', lambda: 'r' in resp, 20, 'sale answer')
        yield ('until', lambda: len(ships()) > len(s0), 20, 'ship in inventory')
        H.ev('SHIP-BOUGHT', result=resp.get('r'), shipsBefore=s0, shipsAfter=ships(), goldBefore=g0,
             goldAfter=s_lanes.gold(H), said=warnings[k:])
        if resp.get('r') != 2 or len(ships()) <= len(s0):
            H.ev('FAIL', why='the shipwright did not sell the sloop (makeSaleResponse %s)' % resp.get('r'),
                 said=warnings[k:]); return False
        s_lanes.stage(H, 'island1', 'bought', ship=[s for s in ships() if s not in s0])
    finally:
        npc.makeSaleResponse = orig
        if la.getGameState() == 'NPCInteract':
            try:
                if getattr(npc, 'storeMenuGUI', None) is not None:
                    npc.storeMenuGUI.closePanel()
                npc.selectOptionConfirm(InteractGlobals.CANCEL)
            except Exception as e:
                H.ev('SHIP-LEAVE', err=repr(e))
    yield ('until', lambda: la.getGameState() == 'LandRoam', 20, 'back to LandRoam')
    return True
