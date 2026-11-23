"""PARLOR (pir-bot, 11-17): play one hand at a parlor card table, like a player. For the lanes that need a card game.

Walk to the nearest table of the kind (s_story.cardTable: through the tavern door; the Port Royal blackjack table is
in the tavern), press its interact to sit, play ONE hand with the table's own buttons, then press Leave.
Blackjack: the bid slider at the table's minimum bid (2 x its multiplier), Bid, then Hit below 17, else Stay.
Hold'em (PARLOR_KIND=Holdem, the table seats only 200+ gold): Check / Call each round until the hand ends.
The hand is over when the table says so: blackjack's setHandResults (the dealer's result for every seat; the bid is
taken from the gold when it is placed, so a gold change alone is not the end), Hold'em's endOfHand (setTableState at
the last round, or one player left). Fallback for blackjack: the Bid button comes back after cards were played.

Lines: PARLOR-START, STAGE step=parlor what=at-island / at-table / seated / bid / played / hand-over / left,
PARLOR-BID, PARLOR-PLAY (hand, value, hit/stay), PARLOR-RESULT (blackjack), PARLOR-HAND (gold before/after, delta), PARLOR-LEAVE, PASS / FAIL.
PASS = one hand finished at the table and the pirate stood up again (LandRoam).
env: PARLOR_KIND (Blackjack), PARLOR_FROM (island, default Port Royal), PARLOR_SECS (one hand's limit, 240),
PARLOR_RESERVE (gold never bid, 0), PARLOR_GOLD=1 (one 'gold <n>' magic word, MW-GOLD, when below the minimum)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402
import s_story   # noqa: E402
import s_cards   # noqa: E402

KIND = os.environ.get('PARLOR_KIND', 'Blackjack')
FROM = os.environ.get('PARLOR_FROM', s_lanes.PR)
SECS = float(os.environ.get('PARLOR_SECS', '240'))
RESERVE = int(os.environ.get('PARLOR_RESERVE', '0'))
WANT_GOLD = os.environ.get('PARLOR_GOLD', '0') == '1'
HOLDEM_MIN = 200


def minBid(mult):
    """Pure: the blackjack table's lowest bid (the slider's left end)."""
    return 2 * (mult or 1)


def bjMove(value):
    """Pure: the move for a blackjack hand worth value: 'hit' below 17, else 'stay'."""
    return 'hit' if value < 17 else 'stay'


def needGold(kind, mult, reserve):
    """Pure: the gold the pirate needs in pocket to sit and play one hand."""
    return (HOLDEM_MIN if kind == 'Holdem' else minBid(mult)) + reserve


def run(H):
    from pirates.minigame import PlayingCardGlobals as PCG
    la = H.la
    H.ev('PARLOR-START', kind=KIND, frm=FROM, gold=s_lanes.gold(H), here=H.area())
    if not (yield from s_lanes.onIsland(H, 'parlor', FROM)):
        H.ev('FAIL', why='could not get to %s' % FROM, area=H.area()); return
    s_lanes.stage(H, 'parlor', 'at-island', island=FROM)
    r = yield from s_lanes.walkTo(H, 'parlor', lambda st: s_story.cardTable(H, KIND, st), 300, 'a %s table' % KIND)
    if not isinstance(r, tuple):
        H.ev('FAIL', why='could not walk to a %s table' % KIND, la=H.P(la), area=H.area()); return
    doId = r[1]
    t = H.cr.doId2do.get(doId)
    if t is None:
        H.ev('FAIL', why='the table left the client', table=doId); return
    mult = getattr(t, 'betMultiplier', 1) or 1
    s_lanes.stage(H, 'parlor', 'at-table', table=doId, uid=getattr(t, 'uniqueId', None), mult=mult,
                  d=round(s_story.hdist(H, t), 1))
    need = needGold(KIND, mult, RESERVE)
    if s_lanes.gold(H) < need and WANT_GOLD:
        H.ev('MW-GOLD', why='the test pirate has %d gold, the table needs %d' % (s_lanes.gold(H), need))
        H.mw('gold %d' % (need + 20))
        yield ('until', lambda: s_lanes.gold(H) >= need, 10, 'parlor gold')
    if s_lanes.gold(H) < need:
        H.ev('FAIL', why='gold %d below what the table needs (%d)' % (s_lanes.gold(H), need)); return

    # sit: the interact on the table's "sit down" prompt
    H.walk_cancel()
    t.requestInteraction(la.doId)
    yield ('until', lambda: t.isLocalAvatarSeated() and getattr(t, 'gui', None) is not None, 20, 'sit at table')
    if not (t.isLocalAvatarSeated() and getattr(t, 'gui', None) is not None):
        try:
            t.deleteRequestDialogs()
        except Exception:
            pass
        H.ev('FAIL', why='not seated after 20 s (table full?)', gs=la.getGameState()); return
    s_lanes.stage(H, 'parlor', 'seated', table=doId)

    res = {}
    hook = 'setHandResults' if KIND == 'Blackjack' else None
    origHR = getattr(t, hook) if hook else None
    if hook:
        def hr(results, *a):
            res['r'] = list(results)
            try:
                res['mine'] = results[t.localAvatarSeat]
            except Exception:
                pass
            H.ev('PARLOR-RESULT', results=list(results), mine=res.get('mine'), seat=getattr(t, 'localAvatarSeat', None))
            return origHR(results, *a)
        setattr(t, hook, hr)
    g0 = s_lanes.gold(H)
    t0 = time.time()
    bid, played, over, moves = None, False, None, 0
    while time.time() - t0 < SECS:
        if not t.isLocalAvatarSeated() or getattr(t, 'gui', None) is None:
            over = 'stood-up'
            break
        g = s_lanes.gold(H)
        if bid is not None and 'r' in res:
            over = 'result'
            yield 2                         # the payout lands in the gold just after the result
            break
        if KIND != 'Blackjack' and played and getattr(t, 'endOfHand', False):
            over = 'end-of-hand'
            yield 2
            break
        gui = t.gui
        if KIND == 'Blackjack':
            if s_cards._normal(getattr(gui, 'bidButton', None)):
                if played:
                    over = 'push'           # the bid came back after cards, gold unchanged
                    break
                if bid is None:
                    bid = minBid(mult)
                    try:
                        gui.bidSlider['value'] = min(1.0, bid / (50.0 * mult))
                    except Exception:
                        pass
                    gui.bidAmount = bid
                    H.ev('PARLOR-BID', bid=bid, gold=g, mult=mult)
                    s_lanes.stage(H, 'parlor', 'bid', bid=bid)
                    gui.playerAction(PCG.Bid)
            elif _hitReady(gui):
                try:
                    hand = list(t.getLocalAvatarHand() or [])
                except Exception:
                    hand = []
                v = PCG.getBlackjackHandValue(hand)
                m = bjMove(v)
                moves += 1
                H.ev('PARLOR-PLAY', hand=hand, value=v, a=m, n=moves)
                if not played:
                    s_lanes.stage(H, 'parlor', 'played', value=v, a=m)
                played = True
                gui.playerAction(PCG.Hit if m == 'hit' else PCG.Stay)
        else:
            pb = getattr(gui, 'passButton', None)
            dr = getattr(gui, 'disableReason', None)
            if _normal(pb) and (dr is None or dr.isHidden()):
                args = list(pb['extraArgs'] or [PCG.CheckCall])
                moves += 1
                H.ev('PARLOR-PLAY', a='check' if args[0] == PCG.Check else 'call', round=getattr(t, 'round', None), n=moves)
                if not played:
                    s_lanes.stage(H, 'parlor', 'played', a='check-call')
                played, bid = True, bid or 0
                gui.playerAction(*args)
        yield 0.5
    if hook:
        setattr(t, hook, origHR)
    g1 = s_lanes.gold(H)
    H.ev('PARLOR-HAND', over=over, goldBefore=g0, goldAfter=g1, delta=g1 - g0, bid=bid, moves=moves,
         secs=round(time.time() - t0))
    if over in ('result', 'push', 'end-of-hand'):
        s_lanes.stage(H, 'parlor', 'hand-over', how=over, delta=g1 - g0)
    if t.isLocalAvatarSeated():
        H.ev('PARLOR-LEAVE', gold=g1)
        try:
            t.guiCallback(PCG.Leave)
        except Exception as e:
            H.ev('PARLOR-LEAVE', err=repr(e))
        yield ('until', lambda: not t.isLocalAvatarSeated() and la.getGameState() == 'LandRoam', 30, 'stand up')
    left = not t.isLocalAvatarSeated() and la.getGameState() == 'LandRoam'
    s_lanes.stage(H, 'parlor', 'left', ok=left)
    if over not in ('result', 'push', 'end-of-hand'):
        H.ev('FAIL', why='the hand did not finish (%s) in %d s' % (over or 'time', SECS), played=played, bid=bid); return
    if not left:
        H.ev('FAIL', why='hand played but the pirate did not stand up (gs %s)' % la.getGameState()); return
    H.ev('PASS', what='played one hand of %s' % KIND, how=over, delta=g1 - g0, moves=moves)


def _normal(b):
    return s_cards._normal(b)


def _hitReady(gui):
    return s_cards._normal(getattr(gui, 'hitButton', None))
