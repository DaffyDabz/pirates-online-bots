"""SINK1 / DOCK1 (pir-bot job 45, 11-19): the proofs for pir-boat's server patches 0362 and 0363, played like a player.

0362 (DistributedShipAI.b_setGameState): a sink sent 'Sinking' to the crew two or three times (setHp(0) starts it, the
shooter asks again, a late volley asks a third time). Each repeat ended the sinking scene on a black screen and
played it again, and the server restarted the crew-ashore timer. With 0362 the ship is told Sinking once.
0363 (DistributedShipBroadsideAI._doDamage): a volley still in the air when the pirate docked landed on his put-away
ship and sank it at the dock: Sunk, a repair bill he never earned, no launch until he paid. With 0363 a volley that
lands on a ship that is Sinking, Sunk, PutAway or Off (or has 0 hp) does nothing.

Client facts this rests on (client tree, read 11-19):
- GameFSMShip.enterSinking -> ship.registerMainBuiltFunction(ship.sinkingBegin); DistributedShip.sinkingBegin is the
  sinking scene (it sends ship.uniqueName('shipSinking') and puts the local crew in a Cutscene); its track ends with
  cleanupLocalSinking (the fade). The bound method is looked up when the state is entered, so the instance wrappers
  here count every scene.
- The server's setGameState(stateName, avId, timeStamp) reaches the ship and its owner view (PlayerShipOV.setGameState);
  both are wrapped and every state is logged (SHIP-STATE, with who).
- DistributedShip.sendCrewToIsland(islandId, posH): the server sends the crew ashore after a sink (about 20 s).
- DistributedShipBroadside.doBroadside(side, delays, hitPosList, zoneId, flightTime, timestamp): an NPC volley; it
  lands flightTime (max(1, dist / 500)) plus up to max(delays) (0.5) s later. The class method is wrapped (and put
  back) so every volley near our ship is logged (VOLLEY) with when it lands.
The client logs none of this by itself, so these lines are the client log the judge reads.

SINK_MODE=sink (SINK1): launch at SINK_FROM (Port Royal), find a Navy ship, keep alongside it (SINK_HOLD_R ft) without
  firing until it sinks us (SINK_SECS), then wait ashore (SINK_SETTLE s more for any late repeat).
  PASS = exactly 1 sinking scene, 'Sinking' told once (ship and owner view), and he lands on his return port
  (getReturnLocation(); none = Port Royal). Lines: SINK-START, SINK-FOE, SINK-HP, SHIP-STATE, SINK-SCENE, SINK-FADE,
  SINK-SENT (sendCrewToIsland), SINK-ASHORE, SINK-END, then PASS / FAIL.
  SINK_RELAUNCH=1 also launches again afterwards (pays or gets the free mend as a player would): SINK-RELAUNCH.
SINK_MODE=dock (DOCK1): launch, find a Navy ship, close in until it fires at us, sail home to SINK_FROM; at the anchor
  hold the sail down and press the anchor the moment a volley is in the air (DOCK_WAIT s for one). Ashore: the ship's
  state and hp over DOCK_ASHORE s, then launch again WITHOUT the shipwright (sailing.launch aboard=True) and compare
  the gold. PASS = a volley was in the air at the press, the ship is not Sunk and has hp, it launched again, and no
  gold went (no repair bill). FAIL = the ship is Sunk or at 0 hp after the dock (the 0363 bug) or would not launch.
  No volley at the press = that try is INCONCLUSIVE; up to DOCK_TRIES tries. landedAfterPutAway in DOCK-RESULT says
  whether a volley truly landed after the ship was put away (the exact 0363 case) or only during the dock.
  Lines: DOCK-START, DOCK-TRY, SINK-FOE, VOLLEY, DOCK-PRESS (the volley, its age, when it lands), DOCK-NO-VOLLEY,
  SHIP-STATE, DOCK-ASHORE, DOCK-RELAUNCH, DOCK-RESULT, DOCK-END, then PASS / FAIL / INCONCLUSIVE.
SINK_MODE=sink SINK_SEAT=cannon (SINK1 seat, job 47; proofs for 0364 server + 0365 client): as SINK1, but once the
  Navy ship has knocked our hp down to SEAT_HP of max he lets go of the wheel, walks to the nearest free deck cannon,
  sits on it and then presses nothing at all through the sink. From the first sinking scene the bot times: freed from
  the cannon (localAvatar.cannon gone), ashore (LandRoam on an island), and the server's eject (CLIENT_EJECT, the
  "connect again" box; or the client dropping to noConnection).
  PASS = freed and ashore within SEAT_ASHORE_BY s (65; the 0365 client), and the ship shown Sunk (SHIP-STATE or the
  owner view) within SEAT_SUNK_WAIT s of landing; or, on a client without 0365 only, the eject box within
  SEAT_EJECT_BY s (85). An eject on a 0365 client is a FAIL (0365 should have got him ashore first).
  The server half is for pir-test to read in the AI log (SEAT-END names it): ejected = one sunk-ship-eject for this
  avatar and ship (no sunk-ship-give-up unless he was still listed at 95 s); ashore = no sunk-ship-eject for him.
  Lines: SEAT-START (client0365 = the installed client has 0365), SINK-FOE, SINK-HP, SEAT-LEAVE-WHEEL, SEAT-GOTO,
  SINK-SEAT, SHIP-STATE, SINK-SCENE, SEAT-GS (every game state change), SEAT-FREED, SEAT-EJECT, SINK-ASHORE,
  SEAT-END, then PASS / FAIL (step sink-seat).
Test pirates only: pirate 100000170 and ship 100000173 are refused (FAIL). No magic word but the setup teleport onto
SINK_FROM (s_lanes.onIsland) and the repair gold s_shipquest.launchShip may give a broke test pirate before the first
launch (MW-GOLD, logged; never inside the DOCK1 relaunch check).
env: SINK_MODE (sink), SINK_FROM (Port Royal uid), SINK_SECS (1200), SINK_FIND_SECS (300), SINK_HOLD_R (800),
SINK_SETTLE (20), SINK_LAND_SECS (150), SINK_RELAUNCH (0), DOCK_TRIES (3), DOCK_WAIT (180), DOCK_ASHORE (10),
DOCK_PROVOKE_R (1200), VOLLEY_NEAR (2500), DOCK_HOME (1), SINK_SEAT ('' / cannon), SEAT_HP (0.6), SEAT_ASHORE_BY (65),
SEAT_EJECT_BY (85), SEAT_WAIT (150), SEAT_SUNK_WAIT (60)."""
import math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0])))

MODE = os.environ.get('SINK_MODE', 'sink').lower()
PR = '1150922126.8dzlu'           # Port Royal (s_story.PR)
FROM = os.environ.get('SINK_FROM', PR)
SECS = float(os.environ.get('SINK_SECS', '1200'))
FIND_SECS = float(os.environ.get('SINK_FIND_SECS', '300'))
HOLD_R = float(os.environ.get('SINK_HOLD_R', '800'))
SETTLE = float(os.environ.get('SINK_SETTLE', '20'))
LAND_SECS = float(os.environ.get('SINK_LAND_SECS', '150'))
RELAUNCH = os.environ.get('SINK_RELAUNCH', '0') == '1'
DOCK_TRIES = int(os.environ.get('DOCK_TRIES', '3'))
DOCK_WAIT = float(os.environ.get('DOCK_WAIT', '180'))
DOCK_ASHORE = float(os.environ.get('DOCK_ASHORE', '10'))
PROVOKE_R = float(os.environ.get('DOCK_PROVOKE_R', '1200'))
VOLLEY_NEAR = float(os.environ.get('VOLLEY_NEAR', '2500'))
DOCK_HOME = os.environ.get('DOCK_HOME', '1') == '1'
SEAT = os.environ.get('SINK_SEAT', '').lower()
SEAT_HP = float(os.environ.get('SEAT_HP', '0.6'))
SEAT_ASHORE_BY = float(os.environ.get('SEAT_ASHORE_BY', '65'))
SEAT_EJECT_BY = float(os.environ.get('SEAT_EJECT_BY', '85'))
SEAT_WAIT = float(os.environ.get('SEAT_WAIT', '150'))
SEAT_SUNK_WAIT = float(os.environ.get('SEAT_SUNK_WAIT', '60'))
NEVER_PIRATE, NEVER_SHIP = 100000170, 100000173
PATROL_N = 8                      # points on the search ring round SINK_FROM
LEG_R = 1500.0


# ------------------------------------------------------------------------------------------------ pure
def guard(doId, ships):
    """-> None when this pirate may run the step, else why not."""
    if doId == NEVER_PIRATE:
        return 'pirate %d is never touched' % NEVER_PIRATE
    if NEVER_SHIP in (ships or []):
        return 'ship %d is never touched' % NEVER_SHIP
    if not ships:
        return 'the pirate owns no ship'
    return None


def homeOf(ret, default=PR):
    """The island a sunk captain is sent to: his return location, Port Royal when he has none."""
    return ret if ret else default


def countState(states, name, who=None):
    """How many times the server told the ship state `name` ([(t, who, state)]; who = 'ship' / 'ov' / None = any)."""
    return sum(1 for s in states if s[2] == name and (who is None or s[1] == who))


def judgeSink(scenes, states, landed, home):
    """-> (ok, why). One sinking scene, Sinking told once (each listener), landed on the return port."""
    bad = []
    if scenes != 1:
        bad.append('%d sinking scenes (want 1)' % scenes)
    for who in ('ship', 'ov'):
        n = countState(states, 'Sinking', who)
        if n > 1:
            bad.append("'Sinking' told %d times to the %s" % (n, who))
    if countState(states, 'Sinking') == 0 and scenes == 0:
        bad.append('the ship never sank')
    if landed != home:
        bad.append('landed on %s, not the return port %s' % (landed, home))
    return (not bad, '; '.join(bad) or 'one scene, Sinking once, ashore on the return port')


def volley(t, firer, dist, delays, flight):
    """One NPC volley: when it was fired and when its last ball lands."""
    md = max([float(d) for d in (delays or [])] or [0.0])
    return {'t': t, 'firer': firer, 'dist': dist, 'flight': float(flight or 0), 'maxDelay': md,
            'land': t + md + float(flight or 0)}


def inAir(volleys, now):
    """The newest volley still in the air at now (fired, not landed), or None."""
    live = [v for v in volleys if v['t'] <= now < v['land']]
    return max(live, key=lambda v: v['t']) if live else None


def landedAfter(volleys, t):
    """Volleys that land after t (t = the moment the ship was put away)."""
    if t is None:
        return []
    return [v for v in volleys if v['land'] > t]


def firstStateAfter(states, name, t):
    """Time the ship (or its owner view) was first told `name` at or after t, or None."""
    ts = [s[0] for s in states if s[2] == name and s[0] >= t]
    return min(ts) if ts else None


def judgeDock(r):
    """r: one try's facts. -> ('PASS' | 'FAIL' | 'INCONCLUSIVE', why)."""
    sunk = r.get('state') == 'Sunk' or (r.get('hp') is not None and r['hp'] <= 0) or r.get('sunkSeen')
    if r.get('pressed') and sunk:
        return 'FAIL', 'the ship is %s with %s hp after the dock (the 0363 bug)' % (r.get('state'), r.get('hp'))
    if not r.get('pressed'):
        return 'INCONCLUSIVE', r.get('why') or 'never docked'
    if not r.get('volley'):
        return 'INCONCLUSIVE', 'no volley was in the air at the anchor press'
    if not r.get('relaunched'):
        return 'FAIL', 'the ship did not launch again after the dock (%s)' % (r.get('relaunchWhy') or '?')
    paid = (r.get('goldBefore') or 0) - (r.get('goldAfter') or 0)
    if paid > 0:
        return 'FAIL', 'the relaunch cost %d gold (a repair bill)' % paid
    return 'PASS', 'a volley in the air at the press, the ship kept %s hp (%s), launched again, no gold paid' % (
        r.get('hp'), r.get('state'))


def ringPoints(cx, cy, R, n=PATROL_N):
    return [(cx + R * math.cos(2 * math.pi * k / n), cy + R * math.sin(2 * math.pi * k / n)) for k in range(n)]


def holdPoint(fp, fh, d, r=HOLD_R):
    """Where to steer to keep alongside a foe at fp (x, y) heading fh (degrees, Panda: forward = (-sin, cos)):
    straight at it while farther than r + 300, else a point 1500 ft ahead of it (sail with it)."""
    if d > r + 300:
        return fp
    a = math.radians(fh)
    return (fp[0] - 1500 * math.sin(a), fp[1] + 1500 * math.cos(a))


def seatNow(hp, maxHp, frac=SEAT_HP):
    """True once the foe has knocked our hp down to frac of max (it is firing at us and will finish the job)."""
    if hp is None or not maxHp:
        return False
    return hp <= frac * maxHp


def pickCannon(entries, distOf):
    """The nearest deck cannon nobody else is on. entries: ship.cannons.values() ([prop, DistributedPCCannon] each);
    distOf(cannon) -> feet from the pirate. -> the cannon or None."""
    free = []
    for e in entries or []:
        c = e[1] if isinstance(e, (list, tuple)) and len(e) > 1 else None
        if c is None or getattr(c, 'userId', 0) not in (0, None):
            continue
        try:
            free.append((distOf(c), c))
        except Exception:
            continue
    free.sort(key=lambda x: x[0])
    return free[0][1] if free else None


def has0365(src):
    """True when DistributedShip.sendCrewToIsland's source is 0365's (lets go of the cannon, then goes ashore);
    None when the source could not be read."""
    if not src:
        return None
    return '_crewSentAshore' in src and 'requestExit' in src


def since(t, t0):
    return None if t is None or t0 is None else round(t - t0, 1)


def judgeSeat(f):
    """f: the seat run's facts (times are seconds after the first sinking scene). -> (ok, why)."""
    if not f.get('seated'):
        return False, 'never sat on a deck cannon (%s)' % (f.get('why') or '?')
    if not f.get('sank'):
        return False, 'the ship never sank while he sat on the cannon'
    new = f.get('client0365')
    ej, fr, ash = f.get('eject'), f.get('freed'), f.get('ashore')
    if ej is not None and (ash is None or ej < ash):
        if new:
            return False, 'ejected at %.0f s on a 0365 client (0365 should have taken him ashore first)' % ej
        if ej <= SEAT_EJECT_BY:
            return True, 'old client: the "connect again" box at %.0f s (by %.0f)' % (ej, SEAT_EJECT_BY)
        return False, 'old client: the "connect again" box came late, at %.0f s (want by %.0f)' % (ej, SEAT_EJECT_BY)
    if ash is None:
        return False, 'still at sea %.0f s after the sinking scene: freed %s, no eject, not ashore' % (
            f.get('watched') or 0, 'at %.0f s' % fr if fr is not None else 'never')
    if fr is None or fr > ash:
        return False, 'ashore at %.0f s but the cannon never let him go first (freed %s)' % (ash, fr)
    if ash > SEAT_ASHORE_BY:
        return False, 'freed at %.0f s but ashore only at %.0f s (want by %.0f)' % (fr, ash, SEAT_ASHORE_BY)
    if not f.get('sunk'):
        return False, 'ashore at %.0f s but the ship was never shown Sunk (state %s)' % (ash, f.get('state'))
    return True, 'freed from the cannon at %.0f s, ashore at %.0f s (by %.0f), ship shown Sunk' % (
        fr, ash, SEAT_ASHORE_BY)


def aiExpect(f, avId, sid):
    """What pir-test should find in the AI log for this run."""
    if f.get('eject') is not None and (f.get('ashore') is None or f['eject'] < f['ashore']):
        return ('one sunk-ship-eject shipId=%s avatarId=%s; sunk-ship-give-up only if he was still listed at 95 s'
                % (sid, avId))
    return 'no sunk-ship-eject for avatarId=%s (he left the deck himself); no sunk-ship-give-up for shipId=%s' % (
        avId, sid)


# ------------------------------------------------------------------------------------------------ hooks
def broadsideClass():
    from pirates.battle.DistributedShipBroadside import DistributedShipBroadside
    return DistributedShipBroadside


class Watch:
    """Wraps our ship's scene methods, the ship's and owner view's setGameState, and the broadside class's
    doBroadside. undo() puts all of it back."""

    def __init__(self, H, sid):
        self.H, self.sid = H, sid
        self.scenes = 0
        self.sceneT = []            # when each sinking scene began
        self.fades = 0
        self.sent = []
        self.states = []            # (t, 'ship' | 'ov', state)
        self.volleys = []
        self._undo = []
        self.ship = None

    def _wrap(self, obj, name, fn):
        if obj is None or not hasattr(obj, name):
            return
        old = getattr(obj, name)
        had = name in getattr(obj, '__dict__', {})

        def w(*a, **k):
            try:
                fn(*a, **k)
            except Exception as e:
                self.H.ev('watch-err', fn=name, err=str(e))
            return old(*a, **k)
        setattr(obj, name, w)
        self._undo.append((obj, name, old, had))

    def onShip(self, ship):
        """Hook a (new) ship object once."""
        if ship is None or ship is self.ship:
            return
        self.ship = ship
        H = self.H

        def scene(*a, **k):
            self.scenes += 1
            self.sceneT.append(time.time())
            H.ev('SINK-SCENE', n=self.scenes, ship=self.sid, gs=H.la.getGameState())

        def fade(*a, **k):
            self.fades += 1
            H.ev('SINK-FADE', n=self.fades, ship=self.sid)

        def sent(islandId, posH=None, *a, **k):
            isl = H.cr.doId2do.get(islandId)
            uid = isl.getUniqueId() if isl is not None and hasattr(isl, 'getUniqueId') else None
            self.sent.append((time.time(), islandId, uid))
            H.ev('SINK-SENT', island=islandId, uid=uid, n=len(self.sent))

        def st(stateName, *a, **k):
            self.states.append((time.time(), 'ship', stateName))
            H.ev('SHIP-STATE', who='ship', state=stateName, n=countState(self.states, stateName, 'ship'))
        self._wrap(ship, 'sinkingBegin', scene)
        self._wrap(ship, 'cleanupLocalSinking', fade)
        self._wrap(ship, 'sendCrewToIsland', sent)
        self._wrap(ship, 'setGameState', st)

    def install(self):
        H = self.H
        ov = H.cr.getOwnerView(self.sid)

        def ovst(stateName, *a, **k):
            self.states.append((time.time(), 'ov', stateName))
            H.ev('SHIP-STATE', who='ov', state=stateName, n=countState(self.states, stateName, 'ov'))
        self._wrap(ov, 'setGameState', ovst)
        try:
            B = broadsideClass()
        except Exception as e:
            H.ev('watch-err', fn='doBroadside', err=str(e))
            return self
        me = self

        def vol(bs, side, delays, hitPosList, zoneId, flightTime, timestamp=None, *a, **k):
            firer = getattr(bs, 'ship', None)
            mine = H.cr.doId2do.get(me.sid)
            if firer is None or firer is mine or mine is None:
                return
            try:
                d = (firer.getPos(H.render) - mine.getPos(H.render)).length()
            except Exception:
                return
            if d > VOLLEY_NEAR:
                return
            v = volley(time.time(), getattr(firer, 'doId', None), round(d), delays, flightTime)
            me.volleys.append(v)
            H.ev('VOLLEY', n=len(me.volleys), firer=v['firer'], name=getattr(firer, 'name', ''), dist=v['dist'],
                 flight=round(v['flight'], 2), maxDelay=round(v['maxDelay'], 2), landsIn=round(v['land'] - v['t'], 2))
        self._wrap(B, 'doBroadside', vol)
        return self

    def undo(self):
        for obj, name, old, had in reversed(self._undo):
            try:
                if had or isinstance(obj, type):
                    setattr(obj, name, old)
                else:
                    delattr(obj, name)
            except Exception:
                pass
        self._undo = []


# ------------------------------------------------------------------------------------------------ sea moves
def navyFoe(H, ship, SQ):
    """(dist, o) of the nearest afloat Navy NPC ship in view, or None."""
    from pirates.pirate import AvatarTypes as AT
    for d, o in SQ.npcShips(H, ship):
        if SQ.factionOf(o) == AT.Navy:
            return d, o
    return None


class Sea:
    """Steering helpers on one launched ship: patrol the ring round SINK_FROM, keep alongside a foe."""

    def __init__(self, H, ship, keys, sailing):
        self.H, self.ship, self.keys, self.sailing = H, ship, keys, sailing
        isl = sailing.islands().get(FROM)
        c = (isl[1], isl[2]) if isl else (0.0, 0.0)
        R = float(os.environ.get('SHIP_PATROL_R', '8000'))
        self.pts = ringPoints(c[0], c[1], R)
        self.i = None
        self.obst = [(x, y, sailing.OBST_R if n else 900) for u, (n, x, y, f) in sailing.islands().items()]

    def patrol(self):
        from panda3d.core import Point3
        p = self.ship.getPos(self.H.render)
        if self.i is None:
            self.i = min(range(len(self.pts)), key=lambda k: math.hypot(self.pts[k][0] - p[0], self.pts[k][1] - p[1]))
        tx, ty = self.pts[self.i]
        if math.hypot(tx - p[0], ty - p[1]) < LEG_R:
            self.i = (self.i + 1) % len(self.pts)
            tx, ty = self.pts[self.i]
        tgt, mode = self.sailing.route(p, Point3(tx, ty, 0), self.obst)
        self.keys.steer(self.ship, tgt)
        return mode

    def hold(self, foe, d, r=HOLD_R):
        from panda3d.core import Point3
        fp = foe.getPos(self.H.render)
        x, y = holdPoint((fp[0], fp[1]), foe.getH(self.H.render), d, r)
        self.keys.steer(self.ship, Point3(x, y, 0))


def fullSail():
    messenger.send('w'); messenger.send('w-up')


def dropSail():
    messenger.send('s'); messenger.send('s-up')


def runUntil(g, stop):
    """Generator: drive generator g, closing it as soon as stop() is true after one of its steps.
    -> ('done', its value) or ('stopped', None)."""
    x = None
    while True:
        try:
            v = g.send(x)
        except StopIteration as e:
            return 'done', e.value
        if stop():
            g.close()
            return 'stopped', None
        x = yield v


# ------------------------------------------------------------------------------------------------ SINK1
def runSink(H, sid, SQ, sailing, Keys):
    la = H.la
    home = homeOf(la.getReturnLocation())
    ov = H.cr.getOwnerView(sid)
    H.ev('SINK-START', pirate=la.doId, ship=sid, frm=FROM, home=home, ret=la.getReturnLocation(),
         hp=getattr(ov, 'Hp', None), maxHp=getattr(ov, 'maxHp', None), secs=SECS)
    w = Watch(H, sid).install()
    keys = Keys(H)
    try:
        ship = yield from SQ.launchShip(H)
        if ship is None:
            H.ev('FAIL', why='could not launch the ship'); return
        w.onShip(ship)
        fullSail()
        sea = Sea(H, ship, keys, sailing)
        t0 = time.time()
        lastLog = 0
        foeId = None
        while time.time() - t0 < SECS:
            if w.scenes or countState(w.states, 'Sinking') or countState(w.states, 'Sunk'):
                break
            if H.cr.doId2do.get(sid) is None or la.getGameState() != 'ShipPilot':
                break
            f = navyFoe(H, ship, SQ)
            if f is None:
                if time.time() - t0 > FIND_SECS and foeId is None:
                    H.ev('FAIL', why='no Navy ship found in %d s' % FIND_SECS); return
                mode = sea.patrol()
            else:
                d, o = f
                if o.doId != foeId:
                    foeId = o.doId
                    H.ev('SINK-FOE', foe=o.doId, name=getattr(o, 'name', ''), level=SQ.levelOf(o), dist=round(d))
                sea.hold(o, d)
                mode = 'hold'
            if time.time() - lastLog > 10:
                lastLog = time.time()
                H.ev('SINK-HP', hp=getattr(ship, 'Hp', None), mode=mode, foe=foeId,
                     dist=None if f is None else round(f[0]), volleys=len(w.volleys), secs=round(time.time() - t0))
            yield 0.5
        keys.release()
        sank = bool(w.scenes or countState(w.states, 'Sinking'))
        if not sank:
            H.ev('SINK-END', sank=False, gs=la.getGameState(), hp=getattr(ship, 'Hp', None))
            H.ev('FAIL', why='our ship did not sink in %d s (gs %s)' % (SECS, la.getGameState())); return
        tS = time.time()
        yield ('upto', lambda: la.getGameState() == 'LandRoam' and sailing.hereUid(H) is not None, LAND_SECS, 'ashore')
        landed = sailing.hereUid(H)
        H.ev('SINK-ASHORE', here=landed, home=home, gs=la.getGameState(), secs=round(time.time() - tS),
             sent=[s[2] for s in w.sent])
        yield SETTLE                    # a late repeat of Sinking would come now
        ok, why = judgeSink(w.scenes, w.states, landed, home)
        H.ev('SINK-END', sank=True, scenes=w.scenes, fades=w.fades, sinkingShip=countState(w.states, 'Sinking', 'ship'),
             sinkingOv=countState(w.states, 'Sinking', 'ov'), sunk=countState(w.states, 'Sunk'), sent=len(w.sent),
             here=landed, home=home, volleys=len(w.volleys), ok=ok, why=why, hp=getattr(ov, 'Hp', None),
             state=getattr(ov, 'state', None), gold=la.getInventory().getGoldInPocket())
        if RELAUNCH and ok:
            again = yield from SQ.launchShip(H)
            H.ev('SINK-RELAUNCH', ok=again is not None, hp=getattr(ov, 'Hp', None),
                 gold=la.getInventory().getGoldInPocket())
        H.ev('PASS' if ok else 'FAIL', step='sink1', why=why)
    finally:
        keys.release()
        w.undo()


# ------------------------------------------------------------------------------------------------ SINK1 seat
def funcSrc(src, name):
    """The text of method `name` in a module's source (up to the next method), or ''."""
    i = (src or '').find('def %s(' % name)
    if i < 0:
        return ''
    j = src.find('\n    def ', i + 1)
    return src[i:j if j > 0 else len(src)]


def client0365():
    """Does the installed client have 0365? (reads DistributedShip.sendCrewToIsland's source: the loaded class in
    game, else the module file)"""
    import inspect, importlib.util
    try:
        m = sys.modules.get('pirates.ship.DistributedShip')
        if m is not None:
            return has0365(inspect.getsource(m.DistributedShip.sendCrewToIsland))
    except Exception:
        pass
    try:
        spec = importlib.util.find_spec('pirates.ship.DistributedShip')
        with open(spec.origin, encoding='utf-8', errors='replace') as fh:
            return has0365(funcSrc(fh.read(), 'sendCrewToIsland'))
    except Exception:
        return None


class Kick:
    """Notes the server's eject (CLIENT_EJECT -> handleGoGetLost shows the "connect again" box) the moment it comes."""

    def __init__(self, H):
        self.H, self.t, self.code, self._old = H, None, None, None

    def install(self):
        cr, H = self.H.cr, self.H
        old = self._old = cr.handleGoGetLost
        self._had = 'handleGoGetLost' in getattr(cr, '__dict__', {})

        def ggl(di, *a, **k):
            try:
                from panda3d.core import DatagramIterator
                self.code = DatagramIterator(di.getDatagram(), di.getCurrentIndex()).getUint16()
            except Exception:
                pass
            if self.t is None:
                self.t = time.time()
            H.ev('SEAT-EJECT', code=self.code, how='CLIENT_EJECT')
            return old(di, *a, **k)
        cr.handleGoGetLost = ggl
        return self

    def poll(self):
        """Also count a dropped connection (loginFSM noConnection) as the box. -> t or None."""
        if self.t is None:
            try:
                if self.H.cr.loginFSM.getCurrentState().getName() == 'noConnection':
                    self.t = time.time()
                    self.H.ev('SEAT-EJECT', code=None, how='noConnection')
            except Exception:
                pass
        return self.t

    def undo(self):
        if self._old is None:
            return
        try:
            if self._had:
                self.H.cr.handleGoGetLost = self._old
            elif 'handleGoGetLost' in self.H.cr.__dict__:
                del self.H.cr.handleGoGetLost
        except Exception:
            pass
        self._old = None


def gsOf(la):
    try:
        return la.getGameState()
    except Exception:
        return None


def onCannon(H):
    try:
        return getattr(H.la, 'cannon', None)
    except Exception:
        return None


def cannonSpot(c):
    """Where a deck cannon really stands: its prop's cannon post (the cannon object itself sits at the world origin)."""
    prop = getattr(c, 'prop', None)
    return getattr(prop, 'cannonPost', None) or prop or c


def takeCannon(H, ship):
    """Generator: let go of the wheel, walk to the nearest free deck cannon and sit on it. -> the cannon or None."""
    la = H.la
    wheel = getattr(ship, 'wheel', None)
    w = wheel[1] if isinstance(wheel, (list, tuple)) and len(wheel) > 1 else None
    H.ev('SEAT-LEAVE-WHEEL', gs=gsOf(la), wheel=getattr(w, 'doId', None))
    if gsOf(la) == 'ShipPilot':
        if w is not None and hasattr(w, 'requestExit'):
            w.requestExit()
        else:
            from pirates.interact import InteractiveBase
            messenger.send(InteractiveBase.END_INTERACT_EVENT)
        yield ('upto', lambda: gsOf(la) != 'ShipPilot', 15, 'leave wheel')
    if gsOf(la) == 'ShipPilot':
        H.ev('SEAT-LEAVE-WHEEL', ok=False, gs=gsOf(la)); return None
    for n in range(4):
        c = onCannon(H) or pickCannon(list(getattr(ship, 'cannons', {}).values()),
                                      lambda c: cannonSpot(c).getDistance(la))
        if c is None:
            H.ev('SEAT-GOTO', n=n, cannon=None, why='no free deck cannon'); return None
        if onCannon(H) is c:
            return c
        tgt = cannonSpot(c)
        ok = yield from H.walk_to(tgt, arrive=3.0 if n < 2 else 2.0, timeout=30, tag='cannon')
        H.ev('SEAT-GOTO', n=n, cannon=c.doId, reached=ok, d=round(tgt.getDistance(la), 1))
        c.requestInteraction(la.doId)
        yield ('upto', lambda: onCannon(H) is c, 15, 'on cannon')
        if onCannon(H) is c:
            return c
    return None


def watchSeat(H, c, w, kick, tS, sailing, sid):
    """Generator: from the first sinking scene (tS), press nothing and time freed / ashore / eject.
    -> facts (seconds after tS)."""
    la = H.la
    f = {'freed': None, 'ashore': None, 'eject': None, 'here': None, 'gs': []}
    last = None
    while time.time() - tS < SEAT_WAIT:
        now = time.time()
        if kick.poll() is not None:
            f['eject'] = since(kick.t, tS)
            break
        gs = gsOf(la)
        if gs != last:
            last = gs
            f['gs'].append((since(now, tS), gs))
            H.ev('SEAT-GS', gs=gs, secs=since(now, tS))
        if f['freed'] is None and onCannon(H) is not c:
            f['freed'] = since(now, tS)
            H.ev('SEAT-FREED', secs=f['freed'], gs=gs, cannon=getattr(onCannon(H), 'doId', None))
        try:
            here = sailing.hereUid(H) if gs == 'LandRoam' else None
        except Exception:
            here = None
        if here is not None and f['ashore'] is None:
            f['ashore'], f['here'] = since(now, tS), here
            break
        yield 0.25
    f['watched'] = since(time.time(), tS)
    if f['ashore'] is not None and f['eject'] is None:
        ov = H.cr.getOwnerView(sid)
        t1 = time.time()
        while time.time() - t1 < SEAT_SUNK_WAIT:
            if kick.poll() is not None:
                f['eject'] = since(kick.t, tS)      # after he landed: noted, not the verdict
                break
            if countState(w.states, 'Sunk') or getattr(ov, 'state', None) == 'Sunk':
                break
            yield 0.5
        f['state'] = getattr(ov, 'state', None)
    f['sunk'] = bool(countState(w.states, 'Sunk')) or f.get('state') == 'Sunk'
    return f


def runSeat(H, sid, SQ, sailing, Keys):
    la = H.la
    home = homeOf(la.getReturnLocation())
    ov = H.cr.getOwnerView(sid)
    new = client0365()
    H.ev('SEAT-START', pirate=la.doId, ship=sid, frm=FROM, home=home, client0365=new, seatHp=SEAT_HP,
         hp=getattr(ov, 'Hp', None), maxHp=getattr(ov, 'maxHp', None), secs=SECS)
    w = Watch(H, sid).install()
    kick = Kick(H).install()
    keys = Keys(H)
    f = {'client0365': new, 'seated': False, 'sank': False}
    try:
        ship = yield from SQ.launchShip(H)
        if ship is None:
            H.ev('FAIL', step='sink-seat', why='could not launch the ship'); return
        w.onShip(ship)
        fullSail()
        sea = Sea(H, ship, keys, sailing)
        t0 = time.time()
        lastLog = 0
        foeId = None
        sank = lambda: bool(w.scenes or countState(w.states, 'Sinking') or countState(w.states, 'Sunk'))
        maxHp = getattr(ship, 'maxHp', None) or getattr(ov, 'maxHp', None)
        ready = False
        while time.time() - t0 < SECS and not sank():
            if H.cr.doId2do.get(sid) is None or gsOf(la) != 'ShipPilot':
                break
            hp = getattr(ship, 'Hp', None)
            if foeId is not None and seatNow(hp, maxHp):
                ready = True
                break
            fo = navyFoe(H, ship, SQ)
            if fo is None:
                if time.time() - t0 > FIND_SECS and foeId is None:
                    H.ev('FAIL', step='sink-seat', why='no Navy ship found in %d s' % FIND_SECS); return
                mode = sea.patrol()
            else:
                d, o = fo
                if o.doId != foeId:
                    foeId = o.doId
                    H.ev('SINK-FOE', foe=o.doId, name=getattr(o, 'name', ''), level=SQ.levelOf(o), dist=round(d))
                sea.hold(o, d)
                mode = 'hold'
            if time.time() - lastLog > 10:
                lastLog = time.time()
                H.ev('SINK-HP', hp=hp, maxHp=maxHp, mode=mode, foe=foeId, volleys=len(w.volleys),
                     secs=round(time.time() - t0))
            yield 0.5
        keys.release()
        if not ready:
            f['why'] = 'sank before the cannon' if sank() else 'hp never fell to %.0f%% (gs %s, hp %s)' % (
                SEAT_HP * 100, gsOf(la), getattr(ship, 'Hp', None))
        else:
            c = yield from takeCannon(H, ship)
            if c is None:
                f['why'] = 'could not get onto a deck cannon (gs %s)' % gsOf(la)
            else:
                f['seated'] = True
                H.ev('SINK-SEAT', cannon=c.doId, hp=getattr(ship, 'Hp', None), gs=gsOf(la),
                     secs=round(time.time() - t0))
                # from here on: no keys, no clicks, no firing
                while time.time() - t0 < SECS and not sank():
                    if kick.poll() is not None or H.cr.doId2do.get(sid) is None:
                        break
                    if time.time() - lastLog > 10:
                        lastLog = time.time()
                        H.ev('SINK-HP', hp=getattr(ship, 'Hp', None), mode='seated', foe=foeId,
                             onCannon=onCannon(H) is c, gs=gsOf(la), volleys=len(w.volleys),
                             secs=round(time.time() - t0))
                    yield 0.5
                f['sank'] = sank()
                if f['sank']:
                    tS = w.sceneT[0] if w.sceneT else time.time()
                    facts = yield from watchSeat(H, c, w, kick, tS, sailing, sid)
                    f.update(facts)
                    if f.get('ashore') is not None:
                        H.ev('SINK-ASHORE', here=f['here'], home=home, secs=f['ashore'], sent=[s[2] for s in w.sent])
        ok, why = judgeSeat(f)
        H.ev('SEAT-END', seated=f['seated'], sank=f['sank'], client0365=new, freed=f.get('freed'),
             ashore=f.get('ashore'), eject=f.get('eject'), ejectCode=kick.code, here=f.get('here'), home=home,
             scenes=w.scenes, sinkingShip=countState(w.states, 'Sinking', 'ship'), sunk=f.get('sunk'),
             state=f.get('state'), gs=f.get('gs'), aiLog=aiExpect(f, la.doId, sid),
             shipwright='the ship should show Sunk at the shipwright (pay or free mend) at the next visit',
             ok=ok, why=why)
        H.ev('PASS' if ok else 'FAIL', step='sink-seat', why=why)
    finally:
        keys.release()
        kick.undo()
        w.undo()


# ------------------------------------------------------------------------------------------------ DOCK1
def dockTry(H, sid, ship, w, SQ, sailing, Keys, n):
    """Generator, one try: provoke a Navy ship, sail home, press the anchor while a volley flies, check ashore and
    relaunch. -> (result dict, the ship we are on afterwards or None)."""
    la = H.la
    ov = H.cr.getOwnerView(sid)
    r = {'try': n}
    keys = Keys(H)
    w.onShip(ship)
    fullSail()
    sea = Sea(H, ship, keys, sailing)
    t0 = time.time()
    foeId = None
    nv = len(w.volleys)
    H.ev('DOCK-TRY', n=n, hp=getattr(ship, 'Hp', None), gold=la.getInventory().getGoldInPocket())
    # 1. find a Navy ship and close in until it fires at us
    while len(w.volleys) == nv:
        if time.time() - t0 > FIND_SECS + 120:
            keys.release()
            r['why'] = 'no Navy volley at us in %d s' % (time.time() - t0)
            return r, ship
        if H.cr.doId2do.get(sid) is None or la.getGameState() != 'ShipPilot' or countState(w.states, 'Sinking'):
            keys.release()
            r['why'] = 'left the wheel or sank while closing in'
            r['sunkEarly'] = True
            return r, None
        f = navyFoe(H, ship, SQ)
        if f is None:
            sea.patrol()
        else:
            d, o = f
            if o.doId != foeId:
                foeId = o.doId
                H.ev('SINK-FOE', foe=o.doId, name=getattr(o, 'name', ''), level=SQ.levelOf(o), dist=round(d), try_=n)
            sea.hold(o, d, PROVOKE_R)
        yield 0.5
    keys.release()
    # 2. sail home; sail_to's own anchor press is caught (not pressed), so we choose the moment
    want = {'press': False}
    disp = getattr(ship, 'shipStatusDisplay', None)
    if disp is None:
        r['why'] = 'no ship status display (anchor button)'
        return r, ship
    realPress = disp.handleAnchorButton
    had = 'handleAnchorButton' in getattr(disp, '__dict__', {})

    def catch(*a, **k):
        want['press'] = True
    disp.handleAnchorButton = catch
    try:
        res, _ = yield from runUntil(sailing.sail_to(H, FROM, 'DOCK1 home with a Navy ship behind'), lambda: want['press'])
    finally:
        if had:
            disp.handleAnchorButton = realPress
        else:
            try:
                del disp.handleAnchorButton
            except Exception:
                pass
    if not want['press']:
        r['why'] = 'sail_to never reached the anchor (%s)' % res
        r['sunkEarly'] = bool(countState(w.states, 'Sinking'))
        return r, H.cr.doId2do.get(sid)
    # 3. sail down at the anchor: press while a volley is in the air
    dropSail()
    t1 = time.time()
    v = None
    while time.time() - t1 < DOCK_WAIT:
        if countState(w.states, 'Sinking') or H.cr.doId2do.get(sid) is None:
            r['why'] = 'sank at the anchor before the press'
            r['sunkEarly'] = True
            return r, None
        v = inAir(w.volleys, time.time())
        if v is not None:
            break
        yield 0.1
    tP = time.time()
    if v is None:
        H.ev('DOCK-NO-VOLLEY', waited=round(tP - t1), volleys=len(w.volleys))
    else:
        H.ev('DOCK-PRESS', firer=v['firer'], dist=v['dist'], age=round(tP - v['t'], 2), landsIn=round(v['land'] - tP, 2),
             flight=round(v['flight'], 2), hp=getattr(ship, 'Hp', None))
    goldPress = la.getInventory().getGoldInPocket()
    getattr(disp, 'handleAnchorButton')()
    r.update(pressed=True, volley=v is not None, tPress=tP)
    yield ('until', lambda: sailing.hereUid(H) == FROM and la.getGameState() == 'LandRoam', 90, 'ashore at %s' % FROM)
    yield DOCK_ASHORE
    tPut = firstStateAfter(w.states, 'PutAway', tP)
    after = landedAfter(w.volleys, tPut)
    inFlight = landedAfter(w.volleys, tP)
    r.update(state=getattr(ov, 'state', None), hp=getattr(ov, 'Hp', None), maxHp=getattr(ov, 'maxHp', None),
             sunkSeen=bool(firstStateAfter(w.states, 'Sunk', tP) or firstStateAfter(w.states, 'Sinking', tP)),
             here=sailing.hereUid(H), putAwayAfter=None if tPut is None else round(tPut - tP, 2),
             landedAfterPress=len(inFlight), landedAfterPutAway=len(after))
    H.ev('DOCK-ASHORE', here=r['here'], gs=la.getGameState(), state=r['state'], hp=r['hp'], maxHp=r['maxHp'],
         putAwayAfter=r['putAwayAfter'], landedAfterPress=r['landedAfterPress'],
         landedAfterPutAway=r['landedAfterPutAway'], sunkSeen=r['sunkSeen'], gold=la.getInventory().getGoldInPocket())
    # 4. launch again with no shipwright
    r['goldBefore'] = goldPress
    again = None
    if r['state'] != 'Sunk' and (r['hp'] or 0) > 0 and r['here'] == FROM:
        try:
            again = yield from sailing.launch(H, FROM, True)
        except RuntimeError as e:
            r['relaunchWhy'] = str(e)
    else:
        r['relaunchWhy'] = 'ship %s with %s hp, here %s' % (r['state'], r['hp'], r['here'])
    r['relaunched'] = again is not None
    r['goldAfter'] = la.getInventory().getGoldInPocket()
    H.ev('DOCK-RELAUNCH', ok=r['relaunched'], why=r.get('relaunchWhy'), goldBefore=r['goldBefore'],
         goldAfter=r['goldAfter'], hp=getattr(ov, 'Hp', None))
    return r, again


def runDock(H, sid, SQ, sailing, Keys):
    la = H.la
    ov = H.cr.getOwnerView(sid)
    H.ev('DOCK-START', pirate=la.doId, ship=sid, frm=FROM, tries=DOCK_TRIES, wait=DOCK_WAIT,
         hp=getattr(ov, 'Hp', None), maxHp=getattr(ov, 'maxHp', None), gold=la.getInventory().getGoldInPocket())
    w = Watch(H, sid).install()
    verdict, why, results = 'INCONCLUSIVE', 'no try', []
    try:
        ship = None
        for n in range(1, DOCK_TRIES + 1):
            if ship is None:
                if la.getGameState() != 'LandRoam' or sailing.hereUid(H) is None:
                    yield ('upto', lambda: la.getGameState() == 'LandRoam' and sailing.hereUid(H) is not None,
                           LAND_SECS, 'ashore before a try')
                if sailing.hereUid(H) != FROM:
                    yield from sailing.sail_to(H, FROM, 'DOCK1 back to the start')
                ship = yield from SQ.launchShip(H)
                if ship is None:
                    why = 'could not launch for try %d' % n
                    break
            r, ship = yield from dockTry(H, sid, ship, w, SQ, sailing, Keys, n)
            verdict, why = judgeDock(r)
            results.append(r)
            H.ev('DOCK-RESULT', n=n, verdict=verdict, why=why, **dict((k, r[k]) for k in sorted(r) if k != 'tPress'))
            if verdict != 'INCONCLUSIVE':
                break
        if DOCK_HOME and ship is not None and la.getGameState() == 'ShipPilot':
            yield from sailing.sail_to(H, FROM, 'DOCK1 done, home')
        H.ev('DOCK-END', verdict=verdict, why=why, tries=len(results), volleys=len(w.volleys),
             states=[s[2] for s in w.states][-12:])
        H.ev(verdict, step='dock1', why=why)
    finally:
        w.undo()


# ------------------------------------------------------------------------------------------------ entry
def run(H):
    if SEAT not in ('', 'cannon') or (SEAT and MODE != 'sink'):
        H.ev('FAIL', why='SINK_SEAT %r: only cannon, and only with SINK_MODE=sink' % SEAT); return
    import sailing
    import s_lanes
    import s_shipquest as SQ
    from s_dock import Keys
    la = H.la
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    no = guard(la.doId, ships)
    if no:
        H.ev('FAIL', why=no); return
    if MODE not in ('sink', 'dock'):
        H.ev('FAIL', why='SINK_MODE %r is not sink or dock' % MODE); return
    if not sailing.onShip(H) and sailing.hereUid(H) != FROM:
        if not (yield from s_lanes.onIsland(H, 'sink', FROM)):
            H.ev('FAIL', why='could not get onto %s to start' % FROM, area=H.area()); return
    if MODE == 'sink' and SEAT == 'cannon':
        yield from runSeat(H, ships[0], SQ, sailing, Keys)
    elif MODE == 'sink':
        yield from runSink(H, ships[0], SQ, sailing, Keys)
    else:
        yield from runDock(H, ships[0], SQ, sailing, Keys)
