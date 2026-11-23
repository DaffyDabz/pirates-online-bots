"""Bug 2 probe: talk to several Port Royal townfolk like a player (click every OK / next page,
never press Escape) and record whether the pirate gets control back on its own."""
import os, time

PR = '1150922126.8dzlu'


def run(H):
    la = H.la
    B = H.B
    d = os.path.dirname(os.environ['PROOF_SCRIPT'])
    g = {}
    exec(compile(open(os.path.join(d, 's_story.py')).read(), 's_story.py', 'exec'), g)
    sub = la.guiMgr.subtitler
    st = {'clicks': []}

    def clicker(t):
        try:
            b = sub.confirmButton
            if not b.isHidden() and b['command']:
                st['clicks'].append(str(sub.text['text'])[:40])
                b['command'](*(b['extraArgs'] or []))
        except Exception:
            pass
        return t.again
    B.taskMgr.doMethodLater(2.0, clicker, 'np-click')
    oSet = la.b_setGameState

    def bsg(state, *a, **k):
        H.ev('gs', to=state, frm=la.getGameState())
        return oSet(state, *a, **k)
    la.b_setGameState = bsg
    if H.area() is None or H.area()[1] != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: H.area() is not None and H.area()[1] == PR and la.getGameState() == 'LandRoam', 60, 'tp PR')
        yield 5
    from pirates.npc import DistributedNPCTownfolk as DNm
    for meth in ('setQuestsCompleted', 'offerOptions', 'setQuestOffer', 'setQuestLadderOffer', 'playQuestString', 'cancelInteraction', 'presentOffer'):
        orig = getattr(DNm.DistributedNPCTownfolk, meth, None)
        if orig is None:
            continue
        def wrap(self, *a, _o=orig, _m=meth, **k):
            H.ev('npc-call', m=_m, args=repr(a)[:160], gs=la.getGameState(), gui=bool(self.interactGUI))
            return _o(self, *a, **k)
        setattr(DNm.DistributedNPCTownfolk, meth, wrap)
    if os.environ.get('QUEST'):
        for q in H.qids():
            H.mw('dropQuest %s' % q)
            yield 2
        H.mw('giveQuest %s' % os.environ['QUEST'])
        yield 4
    names = os.environ.get('NPC_NAMES', '').split(',') if os.environ.get('NPC_NAMES') else None
    isl = H.cr.doId2do.get(401000618)
    if isl is not None:
        la.setPos(isl, 186, -1880, 4)
        yield 8
    npcs = [o for o in H.cr.doId2do.values() if type(o).__name__ == 'DistributedNPCTownfolk' and not o.isEmpty()]
    npcs.sort(key=lambda o: (o.getPos(H.render) - la.getPos(H.render)).length())
    if names:
        npcs = [o for o in npcs if getattr(o, 'name', '') in names] + [o for o in npcs if getattr(o, 'name', '') not in names]
    H.ev('npcs', n=len(npcs), first=[(o.doId, o.name) for o in npcs[:10]])
    done = 0
    for npc in npcs:
        if done >= int(os.environ.get('NPC_COUNT', '6')):
            break
        if npc.isEmpty() or npc.isDeleted():
            continue
        done += 1
        st['clicks'] = []
        g['near'](H, npc, 5)
        yield 1
        npc.requestInteraction(la.doId)
        H.ev('talk', npc=npc.doId, who=npc.name, shop=npc.getShopId(), help=npc.getHelpId())
        yield 14
        rep = dict(who=npc.name, gs=la.getGameState(), interactMode=npc.interactMode, menu=bool(npc.interactGUI),
                   questMenu=bool(npc.questMenuGUI), subtitleShown=not sub.text.isHidden(),
                   subText=str(sub.text['text'])[:60], confirmShown=not sub.confirmButton.isHidden(),
                   dialogOpen=npc.dialogOpen, movie=hasattr(npc, 'currentDialogMovie'), clicks=st['clicks'],
                   cam=la.cameraFSM.state)
        H.ev('NPC-RESULT', **rep)
        if la.getGameState() != 'LandRoam' or npc.interactMode:
            if npc.interactGUI:
                npc.interactGUI.destroy()
                npc.interactGUI = None
            npc.handleEndInteractKey()
            yield 3
            H.ev('after-escape', gs=la.getGameState(), interactMode=npc.interactMode)
        yield 2
