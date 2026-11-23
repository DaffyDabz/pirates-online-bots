"""Sail proof: deploy own ship by dinghy, take the wheel (the Shift 'use' action -> ShipPilot),
sail forward ~60 s, let go of the wheel, idle 20 s. The client must stay up."""
import time, os
GSECS = float(os.environ.get('SAIL_GSECS','10'))
RATES = [int(x) for x in os.environ.get('SAIL_RATES','120,30').split(',')]
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
    # 3. measure
    if os.environ.get('SAIL_OLD'):
        import importlib.util
        from pirates.ship import ShipPilot2 as SP2
        spec = importlib.util.spec_from_file_location('SP2old', os.path.join(os.path.dirname(os.environ['PROOF_SCRIPT']), 'ShipPilot2_old.py'))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        SP2.ShipPilot2.handleAvatarControls = m.ShipPilot2.handleAvatarControls
        H.ev('old-pilot-patched')
    # 3b. measure: press W like the keyboard does (messenger 'w' -> startAutoSailing + inputState forward)
    from panda3d.core import ClockObject
    gc = ClockObject.getGlobalClock()
    ctl = ship.controlManager.controls.get('ship') if ship.controlManager else None
    def sample(tag, t, p0):
        po = ship.node().getPhysicsObject()
        p = ship.getPos(H.render)
        H.ev('m', tag=tag, t=t, fps=round(gc.getAverageFrameRate(), 1), dt=round(gc.getDt(), 4),
             acc=getattr(ship, 'acceleration', None), maxSpeed=getattr(ship, 'maxSpeed', None),
             Sp=ship.Sp, maxSp=ship.maxSp, Hp=getattr(ship, 'Hp', None), mass=getattr(ship, 'mass', None),
             auto=ship.getIsAutoSailing(), ready=getattr(ship, 'sailsReady', None),
             fwd=inputState.isSet('forward'), vel=round(po.getVelocity().length(), 2),
             pspeed=getattr(ctl, '_ShipPilot2__speed', None), sdt=round(getattr(ctl, 'straightSailDt', 0), 1),
             dist=round((p - p0).length(), 1), gs=la.getGameState(), st=sst(ship))
    for rate in RATES:
        gc.setMode(ClockObject.MForced); gc.setFrameRate(rate)
        yield 3
        for k in range(10):
            if ship.sailsReady: break
            yield 1
        p0 = ship.getPos(H.render)
        messenger.send('w')
        t0 = gc.getFrameTime(); nxt = 2
        while gc.getFrameTime() - t0 < GSECS:
            yield 0.5
            if gc.getFrameTime() - t0 >= nxt:
                nxt += 2; sample('W@%d' % rate, round(gc.getFrameTime() - t0, 1), p0)
        messenger.send('w-up')
        for k in range(10):
            if ship.sailsReady: break
            yield 1
        messenger.send('s'); messenger.send('s-up')
        yield 8
        sample('stop@%d' % rate, 0, p0)
    gc.setMode(ClockObject.MLimited); gc.setFrameRate(120)
    H.ev('sail-done', gs=la.getGameState(), shipState=sst(ship))

