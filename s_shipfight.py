"""SHIPFIGHT (pir-bot, 11-17; pir-ships rework 11-17): fight one enemy ship and sink it, like a player. For the lanes
that need a sea fight.

From Port Royal (SHIPFIGHT_FROM, any island uid): launch our ship at the island's dinghy (sailing.launch, the ship
the pirate owns), sail out at full sail, and fight with s_shipquest.hunt, the same sea fight the story's ship quests
use (patrol a ring round the island, line up a broadside, fire it with its key; ram when the pirate has no broadside
skill). This step stops at the first enemy ship sunk; it does not sail home (the next step, or the story, does that).

What a careful player does on top of hunt() (SMOKE-shipfight 11-17 picked a level-24 Marauder, 2100 hp, and sank):
- picks a fair foe: a ship at most SHIPFIGHT_LEVEL_GAP levels above the pirate, the nearest of those first. With
  none in view: one with SHIPFIGHT_WEAK x our hp or less, lowest hp first. After SHIPFIGHT_PICKY_SECS with neither:
  the lowest-hp ship in view. Others are passed by (hunt's ship-seen says why: 'level 24 > 9 + 3'). It stays on the
  foe it picked while that one stays fair.
- holds the foe on the beam: abeam at SHIPFIGHT_RANGE ft (inside the 2000 ft broadside auto-aim), angling in from
  farther and out when closer (hunt's own aim check still decides each shot).
- breaks off under SHIPFIGHT_BREAK of our max hp, or after losing SHIPFIGHT_LOSS of it in SHIPFIGHT_LOSS_SECS, or
  with a ship over SHIPFIGHT_DANGER_GAP levels above him inside SHIPFIGHT_DANGER_R ft that is closing in (came
  SHIPFIGHT_CLOSE_GAIN ft nearer in SHIPFIGHT_CLOSE_SECS) and hp under SHIPFIGHT_DANGER_HP (pir-bot job 21,
  shipfight12 11-18: a lv 14 Corvette 2448 ft off broke the fight with the Ferret at 424/1000 hp). With the foe under
  SHIPFIGHT_FINISH of its max hp it finishes the kill (FINISH-KILL) unless our hp is under SHIPFIGHT_FINISH_HULL:
  sails to the nearest repair port (SHIPFIGHT_PORTS, HOME-PICK), has the shipwright mend the ship (the one magic word
  is 'gold' when the pirate cannot pay, logged MW-GOLD, as s_shipquest.payRepair does), relaunches there and fights
  on. At most SHIPFIGHT_REPAIRS times.
- stays in starter waters (SMOKE-shipfight6 11-17 chased 'weak' ships 10,000-16,000 ft out among level 18-39 ships
  and sank on the way home): no foe farther than SHIPFIGHT_LEASH ft from the nearest port is picked (0140 keeps
  ships within 9000 ft at level 12 or lower), and hunt's patrol ring is SHIPFIGHT_PATROL_R ft, not 8000.
- keeps after a foe it has hit (pir-bot job 15, shipfight9 11-18: a Ferret shot 1000 -> 255 hp sailed past the leash,
  was dropped without a word and drifted out of sight at 5956 ft): the foe it is on, or the last one it hurt, stays
  allowed up to SHIPFIGHT_STICK_SLACK ft past the leash, so hunt chases it; FOE-DROP says when and why one is let go,
  FOE-REACQUIRE when a hurt one comes back into view.
- one count of sinks: a target that leaves the client's view last seen out of broadside range is FOE-LOST in hunt
  itself (s_shipquest.LOST), so SHIP-HUNT-END sunk and SHIPFIGHT-END sunk agree.
- the wheel lost mid-fight (shipfight9 ended 'left-ship', ship afloat at 1442 hp, LandRoam, no log said why):
  WHEEL-EXIT names who moved the pirate out of ShipPilot (the call stack of gameFSM.request) and the ship's state;
  with the ship afloat and the pirate still aboard it takes the wheel again (RETAKE-WHEEL, hunt's own launch walks to
  the wheel) and fights on, at most SHIPFIGHT_RETAKES times.
- the time limit counts the launch too: a fight ends at SHIPFIGHT_SECS from the start, not that plus the launch.
- fights what is in range (pir-bot job 18, shipfight10 11-18: the first pick was a Ferret 4669 ft off; hunt sailed
  after it for 297 s and never closed in, while three Ferrets inside 2600 ft shot the hull from 2400 to 1196 hp; no
  shot was fired): a foe we have not hurt stays first only while it is within SHIPFIGHT_ENGAGE_R ft, or nothing else
  is; with another foe that close we switch (FOE-DROP why='a foe within ...'). A target farther than that which gains
  us less than SHIPFIGHT_CHASE_GAIN ft in SHIPFIGHT_CHASE_SECS (twice that for one we hurt) is let go (FOE-DROP
  why='not closing in ...') and passed by for SHIPFIGHT_SHUN_SECS. FOE-RANGE every 20 s: the target's distance,
  beam or chase, both hps and the nearest other ship.

Not a quest: hunt() is given a stand-in task that every enemy ship matches and no quest id, so it never stops on a
quest credit. This step watches hunt's own lines and stops it after FOE-SUNK.

Lines: SHIPFIGHT-START, STAGE step=shipfight what=at-island / launched / foe-seen / first-shot / foe-sunk / broke-off /
repaired / stopped, the hunt's own SHIP-HUNT, ship-seen, SHIP-TARGET, BROADSIDE / RAM, FOE-SUNK, OUR-SHIP-SUNK, plus
ship-lv (each ship once: level, hp, ft from the home island, picked or why not), FOE-PICK (how: fair / weak / lowest-hp),
FOE-DROP, FOE-REACQUIRE, FOE-RANGE, FOE-LOST, WHEEL-EXIT, RETAKE-WHEEL, BREAK-OFF (hp, maxHp, foe), REPAIR (hp before / after,
paid), then SHIPFIGHT-END (sunk, lost, shots, onBeam, breaks, retakes, levels seen), PASS / FAIL.
PASS = one FOE-SUNK before our ship sinks and within SHIPFIGHT_SECS (default 900).
Job 23a (11-19, proves patch 0200's ship gold, a Ferret 21-32): after FOE-SUNK it waits SHIPFIGHT_PLUNDER_SECS
(20) s for the plunder, then logs SHIP-GOLD: start (gold at SHIPFIGHT-START), before (gold as the fight that sank it
began, after any repair), after, gain, the sunk foe's level/name, expect (0200's 10*lv+lv*lv, -20% .. +20% and the
faction's +20% at most) and ok. changes = [s after the sink, gold] each time the gold moved. PASS carries gain too.
env: SHIPFIGHT_FROM (default Port Royal), SHIPFIGHT_SECS, SHIPFIGHT_LEVEL_GAP (3), SHIPFIGHT_WEAK (0.5),
SHIPFIGHT_PICKY_SECS (300), SHIPFIGHT_RANGE (1400), SHIPFIGHT_BREAK (0.5), SHIPFIGHT_REPAIRS (2),
SHIPFIGHT_LEASH (8000), SHIPFIGHT_PATROL_R (5500), SHIPFIGHT_PORTS (Port Royal,Tortuga uids), SHIPFIGHT_LOSS (0.2),
SHIPFIGHT_LOSS_SECS (10), SHIPFIGHT_DANGER_R (1500), SHIPFIGHT_DANGER_GAP (8), SHIPFIGHT_DANGER_HP (0.75),
SHIPFIGHT_CLOSE_SECS (20), SHIPFIGHT_CLOSE_GAIN (150), SHIPFIGHT_FINISH (0.5), SHIPFIGHT_FINISH_HULL (0.5),
SHIPFIGHT_STICK_SLACK (4000), SHIPFIGHT_RETAKES (2), SHIPFIGHT_ENGAGE_R (2600), SHIPFIGHT_CHASE_SECS (90),
SHIPFIGHT_CHASE_GAIN (300), SHIPFIGHT_SHUN_SECS (120)."""
import os, sys, time, math, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes      # noqa: E402
import s_shipquest  # noqa: E402
import sailing      # noqa: E402

FROM = os.environ.get('SHIPFIGHT_FROM', s_lanes.PR)
SECS = float(os.environ.get('SHIPFIGHT_SECS', '900'))
LEVEL_GAP = int(os.environ.get('SHIPFIGHT_LEVEL_GAP', '3'))
WEAK = float(os.environ.get('SHIPFIGHT_WEAK', '0.5'))
PICKY_SECS = float(os.environ.get('SHIPFIGHT_PICKY_SECS', '300'))
RANGE = float(os.environ.get('SHIPFIGHT_RANGE', '1400'))
SWING = 25.0                # degrees off the beam when closing in from far / opening out from close
BREAK = float(os.environ.get('SHIPFIGHT_BREAK', '0.5'))
REPAIRS = int(os.environ.get('SHIPFIGHT_REPAIRS', '2'))
LEASH = float(os.environ.get('SHIPFIGHT_LEASH', '8000'))        # ft from the nearest port; 0 = no leash
PATROL_R = float(os.environ.get('SHIPFIGHT_PATROL_R', '5500'))  # hunt's patrol ring while this step runs
PORTS = [u for u in os.environ.get('SHIPFIGHT_PORTS', '%s,%s' % (s_lanes.PR, s_lanes.TORTUGA)).split(',') if u]
LOSS = float(os.environ.get('SHIPFIGHT_LOSS', '0.2'))           # of max hp ...
LOSS_SECS = float(os.environ.get('SHIPFIGHT_LOSS_SECS', '10'))  # ... lost in this many seconds: under heavy fire
DANGER_R = float(os.environ.get('SHIPFIGHT_DANGER_R', '1500'))   # job 21: was 2500
DANGER_GAP = int(os.environ.get('SHIPFIGHT_DANGER_GAP', '8'))
DANGER_HP = float(os.environ.get('SHIPFIGHT_DANGER_HP', '0.75'))
# job 21 (shipfight12): a danger ship counts only while closing in, and a foe under FINISH of its max is finished
CLOSE_SECS = float(os.environ.get('SHIPFIGHT_CLOSE_SECS', '20'))    # s of distance history a closing check looks at
CLOSE_GAIN = float(os.environ.get('SHIPFIGHT_CLOSE_GAIN', '150'))   # ft nearer in that time = closing in
FINISH = float(os.environ.get('SHIPFIGHT_FINISH', '0.5'))           # foe under this of its max hp: finish the kill ...
FINISH_HULL = float(os.environ.get('SHIPFIGHT_FINISH_HULL', '0.5')) # ... unless our hp is under this of max
# DOLL8 (11-21): broke off at 49% hull with a lv2 Ferret at 446/1000 hp, two hits from sinking, and the straw quest
# never moved. Against a starter-level foe (level <= ours + WEAK_GAP) or one under FINISH, hold on to FINISH_BREAK
FINISH_BREAK = float(os.environ.get('SHIPFIGHT_FINISH_BREAK', '0.25'))
WEAK_GAP = int(os.environ.get('SHIPFIGHT_WEAK_GAP', '2'))
# MAIN15 (11-21): far out (a large-ship quest, no leash) every Navy big ship shows 1800-2100 hp against our War
# Sloop's 7200, so 'weak' picked a lv 39 Dreadnought at lv 10 and it sank us (lv 16 Vanguard and lv 26 Monarch went
# down in 3 shots each). Far out, no ship over our level + FAR_GAP is picked, weak or lowest-hp.
# MAIN18 (11-21): near Port Royal 'weak' (2100 hp vs our 5415) picked a lv 34 EITC Warlord at lv 10; it took 2600 hp in
# 10 s and sank us breaking off, then a lv 37 Corsair was next. The cap now holds near port too (lv 16-26 EITC still in).
# MAIN45 (11-22): at lv 14 the cap of +20 let 'weak' pick a lv 34 EITC Warlord again and it sank us. The night's sinks
# went to +12 (lv 26 Monarch at lv 14) and +16 (the same at lv 10); +20 and over sank us every time. Cap is now +16.
FAR_GAP = int(os.environ.get('SHIPFIGHT_FAR_GAP', '16'))
NEAR_R = 3000.0             # foes this close are named when our ship sinks on the way home
RETREAT_NEAR = 2500.0       # a foe this close when we break off, or ...
RETREAT_LANE = 1500.0       # ... this close to the straight line home: the sail home goes round it first ...
RETREAT_LEG = 2000.0        # ... through a point this far out, turned away from it (retreatVia)
STICK_SLACK = float(os.environ.get('SHIPFIGHT_STICK_SLACK', '4000'))  # ft past the leash a foe we are on stays allowed
RETAKES = int(os.environ.get('SHIPFIGHT_RETAKES', '2'))     # times the wheel is taken again after losing it mid-fight
LOST_R = 2600.0             # a target that leaves view last seen farther than this sailed off (hunt fires inside 1900)
STEER_KEYS = ('a', 'd')     # hunt()'s Keys holds these; closing hunt early skips its own release
BEAM = (75.0, 105.0)        # a shot fired with the foe this far off the bow counts as on the beam
# job 18 (shipfight10): hunt holds the beam inside 2600 ft and only chases by route farther out
ENGAGE_R = float(os.environ.get('SHIPFIGHT_ENGAGE_R', '2600'))      # an unhurt foe stays first only this close
CHASE_SECS = float(os.environ.get('SHIPFIGHT_CHASE_SECS', '90'))    # s a chase may go without closing in ...
CHASE_GAIN = float(os.environ.get('SHIPFIGHT_CHASE_GAIN', '300'))   # ... by this many ft
SHUN_SECS = float(os.environ.get('SHIPFIGHT_SHUN_SECS', '120'))     # s a foe we gave up chasing is passed by
CHASE_GAP = float(os.environ.get('SHIPFIGHT_CHASE_GAP', '30'))      # s unseen (repair, patrol) restarts a chase
RANGE_LOG_SECS = 20.0       # FOE-RANGE every this many s
PLUNDER_SECS = float(os.environ.get('SHIPFIGHT_PLUNDER_SECS', '20'))  # job 23a: wait for the sink's gold
PLUNDER_DROP = float(os.environ.get('SHIPFIGHT_PLUNDER_DROP', '0.1'))  # share of our hull lost that ends it
# job 43 (GROG2): the server keeps every ship class above level 5 out of the starter waters (StarterWaters.py: 9000 ft
# of Port Royal and Tortuga and of the strip between them; such ships never spawn, sail or aim in there). A quest that
# counts only such ships (Ch3's AnyLargeShip: Bulwark lv 6 and up) is hunted out there: no leash, a search route past
# FAR_MARGIN ft beyond those waters, one point near each island out there. A hunt that sees no ship the quest counts in
# NOTARGET_SECS ends 'no-target' (SHIP-NO-TARGET names every class it did see).
STARTER_R = float(os.environ.get('SHIPFIGHT_STARTER_R', '9000'))
STARTER_LVL = int(os.environ.get('SHIPFIGHT_STARTER_LVL', '5'))
FAR_MARGIN = float(os.environ.get('SHIPFIGHT_FAR_MARGIN', '3000'))
FAR_RING = float(os.environ.get('SHIPFIGHT_FAR_RING', '5000'))       # ft from each far island's centre
NOTARGET_SECS = float(os.environ.get('SHIPFIGHT_NOTARGET_SECS', '600'))
# MAIN31 (11-21): what the last questHunt ended on (q, why, the levels of the ships its task counts that it saw), so
# s_story can skip a branch quest whose only counted ships are far above the pirate (a lv-19 Centurion for lv 12)
LAST = {}


def shipGoldRange(level):
    """Patch 0200 (NPCShipAI.shipGoldDrop): (10 * lv + lv * lv) x 0.8 .. 1.2, then up to +20% for the faction.
    -> (lo, hi), or None without a level."""
    try:
        lv = max(1, min(int(level), 60))
    except Exception:
        return None
    base = 10 * lv + lv * lv
    return int(round(base * 0.8)), int(round(base * 1.2 * 1.2))


def goldCheck(before, after, level):
    """-> (gain, expect, ok): ok is None when the level is not known."""
    if before is None or after is None:
        return None, shipGoldRange(level), False
    gain = after - before
    exp = shipGoldRange(level)
    return gain, exp, (None if exp is None else exp[0] <= gain <= exp[1])


def plunderCut(hp0, hp, mx, floor=None, drop=None):
    """Pure. Why the plunder wait should stop for our hull, or None. DOLL9 (11-21): the straw Ferret sank with us at
    1010/2400, and a second Ferret shot us down to 82 while the bot sat out the 20 s wait for the gold."""
    floor = FINISH_BREAK if floor is None else floor
    drop = PLUNDER_DROP if drop is None else drop
    if hp is None or not mx:
        return None
    if hp < floor * mx:
        return 'hp %d < %d%% of %d' % (hp, round(100 * floor), mx)
    if hp0 is not None and hp0 - hp > drop * mx:
        return 'lost %d hp while waiting' % (hp0 - hp)
    return None


def plunderWait(H, secs, step=1.0, hull=None):
    """Generator: wait secs after the sink, noting each gold change. -> (gold after, [[s, gold], ...]). hull() ->
    (hp, maxHp) of our ship; the wait ends early (PLUNDER-CUT) when plunderCut says so."""
    t0 = time.time()
    g = s_lanes.gold(H)
    changes = []
    hp0 = hull()[0] if hull else None
    while time.time() - t0 < secs:
        yield step
        if hull:
            hp, mx = hull()
            cut = plunderCut(hp0, hp, mx)
            if cut:
                H.ev('PLUNDER-CUT', why=cut, hp=hp, maxHp=mx, waited=round(time.time() - t0, 1))
                break
        n = s_lanes.gold(H)
        if n != g:
            changes.append([round(time.time() - t0, 1), n])
            g = n
    return g, changes


class AnyShip:
    """A stand-in for a DefeatShipTaskDNA that any NPC ship with a faction matches (s_shipquest.matches)."""
    faction = None
    hull = None
    level = 0
    isFlagship = False


def questIds(fl, task, match):
    """Pure, job 30. fl = [(dist, ship)]; -> the doIds of the ships task counts (match(task, o) -> (ok, why)), or None
    for no task (the AnyShip lane: every ship is ranked)."""
    if task is None:
        return None
    out = set()
    for d, o in fl:
        try:
            if match(task, o)[0]:
                out.add(o.doId)
        except Exception:
            pass
    return out


def sinkCount(why, foeSunk):
    """Pure, job 30: did this fight sink a ship? A FOE-SUNK line, or a quest credit / hand-off (ship tasks are only
    ever credited by a sink: QuestTaskDNA.handleShipDefeat), even when the credit came before the client saw 0 hp."""
    return bool(foeSunk) or why in ('credit', 'complete')


def seen(names, evs):
    """Pure: which fight stages a list of hunt event names shows -> (stage what, ...) in order, each once."""
    out = []
    for k, what in (('SHIP-HUNT', 'launched'), ('SHIP-TARGET', 'foe-seen'), ('BROADSIDE', 'first-shot'),
                    ('RAM', 'first-shot'), ('FOE-SUNK', 'foe-sunk')):
        if k in evs and what not in names and what not in out:
            out.append(what)
    return out


def farOut(c, leash):
    """Pure: ft past the leash for a candidate (dist, doId, level, hp[, ft from the nearest port]), else 0."""
    fp = c[4] if len(c) > 4 else None
    return fp - leash if (leash and fp is not None and fp > leash) else 0


def rank(cands, myLevel, ourHp, stick=None, anyOk=False, gap=None, weak=None, leash=None, slack=None, cap=None):
    """Pure. cands = [(dist, doId, level, hp[, ft from the nearest port])]. -> (how, [doId allowed, best first],
    {doId: why not}). A ship farther than leash ft from the nearest port is never picked (it would take us out of
    starter waters). how = 'fair' (level <= myLevel + gap, nearest first), 'weak' (hp <= weak x ourHp, lowest hp
    first), 'lowest-hp' (anyOk: everything, lowest hp first) or None (nothing to fight yet). The ship we are already
    on (stick) stays first while it is allowed, and up to slack ft past the leash (we chase a foe we are on). A ship
    over level cap is never picked (default myLevel + FAR_GAP, near port and far out)."""
    gap = LEVEL_GAP if gap is None else gap
    weak = WEAK if weak is None else weak
    leash = LEASH if leash is None else leash
    slack = STICK_SLACK if slack is None else slack
    cap = myLevel + FAR_GAP if cap is None else cap
    top = myLevel + gap
    allCands = cands
    cands = [c for c in cands if not farOut(c, leash) or (stick is not None and c[1] == stick and farOut(c, leash) <= slack)]
    inLeash = set(c[1] for c in cands)
    cands = [c for c in cands if (c[2] or 0) <= cap]
    fair = sorted([c for c in cands if (c[2] or 0) <= top], key=lambda c: c[0])
    how, ok = 'fair', fair
    if not fair:
        lim = weak * ourHp if ourHp else 0
        ok = sorted([c for c in cands if c[3] is not None and c[3] <= lim], key=lambda c: (c[3], c[0]))
        how = 'weak'
        if not ok and anyOk:
            ok = sorted([c for c in cands if c[3] is not None], key=lambda c: (c[3], c[0]))
            how = 'lowest-hp'
    order = [c[1] for c in ok]
    if stick in order:
        order.remove(stick)
        order.insert(0, stick)
    why = {}
    for c in allCands:
        if c[1] in order:
            continue
        if c[1] not in inLeash:
            why[c[1]] = '%d ft from port > leash %d' % (c[4], leash) + (' + %d' % slack if c[1] == stick else '')
        elif (c[2] or 0) > cap:
            why[c[1]] = 'level %s > cap %s' % (c[2], cap)
        elif (c[2] or 0) > top:
            why[c[1]] = 'level %s > %s + %s' % (c[2], myLevel, gap)
        else:
            why[c[1]] = 'not picked'
    return (how if order else None), order, why


def holdBeam(d, brg, rng=None):
    """Pure. The bearing to hold the foe at: abeam (90) at rng ft, up to SWING less (angling in) when farther and
    SWING more (opening out) when closer, on the side the foe is on."""
    rng = RANGE if rng is None else rng
    k = max(-SWING, min(SWING, (d - rng) / 20.0))
    return math.copysign(90.0 - k, brg if brg else 1.0)


def shouldBreak(hp, maxHp, brk=None):
    """Pure. Break off and repair: afloat, below brk of max hp."""
    brk = BREAK if brk is None else brk
    return bool(hp is not None and maxHp and 0 < hp < brk * maxHp)


def dangers(cands, myLevel, r=None, gap=None, closing=None):
    """Pure. cands = [(dist, doId, level, hp, ...)] -> [(dist, doId, level)] of ships over gap levels above the
    pirate within r ft of our ship, nearest first. closing = the set of doIds closing in (closingIds); None = all."""
    r = DANGER_R if r is None else r
    gap = DANGER_GAP if gap is None else gap
    return sorted((round(c[0]), c[1], c[2]) for c in cands if c[0] <= r and (c[2] or 0) > myLevel + gap
                  and (closing is None or c[1] in closing))


def closingIds(track, now, secs=None, gain=None):
    """Pure. track = {doId: [(t, dist)] oldest first} -> the set of doIds that came at least gain ft nearer within
    the last secs (the farthest sample in the window minus the latest)."""
    secs = CLOSE_SECS if secs is None else secs
    gain = CLOSE_GAIN if gain is None else gain
    out = set()
    for doId, rows in track.items():
        w = [d for t, d in rows if now - t <= secs and d is not None]
        if len(w) >= 2 and max(w) - w[-1] >= gain:
            out.add(doId)
    return out


def finishing(hp, maxHp, foeFrac, finish=None, hull=None):
    """Pure. True when the foe is under finish of its max hp and our hp is at least hull of ours: finish the kill."""
    finish = FINISH if finish is None else finish
    hull = FINISH_HULL if hull is None else hull
    return bool(foeFrac is not None and foeFrac < finish and hp is not None and maxHp and hp >= hull * maxHp)


def weakFoe(level, myLevel, far=False):
    """Pure. A starter-level foe (level <= ours + WEAK_GAP) we may fight down to FINISH_BREAK. Never far out
    (MAIN16: held on to 25% vs a lv 9 Panther 26000 ft from port, with a lv 18 and lv 31 near, and sank sailing home)."""
    return level is not None and not far and level <= myLevel + WEAK_GAP


def foeFrac(o, first=None):
    """Its hp / max hp, or None. Max from getMaxHp / maxHp, else the hp it had when first seen (Picker.first)."""
    if o is None:
        return None
    hp = s_shipquest.hpOf(o)
    try:
        mx = o.getMaxHp()
    except Exception:
        mx = getattr(o, 'maxHp', None)
    if not mx and first:
        mx = first[0]
    if hp is None or not mx:
        return None
    return float(hp) / mx


def breakWhy(hp, maxHp, hist, now, danger=(), brk=None, loss=None, lossSecs=None, dangerHp=None, foe=None, weak=False):
    """Pure. Why to break off and repair now, or None. hist = [(t, hp)] samples of our hp (oldest first).
    - hp under brk of max (shouldBreak); FINISH_BREAK instead when the foe is weak (a starter-level ship) or under
      FINISH of its max (DOLL8);
    - lost more than loss of max in the last lossSecs (under heavy fire: at the rate SMOKE-shipfight6 lost hp it
      would not reach port); not against a weak foe, which cannot sink us that fast;
    - a ship from dangers() close and hp under dangerHp of max.
    foe = the foe's hp fraction: under FINISH with our hp at least FINISH_HULL, only the first rule applies (job 21)."""
    loss = LOSS if loss is None else loss
    lossSecs = LOSS_SECS if lossSecs is None else lossSecs
    dangerHp = DANGER_HP if dangerHp is None else dangerHp
    if not (hp is not None and maxHp and hp > 0):
        return None
    if brk is None:
        brk = FINISH_BREAK if (weak or (foe is not None and foe < FINISH)) else BREAK
    if shouldBreak(hp, maxHp, brk):
        return 'hp %d < %d%% of %d' % (hp, round(100 * brk), maxHp)
    if finishing(hp, maxHp, foe):
        return None
    old = [h for t, h in hist if now - t <= lossSecs and h is not None]
    if old and not weak and max(old) - hp > loss * maxHp:
        return 'lost %d hp in %d s' % (max(old) - hp, lossSecs)
    if danger and hp < dangerHp * maxHp:
        d, doId, lv = danger[0]
        return 'level %s ship at %d ft and hp %d < %d%%' % (lv, d, hp, round(100 * dangerHp))
    return None


def nearestPort(p, ports):
    """Pure. p = (x, y); ports = [(uid, name, x, y)] -> (uid, name, ft) of the nearest, or (None, None, None)."""
    if p is None or not ports:
        return None, None, None
    u, n, x, y = min(ports, key=lambda t: (t[2] - p[0]) ** 2 + (t[3] - p[1]) ** 2)
    return u, n, round(math.hypot(x - p[0], y - p[1]))


def classLevel(shipClass):
    """The class level the server uses (StarterWaters.classLevel)."""
    try:
        from pirates.ship import ShipGlobals as SG
        return int(SG.getShipLevel(shipClass) or 1)
    except Exception:
        return 1


def farTask(task, lvlOf=None, maxLvl=None):
    """Job 43. (far, why): True when no ship this task counts can be in the starter waters: every class of its hull
    list is above the starter level, or the task asks for a ship above it. No task / no hull list: False."""
    if task is None:
        return False, 'no task'
    lvlOf = classLevel if lvlOf is None else lvlOf
    maxLvl = STARTER_LVL if maxLvl is None else maxLvl
    lvl = getattr(task, 'level', 0) or 0
    if lvl > maxLvl:
        return True, 'task level %s > starter %s' % (lvl, maxLvl)
    hull = getattr(task, 'hull', None)
    if hull is None:
        return False, 'any hull'
    try:
        from pirates.quest.QuestConstants import getShipList
        lst = getShipList(hull)
    except Exception:
        lst = None
    if not lst:
        return False, 'hull %s has no list' % hull
    low = [c for c in lst if lvlOf(c) <= maxLvl]
    if low:
        return False, 'hull %s has starter classes %s' % (hull, low)
    return True, 'hull %s: lowest class level %s > starter %s' % (hull, min(lvlOf(c) for c in lst), maxLvl)


def segDist(px, py, x0, y0, x1, y1):
    """Pure: ft from (px, py) to the segment (x0, y0)-(x1, y1)."""
    dx, dy = x1 - x0, y1 - y0
    L = dx * dx + dy * dy
    t = 0.0 if L <= 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def retreatVia(p, home, foes, near=RETREAT_NEAR, lane=RETREAT_LANE, leg=RETREAT_LEG, turn=60.0):
    """Pure. p, home = (x, y); foes = [(x, y)] of the ships in view. When a foe is within near ft of p, or within lane
    ft of the straight line home, -> a point leg ft away, turned `turn` degrees off the home line to the side away
    from those foes (DOLL4 sank sailing home past two chasing Ferrets); else None."""
    if p is None or home is None or not foes:
        return None
    hx, hy = home[0] - p[0], home[1] - p[1]
    L = math.hypot(hx, hy)
    if L < 1:
        return None
    ux, uy = hx / L, hy / L
    nx, ny = -uy, ux                                    # left of the home line
    side = 0.0
    hit = False
    for fx, fy in foes:
        d = math.hypot(fx - p[0], fy - p[1])
        if d <= near or segDist(fx, fy, p[0], p[1], home[0], home[1]) <= lane and d <= near + leg:
            hit = True
            side += ((fx - p[0]) * nx + (fy - p[1]) * ny) / max(d, 1.0)
    if not hit:
        return None
    s = -1.0 if side > 0 else 1.0                       # away from the foes' side (all dead ahead: left)
    a = math.radians(turn)
    dx, dy = ux * math.cos(a) + s * nx * math.sin(a), uy * math.cos(a) + s * ny * math.sin(a)
    leg = min(leg, L)
    return (p[0] + dx * leg, p[1] + dy * leg)


def starterGap(x, y, centres, r=None):
    """Pure, job 43: ft (x, y) lies outside the starter waters (negative = inside): r ft round each centre and round
    the straight strip from each centre to the next, as StarterWaters.inStarterWaters draws them."""
    r = STARTER_R if r is None else r
    d = [math.hypot(x - cx, y - cy) for cx, cy in centres]
    d += [segDist(x, y, centres[i][0], centres[i][1], centres[i + 1][0], centres[i + 1][1])
          for i in range(len(centres) - 1)]
    return (min(d) if d else float('inf')) - r


def farRoute(isl, centres, start, r=None, margin=None, ring=None):
    """Pure, job 43. isl = {uid: (name, x, y, ...)}. -> [(x, y, name)]: one point ring ft off each named island whose
    centre lies margin ft or more outside the starter waters, on the side facing the point before it, nearest island
    first from start, then the nearest not yet visited. A point that falls inside the waters + margin is turned round
    the island until it is out (or the island is skipped)."""
    r = STARTER_R if r is None else r
    margin = FAR_MARGIN if margin is None else margin
    ring = FAR_RING if ring is None else ring
    left = [(v[0], v[1], v[2]) for u, v in sorted(isl.items()) if v[0] and starterGap(v[1], v[2], centres, r) >= margin]
    out, at = [], (start[0], start[1])
    while left:
        nm, x, y = min(left, key=lambda t: math.hypot(t[1] - at[0], t[2] - at[1]))
        left.remove((nm, x, y))
        a0 = math.atan2(at[1] - y, at[0] - x)
        for k in range(8):
            a = a0 + (k + 1) // 2 * (math.pi / 4) * (1 if k % 2 else -1)
            px, py = x + ring * math.cos(a), y + ring * math.sin(a)
            if starterGap(px, py, centres, r) >= margin:
                out.append((round(px), round(py), nm))
                at = (px, py)
                break
    return out


def dropWhy(foe, why, inView):
    """Pure. Why the foe we were on is no longer the pick: rank's reason, else out of view."""
    if foe in why:
        return why[foe]
    return 'in view, another ranked first' if foe in inView else 'out of view'


def hurt(first, foe):
    """Pure. first = {doId: (hp first seen, last hp, last dist)} -> True when our fire took hp off foe."""
    f = first.get(foe)
    return bool(f is not None and f[0] is not None and f[1] is not None and f[1] < f[0])


def engageStick(cands, stick, hurtStick, r=None):
    """Pure. The foe to keep first (rank's stick), or None to let rank pick the nearest fair one. A foe we hurt is
    kept; one we have not hurt only while it is within r ft, or while no other ship in view is."""
    r = ENGAGE_R if r is None else r
    if stick is None or hurtStick:
        return stick
    me = [c for c in cands if c[1] == stick]
    if not me or me[0][0] <= r:
        return stick
    if any(c[1] != stick and c[0] <= r for c in cands):
        return None
    return stick


def chaseStep(st, foe, d, now, hurtFoe=False, r=None, secs=None, gain=None, gap=None):
    """Pure. st = (foe, t of the last gain, best ft, t the chase began, t last seen) or None. -> (new st, why to give
    up or None). Inside r ft hunt holds the beam, so only a chase farther out is timed; gaining gain ft resets the clock.
    MAIN4 (11-21): after a break-off, repair and patrol the hurt Cerberus came back into view 252 s on and was dropped
    in the same tick against the best range from before the repair. A foe unseen for gap s starts a fresh chase."""
    r = ENGAGE_R if r is None else r
    secs = CHASE_SECS if secs is None else secs
    gain = CHASE_GAIN if gain is None else gain
    gap = CHASE_GAP if gap is None else gap
    if st is None or st[0] != foe or d <= r or now - st[4] > gap:
        return (foe, now, d, now, now), None
    _, tb, best, t0, _ = st
    if d < best - gain:
        return (foe, now, d, t0, now), None
    lim = secs * (2 if hurtFoe else 1)
    if now - tb >= lim:
        return None, 'not closing in: no %d ft gained in %d s (best %d ft, now %d ft)' % (gain, now - tb, best, d)
    return (foe, tb, best, t0, now), None


def stackOf(frames, n=10):
    """Pure. frames = [(filename, lineno, name, ...)] oldest first -> the newest n as 'file.py:123 name'."""
    out = []
    for f in list(frames)[-n:]:
        out.append('%s:%s %s' % (os.path.basename(str(f[0])), f[1], f[2]))
    return out


def canRetake(inWorld, aboard, hp, n, most=None):
    """Pure. Take the wheel again after hunt said 'left-ship'? -> (yes, why)."""
    most = RETAKES if most is None else most
    if not inWorld:
        return False, 'our ship left the client'
    if hp is None or hp <= 0:
        return False, 'our ship is sunk'
    if not aboard:
        return False, 'the pirate is not aboard'
    if n >= most:
        return False, 'took the wheel again %d times already' % n
    return True, 'ship afloat, pirate aboard'


def onBeam(brg):
    return BEAM[0] <= abs(brg or 0) <= BEAM[1]


def shipHp(H, sid):
    """(hp, maxHp) of our ship: the ship itself while it is in the world, else its owner view."""
    o = H.cr.doId2do.get(sid)
    if o is None:
        o = H.cr.getOwnerView(sid)
    if o is None:
        return None, None
    mx = getattr(o, 'maxHp', None)
    if not mx:
        try:
            mx = o.getMaxHp()
        except Exception:
            mx = None
    return s_shipquest.hpOf(o), mx


def shipXY(H, sid):
    o = H.cr.doId2do.get(sid)
    try:
        p = o.getPos(H.render)
        return (p[0], p[1])
    except Exception:
        return None


class Picker:
    """Wraps s_shipquest.npcShips / matches / wantBearing while one hunt() runs, so hunt's own loop takes the foe this
    step picks (its 'good' list is npcShips' order filtered by matches) and holds it on the beam."""

    def __init__(self, H, t0, task=None):
        self.H, self.t0 = H, t0
        self.task = task            # job 30: a quest task -> only ships it counts are ranked (dangers see them all)
        self.allowed, self.why, self.top, self.how = set(), {}, None, None
        self.logged = set()
        self.levels = []
        tbl = sailing.islands()
        self.ports = [(u, tbl[u][0], tbl[u][1], tbl[u][2]) for u in (PORTS or [FROM]) if u in tbl]
        if not self.ports and FROM in tbl:
            self.ports = [(FROM, tbl[FROM][0], tbl[FROM][1], tbl[FROM][2])]
        self.last = []              # the latest [(dist, doId, level, hp, fromPort, name)] in view
        self.first = {}             # doId -> (hp when first seen, last hp, last dist): FOE-SUNK vs out of sight
        self.saved = None
        self.wheel = None           # the last WHEEL-EXIT fields (fight() fills it when hunt says 'left-ship')
        self.want = None            # the last foe our fire hurt: re-acquired when it comes back into view
        self.chase = None           # chaseStep state for the target (job 18)
        self.shun = {}              # doId -> time until which it is passed by (gave up chasing it)
        self.rangeT = 0.0           # last FOE-RANGE
        self.track = {}             # doId -> [(t, dist)] for closingIds (job 21)
        self.finished = set()       # foes a FINISH-KILL was logged for
        self.info = {}              # doId -> (level, name, shipClass) of each ship seen (job 23a: the sunk foe's)
        self.sunk = None            # (doId, level, name, shipClass) of the first foe FOE-SUNK named
        self.matchSeen = set()      # job 43: doIds of the ships the task counts seen so far
        self.classSeen = {}         # job 43: (shipClass, level) -> ships of it seen
        try:
            self.far, self.farWhy = farTask(task)
        except Exception as e:
            self.far, self.farWhy = False, 'check failed: %s' % e
        self.route = None           # job 43: the far search route [(x, y, island)]
        self.savedPts = None

    def seenSummary(self):
        """Job 43: 'class/lv xN' for every class seen, most first."""
        return ['%s/lv%s x%d' % (k[0], k[1], n) for k, n in sorted(self.classSeen.items(), key=lambda t: -t[1])]

    def noTarget(self, now, secs=None):
        """Job 43: True once a quest hunt has gone secs without seeing one ship its task counts."""
        secs = NOTARGET_SECS if secs is None else secs
        return bool(self.task is not None and secs > 0 and not self.matchSeen and now - self.t0 >= secs)

    def fromPort(self, H, o):
        try:
            p = o.getPos(H.render)
        except Exception:
            return None
        return nearestPort((p[0], p[1]), self.ports)[2]

    def lost(self, foe):
        """True when a target that left the client's view was last seen out of broadside range (hunt fires inside
        1900 ft), so our shot cannot have sunk it. Not by hp: one broadside can sink a small Ferret from full."""
        f = self.first.get(foe)
        return bool(f is not None and f[2] > LOST_R)

    def lostInfo(self, foe):
        """s_shipquest.LOST: what we last knew of a target that sailed off, or None when it may have sunk."""
        return list(self.first[foe]) if self.lost(foe) else None

    def myLevel(self):
        try:
            return int(self.H.la.getLevel() or 1)
        except Exception:
            return 1

    def npcShips(self, H, ship):
        fl = self.saved[0](H, ship)
        allc = [(d, o.doId, s_shipquest.levelOf(o), s_shipquest.hpOf(o), self.fromPort(H, o)) for d, o in fl]
        quest = questIds(fl, self.task, self.saved[1])
        cands = allc if quest is None else [c for c in allc if c[1] in quest]
        if quest:
            self.matchSeen |= quest
        ourHp = s_shipquest.hpOf(ship)
        lvl = self.myLevel()
        ids = set(c[1] for c in cands)
        if self.top is not None and hurt(self.first, self.top):
            self.want = self.top
        now = time.time()
        rel = None                  # why the foe we were on is let go (job 18), else dropWhy says
        dist = dict((c[1], c[0]) for c in cands)
        if self.top in dist and self.shun.get(self.top, 0) <= now:
            self.chase, gone = chaseStep(self.chase, self.top, dist[self.top], now, hurt(self.first, self.top))
            if gone:
                self.shun[self.top] = now + SHUN_SECS
                if self.want == self.top:
                    self.want = None
                rel = gone
        shunned = set(i for i, u in self.shun.items() if u > now)
        live = [c for c in cands if c[1] not in shunned]
        stick = self.top if self.top in ids else (self.want if self.want in ids else self.top)
        if stick in shunned:
            stick = None
        es = engageStick(live, stick, hurt(self.first, stick), ENGAGE_R)
        if stick is not None and es is None and rel is None:
            near = min(c[0] for c in live if c[1] != stick and c[0] <= ENGAGE_R)
            rel = 'a foe within %d ft (%d ft) while ours is %d ft off' % (ENGAGE_R, near, dist[stick])
        how, order, why = rank(live, lvl, ourHp, stick=es, anyOk=now - self.t0 > PICKY_SECS,
                               leash=0 if self.far else None)
        for i in shunned:
            if i in ids:
                why[i] = 'passed by %d s more: not closing in' % (self.shun[i] - now)
        self.allowed, self.why = set(order), why
        byId = dict((o.doId, (d, o)) for d, o in fl)
        self.last = [c + (getattr(byId[c[1]][1], 'name', ''),) for c in allc]     # dangers: every ship in view
        for c in allc:
            self.track[c[1]] = [r for r in self.track.get(c[1], []) if now - r[0] <= CLOSE_SECS] + [(now, c[0])]
        if quest is not None:
            for c in allc:
                if c[1] not in quest:
                    why[c[1]] = 'not a ship this quest counts'
        for d, doId, lv, hp, fp in allc:
            f = self.first.get(doId)
            self.first[doId] = (hp if f is None else f[0], hp, d)
            ob = byId[doId][1]
            self.info[doId] = (lv, getattr(ob, 'name', ''), getattr(ob, 'shipClass', None))
            if doId in self.logged:
                continue
            self.logged.add(doId)
            self.levels.append(lv)
            ck = (getattr(ob, 'shipClass', None), lv)
            self.classSeen[ck] = self.classSeen.get(ck, 0) + 1
            o = byId[doId][1]
            H.ev('ship-lv', doId=doId, foeName=getattr(o, 'name', ''), shipClass=getattr(o, 'shipClass', None),
                 level=lv, hp=hp, fromHome=None if fp is None else round(fp), myLevel=lvl,
                 picked=doId in self.allowed, why=why.get(doId, how))
        top = order[0] if order else None
        o0 = H.cr.doId2do.get(self.top) if self.top is not None else None
        sank = o0 is not None and (s_shipquest.hpOf(o0) or 0) <= 0      # at 0 hp: hunt says FOE-SUNK, not a drop
        if self.top is not None and top != self.top and not sank:
            f = self.first.get(self.top)
            H.ev('FOE-DROP', foe=self.top, why=rel or dropWhy(self.top, why, ids), now=top, hurt=hurt(self.first, self.top),
                 last=None if f is None else [f[0], f[1], round(f[2])])
        if top is not None and top == self.want and self.top != top:
            f = self.first.get(top)
            H.ev('FOE-REACQUIRE', foe=top, hp=None if f is None else f[1], dist=None if f is None else round(f[2]))
        if top is not None and (top != self.top or how != self.how):
            d, o = byId[top]
            H.ev('FOE-PICK', foe=top, how=how, foeName=getattr(o, 'name', ''), level=s_shipquest.levelOf(o),
                 hp=s_shipquest.hpOf(o), dist=round(d), myLevel=lvl, ourHp=ourHp, inView=len(cands))
        self.top, self.how = top, how
        if top is not None and now - self.rangeT >= RANGE_LOG_SECS:
            self.rangeT = now
            d, o = byId[top]
            oth = sorted((c for c in cands if c[1] != top), key=lambda c: c[0])
            H.ev('FOE-RANGE', foe=top, dist=round(d), mode='beam' if d <= ENGAGE_R else 'chase', ourHp=ourHp,
                 foeHp=s_shipquest.hpOf(o), nearest=[oth[0][1], round(oth[0][0]), oth[0][2]] if oth else None,
                 shunned=sorted(shunned) or None)
        # the picked ships first, best first; the rest after, nearest first (hunt still logs them as seen)
        rest = [t for t in fl if t[1].doId not in self.allowed]
        return [byId[i] for i in order] + rest

    def matches(self, task, o):
        ok, w = self.saved[1](task, o)
        if ok and getattr(o, 'doId', None) not in self.allowed:
            return False, self.why.get(getattr(o, 'doId', None), 'not picked')
        return ok, w

    def __enter__(self):
        self.saved = (s_shipquest.npcShips, s_shipquest.matches, s_shipquest.wantBearing,
                      getattr(s_shipquest, 'PATROL_R', None), getattr(s_shipquest, 'LOST', None))
        s_shipquest.npcShips, s_shipquest.matches, s_shipquest.wantBearing = self.npcShips, self.matches, holdBeam
        s_shipquest.LOST = self.lostInfo
        if PATROL_R:
            s_shipquest.PATROL_R = PATROL_R
        self.savedPts = getattr(s_shipquest, 'PATROL_PTS', None)
        if self.far:
            if self.route is None:
                self.route = self.farSearch()
            if self.route:
                s_shipquest.PATROL_PTS = self.route
        return self

    def __exit__(self, *a):
        s_shipquest.npcShips, s_shipquest.matches, s_shipquest.wantBearing = self.saved[:3]
        if self.saved[3] is not None:
            s_shipquest.PATROL_R = self.saved[3]
        s_shipquest.LOST = self.saved[4]
        s_shipquest.PATROL_PTS = self.savedPts
        return False

    def farSearch(self):
        """Job 43: the search route past the starter waters, from where the pirate is now. Logs SHIP-SEARCH-FAR."""
        H = self.H
        try:
            p = H.la.getPos(H.render)
            start = (p[0], p[1])
        except Exception:
            start = (self.ports[0][2], self.ports[0][3]) if self.ports else (0.0, 0.0)
        try:
            route = farRoute(sailing.islands(), [(c[2], c[3]) for c in self.ports], start)
        except Exception as e:
            route = []
            H.ev('SHIP-SEARCH-FAR', ok=False, why=self.farWhy, err=repr(e)[:200])
            return route
        H.ev('SHIP-SEARCH-FAR', ok=bool(route), why=self.farWhy, starterR=STARTER_R, margin=FAR_MARGIN,
             islands=[t[2] for t in route], pts=[[t[0], t[1]] for t in route], leash=0)
        return route

    def near(self, r=NEAR_R):
        """The foes in view within r ft at the last look, as 'Name lv N at D ft', nearest first."""
        return ['%s lv %s at %d ft' % (c[5] or c[1], c[2], c[0]) for c in sorted(self.last, key=lambda c: c[0]) if c[0] <= r]


class WheelWatch:
    """While a fight runs: notes who moves the pirate out of ShipPilot (the call stack of its gameFSM.request /
    forceTransition: the server's setGameState, the wheel's own exit, the ship's boarding or sinking code)."""

    def __init__(self, H):
        self.H, self.last, self.fsm, self.wrapped = H, None, None, []

    def __enter__(self):
        fsm = getattr(self.H.la, 'gameFSM', None)
        if fsm is None:
            return self
        self.fsm = fsm
        for name in ('request', 'forceTransition'):
            orig = getattr(fsm, name, None)
            if orig is None:
                continue
            setattr(fsm, name, self.wrap(fsm, name, orig))
            self.wrapped.append(name)
        return self

    def wrap(self, fsm, name, orig):
        def call(state, *a, **kw):
            try:
                cur = fsm.getCurrentOrNextState()
                if cur == 'ShipPilot' and state != 'ShipPilot':
                    self.last = {'t': time.time(), 'how': name, 'frm': cur, 'to': state,
                                 'stack': stackOf(traceback.extract_stack()[:-1])}
            except Exception:
                pass
            return orig(state, *a, **kw)
        return call

    def __exit__(self, *a):
        for name in self.wrapped:
            try:
                delattr(self.fsm, name)      # back to the class's own method
            except Exception:
                pass
        self.wrapped = []
        return False


def wheelState(H, sid, picker, watch):
    """WHEEL-EXIT fields: who moved us, the ship's and the wheel's state, where the pirate is."""
    la, ship = H.la, H.cr.doId2do.get(sid)
    w = next((o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedSteeringWheel'
              and getattr(o, 'shipId', None) == sid), None)
    hp, mx = shipHp(H, sid)
    last = watch.last or {}
    try:
        shipGs = ship.gameFSM.getCurrentOrNextState() if ship is not None and getattr(ship, 'gameFSM', None) else None
    except Exception:
        shipGs = None
    return dict(to=last.get('to'), how=last.get('how'), ago=round(time.time() - last['t'], 1) if last else None,
                stack=last.get('stack'), gs=la.getGameState(), inWorld=ship is not None, hp=hp, maxHp=mx,
                shipGs=shipGs, steering=getattr(ship, 'steeringAvId', None), wheelUser=getattr(w, 'userId', None),
                wheelAllow=getattr(w, 'allowInteract', None), aboard=sailing.onShip(H),
                laParent=getattr(la, 'parentId', None), shipZone=getattr(ship, 'zoneId', None), area=H.area(),
                foe=picker.top, near=picker.near())


def fight(H, sid, secs, got, picker, qid=None, task=None):
    """Generator: one hunt() until a foe sinks, breakWhy() says break off, or hunt ends. -> 'foe-sunk' / 'break-off' /
    hunt's own why ('credit' / 'complete' when a quest's progress moved: job 30's questHunt passes qid and task)."""
    sunk0 = got.get('FOE-SUNK', 0)
    why = None
    hist = []
    end = time.time() + secs                 # hunt's own clock starts after the launch; this one does not
    g = s_shipquest.hunt(H, qid, task if task is not None else AnyShip(), secs)
    watch = WheelWatch(H)
    with picker, watch:
        try:
            while True:
                try:
                    y = next(g)
                except StopIteration as e:
                    why = e.value
                    break
                if got.get('FOE-SUNK', 0) > sunk0:
                    why = 'foe-sunk'
                    break
                if time.time() >= end:
                    why = 'timeout'
                    break
                if picker.noTarget(time.time()):
                    why = 'no-target'
                    H.ev('SHIP-NO-TARGET', q=qid, task=type(task).__name__ if task is not None else None,
                         faction=str(getattr(task, 'faction', None)), hull=getattr(task, 'hull', None),
                         secs=round(time.time() - picker.t0), far=picker.far, farWhy=picker.farWhy,
                         route=[t[2] for t in picker.route or []], seen=picker.seenSummary())
                    break
                if H.la.getGameState() == 'ShipPilot':
                    hp, mx = shipHp(H, sid)
                    now = time.time()
                    dz = dangers(picker.last, picker.myLevel(), closing=closingIds(picker.track, now))
                    foe = H.cr.doId2do.get(picker.top) if picker.top else None
                    ff = foeFrac(foe, picker.first.get(picker.top))
                    weak = foe is not None and weakFoe(s_shipquest.levelOf(foe), picker.myLevel(), picker.far)
                    bw = breakWhy(hp, mx, hist, now, dz, foe=ff, weak=weak)
                    if not bw and picker.top not in picker.finished:
                        would = breakWhy(hp, mx, hist, now, dz)
                        if would:
                            picker.finished.add(picker.top)
                            H.ev('FINISH-KILL', foe=picker.top, foeHp=s_shipquest.hpOf(foe), foeFrac=round(ff, 2),
                                 hp=hp, maxHp=mx, skipped=would, near=picker.near())
                    hist = [t for t in hist if now - t[0] <= LOSS_SECS] + [(now, hp)]
                    if bw:
                        port, pname, pd = nearestPort(shipXY(H, sid), picker.ports)
                        H.ev('BREAK-OFF', hp=hp, maxHp=mx, at=BREAK, why=bw, foe=picker.top,
                             foeHp=s_shipquest.hpOf(foe) if foe is not None else None, port=pname, fromPort=pd,
                             near=picker.near())
                        why = 'break-off'
                        break
                yield y
            if why == 'left-ship':
                picker.wheel = wheelState(H, sid, picker, watch)
                H.ev('WHEEL-EXIT', **picker.wheel)
        finally:
            g.close()
            for k in STEER_KEYS:            # let go of the wheel keys hunt() may hold
                messenger.send(k + '-up')
    return why


def repairAt(H, sid, picker):
    """Generator: sail to the nearest repair port from where the fight ended (HOME-PICK), top the pirate's gold up
    when it cannot pay (MW-GOLD), have the shipwright mend the ship. -> 'ok' when mended above BREAK, 'sunk' when
    our ship sank on the way, else 'failed'."""
    p = shipXY(H, sid)
    uid, name, dist = nearestPort(p, picker.ports)
    uid = uid or FROM
    near = picker.near()
    H.ev('HOME-PICK', port=uid, name=name, dist=dist, at=None if p is None else (round(p[0]), round(p[1])),
         ports=[(t[1], nearestPort(p, [t])[2]) for t in picker.ports], near=near)
    home = next(((t[2], t[3]) for t in picker.ports if t[0] == uid), None)
    foes = [xy for xy in (shipXY(H, c[1]) for c in picker.last) if xy is not None]
    via = retreatVia(p, home, foes)
    if via is not None:
        H.ev('RETREAT-VIA', via=(round(via[0]), round(via[1])), home=name, foes=len(foes), near=near)
    H.sailResult = False
    yield from sailing.sail_to(H, uid, why='repair after break-off', via=via)
    if not getattr(H, 'sailResult', False):
        hp, mx = shipHp(H, sid)
        gs = H.la.getGameState()
        if (hp is not None and hp <= 0) or gs in ('Death', 'Cutscene'):
            H.ev('REPAIR', ok=False, why='sank on the way home (hp %s, %s ft from %s when it broke off, foes near: %s)'
                 % (hp, dist, name, ', '.join(near) or 'none in view'), gs=gs, area=H.area())
            return 'sunk'
        H.ev('REPAIR', ok=False, why='could not sail to %s (a SAIL-FAIL line says why)' % name, hp=hp, gs=gs,
             area=H.area())
        return 'failed'
    ov = H.cr.getOwnerView(sid)
    hp0 = getattr(ov, 'Hp', None)
    try:
        from pirates.ship import ShipGlobals
        cost, gold = ShipGlobals.getRepairCost(ov), H.la.getInventory().getGoldInPocket()
    except Exception:
        cost, gold = 0, 0
    if cost and gold < cost and os.environ.get('STORY_PLAYER') != '1':     # a player bot never uses the gold word
        H.ev('MW-GOLD', why='the pirate cannot pay the repair after a break-off', ship=sid, gold=gold, cost=cost)
        H.mw('gold %d' % (gold + cost + 500))
        yield ('until', lambda: H.la.getInventory().getGoldInPocket() >= cost, 10, 'repair gold')
    hp, paid = yield from sailing.repair(H, uid, sid)
    mx = getattr(H.cr.getOwnerView(sid), 'maxHp', None)
    ok = bool(hp and mx and hp >= BREAK * mx)
    H.ev('REPAIR', ok=ok, hp0=hp0, hp=hp, maxHp=mx, paid=paid, cost=cost, port=name)
    return 'ok' if ok else 'failed'


def run(H):
    la = H.la
    H.ev('SHIPFIGHT-START', frm=FROM, secs=SECS, gold=s_lanes.gold(H), here=H.area(), gs=la.getGameState(),
         myLevel=la.getLevel(), gap=LEVEL_GAP, brk=BREAK, rng=RANGE, repairs=REPAIRS, leash=LEASH, patrol=PATROL_R,
         ports=PORTS, loss=(LOSS, LOSS_SECS), danger=(DANGER_R, DANGER_GAP, DANGER_HP),
         close=(CLOSE_SECS, CLOSE_GAIN), finish=(FINISH, FINISH_HULL))
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    if not ships:
        H.ev('FAIL', why='the pirate owns no ship (Chapter 2 c2.9visitDarby gives the first one)'); return
    sid = ships[0]
    if not (yield from s_lanes.onIsland(H, 'shipfight', FROM)):
        H.ev('FAIL', why='could not get to %s' % FROM, area=H.area()); return
    s_lanes.stage(H, 'shipfight', 'at-island', island=FROM, ships=ships)

    # watch hunt()'s own lines as they are written
    got = {}
    beam = [0, 0]                       # shots on the beam, all shots
    orig = H.ev
    names = set()

    def ev(kind, /, **kw):
        if kind == 'FOE-SUNK' and kw.get('gone') and picker.lost(kw.get('foe')):
            # hunt() counts a target that left the client's view as sunk; one far off or well afloat only sailed off
            kind = 'FOE-LOST'
            kw['last'] = picker.first.get(kw.get('foe'))
        got[kind] = got.get(kind, 0) + 1
        if kind == 'FOE-SUNK' and picker.sunk is None:
            picker.sunk = (kw.get('foe'),) + picker.info.get(kw.get('foe'), (None, '', None))
        if kind == 'BROADSIDE':
            beam[1] += 1
            beam[0] += onBeam(kw.get('brg'))
        r = orig(kind, **kw)
        for what in seen(names, set(got)):
            names.add(what)
            s_lanes.stage(H, 'shipfight', what, **({'foe': kw.get('foe')} if 'foe' in kw else {}))
        return r
    H.ev = ev
    t0 = time.time()
    picker = Picker(H, t0)
    why, breaks, retakes = None, 0, 0
    gold0 = s_lanes.gold(H)
    goldB = gold0
    try:
        while True:
            left = SECS - (time.time() - t0)
            if left < 30:
                why = why or 'timeout'
                break
            picker.wheel = None
            goldB = s_lanes.gold(H)         # job 23a: gold as this fight begins (after any repair)
            why = yield from fight(H, sid, left, got, picker)
            if why == 'left-ship':
                wh = picker.wheel or {}
                ok, rwhy = canRetake(wh.get('inWorld'), wh.get('aboard'), wh.get('hp'), retakes)
                H.ev('RETAKE-WHEEL', ok=ok, why=rwhy, n=retakes + 1 if ok else retakes, foe=picker.top,
                     left=round(left))
                if ok:
                    retakes += 1
                    yield 2                 # let the exit finish before the walk back to the wheel
                    continue
                break
            if why != 'break-off':
                break
            breaks += 1
            s_lanes.stage(H, 'shipfight', 'broke-off', n=breaks)
            if breaks > REPAIRS:
                why = 'broke off %d times' % breaks
                break
            r = yield from repairAt(H, sid, picker)
            if r != 'ok':
                why = 'sunk-going-home' if r == 'sunk' else 'repair-failed'
                break
            s_lanes.stage(H, 'shipfight', 'repaired', n=breaks)
            picker.top = None
    finally:
        H.ev = orig
    gain = None
    if why == 'foe-sunk':
        s_lanes.stage(H, 'shipfight', 'stopped', why='first foe sunk')
        after, changes = yield from plunderWait(H, PLUNDER_SECS, hull=lambda: shipHp(H, sid))
        sk = picker.sunk or (None, None, '', None)
        gain, exp, gok = goldCheck(goldB, after, sk[1])
        H.ev('SHIP-GOLD', start=gold0, before=goldB, after=after, gain=gain, foe=sk[0], level=sk[1], foeName=sk[2],
             shipClass=sk[3], expect=exp, ok=gok, waited=PLUNDER_SECS, changes=changes)
    lv = sorted(l for l in picker.levels if l is not None)
    H.ev('SHIPFIGHT-END', why=why, sunk=got.get('FOE-SUNK', 0), lost=got.get('FOE-LOST', 0), shots=beam[1],
         onBeam=beam[0], rams=got.get('RAM', 0), breaks=breaks, retakes=retakes, seen=got.get('ship-seen', 0), levels=lv,
         secs=round(time.time() - t0), gs=la.getGameState(), area=H.area())
    if why == 'foe-sunk':
        H.ev('PASS', what='sank one enemy ship', shots=beam[1], onBeam=beam[0], breaks=breaks,
             secs=round(time.time() - t0), gold=gain)
    elif why == 'launch-failed':
        H.ev('FAIL', why='the ship did not launch (a SAIL-FAIL line says why)')
    elif why == 'our-ship-sunk':
        H.ev('FAIL', why='our ship sank before it sank one', shots=beam[1], breaks=breaks)
    elif why == 'sunk-going-home':
        H.ev('FAIL', why='our ship sank on the way home to repair (the REPAIR line says how far out and who was near)',
             shots=beam[1], breaks=breaks)
    elif why == 'left-ship':
        H.ev('FAIL', why='lost the wheel mid-fight and could not take it again (WHEEL-EXIT and RETAKE-WHEEL say why)',
             shots=beam[1], retakes=retakes)
    elif why == 'repair-failed':
        H.ev('FAIL', why='broke off but the ship was not mended (a REPAIR line says why)', breaks=breaks)
    elif why and why.startswith('broke off'):
        H.ev('FAIL', why='%s without sinking one (SHIPFIGHT_REPAIRS=%d)' % (why, REPAIRS), shots=beam[1])
    elif not got.get('SHIP-TARGET'):
        H.ev('FAIL', why='no fair enemy ship came in sight in %d s (%s)' % (SECS, why), seen=got.get('ship-seen', 0),
             levels=lv)
    else:
        H.ev('FAIL', why='fought but sank none in %d s (%s)' % (SECS, why), shots=beam[1])


def questHunt(H, qid, task, secs):
    """Generator, pir-bot job 30: the story's ship quests (sink N Navy / EITC ships, capture a captain, recover a
    ship's cargo such as Bonita's copper rod) fought the careful way this lane fights: the Picker ranks only the ships
    the quest's task counts (s_shipquest.matches: faction, hull, level, flagship) and keeps the fair-foe pick, the
    beam hold, the break-off, the repair at the nearest port and the retake of a lost wheel. Every one of these tasks
    is credited by a sink (QuestTaskDNA.handleShipDefeat; capture and recover roll a chance per sink and are sure by
    maxAttempts), so there is no boarding: sink, wait for the plunder, look at the quest.
    After every sink: SHIP-GOLD (q, n, before, after, gain, the sunk foe, 0200's expect, ok, prog before / after).
    Stops on the quest's progress moving ('credit'; 'complete' once the quest is gone) so s_story's own loop sees
    it, or our ship sinking, or secs. -> 'credit' / 'complete' / 'timeout' / 'launch-failed' / 'our-ship-sunk' /
    'left-ship' / 'broke off N times' / 'repair-failed' / 'sunk-going-home' / 'no-target' (job 43).
    Lines: SHIP-QUEST-START, the fight's own lines (SHIP-HUNT, FOE-PICK, BROADSIDE, FOE-SUNK, BREAK-OFF, REPAIR ...),
    SHIP-GOLD per sink, SHIP-QUEST-END (why, sinks, gold start / end, prog)."""
    LAST.clear()
    la = H.la
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    gold0 = s_lanes.gold(H)
    p0 = s_shipquest.prog(H, qid)
    H.ev('SHIP-QUEST-START', q=qid, task=type(task).__name__, faction=str(getattr(task, 'faction', None)),
         hull=getattr(task, 'hull', None), level=getattr(task, 'level', 0), num=getattr(task, 'num', None),
         maxAttempts=getattr(task, 'maxAttempts', None), gold=gold0, prog=p0, myLevel=la.getLevel(), secs=round(secs))
    if not ships:
        H.ev('SHIP-QUEST-END', q=qid, why='launch-failed', sinks=0, note='the pirate owns no ship')
        return 'launch-failed'
    sid = ships[0]
    got = {}
    orig = H.ev
    t0 = time.time()
    picker = Picker(H, t0, task=task)
    if picker.far:
        H.ev('SHIP-QUEST-FAR', q=qid, why=picker.farWhy, note='the ships this quest counts never enter the starter '
             'waters: no leash, search route past them')

    def ev(kind, /, **kw):
        if kind == 'FOE-SUNK' and kw.get('gone') and picker.lost(kw.get('foe')):
            kind = 'FOE-LOST'
            kw['last'] = picker.first.get(kw.get('foe'))
        got[kind] = got.get(kind, 0) + 1
        if kind == 'FOE-SUNK' and picker.sunk is None:
            picker.sunk = (kw.get('foe'),) + picker.info.get(kw.get('foe'), (None, '', None))
        return orig(kind, **kw)
    H.ev = ev
    why, sinks, breaks, retakes = None, 0, 0, 0
    try:
        while True:
            left = secs - (time.time() - t0)
            if left < 30:
                why = why if why in ('credit', 'complete') else 'timeout'
                break
            picker.wheel, picker.sunk = None, None
            goldB, pB, n0 = s_lanes.gold(H), s_shipquest.prog(H, qid), got.get('FOE-SUNK', 0)
            why = yield from fight(H, sid, left, got, picker, qid=qid, task=task)
            if sinkCount(why, got.get('FOE-SUNK', 0) > n0):
                sinks += 1
                after, changes = yield from plunderWait(H, PLUNDER_SECS, hull=lambda: shipHp(H, sid))
                sk = picker.sunk or ((picker.top,) + picker.info.get(picker.top, (None, '', None)))
                gain, exp, gok = goldCheck(goldB, after, sk[1])
                pA = s_shipquest.prog(H, qid)
                H.ev('SHIP-GOLD', q=qid, n=sinks, before=goldB, after=after, gain=gain, foe=sk[0], level=sk[1],
                     foeName=sk[2], shipClass=sk[3], expect=exp, ok=gok, waited=PLUNDER_SECS, changes=changes,
                     progBefore=pB, progAfter=pA)
                if pA is None:
                    why = 'complete'
                    break
                if pA != pB or why in ('credit', 'complete'):
                    why = 'credit'
                    break
                picker.top = None
                continue            # a sink that did not count yet (a capture / cargo roll missed): sink the next
            if why == 'left-ship':
                wh = picker.wheel or {}
                ok, rwhy = canRetake(wh.get('inWorld'), wh.get('aboard'), wh.get('hp'), retakes)
                H.ev('RETAKE-WHEEL', ok=ok, why=rwhy, n=retakes + 1 if ok else retakes, foe=picker.top, left=round(left))
                if ok:
                    retakes += 1
                    yield 2
                    continue
                break
            if why != 'break-off':
                break
            breaks += 1
            if breaks > REPAIRS:
                why = 'broke off %d times' % breaks
                break
            r = yield from repairAt(H, sid, picker)
            if r != 'ok':
                why = 'sunk-going-home' if r == 'sunk' else 'repair-failed'
                break
            picker.top = None
    finally:
        H.ev = orig
    LAST.update(q=qid, why=why, matchLevels=sorted(int(picker.info[i][0]) for i in picker.matchSeen
                                                   if i in picker.info and picker.info[i][0] is not None),
                picked=picker.top)
    H.ev('SHIP-QUEST-END', q=qid, why=why, sinks=sinks, lost=got.get('FOE-LOST', 0), shots=got.get('BROADSIDE', 0),
         breaks=breaks, retakes=retakes, far=picker.far, matched=len(picker.matchSeen), matchLevels=LAST['matchLevels'],
         seen=picker.seenSummary(),
         gold0=gold0, gold=s_lanes.gold(H), before=p0, after=s_shipquest.prog(H, qid),
         secs=round(time.time() - t0), gs=la.getGameState(), area=H.area())
    return why
