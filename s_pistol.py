"""s_pistol: Barbossa's pistol practice (quest_tut_barbossa_pistol_tutorial, c2.11visitBarbossa), played like a player.

The quest script (QuestScripts.txt, ID quest_tut_barbossa_pistol_tutorial) locks the pirate, draws the pistol (Battle
state, FPS camera, aim bounds 150-230) and shows four panels.  Each panel waits for ONE event:

    pistolAim      -> pistolMoved        FPSCamera, any mouse move while the right button is held
    pistolTarget   -> pistolAimedTarget  TargetManager.aimOverTargetTask, the aim ray lands on an enemy (the monkey)
    pistolHit      -> pistolHitTarget    DistributedBattleAvatar.playOuch, any battle avatar is hurt (one hit is enough)
    pistolPractice -> weaponSheathed     Escape -> LocalPirate.requestExitBattle (leaves Battle, sends the event)

Then FINISH_QUEST_MOVIE frees the pirate and the hand-in goes on.  So the quest needs ONE aim-over and ONE hit, then
Escape.  Game check (11-17): the monkey (uid 1175912064.0JB2) is spawned by EnemySpawnNode as a DistributedCreature
(team UNDEAD, battleable, has an aim tube on BattleAimBitmask), so a real player can aim at it, a hit counts, and
Escape leaves Battle.  No game bug found in the code; STORY6 showed currentAimOver never set, cause unknown offline,
so this module logs PISTOL-DIAG with every fact that decides it, applies the player-side fixes, and if a step still
does not come it sends that step's event itself, marked PISTOL-FORCED (a forced run is not proof the step works).

Never sits: every step has a time limit, the whole practice has TOTAL_LIMIT, and after the sheathe a pirate still in
Battle is taken out with requestExitBattle (the game's own Escape handler).

install(H) returns the panel modes it owns; s_story.tutPlay skips those.
"""
import math
import time

MONKEY_UID = '1175912064.0JB2'
MODES = ('pistolAim', 'pistolTarget', 'pistolHit', 'pistolPractice')
WANT = {'pistolAim': 'pistolMoved', 'pistolTarget': 'pistolAimedTarget', 'pistolHit': 'pistolHitTarget',
        'pistolPractice': 'weaponSheathed'}
AIM_BOUNDS = (150.0, 230.0)   # SET_AIM_BOUNDS 190 150 230 (camera heading the script allows)
FIX_AT = 5.0         # s on pistolTarget without an aim-over: check stash / sticky targets / the aim task, fix
AIM_LIMIT = 25.0     # s on pistolAim / pistolTarget, then PISTOL-FORCED
HIT_LIMIT = 20.0     # s on pistolHit
SHEATHE_LIMIT = 8.0  # s on pistolPractice
BATTLE_LIMIT = 15.0  # s still in Battle after the sheathe, then requestExitBattle
TOTAL_LIMIT = 150.0  # s from the first pistol panel to free
SHOT_EVERY = 1.3     # s between shots (pistol reload)
ESC_EVERY = 2.0      # s between Escape presses


# ---------- pure helpers (unit-tested offline) ----------

def heading_to(frm, to):
    """Panda heading (degrees, 0..360) that faces from frm (x, y) to to (x, y)."""
    return math.degrees(math.atan2(-(to[0] - frm[0]), to[1] - frm[1])) % 360.0


def in_bounds(h, lo=AIM_BOUNDS[0], hi=AIM_BOUNDS[1]):
    h %= 360.0
    return lo <= h <= hi if lo <= hi else (h >= lo or h <= hi)


def aim_step(ha, va, sensH, sensP, invert=False, gain=0.5, cap=30.0):
    """Mouse delta that turns the camera `gain` of the way to a point ha deg right / va deg up of the aim ray."""
    dx = max(-cap, min(cap, gain * ha / (sensH or 1.0)))
    dy = max(-cap, min(cap, -gain * va / (sensP or 1.0)))
    return dx, (-dy if invert else dy)


def angles(p):
    """(heading-right, pitch-up) degrees of a point p=(x, y, z) in the aim ray's frame (+y forward)."""
    return (math.degrees(math.atan2(p[0], p[1])),
            math.degrees(math.atan2(p[2], math.hypot(p[0], p[1]))))


def plan(mode, secs, got, over=False, fixed=False, gs=None):
    """What to do now on a panel `mode` shown `secs` ago.  got: its event came after the panel.  over: something is
    under the aim ray.  fixed: the FIX_AT checks ran.  mode 'free' = after the sheathe; gs = the game state."""
    if mode == 'free':
        if gs == 'LandRoam':
            return 'done'
        return 'exit' if gs == 'Battle' and secs > BATTLE_LIMIT else 'wait'
    if got:
        return 'next'
    if mode in ('pistolAim', 'pistolTarget'):
        if secs > AIM_LIMIT:
            return 'force'
        if mode == 'pistolTarget' and secs > FIX_AT and not fixed:
            return 'fix'
        return 'aim'
    if mode == 'pistolHit':
        if secs > HIT_LIMIT:
            return 'force'
        return 'shoot' if over else 'aim'
    if mode == 'pistolPractice':
        return 'force' if secs > SHEATHE_LIMIT else 'sheathe'
    return 'wait'


# ---------- live part ----------

def install(H):
    from panda3d.core import Point3
    from direct.showbase.DirectObject import DirectObject
    from direct.showbase.MessengerGlobal import messenger as msg
    from pirates.piratesgui import NewTutorialPanel as NTPm
    from pirates.pirate import CameraMode as CMm

    st = {'mode': None, 'modeT': 0.0, 'n0': 0, 'fixed': False, 'firstT': None, 'shotT': 0.0, 'escT': 0.0,
          'freeT': None, 'forced': [], 'real': [], 'diagN': 0, 'over': None, 'task': False, 'm3T': 0.0,
          'exitTried': False}
    heard = {'n': 0}
    vm = {'d': None}
    oRead = CMm.CameraMode._mouseReadTask

    def read(cam, task):   # the bot's window has no real mouse: hand FPSCamera our move where it reads the pointer
        r = oRead(cam, task)
        if vm['d'] is not None:
            cam.mouseDelta, vm['d'] = vm['d'], None
        return r
    CMm.CameraMode._mouseReadTask = read
    obs = DirectObject()

    def hear(e):
        heard['n'] += 1
        heard[e] = heard['n']
        H.ev('PISTOL-EVENT', event=e, mode=st['mode'])
    for e in set(WANT.values()):
        obs.accept(e, hear, [e])

    def la():
        return H.la

    def target():
        # the uid can name the area's placeholder node (no gameFSM, at the spawn spot, not the patrolling monkey):
        # STORY6's old aim used whatever came back and never got an aim-over
        for how, get in (('uid', lambda: H.cr.uidMgr.justGetMeMeObject(MONKEY_UID)),
                         ('uidDoId', lambda: H.cr.doId2do.get(H.cr.uidMgr.getDoId(MONKEY_UID)))):
            try:
                o = get()
            except Exception:
                o = None
            if o is not None and hasattr(o, 'gameFSM') and not (hasattr(o, 'isEmpty') and o.isEmpty()):
                return o, how
        from pirates.piratesbase import TeamUtils
        best = None
        for x in list(H.cr.doId2do.values()):
            try:
                if x is la() or not hasattr(x, 'gameFSM') or not TeamUtils.damageAllowed(x, la()):
                    continue
                d = la().getDistance(x)
                d -= 1000 if 'Monkey' in type(x).__name__ or 'Monkey' in repr(getattr(x, 'avatarType', '')) else 0
                if d < 120 and (best is None or d < best[0]):
                    best = (d, x)
            except Exception:
                continue
        return (best[1], 'nearest') if best else (None, None)

    def fps():
        return getattr(getattr(la(), 'cameraFSM', None), 'fpsCamera', None)

    def rayAngles(tgt):
        # the aim ray hangs off base.camera, 1 ft up (TargetManager.startFollowAim), along +y
        zc = tgt.getHeight() * 0.5 if hasattr(tgt, 'getHeight') else 1.5
        p = H.B.camera.getRelativePoint(tgt, Point3(0, 0, zc))
        return angles((p[0], p[1], p[2] - 1.0))

    def diag(tgt, how, why):
        st['diagN'] += 1
        d = {'why': why, 'how': how, 'mode': st['mode']}
        L = la()
        for k, f in (
                ('cls', lambda: type(tgt).__name__),
                ('uidObj', lambda: type(H.cr.uidMgr.justGetMeMeObject(MONKEY_UID)).__name__),
                ('doId', lambda: tgt.doId),
                ('uid', lambda: tgt.getUniqueId()),
                ('fsm', lambda: tgt.gameFSM.state),
                ('team', lambda: tgt.getTeam()),
                ('dmgOk', lambda: __import__('pirates.piratesbase.TeamUtils', fromlist=['x']).damageAllowed(tgt, L)),
                ('stashed', lambda: tgt.isStashed()),
                ('hidden', lambda: tgt.isHidden()),
                ('parent', lambda: tgt.getParent().getName()),
                ('dist', lambda: round(L.getDistance(tgt), 1)),
                ('yFromAv', lambda: round(tgt.getY(L), 1)),
                ('hdgTo', lambda: round(heading_to(tuple(L.getPos(render)), tuple(tgt.getPos(render))), 1)),
                ('avH', lambda: round(L.getH(render) % 360, 1)),
                ('camH', lambda: round(H.B.camera.getH(render) % 360, 1)),
                ('ray', lambda: [round(a, 1) for a in rayAngles(tgt)]),
                ('aimTubes', lambda: len(getattr(tgt, 'aimTubeNodePaths', []) or [])),
                ('battleTubes', lambda: len(getattr(tgt, 'battleTubeNodePaths', []) or [])),
                ('sticky', lambda: list(L.stickyTargets or [])),
                ('aimTask', lambda: bool(H.B.taskMgr.hasTaskNamed('aimOverTarget'))),
                ('reticleEmpty', lambda: H.cr.targetMgr.reticle.isEmpty()),
                ('gs', lambda: L.getGameState()),
                ('mouseCtl', lambda: fps().mouseControl),
                ('over', lambda: getattr(L.currentAimOver, 'doId', None)),
                ('takeAim', lambda: getattr(H.cr.targetMgr.takeAim(L), 'doId', None)),
                ('rayHits', lambda: [(q.getIntoNodePath().getName()[:40], q.getIntoNode().getIntoCollideMask().getWord())
                                     for q in [H.cr.targetMgr.aimQueue.getEntry(i)
                                               for i in range(min(5, H.cr.targetMgr.aimQueue.getNumEntries()))]])):
            if tgt is None and k not in ('uidObj', 'sticky', 'aimTask', 'reticleEmpty', 'gs', 'mouseCtl', 'over', 'takeAim',
                                         'rayHits', 'avH', 'camH'):
                continue
            try:
                d[k] = f()
            except Exception as e:
                d[k] = 'err:' + repr(e)[:60]
        H.ev('PISTOL-DIAG', **d)
        return d

    def fix(tgt):
        # what a player's game would have done: the monkey shown, stale doll targets dropped, the aim task running
        L, did = la(), []
        try:
            if tgt is not None and tgt.isStashed():
                tgt.unstash()
                did.append('unstash')
        except Exception:
            pass
        try:
            if L.stickyTargets:
                L.sendRequestRemoveStickyTargets(list(L.stickyTargets))
                L.setStickyTargets([])
                did.append('sticky')
        except Exception:
            pass
        try:
            if not H.B.taskMgr.hasTaskNamed('aimOverTarget'):
                H.cr.targetMgr.startFollowAim()
                did.append('startFollowAim')
        except Exception:
            pass
        H.ev('PISTOL-FIX', did=did)

    def aim(tgt):
        fc = fps()
        if fc is None or tgt is None:
            return
        now = time.time()
        if not fc.mouseControl and now - st['m3T'] > 2.0:   # right button not taken yet: press it again
            st['m3T'] = now
            msg.send('mouse3-up')
            msg.send('mouse3')
        ha, va = rayAngles(tgt)
        inv = bool(getattr(getattr(H.B, 'options', None), 'mouse_look', False))
        dx, dy = aim_step(ha, va, fc.SensitivityH, fc.SensitivityP, inv)
        if st['mode'] == 'pistolAim' and abs(dx) < 1 and abs(dy) < 1:
            dx = 2.0                                         # the first panel only wants a mouse move
        if abs(dx) >= 0.3 or abs(dy) >= 0.3:
            vm['d'] = (dx, dy)

    def force(m, why):
        st['forced'].append(m)
        H.ev('PISTOL-FORCED', mode=m, event=WANT[m], why=why, secs=round(time.time() - st['modeT'], 1))
        if m == 'pistolPractice':
            try:
                la().requestExitBattle()     # the game's Escape handler: LandRoam + weaponSheathed
            except Exception:
                msg.send('weaponSheathed')
            if heard.get('weaponSheathed', 0) <= st['n0']:
                msg.send('weaponSheathed')
        else:
            msg.send(WANT[m])

    def finish(ok, why):
        st['task'] = False
        try:
            msg.send('mouse3-up')
        except Exception:
            pass
        H.ev('PISTOL-DONE', ok=ok, why=why, real=st['real'], forced=st['forced'],
             secs=round(time.time() - (st['firstT'] or time.time()), 1), gs=la().getGameState())

    def tick(t):
        if not st['task']:
            return t.done
        now = time.time()
        m = st['mode']
        try:
            if st['firstT'] and now - st['firstT'] > TOTAL_LIMIT and m != 'free':
                H.ev('PISTOL-TIMEOUT', mode=m, secs=round(now - st['firstT'], 1))
                diag(*(target() + ('timeout',)))
                # the script is past this panel or stuck on it: put the pistol away the game's way and go free
                if m in WANT and m != 'pistolPractice':
                    force(m, 'timeout')
                force('pistolPractice', 'timeout')
                st['mode'], st['freeT'] = 'free', now
                return t.cont
            if m == 'free':
                gs = la().getGameState()
                a = plan('free', now - st['freeT'], False, gs=gs)
                if a == 'done':
                    finish(not st['forced'], 'free')
                    return t.done
                if a == 'exit' and not st['exitTried']:
                    st['exitTried'] = True
                    H.ev('PISTOL-LEAVE-BATTLE', secs=round(now - st['freeT'], 1))
                    la().requestExitBattle()
                elif a == 'exit' and now - st['freeT'] > BATTLE_LIMIT * 3:
                    finish(False, 'still ' + str(gs))
                    return t.done
                return t.cont
            if m not in WANT:
                return t.cont
            got = heard.get(WANT[m], 0) > st['n0']
            L = la()
            over = getattr(L, 'currentAimOver', None)
            if over is not st['over']:
                st['over'] = over
                H.ev('PISTOL-AIM-OVER', target=getattr(over, 'doId', None), cls=type(over).__name__ if over else None)
            a = plan(m, now - st['modeT'], got, over is not None, st['fixed'])
            tgt, how = target() if a in ('aim', 'shoot', 'fix', 'force') else (None, None)
            if a == 'next':
                st['real'].append(m)
                H.ev('PISTOL-STEP', mode=m, secs=round(now - st['modeT'], 1))
                if m == 'pistolPractice':
                    st['mode'], st['freeT'] = 'free', now
                    msg.send('mouse3-up')
                else:
                    st['mode'] = m + '-done'
                return t.cont
            if a == 'aim':
                if st['diagN'] == 0 and now - st['modeT'] > 3.0 and m == 'pistolTarget':
                    diag(tgt, how, 'first look')
                aim(tgt)
            elif a == 'fix':
                st['fixed'] = True
                diag(tgt, how, 'no aim-over after %ds' % FIX_AT)
                fix(tgt)
            elif a == 'shoot':
                aim(tgt)
                if now - st['shotT'] > SHOT_EVERY:
                    st['shotT'] = now
                    msg.send('mouse1')
                    H.B.taskMgr.doMethodLater(0.15, lambda x: msg.send('mouse1-up') or x.done, 'pistol-up')
                    H.ev('PISTOL-SHOT', over=getattr(over, 'doId', None))
            elif a == 'sheathe':
                if now - st['escT'] > ESC_EVERY:
                    st['escT'] = now
                    msg.send('mouse3-up')
                    msg.send('escape')
                    H.ev('PISTOL-ESC')
            elif a == 'force':
                diag(tgt, how, 'limit')
                force(m, 'limit')
                st['mode'] = m + '-forced'
                if m == 'pistolPractice':
                    st['mode'], st['freeT'] = 'free', now
        except Exception as e:
            H.ev('PISTOL-err', mode=m, err=repr(e)[-300:])
        return t.cont

    def act(panel):
        r = wAct(panel)
        m = getattr(panel, 'mode', None)
        if m in MODES:
            now = time.time()
            st.update(mode=m, modeT=now, n0=heard['n'], fixed=False if m == 'pistolTarget' else st['fixed'])
            if st['firstT'] is None:
                st['firstT'] = now
            H.ev('PISTOL-PANEL', mode=m)
            if m in ('pistolAim', 'pistolTarget', 'pistolHit'):
                msg.send('mouse3')
                st['m3T'] = now
            if not st['task']:
                st['task'] = True
                H.B.taskMgr.add(tick, 'pistol-practice')
        return r
    wAct = NTPm.NewTutorialPanel.activate
    NTPm.NewTutorialPanel.activate = act
    H.ev('PISTOL-READY')
    return set(MODES)
