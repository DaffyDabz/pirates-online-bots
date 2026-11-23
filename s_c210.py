def run(H):
    la = H.la
    for i in range(8):
        inv = la.getInventory()
        ships = None
        try:
            ships = inv.getShipDoIdList() if inv else None
        except Exception as e:
            ships = 'err %s' % e
        fsm = getattr(la, 'gameFSM', None)
        H.ev('c210', i=i, gs=la.getGameState(), lock=getattr(fsm, 'lockFSM', None), ships=ships, qids=H.qids(),
             step=H.step(), area=H.area(), la=H.P(la),
             dialog=repr(getattr(la, 'currentDialogMovie', None))[:80],
             docks=[(o['cls'], o['doId'], o['dist']) for o in H.objs('Dock')][:4] + [(o['cls'], o['doId'], o['dist']) for o in H.objs('Shipwright')][:4],
             dinghy=[(o['cls'], o['doId'], o['dist']) for o in H.objs('Dinghy')][:4])
        yield 8
