"""Stray quest-beam census at Port Royal: count render.findAllMatches('**/QuestIndicatorParticleDummy;+s+h') (plus the
skyBeam geoms) before a quest step changes, right after, and after a short real walk. The step change is the game's own
quest completion (skipQuest -> QuestManagerAI.completeQuest -> the next quest is handed out). Logs, per dummy: position,
hidden / stashed, parent name, distance to the pirate, whether it is the current indicator target. Always PASS (hard stop)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
from panda3d.core import Filename, Vec3

TAG = os.environ.get('BEAM_TAG', 'beams')
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])), 'shots', 'bulbs')


def count(H, label):
    R, la = H.render, H.la
    cur = None
    try:
        ind = getattr(la, 'questIndicator', None)
        node = getattr(ind, 'indicatorNode', None) if ind else None
        if node is not None:
            cur = [round(v) for v in node.getPos(R)]
    except Exception as e:
        cur = 'err ' + repr(e)
    out = []
    for np in R.findAllMatches('**/QuestIndicatorParticleDummy;+s+h'):
        p = np.getPos(R)
        out.append(dict(pos=[round(v) for v in p], hidden=bool(np.isHidden()), stashed=bool(np.isStashed()),
                        parent=np.getParent().getName(), parentIsRender=(np.getParent() == R),
                        nearOrigin=bool(abs(p[0]) < 5 and abs(p[1]) < 5), distToPirate=round((p - la.getPos(R)).length()),
                        isCurrent=(isinstance(cur, list) and abs(p[0] - cur[0]) + abs(p[1] - cur[1]) < 6)))
    sky = 0
    for g in R.findAllMatches('**/+GeomNode'):
        q = g
        while not q.isEmpty() and q != R:
            if 'skyBeam' in q.getName():
                sky += 1
                break
            q = q.getParent()
    qs = getattr(la, 'questStep', None)
    shown = sum(1 for d in out if not d['hidden'] and not d['stashed'])
    H.ev('beam-count', label=label, total=len(out), shown=shown, onRender=sum(1 for d in out if d['parentIsRender']),
         nearOrigin=sum(1 for d in out if d['nearOrigin']), skyBeamGeoms=sky, currentIndicator=cur, dummies=out,
         qids=list(H.qids()), qstep=repr(qs) if qs else None, area=H.area())
    try:
        os.makedirs(OUTDIR, exist_ok=True)
        H.B.win.saveScreenshot(Filename.fromOsSpecific(os.path.join(OUTDIR, '%s-%s.png' % (TAG, label))))
    except Exception:
        pass
    return len(out), shown


def run(H):
    la, R = H.la, H.render
    T0 = time.time()
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    yield 8
    res = {}
    try:
        res['before'] = count(H, '1-before')
        if not H.qids():
            H.mw('giveQuest c2_visit_will_turner')
            yield 4
        H.mw('skipQuest')           # the game's own quest completion: the step changes, the next quest arrives
        yield 4
        res['after4s'] = count(H, '2-after-4s')
        yield 8
        res['after12s'] = count(H, '3-after-12s')
        p0 = la.getPos(R)
        fwd = R.getRelativeVector(la, Vec3(0, 1, 0))
        fwd.setZ(0)
        fwd.normalize()
        ok = yield from H.walk_to(p0 + fwd * 25, ref=R, arrive=2.0, tag='beam-walk', timeout=30)
        yield 3
        res['afterWalk'] = count(H, '4-after-walk')
        H.mw('skipQuest')           # a second step change
        yield 8
        res['after2nd'] = count(H, '5-after-2nd-step')
    except Exception as e:
        H.ev('beam-error', err=repr(e))
    H.ev('beam-summary', secs=round(time.time() - T0), res={k: list(v) for k, v in res.items()})
    H.ev('PASS', note='beam census done')
