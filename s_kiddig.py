"""KID DIG (pir-boat, 11-17): dig the same treasure spot twice, then a second spot, and check the chest shows every
time. Proves patch 0133 (client: pirates/treasuremap/DistributedBuriedTreasure.py).

The bug 0133 fixes: a dig ends with showTreasure (lids open, then the whole spot fades to alpha 0 and the chest is
stashed). 5 s later the AI resets the spot (setCurrentDepth(startingDepth)); the stock client only stashed the chest
there and never undid the fade or closed the lids, so the NEXT dig at that spot (same client) showed no chest and no
dirt: the kid dug at nothing. 0133 clears the colour scale and transparency and closes the lids on the reset.

What it does (Tortuga by default; every walk under FAST_START=1 is a warp to the spot, logged SETUP-WARP):
1. Spot A = the nearest live dig spot (DistributedBuriedTreasure in view within KID_DIG_RANGE ft); with none in view
   it walks to the nearest spot in dig_spots.json until one shows.
2. dig A, dig A again (the 0133 proof), then dig B (another spot, a different doId).
   Each dig: dropQuest 518 / giveQuest 518 (a fresh 'recover a treasure' quest, so the server lets him dig: with no
   open treasure task it says AlreadySearched), walk within 5 ft, requestInteraction (the same call the game makes
   when he presses the dig key), retry on a refusal (518 rolls 80% per dig) up to KID_DIG_TRIES, then wait:
   - DIG-SEEN: the first depth step below the start: the chest must be unstashed and the spot NOT faded
     (no colour scale, or alpha > 0.99). A faded spot here is the old bug ('chest invisible').
   - DIG-OPENED: showTreasure (the chest opens; gold).
   - DIG-RESET: the AI's reset 5 s later: no colour scale, no transparency, lids closed (hpr ~0), chest stashed.
   - DIG-FREE: his game state is back to LandRoam (not stuck in Digging), and he is still online.
3. dropQuest 518 at the end (it is the step's own quest; it is never kept).
PASS only when all three digs went through every check and he stayed online. Without 0133 in the client it still
runs (PATCH-CHECK present=False) and the second dig at A FAILs 'chest invisible': that is the old bug, shown.

env: KID_DIG_AT (island uid; default Tortuga; '' = stay), KID_DIG_QUEST (518), KID_DIG_TRIES (5), KID_DIG_RANGE (300).
Lines: KID-DIG-START, PATCH-CHECK, STAGE step=dig what=on-island / spot-a / spot-b / dig n, DIG-QUEST, DIG-REQUEST,
DIG-EV (every hooked client call on a spot), DIG-DENIED (a refusal), DIG-SEEN, DIG-OPENED, DIG-RESET, DIG-FREE,
DIG-RESULT (one per dig), then PASS / FAIL. Run time after boot: about 3 min."""
import os, sys, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402
import s_story   # noqa: E402

NEVER = 100000170
AT = os.environ.get('KID_DIG_AT', s_lanes.TORTUGA)
QID = os.environ.get('KID_DIG_QUEST', '518')
TRIES = int(os.environ.get('KID_DIG_TRIES', '5'))
RANGE = float(os.environ.get('KID_DIG_RANGE', '300'))
STEP = 'dig'
HOOKED = ('setCurrentDepth', 'showTreasure', 'startDigging', 'rejectInteraction', 'stopDigging')


def hasPatch():
    """0133 is in the loaded client: the reset branch of setCurrentDepth clears the colour scale."""
    import inspect
    from pirates.treasuremap.DistributedBuriedTreasure import DistributedBuriedTreasure as D
    try:
        return 'clearColorScale' in inspect.getsource(D.setCurrentDepth)
    except Exception:
        return None


def faded(spot):
    """The spot is faded out (the old bug): it has a colour scale whose alpha is below 0.99."""
    try:
        return bool(spot.hasColorScale() and spot.getColorScale()[3] < 0.99)
    except Exception:
        return False


def lidsShut(spot):
    out = []
    for name in ('chestLidHigh', 'chestLidMed', 'chestLidLow'):
        lid = getattr(spot, name, None)
        if lid is None or lid.isEmpty():
            continue
        out.append(max(abs(v) for v in lid.getHpr()) < 1.0)
    return all(out) if out else None


def resetLooks(spot):
    """Pure-ish: the reset visuals -> (ok, facts)."""
    chest = getattr(spot, 'chest', None)
    facts = {'colorScale': bool(spot.hasColorScale()), 'transparent': bool(spot.hasTransparency()),
             'lidsShut': lidsShut(spot), 'chestStashed': bool(chest.isStashed()) if chest else None}
    ok = not facts['colorScale'] and not facts['transparent'] and facts['lidsShut'] is not False and \
        facts['chestStashed'] is not False
    return ok, facts


def verdict(digs, want=3, err=None):
    """Pure. digs = [{'n', 'spot', 'ok', 'why'}], err = the step's own error line -> (ok, why)."""
    if err:
        return False, 'the step itself broke after %d digs: %s (see KID-STEP-ERROR)' % (len(digs), err)
    if len(digs) < want:
        bad = next((d for d in digs if not d['ok']), None)
        return False, bad['why'] if bad else 'only %d of %d digs ran' % (len(digs), want)
    bad = next((d for d in digs if not d['ok']), None)
    if bad:
        return False, 'dig %d (%s): %s' % (bad['n'], bad['label'], bad['why'])
    if digs[0]['spot'] != digs[1]['spot'] or digs[2]['spot'] == digs[0]['spot']:
        return False, 'the digs were not A, A, B (%s)' % [d['spot'] for d in digs]
    return True, 'dug the same chest twice and a second chest: the chest showed, opened and reset every time'


def online(H):
    try:
        if H.cr.loginFSM.getCurrentState().getName() == 'noConnection':
            return False
    except Exception:
        pass
    return H.la is not None and H.la.doId in H.cr.doId2do


def run(H):
    la, cr = H.la, H.cr
    if la.doId == NEVER:
        H.ev('FAIL', why='refused: pirate 100000170 is never a test pirate'); return
    try:
        import s_fast
        if not s_fast.STATE.get('installed'):
            s_fast.install(H)
    except ImportError:
        pass
    try:
        s_story.watchDisconnect(H)
    except Exception as e:
        H.ev('note', what='watchDisconnect not started', err=repr(e))
    from pirates.treasuremap.DistributedBuriedTreasure import DistributedBuriedTreasure as D

    H.ev('KID-DIG-START', at=AT or 'stay', quest=QID, tries=TRIES)
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if AT:
        ok = yield from s_lanes.onIsland(H, STEP, AT)
        if not ok:
            H.ev('FAIL', why='could not reach the test island %s' % AT, area=H.area()); return
    s_lanes.stage(H, STEP, 'on-island')
    patched = hasPatch()
    H.ev('PATCH-CHECK', patch='0133', present=patched)

    evs = []          # (time, doId, call, args)
    saved = {}

    def hook(name):
        orig = getattr(D, name)
        saved[name] = orig

        def f(self, *a, **k):
            evs.append((time.time(), self.doId, name, a))
            try:
                H.ev('DIG-EV', spot=self.doId, call=name, args=[str(x)[:20] for x in a],
                     depth=getattr(self, 'currentDepth', None), start=getattr(self, 'startingDepth', None))
            except Exception:
                pass
            return orig(self, *a, **k)
        setattr(D, name, f)
    for n in HOOKED:
        hook(n)

    def seen(doId, call, since, test=None):
        return any(t >= since and d == doId and c == call and (test is None or test(a)) for t, d, c, a in evs)

    def spots():
        out = [o for o in list(cr.doId2do.values()) if type(o).__name__ == 'DistributedBuriedTreasure']
        out = [o for o in out if s_story.hdist(H, o) <= RANGE]
        return sorted(out, key=lambda o: s_story.hdist(H, o))

    def findSpot(avoid=()):
        """Generator -> a live spot not in avoid, walking toward the json spots of this area until one shows."""
        live = [o for o in spots() if o.doId not in avoid]
        if live:
            return live[0]
        org, pts = s_story.digSpots(H)
        if org is None or not pts:
            return None
        pts = sorted(pts, key=lambda p: s_story.hdist(H, p, org))
        for p in pts:
            r = yield from s_lanes.walkTo(
                H, STEP, lambda st, p=p: True if ([o for o in spots() if o.doId not in avoid] or
                                                  s_story.near(H, p, 8, st, face=False, ref=org, tag='to-dig'))
                else 'walk-to-json-spot', 90, 'a dig spot')
            live = [o for o in spots() if o.doId not in avoid]
            if live:
                return live[0]
            if r is None:
                break
        return None

    def freshQuest():
        if H.has(QID):
            H.mw('dropQuest %s' % QID)
            yield ('until', lambda: not H.has(QID), 12, 'quest %s dropped' % QID)
        H.mw('giveQuest %s' % QID)
        yield ('until', lambda: H.has(QID), 12, 'quest %s given' % QID)
        H.ev('DIG-QUEST', quest=QID, has=H.has(QID), resp=H.resp[-2:] if getattr(H, 'resp', None) else None)
        return H.has(QID)

    def digOnce(n, label, spot):
        r = {'n': n, 'label': label, 'spot': spot.doId, 'ok': False, 'why': ''}
        s_lanes.stage(H, STEP, 'dig %d' % n, label=label, spot=spot.doId, uid=getattr(spot, 'uniqueId', None),
                      start=spot.startingDepth, depth=spot.currentDepth, faded=faded(spot))
        got = yield from freshQuest()
        if not got:
            r['why'] = 'giveQuest %s did not give the quest' % QID; return r
        went = False
        for k in range(TRIES):
            w = yield from s_lanes.walkTo(H, STEP, lambda st: True if s_story.near(H, spot, 5, st, face=False, tag='dig')
                                          else 'walk-to-dig', 90, 'dig spot %d' % spot.doId)
            if w is None:
                r['why'] = 'could not walk to the spot'; return r
            # the AI resets a spot 5 s after a dig: wait for it to be whole before asking
            yield ('upto', lambda: spot.currentDepth == spot.startingDepth, 12, 'spot whole')
            t0 = time.time()
            H.ev('DIG-REQUEST', spot=spot.doId, n=n, attempt=k + 1, dist=round(s_story.hdist(H, spot), 1))
            spot.requestInteraction(la.doId)
            yield ('upto', lambda: seen(spot.doId, 'startDigging', t0) or seen(spot.doId, 'rejectInteraction', t0),
                   6, 'dig answer')
            if seen(spot.doId, 'startDigging', t0):
                went = True
                break
            H.ev('DIG-DENIED', spot=spot.doId, attempt=k + 1, rejected=seen(spot.doId, 'rejectInteraction', t0),
                 why='AlreadySearched: the quest roll failed or the spot was busy; a fresh quest, then again')
            try:
                la.motionFSM.on()
            except Exception:
                pass
            yield 3
            got = yield from freshQuest()
        if not went:
            r['why'] = 'the server refused %d digs in a row' % TRIES; return r
        start = spot.startingDepth or 1
        yield ('until', lambda: seen(spot.doId, 'setCurrentDepth', t0, lambda a: a and a[0] < start), 15, 'first dig step')
        if not seen(spot.doId, 'setCurrentDepth', t0, lambda a: a and a[0] < start):
            r['why'] = 'no dig step came'; return r
        yield 0.5
        chest = getattr(spot, 'chest', None)
        vis = {'chestThere': chest is not None, 'chestStashed': bool(chest.isStashed()) if chest else None,
               'faded': faded(spot), 'alpha': round(spot.getColorScale()[3], 2) if spot.hasColorScale() else None}
        H.ev('DIG-SEEN', spot=spot.doId, n=n, **vis)
        if not vis['chestThere'] or vis['chestStashed'] or vis['faded']:
            r['why'] = 'chest invisible while digging (%s): the old bug 0133 fixes' % vis; return r
        yield ('until', lambda: seen(spot.doId, 'showTreasure', t0), start + 15, 'chest opens')
        if not seen(spot.doId, 'showTreasure', t0):
            r['why'] = 'the chest never opened (no showTreasure)'; return r
        t1 = time.time()
        H.ev('DIG-OPENED', spot=spot.doId, n=n, secs=round(t1 - t0, 1))
        yield ('until', lambda: seen(spot.doId, 'setCurrentDepth', t1, lambda a: a and a[0] == spot.startingDepth),
               12, 'spot reset')
        if not seen(spot.doId, 'setCurrentDepth', t1, lambda a: a and a[0] == spot.startingDepth):
            r['why'] = 'the spot never reset'; return r
        yield 0.5
        ok, facts = resetLooks(spot)
        H.ev('DIG-RESET', spot=spot.doId, n=n, ok=ok, **facts)
        if not ok:
            r['why'] = 'the reset left the spot wrong (%s)' % facts; return r
        yield ('until', lambda: la.getGameState() == 'LandRoam', 10, 'back to LandRoam')
        gs = la.getGameState()
        H.ev('DIG-FREE', spot=spot.doId, n=n, state=gs, online=online(H))
        if not online(H):
            r['why'] = 'he was dropped from the game'; return r
        if gs != 'LandRoam':
            r['why'] = 'stuck in %s after the dig' % gs; return r
        r['ok'], r['why'] = True, 'chest showed, opened, reset'
        return r

    digs = []
    err = []
    try:
        a = yield from findSpot()
        if a is None:
            H.ev('FAIL', why='no dig spot on this island (none in view, none in dig_spots.json)', area=H.area()); return
        s_lanes.stage(H, STEP, 'spot-a', spot=a.doId, uid=getattr(a, 'uniqueId', None), dist=round(s_story.hdist(H, a), 1))
        for n, label in ((1, 'A'), (2, 'A again')):
            r = yield from digOnce(n, label, a)
            digs.append(r)
            H.ev('DIG-RESULT', **r)
            if not r['ok']:
                return
        b = yield from findSpot(avoid=(a.doId,))
        if b is None:
            digs.append({'n': 3, 'label': 'B', 'spot': None, 'ok': False, 'why': 'no second dig spot found'})
            return
        s_lanes.stage(H, STEP, 'spot-b', spot=b.doId, uid=getattr(b, 'uniqueId', None), dist=round(s_story.hdist(H, b), 1))
        r = yield from digOnce(3, 'B', b)
        digs.append(r)
        H.ev('DIG-RESULT', **r)
    except Exception as e:
        err.append('%s: %s' % (type(e).__name__, e))
        H.ev('KID-STEP-ERROR', err=err[0], tb=traceback.format_exc())
    finally:
        for n, f in saved.items():
            setattr(D, n, f)
        try:
            if H.has(QID):
                H.mw('dropQuest %s' % QID)
        except Exception:
            pass
        ok, why = verdict(digs, err=err[0] if err else None)
        if ok:
            H.ev('PASS', what=why, spots=[d['spot'] for d in digs], patched=patched)
        else:
            H.ev('FAIL', why=why, digs=[(d['label'], d['spot'], d['ok']) for d in digs], patched=patched)
