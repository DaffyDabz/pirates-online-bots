"""ACTIVITIES (pir-bot job 22, 11-19): one hidden run that proves the new Port Royal features live, step by step.

Steps (ACT_STEPS picks them, comma list, default the first six in this order; 7-12 only when named):
  1 shop       buy the cheapest item at the Port Royal gypsy (s_shop.run, unchanged)
  2 blackjack  sit at a blackjack table, bid the minimum, play one hand, stand up (s_parlor.run, unchanged). Then:
               - the gold rule (0210-0212): delta == the hand's result (a win), or 0 / -bid / -2*bid (push, loss,
                 double or split), and gold never under 0;
               - the broke check (0211, ACT_BROKE=1): 'gold 1', sit again; the server must stand him up (or refuse the
                 seat) when the 2+ gold bid comes due, and gold stays >= 0. His gold is put back after.
  3 poker      sit at a Hold'em table, press Fold on the first turn, wait for the hand to end, leave. Gold never
               rises and stays >= 0.
  4 crew       Crew page -> options -> Start a crew (0230) -> the recruit window's OK. Proof: the server's
               responseCrewAdd(1) (he is on the lookout list as a crew of one). The crew itself is made by the server
               when the first crewmate joins (0230), so no band appears here. The lookout is cancelled after.
  5 titles     Titles page (0231/0232): the Land PvP badge. Under rank 1 he gets the rank-1 infamy first (magic word
               givePlayerStack, logged MW-STACK). Press its badge button: PASS when the server's setBadgeIcon echo
               makes la.badge == (title, rank). The page is closed after.
  6 heal       'hp <half>', walk to the nearest townsperson whose menu has Heal, talk, press Heal, press Yes on the
               confirm. PASS when hp is back to max and gold fell by the heal cost (5 on this server).
  7 lookout    (job 28, 0270-0274) Lookout -> PvP -> Skirmish as a player picks it. Alone: request accepted, a match
               chance, then after ~600 s "Nobody else is looking for that game right now" (PASS how=nobody). With a
               second searcher: "Match found" (PASS how=found), answered No. The search is stopped, the page shut.
  8 tablefind  (job 28, 0272-0274) Lookout -> Parlor Games -> Blackjack (ACT_TABLE_KIND=poker for Hold'em). Yes on
               "Match found": he is moved into the tavern 8 ft in front of the busiest open table, "Walk up to the
               table and sit down". PASS when he stands within ACT_TABLE_NEAR (20) ft of a card table, or on "There's
               an open seat right here". FAIL on "No card tables are open", "filled up", "can't be moved".
  9 guild      (job 28, 0255) Guild page -> Create Guild -> OK, then the name box (ACT_GUILD_NAME, default 'Bot Crew
               NNNN', one retry on a taken name), then the member list. PASS when he is in a named guild and in its
               member list. Already in a guild / already named: those parts are skipped (a guild is named once).
               ACT_GUILD_LEAVE=1 leaves the guild afterwards.
 10 omalley    (job 32, 0284) Tortuga: walk to O'Malley (the shipwright), talk, Quest, pick the Ship PvP bread crumb
               (spanish.ShipPVPBreadCrumb), Accept. PASS when it is in his quest list (or he already holds it: it is
               given once). FAIL at once when the district has no Sea Battle SiegeManager (the client hides it).
 11 tradeup    (job 32, 0261-0265) O'Malley: Upgrade -> his Light Sloop -> Yes. PASS when gold fell by the price (950),
               the Light Sloop is gone and a Sloop with its name and cargo is in his list (a new doId). No Light Sloop
               put away: he buys one first (Ships -> Light Sloop -> name panel). Sailing 5 ('level 13712 5') and gold
               by magic word when ACT_GOLD=1. ACT_TRADE_REFUSE=1: ship 100000043 is asked for too; the server must
               answer makeSaleResponse(0) ("cannot be traded in").
 12 topten     (job 32, 0286) types ~topten in chat as an admin pirate. PASS when the UberDOG's answer opens the Top
               Ten panel (one row per guild), no traceback comes back, and the panel goes away after its 15 s.

Each step's own PASS / FAIL / STALL lines are renamed ACT-SUB (verdict=PASS/FAIL) / ACT-STALL, so the run's verdict
is the one final line: ACT-STEP n= name= ok= why= after every step, then PASS (all steps ok) or FAIL (lists them).
Never Host's pirate: a run logged in as 100000170 FAILs at once and does nothing.

Env: ACT_STEPS, ACT_BROKE (1), ACT_GOLD (1 = magic word 'gold' allowed for the shop and tables), ACT_BROKE_SECS (90),
ACT_POKER_SECS (240), ACT_HEAL_FRAC (0.5), ACT_LOOKOUT_SECS (660), ACT_LOOKOUT_GAME (skirmish), ACT_TABLE_KIND
(blackjack), ACT_TABLE_NEAR (20), ACT_GUILD_NAME, ACT_GUILD_LEAVE (0), ACT_TRADE_REFUSE (1), ACT_TOPTEN_SECS
(20), ACT_TOPTEN_GONE (20).
Lines: ACT-START, ACT-STEP, BJ-GOLD, BJ-BROKE, POKER-START/SEAT/FOLD/HAND, CREW-OPEN/START/REPLY/END,
TITLES-OPEN/PICK/BADGE, MW-STACK, HEAL-START/NPC/MENU/CONFIRM/DONE, sys-msg (every system message, steps 7-9),
LOOK-START/OPEN/CANCEL/GAMES/REQ/ACCEPTED/CHANCE/QUEUED/FOUND/FAILED/ANSWER/YES/END, TABLE-START/ANSWER/NEAR/END,
GUILD-START/STATUS/CREATE/NAME/NAMED/NAMETAG/MEMBERS/LEAVE, OMAL-START/NPC/OFFER/MENU/PICK/ACCEPT,
TRADE-START/BUY/REFUSE/MENU/PICK/CONFIRM/DONE, MW-LEVEL, NPC-LEAVE, TOPTEN-START/PANEL/ERROR/GONE, ACT-ERROR (a script error inside a step)."""
import os, sys, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402
import s_story   # noqa: E402
import s_cards   # noqa: E402

HOST = 100000170
DEFAULT = ['shop', 'blackjack', 'poker', 'crew', 'titles', 'heal']
ORDER = DEFAULT + ['lookout', 'tablefind', 'guild',        # job 28: 7-9 run only when ACT_STEPS names them
                   'omalley', 'tradeup', 'topten']           # job 32: 10-12, the same
STEPS = [s.strip() for s in os.environ.get('ACT_STEPS', ','.join(DEFAULT)).split(',') if s.strip()]
BROKE = os.environ.get('ACT_BROKE', '1') == '1'
GOLD = os.environ.get('ACT_GOLD', '1') == '1'
BROKE_SECS = float(os.environ.get('ACT_BROKE_SECS', '90'))
POKER_SECS = float(os.environ.get('ACT_POKER_SECS', '240'))
HEAL_FRAC = float(os.environ.get('ACT_HEAL_FRAC', '0.5'))
TALK = 8.0          # ft: inside a townsperson's 12 ft interact sphere (as s_shop)
# job 27 (ACTIVITIES1, 11-19): from the gypsy's yard every walk under 300 ft (the tavern door 248 ft, Bartholomew
# Watkins 125 ft) ran dry inside the planner's box: the yard's only way out goes east past the box's edge, and
# paths.py plans the 3x wider box only for goals past paths.FAR (300 ft). For this run FAR is 0: a short walk with
# no route in the small box gets the wide search too. Logged ACT-WIDE; ACT_WIDE=0 turns it off.
WIDE = os.environ.get('ACT_WIDE', '1') == '1'
HEAL_WALK_SECS = 180.0   # s to walk to the townsperson (was 90: room for a wide search)


# ---------------- pure helpers

def merge(kw, **extra):
    """Pure: kw plus extra; a key of kw that clashes keeps its value as key + '_'."""
    out = {}
    for k, v in kw.items():
        out[k + '_' if k in extra else k] = v
    out.update(extra)
    return out


def bjGoldOk(delta, mine, bid, gold):
    """Pure: the blackjack gold rule (0210-0212) -> (ok, why). delta = gold after the hand - gold before the bid,
    mine = the server's result for his seat (the amount won, > 0), bid = the stake."""
    if gold is None or gold < 0:
        return False, 'gold %s is under 0' % gold
    if bid is None:
        return False, 'no bid was placed'
    if mine is not None and mine > 0:
        return (delta == mine, 'won %s, gold moved %s' % (mine, delta))
    if mine is not None and delta == mine:
        return True, 'result %s, gold moved %s' % (mine, delta)
    ok = delta in (0, -bid, -2 * bid)
    return ok, 'result %s, gold moved %s (allowed 0 / -%d / -%d)' % (mine, delta, bid, 2 * bid)


def summary(results):
    """Pure: [(n, name, ok, why)] -> (allOk, text)."""
    bad = [r for r in results if not r[2]]
    if not results:
        return False, 'no step ran'
    if not bad:
        return True, 'all %d steps passed' % len(results)
    return False, '%d of %d steps failed: %s' % (len(bad), len(results),
                                                  '; '.join('%d %s (%s)' % (r[0], r[1], r[3]) for r in bad))


# ---------------- verdict capture

def capture(H, gen, n, name):
    """Generator: run gen with H.ev wrapped: its PASS / FAIL become ACT-SUB, STALL becomes ACT-STALL, everything else
    passes through. -> {'kind': 'PASS'/'FAIL'/None, 'kw': {...}, 'evs': [(kind, kw)]}. A script error = FAIL."""
    orig = H.ev
    got = {'kind': None, 'kw': {}, 'evs': []}

    def ev(_kind, /, **kw):                       # not 'kind': s_parlor logs PARLOR-START kind=... (unit_job22)
        kind = _kind
        got['evs'].append((kind, kw))
        if kind in ('PASS', 'FAIL'):
            if got['kind'] is None:
                got['kind'], got['kw'] = kind, kw
            return orig('ACT-SUB', **merge(kw, actN=n, act=name, verdict=kind))
        if kind == 'STALL':
            return orig('ACT-STALL', **merge(kw, actN=n, act=name))
        return orig(kind, **kw)
    H.ev = ev
    try:
        yield from gen
    except Exception as e:
        tb = traceback.format_exc()
        orig('ACT-ERROR', actN=n, act=name, err=repr(e), tb=tb[-1200:])
        if got['kind'] is None:
            got['kind'], got['kw'] = 'FAIL', {'why': 'script error %r' % e}
    finally:
        H.ev = orig
    return got


def find(evs, kind, **match):
    """The kw of the last event of that kind whose fields match, or None."""
    for k, kw in reversed(evs):
        if k == kind and all(kw.get(a) == b for a, b in match.items()):
            return kw
    return None


def landRoam(H, secs=30, label='LandRoam'):
    yield ('until', lambda: H.la.getGameState() == 'LandRoam', secs, label)
    return H.la.getGameState() == 'LandRoam'


# ---------------- 1 shop

def shop(H):
    import s_shop
    s_shop.WANT_GOLD = s_shop.WANT_GOLD or GOLD
    yield from s_shop.run(H)


# ---------------- 2 blackjack

def blackjack(H):
    import s_parlor
    from pirates.minigame import PlayingCardGlobals as PCG
    la = H.la
    s_parlor.KIND, s_parlor.FROM = 'Blackjack', s_lanes.PR
    s_parlor.WANT_GOLD = s_parlor.WANT_GOLD or GOLD
    got = yield from capture(H, s_parlor.run(H), 2, 'blackjack-hand')
    hand = find(got['evs'], 'PARLOR-HAND') or {}
    res = find(got['evs'], 'PARLOR-RESULT') or {}
    at = find(got['evs'], 'STAGE', what='at-table') or {}
    if got['kind'] != 'PASS':
        H.ev('FAIL', why='the hand did not pass: %s' % got['kw'].get('why'), hand=hand); return
    ok, why = bjGoldOk(hand.get('delta'), res.get('mine'), hand.get('bid'), s_lanes.gold(H))
    H.ev('BJ-GOLD', ok=ok, why=why, delta=hand.get('delta'), mine=res.get('mine'), bid=hand.get('bid'),
         gold=s_lanes.gold(H), over=hand.get('over'))
    if not ok:
        H.ev('FAIL', why='blackjack gold rule: %s' % why); return
    if not BROKE:
        H.ev('PASS', what='one blackjack hand, gold right (%s); broke check off' % why); return
    if not GOLD:
        H.ev('PASS', what='one blackjack hand, gold right (%s); broke check needs ACT_GOLD=1' % why); return

    # the broke check (0211): 1 gold, sit, the server must not let him bid 2+ gold
    t = H.cr.doId2do.get(at.get('table'))
    if t is None:
        H.ev('FAIL', why='broke check: the table %s left the client' % at.get('table')); return
    g = s_lanes.gold(H)
    H.ev('MW-GOLD', why='broke check: 1 gold, then sit (put back to %d after)' % g)
    H.mw('gold 1')
    yield ('until', lambda: s_lanes.gold(H) == 1, 10, 'gold 1')
    seated, stood, refused, low = False, False, False, s_lanes.gold(H)
    try:
        r = yield from s_lanes.walkTo(H, 'blackjack', lambda st: True if s_story.near(H, t, s_cards.SIT_FT, st,
                                      tag='back-to-table') else 'walk-to-table', 60, 'the blackjack table')
        H.walk_cancel()
        if r is None:
            H.ev('FAIL', why='broke check: could not walk back to the table'); return
        t.requestInteraction(la.doId)
        yield ('until', lambda: t.isLocalAvatarSeated(), 20, 'broke sit')
        seated = bool(t.isLocalAvatarSeated())
        if not seated:
            refused = True
            try:
                t.deleteRequestDialogs()
            except Exception:
                pass
        else:
            t0 = time.time()
            while time.time() - t0 < BROKE_SECS and t.isLocalAvatarSeated():
                low = min(low, s_lanes.gold(H))
                yield 0.5
            stood = not t.isLocalAvatarSeated()
            if not stood:
                try:
                    t.guiCallback(PCG.Leave)
                except Exception:
                    pass
        yield from landRoam(H, 30, 'broke stand up')
        low = min(low, s_lanes.gold(H))
    finally:
        H.mw('gold %d' % g)
    yield ('until', lambda: s_lanes.gold(H) == g, 10, 'gold back')
    H.ev('BJ-BROKE', seated=seated, stoodUp=stood, refused=refused, lowest=low, goldBack=s_lanes.gold(H) == g,
         gs=la.getGameState())
    if low < 0:
        H.ev('FAIL', why='broke check: gold went to %d' % low); return
    if seated and not stood:
        H.ev('FAIL', why='broke check: with 1 gold he stayed seated %d s (the server did not stand him up)' % BROKE_SECS)
        return
    H.ev('PASS', what='one blackjack hand, gold right (%s); a broke pirate was %s, gold stayed %d'
         % (why, 'stood up' if stood else 'refused a seat', low))


# ---------------- 3 poker

def poker(H):
    import s_parlor
    from pirates.minigame import PlayingCardGlobals as PCG
    la = H.la
    H.ev('POKER-START', gold=s_lanes.gold(H), here=H.area())
    if not (yield from s_lanes.onIsland(H, 'poker', s_lanes.PR)):
        H.ev('FAIL', why='could not get to Port Royal', area=H.area()); return
    r = yield from s_lanes.walkTo(H, 'poker', lambda st: s_story.cardTable(H, 'Holdem', st), 300, "a Hold'em table")
    if not isinstance(r, tuple):
        H.ev('FAIL', why="could not walk to a Hold'em table", la=H.P(la), area=H.area()); return
    t = H.cr.doId2do.get(r[1])
    if t is None:
        H.ev('FAIL', why='the table left the client', table=r[1]); return
    mult = getattr(t, 'betMultiplier', 1) or 1
    need = s_parlor.needGold('Holdem', mult, 0)
    if s_lanes.gold(H) < need and GOLD:
        H.ev('MW-GOLD', why='the test pirate has %d gold, the table needs %d' % (s_lanes.gold(H), need))
        H.mw('gold %d' % (need + 20))
        yield ('until', lambda: s_lanes.gold(H) >= need, 10, 'poker gold')
    if s_lanes.gold(H) < need:
        H.ev('FAIL', why='gold %d below what the table needs (%d)' % (s_lanes.gold(H), need)); return
    g0 = s_lanes.gold(H)
    H.walk_cancel()
    t.requestInteraction(la.doId)
    yield ('until', lambda: t.isLocalAvatarSeated() and getattr(t, 'gui', None) is not None, 20, 'poker sit')
    if not (t.isLocalAvatarSeated() and getattr(t, 'gui', None) is not None):
        try:
            t.deleteRequestDialogs()
        except Exception:
            pass
        H.ev('FAIL', why='not seated after 20 s (table full?)', gs=la.getGameState()); return
    H.ev('POKER-SEAT', table=t.doId, seat=getattr(t, 'localAvatarSeat', None), mult=mult, gold=s_lanes.gold(H))
    folded, over, t0 = False, None, time.time()
    while time.time() - t0 < POKER_SECS:
        if not t.isLocalAvatarSeated() or getattr(t, 'gui', None) is None:
            over = 'stood-up'
            break
        gui = t.gui
        fb, dr = getattr(gui, 'foldButton', None), getattr(gui, 'disableReason', None)
        if s_cards._normal(fb) and (dr is None or dr.isHidden()):
            args = list(fb['extraArgs'] or [PCG.Fold])
            H.ev('POKER-FOLD', round=getattr(t, 'round', None), args=args, gold=s_lanes.gold(H))
            gui.playerAction(*args)
            folded = True
            break
        yield 0.5
    if folded:
        yield ('until', lambda: getattr(t, 'endOfHand', False) or not t.isLocalAvatarSeated(), 90, 'poker hand end')
        over = 'end-of-hand' if getattr(t, 'endOfHand', False) else ('stood-up' if not t.isLocalAvatarSeated()
                                                                      else 'time')
        yield 2
    if t.isLocalAvatarSeated():
        try:
            t.guiCallback(PCG.Leave)
        except Exception as e:
            H.ev('POKER-LEAVE', err=repr(e))
        yield ('until', lambda: not t.isLocalAvatarSeated() and la.getGameState() == 'LandRoam', 30, 'poker stand up')
    left = not t.isLocalAvatarSeated() and la.getGameState() == 'LandRoam'
    g1 = s_lanes.gold(H)
    H.ev('POKER-HAND', folded=folded, over=over, left=left, goldBefore=g0, goldAfter=g1, delta=g1 - g0,
         secs=round(time.time() - t0))
    if not folded:
        H.ev('FAIL', why='no Fold turn came in %d s (%s)' % (POKER_SECS, over or 'time')); return
    if not left:
        H.ev('FAIL', why='folded but did not stand up (gs %s)' % la.getGameState()); return
    if g1 < 0 or g1 > g0:
        H.ev('FAIL', why='folded, but gold %d -> %d' % (g0, g1)); return
    H.ev('PASS', what="folded one Hold'em hand and left", how=over, delta=g1 - g0)


# ---------------- 4 crew

def crew(H):
    from pirates.piratesgui import CrewMatchInviter as CMI
    la, gm = H.la, H.la.guiMgr
    cp = gm.crewPage
    pcm = getattr(H.cr, 'pirateCrewMatch', None)
    band = la.getBandId() if hasattr(la, 'getBandId') else None
    H.ev('CREW-OPEN', inCrew=bool(cp.crew), band=band, matcher=pcm is not None)
    if cp.crew:
        H.ev('FAIL', why='the test pirate is already in a crew (Start a crew is for a pirate with none)'); return
    if pcm is None:
        H.ev('FAIL', why='no crew matcher on the client (base.cr.pirateCrewMatch)'); return
    rep, caught = {}, []
    oAdd = pcm.responseCrewAdd
    oInit = CMI.CrewMatchInviter.__init__

    def add(code, *a):
        rep['add'] = code
        H.ev('CREW-REPLY', code=code, listed=code == 1)
        return oAdd(code, *a)

    def init(self, *a, **k):
        caught.append(self)
        return oInit(self, *a, **k)
    pcm.responseCrewAdd = add
    CMI.CrewMatchInviter.__init__ = init
    try:
        gm.socialPanel.show()
        gm.socialPanel.setPage(cp)
        yield 1
        cp.crewOptions()                        # the page's options button
        yield 1
        b = cp.startACrewButton
        from direct.gui import DirectGuiGlobals as DGG
        if not b or b['state'] == DGG.DISABLED:
            H.ev('FAIL', why='no lit Start a crew button', button=bool(b)); return
        H.ev('CREW-START', state=str(b['state']))
        b['command'](*(b['extraArgs'] or []))
        yield ('until', lambda: bool(caught), 10, 'recruit window')
        if not caught:
            H.ev('FAIL', why='Start a crew pressed, no recruit window'); return
        yield 1
        caught[-1].bOk['command']()            # the recruit window's OK
        yield ('until', lambda: 'add' in rep, 20, 'crew reply')
    finally:
        pcm.responseCrewAdd = oAdd
        CMI.CrewMatchInviter.__init__ = oInit
        try:
            if cp.startACrewState or cp.recruitCrewMatesStatus:
                cp.b_deactivateCrewLookout()       # off the lookout list again, crew of one dropped
        except Exception as e:
            H.ev('CREW-END', err=repr(e))
        try:
            for w in caught:
                if not w.isEmpty():
                    w.destroy()
            gm.socialPanel.hide()
        except Exception:
            pass
    H.ev('CREW-END', reply=rep.get('add'), band=la.getBandId() if hasattr(la, 'getBandId') else None)
    if rep.get('add') != 1:
        H.ev('FAIL', why='the server answered %s to Start a crew (1 = listed as a crew of one)' % rep.get('add'))
        return
    H.ev('PASS', what='Start a crew: the server listed him as a crew of one', reply=1)


# ---------------- 5 titles

def titles(H):
    from pirates.pirate import TitleGlobals as TG
    la, gm = H.la, H.la.guiMgr
    tp = gm.titlesPage
    if tp is None:
        # job 27: GuiManager makes the page only when the client config has want-titles-page on (default off,
        # piratesgui/GuiManager.py:100 and :186-189; ChestTray.py:14 hides its button the same way), and no client
        # .prc sets it. A game config gap, not the bot's lookup
        try:
            import builtins
            want = bool(builtins.base.config.GetBool('want-titles-page', 0))
        except Exception:
            want = None
        H.ev('FAIL', why='the game has no Titles page: want-titles-page is off in the client config '
                         '(piratesgui/GuiManager.py:100)', wantTitlesPage=want); return
    if not gm.pageOpen(tp):
        gm.showTitlesPanel()                   # the B key
    yield 1
    H.ev('TITLES-OPEN', opened=bool(gm.pageOpen(tp)), panels=len(tp.titles or []), badge=getattr(la, 'badge', None))
    try:
        panel = next((p for p in tp.titles or [] if p.titleId == TG.LandPVPTitle), None)
        if panel is None:
            H.ev('FAIL', why='no Land PvP title panel'); return
        if panel.rank < 1:
            inv = la.getInventory()
            invType = TG.getInventoryType(TG.LandPVPTitle)
            need = TG.getBreakpoints(TG.LandPVPTitle)[1]
            H.ev('MW-STACK', why='rank 0: the land infamy for rank 1', stack=invType, amount=need,
                 had=inv.getStackQuantity(invType))
            H.mw('givePlayerStack %d %d' % (invType, need))
            yield ('until', lambda: (inv.getStackQuantity(invType) or 0) >= need, 15, 'infamy')
            tp.refresh()
            yield 0.5
        if panel.rank < 1:
            H.ev('FAIL', why='the Land PvP title is still rank 0'); return
        want = (panel.titleId, panel.rank)
        if panel.landActive or tuple(getattr(la, 'badge', None) or ()) == want:
            # already on: switch it off first, so the press below is a real save
            if panel.landActive:
                panel.landToggle()
            else:
                la.sendRequestSetBadgeIcon(-1, -1)
            yield ('until', lambda: getattr(la, 'badge', None) is None, 10, 'badge off')
        H.ev('TITLES-PICK', title=panel.titleId, rank=panel.rank, badge=getattr(la, 'badge', None))
        panel.landToggle()                     # the badge button on the panel
        yield ('until', lambda: tuple(getattr(la, 'badge', None) or ()) == want, 15, 'badge saved')
        H.ev('TITLES-BADGE', badge=getattr(la, 'badge', None), want=want)
        if tuple(getattr(la, 'badge', None) or ()) != want:
            H.ev('FAIL', why='badge pressed, the server did not save it (badge %s)' % (getattr(la, 'badge', None),))
            return
        H.ev('PASS', what='picked the Land PvP badge, the server saved it', badge=list(want))
    finally:
        try:
            gm.hideSeaChest()
        except Exception:
            pass


# ---------------- 6 heal

def healers(H):
    from pirates.distributed import InteractGlobals as IG
    out = []
    for o in list(H.cr.doId2do.values()):
        if type(o).__name__ != 'DistributedNPCTownfolk' or not hasattr(o, 'getPos'):
            continue
        try:
            menu = IG.getNPCInteractMenu(o.avatarType)
        except Exception:
            menu = None
        if menu and IG.HEAL_HP in menu[1]:
            out.append(o)
    return sorted(out, key=lambda o: s_story.hdist(H, o))


def heal(H):
    import s_shop
    from pirates.distributed import InteractGlobals as IG
    la = H.la
    mx = la.getMaxHp()
    want = max(1, int(mx * HEAL_FRAC))
    H.ev('HEAL-START', hp=la.getHp(), maxHp=mx, to=want, gold=s_lanes.gold(H), here=H.area())
    if la.getHp() >= mx:
        H.mw('hp %d' % want)
        yield ('until', lambda: la.getHp() < mx, 10, 'hp down')
    if la.getHp() >= mx:
        H.ev('FAIL', why='could not lower his hp to test the heal'); return
    from pirates.economy import EconomyGlobals
    cost = EconomyGlobals.getAvatarHealHpCost(mx)
    if s_lanes.gold(H) < cost and GOLD:
        H.ev('MW-GOLD', why='the heal costs %d' % cost)
        H.mw('gold %d' % (cost + 10))
        yield ('until', lambda: s_lanes.gold(H) >= cost, 10, 'heal gold')
    yield ('until', lambda: bool(healers(H)), 5, 'townsperson in view')
    if not healers(H):
        # none here (a tavern): walk to the gypsy's open ground, where townsfolk walk
        isl, area, uid, pos = s_shop.SHOPS['gypsy']
        if not (yield from s_lanes.onIsland(H, 'heal', isl)):
            H.ev('FAIL', why='could not get to Port Royal'); return
        r = yield from s_lanes.walkTo(H, 'heal', lambda st: s_story.goto(H, st, area, pos=pos, arrive=TALK,
                                      tag='to-townsfolk'), 240, 'the townsfolk')
        if r is None:
            H.ev('FAIL', why='could not walk out to the townsfolk', la=H.P(la)); return
        yield ('until', lambda: bool(healers(H)), 20, 'townsperson in view')
    hs = healers(H)
    if not hs:
        H.ev('FAIL', why='no townsperson with Heal in view'); return
    npc = hs[0]
    H.ev('HEAL-NPC', npc=npc.doId, who=getattr(npc, 'name', ''), d=round(s_story.hdist(H, npc), 1))
    r = yield from s_lanes.walkTo(H, 'heal', lambda st: True if s_story.near(H, npc, TALK, st, tag='townsperson')
                                  else 'walk-to-townsperson', HEAL_WALK_SECS, 'the townsperson')
    if r is None:
        H.ev('FAIL', why='could not reach the townsperson', npc=npc.doId, d=round(s_story.hdist(H, npc), 1)); return
    H.walk_cancel()
    sub = la.guiMgr.subtitler
    clicks = []

    def clicker(task):                         # his greeting: press the subtitle's arrow, as s_npc
        try:
            b = sub.confirmButton
            if not b.isHidden() and b['command']:
                clicks.append(str(sub.text['text'])[:40])
                b['command'](*(b['extraArgs'] or []))
        except Exception:
            pass
        return task.again
    H.B.taskMgr.doMethodLater(2.0, clicker, 'act-heal-click')
    g0, hp0 = s_lanes.gold(H), la.getHp()
    try:
        npc.requestInteraction(la.doId)
        yield ('until', lambda: la.getGameState() == 'NPCInteract' and getattr(npc, 'interactGUI', None) is not None,
               25, 'heal menu')
        if getattr(npc, 'interactGUI', None) is None:
            H.ev('FAIL', why='no menu after the interact (25 s)', gs=la.getGameState(), clicks=clicks); return
        ids, states = npc.computeOptions()[:2]
        hs_ = dict(zip(ids, states)).get(IG.HEAL_HP)
        H.ev('HEAL-MENU', npc=npc.doId, options=list(ids), heal=hs_, hp=la.getHp(), clicks=clicks)
        if hs_ != IG.NORMAL:
            H.ev('FAIL', why='the Heal button is not lit (state %s)' % hs_); return
        yield 1.5
        npc.selectOptionConfirm(IG.HEAL_HP)
        yield ('until', lambda: getattr(npc, 'confirmDialog', None) is not None, 10, 'heal confirm')
        dlg = getattr(npc, 'confirmDialog', None)
        if dlg is None:
            H.ev('FAIL', why='Heal pressed, no confirm window'); return
        H.ev('HEAL-CONFIRM', gold=s_lanes.gold(H))
        dlg['command'](1)                      # Yes
        yield ('until', lambda: la.getHp() >= la.getMaxHp(), 15, 'healed')
    finally:
        H.B.taskMgr.remove('act-heal-click')
        try:
            if getattr(npc, 'interactGUI', None):
                npc.interactGUI.destroy()
                npc.interactGUI = None
            npc.handleEndInteractKey()
        except Exception as e:
            H.ev('HEAL-LEAVE', err=repr(e))
    yield from landRoam(H, 20, 'heal leave')
    g1, hp1 = s_lanes.gold(H), la.getHp()
    H.ev('HEAL-DONE', hp=[hp0, hp1], maxHp=la.getMaxHp(), gold=[g0, g1], cost=cost, gs=la.getGameState())
    if hp1 < la.getMaxHp():
        H.ev('FAIL', why='Yes pressed, hp %d of %d' % (hp1, la.getMaxHp())); return
    if g0 - g1 != cost:
        H.ev('FAIL', why='healed, but gold %d -> %d (cost %d)' % (g0, g1, cost)); return
    H.ev('PASS', what='a townsperson healed him for %d gold' % cost, hp=[hp0, hp1])


# ---------------- job 28 (11-19): the Lookout (0270-0274) and the Guild (0255). Opt-in: ACT_STEPS=lookout,tablefind,guild

_now = time.time                 # the unit test swaps in its own clock

PVP, PG = 1, 0                   # PiratesGlobals.GAME_TYPE_PVP / GAME_TYPE_PG
STYLE = {'skirmish': 0, 'teambattle': 2, 'blackjack': 11, 'poker': 10}   # GAME_STYLE_BATTLE / TEAM_BATTLE / ...
NOBODY = 'Nobody else is looking for that game right now'
QUEUED = 'You will be notified when a match is found'
TABLE_MSG = {'walk': 'Walk up to the table and sit down', 'here': "There's an open seat right here",
             'none': 'No card tables are open right now', 'none2': 'No other card tables are open right now',
             'full': 'That table filled up', 'stuck': "You can't be moved from where you are",
             'notyet': "That game isn't on this server yet", 'busy': 'Finish your skirmish first',
             'late': 'You did not answer in time'}
NO_GUILD = ('', '0', 'Null', 'No Guild', None)


def sysHook(H, box):
    """Log every system message (sys-msg) and keep (time, text) in box. -> the undo function (as s_seabattle)."""
    from otp.avatar import DistributedPlayer as DPm
    cls = DPm.DistributedPlayer
    orig = cls.__dict__['setSystemMessage']

    def setSystemMessage(av, aboutId, chatString, *a, **kw):
        box.append((_now(), chatString))
        try:
            H.ev('sys-msg', text=chatString, av=getattr(av, 'doId', None), about=aboutId)
        except Exception:
            pass
        return orig(av, aboutId, chatString, *a, **kw)
    cls.setSystemMessage = setSystemMessage

    def undo():
        cls.setSystemMessage = orig
    return undo


def said(box, text, since=0.0):
    """Pure: the first message in box (after since) that holds text, or None."""
    return next((m for t, m in box if t >= since and text in str(m)), None)


def tableAnswer(box, since=0.0):
    """Pure: the key of the first card-table answer the match maker sent (TABLE_MSG), or None."""
    for t, m in box:
        if t < since:
            continue
        for k, txt in TABLE_MSG.items():
            if txt in str(m):
                return k
    return None


def wrapInst(obj, name, before, saved):
    """Wrap obj.name with an instance attribute that calls before(*args) and then the method. Kept in saved for
    unwrap(). The client dispatches the server's field updates through getattr, so the wrap sees every reply."""
    orig = getattr(obj, name)
    had = name in getattr(obj, '__dict__', {})

    def w(*a, **k):
        try:
            before(*a, **k)
        except Exception as e:
            H_err.append(repr(e))
        return orig(*a, **k)
    setattr(obj, name, w)
    saved.append((obj, name, orig, had))


H_err = []


def unwrap(saved):
    for obj, name, orig, had in reversed(saved):
        try:
            if had:
                setattr(obj, name, orig)
            else:
                delattr(obj, name)
        except Exception:
            pass
    del saved[:]


def lookoutPick(H, lp, cat, style, rep):
    """Press the Lookout like a player: open it, pick the category, then the game. -> the why on a miss, else None."""
    gm = H.la.guiMgr
    import builtins
    launcher = getattr(builtins, 'launcher', None)
    can = launcher.canLeaveFirstIsland() if launcher is not None else None
    H.ev('LOOK-OPEN', cat=cat, style=style, canLeave=can, mode=getattr(lp, 'currMode', None),
         searching=getattr(lp, 'searchActive', None))
    if can is False:
        return 'the Lookout is locked (launcher.canLeaveFirstIsland() is False)'
    if getattr(lp, 'searchActive', False):
        H.ev('LOOK-CANCEL', why='a search was already on')
        lp.cancelSearch()
        yield 1
    if not gm.pageOpen(lp):
        gm.showLookoutPanel()
    yield 1
    lp.itemSelectByValue(cat)                  # the category's list item (UI_VERSION 1: goes straight to its games)
    yield ('until', lambda: getattr(lp, 'typePanel', None) is not None, 5, 'lookout games list')
    if getattr(lp, 'typePanel', None) is None and getattr(lp, 'nextButton', None) is not None:
        lp.nextClick()
        yield ('until', lambda: getattr(lp, 'typePanel', None) is not None, 5, 'lookout games list')
    if getattr(lp, 'typePanel', None) is None:
        return 'picked category %s, no games list came up' % cat
    try:
        vals = [getattr(i, 'value', None) for i in lp.typePanel.activityListItems.items]
    except Exception:
        vals = None                            # list layout not as expected: let the pick itself tell
    H.ev('LOOK-GAMES', cat=cat, styles=vals)
    if vals is not None and style not in vals:
        return 'game %s is not in the Lookout list %s' % (style, vals)
    lp.typePanel.itemSelectByValue(style)      # the game's list item: submits the request (no submit button)
    yield ('until', lambda: 'req' in rep, 5, 'lookout request sent')
    if 'req' not in rep and getattr(lp, 'submitButton', None) is not None:
        lp.submitRequest()
        yield ('until', lambda: 'req' in rep, 10, 'lookout request sent')
    if 'req' not in rep:
        return 'picked game %s, no requestActivity went out' % style
    return None


def lookoutHooks(H, lp, rep, saved):
    la = H.la

    def req(gameType, cat, options, shipIds):
        rep['req'] = (gameType, cat)
        H.ev('LOOK-REQ', style=gameType, cat=cat, options=options, ships=list(shipIds or []))

    def acc():
        rep['acc'] = _now()
        H.ev('LOOK-ACCEPTED')

    def found(matchId, timeToJoin=30):
        rep['found'] = (matchId, timeToJoin, _now())
        H.ev('LOOK-FOUND', match=matchId, timeToJoin=timeToJoin)

    def failed(restart):
        rep.setdefault('failed', []).append((restart, _now()))
        H.ev('LOOK-FAILED', restart=restart)

    def chance(c):
        rep.setdefault('chance', []).append(c)
        H.ev('LOOK-CHANCE', chance=c, word='low' if c <= 1 else 'moderate' if c <= 25 else 'high')
    wrapInst(la, 'requestActivity', req, saved)
    wrapInst(lp, 'requestActivityAccepted', acc, saved)
    wrapInst(lp, 'matchFound', found, saved)
    wrapInst(lp, 'matchFailed', failed, saved)
    wrapInst(lp, 'matchChance', chance, saved)


def lookoutClose(H, lp):
    gm = H.la.guiMgr
    try:
        if getattr(lp, 'searchActive', False):
            lp.cancelSearch()
    except Exception as e:
        H.ev('LOOK-END', err=repr(e))
    try:
        if gm.pageOpen(lp):
            gm.showLookoutPanel()              # it toggles the page shut
    except Exception:
        pass


LOOKOUT_SECS = float(os.environ.get('ACT_LOOKOUT_SECS', '660'))     # the server's search timeout is 600 s
LOOKOUT_GAME = os.environ.get('ACT_LOOKOUT_GAME', 'skirmish')       # skirmish | teambattle
TABLE_KIND = os.environ.get('ACT_TABLE_KIND', 'blackjack')          # blackjack | poker
TABLE_NEAR = float(os.environ.get('ACT_TABLE_NEAR', '20'))          # ft from a card table after the move
GUILD_NAME = os.environ.get('ACT_GUILD_NAME', '')                   # '' = 'Bot Crew NNNN'
GUILD_LEAVE = os.environ.get('ACT_GUILD_LEAVE', '0') == '1'


# ---------------- 7 lookout

def lookout(H):
    """Lookout -> PvP -> Skirmish, the way a player picks it. Alone on the server nobody else is searching, so the
    proof is: request accepted, a match chance, then the 10-minute "Nobody else is looking" answer. With a second
    searcher: "Match found" (the Yes/No box), which is answered No, and the search is stopped."""
    la, lp = H.la, H.la.guiMgr.lookoutPage
    style = STYLE.get(LOOKOUT_GAME, 0)
    rep, saved, box = {}, [], []
    undo = sysHook(H, box)
    t0 = _now()
    H.ev('LOOK-START', game=LOOKOUT_GAME, style=style, secs=LOOKOUT_SECS, here=H.area())
    try:
        lookoutHooks(H, lp, rep, saved)
        why = yield from lookoutPick(H, lp, PVP, style, rep)
        if why:
            H.ev('FAIL', why=why); return
        yield ('until', lambda: 'acc' in rep or said(box, QUEUED, t0) or 'failed' in rep, 15, 'lookout accepted')
        H.ev('LOOK-QUEUED', accepted='acc' in rep, told=said(box, QUEUED, t0) is not None, chance=rep.get('chance'))
        no = said(box, TABLE_MSG['notyet'], t0) or said(box, TABLE_MSG['busy'], t0)
        if no:
            H.ev('FAIL', why='the match maker said: %s' % no); return
        if 'acc' not in rep and not said(box, QUEUED, t0):
            H.ev('FAIL', why='no answer to the Skirmish request in 15 s', failed=rep.get('failed')); return
        yield ('until', lambda: 'found' in rep or said(box, NOBODY, t0) or
               any(not r for r, t in rep.get('failed', [])), LOOKOUT_SECS, 'match found or nobody else')
        secs = round(_now() - t0)
        if 'found' in rep:
            H.ev('LOOK-ANSWER', how='found', secs=secs, match=rep['found'][0],
                 box=getattr(lp, 'confirmMsg', None) is not None)      # the Yes/No box the client opened
            try:
                lp.quickConfirm(False)          # the box's No: he does not leave for the skirmish
            except Exception as e:
                H.ev('LOOK-NO', err=repr(e))
            H.ev('PASS', what='Lookout Skirmish: Match found after %d s' % secs, how='found', chance=rep.get('chance'))
            return
        if said(box, NOBODY, t0):
            H.ev('LOOK-ANSWER', how='nobody', secs=secs, failed=rep.get('failed'))
            if secs < 540:
                H.ev('FAIL', why='"Nobody else" came after %d s (the timeout is 600 s)' % secs); return
            H.ev('PASS', what='Lookout Skirmish: alone, "Nobody else is looking" after %d s' % secs, how='nobody',
                 chance=rep.get('chance'))
            return
        H.ev('FAIL', why='no Match found and no "Nobody else" answer in %d s' % secs, failed=rep.get('failed'),
             chance=rep.get('chance'))
    finally:
        unwrap(saved)
        undo()
        lookoutClose(H, lp)
        H.ev('LOOK-END', secs=round(_now() - t0))


# ---------------- 8 tablefind

def nearestTable(H):
    """The nearest live card table of any kind on the client and its flat distance, or (None, None)."""
    names = set(getattr(s_cards, 'TABLE_CLS', {}).values()) or {'DistributedBlackjackTable', 'DistributedHoldemTable'}
    live = [o for o in list(H.cr.doId2do.values()) if type(o).__name__ in names]
    if not live:
        return None, None
    best = min(live, key=lambda o: s_story.hdist(H, o))
    return best, round(s_story.hdist(H, best), 1)


def tablefind(H):
    """Lookout -> Parlor Games -> Blackjack (or Poker): the match maker picks the open table with the most pirates,
    the Yes on "Match found" moves him into that tavern 8 ft in front of the table: "Walk up to the table and sit
    down." Already in that tavern: "There's an open seat right here". PASS when he stands within ACT_TABLE_NEAR ft
    of a card table after the answer."""
    la, lp = H.la, H.la.guiMgr.lookoutPage
    style = STYLE.get(TABLE_KIND, 11)
    rep, saved, box = {}, [], []
    undo = sysHook(H, box)
    t0 = _now()
    a0 = H.area()
    H.ev('TABLE-START', kind=TABLE_KIND, style=style, here=a0, gold=s_lanes.gold(H))
    try:
        lookoutHooks(H, lp, rep, saved)
        why = yield from lookoutPick(H, lp, PG, style, rep)
        if why:
            H.ev('FAIL', why=why); return
        yield ('until', lambda: 'found' in rep or tableAnswer(box, t0) or 'failed' in rep, 30, 'table found')
        ans = tableAnswer(box, t0)
        if 'found' not in rep:
            H.ev('TABLE-ANSWER', answer=ans, failed=rep.get('failed'))
            if ans == 'here':
                t, d = nearestTable(H)
                H.ev('TABLE-NEAR', d=d, table=getattr(t, 'doId', None), area=H.area())
                H.ev('PASS', what='find a table: "open seat right here" (already in the tavern)', how='here', d=d)
                return
            H.ev('FAIL', why='no Match found for a %s table: %s' % (TABLE_KIND, ans and TABLE_MSG[ans])); return
        H.ev('LOOK-YES', mode=getattr(lp, 'currMode', None), box=getattr(lp, 'confirmMsg', None) is not None)
        lp.quickConfirm(True, lp.searchParams['type'] if getattr(lp, 'searchParams', None) else None)  # the Yes
        yield ('until', lambda: tableAnswer(box, rep['found'][2]) is not None or
               any(not r for r, t in rep.get('failed', [])), 40, 'table answer')
        ans = tableAnswer(box, rep['found'][2])
        H.ev('TABLE-ANSWER', answer=ans, failed=rep.get('failed'), area=H.area())
        if ans == 'here':
            t, d = nearestTable(H)
            H.ev('TABLE-NEAR', d=d, table=getattr(t, 'doId', None), area=H.area())
            H.ev('PASS', what='find a table: "open seat right here" (already in the tavern)', how='here', d=d)
            return
        if ans != 'walk':
            H.ev('FAIL', why='Yes pressed, the answer was %s' % (ans and TABLE_MSG[ans] or 'nothing in 40 s'),
                 teleportFlags=str(getattr(la, 'teleportFlags', ''))); return
        yield ('until', lambda: H.area()[1] != a0[1] and la.getGameState() == 'LandRoam', 60, 'moved to the tavern')
        a1 = H.area()
        t, d = nearestTable(H)
        H.ev('TABLE-NEAR', d=d, table=getattr(t, 'doId', None), cls=type(t).__name__ if t else None, area=a1,
             moved=a1[1] != a0[1], gs=la.getGameState())
        if a1[1] == a0[1]:
            H.ev('FAIL', why='told to walk up to the table, but not moved in 60 s (still %s)' % a1[2]); return
        if d is None or d > TABLE_NEAR:
            H.ev('FAIL', why='moved to %s, nearest card table %s ft (want <= %d)' % (a1[2], d, TABLE_NEAR)); return
        H.ev('PASS', what='find a table: moved into %s, %s ft from a card table' % (a1[2], d), how='moved', d=d)
    finally:
        unwrap(saved)
        undo()
        lookoutClose(H, lp)
        H.ev('TABLE-END', secs=round(_now() - t0), area=H.area())


# ---------------- 9 guild

def guildNamed(name):
    """Pure: does this guild name look like a chosen name (not none, not the 'Pirate Guild N' stand-in)?"""
    return name not in NO_GUILD and not str(name).startswith('Pirate Guild ')


def guild(H):
    """Guild page -> Create Guild -> OK (guild-create, status "Pirate Guild N"), the name box -> a name
    (guild-name, the nametag's guild line), then the member list with him in it. A pirate already in a guild skips
    the create; a guild already named skips the name (the server names a guild once)."""
    la, gm = H.la, H.la.guiMgr
    gp, mgr = gm.guildPage, getattr(H.cr, 'guildManager', None)
    if mgr is None:
        H.ev('FAIL', why='no guild manager on the client (base.cr.guildManager)'); return
    rep, saved = {}, []
    gid0, name0 = la.getGuildId(), la.getGuildName()
    H.ev('GUILD-START', guildId=gid0, guildName=name0, rank=la.getGuildRank() if hasattr(la, 'getGuildRank') else None)

    def status(guildId, guildName, guildRank):
        rep.setdefault('status', []).append((guildId, guildName, guildRank))
        H.ev('GUILD-STATUS', guildId=guildId, guildName=guildName, rank=guildRank)

    def change(guildName, changeStatus):
        rep['change'] = (guildName, changeStatus)
        H.ev('GUILD-NAMED', name=guildName, status=changeStatus, ok=changeStatus == 1)

    def reject(guildId):
        rep['reject'] = guildId
        H.ev('GUILD-NAMED', ok=False, why='name taken', guildId=guildId)

    def members(memberlist):
        rep['members'] = [list(m) for m in memberlist]
        H.ev('GUILD-MEMBERS', n=len(memberlist), ids=[m[0] for m in memberlist],
             names=[m[1] for m in memberlist], me=any(m[0] == la.doId for m in memberlist))
    wrapInst(mgr, 'guildStatusUpdate', status, saved)
    wrapInst(mgr, 'guildNameChange', change, saved)
    wrapInst(mgr, 'guildNameReject', reject, saved)
    wrapInst(mgr, 'receiveMembers', members, saved)
    try:
        gm.socialPanel.show()
        gm.socialPanel.setPage(gp)
        yield 1
        if gid0 and gid0 > 0:
            H.ev('GUILD-CREATE', skip='already in guild %s' % gid0)
        else:
            gp.createGuild()                       # the Create Guild button
            box = getattr(gp, 'confirmBox', None)
            if box is None:
                H.ev('FAIL', why='Create Guild pressed, no confirm window'); return
            ok = getattr(box, '_PiratesConfirm__handleOk', None)
            H.ev('GUILD-CREATE', box=type(box).__name__)
            if ok is not None:
                ok()                                # the confirm window's OK
            else:
                box.bOk['command']()
            yield ('until', lambda: la.getGuildId() and la.getGuildId() > 0, 20, 'guild made')
            if not (la.getGuildId() and la.getGuildId() > 0):
                H.ev('FAIL', why='OK pressed on Create Guild, no guild after 20 s', status=rep.get('status')); return
        gid = la.getGuildId()
        if guildNamed(la.getGuildName()):
            H.ev('GUILD-NAME', skip='already named %r' % la.getGuildName())
        elif hasattr(la, 'getGuildRank') and la.getGuildRank() not in (None, 3):
            H.ev('GUILD-NAME', skip='rank %s is not the guild master (3): only he names it' % la.getGuildRank())
        else:
            for tries in range(2):
                name = GUILD_NAME or 'Bot Crew %04d' % ((int(_now()) + tries * 7) % 10000)
                if tries and GUILD_NAME:
                    name = '%s %d' % (GUILD_NAME, tries + 1)
                rep.pop('change', None); rep.pop('reject', None)
                gp.renameGuild()                    # the name box
                yield 1
                gp.nameEntry.enterText(name)
                H.ev('GUILD-NAME', name=name, tries=tries + 1)
                gp._typedAName()                    # Enter in the name box
                yield ('until', lambda: 'change' in rep or 'reject' in rep, 20, 'guild name answer')
                if 'reject' not in rep:
                    break
            if rep.get('change', (None, 0))[1] != 1:
                H.ev('FAIL', why='the guild name was not taken: %s' % (repr(rep.get('change')) if 'change' in rep else
                                                                       'taken' if 'reject' in rep else 'no answer'))
                return
            yield ('until', lambda: la.getGuildName() == rep['change'][0], 10, 'nametag guild name')
        H.ev('GUILD-NAMETAG', guildName=la.getGuildName(), guildId=la.getGuildId())
        rep.pop('members', None)
        gp.showGuildMembers()                       # the member list button
        yield ('until', lambda: 'members' in rep, 15, 'guild members')
        mem = rep.get('members')
        if mem is None:
            H.ev('FAIL', why='no member list in 15 s'); return
        mine = [m for m in mem if m[0] == la.doId]
        if not mine:
            H.ev('FAIL', why='the member list (%d) does not have him' % len(mem), ids=[m[0] for m in mem]); return
        if not guildNamed(la.getGuildName()):
            H.ev('FAIL', why='in guild %s, but it has no name (%r)' % (gid, la.getGuildName())); return
        H.ev('PASS', what='guild %s %r: made, named, member list has him (rank %s, %d members)' %
             (gid, la.getGuildName(), mine[0][2], len(mem)), guildId=gid, guildName=la.getGuildName())
    finally:
        unwrap(saved)
        if GUILD_LEAVE and la.getGuildId() and la.getGuildId() > 0:
            try:
                mgr.removeMember(la.doId)
                H.ev('GUILD-LEAVE', guildId=la.getGuildId())
            except Exception as e:
                H.ev('GUILD-LEAVE', err=repr(e))
        try:
            gp.revertGui()
            gm.socialPanel.hide()
        except Exception:
            pass


# ---------------- job 32 (11-19): O'Malley's bread crumb (0284), the trade-up (0261-0265), ~topten (0286).
# Opt-in: ACT_STEPS=omalley,tradeup,topten. O'Malley is Tortuga's shipwright, so 10 and 11 talk to the same man.

TORTUGA = '1156207188.95dzlu'
O_MALLEY = '1165199819.22Shochet'                  # tortugaIsland.py: Shipwright, outside, on the island itself
O_MALLEY_POS = (236.008, -261.67, 1.985)          # island-local
BREADCRUMB = 'ShipPVPBreadCrumb'                  # spanish.ShipPVPBreadCrumb (27001) / its ladder (27000)
KEEP_SHIPS = (100000173, 100000043)               # the server never trades these in (SOLD_SHIP_KEEP_SHIPS)
# a ship in its bottle: 'Off', or '' / None when its owner view came from the database (setGameState is not a db
# field: every ship not sailed since the server restart, or just bought; TRADEUP2 11-22 missed his sloop on 'Off')
PUT_AWAY = ('Off', 'PutAway', '', None)
TRADE_REFUSE = os.environ.get('ACT_TRADE_REFUSE', '1') == '1'    # also ask to trade in ship 100000043: refused
TOPTEN_SECS = float(os.environ.get('ACT_TOPTEN_SECS', '20'))     # s for the UberDOG's answer
TOPTEN_GONE = float(os.environ.get('ACT_TOPTEN_GONE', '20'))     # s more for the 15 s panel to go away


def _game():
    """The game constants the three steps use, in one place (the unit test swaps this function)."""
    from pirates.economy import EconomyGlobals as EG
    from pirates.distributed import InteractGlobals as IG
    from pirates.uberdog.UberDogGlobals import InventoryType
    from pirates.reputation import ReputationGlobals as RG
    from pirates.piratesgui import PiratesGuiGlobals as PGG
    return EG, IG, InventoryType, RG, PGG


def byUid(H, uid):
    """The live object in interest whose world-data uid is uid (an NPC), or None."""
    for o in list(H.cr.doId2do.values()):
        try:
            if hasattr(o, 'getUniqueId') and o.getUniqueId() == uid and hasattr(o, 'getPos') and not o.isEmpty():
                return o
        except Exception:
            pass
    return None


def toNpc(H, step, isl, uid, pos, who):
    """Generator: onto island isl, walk to the NPC's world-data spot, then up to him. -> (npc, None) / (None, why)."""
    if not (yield from s_lanes.onIsland(H, step, isl)):
        return None, 'could not get to the island %s' % isl
    npc = byUid(H, uid)
    if npc is None:
        r = yield from s_lanes.walkTo(H, step, lambda st: s_story.goto(H, st, isl, pos=pos, arrive=TALK * 2,
                                                                         tag='to-' + step), 300, who)
        if r is None:
            return None, 'could not walk to %s\'s spot' % who
        yield ('until', lambda: byUid(H, uid) is not None, 20, who + ' in view')
        npc = byUid(H, uid)
        if npc is None:
            return None, '%s is not in view at his spot' % who
    r = yield from s_lanes.walkTo(H, step, lambda st: True if s_story.near(H, npc, TALK, st, tag=step)
                                  else 'walk-to-' + step, 120, who)
    if r is None:
        return None, 'could not reach %s (%.0f ft)' % (who, s_story.hdist(H, npc))
    H.walk_cancel()
    return npc, None


def talk(H, npc, ready, secs=25.0):
    """Generator: talk to npc as a player (his greeting's arrow pressed for him, as in heal) until ready().
    -> the greeting pages pressed."""
    la = H.la
    sub = la.guiMgr.subtitler
    clicks = []

    def clicker(task):
        try:
            b = sub.confirmButton
            if not b.isHidden() and b['command']:
                clicks.append(str(sub.text['text'])[:40])
                b['command'](*(b['extraArgs'] or []))
        except Exception:
            pass
        return task.again
    H.B.taskMgr.doMethodLater(2.0, clicker, 'act-talk-click')
    try:
        npc.requestInteraction(la.doId)
        yield ('until', ready, secs, 'talk')
    finally:
        H.B.taskMgr.remove('act-talk-click')
    return clicks


def leaveNpc(H, npc, IG):
    """Generator: shut his windows and end the talk the game's way, then back to LandRoam."""
    la = H.la
    for name in ('storeMenuGUI', 'pickShipGUI', 'confirmDialog'):
        g = getattr(npc, name, None)
        if g is None:
            continue
        try:
            (g.closePanel if hasattr(g, 'closePanel') else g.destroy)()
        except Exception:
            pass
        try:
            setattr(npc, name, None)
        except Exception:
            pass
    if la.getGameState() == 'NPCInteract':
        try:
            npc.selectOptionConfirm(IG.CANCEL)
        except Exception as e:
            H.ev('NPC-LEAVE', err=repr(e))
        yield 1
    if la.getGameState() == 'NPCInteract':
        H.ev('NPC-LEAVE', ways=s_story.npcExit(H, npc))
    yield from landRoam(H, 20, 'leave npc')


def menuOn(npc, opt, IG):
    """Pure-ish: (in the menu, lit) for option opt of the NPC's menu (computeOptions, as the heal step)."""
    try:
        ids, states = npc.computeOptions()[:2]
    except Exception:
        return False, None, []
    st = dict(zip(ids, states)).get(opt)
    return opt in ids, st == IG.NORMAL, list(ids)


# ---------------- 10 omalley

def heldBreadCrumb(H):
    try:
        return [q.getQuestId() for q in H.la.getQuests() if BREADCRUMB in str(q.getQuestId())]
    except Exception:
        return []


def offerIds(offers):
    """Pure: the quest (or ladder) ids of a quest offer list."""
    out = []
    for o in offers or []:
        q = getattr(o, 'questId', None)
        if q is None and hasattr(o, 'getQuestId'):
            q = o.getQuestId()
        out.append(str(q))
    return out


def omalley(H):
    """Tortuga, O'Malley: the Ship PvP bread crumb (spanish.ShipPVPBreadCrumb). 0284 shows it only while the district
    has a Sea Battle SiegeManager. Walk to him, log his Quest button / quest mark, talk, press Quest, pick the bread
    crumb, Accept. PASS when it is in his quest list."""
    EG, IG, InventoryType, RG, PGG = _game()
    la = H.la
    district = getattr(H.cr, 'distributedDistrict', None)
    siege = getattr(district, 'siegeManager', None) is not None
    H.ev('OMAL-START', siege=siege, quests=[str(q.getQuestId()) for q in la.getQuests()], here=H.area())
    held = heldBreadCrumb(H)
    if held:
        H.ev('PASS', what='he already holds the bread crumb %s (it is given once)' % held, how='held'); return
    if not siege:
        H.ev('FAIL', why='no Sea Battle SiegeManager on the district: the client hides Ship PvP quests (0284)'); return
    npc, why = yield from toNpc(H, 'omalley', TORTUGA, O_MALLEY, O_MALLEY_POS, "O'Malley")
    if npc is None:
        H.ev('FAIL', why=why, la=H.P(la)); return
    try:
        button, mark = npc.hasQuestOffers(), npc.hasQuestOffersForLocalAvatar()
    except Exception as e:
        button = mark = 'err %r' % e
    H.ev('OMAL-NPC', npc=npc.doId, who=getattr(npc, 'name', ''), d=round(s_story.hdist(H, npc), 1),
         questButton=button, questMark=mark)
    rep, saved = {}, []

    def got(kind):
        def f(offers, *a):
            rep['offers'] = (kind, list(offers or []))
            H.ev('OMAL-OFFER', kind=kind, quests=offerIds(offers))
        return f
    wrapInst(npc, 'setQuestOffer', got('quest'), saved)
    wrapInst(npc, 'setQuestLadderOffer', got('ladder'), saved)
    try:
        clicks = yield from talk(H, npc, lambda: 'offers' in rep or (la.getGameState() == 'NPCInteract' and
                                                                     getattr(npc, 'interactGUI', None) is not None))
        inMenu, lit, ids = menuOn(npc, IG.QUEST, IG)
        H.ev('OMAL-MENU', options=ids, quest=inMenu, lit=lit, offered='offers' in rep, clicks=clicks,
             gs=la.getGameState())
        if 'offers' not in rep:
            if getattr(npc, 'interactGUI', None) is None:
                H.ev('FAIL', why='no menu after the talk (25 s)', gs=la.getGameState()); return
            if not inMenu or not lit:
                H.ev('FAIL', why="O'Malley's menu has no lit Quest button", options=ids, questButton=button,
                     questMark=mark); return
            yield 1.5
            npc.selectOptionConfirm(IG.QUEST)
            yield ('until', lambda: 'offers' in rep, 15, 'quest offer')
        if 'offers' not in rep:
            H.ev('FAIL', why='Quest pressed, no quest offer came'); return
        kind, offers = rep['offers']
        mine = [o for o, q in zip(offers, offerIds(offers)) if BREADCRUMB in q]
        if not mine:
            H.ev('FAIL', why='the bread crumb is not offered', offered=offerIds(offers)); return
        yield ('until', lambda: getattr(npc, 'questMenuGUI', None) is not None, 5, 'quest menu')
        menu = getattr(npc, 'questMenuGUI', None)
        btn = None
        for b in getattr(menu, 'questButtons', None) or []:
            try:
                if (b['extraArgs'] or [None])[0] is mine[0]:
                    btn = b
            except Exception:
                pass
        if btn is None:
            H.ev('FAIL', why='the quest list shows no button for the bread crumb'); return
        H.ev('OMAL-PICK', quest=offerIds(mine)[0], kind=kind)
        btn['command'](*(btn['extraArgs'] or []))      # his pick: the quest's text, then Decline / Accept
        pressed = []
        for _ in range(30):
            if heldBreadCrumb(H):
                break
            yield 1
            p = s_story.clickDialog(H)                  # Next on each page, then the last option: Accept
            if p:
                pressed.append(p)
        yield ('until', lambda: bool(heldBreadCrumb(H)), 15, 'bread crumb in his quests')
        H.ev('OMAL-ACCEPT', pressed=pressed, held=heldBreadCrumb(H))
    finally:
        unwrap(saved)
        yield from leaveNpc(H, npc, IG)
    held = heldBreadCrumb(H)
    if not held:
        H.ev('FAIL', why='Accept pressed, the bread crumb is not in his quest list'); return
    H.ev('PASS', what="O'Malley gave him the Ship PvP bread crumb %s" % held[0], how='accepted')


# ---------------- 11 tradeup

def sailLevel(H, RG, InventoryType):
    inv = H.la.getInventory()
    try:
        return RG.getLevelFromTotalReputation(InventoryType.SailingRep,
                                             inv.getAccumulator(InventoryType.SailingRep))[0]
    except Exception:
        return 0


def shipList(H):
    """[(shipId, class, name, state, cargo)] of his ships whose owner view is in."""
    out = []
    for sid in list(H.la.getInventory().getShipDoIdList()):
        ov = H.cr.getOwnerView(sid)
        out.append((sid, getattr(ov, 'shipClass', None), getattr(ov, 'name', None), getattr(ov, 'state', None),
                    list(getattr(ov, 'cargo', None) or [])))
    return out


def tradeIn(ships, L1):
    """Pure: the Light Sloop he may trade in (put away, not a kept ship), or None."""
    for sid, cls_, name, state, cargo in ships:
        if cls_ == L1 and sid not in KEEP_SHIPS and state in PUT_AWAY:
            return sid
    return None


def tradeCheck(before, after, oldId, L2, price, g0, g1):
    """Pure: the trade-up's proof -> (ok, why, newId). Gold down by price, the old ship gone, one new ship of the next
    class with the old name and cargo (cargo cut to the new hold is still ok: logged)."""
    old = [s for s in before if s[0] == oldId]
    if not old:
        return False, 'the ship %s was not his before' % oldId, None
    old = old[0]
    if any(s[0] == oldId for s in after):
        return False, 'the old ship %s is still in his list' % oldId, None
    new = [s for s in after if s[0] not in [b[0] for b in before]]
    if len(new) != 1:
        return False, '%d new ships, not 1' % len(new), None
    new = new[0]
    if new[1] != L2:
        return False, 'the new ship is class %s, not %s' % (new[1], L2), new[0]
    if new[2] != old[2]:
        return False, 'the name changed: %r -> %r' % (old[2], new[2]), new[0]
    if new[4] != old[4][:len(new[4])] or (old[4] and not new[4]):
        return False, 'the cargo changed: %s -> %s' % (old[4], new[4]), new[0]
    if g0 - g1 != price:
        return False, 'gold %d -> %d, the trade-up costs %d' % (g0, g1, price), new[0]
    return True, 'his %r was traded up for %d gold, name and cargo kept' % (old[2], price), new[0]


def buySloop(H, npc, EG, IG, PGG, L1):
    """Generator: Ships -> the Light Sloop -> Purchase -> the name panel's pick (as s_island.buyShip). -> new id."""
    la = H.la
    s0 = [s[0] for s in shipList(H)]
    resp = {}
    saved = []
    wrapInst(npc, 'makeSaleResponse', lambda r, *a: resp.__setitem__('r', r), saved)
    try:
        heard = []
        for name in ('acceptInteraction', 'rejectInteraction', 'offerOptions', 'playQuestString'):
            if hasattr(npc, name):
                wrapInst(npc, name, lambda *a, _n=name: heard.append(_n), saved)
        for n in range(3):    # a player who gets no menu talks to him again
            clicks = yield from talk(H, npc, lambda: la.getGameState() == 'NPCInteract' and
                                     getattr(npc, 'interactGUI', None) is not None)
            if getattr(npc, 'interactGUI', None) is not None:
                break
            H.ev('TRADE-TALK', n=n, heard=heard[:], clicks=clicks, gs=la.getGameState(),
                 npcState=getattr(npc, 'state', None), interactMode=getattr(npc, 'interactMode', None),
                 d=round(s_story.hdist(H, npc), 1))
            del heard[:]
            yield from leaveNpc(H, npc, IG)
            yield 3
        if getattr(npc, 'interactGUI', None) is None:
            H.ev('TRADE-BUY', why='no menu after the talk'); return None
        yield 1.5
        npc.selectOptionConfirm(IG.SHIPS)
        yield ('until', lambda: getattr(npc, 'storeMenuGUI', None) is not None, 10, 'ship store')
        gui = getattr(npc, 'storeMenuGUI', None)
        if gui is None:
            H.ev('TRADE-BUY', why='Ships pressed, no ship store'); return None
        yield 1
        gui.handleBuyItem([L1, 1], PGG.InventoryAdd)
        yield 1
        gui.handleCommitPurchase()
        yield ('until', lambda: getattr(gui, 'namePanel', None) is not None, 5, 'name panel')
        panel = getattr(gui, 'namePanel', None)
        if panel is None:
            H.ev('TRADE-BUY', why='Purchase pressed, no name panel'); return None
        yield 2
        panel.handleCommit()
        yield ('until', lambda: 'r' in resp, 20, 'sale answer')
        yield ('until', lambda: len(shipList(H)) > len(s0), 20, 'ship in inventory')
    finally:
        unwrap(saved)
        yield from leaveNpc(H, npc, IG)
    new = [s[0] for s in shipList(H) if s[0] not in s0]
    H.ev('TRADE-BUY', result=resp.get('r'), new=new, gold=s_lanes.gold(H))
    if not new:
        return None
    yield ('until', lambda: getattr(H.cr.getOwnerView(new[0]), 'shipClass', None) == L1 and
           getattr(H.cr.getOwnerView(new[0]), 'state', None) in PUT_AWAY, 15, 'new sloop owner view')
    return new[0]


def tradeup(H):
    """O'Malley (Tortuga's shipwright): Upgrade -> his Light Sloop -> Yes. PASS when gold fell by the price (950) and
    the Light Sloop became a Sloop with the same name and cargo (the old one gone from his list). He buys a Light Sloop
    first when he has none put away; Sailing 5 and the gold come from magic words on the test pirate (ACT_GOLD).
    ACT_TRADE_REFUSE=1: ship 100000043 is asked for too (not his, a kept ship): the server must refuse it."""
    EG, IG, InventoryType, RG, PGG = _game()
    la = H.la
    L1 = EG.ItemId.INTERCEPTOR_L1
    L2 = EG.SHIP_UPGRADE_NEXT[L1]
    price = EG.getShipUpgrade(L1)[1]
    need = EG.getItemMinLevel(L2) or 0
    lvl = sailLevel(H, RG, InventoryType)
    ships = shipList(H)
    H.ev('TRADE-START', me=la.doId, gold=s_lanes.gold(H), sailing=lvl, need=need, price=price,
         ships=[list(s[:4]) for s in ships], here=H.area())
    if lvl < need:
        if not GOLD:
            H.ev('FAIL', why='Sailing %d, the Sloop needs %d (ACT_GOLD=1 sets it)' % (lvl, need)); return
        H.ev('MW-LEVEL', why='the Sloop needs Sailing %d' % need, sailing=lvl)
        H.mw('level %d %d' % (InventoryType.SailingRep, need))
        yield ('until', lambda: sailLevel(H, RG, InventoryType) >= need, 10, 'sailing level')
        if sailLevel(H, RG, InventoryType) < need:
            H.ev('FAIL', why='Sailing still %d after the level word' % sailLevel(H, RG, InventoryType)); return
    sid = tradeIn(ships, L1)
    want = price + (0 if sid else EG.getItemCost(L1))
    if s_lanes.gold(H) < want:
        if not GOLD:
            H.ev('FAIL', why='gold %d, the trade needs %d' % (s_lanes.gold(H), want)); return
        H.ev('MW-GOLD', why='the trade-up needs %d' % want, gold=s_lanes.gold(H))
        H.mw('gold %d' % (want + 50))
        yield ('until', lambda: s_lanes.gold(H) >= want, 10, 'trade gold')
    npc, why = yield from toNpc(H, 'tradeup', TORTUGA, O_MALLEY, O_MALLEY_POS, "O'Malley")
    if npc is None:
        H.ev('FAIL', why=why, la=H.P(la)); return
    if sid is None:
        sid = yield from buySloop(H, npc, EG, IG, PGG, L1)
        if sid is None:
            H.ev('FAIL', why='he has no Light Sloop put away and could not buy one'); return
        yield from s_lanes.walkTo(H, 'tradeup', lambda st: True if s_story.near(H, npc, TALK, st, tag='tradeup')
                                  else 'walk-to-tradeup', 60, "O'Malley")
        H.walk_cancel()
    box, rep, saved = [], {}, []
    ok, why, newId = False, 'the trade-up did not finish', None
    undo = sysHook(H, box)
    wrapInst(npc, 'makeSaleResponse', lambda r, *a: rep.setdefault('r', []).append(r), saved)
    try:
        if TRADE_REFUSE:
            yield from talk(H, npc, lambda: getattr(npc, 'interactGUI', None) is not None)
            k = len(rep.get('r', []))
            npc.sendRequestUpgradeShip(KEEP_SHIPS[1], 1)   # not in his picker: sent the way its Yes sends
            yield ('until', lambda: len(rep.get('r', [])) > k, 15, 'refuse answer')
            got = rep.get('r', [])[k:]
            H.ev('TRADE-REFUSE', ship=KEEP_SHIPS[1], result=got, said=[m for t, m in box][-2:])
            if got != [0]:
                H.ev('FAIL', why='ship %d was not refused (makeSaleResponse %s)' % (KEEP_SHIPS[1], got)); return
            yield from leaveNpc(H, npc, IG)
        before = shipList(H)
        clicks = yield from talk(H, npc, lambda: la.getGameState() == 'NPCInteract' and
                                 getattr(npc, 'interactGUI', None) is not None)
        inMenu, lit, ids = menuOn(npc, IG.UPGRADE, IG)
        H.ev('TRADE-MENU', options=ids, upgrade=inMenu, lit=lit, clicks=clicks)
        if not inMenu:
            H.ev('FAIL', why="O'Malley's menu has no Upgrade button (0264 not on this client?)", options=ids); return
        yield 1.5
        npc.selectOptionConfirm(IG.UPGRADE)
        yield ('until', lambda: getattr(npc, 'pickShipGUI', None) is not None, 10, 'ship picker')
        pick = getattr(npc, 'pickShipGUI', None)
        if pick is None:
            H.ev('FAIL', why='Upgrade pressed, no ship picker'); return
        frames = []
        try:
            frames = list(pick.shipFrames[pick.OWN])
        except Exception:
            pass
        fr = [f for f in frames if (f['extraArgs'] or [None])[0] == sid]
        H.ev('TRADE-PICK', ship=sid, frames=len(frames), how='frame' if fr else 'direct')
        if fr:
            fr[0]['command'](*fr[0]['extraArgs'])
        else:
            npc.confirmUpgradeShip(sid)
        yield ('until', lambda: getattr(npc, 'confirmDialog', None) is not None, 10, 'trade confirm')
        dlg = getattr(npc, 'confirmDialog', None)
        if dlg is None:
            H.ev('FAIL', why='ship picked, no Yes/No window', said=H_err[-2:]); return
        try:
            text = str(dlg['text'])
        except Exception:
            text = ''
        g0, k = s_lanes.gold(H), len(rep.get('r', []))
        H.ev('TRADE-CONFIRM', text=text[:160], gold=g0)
        dlg['command'](1)                              # Yes
        yield ('until', lambda: len(rep.get('r', [])) > k, 60, 'trade answer')
        yield ('until', lambda: all(s[0] != sid for s in shipList(H)) and
               any(s[1] == L2 for s in shipList(H) if s[0] not in [b[0] for b in before]), 30, 'the new ship')
        after = shipList(H)
        g1 = s_lanes.gold(H)
        ok, why, newId = tradeCheck(before, after, sid, L2, price, g0, g1)
        H.ev('TRADE-DONE', result=rep.get('r', [])[k:], old=sid, new=newId, gold=[g0, g1], price=price,
             ships=[list(s) for s in after], said=[m for t, m in box][-3:])
    finally:
        unwrap(saved)
        undo()
        yield from leaveNpc(H, npc, IG)
    if not ok:
        H.ev('FAIL', why=why); return
    H.ev('PASS', what=why, old=sid, new=newId)


# ---------------- 12 topten

def panelRows(panel):
    """Pure-ish: the row frames of the Top Ten panel (its children that are not its own title text)."""
    try:
        return [c for c in panel.getChildren() if not c.getName().startswith('text')]   # the slots
    except Exception:
        return []


def topten(H):
    """Type ~topten in chat as an admin pirate (b_setChat, as the chat box does). The client word asks the UberDOG
    (0286); its answer opens the Top Ten panel for 15 s. PASS when the panel shows one row per guild sent, with no
    traceback (none in the magic-word answers, none from the panel), and it goes away again."""
    import traceback as tbm
    la, cr = H.la, H.cr
    gm = la.guiMgr
    access = la.getAdminAccess() if hasattr(la, 'getAdminAccess') else None
    want = getattr(cr, 'wantMagicWords', None)
    mgr = getattr(cr, 'guildManager', None)
    H.ev('TOPTEN-START', access=access, wantMagicWords=bool(want), guildManager=mgr is not None)
    if not want:
        H.ev('FAIL', why='magic words are off on this client: ~topten would be said out loud'); return
    if mgr is None:
        H.ev('FAIL', why='no guild manager'); return
    rep, saved = {}, []
    wrapInst(mgr, 'leaderboardTopTen', lambda stuff, *a: rep.__setitem__('stuff', [list(s) for s in stuff]), saved)
    orig = gm.handleTopTen
    had = 'handleTopTen' in getattr(gm, '__dict__', {})

    def handleTopTen(stuff, *a):
        try:
            r = orig(stuff, *a)
            rep['shown'] = _now()
            return r
        except Exception:
            rep['err'] = tbm.format_exc()[-1200:]
            H.ev('TOPTEN-ERROR', tb=rep['err'])
    gm.handleTopTen = handleTopTen
    saved.append((gm, 'handleTopTen', orig, had))
    k = len(H.resp)
    try:
        la.b_setChat('~topten', 0)
        yield ('until', lambda: 'stuff' in rep or 'err' in rep, TOPTEN_SECS, 'top ten answer')
        resp = [str(r) for r in H.resp[k:]]
        tb = [r for r in resp if 'Traceback' in r or 'Exception' in r] + ([rep['err']] if 'err' in rep else [])
        panel = getattr(gm, 'topTen', None)
        shown = panel is not None and not panel.isEmpty() and not panel.isHidden()
        rows = panelRows(panel) if shown else []
        stuff = rep.get('stuff')
        H.ev('TOPTEN-PANEL', got=stuff is not None, guilds=stuff, shown=shown, rows=len(rows),
             names=[c.getName() for c in rows][:12], resp=resp,
             tracebacks=len(tb))
        if tb:
            H.ev('FAIL', why='a traceback: %s' % tb[0][-300:]); return
        if stuff is None:
            H.ev('FAIL', why='no top ten answer in %d s (access %s, said %s)' % (TOPTEN_SECS, access, resp)); return
        if not shown:
            H.ev('FAIL', why='the answer came, no panel shows'); return
        if len(rows) != len(stuff):
            H.ev('FAIL', why='%d rows for %d guilds' % (len(rows), len(stuff))); return
        yield ('until', lambda: panel.isEmpty() or panel.isHidden(), TOPTEN_GONE, 'top ten goes away')
        gone = panel.isEmpty() or panel.isHidden()
        H.ev('TOPTEN-GONE', gone=gone)
        if not gone:
            H.ev('FAIL', why='the panel did not go away after 15 s'); return
    finally:
        unwrap(saved)
    H.ev('PASS', what='~topten showed the Top Ten panel, %d guilds, no traceback' % len(stuff), guilds=stuff)


FN = {'shop': shop, 'blackjack': blackjack, 'poker': poker, 'crew': crew, 'titles': titles, 'heal': heal,
      'lookout': lookout, 'tablefind': tablefind, 'guild': guild,
      'omalley': omalley, 'tradeup': tradeup, 'topten': topten}


def wideOn(H):
    """WIDE: paths.FAR = 0 for this run (see WIDE). -> the old FAR, for wideOff()."""
    paths = getattr(s_story, 'paths', None)
    if paths is None or not hasattr(paths, 'FAR'):
        return None                            # no planner (an offline test's fake s_story): nothing to widen
    old = paths.FAR
    if WIDE:
        paths.FAR = 0.0
        H.ev('ACT-WIDE', far=[old, paths.FAR], why='short walks with no route in the small box get the wide search')
    return old


def wideOff(old):
    if old is not None:
        s_story.paths.FAR = old


def run(H):
    la = H.la
    H.ev('ACT-START', me=la.doId, steps=STEPS, broke=BROKE, gold=s_lanes.gold(H), here=H.area())
    if la.doId == HOST:
        H.ev('FAIL', why="logged in as Host's pirate %d: this run uses only the test pirate" % HOST); return
    bad = [s for s in STEPS if s not in FN]
    if bad:
        H.ev('FAIL', why='unknown ACT_STEPS %s' % bad); return
    results = []
    oldFar = wideOn(H)
    try:
        for n, name in enumerate(ORDER, 1):
            if name not in STEPS:
                continue
            got = yield from capture(H, FN[name](H), n, name)
            ok = got['kind'] == 'PASS'
            why = got['kw'].get('what' if ok else 'why') or ('no verdict' if got['kind'] is None else '')
            H.ev('ACT-STEP', n=n, name=name, ok=ok, why=why)
            results.append((n, name, ok, why))
            H.walk_cancel()
            if la.getGameState() != 'LandRoam':
                yield from landRoam(H, 30, 'between steps')
    finally:
        wideOff(oldFar)
    allOk, text = summary(results)
    H.ev('PASS' if allOk else 'FAIL', **{('what' if allOk else 'why'): text,
                                         'steps': [list(r) for r in results]})
