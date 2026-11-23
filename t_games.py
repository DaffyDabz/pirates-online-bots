"""Offline test of pbot/skills/games.py (games lane, Round 2, 11-22): the player bot plays the proven s_*.py game scripts
as a player. Checked with fake scripts and a fake H on a fake clock:
- a script's PASS / FAIL become GAME-PASS / GAME-FAIL with the game's name; the run's own verdict stays the brain's;
- a magic word (a gold top-up, areaTeleport) is refused: the game ends as a BOT result, the module's flags come back;
- a strict ('until', ...) wait reaches the walker as ('upto', ...), and a timeout is logged as game-wait;
- a game over its time limit is cut and filed as a stuck BOT bug; a FAIL that names a missing server object is GAME;
- the potion table's "whole-run limit" is a kid giving up (no bug); the pirate is walked out of a table after a FAIL;
- money sense: low on gold the earning games come first, rich the spending ones, never below what a table needs;
  a game rests after it is played, and two failures in a row switch it off for the session;
- Host's and the boys' pirates are refused.
Run: python t_games.py <pirates-harness dir>"""
import builtins, os, sys, types

D = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(D, 'pbot', 'skills'))


class Clock:
    t = 1000.0

    @classmethod
    def time(cls):
        return cls.t


class LA:
    def __init__(self, doId=100009999, gold=500):
        self.doId, self.name, self.gold, self.gs = doId, 'Tester', gold, 'LandRoam'

    def getGameState(self):
        return self.gs

    def getInventory(self):
        la = self
        return types.SimpleNamespace(getGoldInPocket=lambda: la.gold)


class H:
    def __init__(self, island='1150922126.8dzlu', **kw):
        self.la, self.island, self.events, self.words = LA(**kw), island, [], []
        self.cr = types.SimpleNamespace(doId2do={})

    def ev(self, name, /, **kw):
        self.events.append((name, kw))

    def mw(self, word):          # the real H would send it: the wrapper must never get here
        self.words.append(word)

    def area(self):
        return 'Port Royal'

    def names(self):
        return [e[0] for e in self.events]


def mod(name, **kw):
    m = types.ModuleType(name)
    m.__dict__.update(kw)
    sys.modules[name] = m
    return m


def on_island(H, step, isl):
    TRIPS.append(isl)
    yield 1
    H.island = isl
    return True


TRIPS = []
lanes = mod('s_lanes', islandOf=lambda H: H.island, onIsland=on_island)
ALL = []          # every item any game handed the walker


def drive(gen, H):
    """The walker, on the fake clock: numbers sleep, ('upto', fn, secs, what) polls; returns the generator's value.
    Records every item it saw."""
    seen = []
    send = None
    while True:
        try:
            item = gen.send(send)
        except StopIteration as e:
            return e.value, seen
        seen.append(item)
        ALL.append(item)
        if isinstance(item, (int, float)):
            Clock.t += item
        elif isinstance(item, tuple) and item[0] == 'upto':
            end = Clock.t + item[2]
            while Clock.t < end and not item[1]():
                Clock.t += 0.25
        elif isinstance(item, tuple) and item[0] == 'until':
            raise AssertionError('a strict until reached the walker: %r' % (item,))


# --- fake game scripts -------------------------------------------------------------------------------------------
def fish_run(H):
    H.la.gs = 'Fishing'
    yield ('until', lambda: False, 5, 'a bite')          # strict wait that times out
    yield 2
    H.ev('FISH-PLACED', at=(1, 2))
    H.la.gold += 35
    H.la.gs = 'LandRoam'
    H.ev('PASS', what='caught a fish, +35 gold')


fishing = mod('s_fishing', FROM='x', ONCE={'a': 1}, SEEN={}, run=fish_run, shot=lambda *a, **k: 'pic')


def shop_run(H):
    if shop.WANT_GOLD:
        H.mw('money 5000')
    yield 1
    H.mw('areaTeleport 1142018473.22dxschafe')           # a script that still asks for one
    H.ev('PASS', what='bought')


shop = mod('s_shop', AT='gypsy', ITEM=0, RESERVE=0, WANT_GOLD=True, run=shop_run)


def bench_run(H):
    yield 1
    H.ev('FAIL', stage='benches', why='no DistributedRepairBench came into the client (server patch 0440 live?)')


bench = mod('s_benchpass', FROM='x', ONCE={}, run=bench_run, shot=lambda *a, **k: 'pic')


def potion_run(H):
    H.la.gs = 'PotionCrafting'
    assert potion.PLAY > 10 ** 8 and potion.injectMissing(H, None) == [], 'potion pieces still injected'
    yield 1
    H.ev('FAIL', stage='time', why='whole-run limit 800 s hit')         # returns still at the table


class Table:
    def __init__(self, la):
        self.la = la

    def getDistance(self, other):
        return 4

    def requestExit(self):
        self.la.gs = 'LandRoam'


DistributedPotionCraftingTable = type('DistributedPotionCraftingTable', (Table,), {})
potion = mod('s_potionpass', FROM='x', ONCE={}, PLAY=170, injectMissing=None, run=potion_run, shot=lambda *a, **k: '')


def cannon_run(H):
    H.la.gs = 'Cannon'
    try:
        while True:                                      # never ends: the skill must cut it
            yield 30
    finally:
        cannon.closed += 1                               # the script's own finally ran


cannon = mod('s_cannonpass', FROM='x', ONCE={'c': 1}, run=cannon_run, shot=lambda *a, **k: '', closed=0)


def sell_run(H):
    assert sell.AT == '', 'sell: the shop not left to the script'
    H.la.gs = 'NPCInteract'
    yield ('until', lambda: False, 15, 'sale answer')
    H.la.gs = 'LandRoam'
    if sell.MODE == 'pass':
        H.la.gold += 6
        H.ev('PASS', what='sold one spare pack back to a shop', price=6)
    elif sell.MODE == 'none':
        H.ev('FAIL', why='nothing to sell (no spare pack of anything gypsy buys back)')
    else:
        H.ev('FAIL', why='the server did not buy it back (makeSaleResponse 0)', item=3001)


sell = mod('s_sell', AT='gypsy', MODE='pass', run=sell_run)


def music(H):
    yield 1
    return True, 'the musician played'


mech = mod('s_mech', btn_music=music)
def pages_shop(H, name, buy):
    if pages.H_gold() < pages.BUY_GOLD:
        H.mw('gold %d' % pages.BUY_GOLD)
    yield 1
    return True, 'bought a hat at the %s' % name


pages = mod('s_pages', BUY_GOLD=5000, GIVE=True, STORE_ORDER=('tailor', 'jeweler'), shop=pages_shop,
            H_gold=lambda: 400, coll=None, shot=lambda *a, **k: '')


def tablefind(H):
    yield 1
    H.ev('FAIL', why='the Lookout is locked (launcher.canLeaveFirstIsland() is False)')


acts = mod('s_activities', TABLE_KIND='blackjack', tablefind=tablefind)
parlor = mod('s_parlor', KIND='Blackjack', FROM='x', WANT_GOLD=True, RESERVE=0, run=None)
stud = mod('s_stud', FROM='x', GOLD='1', HANDS=4, run=None)

import games
games.time = Clock
esc = []
builtins.messenger = types.SimpleNamespace(send=lambda e: esc.append(e))


class Bot:
    def __init__(self, h):
        self.H, self.bugs = h, []

    def bug(self, kind, key, tag, what, tb=''):
        self.bugs.append((kind, tag, key, what))


# 1. a passing game: renamed verdict, until -> upto, game-wait logged, module flags back, the setPos fallback counted
h = H()
r, seen = drive(games.play(h, games.BY['fishing']), h)
assert r['res'] == 'pass' and r['gold1'] - r['gold0'] == 35, r
assert 'GAME-PASS' in h.names() and 'PASS' not in h.names(), h.names()
assert ('upto',) == seen[0][:1] and any(e[0] == 'game-wait' for e in h.events), seen
assert r['placed'] == 1, r
assert fishing.ONCE == {'a': 1} and fishing.shot() == 'pic', 'fishing module not restored'

# 2. a magic word: refused, BOT, flags restored (WANT_GOLD was forced off for the run)
h = H()
b = Bot(h)
sk = games.Games(b)
r, _ = drive(sk.flow('shop'), h)
assert h.words == [], 'a magic word reached the game: %r' % h.words
assert r['res'] == 'bot' and 'magic word' in r['why'] and r['blocked'].startswith('areaTeleport'), r
assert 'GAME-MW-BLOCKED' in h.names() and shop.WANT_GOLD is True, 'shop module not restored'
assert b.bugs and b.bugs[0][1] == 'BOT', b.bugs

# 3. a missing server object is a GAME bug
r, _ = drive(sk.flow('bench'), h)
assert r['res'] == 'game' and b.bugs[-1][1] == 'GAME', (r, b.bugs)

# 4. potion: no injected pieces; out of time = soft (no bug); the pirate is taken out of the table
h = H()
b = Bot(h)
sk = games.Games(b)
t = DistributedPotionCraftingTable(h.la)
h.cr.doId2do[1] = t
r, _ = drive(sk.flow('potion'), h)
assert r['res'] == 'soft' and not b.bugs, (r, b.bugs)
assert esc == ['escape'] and h.la.gs == 'LandRoam' and 'GAME-LEAVE' in h.names(), (esc, h.la.gs)
assert potion.PLAY == 170 and potion.injectMissing is None, 'potion module not restored'

# 5. a game that never ends is cut at its time limit, a stuck BOT bug
t0 = Clock.t
r, _ = drive(sk.flow('cannon'), h)
assert r['res'] == 'bot' and 'time limit' in r['why'], r
assert Clock.t - t0 <= games.BY['cannon'].secs + games.SLACK + 31 + 45, Clock.t - t0   # + the walk out (2 x 20 s)
assert b.bugs[-1][0] == 'stuck' and b.bugs[-1][1] == 'BOT', b.bugs

# 6. the musician's (ok, why) is a verdict
r, _ = drive(sk.flow('music'), h)
assert r['res'] == 'pass' and r['why'] == 'the musician played', r

# 6b. clothes stores: BUY_GOLD off for the run (no magic word), a returned (ok, why) is the verdict; restored after
r, _ = drive(sk.flow('clothes'), h)
assert r['res'] == 'pass' and 'bought a hat' in r['why'] and h.words == [], (r, h.words)
assert pages.BUY_GOLD == 5000, 'pages module not restored'
# 6c. the Lookout locked on a new pirate is not a bug; it is open on every island
n0 = len(b.bugs)
r, _ = drive(sk.flow('tablefind'), h)
assert r['res'] == 'soft' and len(b.bugs) == n0, r
h2 = H(island='tortuga', gold=50)
assert games.Games(Bot(h2)).want()[1].split(':')[0] in ('tablefind', 'collections'), games.Games(Bot(h2)).want()

# 7. money sense
mem = {}
low = games.rank(120, games.PR, 0, mem, rnd=lambda: 0.5)
assert games.BY[low[0][1]].kind == 'earn', low
assert not any(games.BY[n].kind in ('spend', 'gamble') for _, n, _ in low), 'spends with 120 gold: %r' % low
rich = games.rank(5000, games.PR, 0, mem, rnd=lambda: 0.5)
assert games.BY[rich[0][1]].kind in ('spend', 'gamble'), rich
mid = [n for _, n, _ in games.rank(400, games.PR, 0, mem, rnd=lambda: 0.5)]
assert 'stud' not in mid and 'holdem' in mid and 'blackjack' in mid, mid       # 7 Stud wants 500 + the 150 kept
assert 'holdem' not in [n for _, n, _ in games.rank(300, games.PR, 0, mem, rnd=lambda: 0.5)]
away = dict((n, s) for s, n, _ in games.rank(120, 'tortuga', 0, mem, rnd=lambda: 0.5))
here = dict((n, s) for s, n, _ in low)
assert away['fishing'] < here['fishing'], (away, here)
mem = {}
games.note(mem, 'fishing', 'pass', 0)
assert 'fishing' not in [n for _, n, _ in games.rank(120, games.PR, 10, mem)], 'no rest after a game'
assert 'fishing' in [n for _, n, _ in games.rank(120, games.PR, games.REST + 1, mem)]
games.note(mem, 'bench', 'bot', 0)
games.note(mem, 'bench', 'pass', 0)
games.note(mem, 'bench', 'game', 0)
assert 'bench' not in mem.get('off', ()), 'a pass between failures must reset the count'
games.note(mem, 'bench', 'bot', 0)
assert 'bench' in mem['off'], mem

# 8. the setups turn every gold flag off and point at Port Royal
assert games._stud(stud)['GOLD'] is False and games._stud(stud)['HANDS'] == 1
assert games._blackjack(parlor)['WANT_GOLD'] is False and games._holdem(parlor)['KIND'] == 'Holdem'
assert games._shop(shop)['WANT_GOLD'] is False and games._shop(shop)['AT'] in ('gypsy', 'gunsmith', 'bartender')

# 9. Host's and the boys' pirates are refused
for doId in (100000170, 100000656, 100000665):
    h = H(doId=doId)
    drive(games.run(h), h)
    assert h.events[-1][0] == 'FAIL' and 'refusing' in h.events[-1][1]['why'], h.events

# 10. run(H): GAMES=fishing,music passes with no BOT bug
os.environ['GAMES'] = 'fishing,music'
h = H()
drive(games.run(h), h)
assert h.events[-1][0] == 'PASS', h.events[-1]
assert TRIPS == [], 'travelled with no PBOT_HOME: %r' % TRIPS

# --- 11-22 later: pbot/skills/INTERFACE.md and row 49 (selling). Each check reports on its own (fail-before lists all).
FAILS = []


def check(name):
    def wrap(f):
        try:
            f()
        except Exception as e:
            FAILS.append('%s: %s: %s' % (name, type(e).__name__, str(e)[:200]))
        return f
    return wrap


@check('11 sell: a sale passes, the shop is left to the script, the flag comes back')
def _():
    h = H(gold=100)
    b = Bot(h)
    sell.MODE = 'pass'
    r, _ = drive(games.Games(b).flow('sell'), h)
    assert r['res'] == 'pass' and r['gold1'] - r['gold0'] == 6 and not b.bugs, (r, b.bugs)
    assert sell.AT == 'gypsy', 'sell module not restored'
    assert games.BY['sell'].rows == '49' and games.BY['sell'].kind == 'earn'


@check('11b sell: nothing to sell is a kid with nothing spare (no bug)')
def _():
    h = H(gold=100)
    b = Bot(h)
    sell.MODE = 'none'
    r, _ = drive(games.Games(b).flow('sell'), h)
    assert r['res'] == 'soft' and not b.bugs, (r, b.bugs)


@check('11c sell: the server not buying back is a GAME bug with a games- key')
def _():
    h = H(gold=100)
    b = Bot(h)
    sell.MODE = 'nobuy'
    r, _ = drive(games.Games(b).flow('sell'), h)
    assert r['res'] == 'game' and b.bugs and b.bugs[-1][1] == 'GAME', (r, b.bugs)
    assert b.bugs[-1][2].startswith('games-sell-the-server-did-not-buy'), b.bugs[-1][2]


@check('12 sell: pickSale keeps one pack, takes the best price, nothing when under two packs')
def _():
    import importlib.util
    mod('s_story')
    sp = importlib.util.spec_from_file_location('s_sell_real', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                            's_sell.py'))
    real = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(real)
    assert real.pickSale([]) is None
    assert real.pickSale([(1, 9, 5, 10)]) is None, 'sold below one kept pack'          # 9 < 2 packs of 5
    assert real.pickSale([(1, 10, 5, 10)]) == (1, 5, 25)
    assert real.pickSale([(1, 10, 5, 10), (2, 40, 20, 4), (3, 2, 1, 0)]) == (2, 20, 40)   # cost 0: never
    assert real.pickSale([(4, 3, 1, 1)]) is None, 'a sale paying 0 gold'


@check('13 interface: limit 1800, not crewOk, want in the FREE PLAY band 10-39')
def _():
    assert games.Games.limit == 1800 and games.Games.crewOk is False, (getattr(games.Games, 'limit', None),
                                                                       getattr(games.Games, 'crewOk', None))
    for gold in (50, 400, 5000):
        w = games.Games(Bot(H(gold=gold))).want()
        assert w and 10 <= w[0] <= 39, (gold, w)


@check('14 interface: cut() mid-game puts the flags back, rests the game and walks him out')
def _():
    h = H()
    h.cr.doId2do[1] = DistributedPotionCraftingTable(h.la)
    sk = games.Games(Bot(h))
    c0 = cannon.closed
    f = sk.flow('cannon')
    for _ in range(3):
        next(f)
    assert cannon.ONCE == {} and h.la.gs == 'Cannon', (cannon.ONCE, h.la.gs)
    f.close()                                          # what the brain does first
    assert cannon.ONCE == {'c': 1}, 'cannon module not restored after close'
    assert cannon.closed == c0 + 1, 'the script itself was not closed'
    c = sk.cut('crew')
    assert c is not None, 'cut() gave no way out'
    drive(c, h)
    assert h.la.gs == 'LandRoam' and 'GAME-CUT' in h.names(), (h.la.gs, h.names()[-4:])
    assert sk.mem['rest'].get('cannon', 0) > Clock.t and not sk.mem['fails'].get('cannon'), sk.mem
    assert sk.cut('limit') is None, 'a second cut with no game on'


@check('15 interface: bug keys are games- slugs (no spaces)')
def _():
    h = H()
    b = Bot(h)
    drive(games.Games(b).flow('shop'), h)
    k = b.bugs[-1][2]
    assert k.startswith('games-shop-') and ' ' not in k and len(k) <= 64, k


@check('16 interface: no wait handed to the walker is over 2 s (a cut lands)')
def _():
    h = H()
    drive(games.Games(Bot(h)).flow('fishing'), h)
    big = [i for i in ALL if (isinstance(i, (int, float)) and i > 2) or
           (isinstance(i, tuple) and i[0] == 'upto' and i[2] > 2)]
    assert not big, 'waits over 2 s: %r' % big[:5]


@check('17 -Script: run(H) goes to PBOT_HOME first through s_lanes.onIsland (the SETUP teleport)')
def _():
    os.environ['GAMES'] = 'music'
    os.environ['PBOT_HOME'] = games.PR
    try:
        h = H(island='1156207188.95dxschafe')
        drive(games.run(h), h)
    finally:
        os.environ.pop('PBOT_HOME')
    assert TRIPS == [games.PR] and h.island == games.PR, TRIPS
    assert any(e[0] == 'HOME' and e[1].get('ok') for e in h.events), h.names()
    assert h.events[-1][0] == 'PASS', h.events[-1]


@check('18 Port Royal is the id the scripts use (s_story.PR), or every game there is "on another island"')
def _():
    import re
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 's_story.py'), encoding='utf-8').read()
    real = re.search(r"^PR = '([^']+)'", src, re.M).group(1)
    assert games.PR == real, (games.PR, real)


if FAILS:
    print('FAILED %d:' % len(FAILS))
    for f in FAILS:
        print(' ', f)
    sys.exit(1)
print('games ok')
