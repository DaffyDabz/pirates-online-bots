"""GUARDS (pir-quests, 11-17): defeat the enemies a land kill quest asks for, the way a player does.

Why (SAIL6, 11-17): after the sea part of c3r1 the server gave c3r1.2defeatNavyGuards (DefeatTaskDNA num=4,
enemyType=Navy, no location). Its quest step was stype 1 on a Cadet (the server ranks any battle NPC as an NPC step
since patch 0129), so s_story.act() never took the walk-to-enemy branch (it wants stype 2) nor toEnemies (it wants a
location or no step), fell through to the talk branch and stood "talk-wait" by the Cadet for the 420 s limit.
The server's marker was right (the Cadet's posH maps to where the Cadet stood; no server change needed).

What this does, one event line per decision:
  GUARDS-START  the quest, enemy type, kills needed / done, his level, the step object
  FOE-PICK      the enemy picked: a live one of the task's type (avatarType.isA(enemyType), level >= task level),
                the lowest level and nearest that is not in a crowd (s_fighter.pickFoe, up to his level + GUARDS_OVER);
                when every one in view is above that, the weakest anyway (why=hard): the quest needs them
  GUARDS-WALK   a foe further than ROUTE_R ft: walk round the buildings to it first (s_story.go), then fight
  (fight)       s_fighter.Fighter: draw, click combo + best skill, tonic under 45 %, back off under 30 %, return at 75 %
  GUARDS-KILL   one down (the Fighter's 'kill'), with the quest's progress
  GUARDS-SPAWN  none of the task's type known to this client: walk to the next spawn node in this area that can
                make that type (s_story.enemySpawns), else any spawn node in this area
  GUARDS-SKIP   a foe the walk could not reach: left alone for SKIP_SECS
  GUARDS-END    why it stopped: done (quest complete or gone), ko (knocked out: s_story's jail step takes over),
                time (secs used up), state (not roaming), no-spawn (nothing to fight and nowhere to look)
Hooked into s_story: act() returns ('guards',) when wants() says so; run() runs hunt() like the card / ship steps.
env: STORY_GUARDS=0 turns it off (the old fight branch), GUARDS_SECS (one hunt, 300), GUARDS_OVER (3),
GUARDS_VIEW (ft, 600)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__', '.'))))
import s_fighter  # noqa: E402

ON = os.environ.get('STORY_GUARDS', '1') not in ('0', '', 'off')
SECS = float(os.environ.get('GUARDS_SECS', '300'))
OVER = int(os.environ.get('GUARDS_OVER', '3'))
VIEW = float(os.environ.get('GUARDS_VIEW', '600'))
ROUTE_R = 60.0      # ft: a foe further than this is walked to round the buildings first
SKIP_SECS = 30.0    # s: a foe the walk could not reach is left alone this long
BEAT = 0.25
OFF_STATE = 20.0    # s out of LandRoam / Battle (a scene, a door) before the hunt hands back to s_story


# ------------------------------------------------------------------------------------------------- pure (offline)
def choose(rows, lvl, stepId=None, over=OVER, view=VIEW):
    """Pure: rows = (doId, dist, hp, level, (x, y)) of live enemies of the task's type. -> (doId, why) or (None, why).
    The weakest lone one in view up to his level + over ('pick'); else the weakest in view anyway ('hard': the quest
    needs them); else the quest step's own enemy wherever it is ('step'); else None."""
    alive = [r for r in rows if (r[2] or 0) > 0]
    ids, _ = s_fighter.pickFoe(alive, lvl, view, 99, over)
    if ids:
        return ids[0], 'pick'
    inview = sorted((r for r in alive if r[1] <= view), key=lambda r: (r[3] or 0, r[1]))
    if inview:
        return inview[0][0], 'hard'
    if stepId is not None and any(r[0] == stepId for r in alive):
        return stepId, 'step'
    if alive:
        return min(alive, key=lambda r: r[1])[0], 'nearest'
    return None, 'none'


def progressOf(states):
    """Pure: the quest's task states [(progress, goal), ...] -> (done, need) of the first task, or None."""
    if not states:
        return None
    p, g = states[0][0], states[0][1]
    return (p or 0, g or 0)


def isTarget(o, etype, minLvl=0):
    """Pure-ish: an enemy object the task counts: its avatarType isA the task's enemy type, level >= the task's."""
    at = getattr(o, 'avatarType', None)
    if at is None or etype is None:
        return False
    try:
        if not at.isA(etype):
            return False
        if minLvl:
            lv = o.getLevel() if hasattr(o, 'getLevel') else getattr(o, 'level', 0)
            if (lv or 0) < minLvl:
                return False
        return True
    except Exception:
        return False


# ------------------------------------------------------------------------------------------------ live (in the game)
def rowsFor(H, task):
    """s_fighter.foeRows filtered to the enemies this task counts."""
    etype, lvl = getattr(task, 'enemyType', None), max(0, getattr(task, 'level', 0) or 0)
    d2d = H.cr.doId2do
    return [r for r in s_fighter.foeRows(H) if isTarget(d2d.get(r[0]), etype, lvl)]


def progress(H, qid):
    """(done, need) of quest qid's first task; None once the quest is gone (handed in / skipped)."""
    for q in H.la.getQuests():
        if q.getQuestId() == qid:
            try:
                return progressOf([(getattr(s, 'progress', None), getattr(s, 'goal', None)) for s in q.getTaskStates()])
            except Exception:
                return None
    return None


def wants(H, q, task, stype, sobj, inLoc=True):
    """True when this quest's next move is fighting its enemies here: a kill task not yet complete, standing in its
    location (or it has none), and the step points at an enemy or an enemy of the task's type is known to the client.
    Never True for a talk step to a townsperson (s_fighter.isEnemy says no to Townfolk)."""
    if not ON or q.isComplete() or getattr(task, 'enemyType', None) is None or not inLoc:
        return False
    if sobj is not None and s_fighter.isEnemy(H, sobj) and isTarget(sobj, task.enemyType):
        return True
    return bool(rowsFor(H, task))


def _spawnNodes(H, task, story):
    """(x, y, z, name) spawn nodes in this area that can make the task's enemy (all spawn nodes here if none can),
    in the area's frame (as quest_spots.json has them)."""
    objs = story.questSpots()['objs']
    here = story.hereArea(H)
    good = set(story.enemySpawns(task))
    nodes = [tuple(o[1:4]) + (o[5],) for u, o in objs.items() if o[0] == here and u in good]
    if not nodes:
        nodes = [tuple(o[1:4]) + (o[5],) for o in objs.values() if o[0] == here and o[4] == 'Spawn Node']
    return nodes


def _stepId(H):
    qs = H.la.questStep
    try:
        return qs.getStepDoId() if qs else None
    except Exception:
        return None


def _ko(la):
    return (getattr(la, 'hp', 1) or 0) <= 0 or la.getGameState() in ('Death', 'Dying')


def hunt(H, qid, task, secs=SECS, story=None):
    """Generator: fight the task's enemies until the quest is complete (or gone), he is knocked out, or secs pass.
    -> 'done' / 'ko' / 'time' / 'state' / 'no-spawn'."""
    if story is None:
        import s_story as story
    la = H.la
    p0 = progress(H, qid)
    sid = _stepId(H)
    H.ev('GUARDS-START', q=qid, enemy=str(getattr(task, 'enemyType', None)), minLvl=getattr(task, 'level', 0),
         prog=p0, lvl=s_fighter.myLevel(H), hp=getattr(la, 'hp', None), maxHp=getattr(la, 'maxHp', None),
         area=H.area(), step=sid, stepCls=type(H.cr.doId2do.get(sid)).__name__ if sid in H.cr.doId2do else None,
         known=len(rowsFor(H, task)))
    t0, offT = time.time(), None
    fighter, kills, skip, tried, last, why = None, 0, {}, set(), p0, 'time'
    stats = {'hits': 0, 'skills': 0, 'tonics': 0, 'retreats': 0, 'walks': 0, 'spawns': 0}
    try:
        while time.time() - t0 < secs:
            pr = progress(H, qid)
            q = next((x for x in la.getQuests() if x.getQuestId() == qid), None)
            if pr is None or q is None or q.isComplete():
                why = 'done'
                break
            if pr != last:
                H.ev('GUARDS-PROGRESS', q=qid, prog=pr, was=last)
                last = pr
            if _ko(la):
                why = 'ko'
                H.ev('GUARDS-KO', q=qid, foe=fighter and fighter.foe.doId, prog=pr, area=H.area())
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
            lvl = s_fighter.myLevel(H)
            if fighter is not None:
                a = fighter.step()
                stats['tonics'] += a == 'tonic'
                stats['retreats'] += a == 'retreat'
                if a in ('kill', 'lost', 'stuck'):
                    foe = fighter.foe
                    stats['hits'] += fighter.hits
                    stats['skills'] += fighter.skills
                    fighter.close()
                    fighter = None
                    if a == 'kill':
                        kills += 1
                        H.ev('GUARDS-KILL', q=qid, foe=foe.doId, n=kills, prog=progress(H, qid),
                             how='hp 0' if foe.doId in H.cr.doId2do else 'left the client')
                    else:
                        skip[foe.doId] = time.time() + SKIP_SECS
                        H.ev('GUARDS-SKIP', q=qid, foe=foe.doId, why=a, la=H.P(la))
                yield BEAT
                continue
            now = time.time()
            rows = [r for r in rowsFor(H, task) if skip.get(r[0], 0) < now]
            foeId, how = choose(rows, lvl, _stepId(H))
            o = H.cr.doId2do.get(foeId) if foeId is not None else None
            if o is not None:
                d = story.hdist(H, o)
                if d > ROUTE_R:
                    stats['walks'] += 1
                    H.ev('GUARDS-WALK', q=qid, foe=o.doId, how=how, d=round(d, 1), lvl=getattr(o, 'level', None))
                    r = yield from story.go(H, o, 20.0, False, None, 'to-guard')
                    left = story.hdist(H, o) if o.doId in H.cr.doId2do else None
                    if left is not None and left > ROUTE_R and left > d - 5:
                        skip[o.doId] = time.time() + SKIP_SECS
                        H.ev('GUARDS-SKIP', q=qid, foe=o.doId, why='walk got no closer', r=r, left=round(left, 1))
                    continue
                H.walk_cancel()
                H.ev('FOE-PICK', q=qid, foe=o.doId, how=how, kind=str(getattr(o, 'avatarType', None)),
                     cls=type(o).__name__, lvl=getattr(o, 'level', None), myLvl=lvl, hp=getattr(o, 'hp', None),
                     d=round(d, 1), candidates=len(rows))
                me = la.getPos(H.render)
                fighter = s_fighter.Fighter(H, o, (me[0], me[1], me[2]))
                continue
            # none of the task's type known here: look where they spawn
            nodes = _spawnNodes(H, task, story)
            org = story.areaObj(H, story.hereArea(H))
            me = la.getPos(org) if org is not None else la.getPos(H.render)
            node = s_fighter.spawnPick(nodes, (me[0], me[1]), tried, 99)
            if node is None:
                if not nodes:
                    why = 'no-spawn'
                    H.ev('GUARDS-NO-SPAWN', q=qid, area=H.area())
                    break
                tried.clear()
                yield 5
                continue
            stats['spawns'] += 1
            H.ev('GUARDS-SPAWN', q=qid, node=node[3], spot=[round(v, 1) for v in node[:3]],
                 d=round(((node[0] - me[0]) ** 2 + (node[1] - me[1]) ** 2) ** 0.5, 1))
            tried.add(tuple(node[:3]))
            yield from story.go(H, node[:3], 8.0, False, org, 'to-guard-spawn')
            yield 1.0          # stand a second at the camp: enemies spawn and come into interest
    finally:
        if fighter is not None:
            stats['hits'] += fighter.hits
            stats['skills'] += fighter.skills
            fighter.close()
        H.walk_cancel()
    H.ev('GUARDS-END', q=qid, why=why, kills=kills, before=p0, after=progress(H, qid),
         secs=round(time.time() - t0), hp=getattr(la, 'hp', None), **stats)
    return why
