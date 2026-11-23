"""CREWQ (pir-bot job 33, 11-19): two bots on one ship, both on c3r2r1.12recoverWarrants, to prove server patch 0288.

0288 (pir-quests README): a Navy ship sunk by a crewed ship credits the quest of every pirate the sink pays, once per
pirate per ship. Before it, only the pirate whose shot took the last hit point got the warrant roll.

Two hidden games run this step at once: run_two.ps1 -Tag CREWQ -Script s_crewquest.py (same env as CREW2:
BOT_ACCOUNT2 + BOT_AVID2 = the mate; the captain is 100000001 by default). Neither is ever Host's pirate 100000170
nor his ship 100000173 (s_crew2.checkSetup / pickOffer refuse them).

Both: CREWQ-START; the quest given with giveQuest when not held (test pirates only), CREWQ-QUEST; then the CREW2 join
(s_crew2.captain / mate: invite, accept, launch, dinghy, the crew ship row). Its PASS lines are logged here as
CREWQ-JOINED, so a run is only PASS once the quest part passes.
captain: hunts Navy ships with the story's ship fight (s_shipfight.questHunt: the Picker counts only ships the task
  counts), again and again until CREWQ_SINKS sinks moved its quest, the quest is done, or CREWQ_SECS run out. Each
  hunt's end: CREWQ-HUNT (r, prog before / after). It never leaves the wheel to the mate.
mate: stays aboard and presses nothing (never takes the wheel or a cannon), so any credit it gets is 0288's. It logs
  CREWQ-PROG on every change of its task state (progress or attempts: a roll counted even when the warrant did not
  drop) with the time, and CREWQ-SHIP-GONE if the crew ship goes.
PASS captain = its quest moved after a sink. PASS mate = its quest moved while aboard the captain's ship (this step
  never fires for it). judge(captainEvents, mateEvents) (pure) also checks offline that each mate rise came within WINDOW s of a
  captain sink (SHIP-GOLD line): the proof the brain reads.
env: CREWQ_QUEST (c3r2r1.12recoverWarrants), CREWQ_SINKS (2), CREWQ_SECS (2400), CREW_* as s_crew2."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_crew2   # noqa: E402

QUEST = os.environ.get('CREWQ_QUEST', 'c3r2r1.12recoverWarrants')
SINKS = int(os.environ.get('CREWQ_SINKS', '2'))
SECS = float(os.environ.get('CREWQ_SECS', '2400'))
WINDOW = 60.0          # s from a captain sink (SHIP-GOLD) to a mate rise, for judge()
HOST_AV, HOST_SHIP = s_crew2.HOST_AV, s_crew2.HOST_SHIP


# ------------------------------------------------------------------------------------------------ pure
def rose(p0, p1):
    """True when a task state moved: [(progress, attempts)] before / after (s_shipquest.prog). None after = the
    quest was handed in / completed away, which is a move too when it was held before."""
    if p0 is None:
        return False
    if p1 is None:
        return True
    return list(p0) != list(p1)


def judge(cap, mate, window=WINDOW):
    """cap / mate = the two runs' event dicts (walk-CREWQ-<role>-events.jsonl rows). -> (ok, why, pairs):
    pairs = [(sink time, mate rise time)] of mate rises within window s after a captain sink."""
    sinks = [e.get('t') for e in cap if e.get('ev') == 'SHIP-GOLD' and e.get('t') is not None]
    rises = [e.get('t') for e in mate if e.get('ev') == 'CREWQ-PROG' and e.get('t') is not None]
    if not any(e.get('ev') == 'PASS' for e in cap):
        return False, 'no captain PASS (its quest never moved after a sink)', []
    if not any(e.get('ev') == 'PASS' for e in mate):
        return False, 'no mate PASS (its quest never moved while aboard)', []
    pairs = []
    for r in rises:
        before = [s for s in sinks if s <= r and r - s <= window]
        if before:
            pairs.append((max(before), r))
    if not pairs:
        return False, 'no mate rise within %d s of a captain sink' % window, []
    return True, '%d mate rise(s) right after a captain sink' % len(pairs), pairs


def questOf(quests, qid):
    """The held quest with id qid (H.la.getQuests()), or None."""
    for q in quests or []:
        if q.getQuestId() == qid:
            return q
    return None


# ------------------------------------------------------------------------------------------------ in the game
def prog(H):
    q = questOf(H.la.getQuests(), QUEST)
    if q is None:
        return None
    try:
        return [(getattr(s, 'progress', None), getattr(s, 'attempts', None)) for s in q.getTaskStates()]
    except Exception:
        return []


def joinEvents(H):
    """Wrap H.ev so the CREW2 join's PASS is logged as CREWQ-JOINED (the run is PASS only for the quest part).
    -> (restore, seen) where seen['joined'] / seen['fail'] tell how the join ended."""
    orig = H.ev
    seen = {}

    def ev(kind, /, **kw):
        if kind == 'PASS':
            seen['joined'] = kw
            return orig('CREWQ-JOINED', **kw)
        if kind == 'FAIL':
            seen['fail'] = kw.get('why')
        return orig(kind, **kw)
    H.ev = ev

    def restore():
        H.ev = orig
    return restore, seen


def getQuest(H):
    """Generator: the quest held (giveQuest on a test pirate when not). -> True when held."""
    if questOf(H.la.getQuests(), QUEST) is None:
        H.ev('CREWQ-QUEST', what='give', q=QUEST, held=[q.getQuestId() for q in H.la.getQuests()])
        H.mw('giveQuest %s' % QUEST)
        yield ('until', lambda: questOf(H.la.getQuests(), QUEST) is not None, 20, 'quest given')
    held = questOf(H.la.getQuests(), QUEST) is not None
    H.ev('CREWQ-QUEST', what='held' if held else 'not-given', q=QUEST, prog=prog(H))
    return held


def run(H):
    la = H.la
    role = s_crew2.ROLE
    why = s_crew2.checkSetup(role, la.doId, s_crew2.CAPTAIN, s_crew2.MATE)
    H.ev('CREWQ-START', role=role, me=la.doId, captain=s_crew2.CAPTAIN, mate=s_crew2.MATE, q=QUEST, sinks=SINKS,
         secs=SECS, why=why)
    if why:
        H.ev('FAIL', why=why); return
    if not (yield from getQuest(H)):
        H.ev('FAIL', why='%s is not held and giveQuest did not give it' % QUEST); return
    restore, seen = joinEvents(H)
    try:
        yield from s_crew2.run(H)
    finally:
        restore()
    if 'joined' not in seen:
        H.ev('FAIL', why='the crew join did not finish: %s' % seen.get('fail')); return
    if role == 'captain':
        yield from captain(H)
    else:
        yield from mate(H)


def captain(H):
    import s_shipfight
    la = H.la
    t0 = time.time()
    moved = 0
    r = None
    while time.time() - t0 < SECS and moved < SINKS:
        q = questOf(la.getQuests(), QUEST)
        if q is None:
            break
        p0 = prog(H)
        try:
            r = yield from s_shipfight.questHunt(H, QUEST, q.questDNA.getTasks()[0], SECS - (time.time() - t0))
        except Exception:
            import traceback
            r = 'error'
            H.ev('CREWQ-ERROR', tb=traceback.format_exc()[-600:])
        p1 = prog(H)
        if rose(p0, p1) and r in ('credit', 'complete'):
            moved += 1
        H.ev('CREWQ-HUNT', r=r, before=p0, after=p1, moved=moved, crew=crewOf(H))
        if p1 is None or not s_crew2.sailing.onShip(H):
            break             # quest done, or our ship went down / he left it (the mate's ship is gone too)
    if moved:
        H.ev('PASS', what='the captain\'s quest moved after %d sink(s)' % moved, q=QUEST, prog=prog(H))
    else:
        H.ev('FAIL', why='no sink moved the captain\'s quest (last hunt: %s)' % r, prog=prog(H))


def crewOf(H):
    s = H.cr.doId2do.get(H.la.getCrewShipId()) if hasattr(H.la, 'getCrewShipId') else None
    try:
        return list(s.getCrew() or []) if s is not None else None
    except Exception:
        return None


def mate(H):
    la = H.la
    t0 = time.time()
    ship = la.getCrewShipId()
    last = prog(H)
    rises = 0
    H.ev('CREWQ-WATCH', ship=ship, prog=last)
    while time.time() - t0 < SECS:
        p = prog(H)
        if p != last:
            aboard = la.getCrewShipId() == ship
            H.ev('CREWQ-PROG', before=last, after=p, aboard=aboard, gs=la.getGameState())
            if rose(last, p) and aboard:
                rises += 1
                if rises == 1:
                    H.ev('PASS', what='the mate\'s quest moved while aboard the captain\'s ship %s' % ship,
                         q=QUEST, before=last, after=p)
            last = p
            if p is None:
                break
        if la.getCrewShipId() != ship:
            H.ev('CREWQ-SHIP-GONE', ship=ship, now=la.getCrewShipId(), gs=la.getGameState())
            break
        yield 1
    if not rises:
        H.ev('FAIL', why='the mate\'s quest never moved while aboard in %d s' % (time.time() - t0), prog=last)
