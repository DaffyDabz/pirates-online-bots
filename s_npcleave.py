"""NPCLEAVE (reworked 11-17): after a teleport from Port Royal to Tortuga, are Port Royal's NPCs gone from the client?

Why the rework: the old NPCLEAVE (ship parts dropped mid-load, 11-16) forced a sea cell out of sight by hand with
alterInterest. pir-boat found that this was a broken test, not a game bug: the drop it made is not one the game makes.
The real leak was that Port Royal's town NPCs stayed in the client after the pirate left the island (FRIENDTELE3 saw
one 25 s after landing on Tortuga). pir-boat's diff 07 closes the island's cell interests when the pirate leaves it.
This test checks that fix the way a player would meet it: stand on Port Royal, teleport to Tortuga with the game's
own areaTeleport, then watch every Port Royal object leave the client. The old version is in the harness git history.

Steps and event lines:
  NPCLEAVE-START                     where he is
  pr-ready                           on Port Royal's open ground (areaTeleport there when not), LandRoam
  pr-seen n=.. byClass={..} npcs=[..] what Port Royal holds in the client once its town NPCs are in: every object whose
                                      parent is the island (or a child of one of them), minus the island and our own
  tele-out                           the teleport to Tortuga started (TeleportOut, or he left Port Royal)
  landed secs=..                     standing on Tortuga, LandRoam
  pr-left left=.. gone=.. secs=..    each time the count of Port Royal objects still in the client drops
  pr-gone secs=..                    every one of them is gone (secs from landing)
  npc-still-seen ...                 at the end, for what is left: class, name, zone, parent, and the client's
                                      interests still open on Port Royal (the cell handles that hold them)
  back (NPCLEAVE_BACK=1)             teleport back to Port Royal: pr-back folk=.. (the town NPCs come again)
  PASS / FAIL
PASS = all of Port Royal's objects gone within GONE_SECS of landing on Tortuga, no kick. With NPCLEAVE_BACK=1 also:
Port Royal's town NPCs are in sight again within 30 s of landing back there (the fix must not leave the island empty).
In the server's ai.log, diff 07 writes "Avatar <id> left island <PR doId>: closing its <k> cell interests".
env: NPCLEAVE_GONE_SECS (default 10), NPCLEAVE_WATCH (default 25 s of watching after landing), NPCLEAVE_BACK (0)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402
from s_dock import cls   # noqa: E402

PR = '1150922126.8dzlu'
TORTUGA = '1156207188.95dzlu'
GONE_SECS = float(os.environ.get('NPCLEAVE_GONE_SECS', '10'))
WATCH = max(GONE_SECS, float(os.environ.get('NPCLEAVE_WATCH', '25')))
BACK = os.environ.get('NPCLEAVE_BACK', '0') == '1'
# never counted: things that belong to the pirate himself or to the whole district, not to the island
SKIP_CLS = ('DistributedPlayerPirate', 'LocalPirate', 'DistributedPlayerSimpleShip', 'DistributedInventory',
            'DistributedPirateInventory', 'DistributedTravelAgent')


def prObjects(cr, prId, myIds):
    """Pure-ish: the doIds in the client that belong to Port Royal -> {doId: obj}. An object belongs when its parent
    is the island, or (one level down, e.g. an NPC's held weapon or a building's door) its parent is one that does."""
    out = {}
    objs = list(cr.doId2do.items())
    for doId, o in objs:
        if doId == prId or doId in myIds or cls(o) in SKIP_CLS:
            continue
        if getattr(o, 'parentId', None) == prId:
            out[doId] = o
    for doId, o in objs:
        if doId in out or doId == prId or doId in myIds or cls(o) in SKIP_CLS:
            continue
        if getattr(o, 'parentId', None) in out:
            out[doId] = o
    return out


def byClass(objs):
    c = {}
    for o in objs.values():
        k = cls(o)
        c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def name(o):
    try:
        return o.getName()
    except Exception:
        return getattr(o, 'name', None)


def run(H):
    from panda3d.core import DatagramIterator
    la, cr = H.la, H.cr
    got = {}
    orig = cr.handleGoGetLost

    def ggl(di):
        code = None
        try:
            code = DatagramIterator(di.getDatagram(), di.getCurrentIndex()).getUint16()
        except Exception:
            pass
        got['kicked'] = code
        H.ev('KICKED', code=code)
        return orig(di)
    cr.handleGoGetLost = ggl

    last = {}

    def note(leg):
        now = (la.getGameState(), H.area())
        if now != last.get('s'):
            last['s'] = now
            H.ev('state', leg=leg, gs=now[0], area=now[1], pos=H.P(la))

    def watch(leg, cond, secs, step=0.25):
        t0 = time.time()
        while time.time() - t0 < secs:
            note(leg)
            if 'kicked' in got:
                return False
            if cond():
                return True
            yield step
        return cond()

    def where():
        return dict(gs=la.getGameState(), area=H.area(), here=sailing.hereUid(H), pos=H.P(la))

    def island(uid):
        try:
            return cr.getDo(cr.uidMgr.getDoId(uid))
        except Exception:
            return None

    def mine():
        ids = {la.doId}
        for a in ('inventoryId', 'shipId', 'activeShipId'):
            v = getattr(la, a, None)
            if isinstance(v, int):
                ids.add(v)
        return ids

    def townfolk(pr):
        return [o for o in list(cr.doId2do.values()) if cls(o) == 'DistributedNPCTownfolk' and pr is not None
                and getattr(o, 'parentId', None) == pr.doId]

    def onIsland(uid):
        return sailing.hereUid(H) == uid and la.getGameState() == 'LandRoam'

    def tp(leg, uid):
        """Generator: the game's own teleport to an island's open ground -> True when standing there."""
        if onIsland(uid):
            return True
        H.mw('areaTeleport %s' % uid)
        return (yield from watch(leg, lambda: onIsland(uid), 90))

    yield ('until', lambda: la.getGameState() in ('LandRoam', 'ShipPilot', 'WaterRoam'), 60, 'LandRoam')
    H.ev('NPCLEAVE-START', goneSecs=GONE_SECS, watch=WATCH, back=BACK, **where())

    # 1. on Port Royal, with its town NPCs loaded
    if not (yield from tp('pr', PR)):
        H.ev('FAIL', why='could not get to Port Royal at the start', kicked=got.get('kicked'), **where()); return
    pr = island(PR)
    prId = getattr(pr, 'doId', None)
    H.ev('pr-ready', portRoyal=prId, **where())
    yield from watch('pr', lambda: len(townfolk(island(PR))) > 0, 30)
    yield 5                                          # let the rest of the near cells fill in
    myIds = mine()
    snap = prObjects(cr, prId, myIds)
    folk = townfolk(pr)
    H.ev('pr-seen', n=len(snap), byClass=byClass(snap), townfolk=len(folk),
         npcs=sorted(set(filter(None, (name(o) for o in folk))))[:20])
    if not folk:
        H.ev('FAIL', why='no town NPC in sight on Port Royal, nothing to check', n=len(snap), **where()); return

    # 2. teleport to Tortuga
    t0 = time.time()
    H.mw('areaTeleport %s' % TORTUGA)
    if (yield from watch('out', lambda: la.getGameState() == 'TeleportOut' or sailing.hereUid(H) != PR, 30)):
        H.ev('tele-out', secs=round(time.time() - t0, 1), stillHere=len([k for k in snap if k in cr.doId2do]))
    if not (yield from watch('out', lambda: onIsland(TORTUGA), 90)):
        H.ev('FAIL', why='could not get to Tortuga', kicked=got.get('kicked'), **where()); return
    t1 = time.time()
    H.ev('landed', secs=round(t1 - t0, 1), **where())

    # 3. watch Port Royal's objects leave
    def left():
        return [k for k in snap if k in cr.doId2do]
    n = len(left())
    H.ev('pr-left', left=n, gone=len(snap) - n, secs=0.0)
    goneAt = None
    while time.time() - t1 < WATCH:
        note('watch')
        if 'kicked' in got:
            break
        k = len(left())
        if k != n:
            n = k
            H.ev('pr-left', left=n, gone=len(snap) - n, secs=round(time.time() - t1, 1))
        if n == 0:
            goneAt = round(time.time() - t1, 1)
            H.ev('pr-gone', secs=goneAt)
            break
        yield 1.0
    rest = left()
    if rest:
        from direct.distributed.DoInterestManager import DoInterestManager
        pr = island(PR)
        held = [dict(handle=h, desc=getattr(st, 'desc', None), zones=getattr(st, 'zoneIdList', None))
                for h, st in getattr(DoInterestManager, '_interests', {}).items()
                if getattr(st, 'parentId', None) == prId]
        for k in rest[:15]:
            o = cr.doId2do.get(k)
            H.ev('npc-still-seen', doId=k, cls=cls(o), name=name(o), zone=getattr(o, 'zoneId', None),
                 parent=getattr(o, 'parentId', None))
        H.ev('npc-still-seen-sum', left=len(rest), byClass=byClass({k: cr.doId2do[k] for k in rest if k in cr.doId2do}),
             portRoyal=prId, prSeen=pr is not None, prGridView=getattr(pr, 'gridVisContext', None),
             prOn=getattr(pr, '_onOffState', None), clientInterestsOnPR=held, **where())
    if 'kicked' in got:
        H.ev('FAIL', why='kicked', kicked=got['kicked'], **where()); return
    if goneAt is None or goneAt > GONE_SECS:
        H.ev('FAIL', why='%d of %d Port Royal objects still in the client %ss after landing on Tortuga'
             % (len(rest), len(snap), round(time.time() - t1)), goneAt=goneAt, **where()); return

    # 4. optional: back to Port Royal, its town NPCs must come again
    if BACK:
        t2 = time.time()
        if not (yield from tp('back', PR)):
            H.ev('FAIL', why='could not get back to Port Royal', kicked=got.get('kicked'), **where()); return
        ok = yield from watch('back', lambda: len(townfolk(island(PR))) > 0, 30)
        H.ev('pr-back', folk=len(townfolk(island(PR))), secs=round(time.time() - t2, 1))
        if not ok:
            H.ev('FAIL', why='back on Port Royal but no town NPC came in 30 s', **where()); return
    H.ev('PASS', what="Port Royal's objects left the client after the teleport to Tortuga", n=len(snap),
         goneSecs=goneAt, back=BACK)
