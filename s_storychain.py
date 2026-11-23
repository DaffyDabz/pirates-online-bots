"""STORY CHAIN (pir-bot, 11-17, job 4): one leg of a long story run, Chapter 1 to the end of Chapter 3
(c3.8visitJack), over several sessions. run_chain.ps1 runs the legs one after another.

Chapter 1 is the tutorial: run_chain.ps1's first leg is s_newplayer.py (a new pirate plays it and writes the first
checkpoint). Every later leg is this step, logged in as that pirate (BOT_AVID from newplayer-last.json).

Checkpoint file story-checkpoint-<avId>.json beside the step (STORYCHAIN_DIR to put it elsewhere): avId, the main
quest held, its index on the story ladder, the main-story quests in the history, island, area, the leg number, why
it was written and when. It is written on every quest-advanced / STORY-END / stop-done line of s_story and once at the
end of the leg, so a leg cut off by its time limit (or a crash) loses at most one quest.

At the start of a leg the checkpoint is compared with the pirate's own quest state (resumeCheck):
  done   - the history already has c3.8visitJack: CHAIN-DONE, PASS, nothing to play;
  fresh  - no checkpoint yet: start from what the pirate holds (s_story gives STORY_START if nothing);
  same   - the live quest is the checkpoint's: resume;
  ahead  - the pirate is further on than the checkpoint (the last leg ended between two writes): resume, noted;
  behind - the pirate is EARLIER than the checkpoint: the server lost story progress over a logout. CHAIN-BEHIND,
           FAIL (a real save bug; never "fixed" by giving the quest back).
Then s_story.run plays on from the held quest. s_story's STORY_AT is set to the island the pirate is on, so a resume
never teleports (s_story only teleports to STORY_AT when it is somewhere else). The leg's time: STORY_SECS (default
PROOF_SECS - 60).

Lines: CHAIN-START (checkpoint, live, verdict), CHAIN-CKPT (each write), s_story's own lines (with its PASS, if it
reaches the end, renamed STORY-PASS), CHAIN-LEG (from, to, quests advanced, stalls), CHAIN-DONE, PASS / FAIL.
PASS (one leg) = the story moved on at least one quest with no STALL line in the leg, or the chain reached the end
of Chapter 3. A leg with no progress, or with a STALL (s_story skipped a quest it could not play), is FAIL, so the
harness's two-strike rule stops the chain."""
import os, sys, time, json

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))

HOST_AV = 100000170
HERE = os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT']))
DIR = os.environ.get('STORYCHAIN_DIR') or HERE
END = 'c3.8visitJack'
LEG = int(os.environ.get('STORYCHAIN_LEG', '0') or 0)
os.environ.setdefault('STORY_STOP', END)     # s_story reads it on import: the chain's stretch ends with Chapter 3


def ckptPath(avId, d=None):
    return os.path.join(d or DIR, 'story-checkpoint-%d.json' % avId)


def readCheckpoint(avId, d=None):
    try:
        with open(ckptPath(avId, d)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def resumeCheck(ckpt, liveQ, liveIdx, liveDoneIdx, endDone):
    """Pure: (verdict, note). ckpt = the checkpoint dict or None; liveQ / liveIdx = the main quest held now and its
    ladder index (None, None when none is held); liveDoneIdx = the highest ladder index in the history (-1 none);
    endDone = c3.8visitJack is in the history."""
    if endDone:
        return 'done', 'the end of Chapter 3 is already in the history'
    if not ckpt:
        return 'fresh', 'no checkpoint: start from what the pirate holds (%s)' % liveQ
    cq, ci, cd = ckpt.get('quest'), ckpt.get('index'), ckpt.get('doneIndex', -1)
    if liveQ == cq:
        return 'same', 'resume %s' % cq
    if liveDoneIdx < cd:
        return 'behind', 'history reaches ladder %d, the checkpoint had %d' % (liveDoneIdx, cd)
    if liveIdx is not None and ci is not None and liveIdx < ci:
        return 'behind', 'holds %s (ladder %d), the checkpoint had %s (ladder %d)' % (liveQ, liveIdx, cq, ci)
    if liveIdx is None and cq is not None and liveDoneIdx < (ci if ci is not None else -1):
        return 'behind', 'holds no story quest and %s is not in the history' % cq
    return 'ahead', 'holds %s, the checkpoint had %s' % (liveQ, cq)


def position(idx, doneIdx):
    """Pure: how far along the ladder: the held quest's index, or one past the last one in the history."""
    return max(idx if idx is not None else -1, doneIdx + 1)


def legVerdict(fromIdx, toIdx, stalls, endDone):
    """Pure: (ok, why) for one leg."""
    if stalls:
        return False, '%d STALL line(s): %s' % (len(stalls), stalls[:3])
    if endDone:
        return True, 'reached the end of Chapter 3'
    if toIdx is None or fromIdx is None:
        return (toIdx is not None), 'from %s to %s' % (fromIdx, toIdx)
    if toIdx > fromIdx:
        return True, 'advanced %d quest(s) on the ladder' % (toIdx - fromIdx)
    return False, 'no story progress this leg (ladder %s)' % fromIdx


def live(H):
    """(quest id held, its ladder index, highest ladder index in the history, end done) from the pirate itself."""
    import s_story
    q = s_story.mainQuest(H)
    qid = q.getQuestId() if q is not None else None
    hist = set(H.hist())
    doneIdx = -1
    for i, sq in enumerate(s_story.STORY):
        qi = s_story._qint(sq)
        if qi is not None and qi in hist:
            doneIdx = i
    endInt = s_story._qint(END)
    return qid, s_story.ORDER.get(qid), doneIdx, endInt is not None and endInt in hist


def writeCheckpoint(H, why):
    import sailing
    la = H.la
    qid, idx, doneIdx, endDone = live(H)
    rec = {'avId': la.doId, 'name': la.getName(), 'quest': qid, 'index': idx, 'doneIndex': doneIdx, 'end': endDone,
           'island': sailing.hereUid(H), 'area': list(H.area() or []), 'leg': LEG, 'why': why,
           't': time.strftime('%Y-%m-%dT%H:%M:%S')}
    p = ckptPath(la.doId)
    tmp = p + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(rec, f, indent=1)
    os.replace(tmp, p)
    H.ev('CHAIN-CKPT', file=p, **rec)
    return rec


def run(H):
    la = H.la
    if la.doId == HOST_AV:
        H.ev('FAIL', why='refused: %d is the pirate of Host' % HOST_AV); return
    import s_story
    import sailing
    ckpt = readCheckpoint(la.doId)
    qid, idx, doneIdx, endDone = live(H)
    verdict, note = resumeCheck(ckpt, qid, idx, doneIdx, endDone)
    H.ev('CHAIN-START', leg=LEG, checkpoint=ckpt, live={'quest': qid, 'index': idx, 'doneIndex': doneIdx,
         'end': endDone}, verdict=verdict, note=note, area=H.area(), ladder=len(s_story.STORY))
    if verdict == 'done':
        H.ev('CHAIN-DONE', avId=la.doId, hist=H.hist()[-5:])
        H.ev('PASS', what='story chain already at the end of Chapter 3', avId=la.doId); return
    if verdict == 'behind':
        H.ev('CHAIN-BEHIND', note=note, checkpoint=ckpt, quests=H.qids(), hist=H.hist())
        H.ev('FAIL', why='story progress lost since the last checkpoint: %s' % note); return
    here = sailing.hereUid(H)
    if here:
        os.environ['STORY_AT'] = here            # resume where the pirate stands: no setup teleport
    if not os.environ.get('STORY_SECS'):
        os.environ['STORY_SECS'] = str(int(max(60, float(os.environ.get('PROOF_SECS', '600')) - 60)))
    writeCheckpoint(H, 'leg-start')
    ev0 = H.ev
    seen = {'stalls': [], 'pass': None}

    def ev(name, /, **kw):   # positional-only: the checkpoint record has its own 'name' (the pirate's)
        if name == 'STALL':
            seen['stalls'].append(kw.get('q') or kw.get('what'))
        if name == 'PASS':
            seen['pass'] = kw
            name = 'STORY-PASS'
        r = ev0(name, **kw)
        if name in ('quest-advanced', 'STORY-END', 'stop-done', 'STORY-PASS'):
            try:
                writeCheckpoint(H, name)
            except Exception as e:
                ev0('CHAIN-CKPT-ERR', err=repr(e))
        return r
    H.ev = ev
    try:
        yield from s_story.run(H)
    finally:
        H.ev = ev0
    end = writeCheckpoint(H, 'leg-end')
    ok, why = legVerdict(position(idx, doneIdx), position(end['index'], end['doneIndex']), seen['stalls'], end['end'])
    H.ev('CHAIN-LEG', leg=LEG, frm=qid, to=end['quest'], ok=ok, why=why, stalls=seen['stalls'],
         storyPass=bool(seen['pass']))
    if end['end']:
        H.ev('CHAIN-DONE', avId=la.doId, legs=LEG)
    if ok:
        H.ev('PASS', what='story chain leg %d: %s (%s -> %s)' % (LEG, why, qid, end['quest']), end=end['end'])
    else:
        H.ev('FAIL', why='story chain leg %d: %s' % (LEG, why))
