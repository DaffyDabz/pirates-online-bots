"""Card-table and boss-battle quests for s_story: Blackjack / Poker tasks are played at a tavern table like a player
(walk in, sit with the interact, press the table's own Bid / Hit / Stay / Check buttons) until the task's gold goal
counts; the Black Pearl boss battle (c3.7recoverPearl) is entered by its map, stage by stage (gated: STORY_BOSS=1).

Server facts this rests on (server tree, read 2026-11-16):
- Blackjack: DistributedBlackjackTableAI credits QuestManagerAI.blackjackHandWon(av, net) on every hand with a net win
  (a win pays the bid, a blackjack 1.5x). Min bid 2 x the table's bet multiplier. A bid not made in 13 s is the
  minimum, a card not asked for in 20 s is a stay.
- Poker (Holdem): DistributedPokerTableAI credits pokerHandWon(av, pot) on a won pot; a sit needs 200 gold. Its
  _payoutWinner then calls getAccumulators().get() on a list: the AI district dies on the first win (proposal A).
  Default off: STORY_POKER=1 once that fix is on the server.
- Boss: TreasureMapBlackPearlAI.enterReward calls bossBattleCompleted for every participant. Since server patches
  0031-0042 the c3.6 reward gives the Black Pearl map (again at every login on the quest), its Play Now works alone
  (0033), stage one waits until we are in (0036), stage two ends when its ships are at 0 hp (0031), and a win sends
  the result and us home (0039, 0042). The bot presses Play Now (STORY_BOSS_WAY=map), then ends each stage with the
  test word that does what play would (STAGES: ships, barricades, Goliath down), so the server's own checks move the
  fight on. Boarding and the cannon fights at sea are not played. Fallbacks, each logged with why: ~blackpearlai,
  ~bpstate Reward (STORY_BOSS_FIGHT=reward is the old way).

Log words: CARDS-SIT CARDS-BID CARDS-PLAY CARDS-HAND CARDS-DONE CARDS-LEAVE CARDS-FAIL,
BOSS-MAP BOSS-MW BOSS-ENTER BOSS-STAGE BOSS-CREDIT BOSS-LEAVE BOSS-FAIL."""
import os, time

POKER = os.environ.get('STORY_POKER', '0') == '1'
BLACKJACK = os.environ.get('STORY_BLACKJACK', '1') == '1'
BOSS = os.environ.get('STORY_BOSS', '0') == '1'
CARD_SECS = float(os.environ.get('STORY_CARD_SECS', '600'))     # longest one sit at a table
RESERVE = int(os.environ.get('STORY_CARD_RESERVE', '100'))      # gold never bid away (bribes later in the story)
SIT_FT = 7.0                                                    # ft from the table centre to press the interact
TYPES = {'BlackjackTaskDNA': 'Blackjack', 'PokerTaskDNA': 'Holdem'}
BJ_HANDS = int(os.environ.get('STORY_BJ_HANDS', '3'))           # job 33: earn enough for this many full bids first
BROKE_MAX = int(os.environ.get('STORY_BJ_BROKE', '2'))          # job 33: lost it all this often -> give up (skip)

# every parlor table in the world the server builds (worldData, PvP islands left out):
# (kind, bet multiplier, table uid, interior uid = quest_spots.json area, interior-local pos)
TABLES = [
    ('Blackjack', 1, '1169797640.63Shochet', '1153419689.81dzlu0', (-27, 12, 1)),      # Port Royal tavern
    ('Holdem', 1, '1192039708.89dxschafe', '1153419689.81dzlu0', (-20, -5, 1)),
    ('Holdem', 1, '1169798737.63Shochet', '1153419634.08dzlu0', (-9, 23, 1)),           # Port Royal tavern 2
    ('Blackjack', 1, '1169797798.14Shochet', '1156279370.48dzlu0', (-40, -2, 1)),      # Tortuga tavern 2
    ('Holdem', 1, '1219279841.27WDIG', '1156279370.48dzlu0', (-20, -6, 1)),
    ('Holdem', 1, '1190740736.0dxschafe1', '1156207773.33dzlu0', (-16, -7, 1)),        # Tortuga tavern
    ('Blackjack', 5, '1190743212.17dxschafe', '1190741504.0dxschafe0', (-17, -7, 1)),  # Cuba tavern
    ('Holdem', 5, '1190743205.17dxschafe', '1190741504.0dxschafe0', (-40, -7, 1)),
    ('Blackjack', 10, '1190745843.48dxschafe', '1153435103.16dzlu0', (-6, 0, 1)),      # Padres Del Fuego tavern 1
    ('Blackjack', 10, '1190746009.86dxschafe', '1153434762.53dzlu0', (-40, -4, 1)),    # Padres Del Fuego tavern 2
    ('Holdem', 10, '1190746177.47dxschafe', '1153434762.53dzlu0', (-17, -8, 1)),
]
TABLE_CLS = {'Blackjack': 'DistributedBlackjackTable', 'Holdem': 'DistributedHoldemTable'}


def playTypes():
    """Task types s_story plays here (the rest stay in its SKIP_TYPES)."""
    return tuple(t for t, on in (('BlackjackTaskDNA', BLACKJACK), ('PokerTaskDNA', POKER), ('BossBattleTaskDNA', BOSS)) if on)


def tablesOf(kind):
    return [t for t in TABLES if t[0] == kind]


def tableHere(H, kind, here):
    """The live table of that kind in this interior (here = its area uid), nearest first, or None."""
    uids = set(t[2] for t in tablesOf(kind) if t[3] == here)
    if not uids:
        return None
    live = [o for o in list(H.cr.doId2do.values()) if type(o).__name__ == TABLE_CLS[kind] and getattr(o, 'uniqueId', None) in uids]
    if not live:
        return None
    lp = H.la.getPos(H.render)
    return min(live, key=lambda o: (o.getPos(H.render) - lp).length())


def prog(H, qid):
    """(progress, goal gold, complete) of quest qid's card task, or None once the quest is gone."""
    for q in H.la.getQuests():
        if q.getQuestId() == qid:
            try:
                s = q.getTaskStates()[0]
                goal = getattr(s, 'goal', 0) or getattr(q.questDNA.getTasks()[0], 'gold', 0) or 0
                return (getattr(s, 'progress', 0) or 0, goal, q.isComplete())
            except Exception:
                return (0, 0, q.isComplete())
    return None


def gold(H):
    inv = H.la.getInventory()
    return inv.getGoldInPocket() if inv else 0


def bjBid(t, need, have):
    """Blackjack bid: enough to finish the task with one win, in the bid slider's steps (5 gold, at most 50 x the
    multiplier), never into the RESERVE. None = not enough gold to play."""
    mult = getattr(t, 'betMultiplier', 1) or 1
    lo, hi = 2 * mult, 50 * mult
    bid = min(hi, max(lo, -(-need // 5) * 5))
    room = have - RESERVE
    if room < lo:
        return None
    if bid > room:
        bid = max(lo, room // 5 * 5)
    return int(bid)


def stake(need, mult=1):
    """job 33: the bid bjBid makes with gold to spare: the gold still to win in one hand, in 5s, within the table."""
    return int(min(50 * mult, max(2 * mult, -(-max(1, need) // 5) * 5)))


def betPrice(goal, done=0, mult=1, hands=None, reserve=None):
    """job 33: the gold to hold before sitting at blackjack for a task that wins `goal` (done so far): the RESERVE
    (never bid) plus `hands` full bids, so one lost hand does not end the sit. c3r2r2.4blackjack (win 40): 100 +
    3 x 40 = 220."""
    hands = BJ_HANDS if hands is None else hands
    reserve = RESERVE if reserve is None else reserve
    return reserve + hands * stake(goal - done, mult)


def cards0289():
    """job 33: True when this client has server patch 0289 (PlayingCard.setValue makes a whole-number suit; without
    it the first card dealt kills the game with KeyError in PlayingCardGlobals.getImage). Runs the client's own
    setValue on a stand-in card. None = the card module did not load (not judged)."""
    try:
        from pirates.minigame.PlayingCard import PlayingCardBase
    except Exception:
        return None

    class Card:
        def setImage(self):
            pass

        def turnDown(self):
            pass
    c = Card()
    try:
        PlayingCardBase.setValue(c, 27)          # the 2 of the third suit: 27 // 13 = 2, 27 / 13 = 2.07
    except Exception:
        return False
    return type(c.suit) is int and c.suit == 2


def _normal(b):
    from direct.gui import DirectGuiGlobals as DGG
    try:
        return b is not None and not b.isHidden() and b['state'] == DGG.NORMAL
    except Exception:
        return False


def play(H, doId, qid, kind):
    """Generator: sit at table doId (the interact, like a player) and play hands with the table's own buttons until
    quest qid's gold goal counts, CARD_SECS pass, or the gold runs out; then stand up. -> what happened: 'done',
    'time', 'broke' (job 33: lost down to the reserve mid-sit, s_story earns and sits again) or 'give-up <why>'
    (s_story skips the quest then)."""
    from pirates.minigame import PlayingCardGlobals as PCG
    t = H.cr.doId2do.get(doId)
    if t is None:
        return 'give-up table gone'
    p0 = prog(H, qid)
    if p0 is None:
        return 'done'
    have = gold(H)
    need0 = max(1, p0[1] - p0[0])
    if kind == 'Blackjack' and bjBid(t, need0, have) is None:
        H.ev('CARDS-FAIL', q=qid, why='gold %d: below the table minimum + reserve %d' % (have, RESERVE))
        return 'give-up no gold'
    if kind == 'Holdem' and have < 200:
        H.ev('CARDS-FAIL', q=qid, why='gold %d: a poker table seats only 200+' % have)
        return 'give-up no gold'
    H.walk_cancel()
    H.ev('CARDS-SIT', q=qid, kind=kind, table=getattr(t, 'uniqueId', None), doId=doId, gold=have, prog=p0,
         mult=getattr(t, 'betMultiplier', None), d=round((t.getPos(H.render) - H.la.getPos(H.render)).length(), 1))
    t.requestInteraction(H.la.doId)          # the interact key on the table's "sit down" prompt
    yield ('until', lambda: t.isLocalAvatarSeated() and getattr(t, 'gui', None) is not None, 20, 'sit at table')
    if not (t.isLocalAvatarSeated() and getattr(t, 'gui', None) is not None):
        try:
            t.deleteRequestDialogs()          # a "table is full" box, if that was the answer
        except Exception:
            pass
        H.ev('CARDS-FAIL', q=qid, why='not seated after 20 s', gs=H.la.getGameState())
        return 'give-up not seated'
    t_end = time.time() + CARD_SECS
    last, hands, r = (p0, have), 0, 'time'
    while time.time() < t_end:
        p = prog(H, qid)
        g = gold(H)
        if (p, g) != last:
            hands += 1
            H.ev('CARDS-HAND', q=qid, prog=p, gold=g, goldDelta=g - last[1], n=hands)
            last = (p, g)
        if p is None or p[2]:
            r = 'done'
            H.ev('CARDS-DONE', q=qid, prog=p, gold=g, hands=hands)
            break
        if not t.isLocalAvatarSeated() or getattr(t, 'gui', None) is None:
            r = 'give-up stood up'
            H.ev('CARDS-FAIL', q=qid, why='no longer seated', gs=H.la.getGameState())
            break
        gui = t.gui
        if kind == 'Blackjack':
            if _normal(getattr(gui, 'bidButton', None)):
                bid = bjBid(t, max(1, p[1] - p[0]), g)
                if bid is None:
                    # job 33: lost down to the RESERVE mid-sit: stand up; s_story earns more and sits again
                    r = 'broke'
                    H.ev('CARDS-FAIL', q=qid, why='gold %d: below the table minimum + reserve %d (broke: earn, then '
                         'sit again)' % (g, RESERVE))
                    break
                mult = getattr(t, 'betMultiplier', 1) or 1
                try:
                    gui.bidSlider['value'] = min(1.0, bid / (50.0 * mult))    # the bid slider, like dragging it
                except Exception:
                    pass
                gui.bidAmount = bid                                           # what the slider's own update sets
                H.ev('CARDS-BID', q=qid, bid=bid, gold=g, need=p[1] - p[0])
                gui.playerAction(PCG.Bid)
            elif _normal(getattr(gui, 'hitButton', None)):
                try:
                    hand = list(t.getLocalAvatarHand() or [])
                except Exception:
                    hand = []
                v = PCG.getBlackjackHandValue(hand)
                a = PCG.Hit if v < 17 else PCG.Stay
                H.ev('CARDS-PLAY', q=qid, hand=hand, value=v, a='hit' if a == PCG.Hit else 'stay')
                gui.playerAction(a)
        else:
            pb = getattr(gui, 'passButton', None)
            dr = getattr(gui, 'disableReason', None)
            if _normal(pb) and (dr is None or dr.isHidden()):
                args = list(pb['extraArgs'] or [PCG.CheckCall])
                H.ev('CARDS-PLAY', q=qid, a='check' if args[0] == PCG.Check else 'call', round=getattr(t, 'round', None),
                     maxBet=getattr(t, 'maxBet', None))
                gui.playerAction(*args)
        yield 0.5
    if r == 'time':
        H.ev('CARDS-FAIL', q=qid, why='%d s at the table' % CARD_SECS, prog=prog(H, qid), hands=hands)
    # stand up: the table's Leave button (its "are you sure" box answered yes)
    if t.isLocalAvatarSeated():
        H.ev('CARDS-LEAVE', q=qid, gold=gold(H))
        try:
            t.guiCallback(PCG.Leave)
        except Exception as e:
            H.ev('CARDS-FAIL', q=qid, why='leave: %r' % e)
        yield ('until', lambda: not t.isLocalAvatarSeated() and H.la.getGameState() == 'LandRoam', 30, 'stand up')
    return r


# ---------------- the Black Pearl boss battle ----------------
BOSS_WAY = os.environ.get('STORY_BOSS_WAY', 'map').lower()        # map: the map's Play Now; mw: ~blackpearlai
BOSS_FIGHT = os.environ.get('STORY_BOSS_FIGHT', 'stages').lower()  # stages: each stage ended; reward: ~bpstate Reward
# stage three: mw = the bpdestroy words (default until 0310 is live); cannon / wire = s_bpfort shoots the forts down
# (job 34), the words only when that fails
BOSS_FORT = os.environ.get('STORY_BOSS_FORT', 'mw').lower()
MAP_SECS = 30.0                    # the map comes with the c3.6 reward (patch 0031) and again at every login
# (stage the fight must leave, the words that end it the way play would, why, longest wait in s for the next stage).
# Boarding the Pearl and the cannon fights at sea are not played: the words take each ship to 0 hp or each barricade
# down, and the server's own checks move the fight on (patches 0031, 0039, 0042).
STAGES = (
    ('StageOne', ('bpstate StageTwo',), 'stage one is boarding and the ship capture: not played here', 30),
    ('StageTwo', ('bpkill ships',), 'attack ships to 0 hp: the 2 s ship check (patch 0031) ends stage two', 30),
    ('StageThree', ('bpdestroy 0', 'bpdestroy 2'), 'a barricade on each path opens stage four (20 s cutscene)', 60),
    ('StageFour', ('bpkill goliath',), 'Goliath to 0 hp: the 5 s victory check moves on to Reward', 30),
)
AFTER = {'StageOne': 'StageTwo', 'StageTwo': 'StageThree', 'StageThree': 'StageFour', 'StageFour': 'Reward'}
DONE_STATES = ('Reward', 'Completed')


def instance(H):
    """The treasure-map instance we are in (the client's TreasureMapBlackPearl), or None."""
    return next((o for o in list(H.cr.doId2do.values()) if hasattr(o, 'requestTreasureMapLeave')), None)


def pearlMap(H):
    """Our Black Pearl treasure map (DistributedTreasureMap, mapId GAME_STYLE_TM_BLACK_PEARL = 0), or None."""
    me = getattr(H.la, 'doId', None)
    for o in list(H.cr.doId2do.values()):
        if not hasattr(o, 'requestTreasureMapGo') or getattr(o, 'mapId', None) != 0:
            continue
        try:
            owner = o.getOwnerId() if hasattr(o, 'getOwnerId') else None
        except Exception:
            owner = None
        if owner not in (None, 0, me):
            continue
        return o
    return None


def stateOf(i):
    """The instance's fight stage on this client (its FSM state), or None."""
    return getattr(i, 'state', None) if i is not None else None


def pressPlayNow(H, tm):
    """The quest page's Play Now (QuestPage.startTreasureMap(tm, quick=True)): its solo check (patch 0033), the
    teleport confirm, then requestStart. The map's own requestTreasureMapGo when the page is not built yet."""
    page = getattr(getattr(H.la, 'guiMgr', None), 'questPage', None)
    if page is not None and hasattr(page, 'startTreasureMap'):
        page.startTreasureMap(tm, True)
        return 'questPage.startTreasureMap'
    tm.requestTreasureMapGo(True)
    return 'tm.requestTreasureMapGo'


def boss(H, qid):
    """Generator: c3.7recoverPearl as near a player as the bot gets: the Black Pearl map's Play Now, then each stage
    ended the way its own check needs (STAGES), so the server's Reward credits bossBattleCompleted. Falls back to the
    old words (~blackpearlai, ~bpstate Reward), each logged with why. -> 'credited' or 'give-up <why>'."""
    def done():
        p = prog(H, qid)
        return p is None or p[2]

    def inside():
        # in: the instance is here and we stand in it, or its fight has started (stage one's cutscene holds the
        # game state away from LandRoam)
        i = instance(H)
        return i is not None and (H.la.getGameState() == 'LandRoam' or
                                  stateOf(i) not in (None, 'Off', 'WaitClientsReady'))
    if done():
        return 'credited'
    way = 'mw'
    if instance(H) is None and BOSS_WAY == 'map':
        yield ('until', lambda: pearlMap(H) is not None, MAP_SECS, 'black pearl map')
        tm = pearlMap(H)
        if tm is None:
            H.ev('BOSS-FAIL', q=qid, why='no Black Pearl map %d s into c3.7 (patch 0031 gives it)' % MAP_SECS)
        else:
            yield ('until', lambda: H.la.getGameState() == 'LandRoam', 30, 'on land before the map')
            try:
                how = pressPlayNow(H, tm)
                H.ev('BOSS-MAP', q=qid, map=tm.doId, how=how, enabled=tm.getIsEnabled(), la=H.P(H.la), area=H.area())
            except Exception as e:
                how = None
                H.ev('BOSS-FAIL', q=qid, why='Play Now: %r' % (e,))
            if how:
                yield ('until', inside, 180, 'boss instance (map)')
                if instance(H) is not None:
                    way = 'map'
                else:
                    H.ev('BOSS-FAIL', q=qid, why='no instance 180 s after Play Now', gs=H.la.getGameState(),
                         area=H.area())
    if instance(H) is None and os.environ.get('STORY_PLAYER') == '1':
        H.ev('BOSS-FAIL', q=qid, why='no way in by the map; a player bot never uses ~blackpearlai')
        return 'give-up no instance'
    if instance(H) is None:
        H.ev('BOSS-MW', q=qid, word='blackpearlai',
             why='no way in by the map' if BOSS_WAY == 'map' else 'STORY_BOSS_WAY=%s' % BOSS_WAY)
        H.mw('blackpearlai')
        yield ('until', inside, 180, 'boss instance')
    i = instance(H)
    if i is None:
        H.ev('BOSS-FAIL', q=qid, why='no instance 180 s after ~blackpearlai', gs=H.la.getGameState(), area=H.area())
        return 'give-up no instance'
    H.ev('BOSS-ENTER', q=qid, inst=i.doId, cls=type(i).__name__, way=way, state=stateOf(i), area=H.area(),
         la=H.P(H.la))
    # WaitClientsReady waits until we are in (patch 0036), then StageOne
    yield ('until', lambda: done() or stateOf(instance(H)) not in (None, 'Off', 'WaitClientsReady'), 100, 'stage one')
    fought = BOSS_FIGHT == 'stages'
    if fought:
        for stage, words, why, secs in STAGES:
            i = instance(H)
            st = stateOf(i)
            if done() or i is None or st in DONE_STATES:
                break
            if st != stage:
                continue                       # the server is already past this stage
            if stage == 'StageThree' and BOSS_FORT in ('cannon', 'wire'):
                import s_bpfort
                fok, fwhy, frows = yield from s_bpfort.fight(H, i, BOSS_FORT)
                H.ev('BOSS-FORT-STEP', q=qid, ok=fok, why=fwhy, mode=BOSS_FORT, proof=s_bpfort.proofOf(frows)[0])
                if not s_bpfort.connected(H):
                    return 'give-up kicked at the forts'
                if fok:
                    words = ()                 # the forts fell: the server's own barricade check moves on
            if stage == 'StageThree' and words:
                H.ev('FALLBACK', q=qid, how=' / '.join(words), proof=False,
                     why='the barricades go down by the test word, not the cannon: not a 0310 proof'
                     if BOSS_FORT not in ('cannon', 'wire') else 'the fort step did not bring them down')
            for w in (words if os.environ.get('STORY_PLAYER') != '1' else ()):
                H.ev('BOSS-MW', q=qid, word=w, why=why, state=st)
                H.mw(w)
            nxt = AFTER[stage]
            t0 = time.time()
            yield ('until', lambda: done() or stateOf(instance(H)) != stage, secs, 'past %s' % stage)
            got = stateOf(instance(H))
            ok = got == nxt or got in DONE_STATES or done()
            H.ev('BOSS-STAGE', q=qid, stage=stage, ok=ok, now=got, want=nxt, secs=round(time.time() - t0, 1))
            if not ok:
                fought = False
                break
    if not done() and stateOf(instance(H)) not in DONE_STATES and os.environ.get('STORY_PLAYER') != '1':
        H.ev('BOSS-MW', q=qid, word='bpstate Reward', state=stateOf(instance(H)),
             why='a stage did not move on (BOSS-STAGE ok=False): Reward runs the real bossBattleCompleted'
             if BOSS_FIGHT == 'stages' else 'STORY_BOSS_FIGHT=%s' % BOSS_FIGHT)
        H.mw('bpstate Reward')
    yield ('until', done, 60, 'boss credit')
    ok = done()
    H.ev('BOSS-CREDIT', q=qid, ok=ok, way=way, fought=fought, prog=prog(H, qid))
    if instance(H) is not None:
        # patch 0039 sends us home 4 s into Completed; the leave button only if we are still in
        yield ('until', lambda: instance(H) is None, 15, 'sent home')
    i = instance(H)
    if i is not None:
        H.ev('BOSS-LEAVE', q=qid, inst=i.doId)
        try:
            i.requestTreasureMapLeave()        # the instance's own leave (its end screen's button)
        except Exception as e:
            H.ev('BOSS-FAIL', q=qid, why='leave: %r' % (e,))
    yield ('until', lambda: instance(H) is None and H.la.getGameState() == 'LandRoam', 120, 'leave boss instance')
    if instance(H) is not None:
        H.ev('BOSS-FAIL', q=qid, why='still in the instance 120 s after leave', gs=H.la.getGameState(), area=H.area())
    return 'credited' if ok else 'give-up no credit'
