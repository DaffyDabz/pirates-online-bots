"""Offline test of s_shipfight.chaseStep after a repair (MAIN4, 11-21): the hurt Spanish Cerberus came back into view
5943 ft off, 252 s after the bot broke off at 1639 ft, and was dropped in the same tick as 'not closing in'. A foe
unseen for CHASE_GAP s now starts a fresh chase; a chase seen every tick still gives up after CHASE_SECS.
Run: python3.9 t_shipfight_chase.py <dir holding s_shipfight.py>"""
import importlib, os, sys, types

D = os.path.abspath(sys.argv[1])
os.environ['PROOF_SCRIPT'] = os.path.join(D, 'x.py')
lanes = types.ModuleType('s_lanes')
lanes.PR = lanes.TORTUGA = 'x'
sq = types.ModuleType('s_shipquest')
sail = types.ModuleType('sailing')
sys.modules.update({'s_lanes': lanes, 's_shipquest': sq, 'sailing': sail})
sys.path.insert(0, D)
S = importlib.import_module('s_shipfight')
FOE = 401032519


def run(samples, hurt=True):
    st, gone = None, None
    for t, d in samples:
        st, gone = S.chaseStep(st, FOE, d, t, hurt, r=1000, secs=90, gain=300)
        if gone:
            return t, gone
    return None, None


# MAIN4: chased to 1639 ft, broke off at t=10 (no more samples while repairing), seen again at t=262 5943 ft off
t, gone = run([(0, 1800), (5, 1639), (10, 1700), (262, 5943), (263, 5905)])
assert gone is None, 'MAIN4: a re-acquired foe was dropped at once: %s at t=%s' % (gone, t)
# the fresh chase is still timed: seen every second, never gaining, gives up after 2 x 90 s (hurt foe)
t, gone = run([(262 + i, 5943) for i in range(200)])
assert gone and t == 262 + 180, (t, gone)
t, gone = run([(i, 3000) for i in range(100)], hurt=False)
assert gone and t == 90, (t, gone)
# closing in keeps it going
t, gone = run([(i, 6000 - 20 * i) for i in range(250)])
assert gone is None, gone
print('chase ok')
