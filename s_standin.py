"""STANDIN (pir-bot job 35, 11-19): one hidden run that drives pir-boat's TEST-ONLY stand-ins (server-tree patches
0298T + 0299T, the admin magic word ~standin, on only when the TEST server config says want-test-standins 1).
Spec: side-session note pir-boat-standin-1119.md, steps A, C and F.

STANDIN_DO picks the flows (comma list, default lookout,team,seabattle, run in that order):
  lookout    (step A) Lookout > PvP > Skirmish > search, then H.mw('standin lookout'). Reply "TEST: Stand-in Sam
             joined your search. Match found: say yes on your Lookout." and the Lookout's own Match found
             (lookoutMatchFound) -> say yes (lp.quickConfirm(True, ...)) -> "Off to the skirmish!" (moved, best from
             Tortuga) or "You're already here" -> "Skirmish against Stand-in Sam!" -> the knockouts, every 8 s
             ("X knocked out Y! Score: ...") -> "<bot> wins the skirmish!" -> "You earned 50 gold for the skirmish."
             and gold up by 50. PASS = Match found, the skirmish, the bot's side won, +50 gold.
  team       (step C) Lookout > PvP > Team Battle > search, then 'standin lookout team 3' -> 2 v 2 (the bot and
             Stand-in Bess against two more), first to 5: "Skirmish! Your team (<bot> and Stand-in Bess) ...".
             PASS = Match found, the team line, the bot's team won 5-1 (5 = the win, 1 = the other side's last score).
             Gold is logged, not required (the 50 gold is paid once in a while: manager.mayReward).
  seabattle  (step F) s_seabattle.run (its SB-DOCK, SB-LAUNCH, SB-STANDIN with 'standin seabattle', SB-SINK):
             PASS = "Stand-in: <ship> (<d> ft away) now sails for the Spanish. Sink it!" and, when it sinks,
             "Score: French 1, Spanish 0." (our side's count up by one). Its SEABATTLE_* settings apply.
After the flows: 'standin clear' ("TEST: <n> stand-ins cleared."), logged, never a verdict.

FAIL at once when any reply or message says "was NOT counted" (that text is an AI log line, so the AI log judge
below is the real check), "Stand-ins are off on this server." (want-test-standins is not on), or "TEST: ~standin
... failed (see the AI log)". Each flow's own PASS / FAIL lines are renamed ACT-SUB (s_activities.capture); the
run's verdict is the one final line: SI-FLOW name= ok= why= after every flow, then PASS (all ok) or FAIL.

The AI log lines (":TestStandInAI(warning): TEST stand-in: ...") never reach the client. After the run pir-test
judges them with this file, offline, no game:
    python -B s_standin.py --ailog <the AI log> [--flows lookout,team,seabattle]
It prints one JSON line and exits 0 on PASS: a "match N found" line for each Lookout flow, "Final score: ..." with
the winner's 3 (1v1) / 5-1 (team), "a point for the French: French 1, Spanish 0" (seabattle), and no
"was NOT counted" line at all.

Guard: runs on pirate 100000001 only (the admin bot toon); 100000170 and a pirate owning ship 100000173 FAIL at
once and nothing is sent.
Env: STANDIN_DO, STANDIN_SECS (240: a fight), STANDIN_FOUND_SECS (45), STANDIN_GOLD_SECS (20), STANDIN_TEAM_N (3).
Lines: SI-START, SI-GUARD, SI-WORD, SI-REPLY, SI-FOUND, SI-YES, SI-MOVE, SI-FIGHT, SI-KO, SI-WIN, SI-GOLD, SI-FLOW,
SI-CLEAR, ACT-SUB, SI-ERROR, sys-msg (every system message), LOOK-* (s_activities' Lookout helpers), SB-* (s_seabattle).
Pure functions first (unit_job35.py); the game parts import the game only when they run."""
import json, os, re, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0]))  # exec'd by a walker: maybe no __file__
if HERE not in sys.path:
    sys.path.insert(0, HERE)

TEST_PIRATE = 100000001
NEVER_PIRATE = 100000170
NEVER_SHIP = 100000173
FLOWS = ('lookout', 'team', 'seabattle')
DO = [s.strip().lower() for s in os.environ.get('STANDIN_DO', ','.join(FLOWS)).split(',') if s.strip()]
FIGHT_SECS = float(os.environ.get('STANDIN_SECS', '240'))
FOUND_SECS = float(os.environ.get('STANDIN_FOUND_SECS', '45'))
GOLD_SECS = float(os.environ.get('STANDIN_GOLD_SECS', '20'))
TEAM_N = int(os.environ.get('STANDIN_TEAM_N', '3'))
WIN_GOLD = 50
WIN = {'lookout': 3, 'team': 5}                 # PVPSkirmishAI: first to 3 (1v1), 5 (more pirates)
WORD = {'lookout': 'standin lookout skirmish', 'team': 'standin lookout team %d' % TEAM_N}
GAME = {'lookout': 'skirmish', 'team': 'teambattle'}
SEA_WORD, SEA_WORD_FAR = 'standin seabattle', 'standin seabattle %d'
CLEAR_WORD = 'standin clear'
_now = time.time                                # the unit test swaps in its own clock

# ---- the server's own texts (TestStandInAI 0299T, DistributedMatchMakerAI, PVPSkirmishAI, SeaBattleManagerAI)
NOT_COUNTED = 'was NOT counted'
OFF = 'Stand-ins are off on this server.'
_R = [
    ('found', re.compile(r'^TEST: (.+) joined your search\. Match found: say yes on your Lookout\.$')),
    ('waiting', re.compile(r'^TEST: (.+) look for a (Skirmish|Team Battle) of (\d+) at (.+)\. Now search for PvP')),
    ('started', re.compile(r'^TEST: (Skirmish|Team Battle) with (.+) here\. First to (\d+) knockouts\.')),
    ('cleared', re.compile(r'^TEST: (\d+) stand-ins cleared\.$')),
    ('none', re.compile(r'^TEST: you have no stand-ins\.$')),
    ('status', re.compile(r'^TEST: (.+)$')),
    ('error', re.compile(r'^TEST: ~standin (\S+) failed \(see the AI log\)\.$')),
    ('busy', re.compile(r'^Finish your skirmish first\.$')),
    ('notloaded', re.compile(r'^(.+) is not loaded on this district\.$')),
    ('off', re.compile(r'^Stand-ins are off on this server\.$')),
    ('sea', re.compile(r'^Stand-in: (.+) \((\d+) ft away\) now sails for the (French|Spanish)\. Sink it!$')),
    ('far', re.compile(r'^No NPC ship within (\d+) feet\. Sail closer to one and try again\.$')),
    ('seaoff', re.compile(r'^Sea Battle is off on this server\.$')),
    ('seajoin', re.compile(r'^Join the Sea Battle first: ')),
    ('seaship', re.compile(r'^Sail out on your ship first\.$')),
    ('usage', re.compile(r'^TEST ~standin lookout ')),
]
ORDER = ['error', 'found', 'waiting', 'started', 'cleared', 'none', 'busy', 'notloaded', 'off', 'sea', 'far',
         'seaoff', 'seajoin', 'seaship', 'usage', 'status']   # 'status' (any other TEST: line) last
_RD = dict(_R)
MOVE = 'Off to the skirmish! It starts when everyone arrives.'
HERE_MSG = "You're already here: the skirmish starts when everyone arrives."
LATE = 'You did not answer in time, so the search ended.'
STUCK = "You can't be moved from where you are, so you were left out of the skirmish."
_START = re.compile(r'^(?:Skirmish! Your team \((.+)\) against (.+)\.|Skirmish against (.+)!|'
                    r'Free-for-all skirmish against (.+)!) First to (\d+) knockouts wins\.')
_KO = re.compile(r'^(.+?) knocked out (.+?)! Score: (.+)\.$')
_WIN = re.compile(r'^(.+?) knocked out (.+?)\. (.+) wins the skirmish!$')
_TIMEUP = re.compile(r'^Time is up! (?:(.+) wins the skirmish\.|It is a tie\.)$')
_GOLD = re.compile(r'^You earned (\d+) gold for the skirmish\.$')
_SEASCORE = re.compile(r'Score: French (\d+), Spanish (\d+)\.')
# the AI log
AI_PREFIX = 'TEST stand-in: '
_AI_FOUND = re.compile(r'^(.+?): match (\d+) found, joining in (\d+) seconds$')
_AI_JOINED = re.compile(r'^(.+?) joined match (\d+) \((\d+) of (\d+) in\)$')
_AI_STARTED = re.compile(r'^skirmish (\d+) started with (\d+) stand-ins of pirate (\d+) \(first to (\d+)\): (.*)$')
_AI_FINAL = re.compile(r'^(.+?) knocked out (.+?)\. Final score: (.+)$')
_AI_POINT = re.compile(r'^(.+?) sank (.+?), a point for the (French|Spanish): French (\d+), Spanish (\d+)$')
_AI_MADE = re.compile(r'^(.+?) \((\d+)\) made for pirate (\d+) at (.+)$')


def reply(text):
    """Pure: a ~standin answer (or a match-maker / Sea Battle answer to it) -> (kind, groups) or None."""
    t = str(text or '').strip()
    for k in ORDER:
        m = _RD[k].match(t)
        if m:
            return k, m.groups()
    return None


def scores(text):
    """Pure: 'A and B 4, C and D 1' (PVPSkirmishAI.scoreText, the Lookout way) -> [(teamName, n)] or None."""
    out = []
    for part in str(text or '').rstrip('.').split(', '):
        bits = part.rsplit(' ', 1)
        if len(bits) != 2 or not bits[1].isdigit():
            return None
        out.append((bits[0], int(bits[1])))
    return out or None


def skirmishMsg(text):
    """Pure: one client system message of the skirmish -> (kind, data) or None.
    kinds: move, here, late, start {mine, others, first}, ko {by, who, score}, win {by, who, team}, timeup {team},
    gold n, notcounted, sea (french, spanish)."""
    t = str(text or '').strip()
    if NOT_COUNTED in t:
        return 'notcounted', t
    if t.startswith(MOVE[:20]):
        return 'move', t
    if t.startswith(HERE_MSG[:20]):
        return 'here', t
    if t.startswith(LATE[:30]):
        return 'late', t
    m = _START.match(t)
    if m:
        mine, othersT, others1, ffa, first = m.groups()
        return 'start', {'mine': mine, 'others': othersT or others1 or ffa, 'ffa': ffa is not None,
                         'first': int(first)}
    m = _WIN.match(t)
    if m:
        return 'win', {'by': m.group(1), 'who': m.group(2), 'team': m.group(3)}
    m = _KO.match(t)
    if m:
        return 'ko', {'by': m.group(1), 'who': m.group(2), 'score': scores(m.group(3))}
    m = _TIMEUP.match(t)
    if m:
        return 'timeup', {'team': m.group(1)}
    m = _GOLD.match(t)
    if m:
        return 'gold', int(m.group(1))
    m = _SEASCORE.search(t)
    if m:
        return 'sea', (int(m.group(1)), int(m.group(2)))
    return None


def onTeam(teamName, me):
    """Pure: is the pirate named me on the team named teamName ('A and B')?"""
    return me in str(teamName or '').split(' and ')


def judgeFight(msgs, me, flow):
    """Pure: the skirmish's client messages (texts, in order) -> (ok, why, facts). ok = it started, the bot's side
    won, the winner's score is WIN[flow] and (team) the other side's is 1; for 'lookout' the 50 gold came too."""
    f = {'start': None, 'kos': [], 'win': None, 'gold': [], 'moved': None, 'last': None, 'notcounted': []}
    for t in msgs:
        r = skirmishMsg(t)
        if r is None:
            continue
        k, d = r
        if k == 'notcounted':
            f['notcounted'].append(d)
        elif k in ('move', 'here'):
            f['moved'] = k
        elif k == 'start':
            f['start'] = d
        elif k == 'ko':
            f['kos'].append(d)
            if d['score']:
                f['last'] = d['score']
        elif k == 'win':
            f['win'] = d
        elif k == 'timeup':
            f['win'] = dict(d, by=None, timeup=True)
        elif k == 'gold':
            f['gold'].append(d)
    if f['notcounted']:
        return False, 'a knockout %s: %s' % (NOT_COUNTED, f['notcounted'][0]), f
    if f['start'] is None:
        return False, 'no "Skirmish against" / "Your team" message: the skirmish never started', f
    if flow == 'team' and not (f['start'].get('mine') and onTeam(f['start']['mine'], me)):
        return False, 'not a team skirmish with the bot on a team: %s' % (f['start'],), f
    w = f['win']
    if w is None:
        return False, 'no winner (%d knockouts seen, last score %s)' % (len(f['kos']), f['last']), f
    if w.get('timeup'):
        return False, 'time ran out (%s), nobody reached %d' % (w.get('team') or 'a tie', WIN[flow]), f
    if not onTeam(w['team'], me):
        return False, '%s won the skirmish, not the bot (%s)' % (w['team'], me), f
    last = dict(f['last'] or [])
    other = [n for team, n in last.items() if not onTeam(team, me)]
    final = (WIN[flow], max(other) if other else 0)
    f['final'] = final
    if f['start']['first'] != WIN[flow]:
        return False, 'first to %d, not %d' % (f['start']['first'], WIN[flow]), f
    if flow == 'team' and final != (5, 1):
        return False, 'team battle ended %d-%d, not 5-1' % final, f
    if flow == 'lookout' and WIN_GOLD not in f['gold']:
        return False, 'won %d-%d but no "You earned 50 gold for the skirmish." (%s)' % (final + (f['gold'],)), f
    return True, '%s won %d-%d%s' % (w['team'], final[0], final[1],
                                    ', +%d gold' % WIN_GOLD if WIN_GOLD in f['gold'] else ''), f


def guard(doId, ships):
    """Pure: -> None when this pirate may run it, else why not."""
    if doId == NEVER_PIRATE:
        return 'pirate %d is never touched' % NEVER_PIRATE
    if NEVER_SHIP in (ships or []):
        return 'ship %d is never touched' % NEVER_SHIP
    if doId != TEST_PIRATE:
        return 'the stand-ins run on the admin bot pirate %d only (this is %s)' % (TEST_PIRATE, doId)
    return None


def flowsOf(do):
    """Pure: STANDIN_DO -> (the flows in run order, the unknown names)."""
    want = [d for d in do if d]
    return [f for f in FLOWS if f in want], [d for d in want if d not in FLOWS]


def summary(results):
    """Pure: [(name, ok, why)] -> (allOk, text)."""
    if not results:
        return False, 'no flow ran'
    bad = [r for r in results if not r[1]]
    if not bad:
        return True, 'all %d flows passed: %s' % (len(results), '; '.join('%s %s' % (r[0], r[2]) for r in results))
    return False, '%d of %d flows failed: %s' % (len(bad), len(results), '; '.join('%s (%s)' % (r[0], r[2])
                                                                                  for r in bad))


# ---- the AI log judge (pir-test runs it on the AI log after the game)

def aiLines(lines):
    """Pure: raw AI log lines -> the stand-in texts (the part after 'TEST stand-in: ')."""
    out = []
    for ln in lines:
        i = ln.find(AI_PREFIX)
        if i >= 0:
            out.append(ln[i + len(AI_PREFIX):].rstrip('\r\n'))
    return out


def judgeAiLog(lines, flows=FLOWS, bot=None):
    """Pure: the AI log -> (ok, why, facts). Raw lines or already-stripped texts both work.
    FAIL on any 'was NOT counted'. Per flow: lookout and team need a 'match N found' line, a 'skirmish S started' line
    and a 'Final score' (lookout: the winner 3; team: 5-1); seabattle needs 'a point for the French: French 1,
    Spanish 0' (or any point for the bot's side: the score goes up by one)."""
    texts = aiLines(lines) or [ln.rstrip('\r\n') for ln in lines]     # raw log lines, or already-stripped texts
    on = [ln for ln in lines if 'TEST stand-ins are ON' in ln]
    f = {'on': bool(on), 'notcounted': [], 'found': [], 'joined': [], 'started': [], 'final': [], 'points': [],
         'made': []}
    for t in texts:
        if NOT_COUNTED in t:
            f['notcounted'].append(t)
            continue
        for k, rx in (('found', _AI_FOUND), ('joined', _AI_JOINED), ('started', _AI_STARTED), ('final', _AI_FINAL),
                      ('points', _AI_POINT), ('made', _AI_MADE)):
            m = rx.match(t)
            if m:
                f[k].append(m.groups())
                break
    why = []
    if f['notcounted']:
        return False, '%d knockout(s) %s: %s' % (len(f['notcounted']), NOT_COUNTED, f['notcounted'][0]), f
    fights = [fl for fl in flows if fl in ('lookout', 'team')]
    if fights:
        if len(set(m[1] for m in f['found'])) < len(fights):
            why.append('%d "match N found" line(s) for %d Lookout flow(s)' % (len(set(m[1] for m in f['found'])),
                                                                             len(fights)))
        finals = [scores(m[2]) for m in f['final']]
        for fl in fights:
            want = WIN[fl]
            hit = [s for s in finals if s and max(n for _, n in s) == want and
                   (fl != 'team' or sorted(n for _, n in s) == [1, 5]) and
                   (fl != 'lookout' or len(s) == 2)]
            if not hit:
                why.append('no "Final score" of %s for %s (finals: %s)' % ('5-1' if fl == 'team' else want, fl,
                                                                           [m[2] for m in f['final']]))
    if 'seabattle' in flows:
        if not any(int(p[3]) + int(p[4]) == 1 and p[2] == 'French' and int(p[3]) == 1 for p in f['points']):
            if not f['points']:
                why.append('no "a point for the French: French 1, Spanish 0" line')
            elif not any(p[2] == 'French' for p in f['points']):
                why.append('only Spanish points: %s' % (f['points'],))
            else:
                f['pointNote'] = 'a French point, but not 1-0 (the battle was joined mid-score)'
    if why:
        return False, '; '.join(why), f
    return True, 'AI log: %s ok, no "was NOT counted"' % ','.join(flows), f


# ---- the game parts

def word(H, w, secs=15.0, want=None):
    """Generator: H.mw(w), wait for its answer (reply() matches; want = the kinds that end the wait).
    -> (kind, groups, text) or (None, None, None)."""
    n = len(H.resp)
    H.ev('SI-WORD', word='~' + w)
    H.mw(w)

    def got():
        for r in H.resp[n:]:
            a = reply(r)
            if a and (want is None or a[0] in want or a[0] in ('error', 'off', 'busy', 'notloaded', 'usage')):
                return a[0], a[1], r
        return None
    yield ('until', lambda: got() is not None, secs, 'answer to ~' + w)
    a = got()
    H.ev('SI-REPLY', word='~' + w, kind=a and a[0], text=a and a[2], others=[r for r in H.resp[n:]][:6])
    return a or (None, None, None)


def badReply(kind, text):
    if kind == 'off':
        return 'want-test-standins is not on: %s' % text
    if kind == 'error':
        return 'the word broke on the AI: %s' % text
    if kind in ('busy', 'notloaded', 'usage'):
        return text
    return None


def fightFlow(H, flow):
    """Generator, one Lookout flow (A: lookout, C: team) with s_activities' Lookout helpers. Logs PASS / FAIL."""
    import s_activities as A
    import s_lanes
    la, lp = H.la, H.la.guiMgr.lookoutPage
    me = la.getName()
    style = A.STYLE[GAME[flow]]
    rep, saved, box = {}, [], []
    undo = A.sysHook(H, box)
    t0 = _now()
    g0 = s_lanes.gold(H)
    H.ev('SI-FIGHT', flow=flow, step='start', me=me, style=style, here=H.area(), gold=g0)
    try:
        A.lookoutHooks(H, lp, rep, saved)
        why = yield from A.lookoutPick(H, lp, A.PVP, style, rep)
        if why:
            H.ev('FAIL', why='Lookout: ' + why); return
        yield ('until', lambda: 'acc' in rep or A.said(box, A.QUEUED, t0) or 'failed' in rep, 15, 'search accepted')
        if 'acc' not in rep and not A.said(box, A.QUEUED, t0):
            H.ev('FAIL', why='the Lookout search was not accepted in 15 s', failed=rep.get('failed')); return
        kind, grp, text = yield from word(H, WORD[flow], 20, ('found', 'waiting'))
        bad = badReply(kind, text)
        if bad or kind is None:
            H.ev('FAIL', why=bad or 'no answer to ~%s' % WORD[flow]); return
        if kind == 'waiting':                   # the server did not see the search: search once more
            H.ev('SI-FOUND', flow=flow, how='waiting', text=text)
            why = yield from A.lookoutPick(H, lp, A.PVP, style, rep)
            if why:
                H.ev('FAIL', why='Lookout (second search): ' + why); return
        yield ('until', lambda: 'found' in rep or A.said(box, LATE, t0), FOUND_SECS, 'Match found')
        if 'found' not in rep:
            H.ev('FAIL', why='no Match found on the Lookout within %d s of "%s"' % (FOUND_SECS, text)); return
        H.ev('SI-FOUND', flow=flow, how=kind, text=text, match=rep['found'][0], secs=round(_now() - t0),
             box=getattr(lp, 'confirmMsg', None) is not None)
        t1 = _now()
        params = getattr(lp, 'searchParams', None)
        lp.quickConfirm(True, params['type'] if params else None)     # the box's yes
        H.ev('SI-YES', flow=flow)
        yield ('until', lambda: any(A.said(box, x, t1) for x in (MOVE, HERE_MSG, LATE, STUCK[:30])), 20,
               'off to the skirmish')
        moved = 'move' if A.said(box, MOVE, t1) else 'here' if A.said(box, HERE_MSG, t1) else None
        H.ev('SI-MOVE', flow=flow, how=moved, here=H.area())
        late = A.said(box, LATE, t1) or A.said(box, STUCK[:30], t1)
        if late or moved is None:
            H.ev('FAIL', why='after the yes: %s' % (late or 'no "Off to the skirmish" message')); return
        msgs = lambda: [m for t, m in box if t >= t1]

        def done():
            j = [skirmishMsg(m) for m in msgs()]
            return any(r and r[0] in ('win', 'timeup', 'notcounted') for r in j)
        yield ('until', lambda: any((skirmishMsg(m) or ('',))[0] == 'start' for m in msgs()), 90, 'skirmish start')
        H.ev('SI-FIGHT', flow=flow, step='started', start=next((skirmishMsg(m)[1] for m in msgs()
                                                                 if (skirmishMsg(m) or ('',))[0] == 'start'), None),
             here=H.area())
        yield ('until', done, FIGHT_SECS, 'skirmish over')
        if any((skirmishMsg(m) or ('',))[0] == 'win' for m in msgs()):
            yield ('until', lambda: any((skirmishMsg(m) or ('',))[0] == 'gold' for m in msgs()), GOLD_SECS,
                   'skirmish gold')
        for m in msgs():
            r = skirmishMsg(m)
            if r and r[0] == 'ko':
                H.ev('SI-KO', flow=flow, by=r[1]['by'], who=r[1]['who'], score=r[1]['score'])
        ok, why, facts = judgeFight(msgs(), me, flow)
        g1 = s_lanes.gold(H)
        H.ev('SI-WIN', flow=flow, ok=ok, why=why, final=facts.get('final'), win=facts.get('win'), moved=moved)
        H.ev('SI-GOLD', flow=flow, before=g0, after=g1, delta=g1 - g0, told=facts.get('gold'))
        if ok and flow == 'lookout' and g1 - g0 < WIN_GOLD:
            ok, why = False, why + ' but gold moved %d, not +%d' % (g1 - g0, WIN_GOLD)
        if ok:
            H.ev('PASS', what='%s: Match found, %s' % ('Lookout skirmish' if flow == 'lookout' else 'Team Battle', why))
        else:
            H.ev('FAIL', why=why)
    finally:
        A.unwrap(saved)
        undo()
        A.lookoutClose(H, lp)


def seaFlow(H):
    """Generator, step F: s_seabattle's whole run, its stand-in word now ~standin seabattle (0299T)."""
    import s_seabattle
    yield from s_seabattle.run(H)


def clear(H):
    kind, grp, text = yield from word(H, CLEAR_WORD, 10, ('cleared', 'none'))
    H.ev('SI-CLEAR', kind=kind, text=text)


def run(H):
    import s_activities as A
    la = H.la
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    flows, unknown = flowsOf(DO)
    H.ev('SI-START', pirate=la.doId, flows=flows, unknown=unknown, here=H.area(), ships=ships)
    no = guard(la.doId, ships)
    if no:
        H.ev('SI-GUARD', why=no)
        H.ev('FAIL', why=no); return
    if unknown or not flows:
        H.ev('FAIL', why='STANDIN_DO: unknown %s (flows: %s)' % (unknown, ', '.join(FLOWS))); return
    yield ('until', lambda: la.getInventory() is not None, 30, 'inventory')
    kind, grp, text = yield from word(H, 'standin status', 10)
    bad = badReply(kind, text) if kind in ('off', 'error') else None
    if bad or kind is None:
        H.ev('FAIL', why=bad or 'no answer to ~standin status (is 0298T on the AI?)'); return
    results = []
    try:
        for flow in flows:
            gen = fightFlow(H, flow) if flow != 'seabattle' else seaFlow(H)
            got = yield from A.capture(H, gen, len(results) + 1, flow)
            nc = [kw for k, kw in got['evs'] if k == 'sys-msg' and NOT_COUNTED in str(kw.get('text'))]
            ok = got['kind'] == 'PASS' and not nc
            why = (got['kw'].get('what') or got['kw'].get('why') or '') if not nc else 'a knockout %s' % NOT_COUNTED
            H.ev('SI-FLOW', name=flow, ok=ok, why=why)
            results.append((flow, ok, why))
            if flow != 'seabattle':
                yield from clear(H)
                yield 2
    finally:
        try:
            yield from clear(H)
        except Exception as e:
            H.ev('SI-ERROR', where='clear', err=repr(e), tb=traceback.format_exc()[-600:])
    ok, why = summary(results)
    H.ev('PASS' if ok else 'FAIL', why=why, flows=results)


def main(argv):
    """CLI: --ailog <file> [--flows a,b] -> one JSON line, exit 0 on PASS, 1 on FAIL."""
    if '--ailog' not in argv:
        print(__doc__)
        return 2
    path = argv[argv.index('--ailog') + 1]
    flows = FLOWS
    if '--flows' in argv:
        flows = tuple(s for s in argv[argv.index('--flows') + 1].split(',') if s)
    with open(path, encoding='utf-8', errors='replace') as fh:
        lines = fh.readlines()
    ok, why, f = judgeAiLog(lines, flows)
    print(json.dumps({'ok': ok, 'why': why, 'on': f['on'], 'notcounted': f['notcounted'][:5], 'found': f['found'],
                      'final': [x[2] for x in f['final']], 'points': f['points'], 'made': f['made'][:7]}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
