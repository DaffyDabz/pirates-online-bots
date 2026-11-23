"""Launch proof: walk to Port Royal's dinghy like a player (within the game's 25 ft use circle, dock or water), launch
the pirate's first ship, take the wheel, tap W for full sail and check the ship really moves.
Events: LAUNCH-START, then sailing's walk/launch events, l (every 1 s at sea), then PASS or FAIL.
PASS = steering our own ship and it moved >= LAUNCH_MOVE ft in LAUNCH_SECS s at sea. FAIL says why.
Also the quick check that wave 2's repair spots do not break boarding (ship arrives, wheel taken, client alive).
env: LAUNCH_SECS (default 25), LAUNCH_MOVE (default 150)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402
from s_dock import cls   # noqa: E402

PR = '1150922126.8dzlu'
SECS = float(os.environ.get('LAUNCH_SECS', '25'))
MOVE = float(os.environ.get('LAUNCH_MOVE', '150'))


def run(H):
    la = H.la
    R = H.render
    yield ('until', lambda: la.getGameState() in ('LandRoam', 'ShipPilot', 'WaterRoam'), 60, 'LandRoam')
    aboard = sailing.onShip(H)
    H.ev('LAUNCH-START', aboard=aboard, here=sailing.hereUid(H), gs=la.getGameState(), la=H.P(la))
    if not aboard and sailing.hereUid(H) != PR:      # the game's own teleport to Port Royal's open ground
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
    ship = yield from sailing.launch(H, sailing.hereUid(H), aboard)
    if ship is None:
        H.ev('FAIL', why='could not launch the ship (see SAIL-FAIL)'); return
    sid = ship.doId
    spots = [o.doId for o in H.cr.doId2do.values() if cls(o) == 'DistributedShipRepairSpot' and getattr(o, 'shipId', sid) == sid]
    p0 = ship.getPos(R)
    H.ev('at-wheel', ship=sid, hp=getattr(ship, 'Hp', None), repairSpots=len(spots), pos=H.P(ship))
    messenger.send('w'); messenger.send('w-up')      # tap W: full sail
    t0 = time.time()
    moved = 0.0
    while time.time() - t0 < SECS:
        if H.cr.doId2do.get(sid) is None or la.getGameState() != 'ShipPilot':
            H.ev('FAIL', why='left the ship', gs=la.getGameState()); return
        p = ship.getPos(R)
        moved = (p - p0).length()
        try:
            vel = ship.node().getPhysicsObject().getVelocity().length()
        except Exception:
            vel = 0
        H.ev('l', pos=[round(p[0]), round(p[1])], vel=round(vel, 1), moved=round(moved), hp=getattr(ship, 'Hp', None))
        yield 1.0
    messenger.send('s'); messenger.send('s-up')      # tap S: drop sail
    if moved >= MOVE:
        H.ev('PASS', what='launched at Port Royal, took the wheel, sailed', moved=round(moved), secs=SECS, repairSpots=len(spots))
    else:
        H.ev('FAIL', why='ship did not move under full sail', moved=round(moved), need=MOVE)
