"""pbot skill GAMES (games lane, Round 2, 11-22): the player bot's mini-games and its money sense.

The bot plays the games the s_*.py step scripts already proved in the live game, the way a kid would: fishing, the
cannon defense, the repair benches and the potion table earn gold; the card tables, the shops and the musician spend it.
Each game runs its own proven script, wrapped so it plays by the player-bot rules:

- never a magic word: the wrapped H refuses every H.mw (the gold top-ups, areaTeleport, giveQuest...); a script that
  asks for one ends that game at once, as a BOT bug (the catalogue below turns every gold flag off first);
- no client-side cheats: the potion table's injected pieces are off (real drops only, it may run out of time: that is
  a kid giving up, not a bug), no pictures (the window is off);
- the bot starts a game only on the island it is standing on (travel belongs to TRAVEL, never areaTeleport);
- one verdict per run belongs to the brain: the script's PASS / FAIL lines become GAME-PASS / GAME-FAIL with the game's
  name, its STALL lines become game-stall, and a strict ('until', ...) wait becomes an ('upto', ...) one (a timeout is
  logged here, game-wait, and the script's own check after it decides).

Money sense (rank): low on gold (< LOW) the earning games come first, rich (> RICH) the spending ones; it never spends
below KEEP; a game just played rests REST seconds; a game that failed twice in a row is off for the rest of the session.

Rows (PLAYERBOTS-activities.md): 29c/69 cannon, 47 shop, 48 clothes stores, 50 musician, 51 blackjack, 52 Hold'em,
53 7 Stud, 54 Lookout table search, 58 the collections page, 65 fishing, 66 repair bench, 67/68 potion (the game itself
gives the brew's buff, 0445), 49 selling a spare pack back to a shop (s_sell: the store window sends no sell list, so
the bot sends the store's own 'makeSale' with one; the server buys back at half price). Not here: 56 digging and 57
searching crates (only when a quest asks: a dig needs a treasure map quest, the crates a quest item; the quest skill
drives them through s_story.container / s_kiddig).

Use (pbot/skills/INTERFACE.md): Games(bot).want() -> (score 10-39, the FREE PLAY band, why) or None;
Games(bot).flow() is the generator the brain drives (walker items, no wait over CHUNK s, returns a result dict) inside
`limit`; cut(why) -> the generator that walks him out of the game. As a step script (PROOF_SCRIPT = this file, through
run_bot.ps1 -Script): run(H) goes to PBOT_HOME (the runner's -Island) first, then plays GAMES (a comma list, default
the money sense) for GAMES_SECS and passes when GAMES_WANT games passed with no BOT bug."""
import builtins, os, random, re, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PBOT = os.path.dirname(HERE)
HARNESS = os.path.dirname(PBOT)
for _p in (PBOT, HARNESS):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault('PROOF_SCRIPT', os.path.join(PBOT, 'b_brain.py'))   # the s_*.py scripts put its folder on sys.path

PR = '1150922126.8dzlu'               # Port Royal (s_story.PR; 1142018473.22dxschafe is Isla de Padres)
LOW = int(os.environ.get('GAMES_LOW', '300'))        # below this the bot earns first
RICH = int(os.environ.get('GAMES_RICH', '2000'))     # above this it likes to spend
KEEP = int(os.environ.get('GAMES_KEEP', '150'))      # gold it never spends (a kid keeps some)
REST = float(os.environ.get('GAMES_REST', '1200'))   # s before the same game again
OFF_AFTER = 2                                        # failures in a row before a game is off for the session
SLACK = 90.0                                         # s over a game's own time limit before the skill cuts it
CHUNK = 2.0                                          # s: the longest wait handed to the brain, so a cut lands


class Blocked(Exception):
    """A wrapped script asked for a magic word."""


class Game:
    """island None = anywhere. call(m, H) -> the script's generator (default m.run(H)); ret: it returns (ok, why)
    instead of writing a verdict line."""

    def __init__(self, name, mod, kind, base, need, secs, island=PR, setup=None, call=None, ret=False, gamefail=(),
                 soft=(), rows=''):
        self.name, self.mod, self.kind, self.base, self.need, self.secs = name, mod, kind, base, need, secs
        self.island, self.setup, self.call, self.ret, self.gamefail, self.soft, self.rows = (island, setup, call, ret,
                                                                                            gamefail, soft, rows)


def _noShots(m):
    return {'shot': lambda *a, **k: ''} if hasattr(m, 'shot') else {}


def _fishing(m):
    return dict(_noShots(m), FROM=PR, ONCE={}, SEEN={'n': -1, 'max': 0, 'ids': set()})


def _potion(m):
    # real drops only: PLAY never reached, and the injection is a no-op if the board fills (the script then plays on)
    return dict(_noShots(m), FROM=PR, ONCE={}, PLAY=10 ** 9, injectMissing=lambda H, g: [])


def _bench(m):
    return dict(_noShots(m), FROM=PR, ONCE={})


def _cannon(m):
    return dict(_noShots(m), FROM=PR, ONCE={})


def _blackjack(m):
    return dict(KIND='Blackjack', FROM=PR, WANT_GOLD=False, RESERVE=KEEP)


def _holdem(m):
    return dict(KIND='Holdem', FROM=PR, WANT_GOLD=False, RESERVE=KEEP)


def _stud(m):
    return dict(FROM=PR, GOLD=False, HANDS=1)


def _shop(m):
    return dict(AT=random.choice(('gypsy', 'gunsmith', 'bartender')), ITEM=0, RESERVE=KEEP, WANT_GOLD=False)


def _music(m):
    return _noShots(m)


def _clothes(m):
    return dict(_noShots(m), BUY_GOLD=0)          # BUY_GOLD: a pirate with less is given that much (a magic word)


def _coll(m):
    return dict(_noShots(m), GIVE=False)          # GIVE: the missing sets are given (a magic word)


def _sell(m):
    return dict(AT=os.environ.get('GAMES_SELL_AT', ''))   # '' = the shop that pays most for a spare pack


def _tablefind(m):
    return dict(TABLE_KIND=random.choice(('blackjack', 'poker')))


GAMES = [
    #     name        script          kind     base need secs  setup      entry
    Game('fishing', 's_fishing', 'earn', 0.60, 0, 480, setup=_fishing, rows='65',
         gamefail=('no DistributedFishingSpot',)),
    Game('cannon', 's_cannonpass', 'earn', 0.50, 0, 1500, setup=_cannon, rows='29c/69',
         gamefail=('no DistributedDefendEntrance', 'no DistributedDefendWorld')),
    Game('bench', 's_benchpass', 'earn', 0.45, 0, 420, setup=_bench, rows='66',
         gamefail=('no DistributedRepairBench',)),
    Game('potion', 's_potionpass', 'earn', 0.40, 0, 800, setup=_potion, rows='67/68',
         gamefail=('no DistributedPotionCraftingTable',), soft=('whole-run limit', 'no free column pair')),
    Game('blackjack', 's_parlor', 'gamble', 0.35, 4, 540, setup=_blackjack, rows='51'),
    Game('holdem', 's_parlor', 'gamble', 0.20, 200, 540, setup=_holdem, rows='52'),
    Game('stud', 's_stud', 'gamble', 0.25, 500, 780, setup=_stud, rows='53'),
    Game('shop', 's_shop', 'spend', 0.30, 60, 600, setup=_shop, rows='47',
         gamefail=('the server did not sell',), soft=('nothing on the shelf he can buy',)),
    Game('sell', 's_sell', 'earn', 0.30, 0, 420, setup=_sell, rows='49',
         gamefail=('the server did not buy', 'paid wrong'), soft=('nothing to sell',)),
    Game('music', 's_mech', 'spend', 0.20, 105, 600, setup=_music, call=lambda m, H: m.btn_music(H), ret=True,
         rows='50'),
    Game('clothes', 's_pages', 'spend', 0.25, 200, 600, setup=_clothes, ret=True, rows='48',
         call=lambda m, H: m.shop(H, random.choice(m.STORE_ORDER), True), soft=('nothing to buy',)),
    Game('tablefind', 's_activities', 'fun', 0.15, 0, 240, island=None, setup=_tablefind, rows='54',
         call=lambda m, H: m.tablefind(H), soft=('the Lookout is locked',)),
    Game('collections', 's_pages', 'fun', 0.10, 0, 120, island=None, setup=_coll, ret=True, rows='58',
         call=lambda m, H: m.coll(H), soft=('need 2+ pictures',)),
]
BY = {g.name: g for g in GAMES}


# ------------------------------------------------------------------------------------------------ pure
def rank(gold, island, now, mem, rnd=random.random, games=GAMES):
    """Pure. The games worth starting now, best first: [(score, name, why)]. mem = {'rest': {name: t}, 'off': set(),
    'fails': {name: n}}. A game on another island scores lower and says so (the brain may travel there, never here)."""
    out = []
    for g in games:
        if g.name in mem.get('off', ()):
            continue
        if now < mem.get('rest', {}).get(g.name, 0):
            continue
        spends = g.kind in ('spend', 'gamble')
        if spends and gold < g.need + KEEP:
            continue
        s, why = g.base, []
        if g.kind == 'earn' and gold < LOW:
            s += 0.40
            why.append('low on gold (%d)' % gold)
        if spends and gold > RICH:
            s += 0.30
            why.append('rich (%d)' % gold)
        if spends and gold < LOW + g.need:
            s -= 0.25
            why.append('saving')
        if g.island is not None and island != g.island:
            s -= 0.30
            why.append('on another island')
        s += 0.15 * rnd()
        out.append((round(s, 3), g.name, ', '.join(why) or g.kind))
    out.sort(key=lambda r: -r[0])
    return out


def outcome(g, ev):
    """Pure. -> 'pass' / 'soft' (a kid gave up: no bug) / 'game' (a GAME bug) / 'bot' (a BOT bug) for the verdict
    event ('PASS' or 'FAIL', kw) of game g; None (no verdict) is a BOT bug too."""
    if ev is None:
        return 'bot'
    name, kw = ev
    if name == 'PASS':
        return 'pass'
    why = str(kw.get('why', ''))
    if any(s in why for s in g.soft):
        return 'soft'
    if any(s in why for s in g.gamefail):
        return 'game'
    return 'bot'


def note(mem, name, res, now):
    """Pure. Book a finished game into mem: rest it, count failures in a row, switch it off after OFF_AFTER."""
    mem.setdefault('rest', {})[name] = now + REST
    fails = mem.setdefault('fails', {})
    if res in ('pass', 'soft'):
        fails[name] = 0
    else:
        fails[name] = fails.get(name, 0) + 1
        if fails[name] >= OFF_AFTER:
            mem.setdefault('off', set()).add(name)
    return mem


# ------------------------------------------------------------------------------------------------ the wrapper
class PlayerH:
    """The walker's H as a player bot's script sees it: everything delegates, except the verdict lines, STALL lines and
    magic words."""

    def __init__(self, H, game):
        self._H, self._g = H, game
        self.verdict = None
        self.stalls = 0
        self.placed = 0
        self.blocked = None

    def __getattr__(self, k):
        return getattr(self._H, k)

    def ev(self, name, /, **kw):
        if name in ('PASS', 'FAIL'):
            if self.verdict is None:
                self.verdict = (name, dict(kw))
            return self._H.ev('GAME-' + name, game=self._g.name, **kw)
        if name.endswith('-PLACED'):            # a script's client-side setPos fallback (s_fishing FISH-PLACED): counted
            self.placed += 1
        if name == 'STALL':
            self.stalls += 1
            return self._H.ev('game-stall', game=self._g.name, **kw)
        return self._H.ev(name, **kw)

    def mw(self, word):
        self.blocked = str(word)
        self._H.ev('GAME-MW-BLOCKED', game=self._g.name, word=str(word).split(' ')[0])
        raise Blocked(word)


def _module(g):
    import importlib
    return importlib.import_module(g.mod)


def _apply(m, setup):
    old = {}
    for k, v in setup.items():
        old[k] = getattr(m, k, _MISSING)
        setattr(m, k, v)
    return old


def _restore(m, old):
    for k, v in old.items():
        if v is _MISSING:
            try:
                delattr(m, k)
            except AttributeError:
                pass
        else:
            setattr(m, k, v)


_MISSING = object()


def play(H, g):
    """Generator: play game g once through its proven script, as a player. Yields walker items; returns a dict
    {game, res ('pass' / 'soft' / 'game' / 'bot'), why, secs, gold0, gold1, stalls, blocked}."""
    t0 = time.time()
    PH = PlayerH(H, g)
    gold0 = _gold(H)
    H.ev('GAME-START', game=g.name, rows=g.rows, kind=g.kind, gold=gold0, area=_area(H))
    m = _module(g)
    old = _apply(m, g.setup(m) if g.setup else {})
    err = None
    end = t0 + g.secs + SLACK
    gen = None
    try:
        gen = g.call(m, PH) if g.call else m.run(PH)
        if g.ret:
            gen = _asVerdict(PH, gen)
        send = None
        while True:
            if time.time() >= end:          # >=: past `end` _small hands back nothing, so never loop on it
                gen.close()
                err = 'over its time limit (%d s)' % (g.secs + SLACK)
                break
            try:
                item = gen.send(send)
            except StopIteration:
                break
            send = None
            if isinstance(item, tuple) and item and item[0] == 'until':
                fn, secs = item[1], item[2]
                what = item[3] if len(item) > 3 else '?'
                yield from _small(('upto', fn, secs, what), end)
                if not _ok(fn):
                    H.ev('game-wait', game=g.name, what=what, secs=secs)
            else:
                yield from _small(item, end)
    except Blocked as e:
        err = 'asked for the magic word %r' % str(e).split(' ')[0]
    except Exception:
        err = 'crashed: ' + traceback.format_exc().strip().splitlines()[-1][:160]
        PH.tb = traceback.format_exc()
    finally:
        if gen is not None:
            try:
                gen.close()         # the script's own finally (a hook put back) runs now, also on a cut
            except Exception:
                pass
        _restore(m, old)
    yield from leave(H, g)
    ev = PH.verdict
    if err:
        ev = ('FAIL', {'why': err, 'stage': 'skill'})
    res = outcome(g, ev) if not err else 'bot'
    out = dict(game=g.name, res=res, why=(ev[1].get('why') or ev[1].get('what')) if ev else 'no verdict line',
               stage=ev[1].get('stage') if ev else None, secs=round(time.time() - t0), gold0=gold0, gold1=_gold(H),
               stalls=PH.stalls, placed=PH.placed, blocked=PH.blocked, tb=getattr(PH, 'tb', ''))
    H.ev('GAME-END', **{k: v for k, v in out.items() if k != 'tb'})
    return out


def _ok(fn):
    try:
        return bool(fn())
    except Exception:
        return False


def _small(item, end=float('inf')):
    """Generator: one walker item as waits of at most CHUNK s (the same wait in pieces, so a cut lands between them:
    INTERFACE.md section 4); a sleep stops early past `end`."""
    if isinstance(item, (int, float)) and not isinstance(item, bool):
        left = float(item)
        while left > CHUNK and time.time() < end:
            yield CHUNK
            left -= CHUNK
        if left > 0 and time.time() < end:
            yield min(left, CHUNK)
        return
    if isinstance(item, tuple) and len(item) >= 3 and item[0] == 'upto' and item[2] > CHUNK:
        fn, stop = item[1], time.time() + item[2]
        what = item[3] if len(item) > 3 else '?'
        while True:
            yield ('upto', fn, min(CHUNK, max(stop - time.time(), 0.25)), what)
            if _ok(fn) or time.time() >= min(stop, end):
                return
    yield item


def _asVerdict(PH, gen):
    """s_mech's buttons and s_pages' parts return (ok, why) instead of a verdict line: make it one."""
    r = yield from gen
    ok, why = r if isinstance(r, tuple) else (bool(r), str(r))
    PH.ev('PASS' if ok else 'FAIL', what=why, why=why)


def leave(H, g):
    """Generator: back to LandRoam after a game (a FAIL returns where it stood: at the table, the bench, the cards).
    The end-interact key first, as a player presses it; then the object's own requestExit."""
    la = H.la
    if _gs(la) in ('LandRoam', None):
        return
    H.ev('GAME-LEAVE', game=g.name, gs=_gs(la))
    messenger = getattr(builtins, 'messenger', None)
    if messenger is not None:
        messenger.send('escape')
    yield from _small(('upto', lambda: _gs(la) == 'LandRoam', 20, 'leave by escape'))
    if _gs(la) == 'LandRoam':
        return
    for o in list(H.cr.doId2do.values()):
        n = type(o).__name__
        if hasattr(o, 'requestExit') and any(k in n for k in ('Potion', 'RepairBench', 'FishingSpot', 'Table')):
            try:
                if o.getDistance(la) > 30:      # only the one he is at
                    continue
            except Exception:
                pass
            try:
                o.requestExit()
                H.ev('GAME-LEAVE', game=g.name, via='requestExit', obj=n)
            except Exception:
                pass
    yield from _small(('upto', lambda: _gs(la) == 'LandRoam', 20, 'leave by requestExit'))


def _gs(la):
    try:
        return la.getGameState()
    except Exception:
        return None


def _gold(H):
    try:
        inv = H.la.getInventory()
        return inv.getGoldInPocket() if inv else 0
    except Exception:
        return 0


def _area(H):
    try:
        return H.area()
    except Exception:
        return None


def _island(H):
    try:
        import s_lanes
        return s_lanes.islandOf(H)
    except Exception:
        return None


# ------------------------------------------------------------------------------------------------ the skill
def score(s):
    """Pure. rank()'s score (about 0-1.2) as a want in the FREE PLAY band 10-39 (INTERFACE.md section 3)."""
    return max(10, min(39, int(round(10 + 20 * s))))


def slug(text, n=48):
    """Pure. A stable short bug-key piece: lowercase words joined by '-'."""
    return re.sub('[^a-z0-9]+', '-', str(text).lower()).strip('-')[:n].strip('-') or 'x'


class Games:
    """The skill as the brain holds it (pbot/skills/INTERFACE.md). bot = the brain (.H, .ev, .bug(kind, key, tag,
    what, tb)). A game is the bot's own free play, so not crewOk: a crew invite cuts it, and cut() walks him out."""
    name = 'games'
    limit = 1800            # s: the longest game (cannon defense, 1500 s + SLACK) and the walk out
    crewOk = False

    def __init__(self, bot, only=None):
        self.bot, self.H = bot, bot.H
        self.mem = {'rest': {}, 'off': set(), 'fails': {}}
        self.only = only
        self.results = []
        self.cur = None

    def choices(self, island=None):
        games = [g for g in GAMES if not self.only or g.name in self.only]
        return rank(_gold(self.H), island or _island(self.H), time.time(), self.mem, games=games)

    def _here(self):
        isl = _island(self.H)
        return [c for c in self.choices(isl) if BY[c[1]].island in (None, isl)]

    def want(self):
        """-> (score 10-39, 'game: why') for the best game on this island, or None."""
        here = self._here()
        if not here:
            return None
        s, name, why = here[0]
        return score(s), '%s: %s' % (name, why)

    def cut(self, why):
        """The brain stopped the flow (limit, crew, safety, down, error) and closed it (play() put the module flags
        back): rest that game, not a failure, and hand back the walk out of it; None when no game was on."""
        g, self.cur = self.cur, None
        if g is None:
            return None
        self.mem.setdefault('rest', {})[g.name] = time.time() + REST
        self.H.ev('GAME-CUT', game=g.name, why=why)
        return leave(self.H, g)

    def flow(self, name=None):
        """Generator: play the best game here (or `name`) once; book it; file a bug when it says so."""
        if name is None:
            w = self._here()
            if not w:
                return None
            name = w[0][1]
        g = self.cur = BY[name]
        r = yield from play(self.H, g)
        self.cur = None
        note(self.mem, name, r['res'], time.time())
        self.results.append(r)
        if r['res'] in ('game', 'bot'):
            tag = 'GAME' if r['res'] == 'game' else 'BOT'
            kind = 'traceback' if r['tb'] else ('stuck' if 'time limit' in str(r['why']) else 'other')
            key = 'games-%s-%s' % (name, slug(r['why']))
            what = 'the player bot played %s (rows %s): %s at stage %s' % (name, g.rows, r['why'], r['stage'])
            try:
                self.bot.bug(kind, key, tag, what, tb=r['tb'])
            except Exception:
                self.H.ev('games-bug-failed', tb=traceback.format_exc()[-300:])
        return r


class _Solo:
    """A stand-in brain for run(H): files bugs straight through bugfile."""

    def __init__(self, H):
        self.H = H

    def bug(self, kind, key, tag, what, tb=''):
        import bugfile
        la = self.H.la
        sig, path, count = bugfile.report(kind, key, tag, what, where=str(_area(self.H)),
                                          pirate='%s %s' % (getattr(la, 'name', '') or '?', la.doId),
                                          source='pbot games', tb=tb)
        self.H.ev('BUG', sig=sig, kind=kind, tag=tag, what=what[:160], count=count)


def run(H):
    """Step script: play games for GAMES_SECS; PASS when GAMES_WANT of them passed and no BOT bug was filed."""
    only = [s.strip() for s in os.environ.get('GAMES', '').split(',') if s.strip()] or None
    secs = float(os.environ.get('GAMES_SECS', '3600'))
    want = int(os.environ.get('GAMES_WANT', str(len(only) if only else 3)))
    la = H.la
    if la.doId in (100000170, 100000173, 100000656, 100000665):
        H.ev('FAIL', why='refusing: pirate %s is Host\'s or a boy\'s' % la.doId)
        return
    yield from _small(('upto', lambda: _gs(la) == 'LandRoam', 90, 'LandRoam'))
    home =os.environ.get('PBOT_HOME', '')
    if home and _island(H) != home:
        import s_lanes          # the runner's -Island: the brain's SETUP teleport, which -Script runs without a brain
        ok = yield from s_lanes.onIsland(H, 'home', home)
        H.ev('HOME', island=home, ok=ok, area=_area(H))
    sk = Games(_Solo(H), only)
    H.ev('GAMES', only=only, secs=secs, want=want, gold=_gold(H), island=_island(H), choices=sk.choices()[:5])
    t0 = time.time()
    order = list(only) if only else None
    while time.time() - t0 < secs:
        name = None
        if order:
            name = order.pop(0)
            if name not in BY:
                H.ev('FAIL', why='no game called %s' % name)
                return
        elif only:
            break
        elif sk.want() is None:
            H.ev('games-none', why='nothing to play on this island now', choices=sk.choices()[:5])
            yield from _small(30)
            continue
        yield from sk.flow(name)
        yield from _small(3)
    res = sk.results
    passed = [r['game'] for r in res if r['res'] == 'pass']
    bots = [r for r in res if r['res'] == 'bot']
    H.ev('PASS' if len(passed) >= want and not bots else 'FAIL',
         what='played %d games: %s' % (len(res), ', '.join('%s %s' % (r['game'], r['res']) for r in res)),
         why='%d passed (want %d), %d BOT' % (len(passed), want, len(bots)), passed=passed)
