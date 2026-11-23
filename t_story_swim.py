"""Offline test of s_story.blindWhy + swimBack (DOLL10, 11-21): no route to a pitch barrel 1341 ft off on the Port
Royal hill, so the straight last walk took him off the dock into the sea, and he swam on the spot for 15 min waiting
for the game state to change. Now no blind straight walk past BLIND_MAX when the route search ran, and a swim off a
ship swims back to where he last stood on land, SWIM_TRIES times, then a STALL.
Run: python3.9 t_story_swim.py <dir holding s_story.py>"""
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

bw = getattr(S, 'blindWhy', None)
assert bw is not None, 'DOLL10: no blindWhy, a failed route still walks a straight line into the sea'
# DOLL10's own search: 1145 points expanded, ran dry 20 ft short, the barrel 1341 ft off
DOLL10 = {'expanded': 1145, 'nearest': [1099.3, 1098.9, 162.9], 'nearestLeft': 20.0, 'dry': True}
assert bw(1341.4, DOLL10) is not None, 'DOLL10: walked a straight 1341 ft line off the dock'
assert bw(120.0, DOLL10) is None             # close: the straight last bit is still tried
assert bw(1341.4, {}) is None                # no search ran (no floor data here): the old straight walk
assert bw(1341.4, {'expanded': 0}) is None
assert bw(None, DOLL10) is None

sb = getattr(S, 'swimBack', None)
assert sb is not None, 'DOLL10: no swimBack, he swims on the spot until the chunk ends'
cur = {'landPt': (323.5, 24.6, 4.1)}
assert sb(cur, 100.0) is None                # just fell in
assert sb(cur, 103.0) is None
assert sb(cur, 106.0) == 'swim' and cur['swims'] == 1
assert sb(cur, 170.0) == 'swim' and sb(cur, 240.0) == 'swim' and cur['swims'] == 3
# MAIN35 (11-22): three swims back at a cliff, then five story quests skipped in a row while he swam below Padres.
# Now the first answer after the swims is a teleport to a port; only still swimming after that skips the quest.
r = sb(cur, 300.0, qid='q1')
assert r == 'tp', 'MAIN35: three failed swims back skip the quest (%r) instead of a teleport to a port' % (r,)
assert cur['swims'] == 0 and 'swimT' not in cur
assert sb(cur, 301.0, qid='q1') is None      # landed in the water again: wait SWIM_SECS first
assert [sb(cur, t, qid='q1') for t in (307.0, 320.0, 333.0)] == ['swim'] * 3
assert sb(cur, 346.0, qid='q1') == 'stall'   # one teleport per quest, then the old skip
cur2 = dict(cur, swims=3)
assert sb(cur2, 400.0, qid='q2') == 'tp'     # the next quest gets its own teleport
sp = getattr(S, 'swimPort', None)
assert sp is not None and sp('padres') == S.PR and sp(S.PR) == S.TORTUGA and S.TORTUGA != S.PR
assert sb({'landPt': None}, 0.0) is None and sb({}, 50.0) is None    # nowhere known: wait as before
print('swim ok')

# MAIN34 (11-22): a launch walked him into the sea at the Padres dinghy; the 'back on land' wait (LandRoam only) ran
# its full 120 s while he swam. Swimming off a ship now ends that wait too.
aw = getattr(S, 'ashoreOrSwim', None)
assert aw is not None, 'MAIN34: no ashoreOrSwim, a swim after a failed launch waits the full 2 min for LandRoam'
assert aw('WaterRoam', 'padres', False, False), 'MAIN34: swimming at Padres still waits for LandRoam'
assert aw('LandRoam', 'padres', False, False) and aw('LandRoam', None, True, False)   # ashore / in jail as before
assert not aw('LandRoam', None, False, False)            # between areas
assert not aw('WaterRoam', 'padres', False, True)        # on the ship's deck: not a swim
assert not aw('Teleporting', 'padres', False, False)
src = open(os.path.join(D, 's_story.py')).read()
assert "lambda: ashore(H), 120, 'back on land'" not in src, 'MAIN34: a back-on-land wait still ignores swimming'
print('swim-wait ok')
