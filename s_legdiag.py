"""Leg check: why IND11 (11-16 18:55) planned no walk from the Port Royal east end (674.4, -11.3, 23.6) to Darby: every
grid shift and the wide box ran dry, the nearest point (265.7, 37.3, 1.9) still 540 ft away. IND6 ran dry at the same
spot before the half-step grid shift found the narrow way off the beach; since a8a1545 the wall probes also follow the
ground (FOLLOW: knee 1.5 ft and chest 4.0 ft over each two samples), and the walker steps up MAX_RISE (2.5 ft) between
samples, so a step near a sample can put the knee probe into its riser. This run measures it.
At Port Royal, with a logged SETUP-POS to LEGDIAG_AT (diagnosis only, never in play):
  legdiag-plan   plans to Darby from the spot and from IND11's start with each probe set: old (no ground-following
                 probes), now (1.5, 4.0), raised (3.0, 5.0): route length or None, and where the search stopped
  legdiag-rays   for 16 headings, legs of 20 and 40 ft out of the spot: open (O/N/R) or closed (-) with each set
  legdiag-hits   for legs the current probes close and the old do not: the probes that hit (height, side offset,
                 sample, ground z at both samples, hit z, what it hit)
PASS when everything is logged (the goal is the data).
env: LEGDIAG_AT ('x,y,z', default the dry spot)."""
import os, sys, math, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
from panda3d.core import Point3   # noqa: E402
import sailing, paths   # noqa: E402

PR = '1150922126.8dzlu'
AT = tuple(float(v) for v in os.environ.get('LEGDIAG_AT', '265.7,37.3,1.9').split(','))
IND11 = (674.4, -11.3, 23.6)
DARBY = (-274.3, 57.3, 2.7)
SETS = (('old', ()), ('now', (1.5, 4.0)), ('raised', (3.0, 5.0)))


def probe_hits(H, ground, p, q, follow):
    """The ground-following probes of leg p -> q that hit a wall: [height, offset, sample, z0, z1, hit z, into]."""
    from otp.otpbase import OTPGlobals
    from s_control import _hits
    m = max(1, int(paths.dist(p, q) / paths.SAMPLE))
    samples = [(p[0] + (q[0] - p[0]) * i / m, p[1] + (q[1] - p[1]) * i / m, p[2] + (q[2] - p[2]) * i / m)
               for i in range(m + 1)]
    zs = ground(samples)
    if any(z is None for z in zs):
        return ['ground missing']
    L = paths.dist(p, q)
    sx, sy = -(q[1] - p[1]) / L, (q[0] - p[0]) / L
    out = []
    for i in range(m):
        (x0, y0, _), (x1, y1, _) = samples[i], samples[i + 1]
        for h in follow:
            for o in (-1.2, 0.0, 1.2):
                A = Point3(x0 + sx * o, y0 + sy * o, zs[i] + h)
                B = Point3(x1 + sx * o, y1 + sy * o, zs[i + 1] + h)
                hs = _hits(H, [(A, B)], OTPGlobals.WallBitmask)
                if hs:
                    e = hs[0]
                    into = '/'.join(str(e.getIntoNodePath()).split('/')[-3:])
                    out.append([h, o, i, round(zs[i], 1), round(zs[i + 1], 1),
                                round(e.getSurfacePoint(H.render)[2], 1), into])
    return out[:12]


def run(H):
    la, R = H.la, H.render
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if sailing.hereUid(H) != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
    H.ev('SETUP-POS', to=list(AT), frm=H.P(la), why='diagnosis: where IND11 planned no route to Darby')
    la.setPos(R, *AT)
    yield 3
    p = la.getPos(R)
    a = (p[0], p[1], p[2])
    sets = [(name, f, paths.live(H, 0.0, f)) for name, f in SETS]
    ground = sets[0][2][1]
    for frm_name, frm in (('spot', a), ('ind11', IND11)):
        for name, f, (legs_ok, gr) in sets:
            t0 = time.time()
            g, r, checks = yield from paths.best_route_g(frm, [DARBY], legs_ok, gr, (), 0.0, 1)
            H.ev('legdiag-plan', frm=frm_name, probes=name, follow=list(f),
                 length=round(paths.length(frm, r), 1) if r else None,
                 path=[[round(v, 1) for v in w] for w in r] if r else None, checks=checks,
                 secs=round(time.time() - t0, 1), **({} if r else {'search': dict(paths.LAST)}))
    rays, hits = {}, {}
    for k in range(16):
        hd = k * 22.5
        dx, dy = math.cos(math.radians(hd)), math.sin(math.radians(hd))
        row = []
        for r in (20, 40):
            gz = ground([(a[0] + dx * r, a[1] + dy * r, a[2])])[0]
            if gz is None:
                row.append('%d:no floor' % r)
                continue
            q = (a[0] + dx * r, a[1] + dy * r, gz)
            res = [(name, legs_ok([(a, q, False)])[0]) for name, f, (legs_ok, gr) in sets]
            row.append('%d:%s' % (r, ''.join(n[0].upper() if v else '-' for n, v in res)))
            if res[0][1] and not res[1][1]:
                hits['%05.1f/%d' % (hd, r)] = probe_hits(H, ground, a, q, sets[1][1])
            yield 0
        rays['%05.1f' % hd] = row
    H.ev('legdiag-rays', at=H.P(la), key='O/N/R = open with the old/now/raised probes, - = closed', rays=rays)
    H.ev('legdiag-hits', hits=hits)
    H.ev('PASS', what='leg probes measured')
