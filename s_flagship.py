"""FLAGSHIP (pir-ships, 11-17): cripple a flagship, grapple it, board it, beat its deck crew and captain, loot it.

The bot step for server-tree patches 0135-0138 (flagship boarding, steps 1-4) and 0122 (the flagship test knobs).
From Port Royal (FLAGSHIP_FROM, any island uid):
 1. hunt   - launch our ship and fight with s_shipquest.hunt, the story's own sea fight, given a stand-in task that
             only flagships match. 0135 stops a flagship at 0 hp ("crippled") instead of sinking it, so hunt's own
             FOE-SUNK (hp <= 0) is where this step takes over.
 2. close  - check it is crippled (its game state WaitingForGrapple, our ship's boardableShipId = it), sail at it
             until it is within FLAGSHIP_CLOSE_R, put it on the beam, drop sail and leave the wheel.
 3. cannon - walk to the deck cannon on the side facing it (the one most nearly abeam of it), take it, load the
             grappling hook ammo (12908, free and infinite).
 4. grapple- aim at the flagship's grapple targets (the client puts them on it when it is crippled), the same way the
             mouse aims the cannon (CannonCamera), and fire, up to FLAGSHIP_GRAPPLE_SHOTS. A hit sends the game's own
             suggestProjectileSkillResult. If none lands, one direct hit report is sent for a target (logged
             GRAPPLE-HITCALL, route=hitcall: it proves the AI side, not the aiming). 0136 tows it alongside.
 5. board  - when it is InPosition, answer Yes on the game's "Board?" panel (its own button handler); with no panel
             in 15 s, the same request direct (BOARD-ASK route=direct). 0137 swings the crew across.
 6. deck   - on the flagship's deck, fight every enemy on it (s_fighter.Fighter, one at a time, nearest first) until
             the flagship is Defeated (0138: waves, then its captain).
 7. loot   - wait for the swing back to our ship; check the pocket gold, the loot popup and the royal chest in the hold.

Lines: FLAGSHIP-START, STAGE step=flagship what=at-island / launched / foe-seen / first-shot / crippled /
alongside / at-cannon / grapple-fired / grappled / in-position / boarding / on-deck / deck-foe / deck-kill /
defeated / swung-back / loot, plus GRAPPLE-SHOT, GRAPPLE-HITCALL, BOARD-ASK, DECK-FOE, DECK-KILL, LOOT-POPUP,
SAIL-DOWN, FLAGSHIP-END (every stage's result and time), then PASS or FAIL (why = the first stage that did not happen).
PASS = crippled, grappled, boarded, deck fight won (Defeated), swung back, and paid (gold rose or a loot popup).
FLAGSHIP_NEED_CHEST=1 also needs a royal chest in the hold (set flagship-special-loot-chance 1 on the AI).

env: FLAGSHIP_FROM (default Port Royal), FLAGSHIP_SECS (whole step, default 440), FLAGSHIP_HUNT_SECS (180),
FLAGSHIP_DECK_SECS (200), FLAGSHIP_CLOSE_R (450 ft), FLAGSHIP_GRAPPLE_SHOTS (6), FLAGSHIP_NO_HITCALL=1 (no direct
hit report: a miss is a FAIL), FLAGSHIP_NEED_CHEST, FLAGSHIP_DECK_R (130 ft: enemies this near its centre are on it).
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__', '.'))))

FROM = os.environ.get('FLAGSHIP_FROM', '1150922126.8dzlu')       # Port Royal (s_lanes.PR)
SECS = float(os.environ.get('FLAGSHIP_SECS', '440'))
HUNT_SECS = float(os.environ.get('FLAGSHIP_HUNT_SECS', '180'))
DECK_SECS = float(os.environ.get('FLAGSHIP_DECK_SECS', '200'))
CLOSE_R = float(os.environ.get('FLAGSHIP_CLOSE_R', '450'))
SHOTS = int(os.environ.get('FLAGSHIP_GRAPPLE_SHOTS', '6'))
HITCALL = os.environ.get('FLAGSHIP_NO_HITCALL') != '1'
NEED_CHEST = os.environ.get('FLAGSHIP_NEED_CHEST') == '1'
DECK_R = float(os.environ.get('FLAGSHIP_DECK_R', '130'))

GRAPPLE = 12908            # InventoryType.CannonGrappleHook: infinite, free (WeaponGlobals, probed 11-17)
SKCHEST = 3                # EconomyGlobals.CARGO_SKCHEST: a royal chest in the hold
SHOT_V = 750 * 0.6         # cannon shot speed with grapples: projectile power 750 x 0.6 (ProjectileAmmo)
GRAV = 4 * 32.174          # the cannonball's gravity (4 g)
PITCH = (-12.0, 24.0)      # CannonCamera's pitch limits
SWING = 60.0               # CannonCamera's heading limits, either side of the cannon's rest
STEER_KEYS = ('a', 'd')
CRIPPLED = ('WaitingForGrapple', 'GrappleLerping', 'InPosition')
STAGES = ('crippled', 'grappled', 'in-position', 'on-deck', 'defeated', 'swung-back', 'paid')


class FlagshipOnly:
    """A stand-in for a DefeatShipTaskDNA that only flagships match (s_shipquest.matches: isFlagship needs
    o.isFlagship; every flagship class has a team, so faction None matches it)."""
    faction = None
    hull = None
    level = 0
    isFlagship = True


# ---------------------------------------------------------------------------------------------- pure (offline tests)
def aim(start, target, v=SHOT_V, g=GRAV):
    """The render heading and pitch (degrees) that drop a shot fired at speed v from start onto target, on the low
    arc. -> (H, P), P None when it is out of range. Panda heading: 0 = +Y, 90 = -X."""
    dx, dy, dz = target[0] - start[0], target[1] - start[1], target[2] - start[2]
    h = math.degrees(math.atan2(-dx, dy))
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return h, None
    disc = v ** 4 - g * (g * d * d + 2 * dz * v * v)
    if disc < 0:
        return h, None
    return h, math.degrees(math.atan((v * v - math.sqrt(disc)) / (g * d)))


def flight(start, target, p, v=SHOT_V, g=GRAV):
    """Pure: where a shot at pitch p (degrees) along the line start->target is when it has gone the horizontal
    distance to target -> (seconds, height error ft). For the offline test of aim()."""
    d = math.hypot(target[0] - start[0], target[1] - start[1])
    vx, vz = v * math.cos(math.radians(p)), v * math.sin(math.radians(p))
    t = d / vx
    return t, start[2] + vz * t - 0.5 * g * t * t - target[2]


def wrap180(a):
    return ((a + 180.0) % 360.0) - 180.0


def pickCannon(rows, fx, fy, maxOff=55.0):
    """Pure. rows = [(doId, cx, cy)] our ship's cannons in its own frame (+x starboard, +y bow), (fx, fy) the
    flagship there. -> [(off-beam degrees, doId)] best first: only cannons on the flagship's side (cx and fx the same
    sign); off-beam = the angle between the cannon->flagship line and that side's beam. Those over maxOff come last."""
    out = []
    for doId, cx, cy in rows:
        if cx == 0 or cx * fx <= 0:
            continue
        off = math.degrees(math.atan2(abs(fy - cy), abs(fx - cx)))
        out.append((off, doId))
    out.sort(key=lambda r: (r[0] > maxOff, r[0]))
    return out


def onBeam(brg, lo=50.0, hi=130.0):
    """Pure: the flagship is on the beam (a broadside cannon can swing onto it)."""
    return lo <= abs(brg) <= hi


def deckRows(rows, centre, r=DECK_R):
    """Pure. rows = s_fighter.foeRows rows (doId, dist, hp, lvl, (x, y)); centre = the flagship (x, y). -> the live
    ones within r ft of it, nearest to us first."""
    out = [row for row in rows if (row[2] or 0) > 0
           and math.hypot(row[4][0] - centre[0], row[4][1] - centre[1]) <= r]
    out.sort(key=lambda row: row[1])
    return out


def verdict(st):
    """Pure. st = {stage: True/False, ...} plus 'chest' -> ('PASS', what) or ('FAIL', the first stage missed)."""
    for k in STAGES:
        if not st.get(k):
            return 'FAIL', k
    if NEED_CHEST and not st.get('chest'):
        return 'FAIL', 'chest'
    return 'PASS', 'crippled, grappled, boarded, beat the deck and the captain, swung back and was paid'


WHY = {'crippled': 'the flagship was not crippled (sank or got away): is 0135 live?',
       'grappled': 'no grapple landed (0136 tow never started)',
       'in-position': 'grappled but never came alongside (0136)',
       'on-deck': 'never landed on the flagship deck (0137)',
       'defeated': 'on the deck but the flagship was not Defeated (0138 deck fight)',
       'swung-back': 'never swung back to our ship (0138)',
       'paid': 'swung back but no gold and no loot popup (0138 / 0114 pay)',
       'chest': 'no royal chest in the hold (FLAGSHIP_NEED_CHEST=1; is flagship-special-loot-chance 1 set?)'}


# ---------------------------------------------------------------------------------------------- live (in the game)
def gsOf(o):
    try:
        return o.queryGameState()
    except Exception:
        return getattr(getattr(o, 'gameFSM', None), 'state', None)


def knockedOut(la):
    return (getattr(la, 'hp', 1) or 0) <= 0 or la.getGameState() in ('Death', 'Dying')


def cannonsOf(H, sid):
    return [o for o in list(H.cr.doId2do.values())
            if type(o).__name__ == 'DistributedShipCannon' and getattr(o, 'shipId', None) == sid]


def wheelOf(H, sid):
    w = [o for o in list(H.cr.doId2do.values())
         if type(o).__name__ == 'DistributedSteeringWheel' and getattr(o, 'shipId', None) == sid]
    return w[0] if w else None


def cannonPos(c):
    post = getattr(getattr(c, 'prop', None), 'cannonPost', None)
    try:
        if post is not None and not post.isEmpty():
            return post.getPos(render)
    except Exception:
        pass
    return c.getPos(render)


def targetsOf(foe):
    """The flagship's grapple targets the client built when it was crippled -> [(render pos, index, name)]."""
    out = []
    for t in list(getattr(getattr(foe, 'gameFSM', None), 'targets', None) or []):
        try:
            np = t[2]
            name = np.getNetTag('targetId') or np.getTag('targetId')
            out.append((np.getPos(render), int(name[-1:]) if name[-1:].isdigit() else 0, name))
        except Exception:
            continue
    if not out:
        try:
            for i, np in enumerate(foe.root.findAllMatches('**/grappleTargetSphere')):
                name = np.getNetTag('targetId') or np.getTag('targetId') or ''
                out.append((np.getPos(render), int(name[-1:]) if name[-1:].isdigit() else i, name))
        except Exception:
            pass
    return out


def setAim(cannon, hr, p):
    """Point the cannon the way CannonCamera does from the mouse: the swing node, the pitch node, the ship's
    avCannonRotate and currentHpr (so the camera's next frame keeps it). -> (relH, clamped?)."""
    prop, ship = cannon.prop, cannon.ship
    prop.hNode.setH(render, hr)
    rel = wrap180(prop.hNode.getH())
    clamped = abs(rel) > SWING or not (PITCH[0] <= p <= PITCH[1])
    rel = max(-SWING, min(SWING, rel))
    p = max(PITCH[0], min(PITCH[1], p))
    prop.hNode.setH(rel)
    prop.pivot.setH(0)
    prop.pivot.setP(p)
    prop.pivot.setR(render, 0)
    rot = getattr(ship, 'avCannonRotate', None)
    if rot is not None:
        rot.setH(rel)
        rot.setP(p)
        rot.setR(render, 0)
    prop.currentHpr = (rel + getattr(prop, 'shipH', 0), prop.pivot.getP(render), 0)
    return rel, clamped


def run(H):
    import s_lanes      # noqa: E402  (the harness's own modules, beside PROOF_SCRIPT)
    import s_shipquest  # noqa: E402
    import s_dock       # noqa: E402
    import s_fighter    # noqa: E402  (pir-bot job 6)
    import sailing      # noqa: E402
    la, R = H.la, H.render
    T0 = time.time()
    st = {}
    stamps = {}
    info = {'foe': None, 'shots': 0, 'hitcall': 0, 'kills': 0, 'deckSeen': 0, 'board': None, 'popups': [],
            'gold0': None, 'gold1': None, 'chest0': None, 'chest1': None}
    left = lambda: SECS - (time.time() - T0)      # noqa: E731

    def stage(what, **kw):
        stamps[what] = round(time.time() - T0)
        s_lanes.stage(H, 'flagship', what, t=stamps[what], **kw)

    H.ev('FLAGSHIP-START', frm=FROM, secs=SECS, hunt=HUNT_SECS, deck=DECK_SECS, closeR=CLOSE_R, shots=SHOTS,
         hitcall=HITCALL, needChest=NEED_CHEST, gold=s_lanes.gold(H), here=H.area(), gs=la.getGameState())
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    if not ships:
        H.ev('FAIL', why='the pirate owns no ship (Chapter 2 c2.9visitDarby gives the first one)'); return
    if not (yield from s_lanes.onIsland(H, 'flagship', FROM)):
        H.ev('FAIL', why='could not get to %s' % FROM, area=H.area()); return
    stage('at-island', island=FROM, ships=ships)

    keys = s_dock.Keys(H)
    fighter = None
    cannon = None
    ms = getattr(getattr(la, 'guiMgr', None), 'messageStack', None)
    origLoot = getattr(ms, 'showLoot', None) if ms is not None else None
    if origLoot is not None:
        def showLoot(*a, **k):
            info['popups'].append({'items': len(a[0]) if a and hasattr(a[0], '__len__') else None,
                                   'gold': k.get('gold', a[1] if len(a) > 1 else 0)})
            H.ev('LOOT-POPUP', n=len(info['popups']), gold=info['popups'][-1]['gold'],
                 items=info['popups'][-1]['items'])
            return origLoot(*a, **k)
        ms.showLoot = showLoot
    origEv = H.ev
    try:
        # ---- 1. hunt: the story's own sea fight, stopped at the cripple (hp 0)
        got, kw0 = {}, {}

        def ev(kind, **kw):
            got[kind] = got.get(kind, 0) + 1
            if kind in ('SHIP-TARGET', 'FOE-SUNK') and 'foe' in kw:
                kw0[kind] = kw['foe']
            r = origEv(kind, **kw)
            for k, what in (('SHIP-HUNT', 'launched'), ('SHIP-TARGET', 'foe-seen'), ('BROADSIDE', 'first-shot'),
                            ('RAM', 'first-shot')):
                if kind == k and what not in stamps:
                    stage(what, **({'foe': kw.get('foe')} if 'foe' in kw else {}))
            return r
        H.ev = ev
        g = s_shipquest.hunt(H, None, FlagshipOnly(), min(HUNT_SECS, left()))
        why = None
        try:
            while True:
                try:
                    y = next(g)
                except StopIteration as e:
                    why = e.value
                    break
                if got.get('FOE-SUNK'):
                    why = 'foe-down'
                    break
                yield y
        finally:
            g.close()
            H.ev = origEv
            for k in STEER_KEYS:
                messenger.send(k + '-up')
        foeId = kw0.get('FOE-SUNK') or kw0.get('SHIP-TARGET')
        info['foe'] = foeId
        if why != 'foe-down':
            msg = {'launch-failed': 'the ship did not launch (a SAIL-FAIL line says why)',
                   'our-ship-sunk': 'our ship sank before the flagship was crippled'}.get(why)
            if msg is None and not got.get('SHIP-TARGET'):
                msg = 'no flagship came in sight in %d s (is 0122 flagship-spawn-near set, pop-max >= 1?)' % HUNT_SECS
            if msg is None:
                msg = 'fought a flagship but did not cripple it in %d s (%s; 0122 flagship-hp-scale?)' % (HUNT_SECS, why)
            st['fail'] = msg
            return

        # ---- 2. crippled? then close in, put it on the beam, drop sail, leave the wheel
        ship = sailing.onShip(H) and la.getParentObj()
        sid = getattr(ship, 'doId', None)

        def foeObj():
            return H.cr.doId2do.get(foeId)
        t = time.time()
        while time.time() - t < 12:
            foe = foeObj()
            if foe is None or gsOf(foe) in CRIPPLED:
                break
            yield 0.5
        foe = foeObj()
        fgs = gsOf(foe) if foe else None
        if foe is None or fgs not in CRIPPLED:
            st['fail'] = 'the flagship %s %s instead of being crippled (0135 not live?)' % (
                foeId, 'is gone (sank)' if foe is None else 'is in state %s' % fgs)
            return
        st['crippled'] = True
        stage('crippled', foe=foeId, foeGs=fgs, boardable=getattr(ship, 'boardableShipId', None),
              foeClass=getattr(foe, 'shipClass', None), foeName=getattr(foe, 'name', ''))
        t = time.time()
        while time.time() - t < min(90, left()) and la.getGameState() == 'ShipPilot':
            if foeObj() is None:
                st['fail'] = 'the crippled flagship sank before we got alongside (crippled clock?)'; return
            fp = foe.getPos(R)
            d = (fp - ship.getPos(R)).length()
            brg = s_shipquest.bearing(H, ship, fp)
            if d > CLOSE_R:
                keys.steer(ship, fp)
            elif onBeam(brg):
                break
            else:
                s_shipquest.turnKeys(keys, brg, math.copysign(90.0, brg or 1.0))
            yield 0.5
        keys.release()
        for _ in range(3):                       # S drops a sail level each tap
            messenger.send('s'); messenger.send('s-up')
            yield 0.4
        p0 = ship.getPos(R)
        yield 1.0
        H.ev('SAIL-DOWN', speed=round((ship.getPos(R) - p0).length()), dist=round((foe.getPos(R) - ship.getPos(R)).length()),
             brg=round(s_shipquest.bearing(H, ship, foe.getPos(R))))
        wheel = wheelOf(H, sid)
        if la.getGameState() == 'ShipPilot' and wheel is not None:
            wheel.requestExit()
        t = time.time()
        while time.time() - t < 10 and la.getGameState() == 'ShipPilot':
            yield 0.5
        if la.getGameState() == 'ShipPilot':
            st['fail'] = 'could not leave the wheel (still ShipPilot)'; return
        stage('alongside', dist=round((foe.getPos(R) - ship.getPos(R)).length()), gs=la.getGameState())

        # ---- 3. the cannon on the flagship's side, most nearly abeam of it
        fl = ship.getRelativePoint(R, foe.getPos(R))
        rows = []
        for c in cannonsOf(H, sid):
            cp = ship.getRelativePoint(R, cannonPos(c))
            rows.append((c.doId, cp[0], cp[1]))
        pick = pickCannon(rows, fl[0], fl[1])
        if not pick:
            st['fail'] = 'no cannon on the side facing the flagship (cannons %s, flagship at x %.0f)' % (rows, fl[0]); return
        cannon = H.cr.doId2do.get(pick[0][1])
        ok = yield from H.walk_to(lambda: cannonPos(cannon), arrive=4.0, timeout=30, tag='to-cannon')
        if not ok:
            H.ev('SETUP-NEAR', what='cannon %d' % cannon.doId, why='walk to it failed: placed beside it')
            s_dock.near(H, cannon, 4)
            yield 1
        cannon.requestInteraction(la.doId)
        t = time.time()
        while time.time() - t < 10 and getattr(la, 'cannon', None) is not cannon:
            yield 0.5
        if getattr(la, 'cannon', None) is not cannon:
            st['fail'] = 'cannon %d did not take him (gs %s)' % (cannon.doId, la.getGameState()); return
        stage('at-cannon', cannon=cannon.doId, offBeam=round(pick[0][0]), ammo=cannon.getAmmoSkillId())
        try:
            cannon.selectAmmo(GRAPPLE)
        except Exception as e:
            H.ev('act', step='flagship', a='selectAmmo failed: %r' % (e,))
        if cannon.getAmmoSkillId() != GRAPPLE:
            cannon.setAmmoSkillId(GRAPPLE)
        yield 0.5

        # ---- 4. grapples: aim at its targets the way the mouse does, fire, watch for the tow
        sent = []
        if 'sendRequestProjectileSkill' not in cannon.__dict__:
            origSend = cannon.sendRequestProjectileSkill

            def send(skillId, ammoSkillId, posHpr, *a, **k):
                sent.append((ammoSkillId, [round(v, 1) for v in posHpr]))
                return origSend(skillId, ammoSkillId, posHpr, *a, **k)
            cannon.sendRequestProjectileSkill = send

        def towed():
            f = foeObj()
            return f is not None and gsOf(f) in ('GrappleLerping', 'InPosition')
        n = 0
        while n < SHOTS and not towed() and left() > 60:
            f = foeObj()
            if f is None:
                st['fail'] = 'the flagship sank while we fired grapples'; return
            tg = targetsOf(f)
            if not tg:
                H.ev('act', step='flagship', a='no grapple targets on the flagship yet (client builds them when crippled)')
                yield 1
                n += 0.5
                continue
            mz = cannon.prop.cannonExitPoint.getPos(R)
            tp, idx, name = min(tg, key=lambda r: (r[0] - mz).length())
            hr, p = aim(mz, tp)
            if p is None:
                H.ev('GRAPPLE-SHOT', n=int(n) + 1, out='out-of-range', dist=round((tp - mz).length()), target=name)
                yield 2
                n += 1
                continue
            for _ in range(3):              # hold the aim a few frames so the camera's own task keeps it
                rel, clamped = setAim(cannon, hr, p)
                yield 0.1
            if cannon.volley <= 0 or (la.skillDiary.getTimeRemaining(cannon.skillId) or 0) > 0:
                yield 0.5
                continue
            k0 = len(sent)
            cannon.fireCannon()
            yield 0.3
            n += 1
            info['shots'] += 1
            if 'grapple-fired' not in stamps:
                stage('grapple-fired', target=name)
            H.ev('GRAPPLE-SHOT', n=info['shots'], target=name, idx=idx, dist=round((tp - mz).length()),
                 want=[round(hr, 1), round(p, 1)], rel=round(rel, 1), clamped=clamped,
                 sent=sent[k0][1] if len(sent) > k0 else None, ammo=sent[k0][0] if len(sent) > k0 else None)
            t = time.time()
            while time.time() - t < 4 and not towed():
                yield 0.25
        if not towed() and HITCALL and foeObj() is not None:
            f = foeObj()
            tg = targetsOf(f)
            tp, idx, name = tg[0] if tg else (f.getPos(R), 0, '')
            from direct.distributed.ClockDelta import globalClockDelta
            from pirates.battle import WeaponGlobals
            H.ev('GRAPPLE-HITCALL', route='hitcall', target=name, idx=idx, shots=info['shots'],
                 why='no aimed grapple landed: one direct hit report proves the AI side, not the aim')
            info['hitcall'] += 1
            cannon.sendSuggestProjectileSkillResult(cannon.skillId, GRAPPLE, WeaponGlobals.RESULT_HIT, f.doId, [],
                                                    [tp[0], tp[1], tp[2]], [0, 0, 1], [0, 99, idx],
                                                    globalClockDelta.getFrameNetworkTime(bits=32))
            t = time.time()
            while time.time() - t < 6 and not towed():
                yield 0.25
        if not towed():
            st['fail'] = '%s (%d shots%s, flagship %s)' % (WHY['grappled'], info['shots'],
                                                          ', 1 hit report' if info['hitcall'] else '',
                                                          gsOf(foeObj()) if foeObj() else 'gone')
            return
        st['grappled'] = True
        stage('grappled', route='hitcall' if info['hitcall'] else 'aimed', shots=info['shots'], foeGs=gsOf(foeObj()))

        # ---- 5. tow alongside, then Yes on the Board? panel
        t = time.time()
        while time.time() - t < min(90, left()) and foeObj() is not None and gsOf(foeObj()) != 'InPosition':
            yield 0.5
        if foeObj() is None or gsOf(foeObj()) != 'InPosition':
            st['fail'] = '%s (state %s after %d s)' % (WHY['in-position'], gsOf(foeObj()) if foeObj() else 'gone',
                                                       time.time() - t)
            return
        st['in-position'] = True
        foe = foeObj()
        stage('in-position', dist=round((foe.getPos(R) - ship.getPos(R)).length()))
        t = time.time()
        while time.time() - t < 15 and not getattr(ship, 'boardingPanel', None):
            yield 0.5
        if getattr(ship, 'boardingPanel', None):
            info['board'] = 'panel-yes'
            H.ev('BOARD-ASK', route='panel-yes', secs=round(time.time() - t))
            ship._DistributedShip__handleBoardingChoice(True)     # what the panel's Yes button calls
        else:
            info['board'] = 'direct'
            H.ev('BOARD-ASK', route='direct', why='no Board? panel in 15 s', boardable=getattr(ship, 'boardableShipId', None))
            ship.d_requestBoardFlagship(foe.doId)
        stage('boarding', route=info['board'])
        cannon = None if getattr(la, 'cannon', None) is None else cannon

        # ---- 6. land on its deck, fight until it is Defeated
        t = time.time()
        while time.time() - t < 30 and la.getParentObj() is not foe:
            yield 0.5
        if la.getParentObj() is not foe:
            st['fail'] = '%s (parent %s, gs %s, flagship %s)' % (WHY['on-deck'], H.area(), la.getGameState(),
                                                               gsOf(foe))
            return
        st['on-deck'] = True
        yield ('upto', lambda: la.getGameState() in ('LandRoam', 'Battle'), 10, 'standing on the deck')
        me = la.getPos(R)
        safe = (me[0], me[1], me[2])
        info['gold0'] = s_lanes.gold(H)
        info['chest0'] = list(getattr(ship, 'cargo', []) or []).count(SKCHEST)
        stage('on-deck', foeGs=gsOf(foe), gold=info['gold0'], chests=info['chest0'])
        seen, done = set(), set()
        t = time.time()
        last = None
        while time.time() - t < min(DECK_SECS, left() - 20):
            f = foeObj()
            fgs = gsOf(f) if f else None
            if f is None or fgs not in ('Boarded',):
                break
            if knockedOut(la):
                st['fail'] = 'knocked out on the deck (%d kills; flagship-deck-hp-scale?)' % info['kills']; return
            fp = f.getPos(R)
            rows = deckRows(s_fighter.foeRows(H), (fp[0], fp[1]))
            for row in rows:
                if row[0] not in seen:
                    seen.add(row[0])
                    info['deckSeen'] += 1
                    o = H.cr.doId2do.get(row[0])
                    H.ev('DECK-FOE', foe=row[0], name=getattr(o, 'name', ''), lvl=row[3], hp=row[2],
                         dist=round(row[1]), n=info['deckSeen'])
                    if info['deckSeen'] == 1:
                        stage('deck-foe', foe=row[0])
            if fighter is not None:
                r = fighter.step()
                if r != last:
                    H.ev('act', step='flagship', a='deck %s %d' % (r, fighter.foe.doId), hp=getattr(la, 'hp', None))
                    last = r
                if r in ('kill', 'lost', 'stuck'):
                    if r == 'kill':
                        info['kills'] += 1
                        H.ev('DECK-KILL', foe=fighter.foe.doId, n=info['kills'], hits=fighter.hits,
                             skills=fighter.skills)
                        stage('deck-kill', n=info['kills'])
                    done.add(fighter.foe.doId)
                    fighter.close()
                    fighter = None
                    H.walk_cancel()
            rows = [row for row in rows if row[0] not in done]
            if fighter is None and rows:
                o = H.cr.doId2do.get(rows[0][0])
                if o is not None:
                    fighter = s_fighter.Fighter(H, o, safe)
            yield 0.25
        if fighter is not None:
            fighter.close()
            fighter = None
        H.walk_cancel()
        f = foeObj()
        fgs = gsOf(f) if f else None
        if fgs not in ('Defeated', 'Sinking', 'Sunk') and not (f is None and info['kills']):
            st['fail'] = '%s (state %s, %d deck enemies seen, %d beaten in %d s)' % (
                WHY['defeated'], fgs, info['deckSeen'], info['kills'], time.time() - t)
            return
        st['defeated'] = True
        stage('defeated', foeGs=fgs, kills=info['kills'], seen=info['deckSeen'])

        # ---- 7. swing back, paid, chest in the hold
        t = time.time()
        while time.time() - t < min(45, left()) and not sailing.onShip(H):
            yield 0.5
        if not sailing.onShip(H):
            st['fail'] = '%s (parent %s, gs %s)' % (WHY['swung-back'], H.area(), la.getGameState()); return
        st['swung-back'] = True
        stage('swung-back', secs=round(time.time() - t))
        t = time.time()
        while time.time() - t < min(25, left()):
            info['gold1'] = s_lanes.gold(H)
            info['chest1'] = list(getattr(ship, 'cargo', []) or []).count(SKCHEST)
            if (info['gold1'] > info['gold0'] or info['popups']) and (info['chest1'] > info['chest0'] or not NEED_CHEST):
                break
            yield 1
        st['paid'] = info['gold1'] > info['gold0'] or bool(info['popups'])
        st['chest'] = info['chest1'] > info['chest0']
        stage('loot', gold=info['gold1'] - info['gold0'], popups=len(info['popups']), chests=info['chest1'] - info['chest0'],
              cargo=list(getattr(ship, 'cargo', []) or []))
    finally:
        H.ev = origEv
        keys.release()
        if fighter is not None:
            fighter.close()
        try:
            H.walk_cancel()
        except Exception:
            pass
        if cannon is not None:
            cannon.__dict__.pop('sendRequestProjectileSkill', None)
            if getattr(la, 'cannon', None) is cannon:
                try:
                    cannon.requestExit()
                except Exception:
                    pass
        if origLoot is not None:
            ms.__dict__.pop('showLoot', None)
            if getattr(ms, 'showLoot', None) is not origLoot and 'showLoot' not in type(ms).__dict__:
                ms.showLoot = origLoot
        res, what = verdict(st)
        H.ev('FLAGSHIP-END', result=res, stages={k: bool(st.get(k)) for k in STAGES}, chest=bool(st.get('chest')),
             t=stamps, foe=info['foe'], shots=info['shots'], hitcall=info['hitcall'], board=info['board'],
             deckSeen=info['deckSeen'], kills=info['kills'], popups=len(info['popups']),
             gold=(info['gold0'], info['gold1']), chests=(info['chest0'], info['chest1']),
             secs=round(time.time() - T0), gs=la.getGameState(), area=H.area())
        if res == 'PASS':
            H.ev('PASS', what=what + (' (grapple by hit report)' if info['hitcall'] else ''),
                 board=info['board'], kills=info['kills'], secs=round(time.time() - T0))
        else:
            H.ev('FAIL', why=st.get('fail') or WHY.get(what, what), stage=what, secs=round(time.time() - T0))
