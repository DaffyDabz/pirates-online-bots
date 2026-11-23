"""Sail proof: deploy own ship by dinghy, take the wheel (the Shift 'use' action -> ShipPilot),
sail forward ~60 s, let go of the wheel, idle 20 s. The client must stay up."""
import time
from direct.showbase.InputStateGlobal import inputState


def near(H, obj, d=4):
    R = H.render
    p = obj.getPos(R)
    H.la.setPos(R, p + R.getRelativeVector(obj, (0, 1, 0)) * d)
    H.la.headsUp(obj)
    H.la.setP(0); H.la.setR(0)


def cls(o):
    return type(o).__name__


def sst(s):
    try:
        return s.queryGameState() if s is not None else None
    except Exception as e:
        return "?%s" % e


def run(H):
    la = H.la
    ships = list(la.getInventory().getShipDoIdList())
    H.ev('sail-start', gs=la.getGameState(), area=H.area(), ships=ships, qids=H.qids(),
         dinghy=[(o['doId'], o['dist']) for o in H.objs('Dinghy')][:3])
    if not ships:
        return
    sid = ships[0]
    # 0. repair the harness ship at the shipwright's (it sits at 0 Hp from older runs)
    inv = la.getInventory()
    sk = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedShopKeeper']
    g0 = inv.getGoldInPocket()
    if sk:
        sk[0].sendUpdate('requestPurchaseRepair', [sid])
        yield 5
    H.ev('repair', shopkeepers=len(sk), gold=[g0, inv.getGoldInPocket()])
    # 1. deploy by the nearest dinghy
    for tries in range(4):
        if sid in H.cr.doId2do:
            break
        dg = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedDinghy']
        if not dg:
            isl = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedIsland' and 'Port Royal' in str(getattr(o, 'name', ''))]
            if isl:   # Port Royal dock dinghy (worldData PortRoyalIsland.py)
                la.setPos(isl[0], 455, -1995, 12)
            H.ev('no-dinghy', area=H.area(), la=H.P(la)); yield 8; continue
        dg.sort(key=lambda d: (d.getPos(H.render) - la.getPos(H.render)).length())
        d = dg[0]
        near(H, d, 4)
        d.requestInteraction(la.doId)
        yield 3
        try:
            d.ownShipSelected(sid)
        except Exception as e:
            H.ev('ownShipSelected-err', err=str(e))
        H.ev('deploy', dinghy=d.doId, ship=sid)
        yield 25
    ship = H.cr.doId2do.get(sid)
    H.ev('deployed', have=ship is not None, gs=la.getGameState(),
         parent=str(la.getParent())[-60:], shipState=sst(ship), shipCls=cls(ship) if ship else None)
    if ship is None:
        return
    for i in range(6):
        yield 5
        H.ev('wait-ship', gs=la.getGameState(), shipState=sst(ship), hp=getattr(ship, 'Hp', None), shp=getattr(ship,'maxHp',None),
             wheelsAll=[(cls(o), o.doId, getattr(o, 'shipId', None)) for o in H.cr.doId2do.values() if 'Wheel' in cls(o)][:4])
        if la.getGameState() != 'Cutscene':
            break
    # 2. take the wheel (what Shift at the wheel does)
    wheels = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedSteeringWheel'
              and getattr(o, 'shipId', None) == sid]
    H.ev('wheels', n=len(wheels))
    if not wheels:
        return
    w = wheels[0]
    near(H, w, 3)
    w.requestInteraction(la.doId)
    yield 6
    H.ev('at-wheel', gs=la.getGameState(), shipState=sst(ship))
    # 3. sail ~60 s
    inputState.set('forward', True, inputSource=inputState.WASD)
    t0 = time.time()
    while time.time() - t0 < 60:
        yield 10
        navy = [o for o in H.cr.doId2do.values() if 'Ship' in cls(o) and o.doId != sid and hasattr(o, 'queryGameState')]
        H.ev('sailing', t=round(time.time() - t0), gs=la.getGameState(), pos=H.P(ship),
             speed=round(getattr(ship, 'getSpeed', lambda: 0)() or 0, 1) if hasattr(ship, 'getSpeed') else None,
             otherShips=len(navy))
    inputState.set('forward', False, inputSource=inputState.WASD)
    yield 5
    # 4. let go of the wheel
    try:
        w.requestExit()
    except Exception as e:
        H.ev('exit-err', err=str(e))
    yield 20
    H.ev('sail-done', gs=la.getGameState(), shipState=sst(ship))
