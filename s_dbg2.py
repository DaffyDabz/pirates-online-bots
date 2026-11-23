def run(H):
    la = H.la
    R = H.render
    yield 4
    qs = la.questStep
    H.ev('dbg-step', step=repr(qs), qids=H.qids(), hist=H.hist())
    org = H.cr.doId2do.get(401000618)
    la.setPos(org, -430, -1790, 10)
    for i in range(4):
        yield 4
        ds = [(d.doId, type(d).__name__, round((d.getPos(R) - la.getPos(R)).length()), getattr(d, 'interiorUid', None)) for d in list(H.cr.doId2do.values()) if 'Door' in type(d).__name__]
        ds.sort(key=lambda x: x[2])
        H.ev('dbg-doors', i=i, n=len(ds), near=ds[:6], has722=401000722 in H.cr.doId2do, zone=la.zoneId, par=str(la.getParent()))
