"""TUNNELS (pir-bot, 11-17, job 3): walk through every cave and tunnel door on Port Royal and Tortuga, and back.

The links come from quest_spots.json 'exits' (the world data): every 'tunnel' exit between two areas of the island,
plus every 'door' into a cave interior (Tortuga's tortuga_cave_b_int_1). Port Royal has 7 tunnels, Tortuga 7
tunnels and 1 cave door. tunnelEdges() puts each link once, its near side first (the side fewer hops from the open
island), nearest links first, so the walk goes out link by link.

For each link a -> b (its world uid in 'via'): walk to a (s_story.goto: through the doors / tunnels on the way, like
the story), then from a to b through this link (TUNNEL-THROUGH), then back to a (TUNNEL-BACK). A link that fails is
logged (TUNNEL-FAIL) and the walk goes on with the next one. s_story.useTunnel's own TUNNEL-QUICKLOAD /
TUNNEL-STUCK lines say why a tunnel hung. Islands: TUNNEL_ISLANDS (default both); from one island to the next the
step uses the game's areaTeleport (SETUP-TP, s_lanes.onIsland): this step is about the doors, not the sail.

Lines: TUNNELS-START (the link list), STAGE step=tunnels what=island / at-near-side / through / back for each link
(with link=i/n, via, frm, to), TUNNEL-THROUGH / TUNNEL-BACK (secs), TUNNEL-FAIL, TUNNELS-END, PASS / FAIL.
PASS = every link went through and back. env: TUNNEL_ISLANDS (comma uids), TUNNEL_SECS (one leg's limit, 240),
TUNNEL_ONLY (comma via uids: just those links)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402
import s_story   # noqa: E402

ISLANDS = [s for s in os.environ.get('TUNNEL_ISLANDS', '%s,%s' % (s_lanes.PR, s_lanes.TORTUGA)).split(',') if s]
LEG = float(os.environ.get('TUNNEL_SECS', '240'))
ONLY = set(s for s in os.environ.get('TUNNEL_ONLY', '').split(',') if s)


def _depths(qs, island):
    """Pure: {area uid: hops from the island's open area} over the island's own exits."""
    areas, ex = qs['areas'], qs['exits']
    d, todo = {island: 0}, [island]
    while todo:
        a = todo.pop(0)
        for e in ex.get(a, []):
            b = e[0]
            if b not in d and (areas.get(b) or [None])[0] == island:
                d[b] = d[a] + 1
                todo.append(b)
    return d


def tunnelEdges(qs, island):
    """Pure: [(a, b, via, kind)] for every tunnel between two areas of island, and every door into a cave interior;
    each link once (by via), a = the side nearer the open island, sorted by (depth of a, depth of b, via)."""
    areas, ex = qs['areas'], qs['exits']
    dep = _depths(qs, island)
    seen, out = set(), []
    for a, exits in ex.items():
        if a not in dep:
            continue
        for e in exits:
            b, kind, via = e[0], e[4], e[5]
            # a cave door is two objects (outside and inside, two ids): one link per pair of areas
            key = via if kind == 'tunnel' else ('door',) + tuple(sorted((a, b)))
            if b not in dep or key in seen:
                continue
            if kind == 'door' and not (areas[b][1] == 'interior' and 'cave' in areas[b][2]) \
                    and not (areas[a][1] == 'interior' and 'cave' in areas[a][2]):
                continue
            if kind not in ('tunnel', 'door'):
                continue
            seen.add(key)
            x, y = (a, b) if (dep[a], a) <= (dep[b], b) else (b, a)
            out.append((x, y, via, kind))
    out.sort(key=lambda t: (dep[t[0]], dep[t[1]], t[2]))
    return out


def name(qs, uid):
    return (qs['areas'].get(uid) or [None, None, uid])[2]


def leg(H, to, tag):
    """Generator: walk to area `to` -> (ok, secs)."""
    t0 = time.time()
    r = yield from s_lanes.walkTo(H, 'tunnels', lambda st: s_story.goto(H, st, to, tag=tag), LEG, name(s_story.questSpots(), to))
    return r is True and s_story.hereArea(H) == to, round(time.time() - t0)


def run(H):
    qs = s_story.questSpots()
    plan = []
    for isl in ISLANDS:
        plan += [(isl,) + e for e in tunnelEdges(qs, isl) if not ONLY or e[2] in ONLY]
    H.ev('TUNNELS-START', islands=ISLANDS, n=len(plan),
         links=[[name(qs, a), name(qs, b), via, kind] for _, a, b, via, kind in plan], here=H.area())
    if not plan:
        H.ev('FAIL', why='no tunnel links on %s in quest_spots.json' % ISLANDS); return
    done, failed = [], []
    isl0 = None
    for i, (isl, a, b, via, kind) in enumerate(plan):
        tag = '%d/%d' % (i + 1, len(plan))
        if isl != isl0:
            if s_lanes.islandOf(H) != isl:
                # out to the open island first (a cave of the last island is not where areaTeleport starts from)
                if isl0 is not None:
                    yield from leg(H, isl0, 'out')
                if not (yield from s_lanes.onIsland(H, 'tunnels', isl)):
                    H.ev('TUNNEL-FAIL', link=tag, why='could not get to island %s' % isl)
                    failed += [p[3] for p in plan if p[0] == isl]
                    isl0 = isl
                    continue
            s_lanes.stage(H, 'tunnels', 'island', island=isl, islandName=name(qs, isl))   # ev() takes name itself
            isl0 = isl
        if via in failed:
            continue
        kw = dict(link=tag, via=via, kind=kind, frm=name(qs, a), to=name(qs, b))
        ok, secs = yield from leg(H, a, 'near-side')
        if not ok:
            H.ev('TUNNEL-FAIL', why='could not reach the near side', at=H.area(), secs=secs, **kw)
            failed.append(via)
            continue
        s_lanes.stage(H, 'tunnels', 'at-near-side', **kw)
        ok, secs = yield from leg(H, b, 'through')
        if not ok:
            H.ev('TUNNEL-FAIL', why='did not come out on the far side', at=H.area(), secs=secs, **kw)
            failed.append(via)
            continue
        H.ev('TUNNEL-THROUGH', secs=secs, **kw)
        s_lanes.stage(H, 'tunnels', 'through', **kw)
        ok, secs = yield from leg(H, a, 'back')
        if not ok:
            H.ev('TUNNEL-FAIL', why='did not come back', at=H.area(), secs=secs, **kw)
            failed.append(via)
            continue
        H.ev('TUNNEL-BACK', secs=secs, **kw)
        s_lanes.stage(H, 'tunnels', 'back', **kw)
        done.append(via)
    H.ev('TUNNELS-END', done=len(done), failed=failed, n=len(plan), area=H.area())
    if failed:
        H.ev('FAIL', why='%d of %d links failed' % (len(failed), len(plan)), failed=failed, done=len(done)); return
    H.ev('PASS', what='walked through and back all %d cave and tunnel links' % len(plan))
