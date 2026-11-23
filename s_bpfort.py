"""BPFORT (pir-bot job 34, 11-19): the Black Pearl voyage's stage three played: the ship's cannon fired at a barricade
fort until it falls, the fort's hp logged after every hit. The proof for server patch 0310.

0310 (pir-ships README): DistributedFortAI.hitByProjectile took 3 arguments (skillId, ammoSkillId, attackerDoId) but
the client sends 2 (DistributedFort.sendHitByProjectile(skillId, ammoSkillId)), so the first cannonball that hit a
fort kicked the pirate. With 0310 attackerDoId defaults to the sender, and each hit takes 500 hp
(TreasureMapBlackPearlGlobals: small fort 5000 = 10 hits, medium 7500 = 15, large 10000 = 20).

Client facts this rests on (client tree, read 11-19):
- The instance (TreasureMapBlackPearl) has fortIds; each DistributedFort has objKey (its world uid), hp, maxHp and
  fortNode (the island's '=uid=<objKey>' node). barricadesDestroyed lists the barricades that fell.
- FortPairsDict (barricade -> its 2 forts): fort 0B is shared by barricades 0 and 1 and a hit on it counts for 0 only,
  so the forts hit here are the un-shared ones: 0A '1175905981.42kmuller' (barricade 0) and 2A
  '1175906682.53kmuller' (barricade 2). One barricade on each path opens stage four.
- The Black Pearl (an NPC ship on the players' team) has deck cannons (DistributedShipCannon). Manning one is
  requestInteraction(avId) (the server's handleRequestInteraction accepts anyone), fireCannon() fires along the
  cannon's hNode heading and pivot pitch, volley counts the balls before a reload, requestExit() leaves it.
- A ball that strikes a fort's collision calls fort.gotHitByProjectile -> sendHitByProjectile(skillId, ammoSkillId),
  the one message 0310 fixes.

BPFORT_MODE (also STORY_BOSS_FORT in s_cards.boss):
  cannon  man the Pearl's cannon nearest the fort, aim at the fort, sweep the pitch until a shot takes hp, then keep
          firing at that pitch (default for this step)
  wire    the client's own hit message, fort.sendHitByProjectile(CannonShoot, CannonRoundShot), once a reload
          (1.5 s): the exact bytes a cannonball hit sends, without the aiming
  The proof is the cannon: only real cannonballs fired from the Pearl's cannon prove 0310 (no magic word).
  When the cannon cannot bring a fort down (no cannon, no shot took hp in the whole sweep, or out of time), the step
  falls back so the voyage can go on, logged FALLBACK (how, why, proof=False):
    BPFORT_FALLBACK=bpdestroy (default) the test word ~bpdestroy <barricade>; wire = the client's hit message; none.
  Any FALLBACK, or wire mode, means the run is NOT a 0310 proof: BOSS-FORT proof=False and the standalone run FAILs.
Lines: BPFORT-START, FORT-TARGET (uid, barricade, hp, maxHp, distance), FORT-STATE (hit boxes set up, aim source), FORT-CANNON (the manned cannon), FORT-SHOT
(shot n, pitch), FORT-HIT (uid, barricade, before, after, drop, via, shot, pitch, mine), FORT-DOWN, FORT-KICK (the
connection or the pirate is gone: the 0310 bug), FALLBACK, BOSS-FORT (the summary, with proof), then PASS / FAIL.
judgeFort(events) (pure): each of our hits took 500 hp (or the rest), every fort fell, no kick (the fight worked).
proofOf(events) (pure): judgeFort ok, no FALLBACK, every hit of ours by the cannon (the 0310 proof).
Standalone (BPFORT as its own run): test pirates only (never 100000170). In by the Black Pearl map's Play Now when
the pirate holds the map, else ~blackpearlai; stages one and two ended with s_cards' words; then the forts.
env: BPFORT_MODE (cannon), BPFORT_BARRICADES (0,2), BPFORT_SECS (300 a fort), BPFORT_FALLBACK (bpdestroy), BPFORT_LEAVE (1)."""
import math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0])))

MODE = os.environ.get('BPFORT_MODE', 'cannon').lower()
BARRICADES = [int(b) for b in os.environ.get('BPFORT_BARRICADES', '0,2').split(',') if b.strip()]
SECS = float(os.environ.get('BPFORT_SECS', '300'))
_FB = os.environ.get('BPFORT_FALLBACK', 'bpdestroy').lower()
FALLBACK = {'1': 'bpdestroy', '0': 'none', '': 'none'}.get(_FB, _FB)      # bpdestroy, wire or none
LEAVE = os.environ.get('BPFORT_LEAVE', '1') == '1'
PROBE = os.environ.get('BPFORT_PROBE', '0') == '1'
HOST_AV = 100000170
BP_ISLAND = '1171761224.13sdnaik'
# world data (BlackpearlIsland.py), island-relative: every fort is 2000-6000 ft from the bay where the pirate lands
FORT_POS = {'1175905981.42kmuller': (2028, -2122, 104), '1175906682.53kmuller': (1976, -3820, 55)}
HIT = 500                          # DistributedFortAI: hp a cannonball hit takes
# barricade -> the fort to hit (FortPairsDict's first fort that is not shared with a lower barricade)
FORT_OF = {0: '1175905981.42kmuller', 1: '1171851678.08sdnaik', 2: '1175906682.53kmuller',
           3: '1175906834.64kmuller', 4: '1175908312.45kmuller'}
CANNON_SHOOT, CANNON_ROUND = 12900, 12901    # InventoryType.CannonShoot / CannonRoundShot
WIRE_GAP = 1.5                     # s between wire hits (about a reload)
SHOT_WAIT = 5.0                    # s a shot may take to land before it counts as a miss
PITCHES = (0, 3, 6, 9, 12, 15, 18, 22, 26, 30, -3)   # degrees above the straight line to the fort
MISSES_TO_RESWEEP = 3
K0 = 1.07e-4                       # the ball's drop (g / 2v^2) fitted from BPFORT10's landings; each landing refits it
LAND_WAIT = 8.0                    # s a ball may take to land
SPOT_SHOTS = 12                    # shots one cannon gets before the next is tried
OUT_OF_ARC = 2                     # shots in a row its arc cannot follow before the next cannon is tried
MAX_CANNONS = 4


# ------------------------------------------------------------------------------------------------ pure
def hitsToFall(maxHp, hit=HIT):
    """Hits a fort of maxHp takes to fall."""
    return int(math.ceil(float(maxHp) / hit)) if maxHp and hit else 0


def dropOk(before, after, hit=HIT):
    """True when one hit took what a cannonball takes: hit hp, or the rest when less was left."""
    if before is None or after is None:
        return False
    return before - after == min(hit, before) and after >= 0


def nextPitch(plan, idx, hitAt):
    """The pitch for the next shot and the next sweep index: the one that hit, once one has, else the next untried one
    (None when the sweep is spent)."""
    if hitAt is not None:
        return hitAt, idx
    if idx >= len(plan):
        return None, idx
    return plan[idx], idx + 1


def heading(dx, dy):
    """Panda's H of a level direction (H 0 = +y, H 90 = -x)."""
    return math.degrees(math.atan2(-dx, dy))


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def fitK(D, theta, dz):
    """K = g / (2 v^2) from one landing: a ball launched theta degrees up lands D ft out, dz ft above its exit point.
    BPFORT10's 11 sea landings (pitch 3-23, 640-4050 ft) all fit K = 1.0-1.1e-4. None when the landing says nothing."""
    t = math.tan(math.radians(theta))
    if D <= 1:
        return None
    k = (D * t - dz) / (D * D * (1 + t * t))
    return k if k > 0 else None


def heightAt(K, x, theta):
    """How high (ft above the exit point) a ball launched theta degrees up is x ft out."""
    t = math.tan(math.radians(theta))
    return x * t - K * x * x * (1 + t * t)


def solvePitch(K, x, dz):
    """-> (theta, reachable): the low launch angle that puts the ball dz ft up at x ft out; when no angle does, the
    angle that gets it highest there (and False)."""
    a = K * x * x
    if a <= 0:
        return 0.0, False
    disc = x * x - 4 * a * (a + dz)
    if disc < 0:
        return math.degrees(math.atan(x / (2 * a))), False
    return math.degrees(math.atan((x - math.sqrt(disc)) / (2 * a))), True


def spot(E, L, T, K, theta, gain=1.0):
    """One shot's correction (pure). E = exit point, L = where the ball landed, T = the target (x, y, z), theta = the
    launch angle (render P) it flew at. -> {dH (add to the cannon's heading), K (refit from this landing, else the
    old one), theta (the next launch angle), reach, missH (ft left/right), missR (ft long + / short -)}."""
    dxL, dyL = L[0] - E[0], L[1] - E[1]
    dxT, dyT = T[0] - E[0], T[1] - E[1]
    dH = wrap(heading(dxT, dyT) - heading(dxL, dyL)) * gain
    D, x = math.hypot(dxL, dyL), math.hypot(dxT, dyT)
    k = fitK(D, theta, L[2] - E[2]) or K
    th, reach = solvePitch(k, x, T[2] - E[2])
    side = math.sin(math.radians(wrap(heading(dxL, dyL) - heading(dxT, dyT)))) * D
    return {'dH': round(dH, 2), 'K': k, 'theta': round(th, 2), 'reach': reach, 'missH': round(side, 1),
            'missR': round(D - x, 1)}


def judgeFort(events, hit=HIT):
    """events = this run's event rows ({'ev':..., ...}). -> (ok, why, forts) with forts = {uid: summary}.
    OK when no FORT-KICK, every FORT-TARGET fort has a FORT-DOWN, at least one hit of ours landed on each, and each of
    our hits (mine=True) took hit hp (or the rest)."""
    forts = {}
    kicks = [e for e in events if e.get('ev') == 'FORT-KICK']
    for e in events:
        k = e.get('ev')
        uid = e.get('uid')
        if k == 'FORT-TARGET':
            forts.setdefault(uid, {'barricade': e.get('barricade'), 'maxHp': e.get('maxHp'), 'hits': 0, 'bad': [],
                                   'down': False, 'other': 0})
        elif k == 'FORT-HIT' and uid in forts:
            f = forts[uid]
            if e.get('mine'):
                f['hits'] += 1
                if not dropOk(e.get('before'), e.get('after'), hit):
                    f['bad'].append((e.get('before'), e.get('after')))
            else:
                f['other'] += 1
        elif k == 'FORT-DOWN' and uid in forts:
            forts[uid]['down'] = True
            if e.get('already') and not forts[uid]['hits']:
                forts[uid]['already'] = True     # down before we came: nothing to prove on it
        elif k == 'FALLBACK' and uid in forts and str(e.get('how', '')).startswith('bpdestroy'):
            forts[uid]['word'] = True            # the test word took it down: it fell, no hits of ours to judge
    if kicks:
        return False, 'kicked: %s' % kicks[0].get('why'), forts
    if not forts:
        return False, 'no fort was targeted', forts
    if all(f.get('already') for f in forts.values()):
        return False, 'every fort was down already: nothing proven', forts
    for uid, f in sorted(forts.items()):
        if f.get('already'):
            continue
        if f.get('word') and not f['hits']:
            if not f['down']:
                return False, 'fort %s did not fall to ~bpdestroy either' % uid, forts
            continue
        if not f['hits']:
            return False, 'no hit of ours landed on fort %s' % uid, forts
        if f['bad']:
            return False, 'fort %s: a hit took the wrong hp %s' % (uid, f['bad'][0]), forts
        if not f['down']:
            return False, 'fort %s did not fall (%d hits)' % (uid, f['hits']), forts
    return True, '%d fort(s) fell, %d hits of %d hp, no kick' % (
        len(forts), sum(f['hits'] for f in forts.values()), hit), forts


# ------------------------------------------------------------------------------------------------ in the game
def connected(H):
    try:
        if hasattr(H.cr, 'isConnected') and not H.cr.isConnected():
            return False
    except Exception:
        pass
    la = getattr(H, 'la', None)
    return la is not None and not (hasattr(la, 'isEmpty') and la.isEmpty()) and H.cr.doId2do.get(la.doId) is la


def fortsOf(H, inst):
    """objKey -> the live DistributedFort of the instance."""
    out = {}
    for fid in list(getattr(inst, 'fortIds', None) or []):
        f = H.cr.doId2do.get(fid)
        if f is not None and getattr(f, 'objKey', None):
            out[f.objKey] = f
    return out


def uidNode(H, fort):
    """The island's model node for this fort (world data uid), loaded with the island's objects; None when absent."""
    isl = island(H)
    if isl is None:
        return None
    n = isl.find('**/=uid=%s' % fort.objKey)
    return None if n.isEmpty() else n


def boundsCentre(H, np, b):
    """A node's bounds centre in render. getBounds() is in the node's PARENT's space (it holds the node's own
    transform), so reading it from the node itself moved every point by that transform twice (sim 11-21)."""
    par = np.getParent()
    return H.render.getRelativePoint(par if not par.isEmpty() else H.render, b.getCenter())


def fortPoint(H, fort, why=False):
    """The fort's middle in render: its fortNode's bounds (set by the fort's own setupCollisions), else the island's
    node with the fort's uid, else its world-data spot on the island, else its own position. The last one is the
    island's middle: BPFORT8 (11-21) aimed there, about 40 degrees off fort 0A, and every shot missed."""
    for src, node in (('fortNode', getattr(fort, 'fortNode', None)), ('uidNode', uidNode(H, fort))):
        try:
            if node is not None and not node.isEmpty():
                b = node.getBounds()
                if not b.isEmpty():
                    pt = boundsCentre(H, node, b)
                    return (pt, src) if why else pt
        except Exception:
            pass
    isl = island(H)
    if isl is not None and fort.objKey in FORT_POS:
        from panda3d.core import Point3
        pt = H.render.getRelativePoint(isl, Point3(*FORT_POS[fort.objKey]))
        return (pt, 'worldData') if why else pt
    pt = fort.getPos(H.render)
    return (pt, 'ownPos') if why else pt


def fortState(H, fort):
    """Whether the fort can take a cannonball: DistributedFort.__setupIslandDependentObjects sets
    islandDependedObjectsSetup once its drawbridge piers are in render, and its setupCollisions tags the fort's
    collision nodes with fortId (gotHitByProjectile reads that tag). Before that no shot can count."""
    out = {'setup': getattr(fort, 'islandDependedObjectsSetup', 0)}
    fn = getattr(fort, 'fortNode', None)
    out['fortNode'] = fn is not None and not fn.isEmpty()
    un = uidNode(H, fort)
    out['uidNode'] = un is not None
    isl = island(H)
    out['level'] = getattr(isl, 'lastZoneLevel', None) if isl is not None else None
    try:
        out['tagged'] = H.render.findAllMatches('**/=fortId=%d' % fort.doId).getNumPaths()
    except Exception as e:
        out['tagged'] = repr(e)
    try:
        from pirates.treasuremap import TreasureMapBlackPearlGlobals as G
        out['piers'] = {n: not H.render.find('**/%s' % n).isEmpty() for n in G.DrawbridgeDict.get(fort.objKey, ())}
    except Exception as e:
        out['piers'] = repr(e)
    try:
        out['postLoad'] = len(H.cr.distributedDistrict.worldCreator.postLoadCalls)
    except Exception as e:
        out['postLoad'] = repr(e)
    pt, src = fortPoint(H, fort, why=True)
    out['aim'] = src
    out['d'] = round((pt - H.la.getPos(H.render)).length(), 1)
    return out


def fallen(inst, fort, barricade):
    return (fort.hp is not None and fort.hp <= 0) or barricade in list(getattr(inst, 'barricadesDestroyed', []) or [])


def cannons(H):
    """The deck cannons in view: DistributedShipCannon objects that have their model."""
    return [o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedShipCannon'
            and getattr(o, 'prop', None) is not None and hasattr(o, 'fireCannon')]


def pickCannon(H, pt):
    """The cannon to man: on the ship the pirate stands on when he is on one, else the nearest to him; of those the
    one nearest the fort."""
    la = H.la
    cs = cannons(H)
    mine = getattr(getattr(la, 'ship', None), 'doId', None)
    on = [c for c in cs if getattr(c, 'shipId', None) == mine] if mine else []
    if not on:
        me = la.getPos(H.render)
        on = [c for c in cs if (c.getPos(H.render) - me).length() < 120]
    if not on:
        return None
    return min(on, key=lambda c: (c.getPos(H.render) - pt).length())


def aim(H, c, pt, off):
    """Point the cannon at pt and raise it off degrees (the way the game's own AI aims, doAIAttack). -> the aim row.
    A manned ship cannon is held by CannonCamera.__moveCamera every frame: it sets hNode H and pivot P from
    ship.avCannonRotate and prop.currentHpr (clamped to the camera's minH..maxH, minP..maxP), so setting the nodes
    alone is undone the next frame (BPFORT9: 11 shots, 0 hits). The aim goes into that camera state too."""
    prop = c.prop
    prop.hNode.lookAt(H.render, pt)
    h, p = prop.hNode.getH(), prop.hNode.getP() + off
    prop.hNode.setP(0)
    prop.hNode.setR(0)
    prop.pivot.setP(p)
    ship = getattr(prop, 'ship', None)
    rot = getattr(ship, 'avCannonRotate', None) if ship is not None else None
    if rot is not None:
        rot.setH(h)
        rot.setP(p)
        prop.currentHpr = (h + getattr(prop, 'shipH', 0), prop.pivot.getP(H.render), 0)
    cam = getattr(getattr(H.la, 'cameraFSM', None), 'cannonCamera', None)
    lim = tuple(getattr(cam, n, None) for n in ('minH', 'maxH', 'minP', 'maxP'))
    arc = None not in lim and lim[0] <= h <= lim[1] and lim[2] <= p <= lim[3]
    return {'wantH': round(h, 1), 'wantP': round(p, 1), 'inArc': arc, 'arc': lim, 'held': rot is not None}


def aimNow(H, c):
    """The cannon's real aim now (what _doFireCannon sends): hNode H in its parent and render, pivot P."""
    prop = c.prop
    return {'gotH': round(prop.hNode.getH(), 1), 'gotP': round(prop.pivot.getP(), 1),
            'renderH': round(prop.hNode.getH(H.render), 1), 'renderP': round(prop.pivot.getP(H.render), 1)}


def arcOf(H):
    """The cannon camera's limits (minH, maxH, minP, maxP): how far a player can swing and raise a ship cannon."""
    cam = getattr(getattr(H.la, 'cameraFSM', None), 'cannonCamera', None)
    return tuple(getattr(cam, n, None) for n in ('minH', 'maxH', 'minP', 'maxP'))


def aimRaw(H, c, h, p):
    """Set the cannon to heading h (in its mount, as the camera's relH) and pivot pitch p, kept inside the arc a
    player has (arcOf) and written into the camera state that holds it every frame (see aim). -> (h, p, clamped)."""
    lim = arcOf(H)
    h0, p0 = h, p
    if None not in lim:
        h = max(lim[0], min(lim[1], h))
        p = max(lim[2], min(lim[3], p))
    prop = c.prop
    prop.hNode.setHpr(h, 0, 0)
    prop.pivot.setP(p)
    ship = getattr(prop, 'ship', None)
    rot = getattr(ship, 'avCannonRotate', None) if ship is not None else None
    if rot is not None:
        rot.setH(h)
        rot.setP(p)
        prop.currentHpr = (h + getattr(prop, 'shipH', 0), prop.pivot.getP(H.render), 0)
    return h, p, (h, p) != (h0, p0)


def relH(H, c, pt):
    """The heading (in the cannon's mount) that faces pt: what hNode H must be."""
    tmp = c.prop.hNode.getParent().attachNewNode('bpfortAim')
    try:
        tmp.lookAt(H.render, pt)
        return wrap(tmp.getH())
    finally:
        tmp.removeNode()


def exitPoint(H, c):
    prop = c.prop
    n = getattr(prop, 'cannonExitPoint', None)
    return tuple((n if n is not None else prop.pivot).getPos(H.render))


def rankCannons(H, pt):
    """The cannons to try, best first: on the ship the pirate stands on (else within 120 ft), the ones whose swing
    reaches pt first, then the smallest swing, then the nearest. BPFORT10 took the one nearest the fort by its object
    position (712 ft, wrong: its balls left from the Pearl 3330 ft out) and the fort was 92 deg round, past its 60."""
    la = H.la
    cs = cannons(H)
    mine = getattr(getattr(la, 'ship', None), 'doId', None)
    on = [c for c in cs if getattr(c, 'shipId', None) == mine] if mine else []
    if not on:
        me = la.getPos(H.render)
        on = [c for c in cs if (c.prop.getPos(H.render) - me).length() < 120]
    lim = arcOf(H)
    out = []
    for c in on:
        try:
            h = relH(H, c, pt)
        except Exception:
            continue
        inArc = None in lim or lim[0] <= h <= lim[1]
        out.append((not inArc, abs(h), (c.prop.getPos(H.render) - pt).length(), c, h))
    out.sort(key=lambda r: r[:3])
    return [(r[3], r[4]) for r in out]


def hitBoxes(H, fort):
    """The fort's hit boxes (its setupCollisions tags them fortId) -> [(name, centre (x, y, z), radius)] in render."""
    out = []
    try:
        nps = H.render.findAllMatches('**/=fortId=%d' % fort.doId)
    except Exception:
        return out
    for i in range(nps.getNumPaths()):
        np = nps.getPath(i)
        try:
            b = np.getBounds()
            if b.isEmpty():
                continue
            ctr = boundsCentre(H, np, b)
            par = np.getParent()
            rad = b.getRadius() * abs((par if not par.isEmpty() else np).getSz(H.render)) \
                if hasattr(b, 'getRadius') else 0.0
            out.append((np.getName(), tuple(ctr), rad))
        except Exception:
            pass
    return out


def pickBox(boxes, E, K, thMax):
    """The box to aim at from E: the nearest one a ball launched at most thMax degrees up reaches (its centre), else
    the one it comes closest to reaching. -> (box, theta, reach, short ft) or None."""
    best = None
    for b in boxes:
        x = math.hypot(b[1][0] - E[0], b[1][1] - E[1])
        dz = b[1][2] - E[2]
        th, reach = solvePitch(K, x, dz)
        ok = reach and th <= thMax
        top = max(heightAt(K, x, min(th, thMax)), heightAt(K, x, thMax))
        short = 0.0 if ok else round(dz - top, 1)
        key = (not ok, short if not ok else x)
        if best is None or key < best[0]:
            best = (key, b, round(th, 2), ok, short)
    return best[1:] if best else None


class Impacts:
    """Every ball of this cannon that strikes something: the cannon's own projectileHitEvent (WeaponBase accepts the
    same event and calls the fort's gotHitByProjectile for objType COLL_FORT)."""

    def __init__(self, H, c, fort, w, log):
        from direct.showbase.DirectObject import DirectObject
        self.H, self.fort, self.w, self.log = H, fort, w, log
        self.n = 0
        self.byShot = {}               # shot -> [(t, into, objType, at, mine)]: the spotter reads where each ball fell
        self.fortHits = 0
        self.do = DirectObject()
        self.do.accept(c.projectileHitEvent, self.hit)

    def hit(self, entry, *a):
        self.n += 1
        row = {'shot': self.w.shot, 'n': self.n}
        try:
            np = entry.getIntoNodePath()
            row['into'] = np.getName()
            row['objType'] = np.getNetTag('objType')
            row['fortId'] = np.getNetTag('fortId')
            row['mine'] = row['fortId'] == str(self.fort.doId)
            if row['mine']:
                self.fortHits += 1
            if entry.hasSurfacePoint():
                sp = entry.getSurfacePoint(self.H.render)
                row['at'] = [round(v, 1) for v in sp]
                row['toFort'] = round((sp - fortPoint(self.H, self.fort)).length(), 1)
                self.byShot.setdefault(row['shot'], []).append(
                    (time.time(), row['into'], row['objType'], tuple(sp), row['mine']))
        except Exception as e:
            row['err'] = repr(e)
        self.log('FORT-IMPACT', **row)

    def landing(self, shot, E, near=300.0):
        """Where this shot's ball came down: its first strike more than near ft (level) from the exit point E (the
        ball also clips the Pearl's own deck and panels on the way out: BPFORT10, 55 such). -> (x, y, z) or None."""
        for t, into, ot, at, mine in self.byShot.get(shot, ()):
            if mine or math.hypot(at[0] - E[0], at[1] - E[1]) > near:
                return at
        return None

    def stop(self):
        self.do.ignoreAll()


def ready(H, c):
    try:
        left = H.la.skillDiary.getTimeRemaining(c.skillId) or 0
    except Exception:
        left = 0
    return getattr(c, 'volley', 1) > 0 and left <= 0


def proofOf(events, hit=HIT):
    """-> (proof, why): True only when the forts fell to the Pearl's cannon alone: judgeFort ok, no FALLBACK row, and
    every hit of ours came from the cannon. Anything else may move the voyage on but proves nothing about 0310."""
    ok, why, forts = judgeFort(events, hit)
    if not ok:
        return False, 'not a 0310 proof: ' + why
    fb = [e for e in events if e.get('ev') == 'FALLBACK']
    if fb:
        return False, 'FALLBACK used (%s, %s): not a 0310 proof' % (fb[0].get('how'), fb[0].get('why'))
    vias = sorted(set(str(e.get('via')) for e in events if e.get('ev') == 'FORT-HIT' and e.get('mine') and
                      e.get('uid') in forts))
    if vias != ['cannon']:
        return False, 'hits by %s, not the cannon: not a 0310 proof' % (vias,)
    n = len([1 for f in forts.values() if not f.get('already')])
    return True, "%d fort(s) fell to the Pearl's cannon alone, no kick, no word (0310 proven)" % n


class Watch:
    """Logs every hp change of one fort as FORT-HIT; `mine` when it came within SHOT_WAIT s of our shot."""

    def __init__(self, H, inst, fort, barricade, log):
        self.H, self.inst, self.fort, self.b, self.log = H, inst, fort, barricade, log
        self.hp = fort.hp
        self.shotAt = None
        self.shot = 0
        self.pitch = None
        self.via = None
        self.mine = 0

    def fired(self, via, pitch=None):
        self.shot += 1
        self.shotAt = time.time()
        self.via, self.pitch = via, pitch

    def tick(self):
        """-> the hp drop seen this tick (0 when none)."""
        hp = self.fort.hp
        if hp == self.hp:
            return 0
        before, self.hp = self.hp, hp
        mine = self.shotAt is not None and time.time() - self.shotAt <= SHOT_WAIT
        if mine:
            self.mine += 1
            self.shotAt = None
        self.log('FORT-HIT', uid=self.fort.objKey, barricade=self.b, before=before, after=hp,
                 drop=(before - hp) if before is not None and hp is not None else None, via=self.via if mine else None,
                 shot=self.shot if mine else None, pitch=self.pitch if mine else None, mine=mine,
                 ok=dropOk(before, hp) if mine else None, hits=self.mine)
        return (before or 0) - (hp or 0)


def wire(H, inst, fort, b, w, t0, log):
    """Generator: the client's own hit message once a reload until the fort falls. -> 'down', 'kick' or 'time'."""
    while time.time() - t0 < SECS:
        if not connected(H):
            log('FORT-KICK', uid=fort.objKey, why='connection or pirate gone after %d hit(s) sent' % w.shot)
            return 'kick'
        if fallen(inst, fort, b):
            return 'down'
        w.fired('wire')
        log('FORT-SHOT', uid=fort.objKey, shot=w.shot, via='wire')
        fort.sendHitByProjectile(CANNON_SHOOT, CANNON_ROUND)
        end = time.time() + WIRE_GAP
        while time.time() < end:
            w.tick()
            if not connected(H):
                break
            yield 0.25
        w.tick()
    return 'down' if fallen(inst, fort, b) else 'time'


def cannon(H, inst, fort, b, w, t0, log):
    """Generator: man the Pearl's cannons in turn (rankCannons) and fire at the fort's hit boxes with a spotter: each
    ball's landing corrects the heading and refits the ball's drop (spot), the way a gunner walks shots onto a target.
    A cannon is left when its swing cannot follow the fort (OUT_OF_ARC shots in a row), when no angle it has reaches a
    hit box (2 in a row), or after SPOT_SHOTS misses. -> 'down', 'kick', 'time', 'no-cannon' or 'miss'.
    BPFORT10 (11-21): one cannon, a fixed pitch sweep, 0 of 55 strikes on the fort."""
    pt = fortPoint(H, fort)
    ranked = rankCannons(H, pt)
    boxes = hitBoxes(H, fort)
    zs = [bx[1][2] for bx in boxes]
    log('FORT-BOXES', uid=fort.objKey, n=len(boxes), zLow=round(min(zs), 1) if zs else None,
        zHigh=round(max(zs), 1) if zs else None, centre=[round(v, 1) for v in pt], cannons=len(ranked),
        boxes=[[bx[0]] + [round(v) for v in bx[1]] + [round(bx[2])] for bx in boxes[:16]])
    if not ranked:
        log('FORT-CANNON', uid=fort.objKey, ok=False, why='no deck cannon in view', cannons=len(cannons(H)))
        return 'no-cannon'
    st = {'K': K0, 'tilt': 0.0}
    ends = []
    for n, (c, h0) in enumerate(ranked[:MAX_CANNONS]):
        r = yield from oneCannon(H, inst, fort, b, w, t0, log, c, h0, boxes or [('centre', tuple(pt), 0.0)], st, n)
        ends.append(r)
        if r in ('down', 'kick', 'time'):
            return r
        yield ('until', lambda: not getattr(c, 'localAvatarUsingWeapon', False), 6, 'cannon left')
        if time.time() - t0 >= SECS:
            return 'time'
    log('FORT-REACH', uid=fort.objKey, cannons=len(ends), ends=ends, K='%.3e' % st['K'], tilt=round(st['tilt'], 2))
    return 'miss' if any(e != 'no-cannon' for e in ends) else 'no-cannon'


def oneCannon(H, inst, fort, b, w, t0, log, c, h0, boxes, st, n):
    """Generator: one cannon's turn (see cannon). -> 'down', 'kick', 'time', 'no-cannon', 'arc', 'reach' or 'miss'."""
    c.requestInteraction(H.la.doId)
    yield ('until', lambda: getattr(c, 'localAvatarUsingWeapon', False), 10, 'cannon manned')
    manned = bool(getattr(c, 'localAvatarUsingWeapon', False))
    E = exitPoint(H, c)
    lim = arcOf(H)
    log('FORT-CANNON', uid=fort.objKey, cannon=c.doId, ship=getattr(c, 'shipId', None), ok=manned, n=n,
        relH=round(h0, 1), arc=lim, exit=[round(v, 1) for v in E], volley=getattr(c, 'volley', None),
        d=round(math.hypot(fortPoint(H, fort)[0] - E[0], fortPoint(H, fort)[1] - E[1]), 1))
    if not manned:
        return 'no-cannon'
    pMax = lim[3] if lim[3] is not None else 30.0
    box, th, reach, short = pickBox(boxes, E, st['K'], pMax + st['tilt'])
    cmdH, out, unreach, near, shots, misses, r = h0, 0, 0, 0, 0, 0, 'miss'
    imp = Impacts(H, c, fort, w, log)
    try:
        while misses < SPOT_SHOTS:
            if time.time() - t0 >= SECS:
                r = 'time'
                break
            if not connected(H):
                log('FORT-KICK', uid=fort.objKey, why='connection or pirate gone after cannon shot %d' % w.shot)
                return 'kick'
            if fallen(inst, fort, b):
                r = 'down'
                break
            yield ('until', lambda: ready(H, c), 20, 'cannon reload')
            E = exitPoint(H, c)
            h, p, clamped = aimRaw(H, c, cmdH, th - st['tilt'])
            w.fired('cannon', round(th, 2))
            shots += 1
            shot = w.shot
            log('FORT-SHOT', uid=fort.objKey, shot=shot, via='cannon', cannon=c.doId, box=box[0],
                wantH=round(cmdH, 2), wantTheta=round(th, 2), h=round(h, 2), p=round(p, 2), clamped=clamped,
                exit=[round(v, 1) for v in E], volley=getattr(c, 'volley', None))
            c.fireCannon()
            yield 0.3
            now = aimNow(H, c)
            st['tilt'] = now['renderP'] - now['gotP']
            log('FORT-AIM', shot=shot, **now)
            end = time.time() + LAND_WAIT
            took, L, hitFort = 0, None, False
            while time.time() < end:
                took = took or w.tick()
                L = imp.landing(shot, E)
                hitFort = any(x[4] for x in imp.byShot.get(shot, ()))
                if took or (L is not None and not hitFort) or not connected(H):
                    break
                yield 0.2             # a fort strike waits here for its hp (the server's answer)
            misses += 0 if took > 0 else 1
            if took > 0 or L is None:
                log('FORT-SPOT', shot=shot, took=took, hitFort=hitFort, landed=None if L is None else
                    [round(v, 1) for v in L])
                continue              # a hit: the same aim again; no landing seen: fire again as it was
            s = spot(E, L, box[1], st['K'], now['renderP'])
            st['K'] = s['K']
            cmdH = wrap(h + s['dH'])
            box, th, reach, short = pickBox(boxes, E, st['K'], pMax + st['tilt'])
            near = near + 1 if reach and abs(s['missH']) < 15 else 0
            th += (0.0, 0.4, -0.4, 0.8, -0.8)[near % 5]     # on the line and still no strike: walk the pitch round it
            arcOut = None not in lim and not (lim[0] <= cmdH <= lim[1])
            out = out + 1 if arcOut else 0
            unreach = unreach + 1 if not reach else 0
            log('FORT-SPOT', shot=shot, took=0, hitFort=hitFort, landed=[round(v, 1) for v in L], missH=s['missH'],
                missR=s['missR'], dH=s['dH'], K='%.3e' % st['K'], nextH=round(cmdH, 2), nextTheta=round(th, 2),
                box=box[0], reach=reach, short=short, outOfArc=arcOut, tilt=round(st['tilt'], 2))
            if out >= OUT_OF_ARC:
                r = 'arc'
                break
            if unreach >= 2:
                r = 'reach'
                break
    finally:
        imp.stop()
        log('FORT-IMPACTS', uid=fort.objKey, cannon=c.doId, impacts=imp.n, fortHits=imp.fortHits, shots=shots, end=r)
        try:
            if getattr(c, 'localAvatarUsingWeapon', False):
                c.requestExit()
        except Exception:
            pass
    return r


def fight(H, inst, mode=None, log=None):
    """Generator: every BARRICADES fort shot down. -> (ok, why, events) judged by judgeFort on this fight's lines."""
    mode = (mode or MODE).lower()
    rows = []

    def ev(kind, **kw):
        kw2 = dict(kw)
        kw2['ev'] = kind
        kw2['t'] = time.time()
        rows.append(kw2)
        (log or H.ev)(kind, **kw)
    ev('BPFORT-START', mode=mode, barricades=BARRICADES, state=getattr(inst, 'state', None),
       forts=len(getattr(inst, 'fortIds', []) or []))
    yield ('until', lambda: all(FORT_OF.get(b) in fortsOf(H, inst) for b in BARRICADES), 30, 'forts in view')
    if PROBE and not all(FORT_OF.get(b) in fortsOf(H, inst) for b in BARRICADES):
        yield from probe(H, inst, ev)
    forts = fortsOf(H, inst)
    for b in BARRICADES:
        uid = FORT_OF.get(b)
        fort = forts.get(uid)
        if fort is None:
            ev('FORT-TARGET', uid=uid, barricade=b, ok=False, why='fort not in view', have=sorted(forts))
            continue
        ev('FORT-TARGET', uid=uid, barricade=b, hp=fort.hp, maxHp=fort.maxHp, hits=hitsToFall(fort.maxHp),
           d=round((fortPoint(H, fort) - H.la.getPos(H.render)).length(), 1), gs=H.la.getGameState())
        ev('FORT-STATE', uid=uid, when='target', **fortState(H, fort))
        yield ('until', lambda: getattr(fort, 'islandDependedObjectsSetup', 0), 20, 'fort hit boxes set up')
        ev('FORT-STATE', uid=uid, when='after 20 s', **fortState(H, fort))
        if fallen(inst, fort, b):
            ev('FORT-DOWN', uid=uid, barricade=b, hp=fort.hp, already=True)
            continue
        w = Watch(H, inst, fort, b, ev)
        t0 = time.time()
        if mode == 'cannon':
            r = yield from cannon(H, inst, fort, b, w, t0, ev)
            if r in ('miss', 'no-cannon', 'time') and FALLBACK != 'none' and connected(H):
                r = yield from fallback(H, inst, fort, b, w, ev, r)
        else:
            ev('FALLBACK', uid=uid, barricade=b, how='wire', why='BPFORT_MODE=wire', proof=False)
            r = yield from wire(H, inst, fort, b, w, t0, ev)
        yield ('until', lambda: fallen(inst, fort, b) or not connected(H), 5, 'fort falls')
        w.tick()
        if connected(H):
            ev('FORT-STATE', uid=uid, when='after shots', **fortState(H, fort))
        if r == 'kick':
            break
        if fallen(inst, fort, b):
            ev('FORT-DOWN', uid=uid, barricade=b, hp=fort.hp, hits=w.mine, shots=w.shot,
               secs=round(time.time() - t0, 1), destroyed=list(getattr(inst, 'barricadesDestroyed', []) or []))
        else:
            ev('FORT-STUCK', uid=uid, barricade=b, hp=fort.hp, r=r, hits=w.mine, shots=w.shot)
    ok, why, summary = judgeFort(rows)
    proof, pwhy = proofOf(rows)
    ev('BOSS-FORT', ok=ok, why=why, proof=proof, proofWhy=pwhy, mode=mode, forts=summary)
    return ok, why, rows


def island(H):
    for o in list(H.cr.doId2do.values()):
        if getattr(o, 'uniqueId', None) == BP_ISLAND:
            return o
    return None


def gridInfo(H, isl):
    """What the client knows of the island's zone grid, and which zone each fort spot falls in on it."""
    la = H.la
    out = {'island': getattr(isl, 'doId', None), 'laZone': la.zoneId, 'laParent': getattr(la, 'parentId', None),
           'laPos': [round(v) for v in la.getPos(isl if isl is not None else H.render)], 'seen': sorted(fortsOf(H, inst_of(H)))}
    if isl is not None:
        for k in ('gridSize', 'cellWidth', 'startingZone', 'viewingRadius', 'sphereRadii', 'sphereCenter'):
            v = getattr(isl, k, None)
            out[k] = list(v) if isinstance(v, (list, tuple)) else v
        try:
            out['fortZones'] = {uid[-14:]: isl.getZoneFromXYZ(p) for uid, p in FORT_POS.items()}
        except Exception as e:
            out['fortZones'] = repr(e)
        for k in ('lastZoneLevel', 'levelForced', 'undockable'):
            out[k] = getattr(isl, k, '?')
    # 0424 puts the forts in island zone 101, opened by DistributedIsland.loadZoneLevel(1) as the 'ShipDeployer' interest
    out['tags'] = [list(t) for t, c in getattr(la, 'interestHandles', [])]
    try:
        def zl(z):
            return sorted(z)[:6] if isinstance(z, (list, tuple, set)) else z
        out['interests'] = [[getattr(s, 'desc', ''), getattr(s, 'parentId', None), zl(getattr(s, 'zoneIdList', None))]
                            for s in list(H.cr._interests.values())]
    except Exception as e:
        out['interests'] = repr(e)
    out['fortObjs'] = [[o.doId, getattr(o, 'parentId', None), getattr(o, 'zoneId', None), getattr(o, 'objKey', None)]
                       for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedFort']
    inst = inst_of(H)
    ids = list(getattr(inst, 'fortIds', None) or [])
    out['fortIds'] = ids
    out['fortIdsKnown'] = [i for i in ids if i in H.cr.doId2do]
    # what the client holds under the island per zone (zone 101 by class): the island's own ShipDeployer lives in
    # zone 101 too, so it says whether the zone 101 interest delivers anything at all
    kids = {}
    for o in list(H.cr.doId2do.values()):
        if isl is not None and getattr(o, 'parentId', None) == isl.doId:
            z = getattr(o, 'zoneId', None)
            kids.setdefault(z, []).append(type(o).__name__)
    out['zone101'] = sorted(kids.get(101, []))
    out['kidZones'] = {str(z): len(v) for z, v in sorted(kids.items(), key=lambda kv: -len(kv[1]))[:8]}
    out['deferred'] = [len(getattr(H.cr, 'deferredGenerates', None) or []), len(getattr(H.cr, 'deferredDoIds', None) or {})]
    cache = getattr(H.cr, 'cache', None)
    try:
        out['cached'] = [i for i in ids if cache is not None and cache.contains(i)]
    except Exception as e:
        out['cached'] = repr(e)
    return out


def inst_of(H):
    import s_cards
    return s_cards.instance(H)


def probe(H, inst, ev):
    """Generator (BPFORT_PROBE=1): the forts are not in view from the bay. Log the island grid, walk the pirate to
    fort 0A's spot (setPos on the island: a client-driven move), wait 20 s, log again. The island grid (754 cells
    from BlackpearlWorld's LOD sphere) holds every fort, and the client is given only the cells about 225 ft round
    the pirate, so forts that show up there = distance only; still none = a real bug to chase from these lines."""
    isl = island(H)
    ev('FORT-PROBE', where='bay', **gridInfo(H, isl))
    if isl is None:
        return
    x, y, z = FORT_POS['1175905981.42kmuller']
    H.la.setPos(isl, x - 150, y - 150, z + 20)
    yield ('until', lambda: FORT_OF[0] in fortsOf(H, inst), 20, 'fort 0A in view near it')
    ev('FORT-PROBE', where='fort 0A', **gridInfo(H, isl))
    if FORT_OF[0] in fortsOf(H, inst):
        return
    # diagnostic only: open island zone 101 by hand. Forts that come now = the client never opened it (a game bug in
    # the island's zone levels); still none = the AI side. A FALLBACK row, so this run can never PASS.
    ev('FALLBACK', uid=None, barricade=None, how='interest101', why='forts not in view', proof=False)
    H.cr.addInterest(isl.doId, 101, 'bpfort-probe-101')
    yield ('until', lambda: FORT_OF[0] in fortsOf(H, inst), 20, 'forts after a zone 101 interest')
    ev('FORT-PROBE', where='after manual 101', **gridInfo(H, isl))


def fallback(H, inst, fort, b, w, ev, why):
    """Generator: the cannon could not bring this fort down. FALLBACK (proof=False), then ~bpdestroy <b> or the wire.
    -> 'down', 'kick' or 'time'."""
    if FALLBACK == 'wire':
        ev('FALLBACK', uid=fort.objKey, barricade=b, how='wire', why=why, shots=w.shot, hits=w.mine, proof=False)
        r = yield from wire(H, inst, fort, b, w, time.time(), ev)
        return r
    word = 'bpdestroy %d' % b
    ev('FALLBACK', uid=fort.objKey, barricade=b, how=word, why=why, shots=w.shot, hits=w.mine, proof=False)
    H.mw(word)
    yield ('until', lambda: fallen(inst, fort, b) or not connected(H), 30, 'fort down by ~bpdestroy')
    if not connected(H):
        ev('FORT-KICK', uid=fort.objKey, why='gone after ~bpdestroy')
        return 'kick'
    return 'down' if fallen(inst, fort, b) else 'time'


def board(H, inst, ev):
    """Generator: the pirate onto the Black Pearl the game's own way. Stage one ends on the client with
    stageOneCutsceneDone: teleportMgr.localTeleportToId(pearlId, localAvatar) puts him on its deck. The run skips stage
    one (bpstate StageTwo), so he is still ashore at the bay with no cannon near (BPFORT7 05:26: 52 cannons, none
    within 120 ft). -> True when he stands on the Pearl and its deck cannons are built."""
    la = H.la
    pid = getattr(inst, 'pearlId', 0)

    def onPearl():
        return getattr(getattr(la, 'ship', None), 'doId', None) == pid and getattr(la, 'parentId', None) == pid

    def deck():
        return [c for c in cannons(H) if getattr(c, 'shipId', None) == pid]
    if not pid:
        ev('BPFORT-BOARD', ok=False, why='the instance has no pearlId')
        return False
    if not onPearl():
        yield ('until', lambda: pid in H.cr.doId2do, 30, 'the Pearl generated')
        if pid not in H.cr.doId2do:
            ev('BPFORT-BOARD', ok=False, pearl=pid, why='the Pearl is not in view')
            return False
        H.cr.teleportMgr.localTeleportToId(pid, la, showLoadingScreen=False)
        yield ('until', onPearl, 60, 'on the Pearl')
    yield ('until', lambda: len(deck()) > 0, 30, "the Pearl's deck cannons")
    ok = onPearl()
    ev('BPFORT-BOARD', ok=ok, pearl=pid, ship=getattr(getattr(la, 'ship', None), 'doId', None),
       parent=getattr(la, 'parentId', None), gs=la.getGameState(), deckCannons=len(deck()),
       pos=[round(v) for v in la.getPos(H.render)])
    return ok


def run(H):
    """BPFORT on its own: in, stages one and two ended with the test words, the forts shot down, out."""
    import s_cards
    la = H.la
    H.ev('BPFORT-RUN', me=la.doId, mode=MODE, barricades=BARRICADES, secs=SECS)
    if la.doId == HOST_AV:
        H.ev('FAIL', why='BPFORT never runs on Host\'s pirate %d' % HOST_AV); return
    if s_cards.instance(H) is None:
        tm = s_cards.pearlMap(H)
        if tm is not None:
            yield ('until', lambda: la.getGameState() == 'LandRoam', 30, 'on land before the map')
            H.ev('BPFORT-IN', how=s_cards.pressPlayNow(H, tm), map=tm.doId)
            yield ('until', lambda: s_cards.instance(H) is not None, 180, 'boss instance (map)')
        if s_cards.instance(H) is None:
            H.ev('BPFORT-IN', how='mw blackpearlai', why='no Black Pearl map' if tm is None else 'no instance by the map')
            H.mw('blackpearlai')
            yield ('until', lambda: s_cards.instance(H) is not None, 180, 'boss instance')
    inst = s_cards.instance(H)
    if inst is None:
        H.ev('FAIL', why='no Black Pearl instance'); return
    yield ('until', lambda: s_cards.stateOf(s_cards.instance(H)) not in (None, 'Off', 'WaitClientsReady'), 100, 'stage one')
    for stage, words, why, secs in s_cards.STAGES:
        st = s_cards.stateOf(s_cards.instance(H))
        if stage == 'StageThree' or st != stage:
            if st == 'StageThree':
                break
            continue
        for wd in words:
            H.ev('BOSS-MW', word=wd, why=why, state=st)
            H.mw(wd)
        yield ('until', lambda: s_cards.stateOf(s_cards.instance(H)) != stage, secs, 'past %s' % stage)
    inst = s_cards.instance(H)
    if s_cards.stateOf(inst) != 'StageThree':
        H.ev('FAIL', why='the fight is not at stage three', state=s_cards.stateOf(inst)); return
    if MODE == 'cannon':
        yield from board(H, inst, H.ev)
    ok, why, rows = yield from fight(H, inst)
    proof, pwhy = proofOf(rows)
    if connected(H):
        yield ('until', lambda: s_cards.stateOf(s_cards.instance(H)) != 'StageThree', 60, 'stage four')
        H.ev('BPFORT-STAGE', now=s_cards.stateOf(s_cards.instance(H)))
        if LEAVE and s_cards.instance(H) is not None:
            try:
                s_cards.instance(H).requestTreasureMapLeave()
            except Exception as e:
                H.ev('BPFORT-LEAVE', err=repr(e))
            yield ('until', lambda: s_cards.instance(H) is None and la.getGameState() == 'LandRoam', 120, 'out')
    if ok and proof:
        H.ev('PASS', what='the barricade fort(s) fell to cannon hits, no kick (0310)', why=pwhy, fight=why)
    else:
        H.ev('FAIL', why=pwhy if ok else why, fight=why, proof=False)
