QID = 'c2_visit_tia_dalma'
JUNGLE = '1161798288.34sdnaik'
PR = '1150922126.8dzlu'
TIA = '1154497344.0jubutlerPR'


def tia(H):
    d = H.cr.uidMgr.uid2doId.get(TIA)
    return H.cr.doId2do.get(d) if d else None


def tunnel_to(H, dest):
    tun = next((o for o in H.cr.doId2do.values() if type(o).__name__ == 'DistributedGATunnel' and dest in list(o.areaUid)), None)
    if tun is None:
        H.ev('no-tunnel', dest=dest)
        return False
    idx = 1 - list(tun.areaUid).index(dest)
    H.la.setPos(H.render, tun.getPos(H.render))
    tun._DistributedGATunnel__handleOnFloor(idx, None)
    H.ev('enter-tunnel', tunnel=tun.doId, dest=dest)
    return True


def info(H, tag):
    t = tia(H)
    if t is None:
        H.ev('tia-info', tag=tag, present=False)
        return
    try:
        names = t.getAnimNames()
    except Exception as e:
        names = 'err %s' % e
    parts = None
    try:
        parts = t.getPartNames()
    except Exception:
        pass
    H.ev('tia-info', tag=tag, anim=H.curAnim(t), names=names, parts=parts, animSet=getattr(t, 'animSet', None),
         castDnaId=getattr(t, 'castDnaId', None), state=getattr(t, 'state', None), interactAnim=getattr(t, 'interactAnim', None),
         animIval=repr(getattr(t, 'animIval', None))[:80], lockFSM=getattr(t, 'lockFSM', None),
         cls=[c.__name__ for c in type(t).__mro__][:8], lods=(t.getLODNames() if hasattr(t, 'getLODNames') else None),
         animControls=[(str(a.getAnim().getName()) if a.getAnim() else None, a.isPlaying()) for a in t.getAnimControls()][:10] if hasattr(t, 'getAnimControls') else None)


def run(H):
    H.snap('initial')
    if not H.has(QID):
        H.mw('giveQuest %s' % QID)
        yield ('until', lambda: H.has(QID), 15, 'give ' + QID)
    if H.area()[1] != PR and H.area()[1] != JUNGLE:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: H.area()[1] == PR and H.la.getGameState() == 'LandRoam', 60, 'tp PR')
        yield 6
    H.ev('step-tia', **H.step())
    if H.area()[1] == PR:
        tunnel_to(H, JUNGLE)
    yield ('until', lambda: tia(H) is not None, 40, 'tia generated')
    for k in range(6):
        info(H, 'arrive+%d' % k)
        yield 0.5
    for i in range(60):
        t = tia(H)
        H.ev('tia', i=i, anim=None if t is None else H.curAnim(t), gs=H.la.getGameState(),
             q=[(q['id'], q['complete']) for q in H.quests()], dialogs=len(H.dialogs))
        if not H.has(QID) and i > 2:
            break
        yield 5
    yield 5
    t = tia(H)
    info(H, 'final')
    H.ev('TIA-FINAL', anim=None if t is None else H.curAnim(t), hidden=None if t is None else t.isHidden())
    H.animCheck('tia-final')
    H.snap('tia-end')
