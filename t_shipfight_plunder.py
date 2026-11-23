"""Offline test of s_shipfight's plunder wait (DOLL9, 11-21): the straw Ferret sank with us at 1010/2400 and a second
Ferret shot us down to 82 while the bot sat out the 20 s wait for the gold. The wait now ends (PLUNDER-CUT) under
FINISH_BREAK of our hull or after losing PLUNDER_DROP of it, so the next fight's break-off sends us to repair.
Run: python3.9 t_shipfight_plunder.py <dir holding s_shipfight.py>"""
import importlib, os, sys, types

D = os.path.abspath(sys.argv[1])
os.environ['PROOF_SCRIPT'] = os.path.join(D, 'x.py')
lanes = types.ModuleType('s_lanes')
lanes.PR = lanes.TORTUGA = 'x'
lanes.gold = lambda H: 50
sq = types.ModuleType('s_shipquest')
sail = types.ModuleType('sailing')
sys.modules.update({'s_lanes': lanes, 's_shipquest': sq, 'sailing': sail})
sys.path.insert(0, D)
S = importlib.import_module('s_shipfight')
MX = 2400
assert S.plunderCut(1010, 1000, MX) is None                      # a quiet wait goes on
assert S.plunderCut(1010, 590, MX) == 'hp 590 < 25% of 2400'
assert S.plunderCut(2000, 1700, MX) == 'lost 300 hp while waiting'
assert S.plunderCut(None, None, MX) is None


class H:
    evs = []

    def ev(self, kind, **kw):
        self.evs.append((kind, kw))


# DOLL9's wait: 1010 at the sink, ~45 hp a second from the second Ferret; with a fake clock 1 s a step
clock = [0.0]
S.time = types.SimpleNamespace(time=lambda: clock[0])
hull = iter([1010] + [1010 - 45 * i for i in range(1, 30)])
h = H()
g = S.plunderWait(h, 20, hull=lambda: (next(hull), MX))
try:
    while True:
        next(g)
        clock[0] += 1
except StopIteration as e:
    out = e.value
cut = [kw for k, kw in h.evs if k == 'PLUNDER-CUT']
assert cut and cut[0]['hp'] >= 600, 'DOLL9: sat out the wait down to %s hp' % (cut[0]['hp'] if cut else '82')
assert out == (50, [])
print('plunder ok', cut[0]['why'], cut[0]['waited'])
