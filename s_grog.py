"""GROG (pir-bot job 36, 2026-11-19): the bot plays Grog's ladder c3r2r5 (c3r2r5.1visitGrog .. c3r2r5.11visitJoshamee)
end to end as the test pirate 100000001, and says per step whether it was played for real.

Run: run_walk.ps1 -Tag GROG -Script s_grog.py (the harness logs walk-GROG-events.jsonl). Pirate 100000170 is refused.

How: s_story plays it (talks, kills, drops, ship fights at sea, the two bribes with s_earn gold), with these env
defaults (each can be overridden):
  STORY_START=c3r2r5.1visitGrog  given when the pirate holds no Grog step
  STORY_STOP=''                  s_grog ends the run itself: Joshamee handed in, then STORY-END-NO-NEXT
  STORY_GRIND=play               every r2 step is a grind type; without this s_story would skipQuest the repeats
  STORY_WEAK_MARGIN=12           the Giant Crabs of Entrails are level 16-23 (Driftwood); margin 3 would skip it
                                 as STORY-TOO-WEAK. GROG_WEAK_MARGIN sets it.
s_story's main-quest list is cut to the Grog steps (GROG_ONLY=1, the default), so another story quest the pirate
holds is left alone (never dropped: the server's dropQuest writes a quest into the history, QuestManagerAI.py:392).

The order the server hands the steps out (QuestLadder.py, the same on server and client; unit_job36 checks it):
  c3r2r5r2Medicine is a QuestChoiceSingle, and that class is a bare QuestLadder: no pick. The pirate gets the
  KrakenEye ladder first (r2r1.1-.5: an eye from a Navy large ship, 20 Rock Crabs, the eye to the blacksmith, his
  50-gold bribe, the powder to Grog), then Crocwater (5 Big Alligators), then Entrails (2 Giant Crabs on Driftwood).
  Medicine2, 3 and 4 are QuestChoices: all their steps at once (s_story plays them in ladder order). Medicine3 has
  r2.9recoverWater, 4 EITC ships: hull 108 is no ship list (getShipList(108) is None), so any EITC ship counts;
  patch 0306 drops the hull on the server too. r2.9 PASS = the 0306 proof line GROG-0306.

Lines (s_grog's own):
  GROG-SETUP     avId, level, gold, held Grog steps, Grog steps already in the history
  quest-held     a Grog step is held (first seen), with its task states [progress, goal, attempts]
  quest-progress a Grog step's task progress went up: q, progress, goal, frm
  quest-complete a Grog step is done: q, via 'complete' (the client shows it done) or 'history' (handed in before
                 the client showed it)
  quest-handed-in the step left the quest list and is in the history
  GROG-STEP      at the end, one per step: q, ok, why
  GROG-0306      r2.9recoverWater counted 4 EITC ships
  PASS / FAIL    PASS = every step has quest-complete (and quest-progress if it is a kill / drop / ship step) and no
                 SKIP / STALL / STORY-TOO-WEAK for it. s_story's own PASS (none with STORY_STOP='') would be
                 STORY-PASS.
A Grog step already in the history at the start can never be handed in again (QuestManagerAI.py:518-523): FAIL
GROG-HISTORY at once, the pirate needs those history entries removed first.

Offline judge: python -B s_grog.py --events walk-GROG-events.jsonl  (exit 0 on PASS; prints one line per step)."""
import json, os, sys

HOST_AV = 100000170

# the server's order (see above). kind: talk (visit / deliver / bribe: quest-complete only) or count (kill / drop /
# ship: quest-progress too)
STEPS = [
    ('c3r2r5.1visitGrog', 'talk'),
    ('c3r2r5r2r1.1recoverEyeShips', 'count'),
    ('c3r2r5r2r1.2defeatCrabs', 'count'),
    ('c3r2r5r2r1.3deliverEye', 'talk'),
    ('c3r2r5r2r1.4bribeBlacksmith', 'talk'),
    ('c3r2r5r2r1.5deliverPowder', 'talk'),
    ('c3r2r5r2.2recoverCrocwater', 'count'),
    ('c3r2r5r2.3recoverEntrails', 'count'),
    ('c3r2r5r2.4recoverGuano', 'count'),
    ('c3r2r5r2.5recoverSplinter', 'count'),
    ('c3r2r5r2.6recoverDust', 'count'),
    ('c3r2r5r2.7recoverEarth', 'count'),
    ('c3r2r5r2.8recoverLichens', 'count'),
    ('c3r2r5r2.9recoverWater', 'count'),
    ('c3r2r5r2.10recoverEggs', 'count'),
    ('c3r2r5r2.11recoverMoney', 'count'),
    ('c3r2r5r2.12recoverNightshade', 'count'),
    ('c3r2r5r2.13recoverWhiskers', 'count'),
    ('c3r2r5.3deliverJack', 'talk'),
    ('c3r2r5.4recoverEyes', 'count'),
    ('c3r2r5.5deliverJack', 'talk'),
    ('c3r2r5.6deliverEyes', 'talk'),
    ('c3r2r5.7deliverMallet', 'talk'),
    ('c3r2r5.8bribeMallet', 'talk'),
    ('c3r2r5.9deliverRemedy', 'talk'),
    ('c3r2r5.10administerRemedy', 'talk'),
    ('c3r2r5.11visitJoshamee', 'talk'),
]
IDS = [s[0] for s in STEPS]
KIND = dict(STEPS)
FIRST, LAST = IDS[0], IDS[-1]
WATER = 'c3r2r5r2.9recoverWater'
BAD_EVENTS = ('SKIP', 'STALL', 'SKIP-NOT-SHOWN')

if __name__ != '__main__':
    os.environ.setdefault('STORY_START', FIRST)
    os.environ['STORY_STOP'] = os.environ.get('GROG_STOP', '')
    os.environ.setdefault('STORY_GRIND', 'play')
    os.environ.setdefault('STORY_WEAK_MARGIN', os.environ.get('GROG_WEAK_MARGIN', '12'))
    if os.environ.get('PROOF_SCRIPT'):
        sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))


def _ts(q):
    ts = q.get('ts')
    return [tuple(t) for t in ts] if isinstance(ts, (list, tuple)) else []


def _prog(ts):
    return [t[0] or 0 for t in ts]


class Watch(object):
    """Pure (no game calls): fed H.quests() and H.hist() each tick, it says which quest-* lines to write."""

    def __init__(self, qint):
        self.qint = qint          # quest id -> quest int (the history holds ints)
        self.held = {}            # qid -> last progress list
        self.done = set()
        self.gone = set()

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
            if qid in self.held and qid not in now and qid not in self.gone and self.qint.get(qid) in hist:
                self.gone.add(qid)
                if qid not in self.done:
                    self.done.add(qid)
                    out.append(('quest-complete', {'q': qid, 'via': 'history'}))
                out.append(('quest-handed-in', {'q': qid}))
        return out


def judge(events):
    """events: the walk-*-events.jsonl records (dicts with 'ev'). -> (ok, rows), rows = [(qid, ok, why)] in STEPS
    order. A step passes with quest-complete, quest-progress too for a count step, and no SKIP / STALL for it."""
    st = dict((q, {'held': False, 'prog': [], 'done': None, 'bad': []}) for q in IDS)
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
    for q in IDS:
        s = st[q]
        if s['bad']:
            rows.append((q, False, 'not played for real: %s' % '; '.join(s['bad'])))
        elif s['done'] is None:
            rows.append((q, False, 'never completed' if s['held'] else 'never held'))
        elif KIND[q] == 'count' and not s['prog']:
            rows.append((q, False, 'completed (%s) with no quest-progress line' % s['done']))
        else:
            rows.append((q, True, 'complete (%s)%s' % (s['done'], ', progress %s' % s['prog'][-1] if s['prog'] else '')))
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
    import s_story
    qint = _qint()
    hist = set(H.hist())
    inHist = [q for q in IDS if qint[q] in hist]
    held = [q for q in H.qids() if q in KIND]
    H.ev('GROG-SETUP', avId=la.doId, level=la.getLevel(), gold=getattr(la, 'getMoney', lambda: None)(), held=held,
         inHistory=inHist, start=s_story.START, grind=os.environ.get('STORY_GRIND'), margin=s_story.WEAK_MARGIN)
    if inHist:
        H.ev('GROG-HISTORY', steps=inHist)
        H.ev('FAIL', why='Grog steps already in the quest history can never be handed in again '
                         '(QuestManagerAI.py:518-523): %s' % ', '.join(inHist))
        return
    if os.environ.get('GROG_ONLY', '1') == '1':
        s_story.STORY = list(IDS)
        s_story.ORDER = dict((q, i) for i, q in enumerate(IDS))
    w = Watch(qint)
    ev0 = H.ev
    rec = []

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
            ev0('GROG-WATCH-ERR', err=repr(e)[-300:])

    def wrap(fn):
        def f():
            watch()
            return fn()
        return f

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
    ok, rows = judge(rec)
    for q, good, why in rows:
        H.ev('GROG-STEP', q=q, ok=good, why=why)
    water = dict((r[0], r) for r in rows)[WATER]
    if water[1]:
        H.ev('GROG-0306', q=WATER, why='4 EITC ships counted, any hull (hull 108 is no ship list; 0306)')
    bad = [r for r in rows if not r[1]]
    if ok:
        H.ev('PASS', mission='Grog %s..%s' % (FIRST, LAST), steps=len(rows))
    else:
        H.ev('FAIL', why='%d of %d Grog steps not played: %s' % (len(bad), len(rows),
                                                                  '; '.join('%s %s' % (q, why) for q, _, why in bad[:6])))


def main(argv):
    if len(argv) < 3 or argv[1] != '--events':
        print('usage: python -B s_grog.py --events walk-GROG-events.jsonl')
        return 2
    ok, rows = judge(readEvents(argv[2]))
    for q, good, why in rows:
        print('%-4s %-32s %s' % ('ok' if good else 'FAIL', q, why))
    print('PASS' if ok else 'FAIL: %d of %d steps' % (len([r for r in rows if not r[1]]), len(rows)))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
