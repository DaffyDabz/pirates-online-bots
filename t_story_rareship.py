"""Offline test of s_story.rareShip (MAIN30, 11-21): Archer's capture counts only Navy warships, about 3 lv-9
Panthers in the whole sea; a 600 s far search saw 22 ships and none it counts (SHIP-NO-TARGET), and SHIP_LIMIT (1800 s)
never ran out inside a 20-min chunk, so every chunk would hunt again. A branch quest whose hunt ends 'no-target' with
no progress is now skipped ('rare'). MAIN31: the one counted ship found was a lv-19 Centurion for a lv-12
pirate; it broke off and sailed home to repair. A hunt whose counted ships are all too strong is skipped ('strong').
Run: python3.9 t_story_rareship.py <dir holding s_story.py>"""
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

rs = getattr(S, 'rareShip', None)
assert rs is not None, 'MAIN30: no rareShip, a branch ship quest with no counted ship at sea is hunted again every chunk'
Q = 'c3r3r1r25r2.1captureArcher'
# MAIN30's own end: SHIP-STEP r no-target, progress [[0, 0]] before and after
assert rs('no-target', [[0, 0]], [[0, 0]], Q) == 'rare'
# MAIN31: one Centurion lv 19 counted, the pirate lv 12: broke off, sailed home to repair, chunk over with no progress
assert rs('timeout', [[0, 0]], [[0, 0]], Q, [19], 12) == 'strong'
assert rs('broke off 3 times', [[0, 0]], [[0, 0]], Q, [19, 39], 12) == 'strong'
# a Panther lv 9 among them can be fought: hunt on; so can lv 15 (inside WEAK_MARGIN 3)
assert rs('timeout', [[0, 0]], [[0, 0]], Q, [9, 19], 12) is None
assert rs('timeout', [[0, 0]], [[0, 0]], Q, [15], 12) is None
assert rs('timeout', [[0, 0]], [[0, 0]], Q, [], 12) is None
assert rs('timeout', [[0, 0]], [[0, 0]], Q, None, 12) is None
# progress moved, another ending, or a main-line quest: hunt on (the STALL still guards the main line)
assert rs('no-target', [[0, 0]], [[1, 0]], Q) is None
assert rs('timeout', [[0, 0]], [[1, 0]], Q, [19], 12) is None
for r in ('timeout', 'foe-sunk', 'credit', 'our-ship-sunk', 'launch-failed', None):
    assert rs(r, [[0, 0]], [[0, 0]], Q) is None, r
assert rs('no-target', [[0, 0]], [[0, 0]], 'c3.1sinkShips') is None
assert rs('timeout', [[0, 0]], [[0, 0]], 'c3.1sinkShips', [19], 12) is None
assert rs('no-target', [[0, 0]], [[0, 0]], 'c2.2defeatSkeletons') is None
# MAIN43: Biggleton's hunt timed out the second it picked a fair lv-19 Centurion: hunt again, no skip
assert rs('timeout', [[0, 0]], [[0, 0]], Q, [19, 39], 14, fair=True) is None, 'MAIN43: skipped as too strong with a fair foe picked'
assert rs('no-target', [[0, 0]], [[0, 0]], Q, None, 14, fair=True) == 'rare'
assert rs('no-target', [[0, 0]], [[0, 0]], None) is None
S.SHIP_RARE_SKIP = False
assert rs('no-target', [[0, 0]], [[0, 0]], Q) is None
assert rs('timeout', [[0, 0]], [[0, 0]], Q, [19], 12) is None
print('rareship ok')
