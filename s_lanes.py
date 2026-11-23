"""Shared bits for the lane steps s_shop, s_shipfight and s_parlor (pir-bot, 11-17). Not a step itself (no run()).

walkTo() drives the same walk helpers s_story uses (s_story.goto / near / cardTable / useDoor): each tick it asks a
function where to go, and runs the walk that function left in st['go'] (held keys, round the buildings, never
setPos). onIsland() is the one setup move: the game's own areaTeleport when the pirate starts on another island,
logged SETUP-TP, never in the middle of a step."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402
import s_story   # noqa: E402

PR = s_story.PR
TORTUGA = '1156207188.95dzlu'


def stage(H, step, what, **kw):
    """One STAGE line: step = the lane step (shop / shipfight / parlor), what = how far it got."""
    H.ev('STAGE', step=step, what=what, gs=H.la.getGameState(), area=H.area(), **kw)


def islandOf(H):
    """The island uid the pirate is on or in (an interior counts as its island), or None at sea / unknown."""
    here = s_story.hereArea(H)
    a = s_story.questSpots()['areas'].get(here)
    if a:
        return a[0]
    return sailing.hereUid(H)


def onIsland(H, step, uid):
    """Generator: True once the pirate stands on island uid (or in one of its buildings), in LandRoam. Setup only:
    from anywhere else it uses the game's areaTeleport, logged SETUP-TP with why."""
    yield ('until', lambda: H.la.getGameState() in ('LandRoam', 'ShipPilot', 'WaterRoam'), 60, 'LandRoam')
    if islandOf(H) == uid and H.la.getGameState() == 'LandRoam':
        return True
    H.ev('SETUP-TP', step=step, to=uid, frm=H.area(), gs=H.la.getGameState(), why='the step starts on this island')
    H.mw('areaTeleport %s' % uid)
    yield ('until', lambda: sailing.hereUid(H) == uid and H.la.getGameState() == 'LandRoam', 90, 'on ' + uid)
    return sailing.hereUid(H) == uid and H.la.getGameState() == 'LandRoam'


def walkTo(H, step, fn, secs, tag):
    """Generator. fn(st) is asked each tick: True (there), a tuple (there, with what it found, e.g. s_story.cardTable's
    ('cards', doId, kind)), ('sail', island) (it is on another island: not walkable, a STALL), or a string saying what
    it is doing, with a walk left in st['go']. -> True / the tuple, or None after a STALL (logged)."""
    st = {}
    t0 = time.time()
    last = None
    while time.time() - t0 < secs:
        r = fn(st)
        if r is True or (isinstance(r, tuple) and r and r[0] != 'sail'):
            return r
        if isinstance(r, tuple):
            H.ev('STALL', step=step, what='%s is on another island (%s): this step does not sail' % (tag, r[1]),
                 area=H.area())
            return None
        if r != last:
            H.ev('act', step=step, a=str(r), la=H.P(H.la), area=H.area())
            last = r
        g = st.pop('go', None)
        if g is not None and H.la.getGameState() == 'LandRoam':
            obj, arrive, face, ref, t = g
            yield from s_story.go(H, obj, arrive, face, ref, t)
        else:
            yield 1
    H.ev('STALL', step=step, what='walk to %s took over %d s' % (tag, secs), last=str(last), la=H.P(H.la),
         area=H.area())
    return None


def gold(H):
    inv = H.la.getInventory()
    return inv.getGoldInPocket() if inv else 0
