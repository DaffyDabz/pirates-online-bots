"""Offline test of s_story.landPort (DOLL9, 11-21): the straw ship quest ended at sea, the pitch barrels step names no
island, and the bot sat 390 s in aboard-wait. A land task with no step island now sails to the nearest repair port.
Run: python3.9 t_story_landport.py <dir holding s_story.py>"""
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
os.environ['STORY_LADDER'] = ','          # no ladder walked: the game's quest tables are not loaded offline
for n in ('pirates', 'pirates.quest', 'pirates.quest.QuestLadderDB', 'pirates.quest.QuestDNA'):
    stub(n)
sys.modules['pirates.quest.QuestDNA'].QuestDNA = type('QuestDNA', (), {})
sys.path.insert(0, D)
S = importlib.import_module('s_story')
TBL = {'pr': ('Port Royal', 0.0, 0.0, ''), 'tg': ('Tortuga', 10000.0, 0.0, ''), 'x': ('Isla', 3000.0, 0.0, '')}
P = ['pr', 'tg']
lp = getattr(S, 'landPort', None)
assert lp is not None, 'DOLL9: no landPort, a land task aboard with no step island waits forever'
assert lp('RecoverContainerItemTaskDNA', (2724.0, 7172.0), TBL, P) == 'pr'     # DOLL9's spot: Port Royal 9448 ft
assert lp('RecoverContainerItemTaskDNA', (9000.0, 500.0), TBL, P) == 'tg'
assert lp('DefeatTaskDNA', None, TBL, P) == 'pr'
assert lp('VisitTaskDNA', (0.0, 0.0), TBL, P) is None                          # not a land grind: unchanged
assert lp('RecoverContainerItemTaskDNA', (0.0, 0.0), TBL, []) is None
print('landport ok')
