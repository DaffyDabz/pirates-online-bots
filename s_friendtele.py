"""Teleport to a friend on land (11-16): the server looked for the main world by an empty name and found none, a friend
the client can't see was asked through a handle that went nowhere, a refusal never reached the pirate (his teleport
lock stayed set), and he would have landed at the island's spawn point, not by his friend (server-tree patch 0048
fixes all four). Two pirates at once is not allowed on this PC, so a town NPC on Port Royal stands in for the friend:
the server's friend check takes any object in this district on land in the main world, and an NPC has no teleport
flags, so it always says yes. This script, from Port Royal:
  leg R, refused: asks to teleport to a pirate who is not there (doId 1, the friend-list path for one the client can't
    see). The server refuses; he must not leave, his teleport lock must clear, and the game must say why.
  leg S, same island: asks the server for the NPC while on its island. The server answers "already here"; same checks.
  leg F, the friend: teleports to Tortuga, then asks to teleport to the NPC on Port Royal (one the client can't see now,
    so it goes straight to the server). He must leave, land on Port Royal within NEAR ft of the NPC, and hold HOLD s
    there with no kick.
Events: FRIENDTELE-START, state (each game state / area change), friend (the NPC picked), warning (each on-screen
warning), ask, refused-ok, tele-out, landed, hold, leg-pass, then PASS or FAIL. The run's walk-X.err must also hold 0
tracebacks, and the AI log 0 'Cannot initiate teleport' and one 'Teleporting avatar ... to friend' line with a spawn.
env: FRIENDTELE_HOLD (default 60 s on the island), FRIENDTELE_NEAR (default 12 ft), FRIENDTELE_LEGS (default RSF)."""
import math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402
from s_dock import cls   # noqa: E402

PR = '1150922126.8dzlu'
TORTUGA = '1156207188.95dzlu'
NAMES = {PR: 'Port Royal', TORTUGA: 'Tortuga'}
HOLD = float(os.environ.get('FRIENDTELE_HOLD', '60'))
NEAR = float(os.environ.get('FRIENDTELE_NEAR', '12'))
LEGS = os.environ.get('FRIENDTELE_LEGS', 'RSF').upper()
NOBODY = 1   # a doId no object has


def run(H):
    from panda3d.core import DatagramIterator, Point3
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

    # every on-screen warning (the refusal's reason shows as one)
    warnings = []
    origWarn = la.guiMgr.createWarning

    def warn(msg, *a, **k):
        warnings.append(msg)
        H.ev('warning', msg=msg)
        return origWarn(msg, *a, **k)
    la.guiMgr.createWarning = warn

    last = {}

    def note(leg):
        # one event each time the game state or the area changes (TeleportOut, the teleport zone, TeleportIn...)
        now = (la.getGameState(), H.area())
        if now != last.get('s'):
            last['s'] = now
            H.ev('state', leg=leg, gs=now[0], area=now[1], pos=H.P(la))

    def watch(leg, cond, secs):
        """Generator: poll cond every 0.25 s for secs, noting state changes. -> True when it held."""
        t0 = time.time()
        while time.time() - t0 < secs:
            note(leg)
            if 'kicked' in got:
                return False
            if cond():
                return True
            yield 0.25
        return cond()

    def inTele():
        try:
            return bool(cr.teleportMgr.amInTeleport())
        except Exception:
            return None

    def where():
        return dict(gs=la.getGameState(), area=H.area(), here=sailing.hereUid(H), inTeleport=inTele(), pos=H.P(la))

    def island(uid):
        return cr.getDo(cr.uidMgr.getDoId(uid))

    def flat(a, b):
        pa, pb = a.getPos(render), b.getPos(render)
        return math.hypot(pa[0] - pb[0], pa[1] - pb[1])

    def toPR(leg):
        """Generator: the game's own teleport to Port Royal's open ground. -> True when standing there."""
        if sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam':
            return True
        H.mw('areaTeleport %s' % PR)
        ok = yield from watch(leg, lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90)
        yield 5
        return ok

    yield ('until', lambda: la.getGameState() in ('LandRoam', 'ShipPilot', 'WaterRoam'), 60, 'LandRoam')
    H.ev('FRIENDTELE-START', legs=LEGS, hold=HOLD, near=NEAR, **where())
    if not (yield from toPR('start')):
        H.ev('FAIL', why='could not get to Port Royal at the start', kicked=got.get('kicked'), **where()); return
    spawnPos = la.getPos(render)

    # the stand-in: the town NPC on Port Royal's open ground farthest from where we stand, so landing beside him is
    # told apart from landing at the island's spawn point
    def townfolk():
        pr = island(PR)
        return [o for o in list(cr.doId2do.values()) if cls(o) == 'DistributedNPCTownfolk' and pr is not None
                and o.getParentObj() is pr and not o.isEmpty()]
    yield from watch('start', lambda: len(townfolk()) > 0, 30)
    folk = townfolk()
    if not folk:
        H.ev('FAIL', why='no town NPC in sight on Port Royal to stand in for the friend', **where()); return
    npc = max(folk, key=lambda o: flat(o, la))
    npcId = npc.doId
    npcName = npc.getName() if hasattr(npc, 'getName') else None
    npcFromSpawn = round(flat(npc, la), 1)
    H.ev('friend', npc=npcId, npcName=npcName, pos=H.P(npc), fromSpawn=npcFromSpawn, seen=len(folk),
         weak=npcFromSpawn < NEAR + 10)

    def refusedLeg(leg, ask, wantText):
        """Generator: ask, then: no TeleportOut, the teleport lock clears, a warning says why. -> None, or why it failed."""
        n = len(warnings)
        before = sailing.hereUid(H)
        ask()
        H.ev('ask', leg=leg, **where())
        left = yield from watch(leg, lambda: la.getGameState() == 'TeleportOut', 8)
        if 'kicked' in got:
            return 'kicked'
        if left:
            return 'he left (TeleportOut) on a teleport the server should refuse'
        if not (yield from watch(leg, lambda: inTele() is False, 5)):
            return 'his teleport lock stayed set after the refusal (the old bug)'
        said = warnings[n:]
        if not said:
            return 'no warning said why he could not teleport'
        if wantText and not any(wantText in m for m in said):
            return 'the warning was not the expected one (want %r)' % wantText
        if sailing.hereUid(H) != before or la.getGameState() != 'LandRoam':
            return 'he moved off the island'
        H.ev('refused-ok', leg=leg, said=said, **where())
        return None

    results = {}
    for leg in LEGS:
        if leg == 'R':
            # the friend-list path for one the client can't see (doId 1 is in nobody's doId2do)
            why = yield from refusedLeg(leg, lambda: cr.teleportMgr.queryAvatarForTeleport(NOBODY), None)
            results[leg] = why or 'refused, lock cleared'
        elif leg == 'S':
            # the NPC is in sight here; a real friend in sight answers through his own client first, then his client
            # asks the server exactly this (an NPC has no client to answer, so ask the server directly)
            if npcId not in cr.doId2do:
                yield from toPR(leg)
            why = yield from refusedLeg(leg, lambda: cr.teleportMgr.requestTeleportToAvatar(
                cr.distributedDistrict.doId, 0, npcId, 0), 'already here')
            results[leg] = why or 'already here, lock cleared'
        elif leg == 'F':
            H.mw('areaTeleport %s' % TORTUGA)
            if not (yield from watch(leg, lambda: sailing.hereUid(H) == TORTUGA and la.getGameState() == 'LandRoam', 90)):
                H.ev('FAIL', leg=leg, why='could not get to Tortuga', kicked=got.get('kicked'), **where()); return
            yield 5
            # out of sight now, so the friend-list path goes straight to the server
            yield from watch(leg, lambda: npcId not in cr.doId2do, 20)
            stillSeen = npcId in cr.doId2do
            if stillSeen:
                # FRIENDTELE3: Port Royal's town NPC stayed in the client 25 s after landing on Tortuga. Its cell
                # should close on both sides (the island's grid view at turnOff, the server's per-cell interests at
                # handleChildLeave), so this is a finding of its own, not the friend teleport's verdict: log who
                # holds the cell open, then ask the server for him directly, as leg S does
                from direct.distributed.DoInterestManager import DoInterestManager
                o, pr = cr.doId2do.get(npcId), island(PR)
                prId = getattr(pr, 'doId', None)
                held = [dict(handle=h, desc=getattr(st, 'desc', None), zones=getattr(st, 'zoneIdList', None))
                        for h, st in getattr(DoInterestManager, '_interests', {}).items()
                        if getattr(st, 'parentId', None) == prId]
                H.ev('npc-still-seen', leg=leg, npc=npcId, zone=getattr(o, 'zoneId', None),
                     parent=getattr(o, 'parentId', None), portRoyal=prId, prSeen=pr is not None,
                     prGridView=getattr(pr, 'gridVisContext', None), prOn=getattr(pr, '_onOffState', None),
                     clientInterestsOnPR=held, **where())
            t0 = time.time()
            H.ev('ask', leg=leg, npc=npcId, how='server' if stillSeen else 'friend-list', **where())
            if stillSeen:
                cr.teleportMgr.requestTeleportToAvatar(cr.distributedDistrict.doId, 0, npcId, 0)
            else:
                cr.teleportMgr.queryAvatarForTeleport(npcId)
            if not (yield from watch(leg, lambda: la.getGameState() == 'TeleportOut', 30)):
                H.ev('FAIL', leg=leg, why='the teleport never started (no TeleportOut in 30 s); see ai.log "Cannot '
                     'teleport avatar" / "Cannot initiate teleport"', warnings=warnings[-3:], kicked=got.get('kicked'),
                     **where()); return
            H.ev('tele-out', leg=leg, secs=round(time.time() - t0, 1))
            if not (yield from watch(leg, lambda: sailing.hereUid(H) and la.getGameState() == 'LandRoam', 120)):
                H.ev('FAIL', leg=leg, why='did not land on an island in 120 s', kicked=got.get('kicked'), **where()); return
            if sailing.hereUid(H) != PR:
                H.ev('FAIL', leg=leg, why='landed on the wrong island', got=NAMES.get(sailing.hereUid(H)), **where())
                return
            yield from watch(leg, lambda: npcId in cr.doId2do, 15)
            friend = cr.doId2do.get(npcId)
            if friend is None:
                H.ev('FAIL', leg=leg, why='landed on Port Royal but the NPC is not in sight (far from him)', **where())
                return
            dist = round(flat(friend, la), 1)
            rel = la.getRelativePoint(friend, Point3(0, 0, 0))
            facing = round(math.degrees(math.atan2(rel[0], rel[1])))     # 0 = looking straight at him
            fromSpawn = round(math.hypot(la.getX(render) - spawnPos[0], la.getY(render) - spawnPos[1]), 1)
            H.ev('landed', leg=leg, secs=round(time.time() - t0, 1), fromFriend=dist, facing=facing,
                 fromIslandSpawn=fromSpawn, friendPos=H.P(friend), **where())
            if dist > NEAR:
                H.ev('FAIL', leg=leg, why='landed %s ft from the friend (want <= %s): the island spawn point, not by him'
                     % (dist, NEAR), **where()); return
            t1 = time.time()
            while time.time() - t1 < HOLD:
                yield from watch(leg, lambda: 'kicked' in got or sailing.hereUid(H) != PR, 10)
                bad = 'kicked' in got or sailing.hereUid(H) != PR
                H.ev('hold', leg=leg, secs=round(time.time() - t1), **where())
                if bad:
                    H.ev('FAIL', leg=leg, why='kicked or moved off the island during the hold', kicked=got.get('kicked'),
                         **where()); return
            if inTele():
                H.ev('FAIL', leg=leg, why='his teleport lock is still set after landing', **where()); return
            results[leg] = 'landed %s ft from the friend, facing %s deg' % (dist, facing)
        else:
            continue
        if leg in 'RS' and results[leg] not in ('refused, lock cleared', 'already here, lock cleared'):
            H.ev('FAIL', leg=leg, why=results[leg], warnings=warnings[-3:], kicked=got.get('kicked'), **where()); return
        H.ev('leg-pass', leg=leg, result=results[leg], **where())
        yield 3
    if not results:
        H.ev('FAIL', why='no leg ran', legs=LEGS); return
    H.ev('PASS', what='teleport to a friend: refused cleanly with a reason, and landed beside him on his island',
         legs=results, friend=npcId, hold=HOLD)
