"""SEABATTLE (pir-bot job 24, 11-19): live proof of pir-ships' Sea Battle (server-tree patches 0250-0253), Plan A:
one pirate (100000001 only) against an NPC ship that the TEST-ONLY magic word ~standin seabattle (patch 0299T, applied
on the AI by pir-test before the run) puts on the other team. Spec: side-session note pir-ships-seabattle-bot-spec.md.

Steps (each logs one SB- line; PASS = 1, 2, 4 and 5 ok within SEABATTLE_SECS):
  1 SB-DOCK      sail (sailing.sail_to) to the team dock, SEABATTLE_DOCK (default the French dock, Ile d'Etable de
                 Porc 1196970080.56sdnaik; the Spanish one is Isla de la Avaricia 1196970035.53sdnaik). dinghies=
                 the live dinghies there.
  2 SB-LAUNCH    launch from its dinghy (s_shipquest.hunt's own launch) -> the system message "You sail for the
                 French!" and la.getSiegeTeam() == 1 (2 for the Spanish dock).
  3              hunt NPC ships WITHOUT docking (docking puts the ship away and it leaves the battle): s_shipquest.hunt
                 through s_shipfight.Picker (patrol ring round the dock, fair-foe pick). Before the stand-in no shot
                 is fired at a ship nearer than HOLD_R: the magic word picks the nearest ship, which we must not sink
                 first.
  4 SB-STANDIN   with an NPC ship within STANDIN_R (3000 ft): H.mw('standin seabattle') (0299T; the old 0254T word
                 seaBattleStandIn is gone). Its answer "Stand-in: <name> (<n> ft away) now sails for the Spanish.
                 Sink it!" and that ship's getSiegeTeam() == the other team. "No NPC ship within 3000 feet. Sail
                 closer...": retried once as 'standin seabattle 6000'. Any other refusal ("Sea Battle is off on this
                 server.", "Join the Sea Battle first: ...", "Sail out on your ship first.", "Stand-ins are off on
                 this server.", "TEST: ~standin seabattle failed (see the AI log).") is a FAIL with its text.
  5 SB-SINK      the stand-in becomes hunt's only target; sink it -> "Score: French 1, Spanish 0." (our team's count
                 up by one; a battle joined at 2-1 with no score seen yet: the
                 message right after the stand-in sinks counts when our count is >= 1).
  6 (optional)   our ship sinks: SB-SUNK (the "Your ship sank in the Sea Battle. It is repaired and its hold is safe"
                 message, landed at our dock?), then a new hunt launches again -> SB-RELAUNCH team=1. At most
                 SEABATTLE_RELAUNCHES (2).
  7 (optional)   SEABATTLE_AWAY=1: after the sink, sail to SEABATTLE_AWAY_TO (Port Royal) and dock there; within
                 AWAY_WAIT s "You have left the Sea Battle." and la.getSiegeTeam() == 0 -> SB-LEFT.
Every system message the client gets while this runs is logged as sys-msg (otp DistributedPlayer.setSystemMessage).
Guard: FAIL at once for pirate 100000170 or a pirate owning ship 100000173; any pirate but 100000001 FAILs too unless
SEABATTLE_ANY_PIRATE=1.
Pure functions first (unit_job24.py), the generator below runs in the game (no game import at module load)."""
import os
import re
import time

FRENCH_DOCK = '1196970080.56sdnaik'      # Ile d'Etable de Porc
SPANISH_DOCK = '1196970035.53sdnaik'     # Isla de la Avaricia
FRENCH, SPANISH = 1, 2
TEAM_NAMES = {FRENCH: 'French', SPANISH: 'Spanish'}
DOCK_TEAM = {FRENCH_DOCK: FRENCH, SPANISH_DOCK: SPANISH}

DOCK = os.environ.get('SEABATTLE_DOCK', FRENCH_DOCK)
SECS = float(os.environ.get('SEABATTLE_SECS', '1500'))
STANDIN_R = float(os.environ.get('SEABATTLE_STANDIN_R', '3000'))   # ft: send the magic word with a ship this near
STANDIN_FAR = 6000                                                  # the one retry after "No NPC ship within"
HOLD_R = float(os.environ.get('SEABATTLE_HOLD_R', '2000'))          # no shot at a ship this near before the stand-in
RELAUNCHES = int(os.environ.get('SEABATTLE_RELAUNCHES', '2'))
AWAY = os.environ.get('SEABATTLE_AWAY', '0') == '1'
AWAY_TO = os.environ.get('SEABATTLE_AWAY_TO', '')                  # '' = s_lanes.PR
AWAY_WAIT = float(os.environ.get('SEABATTLE_AWAY_WAIT', '120'))     # the server leaves the battle after 60 s away
ANY_PIRATE = os.environ.get('SEABATTLE_ANY_PIRATE', '0') == '1'
TEST_PIRATE = 100000001
NEVER_PIRATE, NEVER_SHIP = 100000170, 100000173
TEAM_WAIT = 30.0           # s after the launch for the team message and siege team
ANSWER_WAIT = 15.0         # s for the magic word's answer
STANDIN_TEAM_WAIT = 10.0   # s for the stand-in ship's siege team to reach the client
SCORE_WAIT = 20.0          # s after the stand-in sank for the score message
LAND_WAIT = 60.0           # s after our ship sank for the crew to land
ASK_GAP = 20.0             # s between two stand-in words (a lost answer is asked again)

SANK_MSG = 'Your ship sank in the Sea Battle'
REFUSALS = ('Sea Battle is off', 'Join the Sea Battle first', 'Sail out on your ship first',   # 0299T
            'Stand-ins are off on this server', 'TEST: ~standin seabattle failed', 'TEST ~standin lookout')
_STANDIN = re.compile(r'^Stand-in: (.+) \((\d+) ft away\) now sails for the (French|Spanish)\. Sink it!')
_SCORE = re.compile(r'Score: French (\d+), Spanish (\d+)\.')
_LAUNCH = re.compile(r'You sail for the (French|Spanish)!')
_FAR = re.compile(r'^No NPC ship within (\d+) feet')


# ------------------------------------------------------------------------------------------------ pure
def teamOfDock(uid):
    return DOCK_TEAM.get(uid)


def otherTeam(team):
    return {FRENCH: SPANISH, SPANISH: FRENCH}.get(team)


def launchTeam(text):
    """'You sail for the French! ...' -> 1 (2 for Spanish), else None."""
    m = _LAUNCH.search(text or '')
    return None if m is None else (FRENCH if m.group(1) == 'French' else SPANISH)


def parseScore(text):
    """'Score: French 1, Spanish 0.' -> (1, 0), else None."""
    m = _SCORE.search(text or '')
    return None if m is None else (int(m.group(1)), int(m.group(2)))


def scoreUp(before, after, team):
    """True when our team's count in `after` is one more than in `before`. No score seen yet (the bot can join a
    battle that is already 2-1): the score message that comes right after the stand-in sinks counts when our team has
    at least one sink (in Plan A the stand-in is the only Spanish ship, so only our side can score)."""
    if after is None or team not in (FRENCH, SPANISH):
        return False
    i = team - 1
    if before is None:
        return after[i] >= 1
    return after[i] == before[i] + 1


def standinAnswer(text):
    """The ~standin seabattle answer -> ('ok', name, dist, teamName) / ('far', maxDist) / ('refused', text) / None
    (not an answer to this word)."""
    t = text or ''
    m = _STANDIN.match(t)
    if m:
        return ('ok', m.group(1), int(m.group(2)), m.group(3))
    m = _FAR.match(t)
    if m:
        return ('far', int(m.group(1)))
    for r in REFUSALS:
        if t.startswith(r):
            return ('refused', t)
    return None


def standinWord(retry):
    return 'standin seabattle %d' % STANDIN_FAR if retry else 'standin seabattle'


def guard(doId, ships, anyOk=ANY_PIRATE):
    """-> None when this pirate may run the step, else why not."""
    if doId == NEVER_PIRATE:
        return 'pirate %d is never touched' % NEVER_PIRATE
    if NEVER_SHIP in (ships or []):
        return 'ship %d is never touched' % NEVER_SHIP
    if doId != TEST_PIRATE and not anyOk:
        return 'Plan A runs on pirate %d only (this is %s; SEABATTLE_ANY_PIRATE=1 allows another)' % (TEST_PIRATE, doId)
    return None


def passed(marks):
    """PASS = steps 1, 2, 4 and 5 ok."""
    return all(marks.get(k) for k in ('dock', 'launch', 'standin', 'sink'))


def nearestFoe(last, exclude=()):
    """Picker.last rows (dist, doId, level, hp, fromPort, name) -> the nearest (dist, doId, name) not excluded."""
    rows = sorted((r for r in (last or []) if r[1] not in exclude), key=lambda r: r[0])
    return None if not rows else (rows[0][0], rows[0][1], rows[0][5] if len(rows[0]) > 5 else '')


# ------------------------------------------------------------------------------------------------ in the game
def siegeTeam(o):
    try:
        return int(o.getSiegeTeam() or 0)
    except Exception:
        return None


def hookMessages(H, box):
    """Log every system message (sys-msg) and keep its text in box. -> the undo function."""
    from otp.avatar import DistributedPlayer as DPm
    cls = DPm.DistributedPlayer
    orig = cls.__dict__['setSystemMessage']

    def setSystemMessage(av, aboutId, chatString, *a, **kw):
        box.append((time.time(), chatString))
        try:
            H.ev('sys-msg', text=chatString, av=getattr(av, 'doId', None), about=aboutId)
        except Exception:
            pass
        return orig(av, aboutId, chatString, *a, **kw)
    cls.setSystemMessage = setSystemMessage

    def undo():
        cls.setSystemMessage = orig
    return undo


def run(H):
    import s_lanes
    import sailing
    import s_shipquest
    import s_shipfight as SF
    la = H.la
    team = teamOfDock(DOCK)
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    H.ev('SB-START', pirate=la.doId, ships=ships, dock=DOCK, team=TEAM_NAMES.get(team), secs=SECS,
         standinR=STANDIN_R, holdR=HOLD_R, relaunches=RELAUNCHES, away=AWAY, here=H.area(), gs=la.getGameState(),
         siege=siegeTeam(la), gold=s_lanes.gold(H))
    no = guard(la.doId, ships, ANY_PIRATE)
    if no:
        H.ev('FAIL', why=no); return
    if team is None:
        H.ev('FAIL', why='SEABATTLE_DOCK %s is not a Sea Battle dock' % DOCK); return
    if not ships:
        H.ev('FAIL', why='the pirate owns no ship'); return
    sid = ships[0]
    t0 = time.time()
    marks = {}
    box = []                    # (t, text) of every system message
    undo = hookMessages(H, box)

    # watch hunt()'s own lines as they are written (as SHIPFIGHT does)
    got = {}
    sunkIds = []
    orig = H.ev

    def ev(kind, **kw):
        if kind == 'FOE-SUNK' and kw.get('gone') and picker is not None and picker.lost(kw.get('foe')):
            kind = 'FOE-LOST'
            kw['last'] = picker.first.get(kw.get('foe'))
        got[kind] = got.get(kind, 0) + 1
        if kind == 'FOE-SUNK':
            sunkIds.append(kw.get('foe'))
        return orig(kind, **kw)
    picker = None
    H.ev = ev
    try:
        # ---- 1: sail to the dock
        here = sailing.hereUid(H)
        if here != DOCK:
            if here is None or la.getGameState() != 'LandRoam':
                # setup only: the step starts on land with the ship put away
                if not (yield from s_lanes.onIsland(H, 'seabattle', s_lanes.PR)):
                    H.ev('FAIL', why='could not get onto land to start', area=H.area()); return
            yield from sailing.sail_to(H, DOCK, 'Sea Battle dock')
        dinghies = list(sailing.live_dinghies(H) or [])
        marks['dock'] = sailing.hereUid(H) == DOCK and la.getGameState() == 'LandRoam'
        H.ev('SB-DOCK', island=DOCK, ok=marks['dock'], here=sailing.hereUid(H), gs=la.getGameState(),
             dinghies=len(dinghies), siege=siegeTeam(la), secs=round(time.time() - t0))
        if not marks['dock']:
            H.ev('FAIL', why='not at the Sea Battle dock', marks=marks); return

        # ---- 2-6: launch, hunt, stand-in, sink (a sunk ship relaunches)
        picker = SeaPicker(H, t0, SF, s_shipquest, sailing, marks)
        launches = 0
        while time.time() - t0 < SECS and not marks.get('sink'):
            res = yield from battle(H, sid, team, picker, box, marks, launches, got, sunkIds, t0, s_shipquest, SF)
            launches += 1
            if res in ('done', 'fail'):
                break
            if res == 'our-ship-sunk' or res == 'left-ship':
                ok = yield from landed(H, sid, box, res, sailing)
                if launches > RELAUNCHES or not ok:
                    break
                continue
            break                        # timeout / launch-failed / stopped
        # ---- 7 (optional): away from the battle
        if AWAY and marks.get('sink'):
            yield from away(H, box, marks, s_lanes, sailing)
        H.ev('SB-END', marks=marks, launches=launches, sunk=sunkIds, got=dict((k, got[k]) for k in sorted(got)
             if k in ('FOE-SUNK', 'FOE-LOST', 'BROADSIDE', 'OUR-SHIP-SUNK', 'SHIP-TARGET')),
             msgs=[t for _, t in box][-12:], secs=round(time.time() - t0), siege=siegeTeam(la))
        if passed(marks):
            H.ev('PASS', step='seabattle', team=TEAM_NAMES[team], standin=marks.get('standinId'),
                 score=marks.get('score'), relaunched=marks.get('relaunch', False), left=marks.get('left'),
                 secs=round(time.time() - t0))
        else:
            missing = [k for k in ('dock', 'launch', 'standin', 'sink') if not marks.get(k)]
            H.ev('FAIL', why='Sea Battle steps not proven: %s' % ', '.join(missing), marks=marks,
                 secs=round(time.time() - t0))
    finally:
        H.ev = orig
        undo()
        for k in SF.STEER_KEYS:
            messenger.send(k + '-up')


def battle(H, sid, team, picker, box, marks, launches, got, sunkIds, t0, s_shipquest, SF):
    """Generator: one hunt() from the dock's dinghy. Checks the team message after the launch, sends the stand-in
    word, makes the stand-in hunt's target and waits for the score. -> 'done' (sunk + scored) / 'fail' (a refusal)
    / hunt's own why ('our-ship-sunk', 'left-ship', 'timeout', 'launch-failed')."""
    la = H.la
    mine = 'relaunch' if launches else 'launch'
    tag = 'SB-RELAUNCH' if launches else 'SB-LAUNCH'
    left = max(1.0, SECS - (time.time() - t0))
    g = s_shipquest.hunt(H, None, SF.AnyShip(), left)
    nBox = len(box)
    pilotT = None            # when the pirate first took the wheel
    teamDone = False
    sunk0 = len(sunkIds)
    sankT = None             # the stand-in sank (FOE-SUNK on it) at
    why = None
    with picker:
        try:
            while True:
                try:
                    y = next(g)
                except StopIteration as e:
                    why = e.value
                    break
                now = time.time()
                if now - t0 >= SECS:
                    why = 'timeout'
                    break
                msgs = [t for _, t in box[nBox:]]
                # ---- the launch: team message + siege team
                if not teamDone and la.getGameState() == 'ShipPilot':
                    pilotT = pilotT or now
                    lt = next((launchTeam(t) for t in msgs if launchTeam(t)), None)
                    st = siegeTeam(la)
                    if (lt == team and st == team) or now - pilotT > TEAM_WAIT:
                        teamDone = True
                        ok = lt == team and st == team
                        marks[mine] = ok
                        ship = H.cr.doId2do.get(sid)
                        H.ev(tag, team=st, want=team, msg=next((t for t in msgs if launchTeam(t)), None), ok=ok,
                             shipTeam=siegeTeam(ship) if ship is not None else None, ship=sid,
                             secs=round(now - pilotT))
                        if not ok and not launches:
                            H.ev('FAIL', why='launched from the %s dock but got no team (message %r, siege team %s)'
                                 % (TEAM_NAMES[team], lt, st))
                            why = 'fail'
                            break
                # ---- the stand-in word
                if teamDone and marks.get(mine) and picker.standin is None:
                    r = picker.ask(now, msgs)
                    if r == 'fail':
                        why = 'fail'
                        break
                # ---- the sink and the score
                if picker.standin is not None and sankT is None and picker.standin in sunkIds[sunk0:]:
                    sankT = now
                sc = next((parseScore(t) for t in reversed(msgs) if parseScore(t)), None)
                if sc is not None and sc != marks.get('score') and picker.standin is not None:
                    up = scoreUp(marks.get('score'), sc, team)
                    marks['score'] = sc
                    if up:
                        marks['sink'] = True
                        H.ev('SB-SINK', score='%d-%d' % sc, ok=True, foe=picker.standin, name=picker.standinName,
                             sunkSeen=sankT is not None, secs=round(now - t0))
                        why = 'done'
                        break
                if sankT is not None and now - sankT > SCORE_WAIT:
                    H.ev('SB-SINK', score=None if marks.get('score') is None else '%d-%d' % marks['score'], ok=False,
                         foe=picker.standin, name=picker.standinName, why='no score message %d s after the sink'
                         % SCORE_WAIT, msgs=msgs[-6:])
                    why = 'done'
                    break
                yield y
        finally:
            g.close()
            for k in SF.STEER_KEYS:
                messenger.send(k + '-up')
    if why == 'fail':
        return 'fail'
    return why


def landed(H, sid, box, res, sailing):
    """Generator after our ship sank (or the pirate left the wheel): wait for land, log SB-SUNK. -> True when he
    stands on land again (so a new hunt can launch from the dinghy)."""
    la = H.la
    yield ('upto', lambda: la.getGameState() == 'LandRoam' and sailing.hereUid(H) is not None, LAND_WAIT, 'landed')
    yield ('upto', lambda: any(SANK_MSG in t for _, t in box[-10:]), 10, 'sank msg')
    msg = next((t for _, t in box[-10:] if SANK_MSG in t), None)
    ov = H.cr.getOwnerView(sid)
    here = sailing.hereUid(H)
    H.ev('SB-SUNK', how=res, msg=msg, here=here, atDock=here == DOCK, gs=la.getGameState(),
         hp=getattr(ov, 'Hp', None), maxHp=getattr(ov, 'maxHp', None), siege=siegeTeam(la))
    if here is not None and here != DOCK and la.getGameState() == 'LandRoam':
        yield from sailing.sail_to(H, DOCK, 'back to the Sea Battle dock')
    return la.getGameState() == 'LandRoam' and sailing.hereUid(H) == DOCK


def away(H, box, marks, s_lanes, sailing):
    """Generator, optional step 7: dock away from the battle and wait for 'You have left the Sea Battle.'"""
    la = H.la
    to = AWAY_TO or s_lanes.PR
    n0 = len(box)
    t1 = time.time()
    yield from sailing.sail_to(H, to, 'leave the Sea Battle')
    yield ('upto', lambda: any('You have left the Sea Battle' in t for _, t in box[n0:]) and siegeTeam(la) == 0,
           AWAY_WAIT, 'left the battle')
    msg = next((t for _, t in box[n0:] if 'You have left the Sea Battle' in t), None)
    marks['left'] = bool(msg) and siegeTeam(la) == 0
    H.ev('SB-LEFT', ok=marks['left'], msg=msg, siege=siegeTeam(la), to=to, here=sailing.hereUid(H),
         secs=round(time.time() - t1))


class SeaPicker:
    """s_shipfight.Picker for the Sea Battle: the dock is the only port (patrol ring and leash round it), no shot at
    a near ship before the stand-in, then the stand-in is hunt's only target. Wraps a real Picker (s_shipfight is imported in the game only)."""

    def __init__(self, H, t0, SF, s_shipquest, sailing, marks):
        self.p = SF.Picker(H, t0)
        self.marks = marks
        tbl = sailing.islands()
        if DOCK in tbl:
            self.p.ports = [(DOCK, tbl[DOCK][0], tbl[DOCK][1], tbl[DOCK][2])]
        self.H, self.SF, self.sq = H, SF, s_shipquest
        self.standin, self.standinName = None, None
        self.asked = []            # (t, word, len(H.resp) before)
        self.retried = False
        self.answer = None         # (word, text) waiting for its stand-in ship to turn
        self.answerT = None

    # the real Picker's fields hunt and battle() read
    def __getattr__(self, k):
        return getattr(self.__dict__['p'], k)

    def __enter__(self):
        self.p.__enter__()
        # Picker.__enter__ put its bound methods in; ours wrap them
        self.sq.npcShips, self.sq.matches = self.npcShips, self.matches
        return self

    def __exit__(self, *a):
        return self.p.__exit__(*a)

    def npcShips(self, H, ship):
        out = self.p.npcShips(H, ship)
        if self.standin is None:
            return out
        hit = [t for t in out if t[1].doId == self.standin]
        if not hit:
            return out
        p = self.p
        if p.top != self.standin:
            d, o = hit[0]
            H.ev('FOE-PICK', foe=self.standin, how='stand-in', foeName=getattr(o, 'name', ''), dist=round(d),
                 hp=self.sq.hpOf(o), team=siegeTeam(o))
        p.allowed = {self.standin}
        p.top = p.want = self.standin
        return hit + [t for t in out if t[1].doId != self.standin]

    def matches(self, task, o):
        oid = getattr(o, 'doId', None)
        if self.standin is not None:
            if oid == self.standin:
                return True, 'the stand-in'
            return False, 'not the stand-in'
        d = next((r[0] for r in self.p.last if r[1] == oid), None)
        if d is not None and d < HOLD_R:
            return False, 'hold fire: the stand-in word first (%d ft)' % d
        return self.p.matches(task, o)

    def ask(self, now, msgs):
        """Called each beat once the team is proven. Sends the stand-in word with a ship within STANDIN_R, reads its
        answer, finds the stand-in ship. -> 'fail' on a refusal, else None."""
        H = self.H
        if self.answer is not None:
            return self.findStandin(now)
        if self.asked:
            t, word, n = self.asked[-1]
            ans = next((standinAnswer(r) for r in H.resp[n:] if standinAnswer(r)), None)
            if ans is None:
                if now - t < max(ANSWER_WAIT, ASK_GAP):
                    return None
                H.ev('SB-STANDIN-ASK', what='no answer', word=word, secs=round(now - t))
            elif ans[0] == 'ok':
                self.answer, self.answerT = (word, ans), now
                return self.findStandin(now)
            elif ans[0] == 'far':
                if self.retried:
                    H.ev('FAIL', why='~standin seabattle: %s (after the retry at %d ft)'
                         % (next(r for r in H.resp[n:] if standinAnswer(r)), STANDIN_FAR))
                    return 'fail'
                self.retried = True
                H.ev('SB-STANDIN-ASK', what='far', word=word, retry=standinWord(True))
                self.send(now, True)
                return None
            else:
                H.ev('FAIL', why='~standin seabattle refused: %s' % ans[1])
                return 'fail'
        nf = nearestFoe(self.p.last)
        if nf is None or nf[0] > STANDIN_R:
            return None
        if self.asked and now - self.asked[-1][0] < ASK_GAP:
            return None
        H.ev('SB-STANDIN-ASK', what='send', nearest=nf[1], name=nf[2], dist=round(nf[0]))
        self.send(now, False)
        return None

    def send(self, now, retry):
        w = standinWord(retry)
        self.asked.append((now, w, len(self.H.resp)))
        self.H.mw(w)

    def findStandin(self, now):
        """The answer named a ship: find it in view (the other team's siege team, its name, nearest first)."""
        H = self.H
        word, ans = self.answer
        _, name, dist, teamName = ans
        want = SPANISH if teamName == 'Spanish' else FRENCH
        rows = []
        for o in list(H.cr.doId2do.values()):
            if 'NPCShip' not in type(o).__name__ or not hasattr(o, 'getPos'):
                continue
            rows.append((siegeTeam(o) == want, getattr(o, 'name', '') == name, o))
        team = [r for r in rows if r[0]]
        named = [r for r in rows if r[1]]
        pick = (team and [r for r in team if r[1]] or team or None)
        waited = now - self.answerT
        if not pick and waited < STANDIN_TEAM_WAIT:
            return None
        o = (pick or named or [(None, None, None)])[0][2]
        ok = bool(pick)
        if o is None:
            H.ev('FAIL', why='the stand-in %r was named but is not in view' % name, answer=ans)
            return 'fail'
        self.standin, self.standinName = o.doId, getattr(o, 'name', name)
        H.ev('SB-STANDIN', doId=o.doId, name=self.standinName, ok=ok, team=siegeTeam(o), want=want, answer=ans[:3],
             word=word, ft=dist, byName=bool(named), secs=round(waited, 1))
        self.marks['standin'] = ok
        self.marks['standinId'] = o.doId
        return None
