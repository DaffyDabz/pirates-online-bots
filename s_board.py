"""BOARD (live check item 7, 11-20): one pirate boards another pirate's ship from a dock rowboat's list.

Two hidden games run this step at once (run_board.ps1). Two test pirates only: never Host's 100000170 or his ship
100000173, never the boys' pirates 100000656 / 100000665. The step stops with FAIL at once if so.

A (BOARD_ROLE=A, the light game: 320x240 window, 5 fps, 10 fps only while it walks): on Port Royal, waits until B's
  rowboat list is open, then launches its own first ship at the dinghy and takes the wheel (sailing.launch). It writes
  the time its ship came into being, then waits by the dock until it sees B standing on its ship.
B (BOARD_ROLE=B, full game, takes the pictures): on Port Royal, walks to the dinghy and opens its list BEFORE A
  launches. Round 1: A's ship must show up in the open list (top of "Own", with A's name) within BOARD_LIVE_MAX s of
  A's ship coming into being. Round 2: closes the list, opens it again, A's ship must be there. Then clicks A's ship's
  Board button (the frame's own button command) and must end up standing on A's ship.
Pictures (B): board_list_live.png (round 1), board_list_reopened.png (round 2), board_b_on_a_ship.png.
The two games talk through small files in BOARD_DIR (B-list-open, A-launched, B-aboard, <role>-done).

Lines: BOARD-START, BOARD-STAGE what=..., BOARD-OFFER (each list the dinghy sent B), BOARD-FRAME (A's row in B's
  "Own" list), BOARD-SHOT, then PASS / FAIL (one per game).
env: BOARD_ROLE (A | B), BOARD_A (avId of A), BOARD_B (avId of B), BOARD_DIR (D:\\scratch\\lanes\\live\\board),
     BOARD_LIVE_MAX (5 s), BOARD_SECS (900)."""
import os, sys, time, json

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402

NEVER = (100000170, 100000656, 100000665)
HOST_SHIP = 100000173
PR = '1150922126.8dzlu'
ROLE = os.environ.get('BOARD_ROLE', '')
A = int(os.environ.get('BOARD_A', '0') or 0)
B = int(os.environ.get('BOARD_B', '0') or 0)
DIR = os.environ.get('BOARD_DIR', r'C:\PiratesBots\out\live\board')
SHOTS = os.environ.get('BOARD_SHOTS', r'C:\PiratesBots\out\live')
LIVE_MAX = float(os.environ.get('BOARD_LIVE_MAX', '5'))
SECS = float(os.environ.get('BOARD_SECS', '900'))
MINI = os.environ.get('BOARD_MINI') == '1'     # A minimizes once it is at the wheel (only if the mini check passed)
B_FPS = 15                                     # Host's OK (11-20): both games tiny; B still has to click and walk


def cls(o):
    return type(o).__name__


def put(name, **kw):
    kw.setdefault('t', time.time())
    tmp = os.path.join(DIR, name + '.tmp')
    with open(tmp, 'w') as f:
        json.dump(kw, f)
    os.replace(tmp, os.path.join(DIR, name))


def get(name):
    try:
        with open(os.path.join(DIR, name)) as f:
            return json.load(f)
    except Exception:
        return None


def shot(H, name):
    from panda3d.core import Filename
    path = os.path.join(SHOTS, name)
    try:
        ok = H.B.win.saveScreenshot(Filename.fromOsSpecific(path))
    except Exception as e:
        ok = 'err %s' % e
    H.ev('BOARD-SHOT', file=path, ok=ok)


def fps(n):
    globalClock.setFrameRate(n if ROLE == 'A' else B_FPS)


def checkSetup(me):
    if ROLE not in ('A', 'B'):
        return 'BOARD_ROLE must be A or B'
    if not A or not B or A == B:
        return 'BOARD_A and BOARD_B must be two different test pirates'
    if A in NEVER or B in NEVER or me in NEVER:
        return 'refused: a real player\'s pirate'
    if me != (A if ROLE == 'A' else B):
        return 'this game logged in as %d, not the %s pirate' % (me, ROLE)
    return None


def toPortRoyal(H):
    la = H.la
    if sailing.hereUid(H) != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 3


def otherDone():
    """The other game's end ('ok' / 'bad', never the word itself: run_board.ps1 reads a quoted PASS as a pass)."""
    o = get(('B' if ROLE == 'A' else 'A') + '-done')
    return None if o is None else ('ok' if o.get('ok') else 'bad')


def end(H, verdict, **kw):
    H.ev(verdict, role=ROLE, **kw)
    put(ROLE + '-done', ok=verdict == 'PASS')


def run(H):
    la = H.la
    yield ('until', lambda: la.getGameState() == 'LandRoam', 120, 'LandRoam')
    why = checkSetup(la.doId)
    H.ev('BOARD-START', role=ROLE, me=la.doId, a=A, b=B, why=why)
    if why:
        end(H, 'FAIL', why=why); return
    try:                    # both games tiny (Host's OK); B's pictures are 320x240 too
        from panda3d.core import WindowProperties
        wp = WindowProperties()
        wp.setSize(320, 240)
        H.B.win.requestProperties(wp)
    except Exception as e:
        H.ev('BOARD-SMALL-ERR', err=str(e))
    fps(10)
    yield from toPortRoyal(H)
    if ROLE == 'A':
        yield from runA(H)
    else:
        yield from runB(H)


def runA(H):
    la = H.la
    ships = list(la.getInventory().getShipDoIdList())
    if not ships or ships[0] == HOST_SHIP:
        end(H, 'FAIL', why='A has no ship of its own', ships=ships); return
    sid = ships[0]
    H.ev('BOARD-STAGE', what='waiting for B\'s open list', ship=sid)
    yield ('upto', lambda: get('B-list-open') or otherDone(), 600)
    if not get('B-list-open'):
        end(H, 'FAIL', why='B never opened its rowboat list', b=otherDone()); return
    # launch, and note the moment the ship came into being (the server's offer to B can only follow that)
    marks = {}
    origEv = H.ev

    def evHook(name, /, **kw):
        if name == 'launch' and 'select' not in marks:
            marks['select'] = time.time()
        origEv(name, **kw)
    H.ev = evHook
    g = sailing.launch(H, PR, False)
    ship = None
    try:
        while True:
            try:
                y = next(g)
            except StopIteration as e:
                ship = e.value
                break
            if 'ship' not in marks and sid in H.cr.doId2do:
                marks['ship'] = time.time()
                put('A-launched', ship=sid, select=marks.get('select'), shipT=marks['ship'], t=marks['ship'])
                origEv('BOARD-STAGE', what='ship came into being', ship=sid)
            yield y
    finally:
        H.ev = origEv
    if 'ship' not in marks and sid in H.cr.doId2do:
        marks['ship'] = time.time()
        put('A-launched', ship=sid, select=marks.get('select'), shipT=marks['ship'], t=marks['ship'])
    if ship is None:
        end(H, 'FAIL', why='A could not launch its ship (see SAIL-FAIL)'); return
    fps(5)
    H.ev('BOARD-STAGE', what='at the wheel by the dock', ship=sid, pos=H.P(ship))
    if MINI:                # no picture from here on: A only waits for B
        from panda3d.core import WindowProperties
        wp = WindowProperties()
        wp.setMinimized(True)
        H.B.win.requestProperties(wp)
        H.ev('BOARD-STAGE', what='minimized')

    def bOnShip():
        b = H.cr.doId2do.get(B)
        p = b.getParentObj() if b is not None and hasattr(b, 'getParentObj') else None
        return getattr(p, 'doId', None) == sid
    yield ('upto', lambda: bOnShip() or otherDone(), SECS)
    seen = bOnShip()
    if seen:
        H.ev('BOARD-STAGE', what='B is standing on my ship', ship=sid)
        yield ('upto', lambda: otherDone(), 30)
        end(H, 'PASS', what='B boarded A\'s ship', ship=sid, b=otherDone())
    else:
        end(H, 'FAIL', why='B never stood on A\'s ship', b=otherDone())


def ownRows(d):
    p = getattr(d, 'shipSelection', None)
    if p is None:
        return []
    out = []
    for i, f in enumerate(list(p.shipFrames.get(p.OWN, []))):
        try:
            out.append((i, f['shipId'], f['shipType'], f))
        except Exception:
            pass
    return out


def aRow(d, sid):
    for i, s, t, f in ownRows(d):
        if s == sid:
            return i, f
    return None


def rowInfo(d, sid):
    r = aRow(d, sid)
    if r is None:
        return None
    i, f = r

    def opt(fn):
        try:
            return fn()
        except Exception as e:
            return 'err %s' % e
    p = d.shipSelection
    from pirates.piratesgui.ShipFrameDeploy import ShipFrameDeploy
    rows = ownRows(d)
    # "top of Own": no own ship above it (another pirate's ship that was offered earlier may be)
    return {'index': i, 'rows': len(rows), 'top': all(t != ShipFrameDeploy.STOwn for j, s, t, g in rows[:i]),
            'ownTab': opt(lambda: p.page == p.OWN), 'ship': opt(lambda: f['shipName']),
            'captain': opt(lambda: f['avatarName']), 'crewNames': opt(lambda: list(f.snapShot['crewNames'])),
            'button': getattr(f, 'button', None) is not None, 'shown': opt(lambda: not f.isHidden())}


def hookOffers(H, d):
    """Log every list the dinghy sends B (time, tab, ships, owners)."""
    for meth, tab in (('offerBandOptions', 'crew'), ('offerFriendOptions', 'friend'),
                      ('offerGuildOptions', 'guild'), ('offerPublicOptions', 'public')):
        orig = getattr(d, meth)

        def hook(options, _orig=orig, _tab=tab):
            try:
                H.ev('BOARD-OFFER', tab=_tab, ships=[(o[0], o[1], o[-1]) for o in options])
            except Exception:
                pass
            return _orig(options)
        setattr(d, meth, hook)


def openList(H, d):
    la = H.la
    d.requestInteraction(la.doId)
    yield ('until', lambda: la.getGameState() == 'DinghyInteract' and getattr(d, 'shipSelection', None) is not None,
           20, 'rowboat list open')
    return la.getGameState() == 'DinghyInteract' and getattr(d, 'shipSelection', None) is not None


def runB(H):
    la = H.la
    d = yield from sailing.to_dinghy(H, PR)
    if d is None:
        end(H, 'FAIL', why='B could not reach a dinghy'); return
    hookOffers(H, d)
    if not (yield from openList(H, d)):
        end(H, 'FAIL', why='B\'s rowboat list did not open', gs=la.getGameState()); return
    yield 2
    put('B-list-open', dinghy=d.doId)
    H.ev('BOARD-STAGE', what='list open, waiting for A to launch', own=[(i, s) for i, s, t, f in ownRows(d)])

    # round 1: A launches while B's list is open
    yield ('upto', lambda: get('A-launched') or otherDone(), 600)
    al = get('A-launched')
    if not al:
        end(H, 'FAIL', why='A never launched', a=otherDone()); return
    sid = al['ship']
    if sid == HOST_SHIP:
        end(H, 'FAIL', why='refused: Host\'s ship'); return
    yield ('upto', lambda: aRow(d, sid) is not None or la.getGameState() != 'DinghyInteract', 60)
    seenT = time.time() if aRow(d, sid) is not None else None
    live = round(seenT - al['shipT'], 1) if seenT else None
    info1 = rowInfo(d, sid)
    H.ev('BOARD-FRAME', round=1, ship=sid, afterShip=live,
         afterSelect=round(seenT - al['select'], 1) if seenT and al.get('select') else None, row=info1)
    if info1 is not None:
        yield 1.5
        shot(H, 'board_list_live.png')
    r1 = live is not None and live <= LIVE_MAX and info1 is not None and info1['top'] is True

    # round 2: close the list, open it again
    try:
        d.shipSelection.closePanel()
    except Exception as e:
        H.ev('BOARD-CLOSE-ERR', err=str(e))
    yield ('until', lambda: la.getGameState() != 'DinghyInteract', 15, 'list closed')
    yield 3
    if not (yield from openList(H, d)):
        end(H, 'FAIL', why='B\'s rowboat list did not open again', round1=r1); return
    t2 = time.time()
    yield ('upto', lambda: aRow(d, sid) is not None, 15)
    info2 = rowInfo(d, sid)
    H.ev('BOARD-FRAME', round=2, ship=sid, afterOpen=round(time.time() - t2, 1), row=info2)
    if info2 is None:
        end(H, 'FAIL', why='A\'s ship not in the reopened list', round1=r1); return
    yield 1.5
    shot(H, 'board_list_reopened.png')
    r2 = info2['top'] is True

    # board: the Board button on A's row, as a click
    i, f = aRow(d, sid)
    try:
        f.button.commandFunc(None)
        H.ev('BOARD-STAGE', what='clicked Board', ship=sid)
    except Exception as e:
        end(H, 'FAIL', why='the Board button failed: %s' % e); return

    def onA():
        p = la.getParentObj()
        return getattr(p, 'doId', None) == sid
    yield ('until', onA, 90, 'standing on A\'s ship')
    aboard = onA()
    if aboard:
        yield ('until', lambda: la.getGameState() in ('LandRoam', 'WaterRoam'), 20, 'walking on deck')
        yield 3
        shot(H, 'board_b_on_a_ship.png')
        put('B-aboard', ship=sid)
    if r1 and r2 and aboard:
        end(H, 'PASS', what='A\'s ship showed live and after reopening, B boarded', liveSecs=live)
    else:
        end(H, 'FAIL', why='round1=%s (%s s, max %s) round2=%s aboard=%s' % (r1, live, LIVE_MAX, r2, aboard))
    yield 10
