"""Story walk with every OK / next-page / name panel clicked like a player, logging each game
state change and whether an NPC interaction is left open after each quest."""
import os, time


def run(H):
    la = H.la
    B = H.B
    d = os.path.dirname(os.environ['PROOF_SCRIPT'])
    g = {}
    sub_ = os.environ.get('REG_SUB', 's_story.py')
    exec(compile(open(os.path.join(d, sub_)).read(), sub_, 'exec'), g)
    st = {'clicks': 0}
    sub = la.guiMgr.subtitler

    def clicker(t):
        try:
            b = sub.confirmButton
            if not b.isHidden() and b['command']:
                st['clicks'] += 1
                H.ev('click', n=st['clicks'], text=str(sub.text['text'])[:50], gs=la.getGameState())
                b['command'](*(b['extraArgs'] or []))
        except Exception:
            import traceback
            H.ev('click-err', tb=traceback.format_exc()[-300:])
        return t.again
    B.taskMgr.doMethodLater(2.5, clicker, 'rg-click')
    from pirates.piratesgui import NamePanelGui as NPm
    oNPi = NPm.NamePanelGui.__init__

    def npi(panel, *a, **k):
        oNPi(panel, *a, **k)
        H.ev('name-panel-open')
        B.taskMgr.doMethodLater(3.0, lambda t: panel.handleCommit() and None or t.done, 'rg-name')
    NPm.NamePanelGui.__init__ = npi
    from pirates.piratesgui import NewTutorialPanel as NTPm
    oAct = NTPm.NewTutorialPanel.activate

    def tact(panel):
        r = oAct(panel)

        def press(t):
            for which in ('noTutorial', 'yesTutorial'):
                b = getattr(panel, which, None)
                try:
                    if b is not None and not b.isEmpty() and b['command']:
                        H.ev('tut-panel-click', which=which)
                        b['command'](*(b['extraArgs'] or []))
                        return t.done
                except Exception:
                    import traceback
                    H.ev('tut-click-err', tb=traceback.format_exc()[-300:])
                    return t.done
            return t.done
        B.taskMgr.doMethodLater(2.0, press, 'rg-tut')
        return r
    NTPm.NewTutorialPanel.activate = tact
    oSet = la.b_setGameState

    def bsg(state, *a, **k):
        H.ev('gs', to=state, frm=la.getGameState(), lock=la.gameFSM.lockFSM)
        return oSet(state, *a, **k)
    la.b_setGameState = bsg

    def openNpcs():
        return [(o.doId, getattr(o, 'name', '')) for o in H.cr.doId2do.values() if getattr(o, 'interactMode', 0)]

    def mon(t):
        H.ev('mon', gs=la.getGameState(), cam=la.cameraFSM.state, open=openNpcs(), q=H.qids())
        return t.again
    B.taskMgr.doMethodLater(10, mon, 'rg-mon')
    for q in H.qids():
        H.mw('dropQuest %s' % q)
        yield 2
    yield from g['run'](H)
    H.ev('RESULT', gs=la.getGameState(), open=openNpcs(), q=H.qids(), hist=H.hist())
