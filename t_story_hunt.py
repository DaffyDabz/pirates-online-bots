"""Offline test of s_story.huntAreas (DOLL18, 11-21): the rock crab blood quest names no place, the beam sent him to
Padres' south beach and no walk from where he lands reached it. A kill task that names no place is hunted in its HUNT
areas; one that names a place, or an enemy HUNT does not list, follows the old way.
Run: python3.9 t_story_hunt.py <dir holding s_story.py>"""
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
          'pirates.quest.QuestConstants'):
    stub(n)
sys.modules['pirates.quest.QuestDNA'].QuestDNA = type('QuestDNA', (), {})
sys.modules['pirates.quest.QuestConstants'].getLocationList = lambda loc: [loc]
sys.path.insert(0, D)
S = importlib.import_module('s_story')
assert hasattr(S, 'huntAreas'), 'DOLL18: no huntAreas, a blood quest follows the beam to the unreachable beach'
AT = types.SimpleNamespace(RockCrab=object(), Scorpion=object(), Wasp=object(), Bat=object(), Alligator=object(),
                           Undead=object(), Clod=object(), Sludge=object(), Mire=object(), Muck=object())
T = lambda et, loc=None: types.SimpleNamespace(enemyType=et, location=loc)
RUM, PRJ = ('1161282725.84kmuller',), ('1164141722.61sdnaik',)
assert S.huntAreas(T(AT.RockCrab), AT) == RUM          # DOLL18's quest: Rumrunner's, not Padres
assert S.huntAreas(T(AT.Wasp), AT) == RUM
for n in ('Scorpion', 'Alligator', 'Bat'):
    assert S.huntAreas(T(getattr(AT, n)), AT) == PRJ, n
PRJA = ('1169592956.59sdnaik',)                         # wdr6 bone dust: the mud monsters, Port Royal jungles A and C
for n, want in (('Clod', PRJ), ('Muck', PRJ), ('Sludge', PRJA), ('Mire', PRJA + PRJ)):
    assert S.huntAreas(T(getattr(AT, n)), AT) == want, n
for a in PRJA + PRJ:                                   # all on Port Royal, so the sail goes to the right island
    assert S.questSpots()['areas'][a][0] == '1150922126.8dzlu', a
assert S.huntAreas(T(AT.RockCrab, 'someIsland'), AT) is None   # names a place: kills elsewhere do not count
assert S.huntAreas(T(AT.Undead), AT) is None                   # not in HUNT: the beam as before
assert S.huntAreas(types.SimpleNamespace(location=None), AT) is None
os.environ['STORY_HUNT'] = '0'
assert S.huntAreas(T(AT.RockCrab), AT) is None
for a in set(RUM + PRJ):                                       # the areas are real quest_spots areas
    assert a in S.questSpots()['areas'] or not S.questSpots()['areas'], a
print('hunt ok')
