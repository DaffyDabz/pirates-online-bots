"""Offline test of s_story.runFrom (MAIN23, 11-21): a level-11 War Sloop traded broadsides with level 34-39 warships
at hull 0.75 and only ran at 0.47, then sank with the boys aboard. A ship 10+ levels above ours near us is run from
once hit (MAIN25: at any hull it fought the wide pass and never arrived). MAIN32 (11-22): at hull 0.35 it ran ~500 s from warships trailing at
2500 ft that never fired again; a ship not hit for HIT_QUIET seconds sails on. Run: python3.9 t_story_flee.py <dir holding s_story.py>"""
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
rf = getattr(S, 'runFrom', None)
assert rf is not None, 'MAIN23: no runFrom, the sail runs only below half hull'
assert rf(0.75, 11, [39, 34, 44])          # MAIN23's spot: Dreadnought lv39 at 1067 ft, hull 0.75
assert not rf(1.0, 11, [21])               # unhit: pass it wide, never run (MAIN25 swapped flee/avoid ~60 times)
assert not rf(1.0, 11, [41, 28, 39])       # MAIN25's spot off Padres at hull 1.0
assert rf(0.9, 11, [21])                   # hit and 10 above: run
assert not rf(0.85, 11, [18, 9])           # Shadow Crow lv18 / Panther lv9: fight on, as MAIN23 did and won
assert rf(0.45, 11, [2])                   # low hull: any ship near (unchanged)
assert not rf(0.45, 11, [])                # nothing near: no run
assert not rf(None, 0, [5])                # hull unread, level unread: fight on
# MAIN32: hull 0.35, Black Harbinger lv36 / Man-O-War lv29 / Bulwark lv6 trailing, last hit 300 s ago: sail on
assert rf(0.35, 12, [36, 29, 6], 0.0)       # hit just now: run (MAIN23 still holds)
assert rf(0.35, 12, [36, 29, 6], 25.0)      # hit 25 s ago: still run
assert not rf(0.35, 12, [36, 29, 6], 300.0) # nothing has hit us for 300 s: pass them, do not turn back
assert not rf(0.9, 11, [21], 31.0)
assert rf(0.9, 11, [21], 5.0)
print('flee ok')
