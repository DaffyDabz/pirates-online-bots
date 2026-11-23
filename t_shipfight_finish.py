"""Offline test of s_shipfight.breakWhy's finish rule (DOLL8, 11-21): against a lv2 Navy Ferret at 446/1000 hp the
bot broke off at 1178/2400 hull, two broadsides from the sink. Now it holds on to FINISH_BREAK (25%) of our hull when
the foe is weak or under FINISH of its max, and still breaks off under that, or for a strong foe at 49%.
Run: python3.9 t_shipfight_finish.py <dir holding s_shipfight.py>"""
import importlib, os, sys, types

D = os.path.abspath(sys.argv[1])
os.environ['PROOF_SCRIPT'] = os.path.join(D, 'x.py')
lanes = types.ModuleType('s_lanes')
lanes.PR = lanes.TORTUGA = 'x'
sq = types.ModuleType('s_shipquest')
sq.hpOf = lambda o: getattr(o, 'Hp', None)
sq.levelOf = lambda o: getattr(o, 'level', 0)
sail = types.ModuleType('sailing')
sys.modules.update({'s_lanes': lanes, 's_shipquest': sq, 'sailing': sail})
sys.path.insert(0, D)
S = importlib.import_module('s_shipfight')

MX, NOW = 2400, 1000.0
# DOLL8's own numbers: our hull 1178/2400 (49%), losing ~10 hp/s, the Ferret at 446/1000
hist = [(NOW - 10, 1278), (NOW - 5, 1228)]
bw = S.breakWhy(1178, MX, hist, NOW, foe=0.446, weak=True)
assert bw is None, 'DOLL8: kept firing at a lv2 Ferret two hits from sinking: ' + str(bw)
bw = S.breakWhy(1178, MX, hist, NOW, foe=0.446)
assert bw is None, 'half-dead foe, any level: keep firing: ' + str(bw)
bw = S.breakWhy(1178, MX, hist, NOW, foe=0.9, weak=True)
assert bw is None, 'weak foe at full hp: keep firing to 25%: ' + str(bw)
# ... and it still breaks off
assert S.breakWhy(590, MX, hist, NOW, foe=0.2, weak=True) == 'hp 590 < 25% of 2400'
assert S.breakWhy(1178, MX, hist, NOW, foe=0.6) == 'hp 1178 < 50% of 2400'          # strong foe, not half dead
assert S.breakWhy(1178, MX, hist, NOW, foe=0.6, brk=0.5) == 'hp 1178 < 50% of 2400'  # an explicit brk wins
heavy = [(NOW - 8, 1800)]
assert S.breakWhy(1300, MX, heavy, NOW, foe=0.6) == 'lost 500 hp in 10 s'           # strong foe, heavy fire
assert S.breakWhy(1300, MX, heavy, NOW, foe=0.6, weak=True) is None                  # a weak foe cannot do that
dz = [(500, 9, 30)]
assert S.breakWhy(1500, MX, [], NOW, dz, foe=0.6, weak=True).startswith('level 30 ship')  # a big ship near: go
assert S.breakWhy(None, MX, [], NOW, foe=0.4, weak=True) is None
print('finish ok')
