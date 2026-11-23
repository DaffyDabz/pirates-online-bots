"""Walk-control proof: the bot moves like a player (held keys, never setPos) and the numbers show it.
After login it stands on open ground near where it landed, walks a fixed 4-leg square (CTRL_SIDE ft a side, default 20)
and then one straight CTRL_LONG ft leg (default 60), and reports per leg: start / end distance, max heading error
after the turn phase, seconds, stuck tries.
Emits PASS (the event run_walk.ps1's two-strike rule counts) only when every leg arrived within 2 ft, the heading
error after the turn phase stayed under 15 deg on every leg, no leg gave up as stuck and the TELEPORT tripwire
counted 0. Otherwise it emits FAIL with the numbers.
env: CTRL_AREA (uid to areaTeleport to first; default Port Royal when logged in inside a building),
     CTRL_ROT (deg to rotate the whole pattern first; it then turns 90 at a time until every leg is open ground),
     CTRL_SIDE, CTRL_LONG."""
import os, sys, time, math
from panda3d.core import Vec3, Point3, BitMask32, CollisionTraverser, CollisionHandlerQueue, CollisionNode, CollisionSegment

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing   # noqa: E402
from otp.otpbase import OTPGlobals   # noqa: E402

PR = '1150922126.8dzlu'
SIDE = float(os.environ.get('CTRL_SIDE', '20'))
LONG = float(os.environ.get('CTRL_LONG', '60'))
ROT = float(os.environ.get('CTRL_ROT', '0'))
ARRIVE = 0.8            # walk_to stops within this; the verdict re-measures after the avatar has settled
MAX_END = 2.0           # every leg must end within this many ft of its target
MAX_HERR = 15.0         # heading error (deg) after the turn phase must stay under this


def flat(v):
    v.setZ(0)
    v.normalize()
    return v


def _hits(H, segs, mask):
    """Collision hits (render space, nearest first) of segments [(a, b)] against mask, skipping the pirate itself and
    intangible solids (zone / quest-marker bubbles on the wall mask that the pirate walks through; CTRL6 stood in one)."""
    R = H.render
    cn = CollisionNode('ctrl-probe')
    for a, b in segs:
        cn.addSolid(CollisionSegment(a, b))
    cn.setFromCollideMask(mask)
    cn.setIntoCollideMask(BitMask32.allOff())
    np = R.attachNewNode(cn)
    q = CollisionHandlerQueue()
    t = CollisionTraverser('ctrl-probe')
    t.addCollider(np, q)
    t.traverse(R)
    np.removeNode()
    q.sortEntries()
    out = []
    for i in range(q.getNumEntries()):
        e = q.getEntry(i)
        if H.la.isAncestorOf(e.getIntoNodePath()) or not e.getInto().isTangible():
            continue
        out.append(e)
    return out


def blocked(H, a, b):
    """Why the straight walk a -> b is not open ground, or None when it is: a wall at knee or chest height (the mask
    the pirate's own wall collisions use), no ground under it, or a step / drop over 2 ft between 4 ft samples.
    Picking open ground is what a tester does before a control test (CTRL4 walked into something at Port Royal)."""
    for z in (1.5, 4.0):
        w = _hits(H, [(Point3(a[0], a[1], a[2] + z), Point3(b[0], b[1], b[2] + z))], OTPGlobals.WallBitmask)
        if w:
            p = w[0].getSurfacePoint(H.render)
            return 'wall %s at %s' % (w[0].getIntoNodePath().getName(), [round(p[0], 1), round(p[1], 1)])
    d = Vec3(b[0] - a[0], b[1] - a[1], 0)
    n = max(1, int(d.length() / 4))
    prev = None
    for i in range(n + 1):
        x, y = a[0] + d[0] * i / n, a[1] + d[1] * i / n
        g = _hits(H, [(Point3(x, y, a[2] + 10), Point3(x, y, a[2] - 10))], OTPGlobals.FloorBitmask)
        if not g:
            return 'no ground at %s' % [round(x, 1), round(y, 1)]
        z = max(e.getSurfacePoint(H.render)[2] for e in g)
        if prev is not None and abs(z - prev) > 2.0:
            return 'step %.1f ft at %s' % (z - prev, [round(x, 1), round(y, 1)])
        prev = z
    return None


def layout(p0, fwd, right):
    return [('sq1-fwd', p0 + fwd * SIDE),
            ('sq2-right', p0 + fwd * SIDE + right * SIDE),
            ('sq3-back', p0 + right * SIDE),
            ('sq4-home', p0 + Vec3(0, 0, 0)),
            ('long-fwd', p0 + fwd * LONG)]


def run(H):
    la = H.la
    R = H.render
    yield ('until', lambda: la.getGameState() == 'LandRoam', 60, 'LandRoam')
    here = H.area()[1] if H.area() else None
    uid = os.environ.get('CTRL_AREA') or (PR if sailing.hereUid(H) is None else None)
    if uid and uid != here:          # inside a building (or told to): the game's own teleport to open ground
        H.mw('areaTeleport %s' % uid)
        yield ('until', lambda: H.area() is not None and H.area()[1] == uid and la.getGameState() == 'LandRoam', 90, 'tp ' + uid)
        yield 5
    yield 4                          # let the ground load and the pirate land
    try:
        speeds = [round(s, 1) for s in la.controlManager.getSpeeds()]
    except Exception as e:
        speeds = 'err %s' % e
    p0 = la.getPos(R)
    fwd = flat(R.getRelativeVector(la, Vec3(0, 1, 0)))
    right = flat(R.getRelativeVector(la, Vec3(1, 0, 0)))
    # the pattern turned ROT, then ROT + 90 / 180 / 270 until every leg is open ground
    f0, r0 = fwd, right
    legs, rot = None, ROT
    for k in range(4):
        rot = ROT + 90 * k
        a = math.radians(rot)
        fwd, right = flat(f0 * math.cos(a) + r0 * math.sin(a)), flat(r0 * math.cos(a) - f0 * math.sin(a))
        cand = layout(p0, fwd, right)
        why = None
        prev = p0
        for name, pt in cand:
            why = blocked(H, prev, pt)
            if why:
                H.ev('control-probe', rot=rot, leg=name, why=why)
                break
            prev = pt
        if not why:
            legs = cand
            break
    H.ev('control-start', area=H.area(), la=H.P(la), h=round(la.getH(R), 1), gs=la.getGameState(), speeds=speeds,
         side=SIDE, long=LONG, rot=rot, clear=legs is not None, island=sailing.hereUid(H))
    if legs is None:
        H.ev('FAIL', why='no open ground for the pattern in any of 4 directions (control-probe events say what is in the way)')
        return
    res = []
    t0 = time.time()
    for name, pt in legs:
        ok = yield from H.walk_to(pt, ref=R, arrive=ARRIVE, tag=name)
        w = H.lastWalk
        yield 0.5                    # the stop must be real: measure after the avatar has settled
        cur = la.getPos(R)
        end = math.hypot(cur[0] - pt[0], cur[1] - pt[1])
        r = dict(leg=name, ok=bool(ok), why=w.why, start=round(w.start, 1), end=round(end, 2),
                 herr=round(w.maxerr, 1), secs=w.secs, turnSecs=round(w.turnSecs, 2), stuck=w.tries)
        res.append(r)
        H.ev('control-leg', **r)
        if w.why == 'stuck':
            break                    # gave up: no point walking on, the verdict says where
    bad = []
    for r in res:
        if not r['ok']:
            bad.append('%s did not arrive (%s)' % (r['leg'], r['why']))
        elif r['end'] > MAX_END:
            bad.append('%s ended %.2f ft off' % (r['leg'], r['end']))
        if r['herr'] >= MAX_HERR:
            bad.append('%s heading error %.1f deg' % (r['leg'], r['herr']))
        if r['why'] == 'stuck':
            bad.append('%s gave up stuck' % r['leg'])
    if len(res) < len(legs) and not bad:
        bad.append('only %d of %d legs walked' % (len(res), len(legs)))
    tele = H.teleports()
    if tele:
        bad.append('%d TELEPORT call(s) from harness code' % tele)
    summary = dict(legs=res, teleports=tele, secs=round(time.time() - t0, 1),
                   worstEnd=max((r['end'] for r in res), default=None),
                   worstHerr=max((r['herr'] for r in res), default=None),
                   stuckTries=sum(r['stuck'] for r in res))
    H.ev('control-report', **summary)
    if bad:
        H.ev('FAIL', why=bad, **summary)
        return
    H.ev('PASS', legs=len(res), worstEnd=summary['worstEnd'], worstHerr=summary['worstHerr'], teleports=tele,
         stuckTries=summary['stuckTries'], secs=summary['secs'])
