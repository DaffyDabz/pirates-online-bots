"""Ship repair measurement (11-16, after BATTLE2 sailed a sunk ship): does the shipwright's repair go through, and
which signal shows it on the client? At Port Royal: give quest gold when short (test setup, logged), then
sailing.repair: walk to the shipwright like a player and press his repair button (the game's own
sendRequestRepairShip). Then log gold and the ship's owner-view Hp every second for 8 s.
REPAIR1 looked for class 'DistributedShopKeeper', found none (every townsperson is a shop: DistributedNPCTownfolk)
and never sent a repair.
Events: REPAIR-START, repair, rp (every 1 s), then PASS (a measurement: passes once the data is logged)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402

PR = '1150922126.8dzlu'


def run(H):
    la = H.la
    yield ('until', lambda: la.getGameState() == 'LandRoam', 60, 'LandRoam')
    if sailing.hereUid(H) != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
    inv = la.getInventory()
    gold = inv.getGoldInPocket()
    if gold < 500:
        H.mw('gold 2000')
        yield 3
        H.ev('SETUP-GOLD', before=gold, after=inv.getGoldInPocket())
    sid = list(inv.getShipDoIdList())[0]
    ov = H.cr.getOwnerView(sid)
    H.ev('REPAIR-START', ship=sid, ov=ov is not None, hp=getattr(ov, 'Hp', None), maxHp=getattr(ov, 'maxHp', None),
         gold=inv.getGoldInPocket(), spots=len(sailing.shipwrightSpots(PR)), inInterest=len(sailing.shipwrights(H)))
    hp, paid = yield from sailing.repair(H, PR, sid)
    for i in range(8):
        yield 1.0
        ov = H.cr.getOwnerView(sid)
        H.ev('rp', t=i + 1, hp=getattr(ov, 'Hp', None), gold=inv.getGoldInPocket())
    H.ev('PASS', paid=paid, hp=getattr(ov, 'Hp', None), gold=inv.getGoldInPocket())
