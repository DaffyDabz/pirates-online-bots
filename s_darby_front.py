"""Front check: what stands in front of Darby's counter, and which water line lets the planner reach it. TALK1 (11-16)
planned no route from the mansion yard to Darby: the search came down the hill to (-304.3, 62.0) on the west side of his
booth and ran dry 30 ft off. PK2 showed why it may be: the booth is walled west and south, its counter opens north, and
the dirt in front of it lies below z 1.0 (paths.WATER_Z), so the planner reads it as harbour. The game swims only where
the ground is 5 ft under the sea (MotionFSM: avZ + 5 <= waterZ; sea level 0).
At Port Royal (the pirate is put at each spot, logged SETUP-POS, diagnosis only, never in play) it logs:
  df-npc     Darby's position and heading (the way his counter faces)
  df-spot    for spots 6/12/18/26 ft in front of him: where the pirate settles, the sea height there, whether the game
             has it wading, over water or swimming
  df-plan    plans from the west side (where TALK1's search stopped) and from the mansion yard to talk range, with the
             water line at 1.0 (now), -3.0 and -4.0
PASS when everything is logged (the goal is the data)."""
import os, sys, math

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing, paths   # noqa: E402
from s_talk_walk import find, DARBY, YARD, PR   # noqa: E402
from s_story import TALK   # noqa: E402

WEST = (-304.3, 62.0, 1.1)


def water(H):
    la = H.la
    m = getattr(la, 'motionFSM', None)
    try:
        wz = H.cr.getWaterHeight(la)
    except Exception as e:      # noqa: BLE001 - a diagnosis logs what it can
        wz = repr(e)
    return dict(at=H.P(la), ocean=bool(H.cr.isOceanEnabled()), waterZ=wz, gs=la.getGameState(),
                ground=getattr(m, 'groundState', None), inwater=getattr(m, '_MotionFSM__inwater', None),
                over=getattr(m, '_MotionFSM__overwater', None), sub=getattr(m, '_MotionFSM__submerged', None))


def run(H):
    la, R = H.la, H.render
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if sailing.hereUid(H) != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
    first = (DARBY[0], DARBY[1] + 6, 3.5)
    H.ev('SETUP-POS', to=list(first), frm=H.P(la), why='diagnosis: in front of Darby\'s counter')
    la.setPos(R, *first)
    yield ('until', lambda: find(H) is not None, 20, 'Darby in view')
    n = find(H)
    hd = n.getH(R) if n is not None else None
    H.ev('df-npc', at=H.P(n) if n is not None else None, h=hd)
    for d in (6, 12, 18, 26):
        s = (DARBY[0], DARBY[1] + d, 3.5)
        H.ev('SETUP-POS', to=list(s), frm=H.P(la), why='diagnosis: %d ft north of Darby' % d)
        la.setPos(R, *s)
        yield 4
        H.ev('df-spot', ft=d, **water(H))
    la.setPos(R, *first)
    yield 3
    legs_ok, ground = paths.live(H, TALK)
    old = paths.WATER_Z
    try:
        for start, name in ((WEST, 'west'), (YARD, 'yard')):
            for wz in (1.0, -3.0, -4.0):
                paths.WATER_Z = wz
                r, checks = yield from paths.plan_g(start, DARBY, legs_ok, ground, (), TALK)
                if r is None:
                    r, checks = yield from paths.plan_g(start, DARBY, legs_ok, ground, (), TALK,
                                                        margin=paths.WIDE * paths.MARGIN,
                                                        max_expand=paths.WIDE * paths.MAX_EXPAND)
                H.ev('df-plan', frm=name, waterZ=wz, checks=checks,
                     path=[[round(v, 1) for v in w] for w in r] if r else None,
                     length=round(paths.length(start, r), 1) if r else None, search=dict(paths.LAST))
                yield 0
    finally:
        paths.WATER_Z = old
    H.ev('PASS', what='front of Darby\'s counter measured')
