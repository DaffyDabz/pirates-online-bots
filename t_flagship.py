"""Offline test of s_flagship.py: the pure functions, then whole runs against a fake game world.
Run: python3.9 t_flagship.py <dir holding s_flagship.py>"""
import builtins, importlib, math, os, sys, types

D = os.path.abspath(sys.argv[1])
sys.path.insert(0, D)
os.environ.pop('PROOF_SCRIPT', None)
F = importlib.import_module('s_flagship')

# ------------------------------------------------------------------ 1. pure functions
# aim: the pitch it picks lands the shot on the target (closed form and a 1 ms step integration)
for start, tgt in [((0, 0, 20), (0, 400, 15)), ((10, -5, 22), (350, 300, 30)), ((0, 0, 25), (-600, 50, 5)),
                   ((0, 0, 20), (0, 900, 10)), ((0, 0, 20), (120, 0, 40))]:
    h, p = F.aim(start, tgt)
    assert p is not None, (start, tgt)
    t, err = F.flight(start, tgt, p)
    assert abs(err) < 0.01, (start, tgt, p, err)
    # integrate along the heading: Panda H, 0 = +Y, 90 = -X
    vx = F.SHOT_V * math.cos(math.radians(p)); vz = F.SHOT_V * math.sin(math.radians(p))
    x, y, z = start; dt = 0.001; tt = 0
    dirx, diry = -math.sin(math.radians(h)), math.cos(math.radians(h))
    d = math.hypot(tgt[0] - start[0], tgt[1] - start[1])
    while math.hypot(x - start[0], y - start[1]) < d:
        x += vx * dirx * dt; y += vx * diry * dt; z += vz * dt; vz -= F.GRAV * dt; tt += dt
    assert math.hypot(x - tgt[0], y - tgt[1]) < 1.0 and abs(z - tgt[2]) < 1.5, ((x, y, z), tgt)
assert F.aim((0, 0, 0), (0, 5000, 0))[1] is None            # out of range
assert F.aim((0, 0, 0), (0, 0, 0))[1] is None
h, p = F.aim((0, 0, 0), (-100, 0, 0)); assert abs(h - 90) < 1e-6
h, p = F.aim((0, 0, 0), (100, 0, 0)); assert abs(h + 90) < 1e-6
assert F.wrap180(190) == -170 and F.wrap180(-190) == 170 and F.wrap180(45) == 45
# pickCannon: right side only when the flagship is to starboard, nearest abeam first, far off-beam last
rows = [(1, -8, 10), (2, 8, 10), (3, 8, -10), (4, 8, 30), (5, 0, 0)]
pk = F.pickCannon(rows, 300, -5)
assert [d for _, d in pk] == [3, 2, 4], pk
assert [d for _, d in F.pickCannon(rows, -300, 0)] == [1]
pk = F.pickCannon([(7, 8, 0), (8, 8, 200)], 100, 300)       # 7 is 71 deg off beam, 8 is 63: both > 55, nearer first
assert [d for _, d in pk] == [8, 7], pk
assert F.pickCannon([(9, 8, 0)], 100, 0) == [(0.0, 9)]
assert F.onBeam(90) and F.onBeam(-60) and not F.onBeam(20) and not F.onBeam(-160)
# deckRows: live, near the flagship centre, nearest to us first
rows = [(1, 50, 30, 5, (100, 100)), (2, 20, 0, 5, (100, 110)), (3, 30, 30, 5, (105, 95)), (4, 10, 30, 5, (900, 900))]
assert [r[0] for r in F.deckRows(rows, (100, 100))] == [3, 1]
# verdict
full = {k: True for k in F.STAGES}
assert F.verdict(full)[0] == 'PASS'
for k in F.STAGES:
    s = dict(full); s[k] = False
    assert F.verdict(s) == ('FAIL', k), k
F.NEED_CHEST = True
assert F.verdict(full) == ('FAIL', 'chest') and F.verdict(dict(full, chest=True))[0] == 'PASS'
F.NEED_CHEST = False
assert set(F.WHY) >= set(F.STAGES) | {'chest'}
print('pure ok')


# ------------------------------------------------------------------ 2. a fake world, whole runs
class V(tuple):
    def __new__(cls, x, y=0, z=0):
        return tuple.__new__(cls, (float(x), float(y), float(z)))
    def __sub__(self, o): return V(self[0] - o[0], self[1] - o[1], self[2] - o[2])
    def __add__(self, o): return V(self[0] + o[0], self[1] + o[1], self[2] + o[2])
    def length(self): return math.sqrt(sum(c * c for c in self))

RENDER = object()

class Clock:
    t = 1000.0
    @staticmethod
    def time(): return Clock.t

class Msg:
    def __init__(self): self.sent = []
    def send(self, k): self.sent.append(k)

class NP:
    """A node with a render position and a local H/P under a parent at heading 0 (our ship faces +Y)."""
    def __init__(self, pos=(0, 0, 0), tag='', base=0.0, foe=None):
        self._pos, self.h, self.p, self.tag, self.base, self.foe = V(*pos), 0.0, 0.0, tag, base, foe
    @property
    def pos(self): return self._pos + self.foe.pos if self.foe is not None else self._pos
    def getPos(self, other=None): return self.pos
    def isEmpty(self): return False
    def setH(self, a, b=None): self.h = (b - self.base) if b is not None else a
    def getH(self, other=None): return self.h + (self.base if other is not None else 0)
    def setP(self, a, b=None): self.p = b if b is not None else a
    def getP(self, other=None): return self.p
    def setR(self, *a): pass
    def getNetTag(self, k): return self.tag if k == 'targetId' else ''
    def getTag(self, k): return ''


class World:
    def __init__(self, sc):
        self.sc = sc                     # the scenario: a dict of switches
        self.ev = []
        self.gold = 1000
        self.cargo = []
        la = types.SimpleNamespace(doId=100000001, hp=500, cannon=None, gs='LandRoam', parent=None, pos=V(0, 0, 10))
        la.getGameState = lambda: la.gs
        la.getParentObj = lambda: la.parent
        la.getPos = lambda other=None: la.pos
        la.getInventory = lambda: types.SimpleNamespace(getShipDoIdList=lambda: [100000043])
        la.skillDiary = types.SimpleNamespace(getTimeRemaining=lambda s: 0)
        self.loots = []
        ms = types.SimpleNamespace()
        ms.showLoot = lambda *a, **k: self.loots.append((a, k))
        self.ms = ms
        la.guiMgr = types.SimpleNamespace(messageStack=ms)
        self.la = la
        ship = types.SimpleNamespace(doId=100000043, pos=V(0, 0, 0), boardingPanel=None, boardableShipId=None,
                                     cargo=self.cargo, avCannonRotate=NP())
        ship.getPos = lambda other=None: ship.pos
        ship.getRelativePoint = lambda other, p: V(*p) - ship.pos
        self.boardAsk = []
        ship._DistributedShip__handleBoardingChoice = lambda yes: self.boardAsk.append(('panel', yes))
        ship.d_requestBoardFlagship = lambda fid: self.boardAsk.append(('direct', fid))
        self.ship = ship
        foe = types.SimpleNamespace(doId=777, pos=V(0, 1500, 0), gs='Patrol', hp=100, shipClass=61, name='HMS Test',
                                    isFlagship=1)
        foe.getPos = lambda other=None: foe.pos
        foe.queryGameState = lambda: foe.gs
        foe.getHp = lambda: foe.hp
        self.targets = []
        foe.gameFSM = types.SimpleNamespace(targets=self.targets)
        self.foe = foe
        self.cr = types.SimpleNamespace(doId2do={100000043: ship, 777: foe})
        if sc.get('noFlagship'):
            del self.cr.doId2do[777]
        wheel = types.SimpleNamespace(doId=900, shipId=100000043)
        wheel.requestExit = lambda: setattr(la, 'gs', 'LandRoam')
        type(wheel).__name__  # SimpleNamespace; the step finds it by class name, so use real classes below
        self.cannons = []
        self.fired = []
        self.hitcalls = []
        self.deck = {}
        self.t = 0
        self.towAt = None

    # ---- the per-yield world tick
    def tick(self, dt):
        Clock.t += dt
        foe, la, sc = self.foe, self.la, self.sc
        if foe.gs == 'GrappleLerping' and Clock.t - self.towAt > 5:
            foe.gs = 'InPosition'
            foe.pos = self.ship.pos + V(80, 0, 0)
            if not sc.get('noPanel'):
                self.ship.boardingPanel = object()
        if self.boardAsk and foe.gs == 'InPosition' and la.parent is not foe:
            foe.gs = 'Boarded'
            la.parent = foe
            la.pos = foe.pos + V(0, 0, 15)
            la.gs = 'LandRoam'
            for i in range(sc.get('crew', 2)):
                self.deck[5000 + i] = [30.0, foe.pos + V(10 * i, 5, 15)]
        if foe.gs == 'Boarded' and self.deck and all(v[0] <= 0 for v in self.deck.values()):
            foe.gs = 'Defeated'
            self.defAt = Clock.t
            if not sc.get('noChest'):
                self.cargo.append(3)
        if foe.gs == 'Defeated' and Clock.t - self.defAt > 10 and la.parent is foe:
            la.parent = self.ship
            la.pos = self.ship.pos + V(0, 0, 10)
            if not sc.get('noPay'):
                self.gold += 250
                self.ms.showLoot([], gold=250)

    def grappleHit(self):
        if self.foe.gs == 'WaitingForGrapple':
            self.foe.gs = 'GrappleLerping'
            self.towAt = Clock.t


class Cannon:
    pass
Cannon.__name__ = 'DistributedShipCannon'
class Wheel:
    pass
Wheel.__name__ = 'DistributedSteeringWheel'


def build(sc):
    W = World(sc)
    la, ship, foe = W.la, W.ship, W.foe
    w = Wheel(); w.doId = 900; w.shipId = ship.doId
    w.requestExit = lambda: setattr(la, 'gs', 'LandRoam')
    W.cr.doId2do[900] = w
    for i, (x, y) in enumerate([(-8, 10), (8, 10), (8, -10)]):
        c = Cannon(); c.doId = 800 + i; c.shipId = ship.doId; c.ship = ship
        c.skillId = 12900; c.volley = 10; c.ammo = 12901
        c.prop = types.SimpleNamespace(cannonPost=NP((x, y, 8), foe=ship), hNode=NP(base=-90.0 if x > 0 else 90.0), pivot=NP(), cannonExitPoint=NP((x + (2 if x > 0 else -2), y, 12), foe=ship),
                                       currentHpr=(0, 0, 0), shipH=0)
        c.getPos = lambda other=None, c=c: c.prop.cannonPost.pos
        def ri(avId, c=c):
            la.cannon = c; la.gs = 'Cannon'
        c.requestInteraction = ri
        c.requestExit = lambda c=c: (setattr(la, 'cannon', None), setattr(la, 'gs', 'LandRoam'))
        c.getAmmoSkillId = lambda c=c: c.ammo
        c.selectAmmo = lambda a, c=c: setattr(c, 'ammo', a)
        c.setAmmoSkillId = lambda a, c=c: setattr(c, 'ammo', a)
        def send(skillId, ammo, posHpr, charge, ts, c=c):
            W.fired.append((c.doId, ammo, posHpr))
        c.sendRequestProjectileSkill = send       # class-level stand-in: put on the class below
        del c.sendRequestProjectileSkill
        def fire(c=c):
            if c.volley > 0:
                ph = c.prop
                c.sendRequestProjectileSkill(c.skillId, c.getAmmoSkillId(),
                                             list(ph.cannonExitPoint.getPos(RENDER)) + [ph.hNode.getH(RENDER), ph.pivot.getP(RENDER), 0],
                                             0.0, 0)
                c.volley -= 1
                # the aimed shot lands when it is aimed at a target and the scenario lets aimed shots land
                if not W.sc.get('aimMisses') and c.getAmmoSkillId() == 12908 and W.targets:
                    start = ph.cannonExitPoint.getPos(RENDER)
                    for t in W.targets:
                        h, p = F.aim(start, t[2].pos)
                        if abs(F.wrap180(ph.hNode.getH(RENDER) - h)) < 1 and abs(ph.pivot.getP() - p) < 1:
                            W.grappleHit()
        c.fireCannon = fire
        def hitcall(skillId, ammo, result, targetId, areas, pos, normal, codes, ts):
            W.hitcalls.append((skillId, ammo, result, targetId, codes))
            if targetId == foe.doId and ammo == 12908:
                W.grappleHit()
        c.sendSuggestProjectileSkillResult = hitcall
        W.cr.doId2do[c.doId] = c
        W.cannons.append(c)
    return W


class CannonSendMixin:
    pass


def fakeModules(W):
    sc = W.sc
    la, ship, foe = W.la, W.ship, W.foe

    def stage(H, step, what, **kw):
        H.ev('STAGE', step=step, what=what, **kw)
    def onIsland(H, step, uid):
        yield 1
        return True
    s_lanes = types.SimpleNamespace(stage=stage, onIsland=onIsland, gold=lambda H: W.gold, PR='pr')

    def bearing(H, ship_, target):
        rel = ship_.getRelativePoint(RENDER, target)
        return math.degrees(math.atan2(rel[0], rel[1]))
    def turnKeys(keys, brg, want, dead=8.0):
        keys.set('a', brg < want - dead); keys.set('d', brg > want + dead)
        # the fake ship turns: put the foe on the beam after a few beats
        W.turns = getattr(W, 'turns', 0) + 1
        if W.turns > 3:
            d = (foe.pos - ship.pos).length()
            foe.pos = ship.pos + V(d, 0, 0)
    def hunt(H, qid, task, secs):
        assert isinstance(task, F.FlagshipOnly) and task.isFlagship
        la.gs = 'ShipPilot'; la.parent = ship
        H.ev('SHIP-HUNT', q=qid)
        yield 1
        if sc.get('noFlagship'):
            for _ in range(3):
                yield 1
            return 'timeout'
        H.ev('SHIP-TARGET', foe=foe.doId, dist=1500)
        yield 0.5
        H.ev('BROADSIDE', foe=foe.doId, side='right')
        yield 0.5
        foe.hp = 0
        if sc.get('sinks'):
            del W.cr.doId2do[777]
        else:
            foe.gs = 'WaitingForGrapple'
            ship.boardableShipId = foe.doId
            for i in range(2):
                W.targets.append([None, None, NP(V(-12, 10 * i, 14), tag='grapple_left_%d' % i, foe=foe)])
        H.ev('FOE-SUNK', foe=foe.doId)
        yield 0.5
        yield 0.5
        return 'timeout'
    s_shipquest = types.SimpleNamespace(hunt=hunt, bearing=bearing, turnKeys=turnKeys)

    class Keys:
        def __init__(self, H): self.down = set()
        def set(self, k, on):
            (self.down.add if on else self.down.discard)(k)
        def steer(self, ship_, target, dead=6.0):
            # the fake ship sails 60 ft a beat straight at it
            dv = V(*target) - ship_.pos
            n = dv.length()
            if n > 1:
                ship_.pos = ship_.pos + V(dv[0] / n * 60, dv[1] / n * 60, 0)
            return 0.0
        def release(self): self.down.clear()
    def near(H, obj, d=4):
        yield 1
        return True
    s_dock = types.SimpleNamespace(Keys=Keys, near=near)

    def foeRows(H):
        out = []
        for i, (hp, p) in W.deck.items():
            out.append((i, (p - la.pos).length(), hp, 5, (p[0], p[1])))
        return out
    class Fighter:
        def __init__(self, H, o, safe):
            self.foe, self.hits, self.skills, self.n = o, 0, 0, 0
            assert len(safe) == 3
        def step(self):
            if sc.get('ko'):
                la.hp = 0
                return 'fight'
            self.n += 1
            self.hits += 1
            W.deck[self.foe.doId][0] -= 10
            return 'kill' if W.deck[self.foe.doId][0] <= 0 else 'fight'
        def close(self): W.closed = getattr(W, 'closed', 0) + 1
    s_fighter = types.SimpleNamespace(foeRows=foeRows, Fighter=Fighter)
    sailing = types.SimpleNamespace(onShip=lambda H: la.parent is ship)
    for n, m in (('s_lanes', s_lanes), ('s_shipquest', s_shipquest), ('s_dock', s_dock), ('s_fighter', s_fighter),
                 ('sailing', sailing)):
        sys.modules[n] = m
    # the hit report's imports
    sys.modules['direct'] = types.ModuleType('direct')
    sys.modules['direct.distributed'] = types.ModuleType('direct.distributed')
    cd = types.ModuleType('direct.distributed.ClockDelta')
    cd.globalClockDelta = types.SimpleNamespace(getFrameNetworkTime=lambda bits=32: 42)
    sys.modules['direct.distributed.ClockDelta'] = cd
    sys.modules['pirates'] = types.ModuleType('pirates')
    sys.modules['pirates.battle'] = types.ModuleType('pirates.battle')
    wg = types.ModuleType('pirates.battle.WeaponGlobals'); wg.RESULT_HIT = 1
    sys.modules['pirates.battle.WeaponGlobals'] = wg
    sys.modules['pirates.battle'].WeaponGlobals = wg


def runOnce(sc, **env):
    W = build(sc)
    # deck enemies appear as client objects for H.cr.doId2do.get
    class Deck(dict):
        pass
    fakeModules(W)
    for k, v in env.items():
        setattr(F, k, v)
    F.time = Clock
    builtins.render = RENDER
    builtins.messenger = Msg()
    # the cannons' send must be a class attribute so the step's wrapper goes in the instance __dict__
    def csend(self, skillId, ammo, posHpr, charge, ts):
        W.fired.append((self.doId, ammo, list(posHpr)))
    Cannon.sendRequestProjectileSkill = csend
    H = types.SimpleNamespace(la=W.la, cr=W.cr, render=RENDER)
    def ev(kind, **kw):
        W.ev.append((kind, kw))
    H.ev = ev
    H.area = lambda: ('fake', None, None)
    def walk_to(target, arrive=2.0, timeout=None, face=False, tag=''):
        p = target() if callable(target) else target.getPos(RENDER)
        W.la.pos = V(*p)
        yield 1
        return True
    H.walk_to = walk_to
    H.walk_cancel = lambda: None
    # deck enemies as objects
    orig_get = W.cr.doId2do
    class D2D(dict):
        def get(self, k, d=None):
            if k in W.deck:
                return types.SimpleNamespace(doId=k, name='deck %d' % k)
            return dict.get(self, k, d)
    W.cr.doId2do = D2D(orig_get)
    g = F.run(H)
    n = 0
    try:
        y = next(g)
        while True:
            n += 1
            assert n < 20000, 'runaway'
            if isinstance(y, tuple):
                fn, secs = y[1], y[2]
                t0 = Clock.t
                while not fn() and Clock.t - t0 < secs:
                    W.tick(0.5)
            else:
                W.tick(float(y))
            y = g.send(None)
    except StopIteration:
        pass
    for k, v in env.items():
        pass
    kinds = [k for k, _ in W.ev]
    last = [kw for k, kw in W.ev if k in ('PASS', 'FAIL')]
    assert len(last) == 1, kinds
    res = [k for k, _ in W.ev if k in ('PASS', 'FAIL')][0]
    end = [kw for k, kw in W.ev if k == 'FLAGSHIP-END'][0]
    # every run cleans up: keys up, hooks off, out of the cannon
    assert 'showLoot' not in W.ms.__dict__ or W.ms.showLoot.__name__ == '<lambda>', W.ms.__dict__
    for c in W.cannons:
        assert 'sendRequestProjectileSkill' not in c.__dict__, c.doId
    assert W.la.cannon is None
    assert H.ev is ev
    return W, res, last[0], end, kinds


def stages(W):
    return [kw['what'] for k, kw in W.ev if k == 'STAGE']


def restoreEnv():
    F.NEED_CHEST, F.HITCALL = False, True


# A. the whole thing, aimed grapple, the Board? panel
W, res, kw, end, kinds = runOnce({})
assert res == 'PASS', (kw, stages(W))
assert stages(W) == ['at-island', 'launched', 'foe-seen', 'first-shot', 'crippled', 'alongside', 'at-cannon',
                     'grapple-fired', 'grappled', 'in-position', 'boarding', 'on-deck', 'deck-foe', 'deck-kill',
                     'deck-kill', 'defeated', 'swung-back', 'loot'], stages(W)
assert W.fired and W.fired[0][1] == 12908 and W.fired[0][0] == 801, W.fired     # starboard cannon: the flagship is put on the +x beam
assert not W.hitcalls and W.boardAsk == [('panel', True)] and end['board'] == 'panel-yes', (W.hitcalls, W.boardAsk, end, [kw for k, kw in W.ev if k == 'GRAPPLE-SHOT'])
assert end['kills'] == 2 and end['deckSeen'] == 2 and end['gold'] == (1000, 1250) and end['chests'] == (0, 1)
assert 'GRAPPLE-SHOT' in kinds and 'SAIL-DOWN' in kinds and 'LOOT-POPUP' in kinds and 'DECK-KILL' in kinds
assert 'hit report' not in kw['what']
print('A ok: PASS by aimed grapple + panel,', len(W.fired), 'shot(s), cannon', W.fired[0][0])

# B. aimed shots miss -> one hit report; no panel -> direct board request
W, res, kw, end, kinds = runOnce({'aimMisses': True, 'noPanel': True})
assert res == 'PASS' and 'hit report' in kw['what'], kw
assert len(W.fired) == F.SHOTS and len(W.hitcalls) == 1 and W.hitcalls[0][1] == 12908 and W.hitcalls[0][3] == 777
assert W.boardAsk == [('direct', 777)] and end['hitcall'] == 1
print('B ok: PASS by hit report after', len(W.fired), 'misses, direct board')

# C. no hit report allowed -> FAIL grappled
F.HITCALL = False
W, res, kw, end, kinds = runOnce({'aimMisses': True})
assert res == 'FAIL' and kw['stage'] == 'grappled' and 'no grapple landed' in kw['why'], kw
restoreEnv()
print('C ok:', kw['why'])

# D. the flagship sinks instead of being crippled
W, res, kw, end, kinds = runOnce({'sinks': True})
assert res == 'FAIL' and kw['stage'] == 'crippled' and '0135' in kw['why'], kw
print('D ok:', kw['why'])

# E. no flagship in sight
W, res, kw, end, kinds = runOnce({'noFlagship': True})
assert res == 'FAIL' and 'no flagship came in sight' in kw['why'], kw
assert 'a-up' in builtins.messenger.sent and 'd-up' in builtins.messenger.sent
print('E ok:', kw['why'])

# F. knocked out on the deck
W, res, kw, end, kinds = runOnce({'ko': True})
assert res == 'FAIL' and 'knocked out' in kw['why'] and kw['stage'] == 'defeated', kw
print('F ok:', kw['why'])

# G. no pay; H. chest needed but none
W, res, kw, end, kinds = runOnce({'noPay': True})
assert res == 'FAIL' and kw['stage'] == 'paid', kw
F.NEED_CHEST = True
W, res, kw, end, kinds = runOnce({'noChest': True})
assert res == 'FAIL' and kw['stage'] == 'chest', kw
W, res, kw, end, kinds = runOnce({})
assert res == 'PASS', kw
restoreEnv()
print('G/H ok: no pay -> FAIL paid; NEED_CHEST with no chest -> FAIL chest, with one -> PASS')
print('t_flagship ok')
