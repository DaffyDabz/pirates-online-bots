"""Offline test of s_story.repeatGrind for ship quests (MAIN6, 11-21): Splinter (RecoverShipItem) was credited for
real, then Grog's r2.9recoverWater (4 EITC ships, lv 37-44) kept a notoriety-7 pirate at sea 9 min with no sink.
A proven ship type is now skipped like a proven land grind; an unproven one, a main-line quest and STORY_GRIND=play
still play for real.
Run: python3.9 t_story_shipskip.py <dir holding s_story.py>"""
import importlib, json, os, sys, tempfile, types

D = os.path.abspath(sys.argv[1])
T = tempfile.mkdtemp()
os.environ['PROOF_SCRIPT'] = os.path.join(T, 'x.py')
stub = lambda n: sys.modules.setdefault(n, types.ModuleType(n))
lanes = stub('s_lanes')
lanes.PR, lanes.TORTUGA = 'pr', 'tg'
for n in ('sailing', 'paths', 's_shipquest', 's_cards', 's_guards', 's_earn'):
    stub(n)
sys.modules['s_cards'].playTypes = lambda: ()
sys.modules['s_cards'].TYPES = {}
os.environ.update(STORY_START='x', STORY_STOP='x')
os.environ['STORY_LADDER'] = ','
for n in ('pirates', 'pirates.quest', 'pirates.quest.QuestLadderDB', 'pirates.quest.QuestDNA'):
    stub(n)
sys.modules['pirates.quest.QuestDNA'].QuestDNA = type('QuestDNA', (), {})
sys.path.insert(0, D)
S = importlib.import_module('s_story')

RecoverShipItemTaskDNA = type('RecoverShipItemTaskDNA', (), {})
DefeatShipTaskDNA = type('DefeatShipTaskDNA', (), {})
DefeatTaskDNA = type('DefeatTaskDNA', (), {})


def quest(qid, task, fin=None):
    dna = types.SimpleNamespace(getTasks=lambda: [task()], getFinalizeInfo=lambda: fin)
    return types.SimpleNamespace(getQuestId=lambda: qid, questDNA=dna)


WATER = quest('c3r2r5r2.9recoverWater', RecoverShipItemTaskDNA)
assert S.repeatGrind(WATER) is None                  # nothing proven yet: play for real
assert S.prove('c3r2r5r2.5recoverSplinter', 'RecoverShipItemTaskDNA', 'MAIN6')
assert S.repeatGrind(WATER) == 'RecoverShipItemTaskDNA', 'MAIN6: a proven ship drop still plays 4 EITC ships for real'
assert S.repeatGrind(quest('c3r1.2defeatShips', DefeatShipTaskDNA)) is None      # DefeatShip not proven on its own
assert S.repeatGrind(quest('c3.5recoverThing', RecoverShipItemTaskDNA)) is None  # main line: always for real
assert S.repeatGrind(quest('c3r2r9.2recoverX', RecoverShipItemTaskDNA, fin=[1])) is None   # own scenes
# DOLL13: the doll chain's ship drop is the same proven type; its land steps still play
assert S.repeatGrind(quest('wdr2.3recoverSilk', RecoverShipItemTaskDNA)) == 'RecoverShipItemTaskDNA', 'DOLL13: Silk played for real'
assert S.repeatGrind(quest('wdr4.1bloodOfRockCrab', DefeatTaskDNA)) is None      # chain land steps: always for real
assert S.repeatGrind(quest('wdr2Materials', RecoverShipItemTaskDNA)) is None     # a chain's parent id, not a step
# DOLL14: the card-game skip list must stay the card games, never the grinds
assert not set(S.SKIP_TYPES) & set(S.REPEAT_TYPES), 'DOLL14: grinds in the type-off skip list %s' % (S.SKIP_TYPES,)
os.environ['STORY_GRIND'] = 'play'
assert S.repeatGrind(WATER) is None
del os.environ['STORY_GRIND']
assert 'RecoverShipItemTaskDNA' not in S.GRIND_TYPES  # land-only list (landPort, aboard sail) unchanged
assert S.landPort('RecoverShipItemTaskDNA', (0, 0)) is None
assert json.load(open(os.path.join(T, 'story-proven.json')))['RecoverShipItemTaskDNA']['tag'] == 'MAIN6'
print('shipskip ok')
