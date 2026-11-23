"""Offline test of pbot\\skills\\land.py step 1 (11-22): a knocked-out pirate gets out of jail, and a hurt one drinks a tonic
between fights. Fake world: no game, no s_story (the jail stepper itself is proven live by the island tour; here a stand-in
with the same contract is injected: jail(H, st) -> a word while it works and leaves its walks in st['go'], None when out).
BEFORE: the brain today does nothing for a jailed pirate (st_down only logs; gs not in PLAY -> WAIT), so the same world
with no land skill leaves the pirate in its cell for the whole time. AFTER: Land.want() asks for the jail duty first and
Land.flow() walks the pirate out; a hurt pirate on land drinks (keeping one tonic, one drink per TONIC_GAP s); a jail it
cannot leave files a BOT 'stuck' bug.
Run: python3 t_land_duty.py <dir holding pbot\\skills\\land.py's harness, e.g. C:\\Dev\\Toontown\\pirates-harness>"""
import os, sys, types

D = os.path.abspath(sys.argv[1])
sys.path.insert(0, D)
sys.path.insert(0, os.path.join(D, 'pbot', 'skills'))


class Clock:
    t = 1000.0

    def time(self):
        return self.t


CLK = Clock()


# ---- a fake game module for the two imports Fighter / land make
ug = types.ModuleType('pirates.uberdog.UberDogGlobals')


class InventoryType:
    UseItem = 7
    Vitae_Level = 99


ug.InventoryType = InventoryType
for n in ('pirates', 'pirates.uberdog'):
    sys.modules[n] = types.ModuleType(n)
sys.modules['pirates.uberdog.UberDogGlobals'] = ug


class Inv:
    def __init__(self, w):
        self.w = w

    def getTonics(self):
        return {1: self.w.tonics}

    def getStackQuantity(self, k):
        return self.w.vitae if k == InventoryType.Vitae_Level else 0


class Diary:
    def getTimeRemaining(self, sid):
        return 0


class Tray:
    def __init__(self, w):
        self.w = w
        self.tonicButton = types.SimpleNamespace(getBestTonic=lambda: 1)

    def trySkill(self, sid, ammo, combo=0, charge=0):
        w = self.w
        if sid != InventoryType.UseItem or w.tonics <= 0 or w.gs != 'LandRoam':
            return 0
        w.tonics -= 1
        w.la.hp = min(w.la.maxHp, w.la.hp + w.heal)
        return 1


class Avatar:
    pass


class World:
    """A pirate on land (hp, tonics) or in a jail cell. stage = how far the stand-in jail stepper got."""

    def __init__(self, jailed=False, hp=400, maxHp=1000, tonics=3, heal=100, stuckInJail=False):
        self.tonics, self.heal, self.vitae = tonics, heal, 0
        self.jailed, self.stage, self.stuck = jailed, 0, stuckInJail
        self.gs = 'LandRoam'
        self.events, self.bugs = [], []
        la = self.la = Avatar()
        la.hp, la.maxHp, la.doId, la.name = (1 if jailed else hp), maxHp, 100000999, 'Test Pirate'
        la.jailCellIndex = 0 if jailed else 100
        la.getGameState = lambda: self.gs
        la.getInventory = lambda: Inv(self)
        la.skillDiary = Diary()
        la.guiMgr = types.SimpleNamespace(combatTray=Tray(self))
        self.H = types.SimpleNamespace(la=la, cr=None, ev=lambda name, **kw: self.events.append((name, kw)),
                                       area=self.area, P=lambda a: (0, 0, 0))

    def area(self):
        return ('DistributedJailInterior', 1) if self.jailed else ('DistributedIsland', 2)

    def names(self):
        return [e[0] for e in self.events]

    def freed(self):
        self.jailed, self.la.jailCellIndex = False, 100


def fakeStory(w):
    """The s_story stand-in: kick (3 calls), a walk out of the cell, a walk to the jail door, then out."""
    m = types.ModuleType('s_story')

    def jail(H, st):
        if not w.jailed:
            return None
        if w.stuck:
            return 'jail-kick'                       # the door never breaks
        if w.stage < 3:
            w.stage += 1
            return 'jail-kick'
        if w.stage == 3:
            st['go'] = ('cell', 3, None, None, 'out of the cell')
            return 'out-of-cell'
        if w.stage == 4:
            st['go'] = ('door', 3, None, None, 'jail door')
            return 'jail-door'
        w.freed()
        return None

    def go(H, obj, arrive, face, ref, tag):
        yield 3
        w.stage += 1
    m.jail, m.go = jail, go
    return m


def drive(w, gen, limit=2000):
    """Run a land generator on the fake clock. -> its return value."""
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
                    land_tick(w)
            else:
                CLK.t += item
                land_tick(w)
            item = next(gen)
    except StopIteration as e:
        return e.value


def land_tick(w):
    pass


class Bot:
    def __init__(self, w):
        self.H = w.H
        self.w = w

    def bug(self, kind, key, tag, what, tb=''):
        self.w.bugs.append((kind, key, tag, what))


fails = []


def check(name, ok, info=''):
    print(('PASS ' if ok else 'FAIL ') + name + (' ' + str(info) if info and not ok else ''))
    if not ok:
        fails.append(name)


import land            # noqa: E402
land.time = CLK        # the skill's clock is the fake one

# ---- 1. pure: the duty table
def d(**kw):
    s = {'jailed': False, 'hpf': 1.0, 'tonics': 3, 'ready': True, 'gs': 'LandRoam', 'tonicAgo': None}
    s.update(kw)
    return land.duty(s)

check('jailed -> jail duty', (d(jailed=True) or ('',))[0] == 'jail')
check('jail beats a tonic', (d(jailed=True, hpf=0.2) or ('',))[0] == 'jail')
check('hurt on land with spare tonics -> tonic', (d(hpf=0.4) or ('',))[0] == 'tonic')
check('healthy -> nothing', d(hpf=0.9) is None)
check('last tonic is kept for the next fight', d(hpf=0.3, tonics=1) is None)
check('not while fighting (Battle)', d(hpf=0.3, gs='Battle') is None)
check('not within TONIC_GAP of the last drink', d(hpf=0.3, tonicAgo=3.0) is None)
check('again after TONIC_GAP', (d(hpf=0.3, tonicAgo=9.0) or ('',))[0] == 'tonic')
check('tonic timer not ready -> nothing', d(hpf=0.3, ready=False) is None)
check('Vitae running: foes no stronger than itself', land.foeOver(1) == 0 and land.foeOver(0) == land.s_fighter.LVL_OVER >= 1)
last = {}
check('SpeedChat: hi goes', land.scDue('hi', last, 0.0) == 100)
last['hi'] = 0.0
check('SpeedChat: not again within the gap', land.scDue('hi', last, land.SC_GAP - 1) is None)
check('SpeedChat: again after the gap', land.scDue('hi', last, land.SC_GAP) == 100)
check('SpeedChat: unknown line is never sent', land.scDue('type this', {}, 0.0) is None)

# ---- 2. BEFORE: the brain today (no land skill) leaves a jailed pirate in its cell
w = World(jailed=True)
CLK.t += 420
check('BEFORE: no land skill -> still in jail after 420 s', land.jailedNow(w.H))

# ---- 3. AFTER: Land walks it out
w = World(jailed=True)
sys.modules['s_story'] = fakeStory(w)
sk = land.Land(Bot(w))
check('want(): jail first', (sk.want() or (0,))[0] == land.SCORE['jail'], sk.want())
t0 = CLK.t
r = drive(w, sk.flow())
check('AFTER: flow returns a small dict, ok', isinstance(r, dict) and r.get('duty') == 'jail' and r.get('ok') is True, r)
check('AFTER: out of the jail', not land.jailedNow(w.H))
check('AFTER: no BOT bug filed', not w.bugs, w.bugs)
n = w.names()
check('AFTER: events LAND-JAIL, steps, LAND-JAIL-OUT ok',
      'LAND-JAIL' in n and 'LAND-JAIL-STEP' in n and n[-1] == 'LAND-JAIL-OUT' and dict(w.events[-1][1])['ok'] is True, n)
steps = [kw['a'] for name, kw in w.events if name == 'LAND-JAIL-STEP']
check('AFTER: steps in order kick, cell, door', steps == ['jail-kick', 'out-of-cell', 'jail-door'], steps)
check('AFTER: well inside JAIL_LIMIT', CLK.t - t0 < land.JAIL_LIMIT / 2, CLK.t - t0)
check('AFTER: out of jail at hp 1 -> it drinks next, not the jail again', (sk.want() or ('', ''))[1].startswith('tonic'), sk.want())

# ---- 4. a jail it cannot leave: a BOT stuck bug, flow returns False
w = World(jailed=True, stuckInJail=True)
sys.modules['s_story'] = fakeStory(w)
land.JAIL_LIMIT = 40.0
sk = land.Land(Bot(w))
r = drive(w, sk.flow())
check('stuck: flow returns ok False', isinstance(r, dict) and r.get('ok') is False, r)
check('stuck: one BOT stuck bug', len(w.bugs) == 1 and w.bugs[0][0] == 'stuck' and w.bugs[0][2] == 'BOT', w.bugs)
check('stuck: bug key is land-stuck-jail-<area class>', w.bugs[0][1] == 'land-stuck-jail-distributedjailinterior', w.bugs)

# ---- 5. tonics between fights: hurt, 3 tonics, +10% per drink
w = World(jailed=False, hp=300, tonics=3, heal=100)
sk = land.Land(Bot(w))
check('tonic: wanted at 30% with 3 tonics', (sk.want() or ('',))[1].startswith('tonic'), sk.want())
r = drive(w, sk.flow())
check('tonic: drank (ok, hp up, tonics 2)', isinstance(r, dict) and r.get('ok') is True and w.la.hp == 400 and w.tonics == 2,
      (r, w.la.hp, w.tonics))
check('tonic: tray is unwrapped again afterwards', 'trySkill' not in w.la.guiMgr.combatTray.__dict__)
check('tonic: not again at once (TONIC_GAP)', sk.want() is None)
CLK.t += land.TONIC_GAP
check('tonic: again after the gap (hp 40%, 2 tonics)', sk.want() is not None)
drive(w, sk.flow())
check('tonic: second drink', w.tonics == 1 and w.la.hp == 500, (w.tonics, w.la.hp))
CLK.t += land.TONIC_GAP
check('tonic: the last one is kept', sk.want() is None)
check('tonic: events LAND-TONIC x2', w.names().count('LAND-TONIC') == 2, w.names())

# ---- 6. step script refuses the boys' and Host's pirates
w = World()
for pid in land.NEVER:
    w.la.doId = pid
    out = list(land.run(w.H))
    check('run() refuses %d' % pid, out == [] and w.events and w.events[-1][0] == 'FAIL')
    w.events.clear()

# ---- 7. the INTERFACE.md shape (pbots 11-22)
check('INTERFACE: name/limit/crewOk', land.Land.name == 'land' and land.Land.limit == 600 and land.Land.crewOk is False)

w = World(hp=1000, tonics=3)
reads = []
w.la.getInventory = lambda: reads.append(1) or Inv(w)
sk = land.Land(Bot(w))
got = sk.want()
check('INTERFACE: want() on a healthy pirate asks for the free-play hunt (30); the unspent stacks are read once (cached 15 s)',
      got is not None and got[0] == 30 and 'hunt' in got[1] and len(reads) == 1, (got, reads))
sk.quietUntil['hunt'] = land.time.time() + 100.0
check('INTERFACE: ... and is None while the hunt rests, with no new inventory read inside the 15 s cache',
      sk.want() is None and len(reads) == 1, reads)

w = World(hp=300)
sk = land.Land(Bot(w))
r = sk.cut('limit')
check('INTERFACE: cut() returns None (nothing to clean) and logs LAND-CUT', r is None and 'LAND-CUT' in w.names(), w.names())

# PlayerH: reserved names renamed, mw refused (BOT bug via flow), snap is not a screenshot
w = World()
ph = land.PlayerH(w.H)
ph.ev('PASS', why='x')
ph.ev('CREW-JOIN')
ph.ev('PBOT-X')
ph.ev('LAND-OWN')
check('PlayerH: PASS/CREW-/PBOT- renamed LAND-..., own names kept', w.names() == ['LAND-PASS', 'LAND-CREW-JOIN', 'LAND-PBOT-X', 'LAND-OWN'], w.names())
try:
    ph.mw('giveQuest 1')
    check('PlayerH: mw raises Blocked', False)
except land.Blocked:
    check('PlayerH: mw raises Blocked', ph.blocked == 'giveQuest 1' and 'LAND-MW-BLOCKED' in w.names())

# strict(): until -> upto, and the value comes through
w = World()
state = {'v': False}


def inner():
    yield ('until', lambda: state['v'], 5, 'thing')
    yield 2
    return 'done'


g = land.strict(inner(), land.PlayerH(w.H))
first = next(g)
check('strict: until became upto', first[0] == 'upto' and first[2] == 5 and first[3] == 'thing', first)
second = g.send(None)
check('strict: a failed wait logs LAND-WAIT and goes on', second == 2 and 'LAND-WAIT' in w.names(), (second, w.names()))
try:
    g.send(None)
    check('strict: returns the generator value', False)
except StopIteration as e:
    check('strict: returns the generator value', e.value == 'done', e.value)

# flow(): a crash is one BOT traceback bug with a land-crash key, the skill goes quiet, flow returns ok False
w = World(jailed=True)
boom = types.ModuleType('s_story')


def jailBoom(H, st):
    raise ValueError('boom')


boom.jail, boom.go = jailBoom, lambda *a, **k: iter(())
sys.modules['s_story'] = boom
sk = land.Land(Bot(w))
r = drive(w, sk.flow())
check('crash: flow returns ok False, why bot', isinstance(r, dict) and r.get('ok') is False and r.get('why') == 'bot', r)
check('crash: one BOT traceback bug with a land-crash key',
      len(w.bugs) == 1 and w.bugs[0][0] == 'traceback' and w.bugs[0][2] == 'BOT' and w.bugs[0][1].startswith('land-crash-valueerror'), w.bugs)
check('crash: SAFETY (jail) never goes quiet, it is asked again', sk.want() is not None and sk.want()[0] == land.SCORE['jail'])

# flow(): a magic word asked for is blocked, filed once as a BOT bug
w = World(jailed=True)
mwm = types.ModuleType('s_story')


def jailMw(H, st):
    H.mw('removeGroggy')


mwm.jail, mwm.go = jailMw, lambda *a, **k: iter(())
sys.modules['s_story'] = mwm
sk = land.Land(Bot(w))
r = drive(w, sk.flow())
check('mw: blocked, one BOT bug land-mw-blocked', len(w.bugs) == 1 and w.bugs[0][1] == 'land-mw-blocked' and w.bugs[0][2] == 'BOT', w.bugs)

print('ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails))
sys.exit(1 if fails else 0)
