"""pbot skill SEA (boats lane, Round 2, 11-22): the player bot sails its OWN ship (PLAYERBOTS-activities.md rows
11-28, 29b) with the helpers the sea rechecks proved in the live game.

- One flow = one outing from a port: buy a sloop first when it owns no ship (row 11, Port Royal's shipwright, s_island
  .buyShip), launch and take the wheel (rows 12, 15: s_shipquest.hunt -> launchShip -> sailing.launch, which repairs
  at the shipwright first), hunt one FAIR NPC ship (row 21, s_shipfight.fight), break off and repair at the nearest
  port when the hull runs low (rows 15, 16: s_shipfight.repairAt, 2 repairs at most), wait for the plunder after a
  sink (row 20), sail home and dock so the hold sells (rows 12, 20: sailing.sail_to, 0412), and at Tortuga trade the
  Light Sloop up when gold and Sailing allow (row 18, s_activities.tradeup, no magic word).
- FAIR only (the FLAGSHIP2 lesson, row 23 parked): a flagship is never a target. The hunt's own pick (Picker.rank:
  level gap, weak foes, leash, break-off under 50% hull or 20% lost in 10 s, danger flee) runs on a match test that
  refuses every flagship (fairMatch). Two bad outings in a row (broke off, sank, lost the wheel) -> the next outing
  is a hop to the other home port (row 13): no third try in the same waters.
- Sea monsters (row 22): one in view ends the hunt and the ship goes home (SEA-MONSTER); fighting one is v2.
  Ship skills (row 28, Open Fire) are v2. Row 29b (a friend's cannon) is the brain's CANNON state.
- Never: a magic word (PlayerH raises Blocked), a pirate or a player's ship as a target (NPC ships only), typed
  chat, pictures, a teleport other than the game's own island teleport (putAway).
- Events: SEA-OUTING (start / end), SEA-BUY, SEA-GOLD, SEA-SUNK, SEA-DOCKED, SEA-MONSTER, SEA-TRADE, SEA-PUTAWAY,
  SEA-CUT, SEA-QUIET, SEA-WAIT, SEA-MW-BLOCKED, and the helpers' own lines (FOE-PICK, BREAK-OFF, REPAIR, ...) with the
  reserved names renamed SEA-PASS / SEA-FAIL / SEA-STALL ...
- Fits pbot/skills/INTERFACE.md: limit 1200, crewOk False, FREE PLAY band (30, 15 when hopping), keys 'sea-...'.
  cut('crew') is the putAway the brain asks for (rule 8.3): the ship away, the mate on land.

As a step script (PROOF_SCRIPT = this file, through pbots' runner): run(H) plays outings for SEA_SECS and passes when
one outing launched, hunted fair (a sink, or no fair target in time), came home docked or ashore after a sink, with no
magic word asked for, no flagship picked and no BOT bug."""
import os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PBOT = os.path.dirname(HERE)
HARNESS = os.path.dirname(PBOT)
for _p in (PBOT, HARNESS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ['STORY_PLAYER'] = '1'      # the player rules (s_shipfight.repairAt, s_shipquest.payRepair: no gold word)
os.environ.setdefault('PROOF_SCRIPT', os.path.join(HARNESS, 'x.py'))   # s_shipfight puts its dir on sys.path at import

PR = '1150922126.8dzlu'               # Port Royal (s_lanes.PR)
TORTUGA = '1156207188.95dzlu'         # Tortuga (s_lanes.TORTUGA)
PORTS = (PR, TORTUGA)
SCORE = 30                            # FREE PLAY band (INTERFACE 3)
SCORE_LOW = 15                        # a hop after bad outings asks more quietly
BAD_MAX = 2                           # bad outings in a row before the next one is a hop
REST = {'good': 120, 'even': 180, 'bad': 300}   # s want() stays None after an outing, so other free play gets a turn
FIGHT_SECS = float(os.environ.get('SEA_FIGHT_SECS', '600'))    # s of hunting per outing
SEA_SECS = float(os.environ.get('SEA_SECS', '1500'))           # run(H): s of outings
OUTING_MIN = 400                      # run(H): no new outing with less than this left
HOME_WAIT = 120                       # s for the shore after our ship sank
MONSTER_EVERY = 5.0                   # s between looks for a sea monster
TRIES = 2                             # the same failure (buy, launch) twice in a game: the skill stops asking
RESERVED = ('PASS', 'FAIL', 'STALL', 'MILESTONE', 'STATE', 'BUG', 'BRAIN')   # the brain's event names (INTERFACE 4)
NEVER = (100000170, 100000173, 100000656, 100000665)  # a proof run never plays as one of these
GOOD = ('foe-sunk', 'hopped')
EVEN = ('timeout', 'no-target', 'monster')


class Blocked(Exception):
    pass


def slug(s):
    return ''.join(c if c.isalnum() else '-' for c in str(s).lower()).strip('-')[:40] or 'x'


# ---------------------------------------------------------------------------------------------- pure
def choose(s):
    """Pure: does the sea skill want the turn? s = {crew, down, gs, island, ships, canBuy, canLaunch, bad, restLeft,
    dead} -> (score, why, mode) or None. mode 'buy' (no ship yet: buy, then hunt), 'hunt', 'hop' (sail to the other
    home port after BAD_MAX bad outings)."""
    if s.get('crew') or s.get('down') or s.get('dead'):
        return None
    if s.get('gs') != 'LandRoam' or not s.get('island'):
        return None
    if (s.get('restLeft') or 0) > 0:
        return None
    if not s.get('ships'):
        if not s.get('canBuy'):
            return None
        return SCORE, 'no ship: buy a sloop at the shipwright', 'buy'
    if not s.get('canLaunch'):
        return None
    if (s.get('bad') or 0) >= BAD_MAX:
        return SCORE_LOW, '%d bad outings here: sail to the other port' % s['bad'], 'hop'
    return SCORE, 'hunt a fair NPC ship', 'hunt'


def nextPort(here):
    """Pure: the home port a hop sails to."""
    return TORTUGA if here == PR else PR


def grade(why):
    """Pure: an outing's end -> 'good' / 'even' / 'bad'."""
    if why in GOOD:
        return 'good'
    if why in EVEN:
        return 'even'
    return 'bad'


def streakAfter(bad, why):
    """Pure: bad outings in a row after one that ended with why."""
    g = grade(why)
    return 0 if g == 'good' else (bad if g == 'even' else bad + 1)


def fairMatch(match):
    """Pure: match(task, o) -> (ok, why) as the hunt asks it, refusing every flagship (FLAGSHIP2: one bot is
    outgunned; row 23 parked)."""
    def fair(task, o):
        ok, why = match(task, o)
        if ok and getattr(o, 'isFlagship', False):
            return False, 'a flagship: never solo (row 23 parked, FLAGSHIP2)'
        return ok, why
    return fair


def tradeDue(here, hasL1, gold, price, l1Cost, sailLvl, need):
    """Pure: may the trade-up run without a magic word? At Tortuga, Sailing high enough, gold for the price (and for
    the Light Sloop too when none is put away)."""
    if here != TORTUGA or sailLvl < need:
        return False
    return gold >= price + (0 if hasL1 else l1Cost)


def outingOk(o):
    """Pure: one outing that proves the skill: launched, hunted fair (a sink or nothing fair in time) or hopped, and
    ended docked or ashore, with no flagship picked."""
    if not o or o.get('res') == 'bot' or o.get('flagPicks'):
        return False
    if not o.get('launched'):
        return False
    return o.get('why') in GOOD + EVEN + ('our-ship-sunk',) and bool(o.get('docked') or o.get('ashore'))


# ---------------------------------------------------------------------------------------------- the wrapper
class PlayerH:
    """The walker's H as the sea helpers see it in a player bot: everything delegates, except magic words (refused)
    and the reserved event names (renamed SEA-..., so they never end the brain's run)."""

    def __init__(self, H):
        self._H = H
        self.blocked = None
        self.stalls = 0
        self.verdict = None             # the last PASS/FAIL a helper wrote (buyShip, tradeup): (name, why)

    def __getattr__(self, k):
        return getattr(self._H, k)

    def ev(self, name, /, **kw):          # positional-only: an event may carry its own name= (HOME-PICK)
        if name == 'STALL':
            self.stalls += 1
        if name in ('PASS', 'FAIL'):
            self.verdict = (name, kw.get('why') or kw.get('what'))
        if name in RESERVED or name.startswith(('CREW-', 'PBOT-')):
            return self._H.ev('SEA-' + name, **kw)
        return self._H.ev(name, **kw)

    def snap(self, tag):
        return self._H.ev('SEA-SNAP', tag=tag)

    def mw(self, word):
        self.blocked = str(word)
        self._H.ev('SEA-MW-BLOCKED', word=str(word).split(' ')[0], full=str(word)[:80])
        raise Blocked(word)


def drive(gen, H, look=None, every=MONSTER_EVERY):
    """Drive gen, turning a strict ('until', ...) wait into ('upto', ...) (a SEA-WAIT line when it runs out), and
    asking look() every `every` s: a truthy answer closes gen. -> ('done', gen's value) / ('stopped', look's answer)."""
    send, last = None, time.time()
    try:
        while True:
            try:
                item = gen.send(send)
            except StopIteration as e:
                return 'done', e.value
            send = None
            if look is not None and time.time() - last >= every:
                last = time.time()
                hit = look()
                if hit:
                    return 'stopped', hit
            if isinstance(item, tuple) and item and item[0] == 'until':
                fn, secs = item[1], item[2]
                what = item[3] if len(item) > 3 else '?'
                yield ('upto', fn, secs, what)
                try:
                    ok = fn()
                except Exception:
                    ok = False
                if not ok:
                    H.ev('SEA-WAIT', what=what, secs=secs)
            else:
                yield item
    finally:
        gen.close()


# ---------------------------------------------------------------------------------------------- live helpers
def _SF():
    import s_shipfight
    return s_shipfight


def _sail():
    import sailing
    return sailing


_FAIR = {}


def fairPicker(SF):
    """s_shipfight.Picker whose match test refuses flagships while it is entered (hunt() and Picker.npcShips both ask
    self.saved[1]); the real one is put back before Picker restores s_shipquest."""
    if 'cls' not in _FAIR:
        class FairPicker(SF.Picker):
            def __enter__(self):
                r = super().__enter__()
                self._real = self.saved
                self.saved = (self._real[0], fairMatch(self._real[1])) + tuple(self._real[2:])
                return r

            def __exit__(self, *a):
                self.saved = self._real
                return super().__exit__(*a)
        _FAIR['cls'] = FairPicker
    return _FAIR['cls']


def shipIds(la):
    try:
        return list(la.getInventory().getShipDoIdList())
    except Exception:
        return []


def gold(la):
    try:
        return la.getInventory().getGoldInPocket()
    except Exception:
        return 0


def nearestPort(H):
    """The home port nearest the pirate (Port Royal when unsure)."""
    try:
        tbl = _sail().islands()
        p = H.la.getPos(H.render)
        return min(PORTS, key=lambda u: (tbl[u][1] - p[0]) ** 2 + (tbl[u][2] - p[1]) ** 2)
    except Exception:
        return PR


def monsterInView(H):
    """'Kraken' / 'Sea Serpent' when one is in the client's view, else None."""
    import s_seamonster
    for kind, k in s_seamonster.KINDS.items():
        try:
            if s_seamonster.monsters(H, kind):
                return k.get('name', kind)
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------------------------- the skill
class Sea:
    """The skill as the brain holds it. bot = the brain (.H, .la, .cr, .gs(), .down(), .captain(), .bug(...))."""
    name = 'sea'
    limit = 1200                # an outing: launch, up to FIGHT_SECS of hunting, a repair, the sail home
    crewOk = False              # in a boy's crew the brain's crew states play; cut('crew') puts our ship away

    def __init__(self, bot):
        self.bot, self.H = bot, bot.H
        self.PH = PlayerH(bot.H)
        self.bad = 0
        self.restUntil = 0
        self.fails = {}         # key -> times this game
        self.dead = None        # why the skill stopped asking (TRIES of the same failure)
        self.results = []
        self._g = None          # game modules, imported on the first want()

    # -- reads (want() runs 30 times a minute: no walking, no scans)
    def _game(self):
        if self._g is None:
            from pirates.piratesbase import PiratesGlobals
            from pirates.economy import EconomyGlobals
            from pirates.ship import ShipGlobals
            self._g = (PiratesGlobals, EconomyGlobals, ShipGlobals)
        return self._g

    def _call(self, name, default=None):
        f = getattr(self.bot, name, None)
        try:
            return f() if f else default
        except Exception:
            return default

    def canBuy(self, la, here):
        PG, EG, SG = self._game()
        try:
            tut = la.style.getTutorial()
        except Exception:
            return False
        return here == PR and tut >= PG.TUT_GOT_SHIP and gold(la) >= EG.getItemCost(EG.ItemId.INTERCEPTOR_L1)

    def canLaunch(self, la, sid):
        """Afloat, or sunk with the repair paid (or free: server-tree 0156)."""
        PG, EG, SG = self._game()
        ov = self.bot.cr.getOwnerView(sid)
        hp = getattr(ov, 'Hp', None)
        if hp is None or hp > 0:
            return True
        cost, g = SG.getRepairCost(ov), gold(la)
        return g >= cost or (hasattr(SG, 'getRepairPrice') and SG.getRepairPrice(cost, g) == 0)

    def state(self):
        la = self.bot.la
        here = _sail().hereUid(self.H)
        ships = shipIds(la)
        return dict(crew=self._call('captain') is not None, down=bool(self._call('down', False)),
                    gs=self._call('gs') or la.getGameState(), island=here, ships=ships,
                    canBuy=False if ships else self.canBuy(la, here),
                    canLaunch=bool(ships) and self.canLaunch(la, ships[0]), bad=self.bad,
                    restLeft=max(0, self.restUntil - time.time()), dead=self.dead)

    def want(self):
        """-> (score, why) or None (choose() says when)."""
        if self.dead or time.time() < self.restUntil:
            return None
        try:
            c = choose(self.state())
        except Exception:
            return None
        return None if c is None else c[:2]

    def quiet(self, secs, why):
        self.restUntil = time.time() + secs
        self.H.ev('SEA-QUIET', secs=secs, why=why)

    def failed(self, key, what, tag='BOT'):
        """File a BOT (or GAME) bug once per failure; the same one TRIES times stops the skill for this game."""
        n = self.fails[key] = self.fails.get(key, 0) + 1
        try:
            self.bot.bug('other', key, tag, what)
        except Exception:
            self.H.ev('SEA-BUG-FAILED', tb=traceback.format_exc()[-300:])
        if n >= TRIES:
            self.dead = '%s %d times' % (key, n)
            self.H.ev('SEA-QUIET', secs=None, why=self.dead)

    # -- the outing
    def flow(self):
        """Generator: one outing. Returns {res ('good' / 'even' / 'bad' / 'bot'), why, mode, launched, docked, ashore,
        sunk, breaks, retakes, gold0, gold1, flagPicks, secs, blocked}."""
        H, PH = self.H, self.PH
        st = self.state()
        c = choose(st) or (None, 'asked without a want', 'hunt')
        mode = c[2]
        t0 = time.time()
        out = dict(res=None, why=None, mode=mode, launched=False, docked=False, ashore=False, sunk=0, breaks=0,
                   retakes=0, gold0=gold(self.bot.la), gold1=None, flagPicks=0, secs=0, blocked=None)
        H.ev('SEA-OUTING', what='start', mode=mode, why=c[1], island=st['island'], ships=st['ships'], gold=out['gold0'],
             bad=self.bad, area=H.area())
        err, tb, key = None, '', None
        try:
            yield from self._outing(PH, mode, out)
        except Blocked as e:
            err = 'asked for the magic word %r' % str(e).split(' ')[0]
            key = 'sea-mw-blocked'
        except Exception as e:
            tb = traceback.format_exc()
            err = 'crashed: ' + tb.strip().splitlines()[-1][:160]
            frames = traceback.extract_tb(e.__traceback__)
            key = 'sea-crash-%s-%s' % (slug(type(e).__name__), slug(frames[-1].name if frames else '?'))
        finally:
            PH.__dict__.pop('ev', None)          # the outing's event hook, if a cut closed us inside it
        out.update(gold1=gold(self.bot.la), secs=round(time.time() - t0), blocked=PH.blocked)
        if err:
            out.update(res='bot', why=err)
        else:
            out['res'] = grade(out['why'])
            self.bad = streakAfter(self.bad, out['why'])
        H.ev('SEA-OUTING', what='end', **out)
        self.results.append(out)
        if err:
            what = 'the player bot was at sea (%s, %s): %s' % (mode, out.get('stage'), err)
            try:
                self.bot.bug('traceback' if tb else 'other', key, 'BOT', what, tb=tb)
            except Exception:
                H.ev('SEA-BUG-FAILED', tb=traceback.format_exc()[-300:])
            self.quiet(600, key)
        else:
            self.quiet(REST[out['res']], 'rest after a %s outing (%s)' % (out['res'], out['why']))
        return out

    def _outing(self, H, mode, out):
        SF, sailing = _SF(), _sail()
        la = H.la
        here = sailing.hereUid(H)
        out['stage'] = 'start'
        if not shipIds(la):
            out['stage'] = 'buy'
            ok = yield from self._buy(H)
            H.ev('SEA-BUY', ok=ok, ships=shipIds(la), gold=gold(la), said=(H.verdict or (None, None))[1])
            if not ok or not shipIds(la):
                out['why'] = 'buy-failed'
                self.failed('sea-buy-failed', 'the player bot could not buy a sloop at Port Royal\'s shipwright: %s'
                            % ((H.verdict or (None, 'no ship after the buy'))[1],))
                return
        sid = shipIds(la)[0]
        look = lambda: monsterInView(H)
        if mode == 'hop':
            to = nextPort(here)
            out['stage'] = 'hop'
            H.sailResult = False
            how, v = yield from drive(sailing.sail_to(H, to, why='hop: %d bad outings at %s' % (self.bad, here)), H, look)
            out['launched'] = bool(sailing.onShip(H) or H.sailResult)
            if how == 'stopped':
                H.ev('SEA-MONSTER', monster=v, when='hop')
            out['why'] = 'hopped' if H.sailResult else 'hop-failed'
            if not H.sailResult:
                yield from self._home(H, sid, out, 'the hop did not land')
            else:
                out['docked'] = True
                H.ev('SEA-DOCKED', at=to, how='hop', hold=self._hold(sid))
            return
        out['stage'] = 'hunt'
        why = yield from self._hunt(H, SF, sid, out, look)
        out['why'] = why
        if why in ('our-ship-sunk', 'sunk-going-home'):
            out['stage'] = 'sunk'
            H.ev('SEA-SUNK', why=why, gs=la.getGameState(), area=H.area())
            yield ('upto', lambda: la.getGameState() == 'LandRoam' and sailing.hereUid(H) is not None, HOME_WAIT,
                   'ashore after the sink')
            out['ashore'] = la.getGameState() == 'LandRoam' and sailing.hereUid(H) is not None
            if why == 'sunk-going-home':
                out['why'] = 'our-ship-sunk'
            return
        if why == 'launch-failed':
            self.failed('sea-launch-failed', 'the player bot\'s ship %s did not launch at %s (a SAIL-FAIL line says '
                        'why)' % (sid, here))
            return
        out['stage'] = 'home'
        yield from self._home(H, sid, out, why)
        if out['docked'] and sailing.hereUid(H) == TORTUGA:
            out['stage'] = 'trade'
            yield from self._tradeup(H, out)

    def _hunt(self, H, SF, sid, out, look):
        """s_shipfight.run's loop on a FairPicker: fight, retake the wheel, break off and repair (REPAIRS at most),
        wait for the plunder. -> the end ('foe-sunk', 'break-off' ..., 'monster')."""
        got = {}
        t0 = time.time()
        picker = fairPicker(SF)(H, t0, task=SF.AnyShip())
        orig = H.ev
        cr = H.cr

        def hook(kind, /, **kw):
            if kind == 'FOE-SUNK' and kw.get('gone') and picker.lost(kw.get('foe')):
                kind = 'FOE-LOST'
                kw['last'] = picker.first.get(kw.get('foe'))
            got[kind] = got.get(kind, 0) + 1
            if kind == 'FOE-SUNK' and picker.sunk is None:
                picker.sunk = (kw.get('foe'),) + picker.info.get(kw.get('foe'), (None, '', None))
            if kind == 'FOE-PICK' and getattr(cr.doId2do.get(kw.get('foe')), 'isFlagship', False):
                out['flagPicks'] += 1
            return orig(kind, **kw)
        H.ev = hook
        why, goldB = None, gold(H.la)
        try:
            while True:
                left = FIGHT_SECS - (time.time() - t0)
                if left < 30:
                    why = why or 'timeout'
                    break
                picker.wheel = None
                goldB = gold(H.la)
                how, why = yield from drive(SF.fight(H, sid, left, got, picker, task=SF.AnyShip()), H, look)
                out['launched'] = out['launched'] or bool(got.get('SHIP-HUNT'))
                if how == 'stopped':
                    H.ev('SEA-MONSTER', monster=why, hp=SF.shipHp(H, sid), when='hunt')
                    why = 'monster'
                    break
                if why == 'left-ship':
                    wh = picker.wheel or {}
                    ok, rwhy = SF.canRetake(wh.get('inWorld'), wh.get('aboard'), wh.get('hp'), out['retakes'])
                    H.ev('RETAKE-WHEEL', ok=ok, why=rwhy, n=out['retakes'] + (1 if ok else 0), foe=picker.top)
                    if ok:
                        out['retakes'] += 1
                        yield 2
                        continue
                    break
                if why != 'break-off':
                    break
                out['breaks'] += 1
                if out['breaks'] > SF.REPAIRS:
                    why = 'broke off %d times' % out['breaks']
                    break
                how, r = yield from drive(SF.repairAt(H, sid, picker), H)
                if r != 'ok':
                    why = 'sunk-going-home' if r == 'sunk' else 'repair-failed'
                    break
                picker.top = None
        finally:
            H.__dict__.pop('ev', None)
        out['sunk'] = got.get('FOE-SUNK', 0)
        if why == 'foe-sunk':
            how, res = yield from drive(SF.plunderWait(H, SF.PLUNDER_SECS, hull=lambda: SF.shipHp(H, sid)), H)
            after, changes = res if isinstance(res, tuple) else (gold(H.la), [])
            sk = picker.sunk or (None, None, '', None)
            gain, exp, gok = SF.goldCheck(goldB, after, sk[1])
            H.ev('SEA-GOLD', before=goldB, after=after, gain=gain, foe=sk[0], level=sk[1], foeName=sk[2],
                 shipClass=sk[3], expect=exp, ok=gok, changes=changes)
        H.ev('SEA-HUNT-END', why=why, sunk=out['sunk'], lost=got.get('FOE-LOST', 0), breaks=out['breaks'],
             retakes=out['retakes'], seen=got.get('ship-seen', 0), flagPicks=out['flagPicks'],
             secs=round(time.time() - t0), gs=H.la.getGameState(), area=H.area())
        return why

    def _hold(self, sid):
        try:
            return len(list(getattr(self.bot.cr.getOwnerView(sid), 'cargo', None) or []))
        except Exception:
            return None

    def _home(self, H, sid, out, why):
        """Sail to the nearest home port and dock (the hold sells, 0412). Already ashore: nothing to do."""
        sailing = _sail()
        la = H.la
        if la.getGameState() == 'LandRoam' and sailing.hereUid(H) is not None and not sailing.onShip(H):
            out['docked'] = True
            return
        to = nearestPort(H)
        hold = self._hold(sid)
        H.sailResult = False
        yield from drive(sailing.sail_to(H, to, why='home after the hunt (%s)' % why), H)
        out['docked'] = bool(H.sailResult)
        H.ev('SEA-DOCKED', ok=out['docked'], at=to, hold=hold, holdAfter=self._hold(sid), gold=gold(la))
        if not out['docked'] and la.getGameState() in ('Death', 'Cutscene'):
            yield ('upto', lambda: la.getGameState() == 'LandRoam', HOME_WAIT, 'ashore after the sink')
            out['ashore'] = la.getGameState() == 'LandRoam'

    def _buy(self, H):
        """Generator: s_island.buyShip at Port Royal (Port Royal only; want() asks only there). -> True when bought."""
        import s_island
        from pirates.piratesgui import PiratesGuiGlobals
        from pirates.distributed import InteractGlobals
        from pirates.uberdog.UberDogGlobals import InventoryCategory
        from pirates.piratesbase import PiratesGlobals
        from pirates.economy import EconomyGlobals
        la, cr = H.la, H.cr
        warnings = []
        origWarn = la.guiMgr.createWarning

        def warn(msg, *a, **k):
            warnings.append(str(msg)[:120])
            return origWarn(msg, *a, **k)
        la.guiMgr.createWarning = warn
        H.verdict = None
        s_island.WANT_GOLD = False      # his own gold only (want() asks only when he can pay)
        try:
            how, ok = yield from drive(s_island.buyShip(H, la, cr, EconomyGlobals.ItemId.INTERCEPTOR_L1,
                                                        lambda: shipIds(la), warnings, PiratesGuiGlobals,
                                                        InteractGlobals, InventoryCategory, PiratesGlobals,
                                                        EconomyGlobals), H)
        finally:
            la.guiMgr.createWarning = origWarn
        if warnings:
            H.ev('SEA-SAID', said=warnings[-3:])
        return bool(ok)

    def _tradeup(self, H, out):
        """Row 18 at Tortuga: Light Sloop -> Sloop when tradeDue (gold and Sailing are his own; no magic word, no
        refused-ship test)."""
        import s_activities as A
        EG, IG, IT, RG, PGG = A._game()
        L1 = EG.ItemId.INTERCEPTOR_L1
        L2 = EG.SHIP_UPGRADE_NEXT[L1]
        price, need = EG.getShipUpgrade(L1)[1], EG.getItemMinLevel(L2) or 0
        hasL1 = A.tradeIn(A.shipList(H), L1) is not None
        lvl = A.sailLevel(H, RG, IT)
        if not tradeDue(_sail().hereUid(H), hasL1, gold(H.la), price, EG.getItemCost(L1), lvl, need):
            return
        saved = (A.GOLD, A.TRADE_REFUSE)
        A.GOLD, A.TRADE_REFUSE = False, False
        H.verdict = None
        try:
            yield from drive(A.tradeup(H), H)
        finally:
            A.GOLD, A.TRADE_REFUSE = saved
        H.ev('SEA-TRADE', ok=(H.verdict or ('?',))[0] == 'PASS', why=(H.verdict or (None, None))[1], sailing=lvl,
             price=price, ships=[list(s[:4]) for s in A.shipList(H)])

    # -- cut
    def cut(self, why):
        """The brain stopped the outing. why 'crew' (and any other but down): put the ship away, the mate on land
        (INTERFACE rule 8.3). Down: nothing acts."""
        self.H.ev('SEA-CUT', why=why)
        if why == 'limit':
            self.quiet(REST['bad'], 'cut at the limit')
        if why == 'down':
            return None
        return self.putAway(why)

    def putAway(self, why):
        """Generator (<= 60 s): off the wheel, off our ship, onto the nearest home port by the game's own island
        teleport."""
        sailing = _sail()
        H, la = self.PH, self.H.la
        import builtins
        m = getattr(builtins, 'messenger', None)
        if m is not None:
            for k in ('w', 'a', 'd', 's'):
                m.send(k + '-up')
        aboard = sailing.onShip(H)
        gs = la.getGameState()
        if not aboard and gs != 'ShipPilot':
            H.ev('SEA-PUTAWAY', ok=True, why=why, how='ashore already', gs=gs, area=H.area())
            return
        to = nearestPort(H)
        try:
            H.cr.teleportMgr.requestTeleportToIsland(to)
            err = None
        except Exception as e:
            err = repr(e)[:160]
        yield ('upto', lambda: la.getGameState() == 'LandRoam' and sailing.hereUid(H) is not None, 45,
               'put away: ashore')
        ok = la.getGameState() == 'LandRoam' and sailing.hereUid(H) is not None
        if not ok and la.getGameState() == 'ShipPilot':
            import s_everyship
            ship = la.getParentObj()
            yield from drive(s_everyship.leaveWheel(H, ship), H)
        H.ev('SEA-PUTAWAY', ok=ok, why=why, how='island teleport', to=to, err=err, gs=la.getGameState(),
             area=H.area())


class _Solo:
    """A stand-in brain for run(H): no crew, files bugs straight through bugfile."""

    def __init__(self, H):
        self.H, self.la, self.cr = H, H.la, H.cr

    def captain(self):
        return None

    def gs(self):
        return self.la.getGameState()

    def down(self):
        return self.la.getGameState() in ('Death', 'Dying') or (getattr(self.la, 'hp', 1) or 0) <= 0

    def bug(self, kind, key, tag, what, tb=''):
        import bugfile
        la = self.la
        sig, path, count = bugfile.report(kind, key, tag, what, where=str(self.H.area()),
                                          pirate='%s %s' % (getattr(la, 'name', '') or '?', la.doId),
                                          source='pbot sea', tb=tb)
        self.H.ev('BUG', sig=sig, kind=kind, tag=tag, what=what[:160], count=count)


def run(H):
    """Step script: outings for SEA_SECS; PASS on the first outing outingOk() takes, with no magic word and no BOT
    bug (the run stops there)."""
    la = H.la
    if la.doId in NEVER:
        H.ev('FAIL', why='refusing: pirate %s is Host\'s or a boy\'s' % la.doId)
        return
    yield ('upto', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    sailing = _sail()
    sk = Sea(_Solo(H))
    here = sailing.hereUid(H)
    if here not in PORTS:
        to = PR if here is None else nearestPort(H)
        H.ev('SEA-TELEPORT', frm=here, to=to)
        H.cr.teleportMgr.requestTeleportToIsland(to)
        yield ('upto', lambda: la.getGameState() == 'LandRoam' and sailing.hereUid(H) in PORTS, 60, 'a home port')
    try:
        tut = la.style.getTutorial()
    except Exception:
        tut = None
    st = sk.state()
    try:
        level = la.getLevel()
    except Exception:
        level = None
    H.ev('SEA-START', secs=SEA_SECS, pirate=la.doId, level=level, gold=gold(la), tut=tut, ships=st['ships'],
         canBuy=st['canBuy'], canLaunch=st['canLaunch'], island=st['island'], area=H.area(), want=sk.want())
    t0 = time.time()
    proof = None
    while SEA_SECS - (time.time() - t0) >= OUTING_MIN:
        sk.restUntil = 0            # a proof run does not rest between outings
        if sk.want() is None:
            if sk.dead:
                break
            st = sk.state()
            if not st['ships'] and not st['canBuy']:
                break               # no ship and nothing will change: the FAIL says why
            yield 10
            continue
        r = yield from sk.flow()
        if r['res'] == 'bot':
            break
        if outingOk(r):
            proof = r
            break
        yield 1
    bots = [r for r in sk.results if r['res'] == 'bot']
    ok = proof is not None and not bots and sk.PH.blocked is None
    if ok:
        why = 'outing %s: %s, launched, %s' % (proof['mode'], proof['why'], 'docked' if proof['docked'] else 'ashore')
    elif bots:
        why = bots[0]['why']
    elif not sk.results:
        st = sk.state()
        why = ('no ship and cannot buy one (tutorial %s, gold %s, at %s)' % (tut, gold(la), st['island'])
               if not st['ships'] else 'the skill never wanted the turn (%s)' % (sk.dead or st))
    else:
        why = 'no outing proved it: %s' % ['%s/%s/%s' % (r['mode'], r['why'], 'docked' if r['docked'] else
                                                         ('ashore' if r['ashore'] else 'at sea')) for r in sk.results]
    H.ev('PASS' if ok else 'FAIL', what='%d outings in %d s' % (len(sk.results), time.time() - t0), why=why,
         outings=[dict((k, r.get(k)) for k in ('mode', 'why', 'res', 'launched', 'docked', 'ashore', 'sunk',
                                               'breaks', 'flagPicks', 'gold0', 'gold1', 'secs'))
                  for r in sk.results])
