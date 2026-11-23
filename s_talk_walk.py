"""Talk check: the bot walks from the governor's mansion yard down to Darby Drydock and talks to him like a player.
STORY16 (11-16) planned no route there: Darby stands inside his shipwright booth behind the counter, and the bot asked
for a walk to within 5-6 ft of him, which only goes through the counter. s_story now talks from TALK ft (the game's talk
prompt shows inside 12 ft) and the planner leaves unchecked only the last bit the walk never covers.
The pirate is put at the mansion yard (logged SETUP-POS, test setup only), then walks with s_story's own go() (held
keys, planned round the buildings) and asks to talk. PASS when the game accepts the talk (NPCInteract) within 12 ft."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402
from s_story import go, hdist, TALK   # noqa: E402

PR = '1150922126.8dzlu'
YARD = (-261.8, -688.0, 47.0)
DARBY = (-274.3, 57.3, 2.7)
SPHERE = 12.0        # the talk prompt's reach (InteractiveBase sphereScale)


def find(H):
    """Darby's NPC object once he is in interest (the townfolk standing on his spot), else None."""
    from panda3d.core import Point3
    for o in list(H.cr.doId2do.values()):
        if type(o).__name__ == 'DistributedNPCTownfolk' and (o.getPos(H.render) - Point3(*DARBY)).length() < 15:
            return o
    return None


def run(H):
    la, R = H.la, H.render
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if sailing.hereUid(H) != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
    H.ev('SETUP-POS', to=list(YARD), frm=H.P(la), why='test setup: start at the mansion yard as STORY16 did')
    la.setPos(R, *YARD)
    yield 3
    t0 = time.time()
    ok = yield from go(H, DARBY, TALK, False, None, 'to-darby')
    H.ev('walked', ok=ok, left=round(hdist(H, DARBY), 1), secs=round(time.time() - t0), at=H.P(la))
    yield ('until', lambda: find(H) is not None, 20, 'Darby in view')
    n = find(H)
    if n is None:
        H.ev('FAIL', why='Darby never came into view', left=round(hdist(H, DARBY), 1))
        return
    if hdist(H, n) > TALK:
        yield from go(H, n, TALK, True, None, 'to-darby-npc')
    d = round(hdist(H, n), 1)
    H.ev('at-darby', npc=n.doId, npcName=getattr(n, 'name', ''), dist=d, at=H.P(la))
    if d > SPHERE:
        H.ev('FAIL', why='could not get within talking range of Darby', dist=d)
        return
    n.requestInteraction(la.doId)
    yield ('until', lambda: la.getGameState() == 'NPCInteract', 20, 'talk accepted')
    gs = la.getGameState()
    H.ev('PASS' if gs == 'NPCInteract' else 'FAIL', what='walked from the mansion to Darby and talked across the counter',
         dist=d, gs=gs, secs=round(time.time() - t0))
