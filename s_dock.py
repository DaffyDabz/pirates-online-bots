"""Item 6: dock at Tortuga the way a kid does. Deploy by Tortuga's dinghy, take the wheel, sail out past the
port sphere (anchor must go away), turn back and steer at the shore with the keyboard (w / a / d / s),
stop at the shore, check the anchor stays up, click it, land, then walk to Jack (c3visitJack).
Every 0.5 s at sea: dist to the island centre, ship z, port, anchor shown, Hp, jumps, warnings, enemies.
PASS = anchor shown >= 10 s continuous once stopped, no jump, z never below start-1, lands in Tortuga, quest moves.
Only then does it emit the PASS event (run_walk.ps1's two-strike rule counts a run as passed on PASS alone)."""
import os, time, math, runpy
from panda3d.core import Point3, Vec3

TORTUGA = '1156207188.95dzlu'
OUT_R = float(os.environ.get('DOCK_OUT', '3700'))     # port sphere (level 1) is 3200 at Tortuga
SAIL_SECS = float(os.environ.get('DOCK_SAIL_SECS', '420'))


def cls(o):
    return type(o).__name__


def near(H, obj, d=4):
    """Generator (yield from): walk up to obj like a player (held keys, no setPos) until within d ft, then face it.
    -> True when there, False when it could not get there (the stuck / leg events say why)."""
    ok = yield from H.walk_to(obj, arrive=d, face=True, tag='near ' + cls(obj))
    return ok


def island(H):
    for o in H.cr.doId2do.values():
        if cls(o) == 'DistributedIsland' and getattr(o, 'uniqueId', None) == TORTUGA:
            return o
    return None


def centre(H, isl):
    zc = getattr(isl, 'zoneCenter', None) or getattr(isl, 'sphereCenter', None) or (0, 0)
    return H.render.getRelativePoint(isl, Point3(zc[0], zc[1], 0))


def anchorShown(ship):
    sd = getattr(ship, 'shipStatusDisplay', None)
    b = getattr(sd, 'anchorButton', None) if sd else None
    try:
        return bool(b) and not b.isHidden()
    except Exception:
        return False


class Keys:
    """Keyboard-like steering: press / release the same messenger events the keys send."""
    def __init__(self, H):
        self.H = H
        self.down = set()

    def set(self, k, on):
        if on and k not in self.down:
            messenger.send(k); self.down.add(k)
        elif not on and k in self.down:
            messenger.send(k + '-up'); self.down.discard(k)

    def steer(self, ship, target, dead=6.0):
        """Turn toward a render-space point. Returns the bearing in degrees (+ = right)."""
        rel = ship.getRelativePoint(self.H.render, target)
        brg = math.degrees(math.atan2(rel[0], rel[1]))
        self.set('a', brg < -dead)
        self.set('d', brg > dead)
        return brg

    def release(self):
        for k in list(self.down):
            self.set(k, False)


def run(H):
    la = H.la
    warns = []
    try:
        orig = la.guiMgr.createWarning

        def cw(text, *a, **k):
            warns.append(str(text)[:80])
            H.ev('warning', text=str(text)[:120])
            return orig(text, *a, **k)
        la.guiMgr.createWarning = cw
    except Exception as e:
        H.ev('warn-hook-err', err=str(e))

    ships = list(la.getInventory().getShipDoIdList())
    H.ev('dock-start', gs=la.getGameState(), area=H.area(), ships=ships, qids=H.qids())
    if not ships:
        H.ev('FAIL', why='no ship'); return
    sid = ships[0]
    if 'c3visitJack' not in H.qids() and 'c3visitJack' not in H.hist():
        H.mw('giveQuest c3visitJack')
        yield ('until', lambda: 'c3visitJack' in H.qids(), 15, 'give c3visitJack')
    # 0. to Tortuga on foot
    if H.area() is None or H.area()[1] != TORTUGA:
        H.mw('areaTeleport %s' % TORTUGA)
        yield ('until', lambda: H.area() is not None and H.area()[1] == TORTUGA and la.getGameState() == 'LandRoam', 90, 'tp Tortuga')
        yield 5
    H.ev('at-tortuga', area=H.area(), la=H.P(la), qids=H.qids())
    # repair (harness ship can be at 0 Hp from older runs)
    sk = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedShopKeeper']
    if sk:
        sk[0].sendUpdate('requestPurchaseRepair', [sid]); yield 4
    # 1. deploy by the nearest dinghy
    for tries in range(4):
        if sid in H.cr.doId2do:
            break
        dg = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedDinghy']
        if not dg:
            # logged in somewhere in town, out of the dock's grid cells: walk to the teleport
            # arrival point by the dock (DOCK2: areaTeleport landed here, dinghy in interest)
            H.ev('no-dinghy', area=H.area(), la=H.P(la))
            if not (yield from H.walk_to((10415.7, 16924.7, 7.0), arrive=3.0, tag='to-dock')):
                H.ev('FAIL', why='could not walk to the dock', la=H.P(la)); return
            yield 8; continue
        dg.sort(key=lambda d: (d.getPos(H.render) - la.getPos(H.render)).length())
        d = dg[0]
        if not (yield from near(H, d, 4)):
            H.ev('FAIL', why='could not walk up to the dinghy', la=H.P(la)); return
        d.requestInteraction(la.doId)
        yield 3
        try:
            d.ownShipSelected(sid)
        except Exception as e:
            H.ev('ownShipSelected-err', err=str(e))
        H.ev('deploy', dinghy=d.doId, ship=sid)
        yield 25
    ship = H.cr.doId2do.get(sid)
    if ship is None:
        H.ev('FAIL', why='ship never arrived'); return
    yield ('until', lambda: la.getGameState() != 'Cutscene', 40, 'launch cutscene')
    # 2. take the wheel
    wheels = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedSteeringWheel' and getattr(o, 'shipId', None) == sid]
    if not wheels:
        H.ev('FAIL', why='no wheel'); return
    if not (yield from near(H, wheels[0], 3)):
        H.ev('FAIL', why='could not walk up to the wheel', la=H.P(la)); return
    wheels[0].requestInteraction(la.doId)
    yield ('until', lambda: getattr(ship, 'steeringAvId', None) == la.doId, 20, 'take wheel')
    isl = island(H)
    if isl is None:
        H.ev('FAIL', why='Tortuga island object not in interest at sea'); return
    deps = [o for o in H.cr.doId2do.values() if cls(o) == 'DistributedShipDeployer' and o.getParentObj() is isl]
    dep = deps[0] if deps else None
    H.ev('at-wheel', gs=la.getGameState(), steer=getattr(ship, 'steeringAvId', None), port=la.getPort(),
         anchor=anchorShown(ship), zoneRadii=getattr(isl, 'zoneRadii', None), zoneCenter=getattr(isl, 'zoneCenter', None),
         deployer=(dep.doId, dep.minRadius, dep.maxRadius, H.P(dep)) if dep else None)

    keys = Keys(H)
    z0 = ship.getZ(H.render)
    # the deployer (and its interest) goes away past the port sphere: keep where it was
    depPos = dep.getPos(H.render) if dep is not None else None
    depMin = dep.minRadius if dep is not None else None
    st = {'last': ship.getPos(H.render), 'minZ': z0, 'jumps': [], 'anchorRun': 0.0, 'anchorBest': 0.0,
          'flips': 0, 'lastA': anchorShown(ship), 'hpMin': getattr(ship, 'Hp', None)}

    def sample(phase, target=None):
        p = ship.getPos(H.render)
        c = centre(H, isl)
        d = (Vec3(p[0] - c[0], p[1] - c[1], 0)).length()
        step = (p - st['last']).length()
        try:
            vel = ship.node().getPhysicsObject().getVelocity().length()
        except Exception:
            vel = 0
        if step > 30 + vel * 0.5 * 1.5:
            st['jumps'].append((phase, round(step, 1), [round(v, 1) for v in st['last']], [round(v, 1) for v in p]))
            H.ev('JUMP', phase=phase, step=round(step, 1), vel=round(vel, 1), frm=st['last'], to=p)
        st['last'] = p
        z = ship.getZ(H.render)
        st['minZ'] = min(st['minZ'], z)
        a = anchorShown(ship)
        if a != st['lastA']:
            st['flips'] += 1
            H.ev('anchor', shown=a, phase=phase, dist=round(d, 1), port=la.getPort())
        st['lastA'] = a
        hp = getattr(ship, 'Hp', None)
        if hp is not None and st['hpMin'] is not None:
            st['hpMin'] = min(st['hpMin'], hp)
        foes = 0
        for o in H.cr.doId2do.values():
            n = cls(o)
            if 'Ship' in n and o is not ship and hasattr(o, 'getPos') and n not in ('DistributedShipDeployer',):
                try:
                    if (o.getPos(H.render) - p).length() < 1500:
                        foes += 1
                except Exception:
                    pass
        brg = keys.steer(ship, target) if target is not None else None
        dd = None if depPos is None else round((Vec3(p[0] - depPos[0], p[1] - depPos[1], 0)).length(), 1)
        st['dd'] = dd
        H.ev('s', ph=phase, d=round(d, 1), dd=dd, z=round(z, 2), port=la.getPort(), anchor=a, hp=hp, vel=round(vel, 1),
             brg=None if brg is None else round(brg), keys=sorted(keys.down), ships1500=foes, gs=la.getGameState())
        return d, a, vel

    # 3. sail out, away from the island, until past the port sphere
    for k in range(10):
        if getattr(ship, 'sailsReady', True): break
        yield 1
    messenger.send('w'); messenger.send('w-up')   # a tap of W: full sail (auto-sail)
    t0 = time.time()
    d = 0
    while time.time() - t0 < SAIL_SECS:
        p = ship.getPos(H.render); c = centre(H, isl)
        out = Point3(p[0] + (p[0] - c[0]), p[1] + (p[1] - c[1]), 0)
        d, a, vel = sample('out', out)
        if d > OUT_R:
            break
        yield 0.5
    H.ev('out-done', dist=round(d, 1), port=la.getPort(), anchor=anchorShown(ship), secs=round(time.time() - t0))
    st['outOk'] = d > OUT_R
    if d <= OUT_R:
        H.ev('FAIL', why='never got past the port sphere', dist=d)
    # 4. turn back and steer at the shore until the barrier stops us
    t0 = time.time()
    stopped = None
    best = 1e9
    while time.time() - t0 < SAIL_SECS:
        tgt = depPos if depPos is not None else centre(H, isl)
        d, a, vel = sample('in', tgt)
        dd = st.get('dd')
        best = min(best, d if dd is None else dd)
        reef = any('reef' in w.lower() or 'close' in w.lower() for w in warns[-3:])
        slow = st['slow'] = (st.get('slow', 0) + 1) if (dd is not None and dd < depMin + 300 and vel < 5) else 0
        if stopped is None and (reef or slow >= 4 or (dd is not None and dd < depMin + 60)):
            stopped = time.time()
            keys.release()
            messenger.send('s'); messenger.send('s-up')   # a tap of S: drop sail
            H.ev('at-shore', dist=round(d, 1), dd=dd, depMin=depMin, vel=round(vel, 1), reef=reef, warns=warns[-3:], port=la.getPort(), anchor=a)
            break
        yield 0.5
    if stopped is None:
        H.ev('FAIL', why='never reached the shore', best=round(best, 1))
    # 5. stopped at the shore: the anchor must stay up
    t0 = time.time()
    run_ = 0.0
    while time.time() - t0 < 40:
        d, a, vel = sample('stop')
        run_ = run_ + 0.5 if a else 0.0
        st['anchorBest'] = max(st['anchorBest'], run_)
        if run_ >= 12:
            break
        yield 0.5
    H.ev('ANCHOR-CHECK', ok=st['anchorBest'] >= 10, best=st['anchorBest'], flips=st['flips'], jumps=len(st['jumps']),
         z0=round(z0, 2), minZ=round(st['minZ'], 2), zOk=st['minZ'] >= z0 - 1, hpMin=st['hpMin'], warns=warns[-6:])
    keys.release()
    if not anchorShown(ship):
        H.ev('FAIL', why='no anchor to click at the shore'); return
    # 6. click the anchor, the way the button does
    ship.shipStatusDisplay.handleAnchorButton()
    yield ('until', lambda: H.area() is not None and H.area()[1] == TORTUGA and la.getGameState() == 'LandRoam', 90, 'land at Tortuga')
    H.ev('DOCKED', ok=H.area() is not None and H.area()[1] == TORTUGA, area=H.area(), gs=la.getGameState(), la=H.P(la))
    if H.area() is None or H.area()[1] != TORTUGA:
        return
    # 7. walk to Jack with the story walker's own step logic
    S = runpy.run_path(os.path.join(os.path.dirname(os.environ['PROOF_SCRIPT']), 's_story.py'))
    q = next((q for q in la.getQuests() if q.getQuestId() == 'c3visitJack'), None)
    if q is None:
        H.ev('FAIL', why='c3visitJack not held', qids=H.qids()); return
    S['track'](H, 'c3visitJack')
    yield 4
    cur = {}
    last = None
    t0 = time.time()
    while time.time() - t0 < 240:
        if 'c3visitJack' not in H.qids():
            H.ev('JACK', ok=True, qids=H.qids(), hist=H.hist()[-3:], secs=round(time.time() - t0))
            # true mission end: docked at Tortuga AND the quest moved, with a clean sail
            faults = [n for n, bad in (('out', not st.get('outOk')), ('shore', stopped is None),
                                       ('anchor', st['anchorBest'] < 10), ('jump', bool(st['jumps'])),
                                       ('z', st['minZ'] < z0 - 1)) if bad]
            if faults:
                H.ev('FAIL', why='quest moved but the sail had faults', faults=faults)
            else:
                H.ev('PASS', mission='c3visitJack', area=H.area(), qids=H.qids())
            return
        if la.getGameState() != 'LandRoam':
            yield 2; continue
        q = next((q for q in la.getQuests() if q.getQuestId() == 'c3visitJack'), None)
        if q is not None and q.isComplete():
            yield 3; continue
        a = S['act'](H, q, cur)
        if a != last:
            H.ev('act', a=a, la=H.P(la), area=H.area(), step=repr(la.questStep))
            last = a
        yield 3
    H.ev('JACK', ok=False, qids=H.qids(), step=H.step())
