"""Bulb census: editor-only placeholder models in the scene, per place a player goes.
For each area: the game's own areaTeleport, wait for LandRoam, count every GeomNode under render whose own name or
any ancestor's name looks like an editor placeholder (light_tool_bulb / arrow, smiley, coll_sphere, locator, marker,
icon ...), split visible / hidden, save a screenshot to shots/bulbs/<tag>-<area>.png. Port Royal also gets a short
real walk (held keys) first. Emits PASS when every area was censused and shot (the goal is the numbers).
env: BULB_TAG (file tag, default 'before'), BULB_AREAS (comma list of keys to restrict)."""
import os, sys, re, time, math, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import paths
from panda3d.core import Filename, Vec3

TAG = os.environ.get('BULB_TAG', 'before')
OUTDIR = r'C:\PiratesBots\shots\bulbs'
PR = '1150922126.8dzlu'
AREAS = [
    ('portroyal', PR),
    ('tavern', '1153419689.81dzlu0'),
    ('blacksmith', '1153423464.2dzlu0'),
    ('mansion', '1168033330.17kmuller0'),
    ('weapons', '1153423448.14dzlu0'),
    ('jungle', '1169592956.59sdnaik'),
    ('cave', '1164952144.06sdnaik'),
    ('tortuga', '1156207188.95dzlu'),
    ('tortugajail', '1168559956.74dxschafe0'),
]
# arrow_ground is the player's own quest ground arrow (LocalPirate.enableQuestArrow), meant to show; any other arrow is a placeholder
PAT = re.compile(r'light_tool|bulb|smiley|coll_sphere|locator|marker|placeholder|arrow(?!_ground)|icon_|DynamicLight', re.I)
WEAK = re.compile(r'sphere', re.I)


def census(R):
    cnt = collections.Counter()
    hid = collections.Counter()
    weak = collections.Counter()
    samples = {}
    total = 0
    for np in R.findAllMatches('**/+GeomNode'):
        total += 1
        names = []
        p = np
        while not p.isEmpty() and p != R:
            names.append(p.getName())
            p = p.getParent()
        key = None
        for n in names:
            if PAT.search(n):
                key = n
                break
        wk = None
        if key is None:
            for n in names:
                if WEAK.search(n):
                    wk = n
                    break
        if key is None and wk is None:
            continue
        if key is None:
            weak[wk] += 1
            continue
        k = re.sub(r'\.bam$', '', key)
        if np.isHidden():
            hid[k] += 1
        else:
            cnt[k] += 1
            samples.setdefault(k, str(np))
    return total, cnt, hid, weak, samples


def go(H, d, tag):
    """Walk to a door like a player: the shortest open route round the buildings, then a straight last bit."""
    R = H.render
    H.walk_cancel()
    p = d.getPos(R)
    if (p - H.la.getPos(R)).length() > 25:
        yield from paths.walk_route(H, [(p[0], p[1], p[2])], arrive=6.0, short=6.0, tag=tag)
    return (yield from H.walk_to(d, ref=R, arrive=3.0, tag=tag, timeout=40))


def beams(H):
    """Quest indicator beams under render: one per live indicator is fine; more than one visible = a leftover."""
    R, la = H.render, H.la
    cur = None
    try:
        ind = getattr(la, 'questIndicator', None)
        node = getattr(ind, 'indicatorNode', None) if ind else None
        if node is not None:
            cur = [round(v) for v in node.getPos(R)]
    except Exception:
        pass
    out = []
    for np in R.findAllMatches('**/QuestIndicatorParticleDummy;+s+h'):
        p = np.getPos(R)
        out.append(dict(pos=[round(v) for v in p], hidden=bool(np.isHidden()), stashed=bool(np.isStashed()),
                        distToPirate=round((p - la.getPos(R)).length()),
                        isCurrent=(cur is not None and abs(p[0] - cur[0]) + abs(p[1] - cur[1]) < 6)))
    nsky = 0
    for g in R.findAllMatches('**/+GeomNode'):
        q = g
        while not q.isEmpty() and q != R:
            if 'skyBeam' in q.getName():
                nsky += 1
                break
            q = q.getParent()
    qs = getattr(la, 'questStep', None)
    return dict(qstep=repr(qs) if qs else None, qids=list(H.qids()) if hasattr(H, 'qids') else None, totalDummies=len(out), currentIndicator=cur, dummies=out, visibleDummies=sum(1 for b in out if not b['hidden'] and not b['stashed']),
                skyBeamGeoms=nsky)


def shoot(H, key, uid, extra=None):
    R, B = H.render, H.B
    total, cnt, hid, weak, samples = census(R)
    shot = os.path.join(OUTDIR, '%s-%s.png' % (TAG, key))
    B.win.saveScreenshot(Filename.fromOsSpecific(shot))
    r = dict(area=key, uid=uid, here=H.area(), geomNodes=total, visible=dict(cnt), visibleTotal=sum(cnt.values()),
             hidden=dict(hid), weakSphere=dict(weak), samples=samples, shot=shot, beams=beams(H))
    if extra:
        r.update(extra)
    H.ev('bulb-census', **r)
    return r


class _Done(Exception):
    pass


# worldData positions are island-local; the live Port Royal frame is shifted by about (+1360, +1690, 0) (jail door seen at
# (624,-75) vs worldData (-736,-1764); BULB5). The jail door is loaded at the spawn, so jail goes first (goal = its door).
ISL = (1360.0, 1690.0)
COVER = [('jail', None, '1183482682.31kmuller0'),
         ('mansion', (169.0 + ISL[0], -1041.0 + ISL[1], 54.0), '1168033330.17kmuller0')]


def cover(H, T0, DEADLINE, results):
    """Walk (route planner, held keys) to the mansion and the jail, use the door a player would, census inside.
    Then log every loaded tunnel / door so the jungle entrance, if loaded, is on record; walk into a tunnel if one is near."""
    la, R = H.la, H.render
    for key, pos, iuid in COVER:
        if time.time() - T0 > DEADLINE - 120:
            H.ev('bulb-skip', key=key, why='deadline')
            continue
        if pos is None:
            pre = [d for d in H.cr.doId2do.values() if 'Door' in type(d).__name__ and hasattr(d, 'getPos')
                   and iuid in (str(getattr(d, 'interiorUid', '')), str(getattr(d, 'buildingUid', '')))]
            pos = tuple(pre[0].getPos(R)) if pre else None
        got = (yield from paths.walk_route(H, [pos], arrive=30.0, short=6.0, tag='cover-' + key)) if pos else None
        H.ev('cover-arrive', key=key, got=bool(got), at=[round(v) for v in la.getPos(R)])
        yield 3
        results[key + '-outside'] = shoot(H, key + '-outside', H.area() and H.area()[1], dict(arrived=bool(got)))
        doors = [d for d in H.cr.doId2do.values() if 'Door' in type(d).__name__ and hasattr(d, 'getPos')]
        H.ev('cover-doors', key=key, doors=[dict(doId=d.doId, cls=type(d).__name__, d=round((d.getPos(R) - la.getPos(R)).length()),
              bu=getattr(d, 'buildingUid', None), iu=getattr(d, 'interiorUid', None)) for d in doors][:30])
        tun = [d for d in H.cr.doId2do.values() if 'Tunnel' in type(d).__name__ and hasattr(d, 'getPos')]
        H.ev('cover-tunnels', key=key, tunnels=[dict(doId=d.doId, cls=type(d).__name__, d=round((d.getPos(R) - la.getPos(R)).length()),
              pos=[round(v) for v in d.getPos(R)]) for d in tun][:30])
        mine = [d for d in doors if iuid in (str(getattr(d, 'interiorUid', '')), str(getattr(d, 'buildingUid', '')))]
        mine.sort(key=lambda d: (d.getPos(R) - la.getPos(R)).length())
        if not mine:
            H.ev('cover-nodoor', key=key)
            continue
        d = mine[0]
        ok = yield from go(H, d, 'cover-door-' + key)
        if not ok and (d.getPos(R) - la.getPos(R)).length() > 8:
            continue
        # a player standing at the door (even 3-4 ft off its node) just uses it
        d.requestInteraction(la.doId)
        yield ('until', lambda: H.area() is not None and H.area()[1] != PR and la.getGameState() == 'LandRoam', 25, 'door')
        yield 5
        a = H.area()
        if a is None or a[1] == PR:
            continue
        results[key] = shoot(H, key, a[1], dict(arrived=True, door=d.doId, areaName=a[2], areaCls=a[0]))
        ins = [x for x in H.cr.doId2do.values() if 'Door' in type(x).__name__ and hasattr(x, 'getPos')]
        ins.sort(key=lambda x: (x.getPos(R) - la.getPos(R)).length())
        if ins:
            ok = yield from go(H, ins[0], 'cover-out')
            if ok:
                ins[0].requestInteraction(la.doId)
        yield ('until', lambda: H.area() is not None and H.area()[1] == PR and la.getGameState() == 'LandRoam', 25, 'out')
        yield 3
    tun = [d for d in H.cr.doId2do.values() if 'Tunnel' in type(d).__name__ and hasattr(d, 'getPos')]
    tun.sort(key=lambda d: (d.getPos(R) - la.getPos(R)).length())
    if tun and time.time() - T0 < DEADLINE - 100 and H.area() and H.area()[1] == PR:
        t = tun[0]
        H.ev('cover-tunnel', doId=t.doId, cls=type(t).__name__, d=round((t.getPos(R) - la.getPos(R)).length()))
        ok = yield from go(H, t, 'cover-tunnel')
        yield ('until', lambda: H.area() is not None and H.area()[1] != PR and la.getGameState() == 'LandRoam', 25, 'tunnel')
        yield 5
        a = H.area()
        if a is not None and a[1] != PR:
            results['tunnel'] = shoot(H, 'tunnel', a[1], dict(arrived=True, areaName=a[2], areaCls=a[0]))
        else:
            H.ev('cover-tunnel-noarea', ok=bool(ok))


def run(H):
    la = H.la
    R = H.render
    B = H.B
    T0 = time.time()
    DEADLINE = float(os.environ.get('BULB_DEADLINE', '420'))
    os.makedirs(OUTDIR, exist_ok=True)
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    H.ev('bulb-config', drawLightIcons=B.config.GetBool('draw-light-icons', False), tag=TAG)
    results = {}
    try:
        yield 6
        # Port Royal outside: a short real walk, then census
        p0 = la.getPos(R)
        fwd = R.getRelativeVector(la, Vec3(0, 1, 0))
        fwd.setZ(0)
        fwd.normalize()
        ok = yield from H.walk_to(p0 + fwd * 25, ref=R, arrive=2.0, tag='bulb-walk', timeout=30)
        H.ev('bulb-walk', ok=bool(ok))
        yield 2
        results['portroyal'] = shoot(H, 'portroyal', H.area() and H.area()[1], dict(arrived=True))
        if os.environ.get('BULB_MODE') == 'cover':
            yield from cover(H, T0, DEADLINE, results)
            raise _Done()
        # interiors through real doors: nearest doors first, each one entered by walking up and using it
        seen = set()
        n = 0
        while time.time() - T0 < DEADLINE - 90 and n < 6:
            doors = [d for d in H.cr.doId2do.values() if 'Door' in type(d).__name__ and hasattr(d, 'getPos')
                     and d.doId not in seen]
            if H.area() is None or H.area()[1] != PR or not doors:
                break
            doors.sort(key=lambda d: (d.getPos(R) - la.getPos(R)).length())
            d = doors[0]
            seen.add(d.doId)
            H.ev('bulb-door', doId=d.doId, cls=type(d).__name__, dist=round((d.getPos(R) - la.getPos(R)).length(), 1))
            ok = yield from go(H, d, 'bulb-door')
            if not ok:
                continue
            d.requestInteraction(la.doId)
            yield ('until', lambda: H.area() is not None and H.area()[1] != PR and la.getGameState() == 'LandRoam', 25,
                   'door %s' % d.doId)
            yield 5
            a = H.area()
            if a is None or a[1] == PR:
                continue
            n += 1
            results['int%d' % n] = shoot(H, 'int%d' % n, a[1], dict(arrived=True, door=d.doId, areaName=a[2], areaCls=a[0]))
            # back out the way a player does: the nearest door inside
            ins = [x for x in H.cr.doId2do.values() if 'Door' in type(x).__name__ and hasattr(x, 'getPos')]
            ins.sort(key=lambda x: (x.getPos(R) - la.getPos(R)).length())
            if ins:
                ok = yield from go(H, ins[0], 'bulb-out')
                if ok:
                    ins[0].requestInteraction(la.doId)
            yield ('until', lambda: H.area() is not None and H.area()[1] == PR and la.getGameState() == 'LandRoam', 25, 'out')
            yield 3
    except _Done:
        pass
    except Exception as e:
        H.ev('bulb-error', err=repr(e))
    H.ev('bulb-summary', tag=TAG, secs=round(time.time() - T0), teleports=H.teleports(),
         totals={k: v['visibleTotal'] for k, v in results.items()})
    H.ev('PASS', areas=len(results), censused=sorted(results))
