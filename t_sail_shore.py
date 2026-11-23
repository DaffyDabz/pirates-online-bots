"""Offline test of sailing.shoreGrow (MAIN22-24, 11-21): every Port Royal -> Padres sail ran aground on Port Royal's
north coast and slid along it for 5 min. Aground (a shore warning, ship slow) grows the nearest island's circle so the
route aims further out. Run: python3.9 t_sail_shore.py <dir holding sailing.py>"""
import os, sys, types

D = os.path.abspath(sys.argv[1])
sys.path.insert(0, D)
for n in ('panda3d', 'panda3d.core', 'direct', 'direct.showbase', 'direct.showbase.DirectObject', 's_dock', 'paths'):
    sys.modules.setdefault(n, types.ModuleType(n))
sys.modules['panda3d.core'].Point3 = sys.modules['panda3d.core'].Vec3 = object
d = sys.modules['s_dock']
d.Keys = d.anchorShown = d.near = d.cls = None
import sailing as S
sg = getattr(S, 'shoreGrow', None)
assert sg is not None, 'MAIN24: no shoreGrow, an aground ship slides along the coast until the sail times out'
W = [(100.0, 'You are sailing too close to shore!')]
obst = [(0.0, 0.0, 3300.0), (20000.0, 0.0, 3300.0)]
st = {}
assert sg(obst, (300.0, 3400.0), W, 7.0, 110.0, st) == 0 and obst[0][2] == 3800.0      # MAIN24: aground, 6.6 ft/s
assert sg(obst, (300.0, 3400.0), W, 7.0, 113.0, st) is None                             # not again within 6 s
assert sg(obst, (300.0, 3400.0), W, 80.0, 120.0, st) is None                            # full speed: not aground
assert sg(obst, (300.0, 3400.0), [], 7.0, 120.0, st) is None                            # no warning: slow for a fight
assert sg(obst, (300.0, 3400.0), W, 7.0, 200.0, st) is None                             # warning 100 s old
assert sg(obst, (10000.0, 9000.0), W, 7.0, 120.0, st) is None                           # far from every island
for k in range(4):
    assert sg(obst, (300.0, 3400.0), W, 7.0, 120.0 + 7 * k, st) == 0
assert obst[0][2] == 5800.0 and sg(obst, (300.0, 3400.0), W, 7.0, 150.0, st) is None    # SHORE_MAX reached
assert obst[1][2] == 3300.0
print('shore ok')
