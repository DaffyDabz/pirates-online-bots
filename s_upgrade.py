"""UPG1 (places lane, 11-21): the story pirate gets the biggest ship his Sailing level and gold allow.
MAIN5 (11-21 08:00) stalled at Splinter (c3r2r5r2.5recoverSplinter): the Undead ships there are lv18-21, his Light
Sloop (2400 hp) lost 500-750 hp per 10 s and sank none. The level grind proves nothing about the quests, so (brain
decision 11-21) his Sailing level is raised with the game's own admin word and he buys a bigger ship with his own gold.

Test pirate 100000596 only (never 100000170 or ship 100000173). On Port Royal:
 1. Sailing to UPG_SAILING (15) by `level 13712 <n>` (MW-LEVEL, logged); the game's own setReputation path.
 2. pick(): the biggest shelf class he can afford with the gold he has and the level he now has (no gold word).
    With 24k gold at Sailing 15 that is the War Sloop (3, 20000); War Galleon 40000, War Frigate 60000.
 3. A ship of that class or bigger already in his list is kept (UPG-HAVE); else he buys it at the shipwright through
    his store (s_activities.buySloop), as boats' EVERY1 does.
UPG-SHIP carries the ship id the story chunks then sail (BOT_SHIP). PASS when he owns it.
env: UPG_SAILING (15)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0])))

NEED = int(os.environ.get('UPG_SAILING', '15'))
PR = '1150922126.8dzlu'
PIRATE = 100000596
NEVER_PIRATE, NEVER_SHIP = 100000170, 100000173
BIG = (23, 13, 3, 22, 12, 2, 21, 11, 1)    # the shipwright's shelf, biggest first


# ------------------------------------------------------------------------------------------------ pure
def pick(gold, level, cost, minLevel):
    """Pure: the biggest shelf class his level allows and his gold pays for. -> class or None."""
    for c in BIG:
        price = cost(c)
        if price is not None and price <= gold and (minLevel(c) or 0) <= level:
            return c
    return None


def have(ships, c):
    """Pure: a ship of class c or a bigger one already in his list [(id, class, ...)]. -> id or None."""
    ok = BIG[:BIG.index(c) + 1]
    for s in ships:
        if s[1] in ok and s[0] != NEVER_SHIP:
            return s[0]
    return None


# ------------------------------------------------------------------------------------------------ the run
def run(H):
    import sailing, s_lanes
    import s_activities as A
    import s_everyship as E
    EG, IG, IT, RG, PGG = A._game()
    la = H.la
    if la.doId != PIRATE or la.doId == NEVER_PIRATE:
        H.ev('FAIL', why='UPG1 runs on the story pirate %d only, not %d' % (PIRATE, la.doId)); return
    yield ('upto', lambda: all(s[1] is not None for s in A.shipList(H)), 60)
    start = A.shipList(H)
    H.ev('UPG-START', gold=s_lanes.gold(H), sailing=A.sailLevel(H, RG, IT), ships=[list(s[:4]) for s in start],
         here=H.area())
    if any(s[0] == NEVER_SHIP for s in start):
        H.ev('FAIL', why='ship %d is in this list' % NEVER_SHIP); return
    if not sailing.onShip(H) and sailing.hereUid(H) != PR:
        if not (yield from s_lanes.onIsland(H, 'upgrade', PR)):
            H.ev('FAIL', why='could not get onto Port Royal', area=H.area()); return
    # 1. Sailing level
    if A.sailLevel(H, RG, IT) < NEED:
        H.ev('MW-LEVEL', why='a bigger ship for Splinter needs Sailing %d' % NEED, sailing=A.sailLevel(H, RG, IT))
        H.mw('level %d %d' % (IT.SailingRep, NEED))
        yield ('until', lambda: A.sailLevel(H, RG, IT) >= NEED, 10, 'sailing level')
    lvl, gold = A.sailLevel(H, RG, IT), s_lanes.gold(H)
    # 2. which ship
    c = pick(gold, lvl, EG.getItemCost, EG.getItemMinLevel)
    H.ev('UPG-PICK', cls=c, name=E.NAMES.get(c), cost=c and EG.getItemCost(c), gold=gold, sailing=lvl)
    if c is None:
        H.ev('FAIL', why='no shelf ship for Sailing %d and %d gold' % (lvl, gold)); return
    # 3. keep or buy
    sid = have(start, c)
    if sid is not None:
        H.ev('UPG-HAVE', ship=sid, cls=[s[1] for s in start if s[0] == sid][0])
    else:
        npc = yield from E.toWright(H)
        if npc is None:
            H.ev('FAIL', why='could not reach the Port Royal shipwright'); return
        sid = yield from A.buySloop(H, npc, EG, IG, PGG, c)
        if sid is None:
            H.ev('FAIL', why='could not buy class %d at the shipwright' % c); return
    H.ev('UPG-SHIP', ship=sid, cls=c, name=E.NAMES.get(c), gold=s_lanes.gold(H), sailing=A.sailLevel(H, RG, IT),
         ships=[list(s[:4]) for s in A.shipList(H)])
    H.ev('PASS', what='story pirate at Sailing %d owns ship %d (%s)' % (A.sailLevel(H, RG, IT), sid, E.NAMES.get(c)))
