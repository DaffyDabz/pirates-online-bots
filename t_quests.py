"""Offline test of pbot\\skills\\quests.py (PLAYERBOTS round 2, places 11-22): the player bot's quest skill.
- In a boy's crew (the brain has a captain) it asks for no time; solo with a held quest it asks for the turn; with
  nothing held (or all set aside) it asks for none.
- flow() drives the story loop for one slice: a strict wait becomes a soft one (QUEST-WAIT), the engine's reserved
  event names (PASS/FAIL/STALL/MILESTONE/STATE/BUG/BRAIN/CREW-*/PBOT-*) are renamed QUEST-..., so they never end or
  confuse the brain's run, the story moving is 'progress'; H.snap and the chapter picture are events, never pictures.
- Fits pbot/skills/INTERFACE.md: limit/crewOk set, cut() keeps the loop state, stable bug keys 'quests-...', quiet
  (want() None) after a BOT bug, a limit cut, or three idle slices in a row.
- A magic word asked for never reaches the game: the slice ends, res 'bot', a BOT bug is filed.
- The whole bot process runs the story engine by the player policy (STORY_PLAYER=1).
s_story is a stand-in here (its player policy has its own test, t_story_player.py).
Run: python3.9 t_quests.py <harness dir>"""
import importlib, os, sys, time, types

D = os.path.abspath(sys.argv[1])
FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


# ---- a stand-in story engine
S = types.ModuleType('s_story')
S.ASIDE, S.LADDERS = {}, ['MainStory']
S.held, S.score = [], [(3, 0)]
S.script = []                           # what the next loop() does: a list of walker items / ('mw', w) / ('ev', n)


S.TASK = {}                             # qid -> the class name of its first task (default a visit)
S.s_shipquest = types.SimpleNamespace(SHIP_TYPES=('DefeatShipTaskDNA',), DOCK_TYPES=('MaroonNPCTaskDNA',))
S.ENEMY_TYPES = ('DefeatTaskDNA',)


def _q(qid):
    task = type(S.TASK.get(qid, 'VisitTaskDNA'), (), {})()
    return types.SimpleNamespace(getQuestId=lambda: qid, isComplete=lambda: False,
                                 questDNA=types.SimpleNamespace(getTasks=lambda: [task]))


S.mainQuest = lambda H: _q(S.held[0]) if S.held else None
S.chunkScore = lambda H: S.score[0]
S.shot = lambda H, name: H.pictures.append(name)
S.HOOKS, S.PISTOL_OWNED = [], set()
for _n in ('tutNo', 'okAndName', 'tutWatch', 'tutPlay'):
    setattr(S, _n, (lambda n: lambda H: S.HOOKS.append(n))(_n))
P = types.ModuleType('s_pistol')
P.install = lambda H: (S.HOOKS.append('pistol'), {'pistolTut'})[1]
sys.modules['s_pistol'] = P


def _loop(H, L):
    for it in S.script:
        k = it[0] if isinstance(it, tuple) else None
        if k == 'mw':
            H.mw(it[1])
        elif k == 'ev':
            H.ev(it[1], why='x')
        elif k == 'evname':
            H.ev(it[1], name='door')         # the engine's TARGET-GONE carries its own name= field
        elif k == 'score':
            S.score[0] = it[1]
        elif k == 'tend':
            S.TENDS.append(L['t_end'] - time.time())
        elif k == 'cur':
            L['cur']['id'] = it[1]
        elif k == 'boom':
            raise KeyError('boom')
        elif k == 'snap':
            H.snap(it[1])
        elif k == 'shot':
            S.shot(H, it[1])
        else:
            got = yield it
            L['seen'].append(('got', got))


S.loop = _loop
S.here, S.stepUid, S.token, S.drop, S.hops = ['PR'], [None], [True], set(), []
S.sailing = types.SimpleNamespace(hereUid=lambda H: S.here[0])
S.stepIslandUid = lambda H: S.stepUid[0]
S.mapOk = lambda H, uid: S.token[0]


def _mapHop(H, uid, why=''):
    S.hops.append(uid)
    if uid not in S.drop:
        S.here[0] = uid


def _skipQ(H, qid, why=''):
    S.ASIDE[qid] = why
    H.ev('ASIDE', q=qid, why=why)
    return False


S.mapHop, S.skipQ = _mapHop, _skipQ
sys.modules['s_story'] = S
sys.path.insert(0, os.path.join(D, 'pbot', 'skills'))
os.environ.pop('STORY_PLAYER', None)
try:
    Q = importlib.import_module('quests')
except ImportError as e:
    print('FAIL:\n  no quest skill (pbot/skills/quests.py): %s' % e)
    sys.exit(1)

check(os.environ.get('STORY_PLAYER') == '1', 'the quest skill does not put the bot on the player policy')


class FakeH:
    def __init__(self):
        self.words, self.evs, self.pictures = [], [], []
        self.la = types.SimpleNamespace(doId=100000999, name='Bot', getGameState=lambda: 'LandRoam')

    def mw(self, w):
        self.words.append(w)

    def ev(self, name, /, **kw):
        self.evs.append((name, kw))

    def qids(self):
        return list(S.held)

    def area(self):
        return ('pr', 0)

    def snap(self, tag):
        self.pictures.append(tag)

    def names(self):
        return [e[0] for e in self.evs]


class Brain:
    def __init__(self, H, cap=None):
        self.H, self.cap, self.bugs = H, cap, []

    def captain(self):
        return self.cap

    def bug(self, kind, key, tag, what, tb=''):
        self.bugs.append((kind, key, tag, what))


def drive(gen, answer=True):
    """Run a flow like the brain does; answer each yielded item with `answer`; -> (items, result)."""
    items, send = [], None
    while True:
        try:
            it = gen.send(send)
        except StopIteration as e:
            return items, e.value
        items.append(it)
        send = answer


# want(): crew / solo / nothing held
H = FakeH()
S.held = ['c3.1visitA']
check(Q.Quests(Brain(H, cap=100000656)).want() is None, "in Player1's crew the quest skill still asked for the turn")
w = Q.Quests(Brain(H)).want()
check(w is not None and w[0] > 0 and 'c3.1visitA' in w[1], 'solo with a held quest the skill did not ask: %r' % (w,))
S.held = []
check(Q.Quests(Brain(H)).want() is None, 'with nothing held the skill still asked for the turn')

# flow(): a strict wait becomes soft, the engine's verdict and stall lines are renamed, progress counted
S.held = ['c3.1visitA']
S.score[0] = (3, 0)
S.script = [('until', lambda: False, 30, 'npc talk'), ('ev', 'STALL'), ('ev', 'PASS'), ('ev', 'MILESTONE'),
            ('ev', 'STATE'), ('ev', 'CREW-JOIN'), ('ev', 'STORY-STEP'), ('evname', 'TARGET-GONE'), ('snap', 'c3-x'), ('shot', 'chapter3'),
            ('score', (4, 0)), 5]
H = FakeH()
B = Brain(H)
items, r = drive(Q.Quests(B).flow())
check(items and items[0][0] == 'upto' and items[0][2] == 30, 'a strict wait reached the walker as strict: %r' % items[:1])
check('QUEST-WAIT' in H.names(), 'a strict wait that ran out logged no QUEST-WAIT')
check('STALL' not in H.names() and 'QUEST-STALL' in H.names(), 'the engine STALL was not renamed')
check('PASS' not in H.names() and 'QUEST-PASS' in H.names(), 'the engine PASS was not renamed (it would end the run)')
for n in ('MILESTONE', 'STATE', 'CREW-JOIN'):
    check(n not in H.names() and 'QUEST-' + n in H.names(), 'the reserved name %s was not renamed' % n)
check('STORY-STEP' in H.names(), 'an ordinary engine event was renamed')
check(('TARGET-GONE', {'name': 'door'}) in H.evs, 'an engine event with its own name= field did not pass through')
check(not H.pictures, 'a picture was taken in play: %s' % H.pictures)
check('QUEST-SNAP' in H.names() and 'QUEST-CHAPTER' in H.names(), 'snap / chapter picture left no event')
check(r and r['res'] == 'progress' and r['stalls'] == 1, 'a slice where the story moved was not progress: %r' % r)
check(5 in items, 'a plain sleep did not reach the walker')
check(not B.bugs and not H.words, 'a clean slice filed a bug or sent a word')
check(S.HOOKS == ['tutNo', 'okAndName', 'pistol', 'tutWatch', 'tutPlay'] and 'pistolTut' in S.PISTOL_OWNED,
      "the engine's player helpers (tutorial No, Darby's OK, pistol) were not put in before the loop: %s" % S.HOOKS)
check([n for n in H.names() if n == 'QUEST-SLICE'] == ['QUEST-SLICE', 'QUEST-SLICE'], 'no QUEST-SLICE start/end')

# flow(): the engine asks for a magic word -> never sent, slice ends, BOT bug
S.script = [1, ('mw', 'skipQuest c3.1visitA'), 2]
H = FakeH()
B = Brain(H)
items, r = drive(Q.Quests(B).flow())
check(H.words == [], 'a magic word reached the game: %s' % H.words)
check('QUEST-MW-BLOCKED' in H.names(), 'no QUEST-MW-BLOCKED line')
check(r['res'] == 'bot' and 2 not in items, 'the slice went on after a magic word: %r' % r)
check(B.bugs and B.bugs[0][2] == 'BOT' and B.bugs[0][0] == 'other', 'no BOT bug for the magic word: %r' % B.bugs)
check(B.bugs and B.bugs[0][1] == 'quests-mw-blocked', 'the magic-word bug key is not stable: %r' % B.bugs[:1])

# flow(): the engine crashes -> traceback BOT bug, the brain keeps going (no raise)
S.script = [('boom',)]
H = FakeH()
B = Brain(H)
sk = Q.Quests(B)
try:
    items, r = drive(sk.flow())
    check(r['res'] == 'bot' and B.bugs and B.bugs[0][0] == 'traceback', 'an engine crash filed no traceback bug')
    check(B.bugs and B.bugs[0][1].startswith('quests-crash-keyerror') and '0x' not in B.bugs[0][1],
          'the crash bug key is not a stable slug: %r' % B.bugs[:1])
    check(sk.want() is None and 'QUEST-QUIET' in H.names(), 'after a BOT bug the skill still asked for the turn')
except Exception as e:
    check(False, 'an engine crash escaped the skill: %r' % e)

# flow(): nothing moved -> idle; L survives across slices
S.score[0] = (3, 0)                     # the first slice moves the story, then nothing does
S.script = [('score', (4, 0)), 1]
H = FakeH()
sk = Q.Quests(Brain(H))
drive(sk.flow())
L0 = sk.L
items, r = drive(sk.flow())
check(r['res'] == 'idle', 'a slice where nothing moved was not idle: %r' % r)
check(sk.L is L0 and len(L0['seen']) == 2, 'the story loop state was not kept across slices')
check(len(S.HOOKS) == 5, 'the player helpers were put in more than once: %s' % S.HOOKS)
check(sk.want() is not None, 'one idle slice already made the skill quiet')   # the first slice moved
drive(sk.flow())
check(sk.want() is not None, 'two idle slices already made the skill quiet')
drive(sk.flow())
check(sk.want() is None, 'three idle slices in a row did not make the skill quiet')
sk.quietUntil = 0
check(sk.want() is not None, 'the quiet time never ends')

# flow(): a sea fight, a dock sail or a land hunt gets the long slice (the engine caps the fight at the slice's end)
S.script, S.TENDS = [('tend',)], []
S.TASK = {'c3r1.1sinkNavyShips': 'DefeatShipTaskDNA', 'c3r1.2defeatNavyGuards': 'DefeatTaskDNA',
          'c2.4maroon': 'MaroonNPCTaskDNA'}
for qid in ('c3r1.1sinkNavyShips', 'c3r1.2defeatNavyGuards', 'c2.4maroon', 'c3.1visitA'):
    S.held = [qid]
    drive(Q.Quests(Brain(FakeH())).flow())
check(len(S.TENDS) == 4 and all(500 < t <= 540 for t in S.TENDS[:3]) and 100 < S.TENDS[3] <= 150,
      'a fight quest did not get the long slice, or a visit did: %s' % [round(t) for t in S.TENDS])
S.TASK, S.held = {}, ['c3.1visitA']

# INTERFACE: limit, crewOk, cut()
check(Q.Quests.limit == 600 and Q.Quests.crewOk is False and Q.Quests.name == 'quests', 'limit/crewOk/name not set')
H = FakeH()
sk = Q.Quests(Brain(H))
drive(sk.flow())
L0 = sk.L
check(sk.cut('safety') is None and sk.L is L0 and 'QUEST-CUT' in H.names(), 'cut() did not keep the loop state')
check(sk.want() is not None, 'a safety cut made the skill quiet')
sk.cut('limit')
check(sk.want() is None, 'a cut at the limit did not make the skill quiet')

# run(): refuses the boys' and Host's pirates
for pid in (100000170, 100000656, 100000665):
    H = FakeH()
    H.la.doId = pid
    list(Q.run(H))
    check(H.names() == ['FAIL'], 'the step script played as protected pirate %s' % pid)

# flow(): the quest's door is on another island (proofs 9-10: recoverClaw's door on Tortuga, the pirate on Port Royal;
# the engine sails only for an island step, so he walked to Port Royal doors until a 420 s stall, every proof) -> the
# loop stops at once, then the map's teleport there, or the quest is set aside when there is none
CLAW = 'c3r2r1r1.1recoverClaw'


def door(stype=6, step='TORT', token=True, drop=(), active=CLAW):
    S.here[0], S.stepUid[0], S.token[0], S.drop, S.hops[:] = 'PR', step, token, set(drop), []
    S.ASIDE.clear()
    S.held, S.script = [CLAW], [('cur', CLAW), 1, 1, 1]
    H = FakeH()
    H.la.activeQuestId, H.la.questStep = active, types.SimpleNamespace(getStepType=lambda: stype)
    H.cancels = []
    H.walk_cancel = lambda: H.cancels.append(1)
    sk = Q.Quests(Brain(H))
    sk._l()['cur']['st'] = {'approach': (401001755, 401001753)}
    items, r = drive(sk.flow())
    hop = [k for n, k in H.evs if n == 'QUEST-DOOR-HOP']
    return H, sk, items, r, hop


H, sk, items, r, hop = door()
check(1 not in items and H.cancels, 'a door step on another island was walked to on this one: %s' % items)
check(S.hops == ['TORT'] and S.here[0] == 'TORT' and any(i[:1] == ('upto',) and i[3] == 'door hop' for i in items),
      'no map teleport to the island of the quest door: %s' % S.hops)
check(hop and hop[0]['ok'] is True and sk.L['cur']['st'] == {} and CLAW not in S.ASIDE and H.words == [],
      'the door hop landed but was not counted: %s %s' % (hop, sk.L['cur']['st']))
H, sk, items, r, hop = door(token=False)
check(1 not in items and S.hops == [] and CLAW in S.ASIDE and hop and hop[0]['ok'] is False,
      'a door on an island he holds no teleport for was not set aside at once: %s %s' % (S.hops, S.ASIDE))
H, sk, items, r, hop = door(drop=['TORT'])
check(S.hops == ['TORT'] and S.here[0] == 'PR' and CLAW in S.ASIDE, 'a door hop that never landed was not set aside')
for kw, what in ((dict(step='PR'), 'a door on this island'), (dict(stype=3), 'an island step (the engine sails it)'),
                 (dict(active='c3.9other'), 'a step of another quest'), (dict(step=None), 'a step naming no island')):
    H, sk, items, r, hop = door(**kw)
    check(items.count(1) == 3 and S.hops == [] and not hop and not S.ASIDE, '%s stopped the slice' % what)
S.ASIDE.clear()
S.held, S.script = ['c3.1visitA'], []

# pure helpers
check(Q.moved((3, 0), (3, 1)) and Q.moved((3, 5), (4, 0)) and not Q.moved((3, 1), (3, 1)), 'moved() wrong')
check(Q.doorAway(6, 'T', 'P') == 'T' and Q.doorAway(5, 'T', 'P') == 'T' and Q.doorAway(3, 'T', 'P') is None and
      Q.doorAway(6, 'P', 'P') is None and Q.doorAway(6, None, 'P') is None and Q.doorAway(6, 'T', None) is None,
      'doorAway() wrong')
check(Q.choose(None, None) is None and Q.choose(1, 'x') is None and Q.choose(None, 'x')[0] > 0, 'choose() wrong')

print('FAIL:\n  ' + '\n  '.join(FAILS) if FAILS else 'quests ok')
sys.exit(1 if FAILS else 0)
