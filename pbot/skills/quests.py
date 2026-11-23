"""pbot skill QUESTS (places lane, Round 2, 11-22): the player bot does its own quests (PLAYERBOTS-activities.md rows
1-9, 61, 63) with the story engine that played chapters 1-3 in the live game (s_story).

- The engine: s_story.loop(H, L), the story run's own loop (one tick per pass: the held quest, its step, the walk, the
  sail, the sea fight, the card table, the bribe, the hand-in). This skill drives it in slices (QUEST_SLICE s each)
  with one L kept across slices, so a quest picks up where the last slice left it.
- The player policy (s_story, STORY_PLAYER=1, set here for the whole bot process): never a magic word. A quest the story
  run would skip is set ASIDE (the next held quest goes first; it comes back after STORY_ASIDE_SECS or a level-up),
  repeats are played, travel is sail / walk / the map's own island teleport when the pirate holds that island's token
  (row 61), earning never grants gold, a sunk ship's repair is earned, the Black Pearl boss is set aside.
- Belt and braces: the H the engine sees refuses every H.mw. A word asked for ends the slice at once and files a BOT bug.
- Ladders: MainStory and the voodoo doll (WeaponDoll) by default (QUEST_LADDERS). Only quests the pirate HOLDS are
  played; the game hands the next one out at each hand-in, as it does for a kid.
- In a crew with a listed captain (a boy) the skill asks for no time: the brain's crew states follow him, fight
  beside him and man his cannon, and the server pays the crew's quest credit for his sinks and kills (0288, 0368).
  The bot cannot read his quest (setActiveQuest/setQuestStep are ownrecv), so it never works its own quest there.
- Events: QUEST-SLICE (start / end, what moved), QUEST-MW-BLOCKED, QUEST-STALL / QUEST-PASS / ... (the engine's own
  reserved names, renamed), QUEST-WAIT (a strict wait that ran out), QUEST-NONE (nothing held that is not set aside),
  QUEST-CHAPTER (the engine's chapter picture, not taken: no pictures in play), QUEST-SNAP, QUEST-CUT, QUEST-QUIET,
  QUEST-DOOR-HOP (the quest's door is on another island: the map's teleport there, else the quest is set aside).
- Fits pbot/skills/INTERFACE.md (pbots 11-22): limit 600, crewOk False, STORY band score 50, keys 'quests-...'. A slice
  that filed a BOT bug, a cut at the limit, or three slices in a row where nothing moved make the skill quiet for a
  while (want() None) so free play gets the turn instead of a stuck quest.

Use (same shape as the games and land skills): Quests(bot).want() -> (score, why) or None; Quests(bot).flow() is the
generator the brain drives (yields walker items, returns a result dict). bot = the brain (.H, .captain(), .bug(...)).
As a step script (PROOF_SCRIPT = this file, through pbots' runner): run(H) quests for QUEST_SECS and passes when the
story moved (a quest handed in or a task count up) with no magic word asked for and no BOT bug."""
import os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PBOT = os.path.dirname(HERE)
HARNESS = os.path.dirname(PBOT)
for _p in (PBOT, HARNESS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ['STORY_PLAYER'] = '1'      # the whole bot process plays by the player rules (s_story, s_earn, s_shipquest...)
os.environ.setdefault('STORY_LADDER', os.environ.get('QUEST_LADDERS', 'MainStory,WeaponDoll'))
os.environ.setdefault('STORY_AT', 'here')

SLICE = float(os.environ.get('QUEST_SLICE', '150'))   # s of story loop per flow (a sail or a fight can run over)
# a sea fight / dock sail / land hunt: the engine gives it only what is left of the slice (s_story SHIP_SECS and
# s_guards.SECS are capped at t_end), so 150 s never sank a ship (proof 4: 8 sea fights of 60-150 s, 0 sunk). Under the
# brain's 600 s limit.
FIGHT_SLICE = float(os.environ.get('QUEST_FIGHT_SLICE', '540'))
SCORE = 50                                            # how loudly a held quest asks the brain for the turn (STORY band)
QUIET_BUG, QUIET_IDLE, IDLES = 600, 300, 3            # quiet after a BOT bug or a limit cut / after IDLES idle slices
RESERVED = ('PASS', 'FAIL', 'STALL', 'MILESTONE', 'STATE', 'BUG', 'BRAIN')   # the brain's event names (INTERFACE 4)
DOOR_STEPS = (5, 6)                                   # QuestStep types: exterior / interior door
HOP_SECS = 90.0
NEVER = (100000170, 100000173, 100000656, 100000665)  # a proof run never plays as one of these


class Blocked(Exception):
    pass


def _S():
    import s_story           # lazily: it reads the quest ladders from the game at import
    if getattr(s_story, 'shot', None) is not _noShot:
        s_story.shot = _noShot   # no pictures in play (INTERFACE 4): the engine's chapter picture becomes an event
    return s_story


_HOOKED = []


def hooks(H):
    """The engine's own run() puts its player helpers in once before its loop (tutorial panels answered like a
    player: No to the cutlass tutorial; Darby's OK and ship name; the pistol and Barbossa tutorials). The skill calls
    loop() directly, so it puts them in itself, once per process (PBOT1-quests 11-22: without them Yes on the cutlass
    panel left the pirate in Dialog for 12 min). Not the engine's disconnect watch: a lost connection is the brain's."""
    if _HOOKED:
        return
    _HOOKED.append(1)
    S = _S()

    def pistol(h):
        import s_pistol
        S.PISTOL_OWNED.update(s_pistol.install(h))
    for f in (S.tutNo, S.okAndName, pistol, S.tutWatch, S.tutPlay):
        try:
            f(H)
        except Exception as e:
            H.ev('QUEST-HOOK-ERR', hook=getattr(f, '__name__', '?'), why=repr(e)[-200:])


def _noShot(H, name):
    H.ev('QUEST-CHAPTER', chapter=name)


def slug(s):
    return ''.join(c if c.isalnum() else '-' for c in str(s).lower()).strip('-')[:40] or 'x'


# ---------------------------------------------------------------------------------------------- pure
def sliceFor(S, q):
    """-> the slice length for quest q: FIGHT_SLICE when its task is played at sea or by a land hunt, else SLICE."""
    try:
        t = type(q.questDNA.getTasks()[0]).__name__
    except Exception:
        return SLICE
    sq = getattr(S, 's_shipquest', None)
    fights = getattr(sq, 'SHIP_TYPES', ()) + getattr(sq, 'DOCK_TYPES', ()) + getattr(S, 'ENEMY_TYPES', ())
    return FIGHT_SLICE if t in fights else SLICE


def choose(captain, qid):
    """Pure: does the quest skill want the turn? -> (score, why) or None.
    captain = the brain's captain (a boy's crew) or None; qid = the quest the engine would work on (held, not set
    aside; the main story comes first, s_story.mainQuest's ladder order) or None."""
    if captain is not None:
        return None
    if qid is None:
        return None
    return SCORE, 'quest %s' % qid


def moved(score0, score1):
    """Pure: the story moved between two chunkScores (quests handed in, task counts + finished quests held)."""
    return tuple(score1) > tuple(score0)


def doorAway(stype, step, here):
    """Pure. -> the island uid of a door step (exterior 5 / interior 6) on another island than here, else None.
    The engine sails only for an island step (stype 3); a door step on another island it walks to on the island he
    stands on (proofs 9-10, 11-22: c3r2r1r1.1recoverClaw's door is on Tortuga, the pirate on Port Royal; he walked to
    the beam at (0, 0, 0), used the nearest Port Royal door (DOOR-MISMATCH) until QUEST-STALL at 420 s: a slice
    gone every proof)."""
    if stype in DOOR_STEPS and step and here and step != here:
        return step
    return None


# ---------------------------------------------------------------------------------------------- the wrapper
class PlayerH:
    """The walker's H as the story engine sees it in a player bot: everything delegates, except magic words (refused)
    and the engine's own reserved event names (renamed QUEST-..., so they never end the brain's run), and H.snap (a
    short QUEST-SNAP line)."""

    def __init__(self, H):
        self._H = H
        self.blocked = None
        self.stalls = 0

    def __getattr__(self, k):
        return getattr(self._H, k)

    def ev(self, name, /, **kw):     # positional-only like walker.ev: an engine event may carry name= (TARGET-GONE)
        if name == 'STALL':
            self.stalls += 1
        if name in RESERVED or name.startswith(('CREW-', 'PBOT-')):
            return self._H.ev('QUEST-' + name, **kw)
        return self._H.ev(name, **kw)

    def snap(self, tag):
        return self._H.ev('QUEST-SNAP', tag=tag)

    def mw(self, word):
        self.blocked = str(word)
        self._H.ev('QUEST-MW-BLOCKED', word=str(word).split(' ')[0], full=str(word)[:80])
        raise Blocked(word)


def strict(gen, H, stop=None):
    """Drive gen, turning a strict ('until', ...) wait into ('upto', ...): the walker logs a STALL when one runs out;
    here it is a quest-wait line and the engine's own check after it decides. Returns gen's value, or ('stop', x)
    when stop() gave x before an item (gen is closed then)."""
    send = None
    while True:
        try:
            item = gen.send(send)
        except StopIteration as e:
            return e.value
        send = None
        x = stop() if stop else None
        if x:
            gen.close()
            return ('stop', x)
        if isinstance(item, tuple) and item and item[0] == 'until':
            fn, secs = item[1], item[2]
            what = item[3] if len(item) > 3 else '?'
            yield ('upto', fn, secs, what)
            try:
                ok = fn()
            except Exception:
                ok = False
            if not ok:
                H.ev('QUEST-WAIT', what=what, secs=secs)
        else:
            yield item


# ---------------------------------------------------------------------------------------------- the skill
class Quests:
    """The skill as the brain holds it. bot = the brain (it has .H, .captain() and .bug(kind, key, tag, what, tb))."""
    name = 'quests'
    limit = 600                 # a quest step with a sail or a sea fight runs past SLICE; the brain cuts at this
    crewOk = False              # in a boy's crew the brain's crew states play (the boys come first)

    def __init__(self, bot):
        self.bot, self.H = bot, bot.H
        self.PH = PlayerH(bot.H)
        self.L = None
        self.results = []
        self.quietUntil = 0
        self.idles = 0

    def _captain(self):
        f = getattr(self.bot, 'captain', None)
        try:
            return f() if f else None
        except Exception:
            return None

    def _l(self):
        if self.L is None:
            S = _S()
            self.L = dict(seen=[], stalls=[], skips=[], stopDone=lambda: False,
                          cur={'id': None, 't0': 0, 'st': {}, 'completeT': None, 'completeReal': None, 'lastAct': None},
                          passEv=lambda why: self.H.ev('QUEST-END', why=why), t_end=0, score0=S.chunkScore(self.H))
        return self.L

    def want(self):
        """-> (score, why) for the quest the engine would work on now, or None (a boy's crew, or nothing held that is
        not set aside), or None while quiet (section in the docstring)."""
        if time.time() < self.quietUntil:
            return None
        S = _S()
        try:
            q = S.mainQuest(self.H)
        except Exception:
            return None
        qid = q.getQuestId() if q is not None else None
        return choose(self._captain(), qid)

    def quiet(self, secs, why):
        self.quietUntil = time.time() + secs
        self.idles = 0
        self.H.ev('QUEST-QUIET', secs=secs, why=why)

    def cut(self, why):
        """The brain stopped the slice (limit, crew, safety, down, error). The loop state L is kept, so the quest picks
        up where it was next time. Nothing to clean up: a sail or a walk stops with the brain's release()."""
        self.H.ev('QUEST-CUT', why=why, q=(self.L or {}).get('cur', {}).get('id'))
        if why == 'limit':
            self.quiet(QUIET_BUG, 'cut at the limit')
        return None

    def away(self, S, H, L):
        """-> the island of the tracked quest's door step when that island is not the one he stands on, else None."""
        la = H.la
        qs, qid = getattr(la, 'questStep', None), L['cur'].get('id')
        if not qs or not qid or getattr(la, 'activeQuestId', None) != qid or la.getGameState() != 'LandRoam':
            return None
        return doorAway(qs.getStepType(), S.stepIslandUid(H), S.sailing.hereUid(H))

    def doorHop(self, S, H, L, uid):
        """Generator: the door step is on island uid. The map's island teleport there when he holds its token (a kid
        would sail; the engine sails only for an island step), else the quest is set aside at once."""
        qid = L['cur'].get('id')
        cancel = getattr(H, 'walk_cancel', None)
        if cancel:
            cancel()
        landed = lambda: S.sailing.hereUid(H) == uid and H.la.getGameState() == 'LandRoam'
        if S.mapOk(H, uid):
            S.mapHop(H, uid, 'door step on another island')
            yield ('upto', landed, HOP_SECS, 'door hop')
        ok = landed()
        H.ev('QUEST-DOOR-HOP', q=qid, to=uid, ok=ok)
        if ok:
            L['cur']['st'] = {}           # the walks and doors tried on the other island are not this one's
        else:
            S.skipQ(H, qid, 'door step on island %s, no map teleport there (the engine sails only for an island '
                            'step)' % uid)

    def flow(self):
        """Generator: one slice of questing. Returns {res ('progress' / 'idle' / 'bot'), why, seen, aside, stalls,
        secs, score0, score1, blocked}."""
        S, H, PH = _S(), self.H, self.PH
        hooks(PH)
        L = self._l()
        t0 = time.time()
        score0 = S.chunkScore(H)
        nSeen = len(L['seen'])
        q = S.mainQuest(H)
        secs = sliceFor(S, q)
        L['t_end'] = t0 + secs
        H.ev('QUEST-SLICE', what='start', q=q.getQuestId() if q is not None else None, secs=secs,
             aside=sorted(S.ASIDE), area=H.area())
        err, tb, key = None, '', None
        try:
            r = yield from strict(S.loop(PH, L), H, lambda: self.away(S, H, L))
            if isinstance(r, tuple) and r[0] == 'stop':
                yield from self.doorHop(S, PH, L, r[1])
        except Blocked as e:
            err = 'asked for the magic word %r' % str(e).split(' ')[0]
            key = 'quests-mw-blocked'
        except Exception as e:
            tb = traceback.format_exc()
            err = 'crashed: ' + tb.strip().splitlines()[-1][:160]
            frames = traceback.extract_tb(e.__traceback__)
            key = 'quests-crash-%s-%s' % (slug(type(e).__name__), slug(frames[-1].name if frames else '?'))
        score1 = S.chunkScore(H)
        res = 'bot' if err else ('progress' if moved(score0, score1) else 'idle')
        out = dict(res=res, why=err or ('%s -> %s' % (score0, score1)), seen=L['seen'][nSeen:], aside=sorted(S.ASIDE),
                   stalls=PH.stalls, secs=round(time.time() - t0), score0=score0, score1=score1, blocked=PH.blocked)
        H.ev('QUEST-SLICE', what='end', **out)
        self.results.append(out)
        if err:
            what = 'the player bot was questing (%s): %s' % (L['cur'].get('id'), err)
            try:
                self.bot.bug('traceback' if tb else 'other', key, 'BOT', what, tb=tb)
            except Exception:
                H.ev('QUEST-BUG-FAILED', tb=traceback.format_exc()[-300:])
            self.quiet(QUIET_BUG, key)
        elif res == 'idle':
            self.idles += 1
            if self.idles >= IDLES:
                self.quiet(QUIET_IDLE, '%d slices in a row moved nothing' % IDLES)
        else:
            self.idles = 0
        if q is None and S.mainQuest(H) is None:
            H.ev('QUEST-NONE', held=H.qids(), aside=sorted(S.ASIDE))
        return out


class _Solo:
    """A stand-in brain for run(H): no crew, files bugs straight through bugfile."""

    def __init__(self, H):
        self.H = H

    def captain(self):
        return None

    def bug(self, kind, key, tag, what, tb=''):
        import bugfile
        la = self.H.la
        sig, path, count = bugfile.report(kind, key, tag, what, where=str(self.H.area()),
                                          pirate='%s %s' % (getattr(la, 'name', '') or '?', la.doId),
                                          source='pbot quests', tb=tb)
        self.H.ev('BUG', sig=sig, kind=kind, tag=tag, what=what[:160], count=count)


def run(H):
    """Step script: quest for QUEST_SECS; PASS when the story moved, no magic word was asked for and no BOT bug."""
    secs = float(os.environ.get('QUEST_SECS', '1200'))
    la = H.la
    if la.doId in NEVER:
        H.ev('FAIL', why='refusing: pirate %s is Host\'s or a boy\'s' % la.doId)
        return
    yield ('upto', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    S = _S()
    sk = Quests(_Solo(H))
    score0 = S.chunkScore(H)
    H.ev('QUEST-RUN', secs=secs, slice=SLICE, ladders=S.LADDERS, held=H.qids(), score=score0, want=sk.want())
    t0 = time.time()
    while time.time() - t0 < secs:
        if sk.want() is None:
            if time.time() < sk.quietUntil:
                H.ev('QUEST-QUIET-WAIT', left=round(sk.quietUntil - time.time()))   # the walker's HANG is 240 s quiet
                yield 30
                continue
            H.ev('QUEST-NONE', why='nothing held that is not set aside', held=H.qids(), aside=sorted(S.ASIDE))
            yield 30
            continue
        r = yield from sk.flow()
        if r['res'] == 'bot':
            break
        yield 1
    score1 = S.chunkScore(H)
    bots = [r for r in sk.results if r['res'] == 'bot']
    ok = moved(score0, score1) and not bots
    H.ev('PASS' if ok else 'FAIL', what='quested %d s in %d slices: %s -> %s' % (time.time() - t0, len(sk.results),
                                                                                score0, score1),
         why='story moved, no magic word' if ok else (bots[0]['why'] if bots else 'the story did not move'),
         seen=[x for r in sk.results for x in r['seen']], aside=sorted(S.ASIDE))
