"""LANDFIGHT (pir-bot, 11-17, job 3; job 6 = fight like a competent player): kill one land enemy and pick up its loot.

On Port Royal (LANDFIGHT_FROM, any island uid; LANDFIGHT_AREA = a jungle / cave area uid of that island, reached
through its tunnels with s_story.goto). Job 6 (LAND1 was knocked out in the strong camps, never having "seen" one
enemy): the fighting is s_fighter.Fighter (pick a weak lone enemy for his level, draw the player's way, left-click
combo + best ready skill, tonic under 45 % health, back off under 30 % and come back at 75 %). Seeking is careful:
walk to the spawn nodes weakest camp first (s_fighter.spawnPick), look every beat while walking (stop and fight as
soon as a weak enemy is in view), and walk on (FOE-DANGER) when only strong ones are near. If an enemy hits him while
he seeks, he fights back when it is weak, else backs off (HIT-WHILE-SEEKING).

The loot: this game has no loot chest for land enemies. On a kill the server puts the gold straight in the pocket
(BattleManagerAI.rewardAttacker: EnemyGlobals.getGoldDrop, then the weapon reputation; 1 kill in 5 also gives a
card), and the client shows the gold popup (LocalPirate.setMoney -> messageStack.showLoot). So "picked up" means the
pocket gold went up after the kill and the popup was shown; this step hooks showLoot to see it.

Lines: LANDFIGHT-START, STAGE step=landfight what=at-island / in-area / foe-seen / first-swing / foe-killed / loot,
SPAWN-PICK, FOE-PICK (+ FOE-SKIP counts), FOE-DANGER, the Fighter's WEAPON-DRAWN / ATTACK / SKILL / TONIC /
RETREAT / REST / RETURN / ATTACK-FALLBACK, LOOT-SHOWN, LANDFIGHT-END (gold, cutlass rep, tonics, retreats), PASS/FAIL.
PASS = one foe killed (hp 0 or it left the client after our hits) AND the pocket gold rose (or the popup showed).
env: LANDFIGHT_FROM (Port Royal), LANDFIGHT_AREA (the island itself), LANDFIGHT_SECS (600), LANDFIGHT_MAXLVL (99:
never above this level), LANDFIGHT_KILLS (1), LANDFIGHT_OVER (1: enemies up to his level + this)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__', '.'))))
import s_lanes    # noqa: E402
import s_story    # noqa: E402
import s_fighter  # noqa: E402

FROM = os.environ.get('LANDFIGHT_FROM', s_lanes.PR)
AREA = os.environ.get('LANDFIGHT_AREA', '') or FROM
SECS = float(os.environ.get('LANDFIGHT_SECS', '600'))
MAXLVL = int(os.environ.get('LANDFIGHT_MAXLVL', '99'))
KILLS = int(os.environ.get('LANDFIGHT_KILLS', '1'))
OVER = int(os.environ.get('LANDFIGHT_OVER', str(s_fighter.LVL_OVER)))
VIEW = s_fighter.VIEW
LOOT_WAIT = 10         # s after the kill for the gold to land
BEAT = 0.25


def spawnNodes(qs, area):
    """Pure: the (x, y, z, name) of every enemy spawn node in that area of quest_spots.json."""
    return [tuple(o[1:4]) + (o[5],) for o in qs.get('objs', {}).values() if o[0] == area and o[4] == 'Spawn Node']


def cutlassRep(H):
    from pirates.uberdog.UberDogGlobals import InventoryType
    inv = H.la.getInventory()
    return inv.getAccumulator(InventoryType.CutlassRep) if inv else 0


def pick(H, lvl):
    """-> (foe object or None, rows). Logs FOE-PICK with why the others were left."""
    rows = s_fighter.foeRows(H)
    ids, skip = s_fighter.pickFoe(rows, lvl, VIEW, MAXLVL, OVER)
    if not ids:
        return None, rows
    o = H.cr.doId2do.get(ids[0])
    if o is None:
        return None, rows
    why = {}
    for w in skip.values():
        k = w.split(' ')[0]
        why[k] = why.get(k, 0) + 1
    H.ev('FOE-PICK', foe=o.doId, kind=str(getattr(o, 'avatarType', None)), cls=type(o).__name__,
         lvl=getattr(o, 'level', None), myLvl=lvl, hp=getattr(o, 'hp', None), maxHp=getattr(o, 'maxHp', None),
         d=round(s_story.hdist(H, o), 1), candidates=len(ids), seen=len(rows), skipped=why)
    return o, rows


def attacker(H, rows, lvl):
    """The nearest live enemy within 12 ft (someone hitting him while he walks), as (obj, weak?) or (None, None)."""
    near = sorted((r for r in rows if (r[2] or 0) > 0 and r[1] <= 12.0), key=lambda r: r[1])
    if not near:
        return None, None
    o = H.cr.doId2do.get(near[0][0])
    return o, (near[0][3] or 0) <= min(MAXLVL, lvl + OVER)


def run(H):
    la = H.la
    g0, r0 = s_lanes.gold(H), cutlassRep(H)
    H.ev('LANDFIGHT-START', frm=FROM, area=AREA, gold=g0, rep=r0, here=H.area(), hp=getattr(la, 'hp', None),
         maxHp=getattr(la, 'maxHp', None), lvl=s_fighter.myLevel(H), over=OVER)
    if not (yield from s_lanes.onIsland(H, 'landfight', FROM)):
        H.ev('FAIL', why='could not get to %s' % FROM, area=H.area()); return
    s_lanes.stage(H, 'landfight', 'at-island', island=FROM)
    if AREA != FROM:
        r = yield from s_lanes.walkTo(H, 'landfight', lambda st: s_story.goto(H, st, AREA, tag='to-area'), 300, AREA)
        if r is not True:
            H.ev('FAIL', why='could not walk to area %s' % AREA, area=H.area()); return
    s_lanes.stage(H, 'landfight', 'in-area', uid=s_story.hereArea(H))

    # the gold popup: LocalPirate.setMoney -> guiMgr.messageStack.showLoot([], gold=gain)
    loot = []
    ms = la.guiMgr.messageStack
    origLoot = ms.showLoot

    def showLoot(items, gold=0, *a, **k):
        loot.append(gold)
        H.ev('LOOT-SHOWN', gold=gold, items=len(items or []), pocket=s_lanes.gold(H))
        return origLoot(items, gold, *a, **k)
    ms.showLoot = showLoot

    nodes = spawnNodes(s_story.questSpots(), s_story.hereArea(H))
    tried = set()
    kills, gKill, seenFoe, fighter, node, dangerT = 0, None, False, None, None, 0.0
    stats = {'tonics': 0, 'retreats': 0, 'skills': 0, 'hits': 0, 'fallback': 0}
    t0 = time.time()
    try:
        while time.time() - t0 < SECS and kills < KILLS:
            if (getattr(la, 'hp', 1) or 0) <= 0 or la.getGameState() in ('Death', 'Dying'):
                H.ev('FAIL', why='the pirate was knocked out', foe=fighter and fighter.foe.doId,
                     hits=stats['hits'] + (fighter.hits if fighter else 0), tonics=stats['tonics'],
                     retreats=stats['retreats'], area=H.area())
                return
            lvl = s_fighter.myLevel(H)
            if fighter is not None:
                a = fighter.step()
                stats['tonics'] += a == 'tonic'
                stats['retreats'] += a == 'retreat'
                if a == 'fight' and fighter.hits == 1 and not fighter.__dict__.get('_firstLogged'):
                    fighter._firstLogged = True
                    s_lanes.stage(H, 'landfight', 'first-swing', foe=fighter.foe.doId, hp=getattr(fighter.foe, 'hp', None))
                if a in ('kill', 'lost', 'stuck'):
                    foe = fighter.foe
                    stats['hits'] += fighter.hits
                    stats['skills'] += fighter.skills
                    stats['fallback'] += fighter.refused > s_fighter.FALLBACK_AFTER
                    fighter.close()
                    fighter = None
                    if a == 'kill':
                        kills += 1
                        gKill = s_lanes.gold(H)
                        s_lanes.stage(H, 'landfight', 'foe-killed', foe=foe.doId, n=kills,
                                      how='hp 0' if foe.doId in H.cr.doId2do else 'left the client')
                    elif a == 'stuck':
                        H.ev('FOE-STUCK', foe=foe.doId, la=H.P(la))
                    else:
                        H.ev('FOE-LOST', foe=foe.doId, why='gone before our first hit')
                yield BEAT
                continue
            # seeking: look first, every beat (also while walking to a spawn node)
            foe, rows = pick(H, lvl)
            if foe is None:
                hitter, weak = attacker(H, rows, lvl)
                if hitter is not None and (getattr(la, 'hp', 1) or 0) < (getattr(la, 'maxHp', 0) or 0):
                    H.ev('HIT-WHILE-SEEKING', foe=hitter.doId, lvl=getattr(hitter, 'level', None), myLvl=lvl,
                         weak=weak, hp=getattr(la, 'hp', None))
                    if weak:
                        foe = hitter
                    else:
                        me, fp = la.getPos(H.render), hitter.getPos(H.render)
                        to = s_fighter.retreatPoint((me[0], me[1], me[2]), (fp[0], fp[1], fp[2]), None, 60.0)
                        stats['retreats'] += 1
                        H.ev('RETREAT', foe=hitter.doId, why='a strong enemy hit him while seeking',
                             to=[round(v, 1) for v in to])
                        yield from H.walk_to(to, arrive=4.0, timeout=25, tag='flee')
                        node = None
                        continue
            if foe is not None:
                H.walk_cancel()
                node = None
                if not seenFoe:
                    s_lanes.stage(H, 'landfight', 'foe-seen', foe=foe.doId, kind=str(getattr(foe, 'avatarType', None)))
                    seenFoe = True
                me = la.getPos(H.render)
                fighter = s_fighter.Fighter(H, foe, (me[0], me[1], me[2]))
                continue
            bad = s_fighter.danger(rows, lvl, s_fighter.DANGER_R, OVER)
            if bad and node is not None and time.time() - dangerT > 5:
                dangerT = time.time()
                H.ev('FOE-DANGER', near=len(bad), myLvl=lvl, node=node[3], why='only enemies above his level here')
                tried.add(tuple(node[:3]))
                node = None
            if node is None:
                org = s_story.areaObj(H, s_story.hereArea(H))
                me = la.getPos(org) if org is not None else la.getPos(H.render)
                node = s_fighter.spawnPick(nodes, (me[0], me[1]), tried, lvl)
                if node is None:
                    if not nodes:
                        H.ev('FAIL', why='no enemy in view and no spawn node in this area'); return
                    H.ev('SPAWN-ROUND-DONE', nodes=len(nodes), allowed=sum(
                        1 for n in nodes if s_fighter.tier(n[3]) <= s_fighter.maxTier(lvl)))
                    tried.clear()
                    yield 5
                    continue
                H.ev('SPAWN-PICK', node=node[3], tier=s_fighter.tier(node[3]), maxTier=s_fighter.maxTier(lvl),
                     myLvl=lvl, spot=[round(v, 1) for v in node[:3]],
                     d=round(((node[0] - me[0]) ** 2 + (node[1] - me[1]) ** 2) ** 0.5, 1))
                node = tuple(node) + (org,)          # (x, y, z, name, area frame)
            r = H.walk_poll(node[:3], ref=node[4], arrive=8.0, face=False, tag='to-spawn')
            if r is True or r is None:
                if r is None:
                    H.ev('SPAWN-UNREACHABLE', node=node[3], spot=[round(v, 1) for v in node[:3]])
                tried.add(tuple(node[:3]))
                node = None
                yield 1.0 if r is True else BEAT      # stand a second at the camp: enemies spawn and come in view
                continue
            yield BEAT
        if fighter is not None:
            stats['hits'] += fighter.hits
            stats['skills'] += fighter.skills
            fighter.close()
            fighter = None
        if kills:
            yield ('until', lambda: s_lanes.gold(H) > g0 or loot, LOOT_WAIT, 'loot gold')
    finally:
        ms.showLoot = origLoot
        if fighter is not None:
            fighter.close()
        H.walk_cancel()
    g1, r1 = s_lanes.gold(H), cutlassRep(H)
    if kills and (g1 > g0 or loot):
        s_lanes.stage(H, 'landfight', 'loot', gold=g1 - g0, popup=sum(loot))
    H.ev('LANDFIGHT-END', kills=kills, goldBefore=g0, goldAfter=g1, goldAtKill=gKill, repBefore=r0, repAfter=r1,
         popups=loot, secs=round(time.time() - t0), hp=getattr(la, 'hp', None), **stats)
    if not kills:
        H.ev('FAIL', why='killed no enemy in %d s' % SECS, seen=seenFoe); return
    if not (g1 > g0 or loot):
        H.ev('FAIL', why='killed %d but no gold came (rep %d -> %d)' % (kills, r0, r1)); return
    H.ev('PASS', what='killed %d land enemy and picked up %d gold' % (kills, g1 - g0), rep=r1 - r0, **stats)
