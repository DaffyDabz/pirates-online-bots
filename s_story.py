"""Follow-the-beam MainStory walker (item 7). Plays the WHOLE main story the way a kid would: read the quest
tracker step, go there (door / NPC / tunnel / quest node / area), talk to NPCs, bribe, search, fight the right enemy
type. Cutscenes/dialogs play for real. Moving to ANOTHER ISLAND is sailed for real (sailing.sail_to: dinghy, wheel,
keyboard steering, anchor), never teleported. Walking between spots on the same island is a real walk (held keys,
never setPos); a spot it cannot walk to is reported (stuck event) and left to the stall / skip logic.

The chain is read from the game itself (QuestLadderDB MainStory: Chapter 1 -> 2 -> 3 ... c3.8visitJack), so STORY
is the true ladder, choices included (a QuestChoice hands out all its quests at once; all must be done).
Ship quests (sink / capture / loot ships, smuggle, maroon) are played at sea: sink / capture / recover-cargo by
s_shipfight.questHunt (job 30: the careful lane fight on only the ships the task counts, SHIP-GOLD per sink;
STORY_SHIP_CAREFUL=0 = the bare s_shipquest.hunt), smuggle / maroon by s_shipquest.dock at the task's port. Card quests (Blackjack; Poker with STORY_POKER=1) are
played at a tavern table by s_cards: walk in, sit, press the table's own buttons until the gold goal counts. The
Black Pearl boss battle runs through s_cards.boss with STORY_BOSS=1. Task types left off are skipQuest'd with a SKIP
event naming the type - see SKIP_TYPES. Grind types (kills, drops, digs, searches) play for real once; their
later branch-quest repeats are skipQuest'd too (SKIP q/type/why) - see GRIND_TYPES, story-proven.json, STORY_GRIND.

env: STORY_AT (island uid the run starts on, default Port Royal: a logged SETUP-TP before the story starts, never
mid-story; 'here' = stay on the island he logged in on), STORY_START (quest id to give when none is held), STORY_STOP (the last quest of this stretch: PASS when it
completes with no STALL skip on the way; SKIP-type skips are listed in the PASS event), STORY_LIMIT (s without
progress = STALL), STORY_SHIP_SECS (one hunt at sea, default 900), STORY_SHIP_LIMIT (s without progress on a ship
quest = STALL, default 1800), STORY_SECS (total), STORY_TP=1 (old behaviour: areaTeleport between islands instead of sailing).
Walks longer than ROUTE_MIN ft on an island go round the buildings (paths.walk_route), then a straight last bit.
A talk left open in NPCInteract (job 16) is clicked through once a task is done (NPC-CLICK), then ended the game's
own way after NPC_LIMIT s (NPC-EXIT); with nothing done it is ended after NPC_HARD s (NPC-STUCK)."""
import math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402
import paths     # noqa: E402
import s_shipquest   # noqa: E402
import s_cards       # noqa: E402
import s_guards      # noqa: E402  (pir-quests 11-17: land kill quests fought with s_fighter)
import s_earn        # noqa: E402  (pir-bot job 23b: earn the gold for a bribe first)

# STORY_LADDER (11-20 whole-story bot): comma list of QuestLadderDB.FameQuestLadderDict keys the walker follows, in
# order (default MainStory). WeaponDoll,TeleportTotem = Tia Dalma's voodoo doll chain and the teleport totem chain.
LADDERS = [x.strip() for x in os.environ.get('STORY_LADDER', 'MainStory').split(',') if x.strip()]
START = os.environ.get('STORY_START', '')
STOP = os.environ.get('STORY_STOP', '')
LIMIT = float(os.environ.get('STORY_LIMIT', '420'))
# a picture each time a chapter ends (the quest id before its first '.' changes: wdr4 -> wdr6), STORY-SHOT
SHOTS = os.environ.get('STORY_SHOTS', r'C:\PiratesBots\out\story\shots')


def chapter(qid):
    return (qid or '').split('.')[0]


def runTag():
    return os.path.basename(os.environ.get('PROOF_EVOUT', '')).replace('walk-', '').replace('-events.jsonl', '') or 'story'


def shot(H, name):
    from panda3d.core import Filename
    p = os.path.join(SHOTS, name + '.png')
    try:
        os.makedirs(SHOTS, exist_ok=True)
        H.B.graphicsEngine.renderFrame()
        ok = H.B.win.saveScreenshot(Filename.fromOsSpecific(p))
    except Exception as e:
        ok = 'err %r' % e
    H.ev('STORY-SHOT', name=name, path=p, ok=ok, gs=H.la.getGameState())

# ship quests (sink / dock, s_shipquest): one hunt at sea lasts up to SHIP_SECS; no progress for SHIP_LIMIT = STALL
SHIP_SECS = float(os.environ.get('STORY_SHIP_SECS', '900'))
SHIP_LIMIT = float(os.environ.get('STORY_SHIP_LIMIT', '1800'))
# MAIN30 (11-21): Archer's capture (Navy warships: the server draws each sea ship from 27 classes at random, so about
# 3 lv-9 Panthers in the whole sea) saw 22 ships and none it counts in a 600 s far search. SHIP_LIMIT never ran out
# inside a 20-min chunk, so each chunk would hunt again. A branch quest (rN) whose hunt ends 'no-target' with no
# progress is skipped (SHIP-RARE); a main-line one still waits for the STALL. 0 = off.
SHIP_RARE_SKIP = os.environ.get('STORY_SHIP_RARE_SKIP', '1') != '0'
# pir-bot job 30: sink / capture / recover-cargo quests fought the careful way (s_shipfight.questHunt: fair foe among
# the ships the task counts, beam hold, break-off + repair, SHIP-GOLD per sink). 0 = the bare s_shipquest.hunt.
SHIP_CAREFUL = os.environ.get('STORY_SHIP_CAREFUL', '1') != '0'
HANDIN_LIMIT = 240      # a complete quest with a step: time to walk to the return NPC and hand it in
# job 20 (NEWP13-NP2): time spent sailing never counts against HANDIN_LIMIT (c3visitJoshamee was done at 42 s, then
# a 250 s sail to Tortuga ran the hand-in clock out: a false STALL the moment he landed). DOOR_REACH: a door's own
# interact sphere is 7 ft (DistributedDoorBase sphereScale 7.0) and the server checks no distance, so a door within
# DOOR_REACH ft (3D) is used from there (he stood 3.2 ft off Bonita's door on its step for 12 min, 40 go-failed).
# GOFAIL_MAX: that many go-failed in a row on one quest step = GO-BLOCKED, logged, then the quest is skipped.
DOOR_REACH = float(os.environ.get('STORY_DOOR_REACH', '6.5'))
GOFAIL_MAX = int(os.environ.get('STORY_GOFAIL_MAX', '6'))
# job 16 (NEWP12-NP2): the pirate sat 18 min in NPCInteract after Joshamee Gibbs (task done [1,1,0]).
NPC_CLICK = 3.0       # s in NPCInteract with a task done: press the dialog's own Next / OK / Accept button
NPC_LIMIT = 30.0      # s in NPCInteract with a task done: end the interact the game's way (NPC-EXIT)
NPC_HARD = 120.0      # s in NPCInteract with nothing done: same, logged NPC-STUCK first
PR = '1150922126.8dzlu'
# STORY_FROM=mansion: before the first quest is given, walk (held keys) to where a player stands after c2.5, the
# governor's mansion yard; run setup only, used for the c2.9 Darby replay after reset_c29.sh
FROM = {'mansion': (-261.8, -688.0, 47.0)}.get(os.environ.get('STORY_FROM', ''))
FINAL = 'c3.8visitJack'      # MainStory's last quest; another ladder's end is its own last quest (FINALS below)
# card games / the Black Pearl boss battle the bot does not play (s_cards plays the ones its env turns on:
# STORY_BLACKJACK default on, STORY_POKER=1, STORY_BOSS=1)
SKIP_TYPES = tuple(t for t in ('PokerTaskDNA', 'BlackjackTaskDNA', 'BossBattleTaskDNA') if t not in s_cards.playTypes())
ENEMY_TYPES = ('DefeatTaskDNA', 'RecoverAvatarItemTaskDNA')
# DOLL18 (11-21): Tia Dalma's blood quests (wdr4.x) name no place, and the server's beam sent him to Padres' south beach,
# 1,800 ft and a volcano from where he lands; the route search ran dry 3 times (100-200 s each) and the chunk was gone.
# A kill task that names no place is hunted where its enemy is thick and a short walk from the dock (quest_spots.json
# areas): AvatarTypes name -> areas. STORY_HUNT=0 = follow the beam as before.
HUNT = {'RockCrab': ('1161282725.84kmuller',), 'Wasp': ('1161282725.84kmuller',),         # Rumrunner's Isle
        'Scorpion': ('1164141722.61sdnaik',), 'Alligator': ('1164141722.61sdnaik',),      # Port Royal jungle C
        'Bat': ('1164141722.61sdnaik',),
        # Tia Dalma's bone dust (wdr6.x): the mud monsters spawn only in Port Royal jungles A and C (worldData)
        'Clod': ('1164141722.61sdnaik',), 'Muck': ('1164141722.61sdnaik',),
        'Sludge': ('1169592956.59sdnaik',), 'Mire': ('1169592956.59sdnaik', '1164141722.61sdnaik')}
# job 33: a kill task whose enemies are more than WEAK_MARGIN levels above the pirate is skipped (STORY-TOO-WEAK):
# Greer's ladder asks level-7 Undead in the Port Royal jungles and level-12 Undead in its cave B
WEAK = os.environ.get('STORY_WEAK', '1') == '1'
WEAK_MARGIN = int(os.environ.get('STORY_WEAK_MARGIN', '3'))


def tooWeak(need, have, seen=None, margin=None):
    """job 33, pure: need = the task's enemy level (the lowest it counts), have = the pirate's level, seen = levels of
    the counted enemies in view. -> (level, have) when the weakest enemy the task counts is more than margin levels
    above the pirate (too weak: skip the quest), else None."""
    margin = WEAK_MARGIN if margin is None else margin
    lv = max([int(need or 0)] + ([min(seen)] if seen else []))
    return (lv, int(have or 0)) if lv > int(have or 0) + margin else None
# grind types: kills, drops, digs, searches. These hand themselves in on the last credit (QuestManagerAI
# completeTaskState -> completeQuest), so a GM skip of one skips no hand-in. Once a type is played for real it is
# written to story-proven.json; its later repeats are skipQuest'd (SKIP event: q, type, why). Main-line quests
# (no rN branch) and quests with finalize scenes always play for real. STORY_GRIND=play plays every one.
GRIND_TYPES = ('DefeatTaskDNA', 'RecoverAvatarItemTaskDNA', 'RecoverTreasureItemTaskDNA', 'RecoverContainerItemTaskDNA')
# MAIN6 (11-21): Grog's r2.9recoverWater (4 EITC ships, lv 37-44) kept a notoriety-7 pirate at sea 9 min with no
# sink, after Splinter (a ship drop) was credited for real. Ship kills and drops credit themselves the same way, so
# they are proven and skipped like the land grinds (each type on its own); GRIND_TYPES stays the land-only list.
SHIP_SKIP_TYPES = ('DefeatShipTaskDNA', 'RecoverShipItemTaskDNA')
# DOLL14 (11-21): this list was named SKIP_TYPES and so replaced the card-game list above, and act() GM-skipped every
# land grind unplayed (Wire, the totem's Bat/Wasp/Leaf/Artifact). Its own name keeps the two apart.
REPEAT_TYPES = GRIND_TYPES + SHIP_SKIP_TYPES
PROVEN_FILE = os.path.join(os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])), 'story-proven.json')
ROUTE_MIN = 30.0      # ft: a walk longer than this on an island is planned round the buildings
# DOLL10 (11-21): no route found to a pitch barrel 1341 ft off on the Port Royal hill, so the old straight last walk
# took him off the dock into the sea, where he swam for 15 min. Past BLIND_MAX ft with a route search that ran, no
# straight walk: the walk fails (go-failed) and the caller picks another target
BLIND_MAX = float(os.environ.get('STORY_BLIND_MAX', '150'))
NEAR_GAIN = 20.0      # ft: a walk to where the route search got nearest must gain at least this much (nearWay)
SWIM_SECS = 5.0       # s: swimming this long off a ship = swim back to where he last stood on land
SWIM_TRIES = 3        # swims back that still leave him in the water = a teleport to a port (SWIM_TPS), then STALL
SWIM_TPS = 1          # MAIN35: teleports to a port per quest after the swims back fail, before the quest is skipped
TORTUGA = '1156207188.95dzlu'
# MAIN39 (11-22): he stood 4.9 ft from the stealSchedule chest on the Padres cliff, inside its 'Search' prompt (the
# container's sphereScale, world data 'Aggro Radius', 5 ft by default), walked at 3 ft for 3.5 min and the quest was
# skipped. A container counts as reached inside its own sphere, at most CONTAINER_REACH ft (3D)
CONTAINER_REACH = float(os.environ.get('STORY_CONTAINER_REACH', '8'))
RETRACE_NEAR = 15.0   # ft: a walk back the way he came starts only within this of where that walk ended (retraceWay)
TRAIL = {}           # the last island walk that reached its goal: area uid + the points he stood on (go, retraceWay)
TALK = 10.0           # ft: a townfolk's talk prompt shows inside 12 ft (InteractiveBase sphereScale); Darby is
                      # behind his booth counter, so a player talks from across it, never from 5 ft


def _ladderNode(name):
    """A ladder by name: Fame ladders (MainStory, WeaponDoll) or Fortune ones (TeleportTotem)."""
    from pirates.quest import QuestLadderDB
    for d in (QuestLadderDB.FameQuestLadderDict, QuestLadderDB.FortuneQuestLadderDict):
        if name in d:
            return d[name]
    raise KeyError('no quest ladder %r' % name)


def _ladder():
    from pirates.quest import QuestLadderDB
    from pirates.quest.QuestDNA import QuestDNA
    out = []

    def walk(n):
        if isinstance(n, QuestDNA):
            out.append(n.getQuestId())
        else:
            for c in n.getContainers():
                walk(c)
    for name in LADDERS:
        walk(_ladderNode(name))
    return out


def _choiceSiblings(qid):
    """The other quests of the QuestChoice that hands out qid (a choice gives all its quests at once and holds a
    finished one until every sibling is done), or [] when qid is not in a choice."""
    from pirates.quest import QuestLadderDB
    from pirates.quest.QuestDNA import QuestDNA
    from pirates.quest.QuestLadderDNA import QuestChoiceDNA
    found = []

    def walk(n):
        if isinstance(n, QuestDNA):
            return
        kids = n.getContainers()
        ids = [c.getQuestId() for c in kids if isinstance(c, QuestDNA)]
        if isinstance(n, QuestChoiceDNA) and qid in ids:
            found.extend(i for i in ids if i != qid)
        for c in kids:
            walk(c)
    for name in LADDERS:
        walk(_ladderNode(name))
    return found


def _qint(qid):
    from pirates.quest import QuestDB
    dna = QuestDB.QuestDict.get(qid)
    return dna.getQuestInt() if dna is not None else None


STORY = _ladder()
ORDER = dict((q, i) for i, q in enumerate(STORY))
if not START:
    START = 'c2_visit_will_turner' if LADDERS == ['MainStory'] else STORY[0]


def _finals():
    """The last quest of each ladder followed (MainStory: c3.8visitJack): with none held after one, the chain ended."""
    from pirates.quest import QuestLadderDB
    from pirates.quest.QuestDNA import QuestDNA
    out = set()
    for name in LADDERS:
        if name == 'MainStory':
            out.add(FINAL)
            continue
        last = []

        def walk(n):
            if isinstance(n, QuestDNA):
                last[:] = [n.getQuestId()]
            else:
                for c in n.getContainers():
                    walk(c)
        walk(_ladderNode(name))
        out.update(last)
    return out


FINALS = _finals()
# STORY_CHUNK=1 (11-20 whole-story bot, 20 min chunks): a stretch that runs out of time with no STALL and more story
# done than at its start (quests handed in, or task counts up) ends with PASS 'chunk progress'; the next chunk resumes
# from the saved quests. Without it, only STORY_STOP done or the ladder's end is a PASS.
CHUNK = os.environ.get('STORY_CHUNK') == '1'


def chunkScore(H):
    """Story done so far on the followed ladders: (quests handed in, task counts + finished quests held)."""
    hist = set(H.hist())
    done = sum(1 for q in STORY if _qint(q) in hist)
    prog = 0
    for d in H.quests():
        if d['id'] in ORDER:
            prog += 1 if d['complete'] else 0
            if isinstance(d['ts'], list):
                prog += sum(int(s[0] or 0) for s in d['ts'])
    return (done, prog)


def mainQuests(H):
    qs = [q for q in H.la.getQuests() if q.getQuestId() in ORDER]
    qs.sort(key=lambda q: ORDER[q.getQuestId()])
    return qs


# job 29 (NEWP15-NP2 11-19): quests the server already force-completed (skipQuest answered) that the client still
# shows as not done. The game's skipQuest (QuestManagerAI.py:1114-1115) sets the progress but never sends it to the
# client; a normal quest leaves the list at once anyway, but a quest inside a QuestChoice (Bonita's claw, rod, blood)
# stays held until its siblings are done too, so the client kept showing 0 of 3 claws and the bot re-skipped the claw
# 39 times in 420 s. mainQuest passes over these so the bot goes on to the siblings.
def shipHunter(H=None, careful=None):
    """Job 30: the generator that fights a sink / capture / recover-cargo quest at sea: s_shipfight.questHunt (the
    careful lane fight, imported here: s_shipfight -> s_lanes imports this module), or s_shipquest.hunt when
    STORY_SHIP_CAREFUL=0 or the import fails (logged SHIP-HUNTER-FALLBACK with the error)."""
    if careful is None:
        careful = SHIP_CAREFUL
    if careful:
        try:
            import s_shipfight
            return s_shipfight.questHunt
        except Exception:
            import traceback
            if H is not None:
                H.ev('SHIP-HUNTER-FALLBACK', why='s_shipfight did not import', tb=traceback.format_exc()[-400:])
    return s_shipquest.hunt


FORCED = {}       # qid -> time the skip was sent

# PLAYERBOTS round 2 (places 11-22): STORY_PLAYER=1 is the player-bot policy (pbot\skills\quests.py). A player bot
# never sends a magic word: a quest the story run would skip is set ASIDE (the next held quest goes first; it comes back
# after ASIDE_SECS or a level-up), repeats are played, travel is sail / walk / the map's own island teleport.
ASIDE = {}        # qid -> (time set aside, pirate level then, why)
ASIDE_SECS = float(os.environ.get('STORY_ASIDE_SECS', '1200'))


def player():
    return os.environ.get('STORY_PLAYER') == '1'


def _level(H):
    try:
        return H.la.getLevel()
    except Exception:
        return 0


def aside(H, qid):
    """True while qid is set aside (player bot): until ASIDE_SECS have passed or the pirate levelled up."""
    a = ASIDE.get(qid)
    if a is None:
        return False
    lvl = _level(H)
    if time.time() - a[0] > ASIDE_SECS or lvl > a[1]:
        ASIDE.pop(qid, None)
        H.ev('ASIDE-BACK', q=qid, why='level-up' if lvl > a[1] else 'cooldown', secs=round(time.time() - a[0]))
        return False
    return True


def skipQ(H, qid, why=''):
    """The story run's skip: the skipQuest magic word. The player bot sets the quest aside instead. -> True if sent."""
    if player():
        ASIDE[qid] = (time.time(), _level(H), why)
        H.ev('ASIDE', q=qid, why=why, secs=ASIDE_SECS, level=_level(H), held=H.qids())
        return False
    H.mw('skipQuest %s' % qid)
    return True


def mapOk(H, uid):
    """The map would teleport this pirate to island uid (he holds its teleport token): LocalPirate's own check."""
    try:
        return bool(H.la.confirmIslandTeleport('from', islandUid=uid))
    except Exception:
        return False


def mapHop(H, uid, why=''):
    """The story run's areaTeleport magic word. The player bot uses the map's own island teleport
    (teleportMgr.requestTeleportToIsland, as s_island's hop 2) when the map allows it, else nothing. -> True if asked."""
    if not player():
        H.mw('areaTeleport %s' % uid)
        return True
    ok = mapOk(H, uid)
    H.ev('MAP-HOP', to=uid, ok=ok, why=why, area=H.area())
    if ok:
        H.cr.teleportMgr.requestTeleportToIsland(uid)
    return ok


def mainQuest(H):
    """The main-story quest to work on: the earliest held one that is not yet complete (else the earliest). A quest in
    FORCED counts as done (the server has it; only the client does not know): after the open ones, a finished one
    (to hand in, like the rod Bonita waits for) comes before it. MAIN13 (11-21): a finished quest already in the
    quest history (100000596's stale c3r2.5.5visitOrinda) can never be handed in; the server refuses it 'already
    completed'. It comes last, so a real hand-in (the Rumrunner's barrel) is not left for a sail back to Orinda."""
    qs = mainQuests(H)
    if ASIDE:
        qs = [q for q in qs if not aside(H, q.getQuestId())]
    if not qs:
        return None
    for q in qs:
        if not q.isComplete() and q.getQuestId() not in FORCED:
            return q
    try:
        hist = set(H.la.getQuestHistory())
    except Exception:
        hist = set()
    for q in qs:
        if q.isComplete() and _qint(q.getQuestId()) not in hist:
            return q
    for q in qs:
        if q.isComplete():
            return q
    return qs[0]


# pir-bot job 5: event waits in place of fixed sleeps. The loop's old sleep (2-5 s) is kept as the CAP of each wait,
# so the slowest case is the old timing; the wait ends early once the state it was waiting out has moved.
UPTO_MIN = float(os.environ.get('STORY_UPTO_MIN', '0.5'))   # never re-tick sooner than this (no busy loop)


def storySnap(H):
    """What the main loop acts on: the held main quest and its progress, the game state, the quest step, the area."""
    q = mainQuest(H)
    prog = None
    if q is not None:
        try:
            prog = (q.getQuestId(), q.isComplete(), repr(getattr(q, 'taskStates', None))[:300])
        except Exception:
            prog = (q.getQuestId(),)
    try:
        qs = H.la.questStep
        step = (qs.getStepType(), repr(getattr(qs, 'originDoId', None)), repr(getattr(qs, 'stepDoId', None))) if qs else None
    except Exception:
        step = None
    return (prog, H.la.getGameState(), step, H.area() and tuple(H.area()))


def changed(H, minSecs=None):
    """-> a condition for ('upto', ...): true once storySnap differs from now, and at least UPTO_MIN s have passed."""
    s0, t0 = storySnap(H), time.time()
    m = UPTO_MIN if minSecs is None else minSecs

    def fn():
        return time.time() - t0 >= m and storySnap(H) != s0
    return fn


def hasStep(H):
    qs = H.la.questStep
    try:
        return bool(qs and qs.getStepType())
    except Exception:
        return False


def settled(H, t0, minSecs):
    """True once minSecs have passed since t0 and the pirate stands in LandRoam with an area (the island is loaded)."""
    return time.time() - t0 >= minSecs and H.la.getGameState() == 'LandRoam' and H.area() is not None


TUT_PANEL = {'t': 0.0}     # pir-bot job 10b: when the last tutorial panel showed (tutWatch)
TUT_QUIET = 45.0           # no Battle exit this soon after a panel: the pistol / sword lessons need Battle


def tutWatch(H):
    """Wrap NewTutorialPanel.activate once to note when a tutorial panel shows."""
    from pirates.piratesgui import NewTutorialPanel as NTPm
    cls = NTPm.NewTutorialPanel
    if getattr(cls, '_pirBotTutWatch', False):
        return
    old = cls.activate

    def activate(self, *a, **kw):
        TUT_PANEL['t'] = time.time()
        return old(self, *a, **kw)
    cls.activate = activate
    cls._pirBotTutWatch = True


def tutRecent():
    return time.time() - TUT_PANEL['t'] < TUT_QUIET


def track(H, qid):
    la = H.la
    try:
        if la.guiMgr.questPage is None:
            la.guiMgr.initQuestPage()
        page = la.guiMgr.questPage
        page.showQuestDetails(qid)
        if la.activeQuestId != qid:
            page.trackQuest()
        else:
            la.refreshActiveQuestStep(False, True)
    except Exception as e:
        H.ev('track-err', err=str(e))


# job 42 (CH3END): an NPC's node can go empty during a walk (it left the client's view, or was made again under the
# same doId), and getPos on an empty NodePath asserts. A target is re-found then (same doId, else same class and name);
# if it is not back yet, the walk goes on to the last place it was seen. That brings it back into view, and act()
# looks it up again on its next pass.
LAST_PT = {}        # (doId or id) -> its last render point
GONE_SEEN = set()   # keys already logged as TARGET-GONE


class TargetGone(Exception):
    pass


def _key(t):
    d = getattr(t, 'doId', None)
    return ('do', d) if d is not None else ('id', id(t))


def _gone(t):
    """True when t is a node whose NodePath went empty (or cannot be asked)."""
    try:
        return hasattr(t, 'isEmpty') and bool(t.isEmpty())
    except Exception:
        return True


def _nameOf(t):
    for k in ('name', '_name'):
        v = t.__dict__.get(k) if hasattr(t, '__dict__') else None
        if isinstance(v, str) and v:
            return v
    return None


def refind(H, target):
    """The live object for a target whose node went empty: the same doId back in doId2do, else the one object of the
    same class with the same name. None when it is not back."""
    d = getattr(target, 'doId', None)
    o = H.cr.doId2do.get(d) if d is not None else None
    if o is not None and o is not target and not _gone(o):
        return o
    name = _nameOf(target)
    if name:
        cls = type(target).__name__
        same = [o for o in list(H.cr.doId2do.values())
                if o is not target and type(o).__name__ == cls and _nameOf(o) == name and not _gone(o)]
        if len(same) == 1:
            return same[0]
    return None


def live(H, target):
    """target itself while its node is good; else the re-found object; else None (gone, not back yet). Points pass."""
    if not hasattr(target, 'getPos') or not _gone(target):
        return target
    return refind(H, target)


def _render_pt(H, target, ref=None):
    if hasattr(target, 'getPos'):
        k = _key(target)
        if _gone(target):
            o = refind(H, target)
            if k not in GONE_SEEN:
                GONE_SEEN.add(k)
                last = LAST_PT.get(k)
                H.ev('TARGET-GONE', target=type(target).__name__, doId=getattr(target, 'doId', None),
                     name=_nameOf(target), refound=getattr(o, 'doId', None) if o is not None else None,
                     last=[round(v, 1) for v in last] if last is not None else None)
            if o is not None:
                p = o.getPos(H.render)
            elif k in LAST_PT:
                return LAST_PT[k]
            else:
                raise TargetGone('%s %s went empty before it was ever seen' % (type(target).__name__,
                                                                               getattr(target, 'doId', None)))
        else:
            p = target.getPos(H.render)
        try:
            LAST_PT[k] = type(p)(p)
        except Exception:
            LAST_PT[k] = p
        return p
    from panda3d.core import Point3
    p = Point3(*target)
    return H.render.getRelativePoint(ref, p) if ref is not None else p


def hdist(H, target, ref=None):
    p, lp = _render_pt(H, target, ref), H.la.getPos(H.render)
    return ((p[0] - lp[0]) ** 2 + (p[1] - lp[1]) ** 2) ** 0.5


def near(H, obj, d, st, face=True, ref=None, tag=None):
    """True when the pirate is within d ft of obj (an object, or an (x, y, z) point in ref's frame). Otherwise it asks
    run() to walk there (st['go']: held keys, round the buildings, never setPos) and returns False."""
    if hdist(H, obj, ref) <= d:
        return True
    st['go'] = (obj, d, face, ref, tag or ('near ' + type(obj).__name__))
    return False


def nearDoor(H, d, st, tag=None):
    """near() for a door (job 20): True inside DOOR_REACH ft of it in 3D, the way a player's interact prompt shows
    inside the door's 7 ft sphere; otherwise walk on to 3 ft as before."""
    try:
        p, lp = d.getPos(H.render), H.la.getPos(H.render)
        d3 = ((p[0] - lp[0]) ** 2 + (p[1] - lp[1]) ** 2 + (p[2] - lp[2]) ** 2) ** 0.5
    except Exception:
        d3 = None
    if d3 is not None and d3 <= DOOR_REACH:
        if d3 > 3:
            H.ev('DOOR-REACH', door=getattr(d, 'doId', None), dist=round(d3, 2), hd=round(hdist(H, d), 2),
                 dz=round(p[2] - lp[2], 2), reach=DOOR_REACH)
        return True
    return near(H, d, 3, st, tag=tag)


def searchReach(sphere):
    """How near (ft) a container must be to search it: inside its interact sphere, as a player's 'Search' prompt shows,
    at most CONTAINER_REACH; 3 ft when the sphere is not known."""
    try:
        return max(3.0, min(float(sphere), CONTAINER_REACH))
    except (TypeError, ValueError):
        return 3.0


def nearContainer(H, c, st, tag=None):
    """near() for a searchable container: True inside searchReach of its sphereScale (3D), else walk on to 3 ft."""
    reach = searchReach(getattr(c, 'sphereScale', None))
    try:
        p, lp = c.getPos(H.render), H.la.getPos(H.render)
        d3 = ((p[0] - lp[0]) ** 2 + (p[1] - lp[1]) ** 2 + (p[2] - lp[2]) ** 2) ** 0.5
    except Exception:
        d3 = None
    if d3 is not None and d3 <= reach:
        if d3 > 3:
            H.ev('CONTAINER-REACH', container=getattr(c, 'doId', None), dist=round(d3, 2), reach=reach)
        return True
    return near(H, c, 3, st, tag=tag)


def _cave_data(uid):
    import s_cavewalk
    try:
        return bool(s_cavewalk.load(uid))
    except Exception:
        return False


def go(H, target, arrive, face, ref, tag):
    """Generator: walk to target like a player. On an island and further than ROUTE_MIN: the shortest open route round
    the buildings (paths.walk_route, re-planned when a leg sticks), then a straight last bit. -> True when there."""
    H.walk_cancel()
    area = H.area()
    if hasattr(target, 'getPos') and _gone(target):
        o = refind(H, target)
        if o is not None:
            H.ev('TARGET-REFOUND', tag=tag, old=getattr(target, 'doId', None), new=getattr(o, 'doId', None))
            target = o
        elif _key(target) not in LAST_PT:
            H.ev('TARGET-GONE', tag=tag, target=type(target).__name__, doId=getattr(target, 'doId', None),
                 name=_nameOf(target), last=None)
            return False
    if hdist(H, target, ref) > ROUTE_MIN and area and area[0] == 'DistributedGAInterior':
        # job 8 (TUNNEL2): inside a jungle or cave walk the trail from the area's world data waypoints, backing up and
        # taking another way when stuck (s_cavewalk), never a straight line through the jungle wall. None = this area
        # has no waypoints: the old straight walk below
        import s_cavewalk
        p = _render_pt(H, target, ref)
        c = yield from s_cavewalk.walk(H, (p[0], p[1], p[2]), max(arrive, 4.0), tag)
        if c == 'area':
            return 'area'
    if (area and area[0] == 'DistributedGAInterior' and hdist(H, target, ref) > max(arrive, 4.0)
            and os.environ.get('ROOM_WALK', '1') != '0' and not _cave_data(area[1])):
        # PAGES4 (11-20): a shop or tavern room has no waypoints, and its door can be up a step from the floor (the
        # Port Royal tailor's landing at z 5): plan round it on a fine grid instead of the straight walk that stuck
        p = _render_pt(H, target, ref)
        r = yield from paths.walk_room(H, (p[0], p[1], p[2]), arrive, tag + ' room')
        H.ev('route-end', tag=tag + ' room', reached=bool(r), left=round(hdist(H, target, ref), 1))
        if H.area() != area:
            return 'area'
    if hdist(H, target, ref) > ROUTE_MIN and area and area[0] == 'DistributedIsland':
        p = _render_pt(H, target, ref)
        g = yield from paths.walk_route(H, [(p[0], p[1], p[2])], arrive=max(arrive, 6.0), short=max(arrive, 6.0), tag=tag)
        H.ev('route-end', tag=tag, reached=g is not None, left=round(hdist(H, target, ref), 1))
        if g is not None and getattr(paths, 'WALKED', None):
            TRAIL.clear()
            TRAIL.update(area=area[1], pts=[tuple(w) for w in paths.WALKED])
        yield from _ride(H, tag, area)
        if H.area() != area:
            # the walk took him through a tunnel or door (TUT21: into King's Run on the way to the spawn tunnel). The
            # target was a point of the old area, so it means nothing here: stop, and act() plans again from the new
            # area. -> 'area' (truthy: the walk did what it was for)
            H.ev('AREA-CHANGED', tag=tag, frm=area, to=H.area())
            return 'area'
        if g is None and hdist(H, target, ref) > arrive:
            # no route: is the target out on the water (a ship by the dock)? Then walk to the floor nearest it, never
            # straight at it (TUT15/TUT16 walked blind from the hill at Bo Beck's boat and stuck on a fence at
            # (70, 92.4), 84 ft short). -> 'shore' when standing there: as close as walking gets
            _, ground = paths.live(H, 0.0)
            me = H.la.getPos(H.render)
            lgs, r = paths.land_goals((p[0], p[1], p[2]), ground, toward=(me[0], me[1], me[2]))
            if r:
                H.ev('SHORE-GOAL', tag=tag, target=[round(v, 1) for v in p],
                     shore=[[round(v, 1) for v in q] for q in lgs], fromTarget=[round(paths.dist(q, p), 1) for q in lgs])
                g2 = yield from paths.walk_route(H, lgs, arrive=3.0, short=0.0, tag=tag + ' shore')
                H.ev('route-end', tag=tag + ' shore', reached=g2 is not None, left=round(hdist(H, target, ref), 1))
                if hdist(H, target, ref) <= arrive:
                    return True
                return 'shore' if g2 is not None else False
            if not lgs:
                H.ev('NO-FLOOR-NEAR', tag=tag, target=[round(v, 1) for v in p], within=paths.SHORE_R)
                return False
            w = nearWay(hdist(H, target, ref), paths.LAST, (me[0], me[1], me[2]))
            if w is not None:
                # MAIN28 (11-21): Romany on Padres, 990 ft off: the search ran dry 147 ft from her and he stood still
                # for 420 s (4 searches, no step taken). Walk to the point the search got nearest her, then the
                # straight last bit below, which is inside BLIND_MAX from there
                H.ev('NEAR-WAY', tag=tag, target=[round(v, 1) for v in p], to=[round(v, 1) for v in w],
                     left=paths.LAST.get('nearestLeft'))
                g3 = yield from paths.walk_route(H, [w], arrive=6.0, short=0.0, tag=tag + ' near')
                H.ev('route-end', tag=tag + ' near', reached=g3 is not None, left=round(hdist(H, target, ref), 1))
                if H.area() != area:
                    H.ev('AREA-CHANGED', tag=tag, frm=area, to=H.area())
                    return 'area'
            me = H.la.getPos(H.render)
            back = retraceWay(TRAIL, area[1], (me[0], me[1], me[2]), (p[0], p[1], p[2]))
            if back:
                # MAIN39 (11-22): up on the Padres cliff by the stealSchedule chest, every search back to the tavern
                # door ran out 780 ft short (73 s each) for 5 min, though he had just walked up from that door. Walk
                # back down the way he came (each point one he stood on), then plan again from there
                TRAIL.clear()
                H.ev('RETRACE', tag=tag, target=[round(v, 1) for v in p], pts=[[round(v, 1) for v in w] for w in back])
                ok = True
                for i, w in enumerate(back):
                    ok = yield from H.walk_to(w, arrive=6.0 if i == len(back) - 1 else paths.TURN_ARRIVE,
                                              tag='%s retrace %d' % (tag, i + 1))
                    if not ok or H.area() != area:
                        break
                H.ev('route-end', tag=tag + ' retrace', reached=bool(ok), left=round(hdist(H, target, ref), 1))
                if H.area() != area:
                    return 'area'
                if ok:
                    return 'retrace'
            if blindWhy(hdist(H, target, ref), paths.LAST):
                H.ev('NO-ROUTE', tag=tag, target=[round(v, 1) for v in p], left=round(hdist(H, target, ref), 1),
                     why=blindWhy(hdist(H, target, ref), paths.LAST))
                return False
    if hdist(H, target, ref) <= arrive:
        return True
    if face and hasattr(target, 'getPos'):
        t2 = live(H, target)
        if t2 is not None:
            return (yield from _lastLeg(H, t2, area, tag, arrive=arrive, face=True, timeout=40, tag=tag))
    p = _render_pt(H, target, ref)
    return (yield from _lastLeg(H, (p[0], p[1], p[2]), area, tag, arrive=arrive, face=False, timeout=40, tag=tag))


def blindWhy(left, search, most=None):
    """Why a straight walk must not be tried after the route search found nothing (None = try it): the target is
    more than BLIND_MAX ft off and the search really ran (it expanded points), so a straight line crosses whatever
    the search went round: buildings, cliffs, the sea."""
    most = BLIND_MAX if most is None else most
    if left is None or left <= most or not (search or {}).get('expanded'):
        return None
    return 'no route and %d ft off (> %d): no blind straight walk' % (left, most)


def rareShip(r, p0, p1, qid, matchLevels=None, have=None, fair=False):
    """MAIN30, pure: why to skip a branch quest's ship hunt that ended with no progress, else None.
    'rare': it ended 'no-target' (no ship the task counts seen in s_shipfight.NOTARGET_SECS).
    'strong' (MAIN31): every ship the task counts that it saw is more than WEAK_MARGIN levels above the pirate
    (tooWeak, as for land kills): a lv-19 Centurion took a lv-12 War Sloop to 40% hull and sent it home to repair.
    MAIN43: not when the hunt ended with a fair foe picked (`fair`, s_shipfight.LAST['picked']): Biggleton's hunt
    timed out the second it picked a lv-19 Centurion, a ship the lv-14 pirate had sunk twice, and the quest was skipped."""
    import re
    if not (SHIP_RARE_SKIP and p0 == p1 and re.match(r'c[\d.]+r\d', qid or '')):
        return None
    if r == 'no-target':
        return 'rare'
    if matchLevels and have and not fair and tooWeak(0, have, matchLevels):
        return 'strong'
    return None


def nearWay(left, search, me, most=None, gain=NEAR_GAIN):
    """Where to walk when the route search found no way to a target `left` ft off: the point the search got nearest it
    (search['nearest'], reached from where he stands), when the target is inside BLIND_MAX ft of that point and the
    point is at least `gain` ft nearer it than here. None = nothing to gain: blindWhy decides as before."""
    most = BLIND_MAX if most is None else most
    s = search or {}
    q, ql = s.get('nearest'), s.get('nearestLeft')
    if left is None or left <= most or q is None or ql is None or not s.get('expanded'):
        return None
    if ql > most or left - ql < gain or math.hypot(q[0] - me[0], q[1] - me[1]) < gain:
        return None
    return tuple(q)


def retraceWay(trail, area, me, target, near=RETRACE_NEAR, gain=NEAR_GAIN):
    """MAIN39, pure: the way back (the points of the last walk that reached its goal, last first, without the one he
    stands at) when the route search finds no way to `target`: that walk was in this area, ended within `near` ft of
    him, and began at least `gain` ft nearer the target than he is. None = no walk to retrace."""
    pts = (trail or {}).get('pts') or []
    if (trail or {}).get('area') != area or len(pts) < 2:
        return None
    hd = lambda a, b: math.hypot(a[0] - b[0], a[1] - b[1])
    if hd(pts[-1], me) > near or hd(pts[0], target) + gain > hd(me, target):
        return None
    return [tuple(w) for w in reversed(pts[:-1])]


def swimBack(cur, now, secs=None, most=None, qid=None, tps=None):
    """What to do while swimming off a ship: None = wait (just fell in, or nowhere known to swim to), 'swim' = swim
    back to cur['landPt'] (counted in cur['swims']), 'tp' = SWIM_TRIES swims back left him in the water: teleport to
    a port (SWIM_TPS per quest), 'stall' = still in the water after that.
    MAIN35 (11-22): the walk to the Padres dinghy slid him into the sea below a cliff; his last land point was 100 ft up
    it, every swim back hit the cliff, and five story quests were skipped one after another while he swam."""
    secs = SWIM_SECS if secs is None else secs
    most = SWIM_TRIES if most is None else most
    tps = SWIM_TPS if tps is None else tps
    t = cur.setdefault('swimT', now)
    if now - t < secs or cur.get('landPt') is None:
        return None
    if cur.get('swims', 0) >= most:
        if cur.get('swimTpQ') != qid:
            cur['swimTpQ'], cur['swimTps'] = qid, 0
        if cur['swimTps'] < tps:
            cur['swimTps'] += 1
            cur['swims'] = 0
            cur.pop('swimT', None)
            return 'tp'
        return 'stall'
    cur['swims'] = cur.get('swims', 0) + 1
    return 'swim'


def swimPort(here):
    """Pure: the port a stuck swimmer is teleported to: Port Royal, or Tortuga when he is at Port Royal."""
    return TORTUGA if here == PR else PR


def _ride(H, tag, area):
    """Generator, MAIN2 (11-21): the game is taking him through a tunnel (a route that ended at the Tortuga graveyard
    tunnel): press nothing until he is out, so the next walk does not carry him back through. -> True if he rode one."""
    import s_cavewalk
    how = s_cavewalk.in_tunnel(H)
    if not how:
        return False
    H.walk_cancel()
    yield from s_cavewalk.ride_tunnel(H, tag, area, how)
    return True


def _lastLeg(H, pt, area, tag0, **kw):
    """Generator: go()'s straight last walk, letting go the moment a tunnel trip starts (MAIN2 walked on inside the
    Tortuga graveyard toward a Tortuga point and bounced back out, twice). -> walk_to's result, or 'area' when the
    tunnel took him to another area (the target meant the old area: act() plans again)."""
    import s_cavewalk
    r, how = yield from s_cavewalk._leg(H, pt, **kw)
    if how:
        yield from s_cavewalk.ride_tunnel(H, tag0, area, how)
        if H.area() != area:
            H.ev('AREA-CHANGED', tag=tag0, frm=area, to=H.area())
            return 'area'
        return False
    return r


def enemiesOf(H, task):
    """Live enemies the task counts: avatar type isA the task's enemyType and at least the task's level."""
    etype = getattr(task, 'enemyType', None)
    lvl = max(0, getattr(task, 'level', 0) or 0)
    out = []
    lp = H.la.getPos(H.render)
    for o in list(H.cr.doId2do.values()):
        # job 6: client enemies have no getAvatarType() (only the AI side and bosses do); the client keeps the
        # attribute .avatarType. Enemy NPC pirates count; player pirates and townsfolk do not.
        n = type(o).__name__
        if o is H.la or 'PlayerPirate' in n or 'LocalPirate' in n or 'Townfolk' in n:
            continue
        try:
            at = getattr(o, 'avatarType', None)
            if at is None or etype is None or not at.isA(etype):
                continue
            if (getattr(o, 'hp', 0) or 0) <= 0:
                continue
            if lvl and (o.getLevel() or 0) < lvl:
                continue
            out.append(((o.getPos(H.render) - lp).length(), o))
        except Exception:
            continue
    out.sort(key=lambda t: t[0])
    return [o for d, o in out]


def fight(H, foe, st):
    """One fight beat: a far foe is walked to round the buildings first; close up, H.engage walks to reach, faces it
    and swings (keys only)."""
    H.drawSword()
    if hdist(H, foe) > 40:
        near(H, foe, 12, st, face=False, tag='to-foe')
        return '%s far' % foe.doId
    return '%s %s' % (foe.doId, H.engage(foe.doId))


def stepIsland(H, sobj):
    """If the step object is (on) another island, that island's uid."""
    if sobj is None:
        return None
    if type(sobj).__name__ == 'DistributedIsland':
        uid = getattr(sobj, 'uniqueId', None)
        return uid if uid and uid != sailing.hereUid(H) else None
    return None


# ---- at sea like a player (STORY23): sailing.sail_to (brain's) runs inside sailGuarded, which retargets when the quest
# step moves (the server turned c2.11 in at the dinghy and gave c3visitJack, the bot kept sailing to Devil's Anvil),
# and lends sail_to a route that keeps clear of enemy ships above our level, fires back once hit, runs when the hull
# is low and turns for the nearest port with a shipwright when it is lower still (launch() repairs there).
AVOID_R = 3500.0     # ft: an enemy ship above our level this close and near our line is passed wide
CLEAR_R = 2200.0     # ft: how wide we pass it
STICK = 25.0         # s: keep the side picked for a ship this long (aim points that flip sides sail circles, STORY12)
FLEE_HP = 0.5        # hull fraction: below this, run from any enemy ship inside FLEE_R
FLEE_R = 2600.0
PORT_HP = 0.3        # hull fraction: below this, turn for the nearest port with a shipwright
# MAIN23 (11-21): a level-11 War Sloop traded broadsides with a Navy Dreadnought lv39 and an EITC Warlord lv34 at
# hull 0.75; FLEE_HP came at 0.47 and the ship sank 12 s later (with Player1 and Player2 aboard as crew). A ship DANGER_LV
# or more levels above ours inside FLEE_R is run from once we have been hit (hull below HIT_HP). MAIN25: run from at
# any hull, the flee (inside 2600 ft) and the wide pass (aims back past it) swapped ~60 times at hull 1.0 off Padres
# and the ship never got there; unhit, the wide pass alone keeps us clear.
DANGER_LV = 10
HIT_HP = 0.98        # hull fraction: below this we have been hit
# MAIN32 (11-22): hull 0.35 after a Bloodhound's shots, then Navy and EITC warships trailed us at ~2500 ft for 500 s
# without one more hit; every touch of FLEE_R turned us back, ~40 flee/avoid swaps and the leg to Padres never closed.
# A ship that has not hit us for HIT_QUIET seconds is passed (wide when above our level), not run from.
HIT_QUIET = 30.0
_PORTS = None


def runFrom(hull, lvl, near, quiet=None):
    """Pure. near = levels of the enemy ships inside FLEE_R, quiet = seconds since our hull last dropped (None: not
    tracked). -> True when the ship should run: hull below FLEE_HP with any of them near, or one DANGER_LV or more
    levels above ours near once we have been hit; never when nothing has hit us for HIT_QUIET seconds."""
    if not near or hull is None:
        return False
    if quiet is not None and quiet > HIT_QUIET:
        return False
    if hull < FLEE_HP:
        return True
    return hull < HIT_HP and max(near) >= (lvl or 0) + DANGER_LV


def stepIslandUid(H):
    """The island uid the quest step names (QuestStep.getIsland), when it is a sailable island."""
    qs = H.la.questStep
    try:
        u = qs.getIsland() if qs else ''
    except Exception:
        u = ''
    return u if u and u in sailing.islands() else None


def landPort(ttype, p, tbl=None, ports=None):
    """Pure. DOLL9 (11-21): the straw ship quest ended at sea, and the pitch barrels step names no island, so the bot
    sat 390 s in aboard-wait. A land task (GRIND_TYPES) with no step island is played on the nearest repair port
    (s_shipfight.PORTS) to p = our ship's (x, y). -> that island's uid, or None."""
    if ttype not in GRIND_TYPES:
        return None
    import s_shipfight
    tbl = sailing.islands() if tbl is None else tbl
    ports = s_shipfight.PORTS if ports is None else ports
    pl = [(u, tbl[u][0], tbl[u][1], tbl[u][2]) for u in ports if u in tbl]
    if not pl:
        return None
    if p is None:
        return pl[0][0]
    return s_shipfight.nearestPort(p, pl)[0]


def shipPos(H, ship):
    try:
        q = ship.getPos(H.render)
        return (q[0], q[1])
    except Exception:
        return None


def myShip(H):
    try:
        ships = list(H.la.getInventory().getShipDoIdList())
    except Exception:
        return None
    return H.cr.doId2do.get(ships[0]) if ships else None


def hull(ship):
    hp = s_shipquest.hpOf(ship)
    try:
        mx = ship.getMaxHp()
    except Exception:
        mx = getattr(ship, 'maxHp', None)
    return hp / float(mx) if hp is not None and mx else None


def ports():
    """uid -> (x, y) of every named island with a dinghy and a shipwright (land, repair, launch again)."""
    global _PORTS
    if _PORTS is None:
        _PORTS = dict((u, (x, y)) for u, (n, x, y, f) in sailing.islands().items()
                      if n and sailing.dinghySpots(u) and sailing.shipwrightSpots(u))
    return _PORTS


def nearestPort(p):
    pp = ports()
    if not pp:
        return None
    return min(pp, key=lambda u: (pp[u][0] - p[0]) ** 2 + (pp[u][1] - p[1]) ** 2)


class SeaSense:
    """Stands in for sailing.route while one sail runs: enemy ships move the aim point (the island routing stays the
    brain's: every aim point still goes through the real route), and broadsides answer a ship that hits us."""

    def __init__(self, H, why):
        self.H, self.why = H, why
        self.orig = sailing.route
        self.side = {}          # foe doId -> (side +1 left / -1 right of our line, time picked)
        self.mode = None
        self.fireT = {}
        self.port = False
        self.hull = None
        self.hitT = None        # when our hull last dropped this sail (MAIN32)
        self.bkeys = s_shipquest.broadsideKeys()
        try:
            self.lvl = H.la.getLevel() or 0
        except Exception:
            self.lvl = 0

    def log(self, mode, **kw):
        if mode != self.mode:
            self.mode = mode
            self.H.ev('SAIL-' + mode.upper(), why=self.why, hull=None if self.hull is None else round(self.hull, 2),
                      lvl=self.lvl, **kw)

    def fire(self, ship, foes):
        """Broadside any enemy ship lined up inside FIRE_R once we have been hit (the game's own keys)."""
        H = self.H
        for d, o in foes:
            if d >= s_shipquest.FIRE_R:
                break
            try:
                brg = s_shipquest.bearing(H, ship, o.getPos(H.render))
                sk = s_shipquest.linedUp(H, ship, o, brg)
            except Exception:
                continue
            if sk in self.bkeys and not s_shipquest.recharging(H, sk) and time.time() - self.fireT.get(sk, 0) > 3:
                self.fireT[sk] = time.time()
                k = self.bkeys[sk]
                messenger.send(k)
                messenger.send(k + '-up')
                H.ev('SAIL-BROADSIDE', foe=o.doId, foeName=getattr(o, 'name', ''), lvl=s_shipquest.levelOf(o),
                     side=s_shipquest.sideName(sk), dist=round(d), foeHp=s_shipquest.hpOf(o), hull=round(self.hull, 2))
                return

    def route(self, p, goal, obst):
        from panda3d.core import Point3, Vec3
        H = self.H
        ship = myShip(H)
        if ship is None:
            return self.orig(p, goal, obst)
        try:
            foes = s_shipquest.npcShips(H, ship)
        except Exception:
            foes = []
        h0, self.hull = self.hull, hull(ship)
        if self.hull is not None and h0 is not None and self.hull < h0 - 0.001:
            self.hitT = time.time()
        if self.hull is not None and self.hull < HIT_HP and foes:
            self.fire(ship, foes)
        if self.hull is not None and self.hull < PORT_HP:
            self.port = True
        P = Vec3(p[0], p[1], 0)
        u = Vec3(goal[0] - p[0], goal[1] - p[1], 0)
        L = u.length()
        if L < 1:
            return self.orig(p, goal, obst)
        u = u / L
        near = [(d, o) for d, o in foes if d < FLEE_R]
        quiet = time.time() - self.hitT if self.hitT is not None else HIT_QUIET + 1
        if runFrom(self.hull, self.lvl, [s_shipquest.levelOf(o) for d, o in near], quiet):
            # run: away from the ships on us, drifting toward the goal when that is not back into them
            c = Vec3(0, 0, 0)
            for d, o in near:
                op = o.getPos(H.render)
                c += Vec3(op[0], op[1], 0)
            c = c / len(near)
            away = P - c
            if away.length() < 1:
                away = Vec3(-u[1], u[0], 0)
            away.normalize()
            dv = away + u * 0.35
            dv.normalize()
            aim = Point3(p[0] + dv[0] * 3000, p[1] + dv[1] * 3000, 0)
            self.log('flee', foes=[(round(d), getattr(o, 'name', ''), s_shipquest.levelOf(o)) for d, o in near[:4]])
            tgt, m = self.orig(p, aim, obst)
            return tgt, 'flee-' + m
        # pass wide of the nearest enemy ship above our level that is on or near our line ahead
        n = Vec3(-u[1], u[0], 0)        # left of our line
        best = None
        for d, o in foes:
            if d >= AVOID_R or s_shipquest.levelOf(o) <= self.lvl:
                continue
            op = o.getPos(H.render)
            r = Vec3(op[0] - p[0], op[1] - p[1], 0)
            t, lat = r.dot(u), r.dot(n)
            if t < -300 or t > L or abs(lat) >= CLEAR_R:
                continue
            if best is None or t < best[0]:
                best = (t, lat, d, o, op)
        if best is None:
            self.log('clear')
            return self.orig(p, goal, obst)
        t, lat, d, o, op = best
        sd = self.side.get(o.doId)
        if sd is None or time.time() - sd[1] > STICK:
            sd = (-1.0 if lat > 0 else 1.0, time.time())       # the side away from it
            self.side[o.doId] = sd
        aim = Point3(op[0] + n[0] * sd[0] * (CLEAR_R + 800) + u[0] * 600,
                     op[1] + n[1] * sd[0] * (CLEAR_R + 800) + u[1] * 600, 0)
        self.log('avoid', foe=o.doId, foeName=getattr(o, 'name', ''), foeLvl=s_shipquest.levelOf(o), dist=round(d),
                 side='left' if sd[0] > 0 else 'right')
        tgt, m = self.orig(p, aim, obst)
        return tgt, 'avoid-' + m


def sailGuarded(H, uid, why):
    """Generator: sailing.sail_to(H, uid) with SeaSense steering, re-reading the quest each tick at the wheel.
    -> 'sailed' / 'failed' / ('retarget', island or None) / ('port', uid). Keys are let go when it stops early."""
    q0 = mainQuest(H)
    qid0 = q0.getQuestId() if q0 else None
    isl0 = stepIslandUid(H)
    sense = SeaSense(H, why)
    gen = sailing.sail_to(H, uid, why=why)
    sailing.route = sense.route
    try:
        while True:
            r = None
            if H.la.getGameState() == 'ShipPilot':
                q = mainQuest(H)
                qid = q.getQuestId() if q else None
                isl = stepIslandUid(H)
                if isl and isl != uid and isl != isl0:
                    r = ('retarget', isl)
                elif qid != qid0 and not isl:
                    r = ('retarget', None)
                elif sense.port:
                    shp = myShip(H)
                    pt = nearestPort(shp.getPos(H.render)) if shp is not None else None
                    if pt and pt != uid:
                        r = ('port', pt)
                if r is not None:
                    gen.close()
                    for k in ('a', 'd'):
                        messenger.send(k + '-up')
                    H.ev('SAIL-' + r[0].upper(), why=why, frm=uid, to=r[1], q0=qid0, q=qid, step0=isl0, step=isl,
                         hull=None if sense.hull is None else round(sense.hull, 2), pos=H.P(H.la))
                    H.sailResult = False
                    return r
            try:
                y = next(gen)
            except StopIteration:
                return 'sailed' if H.sailResult else 'failed'
            yield y
    finally:
        sailing.route = sense.orig


def watchDisconnect(H):
    """A lost connection ends the run at once: a DISCONNECT event (run_walk's strike line takes the last event as its
    reason) and a non-zero exit, never an idle game until PROOF_SECS (STORY23 sat 5 min after 'Lost connection')."""
    import builtins
    if getattr(H, '_dcWatch', False):
        return
    H._dcWatch = True

    def check(task):
        cr = H.cr
        try:
            st = cr.loginFSM.getCurrentState().getName()
        except Exception:
            return task.again
        if st != 'noConnection':
            return task.again
        info = {}
        for k, f in (('area', H.area), ('gs', H.la.getGameState), ('q', lambda: getattr(mainQuest(H), 'getQuestId', lambda: None)())):
            try:
                info[k] = f()
            except Exception as e:
                info[k] = 'err %s' % e
        H.ev('DISCONNECT', state=st, booted=getattr(cr, 'bootedIndex', None), text=str(getattr(cr, 'bootedText', '') or '')[:200],
             **info)
        os._exit(3)
    builtins.taskMgr.doMethodLater(0.5, check, 'story-disconnect-watch')


DIG_SPOTS = None     # area uid -> area-local dig spots, from dig_spots.json (made from the client's world data)


def digSpots(H):
    """(the area object, its dig spots in that area's frame) for the area the pirate stands in."""
    global DIG_SPOTS
    if DIG_SPOTS is None:
        import json
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])), 'dig_spots.json')) as f:
                DIG_SPOTS = json.load(f)
        except Exception:
            DIG_SPOTS = {}
    area = H.area()
    uid = area[1] if area else None
    org = next((o for o in list(H.cr.doId2do.values()) if getattr(o, 'uniqueId', None) == uid and hasattr(o, 'getPos')), None)
    return org, [tuple(p) for p in DIG_SPOTS.get(uid, [])]


QS = None     # quest_spots.json (gen_questspots.py): areas, quest objects (area-local) and the doors/tunnels joining areas


def questSpots():
    global QS
    if QS is None:
        import json
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            d = os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT']))
        except Exception:
            d = here
        p = os.path.join(d, 'quest_spots.json')
        if not os.path.exists(p):
            p = os.path.join(here, 'quest_spots.json')   # pbots (11-22): a step script in a subfolder (pbot\) uses the harness map
        try:                                             # (run 6: the empty fallback gave the captain 0 spawn nodes on Port Royal)
            with open(p) as f:
                QS = json.load(f)
        except Exception:
            QS = {'areas': {}, 'objs': {}, 'exits': {}}
    return QS


def hereArea(H):
    a = H.area()
    return a[1] if a else None


def areaObj(H, uid):
    """The live area object with that uniqueId (its frame is the one quest_spots.json positions are in)."""
    return next((o for o in list(H.cr.doId2do.values()) if getattr(o, 'uniqueId', None) == uid and hasattr(o, 'getPos')), None)


def hops(frm, to):
    """Shortest list of exits [to, x, y, z, kind, via] from area frm to area to on one island (doors and tunnels;
    islands are sailed between), [] when frm is to, None when there is no walk."""
    if frm == to:
        return []
    ex = questSpots()['exits']
    prev, todo = {frm: None}, [frm]
    while todo:
        a = todo.pop(0)
        for e in ex.get(a, []):
            if e[0] in prev:
                continue
            prev[e[0]] = (a, e)
            if e[0] == to:
                out, n = [], to
                while prev[n]:
                    out.append(prev[n][1])
                    n = prev[n][0]
                return out[::-1]
            todo.append(e[0])
    return None


def nearestOf(H, uids):
    """Of quest_spots objs uids: the one in this area nearest the pirate, else the one fewest walks (doors/tunnels)
    away on this island, else one on another island (to sail to)."""
    objs, areas, here = questSpots()['objs'], questSpots()['areas'], hereArea(H)
    org = areaObj(H, here)
    hisl = (areas.get(here) or [None])[0]

    def cost(u):
        a = objs[u][0]
        if a == here and org is not None:
            return (0, hdist(H, tuple(objs[u][1:4]), org))
        h = hops(here, a)
        if h is not None:
            return (1 + len(h), 0)
        return (99 if (areas.get(a) or [None])[0] != hisl else 50, 0)
    us = [u for u in uids if u in objs]
    return min(us, key=cost) if us else None


def useDoor(H, d, st, tag):
    if st.get('door') == d.doId and time.time() - st.get('doorT', 0) < 20:
        return '%s-door-wait %s' % (tag, d.doId)
    if not nearDoor(H, d, st, tag=tag + '-door'):
        return '%s-walk-to-door %s' % (tag, d.doId)
    st['door'] = d.doId
    st['doorT'] = time.time()
    H.ev('GOTO-DOOR', door=d.doId, cls=type(d).__name__, uid=getattr(d, 'interiorUid', None) or getattr(d, 'buildingUid', None), here=H.area())
    d.requestInteraction(H.la.doId)
    return '%s-door %s' % (tag, d.doId)


def useTunnel(H, tun, st, tag='tunnel'):
    """Walk into a tunnel mouth like a player: onto the tunnel floor on this side, whose trigger takes the pirate
    through. Its state is kept per (tunnel, side), so the same tunnel can be used both ways in one quest. Standing on
    that floor 10 s with no trip started: the game's own quick load of the other side (the call its loading screen
    makes), logged TUNNEL-QUICKLOAD. Still on this side a minute later: TUNNEL-STUCK, no teleport."""
    from pirates.piratesbase import PiratesGlobals
    areas = list(tun.areaUid)
    here = hereArea(H)
    if st.get('tun') != (tun.doId, here):
        st['tun'] = (tun.doId, here)
        for k in ('tunT', 'tunQ', 'tunS'):
            st.pop(k, None)
    if H.la.testTeleportFlag(PiratesGlobals.TFInTunnel) or H.la.getGameState() in ('EnterTunnel', 'LeaveTunnel'):
        return '%s-in %s' % (tag, tun.doId)
    # floor i of a tunnel is at its area i end (__handleOnFloor(i) looks for area i's entrance in the loaded area)
    side = areas.index(here) if here in areas else 0
    names = getattr(tun, 'floorNames', None) or []
    fl = tun.find('**/' + names[side]) if len(names) > side else None
    if not st.get('tunT'):
        if fl is not None and not fl.isEmpty() and not fl.getBounds().isEmpty():
            c = fl.getBounds().getApproxCenter()
            onFloor = near(H, (c[0], c[1], c[2]), 2, st, face=False, ref=fl, tag=tag)
        else:
            onFloor = near(H, tun, 3, st, face=False, tag=tag)
        if not onFloor and st.get('goFails', 0) < 3:
            return '%s-walk %s' % (tag, tun.doId)
        st['tunT'] = time.time()
        return '%s %s' % (tag, tun.doId)
    waited = time.time() - st['tunT']
    if waited > 10 and not st.get('tunQ'):
        st['tunQ'] = 1
        H.ev('TUNNEL-QUICKLOAD', tunnel=tun.doId, side=side, here=here, floor=bool(fl is not None and not fl.isEmpty()))
        tun._DistributedGATunnel__handleOnFloor(side, None)
        return '%s-quickload %s' % (tag, tun.doId)
    if waited > 70 and not st.get('tunS'):
        st['tunS'] = 1
        H.ev('TUNNEL-STUCK', tunnel=tun.doId, here=here, la=H.P(H.la))
    if st.get('tunS'):
        return '%s-stuck %s' % (tag, tun.doId)
    return '%s-wait' % tag


def hop(H, st, here, e, tag):
    """Take one door / tunnel from here toward e[0] (an exit from quest_spots.json)."""
    to, x, y, z, kind, via = e
    org = areaObj(H, here)
    dos = list(H.cr.doId2do.values())
    if kind == 'tunnel':
        tun = [o for o in dos if type(o).__name__ == 'DistributedGATunnel'
               and here in list(getattr(o, 'areaUid', None) or ()) and to in list(getattr(o, 'areaUid', None) or ())]
        if tun:
            return useTunnel(H, min(tun, key=lambda o: hdist(H, o)), st, tag + '-tunnel')
    elif x is None:
        # out of an interior: its door back to the building outside (any interior door when that one is not known)
        doors = [o for o in dos if type(o).__name__ == 'DistributedInteriorDoor']
        doors.sort(key=lambda o: (getattr(o, 'buildingUid', None) != via, hdist(H, o)))
        if doors:
            return useDoor(H, doors[0], st, tag)
        return '%s-no-interior-door' % tag
    else:
        doors = [o for o in dos if type(o).__name__ == 'DistributedBuildingDoor']
        doors = [o for o in doors if getattr(o, 'interiorUid', None) == to] or \
                [o for o in doors if org is not None and (o.getPos(H.render) - _render_pt(H, (x, y, z), org)).length() < 10]
        if doors:
            return useDoor(H, min(doors, key=lambda o: hdist(H, o)), st, tag)
    if org is None or x is None:
        return '%s-%s-not-in-view %s' % (tag, kind, via)
    if near(H, (x, y, z), 4, st, face=False, ref=org, tag=tag + '-' + kind):
        return '%s-%s-not-in-view %s' % (tag, kind, via)     # at the mouth / door spot and still nothing here
    return '%s-walk-to-%s %s' % (tag, kind, via)


def goto(H, st, to, pos=None, arrive=3.0, tag='goto'):
    """Go to area `to` (a quest_spots.json area uid) like a player: walk through its doors and tunnels, sail when it is
    on another island (out of a building / cave to the island first). pos (area-local) = walk to that spot there too.
    -> True when there; else what it is doing (a walk left in st['go']), or ('sail', island uid) for run()."""
    areas = questSpots()['areas']
    here = hereArea(H)
    if here == to:
        if pos is None:
            return True
        org = areaObj(H, to)
        if org is None:
            return '%s-no-area-object %s' % (tag, to)
        return True if near(H, tuple(pos), arrive, st, face=False, ref=org, tag=tag) else '%s-walk %s' % (tag, str(pos))
    tisl = (areas.get(to) or [None])[0]
    if tisl is None:
        return '%s-unknown-area %s' % (tag, to)
    if here not in areas:
        return ('sail', tisl)        # at sea / aboard / an area the map does not have: the old way, sail there
    hisl, hkind = areas[here][0], areas[here][1]
    if hisl != tisl:
        if hkind != 'island':
            r = goto(H, st, hisl, None, arrive, tag)      # out to the open island first, then sail
            return '%s-out %s' % (tag, hisl) if r is True else r
        return ('sail', tisl)
    path = hops(here, to)
    if not path:
        return '%s-no-route %s->%s' % (tag, here, to)
    return hop(H, st, here, path[0], tag)


def container(H, q, task, st):
    """Search containers like a player: each one once (the server allows one search per container per task). A named
    container (task.containerId: one uid, or a PropIds group) is walked to through doors / tunnels / sailed to when
    it is not in view; any container: the nearest unsearched one in view."""
    from pirates.quest.QuestConstants import PropIds, getPropList
    la = H.la
    cid = getattr(task, 'containerId', None)
    want = None if cid in (None, PropIds.ANY_PROP) else set(getPropList(cid) or [cid])
    searched = st.setdefault('searched', [])
    cons = [o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedSearchableContainer'
            and (want is None or getattr(o, 'uniqueId', None) in want)
            and (getattr(o, 'uniqueId', None) or o.doId) not in searched]
    cons.sort(key=lambda c: hdist(H, c))
    if cons and hdist(H, cons[0]) < 300:
        c = cons[0]
        if time.time() - st.get('conT', 0) < 15:
            return 'search-wait'
        if not nearContainer(H, c, st, tag='container'):
            return 'walk-to-container %s' % c.doId
        st['conT'] = time.time()
        searched.append(getattr(c, 'uniqueId', None) or c.doId)
        H.ev('SEARCH', container=c.doId, uid=getattr(c, 'uniqueId', None), want=cid, n=len(searched),
             ts=[(getattr(s, 'progress', None), getattr(s, 'attempts', None)) for s in q.getTaskStates()])
        c.requestInteraction(la.doId)
        return 'search %s %s' % (c.doId, getattr(c, 'uniqueId', None))
    left = [u for u in (want or ()) if u not in searched and u not in st.get('unreach', ())]
    if want is None or not left:
        if searched and time.time() - st.get('conT', 0) > 30:
            # every one searched once and the item not found yet: the server may give it on a later try
            H.ev('SEARCH-ROUND-DONE', want=cid, searched=list(searched))
            del searched[:]
        return 'no-container-in-view(want=%s searched=%d)' % (cid, len(searched))
    u = nearestOf(H, left)
    if u is None:
        return 'container-not-in-map %s' % cid
    if st.get('conGo') == u and st.get('goFails', 0) >= 2:
        # DOLL10: no way there (a barrel up on the Port Royal hill): leave it for this quest step (a search round
        # does not bring it back), the next nearest one of the group
        st.setdefault('unreach', []).append(u)
        H.ev('CONTAINER-UNREACHABLE', uid=u, fails=st['goFails'], left=[x for x in left if x != u])
        st['goFails'] = 0
        st.pop('conGo', None)
        return 'container-unreachable %s' % u
    st['conGo'] = u
    o = questSpots()['objs'][u]
    r = goto(H, st, o[0], o[1:4], 6.0, 'to-container')
    if r is True:
        # standing on its spot and it is not on this client: it never spawned
        searched.append(u)
        H.ev('CONTAINER-NOT-HERE', uid=u, area=o[0])
        return 'container-not-here %s' % u
    return r


def dig(H, q, task, st):
    """Buried treasure. Any spot: digAny. A named treasure (task.treasureId: a TreasureIds group): walk / sail to the
    group's spots in turn and dig there. Two digs at a spot with no change in the task's (progress, attempts) means
    the server said no (DIG-DENIED), and the next spot is tried."""
    from pirates.quest.QuestConstants import TreasureIds, getTreasureList
    tid = getattr(task, 'treasureId', None)
    if tid in (None, TreasureIds.ANY_TREASURE):
        return digAny(H, st)
    objs = questSpots()['objs']
    spots = [u for u in (getTreasureList(tid) or [tid]) if u in objs]
    tried = st.setdefault('digTried', [])
    left = [u for u in spots if u not in tried]
    if not left:
        return 'dig-all-tried(%s spots=%d)' % (tid, len(spots))
    u = nearestOf(H, left)
    a, x, y, z = objs[u][:4]
    here = hereArea(H)
    org = areaObj(H, a) if a == here else None
    live = None
    if org is not None:
        from panda3d.core import Point3
        bp = H.render.getRelativePoint(org, Point3(x, y, z))
        ts = [o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedBuriedTreasure']
        live = next((o for o in ts if getattr(o, 'uniqueId', None) == u), None) or \
            next((o for o in ts if (o.getPos(H.render) - bp).length() < 8), None)
    if live is None:
        r = goto(H, st, a, (x, y, z), 6.0, 'to-dig')
        if r is True:
            tried.append(u)
            H.ev('DIG-SPOT-NO-TREASURE', spot=u, area=a)
            return 'dig-spot-no-treasure %s' % u
        return r
    prog = [(getattr(s, 'progress', None), getattr(s, 'attempts', None)) for s in q.getTaskStates()]
    if st.get('digAt') != u:
        st.update(digAt=u, digN=0, digProg=prog)
    elif prog != st.get('digProg'):
        st.update(digN=0, digProg=prog)          # the last dig counted: keep digging here (it resets in a few s)
    if st['digN'] >= 2 and time.time() - st.get('digT', 0) > 12:
        tried.append(u)
        H.ev('DIG-DENIED', spot=u, treasure=live.doId, uid=getattr(live, 'uniqueId', None), want=tid, ts=prog,
             why='2 digs, no credit: the server matches the treasure by uniqueId (see notes: createObjectSpawnNode)')
        return 'dig-denied %s' % u
    if time.time() - st.get('digT', 0) < 12:
        return 'dig-wait %s' % live.doId
    if not near(H, live, 5, st, face=False, tag='dig'):
        return 'walk-to-dig %s' % live.doId
    st['digT'] = time.time()
    st['digN'] += 1
    H.ev('DIG', spot=live.doId, uid=u, n=st['digN'], depth=getattr(live, 'currentDepth', None), ts=prog, la=H.P(H.la))
    live.requestInteraction(H.la.doId)
    return 'dig %s %s' % (live.doId, u)


ENEMY_SPAWNS = {}    # (enemy type name, task level) -> spawn node uids that can make it (quest_spots.json)
SPAWN_TYPES = {}     # spawnable name -> every avatar type a spawn node with it can make


def spawnTypes(name):
    """pir-bot job 11: every avatar type a spawnable can make. NPC_SPAWNABLES entries are pickers that roll
    random.randint over a range (EvilNavy = pickNavy(0, 1): a Cadet or a Guard), and the server rolls one per spawn
    (DistributedEnemySpawnerAI.getAvatarType). enemySpawns used to call each picker once, so every run dropped a random
    part of the spawns from the route table (a Cadet hunt saw half the EvilNavy nodes). Here each value of the picker's
    range is tried in turn, on a stand-in for AvatarTypes' own `random` (put back at once)."""
    if name not in SPAWN_TYPES:
        from pirates.pirate import AvatarTypes as AT
        real, out = AT.random, []

        class Roll:
            def __init__(self, v=None):
                self.v, self.rng = v, []

            def randint(self, a, b):
                self.rng.append((a, b))
                return a if self.v is None else max(a, min(b, self.v))

            def __getattr__(self, k):
                return getattr(real, k)
        try:
            for c in AT.NPC_SPAWNABLES.get(name, ()):
                r = Roll()
                AT.random = r
                try:
                    first = c()
                except Exception:
                    continue
                vals = [first]
                if r.rng:
                    a, b = r.rng[0]
                    for v in range(a, b + 1):
                        AT.random = Roll(v)
                        try:
                            vals.append(c())
                        except Exception:
                            continue
                out.extend(t for t in vals if t not in out)
        finally:
            AT.random = real
        SPAWN_TYPES[name] = out
    return SPAWN_TYPES[name]


def typeMaxLevel(at):
    """The highest level the server gives this avatar type (EnemyGlobals.getRandomEnemyLevel picks in its range)."""
    from pirates.battle import EnemyGlobals
    try:
        st = EnemyGlobals.getBaseStats(at.getNonBossType())
        return st[EnemyGlobals.MAX_LEVEL] if st else 1
    except Exception:
        return 99


def enemySpawns(task):
    """Spawn nodes that can make an enemy the task counts: its type, and (job 11) at least its level, as enemiesOf()
    counts them. A Navy lvl 9 hunt no longer walks round the Cadet / Guard posts. No node reaches the level: every
    node of the type (better a walk than none)."""
    et = task.enemyType
    lvl = max(0, getattr(task, 'level', 0) or 0)
    k = (str(et), lvl)
    if k not in ENEMY_SPAWNS:
        ofType, ofLevel = [], []
        for u, o in questSpots()['objs'].items():
            if o[4] not in ('Spawn Node', 'Dormant NPC Spawn Node'):
                continue
            try:
                ts = [t for t in spawnTypes(o[5]) if t.isA(et)]
            except Exception:
                continue
            if ts:
                ofType.append(u)
                if any(typeMaxLevel(t) >= lvl for t in ts):
                    ofLevel.append(u)
        ENEMY_SPAWNS[k] = ofLevel or ofType
    return ENEMY_SPAWNS[k]


def taskAreas(task):
    """The areas a task counts in (task.location: a LocationIds group or one uid), None = anywhere."""
    loc = getattr(task, 'location', None)
    if loc in (None, '', 'AnyLocation'):
        return None
    from pirates.quest.QuestConstants import getLocationList
    return set(getLocationList(loc) or [loc])


def huntAreas(task, at=None):
    """Where to hunt a kill task that names no place (HUNT), None = it names one, or its enemy is not in HUNT."""
    if os.environ.get('STORY_HUNT', '1') == '0' or taskAreas(task) is not None:
        return None
    et = getattr(task, 'enemyType', None)
    if et is None:
        return None
    if at is None:
        from pirates.pirate import AvatarTypes as at
    return next((a for n, a in HUNT.items() if getattr(at, n, None) == et), None)


def toEnemies(H, task, st, ok):
    """No enemy of the task's type in view: walk to where they spawn, inside the task's location when it has one
    (kills elsewhere do not count, and the server's beam ignores the location)."""
    objs = questSpots()['objs']
    sp = [u for u in enemySpawns(task) if ok is None or objs[u][0] in ok]
    here = hereArea(H)
    if not sp:
        if ok is None or here in ok:
            return None
        a = sorted(ok)[0]
        r = goto(H, st, a, None, 3.0, 'to-location')
        return 'in-location %s' % a if r is True else r
    seen = st.setdefault('spawnSeen', [])
    left = [u for u in sp if u not in seen] or (seen.clear() or sp)
    u = nearestOf(H, left)
    o = objs[u]
    r = goto(H, st, o[0], o[1:4], 10.0, 'to-spawn')
    if r is True:
        seen.append(u)
        return 'at-spawn %s' % u
    return r


def digAny(H, st):
    """Buried treasure (RecoverTreasureItem, any spot counts): walk to the nearest dig spot in view and press to dig
    (the server digs it down, then the chest comes up). None in view: walk to the area's spots one by one (spots out
    of interest are not on this client) and mark each one empty once there."""
    la = H.la
    spots = [o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedBuriedTreasure']
    spots.sort(key=lambda s: hdist(H, s))
    if spots and hdist(H, spots[0]) < 300:
        s = spots[0]
        if time.time() - st.get('digT', 0) < 12:
            return 'dig-wait %s' % s.doId
        if not near(H, s, 5, st, face=False, tag='dig'):
            return 'walk-to-dig %s' % s.doId
        st['digT'] = time.time()
        st['digs'] = st.get('digs', 0) + 1
        H.ev('DIG', spot=s.doId, n=st['digs'], depth=getattr(s, 'currentDepth', None), la=H.P(la))
        s.requestInteraction(la.doId)
        return 'dig %s' % s.doId
    org, pts = digSpots(H)
    tried = st.setdefault('digTried', [])
    left = [p for p in pts if p not in tried]
    if org is None or not left:
        return 'dig-no-spot(area=%s spots=%d tried=%d)' % (H.area(), len(pts), len(tried))
    p = min(left, key=lambda p: hdist(H, p, org))
    if near(H, p, 8, st, face=False, ref=org, tag='dig-spot') or st.get('goFails', 0) >= 2:
        tried.append(p)          # there (or could not walk there) and no dig object came into view: the next spot
        st.pop('go', None)
        st['goFails'] = 0
        H.ev('DIG-SPOT-EMPTY', spot=p, left=round(hdist(H, p, org), 1))
        return 'dig-spot-empty %s' % str(p)
    return 'walk-to-dig-spot %s' % str(p)


def cardTable(H, kind, st):
    """A card task: walk to a table of that kind like a player (through doors, sailed to on another island) ->
    ('cards', table doId, kind) when standing at it, ('sail', island), or what it is doing."""
    here = hereArea(H)
    t = s_cards.tableHere(H, kind, here)
    if t is not None:
        if near(H, t, s_cards.SIT_FT, st, face=True, tag='to-card-table'):
            H.walk_cancel()
            return ('cards', t.doId, kind)
        return 'walk-to-card-table %s' % t.doId
    areas = questSpots()['areas']
    hisl = (areas.get(here) or [None])[0]
    gold = s_cards.gold(H)

    def cost(row):
        # this room, then fewest doors on this island, then another island; a table whose minimum bid the gold
        # cannot cover (above the reserve) last
        tisl = (areas.get(row[3]) or [None])[0]
        if row[3] == here:
            c = 0
        elif tisl is not None and tisl == hisl:
            p = hops(here, row[3])
            c = len(p) if p is not None else 40
        else:
            c = 50
        return c + (100 if kind == 'Blackjack' and 2 * row[1] + s_cards.RESERVE > gold else 0)
    rows = [r for r in s_cards.tablesOf(kind) if r[3] in areas]
    if not rows:
        return 'no-card-table %s' % kind
    row = min(rows, key=cost)
    if st.get('cardRow') != row[2]:
        st['cardRow'] = row[2]
        H.ev('CARDS-WALK', kind=kind, table=row[2], room=row[3], mult=row[1], cost=cost(row), here=here, gold=gold)
    r = goto(H, st, row[3], pos=row[4], arrive=8.0, tag='to-card-table')
    if r is True:
        return 'card-table-not-in-view %s' % row[2]
    return r


JAIL_LIMIT = float(os.environ.get('STORY_JAIL_LIMIT', '300'))   # s in jail (or in limbo) before a STALL
JST = {}            # jail state, kept across quests (a sink can come mid-quest and the quest can change in the cell)
STAGE_SEEN = set()


def stages(H):
    """Logs each first-sail stage once, as it happens: STAGE what=ship-got / launched / sailing / docked / c3.
    ship-got = a ship is in our inventory (the shipwright's, c2.9visitDarby); launched = first time at the wheel;
    sailing = at sea, off every island; docked = standing on an island after being aboard; c3 = a Chapter 3 quest."""
    la = H.la
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    aboard = sailing.onShip(H)
    here = sailing.hereUid(H)

    def once(what, **kw):
        if what not in STAGE_SEEN:
            STAGE_SEEN.add(what)
            H.ev('STAGE', what=what, area=H.area(), la=H.P(la), **kw)
    if ships:
        once('ship-got', ships=ships)
    if aboard and la.getGameState() == 'ShipPilot':
        once('launched', frm=here)
        STAGE_SEEN.add('wasAboard')
        if here is None:
            once('sailing')
    if 'wasAboard' in STAGE_SEEN and not aboard and here is not None and la.getGameState() == 'LandRoam':
        once('docked', at=here)
    if any(q.getQuestId().startswith('c3') for q in mainQuests(H)):
        once('c3', held=[q.getQuestId() for q in mainQuests(H)])


def jailed(H):
    """In the jail interior, or the server says we have a cell (jailCellIndex 100 = no cell)."""
    a = H.area()
    return (a is not None and a[0] == 'DistributedJailInterior') or getattr(H.la, 'jailCellIndex', 100) < 100


def ashoreOrSwim(gs, here, jail, aboard):
    """Pure: stop the 120 s 'back on land' wait. MAIN34 (11-22): a launch that found no route to the Padres dinghy
    walked him into the sea, and the wait for LandRoam ran its full 2 min while he swam; in the water the next sail try
    (a teleport) or the swim back can start at once."""
    return (gs == 'LandRoam' and (here is not None or jail)) or (gs == 'WaterRoam' and not aboard)


def landedOrSwim(H):
    return ashoreOrSwim(H.la.getGameState(), sailing.hereUid(H), jailed(H), sailing.onShip(H))


def ashore(H):
    """Back on solid ground after a sink or a failed launch: standing on an island, or in the jail."""
    return H.la.getGameState() == 'LandRoam' and (sailing.hereUid(H) is not None or jailed(H))


def cellDoorOut(door, spawn, past=6.0):
    """Pure: a point `past` ft beyond the cell door, on the line from where we spawned in the cell through the door
    (door, spawn = (x, y, z) in render). That is outside the cell, in the jail's corridor."""
    dx, dy = door[0] - spawn[0], door[1] - spawn[1]
    d = (dx * dx + dy * dy) ** 0.5 or 1.0
    return (door[0] + dx / d * past, door[1] + dy / d * past, door[2])


def jail(H, st):
    """One step out of jail, like a player: kick our own cell door until it breaks, walk out of the cell, leave by the
    jail's door. -> a short description while it works, or None when not jailed (the story goes on as usual).
    A walk it needs is left in st['go']. Lines: JAIL-LIMBO, JAIL-IN, JAIL-KICK, JAIL-CELL-OPEN, OUT-OF-CELL,
    JAIL-DOOR, JAIL-OUT, or STALL what='stuck in jail' / 'no area after the ship sank'."""
    la = H.la
    gs = la.getGameState()
    now = time.time()
    if H.area() is None and not sailing.onShip(H) and gs not in ('TeleportOut', 'TeleportIn'):
        # no parent area at all: after a sink before patch 0089 the pirate was left here (STORY27)
        t = JST.setdefault('limboT', now)
        if now - t > 10 and not JST.get('limboEv'):
            JST['limboEv'] = True
            H.ev('JAIL-LIMBO', gs=gs, la=H.P(la), cell=getattr(la, 'jailCellIndex', None), secs=round(now - t))
        if now - t > 90:
            if not JST.get('limboStall'):
                JST['limboStall'] = True
                H.ev('STALL', what='no area after the ship sank (patch 0089 not live?)', gs=gs, secs=round(now - t))
            return None
        return 'jail-limbo'
    JST.pop('limboT', None)
    JST.pop('limboEv', None)
    if not jailed(H):
        if JST.get('in') and not JST.get('outEv'):
            JST['outEv'] = True
            H.ev('JAIL-OUT', area=H.area(), la=H.P(la), secs=round(now - JST['in']))
        return None
    cell = getattr(la, 'jailCellIndex', 100)
    if not JST.get('in') or JST.get('outEv'):
        JST.clear()
        JST['in'] = now
        JST['spawn'] = tuple(la.getPos(H.render))
        H.ev('JAIL-IN', area=H.area(), cell=cell, gs=gs, la=H.P(la))
    if now - JST['in'] > JAIL_LIMIT:
        if not JST.get('stall'):
            JST['stall'] = True
            H.ev('STALL', what='stuck in jail', cell=cell, secs=round(now - JST['in']), la=H.P(la), step=JST.get('step'))
        return None
    if gs in ('DoorKicking', 'ThrownInJail'):
        return 'jail-%s' % gs
    dos = list(H.cr.doId2do.values())
    door = next((o for o in dos if type(o).__name__ == 'DistributedCellDoor' and getattr(o, 'cellIndex', -1) == cell), None)
    shut = door is not None and getattr(door, 'open', -1) != door.DSOpen and getattr(door, 'health', 0) > 0
    if shut and not JST.get('outCell'):
        JST['step'] = 'kick'
        if not near(H, door, 5, st, tag='cell-door'):
            return 'jail-walk-to-cell-door %s' % door.doId
        if now - JST.get('kickT', 0) > 15:
            JST['kickT'] = now
            JST['kicks'] = JST.get('kicks', 0) + 1
            H.ev('JAIL-KICK', door=door.doId, cell=cell, health=getattr(door, 'health', None), n=JST['kicks'], la=H.P(la))
            door.requestInteraction(la.doId)
        return 'jail-kick %s' % door.doId
    if door is not None and not JST.get('openEv'):
        JST['openEv'] = True
        H.ev('JAIL-CELL-OPEN', door=door.doId, cell=cell, health=getattr(door, 'health', None),
             secs=round(now - JST['in']))
    if door is not None and not JST.get('outCell'):
        JST['step'] = 'out-of-cell'
        dp = door.getPos(H.render)
        tgt = cellDoorOut((dp[0], dp[1], dp[2]), JST['spawn'])
        if not near(H, tgt, 2.5, st, face=False, tag='out-of-cell'):
            return 'jail-walk-out-of-cell'
        JST['outCell'] = True
        H.ev('OUT-OF-CELL', la=H.P(la), door=door.doId)
    JST['step'] = 'jail-door'
    jailArea = la.getParentObj()
    exits = [o for o in dos if type(o).__name__ == 'DistributedInteriorDoor'
             and getattr(o, 'parentId', None) == getattr(jailArea, 'doId', -1)]
    if not exits:
        return 'jail-no-exit-door'
    d = min(exits, key=lambda o: hdist(H, o))
    if not JST.get('doorEv'):
        JST['doorEv'] = True
        H.ev('JAIL-DOOR', door=d.doId, d=round(hdist(H, d), 1), la=H.P(la))
    return useDoor(H, d, st, 'jail')


NOSTEP_OUT = 30.0      # s with no quest step inside a building before he walks out (MAIN7 11-21: Orinda's visit)


def roomExit(H):
    """Pure-ish: the nearest inside door of the room he stands in (a shop or tavern), else None."""
    a = H.area()
    room = H.la.getParentObj()
    if not a or a[0] != 'DistributedGAInterior' or room is None:
        return None
    exits = [o for o in H.cr.doId2do.values() if type(o).__name__ == 'DistributedInteriorDoor'
             and getattr(o, 'parentId', None) == room.doId]
    return min(exits, key=lambda o: hdist(H, o)) if exits else None


def leaveRoom(H, st):
    """No quest step for NOSTEP_OUT s inside a building: walk out its door like a player would. MAIN7 (11-21) sat 6
    min in the Tortuga tavern on c3r2.5.5visitOrinda: the server gave no step for a goal outdoors (READY 0429 to sink),
    and the bot only re-asked for one. Outdoors the step shows again."""
    t0 = st.setdefault('noStepT', time.time())
    if time.time() - t0 < NOSTEP_OUT:
        return None
    d = roomExit(H)
    if d is None:
        return None
    if not st.get('leaveEv'):
        st['leaveEv'] = True
        H.ev('NOSTEP-LEAVE-ROOM', door=d.doId, room=H.area(), secs=round(time.time() - t0), d=round(hdist(H, d), 1))
    return useDoor(H, d, st, 'leave-room')


def act(H, q, st):
    """One action toward the current task. Returns a short description, or ('sail', uid). A walk it needs is left in
    st['go'] for run() to do."""
    la = H.la
    task = q.questDNA.getTasks()[0]
    ttype = type(task).__name__
    qs = la.questStep
    stype = qs.getStepType() if qs else 0
    sobj = H.cr.doId2do.get(qs.getStepDoId()) if qs and qs.getStepDoId() else None
    if stype:
        st.pop('noStepT', None)        # leaveRoom counts only an unbroken stretch with no step
    if q.isComplete():
        # every task done, only the hand-in is left: just follow the step (door / NPC / island) like a player
        ttype = 'HandIn'
    if ttype in s_shipquest.SHIP_TYPES + s_shipquest.DOCK_TYPES:
        # ship quests are played at sea (run() -> s_shipquest): out of any building / cave to the open island first
        if not sailing.onShip(H) and sailing.hereUid(H) is None:
            here = hereArea(H)
            isl = (questSpots()['areas'].get(here) or [None])[0] or sailing.islandOfUid(here)
            if isl is None:
                return 'ship-quest-no-island %s' % here
            r = goto(H, st, isl, tag='to-open-island')
            if isinstance(r, tuple):
                return 'to-open-island-%s %s' % r[:2]
            return 'on-open-island %s' % isl if r is True else r
        H.walk_cancel()
        if ttype in s_shipquest.DOCK_TYPES:
            uid, how = s_shipquest.dockTarget(H, task)
            return ('dock', uid, how) if uid is not None else 'dock-no-port %s' % how
        return ('shipfight',)
    if ttype in SKIP_TYPES:
        H.walk_cancel()
        return 'skip-type'
    if ttype in s_cards.TYPES:
        if s_cards.cards0289() is False:
            # job 33: without 0289 the first card dealt kills the game (KeyError in PlayingCardGlobals.getImage)
            H.walk_cancel()
            return ('skip', 'CARDS-FAIL', '0289 not on this client: the first card dealt would crash the game', {})
        if ttype in s_earn.BET_TYPES and not sailing.onShip(H):
            # job 33: gold to bet first (the reserve + a few full bids), earned the way the bribe's gold is
            e = s_earn.step(H, q, task, st)
            if e is not None:
                H.walk_cancel()
                return e
        return cardTable(H, s_cards.TYPES[ttype], st)
    if ttype == 'BossBattleTaskDNA':
        H.walk_cancel()
        return ('boss',)
    # another island: sail there (a kid never teleports between islands)
    hunt = huntAreas(task) if ttype in ENEMY_TYPES else None
    isl = stepIsland(H, sobj) if stype == 3 and hunt is None else None
    if isl and not sailing.onShip(H):
        # out of a building / cave first (through its door / tunnel), then sail
        r = goto(H, st, isl, tag='to-island')
        return 'on-island %s' % isl if r is True else r
    if isl:
        H.walk_cancel()
        return ('sail', isl)
    if sailing.onShip(H):
        # aboard our own ship: only a sail makes sense (never walk or teleport off the deck)
        H.walk_cancel()
        if hunt:
            area = (questSpots()['areas'].get(hunt[0]) or [None])[0]
        else:
            area = sailing.areaIsland(H, sobj) if stype == 3 else None
            area = area or stepIslandUid(H)
        if area:
            return ('sail', area)
        if ttype in GRIND_TYPES:
            shp = myShip(H)
            port = landPort(ttype, shipPos(H, shp))
            if port:
                return ('sail', port)
        return 'aboard-wait(step=%s %s)' % (stype, type(sobj).__name__ if sobj is not None else None)
    if ttype in s_earn.PAY_TYPES:
        # job 23b: a paid step (Bonita's bribe asks 50, NP2 came with 8): earn the gold first, the way a kid would
        e = s_earn.step(H, q, task, st)
        if e is not None:
            H.walk_cancel()
            return e
    # combat tasks: fight the nearest enemy of the task's type when one is in view
    if ttype in ENEMY_TYPES:
        ok = taskAreas(task) or hunt
        inLoc = ok is None or hereArea(H) in ok
        if WEAK:
            seen = [o.getLevel() or 0 for o in enemiesOf(H, task)] if inLoc else None
            w = tooWeak(getattr(task, 'level', 0), la.getLevel() or 0, seen)
            if w is not None:
                H.walk_cancel()
                return ('skip', 'STORY-TOO-WEAK', 'enemies level %d, the pirate is level %d (margin %d)'
                        % (w[0], w[1], WEAK_MARGIN), {'need': w[0], 'have': w[1], 'margin': WEAK_MARGIN,
                                                      'enemy': str(getattr(task, 'enemyType', None)),
                                                      'seen': seen, 'area': hereArea(H)})
        if s_guards.wants(H, q, task, stype, sobj, inLoc):
            # SAIL6: a stype-1 step on a Cadet fell through to the talk branch; never talk to an enemy, fight it
            H.walk_cancel()
            return ('guards',)
        foes = enemiesOf(H, task) if inLoc else []      # kills outside the task's location do not count
        if stype == 2 and sobj is not None and sobj in foes:
            foes.remove(sobj)
            foes.insert(0, sobj)
        if foes and (foes[0].getPos(H.render) - la.getPos(H.render)).length() < 400:
            return 'fight %s %s' % (type(foes[0]).__name__, fight(H, foes[0], st))
        if stype == 2 and sobj is not None and inLoc:
            near(H, sobj, 8, st, face=False)
            return 'walk-to-enemy %s' % sobj.doId
        if ok is not None or not stype:
            r = toEnemies(H, task, st, ok)
            if r is not None:
                return r
    if ttype == 'DeployShipTaskDNA':
        # launch like the sails do (sailing.launch: route to a dinghy from the dock, never a straight walk into the
        # harbour; deploy; walk to the wheel). The server credits the quest on the deploy (DistributedDinghyAI).
        if time.time() - st.get('dgT', 0) > 40:
            st['dgT'] = time.time()
            return ('deploy', sailing.hereUid(H))
        return 'deploy-wait'
    if ttype == 'RecoverContainerItemTaskDNA':
        r = container(H, q, task, st)
        if not (isinstance(r, str) and r.startswith('no-container-in-view') and stype):
            return r
    if ttype == 'RecoverTreasureItemTaskDNA':
        from pirates.quest.QuestConstants import TreasureIds
        if getattr(task, 'treasureId', None) not in (None, TreasureIds.ANY_TREASURE):
            return dig(H, q, task, st)        # named spots: walked / sailed to from the map, the step is not needed
        if stype != 3:
            return digAny(H, st)
    if qs and stype and sobj is None and qs.getStepDoId() and stype != 3:
        # step object not in interest yet: walk to where the beam is (posH on the origin)
        org = H.cr.doId2do.get(qs.getOriginDoId())
        key = (qs.getStepDoId(), qs.getOriginDoId())
        if org is not None and st.get('approach') != key:
            x, y, z, h = qs.getPosH()
            if not near(H, (x, y, z), TALK if stype == 1 else 3.0, st, face=False, ref=org, tag='approach') and st.get('goFails', 0) < 2:
                return 'approach-walk %s via %s' % (qs.getStepDoId(), type(org).__name__)
            left = hdist(H, (x, y, z), org)
            if left > 30:
                # two walks failed far from the beam: say so, and try the walk again every 20 s (as quest nodes)
                st.pop('go', None)
                if time.time() - st.setdefault('apFailT', time.time()) > 20:
                    st['goFails'] = 0
                    st.pop('apFailT', None)
                return 'approach-unreached %dft' % left
            st['approach'] = key        # there, or could not walk there (stuck event): go on to the nearest-door logic
            return 'approach %s via %s' % (qs.getStepDoId(), type(org).__name__)
        if org is None:
            return 'no-origin %s' % qs.getOriginDoId()
        if stype in (5, 6):
            # the step's door object never reached this client: use the nearest door to the beam
            x, y, z, h = qs.getPosH()
            from panda3d.core import Point3
            bp = H.render.getRelativePoint(org, Point3(x, y, z))
            doors = [d for d in H.cr.doId2do.values() if 'Door' in type(d).__name__ and hasattr(d, 'getPos')]
            doors.sort(key=lambda d: (d.getPos(H.render) - bp).length())
            if doors and (doors[0].getPos(H.render) - bp).length() < 150 and time.time() - st.get('doorT', 0) > 20:
                d = doors[0]
                if not nearDoor(H, d, st):
                    return 'walk-to-door(nearest) %s' % d.doId
                st['doorT'] = time.time()
                H.ev('DOOR-MISMATCH', stepDoId=qs.getStepDoId(), used=d.doId, cls=type(d).__name__,
                     dist=round((d.getPos(H.render) - bp).length(), 1), uid=getattr(d, 'interiorUid', None) or getattr(d, 'buildingUid', None))
                d.requestInteraction(la.doId)
                return 'door(nearest) %s' % d.doId
        return 'approach-wait'
    if stype in (5, 6) and sobj is not None:          # exterior / interior door
        if st.get('door') != sobj.doId or time.time() - st.get('doorT', 0) > 20:
            if not nearDoor(H, sobj, st):
                return 'walk-to-door %s' % sobj.doId
            st['door'] = sobj.doId
            st['doorT'] = time.time()
            sobj.requestInteraction(la.doId)
            return 'door %s' % sobj.doId
        return 'door-wait'
    if stype == 1 and sobj is not None:                # NPC
        if getattr(task, 'autoTriggerInfo', None) and not q.isComplete() and time.time() - st.setdefault('npcSeen', time.time()) < 15:
            return 'talk-wait-autotrigger'
        if time.time() - st.get('npcT', 0) > 15:
            if not near(H, sobj, TALK, st):
                return 'walk-to-npc %s' % sobj.doId
            st['npcT'] = time.time()
            sobj.requestInteraction(la.doId)
            if ttype == 'BribeNPCTaskDNA':
                # job 25b: the Bribe button the kid's way: gold checked again at the click, then the NPC's own
                # confirmBribe() box, Yes only when it offers Yes (s_earn.bribe); short = no click, earn first
                H.B.taskMgr.doMethodLater(3.0, lambda t, n=sobj: (s_earn.bribe(H, q, task, n, st), t.done)[1], 'walk-bribe')
                return 'bribe %s %s' % (sobj.doId, getattr(sobj, 'name', ''))
            return 'talk %s %s' % (sobj.doId, getattr(sobj, 'name', ''))
        return 'talk-wait'
    if stype == 4 and sobj is not None:                # tunnel
        return useTunnel(H, sobj, st)
    if stype == 7 and qs:                              # quest node
        org = H.cr.doId2do.get(qs.getOriginDoId())
        key = (qs.getOriginDoId(), tuple(round(v) for v in qs.getPosH()))
        if org is not None and st.get('qn') != key:
            x, y, z, h = qs.getPosH()
            if not near(H, (x, y, z), 6.0, st, face=False, ref=org, tag='questnode') and st.get('goFails', 0) < 2:
                return 'questnode-walk %s' % str((x, y, z))
            left = hdist(H, (x, y, z), org)
            if left > 30:
                # two walks failed far from the beam: say so (never 'there'), and try the walk again every 20 s
                st.pop('go', None)
                if time.time() - st.setdefault('qnFailT', time.time()) > 20:
                    st['goFails'] = 0
                    st.pop('qnFailT', None)
                return 'questnode-unreached %dft' % left
            st['qn'] = key          # a new beam spot (e.g. the next enemy spawn) is walked to again
            st['goFails'] = 0
            return 'questnode %s' % str((x, y, z))
        return 'questnode-there'
    if stype == 3 and sobj is not None:                # another (non-island) area
        uid = getattr(sobj, 'uniqueId', None)
        if uid in questSpots()['areas']:
            # walk there through its doors / tunnels (the map in quest_spots.json); another island: out, then sail
            r = goto(H, st, uid, tag='to-area')
            if r is True:
                return 'area-there %s' % uid
            if not (isinstance(r, str) and '-no-route' in r):
                return r
        far = sailing.areaIsland(H, sobj)
        if far:
            return ('sail', far)                       # a cave on another island: sail there first
        if uid and time.time() - st.get('tpT', 0) > 60 and not player():
            st['tpT'] = time.time()
            H.ev('AREA-TELEPORT', to=uid, cls=type(sobj).__name__, here=H.area())
            H.mw('areaTeleport %s' % uid)
            return 'areaTeleport %s' % uid
        return 'area-wait'
    if ttype in ENEMY_TYPES:
        return 'no-enemy-in-view(step=%s)' % stype
    if not stype:
        r = leaveRoom(H, st)
        if r:
            return r
    return 'no-step(type=%s)' % stype



def taskDone(q):
    """The quest is complete, or one of its tasks has reached its goal (walker H.quests() ts [progress, goal, ...])."""
    try:
        if q.isComplete():
            return True
        return any(getattr(t, 'goal', None) and (getattr(t, 'progress', 0) or 0) >= t.goal for t in q.getTaskStates())
    except Exception:
        return False


def talkingTo(H, sobj=None):
    """The NPC the pirate is talking to: interactMode is set by DistributedNPCTownfolk.startInteract."""
    c = [o for o in list(H.cr.doId2do.values()) if getattr(o, 'interactMode', 0) and hasattr(o, 'cancelInteraction')]
    if sobj is not None and sobj in c:
        return sobj
    if c:
        try:
            c.sort(key=lambda o: hdist(H, o))
        except Exception:
            pass
        return c[0]
    return sobj if hasattr(sobj, 'cancelInteraction') else None


def clickDialog(H):
    """Press the open dialog's own button like a player: the last option (Accept) on a choice page, else Next / OK.
    Returns what was pressed, or None when no button shows."""
    sub = H.la.guiMgr.subtitler
    shown = [o for o in (getattr(sub, '_Subtitler__optionButtons', None) or []) if not o.isHidden()]
    btn = shown[-1] if shown else sub.confirmButton
    if btn.isHidden() or not btn['command']:
        return None
    label = ('option:' if shown else 'confirm:') + str(btn['text'])[:20]     # read first: a press relabels it
    btn['command'](*(btn['extraArgs'] or []))
    return label


def npcExit(H, npc):
    """End NPCInteract the game's own way, mildest first; each rung only when the ones before left it on. Returns the
    ways used. dialogFinish ends a dialog movie (DistributedQuestGiver.playDialogMovie listens for it);
    forceDoneChatPage ends a quest string (its doneChatPage handler cancels the interact when no GUI is open);
    handleEndInteractKey is the player's end key; cancelInteraction is what that key calls."""
    la = H.la
    ways = []

    def on():
        return la.getGameState() == 'NPCInteract'
    if npc is not None and hasattr(npc, 'currentDialogMovie'):
        try:
            (getattr(H.B, 'messenger', None) or __import__('builtins').messenger).send('dialogFinish')
            ways.append('dialogFinish')
        except Exception as e:
            ways.append('dialogFinish-err %r' % e)
    if npc is not None and on() and (getattr(npc, 'playingQuestString', False) or getattr(npc, 'dialogOpen', False)):
        try:
            npc.forceDoneChatPage()
            ways.append('forceDoneChatPage')
        except Exception as e:
            ways.append('forceDoneChatPage-err %r' % e)
    if npc is not None and on():
        if getattr(npc, 'questMenuGUI', None):
            try:
                npc.cleanUpQuestMenu()
                ways.append('cleanUpQuestMenu')
            except Exception as e:
                ways.append('cleanUpQuestMenu-err %r' % e)
        try:
            npc.handleEndInteractKey()
            ways.append('handleEndInteractKey')
        except Exception as e:
            ways.append('handleEndInteractKey-err %r' % e)
    if npc is not None and on():
        try:
            npc.cancelInteraction(la)
            ways.append('cancelInteraction')
        except Exception as e:
            ways.append('cancelInteraction-err %r' % e)
    if on():
        try:
            la.b_setGameState('LandRoam')     # last resort: what stopInteract itself sets
            ways.append('setGameState')
        except Exception as e:
            ways.append('setGameState-err %r' % e)
    return ways


def npcTick(H, q, cur, qid):
    """Called each pass while the pirate is in NPCInteract. Once a task is done: press the dialog's buttons every
    NPC_CLICK s; with no button to press, or after NPC_LIMIT s, end the interact (NPC-EXIT). With nothing done, end
    it after NPC_HARD s (NPC-STUCK then NPC-EXIT). Returns what it did, or None."""
    now = time.time()
    t0 = cur.setdefault('npcIT', now)
    secs = now - t0
    # MAIN27: bribing Pauper Pedro moved the quest on to visitFernando with Pedro's talk still open; the new step was
    # not done, so the bot waited NPC_HARD (2 min) on a talk that belonged to the step before. A talk the quest has
    # moved on from is ended like a finished one.
    moved = cur.setdefault('npcQ', qid) != qid
    done = taskDone(q) or moved
    if now - cur.get('npcClickT', 0) < NPC_CLICK or (done and secs < NPC_CLICK):
        return None
    if not done and secs < NPC_HARD:
        return None
    cur['npcClickT'] = now
    qs = H.la.questStep
    sobj = H.cr.doId2do.get(qs.getStepDoId()) if qs and qs.getStepDoId() else None
    npc = talkingTo(H, sobj)
    who = getattr(npc, 'doId', None)
    name = getattr(npc, 'name', '')
    if done and secs < NPC_LIMIT:
        try:
            pressed = clickDialog(H)
        except Exception as e:
            pressed = None
            H.ev('NPC-CLICK-err', q=qid, err=repr(e)[-200:])
        if pressed:
            H.ev('NPC-CLICK', q=qid, npc=who, name=name, pressed=pressed, secs=round(secs, 1),
                 gsAfter=H.la.getGameState())
            return pressed
    if not done:
        H.ev('NPC-STUCK', q=qid, npc=who, name=name, secs=round(secs))
    movie = hasattr(npc, 'currentDialogMovie')
    ways = npcExit(H, npc)
    H.ev('NPC-EXIT', q=qid, npc=who, name=name, secs=round(secs, 1), done=done, ways=ways, movie=movie,
         gsAfter=H.la.getGameState())
    cur['npcIT'] = now          # if the game puts it back in NPCInteract, the next try waits its own time
    cur['npcQ'] = qid
    return 'exit'


def proven():
    import json
    try:
        with open(PROVEN_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def prove(qid, ttype, tag):
    """A grind quest was played to the end for real: its type is proven, later repeats may be GM-completed."""
    import json
    p = proven()
    if ttype in p:
        return False
    p[ttype] = {'q': qid, 'tag': tag, 't': time.strftime('%Y-%m-%d %H:%M')}
    with open(PROVEN_FILE, 'w') as f:
        json.dump(p, f, indent=1)
    return True


def repeatGrind(q):
    """The task type when q is a repeat of a proven grind type that may be GM-completed, else None."""
    import re
    if os.environ.get('STORY_GRIND') == 'play':
        return None
    qid = q.getQuestId()
    ttype = type(q.questDNA.getTasks()[0]).__name__
    if ttype not in REPEAT_TYPES or ttype not in proven():
        return None
    # DOLL13 (11-21): the doll chain's wdr2.3recoverSilk kept level-1 claude2's Light Sloop 15 min against the only
    # EITC ships off Port Royal (lv 7-44), 0 sinks. A weapon chain's ship step is the same proven ship drop, so it is
    # skipped too; its land steps (doll skills, barrels, blood, bone dust) still play for real.
    chainShip = ttype in SHIP_SKIP_TYPES and re.match(r'w[a-z]{1,3}\d+\.\d', qid)
    if not (re.match(r'c[\d.]+r\d', qid) or chainShip) or q.questDNA.getFinalizeInfo():
        return None      # a main-line story quest, or one with its own scenes: always for real
    return ttype


TUT_NO =('doCutlassTutorial',)   # panels whose Yes starts an interactive tutorial that waits on player events


def tutNo(H):
    # walker auto-clicks Yes on every tutorial panel; Yes on these starts a tutorial (script 101) that waits on
    # weaponEquipped etc. and leaves the game in Dialog. Answer No instead (script 102 still levels the cutlass
    # and finishes the quest movie), like a player who skips the tutorial.
    from pirates.piratesgui import NewTutorialPanel as NTPm
    wAct = NTPm.NewTutorialPanel.activate

    def act(panel):
        r = wAct(panel)
        if getattr(panel, 'mode', None) in TUT_NO:
            H.B.taskMgr.remove('walk-yes')

            def no(t):
                try:
                    b = getattr(panel, 'noTutorial', None)
                    cmd = None if b is None or not hasattr(b, '_optionInfo') else b['command']
                    if cmd:
                        cmd(*(b['extraArgs'] or []))
                    H.ev('TUT-NO', mode=panel.mode, has=cmd is not None)
                except Exception as e:
                    H.ev('TUT-NO-err', mode=panel.mode, err=repr(e)[-300:])
                return t.done
            H.B.taskMgr.doMethodLater(1.0, no, 'story-tut-no')
        return r
    NTPm.NewTutorialPanel.activate = act


def okAndName(H):
    # Darby's ship tutorial: dialog pages that wait on their OK button, then the ship-name panel; his second
    # dialog only plays once the name is sent (nameChosen -> shipTutorialPt1 -> tutorialShipConstructed).
    # Click OK and commit the panel's picked name through their own callbacks, like a player (as s_darby).
    from pirates.piratesgui import Subtitler as SUBm
    oCT = SUBm.Subtitler.confirmText

    def ct(sub, text, event, *a, **k):
        r = oCT(sub, text, event, *a, **k)

        def click(t):
            if sub.event == event and not sub.confirmButton.isHidden():   # not clicked yet (s_regress clicks too)
                H.ev('click-OK', text=str(text)[:50], event=event)
                sub.confirmButton['command']()
            return t.done
        H.B.taskMgr.doMethodLater(2.0, click, 'story-ok')
        return r
    SUBm.Subtitler.confirmText = ct
    from pirates.piratesgui import NamePanelGui as NPm
    oNPi = NPm.NamePanelGui.__init__
    if oNPi.__name__ != '__init__':   # s_regress / s_darby exec this file with their own name hook on
        return

    def npi(panel, *a, **k):
        oNPi(panel, *a, **k)

        def commit(t):
            try:
                # read the name first: handleCommit destroys the panel, and a destroyed panel's name raises
                nm, typed = getattr(panel, 'name', None), getattr(panel, 'isTypedName', None)
                panel.handleCommit()
                H.ev('SHIP-NAME', shipName=nm, typed=typed)
            except Exception:
                import traceback
                H.ev('SHIP-NAME-CRASH', tb=traceback.format_exc()[-600:])
            return t.done
        H.B.taskMgr.doMethodLater(3.0, commit, 'story-name')
    NPm.NamePanelGui.__init__ = npi


# c2.11 Barbossa's tutorials (QuestScripts quest_tut_barbossa_pistol/lookout_tutorial) have no skip button: each
# message panel waits on one of these events, which the player's input makes (FPSCamera / TargetManager /
# DistributedBattleAvatar / LocalPirate / GuiManager)
TUT_PLAY = {'pistolAim': ('pistolMoved',), 'pistolTarget': ('pistolAimedTarget',), 'pistolHit': ('pistolHitTarget',),
            'pistolPractice': ('weaponSheathed',), 'lookoutChestOpen': ('seachestOpened',),
            'lookoutOpen': ('lookoutOpened',), 'lookoutClose': ('lookoutClosed', 'seachestClosed'),
            # c1 Doggerel Dan's sea chest (quest_tut_seachest_intro_100): chest icon, journal icon, chest icon again
            'seachestOpen': ('seachestOpened',), 'questPageOpen': ('questPageOpened',),
            'questPageClose': ('seachestClosed', 'questPageClosed')}
MONKEY_UID = '1175912064.0JB2'   # the pistol target the script unstashes
TUT_RETRY = 4.0                  # s between tries while a panel's event has not come
PISTOL_OWNED = set()             # panel modes s_pistol.py plays (pir-bot job 7); tutPlay leaves them alone


def tutPlay(H):
    # Play them like a player: hold the right mouse button and move the mouse onto the monkey, left-click to shoot,
    # Escape to put the pistol away; click the sea chest icon, the telescope, then the chest again. Buttons go
    # through the game's own handlers (mouse3 / mouse1 / escape events, the DirectButtons' commands); mouse moves come
    # in where CameraMode reads the window pointer (the bot's window has no real mouse), so FPSCamera turns, bounds
    # and sends pistolMoved itself.
    import math
    from panda3d.core import Point3
    from direct.showbase.DirectObject import DirectObject
    from pirates.piratesgui import NewTutorialPanel as NTPm
    from pirates.pirate import CameraMode as CMm
    from direct.showbase.MessengerGlobal import messenger as msg
    vm = {'d': None}
    aim = {'on': False, 't0': 0.0, 'over': None, 'warned': False, 'n0': 0}
    heard = {'n': 0}             # event -> number of the last time it came (a panel only counts what came after it)
    oRead = CMm.CameraMode._mouseReadTask

    def read(cam, task):
        r = oRead(cam, task)
        if vm['d'] is not None:
            cam.mouseDelta, vm['d'] = vm['d'], None
        return r
    CMm.CameraMode._mouseReadTask = read
    obs = DirectObject()

    def hear(e):
        heard['n'] += 1
        heard[e] = heard['n']
        H.ev('TUT-EVENT', event=e)
    for e in set(x for v in TUT_PLAY.values() for x in v):
        obs.accept(e, hear, [e])

    def target():
        o = None
        try:
            o = H.cr.uidMgr.justGetMeMeObject(MONKEY_UID)
        except Exception:
            pass
        if o is None or (hasattr(o, 'isEmpty') and o.isEmpty()):
            from pirates.battle import TeamUtils
            best = None
            for x in list(H.cr.doId2do.values()):
                try:
                    if x is H.la or not hasattr(x, 'gameFSM') or not TeamUtils.damageAllowed(x, H.la):
                        continue
                    d = H.la.getDistance(x)
                    if d < 120 and (best is None or d < best[0]):
                        best = (d, x)
                except Exception:
                    continue
            o = best[1] if best else None
        return o

    def aimTask(t):
        if not aim['on']:
            return t.done
        fc = getattr(getattr(H.la, 'cameraFSM', None), 'fpsCamera', None)
        tgt = target()
        if fc is None or tgt is None:
            if not aim['warned']:
                aim['warned'] = True
                H.ev('TUT-AIM-NO-TARGET', fps=fc is not None)
            return t.cont
        if not fc.mouseControl and time.time() - aim['t0'] > 2.0:   # right button not taken yet: press it again
            aim['t0'] = time.time()
            msg.send('mouse3-up')
            msg.send('mouse3')
        zc = tgt.getHeight() * 0.6 if hasattr(tgt, 'getHeight') else 2.0
        p = H.B.cam.getRelativePoint(tgt, Point3(0, 0, zc))
        ha = math.degrees(math.atan2(p[0], p[1]))
        va = math.degrees(math.atan2(p[2], math.hypot(p[0], p[1])))
        dx = max(-30.0, min(30.0, 0.5 * ha / fc.SensitivityH))      # half the way each frame, like a hand
        dy = max(-30.0, min(30.0, -0.5 * va / fc.SensitivityP))
        if getattr(getattr(H.B, 'options', None), 'mouse_look', False):
            dy = -dy
        if heard.get('pistolMoved', 0) <= aim['n0'] and abs(dx) < 1 and abs(dy) < 1:
            dx = 2.0
        over = getattr(H.la, 'currentAimOver', None)
        if over is not aim['over']:
            aim['over'] = over
            H.ev('TUT-AIM-OVER', target=getattr(over, 'doId', None), want=getattr(tgt, 'doId', None),
                 h=round(ha, 1), p=round(va, 1))
        if abs(dx) >= 0.5 or abs(dy) >= 0.5:
            vm['d'] = (dx, dy)
        return t.cont

    def aimStart():
        if not aim['on']:
            aim.update(on=True, t0=time.time(), warned=False, n0=heard['n'])
            msg.send('mouse3')
            H.B.taskMgr.add(aimTask, 'story-tut-aim')

    def aimStop():
        if aim['on']:
            aim['on'] = False
            msg.send('mouse3-up')

    def click(m):
        if m == 'pistolHit':
            msg.send('mouse1')
            H.B.taskMgr.doMethodLater(0.15, lambda t: msg.send('mouse1-up') or t.done, 'story-tut-up')
        elif m == 'pistolPractice':
            aimStop()
            msg.send('escape')
        else:
            tray = H.la.guiMgr.chestTray
            b = {'lookoutOpen': tray.lookoutButton, 'questPageOpen': tray.questButton}.get(m, tray.chestButton)
            b.commandFunc(None)

    def act(panel):
        r = wAct(panel)
        m = getattr(panel, 'mode', None)
        if m not in TUT_PLAY or m in PISTOL_OWNED:
            return r
        H.ev('TUT-PLAY', mode=m)
        n = {'tries': 0, 'n0': heard['n']}

        def play(t):
            if any(heard.get(e, 0) > n['n0'] for e in TUT_PLAY[m]):
                if m == 'pistolPractice':
                    aimStop()
                return t.done
            if n['tries'] >= 6:
                H.ev('TUT-PLAY-GAVE-UP', mode=m, heard=dict(heard), over=getattr(aim['over'], 'doId', None))
                aimStop()
                return t.done
            n['tries'] += 1
            try:
                if m in ('pistolAim', 'pistolTarget', 'pistolHit'):
                    aimStart()
                if m not in ('pistolAim', 'pistolTarget'):
                    if m != 'pistolHit' or getattr(H.la, 'currentAimOver', None) is not None:
                        click(m)
                        H.ev('TUT-CLICK', mode=m, n=n['tries'])
            except Exception as e:
                H.ev('TUT-PLAY-err', mode=m, err=repr(e)[-300:])
            t.delayTime = TUT_RETRY
            return t.again
        H.B.taskMgr.doMethodLater(1.5, play, 'story-tut-' + m)
        return r
    wAct = NTPm.NewTutorialPanel.activate
    NTPm.NewTutorialPanel.activate = act


def run(H):
    H.snap('initial')
    try:
        wp = H.B.win.getProperties()
        H.ev('win-props', fullscreen=wp.getFullscreen(), undecorated=wp.getUndecorated(),
             size=[wp.getXSize(), wp.getYSize()], origin=[wp.getXOrigin(), wp.getYOrigin()],
             winType=type(H.B.win).__name__, offscreen=bool(os.environ.get('PROOF_OFFSCREEN')))
    except Exception as e:
        H.ev('win-props-err', err=str(e))
    stopInt = _qint(STOP) if STOP else None
    H.ev('story-chain', n=len(STORY), first=STORY[0], last=STORY[-1], stop=STOP, stopInt=stopInt, ladders=LADDERS,
         tp=bool(os.environ.get('STORY_TP')))
    # BOT_SHIP (places 11-21): the shared test pirate can own a lane's extra ship (DOLL5: boats' Light Galleon came
    # first and never launched); put this run's own ship first, as s_everyship.ordered does (every user takes [0])
    want = int(os.environ.get('BOT_SHIP') or 0)
    try:
        inv = H.la.getInventory()
        orig = inv.getShipDoIdList
        if want and want in list(orig()):
            inv.getShipDoIdList = lambda: [want] + [x for x in orig() if x != want]
        H.ev('BOT-SHIP', want=want or None, ships=list(inv.getShipDoIdList()))
    except Exception as e:
        H.ev('BOT-SHIP-err', err=str(e))
    seen, stalls, skips = [], [], []
    FORCED.clear()
    cur = {'id': None, 't0': 0, 'st': {}, 'completeT': None, 'completeReal': None, 'lastAct': None}

    # STORY_FORCE (11-17 pir-test): the shared test pirate has often done the forced step before (STEP-STORY6 ended at
    # once on 'stop-already-done'), so a forced step counts as done only once it was held this run and then completed
    force = {'on': bool(os.environ.get('STORY_FORCE')) and STOP == START, 'held': False}

    def stopDone():
        if force['on']:
            q = next((q for q in mainQuests(H) if q.getQuestId() == STOP), None)
            if q is not None and not q.isComplete():
                force['held'] = True
                return False
            return force['held']
        return stopInt is not None and stopInt in list(H.la.getQuestHistory())

    def passEv(why):
        if stalls:
            H.ev('STRETCH-END-WITH-STALLS', why=why, stalls=stalls, skips=skips, seen=seen)
        else:
            H.ev('PASS', mission='%s %s..%s' % ('+'.join(LADDERS), seen[0] if seen else None, STOP or sorted(FINALS)), why=why,
                 seen=seen, skips=skips, tp=bool(os.environ.get('STORY_TP')), area=H.area())

    if stopDone():
        H.ev('stop-already-done', stop=STOP, hist=H.hist())
        return
    watchDisconnect(H)
    tutNo(H)
    okAndName(H)
    try:
        import s_pistol
        PISTOL_OWNED.update(s_pistol.install(H))
    except Exception as e:
        H.ev('PISTOL-err', why=repr(e))
    try:
        tutWatch(H)
    except Exception as e:
        H.ev('TUT-WATCH-err', why=repr(e))
    try:
        tutPlay(H)
    except Exception as e:   # only Barbossa's tutorials need it: log, don't end the run here
        H.ev('TUT-PLAY-err', why=repr(e))
    at =os.environ.get('STORY_AT', PR)
    if at == 'here':
        # 11-21 MAIN10: a chunk that logs in on the island its last chunk ended on (Orinda's Tortuga) stays there;
        # the teleport to Port Royal cost a 4 min sail straight back. Only a pirate not on an island is moved.
        at = sailing.hereUid(H) or PR
    if sailing.hereUid(H) != at:
        # run setup only (another chat's run may have left the test pirate anywhere): never used mid-story
        H.ev('SETUP-TP', to=at, here=H.area())
        H.mw('areaTeleport %s' % at)
        yield ('until', lambda: sailing.hereUid(H) == at and H.la.getGameState() == 'LandRoam', 60, 'setup tp')
        _t = time.time()
        yield ('upto', lambda: settled(H, _t, 2.0), 5, 'island loaded after setup tp')
    # 11-21 MAIN1: measured from the walker's watchdog start (login took 23 s), not from here, else the watchdog
    # kills the run first; a long sail can still overrun, so a CHUNK run also ends through the timeout hook below
    W = sys.modules.get('pir_walker')
    wt0 = getattr(W, 'WATCH', {}).get('t0') or time.time()
    secs = float(os.environ.get('STORY_SECS', str(max(60.0, float(os.environ.get('PROOF_SECS', '600')) - 60 - (time.time() - wt0)))))
    t_end = time.time() + secs
    if FROM:
        t0 = time.time()
        ok = yield from go(H, FROM, 10.0, False, None, 'setup-from')
        H.ev('SETUP-WALK', to=list(FROM), ok=ok, left=round(hdist(H, FROM), 1), secs=round(time.time() - t0))
    if os.environ.get('TUT_THEN_STORY'):
        # straight from the tutorial (s_tutorial hands over at Port Royal): a new pirate gets his first story quest
        # from the game itself once Jolly Roger's scene is over. Wait for it like a player would, and say what he holds
        yield ('until', lambda: any(not q.isComplete() and not q.getQuestId().startswith('Chapter1.')
                                    for q in mainQuests(H)), 45, 'first story quest after the tutorial')
        held = [q.getQuestId() for q in mainQuests(H)]
        H.ev('STORY-HANDOFF', held=held, all=H.qids(), hist=H.hist()[-5:], area=H.area())
        # a Chapter 1 (tutorial) quest still held here can never be done or handed in: its boat and island are gone.
        # Report it, then skip it so the story can start (a game bug to fix server-side if this event ever shows)
        for q in [q for q in mainQuests(H) if q.getQuestId().startswith('Chapter1.')]:
            H.ev('SKIP', q=q.getQuestId(), type='tutorial', why='tutorial quest still held after the tutorial ended')
            skips.append((q.getQuestId(), 'tutorial quest left over'))
            skipQ(H, q.getQuestId(), 'tutorial quest left over')
            yield ('upto', lambda: q.getQuestId() not in H.qids(), 3, 'tutorial quest skipped')
    if os.environ.get('STORY_FORCE') and mainQuest(H) is not None and mainQuest(H).getQuestId() != START:
        # test setup only (11-17 pir-test): start a chosen step (a ship quest) on the shared test pirate
        H.ev('STORY-FORCE', drop=mainQuest(H).getQuestId(), q=START)
        H.mw('dropQuest %s' % mainQuest(H).getQuestId())
        yield ('until', lambda: mainQuest(H) is None, 15, 'force drop')
    if mainQuest(H) is None:
        H.ev('STORY-GIVE-START', q=START, why='no main story quest held', all=H.qids())
        H.mw('giveQuest %s' % START)
        yield ('until', lambda: mainQuest(H) is not None, 15, 'give start')
    # test setup only (11-17 pir-test): a START inside a QuestChoice needs its siblings too, as the game hands them
    # out together; with only one held, the finished one waits for siblings the pirate never got (SAIL2's stall)
    if os.environ.get('STORY_FORCE') or os.environ.get('STORY_SIBLINGS'):
        hist = list(H.la.getQuestHistory())
        for sib in _choiceSiblings(START):
            if sib not in H.qids() and _qint(sib) not in hist:
                H.ev('STORY-GIVE-SIBLING', q=sib, of=START)
                H.mw('giveQuest %s' % sib)
                yield ('until', lambda: sib in H.qids(), 15, 'give sibling %s' % sib)
    H.ev('STORY-START', q=getattr(mainQuest(H), 'getQuestId', lambda: None)(), secs=round(secs))
    score0 = chunkScore(H)
    H.ev('chunk-start', score=score0, quests=[d for d in H.quests() if d['id'] in ORDER])
    if CHUNK and hasattr(W, 'WATCH'):
        def lastWord():   # the watchdog fired mid-step: still a chunk end, PASS if the story moved
            score1 = chunkScore(H)
            H.ev('chunk-end', score0=score0, score=score1, at='watchdog', quests=[d for d in H.quests() if d['id'] in ORDER])
            if score1 > score0:
                passEv('chunk progress %s -> %s (at the watchdog)' % (score0, score1))
        W.WATCH['hooks'].append(lastWord)
    yield from loop(H, dict(seen=seen, stalls=stalls, skips=skips, cur=cur, stopDone=stopDone, passEv=passEv,
                            t_end=t_end, score0=score0))


def loop(H, L):
    """The story loop, one tick per pass, until L['t_end'] (run()'s body; PLAYERBOTS quests.py drives it too with
    its own L). Ends early at the stop, the story's end, no next quest (a player bot: every held one set aside) or
    three failed launches."""
    seen, stalls, skips, cur = L['seen'], L['stalls'], L['skips'], L['cur']
    stopDone, passEv, t_end, score0 = L['stopDone'], L['passEv'], L['t_end'], L['score0']
    while time.time() < t_end:
        if stopDone():
            H.ev('stop-done', stop=STOP, after=round(time.time() - cur['t0'], 1), qids=H.qids())
            shot(H, '%s-stop-%s' % (runTag(), STOP))     # the goal's end gets a picture too (DOLL21 stopped mid-chapter)
            passEv('%s completed' % STOP)
            break
        q = mainQuest(H)
        if q is None:
            yield ('until', lambda: mainQuest(H) is not None or stopDone(), 5 if player() else 45,
                   'next story quest after %s' % cur['id'])
            if stopDone():
                continue
            q = mainQuest(H)
            if q is None:
                if cur['id'] in FINALS:
                    H.ev('STORY-END', after=cur['id'], qids=H.qids(), hist=H.hist())
                    if not STOP:
                        passEv('reached the end of %s' % '+'.join(LADDERS))
                else:
                    H.ev('STORY-END-NO-NEXT', after=cur['id'], qids=H.qids(), hist=H.hist())
                break
        qid = q.getQuestId()
        if qid != cur['id']:
            # the game's own pick before track(): the server tracks the next quest after a hand-in (brain d189392),
            # so trackedBefore == qid means it worked and '' means it did not
            trackedBefore = H.la.activeQuestId
            if cur['id']:
                H.ev('quest-advanced', frm=cur['id'], to=qid, secs=round(time.time() - cur['t0'], 1),
                     held=[x.getQuestId() for x in mainQuests(H)], trackedBefore=trackedBefore,
                     stepBefore=repr(H.la.questStep))
                if chapter(qid) != chapter(cur['id']):
                    shot(H, '%s-end-%s' % (runTag(), chapter(cur['id'])))
                from pirates.quest import QuestDB
                ftype = type(QuestDB.QuestDict[cur['id']].getTasks()[0]).__name__
                if ftype in SKIP_TYPES and cur['id'] not in [s[0] for s in skips + stalls]:
                    tag = os.path.basename(os.environ.get('PROOF_EVOUT', '')).replace('walk-', '').replace('-events.jsonl', '')
                    if prove(cur['id'], ftype, tag):
                        H.ev('PROVEN', q=cur['id'], type=ftype, tag=tag)
            cur.update(id=qid, t0=time.time(), st={}, completeT=None, completeReal=None, lastAct=None)
            seen.append(qid)
            H.ev('QUEST', q=qid, i=ORDER[qid], task=type(q.questDNA.getTasks()[0]).__name__, area=H.area(),
                 held=[x.getQuestId() for x in mainQuests(H)])
            track(H, qid)
            yield ('upto', lambda: hasStep(H), 4, 'tracker step')
            H.ev('tracker', q=qid, **H.step())
            continue
        gs = H.la.getGameState()
        if time.time() - cur.get('hb', 0) > 60:
            cur['hb'] = time.time()
            H.ev('heartbeat', q=qid, gs=gs, area=H.area(), ts=[x for x in H.quests() if x['id'] == qid])
        stages(H)
        jr = jail(H, cur['st'])
        if jr is not None:
            if jr != cur['lastAct']:
                H.ev('act', q=qid, a=jr, la=H.P(H.la), area=H.area())
                cur['lastAct'] = jr
            cur['t0'] = time.time()     # time in jail is not the quest stalling (jail() has its own limit)
            g = cur['st'].pop('go', None)
            if g is not None and H.la.getGameState() == 'LandRoam':
                obj, arrive, face, ref, tag = g
                yield from go(H, obj, arrive, face, ref, tag)
            else:
                yield ('upto', changed(H), 2, 'jail tick')
            continue
        aboard = sailing.onShip(H)
        if gs != 'LandRoam' and not (aboard and gs in ('ShipPilot', 'LandRoam')):
            # NEWP5-NP2 11-18: a weapon left drawn kept the pirate in Battle for 20 min; leave Battle the game's own way
            try:
                fightTask = 'Defeat' in type(q.questDNA.getTasks()[0]).__name__
            except Exception:
                fightTask = True
            if gs == 'Battle' and not aboard and not tutRecent():   # job 10b: fight quests too
                bt = cur.setdefault('battleT', time.time())
                if time.time() - bt > 30 and time.time() - cur.get('escT', 0) > 10:
                    cur['escT'] = time.time()
                    try:
                        H.la.requestExitBattle()
                        H.ev('BATTLE-EXIT', q=qid, secs=round(time.time() - bt), fight=fightTask,
                             gsAfter=H.la.getGameState())
                    except Exception as e:
                        H.ev('BATTLE-EXIT-err', err=repr(e)[-200:])
            else:
                cur.pop('battleT', None)
            if gs == 'NPCInteract' and not aboard:
                # job 16: a finished talk left on screen (Gibbs, c3visitJoshamee) waited 18 min here
                npcTick(H, q, cur, qid)
            else:
                cur.pop('npcIT', None)
                cur.pop('npcQ', None)
            if gs == 'WaterRoam' and not aboard:
                # DOLL10: a walk ended in the sea and he swam on the spot for 15 min waiting for the game state to
                # change. A player swims back to where he left the land
                sw = swimBack(cur, time.time(), qid=qid)
                if sw == 'swim':
                    pt = cur['landPt']
                    H.ev('SWIM-BACK', q=qid, n=cur['swims'], to=[round(v, 1) for v in pt], la=H.P(H.la))
                    yield from _lastLeg(H, pt, H.area(), 'swim-back', arrive=3.0, face=False, timeout=60,
                                        tag='swim-back')
                    continue
                if sw == 'tp':
                    here = sailing.hereUid(H)
                    to = swimPort(here)
                    H.ev('SWIM-TP', q=qid, to=to, frm=here, la=H.P(H.la), to_land=cur.get('landPt'),
                         why='%d swims back did not reach land' % SWIM_TRIES)
                    H.snap('swim-tp')
                    if mapHop(H, to, 'swim-tp'):
                        yield ('until', lambda: sailing.hereUid(H) == to and H.la.getGameState() == 'LandRoam', 90,
                               'swim tp')
                        continue
                    sw = 'stall'
                if sw == 'stall':
                    H.ev('STALL', what='swimming: %d swims back did not reach land' % SWIM_TRIES, q=qid,
                         la=H.P(H.la), to=cur.get('landPt'))
                    stalls.append((qid, 'swimming'))
                    H.snap('stall-swimming')
                    skipQ(H, qid, 'swimming')
                    cur.pop('swimT', None)
                    cur['swims'] = 0
                    yield ('upto', changed(H), 3, 'after skip of a swim')
                    continue
            else:
                cur.pop('swimT', None)
            yield ('upto', changed(H), 2, 'game state')
            continue
        cur.pop('battleT', None)
        cur.pop('npcIT', None)
        cur.pop('npcQ', None)
        cur.pop('swimT', None)
        cur['swims'] = 0
        if not aboard:
            try:
                lp = H.la.getPos(H.render)
                cur['landPt'] = (lp[0], lp[1], lp[2])
            except Exception:
                pass
        done = q.isComplete()
        if done:
            # tasks done but not handed in (the finishing scene did not play, or an earlier run stopped first).
            # Give the game 10 s to finish on its own, then follow the quest step to the return NPC and talk.
            if cur['completeT'] is None:
                cur['completeT'] = time.time()
                H.ev('complete', q=qid, step=repr(H.la.questStep))
            if cur.get('completeReal') is None:
                cur['completeReal'] = time.time()
            qs = H.la.questStep
            stepNow = bool(qs and qs.getStepType())     # job 10b: was `hasStep`, which broke hasStep(H) above
            # job 20: aboard his ship the hand-in clock stands still (the trip to the return NPC is a sail)
            now = time.time()
            if sailing.onShip(H):
                if cur.get('shipT') is not None:
                    cur['completeT'] += now - cur['shipT']
                cur['shipT'] = now
            else:
                cur.pop('shipT', None)
            waited = time.time() - cur['completeT']
            if waited > (HANDIN_LIMIT if stepNow else 90):
                H.ev('STALL', what='complete but never finalized', q=qid, hadStep=stepNow, lastAct=cur['lastAct'])
                stalls.append((qid, 'complete but never finalized'))
                H.snap('stall-complete')
                skipQ(H, qid, 'complete but never finalized')
                cur['completeT'] = time.time()
                yield ('upto', changed(H), 3, 'after skip of a stuck hand-in')
                continue
            # STORY8 11-20: the 10 s 'let the game finish' wait runs on the real clock. On the frozen sailing clock
            # (job 20) a quest finished at sea never got past it: 11 min aboard with 6/6 warrants, never sailing home.
            real = time.time() - cur['completeReal']
            if real < 10 or not stepNow:
                if real >= 10 and time.time() - cur['st'].get('trT', 0) > 10:
                    cur['st']['trT'] = time.time()
                    track(H, qid)
                yield ('upto', changed(H), 3, 'hand-in')
                continue
        lim = SHIP_LIMIT if type(q.questDNA.getTasks()[0]).__name__ in s_shipquest.SHIP_TYPES + s_shipquest.DOCK_TYPES else LIMIT
        if not done and time.time() - cur['t0'] > lim:
            H.ev('STALL', what='no progress in %ds' % lim, q=qid, lastAct=cur['lastAct'])
            stalls.append((qid, 'no progress: %s' % cur['lastAct']))
            H.snap('stall')
            skipQ(H, qid, 'no progress: %s' % cur['lastAct'])
            cur['t0'] = time.time()
            yield ('upto', changed(H), 5, 'after skip of a stalled quest')
            continue
        rep = repeatGrind(q) if not done and not player() else None
        if rep:
            if qid in FORCED:
                # job 29: one skip only. Still shown as not done 15 s after it: the server has it (the client was
                # never told), so leave it and go on to the next held quest (its choice siblings) instead of looping
                if time.time() - FORCED[qid] > 15:
                    if not cur['st'].get('forcedEv'):
                        cur['st']['forcedEv'] = True
                        sibs = [x.getQuestId() for x in mainQuests(H) if x.getQuestId() != qid]
                        H.ev('SKIP-NOT-SHOWN', q=qid, type=rep, siblings=sibs, ts=[x for x in H.quests() if x['id'] == qid],
                             why='skipQuest answered but the client still shows the quest not done: '
                                 'QuestManagerAI.py:1114-1115 force-completes without sendTaskStates; going on to '
                                 'the next held quest')
                    yield ('upto', changed(H), 3, 'forced quest left for the next one')
                    continue
            else:
                p = proven()[rep]
                H.ev('SKIP', q=qid, type=rep, why='repeat of %s, played for real in %s (%s)' % (rep, p.get('tag'), p.get('q')))
                if qid not in [s[0] for s in skips]:
                    skips.append((qid, 'repeat %s' % rep))
                FORCED[qid] = time.time()
                H.mw('skipQuest %s' % qid)
            yield ('upto', changed(H), 3, 'after repeat skip')
            continue
        try:
            a = act(H, q, cur['st'])
        except Exception:
            import traceback
            a = 'act-error ' + traceback.format_exc()[-400:]
        if isinstance(a, tuple) and a[0] in ('shipfight', 'dock'):
            # a ship quest: sink matching ships at sea, or drop anchor at the task's port (s_shipquest)
            H.ev('act', q=qid, a=' '.join(str(x) for x in a), la=H.P(H.la), area=H.area())
            cur['lastAct'] = a[0]
            p0 = s_shipquest.prog(H, qid)
            try:
                if a[0] == 'shipfight':
                    secs = max(60.0, min(SHIP_SECS, t_end - time.time()))
                    hunter = shipHunter(H)
                    r = yield from hunter(H, qid, q.questDNA.getTasks()[0], secs)
                else:
                    r = yield from s_shipquest.dock(H, a[1], qid)
            except Exception:
                import traceback
                r = 'error'
                H.ev('ship-quest-error', q=qid, tb=traceback.format_exc()[-600:])
                for k in ('a', 'd'):
                    messenger.send(k + '-up')
            p1 = s_shipquest.prog(H, qid)
            if p1 != p0:
                cur['t0'] = time.time()
            H.ev('SHIP-STEP', q=qid, a=a[0], r=r, before=p0, after=p1, gs=H.la.getGameState(), area=H.area())
            # DOLL2 11-20: aboard a ship with no wheel, 'launch-failed' came back every 21 s for 18 min. Three in a row
            # with no progress end the run with a STALL and a picture instead of holding the game slot
            cur['launchFails'] = cur.get('launchFails', 0) + 1 if r == 'launch-failed' and p1 == p0 else 0
            if cur['launchFails'] >= 3:
                H.ev('STALL', what='the ship launch failed 3 times in a row (the SAIL-FAIL lines say why)', q=qid)
                stalls.append((qid, 'launch failed 3 times'))
                H.snap('stall')
                if CHUNK:
                    score1 = chunkScore(H)
                    H.ev('chunk-end', score0=score0, score=score1, quests=[d for d in H.quests() if d['id'] in ORDER])
                    if score1 > score0:
                        passEv('chunk progress %s -> %s' % (score0, score1))
                break
            last = getattr(sys.modules.get('s_shipfight'), 'LAST', None) or {}
            lv = last.get('matchLevels') if last.get('q') == qid else None
            rare = rareShip(r, p0, p1, qid, lv, H.la.getLevel(), fair=bool(last.get('picked')) if lv is not None else False)
            if rare:
                why = type(q.questDNA.getTasks()[0]).__name__
                H.ev('SHIP-RARE', q=qid, kind=rare, matchLevels=lv, myLevel=H.la.getLevel(),
                     why='no ship the task counts seen in a full search (SHIP-NO-TARGET lists what was)' if rare == 'rare'
                     else 'every ship the task counts that was seen is more than %d levels above the pirate' % WEAK_MARGIN)
                H.ev('SKIP', q=qid, type=why, why='ship-%s: %s' % (rare, 'none of its ships found at sea' if rare == 'rare'
                                                                    else 'its ships are too strong (lv %s)' % lv))
                skips.append((qid, '%s ship-%s' % (why, rare)))
                H.snap('ship-rare')
                skipQ(H, qid, 'ship-%s' % rare)
                track(H, qid)
                yield ('upto', changed(H), 5, 'after ship-rare skip')
                continue
            if not sailing.onShip(H) and H.la.getGameState() != 'LandRoam':
                # our ship went down (or a failed launch): wait to be back on land before the next try
                yield ('until', lambda: landedOrSwim(H), 120, 'back on land')
            track(H, qid)
            yield ('upto', changed(H), 3, 'after ship step')
            continue
        if isinstance(a, tuple) and a[0] == 'guards':
            # a land kill quest: find, walk to and defeat the task's enemies (s_guards.hunt -> s_fighter.Fighter)
            H.ev('act', q=qid, a='guards', la=H.P(H.la), area=H.area())
            cur['lastAct'] = 'guards'
            p0 = s_guards.progress(H, qid)
            try:
                r = yield from s_guards.hunt(H, qid, q.questDNA.getTasks()[0], max(60.0, min(s_guards.SECS, t_end - time.time())))
            except Exception:
                import traceback
                r = 'error'
                H.ev('guards-error', q=qid, tb=traceback.format_exc()[-600:])
            if s_guards.progress(H, qid) != p0:
                cur['t0'] = time.time()
            track(H, qid)
            yield ('upto', changed(H), 3, 'after guards step (%s)' % r)
            continue
        if isinstance(a, tuple) and a[0] == 'earn':
            # job 23b: too little gold for a paid step: fight for it (s_earn.earn), GOLD-GRANT only after EARN_SECS
            H.ev('act', q=qid, a='earn gold to %s' % a[1], la=H.P(H.la), area=H.area())
            cur['lastAct'] = 'earn'
            e0 = time.time()
            try:
                r = yield from s_earn.earn(H, q, cur['st'])
            except Exception:
                import traceback
                r = 'error'
                H.ev('earn-error', q=qid, tb=traceback.format_exc()[-600:])
            cur['t0'] += time.time() - e0        # earning is not the quest stalling
            yield ('upto', changed(H), 3, 'after earn (%s)' % r)
            continue
        if isinstance(a, tuple) and a[0] == 'deploy':
            H.ev('act', q=qid, a='deploy at %s' % a[1], la=H.P(H.la), area=H.area())
            cur['lastAct'] = 'deploy'
            ship = yield from sailing.launch(H, a[1], False)
            H.ev('DEPLOY', q=qid, ship=getattr(ship, 'doId', None), gs=H.la.getGameState(), hist=H.hist()[-3:])
            cur['t0'] = time.time()        # the launch is progress
            yield ('upto', changed(H), 4, 'after deploy')
            continue
        if isinstance(a, tuple) and a[0] in ('cards', 'boss'):
            # a card task at the table we stand by (s_cards.play), or the Black Pearl boss battle (s_cards.boss)
            H.ev('act', q=qid, a=' '.join(str(x) for x in a), la=H.P(H.la), area=H.area())
            cur['lastAct'] = a[0]
            p0 = s_cards.prog(H, qid)
            try:
                if a[0] == 'cards':
                    r = yield from s_cards.play(H, a[1], qid, a[2])
                else:
                    r = yield from s_cards.boss(H, qid)
            except Exception:
                import traceback
                r = 'give-up error'
                H.ev('cards-error', q=qid, tb=traceback.format_exc()[-600:])
            p1 = s_cards.prog(H, qid)
            if p1 != p0:
                cur['t0'] = time.time()
            H.ev('CARDS-STEP', q=qid, a=a[0], r=r, before=p0, after=p1, gs=H.la.getGameState(), area=H.area())
            if r == 'broke':
                # job 33: lost to the reserve mid-sit: act() earns again before the next sit, BROKE_MAX times
                cur['st']['broke'] = cur['st'].get('broke', 0) + 1
                if cur['st']['broke'] > s_cards.BROKE_MAX:
                    r = 'give-up broke %d times' % cur['st']['broke']
            if isinstance(r, str) and r.startswith('give-up') and p1 is not None and not p1[2]:
                why = type(q.questDNA.getTasks()[0]).__name__
                H.ev('SKIP', q=qid, type=why, why='%s: %s' % (a[0], r))
                skips.append((qid, '%s %s' % (why, r)))
                skipQ(H, qid, '%s: %s' % (a[0], r))
            if H.la.getGameState() != 'LandRoam':
                yield ('until', lambda: H.la.getGameState() == 'LandRoam', 60, 'back to roaming')
            track(H, qid)
            yield ('upto', changed(H), 3, 'after cards step')
            continue
        if isinstance(a, tuple) and a[0] == 'sail':
            H.ev('act', q=qid, a='sail %s' % a[1], la=H.P(H.la), area=H.area(), step=repr(H.la.questStep))
            cur['lastAct'] = 'sail %s' % a[1]
            sailT0 = time.time()
            if os.environ.get('STORY_TP') and not player():
                H.mw('areaTeleport %s' % a[1])
                yield ('until', lambda: sailing.hereUid(H) == a[1] and H.la.getGameState() == 'LandRoam', 90, 'tp')
            else:
                r = None
                # 11-21 DOLL16: a sail that ends in ('port', ...) (hull low) leaves this loop on its first try, so the
                # fallback below never came: three sails to Padres each sunk on the way back to port. Failed sails
                # to an island are counted across act() calls; after one, the next try is the teleport.
                fails = H.__dict__.setdefault('sailFails', {})
                for tries in range(3):
                    if (tries or fails.get(a[1], 0)) and not jailed(H) and H.area() is not None and \
                            (not player() or mapOk(H, a[1])):
                        # 11-21 DOLL15: a level-3 sloop could not get near Padres Del Fuego past level 29-44 warships
                        # (avoid / flee back and forth for 5 min, then sunk). This run tests the quests, not the
                        # sailing: after one failed sail the second try is a logged teleport to the quest's island.
                        H.ev('SAIL-TP-FALLBACK', to=a[1], q=qid, tries=tries, last=repr(r), area=H.area())
                        mapHop(H, a[1], 'sail-fallback')
                        yield ('until', lambda: sailing.hereUid(H) == a[1] and H.la.getGameState() == 'LandRoam', 90,
                               'tp fallback')
                        H.sailResult = sailing.hereUid(H) == a[1]
                        r = 'sailed' if H.sailResult else 'failed'
                        break
                    r = yield from sailGuarded(H, a[1], qid)
                    if r == 'sailed' or isinstance(r, tuple):
                        break
                    # back on land somewhere (sunk / failed launch): wait for LandRoam and try again
                    yield ('until', lambda: landedOrSwim(H), 120, 'back on land')
                    _t = time.time()
                    yield ('upto', lambda: settled(H, _t, 1.5), 5, 'ashore before the next sail try')
                    if jailed(H) or H.area() is None:
                        H.ev('SAIL-TO-JAIL', to=a[1], q=qid, area=H.area(), cell=getattr(H.la, 'jailCellIndex', None))
                        r = 'jail'
                        break
                if r == 'sailed' or (isinstance(r, tuple) and r[0] == 'retarget'):
                    fails.pop(a[1], None)
                elif r != 'jail':
                    fails[a[1]] = fails.get(a[1], 0) + 1
                if r == 'jail':
                    pass        # jail() walks him out on the next ticks, then act() sails again
                elif isinstance(r, tuple) and r[0] == 'port':
                    # hull low: land at the nearest port; the next sail's launch() pays the shipwright first
                    r2 = yield from sailGuarded(H, r[1], 'port for repair (%s)' % qid)
                    if r2 != 'sailed' and not sailing.onShip(H):
                        yield ('until', lambda: landedOrSwim(H), 120, 'back on land')
                elif isinstance(r, tuple):
                    pass        # the quest step moved: act() reads the new one next tick
                elif not H.sailResult:
                    H.ev('STALL', what='could not sail to %s' % a[1], q=qid)
                    stalls.append((qid, 'could not sail to %s' % a[1]))
            cur['t0'] = time.time()        # the sail is progress
            if cur['completeT'] is not None:
                # job 20: a done quest's hand-in clock does not run while he sails to the return NPC
                secs = time.time() - sailT0
                cur['completeT'] += secs
                cur.pop('shipT', None)
                H.ev('HANDIN-PAUSE', q=qid, secs=round(secs, 1), why='sail %s' % a[1],
                     waited=round(time.time() - cur['completeT'], 1), limit=HANDIN_LIMIT)
            track(H, qid)
            yield ('upto', changed(H), 4, 'after sail')
            continue
        if isinstance(a, tuple) and a[0] == 'skip':
            # job 33: a quest this pirate cannot play here (too weak for its enemies, a client without 0289)
            why = type(q.questDNA.getTasks()[0]).__name__
            H.ev(a[1], q=qid, why=a[2], **a[3])
            H.ev('SKIP', q=qid, type=why, why=a[2])
            skips.append((qid, '%s %s' % (why, a[2])))
            skipQ(H, qid, a[2])
            yield ('upto', changed(H), 5, 'after %s skip' % a[1])
            continue
        if a != cur['lastAct']:
            H.ev('act', q=qid, a=a, la=H.P(H.la), area=H.area(), step=repr(H.la.questStep))
            cur['lastAct'] = a
        if a == 'skip-type':
            why = type(q.questDNA.getTasks()[0]).__name__
            H.ev('SKIP', q=qid, type=why, why='task type off for this run (s_cards env): %s' % why)
            skips.append((qid, why))
            skipQ(H, qid, 'type off: %s' % why)
            yield ('upto', changed(H), 5, 'after type skip')
            continue
        g = cur['st'].pop('go', None)
        if g is not None:
            obj, arrive, face, ref, tag = g
            stepKey = repr(H.la.questStep)
            if cur['st'].get('gfStep') != stepKey:
                cur['st']['gfStep'] = stepKey      # job 20: the go-failed count is per quest step
                cur['st']['goFails'] = 0
            ok = yield from go(H, obj, arrive, face, ref, tag)
            if ok:
                cur['st']['goFails'] = 0
            else:
                cur['st']['goFails'] = cur['st'].get('goFails', 0) + 1
                H.ev('go-failed', q=qid, tag=tag, fails=cur['st']['goFails'], la=H.P(H.la))
                if cur['st']['goFails'] >= GOFAIL_MAX:
                    # job 20 (NEWP13-NP2: 40 tries in 12 min at Bonita's door): stop, say what blocks him, skip
                    try:
                        p, lp = _render_pt(H, obj, ref), H.la.getPos(H.render)
                        gp, hd, dz = [round(v, 1) for v in p], round(hdist(H, obj, ref), 2), round(p[2] - lp[2], 2)
                    except Exception:
                        gp = hd = dz = None
                    H.ev('GO-BLOCKED', q=qid, tag=tag, fails=cur['st']['goFails'], la=H.P(H.la), goal=gp, hd=hd,
                         dz=dz, arrive=arrive, step=stepKey, lastAct=cur['lastAct'],
                         blocker=('step or lip (goal %.1f ft higher)' % dz) if dz is not None and dz > 1.0 else
                                 ('drop (goal %.1f ft lower)' % -dz) if dz is not None and dz < -1.0 else 'wall or prop')
                    stalls.append((qid, 'go blocked: %s' % tag))
                    H.ev('STALL', what='go blocked: %s' % tag, q=qid, lastAct=cur['lastAct'])
                    H.snap('stall-go-blocked')
                    skipQ(H, qid, 'go blocked: %s' % tag)
                    cur['st']['goFails'] = 0
                    yield ('upto', changed(H), 3, 'after skip of a blocked walk')
                    continue
                yield 2
            continue
        if a.startswith('no-step') or a.startswith('no-enemy') or a == 'questnode-there':
            # nothing to follow: re-request the tracker every 10s
            if time.time() - cur['st'].get('trT', 0) > 10:
                cur['st']['trT'] = time.time()
                track(H, qid)
        yield ('upto', changed(H), 1.5 if a.startswith('fight') else 3, 'main loop')
    else:
        if CHUNK:
            score1 = chunkScore(H)
            H.ev('chunk-end', score0=score0, score=score1, quests=[d for d in H.quests() if d['id'] in ORDER])
            if score1 > score0:
                passEv('chunk progress %s -> %s' % (score0, score1))
    H.ev('STORY-SUMMARY', seen=seen, n=len(seen), stalls=stalls, skips=skips, qids=H.qids(), hist=H.hist())
