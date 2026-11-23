"""Offline test of s_story.mainQuest (MAIN13, 11-21): 100000596 holds a stale c3r2.5.5visitOrinda (finished, its
questInt already in the quest history, so the server refuses it 'already completed') and the finished
c3r3r1.7recoverBarrel. The bot picked the stale one, sailed back to Tortuga and talked to Orinda for 9 minutes. A
finished quest already in the history comes last; an open quest still comes first.
Run: python3.9 t_story_stale.py <dir holding s_story.py>"""
import importlib, os, sys, types

D = os.path.abspath(sys.argv[1])
os.environ['PROOF_SCRIPT'] = os.path.join(D, 'x.py')
stub = lambda n: sys.modules.setdefault(n, types.ModuleType(n))
lanes = stub('s_lanes')
lanes.PR, lanes.TORTUGA = 'pr', 'tg'
for n in ('sailing', 'paths', 's_shipquest', 's_cards', 's_guards', 's_earn'):
    stub(n)
sys.modules['s_cards'].playTypes = lambda: ()
sys.modules['s_cards'].TYPES = {}
os.environ.update(STORY_START='x', STORY_STOP='x')
os.environ['STORY_LADDER'] = ','
for n in ('pirates', 'pirates.quest', 'pirates.quest.QuestLadderDB', 'pirates.quest.QuestDNA',
          'pirates.quest.QuestConstants', 'pirates.quest.QuestDB'):
    stub(n)
sys.modules['pirates.quest.QuestDNA'].QuestDNA = type('QuestDNA', (), {})
sys.modules['pirates.quest.QuestConstants'].getLocationList = lambda loc: [loc]
INTS = {'c3r2.5.5visitOrinda': 3350, 'c3r3r1.7recoverBarrel': 3957, 'c3r3r1.8deliverBarrel': 3958}
sys.modules['pirates.quest.QuestDB'].QuestDict = dict(
    (k, types.SimpleNamespace(getQuestInt=lambda v=v: v)) for k, v in INTS.items())
sys.modules['pirates.quest'].QuestDB = sys.modules['pirates.quest.QuestDB']
sys.path.insert(0, D)
S = importlib.import_module('s_story')


class Q:
    def __init__(self, qid, done):
        self.qid, self.done = qid, done

    def getQuestId(self): return self.qid
    def isComplete(self): return self.done


def pick(held, hist):
    la = types.SimpleNamespace(getQuestHistory=lambda: list(hist))
    S.mainQuests = lambda H: list(held)
    return S.mainQuest(types.SimpleNamespace(la=la)).getQuestId()


stale, barrel = Q('c3r2.5.5visitOrinda', True), Q('c3r3r1.7recoverBarrel', True)
got = pick([stale, barrel], [3349, 3350])
assert got == 'c3r3r1.7recoverBarrel', 'MAIN13: picked %s, the stale Orinda quest the server refuses' % got
assert pick([stale, Q('c3r3r1.8deliverBarrel', False)], [3350]) == 'c3r3r1.8deliverBarrel'   # open first, as before
assert pick([stale, barrel], []) == 'c3r2.5.5visitOrinda'          # not in the history: the earliest, as before
assert pick([stale], [3350]) == 'c3r2.5.5visitOrinda'              # only a stale one held: still worked on
print('stale ok')
