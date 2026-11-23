"""Darby ship tutorial repro: give c2.9visitDarby, walk to Darby, click every OK and submit a
ship name the way the GUI does, then check the pirate is back in LandRoam with control."""
import os, time

PR = '1150922126.8dzlu'


def run(H):
    la = H.la
    B = H.B
    g = {}
    sp = os.path.join(os.path.dirname(os.environ['PROOF_SCRIPT']), 's_story.py')
    exec(compile(open(sp).read(), sp, 'exec'), g)
    st = {'clicks': 0, 'names': 0}
    # ---- hooks: OK button and ship-name panel, driven through their real callbacks
    from pirates.piratesgui import Subtitler as SUBm
    oCT = SUBm.Subtitler.confirmText

    def ct(sub, text, event, *a, **k):
        r = oCT(sub, text, event, *a, **k)
        H.ev('subtitle-confirm', text=str(text)[:60], event=event, gs=la.getGameState())

        def click(t):
            if sub.event == event:
                st['clicks'] += 1
                H.ev('click-OK', n=st['clicks'], gs=la.getGameState())
                sub.confirmButton['command']()
            return t.done
        B.taskMgr.doMethodLater(2.0, click, 'darby-ok')
        return r
    SUBm.Subtitler.confirmText = ct
    from pirates.piratesgui import NamePanelGui as NPm
    oNPi = NPm.NamePanelGui.__init__

    def npi(panel, *a, **k):
        oNPi(panel, *a, **k)
        H.ev('name-panel-open', gs=la.getGameState())

        def commit(t):
            st['names'] += 1
            try:
                panel.handleCommit()
                H.ev('name-panel-commit', gs=la.getGameState())
            except Exception:
                import traceback
                H.ev('NAME-COMMIT-CRASH', tb=traceback.format_exc()[-800:])
            return t.done
        B.taskMgr.doMethodLater(3.0, commit, 'darby-name')
    NPm.NamePanelGui.__init__ = npi
    oSet = la.b_setGameState

    def bsg(state, *a, **k):
        H.ev('b_setGameState', to=state, frm=la.getGameState(), lock=la.gameFSM.lockFSM)
        return oSet(state, *a, **k)
    la.b_setGameState = bsg
    # ---- setup
    if H.area() is None or H.area()[1] != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: H.area() is not None and H.area()[1] == PR and la.getGameState() == 'LandRoam', 60, 'tp PR')
        yield 5
    for q in H.qids():
        H.mw('dropQuest %s' % q)
        yield 2
    H.mw('giveQuest c2.9visitDarby')
    yield ('until', lambda: H.has('c2.9visitDarby'), 20, 'give darby')
    H.ev('given', qids=H.qids(), ships=list(la.getInventory().getShipDoIdList()))
    g['track'](H, 'c2.9visitDarby')
    yield 4
    # ---- walk to Darby and talk
    cur = {}
    t0 = time.time()
    while time.time() - t0 < 120 and H.has('c2.9visitDarby') and not la.getQuests()[0].isComplete():
        if la.getGameState() != 'LandRoam':
            break
        q = [q for q in la.getQuests() if q.getQuestId() == 'c2.9visitDarby'][0]
        a = g['act'](H, q, cur)
        H.ev('act', a=a, gs=la.getGameState())
        yield 3
    # ---- watch the flow finish
    t1 = time.time()
    while time.time() - t1 < 60:
        dm = getattr(la, 'currentDialogMovie', None)
        H.ev('watch', t=round(time.time() - t1), gs=la.getGameState(), lock=la.gameFSM.lockFSM,
             cam=la.cameraFSM.state, qids=H.qids(), clicks=st['clicks'], names=st['names'],
             ignoreKeys=la.guiMgr.ignoreAllKeys, dialog=repr(dm)[:50],
             ships=list(la.getInventory().getShipDoIdList()))
        if H.has('c2.10visitDockworker') and la.getGameState() == 'LandRoam' and time.time() - t1 > 10:
            break
        yield 3
    npcs = [o for o in H.cr.doId2do.values() if getattr(o, 'interactMode', 0)]
    H.ev('RESULT', gs=la.getGameState(), lock=la.gameFSM.lockFSM, cam=la.cameraFSM.state,
         qids=H.qids(), hist=H.hist()[-3:], npcInteractMode=[o.doId for o in npcs],
         ignoreKeys=la.guiMgr.ignoreAllKeys, ships=list(la.getInventory().getShipDoIdList()),
         shipNames=[(k, getattr(o, 'name', None)) for k, o in H.cr.doId2ownerView.items() if 'Ship' in type(o).__name__],
         imgr=getattr(H.cr.interactionMgr, 'isStarted', lambda: '?')() if hasattr(H.cr.interactionMgr, 'isStarted') else repr(getattr(H.cr.interactionMgr, 'state', '?')))
