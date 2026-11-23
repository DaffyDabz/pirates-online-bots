"""GUNNER (pir-bot job 37, 2026-11-19): the bot plays the end of c3r2 (c3r2.5.5visitOrinda .. c3r2.5.8deliverPint) and
then Gunner's whole ladder c3r3r1Gunner (c3r3r1.1visitOrinda .. c3r3r1.53visitJoshamee), 116 steps, as the test pirate
100000001, and says per step whether it was played for real.

Run: run_walk.ps1 -Tag GUNNER -Script s_gunner.py (the harness logs walk-GUNNER-events.jsonl). Pirate 100000170 is
refused. It is a long ladder (hours): run it more than once, each run goes on from the step the pirate holds.

How: s_story plays it (talks, kills, drops, chests, ship fights and docks at sea, bribes with s_earn gold, the poker
and blackjack wins), with these env defaults (each can be overridden):
  GUNNER_FROM=tail               where a pirate that holds no step starts: 'tail' = c3r2.5.5visitOrinda, 'gunner' =
                                 c3r3r1.1visitOrinda, or any step id below. STORY_START is set from it.
  STORY_STOP=''                  s_gunner ends the run itself: Joshamee handed in, then STORY-END-NO-NEXT (GUNNER_STOP)
  STORY_GRIND=play               many steps are grind types; without this s_story would skipQuest the repeats
  STORY_WEAK_MARGIN=12           Navy lv 15 and Huge Alligators are fought, not skipped (GUNNER_WEAK_MARGIN)
  STORY_POKER=1                  c3r3r1r13r3.1poker (win 150): poker is played (check/call), not skipped. The server's
                                 poker crash (DistributedPokerTableAI.py:682) is fixed. s_earn earns the 200 a table
                                 seats with + the 100 reserve first.
s_story's main-quest list is cut to these steps (GUNNER_ONLY=1, the default), so another story quest the pirate holds
is left alone (never dropped: dropQuest writes a quest into the history, QuestManagerAI.py:392).

The order is the server's (QuestLadder.py, the same on server and client; unit_job37 checks it against the live
QuestDB): the MainStory ladder flattened, as s_story.STORY has it. Gold: bribes 50 + 500 + 50 + 50 + 10 + 10.

Step kinds (unit_job37 checks them against the QuestDB):
  talk   visit / deliver / bribe: quest-complete only
  count  a kill / drop / ship / cards step with a goal over 1, or one that waits for its own NPC to hand it in
         (completeRequiresVisit with a return NPC): its progress is seen, so quest-progress is needed too
  once   a goal-1 step that the server hands in the moment it is done (no NPC to return to): the client may never see
         its progress, so quest-complete (often via 'history') is enough

Resume: a step in the history that comes before the first step the pirate holds was handed in on an earlier run: it
counts as done ('handed in before this run'). A step at or after it that is in the history can never be handed in
again (QuestManagerAI.py:518-523): GUNNER-HISTORY + FAIL at once.

Lines (s_gunner's own):
  GUNNER-SETUP    avId, level, gold, held steps, first (the first step judged), earlier (handed in on an earlier run)
  quest-held / quest-progress / quest-complete / quest-handed-in   as s_grog
  GUNNER-POKER    c3r3r1r13r3.1poker was won for real this run
  GUNNER-NEXT     after Joshamee: the server handed out c3r3r2.1visitFabiola (Mary's ladder), ok true / false; the
                  judge counts it as one more row (pir-quests' pass point)
  GUNNER-RESUME   the run ended (time up) before Joshamee with nothing failed: the step(s) held, run it again to go on
  GUNNER-STEP     at the end, one per judged step: q, ok, why
  PASS / FAIL     PASS = every judged step done (this run or an earlier one) with quest-progress for a count step, and
                  no SKIP / STALL for any. s_story's own PASS would be STORY-PASS.

Offline judge: python -B s_gunner.py --events walk-GUNNER-events.jsonl [more runs' files]  (exit 0 on PASS; the files
of several runs are judged together, in the order given)."""
import json, os, sys

HOST_AV = 100000170

# the server's order (MainStory flattened; unit_job37 checks it). kind: see the docstring
STEPS = [
    ('c3r2.5.5visitOrinda', 'talk'),                     # Visit
    ('c3r2.5captureMontrose', 'count'),                  # CaptureShipNPC
    ('c3r2.6visitCarver', 'talk'),                       # Visit
    ('c3r2.7deliverPint', 'talk'),                       # DeliverItem
    ('c3r3r1.1visitOrinda', 'talk'),                     # Visit
    ('c3r3r1.2deliverCargo', 'talk'),                    # DeliverItem
    ('c3r3r1.3deliverCoins', 'talk'),                    # DeliverItem
    ('c3r3r1.4recoverChest', 'count'),                   # RecoverShipItem
    ('c3r3r1.5visitDuchamps', 'talk'),                   # Visit
    ('c3r3r1.6visitOlivier', 'talk'),                    # Visit
    ('c3r3r1.7recoverBarrel', 'count'),                  # RecoverTreasureItem
    ('c3r3r1.8deliverBarrel', 'talk'),                   # DeliverItem
    ('c3r3r1.9sinkShips', 'count'),                      # DefeatShip x5
    ('c3r3r1.10sinkShips', 'count'),                     # DefeatShip x3
    ('c3r3r1.11visitGunner', 'talk'),                    # Visit
    ('c3r3r1r12.1fishRum', 'count'),                     # RecoverTreasureItem
    ('c3r3r1r12.2Grog', 'count'),                        # RecoverAvatarItem
    ('c3r3r1r12.3lightRum', 'count'),                    # RecoverAvatarItem
    ('c3r3r1r12.4darkRum', 'count'),                     # RecoverAvatarItem
    ('c3r3r1r12.5fiveYearRum', 'count'),                 # RecoverShipItem
    ('c3r3r1r12.6tenYearRum', 'count'),                  # RecoverShipItem
    ('c3r3r1r12.7skeletonRum', 'count'),                 # RecoverAvatarItem
    ('c3r3r1r13r1.1visitRico', 'talk'),                  # Visit
    ('c3r3r1r13r1.2bribeRico', 'talk'),                  # BribeNPC
    ('c3r3r1r13r1.3visitGarrett', 'talk'),               # Visit
    ('c3r3r1r13r1.4bribeGarrett', 'talk'),               # BribeNPC
    ('c3r3r1r13r1.5deliverRum', 'talk'),                 # DeliverItem x10
    ('c3r3r1r13r2.1recoverRum', 'count'),                # RecoverShipItem x10
    ('c3r3r1r13r2.2recoverRum', 'count'),                # RecoverShipItem x10
    ('c3r3r1r13r3.1poker', 'count'),                     # Poker
    ('c3r3r1r13r3.2blackjack', 'count'),                 # Blackjack
    ('c3r3r1r13r4.1recoverLadle', 'count'),              # RecoverShipItem
    ('c3r3r1r13r4r2.1recoverSugar', 'count'),            # RecoverShipItem x8
    ('c3r3r1r13r4r2.2recoverWater', 'count'),            # RecoverAvatarItem x3
    ('c3r3r1r13r4r2.3recoverMud', 'once'),               # RecoverAvatarItem
    ('c3r3r1r13r4r2.4recoverBottle', 'once'),            # RecoverAvatarItem
    ('c3r3r1r13r4r3.1recoverMolasses', 'count'),         # RecoverShipItem x12
    ('c3r3r1r13r4r3.2recoverWater', 'count'),            # RecoverAvatarItem x8
    ('c3r3r1r13r4r3.3recoverVanilla', 'once'),           # RecoverShipItem
    ('c3r3r1r13r4r3.4recoverBottle', 'once'),            # RecoverAvatarItem
    ('c3r3r1r13r4r4.1recoverMolasses', 'count'),         # RecoverShipItem x4
    ('c3r3r1r13r4r4.2recoverWater', 'count'),            # RecoverAvatarItem x10
    ('c3r3r1r13r4r4.3recoverVanilla', 'once'),           # RecoverShipItem
    ('c3r3r1r13r4r4.4recoverBottle', 'once'),            # RecoverAvatarItem
    ('c3r3r1.14deliverRum', 'talk'),                     # DeliverItem x67
    ('c3r3r1.15visitGunner', 'talk'),                    # Visit
    ('c3r3r1.16visitPedro', 'talk'),                     # Visit
    ('c3r3r1.17bribePedro', 'talk'),                     # BribeNPC
    ('c3r3r1.18visitFernando', 'talk'),                  # Visit
    ('c3r3r1.19bribeFernando', 'talk'),                  # BribeNPC
    ('c3r3r1.20deliverRum', 'talk'),                     # DeliverItem x14
    ('c3r3r1.20.5visitGunner', 'talk'),                  # Visit
    ('c3r3r1r21r1.1visitRomany', 'talk'),                # Visit
    ('c3r3r1r21r1r2.1recoverMolasses', 'count'),         # RecoverShipItem x5
    ('c3r3r1r21r1r2.2recoverWater', 'count'),            # RecoverAvatarItem x3
    ('c3r3r1r21r1r2.3recoverDust', 'count'),             # RecoverAvatarItem x10
    ('c3r3r1r21r1r2.4recoverGas', 'once'),               # RecoverAvatarItem
    ('c3r3r1r21r1r2.5recoverStingers', 'count'),         # RecoverAvatarItem x10
    ('c3r3r1r21r1r2.6recoverBladder', 'once'),           # RecoverAvatarItem
    ('c3r3r1.22deliverRum', 'talk'),                     # DeliverItem x5
    ('c3r3r1.23visitGunner', 'talk'),                    # Visit
    ('c3r3r1.24visitJoshamee', 'talk'),                  # Visit
    ('c3r3r1r25r1.1visitCarver', 'talk'),                # Visit
    ('c3r3r1r25r1.2deliverPint', 'talk'),                # DeliverItem
    ('c3r3r1r25r1r3.1recoverMolasses', 'count'),         # RecoverShipItem x4
    ('c3r3r1r25r1r3.2recoverHoney', 'count'),            # RecoverShipItem x4
    ('c3r3r1r25r1r3.3recoverWater', 'count'),            # RecoverShipItem x2
    ('c3r3r1r25r1r3.4recoverCinnamon', 'count'),         # RecoverAvatarItem x12
    ('c3r3r1r25r1r3.5recoverCoconut', 'count'),          # RecoverShipItem x4
    ('c3r3r1r25r1r3.6recoverFeather', 'once'),           # RecoverAvatarItem
    ('c3r3r1r25r2.1captureArcher', 'once'),              # CaptureShipNPC
    ('c3r3r1r25r2.2maroonArcher', 'once'),               # MaroonNPC
    ('c3r3r1.26deliverRum', 'talk'),                     # DeliverItem x5
    ('c3r3r1.27visitGunner', 'talk'),                    # Visit
    ('c3r3r1r28.1recoverMolasses', 'count'),             # RecoverShipItem x3
    ('c3r3r1r28.2recoverWater', 'count'),                # RecoverAvatarItem x2
    ('c3r3r1r28.3recoverBarnacles', 'once'),             # RecoverShipItem
    ('c3r3r1r28r4.1visitTomas', 'talk'),                 # Visit
    ('c3r3r1r28r4.2deliverHairballs', 'talk'),           # DeliverItem x4
    ('c3r3r1r28.5recoverFleas', 'count'),                # RecoverAvatarItem x6
    ('c3r3r1r28.6recoverTail', 'count'),                 # RecoverAvatarItem
    ('c3r3r1r28.7recoverTooth', 'count'),                # RecoverAvatarItem
    ('c3r3r1.29deliverRum', 'talk'),                     # DeliverItem x5
    ('c3r3r1.30visitGunner', 'talk'),                    # Visit
    ('c3r3r1r31r1.1visitJoshamee', 'talk'),              # Visit
    ('c3r3r1r31r1.2visitBenedek', 'talk'),               # Visit
    ('c3r3r1r31r1.3recoverEffects', 'count'),            # RecoverTreasureItem
    ('c3r3r1r31r2.1visitFernando', 'talk'),              # Visit
    ('c3r3r1r31r2r2.1sinkNavyShips', 'count'),           # DefeatShip x5
    ('c3r3r1r31r2r2.2sinkEITCShips', 'count'),           # DefeatShip x5
    ('c3r3r1r31r2r2.3sinkSkeletonShips', 'once'),        # DefeatShip
    ('c3r3r1r31r2r2.4smuggleRum', 'once'),               # SmuggleItem
    ('c3r3r1r31r2r2.5smuggleHoney', 'once'),             # SmuggleItem
    ('c3r3r1r31r2r2.6smuggleCinnamon', 'once'),          # SmuggleItem
    ('c3r3r1.32deliverRum', 'talk'),                     # DeliverItem
    ('c3r3r1.33visitGunner', 'talk'),                    # Visit
    ('c3r3r1.34visitBarbossa', 'talk'),                  # Visit
    ('c3r3r1.35captureTrent', 'once'),                   # CaptureShipNPC
    ('c3r3r1.36maroonTrent', 'once'),                    # MaroonNPC
    ('c3r3r1.37deliverKey', 'talk'),                     # DeliverItem
    ('c3r3r1.38deliverRum', 'talk'),                     # DeliverItem
    ('c3r3r1.39visitGunner', 'talk'),                    # Visit
    ('c3r3r1.40captureJones', 'once'),                   # CaptureShipNPC
    ('c3r3r1.41visitMorris', 'talk'),                    # Visit
    ('c3r3r1.42visitPedro', 'talk'),                     # Visit
    ('c3r3r1.43bribePedro', 'talk'),                     # BribeNPC
    ('c3r3r1.44deliverDrink', 'talk'),                   # DeliverItem
    ('c3r3r1.45recoverFlags', 'count'),                  # RecoverShipItem x4
    ('c3r3r1.46visitPedro', 'talk'),                     # Visit
    ('c3r3r1.47bribePedro', 'talk'),                     # BribeNPC
    ('c3r3r1.48deliverDrink', 'talk'),                   # DeliverItem
    ('c3r3r1.49stealSchedule', 'count'),                 # RecoverContainerItem
    ('c3r3r1.50recoverRum', 'once'),                     # RecoverShipItem
    ('c3r3r1.51deliverRum', 'talk'),                     # DeliverItem
    ('c3r3r1.52visitGunner', 'talk'),                    # Visit
    ('c3r3r1.53visitJoshamee', 'talk'),                  # Visit
]
IDS = [s[0] for s in STEPS]
KIND = dict(STEPS)
IDX = dict((q, i) for i, q in enumerate(IDS))
FIRST, LAST = IDS[0], IDS[-1]
GUNNER_FIRST = 'c3r3r1.1visitOrinda'
POKER_Q = 'c3r3r1r13r3.1poker'
EARLIER = 'handed in before this run'
NEXT_Q = 'c3r3r2.1visitFabiola'   # the next chapter's first quest: the server hands it out after Joshamee
NEXT_WAIT = 30
BAD_EVENTS = ('SKIP', 'STALL', 'SKIP-NOT-SHOWN')


def fromStep(v=None):
    v = os.environ.get('GUNNER_FROM', 'tail') if v is None else v
    v = {'tail': FIRST, 'gunner': GUNNER_FIRST, '': FIRST}.get(v, v)
    if v not in IDX:
        raise ValueError('GUNNER_FROM %r is no step of this run' % v)
    return v


if __name__ != '__main__':
    os.environ.setdefault('STORY_START', fromStep())
    os.environ['STORY_STOP'] = os.environ.get('GUNNER_STOP', '')
    os.environ.setdefault('STORY_GRIND', 'play')
    os.environ.setdefault('STORY_WEAK_MARGIN', os.environ.get('GUNNER_WEAK_MARGIN', '12'))
    os.environ.setdefault('STORY_POKER', '1')
    if os.environ.get('PROOF_SCRIPT'):
        sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))


def _ts(q):
    ts = q.get('ts')
    return [tuple(t) for t in ts] if isinstance(ts, (list, tuple)) else []


def _prog(ts):
    return [t[0] or 0 for t in ts]


class Watch(object):
    """Pure (no game calls): fed H.quests() and H.hist() each tick, it says which quest-* lines to write."""

    def __init__(self, qint, earlier=()):
        self.qint = qint          # quest id -> quest int (the history holds ints)
        self.held = {}            # qid -> last progress list
        self.done = set(earlier)  # earlier: already in the history at the start, no lines for these
        self.gone = set(earlier)

    def tick(self, quests, hist):
        out = []
        hist = set(hist)
        now = dict((q['id'], q) for q in quests if q.get('id') in KIND)
        for qid in IDS:
            q = now.get(qid)
            if q is None:
                continue
            ts = _ts(q)
            p = _prog(ts)
            if qid not in self.held:
                out.append(('quest-held', {'q': qid, 'ts': ts}))
            elif p != self.held[qid] and sum(p) > sum(self.held[qid]):
                out.append(('quest-progress', {'q': qid, 'progress': p, 'goal': [t[1] for t in ts],
                                               'frm': self.held[qid]}))
            self.held[qid] = p
            if q.get('complete') and qid not in self.done:
                self.done.add(qid)
                out.append(('quest-complete', {'q': qid, 'via': 'complete', 'ts': ts}))
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
    [(qid, ok, why)] from the first GUNNER-SETUP's 'first' step (FIRST without one). A step passes with
    quest-complete (quest-progress too for a count step) or as handed in on an earlier run, and no SKIP / STALL."""
    setups = [e for e in events if e.get('ev') == 'GUNNER-SETUP']
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
    nxt = [e for e in events if e.get('ev') == 'GUNNER-NEXT']
    if any(e.get('ok') for e in nxt):
        rows.append((NEXT_Q, True, 'offered after %s (the next chapter opened)' % LAST))
    else:
        rows.append((NEXT_Q, False, 'not offered after %s' % LAST if nxt else 'never reached (no GUNNER-NEXT line)'))
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


def run(H):
    la = H.la
    if la.doId == HOST_AV:
        H.ev('FAIL', why='refused: %d is the pirate of Host' % HOST_AV)
        return
    import s_cards, s_story
    if os.environ.get('STORY_POKER') == '1':
        # s_cards / s_story may have been imported before this module set STORY_POKER
        s_cards.POKER = True
        s_story.SKIP_TYPES = tuple(t for t in ('PokerTaskDNA', 'BlackjackTaskDNA', 'BossBattleTaskDNA')
                                   if t not in s_cards.playTypes())
    qint = _qint()
    held = [q for q in H.qids() if q in KIND]
    first, earlier, late = plan(qint, held, H.hist())
    setup = dict(avId=la.doId, level=la.getLevel(), gold=getattr(la, 'getMoney', lambda: None)(), held=held,
                 first=first, earlier=earlier, start=s_story.START, grind=os.environ.get('STORY_GRIND'),
                 margin=s_story.WEAK_MARGIN, skipTypes=list(s_story.SKIP_TYPES))
    H.ev('GUNNER-SETUP', **setup)
    if late:
        H.ev('GUNNER-HISTORY', steps=late)
        H.ev('FAIL', why='steps at or after the one held are already in the quest history and can never be handed in '
                         'again (QuestManagerAI.py:518-523): %s' % ', '.join(late))
        return
    if os.environ.get('GUNNER_ONLY', '1') == '1':
        s_story.STORY = list(IDS)
        s_story.ORDER = dict(IDX)
    w = Watch(qint, earlier)
    ev0 = H.ev
    rec = [dict(setup, ev='GUNNER-SETUP')]

    def ev(name, /, **kw):
        if name == 'PASS':
            name = 'STORY-PASS'
        rec.append(dict(kw, ev=name))
        return ev0(name, **kw)

    def watch():
        try:
            for name, kw in w.tick(H.quests(), H.hist()):
                rec.append(dict(kw, ev=name))
                ev0(name, **kw)
        except Exception as e:
            ev0('GUNNER-WATCH-ERR', err=repr(e)[-300:])

    def wrap(fn):
        def f():
            watch()
            return fn()
        return f

    try:
        from pirates.quest import QuestDB
        nextInt = QuestDB.QuestDict[NEXT_Q].getQuestInt()
    except Exception:
        nextInt = None

    def offered():
        return NEXT_Q in H.qids() or (nextInt is not None and nextInt in H.hist())

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
    finally:
        H.ev = ev0
    watch()
    if qint[LAST] in H.hist() or LAST in earlier:
        # pir-quests' pass point: the server hands out Mary's first quest once Joshamee is handed in
        yield ('until', offered, NEXT_WAIT, 'next chapter %s offered' % NEXT_Q)
        nx = dict(q=NEXT_Q, ok=offered(), after=LAST)
        rec.append(dict(nx, ev='GUNNER-NEXT'))
        H.ev('GUNNER-NEXT', **nx)
    ok, rows = judge(rec)
    for q, good, why in rows:
        H.ev('GUNNER-STEP', q=q, ok=good, why=why)
    byq = dict((r[0], r) for r in rows)
    if POKER_Q in byq and byq[POKER_Q][1] and byq[POKER_Q][2] != EARLIER:
        H.ev('GUNNER-POKER', q=POKER_Q, why='won 150 at a poker table for real')
    bad = [r for r in rows if not r[1]]
    if ok:
        H.ev('PASS', mission='Gunner %s..%s' % (first, LAST), steps=len(rows),
             earlier=len([r for r in rows if r[2] == EARLIER]))
        return
    now = [q for q in H.qids() if q in KIND]
    if now and not any(r[2].startswith('not played') for r in bad):
        H.ev('GUNNER-RESUME', held=now, why='the run ended before %s: run GUNNER again to go on from %s' % (LAST, now[0]))
    H.ev('FAIL', why='%d of %d steps not played: %s' % (len(bad), len(rows),
                                                         '; '.join('%s %s' % (q, why) for q, _, why in bad[:6])))


def main(argv):
    if len(argv) < 3 or argv[1] != '--events':
        print('usage: python -B s_gunner.py --events walk-GUNNER-events.jsonl [more runs ...]')
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
