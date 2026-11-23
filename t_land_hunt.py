"""Offline test of pbot\\skills\\land.py step 2 (11-22): the free-play HUNT (rows 40, 43). A healthy pirate on land with
nothing else to do hunts: it fights what is in view (s_fighter.Fighter), else walks to a spawn camp of its level and looks
again, keeps clear of the boys, never takes a foe above its level while Vitae runs, drinks a tonic between fights, and in a
cave goes to the foe along the cave's trail (s_cavewalk.walk) instead of the straight walk that sticks on the wall.
Fake world: no game. A cave (area 'cave1') with a wall along y = 20 from x = -40 to x = 25; the foe stands north of it. The
straight walk (H.walk_to, and the straight walk inside Fighter.step) sticks on the wall; the stand-in cave walker goes round
by (35, 15) and (35, 28). The real s_fighter pure helpers (pickFoe, spawnPick, tier, danger, retreatPoint) run; Fighter
itself, foeRows and s_story / s_cavewalk are stand-ins with the same contracts.
BEFORE: land.legFor forced to 'engage' (every leg the straight walk, what Fighter does alone, the MAIN48 / cave bug): the
foe behind the wall is never reached, 0 kills. AFTER: the cave leg goes through the cave walker: 1 kill; no waypoints for the
area -> the straight walk (and no later try of the cave walker there); 'no open way' twice -> ONE BOT 'stuck' bug.
Run: python3 t_land_hunt.py <harness dir, e.g. C:\\Dev\\Toontown\\pirates-harness>"""
import math, os, sys, types

D = os.path.abspath(sys.argv[1])
sys.path.insert(0, D)
sys.path.insert(0, os.path.join(D, 'pbot', 'skills'))


class Clock:
    t = 1000.0

    def time(self):
        return self.t


CLK = Clock()

# ---- a fake game module for the imports Fighter / land make
ug = types.ModuleType('pirates.uberdog.UberDogGlobals')


class InventoryType:
    UseItem = 7
    Vitae_Level = 99


ug.InventoryType = InventoryType
for n in ('pirates', 'pirates.uberdog'):
    sys.modules[n] = types.ModuleType(n)
sys.modules['pirates.uberdog.UberDogGlobals'] = ug

WALL_Y, WALL_X = 20.0, (-40.0, 25.0)
PLAYER1 = 100000656


class Foe:
    def __init__(self, w, doId, x, y, lvl=1, hp=100):
        self.w, self.doId, self.pos, self.level, self.hp = w, doId, [x, y, 0.0], lvl, hp

    def getPos(self, R=None):
        return tuple(self.pos)


class Inv:
    def __init__(self, w):
        self.w = w

    def getTonics(self):
        return {1: self.w.tonics}

    def getStackQuantity(self, k):
        return self.w.vitae if k == InventoryType.Vitae_Level else 0

    def getGoldInPocket(self):
        return self.w.gold


class Diary:
    def getTimeRemaining(self, sid):
        return 0


class Avatar:
    pass


class World:
    def __init__(self, wall=True, hp=1000, tonics=3, heal=100, nodes=(), area=('DistributedGAInterior', 'cave1'),
                 nodata=False, noway=False, vitae=0, level=1):
        self.wall, self.tonics, self.heal, self.vitae, self.nodata, self.noway = wall, tonics, heal, vitae, nodata, noway
        self.gold, self.gs, self.areaT, self.nodes = 0, 'LandRoam', area, list(nodes)
        self.events, self.bugs, self.foes = [], [], {}
        self.cave_calls, self.stuck_walks, self.closed, self.cancels, self.koAfter = 0, 0, 0, 0, None
        self.fightSteps = 0
        la = self.la = Avatar()
        la.hp, la.maxHp, la.doId, la.name, la.pos = hp, 1000, 100000999, 'Test Pirate', [0.0, 0.0, 0.0]
        la.jailCellIndex = 100
        la.getGameState = lambda: self.gs
        la.getInventory = lambda: Inv(self)
        la.getLevel = lambda: level
        la.skillDiary = Diary()
        la.getPos = lambda R=None: tuple(la.pos)
        self.H = types.SimpleNamespace(la=la, cr=types.SimpleNamespace(doId2do=self.foes), render='R',
                                       ev=lambda name, **kw: self.events.append((name, kw)), area=lambda: self.areaT,
                                       P=lambda a: [round(v, 1) for v in a.pos], walk_to=self.walk_to,
                                       walk_poll=self.walk_poll, walk_cancel=self.walk_cancel)

    def names(self):
        return [e[0] for e in self.events]

    def count(self, name):
        return self.names().count(name)

    def add(self, doId, x, y, lvl=1, hp=100):
        self.foes[doId] = Foe(self, doId, x, y, lvl, hp)
        return self.foes[doId]

    # -- the straight walk: sticks on the wall
    def step_toward(self, tgt, dist):
        x, y, z = self.la.pos
        dx, dy = tgt[0] - x, tgt[1] - y
        n = math.hypot(dx, dy)
        if n < 1e-6:
            return 'there'
        k = min(1.0, dist / n)
        nx, ny = x + dx * k, y + dy * k
        if self.wall and (y < WALL_Y <= ny):
            cx = x + (nx - x) * ((WALL_Y - y) / (ny - y))
            if WALL_X[0] <= cx <= WALL_X[1]:
                self.la.pos[1] = WALL_Y - 1.0
                return 'stuck'
        self.la.pos[0], self.la.pos[1] = nx, ny
        return 'moved'

    def walk_to(self, pos, ref=None, arrive=1.0, timeout=20.0, face=True, tag=''):
        stuck, t = 0, 0.0
        while t < timeout:
            if math.hypot(pos[0] - self.la.pos[0], pos[1] - self.la.pos[1]) <= arrive:
                return True
            r = self.step_toward(pos, 8.0)
            stuck = stuck + 1 if r == 'stuck' else 0
            if stuck >= 3:
                self.stuck_walks += 1
                return False
            t += 1.0
            yield 1.0
        return False

    def walk_poll(self, target, ref=None, arrive=3.5, face=True, tag=''):
        pos = target.getPos() if hasattr(target, 'getPos') else target
        if math.hypot(pos[0] - self.la.pos[0], pos[1] - self.la.pos[1]) <= arrive:
            return True
        return None if self.step_toward(pos, 2.0) == 'stuck' else False

    def walk_cancel(self):
        self.cancels += 1


class FakeFighter:
    """Fighter's contract: step() every beat -> 'walk' / 'fight' / 'kill' / 'lost' / 'stuck'; the straight walk to the foe."""
    w = None

    def __init__(self, H, foe, safe):
        self.foe, self.hits, self.skills, self.refused, self.H = foe, 0, 0, 0, H

    def step(self):
        w, foe = FakeFighter.w, self.foe
        if foe is None:
            return 'lost'
        if foe.hp <= 0 or foe.doId not in w.foes:
            w.foes.pop(foe.doId, None)
            return 'kill' if self.hits else 'lost'
        d = math.hypot(foe.pos[0] - w.la.pos[0], foe.pos[1] - w.la.pos[1])
        if d > 3.5:
            r = w.walk_poll(foe, arrive=3.5, face=True, tag='engage')
            return 'stuck' if r is None else 'walk'
        foe.hp -= 50
        self.hits += 1
        w.fightSteps += 1
        if w.koAfter is not None and w.fightSteps >= w.koAfter:
            w.la.hp, w.gs = 0, 'Dying'
        if foe.hp <= 0:
            w.foes.pop(foe.doId, None)
            w.gold += 12
            return 'kill'
        return 'fight'

    def tonic(self):
        w = FakeFighter.w
        if w.tonics <= 0:
            return False
        w.tonics -= 1
        w.la.hp = min(w.la.maxHp, w.la.hp + w.heal)
        return True

    def close(self):
        FakeFighter.w.closed += 1


def fakeModules(w):
    st = types.ModuleType('s_story')
    st.hereArea = lambda H: H.area()[1]
    st.questSpots = lambda: {'objs': {str(i): [w.areaT[1], n[0], n[1], 0.0, 'Spawn Node', n[2]] for i, n in enumerate(w.nodes)},
                             'exits': {}}
    st.areaObj = lambda H, uid: None
    st._render_pt = lambda H, target, ref=None: tuple(target)

    def go(H, target, arrive, face, ref, tag):
        pos = target.getPos() if hasattr(target, 'getPos') else target
        return (yield from H.walk_to(pos, arrive=arrive, timeout=40.0, tag=tag))
    st.go = go
    cw = types.ModuleType('s_cavewalk')

    def move_free(wp):
        while math.hypot(wp[0] - w.la.pos[0], wp[1] - w.la.pos[1]) > 1.0:
            x, y = w.la.pos[0], w.la.pos[1]
            n = math.hypot(wp[0] - x, wp[1] - y)
            k = min(1.0, 8.0 / n)
            w.la.pos[0], w.la.pos[1] = x + (wp[0] - x) * k, y + (wp[1] - y) * k
            yield 1.0

    def walk(H, target, arrive, tag):
        w.cave_calls += 1
        if w.nodata:
            H.ev('CAVE-NO-ROUTE', tag=tag, why='no world data waypoints')
            return None
        if w.noway:
            H.ev('CAVE-NO-ROUTE', tag=tag, why='no open way from [1, 2]')
            yield 1.0
            return False
        if w.flip:
            w.areaT = ('DistributedIsland', 'isl1')
            yield 1.0
            return 'area'
        for wp in ((35.0, 15.0), (35.0, 28.0), (target[0], target[1])):
            yield from move_free(wp)
        return math.hypot(target[0] - w.la.pos[0], target[1] - w.la.pos[1]) <= arrive
    cw.walk = walk
    sys.modules['s_story'], sys.modules['s_cavewalk'] = st, cw


def drive(gen, limit=40000):
    steps = 0
    try:
        item = next(gen)
        while True:
            steps += 1
            assert steps < limit, 'driver limit'
            if isinstance(item, tuple):
                _, fn, secs, _what = item
                t0 = CLK.t
                while not fn() and CLK.t - t0 < secs:
                    CLK.t += 1
            else:
                CLK.t += item
            item = next(gen)
    except StopIteration as e:
        return e.value


class Bot:
    def __init__(self, w):
        self.H, self.w = w.H, w

    def bug(self, kind, key, tag, what, tb=''):
        self.w.bugs.append((kind, key, tag, what))


fails = []


def check(name, ok, info=''):
    print(('PASS ' if ok else 'FAIL ') + name + (' ' + str(info) if info and not ok else ''))
    if not ok:
        fails.append(name)


import land            # noqa: E402
land.time = CLK
land.s_fighter.Fighter = FakeFighter
land.s_fighter.foeRows = lambda H: [
    (f.doId, math.hypot(f.pos[0] - H.la.pos[0], f.pos[1] - H.la.pos[1]), f.hp, f.level, (f.pos[0], f.pos[1]))
    for f in FakeFighter.w.foes.values() if f.doId != PLAYER1]


def world(flip=False, **kw):
    w = World(**kw)
    w.flip = flip
    FakeFighter.w = w
    fakeModules(w)
    return w


def hunt(w, **kw):
    """One hunt through Land.flow() (the brain's path). -> (result, land)."""
    L = land.Land(Bot(w))
    L.greeted = {i: 1e12 for i in land.CAPTAINS}       # the boys were greeted already: a hello is its own duty (t_land_social)
    return drive(L.flow()), L


# ---- 1. pure helpers
check('legFor: close = straight, cave beyond 12 ft = cave walker, land beyond 60 ft = route',
      land.legFor(10, True) == 'engage' and land.legFor(13, True) == 'cave' and land.legFor(59, False) == 'engage'
      and land.legFor(61, False) == 'route')
check('huntOk: healthy on land in a cave / island', land.huntOk(0.9, 'LandRoam', 'DistributedGAInterior')
      and land.huntOk(0.8, 'Battle', 'DistributedIsland'))
check('huntOk: not hurt, not on a ship, not in a jail', not land.huntOk(0.5, 'LandRoam', 'DistributedIsland')
      and not land.huntOk(0.9, 'OnShip', 'DistributedIsland') and not land.huntOk(0.9, 'LandRoam', 'DistributedJailInterior'))
check('hunt duty asks at 30, below a tonic (60) and jail (100)',
      land.duty({'hpf': 0.9, 'hunt': True, 'tonics': 3, 'ready': True, 'gs': 'LandRoam'})[0] == 'hunt'
      and land.duty({'hpf': 0.4, 'hunt': False, 'tonics': 3, 'ready': True, 'gs': 'LandRoam'})[0] == 'tonic'
      and land.SCORE['jail'] > land.SCORE['tonic'] > land.SCORE['hunt'] >= 10)
check('hunt quiet -> nothing', land.duty({'hpf': 0.9, 'hunt': True, 'quiet': {'hunt': True}}) is None)
check('restAfter: no-spawn longest, no-foe 300, ko 30', land.restAfter('no-spawn') == 600 and land.restAfter('no-foe') == 300
      and land.restAfter('ko') == 30 and land.restAfter('time') == land.HUNT_REST)
rows = [(1, 14.0, 100, 1, (10.0, 10.0)), (2, 90.0, 100, 1, (90.0, 0.0)), (3, 50.0, 100, 3, (50.0, 0.0))]
check('pickTarget: not the foe next to a boy, and not one over its level', land.pickTarget(rows, 1, 0, {}, 0, [(0.0, 0.0)]) == 2)
check('pickTarget: with no boy the nearest weak one', land.pickTarget(rows, 1, 0, {}, 0, []) == 1)
check('pickTarget: a foe left alone (skip) is passed over', land.pickTarget(rows, 1, 0, {1: 100.0}, 0, []) == 2)
two = [(5, 40.0, 100, 2, (40.0, 0.0))]
check('Vitae: a level-2 foe at level 1 is fought without Vitae, not with it',
      land.pickTarget(two, 1, 0, {}, 0, []) == 5 and land.pickTarget(two, 1, 1, {}, 0, []) is None)
check('attackerRow: a live foe within 12 ft, weak or not', land.attackerRow([(7, 6.0, 90, 4, (1, 1))], 1, 1) == (7, False)
      and land.attackerRow([(7, 30.0, 90, 1, (1, 1))], 1, 1) is None)

# ---- 2. BEFORE: every leg the straight walk (what Fighter does alone): the foe behind the wall is never reached
w = world(nodes=[(5.0, 5.0, 'Noob Skeleton Camp')])
w.add(11, 0.0, 60.0)
keep = land.legFor
land.legFor = lambda d, cave: 'engage'
res, L = hunt(w)
land.legFor = keep
check('BEFORE (straight walk): the foe behind the cave wall is never reached (0 kills, FOE-STUCK)',
      res and res['kills'] == 0 and w.count('LAND-FOE-STUCK') >= 1 and w.cave_calls == 0, (res, w.count('LAND-FOE-STUCK')))

# ---- 3. AFTER: the cave leg goes through the cave walker
w = world(nodes=[(5.0, 5.0, 'Noob Skeleton Camp')])
w.add(11, 0.0, 60.0)
res, L = hunt(w)
check('AFTER: the hunt ends by itself with a result dict', isinstance(res, dict) and res['duty'] == 'hunt' and res['ok'], res)
check('AFTER: the foe behind the wall is killed (1 kill, gold paid)', res and res['kills'] == 1 and res['gold'] == 12, res)
check('AFTER: the cave walker was used, the straight walk never stuck', w.cave_calls >= 1 and w.count('LAND-FOE-STUCK') == 0,
      (w.cave_calls, w.count('LAND-FOE-STUCK')))
check('AFTER: LAND-HUNT, LAND-KILL, LAND-HUNT-END logged; a fighter closed per fight; the walker cancelled',
      w.count('LAND-HUNT') == 1 and w.count('LAND-KILL') == 1 and w.count('LAND-HUNT-END') == 1 and w.closed >= 1
      and w.cancels >= 1, w.names()[:12])
check('AFTER: no foe left -> it ends no-foe and stays quiet', res['end'] in ('no-foe', 'time') and 'hunt' in L.quietUntil
      and land.duty(L.state()) is None, res)
CLK.t += 400.0
check('AFTER: quiet over -> want() asks for a hunt again at 30', (L.want() or (0,))[0] == 30)

# ---- 4. a cave with no waypoints: the straight walk, and no later try of the cave walker there
w = world(wall=False, nodata=True)
w.add(11, 0.0, 60.0)
res, L = hunt(w)
check('no waypoints: the foe is still killed (straight walk)', res and res['kills'] == 1, res)
check('no waypoints: LAND-CAVE-NODATA once, area remembered, inCave() false after', w.count('LAND-CAVE-NODATA') == 1
      and 'cave1' in L.noData and not L.inCave() and w.cave_calls == 1, (w.count('LAND-CAVE-NODATA'), w.cave_calls))

# ---- 5. 'no open way' twice at one area = ONE BOT bug, no crash, the foe left alone
w = world(noway=True, nodes=[(5.0, 5.0, 'Noob Skeleton Camp')])
w.add(11, 0.0, 60.0)
L = land.Land(Bot(w))
r1 = drive(L.flow())
check('no open way: the hunt ends cleanly, nothing killed', r1 and r1['ok'] and r1['kills'] == 0, r1)
check('no open way: one try so far = no bug yet', len(w.bugs) == 0 and w.count('LAND-FOE-NO-WAY') >= 1, (w.bugs, w.names()[:10]))
CLK.t += 400.0
r2 = drive(L.flow())
check('no open way: the second time at that area files ONE BOT stuck bug (key land-cave-no-route-cave1)',
      len(w.bugs) == 1 and w.bugs[0][:3] == ('stuck', 'land-cave-no-route-cave1', 'BOT'), w.bugs)
CLK.t += 400.0
drive(L.flow())
check('no open way: a third hunt does not file it again', len(w.bugs) == 1, w.bugs)

# ---- 6. knocked out mid-fight: the hunt ends ko, the fighter is closed, quiet 30 s
w = world(wall=False)
w.add(11, 0.0, 60.0, hp=500)
w.koAfter = 2
res, L = hunt(w)
check('KO mid-fight: end ko, fighter closed, hunt quiet 30 s', res and res['end'] == 'ko' and w.closed >= 1
      and round(L.quietUntil['hunt'] - CLK.t) in (29, 30), (res, w.closed))

# ---- 7. a tunnel takes it to another area: the hunt ends 'area'
w = world(flip=True)
w.add(11, 0.0, 60.0)
res, L = hunt(w)
check('area changed mid-leg: end area', res and res['end'] == 'area' and res['kills'] == 0, res)

# ---- 8. a tonic between fights: 55% hp, tonics to spare, the foe far away
w = world(wall=False, hp=550)
w.add(11, 0.0, 60.0)
L = land.Land(Bot(w))
res = drive(L.hunt())
check('tonic between fights at 55% hp (heal 100), then the foe is fought', w.count('LAND-TONIC') >= 1 and res['kills'] == 1
      and w.tonics == 2, (w.names()[:8], w.tonics))

# ---- 9. the boys: a foe next to Player1 is left alone, another is hunted
w = world(wall=False)
w.add(11, 10.0, 10.0)
w.add(12, 0.0, 90.0)
w.foes[PLAYER1] = Foe(w, PLAYER1, 0.0, 0.0)        # Player1's pirate, on this client (not an enemy: foeRows leaves him out)
res, L = hunt(w)
check('boys: the foe 14 ft from Player1 is never fought, the far one is (1 kill)', res and res['kills'] == 1
      and 11 in w.foes and 12 not in w.foes, (res, list(w.foes)))

# ---- 10. a spawn node next to a boy is not walked to
w = world(wall=False, nodes=[(5.0, 5.0, 'Noob Skeleton Camp'), (60.0, 0.0, 'Noob Skeleton Camp')])
w.foes[PLAYER1] = Foe(w, PLAYER1, 0.0, 0.0)
res, L = hunt(w)
picks = [kw['spot'] for n, kw in w.events if n == 'LAND-SPAWN-PICK']
check('boys: only the camp 60 ft from Player1 is walked to (not the one 7 ft from him)', picks and all(p[0] == 60.0 for p in picks), picks)
check('hunt ends by itself, no crash (BOT bug list empty)', res and res['ok'] and not w.bugs, (res, w.bugs))

# ---- 11. the hunt's ground: LANDPROOF1 swept camps 1400 ft from where it started (one unreachable on a hillside)
N = 'Noob Skeleton Camp'
NEAR_FAR = [(5.0, 5.0, N), (3000.0, 0.0, N)]
real = land.huntGround
land.huntGround = lambda nodes, here, home, lvl, rng=0: (home, nodes)          # BEFORE: every camp of the island
w = world(wall=False, nodes=NEAR_FAR)
res, L = hunt(w)
picks = [kw['spot'][0] for n, kw in w.events if n == 'LAND-SPAWN-PICK']
check('BEFORE (no cap): the camp 3000 ft away is walked to', 3000.0 in picks, picks)
land.huntGround = real                                                           # AFTER: the ground round the home camp
w = world(wall=False, nodes=NEAR_FAR)
res, L = hunt(w)
picks = [kw['spot'][0] for n, kw in w.events if n == 'LAND-SPAWN-PICK']
hev = [kw for n, kw in w.events if n == 'LAND-HUNT']
check('AFTER: only the camp next to it is walked to, never the one 3000 ft out', picks and all(p < 1000.0 for p in picks), picks)
check('AFTER: LAND-HUNT names the home, the camps kept (1) and the ones left out (1)',
      hev and hev[0]['nodes'] == 1 and hev[0]['far'] == 1 and hev[0]['home'] == (5.0, 5.0), hev)
check('AFTER: the hunt still ends by itself with nothing to fight (no-foe), no BOT bug', res and res['ok'] and res['end'] == 'no-foe'
      and not w.bugs, (res, w.bugs))
check('AFTER: the home is kept for the next hunt in this area', L.home.get('cave1') == (5.0, 5.0), L.home)
w = world(wall=False, nodes=[(1500.0, 0.0, N)])                                 # every camp is far: it still goes to the nearest
res, L = hunt(w)
picks = [kw['spot'][0] for n, kw in w.events if n == 'LAND-SPAWN-PICK']
check('AFTER: all camps far from the pirate = it still walks to the nearest', picks and picks[0] == 1500.0, picks)
# the pure rule (nodes as spawnNodes gives them: x, y, z, name)
NF = [(5.0, 5.0, 0.0, N), (3000.0, 0.0, 0.0, N)]
check('huntGround: no camps = nothing, the home kept', land.huntGround([], (0.0, 0.0), (1.0, 1.0), 1) == ((1.0, 1.0), []))
check('huntGround: the first hunt builds the home round the camp it would take, drops the far ones',
      land.huntGround(NF, (0.0, 0.0), None, 1) == ((5.0, 5.0), [NF[0]]))
two = [(5.0, 5.0, 0.0, N), (900.0, 0.0, 0.0, N)]
check('huntGround: a pirate that walked on (still within the range) keeps the stored home',
      land.huntGround(two, (900.0, 0.0), (5.0, 5.0), 1) == ((5.0, 5.0), two))
check('huntGround: a pirate far from the stored home (a teleport) gets a new one there',
      land.huntGround(NF, (3000.0, 0.0), (5.0, 5.0), 1) == ((3000.0, 0.0), [NF[1]]))
mix = [(100.0, 0.0, 0.0, 'Low Navy'), (800.0, 0.0, 0.0, 'Noob Navy')]
check('huntGround: the home is the weakest camp tier it takes (Noob before Low), the Low one 700 ft off is kept',
      land.huntGround(mix, (100.0, 0.0), None, 1) == ((800.0, 0.0), mix))

print('FAIL: ' + '; '.join(fails) if fails else 'ALL PASS')
sys.exit(1 if fails else 0)
