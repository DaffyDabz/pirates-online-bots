"""Offline test of sailing.dinghyOrHop / pocketHop (MAIN52 / MAIN57 / MAIN59, 11-22): out of Tortuga tavern_2's door
the pirate stood in a pocket with no route to any dinghy, and the ship quest failed 'no open route to any dinghy' 3 times.
With no route he now teleports out to another island and back (the word in a story run, the map in a player bot) and
tries again, once per launch. MAIN59: the server turns away a teleport to the island he stands on ('already there'),
so a hop straight to it never moved him. Run: python3.9 t_sail_pocket.py <dir holding sailing.py>"""
import math, os, sys, types

D = os.path.abspath(sys.argv[1])
sys.path.insert(0, D)
for n in ('panda3d', 'panda3d.core', 'direct', 'direct.showbase', 'direct.showbase.DirectObject', 's_dock', 'paths'):
    sys.modules.setdefault(n, types.ModuleType(n))
sys.modules['panda3d.core'].Point3 = sys.modules['panda3d.core'].Vec3 = object
d = sys.modules['s_dock']
d.Keys = d.anchorShown = d.near = d.cls = None
sys.modules['paths'].dist = lambda a, b: math.hypot(b[0] - a[0], b[1] - a[1])
import sailing as S
assert getattr(S, 'dinghyOrHop', None) is not None, \
    'MAIN57: no dinghyOrHop, a pirate in a pocket with no route to a dinghy fails the launch 3 times and stalls'

TAVERN = (10819.8, 16860.9, 14.9)
DOCK = (10536.7, 17078.9, 3.5)
ISL = '1156207188.95dzlu'                   # Tortuga
PR = '1150922126.8dzlu'                     # Port Royal
SPAWN = {ISL: DOCK, PR: (100.0, 200.0, 5.0)}


class La:
    def __init__(s):
        s.pos, s.gs = TAVERN, 'LandRoam'

    def getPos(s, R):
        return s.pos

    def getGameState(s):
        return s.gs


class Tp:
    def __init__(s, h):
        s.h, s.asked = h, []

    def requestTeleportToIsland(s, uid):
        s.asked.append(uid)
        s.h.teleport(uid)


class H:
    """drop: island uids whose teleport never lands. The server turns away a teleport to the island he is on."""
    def __init__(s, drop=(), isl=ISL):
        s.la, s.render, s.evs, s.words, s.drop, s.isl = La(), None, [], [], set(drop), isl
        s.cr = types.SimpleNamespace(teleportMgr=Tp(s))

    def area(s):
        return ('DistributedIsland', s.isl, '')

    def ev(s, name, **kw):
        s.evs.append((name, kw))

    def P(s, np):
        return list(np.getPos(None))

    def mw(s, w):
        s.words.append(w)
        s.teleport(w.split()[1])

    def teleport(s, uid):
        if uid == s.isl or uid in s.drop:       # 'already there': teleportDenied -1, he stays put
            return
        s.isl, s.la.pos = uid, SPAWN[uid]


def hops(h):
    return [k for n, k in h.evs if n == 'POCKET-HOP']


def run(h, st, routed):
    """Drive dinghyOrHop with a to_dinghy stand-in: a dinghy only from the points in routed. -> (result, calls)."""
    calls = []

    def to_dinghy(H, here):
        calls.append(H.la.pos)
        if False:
            yield
        return 'dinghy' if H.la.pos in routed else None
    S.to_dinghy = to_dinghy
    g = S.dinghyOrHop(h, h.isl, st)
    try:
        y = next(g)
        while True:
            assert y[0] == 'until', y
            y = g.send(None)
    except StopIteration as e:
        return e.value, calls


os.environ.pop('STORY_PLAYER', None)
# MAIN57/59: no route from the pocket -> out to Port Royal and back, he lands by Tortuga's docks, the dinghy is found
h, st = H(), {}
r, calls = run(h, st, [DOCK])
assert h.words == ['areaTeleport ' + PR, 'areaTeleport ' + ISL], \
    'MAIN59: a hop straight to the island he stands on is turned away, he never moves: %s' % h.words
assert r == 'dinghy' and calls == [TAVERN, DOCK] and h.isl == ISL, (r, calls, h.isl)
assert hops(h)[0]['ok'] is True and hops(h)[0]['away'] == PR
# once per launch: the next try in the same launch does not hop again
h.la.pos = TAVERN
r, calls = run(h, st, [DOCK])
assert r is None and calls == [TAVERN] and len(h.words) == 2, (r, calls, h.words)
# a route from where he stands: no hop at all
h, st = H(), {}
r, calls = run(h, st, [TAVERN])
assert r == 'dinghy' and calls == [TAVERN] and h.words == [] and not h.evs
# on Port Royal the hop goes out to Tortuga and back
h, st = H(isl=PR), {}
h.la.pos = TAVERN
SPAWN[PR], keep = DOCK, SPAWN[PR]
r, calls = run(h, st, [DOCK])
SPAWN[PR] = keep
assert h.words == ['areaTeleport ' + ISL, 'areaTeleport ' + PR] and r == 'dinghy', (h.words, r)
# a player bot uses the map's island teleport, never a magic word
os.environ['STORY_PLAYER'] = '1'
h, st = H(), {}
r, calls = run(h, st, [DOCK])
assert r == 'dinghy' and h.words == [] and h.cr.teleportMgr.asked == [PR, ISL], (r, h.words)
os.environ.pop('STORY_PLAYER')
# the way out never lands: no way back asked, no second search, None, POCKET-HOP ok=False
h, st = H(drop=[PR]), {}
r, calls = run(h, st, [DOCK])
assert r is None and calls == [TAVERN] and h.words == ['areaTeleport ' + PR], (r, calls, h.words)
assert hops(h)[0]['ok'] is False and hops(h)[0]['out'] is False
# out lands but the way back never does: he is left on Port Royal, ok=False, no second search
h, st = H(drop=[ISL]), {}
r, calls = run(h, st, [DOCK])
assert r is None and calls == [TAVERN] and hops(h)[0]['ok'] is False and hops(h)[0]['back'] is False, (r, calls)
# not on land (a cutscene, aboard): no hop
h, st = H(), {}
h.la.gs = 'Cutscene'
r, calls = run(h, st, [DOCK])
assert r is None and h.words == [], (r, h.words)
print('pocket ok')
