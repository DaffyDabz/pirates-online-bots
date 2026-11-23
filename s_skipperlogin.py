"""SKIPPER LOGIN (pir-test, 11-18, patch 13 gate): a kid's pirate made with skip-tutorial #t (tutorial flag 0, already in
Port Royal) logs in on a client with skip-tutorial #f plus 0152, and must land in the main world, not in the opening.
env: BOT_ACCOUNT + BOT_AVID = that pirate (never 100000170). Events: SKIP-LOGIN, PASS / FAIL."""
HOST_AV = 100000170


def run(H):
    la = H.la
    yield 5.0
    area = H.area()
    flag = la.style.getTutorial()
    H.ev('SKIP-LOGIN', avId=la.doId, name=la.getName(), tutorialFlag=flag, crTutorial=base.cr.tutorial,
         played=getattr(base.cr, '_playedMainWorld', None), returnLoc=la.getReturnLocation(), area=area)
    if la.doId == HOST_AV:
        H.ev('FAIL', why='refused: %d is the pirate of Host' % HOST_AV); return
    if flag >= 3:
        H.ev('FAIL', why='tutorial flag %d: not a pirate that skipped the opening, so this proves nothing' % flag); return
    if base.cr.tutorial or not area or 'Tutorial' in area[0] or area[2] != 'Port Royal':
        H.ev('FAIL', why='the pirate went into the opening (or not to Port Royal): area %r, cr.tutorial %r' % (area, base.cr.tutorial)); return
    H.snap('skipper-in-world')
    H.ev('PASS', what='pirate %d (tutorial flag %d) logged in to %s, not the opening' % (la.doId, flag, area[2]))
