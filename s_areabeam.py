"""Area-marker beam shots (offline prep for Host's "big light bulb in the sky", 11-16).
The tracked step c2.11visitBarbossa is an AREA step: its QuestIndicatorNodeArea hangs 1000 ft above the step object
(the island) and draws the skyBeam sprite beam (QuestIndicatorEffect) from up to 1e6 ft away; inside 100 ft the beam
stops. This script only looks: it logs the marker and its effect, sails to the island the way a player does
(sailing.launch: dinghy, wheel, held keys; no teleports), lands, walks under the marker, and takes full-frame shots with
the camera pointed at the marker once the camera is within each of SHOT_D ft of it.
  1 login; make sure the c2.11 step is tracked; wait for its QuestIndicatorNodeArea; log it (area-marker event: pos,
    fsm state, effect model / scales / colour / bounds, lens far plane)
  2 launch the ship, sail towards the marker's island (every island but that one is steered round), shots on the way
  3 anchor at the island, walk (held keys) towards the point under the marker, shots on the way
  4 thresholds never reached (the camera cannot get closer than the 1000 ft height unless it is under the marker, and
    the beam only stops at 100 ft) get a shot at the closest point reached, named ...-unreached
Shots go to shots/areabeam/<tag>-d<ft>.png (the camera is only aimed for the instant of the shot, then put back).
PASS = marker found and every threshold has a saved shot. FAIL only for a harness problem (no marker, no ship, the sail
never starts); how the beam looks is judged from the pictures, never by this script.
env: AREA_TAG (default 'AREA1'), AREA_GIVE (quest id to give when the pirate holds none, default c2.11visitBarbossa)."""
import os, sys, time, math

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
from panda3d.core import Filename, Point3, Point2, Vec3, ColorBlendAttrib   # noqa: E402
import sailing, paths   # noqa: E402
from s_dock import Keys, anchorShown   # noqa: E402

TAG = os.environ.get('AREA_TAG', 'AREA1')
QID = os.environ.get('AREA_GIVE', 'c2.11visitBarbossa')
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])), 'shots', 'areabeam')
SHOT_D = [10000, 3000, 1000, 300, 100]
SEA_SECS = 600.0
WALK_SECS = 150.0


def track(H, qid):
    la = H.la
    try:
        if la.guiMgr.questPage is None:
            la.guiMgr.initQuestPage()
        page = la.guiMgr.questPage
        page.showQuestDetails(qid)
        if la.activeQuestId != qid:
            page.trackQuest()
        else:
            la.refreshActiveQuestStep(False, True)
    except Exception as e:
        H.ev('track-err', err=str(e))


def marker(H):
    qi = getattr(H.la, 'questIndicator', None)
    node = getattr(qi, 'indicatorNode', None) if qi else None
    if node is not None and not node.isEmpty() and type(node).__name__ == 'QuestIndicatorNodeArea':
        return node
    return None


def safe(f, default=None):
    try:
        return f()
    except Exception as e:
        return 'err %s' % e if default is None else default


def describe(H, node):
    """Everything the logs need to judge the beam: where, which state, which model, how big, which colour."""
    R, B = H.render, H.B
    d = {'cls': type(node).__name__, 'pos': H.P(node), 'fsm': safe(lambda: node.state),
         'muted': safe(lambda: node.muted), 'parent': str(node.getParent()),
         'stepObj': type(getattr(node, 'stepObj', None)).__name__,
         'stepObjPos': safe(lambda: H.P(node.stepObj)),
         'lensFar': safe(lambda: round(B.camLens.getFar())), 'lensNear': safe(lambda: B.camLens.getNear()),
         'fov': safe(lambda: [round(v, 1) for v in B.camLens.getFov()]),
         'distCamera': safe(lambda: round(node.getPos(B.camera).length())),
         'distPirate': safe(lambda: round(paths.dist(H.la.getPos(R), node.getPos(R))))}
    for k in ('farEffect', 'nearEffect'):
        e = getattr(node, k, None)
        if e is None:
            d[k] = None
            continue
        pd = getattr(e, 'particleDummy', None)
        ed = {'empty': e.isEmpty(), 'type': type(e).__name__, 'pos': H.P(e),
              'scale': safe(lambda: [round(v, 2) for v in e.getScale(R)]),
              'effectScale': getattr(e, 'effectScale', None), 'cardScale': getattr(e, 'cardScale', None),
              'cardScale2': getattr(e, 'cardScale2', None),
              'colorScale': safe(lambda: [round(v, 2) for v in e.getColorScale()]),
              'hidden': e.isHidden(), 'stashed': e.isStashed(),
              'live': safe(lambda: [e.p0.getLivingParticles(), e.p1.getLivingParticles()])}
        if pd is not None and not pd.isEmpty():
            ed['dummy'] = {'pos': H.P(pd), 'parent': str(pd.getParent()),
                           'scale': safe(lambda: [round(v, 2) for v in pd.getScale(R)]),
                           'colorScale': safe(lambda: [round(v, 2) for v in pd.getColorScale()]),
                           'bounds': safe(lambda: str(pd.getBounds())),
                           'tight': safe(lambda: [[round(v) for v in p] for p in (pd.getTightBounds(R) or [])]),
                           'blend': safe(lambda: str(pd.getAttrib(ColorBlendAttrib.getClassType())))}
        ed['skyBeam'] = safe(lambda: [{'name': g.getName(), 'scale': [round(v, 2) for v in g.getScale(R)],
                                       'colorScale': [round(v, 2) for v in g.getColorScale()]}
                                      for g in e.findAllMatches('**/*skyBeam*')][:6])
        d[k] = ed
    return d


def on_screen(H, np_):
    B = H.B
    p = B.cam.getRelativePoint(np_, Point3(0, 0, 0))
    s = Point2()
    if p[1] > 0 and B.camLens.project(p, s):
        return [round(s[0], 2), round(s[1], 2), bool(abs(s[0]) <= 1 and abs(s[1]) <= 1)]
    return None


class Shots:
    def __init__(self, H, node):
        self.H, self.node = H, node
        self.fixed = Point3(node.getPos(H.render))      # the marker's place, kept for when the node is gone
        self.gone = False
        self.done = {}
        self.closest = 1e12
        os.makedirs(OUTDIR, exist_ok=True)

    def alive(self):
        """The marker node goes when the quest step advances (arriving at the island completes the area step; the
        next step's indicator replaces it): that is the game working, so log it once and carry on without the node."""
        if not self.gone and (self.node is None or self.node.isEmpty()):
            self.gone = True
            H, la = self.H, self.H.la
            qi = getattr(la, 'questIndicator', None)
            nn = getattr(qi, 'indicatorNode', None) if qi else None
            H.ev('area-marker-gone', dist=round((self.fixed - self.H.B.camera.getPos(H.render)).length()),
                 area=H.area(), step=repr(getattr(la, 'questStep', None)),
                 newIndicator=type(nn).__name__ if nn is not None else None, closest=round(self.closest))
        return not self.gone

    def dist(self):
        if self.alive():
            return self.node.getPos(self.H.B.camera).length()
        return (self.fixed - self.H.B.camera.getPos(self.H.render)).length()

    def take(self, t, label):
        """Aim the camera at the marker for this one frame, save the full frame, put the camera back."""
        H, B = self.H, self.H.B
        if not self.alive():
            H.ev('area-shot-skip', t=t, label=label, why='marker gone')
            return False
        cam = B.camera
        pos, hpr = Point3(cam.getPos()), Vec3(cam.getHpr())
        d = self.dist()
        f = os.path.join(OUTDIR, '%s-d%05d%s.png' % (TAG, t, label))
        ok = False
        try:
            cam.lookAt(self.node)
            B.graphicsEngine.renderFrame()
            B.graphicsEngine.renderFrame()
            scr = on_screen(H, self.node)
            ok = bool(B.win.saveScreenshot(Filename.fromOsSpecific(f)))
        except Exception as e:
            H.ev('area-shot-err', t=t, err=repr(e))
            scr = None
        finally:
            cam.setPos(pos)
            cam.setHpr(hpr)
        H.ev('area-shot', t=t, label=label, dist=round(d), screen=scr, ok=ok, file=f,
             area=H.area(), la=H.P(H.la), fsm=safe(lambda: self.node.state))
        if ok:
            self.done[t] = f
        return ok

    def poll(self):
        """Call each beat: the largest threshold the camera is now within that has no shot yet."""
        d = self.dist()
        self.closest = min(self.closest, d)
        for t in SHOT_D:
            if t not in self.done and d <= t:
                self.take(t, '')
                break

    def finish(self):
        for t in SHOT_D:
            if t not in self.done:
                self.H.ev('area-unreached', t=t, closest=round(self.closest), markerGone=not self.alive())
                self.take(t, '-unreached')


def run(H):
    la, R = H.la, H.render
    yield ('until', lambda: la.getGameState() in ('LandRoam', 'ShipPilot'), 90, 'LandRoam')
    t_end = time.time() + float(os.environ.get('PROOF_SECS', '900')) - 40
    # 1. the c2.11 step is tracked and its area marker exists
    if QID not in H.qids():
        H.ev('area-give', q=QID, held=H.qids())
        H.mw('giveQuest %s' % QID)
        yield ('until', lambda: QID in H.qids(), 15, 'give %s' % QID)
    t0 = time.time()
    node = None
    lastTrack = 0
    while time.time() - t0 < 90:
        node = marker(H)
        if node is not None:
            break
        if time.time() - lastTrack > 10:
            lastTrack = time.time()
            track(H, QID)
        yield 3
    if node is None:
        H.ev('FAIL', why='no QuestIndicatorNodeArea for %s' % QID, **H.step())
        return
    yield 3
    H.ev('area-marker', active=la.activeQuestId, step=repr(la.questStep), **describe(H, node))
    mp = node.getPos(R)
    tbl = sailing.islands()
    # the island under the marker: the nearest one (the step object is that island)
    tuid = min(tbl, key=lambda u: paths.dist((tbl[u][1], tbl[u][2]), (mp[0], mp[1])))
    H.ev('area-island', uid=tuid, isl=tbl[tuid][0], pos=[tbl[tuid][1], tbl[tuid][2]],
         off=round(paths.dist((tbl[tuid][1], tbl[tuid][2]), (mp[0], mp[1]))))
    shots = Shots(H, node)
    # 2. sail there like a player
    here = sailing.hereUid(H)
    aboard = sailing.onShip(H)
    ship = None
    landed = False
    if here == tuid:
        H.ev('area-already-there', uid=tuid)
        landed = True
    else:
        if here is None and not aboard:
            H.ev('FAIL', why='not on an island and not aboard', area=H.area())
            return
        H.walk_cancel()
        ship = yield from sailing.launch(H, here, aboard)
        if ship is None:
            H.ev('FAIL', why='the ship did not launch (see SAIL-FAIL)')
            return
        keys = Keys(H)
        messenger.send('w'); messenger.send('w-up')      # tap W: full sail
        obst = [(x, y, sailing.OBST_R if n else 900) for u, (n, x, y, f) in tbl.items() if u != tuid]
        ts = time.time()
        dep = depPos = None
        stopped = False
        warns = []
        try:
            orig = la.guiMgr.createWarning

            def cw(text, *a, **k):
                warns.append(str(text)[:80])
                H.ev('warning', text=str(text)[:120])
                return orig(text, *a, **k)
            la.guiMgr.createWarning = cw
        except Exception:
            pass
        tx, ty = tbl[tuid][1], tbl[tuid][2]
        lastLog = 0
        slow = 0
        while time.time() - ts < SEA_SECS and time.time() < t_end - WALK_SECS:
            if la.getGameState() != 'ShipPilot' or ship.isEmpty():
                H.ev('area-left-wheel', gs=la.getGameState(), area=H.area())
                break
            p = ship.getPos(R)
            dist = paths.dist(p, (tx, ty))
            if dist < sailing.ARRIVE_R and dep is None:
                isl = sailing.islandObj(H, tuid)
                if isl is not None:
                    deps = [o for o in H.cr.doId2do.values()
                            if type(o).__name__ == 'DistributedShipDeployer' and o.getParentObj() is isl]
                    if deps:
                        dep = deps[0]
                        depPos = dep.getPos(R)
                        H.ev('sail-arrive', dist=round(dist), deployer=dep.doId, depMin=dep.minRadius)
            goal = depPos if depPos is not None else Point3(tx, ty, 0)
            dd = paths.dist(p, goal) if depPos is not None else None
            tgt, mode = sailing.route(p, goal, obst)
            brg = keys.steer(ship, tgt)
            shots.poll()
            try:
                vel = ship.node().getPhysicsObject().getVelocity().length()
            except Exception:
                vel = 0
            if time.time() - lastLog > 10:
                lastLog = time.time()
                H.ev('s2', d=round(dist), dd=None if dd is None else round(dd), mode=mode, pos=[round(p[0]), round(p[1])],
                     vel=round(vel, 1), cam=round(shots.dist()), shots=sorted(shots.done))
            if dep is not None:
                reef = any('reef' in w.lower() or 'close' in w.lower() for w in warns[-2:])
                slow = slow + 1 if (dd < dep.minRadius + 300 and vel < 5) else 0
                if reef or slow >= 8 or dd < dep.minRadius + 60:
                    keys.release()
                    messenger.send('s'); messenger.send('s-up')     # tap S: drop sail
                    H.ev('at-shore', dd=round(dd), vel=round(vel, 1), reef=reef, cam=round(shots.dist()))
                    stopped = True
                    break
            yield 0.5
        keys.release()
        if stopped:
            t1 = time.time()
            while time.time() - t1 < 30 and not anchorShown(ship):
                yield 0.5
            if anchorShown(ship):
                ship.shipStatusDisplay.handleAnchorButton()
                yield ('until', lambda: sailing.hereUid(H) == tuid and la.getGameState() == 'LandRoam', 90,
                       'land at %s' % tbl[tuid][0])
                landed = sailing.hereUid(H) == tuid
            else:
                H.ev('area-no-anchor', port=la.getPort())
        H.ev('area-sail-end', stopped=stopped, landed=landed, secs=round(time.time() - ts), cam=round(shots.dist()))
    # 3. on the island: walk towards the point under the marker, in 150 ft legs so the shots keep up
    if landed:
        yield 3
        tw = time.time()
        stuck = 0
        while time.time() - tw < WALK_SECS and time.time() < t_end and la.getGameState() == 'LandRoam':
            p = la.getPos(R)
            m = shots.fixed
            gap = paths.dist(p, m)
            shots.poll()
            if gap < 25:
                break
            step = min(150.0, gap)
            goal = (p[0] + (m[0] - p[0]) * step / gap, p[1] + (m[1] - p[1]) * step / gap, p[2])
            ok = yield from H.walk_to(goal, ref=R, arrive=12.0, timeout=25, tag='area-walk')
            shots.poll()
            stuck = 0 if ok else stuck + 1
            if stuck >= 2:
                H.ev('area-walk-stuck', la=H.P(la), gap=round(gap))
                break
        H.ev('area-walk-end', la=H.P(la), cam=round(shots.dist()), gap=round(paths.dist(la.getPos(R), shots.fixed)))
    # 4. thresholds the camera never got within: a shot at the closest point reached
    shots.finish()
    H.ev('area-summary', shots=dict((str(k), v) for k, v in sorted(shots.done.items())), closest=round(shots.closest),
         landed=landed, fsm=safe(lambda: node.state))
    if shots.gone and len(shots.done) < len(SHOT_D):
        # harness worked; the beam ended with the step before the closer thresholds could be reached
        H.ev('PASS', why='marker logged; it went when the step advanced, %d of %d shots' % (len(shots.done), len(SHOT_D)),
             closest=round(shots.closest), landed=landed, area=H.area(), shots=sorted(shots.done))
    elif len(shots.done) == len(SHOT_D):
        H.ev('PASS', why='marker logged, %d shots saved' % len(shots.done), closest=round(shots.closest),
             landed=landed, area=H.area())
    else:
        H.ev('FAIL', why='shots missing: %s' % [t for t in SHOT_D if t not in shots.done])
