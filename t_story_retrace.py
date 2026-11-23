"""Offline test of s_story.searchReach / retraceWay (MAIN39, 11-22).
1. stealSchedule: he stood 4.9 ft from the chest on the Padres cliff, inside its 'Search' prompt (sphereScale, 5 ft by
   default), walked at 3 ft for 3.5 min and the quest was skipped: a container now counts as reached inside its sphere.
2. deliverRum, next: every route search from that cliff back to the tavern door ran out 780 ft short (73 s each) for
   5 min, though he had just walked up from that door: walk back the way he came.
Run: python3.9 t_story_retrace.py <dir holding s_story.py>"""
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

sr = getattr(S, 'searchReach', None)
assert sr is not None, 'MAIN39: no searchReach, 4.9 ft from the chest (inside its Search prompt) he walked 3.5 min'
assert sr(5.0) >= 4.94, sr(5.0)        # MAIN39's nearest: 4.94 ft, the default 5 ft sphere
assert sr(None) == 3.0 and sr('x') == 3.0 and sr(1.0) == 3.0
assert sr(30.0) == S.CONTAINER_REACH    # never further than a player would plausibly search from

rw = getattr(S, 'retraceWay', None)
assert rw is not None, 'MAIN39: no retraceWay, 5 min of 73 s searches on the cliff he had just walked up'
PAD = '1142018473.22dxschafe'
# the walk up from outside the tavern to the chest (MAIN39 'to-container' route, the points he stood on)
TRAIL = {'area': PAD, 'pts': [(8347.4, -23547.6, 70.5), (8151.4, -23719.6, 81.0), (8038.8, -23830.5, 83.5),
                              (7938.8, -23810.5, 70.0), (7509.2, -23694.6, 150.2)]}
ME, DOOR = (7509.6, -23694.4, 150.2), (8357.0, -23549.9, 75.0)
b = rw(TRAIL, PAD, ME, DOOR)
assert b and b[0] == (7938.8, -23810.5, 70.0) and b[-1] == (8347.4, -23547.6, 70.5), b
assert rw(TRAIL, 'other', ME, DOOR) is None                      # another area
assert rw(TRAIL, PAD, (7300.0, -23694.4, 150.2), DOOR) is None   # he walked away from where it ended
assert rw(TRAIL, PAD, ME, (7520.0, -23700.0, 150.2)) is None     # the target is not nearer its start
assert rw({}, PAD, ME, DOOR) is None and rw(None, PAD, ME, DOOR) is None
assert rw({'area': PAD, 'pts': [ME]}, PAD, ME, DOOR) is None
print('t_story_retrace: PASS')
