"""CANNON PASS (fishing/recon lane, 11-21): one cannon defense (server-tree patch 0443, client 56).
Walk to the gold pile at the end of the Port Royal docks, step on it, land on the private cannon island, man a cannon,
sink the raiders as long as the fight lasts, see the result panel, press 'Go home', be paid.

What is the game's own and what is the bot's (the report says the same):
  walk to the pile       held keys through s_lanes.walkTo / s_story.near, never setPos
  hand-over              the 'shift' event (the real interact key); the direct requestInteraction is the logged fallback
  man a cannon           'shift' again at the nearest island cannon -> the game's own startWeapon (state 'Cannon', mouse look)
  aim                    the BOT sets the cannon's own aim nodes (hNode heading, pivot pitch) from the raider's position, with a
                         lead, and solves the pitch from the game's own cannonball numbers (power x 0.6, gravity x 4). A player does
                         this with the mouse: the bot has no mouse.
  fire                   the 'mouse1' event, the game's own fireCannon -> _doFireCannon (the ball, its collisions and the hit
                         report are the game's)
  wave / sinking / pay   the AI's own (world state is read as the HUD gets it); the pay is read as gold before / after + the result
  leave                  the end panel's own 'Go home' button command (the direct world.leave() is the logged fallback)

PASS needs: a cannon manned, >= 1 shot fired, >= 1 raider sunk, the result panel shown, gold up by exactly the reward the panel
names, back on Port Royal in LandRoam. A lost fight with >= 1 sunk still passes (the balance is not a bug); the line says won / lost.

Lines: CANNON-START, STAGE step=cannonpass what=at-island / pile / interact / handover / cannons / manned / fight / result / paid / home,
CANNON-VIEW, CANNON-PHASE, CANNON-FIRE, CANNON-HP, CANNON-SUNK, CANNON-RESULT, CANNON-SHOT, CANNON-PAID, then one PASS or FAIL naming the stage.
Never touches Host's pirate or the boys'. env: CANNON_SECS (whole-run limit, 1500), CANNON_SHOTS (D:\\scratch\\lanes\\cannonpass\\shots),
CANNON_FROM (island, default Port Royal)."""
import math, os, sys, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402
import s_story   # noqa: E402
import sailing   # noqa: E402

SECS = float(os.environ.get('CANNON_SECS', '1500'))
SHOTS = os.environ.get('CANNON_SHOTS', r'C:\PiratesBots\out\cannonpass\shots')
FROM = os.environ.get('CANNON_FROM', s_lanes.PR)
NEVER = (100000170, 100000173, 100000656, 100000665)       # Host's pirate + ship, the boys' pirates
PILE_POS = (10.0, -1680.0, 13.7)                             # Port Royal island frame: the gold pile (0443 PortRoyalIsland.py)
G = 32.174 * 4.0                                             # ProjectileInterval gravityMult 4.0 in Cannon.playAttack
PHASES = {0: 'lobby', 1: 'wave', 2: 'break', 3: 'won', 4: 'lost'}
MIN_P, MAX_P = -12.0, 24.0                                   # CannonCamera pitch limits
ARC_H = 58.0                                                 # CannonCamera heading limit is +-60 from the cannon's parent
ONCE = {}


def named(H, cls):
    return [o for o in list(H.cr.doId2do.values()) if type(o).__name__ == cls]


def entrances(H):
    return named(H, 'DistributedDefendEntrance')


def world(H):
    w = named(H, 'DistributedDefendWorld')
    return w[0] if w else None


def cannons(H):
    """The manned-able cannons in the client. The cannon defense's cannons are DistributedFortCannon (a subclass of
    DistributedIslandCannon), so match the whole family by class name up the MRO, not the exact type."""
    out = []
    for o in list(H.cr.doId2do.values()):
        if 'DistributedIslandCannon' in [k.__name__ for k in type(o).__mro__] and getattr(o, 'prop', None) is not None:
            out.append(o)
    return out


def shot(H, name):
    if name in ONCE:
        return
    ONCE[name] = 1
    from panda3d.core import Filename
    p = os.path.join(SHOTS, name + '.png')
    try:
        os.makedirs(SHOTS, exist_ok=True)
        H.B.graphicsEngine.renderFrame()
        ok = H.B.win.saveScreenshot(Filename.fromOsSpecific(p))
    except Exception as e:
        ok = 'err %r' % e
    H.ev('CANNON-SHOT', name=name, path=p, ok=ok, gs=H.la.getGameState())


def wstate(w):
    """The world's HUD state as a dict: phase, wave, secs, left, sunk, gold."""
    try:
        s = list(w.state)
        return dict(phase=s[0], name=PHASES.get(s[0], s[0]), wave=s[1], secs=s[2], left=s[3], sunk=s[4], gold=s[5])
    except Exception:
        return dict(phase=-1, name='?', wave=0, secs=0, left=0, sunk=0, gold=0)


def mstate(H, cannon):
    """Everything the manning key and the direct request depend on, one dict (each item guarded: a missing attribute is itself the answer).
    Cannon defense run 4 (11-22 00:33): beside a cannon in state Proximity, 'shift' and then the direct requestInteraction both left the
    pirate in LandRoam and nothing in the logs said why. The key only works while the interaction manager runs, is not locked and has picked
    the cannon (it arms 'shift' on the picked object), and the pirate is not airborne; the request needs the AI's accept to come back."""
    d = {}

    def g(name, f):
        try:
            d[name] = f()
        except Exception as ex:
            d[name] = 'ERR %r' % ex
    mgr = H.cr.interactionMgr
    la = H.la
    g('gs', la.getGameState)
    g('cstate', cannon.getCurrentOrNextState)
    g('allow', lambda: cannon.allowInteract)
    g('userId', lambda: cannon.userId)
    g('shift_armed', lambda: cannon.isAccepting('shift'))
    g('mgr_task', lambda: bool(taskMgr.hasTaskNamed('InteractionManagerUpdate')))
    g('mgr_locked', lambda: mgr._InteractionManager__locked)
    g('mgr_nearest', lambda: getattr(mgr.getNearest(), 'doId', None))
    g('mgr_current', lambda: getattr(mgr.getCurrentInteractive(), 'doId', None))
    g('mgr_list', lambda: [[getattr(o, 'doId', None), p] for (o, p) in mgr.getInteractives()])
    g('airborne', la.isAirborne)
    g('motion', lambda: la.motionFSM.getCurrentOrNextState())
    g('world', lambda: type(H.cr.activeWorld).__name__ if H.cr.activeWorld is not None else None)
    g('la_cannon', lambda: getattr(getattr(la, 'cannon', None), 'doId', None))
    g('mode', lambda: cannon.modeFSM.getCurrentState().getName())
    g('dist', lambda: round(s_story.hdist(H, cannon), 1))
    return d


def tele_state(H):
    """What can still move the pirate's game state after a teleport arrival (each item guarded). Cannon defense run 5 (11-22 02:25): the
    bot manned a cannon while the teleport loading screen was still up; ~1 s later LocalPirate.doFadeIn (the second run of the 'irisIn'
    timer, 2 s after allInterestsComplete) did b_setGameState(defaultState) and pulled the pirate out of 'Cannon' (the cannon stayed in 'Use'
    with the pirate as user, so a repeat request got no new setMovie). A kid cannot act under the loading screen: the bot waits for it too."""
    d = {}

    def g(name, f):
        try:
            d[name] = f()
        except Exception as ex:
            d[name] = 'ERR %r' % ex
    la = H.la
    g('loading', lambda: bool(H.cr.loadingScreen.state))
    g('iris', lambda: bool(taskMgr.hasTaskNamed(la.taskName('irisIn'))))
    g('trans', lambda: bool(la.gameFSM.isInTransition()))
    g('gs', la.getGameState)
    g('cannon', lambda: getattr(getattr(la, 'cannon', None), 'doId', None))
    return d


def arrived(H):
    """True once the arrival is over: no loading screen, no pending fade-in timer, no game-state transition, in LandRoam."""
    t = tele_state(H)
    return t['loading'] is not True and t['iris'] is not True and t['trans'] is not True and t['gs'] == 'LandRoam'


def tap_gamestate(H):
    """From here on, log (with the caller's stack) every game-state change made while the pirate is at / entering a cannon."""
    la = H.la
    orig = la.b_setGameState

    def tap(state, *a, **k):
        cur = la.getGameState()
        if cur == 'Cannon' or state == 'Cannon' or getattr(la, 'cannon', None) is not None:
            frames = ['%s:%d %s' % (os.path.basename(f.filename), f.lineno, f.name) for f in traceback.extract_stack()[:-1]][-7:]
            H.ev('CANNON-GS-CHANGE', frm=cur, to=state, by=' < '.join(reversed(frames)), tele=tele_state(H))
        return orig(state, *a, **k)
    la.b_setGameState = tap


def tap_cannon(H, cannon):
    """Log every update the cannon sends and every answer that reaches it, so a request that never gets an answer is told apart from one
    that is answered and ignored."""
    sent = cannon.sendUpdate

    def send(field, *a, **k):
        H.ev('CANNON-SENT', field=field, args=repr(a)[:120], cstate=cannon.getCurrentOrNextState())
        return sent(field, *a, **k)
    cannon.sendUpdate = send
    for name in ('acceptInteraction', 'rejectInteraction', 'setUserId', 'setMovie', 'startWeapon', 'stopWeapon', 'requestExit'):
        orig = getattr(cannon, name, None)
        if orig is None:
            continue

        def f(*a, _o=orig, _n=name, **k):
            H.ev('CANNON-GOT', what=_n, args=repr(a)[:100], gs=H.la.getGameState())
            return _o(*a, **k)
        setattr(cannon, name, f)


def hp(ship):
    for name in ('getHp', ):
        try:
            v = getattr(ship, name)()
            if isinstance(v, (list, tuple)):
                v = v[0]
            return v
        except Exception:
            pass
    return getattr(ship, 'hp', None)


def raiders(H):
    out = []
    for o in named(H, 'NPCShip'):
        try:
            h = hp(o)
            if h is not None and h <= 0:
                continue
            out.append(o)
        except Exception:
            continue
    return out


def towardPile(H, st):
    """s_lanes.walkTo's function: ('pile', doId) once the entrance is in reach, else a walk toward PILE_POS in the island frame."""
    es = entrances(H)
    if es:
        e = min(es, key=lambda o: s_story.hdist(H, o))
        if s_story.near(H, e, 6.0, st, face=True, tag='to-pile'):
            H.walk_cancel()
            return ('pile', e.doId)
        return 'walk-to-pile %s' % e.doId
    org = s_story.areaObj(H, FROM)
    if org is None:
        return 'no-island-object'
    if s_story.near(H, PILE_POS, 30.0, st, face=False, ref=org, tag='to-pile-area'):
        H.walk_cancel()
        return ('at-area', 0)
    return 'walk-to-pile-area'


def towardCannon(H, st):
    cs = cannons(H)
    if not cs:
        return 'no-cannon-in-view'
    c = min(cs, key=lambda o: s_story.hdist(H, o))
    if s_story.near(H, c, 6.0, st, face=True, tag='to-cannon'):
        H.walk_cancel()
        return ('cannon', c.doId)
    return 'walk-to-cannon %s' % c.doId


def flight(sz, pitch, power, d):
    """(seconds, height at horizontal distance d) of a ball that leaves at height sz with `power` at `pitch` degrees."""
    th = math.radians(pitch)
    vh = power * math.cos(th)
    if vh < 1.0:
        return None
    t = d / vh
    return t, sz + power * math.sin(th) * t - 0.5 * G * t * t


def solve(sz, d, tz, power):
    """The pitch (degrees) whose ball is at height tz at distance d, and the miss in feet, in the cannon's pitch limits; or None."""
    best = None
    p = MIN_P
    while p <= MAX_P + 1e-6:
        f = flight(sz, p, power, d)
        if f is not None:
            err = abs(f[1] - tz)
            if best is None or err < best[1]:
                best = (p, err, f[0])
        p += 0.25
    return best


class Track:
    """Raider speed from successive positions (the client smooths them), so the bot can lead the shot."""

    def __init__(self):
        self.last = {}      # doId -> (t, x, y)
        self.vel = {}       # doId -> (vx, vy)

    def update(self, H):
        now = time.time()
        for s in raiders(H):
            p = s.getPos(H.render)
            old = self.last.get(s.doId)
            if old is None or now - old[0] >= 0.5:
                if old is not None and now - old[0] < 3.0:
                    dt = now - old[0]
                    self.vel[s.doId] = ((p[0] - old[1]) / dt, (p[1] - old[2]) / dt)
                self.last[s.doId] = (now, p[0], p[1])


def aim(H, cannon, ship, trk, power):
    """Set the cannon's aim nodes at `ship` with a lead. -> dict(ok, why, ...). Does not fire."""
    prop = cannon.prop
    sp = prop.cannonExitPoint.getPos(H.render)
    tp = ship.getPos(H.render)
    vx, vy = trk.vel.get(ship.doId, (0.0, 0.0))
    px, py = tp[0], tp[1]
    res = None
    for _ in range(3):
        d = math.hypot(px - sp[0], py - sp[1])
        res = solve(sp[2], d, tp[2] + 8.0, power)
        if res is None:
            return dict(ok=False, why='no pitch', d=round(d))
        t = res[2]
        px, py = tp[0] + vx * t, tp[1] + vy * t
    d = math.hypot(px - sp[0], py - sp[1])
    res = solve(sp[2], d, tp[2] + 8.0, power)
    if res is None or res[1] > 14.0:
        return dict(ok=False, why='out of range', d=round(d), err=None if res is None else round(res[1], 1))
    h = math.degrees(math.atan2(-(px - sp[0]), py - sp[1]))
    prop.hNode.setH(H.render, h)
    rel = prop.hNode.getH()
    if abs(rel) > ARC_H:
        return dict(ok=False, why='outside the cannon arc', rel=round(rel), d=round(d))
    prop.pivot.setH(0.0)
    prop.pivot.setP(res[0])
    prop.currentHpr = (h, res[0], 0)
    return dict(ok=True, h=round(h, 1), rel=round(rel, 1), pitch=res[0], miss=round(res[1], 1), d=round(d), t=round(res[2], 2),
                vel=[round(vx), round(vy)])


def power_of(cannon):
    """The ball's launch speed, the game's own number (Cannon.playAttack: attack power x 0.6)."""
    from pirates.battle import WeaponGlobals
    return WeaponGlobals.getAttackProjectilePower(cannon.skillId, cannon.getAmmoSkillId()) * 0.6


def run(H):
    import builtins
    messenger = builtins.messenger
    la = H.la
    H.ev('CANNON-START', pirate=la.doId, frm=FROM, gold=s_lanes.gold(H), here=H.area())
    if la.doId in NEVER:
        H.ev('FAIL', why='refusing: pirate %s is not a test pirate' % la.doId); return
    if not (yield from s_lanes.onIsland(H, 'cannonpass', FROM)):
        H.ev('FAIL', why='could not get to %s' % FROM, area=H.area()); return
    s_lanes.stage(H, 'cannonpass', 'at-island', island=FROM)
    t0 = time.time()
    g0 = s_lanes.gold(H)

    yield ('until', lambda: bool(entrances(H)), 8, 'the gold pile in the client')
    if not entrances(H):
        H.ev('CANNON-TO-AREA', why='no gold pile in view at the start: walking toward the pile spot', pos=list(PILE_POS), la=H.P(la))
        yield from s_lanes.walkTo(H, 'cannonpass', lambda st: towardPile(H, st), 300, 'the gold pile')
        yield ('until', lambda: bool(entrances(H)), 10, 'the gold pile in the client (at the area)')
    if not entrances(H):
        H.ev('FAIL', stage='pile', why='no DistributedDefendEntrance came into the client (server patch 0443 live? want-cannon-defense?)',
             area=H.area(), la=H.P(la)); return
    e = min(entrances(H), key=lambda o: s_story.hdist(H, o))
    H.ev('CANNON-VIEW', tag='pile', pile=e.doId, pos=[round(v, 1) for v in e.getPos(H.render)], me=H.P(la), d=round(s_story.hdist(H, e), 1))
    s_lanes.stage(H, 'cannonpass', 'pile', pile=e.doId)

    r = yield from s_lanes.walkTo(H, 'cannonpass', lambda st: towardPile(H, st), 150, 'the gold pile')
    e = min(entrances(H), key=lambda o: s_story.hdist(H, o)) if entrances(H) else None
    if e is None:
        H.ev('FAIL', stage='walk', why='the pile left the client'); return
    d = s_story.hdist(H, e)
    if not isinstance(r, tuple):
        if d > 14:
            H.ev('FAIL', stage='walk', why='could not walk to the pile (%.1f ft away)' % d, la=H.P(la), area=H.area()); return
        H.ev('CANNON-WALK-STUCK', why='the walk stopped %.1f ft from the pile' % d, la=H.P(la))
        H.walk_cancel()
    yield ('until', lambda: e.getCurrentOrNextState() == 'Proximity', 6, 'pile prompt')
    H.ev('CANNON-PROMPT', state=e.getCurrentOrNextState(), allow=getattr(e, 'allowInteract', None), d=round(d, 1))
    shot(H, 'cannon-1-pile')
    s_lanes.stage(H, 'cannonpass', 'interact', d=round(d, 1))

    # hand-over: the key first, the direct request as the logged fallback
    via = 'key'
    messenger.send('shift')
    yield ('until', lambda: world(H) is not None, 45, 'cannon world by key')
    if world(H) is None:
        via = 'fallback'
        H.ev('CANNON-INTERACT-FALLBACK', why='the shift key did not take the pirate to the cannon island (state %s)' % e.getCurrentOrNextState())
        H.walk_cancel()
        try:
            e.requestInteraction(la.doId)
        except Exception as ex:
            H.ev('CANNON-INTERACT-ERR', err=repr(ex))
        yield ('until', lambda: world(H) is not None, 60, 'cannon world direct')
    w = world(H)
    if w is None:
        H.ev('FAIL', stage='handover', why='no DistributedDefendWorld came into the client after the interact', via=via,
             gs=la.getGameState(), area=H.area()); return
    s_lanes.stage(H, 'cannonpass', 'handover', via=via, world=w.doId)
    # the result arrives as one update: keep it
    result = {}
    orig = w.setDefendResult

    def tap(won, shipsSunk, goldKept, goldReward, _orig=orig):
        result.update(won=won, sunk=shipsSunk, kept=goldKept, reward=goldReward, at=time.time())
        H.ev('CANNON-RESULT-UPDATE', **result)
        return _orig(won, shipsSunk, goldKept, goldReward)
    w.setDefendResult = tap

    yield ('until', lambda: la.getGameState() == 'LandRoam' and bool(cannons(H)), 90, 'LandRoam on the cannon island with cannons')
    cs = cannons(H)
    if la.getGameState() != 'LandRoam' or not cs:
        H.ev('FAIL', stage='cannons', why='no cannon with a prop in the client, or the pirate is not in LandRoam (fell off the platform?)',
             gs=la.getGameState(), n=len(cs), area=H.area(), la=H.P(la),
             classes=sorted(set(type(o).__name__ for o in list(H.cr.doId2do.values()) if 'annon' in type(o).__name__))); return
    H.ev('CANNON-VIEW', tag='island', cannons=[[c.doId, [round(v, 1) for v in c.getPos(H.render)]] for c in cs], me=H.P(la),
         state=wstate(w), area=H.area())
    s_lanes.stage(H, 'cannonpass', 'cannons', n=len(cs), state=wstate(w))
    tap_gamestate(H)

    # the arrival is not over while the loading screen is up (run 5: the bot manned a cannon under it, and the teleport cleanup's fade-in
    # timer pulled the pirate out of 'Cannon' ~1 s later). Wait for it like a kid does: loading screen gone, no irisIn timer, no state
    # transition, LandRoam, all of that held for 4 s (the timer runs 2 s after the loading screen hides).
    H.ev('CANNON-LOAD-WAIT', tag='start', **tele_state(H))
    ok_since = {'t': None}

    def calm():
        if arrived(H):
            if ok_since['t'] is None:
                ok_since['t'] = time.time()
            return time.time() - ok_since['t'] >= 4.0
        ok_since['t'] = None
        return False
    yield ('until', calm, 15, 'the teleport arrival to be over (loading screen gone, fade-in done)')
    H.ev('CANNON-LOAD-WAIT', tag='done' if calm() else 'TIMEOUT', **tele_state(H))
    shot(H, 'cannon-2-island')

    # man the nearest cannon: walk up, the key, the direct request as the fallback
    r = yield from s_lanes.walkTo(H, 'cannonpass', lambda st: towardCannon(H, st), 90, 'a cannon')
    cs = cannons(H)
    if not cs:
        H.ev('FAIL', stage='walk', why='the cannons left the client'); return
    cannon = min(cs, key=lambda o: s_story.hdist(H, o))
    d = s_story.hdist(H, cannon)
    if not isinstance(r, tuple):
        if d > 16:
            H.ev('FAIL', stage='walk', why='could not walk to a cannon (%.1f ft away)' % d, la=H.P(la)); return
        H.walk_cancel()
    try:
        cst = cannon.getCurrentOrNextState()
    except Exception:
        cst = None
    H.ev('CANNON-PROMPT', what='cannon', cannon=cannon.doId, state=cst, d=round(d, 1))

    def manned():
        try:
            return (la.getGameState() == 'Cannon' and getattr(la, 'cannon', None) is cannon
                    and cannon.modeFSM.getCurrentState().getName() == 'fireCannon')
        except Exception:
            return False
    via2 = 'key'
    mgr = H.cr.interactionMgr
    tap_cannon(H, cannon)
    H.ev('CANNON-MAN-STATE', tag='arrived', **mstate(H, cannon))
    # the manager arms 'shift' on the cannon it picks (it re-picks every 0.2 s while it runs): wait for that, and say so when it never does
    if not mstate(H, cannon).get('mgr_task'):
        H.ev('CANNON-MAN-MGR', what='the interaction manager is not running: start() (the game left it stopped or locked)',
             locked=mstate(H, cannon).get('mgr_locked'))
        mgr.start()
    def picked():
        try:
            return mgr.getNearest() is cannon and bool(cannon.isAccepting('shift'))
        except Exception:
            return False
    yield ('until', picked, 8, 'the interaction manager picks the cannon')
    H.ev('CANNON-MAN-STATE', tag='after-pick', **mstate(H, cannon))

    stamp = {'t': 0.0}

    def watch():
        """manned(), and one state line every 3 s while we wait so the log shows what changed (and when) after each press."""
        if time.time() - stamp['t'] >= 3.0:
            stamp['t'] = time.time()
            H.ev('CANNON-MAN-STATE', tag='waiting', **mstate(H, cannon))
        return manned()
    for press in range(3):
        H.ev('CANNON-MAN-PRESS', n=press + 1, **{k: v for k, v in mstate(H, cannon).items() if k in ('cstate', 'shift_armed', 'mgr_nearest', 'airborne', 'gs')})
        messenger.send('shift')
        yield ('until', watch, 4, 'manned by key')
        if manned():
            break
    H.ev('CANNON-MAN-STATE', tag='after-key', **mstate(H, cannon))
    if not manned():
        via2 = 'fallback'
        H.ev('CANNON-MAN-FALLBACK', why='the shift key did not man the cannon (state %s, gs %s)' % (cst, la.getGameState()))
        H.walk_cancel()
        try:
            cannon.requestInteraction(la.doId)
        except Exception as ex:
            H.ev('CANNON-MAN-ERR', err=repr(ex))
        H.ev('CANNON-MAN-STATE', tag='after-request', **mstate(H, cannon))
        yield ('until', watch, 25, 'manned direct')
    if not manned():
        H.ev('CANNON-MAN-STATE', tag='failed', **mstate(H, cannon))
        H.ev('FAIL', stage='manned', why='could not man a cannon', gs=la.getGameState(), via=via2, cannon=cannon.doId); return
    s_lanes.stage(H, 'cannonpass', 'manned', via=via2, cannon=cannon.doId, d=round(d, 1))
    shot(H, 'cannon-3-manned')
    try:
        power = power_of(cannon)
        rmax = power * power * math.sin(2 * math.radians(MAX_P)) / G
        from pirates.battle import WeaponGlobals
        infinite = WeaponGlobals.isInfiniteAmmo(cannon.getAmmoSkillId())
    except Exception as ex:
        H.ev('FAIL', stage='manned', why='no cannonball numbers: %r' % ex); return
    H.ev('CANNON-BALL', power=round(power, 1), skill=getattr(cannon, 'skillId', None), ammo=cannon.getAmmoSkillId(),
         flat_range_at_max_pitch=round(rmax), volley=getattr(cannon, 'volley', None), infinite=infinite,
         shots=getattr(cannon, 'numShots', None))

    # the fight
    trk = Track()
    fires = hits = 0
    last_press = 0.0
    last_phase = None
    last_sunk = 0
    last_log = 0.0
    hpmap = {}
    dropped = 0
    seen_target = False
    fired_picture = False
    man_t = time.time()
    hold_n = 0
    while time.time() - t0 < SECS:
        wd = world(H)
        if wd is not w or wd is None:
            H.ev('CANNON-WORLD-GONE', gs=la.getGameState(), area=H.area(), state=wstate(w), result=dict(result))
            break
        if hold_n < 6 and time.time() - man_t >= hold_n:        # one line a second for the first seconds: when does the pirate stay / leave
            hold_n += 1
            H.ev('CANNON-HOLD', n=hold_n, manned=manned(), **tele_state(H),
                 **{k: v for k, v in mstate(H, cannon).items() if k in ('cstate', 'userId', 'mode')})
        st = wstate(w)
        if st['phase'] != last_phase:
            H.ev('CANNON-PHASE', **st)
            s_lanes.stage(H, 'cannonpass', 'fight', **st)
            last_phase = st['phase']
            if st['phase'] == 1 and st['wave'] == 0:
                shot(H, 'cannon-4-wave1')
        if st['sunk'] > last_sunk:
            H.ev('CANNON-SUNK', sunk=st['sunk'], wave=st['wave'], fires=fires, hits=hits, gold=st['gold'])
            if last_sunk == 0:
                shot(H, 'cannon-5-first-sunk')
            last_sunk = st['sunk']
        if result or getattr(w, 'resultPanel', None) is not None or st['phase'] in (3, 4):
            break
        if not manned():
            if la.getGameState() == 'LandRoam' and dropped < 3:
                dropped += 1
                H.ev('CANNON-DROPPED', n=dropped, state=st, tele=tele_state(H),
                     **{k: v for k, v in mstate(H, cannon).items() if k in ('cstate', 'userId', 'mode', 'la_cannon', 'shift_armed', 'mgr_nearest')})
                # leave first: the cannon is still in 'Use' with this pirate as its user and the client still holds la.cannon, so a plain
                # repeat request only gets an accept and no new setMovie / startWeapon (run 5)
                try:
                    cannon.requestExit()
                except Exception as ex:
                    H.ev('CANNON-MAN-ERR', what='requestExit', err=repr(ex))
                yield 1.5
                H.ev('CANNON-MAN-STATE', tag='after-exit', **mstate(H, cannon))
                messenger.send('shift')                         # the key again, the direct request as the fallback
                yield ('until', manned, 4, 'manned again by key')
                if not manned():
                    try:
                        cannon.requestInteraction(la.doId)
                    except Exception as ex:
                        H.ev('CANNON-MAN-ERR', what='requestInteraction', err=repr(ex))
                    yield ('until', manned, 6, 'manned again direct')
                H.ev('CANNON-REMAN', n=dropped, ok=manned(), **mstate(H, cannon))
                continue
            yield 0.5
            continue
        trk.update(H)
        rs = raiders(H)
        now = time.time()
        for s in rs:                                            # hull points, to see a hit land
            h = hp(s)
            old = hpmap.get(s.doId)
            if old is not None and h is not None and h < old:
                hits += 1
                H.ev('CANNON-HIT', ship=s.doId, hp=h, was=old, hits=hits, fires=fires)
            hpmap[s.doId] = h
        if now - last_log >= 5.0 and rs:
            last_log = now
            cp = cannon.prop.cannonExitPoint.getPos(H.render)
            H.ev('CANNON-HP', n=len(rs), ships=[[s.doId, hp(s), round((s.getPos(H.render) - cp).length())] for s in rs[:6]], fires=fires,
                 hits=hits, state=st)
        target, plan = None, None
        if rs and getattr(cannon, 'volley', 0) > 0:
            cp = cannon.prop.cannonExitPoint.getPos(H.render)
            for s in sorted(rs, key=lambda o: (o.getPos(H.render) - cp).length()):
                a = aim(H, cannon, s, trk, power)
                if a['ok']:
                    target, plan = s, a
                    break
        if target is not None and not seen_target:
            seen_target = True
            H.ev('CANNON-TARGET', ship=target.doId, **plan)
        if target is not None and now - last_press >= 0.7:
            last_press = now
            v0 = getattr(cannon, 'volley', 0)
            messenger.send('mouse1')                            # the game's own fire key path
            yield 0.45                                          # the ball leaves ~10 frames later; re-check the volley
            if getattr(cannon, 'volley', 0) < v0:
                fires += 1
                if fires <= 12 or fires % 10 == 0:
                    H.ev('CANNON-FIRE', n=fires, ship=target.doId, **plan)
                if not fired_picture:
                    fired_picture = True
                    shot(H, 'cannon-4b-firing')
            continue
        yield 0.25

    shot(H, 'cannon-6-end-of-fight')
    s_lanes.stage(H, 'cannonpass', 'result', result=dict(result), fires=fires, hits=hits, state=wstate(w) if world(H) is w else None)
    if not result:
        yield ('until', lambda: bool(result) or world(H) is not w, 20, 'result panel')
    if not result:
        H.ev('FAIL', stage='result', why='the fight did not end with a result in the run time', fires=fires, hits=hits,
             state=wstate(w) if world(H) is w else None, secs=round(time.time() - t0)); return
    panel = getattr(w, 'resultPanel', None)
    yield 1.0
    shot(H, 'cannon-7-result')
    H.ev('CANNON-RESULT', won=bool(result['won']), sunk=result['sunk'], kept=result['kept'], reward=result['reward'], panel=panel is not None,
         fires=fires, hits=hits, secs=round(time.time() - t0))

    # pay: the reward came with the end of the fight
    yield ('until', lambda: s_lanes.gold(H) - g0 >= result['reward'], 15, 'gold paid')
    paid = s_lanes.gold(H) - g0
    H.ev('CANNON-PAID', gold=s_lanes.gold(H), goldBefore=g0, paid=paid, reward=result['reward'], sunk=result['sunk'], kept=result['kept'],
         won=bool(result['won']))
    if result['sunk'] < 1:
        H.ev('FAIL', stage='sink', why='the fight ended with no raider sunk (%d shots, %d hull hits seen)' % (fires, hits), fires=fires,
             hits=hits, result=dict(result)); return
    if fires < 1:
        H.ev('FAIL', stage='fire', why='no shot was fired by the bot', result=dict(result)); return
    if paid != result['reward']:
        H.ev('FAIL', stage='paid', why='the gold change (%d) is not the reward the panel names (%d)' % (paid, result['reward']),
             goldBefore=g0, gold=s_lanes.gold(H)); return
    s_lanes.stage(H, 'cannonpass', 'paid', paid=paid)

    # leave: the panel's own button; the direct world.leave() is the logged fallback
    how = 'button'
    try:
        btn = w.resultPanel.bLeave
        btn.commandFunc(None)
    except Exception as ex:
        how = 'direct'
        H.ev('CANNON-LEAVE-FALLBACK', why='the Go home button did not take %r' % ex)
        try:
            w.leave()
        except Exception as ex2:
            H.ev('CANNON-LEAVE-ERR', err=repr(ex2))
    yield ('until', lambda: world(H) is None and la.getGameState() == 'LandRoam' and sailing.hereUid(H) == FROM, 60, 'home on Port Royal')
    home = world(H) is None and la.getGameState() == 'LandRoam' and sailing.hereUid(H) == FROM
    s_lanes.stage(H, 'cannonpass', 'home', ok=home, how=how)       # stage() adds gs + area itself (passing them again raised TypeError, run 6)
    yield 3.0
    shot(H, 'cannon-8-home')
    if not home:
        H.ev('FAIL', stage='home', why='did not get back to Port Royal after Go home', gs=la.getGameState(), area=H.area(),
             world=world(H) is not None); return
    H.ev('PASS', what='walked onto the gold pile, landed on the cannon island, manned a cannon and fired it, sank raiders, saw the result '
                      'panel (%s), was paid, left by the Go home button' % ('won' if result['won'] else 'lost'),
         paid=paid, sunk=result['sunk'], kept=result['kept'], fires=fires, hits=hits, via=[via, via2, how], secs=round(time.time() - t0))
