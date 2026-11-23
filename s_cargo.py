"""CARGO1 (row 20, 11-22): the cargo hold sells, played like a player. Server-tree patch 0412 (hold-0001): the hold sold
only on Drop Anchor, so a voyage that ended any other way (teleport home, log off, walk off) kept the plunder aboard for
good and a full hold took nothing more ("can't take the boat out, cargo full"). With 0412 the last pirate off the ship
is sold the hold (DistributedShipAI._playerDeparted -> sellHoldTo), and a ship launched with plunder still aboard sells
it at the dock first (DistributedDinghyAI.selectOwnShip).

The run: stand on CARGO_FROM (s_shipfight's SHIPFIGHT_FROM, Port Royal), note the hold as it is (CARGO-START; plunder
left from an earlier voyage must sell at this launch: LAUNCH-SALE), then s_shipfight's own fight (launch, sink one
enemy ship, wait for its gold; its PASS / FAIL are logged as SHIPFIGHT-PASS / SHIPFIGHT-FAIL). The sunk ship's crates
and chests go into the hold (NPCShipAI.rollPlunder -> addPlunder -> setCargo): CARGO-IN, with what the goods are worth
(EconomyGlobals' cargo table, holdRange). Then he goes home:
  CARGO_HOW=leave (default, the 0412 case): from the wheel, the map's own teleport (teleportMgr.requestTeleportToIsland)
    to CARGO_FROM, or to his return location when the map offers only that. Leaving the ship this way sold nothing
    before 0412.
  CARGO_HOW=anchor: sailing.sail_to home and Drop Anchor (the sale that always worked; the end-of-voyage panel too).
Ashore it waits up to CARGO_WAIT s for the sale: the chat line "You sold your plunder for N gold!" (setSystemMessage,
SOLD) and the pocket gold. A solo pirate is paid the whole hold (no captain bonus without a crew).
PASS = plunder went into the hold, the line came, the pocket rose by exactly its N, N is inside what the containers'
goods can be worth, and the ship's owner view shows an empty hold. FAIL names which of these failed; "paid nothing,
hold kept" is the pre-0412 bug.
Lines: CARGO-START, sysmsg (every system chat line), LAUNCH-SALE, SHIPFIGHT-*, CARGO-IN, CARGO-HOME, SOLD, CARGO-END,
then PASS / FAIL. Test pirates only: pirate 100000170 and ship 100000173 are refused.
env: CARGO_HOW (leave), CARGO_FROM (SHIPFIGHT_FROM), CARGO_WAIT (30), CARGO_IN_SECS (15), plus every SHIPFIGHT_*."""
import os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0])))
import s_lanes      # noqa: E402
import s_shipfight  # noqa: E402
import sailing      # noqa: E402

HOW = os.environ.get('CARGO_HOW', 'leave').lower()
FROM = os.environ.get('CARGO_FROM', s_shipfight.FROM)
WAIT = float(os.environ.get('CARGO_WAIT', '30'))
IN_SECS = float(os.environ.get('CARGO_IN_SECS', '15'))
NEVER_AV, NEVER_SHIP = 100000170, 100000173
SOLD_RE = re.compile(r'You sold your plunder for (\d+) gold')


def holdRange(cargo, EG):
    """Pure. (lo, hi) gold the hold can sell for: each container opens into one of its goods (EG.getAllCargoType),
    worth EG.getCargoValue. A container with no goods is worth 0."""
    lo = hi = 0
    for c in cargo or ():
        vals = [EG.getCargoValue(g) or 0 for g in (EG.getAllCargoType(c) or ())]
        if vals:
            lo += min(vals)
            hi += max(vals)
    return lo, hi


def soldGold(texts):
    """Pure. The gold named by every "You sold your plunder for N gold!" line in texts."""
    out = []
    for t in texts:
        m = SOLD_RE.search(str(t))
        if m:
            out.append(int(m.group(1)))
    return out


def judge(cargoIn, gain, sold, rng, cargoAfter):
    """Pure. -> ('PASS' | 'FAIL', why). cargoIn: the hold after the sink; gain: pocket gold after - before the leave;
    sold: soldGold of the lines after the leave; rng: holdRange of cargoIn; cargoAfter: the owner view's hold ashore
    (None = not known)."""
    if not cargoIn:
        return 'FAIL', 'the sink put nothing in the hold'
    n = len(cargoIn)
    if not sold and not gain:
        return 'FAIL', 'left the ship with %d containers aboard and was paid nothing: the hold was kept' % n
    if not sold:
        return 'FAIL', 'the gold went up %s but no "You sold your plunder" line came' % gain
    if gain != sum(sold):
        return 'FAIL', 'the line said %d gold but the pocket went up %s' % (sum(sold), gain)
    if rng and rng[1] and not (max(1, rng[0]) <= gain <= rng[1]):
        return 'FAIL', 'paid %d for %d containers, whose goods are worth %d to %d' % (gain, n, rng[0], rng[1])
    if cargoAfter:
        return 'FAIL', 'paid %d, but the ship still shows %d containers in its hold' % (gain, len(cargoAfter))
    return 'PASS', 'sold %d containers for %d gold' % (n, gain)


def launchSale(pre, sold):
    """Pure. A hold that was not empty before the launch must sell at the launch (0412's dinghy half)."""
    if pre and not sold:
        return 'sailed out with %d containers still in the hold (no sale at the launch)' % len(pre)
    return None


def cargoOf(o):
    try:
        return list(getattr(o, 'cargo', None) or [])
    except Exception:
        return []


def run(H):
    from pirates.economy import EconomyGlobals
    la, cr = H.la, H.cr
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    if la.doId == NEVER_AV or NEVER_SHIP in ships[:1]:
        H.ev('FAIL', why='refused: pirate %d / ship %d are never used by a test' % (NEVER_AV, NEVER_SHIP)); return
    if not ships:
        H.ev('FAIL', why='the pirate owns no ship'); return
    sid = ships[0]
    if not (yield from s_lanes.onIsland(H, 'cargo', FROM)):
        H.ev('FAIL', why='could not get to %s' % FROM, area=H.area()); return

    msgs = []                       # [t, phase, text]
    phase = ['launch']
    origMsg = la.setSystemMessage

    def sysmsg(aboutId, chatString, *a, **k):
        msgs.append([time.time(), phase[0], str(chatString)])
        H.ev('sysmsg', phase=phase[0], text=str(chatString)[:120])
        return origMsg(aboutId, chatString, *a, **k)
    la.setSystemMessage = sysmsg

    def said(p):
        return soldGold(t for _, ph, t in msgs if ph == p)

    origEv = H.ev
    fought = {}

    def ev(kind, /, **kw):
        if kind in ('PASS', 'FAIL'):
            fought[kind] = kw
            kind = 'SHIPFIGHT-' + kind
        elif kind in ('SHIP-TARGET', 'FOE-SUNK') and phase[0] == 'launch':
            phase[0] = 'fight'      # the launch is over by the time a target is picked
        return origEv(kind, **kw)

    try:
        pre = cargoOf(cr.getOwnerView(sid))
        gold0 = s_lanes.gold(H)
        H.ev('CARGO-START', how=HOW, frm=FROM, ship=sid, gold=gold0, pre=pre, preRange=holdRange(pre, EconomyGlobals),
             gs=la.getGameState(), area=H.area())

        # 1. sink one enemy ship (s_shipfight launches, fights, waits for the sink's gold)
        H.ev = ev
        try:
            yield from s_shipfight.run(H)
        finally:
            H.ev = origEv
        bad = launchSale(pre, said('launch'))
        H.ev('LAUNCH-SALE', pre=len(pre), sold=said('launch'), ok=bad is None)
        if bad:
            H.ev('FAIL', why=bad); return
        if 'PASS' not in fought:
            H.ev('FAIL', why='sank no enemy ship, so no plunder (SHIPFIGHT-FAIL says why)', fight=fought.get('FAIL'))
            return

        # 2. the hold after the sink
        phase[0] = 'hold'
        t0 = time.time()
        cargoIn = []
        while time.time() - t0 < IN_SECS:
            cargoIn = cargoOf(cr.doId2do.get(sid)) or cargoOf(cr.getOwnerView(sid))
            if cargoIn:
                break
            yield 1
        rng = holdRange(cargoIn, EconomyGlobals)
        H.ev('CARGO-IN', cargo=cargoIn, n=len(cargoIn), worth=rng, aboard=sailing.onShip(H), gs=la.getGameState())
        if not cargoIn:
            H.ev('FAIL', why='the sink put nothing in the hold (no setCargo in %d s)' % IN_SECS); return
        if not sailing.onShip(H):
            H.ev('FAIL', why='not aboard the ship after the fight (gs %s)' % la.getGameState()); return

        # 3. home: off the ship by the map (0412) or Drop Anchor
        g1 = s_lanes.gold(H)
        phase[0] = 'home'
        if HOW == 'anchor':
            H.ev('CARGO-HOME', how='anchor', to=FROM, gold=g1)
            yield from sailing.sail_to(H, FROM, 'CARGO1 home to sell the hold')
            if not H.sailResult:
                H.ev('FAIL', why='did not get home and drop anchor (SAIL-FAIL says why)'); return
        else:
            rl = getattr(la, 'returnLocation', None)
            ok = [u for u in (FROM, rl) if u]
            allows = {}
            for u in ok:
                try:
                    allows[u] = bool(la.confirmIslandTeleport('from', islandUid=u))
                except Exception as e:
                    allows[u] = False
                    H.ev('map-check-err', uid=u, err=str(e))
            tgt = next((u for u in ok if allows.get(u)), None)
            H.ev('CARGO-HOME', how='map', to=tgt, allows=allows, returnLocation=rl, gold=g1)
            if tgt is None:
                H.ev('FAIL', why='the map offers no island to teleport to from the ship'); return
            cr.teleportMgr.requestTeleportToIsland(tgt)
            yield ('until', lambda: la.getGameState() == 'LandRoam' and sailing.hereUid(H) is not None, 150, 'ashore')
            if la.getGameState() != 'LandRoam':
                H.ev('FAIL', why='did not land after the teleport (gs %s)' % la.getGameState(), area=H.area()); return

        # 4. the sale
        yield ('until', lambda: said('home'), WAIT, 'sold line')
        yield 3
        g2 = s_lanes.gold(H)
        sold = said('home')
        cargoAfter = cargoOf(cr.getOwnerView(sid)) if cr.getOwnerView(sid) is not None else None
        H.ev('SOLD', sold=sold, before=g1, after=g2, gain=g2 - g1, worth=rng, cargoAfter=cargoAfter,
             lines=[t for _, ph, t in msgs if ph == 'home'][-5:])
        verdict, why = judge(cargoIn, g2 - g1, sold, rng, cargoAfter)
        H.ev('CARGO-END', verdict=verdict, why=why, how=HOW, start=gold0, gain=g2 - g1, n=len(cargoIn), area=H.area())
        H.ev(verdict, why=why, gold=g2 - g1)
    finally:
        la.setSystemMessage = origMsg
