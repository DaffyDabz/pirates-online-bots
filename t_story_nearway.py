"""Offline test of s_story.nearWay (MAIN28, 11-21): Romany stood outdoors on Padres Del Fuego 990 ft from Gunner's door;
the route search ran dry 147 ft from her, so no route, no blind straight walk past BLIND_MAX, and he stood still 420 s
until the STALL skipped her. Now he walks to the point the search got nearest her, and the straight last bit from
there is inside BLIND_MAX.
Run: python3.9 t_story_nearway.py <dir holding s_story.py>"""
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
for n in ('pirates', 'pirates.quest', 'pirates.quest.QuestLadderDB', 'pirates.quest.QuestDNA'):
    stub(n)
sys.modules['pirates.quest.QuestDNA'].QuestDNA = type('QuestDNA', (), {})
sys.path.insert(0, D)
S = importlib.import_module('s_story')

nw = getattr(S, 'nearWay', None)
assert nw is not None, 'MAIN28: no nearWay, a dry search 147 ft short of Romany leaves him standing 420 s'
# MAIN28's own search from outside Gunner's house
ME = (7810.3, -23935.2, 105.5)
MAIN28 = {'expanded': 938, 'nearest': [8546.3, -23519.2, 91.1], 'nearestLeft': 147.0, 'dry': True,
          'startLegs': [401, 37, 401]}
w = nw(990.3, MAIN28, ME)
assert w is not None and abs(w[0] - 8546.3) < 0.1 and abs(w[1] + 23519.2) < 0.1, w
assert S.blindWhy(147.0, MAIN28) is None        # from there the straight last bit is allowed
# DOLL10: the barrel 1341 ft off, the search 20 ft from it: walk there (not straight into the sea)
DOLL10 = {'expanded': 1145, 'nearest': [1099.3, 1098.9, 162.9], 'nearestLeft': 20.0, 'dry': True}
assert nw(1341.4, DOLL10, (0.0, 0.0, 0.0)) is not None
# nothing to gain: the nearest point still past BLIND_MAX, too little nearer, or where he stands
assert nw(990.3, dict(MAIN28, nearestLeft=400.0), ME) is None
assert nw(160.0, dict(MAIN28, nearestLeft=147.0), ME) is None
assert nw(990.3, dict(MAIN28, nearest=[7815.0, -23930.0, 105.5]), ME) is None
assert nw(120.0, MAIN28, ME) is None            # close: the straight last bit as before
assert nw(990.3, {}, ME) is None                # no search ran
assert nw(990.3, dict(MAIN28, expanded=0), ME) is None
print('nearway ok')
