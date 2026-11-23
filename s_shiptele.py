"""Teleport from a ship (11-16): the server's teleport manager found no world for a pirate standing on a ship (ship ->
ocean grid -> world) and sent a pirate at sea to his return location instead of the island he asked for (server-tree
patch 0045 fixes both). This script sails out and teleports to an island from the wheel, twice:
  leg A, the map: the map's own call (teleportMgr.requestTeleportToIsland). For an island of the world we sail in the
    client teleports itself (the 'local' path); the event says which path it took.
  leg B, the server: the message the map sends when the island is not one the client has (requestTeleportToIsland
    to the server, the path that failed), to Tortuga or Port Royal but never the return location, so landing at the
    return location (the old bug) shows up as a FAIL.
  leg L, the map from land: the same call as leg A, standing on the island leg B landed on, to the other one. Before
    patch 0053 the map refused every island, on land and at sea (no flag's check survived, so "no island token"
    blocked outright; the privateer line SHIPTELE1 logged was only the next flag the bot read).
Legs A and B: launch at the island we stand on, full sail SAIL s, drop sail, teleport, land on the island (LandRoam
there), then hold HOLD s on it with no kick. Leg L: teleport, land, hold.
Events: SHIPTELE-START, sailing's launch events, at-sea, tele (with the teleport flags word and which flags have a
check), warning (each on-screen warning: a refusal's reason), tele-out, state (each game state / area change), landed,
hold, leg-pass, then PASS or FAIL. The run's walk-X.err must also hold 0 tracebacks, and the AI log no
'Cannot initiate teleport'.
env: SHIPTELE_SAIL (default 15 s under full sail), SHIPTELE_HOLD (default 60 s on the island), SHIPTELE_LEGS (default
ABL)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402
from s_dock import cls   # noqa: E402

PR = '1150922126.8dzlu'
TORTUGA = '1156207188.95dzlu'
CUBA = '1160614528.73sdnaik'
NAMES = {PR: 'Port Royal', TORTUGA: 'Tortuga', CUBA: 'Cuba'}
SAIL = float(os.environ.get('SHIPTELE_SAIL', '15'))
HOLD = float(os.environ.get('SHIPTELE_HOLD', '60'))
LEGS = os.environ.get('SHIPTELE_LEGS', 'ABL').upper()


def run(H):
    from panda3d.core import BitMask32, DatagramIterator
    from pirates.piratesbase import PiratesGlobals
    la, cr = H.la, H.cr
    got = {}
    orig = cr.handleGoGetLost

    def ggl(di):
        code = None
        try:
            code = DatagramIterator(di.getDatagram(), di.getCurrentIndex()).getUint16()
        except Exception:
            pass
        got['kicked'] = code
        H.ev('KICKED', code=code)
        return orig(di)
    cr.handleGoGetLost = ggl

    # every on-screen warning (a refused teleport shows its reason as one)
    warnings = []
    origWarn = la.guiMgr.createWarning

    def warn(msg, *a, **k):
        warnings.append(msg)
        H.ev('warning', msg=msg)
        return origWarn(msg, *a, **k)
    la.guiMgr.createWarning = warn

    def blockers():
        # each flag that stops a teleport out: its reason and whether it has a check. Reads only; the game's own
        # getNextTeleportConfirmFlag changed the pirate's flags in place before patch 0053
        out = []
        word = la.teleportFlags.getWord() & PiratesGlobals.TFNoTeleportOut.getWord()
        for i in range(32):
            if word & (1 << i):
                f = BitMask32.bit(i)
                out.append(dict(bit=i, why=PiratesGlobals.TFNoTeleportReasons.get(f, ''),
                                check=la.teleportConfirmCallbacks.get(f, (None, []))[0] is not None))
        return out

    def flags():
        return dict(flags=la.teleportFlags.getWord(), checks=sorted(k.getHighestOnBit() for k in la.teleportConfirmCallbacks),
                    blockers=blockers())

    last = {}

    def note(leg):
        # one event each time the game state or the area changes (TeleportOut, the teleport zone, TeleportIn...)
        now = (la.getGameState(), H.area())
        if now != last.get('s'):
            last['s'] = now
            H.ev('state', leg=leg, gs=now[0], area=now[1], pos=H.P(la))

    def watch(leg, cond, secs):
        """Generator: poll cond every 0.25 s for secs, noting state changes. -> True when it held."""
        t0 = time.time()
        while time.time() - t0 < secs:
            note(leg)
            if 'kicked' in got:
                return False
            if cond():
                return True
            yield 0.25
        return cond()

    def mapAllows(uid):
        # the map's own check for picking an island (DistributedPlayerPirate.confirmIslandTeleport)
        try:
            return bool(la.confirmIslandTeleport('from', islandUid=uid))
        except Exception as e:
            H.ev('map-check-err', uid=uid, err=str(e))
            return False

    def where():
        return dict(gs=la.getGameState(), area=H.area(), here=sailing.hereUid(H), aboard=sailing.onShip(H),
                    returnLocation=getattr(la, 'returnLocation', None), currentIsland=getattr(la, 'currentIsland', None))

    yield ('until', lambda: la.getGameState() in ('LandRoam', 'ShipPilot', 'WaterRoam'), 60, 'LandRoam')
    aboard = sailing.onShip(H)
    tokens = dict((NAMES[u], bool(la.hasIslandTeleportToken(u))) for u in NAMES)
    H.ev('SHIPTELE-START', legs=LEGS, sail=SAIL, hold=HOLD, tokens=tokens, **where())
    if not aboard and sailing.hereUid(H) != PR:      # the game's own teleport to Port Royal's open ground
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
        aboard = False

    def sailOut(leg):
        """Generator: launch at the island we stand on, full sail SAIL s, drop sail. -> the ship, or None."""
        frm = sailing.hereUid(H)
        ship = yield from sailing.launch(H, frm, sailing.onShip(H))
        if ship is None:
            return None
        messenger.send('w'); messenger.send('w-up')      # tap W: full sail, off the dock
        yield SAIL
        messenger.send('s'); messenger.send('s-up')      # tap S: drop sail
        yield 3
        grid = ship.getParentObj()
        H.ev('at-sea', leg=leg, ship=ship.doId, frm=NAMES.get(frm, frm), pos=H.P(ship), grid=cls(grid) if grid else None,
             zone=getattr(ship, 'zoneId', None), **where())
        return ship

    results = {}
    for leg in LEGS:
        if leg not in 'ABL':
            continue
        frm = sailing.hereUid(H)
        if leg == 'L':
            # the map from land: standing on the island the last leg landed on
            if sailing.onShip(H) or la.getGameState() != 'LandRoam' or not frm:
                H.ev('FAIL', leg=leg, why='not standing on an island for the land leg', **where()); return
            sid = None
        else:
            ship = yield from sailOut(leg)
            if ship is None:
                H.ev('FAIL', leg=leg, why='could not launch the ship (see SAIL-FAIL)', **where()); return
            if not sailing.onShip(H) or la.getGameState() != 'ShipPilot':
                H.ev('FAIL', leg=leg, why='not at the wheel after sailing out', **where()); return
            sid = ship.doId
        if leg in 'AL':
            # the map: an island the map lets him pick (a teleport token, or his return location), not the one we
            # sailed from when there is a choice; from land, never the island he stands on
            ok = sorted([u for u in (TORTUGA, PR) if mapAllows(u) and not (leg == 'L' and u == frm)],
                        key=lambda u: u == frm)
            if not ok and leg == 'L':
                # SHIPTELE4: on land with no token the map offers only his return location, the island he stands on
                # (the game's own rule), so there is nothing to pick; A and B decide the run
                H.ev('leg-skip', leg=leg, why='no teleport token: the map only offers his return location, as in the '
                     'real game', tokens=tokens, **where())
                continue
            if not ok:
                H.ev('FAIL', leg=leg, why='the map would not let him pick Tortuga or Port Royal (no teleport token)',
                     tokens=tokens, **where()); return
            tgt = ok[0]
            isl = cr.getDo(cr.uidMgr.getDoId(tgt))
            path = 'local' if isl is not None and isl.getParentObj() is cr.activeWorld else 'server'
            n = len(warnings)
            H.ev('tele', leg=leg, how='map', to=NAMES[tgt], uid=tgt, path=path, ship=sid, **dict(where(), **flags()))
            cr.teleportMgr.requestTeleportToIsland(tgt)
            if len(warnings) > n:
                H.ev('FAIL', leg=leg, why='the map refused the teleport', said=warnings[n:], **dict(where(), **flags()))
                return
        else:
            # the server: what the map sends for an island the client does not have; never to the return location,
            # so landing there (the old bug) is a FAIL; not back to where we sailed from when there is a choice
            rl = getattr(la, 'returnLocation', None)
            tgt = sorted([u for u in (TORTUGA, PR) if u != rl], key=lambda u: u == frm)[0]
            H.ev('tele', leg=leg, how='server', to=NAMES[tgt], uid=tgt, ship=sid, **where())
            cr.teleportMgr.sendUpdate('requestTeleportToIsland', [tgt])
        t0 = time.time()
        if not (yield from watch(leg, lambda: la.getGameState() == 'TeleportOut', 30)):
            H.ev('FAIL', leg=leg, why='the teleport never started (no TeleportOut in 30 s); for leg B see ai.log '
                 '"Cannot initiate teleport"', canTeleport=la.canTeleport(), said=warnings[-3:],
                 kicked=got.get('kicked'), **dict(where(), **flags())); return
        H.ev('tele-out', leg=leg, secs=round(time.time() - t0, 1))
        landedOn = {}

        def landed():
            h = sailing.hereUid(H)
            if h and la.getGameState() == 'LandRoam':
                landedOn['uid'] = h
                return True
            return False
        if not (yield from watch(leg, landed, 120)):
            H.ev('FAIL', leg=leg, why='did not land on an island in 120 s', kicked=got.get('kicked'), **where()); return
        if landedOn['uid'] != tgt:
            H.ev('FAIL', leg=leg, why='landed on the wrong island', want=NAMES[tgt],
                 got=NAMES.get(landedOn['uid'], landedOn['uid']), **where()); return
        H.ev('landed', leg=leg, on=NAMES[tgt], secs=round(time.time() - t0, 1), shipSeen=sid in cr.doId2do, **where())
        # hold on the island: not kicked, not moved off it, the game still up
        t1 = time.time()
        # in the water counts as off the island: SHIPTELE2's map teleport landed him in the sea at Port Royal's origin
        # (no spawn point; patch 0054) and still passed
        while time.time() - t1 < HOLD:
            yield from watch(leg, lambda: 'kicked' in got or sailing.hereUid(H) != tgt or la.getGameState() == 'WaterRoam',
                             10)
            bad = 'kicked' in got or sailing.hereUid(H) != tgt or la.getGameState() == 'WaterRoam'
            H.ev('hold', leg=leg, secs=round(time.time() - t1), shipSeen=sid in cr.doId2do, pos=H.P(la), **where())
            if bad:
                H.ev('FAIL', leg=leg, why='kicked, in the water or moved off the island during the hold',
                     kicked=got.get('kicked'), pos=H.P(la), **where()); return
        results[leg] = NAMES[tgt]
        H.ev('leg-pass', leg=leg, on=NAMES[tgt], **where())
        if sid is not None:
            # the ship he left is put away; wait for it to leave the client, or the next launch walks to its wheel
            yield from watch(leg, lambda: sid not in cr.doId2do, 30)
            H.ev('ship-gone', leg=leg, ship=sid, gone=sid not in cr.doId2do)
        yield 3
    if not results:
        H.ev('FAIL', why='no leg ran', legs=LEGS); return
    H.ev('PASS', what='teleported from the wheel at sea to the island asked for, landed and held there', legs=results,
         hold=HOLD)
