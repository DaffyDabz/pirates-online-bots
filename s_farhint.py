"""FARHINT (pir-bot job 45, 11-19): the 4 in-game checks for pir-quests' client patch 0356 (the far-sea quest hint),
as one run. pir-quests README "0356-far-sea-quest-hint.diff".

0356: a ship step no Navy Ferret (the one starter-waters class) can count for gets two more lines under its text,
    These ships sail far out to sea.
    Sail past Cuba or Cutthroat Isle to find them!
in the journal, the quest tracker, the quest card, the map marker and the offer panel; they go once the step is done.
The rule is QuestTaskDNA.needsFarSeaHint (False once the task state is complete); the text is PLocalizer.QuestFarSeaHint;
Quest.getStatusText (journal / tracker) and QuestDNA.getDescriptionText(taskStates) (offer panel) add it.

Client facts (client tree, read 11-19): la.guiMgr.questPage (la.guiMgr.initQuestPage() makes it);
updateTrackedQuestLabel(qid) puts quest.getStatusText() on trackedQuestLabel for any held quest; showQuestDetails(qid)
fills detailFrame (the journal page). Both are put back to what they showed after each read.

The checks (one FARHINT-CHECK line each, then PASS / FAIL):
  1  FARHINT_QUEST (dm1.sinkFirstEITCShip: sink 1 EITC ship, any hull; a Sea Viper level 7 is the lowest) shows both
     lines in all four texts: status, offer, tracker, journal.
  2  FARHINT_NAVY_QUEST (c3r1.1sinkNavyShips: sink 1 Navy ship, a Ferret counts) shows neither line in any of them.
  3  the far quest played: s_shipfight.questHunt sails out past the starter waters and sinks a matching ship
     (FARHINT_HUNT_SECS); when the step is credited the lines are gone from status, tracker and journal (or the quest
     is complete and gone). FARHINT_HUNT=0 skips it (the check is then SKIP and the run is PASS-PARTIAL at best).
  4  no error: QuestTaskDNA.needsFarSeaHint and PLocalizer.QuestFarSeaHint exist (the publish is in this client), and
     no read of the quest text raised (each error is a FARHINT-ERR line). pir-test also greps the client .err for
     QuestFarSeaHint / needsFarSeaHint.
Quests are given with the test word giveQuest (logged FARHINT-GIVE). Test pirates only (never 100000170 / ship
100000173). Lines: FARHINT-START, FARHINT-GIVE, FARHINT-TEXT (quest, where, the hint state, the text's end),
FARHINT-ERR, the hunt's own lines (SHIP-QUEST-START ... SHIP-QUEST-END), FARHINT-CHECK n ok, FARHINT-END, PASS / FAIL.
env: FARHINT_QUEST (dm1.sinkFirstEITCShip), FARHINT_NAVY_QUEST (c3r1.1sinkNavyShips), FARHINT_HUNT (1),
FARHINT_HUNT_SECS (1800), FARHINT_FROM (Port Royal uid)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0])))

FAR_Q = os.environ.get('FARHINT_QUEST', 'dm1.sinkFirstEITCShip')
NAVY_Q = os.environ.get('FARHINT_NAVY_QUEST', 'c3r1.1sinkNavyShips')
HUNT = os.environ.get('FARHINT_HUNT', '1') == '1'
HUNT_SECS = float(os.environ.get('FARHINT_HUNT_SECS', '1800'))
FROM = os.environ.get('FARHINT_FROM', '1150922126.8dzlu')     # Port Royal (s_story.PR)
NEVER_PIRATE, NEVER_SHIP = 100000170, 100000173
HINT = ('These ships sail far out to sea.', 'Sail past Cuba or Cutthroat Isle to find them!')
WHERE = ('status', 'offer', 'tracker', 'journal')


# ------------------------------------------------------------------------------------------------ pure
def guard(doId, ships):
    if doId == NEVER_PIRATE:
        return 'pirate %d is never touched' % NEVER_PIRATE
    if NEVER_SHIP in (ships or []):
        return 'ship %d is never touched' % NEVER_SHIP
    return None


def hintLines(text=None):
    """The two hint lines: from PLocalizer.QuestFarSeaHint when given, else the 0356 text."""
    if text:
        ls = tuple(l.strip() for l in str(text).split('\n') if l.strip())
        if len(ls) == 2:
            return ls
    return HINT


def hintState(text, lines=HINT):
    """'both' / 'none' / 'part' (one line only) / 'error' (no text)."""
    if text is None:
        return 'error'
    n = sum(1 for l in lines if l in str(text))
    return {0: 'none', len(lines): 'both'}.get(n, 'part')


def judgeTexts(states, want, skip=()):
    """states: {where: hintState}. want = 'both' or 'none'. -> (ok, [where it is wrong])."""
    bad = [w for w in WHERE if w not in skip and states.get(w) != want]
    return not bad, bad


def tail(text, n=120):
    t = ' | '.join(l.strip() for l in str(text or '').split('\n') if l.strip())
    return t[-n:]


# ------------------------------------------------------------------------------------------------ game reads
def questOf(la, qid):
    for q in la.getQuests() or []:
        if q.getQuestId() == qid:
            return q
    return None


def texts(H, qid, errs, lines):
    """{where: (hintState, text)} for held quest qid. A read that raises is logged FARHINT-ERR and counts 'error'."""
    la = H.la
    q = questOf(la, qid)
    out = {}
    if q is None:
        return out

    def read(where, fn):
        try:
            t = fn()
        except Exception as e:
            errs.append((where, qid, repr(e)))
            H.ev('FARHINT-ERR', q=qid, where=where, err=repr(e)[:300])
            t = None
        out[where] = (hintState(t, lines), t)
    read('status', q.getStatusText)
    read('offer', lambda: q.getQuestDNA().getDescriptionText(q.getTaskStates()))
    qp = None
    try:
        qp = la.guiMgr.questPage
        if qp is None:
            la.guiMgr.initQuestPage()
            qp = la.guiMgr.questPage
    except Exception as e:
        errs.append(('questPage', qid, repr(e)))
        H.ev('FARHINT-ERR', q=qid, where='questPage', err=repr(e)[:300])
    if qp is not None:
        def tracker():
            try:
                qp.updateTrackedQuestLabel(qid)
                return qp.trackedQuestLabel['text']
            finally:
                qp.updateTrackedQuestLabel(getattr(la, 'activeQuestId', None))

        def journal():
            old = getattr(qp, 'detailId', None)
            try:
                qp.showQuestDetails(qid)
                return qp.detailFrame['text']
            finally:
                qp.showQuestDetails(old)
        read('tracker', tracker)
        read('journal', journal)
    for where in WHERE:
        if where in out:
            H.ev('FARHINT-TEXT', q=qid, where=where, hint=out[where][0], text=tail(out[where][1]))
    return out


def give(H, qid):
    """Generator: hold quest qid (giveQuest when not held). -> True when held."""
    la = H.la
    if questOf(la, qid) is None:
        H.ev('FARHINT-GIVE', q=qid, held=[q.getQuestId() for q in la.getQuests() or []])
        H.mw('giveQuest %s' % qid)
        yield ('until', lambda: questOf(la, qid) is not None, 20, 'quest %s given' % qid)
    return questOf(la, qid) is not None


# ------------------------------------------------------------------------------------------------ entry
def run(H):
    la = H.la
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    no = guard(la.doId, ships)
    if no:
        H.ev('FAIL', why=no); return
    errs = []
    checks = {}
    pub = {}
    try:
        from pirates.quest import QuestTaskDNA
        pub['needsFarSeaHint'] = hasattr(QuestTaskDNA, 'needsFarSeaHint')
        pub['farSeaHintText'] = hasattr(QuestTaskDNA, 'farSeaHintText')
    except Exception as e:
        pub['needsFarSeaHint'] = False
        errs.append(('import', 'QuestTaskDNA', repr(e)))
    try:
        from pirates.piratesbase import PLocalizer
        loc = getattr(PLocalizer, 'QuestFarSeaHint', None)
    except Exception as e:
        loc = None
        errs.append(('import', 'PLocalizer', repr(e)))
    pub['QuestFarSeaHint'] = loc is not None
    lines = hintLines(loc)
    H.ev('FARHINT-START', pirate=la.doId, far=FAR_Q, navy=NAVY_Q, hunt=HUNT, secs=HUNT_SECS, published=pub,
         lines=list(lines), gs=la.getGameState(), area=H.area())

    # ---- 1 and 2: the texts of a far step and a starter-waters step
    for n, qid, want in ((1, FAR_Q, 'both'), (2, NAVY_Q, 'none')):
        held = yield from give(H, qid)
        if not held:
            checks[n] = (False, '%s was not given' % qid)
        else:
            t = texts(H, qid, errs, lines)
            ok, bad = judgeTexts(dict((k, v[0]) for k, v in t.items()), want)
            checks[n] = (ok, 'want %s everywhere%s' % (want, '' if ok else '; wrong in ' + ', '.join(bad)))
        H.ev('FARHINT-CHECK', n=n, q=qid, ok=checks[n][0], why=checks[n][1])

    # ---- 3: play the far step, then the lines must be gone
    if not HUNT:
        checks[3] = (None, 'skipped (FARHINT_HUNT=0)')
    elif questOf(la, FAR_Q) is None:
        checks[3] = (False, '%s not held' % FAR_Q)
    else:
        import sailing
        import s_lanes
        import s_shipfight
        if not sailing.onShip(H) and sailing.hereUid(H) is None:
            yield from s_lanes.onIsland(H, 'farhint', FROM)
        q = questOf(la, FAR_Q)
        res = yield from s_shipfight.questHunt(H, FAR_Q, q.getQuestDNA().getTasks()[0], HUNT_SECS)
        q = questOf(la, FAR_Q)
        if res not in ('credit', 'complete'):
            checks[3] = (False, 'the hunt ended %r before the step was done' % (res,))
        elif q is None:
            checks[3] = (True, 'the step was done and the quest is complete and gone (%s)' % res)
        else:
            yield 2                        # the quest's task state update reaches the text
            t = texts(H, FAR_Q, errs, lines)
            ok, bad = judgeTexts(dict((k, v[0]) for k, v in t.items()), 'none', skip=('offer',))
            done = False
            try:
                done = bool(q.isComplete())
            except Exception:
                pass
            checks[3] = (ok, 'hunt %s, complete=%s; %s' % (res, done, 'the hint is gone' if ok
                                                             else 'the hint is still in ' + ', '.join(bad)))
    H.ev('FARHINT-CHECK', n=3, q=FAR_Q, ok=checks[3][0], why=checks[3][1])

    # ---- 4: the publish is here and nothing raised
    ok4 = bool(pub.get('needsFarSeaHint')) and bool(pub.get('QuestFarSeaHint')) and not errs
    checks[4] = (ok4, 'published %s, %d read errors%s' % (pub, len(errs), '' if not errs else ': %s' % errs[:3]))
    H.ev('FARHINT-CHECK', n=4, ok=ok4, why=checks[4][1])

    failed = [n for n in sorted(checks) if checks[n][0] is False]
    skipped = [n for n in sorted(checks) if checks[n][0] is None]
    H.ev('FARHINT-END', checks=dict((n, checks[n][0]) for n in sorted(checks)), failed=failed, skipped=skipped,
         errors=len(errs))
    if failed:
        H.ev('FAIL', step='farhint', why='checks %s failed: %s' % (failed, '; '.join(checks[n][1] for n in failed)))
    else:
        H.ev('PASS', step='farhint', partial=bool(skipped), why='checks %s passed%s' % (
            [n for n in sorted(checks) if checks[n][0]], '' if not skipped else ', %s skipped' % skipped))
