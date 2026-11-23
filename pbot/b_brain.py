# pbots (11-22): the player bot's BRAIN - one state machine, run by walker.py as its step script
# (PROOF_SCRIPT=pbot\b_brain.py, started by pbot\run_bot.ps1 or, for the v1 proof, pbot\run_proof.ps1).
# v1 = the crew mate: it plays like a mate of the family's pirates.
#   SAFETY (knocked out, cutscene) > CREW ASK (an invite from a listed captain) > BOARD his launched ship >
#   CANNON at sea > FIGHT next to him on land > FOLLOW him > STAND / IDLE
# The WoW bot's lessons (WOW-LESSONS.md): ONE pick() with that priority list, a let-table of who may press what,
# leaving a state releases everything it held, every transition logged with its reason, hysteresis (start following
# past FOLLOW_FAR, stop inside FOLLOW_NEAR; keep the cannon CANNON_IDLE s after the last target), a heartbeat event
# every BEAT_EVERY s so the walker's 240 s HANG watchdog never fires, and bugs filed as they happen (bugfile.report).
# Rules it never breaks: joins only when asked by a listed captain (Host 100000170, Player1 100000656, Player2 100000665,
# plus PBOT_CAPTAINS for a test captain), never invites anyone, SpeedChat only, never hits a pirate or a player ship,
# never Host's pirate or ship (100000170 / 100000173) as a target, never a magic word.
# v2 (build 22h) = SKILLS: the whole game, one skill per area in pbot\skills\<area>.py (quests, sea, games, land, crew;
# skills\INTERFACE.md is the contract). Every WANT_EVERY s the brain asks each skill want() -> (score, why) or None:
# SAFETY >= 100 beats everything but a knock-out, in every game state (the jail); FREE PLAY >= 10 runs only with no
# crew, on foot, nothing else to do; a crewOk skill may run in STAND for CREW_SKILL_MAX s. The winner's flow() runs as
# the PLAY state (the walker's yield protocol) until it ends, runs over its limit, a crew needs the mate, a SAFETY skill
# outbids it, it crashes, or the bot goes down; then its cut(why) cleanup, at most CUT_MAX s. A stranded own ship (no
# crew, nothing wanted, or a crew to follow) is put away through sea.putAway in DECK.
# Env: PBOT_CAPTAINS "100000004" (extra captains, test only), PBOT_PROOF=1 (PASS after the four milestones:
# CREW-JOINED, ABOARD, CANNON-SHOT, LAND-FIGHT, with a picture of each), PBOT_WINDOW_OFF=1 (default: the window goes
# off at the avatar chooser; nothing is ever drawn except for pictures), PBOT_TAG (picture names), PBOT_SKILLS (unset
# = every registered skill, "quests,land" = those only, "" = none: the v1 crew mate alone).
import os, sys, time, math, random, traceback, builtins, collections, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
for _p in (HERE, HARNESS):
    if _p not in sys.path:
        sys.path.insert(0, _p)          # the harness pieces import each other from beside PROOF_SCRIPT
import bugfile, paths, sailing, s_lanes, s_crew2, s_fighter, s_bpfort, s_cannonpass, s_shipquest

BUILD = 'pbot-brain 2026-11-22j'
BEAT = 0.25                      # s between picks
BEAT_EVERY = 60.0                # heartbeat event: the walker calls a run with no event for 240 s a HANG
HOST, HOST_SHIP = 100000170, 100000173
PLAYER1, PLAYER2 = 100000656, 100000665
FAMILY = (HOST, PLAYER1, PLAYER2)
CAPTAINS = set(FAMILY) | {int(x) for x in os.environ.get('PBOT_CAPTAINS', '').replace(',', ' ').split() if x}
PROTECTED = {HOST, HOST_SHIP}  # never a target, whatever the game says
PROOF = os.environ.get('PBOT_PROOF') == '1'
WINDOW_OFF = os.environ.get('PBOT_WINDOW_OFF', '1') == '1'
TAG = os.environ.get('PBOT_TAG', 'PBOT')
HOME = os.environ.get('PBOT_HOME', '')      # an island uid: start there (a setup teleport, SETUP-TP) when not in a crew
SHOTS = r'C:\PiratesBots\out\pbots\shots'
MILESTONES = ('CREW-JOINED', 'ABOARD', 'CANNON-SHOT', 'LAND-FIGHT')
ACTIVE_GS = ('LandRoam', 'Battle', 'ShipPilot', 'WaterRoam', 'Cannon')   # game states in which the bot may act at all
                                 # (was PLAY in 22g; PLAY is the brain state a skill's flow runs in since 22h)
LAND = ('LandRoam', 'Battle')    # on foot: a drawn weapon puts the pirate in Battle (LocalPirate.toggleWeapon), still on land
# Game states a live BOARD flow drives the game through itself (the dinghy's ship list = DinghyInteract, then the
# boarding teleport/cutscene): while the flow runs, it owns them. Run 3 cut its own flow 0.4 s after the list opened.
LIST_STATE = 'DinghyInteract'
FOLLOW_NEAR, FOLLOW_FAR = 6.0, 10.0   # ft: stop following inside NEAR, start again past FAR
FOLLOW_ROUTE = 40.0              # ft: a captain farther than this is followed by a planned route (paths.walk_route: round
                                 # buildings, along piers); a straight leg only inside it. Run 7's straight leg from a pier
                                 # to the captain 309 ft away walked the mate off the pier into the water in 3 s
FOLLOW_MAXR = 3000.0             # ft: a captain farther than this is not placed on this island yet (run 5: 48 million ft
                                 # while he sat in the district node); the planner never gets such a goal
FOLLOW_RETRY = 20.0              # s before another route after one that found no way
WATER_WAIT = 15.0                # s in the water (WaterRoam) with a crew before the mate takes the island teleport back to
                                 # land; pick() parks WaterRoam in WAIT, which did nothing (run 7 sat 230 s in the water)
WATER_RETRY = 60.0               # s before another try after a failed one
CAPTAIN_NEAR = 60.0              # ft: a launched captain still this close is walking to the dinghy: walk with him
FIGHT_R = 40.0                   # ft: an enemy within this of the captain or me, fighting one of us, is our fight
CANNON_R = 3000.0                # ft: NPC ships farther than this are not a cannon target. Measured 11-22 (cannon_reach.py on
                                 # the game's own table): the deck cannon's round shot leaves at 780 ft/s (power 1300 x 0.6)
                                 # and reaches ~3500 ft at the 24 deg pitch limit. Run 6's captain held its foe at 1340-1890 ft
                                 # (SHIPFIGHT_RANGE 1400): the old 1200 ft cutoff never saw it and the mate stood in DECK
CANNON_IDLE = 20.0               # s with nothing to shoot before the mate leaves the cannon
CANNON_MAN_WAIT = 10.0           # s for requestInteraction to put him at the cannon
DECK_SEE = 30.0                  # s between deck-see lines (what the mate sees from the deck: run 6 left no trace of why it never shot)
BOARD_RETRY = 25.0               # s between dinghy asks while the crew ship is not offered yet (s_crew2.OFFER_EVERY)
FLOW_MAX = 180.0                 # s a BOARD sub-flow may run before it is cut
LOST_SAY = 300.0                 # s lost before one 'Hello?' on SpeedChat
LOST_WALK = 10.0                 # s lost (with a crew) before the mate heads for the docks: run 4 stood 760 ft from its
                                 # captain for the whole run; at the dinghies a launching captain finds it
DOCK_RETRY = 60.0                # s before another dock walk after one that found no way (twice that after one that did)
LOOK_EVERY = (15.0, 40.0)        # s between idle looks (a short turn on the turn key)
IDLE_LOOK_SECS = 180.0           # s an idle bot looks about; then it stands still and the game's own auto-AFK (afk-delay
                                 # 600 s without a key) puts it to sleep like an idle player; a crew invite wakes it
SC_HI, SC_HELLO_Q, SC_THANKS = 100, 109, 500    # SpeedChat ids: 'Hi!', 'Hello?', 'Thanks!'
# who may press what in each state: the let-table. A press outside it is refused and logged (let-refused).
LET = {'DOWN': set(), 'WAIT': set(), 'IDLE': {'look'}, 'LOST': {'look', 'walk'}, 'STAND': {'look'},
       'FOLLOW': {'walk'}, 'BOARD': {'walk', 'dinghy'}, 'DECK': {'look', 'sail'}, 'CANNON': {'cannon'},
       'FIGHT': {'walk', 'sword', 'tonic'},
       'PLAY': {'walk', 'sword', 'tonic', 'look', 'dinghy', 'cannon', 'sail'}}   # a skill plays the whole game
# ---- skills (v2, build 22h; the contract is skills\INTERFACE.md) ----
SKILLS_DIR = os.path.join(HERE, 'skills')
SKILLS = {'quests': ('quests', 'Quests'), 'sea': ('sea', 'Sea'), 'games': ('games', 'Games'),
          'land': ('land', 'Land'), 'crew': ('crew', 'Crew')}    # name -> (module in skills\, class)
SKILL_LIMIT = {'games': 1800, 'sea': 1200, 'quests': 600, 'land': 600}   # s a flow may run (the skill's own .limit wins)
# A skill with crewOwn = True (crew.py, 22i) is the crew's own: pick() runs it while crewed with the captain out of view
# (before LOST), the crew-cut spares it (limit, safety, error and down still cut it); a skill's optional tick() is called
# every WANT_EVERY s in every state but DOWN (a watch: cheap reads, no presses).
SKILL_LIMIT_DEFAULT = 300.0
WANT_EVERY = 2.0                 # s between want() rounds (a skill that just ended or was cut is not re-asked for one round)
WANT_MIN = 10.0                  # the FREE PLAY floor: a want below it is ignored
SAFETY = 100.0                   # a want at or over this beats every crew state but a knock-out, in every game state (the jail)
CUT_MAX = 60.0                   # s a skill's cut(why) cleanup may run
CREW_SKILL_MAX = 30.0            # s a crewOk skill may run in STAND before the crew gets the mate back
SKILL_RETRY = 5.0                # s before a skill that crashed is asked again
WANT_ERRORS = 3                  # want() crashes before a skill is unloaded for this game
JAIL = ('ThrownInJail',)         # game states that mean the jail (land's SAFETY want)
PUTAWAY_RETRY = 60.0             # s between tries at putting my own stranded ship away (DECK, no crew / a crew to follow)


def early(ev):
    """At the avatar chooser, before the world loads: window off, so nothing is ever uploaded or drawn (MEAS6: ~200 MB)."""
    try:
        if WINDOW_OFF:
            builtins.base.win.setActive(False)
        ev('brain-early', window_off=WINDOW_OFF, build=BUILD)
    except Exception:
        ev('brain-early-error', tb=traceback.format_exc()[-400:])


class Brain:
    def __init__(self, H):
        from direct.showbase.DirectObject import DirectObject
        from pirates.band import BandConstance
        self.BC = BandConstance
        self.H, self.la, self.cr, self.B = H, H.la, H.cr, builtins.base
        self.state, self.since, self.why = 'IDLE', time.time(), 'start'
        self.hist = collections.deque(maxlen=40)       # the last transitions, for bug files
        self.lastBeat = time.time()
        self.seen = set()                              # milestones reached
        self.passed = False
        self.fighter = None                            # s_fighter.Fighter while FIGHT
        self.cannon, self.cannonT, self.cannonLast, self.shots = None, 0.0, 0.0, 0
        self.trk = s_cannonpass.Track()                # NPC ship velocities, so the cannon leads a moving target
        self.seeT = 0.0                                # last deck-see line
        self.seeErrT = 0.0                             # last npcships-error line
        self.flow, self.flowT, self.flowName = None, 0.0, ''
        self.boardNext, self.boardWhy = 0.0, ''       # next dinghy ask, and why the last one ended (pick's STAND reason)
        self.dockNext = 0.0                            # next dock walk while lost
        self.followNext, self.followFarT = 0.0, 0.0    # next route to a far captain; last 'captain not placed yet' line
        self.waterNext = 0.0                           # next try at getting out of the water (st_wait)
        self.bugCount = {}
        self.lookT = time.time() + random.uniform(*LOOK_EVERY)
        self.lookKey = None
        self.looks = 0                                 # idle look key taps so far (the beat shows them: run 2 fell asleep)
        self.wasInBand = s_crew2.inBand(self.la)
        self.acceptT, self.lostT, self.lostSaid, self.downT, self.downs = None, None, False, None, 0
        self.waitSaid = None
        self.listCloseT = 0.0                          # last try at closing a stray dinghy list (st_wait)
        self.sword = False
        # skills (v2): name -> object; when each last ran; its last result; the one running in PLAY
        self.skills, self.ran, self.results = {}, {}, {}
        self.skill, self.skillScore, self.skillT, self.playWhy = None, 0.0, 0.0, ''
        self.playPick = None                           # (score, name, why) pick() chose for PLAY, taken by st_play
        self.wants, self.wantsAt, self.lastWinner = [], 0.0, None
        self.hold, self.wantErr = {}, {}               # name -> not asked before this time; want() crash counts
        self.tickT, self.tickErr = 0.0, {}             # last tick() round; tick() crash counts (22i)
        self.lastCap = None                            # the captain pick() last saw (crewWatch tells a kick from his logoff)
        self.cutGen, self.cutT = None, 0.0             # a skill's cut(why) cleanup generator, and when it started
        self.worldT, self.worldCache = 0.0, None
        self.cannonManned = False                      # the game put me at the cannon (localAvatarUsingWeapon went true)
        self.putAwaySaid, self.putAwayNext = False, 0.0
        self.do = DirectObject()
        self.do.accept(BandConstance.BandInvitationEvent, self.onInvite)
        os.makedirs(SHOTS, exist_ok=True)
        self.loadSkills()

    # ---------- plumbing ----------
    def ev(self, name, /, **kw):      # positional-only like walker.ev: BRAIN/CREW-* events carry a name= field
        self.H.ev(name, **kw)

    def may(self, press):
        if press in LET.get(self.state, ()):
            return True
        self.ev('let-refused', press=press, state=self.state)
        return False

    def milestone(self, name, /, **kw):
        if name in self.seen:
            return
        self.seen.add(name)
        shot = self.shot(name) if PROOF else ''
        self.ev('MILESTONE', name=name, seen=sorted(self.seen), shot=shot, **kw)
        if PROOF and not self.passed and all(m in self.seen for m in MILESTONES):
            self.passed = True
            self.ev('PASS', what='crew mate v1: joined the crew, boarded the ship, fired a cannon, fought on land',
                    shots=self.shots, secs=round(time.time() - self.since))

    def shot(self, tag):
        """A picture even with the window off: on, two frames, save, off again. -> path or ''."""
        from panda3d.core import Filename
        B = self.B
        try:
            was = B.win.isActive()
            if not was:
                B.win.setActive(True)
            for _ in range(2):
                B.graphicsEngine.renderFrame()
            fn = os.path.join(SHOTS, '%s-%s-%s.jpg' % (TAG, tag, time.strftime('%H%M%S')))
            ok = B.win.saveScreenshot(Filename.fromOsSpecific(fn))
            if not was:
                B.win.setActive(False)
            return fn if ok else ''
        except Exception:
            self.ev('shot-failed', tag=tag, tb=traceback.format_exc()[-300:])
            return ''

    def where(self):
        """'Port Royal at (323, 24), game state LandRoam, brain STAND', or aboard 'aboard DistributedPlayerShip 100000750
        (Sea) at (x, y), ...': a string for bug files (H.area() is a tuple; bugfile formats where with %s into a line and
        raised TypeError on it, so run 4's own stuck bug was never filed). H.P may return an 'err ...' string."""
        try:
            a, p = self.H.area(), self.H.P(self.la)
            name = (a[2] or a[1] or a[0]) if a else 'nowhere'
            at = ' at (%d, %d)' % (p[0], p[1]) if isinstance(p, (list, tuple)) and len(p) >= 2 else ''
            ship = self.shipObj() if self.onDeck() else None
            if ship is not None:
                head = 'aboard %s %s (%s)' % (type(ship).__name__, getattr(ship, 'doId', '?'), name)
            else:
                head = str(name)
            return '%s%s, game state %s, brain %s' % (head, at, self.gs(), self.state)
        except Exception:
            return '?'

    def quick(self, on):
        """The body's clock: the move rate while a flow plans or walks, the idle rate otherwise (walker Helper.fast)."""
        try:
            self.H.fast('flow', on)
        except Exception:
            pass

    def bug(self, kind, key, tag, what, tb=''):
        """File a bug (bugfile.report) with the last transitions and, the first time, a picture. The same key is filed
        at most three times by one bot game: the file counts repeats itself, the bot must not spam."""
        n = self.bugCount.get(key, 0) + 1
        self.bugCount[key] = n
        if n > 3:
            return
        try:
            shot = self.shot('bug') if n == 1 else ''
            events = ['%s %s -> %s: %s' % h for h in list(self.hist)[-12:]]
            sig, path, count = bugfile.report(kind, key, tag, what, where=self.where(),
                                              pirate='%s %s' % (getattr(self.la, 'name', '') or '?', self.la.doId),
                                              source='pbot %s' % BUILD, tb=tb, events=events, shot=shot)
            self.ev('BUG', sig=sig, kind=kind, tag=tag, what=what[:160], count=count)
        except Exception:
            self.ev('bug-report-failed', tb=traceback.format_exc()[-300:])

    def beat(self):
        la = self.la
        self.lastBeat = time.time()
        cap = self.captain()
        self.ev('beat', state=self.state, since=round(time.time() - self.since), gs=self.gs(), hp=getattr(la, 'hp', None),
                la=self.H.P(la), area=self.H.area(), crew=bool(cap), captain=cap[0] if cap else None,
                seen=sorted(self.seen), shots=self.shots, downs=self.downs, looks=self.looks,
                afk=bool(getattr(la, 'isAFK', False)), skill=self.skill, want=self.lastWinner,
                skills=sorted(self.skills))

    # ---------- the world ----------
    def gs(self):
        try:
            return self.la.getGameState()
        except Exception:
            return '?'

    def down(self):
        la = self.la
        return (getattr(la, 'hp', 0) or 0) <= 0 or self.gs() in ('Death', 'Dying')

    def onDeck(self):
        """Aboard = my parent object is a ship (a cannon I hold counts too). Never `la.ship`: the band sets that on land
        as well (run 2 stood on the dock in DECK for 4 minutes while the captain waited at sea)."""
        if self.cannon is not None:
            return True
        try:
            p = self.la.getParentObj()
        except Exception:
            return False
        return p is not None and 'Ship' in type(p).__name__

    def wake(self, why):
        """Wake from the game's own auto-AFK sleep: LocalPirate goes AFK after afk-delay (600 s) without a key and plays
        the sleep emote (game state Emote). A player wakes by pressing a key, checkInputState -> delayAFK -> toggleAFK ->
        LandRoam; this takes the same path. Run 2 lay asleep in WAIT for 15 minutes (WAIT may press nothing)."""
        la = self.la
        if time.time() - getattr(self, 'wakeT', 0) < 5:
            return
        self.wakeT = time.time()
        afk = bool(getattr(la, 'isAFK', False))
        try:
            if afk:
                la.delayAFK()
            elif self.gs() == 'Emote':
                la.b_setGameState('LandRoam')
            self.ev('wake', why=why, afk=afk, gs=self.gs())
        except Exception:
            self.ev('wake-failed', why=why, afk=afk, tb=traceback.format_exc()[-200:])

    def closeList(self, why):
        """Close an open dinghy ship list the game's own way: its panel's close button (closePanel -> the dinghy's
        requestExit -> the AI ends the interaction -> exitUse puts the game state back). -> True when one was found."""
        for d in list(self.cr.doId2do.values()):
            if 'Dinghy' not in type(d).__name__:
                continue
            panel = getattr(d, 'shipSelection', None)
            try:
                st = d.getCurrentOrNextState()
            except Exception:
                st = None
            if panel is None and st not in ('Use', 'Waiting'):
                continue
            try:
                if panel is not None:
                    panel.closePanel()
                else:
                    d.requestExit()
                self.ev('list-closed', dinghy=d.doId, how='closePanel' if panel is not None else 'requestExit',
                        dinghyState=st, why=why, gs=self.gs())
                return True
            except Exception:
                self.ev('list-close-failed', dinghy=d.doId, why=why, tb=traceback.format_exc()[-200:])
        self.ev('list-close-none', why=why, gs=self.gs())
        return False

    def captain(self):
        """(captainId, bandMember) of my crew, or None. If I am the leader myself I leave: a bot never leads the boys."""
        la = self.la
        if not s_crew2.inBand(la):
            return None
        try:
            from pirates.band.DistributedBandMember import DistributedBandMember
            members = DistributedBandMember.getBandSetLocalAvatar() or ()
        except Exception:
            return None
        for bm in members:
            if getattr(bm, 'isManager', 0):
                if bm.avatarId == la.doId:
                    self.leaveCrew('I would be the leader')
                    return None
                return bm.avatarId, bm
        return None

    def leaveCrew(self, why):
        if time.time() - getattr(self, 'leftT', 0) < 30:
            return
        self.leftT = time.time()
        self.ev('CREW-LEAVE', why=why)
        try:
            self.cr.PirateBandManager.d_requestRemove(self.la.doId)
        except Exception:
            self.ev('crew-leave-failed', tb=traceback.format_exc()[-200:])

    def dist(self, o):
        try:
            return (o.getPos(self.H.render) - self.la.getPos(self.H.render)).length()
        except Exception:
            return 1e9

    def launched(self, bm):
        try:
            info = bm.getShipInfo()
            return bool(info and info[0])
        except Exception:
            return False

    def shipObj(self):
        """The ship I stand on (my parent object when it is a ship), else the band's la.ship, else None."""
        try:
            p = self.la.getParentObj()
        except Exception:
            p = None
        if p is not None and 'Ship' in type(p).__name__:
            return p
        return getattr(self.la, 'ship', None)

    def npcShips(self):
        """[(dist, ship)] nearest first, measured from the ship I stand on (never from la.ship alone: run 6 could not
        tell whether it was None on the mate; npcShips(H, None) raises and a bare except made every fight 'nothing to
        shoot'). An error is logged, once a minute."""
        try:
            return s_shipquest.npcShips(self.H, self.shipObj() or self.la)
        except Exception as e:
            if time.time() - self.seeErrT > 60:
                self.seeErrT = time.time()
                self.ev('npcships-error', err=repr(e)[:200])
            return []

    def cannonTarget(self, capObj):
        """The NPC ship to shoot: the captain's own target when it is one and afloat, else the nearest within CANNON_R."""
        t = getattr(capObj, 'currentTarget', None) if capObj is not None else None
        if t is not None and 'NPCShip' in type(t).__name__ and t.doId not in PROTECTED:
            hp = s_shipquest.hpOf(t) if hasattr(s_shipquest, 'hpOf') else None
            if hp is None or hp > 0:
                return t
        for d, o in self.npcShips():
            if d <= CANNON_R and o.doId not in PROTECTED:
                return o
        return None

    def deckSee(self, capObj):
        """deck-see: the three nearest NPC ships (doId, ft, hp), what I stand on, la.ship, the cannons in view and the
        captain's target, so a fight with no shot shows why."""
        la, H = self.la, self.H
        try:
            near = [[o.doId, round(d), s_shipquest.hpOf(o)] for d, o in self.npcShips()[:3]]
        except Exception as e:
            near = repr(e)[:120]
        try:
            p = la.getParentObj()
        except Exception:
            p = None
        t = getattr(capObj, 'currentTarget', None) if capObj is not None else None
        try:
            ncan = len(s_bpfort.cannons(H))
        except Exception:
            ncan = None
        self.ev('deck-see', near=near, parent=type(p).__name__ if p is not None else None,
                parentId=getattr(p, 'doId', None), laShip=getattr(getattr(la, 'ship', None), 'doId', None),
                cannons=ncan, capTarget=type(t).__name__ if t is not None else None, reach=CANNON_R,
                la=H.P(la))

    def fightTarget(self, capObj):
        """The enemy to fight on land: the captain's target, or an enemy within FIGHT_R that is fighting him or me."""
        la = self.la
        rows = s_fighter.foeRows(self.H)
        if not rows:
            return None
        byId = {r[0]: r for r in rows}
        t = getattr(capObj, 'currentTarget', None)
        if t is not None and getattr(t, 'doId', None) in byId and t.doId not in PROTECTED:
            return t.doId
        best = None
        for doId, d, hp, lvl, xy in rows:
            if doId in PROTECTED or (hp or 0) <= 0:
                continue
            o = self.cr.doId2do.get(doId)
            tgt = getattr(o, 'currentTarget', None)
            if tgt is None or getattr(tgt, 'doId', None) not in (la.doId, getattr(capObj, 'doId', None)):
                continue
            dc = self.dist(o) if capObj is None else min(d, (o.getPos(self.H.render) - capObj.getPos(self.H.render)).length())
            if dc <= FIGHT_R and (best is None or d < best[1]):
                best = (doId, d)
        return best[0] if best else None

    # ---------- crew ask ----------
    def onInvite(self, av, name, *a):
        mgr = self.cr.PirateBandManager
        try:
            if av in CAPTAINS and not s_crew2.inBand(self.la):
                mgr.d_invitationResponce(av, self.BC.outcome_ok)
                self.acceptT = time.time()
                self.ev('CREW-ACCEPT', av=av, name=name)
            else:
                mgr.d_invitationResponce(av, self.BC.outcome_declined)
                self.ev('CREW-DECLINE', av=av, name=name,
                        why='not a listed captain' if av not in CAPTAINS else 'already in a crew')
        except Exception:
            self.bug('traceback', 'crew invite answer: ' + traceback.format_exc().strip().splitlines()[-1][:100], 'BOT',
                     'answering a crew invite from %s crashed' % av, tb=traceback.format_exc())

    def crewWatch(self):
        now = s_crew2.inBand(self.la)
        if now and not self.wasInBand:
            secs = None if self.acceptT is None else round(time.time() - self.acceptT, 1)
            cap = self.captain()
            self.ev('CREW-JOINED', secs_after_accept=secs, captain=cap[0] if cap else None)
            self.milestone('CREW-JOINED', secs=secs)
            try:
                self.la.b_setSC(SC_HI)
            except Exception:
                pass
        elif self.wasInBand and not now:
            # the game sends setBandId(0, 0) for a kick, the captain's logoff and a dissolved band alike (a crew of one is
            # no crew: DistributedPirateBandManagerAI.removeMember); told apart by whether I asked (leaveCrew within 5 s)
            # and whether the captain's pirate is still in view
            cid = self.lastCap
            if time.time() - getattr(self, 'leftT', 0) < 5:
                why = 'left'
            elif cid is not None and cid in self.cr.doId2do:
                why = 'kicked'
            else:
                why = 'captain gone'
            self.ev('CREW-LEFT', why=why, captain=cid)
            self.acceptT, self.lastCap = None, None
        self.wasInBand = now

    def tickSkills(self):
        """Every WANT_EVERY s, in every state but DOWN: each skill's optional tick() (a watch: cheap reads, no presses;
        crew.py's quest-credit witness). A tick() that raises files one BOT bug and, at WANT_ERRORS, unloads the skill
        for this game, like want()."""
        now = time.time()
        if now - self.tickT < WANT_EVERY or self.state == 'DOWN':
            return
        self.tickT = now
        for name, sk in list(self.skills.items()):
            tick = getattr(sk, 'tick', None)
            if tick is None:
                continue
            try:
                tick()
            except Exception:
                tb = traceback.format_exc()
                last = tb.strip().splitlines()[-1][:120]
                n = self.tickErr[name] = self.tickErr.get(name, 0) + 1
                self.bug('traceback', '%s-tick: %s' % (name, last), 'BOT',
                         'skill %s crashed in tick() (%d of %d before it is unloaded)' % (name, n, WANT_ERRORS), tb=tb)
                if n >= WANT_ERRORS:
                    del self.skills[name]
                    self.ev('skill-unloaded', name=name, why='tick() crashed %d times' % n)

    # ---------- skills (v2) ----------
    def loadSkills(self):
        """Import and build every registered skill (PBOT_SKILLS unset), the listed ones ("quests,land"), or none ("").
        Each is loaded from its own file in skills\ under the module name pbskill_<name>, so a module of the same name
        anywhere else on sys.path (the game tree, the harness) can never shadow it; skills\ goes on sys.path too, so a
        skill may import a sibling helper (bugreport) by name. A skill that fails to import is logged and left out."""
        env = os.environ.get('PBOT_SKILLS')
        names = list(SKILLS) if env is None else [n for n in env.replace(',', ' ').split() if n]
        if SKILLS_DIR not in sys.path:
            sys.path.insert(0, SKILLS_DIR)
        for name in names:
            if name not in SKILLS:
                self.ev('skill-import-failed', name=name, err='not a registered skill (%s)' % ', '.join(SKILLS))
                continue
            mod, cls = SKILLS[name]
            try:
                path = os.path.join(SKILLS_DIR, mod + '.py')
                spec = importlib.util.spec_from_file_location('pbskill_' + mod, path)
                m = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = m
                spec.loader.exec_module(m)
                sk = getattr(m, cls)(self)
            except Exception:
                tb = traceback.format_exc()
                self.ev('skill-import-failed', name=name, module=mod, err=tb.strip().splitlines()[-1][:160], tb=tb[-600:])
                continue
            self.skills[name] = sk
            self.ev('skill-loaded', name=name, module=mod, cls=cls, limit=self.limitOf(name),
                    crewOk=bool(getattr(sk, 'crewOk', False)), crewOwn=bool(getattr(sk, 'crewOwn', False)),
                    cut=hasattr(sk, 'cut'), tick=hasattr(sk, 'tick'))

    def limitOf(self, name):
        return float(getattr(self.skills.get(name), 'limit', None) or SKILL_LIMIT.get(name, SKILL_LIMIT_DEFAULT))

    def onMyShip(self):
        """Aboard one of my own ships (sailing.onShip: the parent object's doId is in my inventory's ship list)."""
        try:
            return bool(sailing.onShip(self.H))
        except Exception:
            return False

    def askWants(self):
        """One want() round, at most every WANT_EVERY s: [(score, name, why)] with score >= WANT_MIN. A skill on hold
        (it just ended, was cut, or crashed) is skipped; a want() that raises files one BOT bug and, at WANT_ERRORS,
        unloads the skill for this game; a bad return (not (score, why)) is logged and ignored."""
        now = time.time()
        if now - self.wantsAt < WANT_EVERY:
            return self.wants
        self.wantsAt = now
        out = []
        for name, sk in list(self.skills.items()):
            if self.hold.get(name, 0.0) > now:
                continue
            try:
                w = sk.want()
            except Exception:
                tb = traceback.format_exc()
                last = tb.strip().splitlines()[-1][:120]
                n = self.wantErr[name] = self.wantErr.get(name, 0) + 1
                self.bug('traceback', '%s-want: %s' % (name, last), 'BOT',
                         'skill %s crashed in want() (%d of %d before it is unloaded)' % (name, n, WANT_ERRORS), tb=tb)
                if n >= WANT_ERRORS:
                    del self.skills[name]
                    self.ev('skill-unloaded', name=name, why='want() crashed %d times' % n)
                continue
            if w is None:
                continue
            try:
                score, why = w
                score = float(score)
            except Exception:
                self.ev('skill-want-bad', name=name, got=repr(w)[:120])
                continue
            if score >= WANT_MIN:
                out.append((score, name, str(why)))
        self.wants = out
        if out:
            best = max(out, key=lambda t: (t[0], -self.ran.get(t[1], 0.0)))
            if best[1] != self.lastWinner:
                self.ev('skill-want', name=best[1], score=best[0], why=best[2], wants=len(out))
            self.lastWinner = best[1]
        elif self.lastWinner is not None:
            self.lastWinner = None
            self.ev('skill-want', name=None, wants=0)
        return out

    def poll(self, minScore=WANT_MIN, crewOk=False, own=False):
        """The best want at or over minScore -> (score, name, why) or None. crewOk=True keeps only the skills that may
        run beside a crew; own=True only the crew's own (crewOwn: crew.py, run while the captain is out of view). Ties go
        to the skill that ran longest ago."""
        best = None
        for score, name, why in self.askWants():
            if score < minScore:
                continue
            if crewOk and not getattr(self.skills.get(name), 'crewOk', False):
                continue
            if own and not getattr(self.skills.get(name), 'crewOwn', False):
                continue
            k = (score, -self.ran.get(name, 0.0))
            if best is None or k > best[0]:
                best = (k, (score, name, why))
        return best[1] if best else None

    def world(self):
        """The shared bot state for skills (INTERFACE.md section 5), cached for 1 s. Every read is guarded: a key whose
        read fails holds its default, never an exception."""
        now = time.time()
        if self.worldCache is not None and now - self.worldT < 1.0:
            return self.worldCache
        la, H = self.la, self.H
        w = {}

        def put(k, fn, dflt=None):
            try:
                w[k] = fn()
            except Exception:
                w[k] = dflt
        w['t'] = now
        put('gs', self.gs, '?')
        w['state'], w['since'] = self.state, round(now - self.since, 1)
        put('island', lambda: s_lanes.islandOf(H) or sailing.hereUid(H), None)

        def areaName():
            a = H.area()
            return (a[2] or a[1] or a[0]) if a else None
        put('area', areaName, None)
        put('areaClass', lambda: (H.area() or (None,))[0], None)
        put('pos', lambda: H.P(la), None)
        put('hp', lambda: getattr(la, 'hp', None), None)
        put('maxHp', lambda: getattr(la, 'maxHp', None), None)
        put('gold', lambda: la.getInventory().getGoldInPocket(), None)
        put('level', la.getLevel, None)

        def crew():
            cap = self.captain()
            from pirates.band.DistributedBandMember import DistributedBandMember
            members = DistributedBandMember.getBandSetLocalAvatar() or ()
            return {'captain': cap[0] if cap else 0, 'members': [bm.avatarId for bm in members]}
        put('crew', crew, {'captain': 0, 'members': []})
        put('onDeck', self.onDeck, False)

        def shipId():
            p = la.getParentObj()
            return p.doId if p is not None and 'Ship' in type(p).__name__ else 0
        put('ship', shipId, 0)
        put('myShip', lambda: w['ship'] if w['ship'] and self.onMyShip() else 0, 0)
        put('quests', lambda: list(H.qids()), [])

        def jailCell():
            c = int(getattr(la, 'jailCellIndex', 100))
            return c if 0 <= c < 100 else -1
        put('jailCell', jailCell, -1)
        w['jailed'] = w['gs'] in JAIL or w['areaClass'] == 'DistributedJailInterior' or w['jailCell'] >= 0
        self.worldT, self.worldCache = now, w
        return w

    # ---------- pick ----------
    def pick(self):
        la = self.la
        gs = self.gs()
        if self.down():
            return 'DOWN', 'knocked out'
        if self.state == 'PLAY' and self.skill is not None:
            # a running skill owns the game states its flow drives through; st_play's cutReason() ends it (crew, safety,
            # limit, error) and a knock-out (above) cuts it
            return 'PLAY', self.playWhy
        safe = self.poll(SAFETY)
        if safe is not None:
            # SAFETY (>= 100): the jail, a cutscene to skip... beats every crew state in every game state
            self.playPick = safe
            return 'PLAY', '%s: %s' % (safe[1], safe[2])
        if self.flow is not None and self.state == 'BOARD':
            # a live BOARD flow owns the states it drives the game through (the ship list, the boarding teleport);
            # only SAFETY (above), a lost crew, and FLOW_MAX in st_board cut it
            if self.captain() is None:
                return 'IDLE', 'no crew'
            return 'BOARD', 'boarding, game state %s' % gs
        if self.flow is not None and self.state == 'DECK':
            # my own ship is being put away (sea.putAway as a DECK flow): a free-play want must not cut it half-way
            return 'DECK', 'putting my own ship away, game state %s' % gs
        if gs == 'Emote' or getattr(la, 'isAFK', False):
            # the game's auto-AFK sleep (or an emote): an idle bot sleeps like an idle player; one with a crew, or with
            # something to do, wakes up. isAFK can go true outside Emote too (run 3: asleep in the dinghy list)
            if self.captain() is None:
                if self.poll(WANT_MIN) is not None:
                    self.wake('something to do')
                    return 'WAIT', 'waking up'
                return 'IDLE', 'asleep (AFK), no crew'
            self.wake('I have a crew to follow')
            return 'WAIT', 'waking up'
        if gs not in ACTIVE_GS:
            return 'WAIT', 'game state %s' % gs
        cap = self.captain()
        if cap is None:
            # FREE PLAY: no crew, on foot, nothing else to do -> the best want (>= WANT_MIN) plays
            want = self.poll(WANT_MIN) if gs in LAND else None
            if want is not None:
                self.playPick = want
                return 'PLAY', '%s: %s' % (want[1], want[2])
            if self.onMyShip():
                return 'DECK', 'on my own ship with no crew and nothing to do: putting it away'
            if gs not in LAND:
                return 'WAIT', 'game state %s, no crew' % gs   # WaterRoam: st_wait takes the island teleport back to land
            return 'IDLE', 'no crew'
        cid, bm = cap
        self.lastCap = cid
        capObj = self.cr.doId2do.get(cid)
        if self.onDeck():
            if self.cannon is None and self.onMyShip():
                return 'DECK', 'on my own ship with a crew to follow: putting it away'
            if self.cannon is not None and time.time() - self.cannonLast < CANNON_IDLE:
                return 'CANNON', 'at the cannon'
            if self.cannonTarget(capObj) is not None:
                return 'CANNON', 'an enemy ship in range'
            return 'DECK', 'aboard, nothing to shoot'
        if gs not in LAND:
            return 'WAIT', 'game state %s' % gs    # WaterRoam too: st_wait takes the island teleport back to land
        near = self.dist(capObj) if capObj is not None else None
        if self.launched(bm) and (near is None or near > CAPTAIN_NEAR):
            if self.flow is not None or time.time() >= self.boardNext:
                return 'BOARD', 'the captain launched his ship'
            return 'STAND', '%s, trying the dinghy again in %ds' % (self.boardWhy or 'crew ship not offered yet',
                                                                     self.boardNext - time.time())
        if capObj is None:
            # the captain is out of view (another island, the sea, a building): the crew's own skill goes first (crew.py:
            # the game's 'go to' teleport, TELE_AFTER s in); LOST walks to the docks and says Hello? otherwise
            want = self.poll(WANT_MIN, crewOk=True, own=True)
            if want is not None:
                self.playPick = want
                return 'PLAY', '%s: %s' % (want[1], want[2])
            return 'LOST', 'captain not in view'
        foe = self.fightTarget(capObj)
        if foe is not None:
            return 'FIGHT', 'enemy %d' % foe
        if near > FOLLOW_FAR or (self.state == 'FOLLOW' and near > FOLLOW_NEAR):
            return 'FOLLOW', 'captain %.0f ft away' % near
        # next to the captain with nothing to do: a crewOk skill may play for CREW_SKILL_MAX s (cutReason)
        want = self.poll(WANT_MIN, crewOk=True)
        if want is not None:
            self.playPick = want
            return 'PLAY', '%s: %s' % (want[1], want[2])
        return 'STAND', 'next to the captain'

    def switch(self, to, why):
        frm = self.state
        self.release(frm, to)
        self.hist.append((time.strftime('%H:%M:%S'), frm, to, why))
        self.state, self.since, self.why = to, time.time(), why
        if to == 'DOWN':
            self.downs += 1
            self.downT = time.time()
        if to == 'LOST':
            self.lostT = time.time()
        self.ev('STATE', frm=frm, to=to, why=why, gs=self.gs(), la=self.H.P(self.la))

    def release(self, frm, to=None):
        """Leaving a state releases everything it held: the fight, the cannon, held keys, a half-done sub-flow, a skill.
        `to` is the state being entered (DOWN, END for the game closing, WAIT after a brain error): a running skill is
        told why it was cut."""
        if self.fighter is not None:
            try:
                self.fighter.close()
            except Exception:
                pass
            self.fighter = None
        if self.cannon is not None:
            try:
                if getattr(self.cannon, 'localAvatarUsingWeapon', 0):
                    self.cannon.requestExit()
            except Exception:
                pass
            self.ev('cannon-leave', shots=self.shots, state=frm)
            self.cannon, self.cannonManned = None, False
        if self.skill is not None:
            # a skill cut from outside its own flow (knocked out, the game closing, a brain error): close its generators,
            # give its cut() one synchronous call (no beats are left to drive a cleanup generator) and hold it one round
            name, sk = self.skill, self.skills.get(self.skill)
            why = 'down' if to == 'DOWN' else 'end' if to == 'END' else 'error'
            for g in (self.flow, self.cutGen):
                try:
                    if g is not None:
                        g.close()
                except Exception:
                    pass
            self.flow, self.cutGen = None, None
            now = time.time()
            self.ran[name] = now
            self.results[name] = ('cut', why)
            self.ev('skill-cut', name=name, why=why, secs=round(now - self.skillT), state=frm, to=to, cleanup='closed')
            if sk is not None and hasattr(sk, 'cut'):
                try:
                    g = sk.cut(why)
                    if hasattr(g, 'close'):
                        g.close()
                except Exception:
                    self.ev('skill-cut-error', name=name, why=why, tb=traceback.format_exc()[-300:])
            self.skill, self.playWhy, self.playPick = None, '', None
            self.hold[name] = max(self.hold.get(name, 0.0), now + WANT_EVERY)
            self.wantsAt = 0.0
            self.quick(False)
            if self.gs() == LIST_STATE:
                self.closeList('skill cut')
        if self.flow is not None:
            try:
                self.flow.close()
            except Exception:
                pass
            self.ev('flow-cut', flow=self.flowName, state=frm)
            self.flow = None
            self.quick(False)
            if self.gs() == LIST_STATE:
                self.closeList('flow cut')       # never leave the dinghy's ship list open behind a cut flow
        if self.lookKey is not None:
            self.key(self.lookKey, False)
            self.lookKey = None
        try:
            self.H.walk_cancel()
        except Exception:
            pass

    # ---------- the states (one beat each; a generator may yield waits) ----------
    def step(self):
        fn = getattr(self, 'st_' + self.state.lower())
        return fn()

    def st_down(self):
        if self.downT and time.time() - self.downT > 120 and self.downT > 0:
            self.ev('down-long', secs=round(time.time() - self.downT))
            self.downT = -1
        return None

    def st_wait(self):
        gs = self.gs()
        if (gs == 'Emote' or getattr(self.la, 'isAFK', False)) and time.time() - self.since > 20:
            self.wake('still asleep after %.0f s in WAIT' % (time.time() - self.since))
        if gs == LIST_STATE and time.time() - self.since > 20 and time.time() - self.listCloseT > 30:
            # a dinghy's ship list open with no flow driving it (run 3 sat in it for 20 minutes): close it, again every 30 s
            self.listCloseT = time.time()
            self.closeList('stray list after %.0f s in WAIT' % (time.time() - self.since))
        if time.time() - self.since > 90 and self.waitSaid != gs:
            self.waitSaid = gs
            self.ev('wait-long', gs=gs, secs=round(time.time() - self.since))
        if self.flow is not None:
            # the water flow runs: pick() keeps WAIT while the game state stays WaterRoam; landing switches the state and
            # release() cuts what is left of the flow (the flow-cut line then follows a STATE line in LandRoam)
            running, r = self.drive('getting out of the water took more than %.0f s' % FLOW_MAX)
            if running:
                return r
            self.waterNext = time.time() + WATER_RETRY
            return None
        if gs == 'WaterRoam' and time.time() - self.since > WATER_WAIT and time.time() >= self.waterNext:
            # a free bot that fell in is as stuck as a crewed one (22g needed a captain; a no-crew bot sat in IDLE)
            self.flowStart(self.flow_water(), 'water')
        return None

    def flow_water(self):
        """In the water with a crew to follow (run 7: a straight follow leg walked off a pier): back to land by the island
        teleport s_lanes.onIsland uses (the areaTeleport magic word, as the HOME setup), then, if that did not land, the
        game's own island teleport. Both tries are logged so the next run shows which one works from WaterRoam."""
        here = s_lanes.islandOf(self.H) or HOME
        t0 = time.time()
        self.ev('water-go', island=here, gs=self.gs(), la=self.H.P(self.la), inWater=round(time.time() - self.since))
        ok = yield from s_lanes.onIsland(self.H, 'water', here)
        how = 'areaTeleport'
        if not ok and self.gs() == 'WaterRoam':
            how = 'requestTeleportToIsland'
            self.ev('water-retry', how=how, island=here, gs=self.gs(), la=self.H.P(self.la))
            try:
                self.cr.teleportMgr.requestTeleportToIsland(here)
            except Exception:
                self.ev('water-retry', how=how, error=traceback.format_exc()[-300:])
            yield ('upto', lambda: self.gs() == 'LandRoam', 60, 'back on land')
            ok = self.gs() == 'LandRoam'
        self.ev('water-recover', island=here, ok=ok, how=how, gs=self.gs(), secs=round(time.time() - t0),
                la=self.H.P(self.la), area=self.H.area())
        if not ok:
            self.bug('stuck', 'water: no way back to land at %s' % self.where(), 'BOT',
                     'the mate fell in the water and neither island teleport got it back on land')
        return ok

    def st_idle(self):
        # look about for a while, then stand still (a key press would keep re-arming the game's auto-AFK timer)
        if time.time() - self.since < IDLE_LOOK_SECS and self.gs() != 'Emote':
            self.look()
        return None

    def st_lost(self):
        """Lost with a crew: look about, and after LOST_WALK s head for the docks (the island's dinghies), where a captain
        who launches needs me and one who walks by sees me (run 4: the mate stood 760 ft from its captain all run). A
        captain coming into view switches to FOLLOW and cuts the walk; his launch cuts it for BOARD (release)."""
        now = time.time()
        if (self.flow is None and self.lostT and now - self.lostT > LOST_WALK and now >= self.dockNext
                and self.may('walk')):
            here = s_lanes.islandOf(self.H)
            if here is None:
                self.dockNext = now + DOCK_RETRY
            elif sailing.dinghy_in_reach(self.H) is not None:
                self.dockNext = now + DOCK_RETRY * 2     # already at a dinghy: no walk (run 5 re-walked 0 ft every 2 min)
            else:
                self.flowStart(self.flow_dock(here), 'dock')
        if self.flow is not None:
            running, r = self.drive('the lost mate took more than %.0f s walking to the docks' % FLOW_MAX)
            if running:
                return r
            self.dockNext = now + (DOCK_RETRY * 2 if r else DOCK_RETRY)
            return None
        self.look()
        if not self.lostSaid and self.lostT and time.time() - self.lostT > LOST_SAY:
            self.lostSaid = True
            try:
                self.la.b_setSC(SC_HELLO_Q)
            except Exception:
                pass
            self.ev('lost-long', secs=round(time.time() - self.lostT))
        return None

    def st_stand(self):
        self.look()
        return None

    def st_deck(self):
        now = time.time()
        if self.flow is not None:
            # my own ship is being put away (sea.putAway, a generator in the yield protocol, driven like a BOARD flow)
            running, r = self.drive('putting my own ship away took more than %.0f s' % FLOW_MAX)
            if running:
                return r
            self.ev('putaway-done', ok=r, gs=self.gs(), onDeck=self.onDeck(), la=self.H.P(self.la))
            self.putAwayNext = now + PUTAWAY_RETRY
            return None
        if self.cannon is None and now >= self.putAwayNext and self.onMyShip():
            # aboard my own ship with nothing to do there (no crew, or a crew to follow ashore): put it away, the way the
            # sea skill does it; without the sea skill the bot stays aboard and says so once
            why = 'crew' if self.captain() is not None else 'idle'
            sk = self.skills.get('sea')
            g = None
            if sk is not None and hasattr(sk, 'putAway') and self.may('sail'):
                try:
                    g = sk.putAway(why)
                except Exception:
                    self.ev('putaway-error', why=why, tb=traceback.format_exc()[-300:])
            if hasattr(g, '__next__'):
                self.ev('putaway-go', ship=getattr(self.shipObj(), 'doId', None), why=why, gs=self.gs())
                self.flowStart(g, 'putaway')
                return None
            if not self.putAwaySaid:
                self.putAwaySaid = True
                self.ev('putaway-none', why=why, ship=getattr(self.shipObj(), 'doId', None), sea='sea' in self.skills)
            self.putAwayNext = now + PUTAWAY_RETRY
        self.look()
        if now - self.seeT >= DECK_SEE:
            self.seeT = now
            cap = self.captain()
            self.deckSee(self.cr.doId2do.get(cap[0]) if cap else None)
        return None

    def st_follow(self):
        cap = self.captain()
        capObj = self.cr.doId2do.get(cap[0]) if cap else None
        if capObj is None or not self.may('walk'):
            return None
        if self.flow is not None:
            # a route-planned leg to a far captain runs; pick() keeps FOLLOW while he is far, and a state change cuts it
            running, r = self.drive('the route-planned walk to the captain took more than %.0f s' % FLOW_MAX)
            if running:
                return r
            if r is None:
                self.followNext = time.time() + FOLLOW_RETRY
            return None
        d = self.dist(capObj)
        if d > FOLLOW_MAXR:
            if time.time() - self.followFarT > 30:
                self.followFarT = time.time()
                self.ev('follow-far', d=round(d), la=self.H.P(self.la), captain=self.H.P(capObj),
                        what='the captain is not placed on this island yet')
            return 1.0
        if d > FOLLOW_ROUTE:
            if time.time() < self.followNext:
                return 1.0
            self.H.walk_cancel()
            self.flowStart(self.flow_follow(capObj), 'follow')
            return None
        r = self.H.walk_poll(capObj, arrive=FOLLOW_NEAR, face=True, tag='follow')
        if r is None:
            self.ev('follow-stuck', la=self.H.P(self.la), captain=self.H.P(capObj))
            self.bug('stuck', 'follow: no way to the captain at %s' % self.where(), 'BOT',
                     'the mate could not find a way to the captain %.0f ft away' % self.dist(capObj))
            self.switch('STAND', 'no way to the captain; waiting')
        return None

    def flow_follow(self, capObj):
        """A route-planned walk to a far captain (paths.walk_route: round buildings, along piers) to within half of
        FOLLOW_ROUTE; the straight legs take the last stretch. -> the goal reached, or None when no way was found."""
        p = capObj.getPos(self.H.render)
        d0 = self.dist(capObj)
        self.ev('follow-route', d=round(d0), la=self.H.P(self.la), captain=self.H.P(capObj))
        g = yield from paths.walk_route(self.H, [(p[0], p[1], p[2])], FOLLOW_ROUTE * 0.5, tag='follow', tries=2,
                                        max_goals=1)
        d1 = self.dist(capObj) if not capObj.isEmpty() else None
        self.ev('follow-route-done', ok=g is not None, frm=round(d0), d=None if d1 is None else round(d1),
                la=self.H.P(self.la), gs=self.gs())
        return g

    def st_fight(self):
        cap = self.captain()
        capObj = self.cr.doId2do.get(cap[0]) if cap else None
        foe = self.fightTarget(capObj)
        foeObj = self.cr.doId2do.get(foe) if foe is not None else None
        if foeObj is None:
            return None                      # pick() leaves FIGHT on the next beat
        if self.fighter is None or getattr(self.fighter.foe, 'doId', None) != foe:
            if self.fighter is not None:
                self.fighter.close()
            if not self.may('sword'):
                return None
            if not self.sword and not getattr(self.la, 'isWeaponDrawn', False):
                try:
                    self.H.drawSword()
                except Exception:
                    pass
                self.sword = True
            safe = tuple(capObj.getPos(self.H.render)) if capObj is not None else None
            self.fighter = s_fighter.Fighter(self.H, foeObj, safe)   # Fighter wants the enemy object, not its id
            self.ev('FIGHT-START', foe=foe, captain=cap[0] if cap else None)
        r = self.fighter.step()
        if r == 'fight' and self.fighter.hits > 0:
            self.milestone('LAND-FIGHT', foe=foe)
        if r in ('kill', 'lost', 'stuck'):
            self.ev('FIGHT-END', foe=foe, how=r, hits=self.fighter.hits, skills=self.fighter.skills)
            if r == 'stuck':
                self.bug('stuck', 'fight: no way to the enemy at %s' % (self.H.area() or '?'), 'BOT',
                         'the mate could not reach enemy %s' % foe)
            self.fighter.close()
            self.fighter = None
        return None

    def st_cannon(self):
        la, H = self.la, self.H
        cap = self.captain()
        capObj = self.cr.doId2do.get(cap[0]) if cap else None
        tgt = self.cannonTarget(capObj)
        if self.cannon is None:
            if tgt is None or not self.may('cannon'):
                return None
            c = s_bpfort.pickCannon(H, tgt.getPos(H.render))
            if c is None:
                if time.time() - self.since > 10 and self.bugCount.get('no cannon', 0) == 0:
                    self.bug('missing', 'no cannon on the crew ship', 'GAME',
                             'aboard the crew ship with an enemy ship in range, but no deck cannon object in view')
                return None
            c.requestInteraction(la.doId)
            self.cannon, self.cannonT, self.cannonLast = c, time.time(), time.time()
            self.cannonManned = False
            self.ev('cannon-man', cannon=c.doId, ship=getattr(c, 'shipId', None))
            return None
        c = self.cannon
        now = time.time()
        using = bool(getattr(c, 'localAvatarUsingWeapon', 0))
        if using and not self.cannonManned:
            self.cannonManned = True
            self.ev('cannon-manned', cannon=c.doId, secs=round(now - self.cannonT, 1))
        if not using:
            if self.cannonManned:
                # the game took me off a manned cannon (the ship docked, sank or was put away): no bug. Run 8 filed
                # "cannon not manned" at 10:38:54, 2 s after docking, because this check knew nothing of the manning
                self.cannon, self.cannonManned = None, False     # onDeck() reads self.cannon: clear it before asking
                self.ev('cannon-left', cannon=c.doId, shots=self.shots, secs=round(now - self.cannonT, 1),
                        onDeck=self.onDeck(), gs=self.gs())
            elif now - self.cannonT > CANNON_MAN_WAIT:
                self.bug('other', 'cannon not manned after requestInteraction', 'BOT',
                         'requestInteraction on deck cannon %s never put the mate at it within %.0f s' % (c.doId, CANNON_MAN_WAIT))
                self.cannon = None
            return None
        if tgt is None:
            return None                      # pick() leaves after CANNON_IDLE
        self.cannonLast = time.time()
        self.trk.update(H)
        res = s_cannonpass.aim(H, c, tgt, self.trk, s_cannonpass.power_of(c))
        if res.get('ok') and s_bpfort.ready(H, c):
            c.fireCannon()
            self.shots += 1
            self.ev('CANNON-SHOT', n=self.shots, target=tgt.doId, **{k: v for k, v in res.items() if k in ('d', 'pitch', 'rel', 'vel')})
            self.milestone('CANNON-SHOT', target=tgt.doId, d=res.get('d'))
            return 0.3
        if not res.get('ok') and time.time() - self.cannonT > 5 and int(time.time()) % 10 == 0:
            self.ev('cannon-hold', why=res.get('why'), d=res.get('d'))
        return None

    # ---------- PLAY: a skill's flow runs (v2) ----------
    def st_play(self):
        if self.cutGen is not None:
            return self.driveCut()
        if self.skill is None:
            pk, self.playPick = self.playPick, None
            if pk is None:
                return None                  # pick() finds something else next beat
            score, name, why = pk
            sk = self.skills.get(name)
            if sk is None:
                return None
            self.skill, self.skillScore, self.skillT = name, score, time.time()
            self.playWhy = '%s: %s' % (name, why)
            try:
                gen = sk.flow()
            except Exception:
                return self.skillError('flow() start', traceback.format_exc())
            cap = self.captain()
            self.ev('skill-start', name=name, score=score, why=why, limit=self.limitOf(name),
                    crew=cap[0] if cap else None, gs=self.gs(), la=self.H.P(self.la), generator=hasattr(gen, '__next__'))
            if not hasattr(gen, '__next__'):
                return self.skillEnd(gen)    # flow() did its work at once and returned a result
            self.flowStart(gen, 'skill:' + name)
        why = self.cutReason()
        if why is not None:
            return self.cutStart(why)
        try:
            item = next(self.flow)
        except StopIteration as e:
            return self.skillEnd(e.value)
        except Exception:
            return self.skillError('flow', traceback.format_exc())
        return item

    def cutReason(self):
        """Why the running skill must stop now: 'crew' (a captain to follow, a crewOk skill past CREW_SKILL_MAX or the
        captain launched / out of view / far; never for the crew's own skill, crewOwn, whose flow IS the crew work),
        'safety' (a SAFETY want from another skill), 'limit' (its time limit, a BOT bug), or None.
        Never 'crew' for a skill running in the SAFETY band (22j): the jail escape runs to its end in a boy's crew too
        (before, a crewed jailed bot started land's jail flow and cut it on the same beat, again every WANT_EVERY s)."""
        name, sk, now = self.skill, self.skills.get(self.skill), time.time()
        cap = self.captain()
        if cap is not None and not getattr(sk, 'crewOwn', False) and self.skillScore < SAFETY:
            if not getattr(sk, 'crewOk', False):
                return 'crew'
            if now - self.skillT > CREW_SKILL_MAX:
                return 'crew'
            capObj = self.cr.doId2do.get(cap[0])
            if capObj is None or self.launched(cap[1]) or self.dist(capObj) > FOLLOW_ROUTE:
                return 'crew'
        safe = self.poll(SAFETY)
        if safe is not None and safe[1] != name and (self.skillScore < SAFETY or safe[0] > self.skillScore):
            return 'safety'
        limit = self.limitOf(name)
        if now - self.skillT > limit:
            self.bug('stuck', '%s: the flow ran over %.0f s' % (name, limit), 'BOT',
                     'skill %s ran past its limit of %.0f s and was cut (%s)' % (name, limit, self.playWhy))
            return 'limit'
        return None

    def cutStart(self, why):
        """Close the skill's flow and start its cut(why) cleanup (a generator gets up to CUT_MAX s of beats)."""
        name, sk, now = self.skill, self.skills.get(self.skill), time.time()
        if self.flow is not None:
            try:
                self.flow.close()
            except Exception:
                self.ev('skill-close-error', name=name, tb=traceback.format_exc()[-300:])
            self.flow = None
        self.quick(False)
        self.ran[name] = now
        self.results[name] = ('cut', why)
        self.ev('skill-cut', name=name, why=why, secs=round(now - self.skillT), gs=self.gs(), la=self.H.P(self.la))
        g = None
        if sk is not None and hasattr(sk, 'cut'):
            try:
                g = sk.cut(why)
            except Exception:
                tb = traceback.format_exc()
                self.bug('traceback', '%s-cut: %s' % (name, tb.strip().splitlines()[-1][:120]), 'BOT',
                         'skill %s crashed in cut(%s)' % (name, why), tb=tb)
        if hasattr(g, '__next__'):
            self.cutGen, self.cutT = g, now
            self.ev('skill-cleanup', name=name, why=why, max=CUT_MAX)
            self.quick(True)
            return None
        self.skillDone()
        return None

    def driveCut(self):
        """One beat of the skill's cleanup generator; CUT_MAX ends it with a BOT bug."""
        name, now = self.skill, time.time()
        if now - self.cutT > CUT_MAX:
            try:
                self.cutGen.close()
            except Exception:
                pass
            self.bug('stuck', '%s: the cleanup ran over %.0f s' % (name, CUT_MAX), 'BOT',
                     'skill %s cut() did not finish within %.0f s (%s)' % (name, CUT_MAX, self.where()))
            self.skillDone()
            return None
        try:
            item = next(self.cutGen)
        except StopIteration as e:
            self.ev('skill-cleanup-done', name=name, secs=round(now - self.cutT, 1), result=e.value, gs=self.gs())
            self.skillDone()
            return None
        except Exception:
            tb = traceback.format_exc()
            self.bug('traceback', '%s-cleanup: %s' % (name, tb.strip().splitlines()[-1][:120]), 'BOT',
                     'skill %s crashed in its cut() cleanup' % name, tb=tb)
            self.skillDone()
            return None
        return item

    def skillDone(self):
        """The skill is over (ended, cut and cleaned up): PLAY is free, the skill is not re-asked for one WANT_EVERY."""
        name, now = self.skill, time.time()
        self.skill, self.flow, self.cutGen, self.playWhy = None, None, None, ''
        self.quick(False)
        if name:
            self.hold[name] = max(self.hold.get(name, 0.0), now + WANT_EVERY)
        self.wantsAt = 0.0
        if self.gs() == LIST_STATE:
            self.closeList('skill done')

    def skillEnd(self, result):
        name, now = self.skill, time.time()
        self.ran[name] = now
        self.results[name] = ('end', result)
        self.ev('skill-end', name=name, result=result, secs=round(now - self.skillT), gs=self.gs(), la=self.H.P(self.la))
        self.skillDone()
        return None

    def skillError(self, where, tb):
        """The skill's flow raised: one BOT bug with the traceback, cut(error), and no re-ask for SKILL_RETRY s."""
        name = self.skill
        last = tb.strip().splitlines()[-1][:120]
        self.bug('traceback', '%s-flow: %s' % (name, last), 'BOT',
                 'skill %s crashed in its %s (%s)' % (name, where, self.playWhy), tb=tb)
        self.hold[name] = time.time() + SKILL_RETRY
        return self.cutStart('error')

    def flowStart(self, gen, name):
        """A sub-flow (a generator the state drives one yield at a time) starts: the body's clock goes to the move rate."""
        self.flow, self.flowT, self.flowName = gen, time.time(), name
        self.quick(True)

    def drive(self, what):
        """Advance the live sub-flow one yield. -> (True, item) while it runs; (False, its result) when it ended; (False,
        None) when it ran over FLOW_MAX and was cut (a bug file says so, `what` is its one-line story)."""
        try:
            item = next(self.flow)
        except StopIteration as e:
            self.flow = None
            self.quick(False)
            return False, e.value
        if time.time() - self.flowT > FLOW_MAX:
            self.flow.close()
            self.flow = None
            self.quick(False)
            self.bug('stuck', '%s: the flow ran over %.0f s' % (self.flowName, FLOW_MAX), 'BOT', what)
            return False, None
        return True, item

    def st_board(self):
        """Drive the dinghy sub-flow one yield at a time, so SAFETY and a lost crew can still cut it."""
        if self.flow is None:
            cap = self.captain()
            if cap is None or not self.may('dinghy'):
                return None
            self.flowStart(self.flow_board(*cap), 'board')
        running, r = self.drive('walking to the dinghy and boarding the crew ship took more than %.0f s' % FLOW_MAX)
        if running:
            return r
        if r is None:
            self.boardNext = time.time() + BOARD_RETRY
        elif r is False:
            self.boardNext = time.time() + BOARD_RETRY * 2
        return None

    def flow_board(self, cid, bm):
        """The s_crew2 mate path: to the dinghy, ask, pick the captain's ship, wait aboard. -> True / None (ask again) / False."""
        H, la = self.H, self.la
        here = s_lanes.islandOf(H)
        if here is None:
            self.boardWhy = 'no island under me'
            self.ev('board-skip', why=self.boardWhy)
            return False
        capName = getattr(self.cr.doId2do.get(cid), 'name', None) or getattr(bm, 'name', None)
        d = yield from sailing.to_dinghy(H, here)
        if d is None:
            self.boardWhy = 'no way to a dinghy found'
            self.bug('stuck', 'board: no dinghy reached on %s' % here, 'BOT',
                     'the mate found no way to a dinghy from %s' % self.where())
            return False
        self.boardWhy = ''
        got = {}
        orig = d.offerBandOptions

        def offer(options, *a, _o=orig):
            got['o'] = options
            return _o(options, *a)
        d.offerBandOptions = offer
        try:
            d.requestInteraction(la.doId)
            yield ('upto', lambda: 'o' in got, 10, 'band options')
            # never=0: the mate boards whichever ship its captain offers, Host's own when Host is the captain
            shipId = s_crew2.pickOffer(got.get('o'), capName, never=0)
            if shipId is None:
                try:
                    d.requestExit()
                except Exception:
                    pass
                self.boardWhy = 'crew ship not offered yet'
                self.ev('board-wait', why=self.boardWhy, options=len(got.get('o') or []), captain=capName)
                return None
            d.bandShipSelected(shipId)
            self.ev('board-pick', ship=shipId, captain=capName)
        finally:
            try:
                del d.offerBandOptions
            except Exception:
                pass

        def aboard():
            return (la.getCrewShipId() == shipId or getattr(la.getCrewShip(), 'doId', None) == shipId
                    or getattr(getattr(la, 'ship', None), 'doId', None) == shipId)
        yield ('upto', aboard, 60, 'aboard the crew ship')
        if not aboard():
            self.bug('other', 'board: dinghy did not put the mate aboard', 'GAME',
                     'bandShipSelected(%s) at the dinghy did not put the mate on the ship within 60 s' % shipId)
            return False
        yield ('upto', lambda: self.gs() != 'Cutscene', 40, 'boarding cutscene')
        self.ev('ABOARD', ship=shipId, gs=self.gs())
        self.milestone('ABOARD', ship=shipId)
        return True

    def flow_dock(self, here):
        """The lost mate's walk to the island's dinghies (sailing.to_dinghy: route-planned round the buildings, the dinghy
        with the shortest open route). -> True at a dinghy, False when no way was found."""
        self.ev('dock-go', island=here, la=self.H.P(self.la), lost=round(time.time() - (self.lostT or time.time())))
        d = yield from sailing.to_dinghy(self.H, here)
        self.ev('dock-done', island=here, ok=d is not None, dinghy=getattr(d, 'doId', None), la=self.H.P(self.la))
        return d is not None

    # ---------- small things ----------
    def key(self, name, on):
        try:
            sys.modules['__main__'].key_set(name, on)
            if on:
                self.la.checkInputState(True)     # what a real key does: re-arm (or end) the game's auto-AFK sleep
        except Exception:
            pass

    def look(self):
        """Idle look: a short press on a turn key now and then, like a player glancing about (never setH: that is a
        teleport-style snap the walker's tripwire counts)."""
        now = time.time()
        if self.lookKey is not None:
            if now >= self.lookEnd:
                self.key(self.lookKey, False)
                self.lookKey = None
            return
        if now < self.lookT or not self.may('look'):
            return
        keys = getattr(sys.modules['__main__'], 'KEYS', ())
        turns = [k for k in keys if 'turn' in k.lower()]
        self.lookT = now + random.uniform(*LOOK_EVERY)
        if not turns:
            return
        self.lookKey = random.choice(turns)
        self.lookEnd = now + random.uniform(0.2, 0.6)
        self.looks += 1
        self.key(self.lookKey, True)

    def close(self):
        self.release(self.state, 'END')
        try:
            self.do.ignoreAll()
        except Exception:
            pass
        self.ev('BRAIN-END', state=self.state, seen=sorted(self.seen), shots=self.shots, downs=self.downs,
                hist=['%s %s -> %s: %s' % h for h in list(self.hist)[-10:]])

    # ---------- the loop ----------
    def main(self):
        la = self.la
        self.ev('BRAIN', build=BUILD, me=la.doId, name=getattr(la, 'name', None), captains=sorted(CAPTAINS),
                proof=PROOF, window_off=WINDOW_OFF, in_crew=self.wasInBand, home=HOME,
                skills=sorted(self.skills), skills_env=os.environ.get('PBOT_SKILLS'))
        if HOME and not self.wasInBand and s_lanes.islandOf(self.H) != HOME:
            # setup only, before any play: the proof's captain waits for the bot on this island
            ok = yield from s_lanes.onIsland(self.H, 'home', HOME)
            self.ev('HOME', island=HOME, ok=ok, area=self.H.area())
        while True:
            try:
                self.crewWatch()
                self.tickSkills()
                want, why = self.pick()
                if want != self.state or (want == 'PLAY' and self.skill is None):
                    # PLAY -> PLAY with no skill running: the last one ended this beat and pick() chose the next; the
                    # STATE line says which (st_play starts it from playPick)
                    self.switch(want, why)
                r = self.step()
                if hasattr(r, '__next__'):
                    r = yield from r
            except Exception:
                tb = traceback.format_exc()
                last = tb.strip().splitlines()[-1][:120]
                self.bug('traceback', 'brain %s: %s' % (self.state, last), 'BOT',
                         'the brain crashed in state %s' % self.state, tb=tb)
                self.release(self.state, 'WAIT')
                self.switch('WAIT', 'after a brain error')
                r = 5
            if time.time() - self.lastBeat > BEAT_EVERY:
                self.beat()
            yield r if isinstance(r, (int, float)) or isinstance(r, tuple) else BEAT


def run(H):
    brain = Brain(H)
    try:
        yield from brain.main()
    finally:
        brain.close()
