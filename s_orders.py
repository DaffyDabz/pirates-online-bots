PR = '1150922126.8dzlu'
QID = 'c2.4recoverOrders'


def track(H, qid):
    la = H.la
    if la.guiMgr.questPage is None:
        la.guiMgr.initQuestPage()
    page = la.guiMgr.questPage
    page.showQuestDetails(qid)
    if la.activeQuestId != qid:
        page.trackQuest()
    else:
        la.refreshActiveQuestStep(False, True)


def run(H):
    import os
    H.snap('initial')
    if os.environ.get('RESET'):
        H.mw('dropAllQuests')
        yield 4
        H.snap('after-dropAll')
    if not H.has(QID):
        H.mw('giveQuest %s' % QID)
        yield ('until', lambda: H.has(QID), 15, 'give ' + QID)
    if H.area() is None or H.area()[1] != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: H.area() is not None and H.area()[1] == PR and H.la.getGameState() == 'LandRoam', 60, 'tp PR')
        yield 8
    H.snap('in-PR')
    track(H, QID)
    yield 6
    H.ev('step-in-town', **H.step())
    H.ev('navy-in-town', n=len(H.objs('NavySailor')))
    yield from H.moveTo(170, -1060, 56)
    yield 12
    H.snap('near-mansion')
    H.ev('step-after-track', **H.step())
    navy = H.objs('NavySailor')
    H.ev('navy-seen', n=len(navy), near=navy[:8])
    H.ev('enemies-seen', n=len(H.objs('NPCSkeleton')) + len(H.objs('NPCNavy')), all=[(o['cls'], o['dist']) for o in H.objs('DistributedNPC') if 'Townfolk' not in o['cls']][:20])
    if not navy:
        return
    H.drawSword()
    yield 2
    tgt = navy[0]['doId']
    for i in range(80):
        if H.has('c2.5deliverOrders') or not H.has(QID):
            break
        o = H.cr.doId2do.get(tgt)
        if o is None or getattr(o, 'hp', 1) <= 0:
            H.ev('target-down', tgt=tgt, i=i)
            yield 4
            nv = [n for n in H.objs('NavySailor') if (n['hp'] or 0) > 0]
            if not nv or H.has('c2.5deliverOrders') or not H.has(QID):
                break
            tgt = nv[0]['doId']
        yield from H.hit(tgt)
        if i % 10 == 0:
            H.ev('hit', i=i, tgt=tgt, hp=getattr(H.cr.doId2do.get(tgt), 'hp', None), q=H.quests())
        yield 1.2
    yield 6
    H.snap('after-fight')
    H.ev('step-after-fight', **H.step())
    yield ('until', lambda: H.has('c2.5deliverOrders'), 20, 'next quest c2.5deliverOrders')
    H.snap('end-orders')
