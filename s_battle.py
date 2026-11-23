"""Enemy ship battle proof: do enemy ships come after you and hit you, the way they should?
Launch at Port Royal's dinghy like a player (sailing.launch), tap W for full sail and steer with A / D at the nearest
enemy ship ('NPCShip'), round any island in the way. With none in sight, sail out to open sea away from the island.
Once one is within BATTLE_ENGAGE ft, tap S (drop sail) and let it fight for BATTLE_FIGHT seconds.
Every second: our Hp, the nearest enemy's distance and speed (ft/s, from its position change), and how far its bow
points off us. Events: BATTLE-START, foe-seen, b (every 1 s), hit (each Hp drop), engage, then PASS or FAIL.
PASS = our Hp dropped while an enemy was within BATTLE_HIT_R ft (it fired on us and hit). FAIL says why.
env: BATTLE_HUNT (s to find and close on an enemy, default 300), BATTLE_FIGHT (default 90), BATTLE_ENGAGE (1500),
     BATTLE_HIT_R (2500)."""
import os, sys, time, math
from panda3d.core import Point3, Vec3

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402
from s_dock import Keys, cls   # noqa: E402

PR = '1150922126.8dzlu'
HUNT = float(os.environ.get('BATTLE_HUNT', '300'))
FIGHT = float(os.environ.get('BATTLE_FIGHT', '90'))
ENGAGE = float(os.environ.get('BATTLE_ENGAGE', '1500'))
HIT_R = float(os.environ.get('BATTLE_HIT_R', '2500'))
SEE_R = 6000.0          # enemies farther than this are ignored (out of interest anyway)


def foes(H, ship):
    """[(dist, enemy)] nearest first: every NPC ship within SEE_R."""
    p = ship.getPos(H.render)
    out = []
    for o in list(H.cr.doId2do.values()):
        if o is ship or 'NPCShip' not in cls(o) or not hasattr(o, 'getPos'):
            continue
        try:
            d = (o.getPos(H.render) - p).length()
        except Exception:
            continue
        if d < SEE_R:
            out.append((d, o))
    out.sort(key=lambda t: t[0])
    return out


def aimOff(H, foe, ship):
    """Degrees between the enemy's bow and the line from it to us (0 = bow on, 90 = broadside on)."""
    rel = foe.getRelativePoint(H.render, ship.getPos(H.render))
    return abs(math.degrees(math.atan2(rel[0], rel[1])))


def run(H):
    la = H.la
    R = H.render
    yield ('until', lambda: la.getGameState() in ('LandRoam', 'ShipPilot'), 60, 'LandRoam')
    aboard = sailing.onShip(H)
    if not aboard and sailing.hereUid(H) != PR:      # the game's own teleport to Port Royal's open ground
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
    gold = la.getInventory().getGoldInPocket()
    if not aboard and gold < 500:
        # test setup: the test pirate has no gold, so the shipwright refused to mend its sunk ship (BATTLE2, 11-16);
        # a kid this far into the story has quest gold
        H.mw('gold 2000')
        yield 3
        H.ev('SETUP-GOLD', before=gold, after=la.getInventory().getGoldInPocket())
    ship = yield from sailing.launch(H, sailing.hereUid(H), aboard)
    if ship is None:
        H.ev('FAIL', why='could not launch the ship (see SAIL-FAIL)'); return
    sid = ship.doId
    keys = Keys(H)
    tbl = sailing.islands()
    obst = [(x, y, sailing.OBST_R if n else 900) for u, (n, x, y, f) in tbl.items()]
    _, px, py, _ = tbl[PR]
    hp0 = getattr(ship, 'Hp', None)
    H.ev('BATTLE-START', ship=sid, hp=hp0, maxHp=getattr(ship, 'maxHp', None), pos=H.P(ship))
    messenger.send('w'); messenger.send('w-up')      # tap W: full sail
    st = {'hits': 0, 'hpLost': 0, 'hitNear': 0, 'minFoe': None, 'foeVmax': 0.0, 'seen': {}, 'hitLog': []}
    last = {'hp': hp0, 't': time.time(), 'foe': None, 'fpos': None}
    phase, t0, tf = 'hunt', time.time(), None

    def gone():
        return H.cr.doId2do.get(sid) is None or la.getGameState() != 'ShipPilot'

    while True:
        now = time.time()
        if gone():
            H.ev('left-ship', gs=la.getGameState(), hp=getattr(ship, 'Hp', None), phase=phase)
            break
        p = ship.getPos(R)
        fl = foes(H, ship)
        for d, o in fl:
            if o.doId not in st['seen']:
                st['seen'][o.doId] = getattr(o, 'name', '')
                H.ev('foe-seen', doId=o.doId, foeName=getattr(o, 'name', ''), level=getattr(o, 'level', None),
                     dist=round(d), pos=H.P(o), cls=cls(o))
        nd, nf = fl[0] if fl else (None, None)
        if nd is not None:
            st['minFoe'] = nd if st['minFoe'] is None else min(st['minFoe'], nd)
        # enemy speed from its own position change (same enemy as last sample only)
        fv = None
        if nf is not None and last['foe'] == nf.doId and last['fpos'] is not None and now > last['t']:
            fp = nf.getPos(R)
            fv = (Vec3(fp[0] - last['fpos'][0], fp[1] - last['fpos'][1], 0)).length() / (now - last['t'])
            st['foeVmax'] = max(st['foeVmax'], fv)
        hp = getattr(ship, 'Hp', None)
        if hp is not None and last['hp'] is not None and hp < last['hp']:
            lost = last['hp'] - hp
            st['hits'] += 1
            st['hpLost'] += lost
            if nd is not None and nd < HIT_R:
                st['hitNear'] += 1
            H.ev('hit', lost=lost, hp=hp, foeDist=None if nd is None else round(nd), foe=None if nf is None else nf.doId, phase=phase)
        try:
            vel = ship.node().getPhysicsObject().getVelocity().length()
        except Exception:
            vel = 0
        if phase == 'hunt':
            if nf is not None and nd < ENGAGE:
                keys.release()
                messenger.send('s'); messenger.send('s-up')      # tap S: drop sail, let it come to us
                phase, tf = 'fight', now
                H.ev('engage', foe=nf.doId, foeName=getattr(nf, 'name', ''), dist=round(nd), hp=hp, secs=round(now - t0))
            else:
                if nf is not None:
                    goal = nf.getPos(R)
                else:       # nobody in sight: open sea, straight out from Port Royal
                    out = Vec3(p[0] - px, p[1] - py, 0)
                    if out.length() < 1:
                        out = Vec3(0, 1, 0)
                    out.normalize()
                    goal = Point3(px + out[0] * 9000, py + out[1] * 9000, 0)
                tgt, mode = sailing.route(p, goal, obst)
                keys.steer(ship, tgt)
                if now - t0 > HUNT:
                    H.ev('hunt-timeout', seen=len(st['seen']), minFoe=None if st['minFoe'] is None else round(st['minFoe']))
                    break
        elif now - tf > FIGHT:
            break
        H.ev('b', ph=phase, pos=[round(p[0]), round(p[1])], vel=round(vel, 1), hp=hp,
             foe=None if nf is None else nf.doId, fd=None if nd is None else round(nd),
             fv=None if fv is None else round(fv, 1), aim=None if nf is None else round(aimOff(H, nf, ship)), n=len(fl))
        last.update(hp=hp, t=now, foe=None if nf is None else nf.doId, fpos=None if nf is None else nf.getPos(R))
        yield 1.0
    keys.release()
    res = dict(hits=st['hits'], hpLost=st['hpLost'], hitNear=st['hitNear'], hp0=hp0, hp=getattr(ship, 'Hp', None),
               enemiesSeen=len(st['seen']), minFoe=None if st['minFoe'] is None else round(st['minFoe']),
               foeVmax=round(st['foeVmax'], 1), fought=tf is not None, secs=round(time.time() - t0))
    if st['hitNear'] > 0:
        H.ev('PASS', **res)
    else:
        why = ('no enemy ship found' if not st['seen'] else
               'never got within %d ft of an enemy' % ENGAGE if tf is None else
               'enemy close but never hit us')
        H.ev('FAIL', why=why, **res)
