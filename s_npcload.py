"""NPC reload check: do the NPCs at Port Royal vanish and come back each time the pirate crosses a 75-ft grid cell?
Host's suspicion (not proven): the stock grid (DistributedCartesianGrid.processVisibility) alters the island's
visibility interest to the ONE new cell, then the client patch (PiratesClientRepository.__handleAvatarZoneChanged)
alters it again to the new cell plus rings 1-3 (about 49 cells); in one frame that is two alterInterest calls, and a
server that deletes what a modify drops would delete and regenerate the NPCs standing in the cells both lists share.
This script only MEASURES that; it never fails the run for what it finds.
After login at Port Royal (areaTeleport when not there), once the island grid interest is joined, a per-frame probe
records: the pirate's zoneId, the length of the grid interest's zoneIdList (DoInterestManager._interests, int for a
stock single-cell alter, list for the patch), and the NPC doIds in cr.doId2do (class name has NPC / Townfolk /
ShopKeeper, not Ship). Events:
  npcload-grid     once: island grid numbers and the interest state at the join
  npc-initial      once: the NPCs there at the start (doId, class, name, distance)
  cell             each zoneId change: old/new zone, zoneIdList len before/after, the alterInterest lens seen in that
                   frame (the transient single cell shows here), pos, cell by position, NPCs live / within 150 ft
  cell-settled     1.5 s after each cell: NPC deletes and generates since the cell, NPCs live now
  npc-gen/npc-del  each NPC appearing / vanishing: doId, class, name, distance from the pirate, seconds since the last
                   cell change, regen (seconds since this doId was deleted, when it came back within 5 s)
  zone-event       the 'avatarZoneChanged' messenger event (local pirate) with the zoneIdList len at that moment
  interest-alter   each cr.alterInterest call on the island grid (hook, pass-through, NPCLOAD_HOOK=0 turns it off)
  npcload-tick     every 5 s (keeps the harness watchdog fed): zone, interest len, NPCs, cells, deletes
  npcload-leg      each walked leg: reached or not, cells crossed, secs
  npcload-summary  the result: cells crossed, zoneIdList len min/max (per frame, and per alterInterest), NPC deletes
                   within 1 s of a cell change (and with the NPC within 150 ft, with their names), reloads
The walk is held keys through paths.walk_route (no setPos): Darby's dock, back to the town centre, then a tour of the
NPCs seen, nearest first but at least 120 ft away so each leg crosses cells. Stops starting legs 45 s before the cap.
PASS when the walk crossed >= 8 cells. FAIL only for harness problems: the grid never joined, or the walk got < 8 cells.
env: NPCLOAD_TAG (default 'NPC1'), NPCLOAD_SECS (walk cap in seconds, default 360; also cut to PROOF_SECS - 240),
NPCLOAD_HOOK (1). Run with run_walk.ps1 -Secs 600 or more (the default 400 is too short for login + a 6 min walk)."""
import os, sys, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
from direct.showbase.DirectObject import DirectObject   # noqa: E402
import sailing, paths   # noqa: E402

PR = '1150922126.8dzlu'
TAG = os.environ.get('NPCLOAD_TAG', 'NPC1')
CAP = float(os.environ.get('NPCLOAD_SECS', '360'))
HOOK = os.environ.get('NPCLOAD_HOOK', '1') == '1'
DARBY = (-274.3, 57.3, 2.7)      # Darby the shipwright's booth (s_talk_walk.DARBY)
START = (152.7, -288.3, 9.7)     # where the pirate stands after areaTeleport to Port Royal (town centre side)
NEAR = 150.0                     # an NPC this close (ft) should not vanish when a cell is crossed
WINDOW = 1.0                     # a delete this soon after a cell change (s) counts as caused by it
SETTLE = 1.5
MIN_CELLS = 8
CAPS = {'npc-gen': 2500, 'npc-del': 2500, 'cell': 600, 'cell-settled': 600, 'zone-event': 600, 'interest-alter': 800}


def zlen(zl):
    """Length of an interest zone list; 1 for the single int zone of a stock alter; None when unknown."""
    if zl is None:
        return None
    if isinstance(zl, int):
        return 1
    try:
        return len(zl)
    except TypeError:
        return 1


def interest(isl):
    """-> (handle int, InterestState or None) of the island grid's visibility interest ((None, None) before it exists)."""
    from direct.distributed.DoInterestManager import DoInterestManager
    h = getattr(isl, 'gridVisContext', None)
    if h is None:
        return None, None
    hi = h.asInt() if hasattr(h, 'asInt') else int(h)
    return hi, getattr(DoInterestManager, '_interests', {}).get(hi)


def nm(o):
    v = getattr(o, 'name', None)
    if isinstance(v, str) and v:
        return v
    try:
        v = o.getName()
        return v if isinstance(v, str) and v else None
    except Exception:
        return None


class Listener(DirectObject):
    def __init__(self, probe):
        DirectObject.__init__(self)
        self.probe = probe
        self.accept('avatarZoneChanged', self.on)

    def on(self, *a):
        try:
            self.probe.on_zone_event(a)
        except Exception:
            pass


class Probe(object):
    def __init__(self, H, isl):
        self.H, self.la, self.R, self.isl = H, H.la, H.render, isl
        self.t0 = time.time()
        self.zone = None            # the pirate's zoneId last frame (None while off the island)
        self.n = None               # interest zoneIdList len last frame
        self.live = {}              # doId -> {cls, name, uid, pos} of the NPCs in doId2do now
        self.known = {}             # doId -> the same, every NPC ever seen
        self.gone = {}              # doId -> (time deleted, was a counted close delete)
        self.isnpc = {}
        self.first = True
        self.cells = 0
        self.cellTimes = []
        self.settle = None
        self.lenMin = self.lenMax = None
        self.alterMin = self.alterMax = None
        self.alterLens = {}
        self.alterOther = 0
        self.shapes = {}            # the alterInterest len sequence of each cell frame -> how many cells
        self.gens = self.dels = 0
        self.delsCell = self.delsClose = 0
        self.cellNames, self.closeNames = {}, {}
        self.reloads = self.reloadsClose = 0
        self.zoneEvents = self.zoneEventsOthers = 0
        self.pending = []
        self.errors = 0
        self.counts = {}
        self.lastTick = 0.0
        self.hooked = self.hookOrig = self.listener = None

    # ---------- events ----------
    def emit(self, name, **kw):
        n = self.counts.get(name, 0) + 1
        self.counts[name] = n
        if n <= CAPS.get(name, 1000):
            self.H.ev(name, **kw)

    def secs(self):
        return round(time.time() - self.t0, 2)

    # ---------- install / remove ----------
    def start(self):
        self.listener = Listener(self)
        if HOOK:
            cr = self.H.cr
            if 'alterInterest' not in cr.__dict__:
                orig = cr.alterInterest
                probe = self

                def hooked(*a, **k):
                    try:
                        probe.on_alter(a, k)
                    except Exception:
                        pass
                    return orig(*a, **k)
                self.hookOrig, self.hooked = orig, hooked
                cr.alterInterest = hooked
        self.H.B.taskMgr.add(self.frame, 'npcload-probe', sort=40)

    def stop(self):
        try:
            self.H.B.taskMgr.remove('npcload-probe')
        except Exception:
            pass
        try:
            if self.listener is not None:
                self.listener.ignoreAll()
        except Exception:
            pass
        try:
            cr = self.H.cr
            if self.hooked is not None and cr.__dict__.get('alterInterest') is self.hooked:
                del cr.alterInterest
        except Exception:
            pass

    # ---------- hooks ----------
    def on_alter(self, a, k):
        parent = a[1] if len(a) > 1 else k.get('parentId')
        zl = a[2] if len(a) > 2 else k.get('zoneIdList')
        if parent != getattr(self.isl, 'doId', None):
            self.alterOther += 1
            return
        n = zlen(zl)
        self.pending.append(n)
        self.alterLens[n] = self.alterLens.get(n, 0) + 1
        if n is not None:
            self.alterMin = n if self.alterMin is None else min(self.alterMin, n)
            self.alterMax = n if self.alterMax is None else max(self.alterMax, n)
        self.emit('interest-alter', len=n, kind=type(zl).__name__, laZone=getattr(self.la, 'zoneId', None),
                  secs=self.secs())

    def on_zone_event(self, a):
        av = a[0] if a else None
        if av is not self.la:
            self.zoneEventsOthers += 1
            return
        self.zoneEvents += 1
        hi, st = interest(self.isl)
        self.emit('zone-event', grid=a[1] if len(a) > 1 else None, zone=a[2] if len(a) > 2 else None,
                  lenNow=zlen(st.zoneIdList) if st is not None else None, laZone=getattr(self.la, 'zoneId', None),
                  pos=self.H.P(self.la), secs=self.secs())

    # ---------- per frame ----------
    def frame(self, task):
        try:
            self.step()
        except Exception:
            self.errors += 1
            if self.errors == 1:
                self.H.ev('probe-error', tb=traceback.format_exc()[-1200:])
        return task.cont

    def is_npc(self, o):
        c = type(o)
        r = self.isnpc.get(c)
        if r is None:
            n = c.__name__
            r = bool(('NPC' in n or 'Townfolk' in n or 'ShopKeeper' in n) and 'Ship' not in n)
            self.isnpc[c] = r
        return r

    def near_count(self, ppos):
        return sum(1 for i in self.live.values() if i['pos'] and paths.dist(ppos, i['pos']) <= NEAR)

    def flush_settle(self, now, ppos, force=False):
        s = self.settle
        if s and (force or now - s['t'] >= SETTLE):
            self.emit('cell-settled', cell=s['cell'], secs=round(now - s['t'], 2), dels=self.dels - s['dels'],
                      gens=self.gens - s['gens'], npcsLive=len(self.live), npcsNear=self.near_count(ppos))
            self.settle = None

    def step(self):
        H, la, R, isl = self.H, self.la, self.R, self.isl
        now = time.time()
        zone = getattr(la, 'zoneId', None)
        hi, st = interest(isl)
        n = zlen(st.zoneIdList) if st is not None else None
        if n is not None:
            self.lenMin = n if self.lenMin is None else min(self.lenMin, n)
            self.lenMax = n if self.lenMax is None else max(self.lenMax, n)
        alt, self.pending = self.pending, []
        ppos = la.getPos(R)
        here = sailing.hereUid(H) == PR

        # --- a cell change: the pirate's zoneId changed while on the island
        if not here:
            self.zone = None
        elif zone is not None:
            if self.zone is not None and zone != self.zone:
                try:
                    byPos = isl.getZoneFromXYZ(la.getPos(isl))
                except Exception:
                    byPos = None
                self.flush_settle(now, ppos, force=True)
                self.cells += 1
                self.cellTimes.append(now)
                key = '-'.join(str(v) for v in alt) or 'none'
                self.shapes[key] = self.shapes.get(key, 0) + 1
                self.emit('cell', n=self.cells, old=self.zone, new=zone, lenBefore=self.n, lenAfter=n, alters=alt,
                          pos=H.P(la), byPos=byPos, npcsLive=len(self.live), npcsNear=self.near_count(ppos),
                          secs=self.secs())
                self.settle = {'t': now, 'cell': self.cells, 'dels': self.dels, 'gens': self.gens}
            self.zone = zone
        self.n = n

        # --- the NPCs in doId2do now
        cur = set()
        new = []
        for o in list(H.cr.doId2do.values()):
            if not self.is_npc(o):
                continue
            did = getattr(o, 'doId', None)
            if did is None:
                continue
            cur.add(did)
            pos = None
            try:
                if not o.isEmpty():
                    p = o.getPos(R)
                    pos = [round(p[0], 1), round(p[1], 1), round(p[2], 1)]
            except Exception:
                pass
            info = self.live.get(did)
            if info is None:
                info = {'cls': type(o).__name__, 'name': nm(o), 'uid': getattr(o, 'uniqueId', None), 'pos': pos}
                self.live[did] = info
                self.known[did] = info
                new.append((did, info))
            else:
                if pos is not None:
                    info['pos'] = pos
                if not info['name']:
                    info['name'] = nm(o)
        since = round(now - self.cellTimes[-1], 3) if self.cellTimes else None

        if self.first:
            self.first = False
            if cur:
                self.emit('npc-initial', count=len(new), npcs=[
                    {'doId': d, 'cls': i['cls'], 'name': i['name'], 'dist': round(paths.dist(ppos, i['pos']), 1) if i['pos'] else None}
                    for d, i in sorted(new, key=lambda t: paths.dist(ppos, t[1]['pos']) if t[1]['pos'] else 1e9)[:80]])
                new = []
        for did, info in new:
            self.gens += 1
            g = self.gone.pop(did, None)
            regen = None
            if g is not None and now - g[0] <= 5.0:
                regen = round(now - g[0], 2)
                self.reloads += 1
                if g[1]:
                    self.reloadsClose += 1
            self.emit('npc-gen', doId=did, cls=info['cls'], npc=info['name'], uid=info['uid'], pos=info['pos'],
                      dist=round(paths.dist(ppos, info['pos']), 1) if info['pos'] else None, sinceCell=since, regen=regen,
                      secs=self.secs())
        for did in [d for d in self.live if d not in cur]:
            info = self.live.pop(did)
            self.dels += 1
            d = round(paths.dist(ppos, info['pos']), 1) if info['pos'] else None
            counted = any(-0.1 <= now - c <= WINDOW for c in self.cellTimes[-6:])
            close = counted and d is not None and d <= NEAR
            if counted:
                self.delsCell += 1
                k = info['name'] or info['cls']
                self.cellNames[k] = self.cellNames.get(k, 0) + 1
                if close:
                    self.delsClose += 1
                    self.closeNames[k] = self.closeNames.get(k, 0) + 1
            self.gone[did] = (now, close)
            self.emit('npc-del', doId=did, cls=info['cls'], npc=info['name'], uid=info['uid'], pos=info['pos'], dist=d,
                      sinceCell=since, nearCell=counted, close=close, secs=self.secs())

        self.flush_settle(now, ppos)
        if now - self.lastTick >= 5.0:
            self.lastTick = now
            H.ev('npcload-tick', secs=self.secs(), zone=zone, interest=n, npcs=len(self.live), cells=self.cells,
                 gens=self.gens, dels=self.dels, delsNearCell=self.delsCell, delsClose=self.delsClose, pos=H.P(la),
                 errors=self.errors)

    def summary(self, extra=None):
        d = dict(tag=TAG, secs=self.secs(), cells=self.cells,
                 lenMin=self.lenMin, lenMax=self.lenMax, alterLenMin=self.alterMin, alterLenMax=self.alterMax,
                 alterLens=self.alterLens, alterOtherParents=self.alterOther, cellAlterShapes=self.shapes,
                 npcGens=self.gens, npcDels=self.dels, npcsSeen=len(self.known),
                 delsWithin1sOfCell=self.delsCell, delsWithin1sAndWithin150ft=self.delsClose,
                 namesWithin1sAndWithin150ft=self.closeNames, namesWithin1sOfCell=self.cellNames,
                 reloadsWithin5s=self.reloads, reloadsAfterCloseDelete=self.reloadsClose,
                 zoneEvents=self.zoneEvents, zoneEventsOthers=self.zoneEventsOthers, hook=HOOK,
                 probeErrors=self.errors)
        if extra:
            d.update(extra)
        return d


def run(H):
    la, R = H.la, H.render
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if sailing.hereUid(H) != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5

    def joined():
        try:
            isl = sailing.islandObj(H, PR)
            if isl is None or sailing.hereUid(H) != PR or la.getGameState() != 'LandRoam':
                return False
            hi, st = interest(isl)
            return st is not None
        except Exception:
            return False

    yield ('until', joined, 60, 'island grid interest joined')
    isl = sailing.islandObj(H, PR)
    if isl is None or not joined():
        H.ev('FAIL', why='never joined the Port Royal grid (island object or its grid interest missing)', tag=TAG,
             area=H.area())
        return
    yield 3          # let the first NPCs load before the first look

    hi, st = interest(isl)
    try:
        byPos = isl.getZoneFromXYZ(la.getPos(isl))
    except Exception as e:
        byPos = 'err %s' % e
    H.ev('npcload-grid', tag=TAG, island=getattr(isl, 'doId', None), handle=hi, gridSize=getattr(isl, 'gridSize', None),
         cellWidth=getattr(isl, 'cellWidth', None), startingZone=getattr(isl, 'startingZone', None),
         viewingRadius=getattr(isl, 'viewingRadius', None), visZone=getattr(isl, 'visZone', None),
         interestLen=zlen(st.zoneIdList), interestKind=type(st.zoneIdList).__name__,
         interestParent=getattr(st, 'parentId', None), interestDesc=getattr(st, 'desc', None),
         laZone=getattr(la, 'zoneId', None), byPos=byPos, pos=H.P(la), hook=HOOK)

    probe = Probe(H, isl)
    probe.start()
    t_start = time.time()
    cap = min(CAP, max(120.0, float(os.environ.get('PROOF_SECS', '600')) - 240.0))
    deadline = t_start + cap
    start0 = tuple(la.getPos(R))
    H.ev('npcload-start', tag=TAG, cap=round(cap), start=[round(v, 1) for v in start0], darby=DARBY, centre=START)
    state = {'fails': 0}

    def left():
        return deadline - time.time()

    def leg(name, goals, arrive):
        c0, p0, t0 = probe.cells, tuple(la.getPos(R)), time.time()
        got = yield from paths.walk_route(H, goals, arrive=arrive, short=arrive, tag=name)
        p1 = la.getPos(R)
        H.ev('npcload-leg', leg=name, got=[round(v, 1) for v in got] if got else None, cells=probe.cells - c0,
             moved=round(paths.dist(p0, p1), 1), secs=round(time.time() - t0, 1), pos=H.P(la))
        state['fails'] = 0 if got else state['fails'] + 1
        return got

    err = None
    try:
        # 1 Darby's dock, 2 back to the town centre
        yield from leg('darby', [DARBY], 40.0)
        if left() > 45:
            yield from leg('centre', [START, start0], 25.0)

        # 3 tour of the NPCs seen: nearest first, but at least 120 ft off so every leg crosses cells
        visited = set()
        laps = 0
        while left() > 45 and state['fails'] < 3:
            here = la.getPos(R)
            cands = []
            for did, i in list(probe.live.items()):
                if did in visited or not i['pos']:
                    continue
                d = paths.dist(here, i['pos'])
                if 40.0 < d <= 600.0:
                    cands.append((0 if d >= 120.0 else 1, d, did, i))
            if not cands:
                # nothing left to visit: another lap Darby <-> centre while cells are short and time remains
                if probe.cells >= 2 * MIN_CELLS or laps >= 3:
                    break
                laps += 1
                yield from leg('darby-lap%d' % laps, [DARBY], 40.0)
                if left() > 45:
                    yield from leg('centre-lap%d' % laps, [START, start0], 25.0)
                visited.clear()
                continue
            cands.sort(key=lambda t: (t[0], t[1]))
            _, d, did, i = cands[0]
            visited.add(did)
            H.ev('npcload-visit', doId=did, npc=i['name'], cls=i['cls'], dist=round(d, 1), pos=i['pos'])
            yield from leg('npc-%s' % did, [tuple(i['pos'])], 25.0)
            yield 0.3
    except Exception:
        err = traceback.format_exc()[-1500:]
        H.ev('npcload-error', tb=err)

    H.walk_cancel()
    yield 2.5            # let the last cell settle and its deletes arrive
    probe.stop()
    probe.flush_settle(time.time(), la.getPos(R), force=True)
    H.ev('npcload-summary', **probe.summary({'walkSecs': round(time.time() - t_start, 1), 'error': err,
                                             'end': H.P(la)}))
    if probe.cells >= MIN_CELLS:
        H.ev('PASS', what='npcload', tag=TAG, cells=probe.cells, delsWithin1sOfCell=probe.delsCell,
             delsWithin1sAndWithin150ft=probe.delsClose)
    else:
        H.ev('FAIL', why='could not walk: crossed %d cells, needed %d' % (probe.cells, MIN_CELLS), tag=TAG, error=err)
