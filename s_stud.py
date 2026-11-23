"""7 STUD (games, 11-21): the live check for 0421 (recon's 7stud-0001: Port Royal tavern 2 and the Tortuga tavern
tables turn from Hold'em to 7 Card Stud). One bot sits at the 7 Stud table and plays a hand to the showdown like a
player who only ever presses Check/Call.

Walk: Port Royal (STUD_FROM) -> the tavern 2 table (s_story.cardTable, with a '7Stud' kind added to s_cards in this
run only) -> sit (gold by magic word when short) -> on each turn press the Check/Call button -> at the end of each hand
log the cards, the winner and the gold -> after a showdown hand (or STUD_HANDS hands) press Leave.

PASS = a hand reached the showdown with 7 cards in his hand, a seat was paid (totalWinnings > 0), his gold moved the
right way for that hand (won: up, by no more than the pot; lost: down), and he stood up again (LandRoam).
FAIL before 0421 is live: the room has a Hold'em table, so no 7 Stud table is found.
Never Host's pirate (a run logged in as 100000170 FAILs at once).

Env: STUD_FROM (Port Royal), STUD_HANDS (4), STUD_SECS (480), STUD_GOLD (1 = magic word 'gold' when short).
Lines: STUD-START/SEAT/TURN/STATE/HAND/LEAVE/END, MW-GOLD, PAGE-SHOT."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402
import s_story   # noqa: E402
import s_cards   # noqa: E402
import s_pages   # noqa: E402

HOST = 100000170
FROM = os.environ.get('STUD_FROM', s_lanes.PR)
HANDS = int(os.environ.get('STUD_HANDS', '4'))
SECS = float(os.environ.get('STUD_SECS', '480'))
GOLD = os.environ.get('STUD_GOLD', '1') == '1'
KIND = '7Stud'
STUD_ROWS = [
    (KIND, 1, '1169798737.63Shochet', '1153419634.08dzlu0', (-9, 23, 1)),      # Port Royal tavern 2 (0421)
    (KIND, 1, '1190740736.0dxschafe1', '1156207773.33dzlu0', (-16, -7, 1)),    # Tortuga tavern (0421)
]


def addKind():
    """This run only: s_cards knows the 7 Stud tables, so s_story.cardTable can walk to one."""
    s_cards.TABLE_CLS[KIND] = 'Distributed7StudTable'
    if not any(r[0] == KIND for r in s_cards.TABLES):
        s_cards.TABLES.extend(STUD_ROWS)


def hook(t, log):
    """Wrap the table's own field handlers: every hand and table state the server sends is kept in log."""
    orig = {n: getattr(t, n) for n in ('setLocalAvatarHand', 'setTableState')}

    def hand(h, _o=orig['setLocalAvatarHand']):
        log['hand'] = list(h)
        log['maxHand'] = max(log.get('maxHand', 0), len(h))
        return _o(h)

    def state(rnd, button, community, hands, wins, chips, _o=orig['setTableState']):
        log['states'].append({'t': time.time(), 'round': rnd, 'hands': [len(x) for x in hands], 'wins': list(wins),
                              'chips': list(chips)})
        return _o(rnd, button, community, hands, wins, chips)
    t.setLocalAvatarHand = hand
    t.setTableState = state
    return orig


def unhook(t, orig):
    for n, f in orig.items():
        try:
            setattr(t, n, f)
        except Exception:
            pass


def run(H):
    from pirates.minigame import PlayingCardGlobals as PCG
    la = H.la
    H.ev('STUD-START', me=la.doId, frm=FROM, gold=s_lanes.gold(H), here=H.area())
    if la.doId == HOST:
        H.ev('FAIL', why="logged in as Host's pirate %d: this run uses only a test pirate" % HOST); return
    addKind()
    if not (yield from s_lanes.onIsland(H, 'stud', FROM)):
        H.ev('FAIL', why='could not get to %s' % FROM, area=H.area()); return
    r = yield from s_lanes.walkTo(H, 'stud', lambda st: s_story.cardTable(H, KIND, st), 300, 'a 7 Stud table')
    if not isinstance(r, tuple):
        here = [type(o).__name__ for o in list(H.cr.doId2do.values()) if 'Table' in type(o).__name__]
        H.ev('FAIL', why='could not walk to a 7 Stud table (is 0421 live?)', tables=sorted(set(here)), area=H.area())
        return
    t = H.cr.doId2do.get(r[1])
    if t is None:
        H.ev('FAIL', why='the table left the client', table=r[1]); return
    ante = list(getattr(t, 'anteList', None) or [5, 10, 20])
    need = 10 * (ante[2] if len(ante) >= 3 else ante[0]) + 300     # the seat minimum, and enough to call to the end
    if s_lanes.gold(H) < need and GOLD:
        H.ev('MW-GOLD', why='the test pirate has %d gold, 7 Stud needs %d' % (s_lanes.gold(H), need))
        H.mw('gold %d' % (need + 200))
        yield ('until', lambda: s_lanes.gold(H) >= need, 10, 'stud gold')
    if s_lanes.gold(H) < need:
        H.ev('FAIL', why='gold %d below what the table needs (%d)' % (s_lanes.gold(H), need)); return
    log = {'states': []}
    orig = hook(t, log)
    try:
        H.walk_cancel()
        t.requestInteraction(la.doId)
        yield ('until', lambda: t.isLocalAvatarSeated() and getattr(t, 'gui', None) is not None, 20, 'stud sit')
        if not (t.isLocalAvatarSeated() and getattr(t, 'gui', None) is not None):
            try:
                t.deleteRequestDialogs()
            except Exception:
                pass
            H.ev('FAIL', why='not seated after 20 s (table full?)', gs=la.getGameState()); return
        H.ev('STUD-SEAT', table=t.doId, cls=type(t).__name__, seat=t.localAvatarSeat, ante=ante,
             rounds=getattr(t, 'numRounds', None), maxHandCards=getattr(t, 'maxHandCards', None), gold=s_lanes.gold(H))
        hands, best, t0 = [], None, time.time()
        g0, seen = s_lanes.gold(H), len(log['states'])
        while time.time() - t0 < SECS and len(hands) < HANDS and best is None:
            if not t.isLocalAvatarSeated() or getattr(t, 'gui', None) is None:
                H.ev('STUD-END', why='stood up by the table', hands=len(hands)); break
            if getattr(t, 'endOfHand', False) and len(log['states']) > seen:
                end = log['states'][-1]
                yield 2.0                                          # the payout's gold update arrives after the state
                g1 = s_lanes.gold(H)
                seat = t.localAvatarSeat
                mine = end['wins'][seat] if seat is not None and seat < len(end['wins']) else None
                show = end['round'] == getattr(t, 'numRounds', 6)
                # his seat's cards from the table state: setLocalAvatarHand carries only the face-down ones (3 of 7)
                cards = end['hands'][seat] if seat is not None and seat < len(end['hands']) else 0
                h = {'n': len(hands) + 1, 'round': end['round'], 'showdown': show, 'myCards': cards,
                     'downCards': len(log.get('hand', [])),
                     'maxCards': log.get('maxHand', 0), 'cardsPerSeat': end['hands'], 'wins': end['wins'],
                     'mine': mine, 'goldBefore': g0, 'goldAfter': g1, 'delta': g1 - g0}
                H.ev('STUD-HAND', **h)
                if h['n'] == 1 or show:
                    s_pages.shot(H, 'stud-hand%d' % h['n'])
                hands.append(h)
                if show and h['myCards'] == 7:
                    best = h
                    break
                yield ('until', lambda: not getattr(t, 'endOfHand', False) or not t.isLocalAvatarSeated(), 20,
                       'stud next hand')
                g0, seen = g1, len(log['states'])                 # before the next hand's ante leaves his pocket
                continue
            gui = t.gui
            pb, dr = getattr(gui, 'passButton', None), getattr(gui, 'disableReason', None)
            if s_cards._normal(pb) and (dr is None or dr.isHidden()):
                args = list(pb['extraArgs'] or [PCG.CheckCall])
                H.ev('STUD-TURN', round=getattr(t, 'round', None), args=args, cards=len(log.get('hand', [])),
                     gold=s_lanes.gold(H))
                gui.playerAction(*args)
                yield 1.0
                continue
            yield 0.5
        if t.isLocalAvatarSeated():
            try:
                t.guiCallback(PCG.Leave)
            except Exception as e:
                H.ev('STUD-LEAVE', err=repr(e))
            yield ('until', lambda: not t.isLocalAvatarSeated() and la.getGameState() == 'LandRoam', 30,
                   'stud stand up')
        left = not t.isLocalAvatarSeated() and la.getGameState() == 'LandRoam'
        H.ev('STUD-LEAVE', left=left, gs=la.getGameState(), gold=s_lanes.gold(H), hands=len(hands))
    finally:
        unhook(t, orig)
    if best is None:
        H.ev('FAIL', why='no hand reached the showdown with 7 cards in %d hand(s) / %d s' % (len(hands), SECS),
             hands=hands); return
    paid = [w for w in best['wins'] if w > 0]
    if not paid:
        H.ev('FAIL', why='showdown with 7 cards, but no seat was paid', hand=best); return
    if best['mine'] is not None and best['mine'] > 0:
        goldOk, how = 0 < best['delta'] <= best['mine'], 'won %d, gold %+d' % (best['mine'], best['delta'])
    else:
        goldOk, how = best['delta'] < 0, 'lost, gold %+d' % best['delta']
    if not goldOk:
        H.ev('FAIL', why='gold did not move the right way for the hand (%s)' % how, hand=best); return
    if not left:
        H.ev('FAIL', why='played to the showdown but did not stand up (gs %s)' % la.getGameState()); return
    H.ev('PASS', what='7 Stud hand to the showdown: 7 cards, seat paid %d, %s, stood up' % (paid[0], how),
         hands=len(hands))
