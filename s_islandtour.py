"""ISLANDTOUR (pir-bot job 19, 11-18, the brain's order): one pirate sails his own ship round every island with a
dock, like a kid on a long trip. From Port Royal (one map hop there if he is not on it): Tortuga, Padres Del Fuego,
Cuba, Isla Tormenta, Kingshead, Cutthroat Isle, then back to Port Royal. At each island: dock (anchor button), step
off onto the island (LandRoam there, ASHORE), then step back on (the next leg's walk to the dinghy and launch) and
sail on. Every crossing is sailing.sail_to (dinghy, wheel, W, A / D round islands, dock laps, anchor), never a
teleport; the only map hops are the start (to Port Royal) and a RECOVER-HOP after a ship lost at sea strands him.

At sea it steers like s_story's sails (s_story.SeaSense): wide round enemy ships above his level (SAIL-AVOID; the
starter waters let one attacker in at a time since server-tree 0166), broadsides back once hit (SAIL-BROADSIDE), runs
below half hull (SAIL-FLEE), and below 30 % turns for the nearest island with a shipwright (TOUR-DIVERT), repairs
there and sails the leg on (once a leg). Per-leg waypoints (the SAIL_VIA idea, several per leg) take the long legs
round islands that sit on the straight line: Tortuga -> Padres passes 1038 ft from Devil's Anvil, Isla Tormenta ->
Kingshead 1329 ft from Cutthroat Isle (sailing.route keeps 3300 ft, but only reacts once the island is on the line).

Repair: at each dock, before he steps back on, the hull is read (REPAIR-CHECK); under half (ISLANDTOUR_REPAIR_AT)
he walks to the shipwright and pays (sailing.repair). Only Port Royal, Tortuga, Padres Del Fuego and Cuba have one
(world data); elsewhere it is REPAIR-NONE and he sails on. sailing.launch's own repair-on-any-damage is turned off
for the tour (it would walk to the shipwright after every scratch); a sunk ship is always mended where it can be.

Lines: TOUR-START, HOP, REPAIR-CHECK, REPAIR-NONE, sailing's own lines (SAIL-START ... vis ... SAILED / SAIL-FAIL,
SHIP-DELETED), TOUR-VIA (a waypoint reached / skipped), TOUR-DIVERT, ASHORE, RECOVER-HOP,
TOUR-LEG n frm to isl try result=SAILED|STUCK why secs seaSecs hull0 hullMin hullEnd maxHp zones nZones
deletedAtSea deletedAtDock repaired vias avoid broadside flee divert dockRefused landed,
TOUR-SUMMARY, then PASS (every leg SAILED and he is back on Port Royal) or FAIL.

env: ISLANDTOUR_ORDER (comma list of island names or uids, default the tour above), ISLANDTOUR_SKIP (names to leave
out), ISLANDTOUR_TRIES (2: sails at one leg before it is given up), ISLANDTOUR_REPAIR_AT (0.5),
ISLANDTOUR_VIAS (JSON {"Tortuga>Padres Del Fuego": [[x, y], ...]} to replace a leg's waypoints; [] = none),
ISLANDTOUR_VIA_R (1500), ISLANDTOUR_VIA_SECS (600). sailing's SAIL_LEG_SECS (900) is each sail's limit.
Never runs on pirate 100000170. Run with ROUTE_TEST=1 so FAST_START warps nothing; give it -Secs 3600."""
import json, math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__', '.'))))
import sailing   # noqa: E402

BANNED = (100000170,)
PR = '1150922126.8dzlu'
TORTUGA = '1156207188.95dzlu'
PADRES = '1142018473.22dxschafe'
CUBA = '1160614528.73sdnaik'
TORMENTA = '1164150392.42dzlu'
KINGSHEAD = '1159933206.48sdnaik'
CUTTHROAT = '1173382404.64sdnaik'
# world data (piratesWorld.py) positions, read once offline (job19/islands.json): the tour's own table, so the divert
# and the waypoint logic need no game import
POS = {PR: ('Port Royal', -88.0, -1848.0), TORTUGA: ('Tortuga', 10568.0, 16760.0),
       PADRES: ('Padres Del Fuego', 8757.0, -24577.0), CUBA: ('Cuba', -16099.0, 1858.0),
       TORMENTA: ('Isla Tormenta', -16723.0, -10071.0), KINGSHEAD: ('Kingshead', 21049.0, -12029.0),
       CUTTHROAT: ('Cutthroat Isle', 13300.0, -10297.0)}
TOUR = [TORTUGA, PADRES, CUBA, TORMENTA, KINGSHEAD, CUTTHROAT, PR]
SHIPWRIGHT = (PR, TORTUGA, PADRES, CUBA)     # islands whose world data has a Shipwright townsperson (and a dinghy)
# (frm, to) -> waypoints. PR -> Tortuga: the line q_sail2632 proved (SAIL2632-1: SAILED 219 s through cell 2632).
# Tortuga -> Padres: west of Devil's Anvil (the line passes it at 1038 ft). Tormenta -> Kingshead: south of Cutthroat
# Isle (1329 ft). The other legs clear every island by > 4800 ft. unit_job19 A sails each leg on sailing.route.
VIAS = {(PR, TORTUGA): [(5000.0, 10400.0)],
        (TORTUGA, PADRES): [(4000.0, 8000.0)],
        (TORMENTA, KINGSHEAD): [(13300.0, -15000.0)]}
REPAIR_AT = float(os.environ.get('ISLANDTOUR_REPAIR_AT', '0.5'))
TRIES = int(os.environ.get('ISLANDTOUR_TRIES', '2'))
VIA_R = float(os.environ.get('ISLANDTOUR_VIA_R', '1500'))
VIA_SECS = float(os.environ.get('ISLANDTOUR_VIA_SECS', '600'))


def name(uid):
    return POS.get(uid, (str(uid),))[0]


def uidOf(s):
    s = s.strip()
    if s in POS:
        return s
    for u, v in POS.items():
        if v[0].lower() == s.lower() or v[0].lower().startswith(s.lower()):
            return u
    return None


def tourOrder(env=None):
    """Pure. The islands to visit in turn (uids), from ISLANDTOUR_ORDER / ISLANDTOUR_SKIP."""
    env = os.environ if env is None else env
    order = [uidOf(s) for s in env['ISLANDTOUR_ORDER'].split(',')] if env.get('ISLANDTOUR_ORDER') else list(TOUR)
    skip = set(uidOf(s) for s in env.get('ISLANDTOUR_SKIP', '').split(',') if s.strip())
    return [u for u in order if u and u not in skip]


def legVias(frm, to, env=None):
    """Pure. The waypoints for the leg frm -> to (ISLANDTOUR_VIAS overrides, keyed 'Frm name>To name')."""
    env = os.environ if env is None else env
    if env.get('ISLANDTOUR_VIAS'):
        over = json.loads(env['ISLANDTOUR_VIAS'])
        k = '%s>%s' % (name(frm), name(to))
        if k in over:
            return [tuple(float(v) for v in w) for w in over[k]]
    return list(VIAS.get((frm, to), []))


def needRepair(hp, maxHp, at=None):
    """Pure. Mend the hull at this dock? Under `at` of full (a sunk ship, hp 0, always); no owner view = unknown = no."""
    at = REPAIR_AT if at is None else at
    if hp is None or not maxHp:
        return False
    return hp <= 0 or hp < at * maxHp


def nearestPort(p, exclude=()):
    """Pure. The island with a shipwright nearest to p = (x, y)."""
    pp = [u for u in SHIPWRIGHT if u not in exclude]
    return min(pp, key=lambda u: (POS[u][1] - p[0]) ** 2 + (POS[u][2] - p[1]) ** 2) if pp else None


class Waypoints:
    """Pure. A leg's waypoints, nearest first. aim(p, now) -> the point to sail at, or None (straight for the goal).
    A waypoint is done when the ship is within r of it, when it is no nearer the target than the ship (passed), or
    after secs aimed at it. say(ev, **kw) logs TOUR-VIA."""

    def __init__(self, pts, target, say=None, r=None, secs=None):
        self.pts, self.target = list(pts), target
        self.say = say or (lambda *a, **k: None)
        self.r = VIA_R if r is None else r
        self.secs = VIA_SECS if secs is None else secs
        self.t0 = None
        self.done = []

    def aim(self, p, now):
        while self.pts:
            w = self.pts[0]
            if self.t0 is None:
                self.t0 = now
            d = math.hypot(p[0] - w[0], p[1] - w[1])
            dShip = math.hypot(p[0] - self.target[0], p[1] - self.target[1])
            dWp = math.hypot(w[0] - self.target[0], w[1] - self.target[1])
            why = None
            if d < self.r:
                why = 'reached'
            elif dShip < dWp - self.r:
                why = 'passed'
            elif now - self.t0 > self.secs:
                why = 'time'
            if why is None:
                return w
            self.pts.pop(0)
            self.done.append((w, why))
            self.say('TOUR-VIA', via=[round(w[0]), round(w[1])], how=why, dist=round(d), secs=round(now - self.t0),
                     left=len(self.pts), pos=[round(p[0]), round(p[1])])
            self.t0 = None
        return None


def legSummary(events, n, frm, to, tryN=1, maxHp=None, hull0=None, hullEnd=None, repaired=None, landed=None):
    """Pure. The TOUR-LEG line from the leg's own events (dicts with 'ev' as in walk-*-events.jsonl)."""
    sailed = [e for e in events if e.get('ev') == 'SAILED' and e.get('ok') and e.get('to') == to]
    fails = [e.get('why') for e in events if e.get('ev') == 'SAIL-FAIL']
    zones, last = [], None
    hps = []
    atSea = atDock = 0
    anchored = False
    for e in events:
        k = e.get('ev')
        if k == 'SAIL-START':
            anchored = False
        elif k == 'ANCHOR-DROP':
            anchored = True
        elif k == 'SHIP-DELETED':
            if anchored:
                atDock += 1
            else:
                atSea += 1
        elif k == 'vis':
            z = e.get('shipZone')
            if z is not None and z != last:
                last = z
                if z not in zones:
                    zones.append(z)
        if k in ('h', 's2') and e.get('hp') is not None:
            hps.append(e['hp'])
        if k == 'SAILED' and e.get('hpMin') is not None:
            hps.append(e['hpMin'])
    ts = [e['t'] for e in events if 't' in e]
    t0 = next((e['t'] for e in events if e.get('ev') == 'SAIL-START' and 't' in e), ts[0] if ts else None)
    tEnd = sailed[-1]['t'] if sailed and 't' in sailed[-1] else (ts[-1] if ts else None)
    ok = bool(sailed)
    why = None if ok else (fails[-1] if fails else 'no SAILED line')
    cnt = lambda k: sum(1 for e in events if e.get('ev') == k)
    hullMin = min(hps) if hps else None
    return dict(n=n, frm=frm, to=to, isl=name(to), frmIsl=name(frm), tryN=tryN, result='SAILED' if ok else 'STUCK',
                why=why, fails=fails or None,
                secs=None if t0 is None or tEnd is None else round(tEnd - t0),
                seaSecs=sailed[-1].get('secs') if sailed else None,
                hull0=hull0, hullMin=hullMin, hullEnd=hullEnd, maxHp=maxHp,
                hullMinPct=None if hullMin is None or not maxHp else round(100.0 * hullMin / maxHp),
                zones=zones, nZones=len(zones), deletedAtSea=atSea, deletedAtDock=atDock, repaired=repaired,
                vias=[e.get('via') for e in events if e.get('ev') == 'TOUR-VIA'] or None,
                avoid=cnt('SAIL-AVOID'), broadside=cnt('SAIL-BROADSIDE'), flee=cnt('SAIL-FLEE'),
                divert=cnt('TOUR-DIVERT'), dockRefused='no anchor button at the shore' in fails,
                landed=landed)


class TourSense:
    """Stands in for sailing.route while a leg sails: the leg's waypoints first, then s_story.SeaSense (enemy ships
    passed wide, broadsides back, flee, port at 30 %) on top of the real island routing."""

    def __init__(self, H, sense, wps):
        self.H, self.sense, self.wps = H, sense, wps

    def route(self, p, goal, obst):
        w = self.wps.aim(p, time.time()) if self.wps is not None else None
        g = goal if w is None else (w[0], w[1], 0)
        return self.sense.route(p, g, obst)


def seaSense(H, why):
    import s_story   # live only: s_story reads the quest ladder from the game at import
    return s_story.SeaSense(H, why)


def shipId(H):
    try:
        ss = list(H.la.getInventory().getShipDoIdList())
    except Exception:
        return None
    return ss[0] if ss else None


def hullOf(H, sid):
    ov = H.cr.getOwnerView(sid) if sid is not None else None
    return getattr(ov, 'Hp', None), getattr(ov, 'maxHp', None)


def onIsland(H):
    return sailing.hereUid(H) if H.la.getGameState() == 'LandRoam' else None


# job 26 (ISLANDTOUR1 leg 7): killed by Cutthroat's monsters on the walk to the dinghy, he woke in Cuba's jail (his
# return port) and the tour gave up. The tour logged only the hull, so the death never showed. Now the pirate's own
# hp and his Death / jail game states are logged, and the tour walks out of jail and carries on.
JAIL_TOUR_LIMIT = float(os.environ.get('ISLANDTOUR_JAIL_LIMIT', '420'))
JAIL_TRIES = int(os.environ.get('ISLANDTOUR_JAIL_TRIES', '2'))      # extra leg tries a jail escape gives
AV = {}             # last pirate hp / game state seen by avWatch


def jailedNow(H):
    """Same test as s_story.jailed (no s_story import, so it runs offline): in a jail interior, or holding a cell."""
    a = H.area()
    return (a is not None and a[0] == 'DistributedJailInterior') or getattr(H.la, 'jailCellIndex', 100) < 100


def avWatch(H):
    """Log the pirate's own hp drops (AV-HP, at most one line per 2 s, with the total lost since the last line) and
    his Death / ThrownInJail game states (AV-DEATH). Called on every step of a leg and of the jail walk."""
    la = H.la
    now = time.time()
    hp, mx, gs = getattr(la, 'hp', None), getattr(la, 'maxHp', None), la.getGameState()
    if hp is not None:
        last = AV.get('hp')
        if last is not None and hp < last:
            AV['lost'] = AV.get('lost', 0) + (last - hp)
        if AV.get('lost') and (now - AV.get('hpT', 0) >= 2 or hp <= 0):
            H.ev('AV-HP', hp=hp, maxHp=mx, lost=AV['lost'], gs=gs, area=H.area(), la=H.P(la))
            AV['hpT'], AV['lost'] = now, 0
        AV['hp'] = hp
    if gs != AV.get('gs'):
        if gs in ('Death', 'ThrownInJail'):
            H.ev('AV-DEATH', gs=gs, frm=AV.get('gs'), hp=hp, maxHp=mx, area=H.area(), la=H.P(la),
                 cell=getattr(la, 'jailCellIndex', None))
        AV['gs'] = gs


def jailOut(H, why, s=None):
    """Generator. In jail: kick the cell door open, walk out of the cell, leave by the jail's door onto the island,
    one s_story.jail() step at a time, doing the walks it leaves in st['go'] (as s_story's run does).
    -> True when out of jail and standing on an island (also True when he was never in jail).
    Lines: TOUR-JAIL, TOUR-JAIL-STEP, s_story's JAIL-* lines, then TOUR-JAIL-OUT ok=."""
    if not jailedNow(H):
        return True
    if s is None:
        import s_story as s     # live only: s_story reads the quest ladder from the game at import
    la = H.la
    t0 = time.time()
    H.ev('TOUR-JAIL', why=why, area=H.area(), cell=getattr(la, 'jailCellIndex', None), gs=la.getGameState(),
         hp=getattr(la, 'hp', None), la=H.P(la))
    st, lastA, n = {}, None, 0
    while time.time() - t0 < JAIL_TOUR_LIMIT:
        avWatch(H)
        jr = s.jail(H, st)
        if jr is None:
            if not jailedNow(H):
                break
            yield 2         # jail() gave up (its own STALL); the limit above ends it
            continue
        if jr != lastA:
            n += 1
            H.ev('TOUR-JAIL-STEP', a=jr, n=n, gs=la.getGameState(), la=H.P(la))
            lastA = jr
        g = st.pop('go', None)
        if g is not None and la.getGameState() == 'LandRoam':
            obj, arrive, face, ref, tag = g
            yield from s.go(H, obj, arrive, face, ref, tag)
        else:
            yield 1
    yield ('upto', lambda: onIsland(H) is not None, 30, 'on the island after jail')
    here = onIsland(H)
    ok = not jailedNow(H) and here is not None
    H.ev('TOUR-JAIL-OUT', ok=ok, island=name(here) if here else None, secs=round(time.time() - t0, 1),
         gs=la.getGameState(), area=H.area(), la=H.P(la))
    return ok


def hop(H, uid, tag):
    """Generator. The map's own island teleport (as s_kidsail). -> True when he stands on uid."""
    la, cr = H.la, H.cr
    t0 = time.time()
    try:
        cr.teleportMgr.requestTeleportToIsland(uid)
    except Exception as e:
        H.ev(tag, to=name(uid), ok=False, err=repr(e)[:120]); return False
    while time.time() - t0 < 120 and not (sailing.hereUid(H) == uid and la.getGameState() == 'LandRoam'):
        yield 0.5
    ok = sailing.hereUid(H) == uid and la.getGameState() == 'LandRoam'
    H.ev(tag, to=name(uid), ok=ok, secs=round(time.time() - t0, 1), gs=la.getGameState(), area=H.area())
    return ok


def dockRepair(H, sid):
    """Generator. At a dock: read the hull, mend it under REPAIR_AT where there is a shipwright. -> repaired or None."""
    here = onIsland(H)
    if here is None or sid is None:
        return None
    yield ('upto', lambda: H.cr.getOwnerView(sid) is not None, 20, 'ship owner view')
    hp, mx = hullOf(H, sid)
    need = needRepair(hp, mx)
    H.ev('REPAIR-CHECK', island=name(here), ship=sid, hp=hp, maxHp=mx,
         pct=None if hp is None or not mx else round(100.0 * hp / mx), need=need, shipwright=here in SHIPWRIGHT)
    if not need:
        return None
    if here not in SHIPWRIGHT:
        H.ev('REPAIR-NONE', island=name(here), hp=hp, maxHp=mx, why='no shipwright on this island; sails on')
        return False
    hp2, paid = yield from sailing.repair(H, here, sid)
    yield 3
    return dict(at=name(here), hp0=hp, hp=hp2, paid=paid)


class Patched:
    """sailing.route -> the tour's sense, sailing.launch -> no repair on a scratch (aboard=True only skips that;
    a sunk ship is mended by dockRepair first), sailing.VIA -> None. Put back on exit."""

    def __init__(self, sense):
        self.sense = sense

    def __enter__(self):
        self.old = (sailing.route, sailing.launch, sailing.VIA)
        orig = self.old[1]

        def launchNoRepair(H, here, aboard):
            return orig(H, here, True)
        launchNoRepair._tour = True
        sailing.route, sailing.launch, sailing.VIA = self.sense.route, launchNoRepair, None
        return self

    def __exit__(self, *a):
        sailing.route, sailing.launch, sailing.VIA = self.old
        return False


def sailLeg(H, to, frm, legN):
    """Generator. One sail to island `to` with the tour's sense; one divert to a port for repair when the hull drops
    under 30 % (s_story.PORT_HP). -> True when he stands on `to`."""
    la = H.la
    sense = seaSense(H, 'islandtour leg %d' % legN)
    base = sense.route

    def say(ev, **kw):
        H.ev(ev, leg=legN, **kw)
    wps = Waypoints(legVias(frm, to), POS[to][1:], say)
    ts = TourSense(H, sense, wps)
    diverted = False
    with Patched(ts):
        gen = sailing.sail_to(H, to, why='islandtour')
        while True:
            if not diverted and sense.port and la.getGameState() == 'ShipPilot':
                ship = H.cr.doId2do.get(shipId(H))
                p = ship.getPos(H.render) if ship is not None else None
                pt = nearestPort((p[0], p[1])) if p is not None else None
                if pt and pt != to:
                    gen.close()
                    for k in ('a', 'd'):
                        messenger.send(k + '-up')
                    diverted = True
                    H.ev('TOUR-DIVERT', leg=legN, frm=name(frm), to=name(to), port=name(pt),
                         hull=None if sense.hull is None else round(sense.hull, 2), pos=[round(p[0]), round(p[1])])
                    sense.port = False
                    ts.wps = None
                    yield from sailing.sail_to(H, pt, why='islandtour divert')
                    if onIsland(H) == pt:
                        yield from dockRepair(H, shipId(H))
                    ts.wps = Waypoints(legVias(pt, to), POS[to][1:], say)
                    gen = sailing.sail_to(H, to, why='islandtour after divert')
                    continue
            avWatch(H)
            if jailedNow(H):
                # job 26: killed ashore (the walk to the dinghy) and thrown in jail; sail_to cannot go on from a cell
                gen.close()
                H.ev('TOUR-JAILED', leg=legN, frm=name(frm), to=name(to), area=H.area(), gs=la.getGameState(),
                     cell=getattr(la, 'jailCellIndex', None))
                break
            try:
                y = next(gen)
            except StopIteration:
                break
            yield y
    sense.route = base
    return onIsland(H) == to


def run(H):
    la, cr = H.la, H.cr
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if la.doId in BANNED:
        H.ev('FAIL', why='ISLANDTOUR never runs on this pirate (his own)'); return
    order = tourOrder()
    sid = shipId(H)
    H.ev('TOUR-START', pirate=la.doId, ship=sid, here=sailing.hereUid(H), order=[name(u) for u in order],
         repairAt=REPAIR_AT, tries=TRIES, vias={'%s>%s' % (name(a), name(b)): v for (a, b), v in VIAS.items()})
    if sid is None:
        H.ev('FAIL', why='the pirate has no ship'); return
    if sailing.hereUid(H) != PR:
        yield 3
        if not (yield from hop(H, PR, 'HOP')):
            H.ev('FAIL', why='map hop to Port Royal did not land'); return
        yield 5
    # the tap: every line the leg writes (sailing's too) is kept for its TOUR-LEG summary
    log = []
    ev0 = H.ev

    def tap(ev, **kw):
        d = dict(kw)
        d['ev'], d['t'] = ev, time.time()
        log.append(d)
        return ev0(ev, **kw)
    H.ev = tap
    legs = []
    try:
        frm = PR
        for n, to in enumerate(order, 1):
            leg = None
            tryN, tries, jails = 0, TRIES, 0
            while tryN < tries:
                tryN += 1
                i0 = len(log)
                if jailedNow(H):
                    yield from jailOut(H, 'before leg %d try %d' % (n, tryN))
                start = onIsland(H) or frm
                repaired = yield from dockRepair(H, sid)
                hp0, mx = hullOf(H, sid)
                ok = yield from sailLeg(H, to, start, n)
                hpE, mxE = hullOf(H, sid)
                leg = legSummary(log[i0:], n, start, to, tryN, maxHp=mx or mxE, hull0=hp0, hullEnd=hpE,
                                 repaired=repaired, landed=ok)
                leg['frm'], leg['frmIsl'] = start, name(start)
                H.ev('TOUR-LEG', **leg)
                if ok:
                    H.ev('ASHORE', leg=n, isl=name(to), gs=la.getGameState(), area=H.area(), la=H.P(la))
                    break
                # STUCK: wait for him to come back up (a sunk ship puts him ashore somewhere), then try again
                yield ('upto', lambda: la.getGameState() in ('LandRoam', 'ShipPilot'), 120, 'back on his feet')
                if jailedNow(H):
                    # job 26: no map hop from a cell ("Sorry, you can't teleport from jail"); walk out, then retry
                    # the leg from the island the jail is on (start = onIsland on the next try). A jail does not use
                    # up a try: up to JAIL_TRIES extra tries per leg.
                    if (yield from jailOut(H, 'leg %d try %d failed' % (n, tryN))):
                        if jails < JAIL_TRIES:
                            jails += 1
                            tries += 1
                        continue
                    break                       # still in jail: no hop works from a cell, the tour stops below
                if la.getGameState() == 'ShipPilot' and cr.doId2do.get(sid) is not None:
                    continue                    # still at the wheel (no anchor at that shore): sail_to goes on aboard
                if onIsland(H) is None:
                    # STORY27: the ship deleted at sea left him on no island ('not standing on an island' for ever)
                    back = start if start in POS else PR
                    if not (yield from hop(H, back, 'RECOVER-HOP')):
                        break
            legs.append(leg)
            frm = to
            if not leg or leg['result'] != 'SAILED':
                here = onIsland(H)
                if jailedNow(H):
                    H.ev('TOUR-STOP', leg=n, why='still in jail after the jail walk', gs=la.getGameState(),
                         area=H.area(), cell=getattr(la, 'jailCellIndex', None))
                    break
                if here is None and not (la.getGameState() == 'ShipPilot' and cr.doId2do.get(sid) is not None):
                    H.ev('TOUR-STOP', leg=n, why='stuck after %d tries and not on an island or at the wheel' % TRIES,
                         gs=la.getGameState(), area=H.area())
                    break
                frm = here or frm
    finally:
        H.ev = ev0
    sailedN = sum(1 for g in legs if g and g['result'] == 'SAILED')
    home = onIsland(H) == PR
    H.ev('TOUR-SUMMARY', legs=len(legs), of=len(order), sailed=sailedN, home=home,
         table=[[g['n'], g['frmIsl'], g['isl'], g['result'], g['secs'], g['hullMinPct'], g['nZones'],
                 g['deletedAtSea'], bool(g['repaired'])] for g in legs if g],
         stuck=[[g['n'], g['isl'], g['why']] for g in legs if g and g['result'] != 'SAILED'] or None)
    if sailedN == len(order) and len(legs) == len(order) and home:
        H.ev('PASS', what='sailed round %d islands and docked back at Port Royal' % (len(order) - 1), legs=len(legs))
    else:
        H.ev('FAIL', why='%d of %d legs sailed%s' % (sailedN, len(order), '' if home else '; not back on Port Royal'))
