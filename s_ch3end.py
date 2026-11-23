"""CH3END (pir-bot job 39, 2026-11-19): the bot plays the rest of Chapter 3, from Mary's ladder c3r3r2 to the end of
the story: c3r3r2.1visitFabiola .. c3.8visitJack, 156 steps (Mary, Giladoga's water and keys, Smith's ship, Montrose
and the Black Pearl), as the test pirate 100000001, and says per step whether it was played for real.

Run: run_walk.ps1 -Tag CH3END -Script s_ch3end.py (the harness logs walk-CH3END-events.jsonl). Pirate 100000170 is
refused. It is a long ladder (hours): run it more than once, each run goes on from the step the pirate holds.

No pick: pir-quests' table (tools/ch3end_steps.md, 142 rows) has Giladoga's water as "pick one" (latrine, crypt). The
game has no pick there: c3r3r3r7water and c3r3r3r7water2 are QuestChoiceSingle (QuestLadder.py:643), a plain ladder
(isChoice() False, no menu, assignFirstQuest takes containers[0], advance the next). The server hands out every
branch, one after the other, as for Grog and Gunner. So this run has the table's 142 steps plus the 14 the table left
out: skeleton water (Orinda), shark water (Benedek), c3r3r3r7.4recoverWater, honeysuckle (Scarlet) and rubber sap
(Bowdash, with a poker win of 80). Latrine (Carver) and crypt (Mallet) are in, in the server's order.

How: s_story plays it (talks, kills, drops, chests, ship fights, captures and maroons, bribes with s_earn gold, the
poker and blackjack wins, the Black Pearl boss through s_cards.boss), with these env defaults (each can be overridden):
  CH3END_FROM=tail               where a pirate that holds no step starts: 'tail' = c3r3r2.1visitFabiola, 'giladoga'
                                 = c3r3r3.1visitCarver, 'smith' = c3r3r4.1visitBowdash, 'pearl' = c3.4captureMontrose,
                                 or any step id below. STORY_START is set from it.
  STORY_STOP=''                  s_ch3end ends the run itself: c3.8visitJack is the story's last quest (CH3END_STOP)
  STORY_GRIND=play               many steps are grind types; without this s_story would skipQuest the repeats
  STORY_WEAK_MARGIN=12           strong Navy and EITC ships are fought, not skipped (CH3END_WEAK_MARGIN)
  STORY_POKER=1                  c3r3r3r7r7.2poker (win 80) and c3r3r3r9r3.6poker (win 150) are played
  STORY_BOSS=1                   c3.7recoverPearl: the Black Pearl boss battle is fought (s_cards.boss), not skipped
s_story's main-quest list is cut to these steps (CH3END_ONLY=1, the default), so another story quest the pirate holds
is left alone. Gold: bribes Flinty 10, Mallet 50, Carver 10 + 100, Scarlet 100, Fabiola 50 (320); the poker tables
seat with 200 + the 100 reserve; s_earn earns what is short (about 500 at the most at once).

The Black Pearl (c3.7recoverPearl): the win calls questMgr.bossBattleCompleted (TreasureMapBlackPearlAI.enterReward).
The quest needs no visit, so the server hands it in at once and the 1 s poll may never see it held. s_ch3end hooks the
client quest's own update (DistributedQuest.setTaskStates, put back after the run), so the server's credit is seen
even if the quest is gone before the next poll. It is judged as a count step: it needs quest-progress and
quest-complete (the fight's quest credit), never the history alone.

Pass point: c3.8visitJack done, then the "Chapter 3 complete, stay tuned" panel (the server's
d_popupProgressBlocker, QuestManagerAI.py:550 on the family server). The panel is watched through the pirate's own
popupProgressBlocker (CH3END-STAYTUNED); the judge counts it as one more row.

Step kinds (unit_job39 checks them against the QuestDB):
  talk   visit / deliver / bribe: quest-complete only
  count  a kill / drop / ship / cards step with a goal over 1, or one that waits for its own NPC to hand it in, and
         the Black Pearl: quest-progress is needed too
  once   a goal-1 step that the server hands in the moment it is done: quest-complete (often via 'history') is enough

Resume: a step in the history before the first step the pirate holds was handed in on an earlier run: it counts as
done. A step at or after it in the history can never be handed in again (QuestManagerAI.py:518-523):
CH3END-HISTORY + FAIL at once.

Lines (s_ch3end's own):
  CH3END-SETUP     avId, level, gold, held steps, first (the first step judged), earlier (handed in on an earlier run)
  quest-held / quest-progress / quest-complete / quest-handed-in   as s_gunner ('via': 'update' = seen by the hook)
  CH3END-POKER     a poker step was won for real this run (one line per poker step)
  CH3END-PEARL     c3.7recoverPearl got its quest credit this run (progress and complete seen)
  CH3END-STAYTUNED the server's stay-tuned panel came (the questId it names)
  CH3END-END       after c3.8visitJack: the panel came, ok true / false
  CH3END-RESUME    the run ended (time up) before c3.8visitJack with nothing failed: the step(s) held
  CH3END-STEP      at the end, one per judged step: q, ok, why
  PASS / FAIL      PASS = every judged step done (this run or an earlier one), quest-progress for a count step, no
                   SKIP / STALL for any, and the stay-tuned panel. s_story's own PASS would be STORY-PASS.

Offline judge: python -B s_ch3end.py --events walk-CH3END-events.jsonl [more runs' files]  (exit 0 on PASS)."""
import json, os, sys

HOST_AV = 100000170

# the server's order (MainStory flattened; unit_job39 checks it). kind: see the docstring
STEPS = [
    ('c3r3r2.1visitFabiola', 'talk'),                    # Visit
    ('c3r3r2.2visitOrinda', 'talk'),                     # Visit
    ('c3r3r2.3captureReginald', 'once'),                 # CaptureShipNPC
    ('c3r3r2.4maroonReginald', 'once'),                  # MaroonNPC
    ('c3r3r2.5captureDennison', 'once'),                 # CaptureShipNPC
    ('c3r3r2.6maroonDennison', 'once'),                  # MaroonNPC
    ('c3r3r2.7captureHedley', 'once'),                   # CaptureShipNPC
    ('c3r3r2.8maroonHedley', 'once'),                    # MaroonNPC
    ('c3r3r2.9captureBiggleton', 'once'),                # CaptureShipNPC
    ('c3r3r2.10maroonBiggleton', 'once'),                # MaroonNPC
    ('c3r3r2.11captureNorman', 'once'),                  # CaptureShipNPC
    ('c3r3r2.12maroonNorman', 'once'),                   # MaroonNPC
    ('c3r3r2.13captureFitzpatrick', 'once'),             # CaptureShipNPC
    ('c3r3r2.14maroonFitzpatrick', 'once'),              # MaroonNPC
    ('c3r3r2.15captureHamilton', 'once'),                # CaptureShipNPC
    ('c3r3r2.16maroonHamilton', 'once'),                 # MaroonNPC
    ('c3r3r2.17visitJohn', 'talk'),                      # Visit
    ('c3r3r2.18recoverRum', 'count'),                    # RecoverShipItem
    ('c3r3r2.19visitMary', 'talk'),                      # Visit
    ('c3r3r2r20.1sinkNavy', 'count'),                    # DefeatShip
    ('c3r3r2r20.2sinkEITC', 'count'),                    # DefeatShip
    ('c3r3r2r20.3sinkSkeleton', 'count'),                # DefeatShip
    ('c3r3r2.20.5recoverBelongings', 'count'),           # RecoverTreasureItem
    ('c3r3r2.21visitJoshamee', 'talk'),                  # Visit
    ('c3r3r3.1visitCarver', 'talk'),                     # Visit
    ('c3r3r3.2visitMcVane', 'talk'),                     # Visit
    ('c3r3r3.3visitGiladoga', 'talk'),                   # Visit
    ('c3r3r3.4deliverKey', 'talk'),                      # DeliverItem
    ('c3r3r3.5bribeFlinty', 'talk'),                     # BribeNPC gold 10
    ('c3r3r3.6deliverKey', 'talk'),                      # DeliverItem
    ('c3r3r3r7r1.1visitOrinda', 'talk'),                 # Visit
    ('c3r3r3r7r1.2recoverWater', 'once'),                # RecoverShipItem
    ('c3r3r3r7r1.3deliverWater', 'talk'),                # DeliverItem
    ('c3r3r3r7r2.1visitCarver', 'talk'),                 # Visit
    ('c3r3r3r7r2.2recoverWater', 'count'),               # RecoverAvatarItem
    ('c3r3r3r7r2.3deliverWater', 'talk'),                # DeliverItem
    ('c3r3r3r7r3.1visitBenedek', 'talk'),                # Visit
    ('c3r3r3r7r3.2recoverWater', 'once'),                # RecoverAvatarItem
    ('c3r3r3r7r3.3deliverWater', 'talk'),                # DeliverItem
    ('c3r3r3r7.4recoverWater', 'count'),                 # RecoverAvatarItem
    ('c3r3r3r7r5.1visitMallet', 'talk'),                 # Visit
    ('c3r3r3r7r5.2bribeMallet', 'talk'),                 # BribeNPC gold 50
    ('c3r3r3r7r5.3deliverWater', 'talk'),                # DeliverItem
    ('c3r3r3r7r6.1visitScarlet', 'talk'),                # Visit
    ('c3r3r3r7r6.2recoverHoneysuckle', 'count'),         # RecoverAvatarItem
    ('c3r3r3r7r6.3deliverHoneysuckle', 'talk'),          # DeliverItem
    ('c3r3r3r7r7.1visitBowdash', 'talk'),                # Visit
    ('c3r3r3r7r7.2poker', 'count'),                      # Poker win 80
    ('c3r3r3r7r7.3recoverSap', 'count'),                 # RecoverAvatarItem
    ('c3r3r3r7r7.4deliverSap', 'talk'),                  # DeliverItem
    ('c3r3r3.8deliverKey', 'talk'),                      # DeliverItem
    ('c3r3r3r9r1.1visitCraven', 'talk'),                 # Visit
    ('c3r3r3r9r1.2visitFlatts', 'talk'),                 # Visit
    ('c3r3r3r9r1.3sinkNavyShips', 'count'),              # DefeatShip
    ('c3r3r3r9r1.4deliverRum', 'talk'),                  # DeliverItem
    ('c3r3r3r9r1.5deliverMoney', 'talk'),                # DeliverItem
    ('c3r3r3r9r1.6deliverKey', 'talk'),                  # DeliverItem
    ('c3r3r3r9r2.1visitMallet', 'talk'),                 # Visit
    ('c3r3r3r9r2.2visitBenedek', 'talk'),                # Visit
    ('c3r3r3r9r2.3recoverChest', 'count'),               # RecoverShipItem
    ('c3r3r3r9r2.4deliverFabiola', 'talk'),              # DeliverItem
    ('c3r3r3r9r2r5.1recoverHair', 'count'),              # RecoverAvatarItem
    ('c3r3r3r9r2r5.2recoverTears', 'count'),             # RecoverAvatarItem
    ('c3r3r3r9r2r5.3recoverBlood', 'count'),             # RecoverAvatarItem
    ('c3r3r3r9r2r5.4recoverGuano', 'count'),             # RecoverAvatarItem
    ('c3r3r3r9r2.6deliverGold', 'talk'),                 # DeliverItem
    ('c3r3r3r9r2.7recoverCoins', 'count'),               # RecoverTreasureItem
    ('c3r3r3r9r2.8blackjack', 'count'),                  # Blackjack win 80
    ('c3r3r3r9r2.9deliverKey', 'talk'),                  # DeliverItem
    ('c3r3r3r9r3.1visitBowdash', 'talk'),                # Visit
    ('c3r3r3r9r3.2capturePenrod', 'once'),               # CaptureShipNPC
    ('c3r3r3r9r3.3maroonPenrod', 'once'),                # MaroonNPC
    ('c3r3r3r9r3.4deliverGold', 'talk'),                 # DeliverItem
    ('c3r3r3r9r3.5sinkNavyShips', 'count'),              # DefeatShip
    ('c3r3r3r9r3.6poker', 'count'),                      # Poker win 150
    ('c3r3r3r9r3.7deliverKey', 'talk'),                  # DeliverItem
    ('c3r3r3r9r4.1recoverChest', 'count'),               # RecoverAvatarItem
    ('c3r3r3r9r4.2visitFabiola', 'talk'),                # Visit
    ('c3r3r3r9r4r3.1recoverCologne', 'count'),           # RecoverAvatarItem
    ('c3r3r3r9r4r3.2recoverOil', 'count'),               # RecoverAvatarItem
    ('c3r3r3r9r4r3.3recoverBile', 'count'),              # RecoverAvatarItem
    ('c3r3r3r9r4.4deliverList', 'talk'),                 # DeliverItem
    ('c3r3r3r9r4.5visitCarver', 'talk'),                 # Visit
    ('c3r3r3r9r4.6bribeCarver', 'talk'),                 # BribeNPC gold 10
    ('c3r3r3r9r4.7deliverRum', 'talk'),                  # DeliverItem
    ('c3r3r3r9r4.8visitCarver', 'talk'),                 # Visit
    ('c3r3r3r9r4.9bribeCarver', 'talk'),                 # BribeNPC gold 100
    ('c3r3r3r9r4.10deliverRum', 'talk'),                 # DeliverItem
    ('c3r3r3r9r4.11deliverOil', 'talk'),                 # DeliverItem
    ('c3r3r3r9r4.12deliverKey', 'talk'),                 # DeliverItem
    ('c3r3r3r9r5.1visitGrog', 'talk'),                   # Visit
    ('c3r3r3r9r5r2.1recoverTeeth', 'count'),             # RecoverAvatarItem
    ('c3r3r3r9r5r2.2recoverVenom', 'count'),             # RecoverAvatarItem
    ('c3r3r3r9r5r2.3recoverSap', 'count'),               # RecoverAvatarItem
    ('c3r3r3r9r5.3deliverRemedy', 'talk'),               # DeliverItem
    ('c3r3r3r9r5.4recoverKey', 'once'),                  # RecoverShipItem
    ('c3r3r3r9r5.5deliverKey', 'talk'),                  # DeliverItem
    ('c3r3r3r9r6.1visitAnne', 'talk'),                   # Visit
    ('c3r3r3r9r6.2defeatSkeletons', 'count'),            # Defeat
    ('c3r3r3r9r6.3deliverKey', 'talk'),                  # DeliverItem
    ('c3r3r3r9r7.1visitScarlet', 'talk'),                # Visit
    ('c3r3r3r9r7.2captureCollier', 'once'),              # CaptureShipNPC
    ('c3r3r3r9r7.3maroonCollier', 'once'),               # MaroonNPC
    ('c3r3r3r9r7.4deliverNecklace', 'talk'),             # DeliverItem
    ('c3r3r3r9r7.5bribeScarlet', 'talk'),                # BribeNPC gold 100
    ('c3r3r3r9r7.6deliverKey', 'talk'),                  # DeliverItem
    ('c3r3r3r9r8.1recoverOrders', 'count'),              # RecoverShipItem
    ('c3r3r3r9r8.2visitBlakeley', 'talk'),               # Visit
    ('c3r3r3r9r8.3visitWoodruff', 'talk'),               # Visit
    ('c3r3r3r9r8.4recoverSalve', 'count'),               # RecoverAvatarItem
    ('c3r3r3r9r8.5deliverWax', 'talk'),                  # DeliverItem
    ('c3r3r3r9r8.6bribeFabiola', 'talk'),                # BribeNPC gold 50
    ('c3r3r3r9r8.7deliverKey', 'talk'),                  # DeliverItem
    ('c3r3r3r9r8.8recoverKey', 'once'),                  # RecoverTreasureItem
    ('c3r3r3r9r8.9deliverKey', 'talk'),                  # DeliverItem
    ('c3r3r3.10recoverChest', 'count'),                  # RecoverShipItem
    ('c3r3r3.11visitJack', 'talk'),                      # Visit
    ('c3r3r3.12recoverKey', 'count'),                    # RecoverShipItem
    ('c3r3r3.13deliverKey', 'talk'),                     # DeliverItem
    ('c3r3r3.14visitJoshamee', 'talk'),                  # Visit
    ('c3r3r4.1visitBowdash', 'talk'),                    # Visit
    ('c3r3r4.2visitSmith', 'talk'),                      # Visit
    ('c3r3r4r3r1.1recoverMeat', 'count'),                # RecoverAvatarItem
    ('c3r3r4r3r1r2.1recoverWood', 'count'),              # RecoverShipItem
    ('c3r3r4r3r1r2.2recoverNails', 'count'),             # RecoverAvatarItem
    ('c3r3r4r3r1r2.3recoverNails', 'count'),             # RecoverShipItem
    ('c3r3r4r3r1r2.4recoverPitch', 'count'),             # RecoverContainerItem
    ('c3r3r4.3.5visitSmith', 'talk'),                    # Visit
    ('c3r3r4r4r1.1recoverMeat', 'count'),                # RecoverAvatarItem
    ('c3r3r4r4r1r2.1recoverWood', 'count'),              # RecoverShipItem
    ('c3r3r4r4r1r2.2recoverNails', 'count'),             # RecoverAvatarItem
    ('c3r3r4r4r1r2.3recoverBeams', 'count'),             # RecoverAvatarItem
    ('c3r3r4r4r1r2.4recoverBolts', 'count'),             # RecoverShipItem
    ('c3r3r4.4.5visitSmith', 'talk'),                    # Visit
    ('c3r3r4r5r1.1recoverMeat', 'count'),                # RecoverAvatarItem
    ('c3r3r4r5r1r2.1recoverWood', 'count'),              # RecoverShipItem
    ('c3r3r4r5r1r2.2recoverNails', 'count'),             # RecoverShipItem
    ('c3r3r4.5.5visitSmith', 'talk'),                    # Visit
    ('c3r3r4r6r1.1recoverMeat', 'count'),                # RecoverAvatarItem
    ('c3r3r4r6r1r2.1recoverBeams', 'count'),             # RecoverShipItem
    ('c3r3r4r6r1r2.2recoverBolts', 'count'),             # RecoverShipItem
    ('c3r3r4.7visitSmith', 'talk'),                      # Visit
    ('c3r3r4.8recoverSails', 'count'),                   # RecoverShipItem
    ('c3r3r4.9recoverRopes', 'count'),                   # RecoverShipItem
    ('c3r3r4.10recoverCannons', 'count'),                # RecoverShipItem
    ('c3r3r4.11recoverFigure', 'count'),                 # RecoverShipItem
    ('c3r3r4.12recoverRum', 'count'),                    # RecoverShipItem
    ('c3r3r4.12.5visitBowdash', 'talk'),                 # Visit
    ('c3r3r4.12.51recoverKey', 'count'),                 # RecoverTreasureItem
    ('c3r3r4.12.52visitSmith', 'talk'),                  # Visit
    ('c3r3r4.13visitJoshamee', 'talk'),                  # Visit
    ('c3.4captureMontrose', 'once'),                     # CaptureShipNPC
    ('c3.5maroonMontrose', 'once'),                      # MaroonNPC
    ('c3.6deliverMap', 'talk'),                          # DeliverItem
    ('c3.7recoverPearl', 'count'),                       # BossBattle (judged as count: its fight credit must show)
    ('c3.8visitJack', 'talk'),                           # Visit
]
IDS = [s[0] for s in STEPS]
KIND = dict(STEPS)
IDX = dict((q, i) for i, q in enumerate(IDS))
FIRST, LAST = IDS[0], IDS[-1]
ALIASES = {'tail': FIRST, '': FIRST, 'giladoga': 'c3r3r3.1visitCarver', 'smith': 'c3r3r4.1visitBowdash',
           'pearl': 'c3.4captureMontrose'}
POKER_QS = ('c3r3r3r7r7.2poker', 'c3r3r3r9r3.6poker')
PEARL_Q = 'c3.7recoverPearl'
LATRINE = ('c3r3r3r7r2.1visitCarver', 'c3r3r3r7r2.2recoverWater', 'c3r3r3r7r2.3deliverWater')
CRYPT = ('c3r3r3r7r5.1visitMallet', 'c3r3r3r7r5.2bribeMallet', 'c3r3r3r7r5.3deliverWater')
EARLIER = 'handed in before this run'
END_ROW = 'stay-tuned'    # the judge's last row: the "Chapter 3 complete, stay tuned" panel
END_WAIT = 30
BAD_EVENTS = ('SKIP', 'STALL', 'SKIP-NOT-SHOWN')


def fromStep(v=None):
    v = os.environ.get('CH3END_FROM', 'tail') if v is None else v
    v = ALIASES.get(v, v)
    if v not in IDX:
        raise ValueError('CH3END_FROM %r is no step of this run' % v)
    return v


if __name__ != '__main__':
    os.environ.setdefault('STORY_START', fromStep())
    os.environ['STORY_STOP'] = os.environ.get('CH3END_STOP', '')
    os.environ.setdefault('STORY_GRIND', 'play')
    os.environ.setdefault('STORY_WEAK_MARGIN', os.environ.get('CH3END_WEAK_MARGIN', '12'))
    os.environ.setdefault('STORY_POKER', '1')
    os.environ.setdefault('STORY_BOSS', '1')
    _here = os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0]
    if _here:
        sys.path.insert(0, os.path.dirname(os.path.abspath(_here)))


def _ts(q):
    ts = q.get('ts')
    return [tuple(t) for t in ts] if isinstance(ts, (list, tuple)) else []


def _prog(ts):
    return [t[0] or 0 for t in ts]


class Watch(object):
    """Pure (no game calls): fed H.quests() and H.hist() each tick (and the hook's quest updates), it says which
    quest-* lines to write."""

    def __init__(self, qint, earlier=()):
        self.qint = qint          # quest id -> quest int (the history holds ints)
        self.held = {}            # qid -> last progress list
        self.done = set(earlier)  # earlier: already in the history at the start, no lines for these
        self.gone = set(earlier)

    def _seen(self, qid, ts, complete, via):
        out = []
        p = _prog(ts)
        if qid not in self.held:
            out.append(('quest-held', dict({'q': qid, 'ts': ts}, **({'via': via} if via else {}))))
            if via and sum(p) > 0:
                # the hook's first update can already carry the credit (the quest was given and done at once)
                out.append(('quest-progress', {'q': qid, 'progress': p, 'goal': [t[1] for t in ts],
                                               'frm': [0] * len(p), 'via': via}))
        elif p != self.held[qid] and sum(p) > sum(self.held[qid]):
            out.append(('quest-progress', dict({'q': qid, 'progress': p, 'goal': [t[1] for t in ts],
                                                'frm': self.held[qid]}, **({'via': via} if via else {}))))
        self.held[qid] = p
        if complete and qid not in self.done:
            self.done.add(qid)
            out.append(('quest-complete', {'q': qid, 'via': via or 'complete', 'ts': ts}))
        return out

    def update(self, qid, ts, complete):
        """The hook: one quest's own update from the server (DistributedQuest.setTaskStates)."""
        if qid not in KIND or qid in self.gone:
            return []
        return self._seen(qid, [tuple(t) for t in ts], complete, 'update')

    def tick(self, quests, hist):
        out = []
        hist = set(hist)
        now = dict((q['id'], q) for q in quests if q.get('id') in KIND)
        for qid in IDS:
            q = now.get(qid)
            if q is None:
                continue
            out += self._seen(qid, _ts(q), q.get('complete'), None)
        for qid in IDS:
            # a 'once' step can be given and handed in between two ticks, never seen held: the history says it is done
            seen = qid in self.held or KIND[qid] == 'once'
            if seen and qid not in now and qid not in self.gone and self.qint.get(qid) in hist:
                self.gone.add(qid)
                if qid not in self.done:
                    self.done.add(qid)
                    out.append(('quest-complete', {'q': qid, 'via': 'history'}))
                out.append(('quest-handed-in', {'q': qid}))
        return out


def plan(qint, held, hist, frm=None):
    """-> (first, earlier, late). first = the first step judged (the start step, or an earlier held one); earlier =
    history steps before the first held step (handed in on an earlier run); late = history steps at or after it,
    which can never be handed in again."""
    hist = set(hist)
    frm = fromStep(frm)
    hi = [IDX[q] for q in held if q in IDX]
    first = IDS[min([IDX[frm]] + hi)]
    pos = min(hi) if hi else IDX[frm]
    inHist = [q for q in IDS if qint.get(q) in hist and q not in held]
    earlier = [q for q in inHist if IDX[q] < pos]
    late = [q for q in inHist if IDX[q] >= pos]
    return first, earlier, late


def judge(events):
    """events: the walk-*-events.jsonl records (dicts with 'ev'), one run or several in order. -> (ok, rows), rows =
    [(qid, ok, why)] from the first CH3END-SETUP's 'first' step (FIRST without one), then the stay-tuned row. A step
    passes with quest-complete (quest-progress too for a count step) or as handed in on an earlier run, and no SKIP /
    STALL. The Black Pearl never passes from the history alone."""
    setups = [e for e in events if e.get('ev') == 'CH3END-SETUP']
    first = setups[0].get('first') if setups and setups[0].get('first') in IDX else FIRST
    earlier = set()
    for e in setups:
        earlier.update(e.get('earlier') or ())
    scope = IDS[IDX[first]:]
    st = dict((q, {'held': False, 'prog': [], 'done': None, 'bad': []}) for q in scope)
    for e in events:
        q = e.get('q')
        if q not in st:
            continue
        k = e.get('ev')
        if k == 'quest-held':
            st[q]['held'] = True
        elif k == 'quest-progress':
            st[q]['prog'].append(e.get('progress'))
        elif k == 'quest-complete' and st[q]['done'] is None:
            st[q]['done'] = e.get('via') or 'complete'
        elif k in BAD_EVENTS:
            st[q]['bad'].append('%s %s' % (k, e.get('type') or e.get('what') or ''))
    rows = []
    for q in scope:
        s = st[q]
        if s['bad']:
            rows.append((q, False, 'not played for real: %s' % '; '.join(s['bad'])))
        elif s['done'] is None and q in earlier:
            rows.append((q, True, EARLIER))
        elif s['done'] is None:
            rows.append((q, False, 'never completed' if s['held'] else 'never held'))
        elif KIND[q] == 'count' and not s['prog']:
            rows.append((q, False, 'completed (%s) with no quest-progress line' % s['done']))
        else:
            rows.append((q, True, 'complete (%s)%s' % (s['done'], ', progress %s' % s['prog'][-1] if s['prog'] else '')))
    tuned = [e for e in events if e.get('ev') == 'CH3END-STAYTUNED']
    ends = [e for e in events if e.get('ev') == 'CH3END-END']
    if tuned:
        rows.append((END_ROW, True, 'the stay-tuned panel came after %s (%s)' % (LAST, tuned[-1].get('next'))))
    else:
        rows.append((END_ROW, False, 'no stay-tuned panel after %s' % LAST if ends else
                     'never reached (no CH3END-END line)'))
    return all(r[1] for r in rows), rows


def readEvents(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def _qint():
    from pirates.quest import QuestDB
    return dict((q, QuestDB.QuestDict[q].getQuestInt()) for q in IDS)


def _states(quest):
    """[(progress, goal, attempts)] of a client quest object (Quest.getTaskStates)."""
    out = []
    for s in quest.getTaskStates() or ():
        out.append((s.getProgress() or 0, s.getGoal() or 0, 0))
    return out


def hookQuests(cb, cls=None):
    """Wrap the client quest class's setTaskStates (the server's update of a quest's progress) so cb(quest) runs
    after each. -> a function that puts the class back."""
    if cls is None:
        from pirates.quest.DistributedQuest import DistributedQuest as cls
    orig = cls.__dict__.get('setTaskStates')

    def setTaskStates(self, taskStates):
        r = orig(self, taskStates)
        try:
            cb(self)
        except Exception:
            pass
        return r
    cls.setTaskStates = setTaskStates

    def unhook():
        cls.setTaskStates = orig
    return unhook


def run(H):
    la = H.la
    if la.doId == HOST_AV:
        H.ev('FAIL', why='refused: %d is the pirate of Host' % HOST_AV)
        return
    import s_cards, s_story
    # s_cards / s_story may have been imported before this module set STORY_POKER / STORY_BOSS
    if os.environ.get('STORY_POKER') == '1':
        s_cards.POKER = True
    if os.environ.get('STORY_BOSS') == '1':
        s_cards.BOSS = True
    s_story.SKIP_TYPES = tuple(t for t in ('PokerTaskDNA', 'BlackjackTaskDNA', 'BossBattleTaskDNA')
                               if t not in s_cards.playTypes())
    qint = _qint()
    held = [q for q in H.qids() if q in KIND]
    first, earlier, late = plan(qint, held, H.hist())
    setup = dict(avId=la.doId, level=la.getLevel(), gold=getattr(la, 'getMoney', lambda: None)(), held=held,
                 first=first, earlier=earlier, start=s_story.START, grind=os.environ.get('STORY_GRIND'),
                 margin=s_story.WEAK_MARGIN, skipTypes=list(s_story.SKIP_TYPES), steps=len(IDS))
    H.ev('CH3END-SETUP', **setup)
    if late:
        H.ev('CH3END-HISTORY', steps=late)
        H.ev('FAIL', why='steps at or after the one held are already in the quest history and can never be handed in '
                         'again (QuestManagerAI.py:518-523): %s' % ', '.join(late))
        return
    if os.environ.get('CH3END_ONLY', '1') == '1':
        s_story.STORY = list(IDS)
        s_story.ORDER = dict(IDX)
    w = Watch(qint, earlier)
    ev0 = H.ev
    rec = [dict(setup, ev='CH3END-SETUP')]
    tuned = []

    def out(name, kw):
        rec.append(dict(kw, ev=name))
        ev0(name, **kw)

    def ev(name, /, **kw):
        if name == 'PASS':
            name = 'STORY-PASS'
        rec.append(dict(kw, ev=name))
        return ev0(name, **kw)

    def watch():
        try:
            for name, kw in w.tick(H.quests(), H.hist()):
                out(name, kw)
        except Exception as e:
            ev0('CH3END-WATCH-ERR', err=repr(e)[-300:])

    def onQuest(quest):
        qid = quest.getQuestId()
        if qid in KIND:
            for name, kw in w.update(qid, _states(quest), quest.isComplete()):
                out(name, kw)

    def onPanel(questId=None, *a):
        tuned.append(questId)
        out('CH3END-STAYTUNED', {'next': questId})

    def wrap(fn):
        def f():
            watch()
            return fn()
        return f

    unhook = None
    try:
        unhook = getattr(H, 'hookQuests', hookQuests)(onQuest)
    except Exception as e:
        ev0('CH3END-HOOK-ERR', what='quest updates', err=repr(e)[-300:])
    panel = getattr(la, 'popupProgressBlocker', None)
    if panel is not None:
        def popupProgressBlocker(*a, **k):
            try:
                onPanel(*a)
            except Exception:
                pass
            return panel(*a, **k)
        la.popupProgressBlocker = popupProgressBlocker
    else:
        ev0('CH3END-HOOK-ERR', what='stay-tuned panel', err='no popupProgressBlocker on the pirate')

    H.ev = ev
    watch()
    gen = s_story.run(H)
    try:
        for y in gen:
            if isinstance(y, tuple) and len(y) >= 3 and y[0] in ('until', 'upto') and callable(y[1]):
                y = (y[0], wrap(y[1])) + tuple(y[2:])
            else:
                watch()
            yield y
        watch()
        if qint[LAST] in H.hist() or LAST in earlier:
            # pir-quests' pass point: the server's stay-tuned panel comes with c3.8visitJack's hand-in
            yield ('until', lambda: bool(tuned), END_WAIT, 'stay-tuned panel')
            nx = dict(q=LAST, ok=bool(tuned), next=tuned[-1] if tuned else None)
            out('CH3END-END', nx)
    finally:
        H.ev = ev0
        if unhook is not None:
            unhook()
        if panel is not None:
            try:
                del la.popupProgressBlocker
            except Exception:
                la.popupProgressBlocker = panel
    ok, rows = judge(rec)
    for q, good, why in rows:
        H.ev('CH3END-STEP', q=q, ok=good, why=why)
    byq = dict((r[0], r) for r in rows)
    for pq in POKER_QS:
        if pq in byq and byq[pq][1] and byq[pq][2] != EARLIER:
            H.ev('CH3END-POKER', q=pq, why='won at a poker table for real')
    if PEARL_Q in byq and byq[PEARL_Q][1] and byq[PEARL_Q][2] != EARLIER:
        cr = [e for e in rec if e.get('ev') == 'BOSS-CREDIT' and e.get('q') == PEARL_Q]
        H.ev('CH3END-PEARL', q=PEARL_Q, why=byq[PEARL_Q][2], way=cr[-1].get('way') if cr else None,
             fought=cr[-1].get('fought') if cr else None)
    bad = [r for r in rows if not r[1]]
    if ok:
        H.ev('PASS', mission='Chapter 3 end %s..%s' % (first, LAST), steps=len(rows),
             earlier=len([r for r in rows if r[2] == EARLIER]))
        return
    now = [q for q in H.qids() if q in KIND]
    if now and not any(r[2].startswith('not played') for r in bad):
        H.ev('CH3END-RESUME', held=now, why='the run ended before %s: run CH3END again to go on from %s' % (LAST, now[0]))
    H.ev('FAIL', why='%d of %d steps not played: %s' % (len(bad), len(rows),
                                                         '; '.join('%s %s' % (q, why) for q, _, why in bad[:6])))


def main(argv):
    if len(argv) < 3 or argv[1] != '--events':
        print('usage: python -B s_ch3end.py --events walk-CH3END-events.jsonl [more runs ...]')
        return 2
    ev = []
    for p in argv[2:]:
        ev.extend(readEvents(p))
    ok, rows = judge(ev)
    for q, good, why in rows:
        print('%-4s %-36s %s' % ('ok' if good else 'FAIL', q, why))
    print('PASS' if ok else 'FAIL: %d of %d steps' % (len([r for r in rows if not r[1]]), len(rows)))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
