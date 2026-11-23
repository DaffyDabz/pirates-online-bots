"""EVERY1 (boats lane, 11-20 night): every ship a pirate can own, played like a player, one class per run.
Host 11-20 23:0x: "make sure he can use every ship".

The ships a pirate can own come from the code: EconomyGlobals.SHIP_SHELF (the shipwright's stock), nine classes:
Light Sloop 1, Light Galleon 11, Light Frigate 21 (Sailing 0); Sloop 2, Galleon 12, Frigate 22 (Sailing 5);
War Sloop 3, War Galleon 13, War Frigate 23 (Sailing 15).

One run = one class (EVERY_CLASS). Test pirate claude2 (100000004) only. On Port Royal:
 1. Sailing level and gold by magic word when the class needs them (MW-LEVEL, MW-GOLD, logged).
 2. Buy the class at the Port Royal shipwright through his store (s_activities.buySloop works for any class id).
    Class 1 uses claude2's own Light Sloop 100000750 instead.
 3. Launch it at the dinghy and take the wheel (s_shipquest.launchShip; his ship list is reordered so this one is
    first, and put back afterwards).
 4. Sail: full sail, PASS when the ship moved SAIL_FT.
 5. Broadside: press each bound broadside key, PASS when its recharge starts (the skill went off). A class with
    maxBroadsides 0 is n/a.
 6. Deck cannon: drop sail, leave the wheel, sit on the nearest deck cannon, fire, PASS when the shot was sent to the
    server. Then off the cannon and back to the wheel. No deck cannons = n/a.
 7. Take a hit: find a Navy ship and keep alongside until our hp falls (HIT_SECS).
 8. Repair: sail clear, drop sail, leave the wheel, use a repair spot on deck, PASS when hp rises.
    No repair spot = the shipwright's repair after docking stands in (logged as how='shipwright').
 9. Dock: sail back to Port Royal and press the anchor; PASS when the ship is put away and he is ashore.
10. Sell the bought ship back at the shipwright through the game's Yes / Yes windows (gold set low first so no
    overflow), then gold and Sailing back as they were (EVERY_GOLD0, Sailing rep 0 by `level 13712 0`).
EVERYSHIP-ROW carries the row; then PASS (every part passed or n/a) or FAIL with the parts that failed.
Never touches pirate 100000170 or ship 100000173. env: EVERY_CLASS (1), EVERY_GOLD0 (27), EVERY_HIT_SECS (420),
EVERY_FIND_SECS (360), EVERY_REPAIR_SECS (150), EVERY_SAIL_FT (150)."""
import math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0])))

CLASS = int(os.environ.get('EVERY_CLASS', '1'))
GOLD0 = int(os.environ.get('EVERY_GOLD0', '27'))
HIT_SECS = float(os.environ.get('EVERY_HIT_SECS', '420'))
FIND_SECS = float(os.environ.get('EVERY_FIND_SECS', '360'))
REPAIR_SECS = float(os.environ.get('EVERY_REPAIR_SECS', '150'))
SAIL_FT = float(os.environ.get('EVERY_SAIL_FT', '150'))
HIT_NEAR = float(os.environ.get('EVERY_HIT_NEAR', '1300'))
HIT_FAR = float(os.environ.get('EVERY_HIT_FAR', '1800'))
HIT_PROVOKE = float(os.environ.get('EVERY_HIT_PROVOKE', '120'))
HIT_FOE_SECS = float(os.environ.get('EVERY_HIT_FOE_SECS', '240'))   # at least this long after the first Navy ship is found
PR = '1150922126.8dzlu'
BOT = 100000004
OWN_SLOOP = 100000750
NEVER_PIRATE, NEVER_SHIP = 100000170, 100000173
TALK, FIND_R = 8.0, 40.0
SHELF = (1, 11, 21, 2, 12, 22, 3, 13, 23)
PARTS = ('launched', 'sailed', 'broadside', 'cannon', 'hit', 'repaired', 'docked')
NAMES = {1: 'Light Sloop', 11: 'Light Galleon', 21: 'Light Frigate', 2: 'Sloop', 12: 'Galleon', 22: 'Frigate',
         3: 'War Sloop', 13: 'War Galleon', 23: 'War Frigate'}


# ------------------------------------------------------------------------------------------------ pure
def judge(row):
    """Pure: (ok, failed parts). True / 'n/a' pass; anything else fails."""
    bad = [p for p in PARTS if row.get(p) not in (True, 'n/a')]
    return not bad, bad


def cls(o):
    return o.__class__.__name__


# ------------------------------------------------------------------------------------------------ helpers
def ordered(H, sid):
    """Put ship sid first in his ship list (sailing.launch takes the first). -> undo()."""
    inv = H.la.getInventory()
    orig = inv.getShipDoIdList
    inv.getShipDoIdList = lambda: [sid] + [x for x in orig() if x != sid]

    def undo():
        inv.__dict__.pop('getShipDoIdList', None)
    return undo


def toWright(H):
    """Generator: walk to the nearest Port Royal shipwright (as s_island.buyShip). -> the npc or None."""
    import sailing, s_story, s_lanes
    from panda3d.core import Point3
    la = H.la
    spots = sailing.shipwrightSpots(PR)
    if not spots:
        H.ev('EVERY-WRIGHT', why='no shipwright in Port Royal world data'); return None
    org = s_story.areaObj(H, PR)
    me = la.getPos(H.render)
    pts = [H.render.getRelativePoint(org, Point3(*p)) if org is not None else Point3(*p) for p in spots]
    k = min(range(len(spots)), key=lambda i: (pts[i] - me).length())
    spot, pt = spots[k], pts[k]
    r = yield from s_lanes.walkTo(H, 'every', lambda st: s_story.goto(H, st, PR, pos=spot, arrive=TALK,
                                                                       tag='to-shipwright'), 300, 'the shipwright')
    if r is None:
        H.ev('EVERY-WRIGHT', why='could not walk to the shipwright', la=H.P(la)); return None

    def wright():
        live = [o for o in sailing.shipwrights(H) if hasattr(o, 'getPos')]
        live = [o for o in live if (o.getPos(H.render) - pt).length() < FIND_R]
        return min(live, key=lambda o: (o.getPos(H.render) - pt).length()) if live else None
    yield ('until', lambda: wright() is not None, 20, 'shipwright in view')
    npc = wright()
    if npc is None:
        H.ev('EVERY-WRIGHT', why='no live shipwright near his spot'); return None
    r = yield from s_lanes.walkTo(H, 'every', lambda st: True if s_story.near(H, npc, TALK, st, tag='shipwright')
                                  else 'walk-to-shipwright', 60, 'the shipwright')
    H.walk_cancel()
    if r is None:
        H.ev('EVERY-WRIGHT', why='could not reach the shipwright', d=round(s_story.hdist(H, npc), 1)); return None
    H.ev('EVERY-WRIGHT', npc=npc.doId, name=getattr(npc, 'name', ''), d=round(s_story.hdist(H, npc), 1))
    return npc


def sellShip(H, npc, sid, IG):
    """Generator: Sell Ships -> the ship -> Yes -> Yes (and the lost-gold Yes if it comes). -> True when it left
    his list."""
    import s_activities as A
    la = H.la
    yield from A.talk(H, npc, lambda: la.getGameState() == 'NPCInteract' and getattr(npc, 'interactGUI', None) is not None)
    gone = False
    try:
        gone = yield from sellSteps(H, npc, sid, IG)
    except Exception as e:
        H.ev('EVERY-SELL-ERR', err=repr(e))
    yield from A.leaveNpc(H, npc, IG)
    return gone


def sellSteps(H, npc, sid, IG):
    import s_activities as A
    la = H.la
    if True:
        inMenu, lit, ids = A.menuOn(npc, IG.SELL_SHIPS, IG)
        H.ev('EVERY-SELL-MENU', options=ids, sell=inMenu, lit=lit)
        if not inMenu:
            return False
        yield 1.5
        npc.selectOptionConfirm(IG.SELL_SHIPS)
        yield ('until', lambda: getattr(npc, 'pickShipGUI', None) is not None, 10, 'sell picker')
        pick = getattr(npc, 'pickShipGUI', None)
        frames = []
        try:
            frames = list(pick.shipFrames[pick.OWN])
        except Exception:
            pass
        fr = [f for f in frames if (f['extraArgs'] or [None])[0] == sid]
        H.ev('EVERY-SELL-PICK', ship=sid, picker=pick is not None, frames=len(frames), how='frame' if fr else 'direct')
        if fr:
            fr[0]['command'](*fr[0]['extraArgs'])
        else:
            npc.confirmSellShip(sid)
        pressed = []
        for n in range(3):          # Yes, Yes again, and the lost-gold Yes if the gold would overflow
            last = pressed[-1][0] if pressed else None
            yield ('until', lambda: getattr(npc, 'confirmDialog', None) is not None and
                   getattr(npc, 'confirmDialog', None) is not last, 8, 'sell window %d' % (n + 1))
            d = getattr(npc, 'confirmDialog', None)
            if d is None or d is last:
                break
            try:
                text = str(d['text'])[:120]
            except Exception:
                text = ''
            pressed.append((d, text))
            d['command'](1)
            yield 1
            if sid not in [s[0] for s in A.shipList(H)]:
                break
        yield ('until', lambda: sid not in [s[0] for s in A.shipList(H)], 20, 'ship sold')
        gone = sid not in [s[0] for s in A.shipList(H)]
        H.ev('EVERY-SOLD', ship=sid, gone=gone, windows=[t for d, t in pressed], gold=la.getInventory().getGoldInPocket())
        return gone


def leaveWheel(H, ship):
    la = H.la
    wheel = getattr(ship, 'wheel', None)
    w = wheel[1] if isinstance(wheel, (list, tuple)) and len(wheel) > 1 else None
    if la.getGameState() == 'ShipPilot':
        if w is not None and hasattr(w, 'requestExit'):
            w.requestExit()
        else:
            from pirates.interact import InteractiveBase
            messenger.send(InteractiveBase.END_INTERACT_EVENT)
        yield ('upto', lambda: la.getGameState() != 'ShipPilot', 15, 'leave wheel')
    return la.getGameState() != 'ShipPilot'


def backToWheel(H):
    import sailing
    ship = yield from sailing.launch(H, None, True)
    return ship


def hpOf(ship, ov):
    h = getattr(ship, 'Hp', None)
    return h if h is not None else getattr(ov, 'Hp', None)


def hitTimeLeft(now, t0, tFoe):
    """True while the take-a-hit step may go on: HIT_SECS from the start, or HIT_FOE_SECS from the first foe found."""
    return now - t0 < HIT_SECS or (tFoe is not None and now - tFoe < HIT_FOE_SECS)


def maxHpOf(ship, ov):
    return getattr(ship, 'maxHp', None) or getattr(ov, 'maxHp', None)


# ------------------------------------------------------------------------------------------------ at sea
def atSea(H, sid, ship, row, why):
    import sailing, s_sink as S, s_shipquest as SQ
    from s_dock import Keys
    from panda3d.core import Point3
    from pirates.ship import ShipGlobals
    la, R = H.la, H.render
    ov = H.cr.getOwnerView(sid)
    keys = Keys(H)
    try:
        # 4. sail
        p0 = ship.getPos(R)
        S.fullSail()
        sea = S.Sea(H, ship, keys, sailing)
        t0 = time.time()
        moved = 0
        while time.time() - t0 < 60 and la.getGameState() == 'ShipPilot':
            sea.patrol()
            moved = (ship.getPos(R) - p0).length()
            if moved >= SAIL_FT and time.time() - t0 > 8:
                break
            yield 0.5
        row['sailed'] = moved >= SAIL_FT
        H.ev('EVERY-SAIL', moved=round(moved), secs=round(time.time() - t0), gs=la.getGameState())
        if not row['sailed']:
            why.append('the ship moved %d ft in 60 s' % moved)
        # 5. broadside
        cfg = ShipGlobals.getShipConfig(CLASS) or {}
        maxB = cfg.get('maxBroadsides')
        bk = SQ.broadsideKeys()
        if maxB == 0:
            row['broadside'] = 'n/a'
        elif not bk:
            row['broadside'] = False
            why.append('no broadside key is bound at the wheel (maxBroadsides %s)' % maxB)
        else:
            fired = {}
            for skill, k in sorted(bk.items()):
                before = SQ.recharging(H, skill)
                messenger.send(k); messenger.send(k + '-up')
                yield ('upto', lambda: SQ.recharging(H, skill), 6, 'broadside %s' % k)
                fired[skill] = (not before) and SQ.recharging(H, skill)
                yield 1
            row['broadside'] = any(fired.values())
            if not row['broadside']:
                why.append('no broadside recharge started after its key')
            H.ev('EVERY-BROADSIDE', keys=bk, fired=fired, maxBroadsides=maxB)
        # 6. deck cannon
        cannons = list(getattr(ship, 'cannons', {}).values())
        if not cannons:
            row['cannon'] = 'n/a'
            H.ev('EVERY-CANNON', cannons=0)
        else:
            S.dropSail()
            yield 3
            c = yield from S.takeCannon(H, ship)
            sent = []
            if c is not None:
                old = c.sendRequestProjectileSkill
                c.sendRequestProjectileSkill = lambda *a, **k: (sent.append(a[:2]), old(*a, **k))[1]
                try:
                    t1 = time.time()
                    while not sent and time.time() - t1 < 20:
                        if c.volley > 0 and not (la.skillDiary.getTimeRemaining(c.skillId) or 0) > 0:
                            c.fireCannon()
                        yield 1
                finally:
                    c.__dict__.pop('sendRequestProjectileSkill', None)
                    if getattr(la, 'cannon', None) is c:
                        c.requestExit()
                yield ('upto', lambda: getattr(la, 'cannon', None) is None, 10, 'off the cannon')
            row['cannon'] = bool(sent)
            H.ev('EVERY-CANNON', cannons=len(cannons), seated=c is not None, sent=[list(map(str, s)) for s in sent][:2])
            if not sent:
                why.append('deck cannon: %s' % ('no shot reached the server' if c is not None else 'could not sit on one'))
            ship = yield from backToWheel(H)
            if ship is None:
                why.append('could not take the wheel again after the cannon'); return
            S.fullSail()
        # 7. take a hit
        mx = maxHpOf(ship, ov)
        hp0 = hpOf(ship, ov)
        t0 = time.time()
        foeId, last, lastLog, d = None, None, 0, None
        # 11-21 class 21: sea.hold steers 1500 ft ahead of a foe once inside 1100 ft, so a fast ship ran ahead of a
        # Ferret chasing it and stayed out of its 2000 ft fire range for 420 s. Inside HIT_NEAR the sail comes down
        # and he waits bow-on for it; past HIT_FAR full sail at it again. After HIT_PROVOKE s with no hit he fires
        # his broadsides at it when it is near, as a player would (any hit makes a Navy ship answer).
        sailUp, provoked, tFoe = True, 0, None
        # 11-21 08:38 class 22: the first Navy ship turned up 346 s into the 420, 5981 ft off, and time ran out 13 s
        # after he fired on it. A found foe gets HIT_FOE_SECS of its own.
        while hitTimeLeft(time.time(), t0, tFoe) and la.getGameState() == 'ShipPilot':
            h = hpOf(ship, ov)
            if h is not None and hp0 is not None and h < hp0:
                row['hit'] = True
                break
            f = S.navyFoe(H, ship, SQ)
            if f is None:
                if time.time() - t0 > FIND_SECS and foeId is None:
                    break
                if not sailUp:
                    S.fullSail(); sailUp = True
                sea.patrol()
            else:
                d, o = f
                last = o
                if o.doId != foeId:
                    foeId = o.doId
                    tFoe = tFoe or time.time()
                    H.ev('EVERY-FOE', foe=o.doId, name=getattr(o, 'name', ''), level=SQ.levelOf(o), dist=round(d))
                if d < HIT_NEAR:
                    if sailUp:
                        S.dropSail(); sailUp = False
                    keys.steer(ship, o.getPos(R))
                else:
                    if not sailUp and d > HIT_FAR:
                        S.fullSail(); sailUp = True
                    keys.steer(ship, o.getPos(R))
                if time.time() - t0 > HIT_PROVOKE and d < HIT_FAR and bk and time.time() - provoked > 20:
                    provoked = time.time()
                    for k in sorted(bk.values()):
                        messenger.send(k); messenger.send(k + '-up')
                    H.ev('EVERY-PROVOKE', foe=o.doId, dist=round(d))
            if time.time() - lastLog > 15:
                lastLog = time.time()
                H.ev('EVERY-HP', hp=hpOf(ship, ov), maxHp=mx, foe=foeId, dist=None if d is None else round(d),
                     sail=sailUp, secs=round(time.time() - t0))
            yield 0.5
        if not sailUp:
            S.fullSail()
        hpHit = hpOf(ship, ov)
        H.ev('EVERY-HIT', hit=bool(row.get('hit')), hp0=hp0, hp=hpHit, maxHp=mx, foe=foeId, secs=round(time.time() - t0))
        if not row.get('hit'):
            row['hit'] = False
            why.append('no hit in %d s (%s)' % (time.time() - t0, 'a Navy ship was found' if foeId else 'no Navy ship found'))
        # get clear of the foe, then stop
        t0 = time.time()
        while time.time() - t0 < 45 and la.getGameState() == 'ShipPilot' and last is not None:
            try:
                p, fp = ship.getPos(R), last.getPos(R)
                v = p - fp
                v.setZ(0)
                if v.length() > 2500:
                    break
                v.normalize()
                keys.steer(ship, Point3(p[0] + v[0] * 3000, p[1] + v[1] * 3000, 0))
            except Exception:
                break
            yield 0.5
        keys.release()
        S.dropSail()
        yield 8
        # 8. repair on deck
        spots = [o for o in list(H.cr.doId2do.values()) if cls(o) == 'DistributedShipRepairSpot' and
                 getattr(o, '_shipId', None) == sid]
        h1 = hpOf(ship, ov)
        if not spots:
            row['repairSpots'] = 0
            H.ev('EVERY-REPAIR', spots=0, hp=h1, maxHp=mx)
        elif h1 is not None and mx and h1 >= mx:
            row['repaired'] = 'n/a' if not row.get('hit') else True
            H.ev('EVERY-REPAIR', spots=len(spots), hp=h1, maxHp=mx, why='already full')
        else:
            row['repairSpots'] = len(spots)
            if (yield from leaveWheel(H, ship)):
                import paths, sailing
                sp = min(spots, key=lambda o: o.getDistance(la))
                ok = False
                # boats 11-21 (War Frigate 07:12): the spot nearest the wheel is 12 ft down on the mid deck; a straight walk
                # jams at the wheel deck's edge, so another deck goes by the deck's own stairs like the wheel does
                if abs(sp.getZ(H.render) - la.getZ(H.render)) > paths.MAX_RISE + 1.0:
                    ok = yield from sailing.wheel_route(H, sp, 'repair-spot', arrive=3.0)
                if not ok:
                    ok = yield from H.walk_to(sp, arrive=3.0, timeout=30, tag='repair-spot')
                sp.requestInteraction(la.doId)
                yield ('upto', lambda: la.getGameState() == 'ShipRepair', 15, 'repairing')
                gs = la.getGameState()
                t1 = time.time()
                # boats 11-21 (War Frigate 07:12): a Navy ship still in range can shoot faster than the spot heals (10 hp
                # per 2 s), so the net hp fell while the repair worked; the spot's heal ticks are counted as rises
                rises = drops = 0
                prev = hpOf(ship, ov)
                while time.time() - t1 < REPAIR_SECS and (prev or 0) < (mx or 0):
                    yield 0.5
                    h = hpOf(ship, ov)
                    if h is not None and prev is not None:
                        rises += h > prev
                        drops += h < prev
                    prev = h
                h2 = hpOf(ship, ov)
                row['repaired'] = h1 is not None and h2 is not None and (h2 > h1 or rises >= 2)
                H.ev('EVERY-REPAIR', spots=len(spots), reached=ok, gs=gs, hp=[h1, h2], maxHp=mx, full=h2 == mx,
                     rises=rises, drops=drops, secs=round(time.time() - t1))
                try:
                    sp.requestExit()
                except Exception:
                    pass
                yield 2
            else:
                H.ev('EVERY-REPAIR', spots=len(spots), why='could not leave the wheel')
            if row.get('repaired') is not True:
                why.append('repair spot: hp did not rise (%s)' % hpOf(ship, ov))
            ship = yield from backToWheel(H)
            if ship is None:
                why.append('could not take the wheel again after the repair'); return
    finally:
        keys.release()


# ------------------------------------------------------------------------------------------------ the run
def run(H):
    import sailing, s_lanes
    import s_activities as A
    import s_shipquest as SQ
    EG, IG, IT, RG, PGG = A._game()
    la = H.la
    row = {'cls': CLASS}
    why = []
    if la.doId != BOT or la.doId == NEVER_PIRATE:
        H.ev('FAIL', why='EVERY1 runs on claude2 (%d) only, not %d' % (BOT, la.doId)); return
    if CLASS not in SHELF:
        H.ev('FAIL', why='class %s is not on the shipwright shelf %s' % (CLASS, SHELF)); return
    from pirates.ship import ShipGlobals
    cost, need = EG.getItemCost(CLASS), EG.getItemMinLevel(CLASS) or 0
    row['name'] = NAMES.get(CLASS, str(CLASS))
    # his ships' owner views come in after login; read too early, a leftover ship had no class yet and was missed (the
    # 01:22 run bought another). Ships that never come in mean the game's ship loader is stuck for him: say so.
    yield ('upto', lambda: all(s[1] is not None for s in A.shipList(H)), 60)
    start = A.shipList(H)
    late = [s[0] for s in start if s[1] is None]
    if late:
        H.ev('FAIL', why='his ships %s never reached his game in 60 s (game: the ship loader is stuck for him)' % late,
             ships=[list(s[:4]) for s in start]); return
    H.ev('EVERY-START', cls=CLASS, name=row['name'], cost=cost, need=need, gold=s_lanes.gold(H),
         sailing=A.sailLevel(H, RG, IT), ships=[list(s[:4]) for s in start], here=H.area())
    if any(s[0] == NEVER_SHIP for s in start):
        H.ev('FAIL', why='ship %d is in this list' % NEVER_SHIP); return
    if not sailing.onShip(H) and sailing.hereUid(H) != PR:
        if not (yield from s_lanes.onIsland(H, 'every', PR)):
            H.ev('FAIL', why='could not get onto Port Royal', area=H.area()); return
    # 1. level and gold
    if A.sailLevel(H, RG, IT) < need:
        H.ev('MW-LEVEL', why='class %d needs Sailing %d' % (CLASS, need), sailing=A.sailLevel(H, RG, IT))
        H.mw('level %d %d' % (IT.SailingRep, need))
        yield ('until', lambda: A.sailLevel(H, RG, IT) >= need, 10, 'sailing level')
    # 2. the ship
    bought = None
    if CLASS == 1:
        sid = OWN_SLOOP if any(s[0] == OWN_SLOOP and s[1] == 1 for s in start) else None
        if sid is None:
            H.ev('FAIL', why='his own Light Sloop %d is not in his list' % OWN_SLOOP); return
    else:
        if s_lanes.gold(H) < cost:
            H.ev('MW-GOLD', why='class %d costs %d' % (CLASS, cost), gold=s_lanes.gold(H))
            H.mw('gold %d' % (cost + 100))
            yield ('until', lambda: s_lanes.gold(H) >= cost, 10, 'gold')
        npc = yield from toWright(H)
        sid = None
        # a ship of this class left by a run that could not sell it back is used (and sold) instead of buying another
        left = [s[0] for s in start if s[1] == CLASS and s[0] not in (OWN_SLOOP, NEVER_SHIP)]
        if left:
            sid = left[0]
            H.ev('EVERY-LEFTOVER', ship=sid, cls=CLASS)
        elif npc is not None:
            sid = yield from A.buySloop(H, npc, EG, IG, PGG, CLASS)
        if sid is None:
            row['bought'] = False
            why.append('could not buy class %d at the shipwright' % CLASS)
        else:
            bought = sid
            row['bought'] = True
    row['ship'] = sid
    undo = ordered(H, sid) if sid else (lambda: None)
    try:
        # 3. launch
        if sid:
            ship = yield from SQ.launchShip(H)
            row['launched'] = ship is not None and ship.doId == sid and getattr(ship, 'steeringAvId', None) == la.doId
            ov = H.cr.getOwnerView(sid)
            H.ev('EVERY-LAUNCH', ok=row['launched'], ship=sid, cls=getattr(ov, 'shipClass', None),
                 hp=getattr(ov, 'Hp', None), maxHp=getattr(ov, 'maxHp', None), gs=la.getGameState())
            if not row['launched']:
                why.append('could not launch it and take the wheel')
            else:
                try:
                    yield from atSea(H, sid, ship, row, why)
                except Exception as e:
                    import traceback
                    H.ev('EVERY-ERR', err=repr(e), tb=traceback.format_exc()[-600:])
                    why.append('script error at sea: %r' % e)
                # 9. dock
                if sailing.onShip(H):
                    yield from sailing.sail_to(H, PR, 'every-ship dock')
                    yield ('upto', lambda: getattr(H.cr.getOwnerView(sid), 'state', None) in ('PutAway', 'Off'), 20,
                           'put away')
                ov = H.cr.getOwnerView(sid)
                st = getattr(ov, 'state', None)
                row['docked'] = bool(getattr(H, 'sailResult', False)) and st in ('PutAway', 'Off')
                H.ev('EVERY-DOCK', ok=row['docked'], state=st, here=sailing.hereUid(H), gs=la.getGameState(),
                     hp=getattr(ov, 'Hp', None))
                if not row['docked']:
                    why.append('dock: sailResult %s, ship state %s' % (getattr(H, 'sailResult', None), st))
        # 8b. no repair spot on deck: the shipwright's repair stands in
        if sid and row.get('repairSpots') == 0 and row.get('hit'):
            hp, paid = yield from sailing.repair(H, sailing.hereUid(H) or PR, sid)
            ov = H.cr.getOwnerView(sid)
            row['repaired'] = hp is not None and hp >= (getattr(ov, 'maxHp', 0) or 0)
            row['repairHow'] = 'shipwright'
            if not row['repaired']:
                why.append('shipwright repair: hp %s' % hp)
    finally:
        undo()
    # 10. sell what we bought, then gold and Sailing back
    if bought:
        H.mw('gold %d' % GOLD0)
        yield ('until', lambda: s_lanes.gold(H) <= GOLD0, 10, 'gold low before the sale')
        sold = False
        if sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam':
            npc = yield from toWright(H)
            if npc is not None:
                sold = yield from sellShip(H, npc, bought, IG)
        row['sold'] = sold
        if not sold:
            why.append('could not sell ship %d back (it stays in his list)' % bought)
    if s_lanes.gold(H) != GOLD0:
        H.mw('gold %d' % GOLD0)
        yield ('until', lambda: s_lanes.gold(H) == GOLD0, 10, 'gold back')
    if need:
        H.mw('level %d 0' % IT.SailingRep)
        yield ('until', lambda: A.sailLevel(H, RG, IT) <= 1, 10, 'sailing back')
    ok, bad = judge(row)
    H.ev('EVERYSHIP-ROW', **dict(row, ok=ok, bad=bad, why=why, gold=s_lanes.gold(H), sailing=A.sailLevel(H, RG, IT),
                                  ships=[list(s[:4]) for s in A.shipList(H)]))
    if ok:
        H.ev('PASS', what='class %d %s: launched, sailed, fired, hit, repaired, docked' % (CLASS, row['name']))
    else:
        H.ev('FAIL', why='class %d %s: %s' % (CLASS, row['name'], '; '.join(why) or ', '.join(bad)))
