"""Offline test of pbot\\skills\\land.py step 3 (11-22): SKILL POINTS (row 45), WEAPONS (row 44), the put-away (cut cleanup) and
the low-tonic event (row 46).
Fake world: no game. A pirate on an island with an inventory of stacks (weapons <Kind>WeaponL1.., skills with the game's
quantity convention learned = 1, each point +1, Unspent<Kind> stacks), the skill page (open with the Skills key through
builtins.messenger; update(rep) picks a weapon's tab; addPoint(skill) spends one point: skill +1, unspent -1), the weapon
toggle (draw / put away, the Battle state), a tray that answers triggerSkillTraySkill, and a stand-in Fighter with the same
contract as the real one (tray, tries, hits, skills, down, foe; step() every beat).
BEFORE: the skill duty replaced by one that does nothing (the pirate never opens the page): the points stay unspent. The weapon
choice forced to the cutlass: dagger, doll... are never drawn. AFTER: the points are spent through the page (right skill,
right weapon tab, page closed again); every owned weapon gets a hunt; its skills are fired between beats; a weapon that lands
no hit in a whole fight is left alone and the cutlass takes over; a weapon that will not draw is left alone; the weapon is put
away at the hunt end and by cut(); a hurt pirate with no tonic says so once.
Run: python3 t_land_skill.py <harness dir, e.g. C:\\Dev\\Toontown\\pirates-harness>"""
import builtins, math, os, sys, types

D = os.path.abspath(sys.argv[1])
sys.path.insert(0, D)
sys.path.insert(0, os.path.join(D, 'pbot', 'skills'))


class Clock:
    t = 1000.0

    def time(self):
        return self.t


CLK = Clock()

# ---- the game's names: sequences from UberDogGlobals.InventoryType (read from the game source 11-22)
SEQ = {
    'Cutlass': (12100, ['Hack', 'Slash', 'Cleave', 'Flourish', 'Stab', 'Parry', 'Endurance', 'Sweep', 'Brawl', 'Taunt', 'Bladestorm']),
    'Pistol': (12200, ['Shoot', 'LeadShot', 'VenomShot', 'BaneShot', 'HexEaterShot', 'SilverShot', 'SteelShot', 'SharpShooter']),
    'Dagger': (12400, ['Cut', 'Swipe', 'Gouge', 'Eviscerate', 'Finesse', 'BladeInstinct', 'Asp', 'Adder', 'ThrowDirt',
                       'Sidewinder', 'ViperNest']),
    'Doll': (12600, ['Attune', 'Poke', 'Swarm', 'Heal', 'Curse', 'Burn', 'Cure', 'Shackles', 'LifeDrain', 'Focus', 'SpiritWard']),
    'Wand': (12700, ['Blast', 'SoulFlay', 'Pestilence', 'Wither', 'Hellfire', 'Banish', 'Desolation', 'Concentration']),
}
KINDS5 = ('Cutlass', 'Dagger', 'Pistol', 'Doll', 'Wand')


class InventoryType:
    UseItem = 7
    Vitae_Level = 99


for kind, (base, names) in SEQ.items():
    pre = 'Staff' if kind == 'Wand' else kind
    for i, n in enumerate(names):
        setattr(InventoryType, pre + n, base + i)
for i, kind in enumerate(KINDS5):
    setattr(InventoryType, kind + 'Rep', 13700 + i)
    setattr(InventoryType, 'Unspent' + kind, 13750 + i)
    for lvl in range(1, 7):
        setattr(InventoryType, '%sWeaponL%d' % (kind, lvl), 1000 + i * 10 + lvl)
InventoryType.CannonRep, InventoryType.UnspentCannon = 13705, 13755     # the page's default tab (SkillPage.currentRep at birth)
REP2KIND = {getattr(InventoryType, k + 'Rep'): k for k in KINDS5}
WID2KIND = {getattr(InventoryType, '%sWeaponL%d' % (k, n)): k for k in KINDS5 for n in range(1, 7)}
IT = InventoryType

ug = types.ModuleType('pirates.uberdog.UberDogGlobals')
ug.InventoryType = InventoryType
wg = types.ModuleType('pirates.battle.WeaponGlobals')
wg.getMojoCost = lambda sid: 0
bm = types.ModuleType('pirates.battle')
bm.WeaponGlobals = wg
for n in ('pirates', 'pirates.uberdog'):
    sys.modules[n] = types.ModuleType(n)
sys.modules['pirates.uberdog.UberDogGlobals'] = ug
sys.modules['pirates.battle'], sys.modules['pirates.battle.WeaponGlobals'] = bm, wg
sys.modules['pirates'].battle = bm


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
        if k == IT.Vitae_Level:
            return 0
        return self.w.stacks.get(k, 0)

    def getGoldInPocket(self):
        return self.w.gold

    def getStackLimit(self, k):                      # 0 = the game has no such stack (SkillPage.addPoint drops the press)
        return 0 if self.w.noLimit else 6


class Diary:
    def __init__(self, w):
        self.w = w

    def getTimeRemaining(self, sid):
        return max(0.0, self.w.rechargeUntil.get(sid, 0.0) - CLK.t)


class Avatar:
    def spentSkillPoint(self, category, *a):         # the class's own method (the flow wraps it on the instance and removes it)
        return 'class'


class Page:
    """SkillPage as the client has it (read from the source 11-22): the tab bar is made by show() (the chest turns to the page);
    currentRep is the Cannon tab until update(rep) picks one (update returns at once, WITHOUT picking, while there is no tab bar);
    localMods are the page's own counts; addPoint drops a press without a word, in the client's order: tutorial gate, no unspent
    point on the CURRENT tab, no stack limit, a skill past 5. A press the game takes is answered by the server at once
    (spentSkillPoint) unless w.dropPresses says the answer is lost."""
    def __init__(self, w):
        self.w, self.reps, self.shows = w, [], 0
        self.tabBar, self.currentRep, self.localMods, self.lastTab = None, IT.CannonRep, {}, None
        self.skillFrames = {}

    def show(self):
        w = self.w
        self.shows += 1
        if self.tabBar is None and not w.noTabBar:
            self.tabBar = object()
        if self.tabBar is not None:
            self.currentRep = self.lastTab or IT.CannonRep

    def setRep(self, rep):
        self.currentRep = rep

    def update(self, rep=None, fromUser=0):
        w = self.w
        if self.tabBar is None:
            return                                   # the client returns before picking a tab
        if w.snaps > 0 and rep is not None:          # a level-up banner just shut the page and re-tabbed it
            w.snaps -= 1
            w.banner_until = CLK.t + 5.0
            w.pageIsOpen = False
            self.currentRep = IT.CannonRep
            return
        self.currentRep = rep or self.lastTab or IT.CannonRep
        if rep is not None:
            self.reps.append(rep)
            if fromUser:
                self.lastTab = rep

    def addPoint(self, sid):
        w = self.w
        if w.pageBroken:
            return
        rep, mods = self.currentRep, self.localMods
        tut = w.la.style.tutorial
        if rep == IT.CutlassRep and tut < 4 and w.stacks.get(IT.CutlassSweep, 0) < 2 and sid != IT.CutlassSweep:
            return
        un = getattr(IT, 'Unspent' + REP2KIND[rep]) if rep in REP2KIND else IT.UnspentCannon
        unSp = mods.get(un, w.stacks.get(un, 0))
        if unSp < 1:
            return
        if w.noLimit:                                # inv.getStackLimit(sid) is falsy
            return
        cur = mods.get(sid, w.stacks.get(sid, 0))
        if cur > 5:
            return
        mods[sid], mods[un] = cur + 1, unSp - 1      # the page's own counts, until the game's answer
        if w.dropPresses > 0:
            w.dropPresses -= 1
            return                                   # spendSkillPoint went nowhere: no answer, the stacks never move
        if w.stacks.get(un, 0) > 0 and 1 <= w.stacks.get(sid, 0) <= 5:
            w.stacks[sid] += 1
            w.stacks[un] -= 1
            mods.pop(un, None)                       # GuiManager.updateUnspent drops the category's local count
            w.la.spentSkillPoint(rep)


class Msg:
    def __init__(self, w):
        self.w = w

    def send(self, evt):
        if evt == 'guiMgrToggleLevels' and not self.w.pageNever:
            self.w.pageIsOpen = not self.w.pageIsOpen
            self.w.toggles += 1
            if self.w.pageIsOpen and not self.w.noShow:
                self.w.page.show()                   # the chest turns to the page


class World:
    def __init__(self, hp=1000, tonics=3, stacks=None, area=('DistributedIsland', 'isl1')):
        self.tonics, self.gold, self.gs, self.areaT = tonics, 0, 'LandRoam', area
        self.stacks = dict(stacks or {})
        self.events, self.bugs, self.foes = [], [], {}
        self.cancels, self.closed, self.toggles = 0, 0, 0
        self.pageIsOpen, self.pageBroken, self.pageNever = False, False, False
        self.ignoreToggles, self.noHit, self.trayRefuse = 0, set(), False
        self.togglesW, self.trigs, self.rechargeUntil = [], [], {}
        self.noLimit, self.noShow, self.noTabBar, self.snaps, self.dropPresses = False, False, False, 0, 0
        self.banner_until = 0.0
        la = self.la = Avatar()
        la.style = types.SimpleNamespace(tutorial=4)         # PiratesGlobals.TUT_GOT_CUTLASS = 4: the tutorial is done
        la.hp, la.maxHp, la.doId, la.name, la.pos = hp, 1000, 100000999, 'Test Pirate', [0.0, 0.0, 0.0]
        la.jailCellIndex, la.mojo = 100, 100
        la.isWeaponDrawn, la.currentWeaponId = False, None
        la.getGameState = lambda: self.gs
        la.getInventory = lambda: Inv(self)
        la.getLevel = lambda: 1
        la.skillDiary = Diary(self)
        la.getPos = lambda R=None: tuple(la.pos)
        self.page = Page(self)
        la.guiMgr = types.SimpleNamespace(skillPage=self.page, pageOpen=lambda p: self.pageIsOpen,
                                          levelUpIval=types.SimpleNamespace(isPlaying=lambda: CLK.t < self.banner_until))
        la.toggleWeapon = self.toggleWeapon
        builtins.messenger = Msg(self)
        self.H = types.SimpleNamespace(la=la, cr=types.SimpleNamespace(doId2do=self.foes), render='R',
                                       ev=lambda name, **kw: self.events.append((name, kw)), area=lambda: self.areaT,
                                       P=lambda a: [round(v, 1) for v in a.pos], walk_to=self.walk_to,
                                       walk_poll=self.walk_poll, walk_cancel=self.walk_cancel)

    def toggleWeapon(self, wid):
        self.togglesW.append(wid)
        if self.ignoreToggles > 0:
            self.ignoreToggles -= 1
            return
        la = self.la
        if la.isWeaponDrawn and la.currentWeaponId == wid:
            la.isWeaponDrawn, self.gs = False, 'LandRoam'
        else:
            la.isWeaponDrawn, la.currentWeaponId, self.gs = True, wid, 'Battle'

    def names(self):
        return [e[0] for e in self.events]

    def count(self, name):
        return self.names().count(name)

    def evs(self, name):
        return [e[1] for e in self.events if e[0] == name]

    def add(self, doId, x, y, lvl=1, hp=100):
        self.foes[doId] = Foe(self, doId, x, y, lvl, hp)
        return self.foes[doId]

    def walk_to(self, pos, ref=None, arrive=1.0, timeout=20.0, face=True, tag=''):
        return True
        yield

    def walk_poll(self, target, ref=None, arrive=3.5, face=True, tag=''):
        pos = target.getPos() if hasattr(target, 'getPos') else target
        n = math.hypot(pos[0] - self.la.pos[0], pos[1] - self.la.pos[1])
        if n <= arrive:
            return True
        k = min(1.0, 2.0 / n)
        self.la.pos[0] += (pos[0] - self.la.pos[0]) * k
        self.la.pos[1] += (pos[1] - self.la.pos[1]) * k
        return False

    def walk_cancel(self):
        self.cancels += 1


class FakeFighter:
    """Fighter's contract: tray / tries / hits / skills / down / foe; step() every beat."""
    w = None

    def __init__(self, H, foe, safe):
        self.foe, self.hits, self.skills, self.refused, self.H = foe, 0, 0, 0, H
        self.tries, self.down, self.beats = [], False, 0
        self.tray = types.SimpleNamespace(triggerSkillTraySkill=self.trigger)

    def trigger(self, sid):
        w, la = FakeFighter.w, FakeFighter.w.la
        w.trigs.append(sid)
        ok = (not w.trayRefuse) and la.isWeaponDrawn and WID2KIND.get(la.currentWeaponId) in ('Dagger', 'Doll', 'Wand') \
            and w.rechargeUntil.get(sid, 0.0) <= CLK.t
        self.tries.append((sid, 0, 1 if ok else 0))
        if ok:
            self.foe.hp -= 40
            w.rechargeUntil[sid] = CLK.t + 6.0

    def step(self):
        w, la, foe = FakeFighter.w, FakeFighter.w.la, self.foe
        if foe.hp <= 0 or foe.doId not in w.foes:
            if foe.doId in w.foes:
                w.foes.pop(foe.doId)
                w.gold += 12
            return 'kill' if self.hits else 'lost'
        if not la.isWeaponDrawn:
            la.toggleWeapon(IT.CutlassWeaponL1)           # Fighter.drawWeapon: the cutlass when nothing is in hand
        d = math.hypot(foe.pos[0] - la.pos[0], foe.pos[1] - la.pos[1])
        if d > 3.5:
            w.walk_poll(foe, arrive=3.5)
            return 'walk'
        self.beats += 1
        if WID2KIND.get(la.currentWeaponId) in w.noHit:
            return 'lost' if self.beats >= 6 else 'fight'
        foe.hp -= 50
        self.hits += 1
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
        w.la.hp = min(w.la.maxHp, w.la.hp + 300)
        return True

    def close(self):
        FakeFighter.w.closed += 1


def fakeModules(w):
    st = types.ModuleType('s_story')
    st.hereArea = lambda H: H.area()[1]
    st.questSpots = lambda: {'objs': {}, 'exits': {}}
    st.areaObj = lambda H, uid: None
    st._render_pt = lambda H, target, ref=None: tuple(target)
    cw = types.ModuleType('s_cavewalk')
    sys.modules['s_story'], sys.modules['s_cavewalk'] = st, cw


def drive(gen, limit=60000):
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
    for f in FakeFighter.w.foes.values()]


def world(**kw):
    w = World(**kw)
    FakeFighter.w = w
    fakeModules(w)
    return w


def sid(name):
    return getattr(IT, name)


def mk(name, **kw):
    return {sid(name): v for name, v in kw.items()}


# ---- 1. pure helpers
ids = {n: sid(n) for k in land.KINDS for n in land.SKILL_ORDER[k]}
q = {n: 1 for n in ids}
check('pickSkill: the first learned skill (stack 1) of the order', land.pickSkill(land.SKILL_ORDER['Cutlass'], q, ids) == 'CutlassHack')
q2 = dict(q, CutlassHack=6)
check('pickSkill: a maxed skill (6) is passed over; a combo skill needs the one before it at 2+',
      land.pickSkill(land.SKILL_ORDER['Cutlass'], q2, ids) == 'CutlassSlash'
      and land.pickSkill(('CutlassSlash',), dict(q, CutlassHack=1), ids) is None
      and land.pickSkill(('CutlassSlash',), dict(q, CutlassHack=2), ids) == 'CutlassSlash')
check('pickSkill: a skill not learned yet (stack 0) is never pressed', land.pickSkill(('DaggerCut',), dict(q, DaggerCut=0), ids) is None)
check('spendPlan: the first weapon (rotation order) with a point and a skill to take it',
      land.spendPlan({'Dagger': 1, 'Doll': 2}, q, ids) == ('Dagger', 'DaggerCut')
      and land.spendPlan({}, q, ids) is None
      and land.spendPlan({'Cutlass': 1}, {n: 6 for n in ids}, ids) is None)
qty = {'DaggerWeaponL1': 1, 'DaggerWeaponL2': 1, 'CutlassWeaponL1': 1, 'WandWeaponL3': 0}
check('ownedWeapons: the best level of each kind owned', land.ownedWeapons(qty) == {'Cutlass': 'CutlassWeaponL1', 'Dagger': 'DaggerWeaponL2'})
own = {'Cutlass': 'a', 'Dagger': 'b', 'Doll': 'c'}
check('weaponKind: round robin over the owned kinds', [land.weaponKind(own, set(), n) for n in range(4)] == ['Cutlass', 'Dagger', 'Doll', 'Cutlass'])
check('weaponKind: a bad kind is skipped; nothing owned or everything bad = the cutlass',
      [land.weaponKind(own, {'Dagger'}, n) for n in range(3)] == ['Cutlass', 'Doll', 'Cutlass']
      and land.weaponKind({}, set(), 5) == 'Cutlass' and land.weaponKind({'Doll': 'c'}, {'Doll'}, 0) == 'Cutlass')
order = [3, 2, 1]
check('pickWeaponSkill: learned (>1), recharged, affordable, not held off',
      land.pickWeaponSkill(order, {3: 1, 2: 2, 1: 3}, {}, 10, {}, {}, 0) == 2
      and land.pickWeaponSkill(order, {3: 2, 2: 2, 1: 3}, {3: 4.0}, 10, {}, {}, 0) == 2
      and land.pickWeaponSkill(order, {3: 2, 2: 2, 1: 3}, {}, 1, {3: 5, 2: 0}, {}, 0) == 2
      and land.pickWeaponSkill(order, {3: 2, 2: 2, 1: 3}, {}, 10, {}, {3: 50.0, 2: 50.0}, 0) == 1
      and land.pickWeaponSkill(order, {3: 1, 2: 1, 1: 1}, {}, 10, {}, {}, 0) is None)
check('duty order: jail, then a tonic, then a skill point (LandRoam only), then the hunt',
      land.duty({'jailed': True, 'unspent': 2, 'hpf': 1.0})[0] == 'jail'
      and land.duty({'hpf': 0.4, 'tonics': 3, 'ready': True, 'gs': 'LandRoam', 'unspent': 2, 'hunt': True})[0] == 'tonic'
      and land.duty({'hpf': 1.0, 'gs': 'LandRoam', 'unspent': 2, 'hunt': True})[0] == 'skill'
      and land.duty({'hpf': 1.0, 'gs': 'Battle', 'unspent': 2, 'hunt': True})[0] == 'hunt'
      and land.duty({'hpf': 1.0, 'gs': 'LandRoam', 'unspent': 2, 'hunt': True, 'quiet': {'skill': True}})[0] == 'hunt'
      and land.SCORE['jail'] > land.SCORE['skill'] > land.SCORE['hunt'] >= 10 and 60 <= land.SCORE['skill'] <= 99)

# ---- 2. skill points: BEFORE = the duty does nothing
base = {IT.UnspentCutlass: 2, IT.CutlassHack: 2, IT.CutlassSlash: 1, IT.CutlassCleave: 1}
w = world(stacks=base)
L = land.Land(Bot(w))
w0 = L.want()
check('the pirate with 2 unspent points asks for the skill duty (65), not the hunt (30)', w0 is not None and w0[0] == 65 and 'skill' in w0[1], w0)


def noSkill():
    return None
    yield


L.skillPoints = noSkill
r = drive(L.flow())
check('BEFORE (the page never opened): the 2 points stay unspent, nothing learned',
      w.stacks[IT.UnspentCutlass] == 2 and w.stacks[IT.CutlassHack] == 2 and w.toggles == 0, w.stacks)

# ---- 3. AFTER: spent through the page
w = world(stacks=dict(base))
L = land.Land(Bot(w))
r = drive(L.flow())
check('AFTER: both points spent: Hack 2 -> 4, unspent 2 -> 0', w.stacks[IT.CutlassHack] == 4 and w.stacks[IT.UnspentCutlass] == 0, w.stacks)
check('AFTER: result ok, spent 2, both the Hack', r == {'duty': 'skill', 'ok': True, 'spent': 2, 'skills': ['CutlassHack', 'CutlassHack']}, r)
check('AFTER: the page opened once and closed again, on the cutlass tab', w.toggles == 2 and not w.pageIsOpen
      and w.page.reps == [IT.CutlassRep, IT.CutlassRep], (w.toggles, w.pageIsOpen, w.page.reps))
check('AFTER: LAND-SKILL, 2 x LAND-SKILL-SPENT; the class\'s spentSkillPoint is back (no wrapper left)',
      w.count('LAND-SKILL') == 1 and w.count('LAND-SKILL-SPENT') == 2 and 'spentSkillPoint' not in vars(w.la), w.names())
check('AFTER: no bug, no quiet; the stacks are read again at the next want() and the pirate hunts', not w.bugs
      and 'skill' not in L.quietUntil and (L.want() or (0, ''))[1].startswith('hunt'), (w.bugs, L.want()))

# a maxed first skill: the next one of the order takes the point; two weapons: each on its own tab
w = world(stacks={IT.UnspentCutlass: 1, IT.UnspentDagger: 1, IT.CutlassHack: 6, IT.CutlassSlash: 1, IT.DaggerCut: 1})
L = land.Land(Bot(w))
r = drive(L.flow())
check('Hack maxed: the point goes to Slash (combo needs Hack at 2+); the dagger point to Cut on the dagger tab',
      r and r['ok'] and r['skills'] == ['CutlassSlash', 'DaggerCut'] and w.stacks[IT.CutlassSlash] == 2 and w.stacks[IT.DaggerCut] == 2
      and w.page.reps == [IT.CutlassRep, IT.DaggerRep], (r, w.page.reps))

# the press spends nothing: one BOT bug, the duty quiet, the page closed, nothing left wrapped
w = world(stacks=dict(base))
w.pageBroken = True
L = land.Land(Bot(w))
r = drive(L.flow())
check('broken +: ok False, ONE BOT bug land-skill-no-spend, the skill duty quiet, the page closed, no wrapper left',
      r and not r['ok'] and len(w.bugs) == 1 and w.bugs[0][1] == 'land-skill-no-spend' and w.bugs[0][2] == 'BOT'
      and 'skill' in L.quietUntil and not w.pageIsOpen and 'spentSkillPoint' not in vars(w.la) and w.count('LAND-SKILL-NOSPEND') == 1,
      (r, w.bugs, w.pageIsOpen))
check('broken +: the next want() is the hunt, not the skill duty again', (L.want() or (0, ''))[1].startswith('hunt'), L.want())

# the page does not open
w = world(stacks=dict(base))
w.pageNever = True
L = land.Land(Bot(w))
r = drive(L.flow())
check('page will not open: ok False, one BOT bug, nothing spent', r and not r['ok'] and len(w.bugs) == 1
      and w.stacks[IT.UnspentCutlass] == 2, (r, w.bugs))

# ---- 3b. the page in a state where the client's addPoint drops the press without a word (LANDPROOF1 11-22: two presses,
# stacks never moved, no answer). BEFORE (the old press-and-wait flow, run from commit 2104bcd) fails each; AFTER the flow reads
# the page's state, repairs what a click would have, and presses when the client would take it.
def scen(flags=None, mods=None, tut=None):
    w = world(stacks=dict(base))
    for k, v in (flags or {}).items():
        setattr(w, k, v)
    if mods:
        w.page.localMods.update(mods)
    if tut is not None:
        w.la.style.tutorial = tut
    L = land.Land(Bot(w))
    return w, L, drive(L.flow())


def spentTwo(w, r):
    return bool(r and r['ok'] and r['spent'] == 2 and w.stacks[IT.CutlassHack] == 4 and w.stacks[IT.UnspentCutlass] == 0
                and not w.bugs and not w.pageIsOpen and 'spentSkillPoint' not in vars(w.la))


w, L, r = scen({'snaps': 1})
check('level-up banner shuts + re-tabs the page right after the tab press: waits it out, reopens, both points spent', spentTwo(w, r)
      and [e['refusal'] for e in w.evs('LAND-SKILL-STATE')][:2] == ['closed', None], (r, w.bugs, [e['refusal'] for e in w.evs('LAND-SKILL-STATE')]))
w, L, r = scen(mods={IT.UnspentCutlass: 0})
check('a stale local count (unspent 0 kept by the page): dropped, both points spent', spentTwo(w, r) and
      any('localMods' in e['fixes'] for e in w.evs('LAND-SKILL-STATE')), (r, w.bugs, w.stacks))
w, L, r = scen({'noShow': True})
check('the page opens without show() (no tab bar, Cannon tab current): show() called, both points spent', spentTwo(w, r)
      and any('show' in e['fixes'] for e in w.evs('LAND-SKILL-STATE')), (r, w.bugs, w.stacks))
w, L, r = scen({'dropPresses': 1})
check('a press the game never answers: pressed again, both points spent, no bug', spentTwo(w, r), (r, w.bugs, w.stacks))
w, L, r = scen()
check('LAND-SKILL-STATE: one line per press with the page state and refusal None', w.count('LAND-SKILL-STATE') == 2
      and all(e['refusal'] is None and e['open'] and e['tab'] and e['rep'] == e['want'] == IT.CutlassRep for e in w.evs('LAND-SKILL-STATE')),
      w.evs('LAND-SKILL-STATE'))
for what, flags, tut, word in (('no tab bar ever', {'noTabBar': True}, None, 'no-tab-bar'), ('no stack limit', {'noLimit': True}, None, 'no-limit'),
                               ('tutorial not done', {}, 2, 'tutorial')):
    w, L, r = scen(flags, tut=tut)
    check('%s: nothing spent, ONE BOT bug land-skill-no-spend that names the cause (%s), duty quiet, page closed' % (what, word),
          r and not r['ok'] and len(w.bugs) == 1 and w.bugs[0][1] == 'land-skill-no-spend' and w.bugs[0][2] == 'BOT'
          and word in w.bugs[0][3] and 'skill' in L.quietUntil and not w.pageIsOpen and w.stacks[IT.UnspentCutlass] == 2
          and 'spentSkillPoint' not in vars(w.la), (r, w.bugs))
check('pressRefusal mirrors addPoint: closed, no tab bar, wrong tab, tutorial, no unspent, no limit, maxed, else None',
      [land.pressRefusal(x) for x in ({'open': False}, {'tab': False}, {'rep': 1, 'want': 2}, {'tutBlock': True}, {'unspent': 0},
                                      {'limit': False}, {'cur': 6}, {}, {'unspent': 1, 'cur': 5, 'rep': 3, 'want': 3})]
      == ['closed', 'no-tab-bar', 'wrong-tab', 'tutorial', 'no-unspent', 'no-limit', 'maxed', None, None])

# not on land sheathed: no skill duty (the page needs LandRoam)
w = world(stacks=dict(base))
w.gs = 'Battle'
L = land.Land(Bot(w))
check('drawn weapon (Battle): no skill duty', not (L.want() or (0, ''))[1].startswith('skill'), L.want())

# ---- 4. weapons: BEFORE = always the cutlass
own = {IT.CutlassWeaponL1: 1, IT.DaggerWeaponL1: 1, IT.DaggerWeaponL2: 1, IT.DollWeaponL1: 1, IT.DaggerAsp: 2, IT.DaggerAdder: 1}


def hunts(n, w, L):
    out = []
    for _ in range(n):
        w.add(11, 0.0, 10.0)
        L.quietUntil.clear()
        out.append(drive(L.flow()))
        CLK.t += 5
    return out


w = world(stacks=dict(own))
L = land.Land(Bot(w))
keep = land.weaponKind
land.weaponKind = lambda owned, bad, nth: 'Cutlass'
res = hunts(4, w, L)
land.weaponKind = keep
used = {WID2KIND[x] for x in w.togglesW}
check('BEFORE (the cutlass only): 4 hunts, the dagger and the doll are never drawn', used == {'Cutlass'}
      and [e['weapon'] for e in w.evs('LAND-WEAPON')] == ['Cutlass'] * 4, (used, [e['weapon'] for e in w.evs('LAND-WEAPON')]))

# ---- 5. AFTER: every owned weapon gets a hunt
w = world(stacks=dict(own))
L = land.Land(Bot(w))
res = hunts(4, w, L)
seq = [e['weapon'] for e in w.evs('LAND-WEAPON')]
check('AFTER: the 4 hunts use Cutlass, Dagger, Doll, Cutlass (round robin over the owned weapons)', seq == ['Cutlass', 'Dagger', 'Doll', 'Cutlass'], seq)
check('AFTER: every hunt killed its foe and ended no-spawn (no camps in the fake)', all(r and r['kills'] == 1 for r in res), res)
used = [WID2KIND[x] for x in w.togglesW]
check('AFTER: each weapon was drawn by its own toggle, the best level of a kind (dagger L2)', 'Dagger' in used and 'Doll' in used
      and IT.DaggerWeaponL2 in w.togglesW and IT.DaggerWeaponL1 not in w.togglesW, w.togglesW)
check('AFTER: the weapon is put away at every hunt end (not drawn, LandRoam, LAND-SHEATHE per hunt)', not w.la.isWeaponDrawn
      and w.gs == 'LandRoam' and w.count('LAND-SHEATHE') == 4, (w.la.isWeaponDrawn, w.gs, w.count('LAND-SHEATHE')))
dag = [e for e in w.evs('LAND-HUNT-END')][1]
check('AFTER: the dagger hunt fired its learned skill (Asp, not the unlearned Adder) between beats',
      IT.DaggerAsp in w.trigs and IT.DaggerAdder not in w.trigs and w.count('LAND-WEAPON-SKILL') >= 1 and dag['wskills'] >= 1,
      (w.trigs, dag))
check('AFTER: no bug, no magic word', not w.bugs and not any(n.startswith('LAND-MW') for n in w.names()), w.bugs)

# ---- 6. a weapon that lands no hit in a whole fight is left alone
w = world(stacks={IT.CutlassWeaponL1: 1, IT.DollWeaponL1: 1})
w.noHit = {'Doll'}
L = land.Land(Bot(w))
res = hunts(3, w, L)
seq = [e['weapon'] for e in w.evs('LAND-WEAPON')]
check('no-hit doll: hunt 2 marks it bad (LAND-WEAPON-BAD), falls back to the cutlass and still kills; hunt 3 skips it',
      L.bad == {'Doll'} and w.count('LAND-WEAPON-BAD') == 1 and res[1] and res[1]['kills'] == 1 and seq == ['Cutlass', 'Doll', 'Cutlass'],
      (L.bad, seq, res))
check('no-hit doll: hunt 2 ended with the cutlass in hand, then put away', w.count('LAND-SHEATHE') == 3 and not w.la.isWeaponDrawn, w.count('LAND-SHEATHE'))

# ---- 7. a weapon that will not draw is left alone (DRAW-RETRY once), the cutlass takes over
w = world(stacks={IT.CutlassWeaponL1: 1, IT.DaggerWeaponL1: 1})
L = land.Land(Bot(w))
res = hunts(1, w, L)                       # hunt 1 = cutlass: draws fine
w.ignoreToggles = 2                        # the dagger's draw (and its retry) is ignored by the game
res += hunts(1, w, L)
check('dagger will not draw: DRAW-RETRY, LAND-WEAPON-BAD (would not draw), the cutlass fights instead and kills',
      w.count('LAND-DRAW-RETRY') == 1 and L.bad == {'Dagger'} and res[1] and res[1]['kills'] == 1
      and any('would not draw' in e['why'] for e in w.evs('LAND-WEAPON-BAD')), (w.names(), L.bad, res))

# ---- 8. the tray refuses the weapon skill: said once, held off 20 s (not asked every beat)
w = world(stacks={IT.DaggerWeaponL1: 1, IT.DaggerAsp: 2})
w.trayRefuse = True
L = land.Land(Bot(w))
res = hunts(1, w, L)
check('refused skill: LAND-WEAPON-SKILL-REFUSED once, asked once inside the 20 s hold-off, the fight still won by clicks',
      w.count('LAND-WEAPON-SKILL-REFUSED') == 1 and w.trigs.count(IT.DaggerAsp) == 1 and res[0] and res[0]['kills'] == 1, (w.trigs, res))

# ---- 9. cut() puts a drawn weapon away; nothing to do when it is not drawn or the pirate is down
w = world()
L = land.Land(Bot(w))
w.la.toggleWeapon(IT.DaggerWeaponL1)
g = L.cut('limit')
check('cut() with a drawn weapon returns a cleanup generator that puts it away and reaches LandRoam',
      g is not None and (drive(g) or True) and not w.la.isWeaponDrawn and w.gs == 'LandRoam' and w.count('LAND-SHEATHE') == 1, w.names())
w = world()
L = land.Land(Bot(w))
check('cut() with nothing drawn -> None', L.cut('safety') is None)
w = world(hp=0)
w.la.toggleWeapon(IT.DaggerWeaponL1)
w.gs = 'Dying'
L = land.Land(Bot(w))
check('cut() on a down pirate -> None (the game handles the state)', L.cut('down') is None)
w = world()
w.pageIsOpen = True
L = land.Land(Bot(w))
L.cut('limit')
check('cut() closes a skill page the flow left open', not w.pageIsOpen and w.toggles == 1, (w.pageIsOpen, w.toggles))

# ---- 10. tonics when low (row 46): hurt with none left says so once per 5 minutes
w = world(hp=550, tonics=0)
L = land.Land(Bot(w))
r = drive(land.strict(L.hunt(), L.PH))
check('hurt (55%) with no tonic: ONE LAND-TONIC-LOW (hp, frac, area) in the hunt', w.count('LAND-TONIC-LOW') == 1
      and w.evs('LAND-TONIC-LOW')[0]['frac'] == 0.55, (w.names(), w.evs('LAND-TONIC-LOW')))
L.tonicLow(0.5)
check('... not again inside 300 s', w.count('LAND-TONIC-LOW') == 1)
CLK.t += 301
L.tonicLow(0.5)
check('... and again after 300 s', w.count('LAND-TONIC-LOW') == 2)
w = world(hp=550, tonics=3)
L = land.Land(Bot(w))
w.tonics = 3
drive(land.strict(L.hunt(), L.PH))
check('hurt with tonics left: no LAND-TONIC-LOW, a tonic is drunk instead', w.count('LAND-TONIC-LOW') == 0 and w.count('LAND-TONIC') >= 1
      and w.tonics < 3, (w.names(), w.tonics))

print('ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails))
sys.exit(1 if fails else 0)
