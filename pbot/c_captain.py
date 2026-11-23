"""pbots (11-22): the CAPTAIN side of the player-bot v1 proof. claude2 (pirate 100000004) stands in for one of the boys:
he invites the bot to his crew, launches his ship, hunts an enemy ship so the bot's cannon has something to shoot at,
docks again and fights an enemy on land so the bot fights beside him. The bot runs pbot\\b_brain.py in its own game
(run_bot.ps1 -Proof); this script paces itself on the bot's own events file (its MILESTONE lines) and ends with
  PASS  when the bot's file shows all four: CREW-JOINED, ABOARD, CANNON-SHOT, LAND-FIGHT
  FAIL  with what the bot missed, or why the captain could not set the stage (a SAIL-FAIL line says why a launch failed).
Pictures: each bot milestone gets a real picture from THIS game (a SHOT event names the file): the bot's stripped body
draws nothing (8x8 stand-in textures, window off), so its own pictures are grey frames.
Walker step script (PROOF_SCRIPT). Env: PBOT_MATE = the bot's pirate id (required; never Host's or a boy's),
PBOT_MATE_EVENTS = the bot's events file (default <harness>\\walk-PBOT1-events.jsonl), CAPTAIN_FROM (island uid, Port
Royal), CAPTAIN_SECS 1500, CAPTAIN_SEA_SECS 600 (the ship fight at most), CAPTAIN_LAND_SECS 360 (the land fight at most).
Rules: SpeedChat only, never Host's ship 100000173 (the launch refuses it), never a player as a target (s_shipfight and
s_fighter pick NPC ships and battleable NPCs only). run_proof.ps1 runs this and the bot under ONE run.lock.
CAPTAIN_MODE (default v1 = the flow above). 'tele' = the crew.py proof (row 32, 11-22): the same crew-up and meet, then
the captain teleports to CAPTAIN_TO (Tortuga) with no ship and waits CAPTAIN_TELE_SECS (420) for the bot to come to him
by the game's own 'go to <crewmate>' teleport (crew.py's tele duty: a CREW-TELE line with out and landed true in its
file) and to come into his view there; PASS then, FAIL on a CREW-TELE-GIVEUP, a CREW-LEFT, the wait running out or the
bot never seen on CAPTAIN_TO. The bot runs the plain brain (no -Proof: it has no four-milestone PASS to give); the
captain writes its stop file (C:\PiratesBots\out\pbots\STOP-<bot tag>) at the very end so run_bot.ps1 ends the run."""
import os, sys, time, json, re, traceback

HERE =os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__', '.')))
HARNESS = os.path.dirname(HERE)
for _p in (HERE, HARNESS):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# the proof's ship fight picks a weaker foe than s_shipfight's default (level gap 3): run 6's 'fair' pick at captain
# level 4 was an EITC Sea Viper lv 7 (1000 hp); it took 569 hp off the 2400-hp ship in 10 s and the captain broke off
# 37 s after its first broadside, before the mate had manned a cannon. Gap 1 = lv 5 and under (the starter waters round
# Port Royal hold nothing above lv 5: Navy Ferrets lv 2 were in view). SHIPFIGHT_* already in the environment wins.
os.environ.setdefault('SHIPFIGHT_LEVEL_GAP', '1')
import paths, sailing, s_lanes, s_story, s_crew2, s_fighter, s_landfight, s_shipfight  # noqa: E402

MATE = int(os.environ.get('PBOT_MATE', '0') or 0)
MATE_EVENTS = os.environ.get('PBOT_MATE_EVENTS') or os.path.join(HARNESS, 'walk-PBOT1-events.jsonl')
FROM = os.environ.get('CAPTAIN_FROM', s_lanes.PR)
SECS = float(os.environ.get('CAPTAIN_SECS', '1500'))
SEA_SECS = float(os.environ.get('CAPTAIN_SEA_SECS', '600'))
LAND_SECS = float(os.environ.get('CAPTAIN_LAND_SECS', '360'))
AFTER_SHOT = 45.0        # s at sea after the bot's first cannon shot (it gets a few more in)
AFTER_FIGHT = 30.0       # s on land after the bot's first hit
INVITE_EVERY = 30
SEE_SECS = 300           # the bot must come into interest on FROM
INVITE_SECS = 240
MEET_SECS = 200          # the captain walks to the bot before launching (run 4: a ship launched 760 ft from the mate, out
MEET_NEAR = 20.0         # of its view, left it lost on the far side of the island); within this many ft = met
MEET_UNSEEN = 20.0       # s with the mate out of view before the captain walks to the island's dinghies: a lost mate heads
                         # there too (b_brain LOST_WALK), so the two meet at the docks (run 7: both spawned on Port Royal
                         # 765 ft apart, out of each other's interest; the captain waited 149 s blind and launched alone)
SHIP_AWAY_SECS = 90      # s for the island teleport off my ship and the game's put-away of it (s_live's proven path)
CREW_LEAVE_SECS = 60     # s a stranger aboard my ship (one of the boys, via the rowboat list) gets to leave first
MEET_MAX = 3000.0        # ft: farther = the mate is not placed on this island yet (run 5: 48 million ft while it still
                         # sat in the district node, 1.2 s before its teleport landed; the planner's grid build over that
                         # box never yielded a frame and the HANG watchdog killed the captain's game at 240 s)
BOARD_SECS = 240
HOST, HOST_SHIP = 100000170, 100000173
BOYS = (100000656, 100000665)
MILESTONES = ('CREW-JOINED', 'ABOARD', 'CANNON-SHOT', 'LAND-FIGHT')
BEAT = 0.25
SHOTS = r'C:\PiratesBots\out\pbots\shots'
MODE = os.environ.get('CAPTAIN_MODE', 'v1')                      # v1 | tele (the crew.py teleport proof)
TO = os.environ.get('CAPTAIN_TO', s_lanes.TORTUGA)              # tele: the island the captain goes to
TELE_WAIT = float(os.environ.get('CAPTAIN_TELE_SECS', '420'))   # tele: s for the bot's CREW-TELE landing (crew.py: 8 s
                                                                # out of view + TeleportOut 30 + landing 120, a refusal
                                                                # retried after 90; the server may refuse while I load)
TELE_SEEN = 90.0                                                # tele: s for the landed bot to come into my view on TO
STOPS = r'C:\PiratesBots\out\pbots'                               # run_bot.ps1's stop files, STOP-<bot tag>
# the bot's run tag (PBOT1), from its events file name: the pictures sit next to the bot's own, <TAG>-<MILESTONE>-captain-*.jpg
TAG = os.environ.get('PBOT_TAG') or re.sub(r'^walk-|-events\.jsonl$', '', os.path.basename(MATE_EVENTS)) or 'PBOT'


class MateFile:
    """The bot's events file, read as it grows (another process writes it, line-buffered). onNew(name) is called once
    per new bot milestone (the captain takes a picture)."""

    def __init__(self, path, onNew=None):
        self.path, self.off, self.rest = path, 0, b''
        self.ms, self.verdict, self.bugs, self.last, self.n = {}, None, 0, None, 0
        self.evs, self.counts = {}, {}      # the last record of each event name, and how many of each (tele mode)
        self.onNew = onNew

    def poll(self):
        try:
            if os.path.getsize(self.path) <= self.off:
                return self.ms
            with open(self.path, 'rb') as f:
                f.seek(self.off)
                data = f.read()
        except OSError:
            return self.ms
        self.off += len(data)
        parts = (self.rest + data).split(b'\n')
        self.rest = parts.pop()
        for raw in parts:
            try:
                r = json.loads(raw.decode('utf-8', 'replace'))
            except Exception:
                continue
            self.n += 1
            self.last = raw[:200].decode('utf-8', 'replace')
            e = r.get('ev')
            if e:
                self.evs[e] = r
                self.counts[e] = self.counts.get(e, 0) + 1
            if e == 'MILESTONE' and r.get('name') not in self.ms:
                self.ms[r['name']] = r.get('t')
                if self.onNew is not None:
                    try:
                        self.onNew(r['name'])
                    except Exception:
                        pass
            elif e == 'BUG':
                self.bugs += 1
            elif e in ('PASS', 'FAIL') and self.verdict is None:
                self.verdict = (e, r.get('what') or r.get('why'))
        return self.ms

    def has(self, name):
        return name in self.poll()


class Beat:
    """A 'beat' event at most every 60 s in a quiet loop: the walker calls 240 s without an event a HANG."""

    def __init__(self, H):
        self.H, self.t = H, time.time()

    def __call__(self, where, **kw):
        if time.time() - self.t > 60:
            self.t = time.time()
            self.H.ev('beat', where=where, gs=self.H.la.getGameState(), hp=getattr(self.H.la, 'hp', None), **kw)


def shot(H, name):
    """A real picture from the captain's game the moment the bot's file shows a new milestone (the captain stands next to
    the bot at each one: on the dock, on his deck, at the wheel while the bot shoots, in the land fight). Same frames-then-
    save as the brain's own shot(); the window here is always on, 1920x1080, full textures."""
    try:
        from panda3d.core import Filename
        os.makedirs(SHOTS, exist_ok=True)
        fn = os.path.join(SHOTS, '%s-%s-captain-%s.jpg' % (TAG, name, time.strftime('%H%M%S')))
        H.B.graphicsEngine.renderFrame()          # H.B = the game's ShowBase (walker)
        H.B.graphicsEngine.renderFrame()
        ok = H.B.win.saveScreenshot(Filename.fromOsSpecific(fn))
        H.ev('SHOT', name=name, file=fn, ok=bool(ok))
    except Exception:
        H.ev('shot-failed', name=name, tb=traceback.format_exc()[-200:])


def meet(H):
    """Generator. Walk to the bot (route-planned, round the buildings) until it is MEET_NEAR ft away or MEET_SECS are up:
    the bot follows once it sees me, so the launch happens next to it. -> ft apart at the end (None: bot not in view)."""
    t0, R = time.time(), H.render
    bot = H.cr.doId2do.get(MATE)
    d = round(s_story.hdist(H, bot), 1) if bot is not None else None
    H.ev('MEET-GO', mate=MATE, d=d, la=H.P(H.la))
    legs, far, unseen, docks = 0, 0, None, False
    while time.time() - t0 < MEET_SECS:
        bot = H.cr.doId2do.get(MATE)
        if bot is None or bot.isEmpty():
            unseen = unseen or time.time()
            if not docks and time.time() - unseen > MEET_UNSEEN:
                # out of view this long = spawned out of interest (run 7): the lost mate walks to the dinghies, so do I
                docks = True
                H.ev('MEET-DOCKS', unseen=round(time.time() - unseen), island=FROM, la=H.P(H.la))
                dt = time.time()
                dg = yield from sailing.to_dinghy(H, FROM)
                H.ev('MEET-DOCKS-DONE', ok=dg is not None, dinghy=getattr(dg, 'doId', None), secs=round(time.time() - dt),
                     seen=MATE in H.cr.doId2do, la=H.P(H.la))
                continue
            yield 1
            continue
        unseen = None
        d = s_story.hdist(H, bot)
        if d <= MEET_NEAR:
            break
        if d > MEET_MAX:                    # not on this island yet: the planner must never get a far goal (run 5)
            far += 1
            yield 1
            continue
        p = bot.getPos(R)
        legs += 1
        g = yield from paths.walk_route(H, [(p[0], p[1], p[2])], MEET_NEAR * 0.75, tag='meet %d' % legs, tries=2,
                                        max_goals=1)
        yield 3 if g is None else 0.5       # no route from here: the bot may be coming to me; look again shortly
    bot = H.cr.doId2do.get(MATE)
    d = round(s_story.hdist(H, bot), 1) if bot is not None else None
    H.ev('MEET-DONE', mate=MATE, d=d, met=d is not None and d <= MEET_NEAR, secs=round(time.time() - t0, 1), legs=legs,
         far=far, docks=docks, la=H.P(H.la))
    return d


def myShip(H):
    """-> (doId, owner view) of my ship that is out (launched, at sea or at the dock), else (None, None). A ship that is
    away reads Off / PutAway / Sunk on its owner view (s_live's check)."""
    try:
        sids = list(H.la.getInventory().getShipDoIdList())
    except Exception:
        return None, None
    for sid in sids:
        ov = H.cr.getOwnerView(sid)
        if ov is not None and getattr(ov, 'state', None) not in (None, 'Off', 'PutAway', 'Sunk'):
            return sid, ov
    return None, None


def shipAway(H, why):
    """Generator. Put my ship away before this game ends: the island teleport off the ship (s_live's proven path: the game
    puts the owner's ship away when he lands), then wait for the owner view to read Off / PutAway / Sunk. Run 7's captain
    logged out with its ship launched and Player1 aboard, and the game kicked him (eject 153; the game-side fix is the bulbs
    lane's READY-ship-owner-offline). A stranger aboard gets CREW_LEAVE_SECS to leave first. -> True when the ship is away."""
    la = H.la
    t0 = time.time()
    sid, ov = myShip(H)
    aboard = sailing.onShip(H)
    state = getattr(ov, 'state', None) if ov is not None else None
    if sid is None and not aboard:
        H.ev('SHIP-AWAY', ok=True, why=why, did='nothing: no ship out', state=state, aboard=aboard, gs=la.getGameState(),
             here=H.area(), secs=0)
        return True

    def crew():
        s = H.cr.doId2do.get(sid) if sid else None
        try:
            return [int(c) for c in s.getCrew()] if s is not None else None
        except Exception:
            return None

    def others():
        return [c for c in (crew() or []) if c not in (la.doId, MATE)]

    H.ev('SHIP-AWAY-GO', why=why, ship=sid, state=state, aboard=aboard, gs=la.getGameState(), crew=crew(), others=others(),
         here=H.area(), la=H.P(la))
    if others():
        yield ('upto', lambda: not others(), CREW_LEAVE_SECS, 'strangers off my ship')
        H.ev('SHIP-AWAY-CREW', others=others(), waited=round(time.time() - t0),
             what='a stranger was aboard my ship' + (' and still is' if others() else ' and left'))
    wheel = next((o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedSteeringWheel'
                  and getattr(o, 'shipId', None) == sid), None)
    if la.getGameState() == 'ShipPilot' and wheel is not None:
        wheel.requestExit()
        yield ('upto', lambda: la.getGameState() != 'ShipPilot', 10, 'off the wheel')

    def landed():
        return sailing.hereUid(H) == FROM and la.getGameState() == 'LandRoam' and not sailing.onShip(H)

    def away():
        return getattr(H.cr.getOwnerView(sid), 'state', None) in ('Off', 'PutAway', 'Sunk')

    H.mw('areaTeleport %s' % FROM)
    yield ('upto', landed, SHIP_AWAY_SECS, 'ashore at %s' % FROM)
    how = 'areaTeleport'
    if not landed():
        # second mechanism, logged apart: the game's own island teleport (the client checks its teleport flags first)
        how = 'requestTeleportToIsland'
        H.ev('SHIP-AWAY-RETRY', how=how, gs=la.getGameState(), here=H.area(), aboard=sailing.onShip(H))
        try:
            H.cr.teleportMgr.requestTeleportToIsland(FROM)
        except Exception:
            H.ev('SHIP-AWAY-RETRY', how=how, error=traceback.format_exc()[-300:])
        yield ('upto', landed, 60, 'ashore at %s (2)' % FROM)
    yield ('upto', away, 30, 'ship put away')
    state = getattr(H.cr.getOwnerView(sid), 'state', None)
    ok = bool(landed() and away())
    H.ev('SHIP-AWAY', ok=ok, why=why, how=how, ship=sid, state=state, landed=landed(), aboard=sailing.onShip(H),
         gs=la.getGameState(), crew=crew(), here=H.area(), secs=round(time.time() - t0), la=H.P(la))
    return ok


def run(H):
    """The proof (_run), then ALWAYS the ship put-away: every exit path of _run (a FAIL return, the PASS, an error) lands
    in shipAway before the game closes. run_proof.ps1 gives the walker's PROOF_SECS watchdog the headroom for it."""
    done = False
    try:
        yield from _run(H)
        done = True
    except Exception:
        tb = traceback.format_exc()
        H.ev('FAIL', why='captain error: %s' % tb.strip().splitlines()[-1][:160], tb=tb[-1500:])
    yield from shipAway(H, 'end of the run' if done else 'after a captain error')
    if MODE == 'tele':
        stopBot(H)


def stopBot(H):
    """tele mode's last act: the bot's stop file (run_bot.ps1 -Once ends its run on it, no strike), so the slot is free
    as soon as the verdict is in. The plain brain would otherwise play on until its PROOF_SECS."""
    fn = os.path.join(STOPS, 'STOP-%s' % TAG)
    try:
        with open(fn, 'w', encoding='utf-8') as f:
            f.write('c_captain tele proof over at %s\n' % time.strftime('%H:%M:%S'))
        H.ev('BOT-STOP', file=fn, ok=True)
    except Exception:
        H.ev('BOT-STOP', file=fn, ok=False, error=traceback.format_exc()[-300:])


def _tele(H, mate, t0, beat):
    """CAPTAIN_MODE=tele, after the crew-up and the meet: I teleport to TO with no ship, then wait for the bot to come to
    me by the game's own crewmate teleport (crew.py's tele duty, armed 8 s after it loses sight of me) and to come into my
    view there. The meet first is not for show: crew.py arms its teleport only after it has SEEN me (want() resets its lost
    clock while I am in view), and the game refuses a 'go to' towards a crewmate in the same area (code -1,
    NoTeleportToSameArea), so I must be seen here first and then be somewhere else."""
    la = H.la
    mate.poll()
    left0 = mate.counts.get('CREW-LEFT', 0)
    H.ev('TELE-GO', to=TO, frm=sailing.hereUid(H), band=la.getBandId(), botSeen=MATE in H.cr.doId2do, la=H.P(la))
    t1 = time.time()
    ok = yield from s_lanes.onIsland(H, 'tele', TO)
    H.ev('TELE-DONE', ok=bool(ok), to=TO, here=sailing.hereUid(H), area=H.area(), gs=la.getGameState(),
         secs=round(time.time() - t1, 1), la=H.P(la))
    if not ok:
        H.ev('FAIL', why='the captain could not get to %s for the teleport proof' % TO, area=H.area(),
             gs=la.getGameState()); return
    s_lanes.stage(H, 'proof', 'captain-away', island=TO, mate=mate.poll())

    # the bot's own file says it is coming: CREW-TELE with out and landed true (a refused try shows landed false; crew.py
    # retries after 90 s, three times, then CREW-TELE-GIVEUP); a new CREW-LEFT = the crew came apart
    end, rec, tries, why = time.time() + TELE_WAIT, None, 0, None
    while time.time() < end:
        mate.poll()
        r = mate.evs.get('CREW-TELE')
        if r is not None and r.get('out') and r.get('landed'):
            rec = r
            break
        tries = mate.counts.get('CREW-TELE', 0)
        if 'CREW-TELE-GIVEUP' in mate.evs:
            why = 'the bot gave up its teleport to me: %s' % mate.evs['CREW-TELE-GIVEUP']; break
        if mate.counts.get('CREW-LEFT', 0) > left0:
            why = 'the crew came apart while I waited: %s' % mate.evs['CREW-LEFT']; break
        beat('wait-tele', tries=tries, last=mate.last, botSeen=MATE in H.cr.doId2do)
        yield 2
    if rec is None:
        H.ev('FAIL', why=why or 'the bot did not land by my side in %d s (%d CREW-TELE line(s))' % (TELE_WAIT, tries),
             tries=tries, crewTele=mate.evs.get('CREW-TELE'), mateLast=mate.last, botSeen=MATE in H.cr.doId2do,
             here=H.area()); return
    s_lanes.stage(H, 'proof', 'bot-landed', tele=rec, tries=tries, mate=mate.poll())

    # the second witness: the bot in my own view on TO (the game lands a crewmate beside the pirate he went to)
    yield ('upto', lambda: MATE in H.cr.doId2do, TELE_SEEN, 'the bot in my view on %s' % TO)
    bot = H.cr.doId2do.get(MATE)
    d = round(s_story.hdist(H, bot), 1) if bot is not None else None
    shot(H, 'CREW-TELE')
    if bot is None:
        H.ev('FAIL', why='the bot\'s file says it landed (area %s) but it never came into my view on %s in %d s'
             % (rec.get('area'), TO, int(TELE_SEEN)), tele=rec, here=H.area(), la=H.P(la)); return
    H.ev('PASS', what='crew teleport: the bot followed the captain to %s by the game\'s crewmate teleport' % TO, to=TO,
         here=H.area(), d=d, tele=rec, tries=tries, secs=round(time.time() - t0), band=la.getBandId(), bot=H.P(bot),
         la=H.P(la))


def _run(H):
    la = H.la
    t0 = time.time()
    mate = MateFile(MATE_EVENTS, onNew=lambda n: shot(H, n))
    beat = Beat(H)
    H.ev('CAPTAIN-START', me=la.doId, mate=MATE, mateEvents=MATE_EVENTS, frm=FROM, secs=SECS, sea=SEA_SECS,
         land=LAND_SECS, here=H.area(), gs=la.getGameState(), mode=MODE, to=TO if MODE == 'tele' else None)
    if la.doId == HOST:
        H.ev('FAIL', why='refused: the captain run never uses Host\'s pirate'); return
    if not MATE or MATE == HOST or MATE in BOYS:
        H.ev('FAIL', why='PBOT_MATE must be a bot pirate id (never Host or the boys)', mate=MATE); return
    if not (yield from s_lanes.onIsland(H, 'proof', FROM)):
        H.ev('FAIL', why='could not get to %s' % FROM, area=H.area()); return
    s_lanes.stage(H, 'proof', 'at-island', island=FROM)

    # 1. the crew: wait for the bot, invite it until it is in
    yield ('until', lambda: MATE in H.cr.doId2do, SEE_SECS, 'bot in interest')
    bot = H.cr.doId2do.get(MATE)
    if bot is None:
        H.ev('FAIL', why='the bot %d never came into interest on %s in %d s (is its game up and on this island?)'
             % (MATE, FROM, SEE_SECS), mateEvents=mate.n, mateLast=mate.poll() and mate.last); return
    s_lanes.stage(H, 'proof', 'bot-seen', bot=MATE, name=getattr(bot, 'name', None), d=round(s_story.hdist(H, bot), 1))
    from direct.showbase.DirectObject import DirectObject
    ans = {}
    do = DirectObject()
    do.accept('BandAdded-%s' % MATE, lambda *a: ans.setdefault('added', time.time()))
    do.accept('BandRequestRejected-%s' % MATE, lambda av, r=None, *a: ans.update(rejected=r))
    try:
        sent, n = 0, 0
        while not ans.get('added') and time.time() - t0 < INVITE_SECS:
            if mate.has('CREW-JOINED'):
                ans.setdefault('added', time.time())
                break
            if not sent or time.time() - sent > INVITE_EVERY:
                if 'rejected' in ans:
                    H.ev('CREW-REJECTED', mate=MATE, why=ans.pop('rejected'))
                H.cr.PirateBandManager.d_requestInvite(MATE)
                n += 1
                H.ev('CREW-INVITE', mate=MATE, n=n)
                if n == 1:
                    s_lanes.stage(H, 'proof', 'invited', mate=MATE)
                sent = time.time()
            yield 1
    finally:
        do.ignoreAll()
    if not ans.get('added'):
        H.ev('FAIL', why='the bot never joined the crew in %d s' % INVITE_SECS, rejected=ans.get('rejected'),
             invites=n, mate=mate.poll(), mateLast=mate.last); return
    s_lanes.stage(H, 'proof', 'crew-made', band=la.getBandId(), mate=mate.poll())

    # 1b. meet the mate: walk to it (it follows once it sees me), so the launch happens beside it (run 4: 760 ft away)
    d = yield from meet(H)
    s_lanes.stage(H, 'proof', 'met', d=d, mate=mate.poll())
    if MODE == 'tele':
        yield from _tele(H, mate, t0, beat)
        return

    # 2. the ship: launch, then wait until the bot is aboard (it boards at the dinghy by itself)
    ships = list(la.getInventory().getShipDoIdList())
    if not ships:
        H.ev('FAIL', why='the captain owns no ship'); return
    if ships[0] == HOST_SHIP:
        H.ev('FAIL', why='the first ship is Host\'s %d' % HOST_SHIP); return
    ship = yield from sailing.launch(H, FROM, False)
    if ship is None:
        H.ev('FAIL', why='the captain could not launch (a SAIL-FAIL line says why)'); return
    sid = ship.doId
    s_lanes.stage(H, 'proof', 'launched', ship=sid)
    end, last, crew = time.time() + BOARD_SECS, None, []
    while time.time() < end:
        s = H.cr.doId2do.get(sid)
        crew = list(s.getCrew() or []) if s is not None else []
        if crew != last:
            H.ev('CREW-LIST', ship=sid, crew=crew)
            last = crew
        if MATE in crew:
            break
        beat('wait-aboard', crew=crew, mate=mate.poll())
        yield 2
    if MATE not in crew:
        H.ev('FAIL', why='the bot did not board in %d s' % BOARD_SECS, crew=last, mate=mate.poll(), mateLast=mate.last)
        return
    s_lanes.stage(H, 'proof', 'bot-aboard', ship=sid, crew=crew, mate=mate.poll())

    # 3. the sea: a real ship fight (s_shipfight picks a fair NPC ship and holds it on the beam) until the bot has
    #    fired a cannon and had AFTER_SHOT s more, a foe sank, or the sea time is up
    got = {}
    orig = H.ev

    def ev(kind, /, **kw):
        got[kind] = got.get(kind, 0) + 1
        return orig(kind, **kw)
    H.ev = ev
    picker = s_shipfight.Picker(H, time.time())
    g = s_shipfight.fight(H, sid, SEA_SECS, got, picker)
    shotT, why = None, None
    try:
        while True:
            try:
                y = next(g)
            except StopIteration as e:
                why = e.value
                break
            if shotT is None and mate.has('CANNON-SHOT'):
                shotT = time.time()
                s_lanes.stage(H, 'proof', 'bot-shot', mate=mate.poll())
            if shotT is not None and time.time() - shotT > AFTER_SHOT:
                g.close(); why = 'bot-shot'; break
            if time.time() - t0 > SECS - LAND_SECS - 150:
                g.close(); why = 'time-for-land'; break
            beat('sea', got=got, mate=mate.poll())
            yield y
    finally:
        H.ev = orig
    H.ev('SEA-END', why=why, got=got, mate=mate.poll(), gs=la.getGameState(), aboard=sailing.onShip(H))

    # 4. home: dock so the bot comes ashore with him
    yield from sailing.sail_to(H, FROM, why='home with the bot')
    if not (s_lanes.islandOf(H) == FROM and la.getGameState() == 'LandRoam'):
        yield ('upto', lambda: s_lanes.islandOf(H) == FROM and la.getGameState() == 'LandRoam', 60, 'ashore')
    if not (s_lanes.islandOf(H) == FROM and la.getGameState() == 'LandRoam'):
        H.ev('FAIL', why='could not get back ashore on %s' % FROM, area=H.area(), gs=la.getGameState(),
             sail=getattr(H, 'sailResult', None), mate=mate.poll()); return
    s_lanes.stage(H, 'proof', 'docked', here=H.area(), mate=mate.poll())
    yield ('upto', lambda: MATE in H.cr.doId2do, 60, 'bot ashore')

    # 5. the land: seek and fight enemies (s_landfight's pick + spawn camps) until the bot has hit one and had
    #    AFTER_FIGHT s more, or the land time is up
    nodes = s_landfight.spawnNodes(s_story.questSpots(), s_story.hereArea(H))
    tried, fighter, node, kills = set(), None, None, 0
    hitT, landT = None, time.time()
    H.ev('LAND-START', nodes=len(nodes), area=H.area(), lvl=s_fighter.myLevel(H))
    try:
        while time.time() - landT < LAND_SECS:
            if hitT is None and mate.has('LAND-FIGHT'):
                hitT = time.time()
                s_lanes.stage(H, 'proof', 'bot-fought', mate=mate.poll())
            if hitT is not None and time.time() - hitT > AFTER_FIGHT:
                break
            beat('land', kills=kills, mate=mate.poll())
            if (getattr(la, 'hp', 1) or 0) <= 0 or la.getGameState() in ('Death', 'Dying'):
                H.ev('KNOCKED-OUT', foe=fighter and fighter.foe.doId, area=H.area())
                if fighter is not None:
                    fighter.close(); fighter = None
                yield ('upto', lambda: la.getGameState() == 'LandRoam' and (getattr(la, 'hp', 0) or 0) > 0, 90, 'revived')
                continue
            lvl = s_fighter.myLevel(H)
            if fighter is not None:
                a = fighter.step()
                if a in ('kill', 'lost', 'stuck'):
                    H.ev('FOE-END', foe=fighter.foe.doId, how=a, hits=fighter.hits)
                    kills += a == 'kill'
                    fighter.close(); fighter = None
                yield BEAT
                continue
            foe, rows = s_landfight.pick(H, lvl)
            if foe is None:
                hitter, weak = s_landfight.attacker(H, rows, lvl)
                if hitter is not None and weak:
                    foe = hitter
            if foe is not None:
                H.walk_cancel()
                node = None
                me = la.getPos(H.render)
                fighter = s_fighter.Fighter(H, foe, (me[0], me[1], me[2]))
                continue
            if node is None:
                org = s_story.areaObj(H, s_story.hereArea(H))
                me = la.getPos(org) if org is not None else la.getPos(H.render)
                node = s_fighter.spawnPick(nodes, (me[0], me[1]), tried, lvl)
                if node is None:
                    if not nodes:
                        H.ev('LAND-NO-CAMP', why='no enemy in view and no spawn node in this area')
                        yield 5
                        continue
                    tried.clear()
                    yield 5
                    continue
                H.ev('SPAWN-PICK', node=node[3], spot=[round(v, 1) for v in node[:3]])
                node = tuple(node) + (org,)
            r = H.walk_poll(node[:3], ref=node[4], arrive=8.0, face=False, tag='to-spawn')
            if r is True or r is None:
                tried.add(tuple(node[:3]))
                node = None
                yield 1.0 if r is True else BEAT
                continue
            yield BEAT
    finally:
        if fighter is not None:
            fighter.close()
        H.walk_cancel()
    H.ev('LAND-END', kills=kills, secs=round(time.time() - landT), mate=mate.poll())

    # the verdict is the bot's: all four milestones in its own file
    yield ('upto', lambda: all(m in mate.poll() for m in MILESTONES), 20, 'bot milestones')
    ms = mate.poll()
    missing = [m for m in MILESTONES if m not in ms]
    if not missing:
        H.ev('PASS', what='the bot %d joined the crew, boarded, fired a cannon and fought on land beside the captain'
             % MATE, mate=ms, botBugs=mate.bugs, botVerdict=mate.verdict, secs=round(time.time() - t0))
    else:
        H.ev('FAIL', why='the bot missed: %s' % ', '.join(missing), mate=ms, botBugs=mate.bugs,
             botVerdict=mate.verdict, botLast=mate.last, secs=round(time.time() - t0))
    yield 10                     # the bot's own PASS line lands a moment after its last milestone
