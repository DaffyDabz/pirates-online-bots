def run(H):
    la = H.la
    R = H.render
    q = 'c2_visit_will_turner'
    if not H.has(q):
        H.mw('giveQuest ' + q)
        yield ('until', lambda: H.has(q), 15, 'give')
    yield 5
    qs = la.questStep
    H.ev('dbg-step', step=repr(qs), hist=H.hist(), qids=H.qids())
    org = H.cr.doId2do.get(qs.getOriginDoId()) if qs else la.getParentObj()
    H.ev('dbg-org', cls=type(org).__name__, uid=getattr(org, 'uniqueId', None), pos=H.P(org), hpr=str(org.getHpr(R)), par=str(la.getParent()), laPar=type(la.getParentObj()).__name__, la=H.P(la), laLocal=str(la.getPos()))
    la.setPos(org, -430, -1790, 10)
    H.ev('dbg-after-set', la=H.P(la), laLocal=str(la.getPos(org)), par=str(la.getParent()))
    yield 1
    H.ev('dbg-1s', la=H.P(la), laLocal=str(la.getPos(org)), par=str(la.getParent()), gs=la.getGameState())
    yield 6
    H.ev('dbg-7s', la=H.P(la), laLocal=str(la.getPos(org)), par=str(la.getParent()), doorSeen=H.cr.doId2do.get(401000722) is not None, step=H.step())
