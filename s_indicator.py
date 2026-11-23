"""Quest indicator check: the arrow at the pirate's feet that points at the quest target (LocalPirate.questArrow, a
billboard turned towards the indicator node) and the light beam on the target (QuestIndicatorEffect: skyBeam sprite
particles on the indicator node). Host 11-16: "make sure the visual indicator works, pointing and shining a light on
the quest location".
At Port Royal with the active quest's step shown:
  1 as the game leaves it: ind-state (arrow, mutes, tutorial level, the beam's nodes and live particle counts, where
    the target sits on screen), turn to face the target, shot <tag>-1-far.png
  2 IND_FORCE=1 only (diagnosis): clear the mutes, build the arrow past the tutorial gate, show the beam, shot 2
  3 walk towards the target until inside the near radius (150 ft), ind-state again, shot 3; does the beam show in the
    frame (ind-seen, report only); the beam lit with the NPC not loaded yet (ind-unloaded)
  4 walk round to 45 ft in front of the NPC, shot 4 (ind-front, report only)
Shots go to shots/indicator/. PASS when IND_STRICT=0 (default): every phase logged and shot (the goal is the data).
IND_STRICT=1 (the proof): PASS only when, at far and near, the arrow is shown and aimed within 15 deg of the target
and the beam on the target has live particles inside the camera view, and a spare beam cleaned up the way a finished
quest step cleans it up leaves no glow behind (ind-cleanup).
env: IND_TAG (default 'diag'), IND_FORCE (0), IND_STRICT (0), IND_GIVE (quest id, '')."""
import os, sys, math

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
from panda3d.core import Filename, Point3, Point2, BillboardEffect   # noqa: E402
import sailing, paths   # noqa: E402

PR = '1150922126.8dzlu'
TAG = os.environ.get('IND_TAG', 'diag')
FORCE = os.environ.get('IND_FORCE', '0') == '1'
STRICT = os.environ.get('IND_STRICT', '0') == '1'
GIVE = os.environ.get('IND_GIVE', '')       # give this quest first when none is held (test setup, logged)
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])), 'shots', 'indicator')
AIM = 15.0
NEAR = 150.0


def bearing(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def adiff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def nodes(H):
    qi = getattr(H.la, 'questIndicator', None)
    node = getattr(qi, 'indicatorNode', None) if qi else None
    return qi, node


def on_screen(H, np_):
    """(x, y) in -1..1 when np_ is in front of the camera and inside the view, else None."""
    B = H.B
    p = B.cam.getRelativePoint(np_, Point3(0, 0, 0))
    s = Point2()
    if p[1] > 0 and B.camLens.project(p, s) and abs(s[0]) <= 1 and abs(s[1]) <= 1:
        return [round(s[0], 2), round(s[1], 2)]
    return None


def effect_state(H, e):
    R = H.render
    d = {'empty': e.isEmpty()}
    if e.isEmpty():
        return d
    pd = e.particleDummy
    d.update(parent=str(e.getParent()), hidden=e.isHidden(), stashed=e.isStashed(), scale=round(e.getScale(R)[0], 2),
             pdParent=str(pd.getParent()), pdHidden=pd.isHidden(), pdStashed=pd.isStashed(), pdPos=H.P(pd),
             pdScale=round(pd.getScale(R)[0], 2) if not pd.isEmpty() else None,
             playing=bool(e.startEffect and e.startEffect.isPlaying()) if getattr(e, 'startEffect', None) else None,
             live=[e.p0.getLivingParticles(), e.p1.getLivingParticles()], screen=on_screen(H, pd) if not pd.isEmpty() else None)
    return d


def state(H, phase):
    la, R, B = H.la, H.render, H.B
    qi, node = nodes(H)
    arrow = getattr(la, 'questArrow', None)
    p = la.getPos(R)
    d = {'phase': phase, 'tut': la.style.getTutorial(), 'noQuestArrow': getattr(la, 'noQuestArrow', None),
         'gs': la.getGameState(), 'active': la.activeQuestId, 'step': repr(la.questStep) if la.questStep else None,
         'qiMuted': getattr(qi, 'muted', None), 'particles': getattr(B, 'particleMgrEnabled', None), 'la': H.P(la)}
    try:                                     # the world-map quest dart (needs the step's island uid from the server)
        d['island'] = la.questStep.getIsland() if la.questStep else None
        d['dart'] = bool(la.guiMgr.mapPage.worldMap.mapBall.questDartPlaced)
    except Exception as e:
        d['dart'] = 'err %s' % e
    # every beam in the world, not just the current one: a beam left at an old quest target is a stray "light bulb"
    d['beams'] = [{'pos': H.P(x), 'shown': not x.isHidden() and not x.isStashed()}
                  for x in R.findAllMatches('**/QuestIndicatorParticleDummy;+s')]
    if node is not None and not node.isEmpty():
        np_ = node.getPos(R)
        d['node'] = {'cls': type(node).__name__, 'fsm': node.state, 'muted': node.muted, 'pos': H.P(node),
                     'dist': round(paths.dist(p, np_), 1), 'parent': str(node.getParent()),
                     'stepObj': type(getattr(node, 'stepObj', None)).__name__, 'screen': on_screen(H, node)}
        for k in ('farEffect', 'nearEffect'):
            e = getattr(node, k, None)
            if e is not None:
                d[k] = effect_state(H, e)
    if arrow is not None and not arrow.isEmpty():
        a = {'stashed': arrow.isStashed(), 'hidden': arrow.isHidden(), 'parent': str(arrow.getParent())}
        bb = arrow.getEffect(BillboardEffect.getClassType())
        if bb is not None:
            look = bb.getLookAt()
            a['lookAt'] = str(look)
            if not look.isEmpty() and node is not None and not node.isEmpty():
                lp, tp = look.getPos(R), node.getPos(R)
                a['aimErr'] = round(adiff(bearing(p, lp), bearing(p, tp)), 1)
        d['arrow'] = a
    else:
        d['arrow'] = None
    H.ev('ind-state', **d)
    return d


def good(d):
    a, fe, ne = d.get('arrow'), d.get('farEffect'), d.get('nearEffect')
    arrow_ok = bool(a) and not a['stashed'] and not a['hidden'] and a.get('aimErr') is not None and a['aimErr'] <= AIM
    beams = [e for e in (fe, ne) if e and not e['empty']]
    beam_ok = any(not e['stashed'] and not e['pdStashed'] and not e['pdHidden'] and sum(e['live']) > 0 and e['screen']
                  for e in beams)
    return arrow_ok, beam_ok


def cleanup_check(H):
    """A spare beam from the pool, lit 20 ft in front of the pirate the way an NPC's near beam is (dummy on the
    target), then cleaned up the way a finished quest step cleans it up (reallyCleanUpEffect). Before the 15:22 fix
    the foot glow (p1) kept emitting and the dummy stayed on the target: a stray glow. True when nothing is left."""
    from pirates.effects.QuestIndicatorEffect import QuestIndicatorEffect
    la, R = H.la, H.render
    spot = R.attachNewNode('ind-cleanup-target')
    spot.setPos(la, 0, 20, 0)
    e = QuestIndicatorEffect.getEffect()
    e.setWantBottomEffect(True)
    e.startLoop()
    e.particleDummy.reparentTo(spot)
    e.reparentTo(spot)
    yield 3
    lit = [e.p0.getLivingParticles(), e.p1.getLivingParticles()]
    e.reallyCleanUpEffect()
    yield 2
    left = {'lit': lit, 'pdInWorld': e.particleDummy.hasParent() and not e.particleDummy.getParent().isEmpty(),
            'pdParent': str(e.particleDummy.getParent()), 'p1On': bool(e.p1.isEnabled()), 'p0On': bool(e.p0.isEnabled()),
            'p1Live': e.p1.getLivingParticles(), 'underSpot': spot.getNumChildren()}
    spot.removeNode()
    ok = sum(lit) > 0 and not left['pdInWorld'] and not left['p1On'] and not left['p0On']
    H.ev('ind-cleanup', ok=ok, **left)
    return ok


def shot(H, name):
    os.makedirs(OUTDIR, exist_ok=True)
    f = os.path.join(OUTDIR, '%s-%s.png' % (TAG, name))
    ok = H.B.win.saveScreenshot(Filename.fromOsSpecific(f))
    H.ev('ind-shot', shot=name, file=f, ok=bool(ok))
    return f


def frame(H):
    from panda3d.core import PNMImage
    img = PNMImage()
    H.B.win.getScreenshot(img)
    return img


def seen(H, node):
    """Does the beam show in the rendered frame, or is it behind a wall or the pirate? Frames with the beam shown and
    stashed, compared in a box round its foot and up its column: pixels brighter with the beam. Report only."""
    e = getattr(node, 'nearEffect', None) or getattr(node, 'farEffect', None)
    if e is None or e.isEmpty() or not e.particleDummy.hasParent():
        return {'seen': False, 'why': 'no beam'}
    s = on_screen(H, e.particleDummy)
    if not s:
        return {'seen': False, 'why': 'off screen'}
    a = frame(H)
    e.hideEffect()
    yield 2
    b = frame(H)
    e.showEffect()
    W, Hh = a.getXSize(), a.getYSize()
    cx, cy = int((s[0] + 1) / 2 * W), int((1 - s[1]) / 2 * Hh)
    lit = 0
    for y in range(max(0, cy - 500), min(Hh, cy + 80), 2):
        for x in range(max(0, cx - 150), min(W, cx + 150), 2):
            if a.getBright(x, y) - b.getBright(x, y) > 0.15:
                lit += 1
    return {'seen': lit >= 40, 'litPx': lit * 4, 'foot': [cx, cy]}


def unloaded_check(H, node):
    """The case patch 0024 fixes: the pirate inside the near radius before the quest NPC has loaded (stepObj None).
    The near beam must stand on the indicator node, not under render at the world origin. Lit with stepObj cleared,
    then lit again on the NPC."""
    R, so = H.render, node.stepObj
    ok, d = False, {}
    node.stepObj = None
    try:
        node.startNearEffect()
        yield 2
        e = node.nearEffect
        pd = e.particleDummy
        d = {'parent': str(e.getParent()), 'pdParent': str(pd.getParent()), 'pdPos': H.P(pd), 'nodePos': H.P(node),
             'live': [e.p0.getLivingParticles(), e.p1.getLivingParticles()]}
        ok = e.getParent() == node and pd.getParent() == node and paths.dist(pd.getPos(R), node.getPos(R)) < 1.0
    finally:
        node.stepObj = so
        if node.state == 'Near':
            node.startNearEffect()
    H.ev('ind-unloaded', ok=ok, **d)
    return ok


def front_shot(H, node):
    """A shot from in front of the quest NPC, 45 ft out along its heading, the way a player walks up to it (from the
    first near stop the NPC can stand behind its counter, the beam hidden)."""
    R, so = H.render, getattr(node, 'stepObj', None)
    if so is None or so.isEmpty():
        H.ev('ind-front', ok=False, why='no NPC'); return
    f = so.getQuat(R).getForward()
    tp = so.getPos(R)
    g = (tp[0] + f[0] * 45.0, tp[1] + f[1] * 45.0, tp[2])
    reached = yield from paths.walk_route(H, [g], 8.0, 0.0, tag='to-front', max_goals=1)
    yield 3
    yield from H.face(node, tag='face target front')
    yield 3
    d = yield from seen(H, node)
    H.ev('ind-front', ok=reached is not None, dist=round(paths.dist(H.la.getPos(R), tp), 1), fsm=node.state, **d)
    shot(H, '4-front')


def run(H):
    la, R = H.la, H.render
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if sailing.hereUid(H) != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
    if GIVE and not H.qids():
        # test setup: the c2.9 reset leaves no quest held, so the quest the proof aims at is given and tracked
        H.mw('giveQuest %s' % GIVE)
        yield ('until', lambda: H.has(GIVE), 20, 'give quest')
        import s_orders
        s_orders.track(H, GIVE)
        H.ev('SETUP-GIVE', quest=GIVE, held=H.qids(), active=la.activeQuestId)
        yield 4
    yield ('until', lambda: nodes(H)[1] is not None and not nodes(H)[1].isEmpty(), 30, 'quest indicator node')
    qi, node = nodes(H)
    if node is None:
        H.ev('FAIL', why='no quest indicator node', active=la.activeQuestId, step=repr(la.questStep)); return
    yield 4                                  # the beam's start sequence and first particles
    results = {}
    ok = yield from H.face(node, tag='face target')
    yield 3
    results['far'] = state(H, 'far')
    results['far']['faced'] = ok
    shot(H, '1-far')
    if FORCE:
        from pirates.piratesbase import PiratesGlobals
        la.noQuestArrow = False
        old = PiratesGlobals.TUT_GOT_PISTOL
        PiratesGlobals.TUT_GOT_PISTOL = 1 << 30
        try:
            qi, node = nodes(H)
            la.enableQuestArrow(getattr(node, 'stepObj', None) or node)
        finally:
            PiratesGlobals.TUT_GOT_PISTOL = old
        la.showQuestArrow()
        qi.showEffect()
        e = getattr(node, 'farEffect', None)
        if e is not None:
            e.showEffect()
        H.ev('ind-force', arrow=getattr(la, 'questArrow', None) is not None)
        yield 4
        results['forced'] = state(H, 'forced')
        shot(H, '2-forced')
    qi, node = nodes(H)
    tp = node.getPos(R)
    g = (tp[0], tp[1], tp[2])
    if paths.dist(la.getPos(R), g) > NEAR - 30:
        reached = yield from paths.walk_route(H, [g], NEAR - 40, 0.0, tag='to-target', max_goals=1)
        H.ev('ind-walk', reached=reached is not None, dist=round(paths.dist(la.getPos(R), g), 1))
    yield 4
    qi, node = nodes(H)
    if node is not None and not node.isEmpty():
        yield from H.face(node, tag='face target near')
    yield 3
    results['near'] = state(H, 'near')
    # the near state only proves "near" when the pirate really got there (a failed walk left it at the far spot)
    nearDist = round(paths.dist(la.getPos(R), g), 1)
    nearReached = nearDist <= NEAR
    shot(H, '3-near')
    if node is not None and not node.isEmpty():
        H.ev('ind-seen', phase='near', **(yield from seen(H, node)))
        unloaded = yield from unloaded_check(H, node)
        yield from front_shot(H, node)
    else:
        unloaded = False
    glow = yield from cleanup_check(H)
    verdict = {k: good(v) for k, v in results.items()}
    H.ev('ind-verdict', glowCleared=glow, nearDist=nearDist, nearReached=nearReached, unloaded=unloaded,
         **{k: {'arrow': v[0], 'beam': v[1]} for k, v in verdict.items()})
    if not STRICT:
        H.ev('PASS', what='indicator diagnosis logged and shot', verdict={k: list(v) for k, v in verdict.items()})
    elif glow and nearReached and unloaded and all(verdict[k] == (True, True) for k in ('far', 'near')):
        H.ev('PASS', what='arrow aimed and beam lit at far and near, on the quest spot before the NPC loads, no glow '
             'left after cleanup', verdict={k: list(v) for k, v in verdict.items()})
    else:
        H.ev('FAIL', why='arrow or beam missing, near spot not reached, beam off the quest spot before the NPC loads, '
             'or a glow left after cleanup', glowCleared=glow, nearDist=nearDist, unloaded=unloaded,
             verdict={k: list(v) for k, v in verdict.items()})
