"""A brand-new pirate plays the opening like a player (server-tree patch 0035): Jack Sparrow's jail scene, Make-A-Pirate,
out of the cell and the jail, Doggerel Dan's sea chest, Bo Beck's boat, three hits on the wreck with the boat's cannon,
the Jolly Roger scene, then Port Royal. With TUT_THEN_STORY=1 it goes on into the story (s_story.run).

Needs walker BOT_NEW_PIRATE=1 (log in to a new slot with 'create') and run_walk BOT_ACCOUNT=<fresh account>, so the
account has no pirate yet. Every button goes through its own command; walking and aiming are held keys (inputState),
firing is the 'control' key event. Never setPos. PASS when the pirate stands in Port Royal with the tutorial done."""
import os, sys, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_story   # noqa: E402
import paths     # noqa: E402

PORT_ROYAL = '1150922126.8dzlu'
JAIL_INTERIOR_DOOR = '1202172574.65kmuller'
KEY_SRC = 'harness-bot'       # the walker's own key source, so its keys_release() frees these too
AIM_TOL = 0.6                 # deg: fire when heading and pitch are both this close
PITCH_TRIES = (0.0, 1.5, -1.5, 3.0, -3.0, 4.5, -4.5, 6.0)   # extra pitch after a miss (wind-free, but the deck rolls)
AFTER_CANNON = ('Act2TargetSunk', 'Act3IntroduceJR', 'Act4BackToMain', 'Act4DoneTutorial')
DOCK_SPOT = (129.1, 127.1, 8.1)   # Chapter1.rung3's quest node on the Rambleshack dock (island frame), when no quest step
DOCK_BACK = 30.0                  # ft walked back along the dock before walking in again, when the scene did not start
# tutorial FSM states -> the event a run logs when it gets there (stageWatch)
STAGE_EV = {'Act2TargetSunk': 'TARGET-SUNK', 'Act3IntroduceJR': 'JR-SCENE', 'Act4BackToMain': 'JR-SANK-BOAT',
            'Act4DoneTutorial': 'TUTORIAL-DONE'}
# messages the tutorial waits on along the boat part (DistributedPiratesTutorial / DistributedTutorialShipCannon)
STAGE_MSGS = {'usedCannon': 'CANNON-USED', 'exitedCannon': 'CANNON-LEFT', 'introduceJR': 'JR-INTRO',
              'JRAttackShip': 'JR-ATTACK', 'JRDestroyShip': 'JR-DESTROY', 'enableBoatBoarding': 'BOAT-BOARDING-ON'}
RUN_T0 = [None]                   # when run() started: the story after the tutorial gets only the run time left


def key(name, on):
    from direct.showbase.InputStateGlobal import inputState
    has = KEY_SRC in inputState._state.get(name, ())
    if on and not has:
        inputState.set(name, True, inputSource=KEY_SRC)
    elif not on and has:
        inputState.set(name, False, inputSource=KEY_SRC)


def keysOff():
    for k in ('forward', 'reverse', 'turnLeft', 'turnRight'):
        key(k, False)


def tut(H):
    return getattr(H.cr, 'tutorialObject', None)


def tstate(H):
    t = tut(H)
    return None if t is None else getattr(t, 'state', None)


def tutNo(H):
    try:
        return H.la.style.getTutorial()
    except Exception:
        return None


def info(H):
    t = tut(H)
    d = {'state': tstate(H), 'tut': tutNo(H), 'game': getattr(H.la.gameFSM, 'state', None), 'area': H.area(),
         'qids': H.qids()}
    if t is not None:
        d.update(leftJail=getattr(t, '_leftJail', None), danStarted=getattr(t, '_danIntroStarted', None),
                 dan=getattr(t, 'NPCDan', None) is not None, boat=getattr(t, 'BoatStumpyDoId', None),
                 hits=getattr(t, 'shipWreckHitCount', None), wreckState=getattr(t, 'shipWreckState', None))
        # probe (TUT16): did Bo Beck reach this client, and what is on his boat
        try:
            d2 = base.cr.doId2do
            sid = getattr(t, 'StumpyDoId', None)
            bid = getattr(t, 'BoatStumpyDoId', None)
            kids = {}
            for o in list(d2.values()):
                if bid and getattr(o, 'parentId', None) == bid:
                    k = '%s@%s' % (o.__class__.__name__, getattr(o, 'zoneId', None))
                    kids[k] = kids.get(k, 0) + 1
            d.update(stumpyId=sid, stumpyHere=sid in d2 if sid else False,
                     stumpyNpc=getattr(t, 'NPCStumpy', None) is not None, boatKids=kids)
        except Exception as e:
            d['probeErr'] = repr(e)
    return d


def wait(H, fn, secs, what, every=45):
    """Generator: poll fn each 0.5 s, an event every `every` s (the walker's HANG fires after 240 s of silence).
    -> True when fn() holds, False (STALL + picture) after secs."""
    t0 = last = time.time()
    while True:
        try:
            if fn():
                return True
        except Exception:
            pass
        now = time.time()
        if now - t0 > secs:
            H.ev('STALL', what=what, **info(H))
            H.snap('stall-' + what)
            return False
        if now - last > every:
            last = now
            H.ev('wait', what=what, secs=round(now - t0), **info(H))
        yield 0.5


def walkUntil(H, gen, stop):
    """Drive a walking generator, dropping it (keys released by its finally) as soon as stop() holds."""
    r = None
    try:
        while True:
            if stop():
                gen.close()
                return True
            y = next(gen)
            yield y
    except StopIteration as e:
        r = e.value
    return r


def panelLog(H):
    from pirates.piratesgui import NewTutorialPanel as NTPm
    o = NTPm.NewTutorialPanel.activate

    def act(panel):
        H.ev('TUT-PANEL', mode=getattr(panel, 'mode', None), state=tstate(H))
        return o(panel)
    NTPm.NewTutorialPanel.activate = act


def makeAPirate(H):
    # Make-A-Pirate in the jail: Next through every page as it comes, then Done (the numeric name the name page
    # picked), each through the button's own command like a click
    ok = yield from wait(H, lambda: tstate(H) == 'Act1MakeAPirate' and getattr(tut(H), 'map', None), 300,
                         'make-a-pirate')
    if not ok:
        return False
    m = tut(H).map
    ok = yield from wait(H, lambda: getattr(m, 'guiNextButton', None) is not None and m.currPageIndex is not None, 60,
                         'map-loaded')
    if not ok:
        return False
    H.ev('MAP-OPEN', page=m.currPageIndex, pages=m.numShops)
    yield 3.0
    for i in range(m.numShops + 2):
        if not m.guiDoneButton.isHidden() or m.currPageIndex >= m.numShops - 1:
            break
        m.guiNextButton['command']()
        H.ev('MAP-NEXT', page=m.currPageIndex)
        _pg, _t = m.currPageIndex, time.time()
        yield ('upto', lambda: time.time() - _t >= 0.5 and m.currPageIndex != _pg, 2.0, 'next maker page')
    H.snap('make-a-pirate')
    m.guiDoneButton['command']()
    H.ev('MAP-DONE', status=getattr(m, 'doneStatus', None))
    ok = yield from wait(H, lambda: tstate(H) == 'EscapeFromLA', 90, 'populated')
    H.ev('PIRATE-MADE', pirate=H.la.getName(), **info(H))
    return ok


def leaveJail(H):
    # Jack's kick opened the cell (LocalPirate.openJailDoor): walk out through the doorway (its hinge and its lock
    # mark the two sides), then to the jail's inside door and use it; the tutorial counts the pirate outside on
    # 'doorToExteriorFadeIn'
    yield from wait(H, lambda: H.la.gameFSM.state == 'LandRoam', 60, 'land-roam')
    _t = time.time()
    yield ('upto', lambda: time.time() - _t >= 1.0 and H.area() is not None, 3.0, 'out of the jail door')
    from panda3d.core import Point3, Vec3
    R = H.render
    lp = H.la.getPos(R)
    try:
        jail = H.la.getParent().getParent()
        hinge = jail.find('**/jail_door01')
        lock = jail.find('**/lock01;+s')
        mid = None
        if not hinge.isEmpty() and not lock.isEmpty():
            mid = (hinge.getPos(R) + lock.getPos(R)) * 0.5
    except Exception as e:
        mid = None
        H.ev('cell-door-err', err=repr(e)[-200:])
    doors = []
    for o in list(H.cr.doId2do.values()):
        if 'Door' in type(o).__name__ and hasattr(o, 'getPos'):
            try:
                doors.append((o.getDistance(H.la), o))
            except Exception:
                pass
    doors.sort(key=lambda x: x[0])
    H.ev('JAIL-DOORS', cell=None if mid is None else [round(v, 1) for v in mid], me=[round(v, 1) for v in lp],
         doors=[{'doId': o.doId, 'cls': type(o).__name__, 'uid': getattr(o, 'uniqueId', None), 'd': round(d, 1)}
                for d, o in doors[:6]])
    door = next((o for d, o in doors if getattr(o, 'uniqueId', None) == JAIL_INTERIOR_DOOR), None)
    if door is None:
        door = next((o for d, o in doors if type(o).__name__ == 'DistributedInteriorDoor'), None)
    if door is None and doors:
        door = doors[0][1]
    if door is None:
        H.ev('STALL', what='no-jail-door', **info(H))
        return False
    if mid is not None:
        out = Vec3(mid[0] - lp[0], mid[1] - lp[1], 0)
        if out.length() > 0.1:
            out.normalize()
        past = Point3(mid[0] + out[0] * 5, mid[1] + out[1] * 5, mid[2])
        ok1 = yield from H.walk_to((mid[0], mid[1], mid[2]), arrive=1.2, timeout=25, tag='cell-doorway')
        ok2 = yield from H.walk_to((past[0], past[1], past[2]), arrive=1.5, timeout=20, tag='out-of-cell')
        H.ev('OUT-OF-CELL', doorway=ok1, past=ok2, me=H.P(H.la))
    left = lambda: getattr(tut(H), '_leftJail', 0)
    for n in range(3):
        if left():
            break
        ok = yield from walkUntil(H, H.walk_to(door, arrive=3.0, timeout=60, tag='jail-door'), left)
        H.ev('GOTO-DOOR', n=n, door=door.doId, reached=ok, d=round(door.getDistance(H.la), 1))
        if left():
            break
        door.requestInteraction(H.la.doId)
        if (yield from wait(H, left, 25, 'outside')):
            break
    ok = bool(left())
    H.ev('LEFT-JAIL' if ok else 'STALL', what='left-jail', **info(H))
    H.snap('outside')
    return ok


def tavernDoor(H):
    # Dan's quest step is the tavern's outside door (QuestStep.STExteriorDoor = 5): stepDoId is that door, posH its spot
    # in the island's frame
    qs = H.la.questStep
    if not qs or qs.getStepType() != 5:
        return qs, None
    door = H.cr.doId2do.get(qs.getStepDoId())
    return qs, door if hasattr(door, 'requestInteraction') else None


def seaChest(H):
    # Doggerel Dan is inside the Rambleshack tavern: walk to its outside door where the quest arrow points and go in,
    # as a player does. Once Dan is generated the tutorial starts his scene itself (DistributedPiratesTutorial.doDanIntro),
    # then the sea chest and Bo Beck's quest; the dialog OKs are clicked by s_story.okAndName, its sea chest / journal
    # panels by s_story.tutPlay
    got = lambda: (tutNo(H) or 0) >= 2 and H.la.gameFSM.state == 'LandRoam'
    dan = lambda: got() or getattr(tut(H), 'NPCDan', None) is not None
    for n in range(3):
        if dan():
            break
        qs, door = tavernDoor(H)
        if qs is None or qs.getStepType() != 5:
            H.ev('TAVERN-STEP', n=n, step=repr(qs), **info(H))
            break
        if door is None:
            # the door is not generated yet (its cell is out of sight): head for its spot until it is
            island = H.cr.doId2do.get(H.la.parentId)
            spot = tuple(qs.posH[:3])
            ok = yield from walkUntil(H, H.walk_to(spot, ref=island, arrive=4.0, timeout=90, tag='tavern-spot'),
                                      lambda: tavernDoor(H)[1] is not None or dan())
            qs, door = tavernDoor(H)
            if door is None:
                H.ev('GOTO-TAVERN', n=n, door=None, step=qs.getStepDoId(), spot=[round(v, 1) for v in spot], reached=ok)
                continue
        ok = yield from walkUntil(H, H.walk_to(door, arrive=3.0, timeout=90, tag='tavern-door'), dan)
        H.ev('GOTO-TAVERN', n=n, door=door.doId, cls=type(door).__name__, reached=ok, d=round(door.getDistance(H.la), 1))
        if dan():
            break
        door.requestInteraction(H.la.doId)
        if (yield from wait(H, dan, 30, 'tavern')):
            break
    H.ev('IN-TAVERN' if dan() else 'STALL', what='tavern', **info(H))
    ok = yield from wait(H, got, 420, 'sea-chest')
    H.ev('GOT-SEACHEST' if ok else 'STALL', what='sea-chest', **info(H))
    return ok


# Rambleshack (world data): a wood fence runs from (26,59) by (39.9,70.4), (65.2,93.4), (84.7,96.2) to (104.4,98.4), and
# another from (117,93) down to (143,63); the dock gate is the gap between them, lit by the torches at (108.1,98.5) and
# (116.6,92.4). Crates, a cart and collision barriers clutter the fence's inland side from x 72 to 98. A player walks
# down the hill on the inland side to the gate, through it, along the dock to the quest node, then to the boat.
DOCK_ROUTE = ((80.0, 66.0, 10.0), (106.8, 84.5, 3.0), (110.7, 95.7, 3.0), (114.6, 104.9, 3.0), (129.1, 127.1, 8.1))


def dockRoute(H, stop):
    """Generator: walk DOCK_ROUTE (island frame) from the first waypoint that is not behind the pirate. -> True when at
    the last one (or stop() held)."""
    # the sea chest can come while the pirate is still in the tavern: wait until he stands on the island outside
    onIsland = lambda: type(H.cr.doId2do.get(H.la.parentId)).__name__ == 'DistributedIsland' or stop()
    if not (yield from wait(H, onIsland, 90, 'outside-tavern')):
        return False
    if stop():
        return True
    island = H.cr.doId2do.get(H.la.parentId)
    if island is None or not hasattr(island, 'getPos') or island.isEmpty():
        return False
    me = H.la.getPos(island)
    end = DOCK_ROUTE[-1]
    d2 = lambda a, b: math.hypot(a[0] - b[0], a[1] - b[1])
    if d2(me, end) < 12.0:
        return True
    start = 0
    for i, w in enumerate(DOCK_ROUTE):
        # skip a waypoint further from the quest node than the pirate already is
        if d2(w, end) < d2(me, end) - 2.0:
            start = i
            break
    else:
        start = len(DOCK_ROUTE) - 1
    ok = True
    for i in range(start, len(DOCK_ROUTE)):
        if stop():
            return True
        w = DOCK_ROUTE[i]
        r = yield from walkUntil(H, H.walk_to(w, ref=island, arrive=3.0, timeout=45, tag='dock-%d' % i), stop)
        if island.isEmpty() or H.cr.doId2do.get(H.la.parentId) is not island:
            H.ev('DOCK-WAY', i=i, to=[w[0], w[1]], reached=r, left='island')
            return bool(stop())
        me = H.la.getPos(island)
        H.ev('DOCK-WAY', i=i, to=[w[0], w[1]], reached=r, me=[round(me[0], 1), round(me[1], 1), round(me[2], 1)])
        ok = bool(r)
    return ok


def dock_end(a, b, ground, step=2.0, back=2.0):
    """Pure: from a (on the dock) step toward b (the boat, out on the water) while there is walkable floor (above
    paths.WATER_Z, no step up or drop a pirate cannot walk); -> the last floor point pulled `back` ft toward a, or a
    itself when the first step already leaves the floor. This is where a player stops at the end of the dock."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return tuple(a)
    ux, uy = dx / L, dy / L
    n = int(L // step)
    pts = [(a[0] + ux * step * i, a[1] + uy * step * i, a[2]) for i in range(1, n + 1)]
    zs = ground(pts) if pts else []
    last, lz, k = tuple(a), a[2], 0
    for i, (p, z) in enumerate(zip(pts, zs)):
        if z is None or z < paths.WATER_Z or z - lz > paths.MAX_RISE or lz - z > paths.MAX_DROP:
            break
        last, lz, k = (p[0], p[1], z), z, i + 1
    if k == 0:
        return tuple(a)
    pull = min(back, step * k)
    return (last[0] - ux * pull, last[1] - uy * pull, last[2])


def stageWatch(H):
    """Log each stage of the boat part as it happens (0.25 s task): tutorial state (TUT-STAGE and its alias), game state,
    the pirate's tutorial number, boarding, the wreck (up / each hit / exit panel), the navy boat, the area, and the
    messages the tutorial waits on (STAGE-EVENT). Stops after the pirate stands in Port Royal. Never throws."""
    from direct.showbase.DirectObject import DirectObject
    obs = DirectObject()
    last = {}

    def onMsg(name):
        def f(*a):
            H.ev('STAGE-EVENT', msg=name, ev=STAGE_MSGS[name], state=tstate(H), game=getattr(H.la.gameFSM, 'state', None))
        return f
    for m in STAGE_MSGS:
        obs.accept(m, onMsg(m))

    def changed(k, v):
        if last.get(k, '<unset>') == v:
            return False
        last[k] = v
        return True

    def task(task):
        try:
            t = tut(H)
            st = tstate(H)
            if changed('state', st) and st is not None:
                H.ev('TUT-STAGE', state=st, alias=STAGE_EV.get(st), tut=tutNo(H))
                if st in STAGE_EV:
                    H.ev(STAGE_EV[st], tut=tutNo(H), area=H.area())
            gs = getattr(H.la.gameFSM, 'state', None)
            if changed('game', gs):
                H.ev('GAME-STATE', game=gs, state=st)
            tn = tutNo(H)
            if changed('tut', tn):
                H.ev('TUT-FLAG', tut=tn, state=st)
            ship = getattr(H.la, 'ship', None)
            sid = getattr(ship, 'doId', None)
            if changed('ship', sid):
                H.ev('BOARDED' if sid else 'LEFT-SHIP', ship=sid, cls=type(ship).__name__ if ship else None, state=st)
            if t is not None:
                w = getattr(t, 'shipWreck', None)
                if changed('wreck', w is not None) and w is not None:
                    H.ev('WRECK-UP', state=st, sailing=True)
                hc = getattr(t, 'shipWreckHitCount', None)
                if changed('hits', hc) and hc:
                    H.ev('WRECK-HIT', n=hc, state=st)
                ws = getattr(t, 'shipWreckState', None)
                if changed('wstate', ws) and ws:
                    H.ev('WRECK-STATE', wreckState=ws, hits=hc)
                nid = getattr(t, 'BoatNavyDoId', None)
                if changed('navy', nid in H.cr.doId2do if nid else False) and nid and nid in H.cr.doId2do:
                    H.ev('NAVY-BOAT', doId=nid, state=st)
            ar = H.area()
            if changed('area', ar):
                H.ev('AREA', area=ar, state=st)
                if t is None and (ar or (None, None))[1] == PORT_ROYAL:
                    H.ev('ARRIVED-PORT-ROYAL', area=ar, tut=tutNo(H), qids=H.qids())
                    obs.ignoreAll()
                    return task.done
        except Exception as e:
            if changed('err', repr(e)[:80]):
                H.ev('stage-watch-err', err=repr(e)[:160])
        return task.again
    H.B.taskMgr.doMethodLater(0.25, task, 'pirBotStageWatch')
    H.ev('stage-watch-on', msgs=sorted(STAGE_MSGS))


def dockEndWalk(H, b, stop):
    """Generator: walk out to the end of the dock toward the boat b (never off it), in the island's frame.
    -> True when there (or stop() held)."""
    island = H.cr.doId2do.get(H.la.parentId)
    if island is None or not hasattr(island, 'getPos'):
        return False
    me, bp = H.la.getPos(island), b.getPos(island)
    _, gr = paths.live(H, 0.0)
    # paths.live samples in render; convert island-frame points through render and back
    R = H.render

    def ground_isl(pts):
        from panda3d.core import Point3
        rp = [R.getRelativePoint(island, Point3(*p)) for p in pts]
        zs = gr([(p[0], p[1], p[2]) for p in rp])
        out = []
        for p, z in zip(rp, zs):
            out.append(None if z is None else island.getRelativePoint(R, Point3(p[0], p[1], z))[2])
        return out
    end = dock_end((me[0], me[1], me[2]), (bp[0], bp[1], bp[2]), ground_isl)
    H.ev('DOCK-END', end=[round(v, 1) for v in end], boat=[round(v, 1) for v in bp], d=round(b.getDistance(H.la), 1))
    r = yield from walkUntil(H, H.walk_to(end, ref=island, arrive=2.0, timeout=40, tag='dock-end'), stop)
    return r


def boatBack(H, stop):
    """Generator: walk DOCK_BACK ft back along the dock toward the gate (the previous dock waypoint), never sideways
    off it -> the pirate can walk into the boat's sphere again."""
    island = H.cr.doId2do.get(H.la.parentId)
    if island is None or not hasattr(island, 'getPos'):
        return False
    me = H.la.getPos(island)
    g = DOCK_ROUTE[-2]
    dx, dy = g[0] - me[0], g[1] - me[1]
    L = math.hypot(dx, dy) or 1.0
    k = min(1.0, DOCK_BACK / L)
    to = (me[0] + dx * k, me[1] + dy * k, me[2])
    r = yield from walkUntil(H, H.walk_to(to, ref=island, arrive=3.0, timeout=40, tag='boat-out'), stop)
    return r


def boat(H):
    # walk to Bo Beck's boat at the dock: its proximity sphere starts his scene, which puts the pirate aboard. The
    # sphere only counts walking in, so a pirate already inside it when Dan finished walks back out and in again
    t = tut(H)
    here = lambda: t.BoatStumpyDoId in H.cr.doId2do
    # the boat may generate early (its cell is in sight from the hill), but the fence stands between: always take the
    # dock route to the quest node first
    triggered0 = lambda: H.la.gameFSM.state in ('Cutscene', 'NPCInteract', 'Dialog') or getattr(H.la, 'ship', None)
    r = yield from dockRoute(H, triggered0)
    H.ev('DOCK-ROUTE', reached=r, **info(H))
    qs = H.la.questStep
    if not here() and qs is not None:
        # the boat is a world ship at the dock, generated only once its cell is in sight: follow the quest arrow there
        island = H.cr.doId2do.get(H.la.parentId)
        spot = tuple(qs.posH[:3])
        ok = yield from walkUntil(H, H.walk_to(spot, ref=island, arrive=4.0, timeout=90, tag='boat-spot'), here)
        H.ev('GOTO-BOAT-SPOT', spot=[round(v, 1) for v in spot], reached=ok, **info(H))
    p0 = H.la.getPos(H.render)
    ok = yield from wait(H, here, 60, 'boat-generated')
    if not ok:
        return None
    b = H.cr.doId2do[t.BoatStumpyDoId]
    aboard = lambda: getattr(H.la, 'ship', None) is b
    triggered = lambda: aboard() or H.la.gameFSM.state in ('Cutscene', 'NPCInteract', 'Dialog')
    H.ev('GOTO-BOAT', boat=b.doId, d=round(b.getDistance(H.la), 1))
    for n, arrive in enumerate((12.0, 6.0, 3.0)):
        if triggered():
            break
        # the boat sits on the water: walk to the shore point nearest it (s_story.go's shore goal), then out to the
        # dock's end toward it, never straight at it off the dock (TUT15/16 stuck on the fence walking blind)
        if n == 0:
            r = yield from walkUntil(H, s_story.go(H, b, arrive, False, None, 'boat'), triggered)
        else:
            r = yield from dockEndWalk(H, b, triggered)
        H.ev('BOAT-WALK', n=n, r=r, d=round(b.getDistance(H.la), 1), **info(H))
        if (yield from wait(H, triggered, 8, 'boat-scene')):
            break
    for n in range(2):
        if triggered():
            break
        # the sphere only counts walking in: back along the dock toward the gate, then out to its end again
        r1 = yield from boatBack(H, triggered)
        r2 = yield from dockEndWalk(H, b, triggered)
        H.ev('BOAT-REENTER', n=n, out=r1, back=r2, d=round(b.getDistance(H.la), 1), **info(H))
        if (yield from wait(H, triggered, 8, 'boat-scene')):
            break
    H.ev('BOAT-SCENE' if triggered() else 'STALL', what='boat-scene', d=round(b.getDistance(H.la), 1), **info(H))
    ok = yield from wait(H, lambda: aboard() and H.la.gameFSM.state == 'LandRoam', 240, 'aboard')
    H.ev('ABOARD' if ok else 'STALL', what='aboard', **info(H))
    return b if ok else None


def toCannon(H, b):
    c = list(b.cannons.values())[0][1]
    using = lambda: getattr(H.la, 'cannon', None) is c
    tgt = c if hasattr(c, 'getPos') else c.prop
    for n in range(4):
        if using():
            break
        ok = yield from H.walk_to(tgt, arrive=3.0 if n < 2 else 2.0, timeout=30, tag='cannon')
        H.ev('GOTO-CANNON', n=n, reached=ok, d=round(tgt.getDistance(H.la), 1))
        c.requestInteraction(H.la.doId)
        yield from wait(H, using, 15, 'on-cannon')
    ok = using()
    H.ev('ON-CANNON' if ok else 'STALL', what='on-cannon', **info(H))
    return c if ok else None


def adiff(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def solve(H, c, T):
    """Heading and pitch (render frame) that put a ball from the muzzle on T: the shot leaves at power*0.6 along the
    barrel plus half the boat's forward speed, and falls at 4x ProjectileInterval gravity (Cannon.playAttack).
    -> (h, p, flightTime) or None when T is out of reach."""
    from pirates.battle import WeaponGlobals
    from direct.interval.ProjectileInterval import ProjectileInterval
    from panda3d.core import Vec3
    v = WeaponGlobals.getAttackProjectilePower(c.skillId, c.getAmmoSkillId()) * 0.6
    g = ProjectileInterval.gravity * 4.0
    S = c.prop.cannonExitPoint.getPos(H.render)
    vb = Vec3(0, 0, 0)
    ship = getattr(c.prop, 'ship', None) or getattr(c, 'ship', None) or getattr(H.la, 'ship', None)
    try:
        if ship:
            vb = ship.smoother.getForwardAxis() * (ship.smoother.getSmoothForwardVelocity() * 0.5)
    except Exception:
        pass
    t = 1.0
    out = None
    for i in range(4):
        A = T - vb * t
        dx, dy, dz = A[0] - S[0], A[1] - S[1], A[2] - S[2]
        R = math.hypot(dx, dy)
        disc = v ** 4 - g * (g * R * R + 2 * dz * v * v)
        if disc < 0 or R < 1:
            return None
        th = math.atan((v * v - math.sqrt(disc)) / (g * R))
        t = R / (v * math.cos(th))
        out = (math.degrees(math.atan2(-dx, dy)), math.degrees(th), t)
    return out


def shoot(H, c):
    # aim the way a player does: hold the arrow keys (CannonCamera turns the barrel) until it points where the
    # ball will land on the wreck, then press the fire key; three hits bring the exit panel, Escape leaves
    t = tut(H)
    ok = yield from wait(H, lambda: getattr(t, 'shipWreck', None) is not None, 40, 'wreck')
    if not ok:
        return False
    from direct.showbase.MessengerGlobal import messenger as msg
    hN, pv = c.prop.hNode, c.prop.pivot
    R = H.render

    def cur():
        return hN.getH(R), pv.getP(R)
    # which way each key turns the barrel (mouse_look flips pitch)
    sign = {}
    for k, idx in (('turnRight', 0), ('forward', 1)):
        a = cur()[idx]
        key(k, True)
        yield 0.25
        key(k, False)
        yield 0.2
        d = adiff(cur()[idx], a) if idx == 0 else cur()[idx] - a
        sign[k] = 1 if d > 0 else -1
        H.ev('AIM-KEY', key=k, moved=round(d, 2))
    # target practice runs inside Act2FindDan; cannonDoneShooting moves on to Act2TargetSunk
    done = lambda: tut(H) is None or tstate(H) in AFTER_CANNON
    shots, hits, tryI, outT, escT = 0, getattr(t, 'shipWreckHitCount', 0), 0, 0.0, None
    t0 = lastEv = time.time()
    try:
        while not done() and time.time() - t0 < 420:
            if getattr(t, 'shipWreckState', 0) >= 1 and escT is None:
                yield 2.0
                escT = time.time()
                keysOff()
                msg.send('escape')
                H.ev('CANNON-ESCAPE', hits=t.shipWreckHitCount)
                continue
            w = getattr(t, 'shipWreck', None)
            if w is None:
                yield 0.5
                continue
            b = w.getTightBounds(R)
            T = (b[0] + b[1]) * 0.5 if b else w.getPos(R)
            sol = solve(H, c, T)
            if sol is None:
                keysOff()
                if time.time() - outT > 30:
                    outT = time.time()
                    H.ev('AIM-OUT-OF-REACH', d=round((T - c.prop.cannonExitPoint.getPos(R)).length(), 1))
                yield 0.5
                continue
            wantH, wantP, ft = sol
            wantP += PITCH_TRIES[tryI % len(PITCH_TRIES)]
            h, p = cur()
            eh, ep = adiff(wantH, h), wantP - p
            key('turnRight', eh * sign['turnRight'] > AIM_TOL)
            key('turnLeft', eh * sign['turnRight'] < -AIM_TOL)
            key('forward', ep * sign['forward'] > AIM_TOL)
            key('reverse', ep * sign['forward'] < -AIM_TOL)
            if time.time() - lastEv > 30:
                lastEv = time.time()
                H.ev('AIMING', eh=round(eh, 1), ep=round(ep, 1), wantP=round(wantP, 1), shots=shots)
            if abs(eh) > AIM_TOL or abs(ep) > AIM_TOL:
                yield 0
                continue
            keysOff()
            rech = H.la.skillDiary.getTimeRemaining(c.skillId) or 0
            if c.volley <= 0 or rech > 0:
                yield 0.2
                continue
            n0 = t.shipWreckHitCount
            msg.send('control')
            shots += 1
            yield from landed(H, t, n0, ft + 1.5, done)
            hit = t.shipWreckHitCount > n0
            H.ev('CANNON-SHOT', n=shots, hit=hit, hits=t.shipWreckHitCount, pitchTry=PITCH_TRIES[tryI % len(PITCH_TRIES)],
                 h=round(h, 1), p=round(p, 1), flight=round(ft, 2))
            if not hit:
                tryI += 1
            if shots >= 40 and t.shipWreckHitCount == hits:
                H.ev('STALL', what='cannon-no-hits', shots=shots)
                return False
    finally:
        keysOff()
    ok = done()
    H.ev('TARGET-PRACTICE-DONE' if ok else 'STALL', what='target-practice', shots=shots, **info(H))
    return ok


def landed(H, t, n0, secs, done):
    t1 = time.time() + secs
    while time.time() < t1:
        if t.shipWreckHitCount > n0 or done():
            return True
        yield 0.1
    return False


def portRoyal(H):
    # Jolly Roger's scene sinks the boat; the tutorial sends the pirate to Port Royal (server-tree patch 0052).
    # 'stopTutorial' comes before the teleport lands, so only standing in Port Royal counts
    from direct.showbase.DirectObject import DirectObject
    seen = {'stop': False}
    obs = DirectObject()
    obs.accept('stopTutorial', lambda: (seen.__setitem__('stop', True), H.ev('STOP-TUTORIAL', **info(H))))
    teleportProbe(H)
    there = lambda: tut(H) is None and (H.area() or (None, None))[1] == PORT_ROYAL
    ok = yield from wait(H, there, 420, 'port-royal')
    if not ok:
        H.ev('NOT-PORT-ROYAL', stop=seen['stop'], **info(H))
        H.ev('TP-FLAGS', **tpFlags())
    _t = time.time()
    yield ('upto', lambda: time.time() - _t >= 1.5 and H.la.getGameState() == 'LandRoam', 5.0, 'roaming in Port Royal')
    obs.ignoreAll()
    return ok


def tpFlags():
    # what decides whether the client's teleport out of the tutorial goes: TUT19 sat on the sunk boat for 6 min
    import builtins
    out = {}
    for name, get in (('inTeleport', lambda: builtins.base.cr.teleportMgr.amInTeleport()),
                      ('phase4', lambda: builtins.base.launcher.getPhaseComplete(4)),
                      ('flags', lambda: str(builtins.localAvatar.getTeleportFlags())),
                      ('activeWorld', lambda: type(builtins.base.cr.activeWorld).__name__),
                      ('tutObj', lambda: type(builtins.base.cr.tutorialObject).__name__)):
        try:
            out[name] = get()
        except Exception as e:
            out[name] = 'err ' + repr(e)[:80]
    return out


def teleportProbe(H):
    # log every call into the tutorial's last act and the teleport manager, with the flags at that moment and any error
    import traceback
    targets = []
    try:
        from pirates.tutorial.DistributedPiratesTutorial import DistributedPiratesTutorial as T
        targets += [(T, n) for n in ('enterAct4BackToMain', 'goBackToMain', 'enterAct4DoneTutorial', 'teleportToPR',
                                     'handleBackToMain')]
        from pirates.instance.DistributedTeleportMgr import DistributedTeleportMgr as M
        targets += [(M, n) for n in ('initiateTeleport', 'teleportInit', 'initiateTeleportAI')]
    except Exception as e:
        H.ev('tp-probe-err', err=repr(e)[:120])
    for cls, name in targets:
        if getattr(cls, '_tpProbe_' + name, False):
            continue
        setattr(cls, '_tpProbe_' + name, True)
        orig = getattr(cls, name)

        def hooked(self, *a, _orig=orig, _name=name, **k):
            H.ev('TP-CALL', fn=_name, args=[str(x)[:40] for x in a[:3]], **tpFlags())
            try:
                return _orig(self, *a, **k)
            except Exception:
                H.ev('TP-ERROR', fn=_name, tb=traceback.format_exc()[-600:])
                raise
        setattr(cls, name, hooked)
    H.ev('tp-probe-on', n=len(targets))


PARENT_SECS = 60.0   # how long after his first move the parent probe logs


def early(ev):
    # Called by the walker at login (before the pirate reaches the world); run(H) only starts 8 s after entered-play
    parentProbe(ev)


def parentProbe(ev):
    # Log every move of the pirate to a new parent in his first PARENT_SECS in the world, with the 6 calls that did it.
    # TUT5 had him in the jail interior, then on the island 1.7 s later at the same x: this names the line. Class-level
    # hooks, so it can go in before the pirate exists. Never throws
    try:
        from pirates.pirate.LocalPirate import LocalPirate
    except Exception as e:
        ev('parent-probe-err', err=repr(e)[:120])
        return
    if getattr(LocalPirate, '_parentProbe', False):
        return
    LocalPirate._parentProbe = True
    t0 = []

    def where(av):
        np = av.getParent()
        return (None if np.isEmpty() else np.getName(), getattr(av, 'parentId', None))

    def log(av, how, args, before):
        try:
            if where(av) == before:
                return
            if not t0:
                t0.append(time.time())
            if time.time() - t0[0] > PARENT_SECS:
                return
            import traceback, builtins
            p = av.getParentObj() if hasattr(av, 'getParentObj') else None
            stack = ['%s:%d %s' % (os.path.basename(f.filename), f.lineno, f.name)
                     for f in traceback.extract_stack()[:-3][-6:]]
            ev('PARENT', how=how, args=[str(a)[:60] for a in args[:3]], frm=list(before),
               cls=None if p is None else type(p).__name__, uid=getattr(p, 'uniqueId', None),
               doId=getattr(p, 'doId', None), node=where(av)[0], zone=getattr(av, 'zoneId', None),
               pos=[round(v, 1) for v in av.getPos(builtins.render)],
               gs=getattr(getattr(av, 'gameFSM', None), 'state', None), stack=stack)
        except Exception as e:
            ev('parent-probe-err', err=repr(e)[:120])

    def wrap(name):
        orig = getattr(LocalPirate, name)

        def hooked(self, *a, **k):
            try:
                before = where(self)
            except Exception:
                before = None
            r = orig(self, *a, **k)
            log(self, name, a, before)
            return r
        setattr(LocalPirate, name, hooked)

    for name in ('reparentTo', 'wrtReparentTo', 'setLocation'):
        try:
            wrap(name)
        except Exception as e:
            ev('parent-probe-err', name=name, err=repr(e)[:120])
    ev('parent-probe-on', secs=PARENT_SECS)


def run(H):
    parentProbe(H.ev)   # a no-op when the walker already put it in at login
    RUN_T0[0] = time.time()
    H.snap('initial')
    H.ev('tutorial-start', **info(H))
    panelLog(H)
    s_story.watchDisconnect(H)   # a lost connection ends the run at once (DISCONNECT event)
    s_story.okAndName(H)
    s_story.tutPlay(H)      # sea chest / lookout panels that wait on the pirate's own clicks, if Dan's scene shows any
    stageWatch(H)           # one event line per boat-part stage, Bo Beck's scene to Port Royal
    steps = (('make-a-pirate', makeAPirate), ('leave-jail', leaveJail), ('sea-chest', seaChest))
    for name, fn in steps:
        if not (yield from fn(H)):
            H.ev('TUTORIAL-STOPPED', at=name, **info(H))
            return
    b = yield from boat(H)
    c = (yield from toCannon(H, b)) if b else None
    if c is None or not (yield from shoot(H, c)):
        H.ev('TUTORIAL-STOPPED', at='boat' if b is None else 'cannon', **info(H))
        return
    if not (yield from portRoyal(H)):
        H.ev('TUTORIAL-STOPPED', at='port-royal', **info(H))
        return
    H.snap('port-royal')
    H.ev('PASS', mission='Tutorial opening (Jack Sparrow) -> Port Royal', pirate=H.la.getName(), **info(H))
    if os.environ.get('TUT_THEN_STORY'):
        s_story.okAndName = s_story.tutPlay = lambda H: None   # already hooked above; never click twice
        if not os.environ.get('STORY_SECS'):
            # s_story counts STORY_SECS from its own start, but the walker ends the run PROOF_SECS after ITS start:
            # give the story only what is left, so STORY-SUMMARY is written before the walker stops
            left = float(os.environ.get('PROOF_SECS', '600')) - (time.time() - RUN_T0[0]) - 45   # walker.py's default
            os.environ['STORY_SECS'] = str(int(max(60, left)))
            H.ev('STORY-TIME', storySecs=os.environ.get('STORY_SECS'), tutSecs=round(time.time() - RUN_T0[0]))
        yield from s_story.run(H)
