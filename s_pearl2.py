"""Black Pearl twice in a row (11-16): the fight used to be playable once per server run (a finished instance was
never freed). Starts the Black Pearl, goes through its Reward with ~bpstate Reward, leaves like a player (the
instance's own leave), waits for the server to tear the old instance down, then starts it again and checks the
second instance is a new one with the pirate inside.
How it starts: the pirate's own treasure map when the client holds one (sendUpdate('requestStart', [5]) as the
DistributedTreasureMap does: the family server's real path); otherwise ~blackpearlai (logged, with why).
Log words: PEARL-START PEARL-IN PEARL-REWARD PEARL-LEAVE PEARL-OUT PEARL-GONE, then PASS or FAIL.
env: PEARL_RUNS (default 2), PEARL_WAIT (seconds to wait after leaving so the monitor tears the old one down, 30)."""
import os, time

RUNS = int(os.environ.get('PEARL_RUNS', '2'))
WAIT = float(os.environ.get('PEARL_WAIT', '30'))


def instance(H):
    return next((o for o in list(H.cr.doId2do.values()) if hasattr(o, 'requestTreasureMapLeave')), None)


def tmap(H):
    return next((o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedTreasureMap'), None)


def start(H, n):
    m = tmap(H)
    if m is not None:
        H.ev('PEARL-START', n=n, how='requestStart', map=m.doId)
        m.sendUpdate('requestStart', [5])
    else:
        H.ev('PEARL-START', n=n, how='~blackpearlai', why='the pirate holds no treasure map object (client side)')
        H.mw('blackpearlai')


def run(H):
    la = H.la
    yield ('until', lambda: la.getGameState() in ('LandRoam', 'ShipPilot'), 90, 'LandRoam')
    seen = []
    for n in range(1, RUNS + 1):
        start(H, n)
        # inside = the client instance has its island (the instance object exists while the pirate is still
        # mid-teleport from Port Royal)
        yield ('until', lambda: instance(H) is not None and len(getattr(instance(H), 'islands', {})) > 0
               and la.getGameState() == 'LandRoam', 180, 'instance %d' % n)
        i = instance(H)
        if i is None:
            H.ev('FAIL', why='start %d: no instance 180 s after the start' % n, gs=la.getGameState(), area=H.area())
            return
        if i.doId in seen:
            H.ev('FAIL', why='start %d: the same instance %d as an earlier start' % (n, i.doId))
            return
        seen.append(i.doId)
        H.ev('PEARL-IN', n=n, inst=i.doId, area=H.area(), la=H.P(la))
        yield 15                              # WaitClientsReady (10 s) into StageOne
        H.mw('bpstate Reward')
        H.ev('PEARL-REWARD', n=n, inst=i.doId)
        yield 8
        H.mw('bpstate Completed')
        yield 4
        H.ev('PEARL-LEAVE', n=n, inst=i.doId)
        try:
            i.requestTreasureMapLeave()
        except Exception as e:
            H.ev('FAIL', why='leave %d: %r' % (n, e))
            return
        yield ('until', lambda: instance(H) is None and la.getGameState() == 'LandRoam', 120, 'leave %d' % n)
        if instance(H) is not None:
            H.ev('FAIL', why='start %d: still in the instance 120 s after leaving' % n)
            return
        H.ev('PEARL-OUT', n=n, area=H.area())
        yield WAIT                            # the server's monitor tears the finished, empty instance down
    H.ev('PASS', why='%d starts in a row, instances %s' % (RUNS, seen), area=H.area())
