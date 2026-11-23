"""Offline test of sailing.legOver + hookWarnings (row 13, 11-22).
1. ISLANDTOUR3 (11-19) leg Tortuga -> Padres: the hidden game ran ~2.5 fps and the game caps a frame at 0.2 s, so the
   ship made 33 ft/s real at 80 ft/s full sail and the wall-clock 900 s limit ended the leg 22k ft short. The limit now
   counts game seconds (a wall cap still ends a frozen game).
2. A second sail_to in one game kept no shore warnings (the hook appended to the first sail's list), so shoreGrow and
   freshReef went blind after the first leg.
Run: python3.9 t_sail_clock.py <dir holding sailing.py>"""
import os, sys, types

D = os.path.abspath(sys.argv[1])
sys.path.insert(0, D)
for n in ('panda3d', 'panda3d.core', 'direct', 'direct.showbase', 'direct.showbase.DirectObject', 's_dock', 'paths'):
    sys.modules.setdefault(n, types.ModuleType(n))
sys.modules['panda3d.core'].Point3 = sys.modules['panda3d.core'].Vec3 = object
d = sys.modules['s_dock']
d.Keys = d.anchorShown = d.near = d.cls = None
import sailing as S

# 1. a 44k ft leg (Tortuga -> west of Devil's Anvil -> Padres) at 80 ft/s game speed, the game at 2.5 fps (wall 0.4 s per
#    frame, game 0.2 s per frame: MAX_DT). Walk frame by frame until the leg is sailed or the limit says stop.
lo = getattr(S, 'legOver', None)
assert lo is not None, 'ISLANDTOUR3: no legOver, a slow-motion game runs out of wall clock 22k ft short'
MAX_DT, WALL_DT, SPEED, LEG = 0.2, 0.4, 80.0, 44000.0
g = t = sailed = 0.0
why = None
while sailed < LEG:
    why = lo(0.0, g, 0.0, t)
    if why:
        break
    g += MAX_DT; t += WALL_DT; sailed += SPEED * MAX_DT
assert why is None, 'ISLANDTOUR3: %s with %d ft left (game %d s, wall %d s)' % (why, LEG - sailed, g, t)
print('slow game: leg sailed in %d game s / %d wall s' % (g, t))
assert lo(0.0, 900.0, 0.0, 900.0)                        # a full-speed game still stops at LEG_SECS
assert lo(0.0, 100.0, 0.0, 900.0 * S.LEG_WALL_X)         # a frozen game still ends on the wall cap
assert lo(0.0, 899.0, 0.0, 899.0) is None

# 2. two sails in one game: the second one's list gets the warnings
hw = getattr(S, 'hookWarnings', None)
assert hw is not None, 'DOLL16: no hookWarnings, a later sail_to never sees a shore warning'
shown, evs = [], []
gm = types.SimpleNamespace(createWarning=lambda text, *a, **k: shown.append(text))
H = types.SimpleNamespace(la=types.SimpleNamespace(guiMgr=gm), ev=lambda k, **kw: evs.append((k, kw)))
w1, w2 = [], []
hw(H, w1)
gm.createWarning('You are sailing too close to shore!')
hw(H, w2)
gm.createWarning('You are sailing too close to shore!')
assert len(w1) == 1 and len(w2) == 1, 'second sail saw %d warnings (first %d)' % (len(w2), len(w1))
assert len(shown) == 2 and len(evs) == 2                 # the game still shows each one; one event each, no double hook
print('clock ok')
