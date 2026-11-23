"""EARN (pir-bot job 23b, 11-19): earn the gold for a paid quest step first, the way a kid would.

Why: NP2 (job 23) brought the test pirate 100000596 to Bonita's bribe (BribeNPCTaskDNA) with 8 gold; she asks 50. The
server only counts a bribe when the pirate pays at least the task's gold (QuestTaskDNA.BribeNPCTaskDNA.handleNPCBribe:
questEvent.gold >= self.gold), so the bribe click did nothing and the quest stalled.

What it does (s_story.act calls step() before a paid step; s_story.run runs earn() on ('earn', target)):
  price   the price of a paid step: BribeNPCTaskDNA.gold (the only quest task the pirate pays for; poker and
          blackjack tasks WIN gold, s_cards keeps its own RESERVE for that).
  short   gold below the price: earn until gold >= price + PAD (10), then go on (no stop-start at the edge).
  earn    out of the building first (the island's own doors, s_story.goto), then fight weak enemies like a player
          (s_fighter: pickFoe / Fighter, spawn nodes weakest camp first), the gold of each kill goes straight into
          the pocket. EARN_SECS (300 s) in all for one paid step.
  grant   only when that time runs out still short: the gold magic word, logged GOLD-GRANT (so a run that needed it
          is easy to see), once per paid step.
  bribe   (job 25b, 11-19) the click itself goes the kid's way: gold is checked again at the click (never send a
          bribe while short: 0260 refuses it and the step stalls), then the NPC's own confirmBribe() opens the box and
          the bot presses Yes only when the box offers Yes (OTPDialog.YesNo). A "You need N gold" box (CancelOnly) is
          cancelled and the step goes back to earning. The old straight b_selectOption is only used on a client
          without confirmBribe.
Events: GOLD-EARN what=start|kill|out|done|stop, GOLD-GRANT, BRIBE what=short|yes|box-short|no-box|direct.
Pure functions first (unit_job23b.py), the generator below runs in the game (no game import at module load)."""
import os
import time

PAD = int(os.environ.get('EARN_PAD', '10'))                 # earn to the price + this
EARN_SECS = float(os.environ.get('EARN_SECS', '300'))       # earning time for one paid step before GOLD-GRANT
OFF_STATE = 30.0       # s out of LandRoam / Battle (a scene, jail) before earn() hands back to the story
OUT_SECS = 90.0        # s to walk out of a building before giving up on the walk
LOOT_WAIT = 10.0       # s after a kill for the gold to land
BEAT = 0.25
PAY_TYPES = ('BribeNPCTaskDNA',)
BET_TYPES = ('BlackjackTaskDNA', 'PokerTaskDNA')  # job 33: gold to bet is earned first too (s_cards.betPrice)
# job 37: a poker table seats only a pirate with 200 gold (s_cards.play: 'a poker table seats only 200+'), so a poker
# step (Gunner's c3r3r1r13r3.1poker, win 150) earns 200 + the RESERVE first. s_story only gets here for poker when
# STORY_POKER=1 (it is in SKIP_TYPES otherwise).
POKER_SIT = 200


# ------------------------------------------------------------------------------------------------ pure
def price(task, done=0):
    """The gold a paid step costs, or None for a step that costs nothing. job 33: a blackjack task's price is the
    gold to sit with (s_cards.betPrice: the reserve + BJ_HANDS bids for what is still to win; `done` = won so far).
    job 37: a poker task's price is the 200 a table seats with + the RESERVE."""
    if type(task).__name__ == 'PokerTaskDNA':
        import s_cards
        return POKER_SIT + s_cards.RESERVE
    if type(task).__name__ in BET_TYPES:
        import s_cards
        try:
            return s_cards.betPrice(int(getattr(task, 'gold', 0) or 0), int(done or 0))
        except (TypeError, ValueError):
            return None
    if type(task).__name__ not in PAY_TYPES:
        return None
    g = getattr(task, 'gold', None)
    if g is None and hasattr(task, 'getGold'):
        g = task.getGold()
    try:
        return int(g) if g else None
    except (TypeError, ValueError):
        return None


def target(gold, cost, earning, pad=PAD):
    """-> the gold to earn up to, or None to go on with the step. Not earning yet: start only when gold < cost.
    Earning already: keep on until gold >= cost + pad."""
    if cost is None:
        return None
    if earning:
        return cost + pad if gold < cost + pad else None
    return cost + pad if gold < cost else None


def overTime(t0, now, secs=EARN_SECS):
    return now - t0 >= secs


YES_NO, CANCEL_ONLY = 4, 2       # otp.otpgui.OTPDialog styles


def bribeChoice(gold, cost, style=None):
    """Before the click (style None): 'short' (gold < cost: earn first) or 'open' (open the box).
    With the box open: 'yes' (YesNo), 'box-short' (CancelOnly: the game says too little gold) or 'no-box'."""
    if style is None:
        return 'short' if cost is not None and gold < cost else 'open'
    if style == YES_NO:
        return 'yes'
    if style == CANCEL_ONLY:
        return 'box-short'
    return 'no-box'


# ------------------------------------------------------------------------------------------------ in the game
def gold(H):
    inv = H.la.getInventory()
    return inv.getGoldInPocket() if inv else 0


def step(H, q, task, st, now=None):
    """Called by s_story.act before a paid step. -> None (go on with the step) or ('earn', target).
    st['earn'] = {price, target, t0, start, kills, granted} while earning (st is the quest's own state)."""
    now = time.time() if now is None else now
    done = 0
    if type(task).__name__ in BET_TYPES:
        import s_cards
        p = s_cards.prog(H, q.getQuestId())
        done = p[0] if p else 0
    cost = price(task, done)
    if cost is None or q.isComplete():
        return None
    g = gold(H)
    est = st.get('earn')
    if est is not None and est.get('price') != cost:
        est = None
    if est is not None and est.get('granted'):
        if g >= cost:
            st.pop('earn', None)
        return None                    # granted once: never grant or earn again for this step
    tgt = target(g, cost, est is not None)
    if tgt is None:
        if est is not None:
            H.ev('GOLD-EARN', what='done', q=q.getQuestId(), price=cost, gold=g, start=est['start'], target=est['target'],
                 secs=round(now - est['t0']), kills=est.get('kills', 0))
            st.pop('earn', None)
        return None
    if est is None:
        est = st['earn'] = {'price': cost, 'target': tgt, 't0': now, 'start': g, 'kills': 0, 'granted': False}
        H.ev('GOLD-EARN', what='start', q=q.getQuestId(), task=type(task).__name__, price=cost, gold=g, target=tgt,
             secs=EARN_SECS, area=H.area())
    if overTime(est['t0'], now) and os.environ.get('STORY_PLAYER') != '1':     # a player bot only earns
        grant(H, q, est, g, now)
        return None
    return ('earn', tgt)


def grant(H, q, est, g, now=None):
    """Earning ran out of time: the gold magic word, logged GOLD-GRANT, once."""
    now = time.time() if now is None else now
    est['granted'] = True
    H.ev('GOLD-GRANT', q=q.getQuestId(), price=est['price'], gold=g, start=est['start'], target=est['target'],
         to=est['target'], secs=round(now - est['t0']), kills=est.get('kills', 0),
         why='earning did not reach the price in %ds' % EARN_SECS)
    H.mw('gold %d' % est['target'])


def money(H):
    """The gold confirmBribe() compares: localAvatar.getMoney(), else the pocket."""
    f = getattr(H.la, 'getMoney', None)
    if f is not None:
        try:
            return f()
        except Exception:
            pass
    return gold(H)


def pressBox(d, value):
    """Press a PDialog button: its command option (DirectDialog), else nothing."""
    try:
        cmd = d['command']
    except Exception:
        cmd = getattr(d, 'command', None)
    if cmd is None:
        return False
    cmd(value)
    return True


def bribe(H, q, task, npc, st, BRIBE=None):
    """bribe() from a taskMgr callback: an error is logged (BRIBE what=error), never lost with the task."""
    try:
        return _bribe(H, q, task, npc, st, BRIBE)
    except Exception:
        import traceback
        H.ev('BRIBE', what='error', npc=getattr(npc, 'doId', None), tb=traceback.format_exc()[-600:])
        return 'error'


def _bribe(H, q, task, npc, st, BRIBE=None):
    """The bribe click, 3 s after requestInteraction (s_story.act). -> 'short' / 'yes' / 'box-short' / 'no-box' /
    'direct'. Short of gold: no click at all, st['earn'] cleared so the next act() earns first."""
    cost = price(task)
    g = money(H)
    qid = q.getQuestId()
    c = bribeChoice(g, cost)
    if c == 'short':
        st.pop('earn', None)
        H.ev('BRIBE', what='short', q=qid, npc=npc.doId, price=cost, gold=g,
             why='gold below the price at the click: no bribe sent, earning first')
        return 'short'
    if getattr(npc, 'confirmBribe', None) is None:
        if BRIBE is None:
            from pirates.distributed import InteractGlobals
            BRIBE = InteractGlobals.BRIBE
        npc.b_selectOption(BRIBE)
        H.ev('BRIBE', what='direct', q=qid, npc=npc.doId, price=cost, gold=g, why='no confirmBribe on this client')
        H.ev('bribe', npc=npc.doId, gold=g)
        return 'direct'
    npc.confirmBribe()
    d = getattr(npc, 'confirmDialog', None)
    style = getattr(d, 'style', None) if d is not None else None
    c = bribeChoice(g, cost, style)
    text = None
    try:
        text = d['text'] if d is not None else None
    except Exception:
        pass
    if c == 'yes':
        pressBox(d, 1)
        H.ev('BRIBE', what='yes', q=qid, npc=npc.doId, price=cost, gold=g, box=text)
        H.ev('bribe', npc=npc.doId, gold=g)
    else:
        if d is not None:
            pressBox(d, -1)
        st.pop('earn', None)
        H.ev('BRIBE', what=c, q=qid, npc=npc.doId, price=cost, gold=g, box=text, style=style,
             why='the box offers no Yes: earning first')
    return c


def outside(H, story):
    """True on the open island (not in a building or a cave)."""
    return story.sailing.hereUid(H) is not None


def earn(H, q, st, story=None, F=None):
    """Generator: earn gold until st['earn']['target'], its time runs out, he is knocked out or a scene takes him.
    -> 'done' / 'time' / 'ko' / 'state' / 'no-way-out' / 'no-spawn'. Kills are counted in st['earn']['kills']."""
    if story is None:
        import s_story as story
    if F is None:
        import s_fighter as F
    la = H.la
    est = st['earn']
    tgt = est['target']
    fighter, node, tried, offT, outT, why = None, None, set(), None, None, 'time'
    try:
        while not overTime(est['t0'], time.time()):
            if gold(H) >= tgt:
                why = 'done'
                break
            if (getattr(la, 'hp', 1) or 0) <= 0 or la.getGameState() in ('Death', 'Dying'):
                why = 'ko'
                break
            gs = la.getGameState()
            if gs not in ('LandRoam', 'Battle'):
                offT = offT or time.time()
                if time.time() - offT > OFF_STATE:
                    why = 'state'
                    break
                yield BEAT
                continue
            offT = None
            if fighter is None and not outside(H, story):
                # in a building (Bonita's tavern) or a cave: out to the island through its own door first
                outT = outT or time.time()
                if time.time() - outT > OUT_SECS:
                    why = 'no-way-out'
                    break
                here = story.hereArea(H)
                isl = (story.questSpots()['areas'].get(here) or [None])[0] or story.sailing.islandOfUid(here)
                r = story.goto(H, st, isl, tag='earn-out') if isl else 'no-island'
                g = st.pop('go', None)
                if g is not None:
                    yield from story.go(H, *g)
                else:
                    yield 1.0
                continue
            if outT is not None:
                H.ev('GOLD-EARN', what='out', q=q.getQuestId(), area=H.area(), secs=round(time.time() - outT))
                outT = None
            lvl = F.myLevel(H)
            if fighter is not None:
                a = fighter.step()
                if a in ('kill', 'lost', 'stuck'):
                    foe = fighter.foe
                    fighter.close()
                    fighter = None
                    if a == 'kill':
                        est['kills'] = est.get('kills', 0) + 1
                        g0 = gold(H)
                        yield ('until', lambda: gold(H) > g0, LOOT_WAIT, 'kill gold')
                        H.ev('GOLD-EARN', what='kill', q=q.getQuestId(), foe=foe.doId, lvl=getattr(foe, 'level', None),
                             n=est['kills'], gold=gold(H), gain=gold(H) - g0, target=tgt)
                        continue
                yield BEAT
                continue
            rows = F.foeRows(H)
            ids, skip = F.pickFoe(rows, lvl, F.VIEW, 99, F.LVL_OVER)
            o = H.cr.doId2do.get(ids[0]) if ids else None
            if o is not None:
                H.walk_cancel()
                node = None
                H.ev('FOE-PICK', foe=o.doId, why='earn gold', kind=str(getattr(o, 'avatarType', None)),
                     lvl=getattr(o, 'level', None), myLvl=lvl, hp=getattr(o, 'hp', None), candidates=len(ids))
                me = la.getPos(H.render)
                fighter = F.Fighter(H, o, (me[0], me[1], me[2]))
                continue
            if node is None:
                here = story.hereArea(H)
                nodes = [tuple(v[1:4]) + (v[5],) for v in story.questSpots().get('objs', {}).values()
                         if v[0] == here and v[4] == 'Spawn Node']
                org = story.areaObj(H, here)
                me = la.getPos(org) if org is not None else la.getPos(H.render)
                pick = F.spawnPick(nodes, (me[0], me[1]), tried, lvl)
                if pick is None:
                    if not nodes:
                        why = 'no-spawn'
                        break
                    tried.clear()
                    yield 5
                    continue
                H.ev('SPAWN-PICK', node=pick[3], why='earn gold', spot=[round(v, 1) for v in pick[:3]], myLvl=lvl)
                node = tuple(pick) + (org,)
            r = H.walk_poll(node[:3], ref=node[4], arrive=8.0, face=False, tag='earn-spawn')
            if r is True or r is None:
                tried.add(tuple(node[:3]))
                node = None
                yield 1.0 if r is True else BEAT      # stand a second at the camp: enemies spawn and come in view
                continue
            yield BEAT
    finally:
        if fighter is not None:
            fighter.close()
        H.walk_cancel()
    H.ev('GOLD-EARN', what='stop', q=q.getQuestId(), why=why, gold=gold(H), target=tgt, kills=est.get('kills', 0),
         secs=round(time.time() - est['t0']))
    return why
