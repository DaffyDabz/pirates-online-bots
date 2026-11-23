"""CREW2 (pir-bot, 11-17, job 3): two test pirates. The mate joins the captain's crew and boards the captain's ship.

Two hidden games run this same step at once (run_two.ps1), one with CREW_ROLE=captain, one with CREW_ROLE=mate.
Neither may ever be Host's pirate 100000170 or sail his ship 100000173: the step stops with FAIL at once if so.

captain (the harness pirate 100000001 by default): on Port Royal, waits for the mate to come into interest, sends
  the crew invite (PirateBandManager.d_requestInvite, the crew page's Invite button), waits for 'BandAdded-<mate>'
  (the server's yes), then launches its ship at the dinghy and takes the wheel (sailing.launch), and waits with the
  ship by the dock until the mate is on its crew list (ship.getCrew()).
mate: on Port Royal, answers the captain's invite with yes (d_invitationResponce(captain, 0), the invite pop-up's
  Accept), waits until it is in a crew (setBandId), walks to the dinghy and asks to use it; the server offers the
  crew's ships (offerBandOptions, patched in 2026-09-16) and the mate picks the captain's
  (DistributedDinghy.bandShipSelected, the "Crew ship" row of the launch panel), then waits to be aboard it.

Lines (both): CREW-START (role, me, the other), STAGE step=crew what=..., PASS / FAIL.
  captain: what = at-island / mate-seen / invited / crew-made / launched / mate-aboard; CREW-INVITE, CREW-ADDED,
    CREW-REJECTED, CREW-LIST.
  mate: what = at-island / invite-got / accepted / in-crew / at-dinghy / ship-offered / picked / aboard;
    CREW-INVITE-GOT, CREW-OFFER (the options the dinghy got), CREW-PICK, CREW-ABOARD.
PASS captain = the mate is on the ship's crew list. PASS mate = its crew ship is the captain's ship.
env: CREW_ROLE (captain | mate), CREW_CAPTAIN (avId, 100000001), CREW_MATE (avId, needed by the captain),
     CREW_FROM (Port Royal), CREW_SECS (900: the whole step's limit for either side)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402
import sailing   # noqa: E402

HOST_AV, HOST_SHIP = 100000170, 100000173
ROLE = os.environ.get('CREW_ROLE', '')
CAPTAIN = int(os.environ.get('CREW_CAPTAIN', '100000001'))
MATE = int(os.environ.get('CREW_MATE', '0') or 0)
FROM = os.environ.get('CREW_FROM', s_lanes.PR)
SECS = float(os.environ.get('CREW_SECS', '900'))
INVITE_EVERY = 30        # s between invites while no answer came
OFFER_EVERY = 25         # s between dinghy asks while the crew ship is not offered yet


def checkSetup(role, me, captain, mate):
    """Pure: None when this run may go on, else why not."""
    if role not in ('captain', 'mate'):
        return 'CREW_ROLE must be captain or mate (is %r)' % role
    if HOST_AV in (me, captain, mate):
        return 'pirate %d belongs to Host: never used by a test' % HOST_AV
    if role == 'captain' and me != captain:
        return 'the captain run logged in as %d, not CREW_CAPTAIN %d' % (me, captain)
    if role == 'captain' and not mate:
        return 'the captain needs CREW_MATE (the second test pirate)'
    if role == 'mate' and me == captain:
        return 'the mate run logged in as the captain %d (set BOT_AVID for the mate)' % me
    if role == 'mate' and mate and me != mate:
        return 'the mate run logged in as %d, not CREW_MATE %d' % (me, mate)
    return None


def pickOffer(options, captainName=None, never=HOST_SHIP):
    """Pure: options = the dinghy's offerBandOptions rows [memberDoId, shipDoId, hp, sp, cargo, crew, 1, siegeTeam,
    captainName]. -> the shipDoId to board: the captain's (by name when known, else the only / first one), never
    Host's ship. None when there is none."""
    rows = [o for o in options or [] if len(o) > 1 and o[1] and o[1] != never]
    if captainName:
        named = [o for o in rows if len(o) > 8 and o[8] == captainName]
        if named:
            return named[0][1]
    return rows[0][1] if rows else None


def inBand(la):
    b = la.getBandId() if hasattr(la, 'getBandId') else None
    return bool(b and b[1])


def run(H):
    la = H.la
    why = checkSetup(ROLE, la.doId, CAPTAIN, MATE)
    H.ev('CREW-START', role=ROLE, me=la.doId, captain=CAPTAIN, mate=MATE, frm=FROM, band=la.getBandId(), why=why)
    if why:
        H.ev('FAIL', why=why); return
    if not (yield from s_lanes.onIsland(H, 'crew', FROM)):
        H.ev('FAIL', why='could not get to %s' % FROM, area=H.area()); return
    s_lanes.stage(H, 'crew', 'at-island', island=FROM, role=ROLE)
    if ROLE == 'captain':
        yield from captain(H)
    else:
        yield from mate(H)


def captain(H):
    from direct.showbase.DirectObject import DirectObject
    la = H.la
    t0 = time.time()
    yield ('until', lambda: MATE in H.cr.doId2do, 300, 'mate in interest')
    if MATE not in H.cr.doId2do:
        H.ev('FAIL', why='the mate %d never came into interest on %s (is the mate run up?)' % (MATE, FROM)); return
    s_lanes.stage(H, 'crew', 'mate-seen', mate=MATE)
    ans = {}
    do = DirectObject()
    do.accept('BandAdded-%s' % MATE, lambda *a: ans.setdefault('added', time.time()))
    do.accept('BandRequestRejected-%s' % MATE, lambda av, r=None, *a: ans.update(rejected=r))
    try:
        sent = 0
        while not ans.get('added') and time.time() - t0 < SECS:
            if not sent or time.time() - sent > INVITE_EVERY:
                if 'rejected' in ans:
                    H.ev('CREW-REJECTED', mate=MATE, why=ans.pop('rejected'))
                base.cr.PirateBandManager.d_requestInvite(MATE)
                H.ev('CREW-INVITE', mate=MATE, n=int(sent > 0) + 1)
                if not sent:
                    s_lanes.stage(H, 'crew', 'invited', mate=MATE)
                sent = time.time()
            yield 1
    finally:
        do.ignoreAll()
    if not ans.get('added'):
        H.ev('FAIL', why='the mate never joined the crew', rejected=ans.get('rejected')); return
    H.ev('CREW-ADDED', mate=MATE, band=la.getBandId())
    s_lanes.stage(H, 'crew', 'crew-made', band=la.getBandId())
    ships = list(la.getInventory().getShipDoIdList())
    if not ships:
        H.ev('FAIL', why='the captain owns no ship'); return
    if HOST_SHIP in ships[:1]:
        H.ev('FAIL', why='the first ship is Host\'s %d' % HOST_SHIP); return
    ship = yield from sailing.launch(H, FROM, False)
    if ship is None:
        H.ev('FAIL', why='the captain could not launch (a SAIL-FAIL line says why)'); return
    s_lanes.stage(H, 'crew', 'launched', ship=ship.doId)
    last = None
    while time.time() - t0 < SECS:
        crew = list(ship.getCrew() or [])
        if crew != last:
            H.ev('CREW-LIST', ship=ship.doId, crew=crew)
            last = crew
        if MATE in crew:
            s_lanes.stage(H, 'crew', 'mate-aboard', ship=ship.doId, crew=crew)
            H.ev('PASS', what='the mate %d is aboard the captain\'s ship %d' % (MATE, ship.doId), crew=crew)
            yield 20                  # stay a little so the mate's own check sees the ship too
            return
        yield 2
    H.ev('FAIL', why='the mate did not board in %d s' % SECS, crew=last)


def mate(H):
    from direct.showbase.DirectObject import DirectObject
    from pirates.band import BandConstance
    la = H.la
    t0 = time.time()
    inv = {}
    do = DirectObject()
    do.accept(BandConstance.BandInvitationEvent, lambda av, name, *a: inv.setdefault('from', (av, name)))
    try:
        while not inBand(la) and time.time() - t0 < SECS:
            if 'from' in inv:
                av, name = inv.pop('from')
                H.ev('CREW-INVITE-GOT', frm=av, name=name)
                s_lanes.stage(H, 'crew', 'invite-got', frm=av)
                if av != CAPTAIN:
                    H.ev('CREW-IGNORE', frm=av, why='not the captain %d' % CAPTAIN)
                    base.cr.PirateBandManager.d_invitationResponce(av, BandConstance.outcome_declined)
                else:
                    base.cr.PirateBandManager.d_invitationResponce(av, BandConstance.outcome_ok)
                    s_lanes.stage(H, 'crew', 'accepted', captain=av)
                    yield ('until', lambda: inBand(la), 20, 'in crew')
            yield 1
    finally:
        do.ignoreAll()
    if not inBand(la):
        H.ev('FAIL', why='no crew invite from %d in %d s' % (CAPTAIN, SECS)); return
    s_lanes.stage(H, 'crew', 'in-crew', band=la.getBandId())
    capName = getattr(H.cr.doId2do.get(CAPTAIN), 'name', None)
    shipId, d = None, None
    while time.time() - t0 < SECS and shipId is None:
        d = yield from sailing.to_dinghy(H, FROM)
        if d is None:
            H.ev('FAIL', why='no open route to a dinghy', la=H.P(la)); return
        s_lanes.stage(H, 'crew', 'at-dinghy', dinghy=d.doId)
        got = {}
        orig = d.offerBandOptions

        def offer(options, *a):
            got['o'] = [list(o) for o in options]
            H.ev('CREW-OFFER', options=got['o'])
            return orig(options, *a)
        d.offerBandOptions = offer
        try:
            d.requestInteraction(la.doId)
            yield ('until', lambda: 'o' in got, 10, 'band options')
            shipId = pickOffer(got.get('o'), capName)
            if shipId is None:
                H.ev('act', step='crew', a='no crew ship offered yet', offered=got.get('o'))
                d.requestExit()
                yield OFFER_EVERY
                continue
            s_lanes.stage(H, 'crew', 'ship-offered', ship=shipId)
            H.ev('CREW-PICK', ship=shipId, captain=capName)
            d.bandShipSelected(shipId)
            s_lanes.stage(H, 'crew', 'picked', ship=shipId)
        finally:
            del d.offerBandOptions
    if shipId is None:
        H.ev('FAIL', why='the captain\'s ship was never offered at the dinghy in %d s' % SECS); return

    def aboard():
        return la.getCrewShipId() == shipId or getattr(la.getCrewShip(), 'doId', None) == shipId
    yield ('until', aboard, 60, 'aboard the crew ship')
    yield ('until', lambda: la.getGameState() != 'Cutscene', 40, 'board cutscene')
    H.ev('CREW-ABOARD', ship=shipId, crewShip=la.getCrewShipId(), gs=la.getGameState(), area=H.area())
    if not aboard():
        H.ev('FAIL', why='picked the crew ship %d but is not aboard it' % shipId, crewShip=la.getCrewShipId()); return
    s_lanes.stage(H, 'crew', 'aboard', ship=shipId)
    H.ev('PASS', what='joined the crew of %d and boarded its ship %d' % (CAPTAIN, shipId))
