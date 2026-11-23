"""Offline test of s_shipfight.py: the pure functions, then whole runs with a fake hunt() / sail_to / repair.
Run: python3.9 t_shipfight.py <dir holding s_shipfight.py>"""
import builtins, importlib, os, sys, types

D = os.path.abspath(sys.argv[1])
os.environ['PROOF_SCRIPT'] = os.path.join(D, 'x.py')
os.environ['SHIPFIGHT_PLUNDER_SECS'] = '0'    # job 23a's 20 s wait for the sink's gold is t_shipfight_plunder's
os.environ['SHIPFIGHT_BREAK'] = os.environ['SHIPFIGHT_FINISH_BREAK'] = '0.4'   # the break at 40% these runs were
                                              # written for; the weak-foe 25% finish is t_shipfight_finish's
PR ='1150922126.8dzlu'

# fake harness modules: only the names s_shipfight uses
lanes = types.ModuleType('s_lanes')
lanes.PR = PR
lanes.TORTUGA = '1156207188.95dzlu'
lanes.gold = lambda H: H.gold
lanes.stage = lambda H, step, what, **kw: H.ev('STAGE', step=step, what=what, **kw)
def onIsland(H, step, uid):
    yield 0
    return True
lanes.onIsland = onIsland
sq = types.ModuleType('s_shipquest')
sq.hpOf = lambda o: getattr(o, 'Hp', None)
sq.levelOf = lambda o: getattr(o, 'level', 0)
def npcShipsOrig(H, ship):
    return sorted([((o.pos - ship.pos), o) for o in H.world if o.Hp > 0], key=lambda t: t[0])
sq.npcShips = npcShipsOrig
sq.matches = lambda task, o: (True, 'ok')
sq.wantBearing = lambda d, brg: 'orig'
sail = types.ModuleType('sailing')
sail.islands = lambda: {PR: ('Port Royal', -87.0, -1848.0, None)}
sys.modules.update({'s_lanes': lanes, 's_shipquest': sq, 'sailing': sail})
sys.path.insert(0, D)
S = importlib.import_module('s_shipfight')
sent = []
builtins.messenger = types.SimpleNamespace(send=lambda k: sent.append(k))

# ------------------------------------------------------------------ 1. pure functions
C = [(900, 1, 24, 2100), (1500, 2, 9, 800), (2500, 3, 6, 600), (3000, 4, 32, 300)]
how, order, why = S.rank(C, 7, 2400)
assert how == 'fair' and order == [2, 3], (how, order)         # level <= 7 + 3, nearest first
assert why[1] == 'level 24 > cap 23' and why[4] == 'level 32 > cap 23', why   # MAIN18: the cap holds near port
assert S.rank(C, 7, 2400, stick=3)[1] == [3, 2]                # stays on the foe it picked
assert S.rank(C, 7, 2400, stick=1)[1] == [2, 3]                # ... only while that one is fair
hi = [(900, 1, 24, 2100), (3000, 4, 32, 300), (2000, 5, 30, 1300)]
how, order, _ = S.rank(hi, 7, 2400, cap=99)                # cap=99: the pick order alone
assert how == 'weak' and order == [4], (how, order)            # none fair: hp <= 0.5 x ours, lowest first
how, order, _ = S.rank([(900, 1, 24, 2100)], 7, 2400)
assert how is None and order == []                            # the failed run's Marauder: passed by
how, order, _ = S.rank([(900, 1, 24, 2100), (2000, 5, 30, 1300)], 7, 2400, anyOk=True, cap=99)
assert how == 'lowest-hp' and order == [5, 1]                 # after PICKY_SECS: the lowest hp in view
assert S.rank([], 7, 2400) == (None, [], {})
# MAIN15 far out (no leash): every Navy big ship ~2000 hp against our 7200, 'weak' took the lv 39 Dreadnought
navy = [(3000, 7, 39, 2100), (6000, 8, 26, 2000), (4000, 9, 36, 1800)]
how, order, why = S.rank(navy, 10, 6032, leash=0, cap=10 + S.FAR_GAP)
assert how == 'weak' and order == [8], (how, order)           # the Monarch, never the Dreadnought or Colossus
assert why[7] == 'level 39 > cap 26', why
# MAIN45: at lv 14 a lv 34 Warlord (2100 hp vs our 5365) was picked 'weak' and sank us; the lv 26 Monarch still goes
how, order, why = S.rank([(5984, 31, 34, 2100), (6000, 32, 26, 1800)], 14, 5365, leash=0)
assert order == [32] and why[31] == 'level 34 > cap 30', (how, order, why)
assert S.rank(navy[:1], 10, 6032, leash=0, cap=30, anyOk=True)[:2] == (None, [])   # not even as lowest-hp
assert S.rank(hi, 7, 2400) == S.rank(hi, 7, 2400, cap=None)  # cap=None = the default cap
# MAIN18 near Port Royal (leash on): 'weak' took a lv 34 EITC Warlord at lv 10 and it sank us; lv 17 is fine
eitc = [(3400, 21, 34, 2100), (4134, 22, 37, 1200), (5986, 23, 17, 1200)]
how, order, why = S.rank(eitc, 10, 5415)
assert order == [23] and 21 not in order and 22 not in order, (how, order, why)
assert S.rank(eitc[:2], 10, 7200, anyOk=True)[:2] == (None, [])   # not even as lowest-hp
# MAIN16 far out: a lv 9 Panther at lv 10 is no reason to hold on to 25% hull 26000 ft from port
assert S.weakFoe(9, 10) and not S.weakFoe(13, 10) and not S.weakFoe(None, 10)
assert not S.weakFoe(9, 10, far=True)
assert S.holdBeam(1400, 30) == 90 and S.holdBeam(1400, -30) == -90
assert S.holdBeam(1900, 40) == 65 and S.holdBeam(5000, 40) == 65     # angle in from far, at most 25 off the beam
assert S.holdBeam(900, -100) == -115                                 # open out when close
b = S.BREAK * 2400                                                   # SHIPFIGHT_BREAK, 0.5 since DOLL9
assert S.shouldBreak(b - 1, 2400) and not S.shouldBreak(b + 1, 2400) and not S.shouldBreak(0, 2400)
assert not S.shouldBreak(None, 2400) and not S.shouldBreak(500, None)
assert S.onBeam(80) and S.onBeam(-100) and not S.onBeam(64) and not S.onBeam(120)
print('pure ok')


# ------------------------------------------------------------------ 2. whole runs
class Foe:
    def __init__(self, doId, pos, level, hp):
        self.doId, self.pos, self.level, self.Hp, self.name, self.shipClass = doId, pos, level, hp, 'foe%d' % doId, 0
    def getPos(self, R):
        return (self.pos, 0.0, 0.0)


class Ship:
    def __init__(self):
        self.doId, self.pos, self.Hp, self.maxHp, self.maxSp, self.Sp, self.modelClass = 43, 0.0, 2400, 2400, 0, 0, 0


class Inv:
    def __init__(self, H): self.H = H
    def getShipDoIdList(self): return [43]
    def getGoldInPocket(self): return self.H.gold


class La:
    def __init__(self, H): self.H, self.gs = H, 'LandRoam'
    def getGameState(self): return self.gs
    def getLevel(self): return 7
    def getInventory(self): return Inv(self.H)


class Harness:
    def __init__(self, world, script, gold=5000):
        self.world, self.script, self.gold = world, script, gold
        self.events, self.render, self.sailResult = [], None, False
        self.ship = Ship()
        self.la = La(self)
        self.cr = types.SimpleNamespace(doId2do={}, getOwnerView=lambda sid: self.ship)
        self.hunts = 0
        self.mws = []
    def ev(self, kind, **kw): self.events.append((kind, kw))
    def area(self): return 'sea'
    def mw(self, w):
        self.mws.append(w); self.gold = int(w.split()[1])
    def kinds(self): return [k for k, _ in self.events]
    def get(self, kind): return [kw for k, kw in self.events if k == kind]


def fakeHunt(H, qid, task, secs):
    """A hunt() that behaves like the real one where s_shipfight cares: it asks npcShips / matches for its
    target, steers with wantBearing, logs the real event names, and lets the script hurt us or sink the foe."""
    H.hunts += 1
    H.la.gs = 'ShipPilot'
    H.cr.doId2do[43] = H.ship
    H.ev('SHIP-HUNT', ship=43, hp=H.ship.Hp)
    assert sq.wantBearing is S.holdBeam and sq.npcShips != npcShipsOrig
    tgt = None
    for step in H.script(H):
        if step == 'sunk':
            H.ship.Hp = 0; H.la.gs = 'Death'; del H.cr.doId2do[43]
            H.ev('OUR-SHIP-SUNK', hp=0)
            return 'our-ship-sunk'
        good = [(d, o) for d, o in sq.npcShips(H, H.ship) if sq.matches(task, o)[0]]
        if tgt is not None and H.cr.doId2do.get(tgt) is None and tgt in [o.doId for o in H.world if o.Hp <= 0]:
            H.ev('FOE-SUNK', foe=tgt)
            tgt = None
        if good:
            d, foe = good[0]
            if foe.doId != tgt:
                tgt = foe.doId
                H.cr.doId2do[tgt] = foe
                H.ev('SHIP-TARGET', foe=tgt, hp=foe.Hp)
            H.ev('BROADSIDE', foe=tgt, brg=step if isinstance(step, (int, float)) else 90, foeHp=foe.Hp, ourHp=H.ship.Hp)
        yield 0.5
    return 'timeout'


def fakeSailTo(H, uid, why='', via=None):
    H.ev('SAIL-START', to=uid, why=why, via=via)
    H.la.gs = 'LandRoam'
    H.cr.doId2do.pop(43, None)
    H.sailResult = True
    yield 1


def fakeRepair(H, here, sid):
    paid = H.gold >= 500
    if paid:
        H.gold -= 500; H.ship.Hp = H.ship.maxHp
    H.ev('repair', hp=H.ship.Hp, paid=paid)
    yield 1
    return H.ship.Hp, paid


sq.hunt = fakeHunt
sail.sail_to = fakeSailTo
sail.repair = fakeRepair
gs = types.ModuleType('pirates.ship.ShipGlobals')
gs.getRepairCost = lambda ov: ov.maxHp - ov.Hp
sys.modules['pirates'] = types.ModuleType('pirates'); sys.modules['pirates.ship'] = types.ModuleType('pirates.ship')
sys.modules['pirates.ship'].ShipGlobals = gs; sys.modules['pirates.ship.ShipGlobals'] = gs


def drive(H):
    g = S.run(H)
    n = 0
    for y in g:
        n += 1
        assert n < 500, 'runaway'
    return H


# a. the failed run's sea: a Marauder close by and a level-9 Panther farther: it fights the Panther and sinks it
def scriptA(H):
    pan = [o for o in H.world if o.doId == 2][0]
    for i in range(6):
        yield 88
        pan.Hp -= 200
    pan.Hp = 0
    del H.cr.doId2do[2]
    yield 90
mar, pan = Foe(1, 900.0, 24, 2100), Foe(2, 1500.0, 9, 1300)
H = drive(Harness([mar, pan], scriptA))
assert H.get('FOE-PICK')[0]['foe'] == 2 and H.get('FOE-PICK')[0]['how'] == 'fair', H.get('FOE-PICK')
assert all(kw['foe'] == 2 for kw in H.get('SHIP-TARGET')) and 'PASS' in H.kinds(), H.events[-3:]
lv = {kw['doId']: kw for kw in H.get('ship-lv')}
assert lv[1]['picked'] is False and lv[1]['why'] == 'level 24 > cap 23' and lv[2]['picked'] is True
assert lv[1]['fromHome'] is not None
end = H.get('SHIPFIGHT-END')[0]
assert end['sunk'] == 1 and end['onBeam'] == end['shots'] == 6 and end['breaks'] == 0 and end['levels'] == [9, 24], end
assert sq.npcShips is npcShipsOrig and sq.wantBearing(1, 1) == 'orig'      # wrappers put back
assert 'a-up' in sent and 'd-up' in sent
print('a ok: passes the Marauder by, sinks the Panther')


# b. hurt under 40%: breaks off, sails home, mends (paying), relaunches, then sinks the foe
def scriptB(H):
    foe = [o for o in H.world if o.doId == 7][0]
    if H.hunts == 1:
        for hp in (2000, 1400, 950, 900, 800):
            H.ship.Hp = hp
            yield 90
        raise AssertionError('should have broken off at 950')
    yield 90
    foe.Hp = 0
    del H.cr.doId2do[7]
    yield 90
H = drive(Harness([Foe(7, 1200.0, 8, 1000)], scriptB, gold=10000))
k = H.kinds()
assert k.index('BREAK-OFF') < k.index('SAIL-START') < k.index('repair') < k.index('REPAIR') and 'PASS' in k, k
assert H.get('BREAK-OFF')[0]['hp'] == 950 and H.hunts == 2 and H.get('REPAIR')[0]['ok'] is True and not H.mws
assert [kw['what'] for kw in H.get('STAGE')].count('broke-off') == 1 and H.get('SHIPFIGHT-END')[0]['breaks'] == 1
print('b ok: breaks off at 950 / 2400, repairs, sinks it on the second launch')


# c. too poor to repair: one logged 'gold' magic word, as payRepair does
H = drive(Harness([Foe(7, 1200.0, 8, 1000)], scriptB, gold=100))
assert len(H.mws) == 1 and H.get('MW-GOLD')[0]['cost'] == 2400 - 950 and 'PASS' in H.kinds(), H.mws
print('c ok: tops the gold up once (MW-GOLD) and repairs')


# d. it keeps getting hurt: breaks off REPAIRS + 1 times, then FAIL, never fighting on at low hp
def scriptD(H):
    H.ship.Hp = 2400
    yield 90
    H.ship.Hp = 700
    yield 90
    raise AssertionError('should have broken off')
H = drive(Harness([Foe(7, 1200.0, 8, 99999)], scriptD))
assert H.get('SHIPFIGHT-END')[0]['breaks'] == S.REPAIRS + 1 and H.hunts == S.REPAIRS + 1
assert H.get('FAIL')[0]['why'].startswith('broke off 3 times'), H.get('FAIL')
print('d ok: gives up after %d repairs' % S.REPAIRS)


# e. only high-level ships in view: no target, it patrols; FAIL says no fair ship and lists the levels
def scriptE(H):
    for i in range(5):
        yield 90
H = drive(Harness([Foe(1, 900.0, 24, 2100), Foe(5, 2000.0, 30, 1300)], scriptE))
assert not H.get('SHIP-TARGET') and not H.get('BROADSIDE'), H.events
f = H.get('FAIL')[0]
assert f['why'].startswith('no fair enemy ship') and f['levels'] == [24, 30], f
print('e ok: passes level 24 / 30 ships by')


# f. sunk anyway: FAIL our ship sank
def scriptF(H):
    yield 90
    yield 'sunk'
H = drive(Harness([Foe(7, 1200.0, 8, 1000)], scriptF))
assert H.get('FAIL')[0]['why'] == 'our ship sank before it sank one' and sq.npcShips is npcShipsOrig
print('t_shipfight ok')
