"""Headless MainStory walker for Pirates (harness pirate 100000001 / account claude1 only).
Boot + login hooks come from cut_proof.py. A step script (PROOF_SCRIPT) defines run(H), a generator:
  yield <secs>                    -> wait
  yield ('until', fn, timeout)    -> poll fn() every 0.5s until truthy or timeout (logs 'stall' on timeout)
  yield ('upto', fn, secs)        -> pir-bot job 5: wait AT MOST secs, ending as soon as fn() is truthy (polled every
                                     0.25s); a timeout is normal (no STALL). The event-driven stand-in for a fixed sleep.
pir-bot job 5 (faster runs):
  SMOKE=1  the run ends ~SMOKE_LINGER (3) s after its first PASS or FAIL line (SMOKE-END), so a smoke check never
           sits out the rest of PROOF_SECS; with SMOKE_STALL_FATAL (default 1 in smoke) the first STALL line is the
           FAIL. Lines after the verdict that say PASS are written as PASS-AFTER-VERDICT (never a second verdict).
  START_WAIT (8)  the step starts when the pirate is ready (LandRoam etc. with a parent) after at least START_MIN (2)
           s, and at most START_WAIT s after entering play (was a fixed 8 s). Logged start-wait.
  TIME-LEDGER line at finish: seconds spent per kind (sleep / until / upto) and per call site (file:line of the yield),
           the top 15, so a run shows where its time went.
Everything is logged to PROOF_EVOUT (jsonl)."""
import os, sys, time, json, runpy, traceback, math

EVOUT = os.environ.get('PROOF_EVOUT', 'walk-events.jsonl')
# pir-bot job 3: BOT_AVID picks which test pirate logs in (the two-bot mode's mate). Never Host's 100000170.
AVID = int(os.environ.get('BOT_AVID', '100000001'))
NEVER = (100000170,)  # brain 11-19: 100000596 is a harness test pirate after all
SECS = float(os.environ.get('PROOF_SECS', '600'))
state = {'played': False, 'done': False, 'verdict': None}
SMOKE = os.environ.get('SMOKE') == '1'
SMOKE_LINGER = float(os.environ.get('SMOKE_LINGER', '3'))
SMOKE_STALL_FATAL = SMOKE and os.environ.get('SMOKE_STALL_FATAL', '1') == '1'
START_WAIT = float(os.environ.get('START_WAIT', '8'))
START_MIN = float(os.environ.get('START_MIN', '2'))
LEDGER = {}          # (kind, site) -> [count, seconds]
# pir-bot job 4: a step that logs out (s_relog) sets NEXT_PICK[0] = the avId to log back in with. After the first
# login the avatar list never picks on its own (a new-pirate run would make a second pirate), and early() runs once.
NEXT_PICK = [None]
ev_f = open(EVOUT, 'w', buffering=1)


LAST = {'t': time.time()}


def ev(name, /, **kw):          # positional-only: an event may carry its own name= field (MAP-NAME)
    LAST['t'] = time.time()
    if name == 'PASS' and state['verdict'] is not None:
        name = 'PASS-AFTER-VERDICT'           # pir-bot job 5: one verdict per run (never a PASS after a FAIL)
    rec = {'t': round(time.time(), 2), 'ev': name}
    rec.update(kw)
    ev_f.write(json.dumps(rec, default=str) + '\n')
    if name in ('PASS', 'FAIL') and state['verdict'] is None:
        state['verdict'] = (name, time.time())
    elif name == 'STALL' and SMOKE_STALL_FATAL and state['verdict'] is None:
        ev('FAIL', why='smoke: the first STALL ends the check', stall=kw)


def ledger_add(kind, site, secs):
    v = LEDGER.setdefault((kind, site), [0, 0.0])
    v[0] += 1
    v[1] += secs


def ledger_line():
    tot = {}
    for (kind, _), (n, secs) in LEDGER.items():
        tot[kind] = round(tot.get(kind, 0) + secs, 1)
    top = sorted(LEDGER.items(), key=lambda kv: -kv[1][1])[:15]
    return {'totals': tot, 'top': [[k[0], k[1], v[0], round(v[1], 1)] for k, v in top]}


def yield_site(gen):
    """file:line of the innermost generator frame a step's yield came from (the call site of the sleep / wait)."""
    g = gen
    try:
        while getattr(g, 'gi_yieldfrom', None) is not None and hasattr(g.gi_yieldfrom, 'gi_frame'):
            g = g.gi_yieldfrom
        f = g.gi_frame
        return '%s:%d' % (os.path.basename(f.f_code.co_filename), f.f_lineno) if f else '?'
    except Exception:
        return '?'


def patch_login():
    m = sys.modules.get('pirates.distributed.PiratesClientRepository')
    if m is None or not hasattr(m, 'PiratesClientRepository'):
        return False
    cls = m.PiratesClientRepository
    if cls.__dict__.get('_walkhooked', False):
        return True
    orig = cls.enterChooseAvatar

    def enterChooseAvatar(self, avList):
        orig(self, avList)
        import builtins
        keys = list(self.avList.keys()) if isinstance(self.avList, dict) else range(len(self.avList))
        pick = None
        if state['played']:
            # back at the avatar list after a logout (pir-bot job 4): pick only what the step asked for
            want, NEXT_PICK[0] = NEXT_PICK[0], None
            if not want or want in NEVER:
                ev('avlist-again', want=want, why='no NEXT_PICK' if not want else 'refused: the pirate of Host')
                return
            for subId in keys:
                for slot, av in enumerate(self.avList[subId]):
                    if hasattr(av, 'dna') and getattr(av, 'id', None) == want:
                        pick = (subId, slot)
            ev('pick', pick=pick, relog=want)
            if pick is None:
                ev('fatal', why='relog: pirate %d not in avList' % want)
                finish()
            self.avChoice.getChoice = lambda: pick

            def again(task):
                builtins.messenger.send(self.avChoiceDoneEvent, [{'mode': 'chose'}])
                return task.done
            builtins.taskMgr.doMethodLater(2.0, again, 'walk-repick')
            return
        # BOT_NEW_PIRATE=1: make a brand-new pirate in the first empty slot (the opening, s_tutorial.py)
        new = os.environ.get('BOT_NEW_PIRATE') == '1'
        for subId in keys:
            for slot, av in enumerate(self.avList[subId]):
                if new and av == -3:   # OTPGlobals.AvatarSlotAvailable
                    pick = (subId, slot)
                    break
                if not new and AVID not in NEVER and hasattr(av, 'dna') and getattr(av, 'id', None) == AVID:
                    pick = (subId, slot)
                    break
            if pick:
                break
        ev('pick', pick=pick, new=new)
        try:
            # a step script's early(ev), if it has one, goes in now, before the pirate reaches the world (s_tutorial's
            # parent probe); run(H) only starts 8 s after entered-play. Only a script that defines early() is run here,
            # so no other script's top level runs twice.
            src = open(os.environ['PROOF_SCRIPT']).read()
            if 'def early(' in src:
                g = {'__file__': os.environ['PROOF_SCRIPT']}  # step scripts read __file__ (s_bpfort, s_pages, s_standin)
                exec(compile(src, os.environ['PROOF_SCRIPT'], 'exec'), g)
                g['early'](ev)
        except Exception:
            ev('early-error', tb=traceback.format_exc()[-400:])
        if pick is None:
            ev('fatal', why='no empty slot for a new pirate' if new else ('BOT_AVID %d is the pirate of Host: refused' % AVID if AVID in NEVER else 'pirate %d not in avList' % AVID))
            finish()
        self.avChoice.getChoice = lambda: pick

        def go(task):
            builtins.messenger.send(self.avChoiceDoneEvent, [{'mode': 'create' if new else 'chose'}])
            return task.done
        builtins.taskMgr.doMethodLater(2.0, go, 'walk-pick')

        def lost(task):   # a boot before the step script starts (pick, create, entering) ends the run at once
            if state['played']:
                return task.done
            try:
                st = self.loginFSM.getCurrentState().getName()
            except Exception:
                return task.again
            if st == 'noConnection':
                ev('DISCONNECT', state=st, before='play', booted=getattr(self, 'bootedIndex', None),
                   text=str(getattr(self, 'bootedText', '') or '')[:200])
                os._exit(3)
            return task.again
        builtins.taskMgr.doMethodLater(0.5, lost, 'walk-prelost')
    cls.enterChooseAvatar = enterChooseAvatar

    origLost = cls.lostConnection

    def lostConnection(self):
        # 11-21 DOLL17: a boot while still connecting (client DC hash mismatch) leaves loginFSM in 'connect' (no
        # transition to noConnection), so the 'walk-prelost' check above never ran and the game sat 19 min to the
        # watchdog. Any lost connection before play ends the run at once.
        if not state['played']:
            ev('DISCONNECT', state='login', before='play', booted=getattr(self, 'bootedIndex', None),
               text=str(getattr(self, 'bootedText', '') or '')[:200])
            os._exit(3)
        return origLost(self)
    cls.lostConnection = lostConnection
    cls._walkhooked = True
    return True


def patch_play():
    m = sys.modules.get('pirates.distributed.PlayGame')
    if m is None or not hasattr(m, 'PlayGame'):
        return False
    cls = m.PlayGame
    if cls.__dict__.get('_walkhooked', False):
        return True
    orig = cls.enterPlay

    def enterPlay(self, requestStatus):
        orig(self, requestStatus)
        if not state['played']:
            state['played'] = True
            import builtins
            b = builtins.base
            ev('entered-play', win=type(b.win).__name__, fps=round(builtins.globalClock.getAverageFrameRate(), 1),
               clockMode=int(builtins.globalClock.getMode()))    # 5 = limited (the 30 fps cap)
            state['playT'] = time.time()
            builtins.taskMgr.doMethodLater(min(START_MIN, START_WAIT), start_when_ready, 'walk-start')
    cls.enterPlay = enterPlay
    cls._walkhooked = True
    return True


def patcher_loop():
    while not state['done']:
        time.sleep(0.1)
        try:
            if patch_login():
                patch_play()
        except Exception:
            traceback.print_exc()


# ---------- teleport tripwire ----------
# While a step script runs, any call from this folder's code (walker.py, s_*.py) to setPos/setH/... on the local avatar
# is logged as a TELEPORT event (file:line) and counted. The game's own calls (movement, teleports, cutscenes) come from
# other folders and are not counted. The count goes into the finish event.
TELE = {'n': 0}
WATCH = {'t0': None, 'hooks': []}   # watchdog start time; hooks run just before watchdog-timeout
HARNESS_DIRS = set()
_IN_HARNESS = {}
TRIP_CALLS = ('setPos', 'setPosHpr', 'setH', 'setP', 'setR', 'setHpr', 'setX', 'setY', 'setZ', 'setXY', 'setXYZ',
              'setFluidPos', 'setFluidX', 'setFluidY', 'setFluidZ', 'headsUp', 'lookAt')


def _in_harness(fn):
    r = _IN_HARNESS.get(fn)
    if r is None:
        try:
            p = os.path.normcase(os.path.abspath(fn))
            r = any(p.startswith(d + os.sep) for d in HARNESS_DIRS)
            if not r and not os.path.isabs(fn) and not fn.startswith('<'):    # exec'd with a bare file name
                r = any(os.path.isfile(os.path.join(d, fn)) for d in HARNESS_DIRS)
        except Exception:
            r = False
        _IN_HARNESS[fn] = r
    return r


def install_tripwire(la):
    HARNESS_DIRS.add(os.path.normcase(os.path.dirname(os.path.abspath(__file__))))
    if os.environ.get('PROOF_SCRIPT'):
        HARNESS_DIRS.add(os.path.normcase(os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT']))))
    for name in TRIP_CALLS:
        orig = getattr(la, name, None)
        if orig is None:
            continue

        def wrap(*a, _orig=orig, _name=name, **k):
            try:
                f = sys._getframe(1)
                fn = f.f_code.co_filename
                if _in_harness(fn):
                    TELE['n'] += 1
                    if TELE['n'] <= 200:
                        ev('TELEPORT', call=_name, where='%s:%d' % (os.path.basename(fn), f.f_lineno), n=TELE['n'])
            except Exception:
                pass
            return _orig(*a, **k)
        try:
            setattr(la, name, wrap)
        except Exception:
            ev('tripwire-skip', call=name)
    ev('tripwire-on', calls=len(TRIP_CALLS), dirs=sorted(HARNESS_DIRS))


# ---------- human-like walking ----------
# The bot walks the way a player does: it holds the same inputs the keyboard sets (forward / turnLeft / turnRight /
# slideLeft / slideRight / jump) through the game's own inputState, and never moves the avatar itself.
KEY_SRC = 'harness-bot'
KEYS = ('forward', 'reverse', 'turnLeft', 'turnRight', 'slideLeft', 'slideRight', 'jump')
NOWALK = ('Cutscene', 'NPCInteract', 'Dialog', 'TeleportIn', 'Unconcious', 'ThrownInJail', 'Off', 'LandTutorial')


def key_set(name, on):
    """Hold/release a game input like a keypress. Idempotent and re-asserting: the game's releaseInputs() wipes every
    source of an input, so a held key that has gone missing is set again on the next call."""
    from direct.showbase.InputStateGlobal import inputState
    has = KEY_SRC in inputState._state.get(name, ())
    if on and not has:
        inputState.set(name, True, inputSource=KEY_SRC)
    elif not on and has:
        inputState.set(name, False, inputSource=KEY_SRC)


def keys_release():
    for k in KEYS:
        try:
            key_set(k, False)
        except Exception:
            pass


class Walk:
    """One walking leg, advanced one frame at a time by step(): turn on the spot until the heading error is small, then
    hold forward with gentle turn corrections, release every key on arrival. Never calls setPos/setH."""
    TURN_IN_PLACE = 35.0           # heading error (deg) above which it stops and turns on the spot
    TURN_DONE = 8.0                # ... until the error is down to this, then it walks
    CORR_ON, CORR_OFF = 6.0, 2.5   # gentle turn correction while walking (hysteresis, deg)
    FACE_TOL = 8.0                 # facing the target after arrival counts within this (deg)
    TURN_BAND_MAX = 20.0           # the turn band widens with the clock's own turn step per frame, never past this
    STUCK_SECS = 3.0               # no progress for this long = stuck

    def __init__(self, H, target, ref=None, arrive=2.0, timeout=None, face=False, tag=''):
        self.H, self.la = H, H.la
        self.tgt, self.ref = target, (ref if ref is not None else H.render)
        self.arrive, self.face, self.tag = arrive, face, tag
        self.phase, self.turning, self.overlay = 'turn', 0, None
        self.tries, self.maxerr, self.turnSecs = 0, 0.0, 0.0
        self.done, self.ok, self.why, self.key, self.end, self.secs = False, None, None, None, None, 0.0
        self.t0 = self.last = self.t_prog = time.time()
        self.t_end, self.face_t0, self.err, self.to = 0.0, None, 0.0, None
        m = self._meas()
        self.start = m[0] if m else 0.0
        self.dist, self.best, self.err_best = self.start, self.start, 999.0
        self.timeout = timeout if timeout is not None else 20.0 + self.start / 10.0
        self.frm = H.P(self.la)
        self.err_prev, self.turnStep = None, 0.0     # the clock's turn step per frame, measured while turning
        if hasattr(H, 'fast'):
            H.fast(('walk', id(self)), True)         # the move clock while this leg runs (off again in _end)

    def _pt(self):
        t = self.tgt
        if callable(t) and not hasattr(t, 'getPos'):
            t = t()
        if hasattr(t, 'getPos'):
            return None if t.isEmpty() else t.getPos(self.ref)
        from panda3d.core import Point3
        return Point3(*t)

    def _meas(self):
        """(horizontal distance, bearing error in deg: + = target is to the right, target point) or None."""
        try:
            p = self._pt()
            if p is None:
                return None
            rel = self.la.getRelativePoint(self.ref, p)
            d = math.hypot(rel[0], rel[1])
            self.to = [round(v, 1) for v in p]
            return d, (math.degrees(math.atan2(rel[0], rel[1])) if d > 0.05 else 0.0), p
        except Exception:
            return None

    def _hold(self, *names):
        for k in KEYS:
            key_set(k, k in names)

    def release(self):
        """Always safe to call: ends the leg if it is still running and lets go of every key."""
        try:
            if not self.done:
                self._end(False, 'aborted')
        finally:
            keys_release()

    def _end(self, ok, why):
        if self.done:
            return self.ok
        self.done, self.ok, self.why, self.t_end = True, ok, why, time.time()
        keys_release()
        if hasattr(self.H, 'fast'):
            self.H.fast(('walk', id(self)), False)
        m = self._meas()
        self.end = round(m[0], 2) if m else None
        self.secs = round(self.t_end - self.t0, 2)
        H = self.H
        if why == 'stuck':
            H.ev('stuck', tag=self.tag, la=H.P(self.la), target=self.to, ref=type(self.ref).__name__,
                 tries=self.tries, dist=self.end)
        if not (self.start <= self.arrive and self.secs < 0.5):
            H.ev('walk-leg', tag=self.tag, ok=ok, why=why, start=round(self.start, 1), end=self.end,
                 maxHerr=round(self.maxerr, 1), secs=self.secs, turnSecs=round(self.turnSecs, 2),
                 stuckTries=self.tries, frm=self.frm, to=self.to, ref=type(self.ref).__name__)
        return ok

    def _check_stuck(self, now, d, err):
        if now - self.t_prog < self.STUCK_SECS:
            return None
        self.tries += 1
        info = dict(tag=self.tag, tries=self.tries, dist=round(d, 1), err=round(err, 1), la=self.H.P(self.la))
        # job 8: back off what he walked into first (a player never jumps on the spot against a wall), then go round it:
        # try 1 = back up 0.7 s, then forward + slide to the side the target is on for 1 s; try 2 = back up 0.7 s, run
        # 0.4 s, then a running jump; try 3 = give up ('stuck') so the route above plans another way
        side = 'slideRight' if err > 0 else 'slideLeft'
        if self.tries == 1:
            self._seq(now, [(0.7, ('reverse',), 0.0), (1.0, ('forward', side), 0.0)])
            self.H.ev('walk-stuck-try', how='backup+sidestep', **info)
        elif self.tries == 2:
            self._seq(now, [(0.7, ('reverse',), 0.0), (0.4, ('forward',), 0.0), (0.6, ('forward',), 0.35)])
            self.H.ev('walk-stuck-try', how='backup+running-jump', **info)
        else:
            return self._end(False, 'stuck')    # no teleport fallback: give up and say so
        self.t_prog = now
        return None

    def _seq(self, now, phases):
        """Run stuck-escape moves one after another: phases = [(secs, keys, jump secs at its start)]."""
        self.seq = list(phases)
        self._next_move(now)

    def _next_move(self, now):
        secs, keys, jump = self.seq.pop(0)
        self.overlay = (now + secs, keys, now + jump if jump else 0.0)

    def step(self):
        """One frame. None = still going; True = arrived (and facing, if asked); False = gave up (see self.why)."""
        if self.done:
            return self.ok
        now = time.time()
        dt = min(now - self.last, 0.25)
        self.last = now
        m = self._meas()
        if m is None:
            return self._end(False, 'target-gone')
        d, err, p = m
        self.dist, self.err = d, err
        ae = abs(err)
        try:
            gs = self.la.getGameState()
        except Exception:
            gs = None
        if gs in NOWALK:            # the game has the controls (cutscene, dialog, teleport): wait, not stuck
            self._hold()
            self.timeout += dt
            self.t_prog = now
            return None
        if now - self.t0 > self.timeout:
            return self._end(False, 'timeout')
        if self.phase != 'face' and d <= self.arrive:
            if not self.face:
                return self._end(True, 'arrived')
            self.phase, self.face_t0, self.overlay = 'face', now, None
        if self.phase == 'face':
            if ae <= self.FACE_TOL or now - self.face_t0 > 4.0:
                return self._end(True, 'arrived')
            self.turnSecs += dt
            self._hold('turnRight' if err > 0 else 'turnLeft')
            return None
        if self.overlay is not None:        # a stuck-escape move (sidestep / jump) is running
            until, keys, jump_until = self.overlay
            if now < until:
                self._hold(*(keys + (('jump',) if now < jump_until else ())))
                return None
            if getattr(self, 'seq', None):
                self._next_move(now)
                return None
            self.overlay = None
            self.best, self.err_best, self.t_prog = d, 999.0, now
        if self.phase == 'turn':
            self.turnSecs += dt
            if self.err_prev is not None:
                # how far one frame's turn moves the error: the band must hold at least one step, or a coarse clock
                # overshoots it every frame (pbots run 4 at 5 fps: 26 deg a frame, -11.8 <-> +14.4 round the 8 deg band)
                s = abs(err - self.err_prev)
                self.turnStep = max(self.turnStep, min(s, 360.0 - s))
            self.err_prev = err
            if ae <= min(self.TURN_BAND_MAX, max(self.TURN_DONE, 0.6 * self.turnStep)):
                self.phase, self.turning, self.err_prev = 'go', 0, None
                self.best, self.t_prog = d, now
            else:
                self._hold('turnRight' if err > 0 else 'turnLeft')
                if ae < self.err_best - 3.0:
                    self.err_best, self.t_prog = ae, now
                return self._check_stuck(now, d, err)
        if ae > self.TURN_IN_PLACE:         # walking, but the target is well off the nose: stop and turn
            self.phase, self.err_best, self.t_prog = 'turn', ae, now
            self._hold('turnRight' if err > 0 else 'turnLeft')
            return None
        if d > 6.0:                         # heading error is judged after the turn phase, away from the target
            self.maxerr = max(self.maxerr, ae)
        if ae < self.CORR_OFF:
            self.turning = 0
        elif ae > self.CORR_ON:
            self.turning = 1 if err > 0 else -1
        keys = ['forward']
        if self.turning:
            keys.append('turnRight' if self.turning > 0 else 'turnLeft')
        self._hold(*keys)
        if d < self.best - 0.4:
            self.best, self.t_prog = d, now
        return self._check_stuck(now, d, err)


def ready():
    """pir-bot job 5: the pirate can be driven: LandRoam / ShipPilot / WaterRoam with a parent object."""
    import builtins
    la = getattr(builtins.base, 'localAvatar', None)
    if la is None:
        return False
    try:
        gs = la.getGameState()
    except Exception:
        return False
    if gs in ('LandRoam', 'ShipPilot', 'WaterRoam'):
        try:
            return la.getParentObj() is not None
        except Exception:
            return True
    return False


def start_when_ready(task):
    waited = time.time() - state.get('playT', time.time())
    try:
        ok = bool(ready())
    except Exception:
        ok = False
    if ok or waited >= START_WAIT:
        ev('start-wait', secs=round(waited, 1), ready=ok)
        return driver_start(task)
    task.delayTime = 0.25
    return task.again


def finish():
    state['done'] = True
    try:
        keys_release()
    except Exception:
        pass
    try:
        ev('TIME-LEDGER', **ledger_line())
    except Exception:
        pass
    ev('finish', teleports=TELE['n'])
    ev_f.flush()
    os._exit(0)


class Helper:
    def __init__(self, la):
        import builtins
        self.la = la
        self.B = builtins.base
        self.cr = self.B.cr
        self.render = builtins.render
        self.ev = ev
        self.resp = []
        self.scenes = []
        self.dialogs = []
        self.yesSecs = float(os.environ.get('PROOF_YES_SECS', '3'))
        self._hook()

    def fast(self, reason, on=True):
        """Run the clock at MOVE_FPS while anything walks or plans (every Walk leg, a brain flow: each a reason), back to
        BOT_FPS when the last reason ends. A 5 fps idle body cannot steer (a 0.2 s frame turns 26 deg, outside Walk's
        8 deg band, so it 2-cycled and went 'stuck') and its planner got a few probes a frame (pbots run 4). A bot
        already at 30 fps sees no change (never under BOT_FPS)."""
        import panda3d.core
        fast = self.__dict__.setdefault('_fast', set())
        (fast.add if on else fast.discard)(reason)
        want = max(BOT_FPS, MOVE_FPS) if fast else BOT_FPS
        if want != self.__dict__.get('_fps', BOT_FPS):     # a 30 fps lane never gets here: nothing to change
            self._fps = want
            try:
                panda3d.core.ClockObject.getGlobalClock().setFrameRate(want)
                self.ev('clock', fps=want, reasons=len(fast))
            except Exception:
                pass

    # ---------- hooks ----------
    def _hook(self):
        H = self
        B = self.B
        from otp.ai import MagicWordManager as MWm
        oMWR = MWm.MagicWordManager.sendMagicWordResponse

        def mwr(mgr, response):
            H.resp.append(response)
            ev('mw-response', response=response)
            return oMWR(mgr, response)
        MWm.MagicWordManager.sendMagicWordResponse = mwr
        from pirates.quest import DistributedQuestAvatar as DQAm
        cls = DQAm.DistributedQuestAvatar
        oStep = cls.setQuestStep

        def setQuestStep(av, args):
            ev('srv-setQuestStep', args=args)
            return oStep(av, args)
        cls.setQuestStep = setQuestStep
        oAct = cls.setActiveQuest

        def setActiveQuest(av, q):
            ev('srv-setActiveQuest', q=q)
            return oAct(av, q)
        cls.setActiveQuest = setActiveQuest
        from pirates.quest import DistributedQuest as DQm
        oSFS = DQm.DistributedQuest.startFinalizeScene

        def sfs(q, idx, giverId, endEvent=None):
            info = q.questDNA.getFinalizeInfo()[idx]
            H.scenes.append((q.getQuestId(), idx, info.get('type'), info.get('sceneId') or info.get('dialogId')))
            ev('startFinalizeScene', quest=q.getQuestId(), idx=idx, giverId=giverId,
               type=info.get('type'), scene=info.get('sceneId') or info.get('dialogId'))
            try:
                return oSFS(q, idx, giverId, endEvent)
            except Exception:
                ev('CRASH-startFinalizeScene', tb=traceback.format_exc()[-1500:])
                raise
        DQm.DistributedQuest.startFinalizeScene = sfs
        oDFS = DQm.DistributedQuest.doneFinalizeScene

        def dfs(q):
            ev('doneFinalizeScene', quest=q.getQuestId())
            try:
                oDFS(q)
            except Exception:
                ev('CRASH-doneFinalizeScene', tb=traceback.format_exc()[-1500:])
                raise
            B.taskMgr.doMethodLater(3.0, lambda t: H.animCheck('after-dfs %s' % q.getQuestId()) or t.done, 'walk-anim')
        DQm.DistributedQuest.doneFinalizeScene = dfs
        from pirates.npc import DistributedNPCTownfolk as DNm
        oPDM = DNm.DistributedNPCTownfolk.playDialogMovie

        def pdm(npc, dialogId, doneCallback=None, oldLocalAvState=None):
            H.dialogs.append(dialogId)
            ev('playDialogMovie', npc=npc.doId, uid=getattr(npc, 'uniqueId', None), dialogId=dialogId, hasCb=doneCallback is not None,
               anim=H.curAnim(npc))
            if os.environ.get('DUMP_SCRIPTS'):
                try:
                    from pirates.quest import QuestParser
                    from pirates.distributed import InteractGlobals
                    sid = InteractGlobals.getNPCTutorial(dialogId) or dialogId
                    ev('dialog-script', sid=sid, lines=QuestParser.lineDict.get(sid))
                except Exception:
                    ev('dialog-script-err', tb=traceback.format_exc()[-400:])
            try:
                return oPDM(npc, dialogId, doneCallback, oldLocalAvState)
            except Exception:
                ev('CRASH-playDialogMovie', tb=traceback.format_exc()[-1500:])
                raise
        DNm.DistributedNPCTownfolk.playDialogMovie = pdm
        oDMC = getattr(DNm.DistributedNPCTownfolk, 'dialogMovieComplete', None)
        if oDMC:
            def dmc(npc, *a):
                ev('dialogMovieComplete-client', npc=npc.doId)
                r = oDMC(npc, *a)
                B.taskMgr.doMethodLater(3.0, lambda t: H.animCheck('after-dialog') or t.done, 'walk-anim2')
                return r
            DNm.DistributedNPCTownfolk.dialogMovieComplete = dmc
        from pirates.piratesgui import NewTutorialPanel as NTPm
        oTAct = NTPm.NewTutorialPanel.activate

        def act(panel):
            r = oTAct(panel)
            ev('panel-activate')

            def click(t):
                try:
                    y = getattr(panel, 'yesTutorial', None)
                    cmd = None if y is None or not hasattr(y, '_optionInfo') else y['command']
                    if cmd:
                        cmd(*(y['extraArgs'] or []))
                    ev('panel-click-yes', has=cmd is not None)
                except Exception:
                    ev('panel-click-err', tb=traceback.format_exc()[-300:])
                return t.done
            B.taskMgr.doMethodLater(H.yesSecs, click, 'walk-yes')
            return r
        NTPm.NewTutorialPanel.activate = act
        from pirates.cutscene import Cutscene as CSm
        oPlay = CSm.Cutscene.play

        def csPlay(cs, *a, **k):
            ev('cutscene-play', cs=getattr(cs, 'name', None))
            return oPlay(cs, *a, **k)
        CSm.Cutscene.play = csPlay
        oDestroy = getattr(CSm.Cutscene, 'destroy', None)
        if oDestroy:
            def csDestroy(cs, *a, **k):
                ev('cutscene-destroy', cs=getattr(cs, 'name', None))
                r = oDestroy(cs, *a, **k)
                B.taskMgr.doMethodLater(2.0, lambda t: H.animCheck('after-cutscene') or t.done, 'walk-anim3')
                return r
            CSm.Cutscene.destroy = csDestroy

    # ---------- queries ----------
    def P(self, np_):
        try:
            return None if np_ is None or np_.isEmpty() else [round(v, 1) for v in np_.getPos(self.render)]
        except Exception as e:
            return 'err %s' % e

    def mw(self, word):
        from otp.ai import MagicWordManager as MWm
        mgr = next((o for o in self.cr.doId2do.values() if isinstance(o, MWm.MagicWordManager)), None)
        ev('mw', word=word, mgr=mgr is not None)
        mgr.sendUpdate('sendMagicWord', [word, self.la.doId])

    def quests(self):
        out = []
        for q in self.la.getQuests():
            try:
                ts = [(getattr(s, 'progress', None), getattr(s, 'goal', None), getattr(s, 'attempts', None)) for s in q.getTaskStates()]
            except Exception as e:
                ts = repr(e)
            out.append({'id': q.getQuestId(), 'complete': q.isComplete(), 'ts': ts})
        return out

    def qids(self):
        return [q.getQuestId() for q in self.la.getQuests()]

    def has(self, qid):
        return qid in self.qids()

    def hist(self):
        return list(self.la.getQuestHistory())

    def area(self):
        p = self.la.getParentObj()
        return None if p is None else (type(p).__name__, getattr(p, 'uniqueId', None), getattr(p, 'name', None))

    def step(self):
        la = self.la
        qs = la.questStep
        ind = getattr(la, 'questIndicator', None)
        node = getattr(ind, 'indicatorNode', None) if ind else None
        d = {'active': la.activeQuestId, 'questStep': repr(qs) if qs else None}
        if node is not None:
            d['ind'] = {'cls': type(node).__name__, 'fsm': node.state, 'pos': self.P(node)}
        return d

    def objs(self, sub):
        out = []
        lp = self.la.getPos(self.render)
        for o in list(self.cr.doId2do.values()):
            n = type(o).__name__
            if sub in n:
                try:
                    dist = round((o.getPos(self.render) - lp).length(), 1)
                except Exception:
                    dist = None
                par = o.getParentObj() if hasattr(o, 'getParentObj') else None
                out.append({'doId': o.doId, 'cls': n, 'name': getattr(o, 'name', None), 'dist': dist,
                            'hp': getattr(o, 'hp', None), 'par': getattr(par, 'uniqueId', None),
                            'type': str(getattr(o, 'avatarType', None))})
        out.sort(key=lambda d: d['dist'] if d['dist'] is not None else 1e9)
        return out

    def curAnim(self, o):
        try:
            return o.getCurrentAnim()
        except Exception as e:
            return 'err %s' % e

    def animCheck(self, tag):
        bad, good = [], 0
        for o in list(self.cr.doId2do.values()):
            if type(o).__name__ != 'DistributedNPCTownfolk':
                continue
            try:
                cur = o.getCurrentAnim()
            except Exception as e:
                cur = 'err %s' % e
            if cur is None:
                bad.append({'doId': o.doId, 'name': getattr(o, 'name', None), 'uid': getattr(o, 'uniqueId', None),
                            'dist': round((o.getPos(self.render) - self.la.getPos(self.render)).length(), 1),
                            'hidden': o.isHidden(), 'state': getattr(o, 'state', None)})
            else:
                good += 1
        ev('anim-check', tag=tag, noAnim=bad, playing=good)
        self.lastBad = bad

    def snap(self, tag):
        ev('snap', tag=tag, quests=self.quests(), hist=self.hist(), area=self.area(), step=self.step(),
           la=self.P(self.la), gs=self.la.getGameState())

    # ---------- actions ----------
    def moveTo(self, x, y, z):
        par = self.la.getParentObj()
        isl = par
        while isl is not None and 'Island' not in type(isl).__name__ and 'GameArea' not in type(isl).__name__:
            isl = isl.getParentObj() if hasattr(isl, 'getParentObj') else None
        ref = isl if isl is not None else self.render
        ok = yield from self.walk_to((x, y, z), ref=ref, arrive=3.0, tag='moveTo')
        ev('moveTo', to=(x, y, z), ref=type(ref).__name__, ok=ok, la=self.P(self.la))
        return ok

    def drawSword(self):
        from pirates.uberdog.UberDogGlobals import InventoryType
        self.la.d_requestCurrentWeapon(InventoryType.CutlassWeaponL1, 1)

    def _swing(self, doId):
        from pirates.uberdog.UberDogGlobals import InventoryType
        from direct.distributed.ClockDelta import globalClockDelta
        if self.cr.doId2do.get(doId) is None:
            return False
        pos = self.la.getPos(self.render)
        self.la.sendRequestTargetedSkill(InventoryType.CutlassHack, 0, 1, doId, [], globalClockDelta.getRealNetworkTime(bits=32), list(pos), 0)
        return True

    def hit(self, doId, reach=3.5):
        """Generator (yield from): walk to within weapon reach of the target, turn to face it, then swing once."""
        t = self.cr.doId2do.get(doId)
        if t is None:
            return False
        ok = yield from self.walk_to(t, arrive=reach, face=True, timeout=30, tag='hit')
        return self._swing(doId) if ok else False

    # ---------- walking (held keys like a player; never setPos/setH; see class Walk) ----------
    def teleports(self):
        return TELE['n']

    def walk_to(self, pos, ref=None, arrive=2.0, timeout=None, face=False, tag=''):
        """Generator: `ok = yield from H.walk_to((x, y, z), ref=render, arrive=2.0, timeout=60)`. pos is a point in ref's
        frame (default render), or a NodePath / distributed object (followed while it moves), or a callable returning
        either. Horizontal distance only. face=True also turns to face the target after arriving. Returns True on
        arrival; False on timeout / stuck (event 'stuck') / target gone. Every key is released on any exit."""
        self.walk_cancel()
        w = Walk(self, pos, ref, arrive, timeout, face, tag)
        self.lastWalk = w
        try:
            while True:
                r = w.step()
                if r is not None:
                    return r
                yield 0.02
        finally:
            w.release()

    def face(self, obj, tag='face'):
        """Generator: turn on the spot (keys only) until facing obj."""
        return (yield from self.walk_to(obj, arrive=1e9, face=True, timeout=6, tag=tag))

    def walk_cancel(self):
        w = getattr(self, '_bg', None)
        if w is not None:
            w.release()
        self._bg = None
        import builtins
        builtins.taskMgr.remove('bot-walk')

    def walk_poll(self, target, ref=None, arrive=2.0, face=False, tag='', timeout=None):
        """For callers that decide in one synchronous call per beat (s_story.act): a per-frame task does the walking.
        True = there already; False = walking (call again later); None = could not get there (retry after 8 s)."""
        import builtins
        key = (id(target) if hasattr(target, 'getPos') else tuple(round(v, 1) for v in target), arrive, id(ref))
        w = getattr(self, '_bg', None)
        if w is not None and w.key == key:
            if not w.done:
                return False
            if not w.ok and time.time() - w.t_end < 8.0:
                return None
        else:
            self.walk_cancel()
        w = Walk(self, target, ref, arrive, timeout, face, tag)
        w.key = key
        r = w.step()
        if r is True:
            return True
        if r is False:
            self._bg = w
            return None
        self._bg = w
        self.lastWalk = w

        def drive(task):
            try:
                r = w.step()
            except Exception:
                ev('walk-error', tb=traceback.format_exc()[-600:])
                w.release()
                return task.done
            return task.cont if r is None else task.done
        builtins.taskMgr.add(drive, 'bot-walk')
        return False

    def engage(self, doId, reach=3.5):
        """One fight beat for synchronous callers: walk to weapon reach and face the target, swing when there.
        -> 'walk' (still closing in) / 'swing' / 'gone' / 'stuck'."""
        t = self.cr.doId2do.get(doId)
        if t is None:
            return 'gone'
        r = self.walk_poll(t, arrive=reach, face=True, tag='engage')
        if r is None:
            return 'stuck'
        if r is False:
            return 'walk'
        return 'swing' if self._swing(doId) else 'gone'


def driver_start(task):
    import builtins
    la = builtins.base.localAvatar
    H = Helper(la)
    install_tripwire(la)
    ev('start-walk', qids=H.qids(), hist=H.hist(), area=H.area(), la=H.P(la))
    path = os.environ['PROOF_SCRIPT']
    g = {'__file__': path}  # step scripts read __file__ at their top level (s_bpfort, s_pages, s_standin)
    exec(compile(open(path).read(), path, 'exec'), g)
    gen = g['run'](H)
    st = {'until': None, 'last': None}

    def tick(t):
        try:
            if st['until'] is not None:
                fn, deadline, what, strict = st['until']
                ok = False
                try:
                    ok = fn()
                except Exception:
                    ev('until-error', tb=traceback.format_exc()[-600:])
                if not ok and time.time() < deadline:
                    t.delayTime = 0.5 if strict else 0.25
                    return t.again
                if not ok and strict:
                    ev('STALL', what=what)
                    H.snap('stall')
                st['until'] = None
            if st['last'] is not None:              # time ledger: what the last yield cost (sleep / until / upto)
                kind, site, t0 = st['last']
                ledger_add(kind, site, time.time() - t0)
                st['last'] = None
            y = next(gen)
            site = yield_site(gen)
            if isinstance(y, tuple) and y and y[0] in ('until', 'upto'):
                strict = y[0] == 'until'
                st['until'] = (y[1], time.time() + y[2], y[3] if len(y) > 3 else '?', strict)
                st['last'] = (y[0], site, time.time())
                t.delayTime = 0.5 if strict else 0.25
            else:
                st['last'] = ('sleep', site, time.time())
                t.delayTime = float(y)
            return t.again
        except StopIteration:
            ev('script-done')
            H.snap('end')
            finish()
        except Exception:
            ev('script-error', tb=traceback.format_exc()[-1500:])
            H.snap('script-error')
            finish()
        return t.done
    builtins.taskMgr.doMethodLater(0.5, tick, 'walk-tick')
    return task.done


def watchdog():
    t0 = WATCH['t0'] = time.time()
    while time.time() - t0 < SECS:
        time.sleep(0.5)
        if state['done']:
            return
        if state['played'] and time.time() - LAST['t'] > 240:
            ev('HANG', secs=round(time.time() - LAST['t']))
            finish()
        v = state['verdict']
        if SMOKE and v is not None and time.time() - v[1] >= SMOKE_LINGER:
            ev('SMOKE-END', verdict=v[0], after=round(time.time() - t0, 1))
            finish()
    for f in list(WATCH['hooks']):   # a script's last word before the kill (s_story: chunk-end + PASS on progress)
        try:
            f()
        except Exception as e:
            ev('timeout-hook-err', err=repr(e))
    ev('watchdog-timeout')
    finish()


sys.path.insert(0, os.getcwd())
import panda3d.core
# No offscreen buffer: PiratesBase forces base.windowType = 'onscreen' and the game calls window-only methods
# (getPointer, requestProperties), so the bot keeps a real window and run_walk.ps1 starts it on a hidden desktop.
# Bot clients run muted. The game loads config/general.prc and game_options pages AFTER this point, and a
# later page wins, so re-apply this page after every load.
MUTE = 'audio-library-name null\naudio-music-active #f\naudio-sfx-active #f\naudio-volume 0\naudio-master-sfx-volume 0\naudio-master-music-volume 0\nsync-video #f'
# pbots 11-22: BOT_PRC = a prc file whose lines join this page (the low-memory bot game, pbot/prc/strip-gl.prc: 8x8
# stand-in textures that keep their names, no reflections or shadows; measured MEAS7 = 1.37-1.49 GB per bot against
# 1.6-1.7 plain), so they too win over every later page. Unset = as before.
_botPrc = os.environ.get('BOT_PRC')
if _botPrc and os.path.exists(_botPrc):
    _lines = [l for l in open(_botPrc).read().splitlines() if l.strip() and not l.startswith('#')]
    # MEAS3-5 (11-22 01:20): the prc variable fake-texture-image does nothing this late (the TexturePool copies it
    # once, when it is made at import), and TexturePool.setFakeTextureImage hands every texture back under the FAKE's
    # name: the pirate maker finds its clothes textures by name (PirateFemale.py clothesTextures.findTexture(name)
    # -> None -> setTexture(None) TypeError before the login screen). A pool filter keeps the names: every texture the
    # game asks for becomes a copy of the 8x8 stand-in named like the real one (proven standalone: a ship model's
    # findTexture('ship_skel_trim_gold_3') still finds it, 192 bytes in RAM instead of 192 KB).
    class _TinyTextures:
        def __init__(self, path):
            self.n = 0
            self.base = panda3d.core.Texture('fake')
            self.ok = self.base.read(panda3d.core.Filename(path))

        def pre_load(self, orig, alpha, channels, alphaChannel, mipmaps, options):
            t = self.base.makeCopy()
            t.setName(orig.getBasenameWoExtension())
            t.setFilename(orig)
            t.setFullpath(orig)
            if not alpha.empty():
                t.setAlphaFilename(alpha)
            self.n += 1
            return t

        def post_load(self, tex):
            return tex
    for _l in list(_lines):
        if _l.startswith('fake-texture-image '):
            _lines.remove(_l)
            TINY_TEXTURES = _TinyTextures(_l.split(None, 1)[1].strip())
            if TINY_TEXTURES.ok:
                panda3d.core.TexturePool.getGlobalPtr().registerFilter(TINY_TEXTURES)
            else:
                sys.stderr.write('walker: stand-in texture %s did not load; textures stay real\n' % _l)
    MUTE += '\n' + '\n'.join(_lines)
# live check 11-20: BOT_LIGHT=1 caps a second game at 5 fps (the two-game boarding check; a step may raise it with
# globalClock.setFrameRate while it walks). The window size comes from the game's own options, not a prc page, so
# the step shrinks the window itself (base.win.requestProperties). Unset = as before. BOT_FPS = any other cap (pbots).
LIGHT = os.environ.get('BOT_LIGHT') == '1'
# Cap at 30 fps in code: the global clock already exists once panda3d.core is imported, so clock-mode in a prc
# page (general.prc's 120 cap too) never applies; uncapped the hidden bot game ran ~700 fps.
BOT_FPS = int(os.environ.get('BOT_FPS') or (5 if LIGHT else 30))    # the idle cap
MOVE_FPS = int(os.environ.get('BOT_MOVE_FPS') or 20)                # while a leg walks or a flow plans (Helper.fast)
_clk = panda3d.core.ClockObject.getGlobalClock()
_clk.setMode(panda3d.core.ClockObject.MLimited)
_clk.setFrameRate(BOT_FPS)
_origPrcFile, _origPrcData = panda3d.core.loadPrcFile, panda3d.core.loadPrcFileData
def _mutedPrcFile(*a, **k):
    r = _origPrcFile(*a, **k)
    _origPrcData('zz-bot-mute', MUTE)
    return r
def _mutedPrcData(*a, **k):
    r = _origPrcData(*a, **k)
    _origPrcData('zz-bot-mute', MUTE)
    return r
panda3d.core.loadPrcFile, panda3d.core.loadPrcFileData = _mutedPrcFile, _mutedPrcData
_origPrcData('zz-bot-mute', MUTE)
from direct.stdpy import threading as pthreading
pthreading.Thread(target=patcher_loop, daemon=True).start()
pthreading.Thread(target=watchdog, daemon=True).start()
ev('start')
# games 11-22: watch Panda's state table for the garbage_collect crash (gcwatch.py, bug cfc4ee). GC_WATCH=0 = off.
if os.environ.get('GC_WATCH', '1') != '0':
    try:
        import gcwatch
        gcwatch.install(ev, os.path.basename(EVOUT).replace('walk-', '').replace('-events.jsonl', ''))
    except Exception:
        traceback.print_exc()
sys.modules['pir_walker'] = sys.modules[__name__]   # runpy below swaps __main__ for PiratesStart; step scripts find the walker here
runpy.run_module('pirates.piratesbase.PiratesStart', run_name='__main__', alter_sys=True)
