"""Offline test of s_shipquest.pickTarget (FLAGSHIP1, 11-22): the hunt took the nearest matching ship every tick, so a
nearer flagship (Navy Kingfisher, 1200 hp) took the target for one broadside while the French Shadow Crow sat at 600/2500,
one broadside from crippled; the bot swung back 15 s later and our sloop sank 3 s after. Now the current target is
fought on while it is a match within STICK_R; the nearest is taken only when there is none, or it is gone or far.
A module without pickTarget is judged by the old rule (good[0]), so the old code FAILs here.
Run: python -I t_shipquest_stick.py <dir holding s_shipquest.py>"""
import importlib, os, sys, types

D = os.path.abspath(sys.argv[1])
os.environ['PROOF_SCRIPT'] = os.path.join(D, 'x.py')
pc = types.ModuleType('panda3d.core')
pc.Point3 = pc.Vec3 = tuple
p3 = types.ModuleType('panda3d')
p3.core = pc
dock = types.ModuleType('s_dock')
dock.Keys = dock.cls = dock.anchorShown = None
sys.modules.update({'panda3d': p3, 'panda3d.core': pc, 'sailing': types.ModuleType('sailing'), 's_dock': dock})
sys.path.insert(0, D)
S = importlib.import_module('s_shipquest')
pick = getattr(S, 'pickTarget', lambda good, tgt: good[0])


class Ship:
    def __init__(self, doId, name):
        self.doId, self.name = doId, name


CROW, KING = Ship(401005528, 'French Shadow Crow'), Ship(401005186, 'Navy Kingfisher')
bad = []
# FLAGSHIP1 07:19:07: on the Crow (1336 ft at the last broadside), the Kingfisher comes in nearer at 1360
d, o = pick([(1360, KING), (1400, CROW)], CROW.doId)
if o is not CROW:
    bad.append('FLAGSHIP1: left the Crow at 600 hp for the nearer Kingfisher')
# ... and keeps on it all the way in
d, o = pick([(900, KING), (2500, CROW)], CROW.doId)
if o is not CROW:
    bad.append('a target at 2500 ft (inside STICK_R) was dropped')
# still the nearest when there is no target, it is gone, or it sailed off past STICK_R
if pick([(1360, KING), (1400, CROW)], None)[1] is not KING:
    bad.append('no target: not the nearest')
if pick([(1360, KING)], CROW.doId)[1] is not KING:
    bad.append('target gone: not the nearest')
if pick([(1360, KING), (3000, CROW)], CROW.doId)[1] is not KING:
    bad.append('target past STICK_R: not the nearest')
if bad:
    print('FAIL: ' + '; '.join(bad))
    sys.exit(1)
print('stick ok')
