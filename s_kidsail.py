"""KIDSAIL (pir-test, 11-18, brain's order): the published kid client (a v456 kid tree) against the live server as
the kids find it: on Port Royal (one map hop there if not), walk to the dinghy, launch the pirate's ship, take the
wheel, full sail for SAIL_SECS, then sail back and dock at Port Royal (anchor, land), then log out.
Lines: KIDSAIL-START, HOP, at-wheel, l (every 2 s at sea), SAILED, DOCKED, LOGOUT, then PASS or FAIL.
No magic words. Never runs on pirate 100000170. env: KIDSAIL_SECS (default 60), KIDSAIL_MOVE (default 300)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__', '.'))))
import sailing   # noqa: E402
import s_lanes   # noqa: E402
import s_relog   # noqa: E402

PR = s_lanes.PR
BANNED = (100000170,)
SECS = float(os.environ.get('KIDSAIL_SECS', '60'))
MOVE = float(os.environ.get('KIDSAIL_MOVE', '300'))


def run(H):
    la, cr, R = H.la, H.cr, H.render
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if la.doId in BANNED:
        H.ev('FAIL', why='KIDSAIL never runs on this pirate (his own)'); return
    H.ev('KIDSAIL-START', pirate=la.doId, here=sailing.hereUid(H), gs=la.getGameState(), gold=s_lanes.gold(H))
    if sailing.hereUid(H) != PR:
        yield 3
        t0 = time.time()
        cr.teleportMgr.requestTeleportToIsland(PR)
        while time.time() - t0 < 120 and not (sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam'):
            yield 0.5
        ok = sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam'
        H.ev('HOP', to='Port Royal', ok=ok, secs=round(time.time() - t0, 1), gs=la.getGameState())
        if not ok:
            H.ev('FAIL', why='map hop to Port Royal did not land'); return
        yield 5
    # a kid's ship can be sunk from an earlier trip: the dinghy then refuses it ("needs a shipwright"), so like a kid
    # go to the shipwright first (a broke pirate is repaired free, server-tree 0156)
    sid0 = list(la.getInventory().getShipDoIdList())[0]
    yield ('upto', lambda: cr.getOwnerView(sid0) is not None, 20, 'ship owner view')
    ov = cr.getOwnerView(sid0)
    H.ev('SHIP-STATE', ship=sid0, ov=ov is not None, hp=getattr(ov, 'Hp', None), maxHp=getattr(ov, 'maxHp', None))
    if ov is None or (getattr(ov, 'Hp', 0) or 0) < (getattr(ov, 'maxHp', 1) or 1):
        hp, paid = yield from sailing.repair(H, PR, sid0)
        yield 3
    ship = yield from sailing.launch(H, PR, False)
    if ship is None:
        H.ev('FAIL', why='could not launch the ship (see SAIL-FAIL)'); return
    sid = ship.doId
    p0 = ship.getPos(R)
    H.ev('at-wheel', ship=sid, hp=getattr(ship, 'Hp', None), pos=H.P(ship))
    messenger.send('w'); messenger.send('w-up')      # tap W: full sail
    t0 = time.time(); moved = 0.0
    while time.time() - t0 < SECS:
        if cr.doId2do.get(sid) is None or la.getGameState() != 'ShipPilot':
            H.ev('FAIL', why='left the ship while sailing', gs=la.getGameState()); return
        p = ship.getPos(R)
        moved = (p - p0).length()
        H.ev('l', pos=[round(p[0]), round(p[1])], moved=round(moved), hp=getattr(ship, 'Hp', None))
        yield 2.0
    H.ev('SAILED', moved=round(moved), secs=SECS, hp=getattr(ship, 'Hp', None))
    if moved < MOVE:
        H.ev('FAIL', why='ship did not move under full sail', moved=round(moved), need=MOVE); return
    yield from sailing.sail_to(H, PR, why='kidsail dock')
    docked = bool(getattr(H, 'sailResult', False))
    H.ev('DOCKED', ok=docked, here=sailing.hereUid(H), gs=la.getGameState())
    if not docked:
        H.ev('FAIL', why='did not dock back at Port Royal (see SAIL-FAIL)'); return
    out = yield from s_relog.logout(H)
    H.ev('LOGOUT', ok=bool(out))
    if out:
        H.ev('PASS', what='kid client: launched at Port Royal, sailed %ds, docked, logged out' % SECS, moved=round(moved))
    else:
        H.ev('FAIL', why='the logout')
