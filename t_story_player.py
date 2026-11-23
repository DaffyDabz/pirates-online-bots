"""Offline test of the player-bot policy (PLAYERBOTS round 2, places 11-22): with STORY_PLAYER=1 the story engine
never sends a magic word. A stall sets the quest ASIDE (the next held quest is played; it comes back after the cooldown
or a level-up), travel uses the map's own island teleport, earning never grants gold, a sunk ship's repair is never
paid by the gold word. Without STORY_PLAYER the story run is unchanged (skipQuest / areaTeleport as before).
Run: python3.9 t_story_player.py <dir holding s_story.py>"""
import importlib, os, sys, tempfile, time, types

D = os.path.abspath(sys.argv[1])
T = tempfile.mkdtemp()
os.environ['PROOF_SCRIPT'] = os.path.join(T, 'x.py')
stub = lambda n: sys.modules.setdefault(n, types.ModuleType(n))
lanes = stub('s_lanes')
lanes.PR, lanes.TORTUGA = 'pr', 'tg'
for n in ('sailing', 'paths', 's_cards', 's_guards', 'panda3d', 'panda3d.core', 's_dock'):
    stub(n)
sys.modules['panda3d.core'].Point3 = sys.modules['panda3d.core'].Vec3 = tuple
sys.modules['s_dock'].Keys = sys.modules['s_dock'].cls = sys.modules['s_dock'].anchorShown = None
sys.modules['s_cards'].playTypes = lambda: ()
sys.modules['s_cards'].TYPES = {}
os.environ.update(STORY_START='x', STORY_STOP='x', STORY_ASIDE_SECS='60')
os.environ['STORY_LADDER'] = ','
for n in ('pirates', 'pirates.quest', 'pirates.quest.QuestLadderDB', 'pirates.quest.QuestDNA', 'pirates.ship',
          'pirates.ship.ShipGlobals'):
    stub(n)
sys.modules['pirates.quest.QuestDNA'].QuestDNA = type('QuestDNA', (), {})
SG = sys.modules['pirates.ship.ShipGlobals']
SG.getRepairCost = lambda ov: 400
SG.getRepairPrice = lambda cost, gold: cost - gold
sys.modules['pirates.ship'].ShipGlobals = SG
sys.path.insert(0, D)
S = importlib.import_module('s_story')
E = importlib.import_module('s_earn')
Q = importlib.import_module('s_shipquest')

FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


def quest(qid, done=False):
    return types.SimpleNamespace(getQuestId=lambda: qid, isComplete=lambda: done)


class Fake:
    def __init__(self, qs, lvl=5, tokens=()):
        self.words, self.evs, self.hops = [], [], []
        self.lvl, self._qs = lvl, qs
        inv = types.SimpleNamespace(getGoldInPocket=lambda: 50, getShipDoIdList=lambda: [7])
        self.la = types.SimpleNamespace(
            getQuests=lambda: list(self._qs), getLevel=lambda: self.lvl, getQuestHistory=lambda: [],
            confirmIslandTeleport=lambda frm, islandUid=None: islandUid in tokens, getInventory=lambda: inv)
        self.cr = types.SimpleNamespace(teleportMgr=types.SimpleNamespace(requestTeleportToIsland=self.hops.append),
                                        getOwnerView=lambda sid: types.SimpleNamespace(Hp=0))

    def mw(self, w):
        self.words.append(w)

    def ev(self, name, **kw):
        self.evs.append((name, kw))

    def qids(self):
        return [q.getQuestId() for q in self._qs]

    def area(self):
        return ('tg', 0)


A, B = quest('c3.1visitA'), quest('c3.2visitB')
S.ORDER.clear()
S.ORDER.update({'c3.1visitA': 0, 'c3.2visitB': 1})
has = all(hasattr(S, n) for n in ('skipQ', 'mapHop', 'aside', 'loop'))
check(has, 'no player policy in s_story (skipQ / mapHop / aside / loop missing): a stall sends ~skipQuest')

if has:
    # story run (no STORY_PLAYER): unchanged, the magic words are sent
    os.environ.pop('STORY_PLAYER', None)
    h = Fake([A, B])
    check(S.skipQ(h, 'c3.1visitA', 'stall') is True and h.words == ['skipQuest c3.1visitA'], 'story skip changed')
    check(S.mapHop(h, 'tg') and h.words[-1] == 'areaTeleport tg', 'story teleport changed')
    S.ASIDE.clear()
    # player bot: a stall sets A aside, no word, B is played next
    os.environ['STORY_PLAYER'] = '1'
    h = Fake([A, B], tokens=('pr',))
    check(S.skipQ(h, 'c3.1visitA', 'no progress') is False, 'player skip said it sent a word')
    check(h.words == [], 'player bot sent a magic word on a stall: %s' % h.words)
    check(S.mainQuest(h) is B, 'set-aside quest A was still picked over B')
    check(any(e[0] == 'ASIDE' for e in h.evs), 'no ASIDE event')
    # a level-up brings A back
    h.lvl = 6
    check(S.mainQuest(h) is A, 'A did not come back after a level-up')
    check(any(e[0] == 'ASIDE-BACK' and e[1]['why'] == 'level-up' for e in h.evs), 'no ASIDE-BACK level-up event')
    # the cooldown brings it back too
    S.skipQ(h, 'c3.1visitA', 'no progress')
    check(S.mainQuest(h) is B, 'A not aside the second time')
    S.ASIDE['c3.1visitA'] = (time.time() - 61, h.lvl, 'x')
    check(S.mainQuest(h) is A, 'A did not come back after the cooldown')
    # everything aside: no quest (the brain's other skills take over), never a skip
    S.skipQ(h, 'c3.1visitA', 'x')
    S.skipQ(h, 'c3.2visitB', 'x')
    check(S.mainQuest(h) is None, 'with every quest aside mainQuest still gave one')
    # travel: the map's own teleport when he holds the token, else nothing; never areaTeleport
    check(S.mapHop(h, 'pr', 'swim') is True and h.hops == ['pr'], 'map hop to a token island not asked')
    check(S.mapHop(h, 'cave', 'swim') is False and h.hops == ['pr'], 'map hop asked without a token')
    check(h.words == [], 'player bot sent a magic word on travel: %s' % h.words)
    # earning past its time: never the gold word
    task = type('BribeNPCTaskDNA', (), {'gold': 300})()
    st = {}
    h = Fake([quest('c3.3bribe')])
    E.step(h, h._qs[0], task, st, now=1000.0)
    E.step(h, h._qs[0], task, st, now=1000.0 + E.EARN_SECS + 1)
    check(not any(w.startswith('gold') for w in h.words), 'player bot granted itself gold: %s' % h.words)
    # sunk ship, cannot pay: no gold word
    h = Fake([])
    SG.getRepairPrice = lambda cost, gold: cost
    list(Q.payRepair(h))
    check(not any(w.startswith('gold') for w in h.words), 'player bot paid a repair by the gold word: %s' % h.words)
    check(any(e[0] == 'REPAIR-SHORT' for e in h.evs), 'no REPAIR-SHORT event')
    # the same two in a story run still use the word (unchanged)
    os.environ.pop('STORY_PLAYER')
    st = {}
    h = Fake([quest('c3.3bribe')])
    E.step(h, h._qs[0], task, st, now=1000.0)
    E.step(h, h._qs[0], task, st, now=1000.0 + E.EARN_SECS + 1)
    check(any(w.startswith('gold') for w in h.words), 'story run no longer grants gold after EARN_SECS')
    h = Fake([])
    list(Q.payRepair(h))
    check(any(w.startswith('gold') for w in h.words), 'story run no longer pays a sunk repair')

print('FAIL:\n  ' + '\n  '.join(FAILS) if FAILS else 'player ok')
sys.exit(1 if FAILS else 0)
