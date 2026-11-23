# Item 5 (09-22): prove the district survives a message whose AI handler raises.
# Needs the TEMP sentinel in DistributedPlayerPirateAI.requestReturnShip (survive_inject.sh);
# survive_restore.sh puts the original back. Pass = ai.log 'district-survived', AI still up, this bot ejected 153.
SENTINEL = 4242424242


def run(H):
    from panda3d.core import DatagramIterator
    cr = H.cr
    got = {}
    orig = cr.handleGoGetLost

    def ggl(di):
        code = None
        try:
            code = DatagramIterator(di.getDatagram(), di.getCurrentIndex()).getUint16()
        except Exception:
            pass
        got['code'] = code
        H.ev('KICKED', code=code)
        return orig(di)
    cr.handleGoGetLost = ggl
    yield 6
    H.ev('survive-send', doId=H.la.doId, sentinel=SENTINEL)
    H.la.sendUpdate('requestReturnShip', [SENTINEL])
    yield ('until', lambda: 'code' in got, 30, 'eject after the raising message')
    H.ev('survive-result', kicked='code' in got, code=got.get('code'))
