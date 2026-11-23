"""LIVE CHECK (pirates-live lane, 11-20): prove a batch works in the real game before the boys are told to try it.
One item per run (env LIVE_ITEM), on a test pirate only (claude2 / 100000004 unless BOT_AVID says otherwise; never
Host's 100000170, never the boys' 100000656 / 100000665).

Items:
  tia      wd.1visitTia: tunnel to the swamp, talk to Tia, quest done, the wdr doll ladder starts (s_tia_cuba)
  tpt      tpt.1visitTia: the same walk for the teleport-totem ladder's first step (21001 in history)
  iron     dd1.recoveriron turned in (skipQuest = the full completion path): no kick, gold paid, dd1.recovercopper
  crate    sd2.findShipLog (Port Royal crates, very rare): a search that finds nothing still plays the search bar
  carver   c3r2r1.11stealList: search Carver's desk in Tortuga, the quest finishes and pays (3019 in history)
  grenade  throw a grenade: the server's landing result reaches the game (setProjectileSkillResult)
  kings    knocked out on Kingshead: wakes in a jail cell, still connected
  howto    the quest SpeedChat "how to" line (msgType 2) goes out as a quest line, the game stays up
  relog    back to pick-a-pirate with enemy ships in view, then back in: the game stays up
  ships    0397: a pirate with two ships sees both in the dock rowboat's list (claude1)
  ship1    0408: a one-ship pirate logs back in, then out again at once while his ship loads, and back: still his ship
  upgrade  boats-0001 (0413, v479): sail, step off, back to town, shipwright Upgrade: a Yes/No or a why-not line

Lines: LIVE-START, LIVE-STEP, LIVE-SHOT, KICKED, the sub-script's own lines (its PASS / FAIL renamed LIVE-PASS /
LIVE-FAIL), then one PASS or FAIL for the item. Field values never hold the word in capitals (run_walk's strike
check looks for it in the events file)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))

ITEM = os.environ.get('LIVE_ITEM', 'tia')
SHOTS = os.environ.get('LIVE_SHOTS', r'C:\PiratesBots\out\live')
NEVER = (100000170, 100000656, 100000665)
KINGSHEAD = '1159933206.48sdnaik'
TORTUGA = '1156207188.95dzlu'
PORT_ROYAL = '1150922126.8dzlu'
GRENADE_WEAPON, GRENADE_THROW, GRENADE_AMMO = 10115, 12500, 14100
OVERALL_REP = 13700

R = {}        # the walker's own ev (PASS / FAIL count once per run)


def verdict(ok, what, **kw):
    R['ev']('PASS' if ok else 'FAIL', item=ITEM, what=what, **kw)


def wrapEv(H):
    """Sub-scripts (s_tia_cuba) end with their own PASS / FAIL: keep them as LIVE-PASS / LIVE-FAIL lines, so the
    item's verdict is this script's."""
    R['ev'] = H.ev
    got = R.setdefault('sub', [])

    def ev(name, /, **kw):
        if name in ('PASS', 'FAIL'):
            got.append((name, kw))
            name = 'LIVE-' + name
        R['ev'](name, **kw)
        if name == 'talk':
            shot(H, R.get('talkShot', 'tia_talk'), 2.0)
    H.ev = ev


def shot(H, name, delay=0.0):
    from panda3d.core import Filename
    p = os.path.join(SHOTS, name + '.png')

    def take(task=None):
        try:
            ok = H.B.win.saveScreenshot(Filename.fromOsSpecific(p))
        except Exception as e:
            ok = 'err %r' % e
        H.ev('LIVE-SHOT', name=name, path=p, ok=ok, area=H.area(), gs=H.la.getGameState())
        return None if task is None else task.done
    if delay:
        H.B.taskMgr.doMethodLater(delay, take, 'live-shot-' + name)
    else:
        take()


def hookKick(H):
    from panda3d.core import DatagramIterator
    cr = H.cr
    orig = cr.handleGoGetLost

    def ggl(di):
        code = None
        try:
            code = DatagramIterator(di.getDatagram(), di.getCurrentIndex()).getUint16()
        except Exception:
            pass
        R['kicked'] = code
        H.ev('KICKED', code=code)
        return orig(di)
    cr.handleGoGetLost = ggl


def gold(H):
    try:
        return H.la.getInventory().getGoldInPocket()
    except Exception as e:
        return 'err %r' % e


def connected(H):
    try:
        return 'kicked' not in R and H.cr.isConnected() and H.B.localAvatar is not None
    except Exception:
        return False


def give(H, qid):
    if H.has(qid):
        return
    H.mw('giveQuest %s' % qid)
    yield ('until', lambda: H.has(qid), 20, 'give ' + qid)


def tp(H, uid, label):
    la = H.la
    if H.area() and H.area()[1] == uid:
        return
    H.mw('areaTeleport %s' % uid)
    yield ('until', lambda: H.area() is not None and H.area()[1] == uid and la.getGameState() == 'LandRoam', 120,
           'tp ' + label)
    yield 5


# ---------------------------------------------------------------- items
def item_tia(H, qid, qint, shotName):
    """s_tia_cuba's own walk and checks; this adds the history check and the talk picture."""
    import builtins
    # 11-21 02:22: on a pirate already past the visit (its next quests held) a re-given visit can never finish
    nxt = 'wdr' if qid == 'wd.1visitTia' else 'tptr'
    if qint in H.hist() and any(q.startswith(nxt) for q in H.qids()):
        if H.has(qid):
            H.mw('dropQuest %s' % qid)
            yield 2
        return verdict(False, 'cannot recheck on this pirate: %s is done and its next quests (%s*) are held, so a '
                       're-given visit never finishes; run it on a pirate before the visit' % (qid, nxt), quests=H.qids())
    os.environ['TIA_QID'] = qid
    R['talkShot'] = shotName
    path = os.path.join(os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])), 's_tia_cuba.py')
    g = {'__file__': path, '__name__': 's_tia_cuba_live'}
    exec(compile(open(path).read(), path, 'exec'), g)
    del R['sub'][:]
    yield from g['run'](H)
    sub = R['sub'][-1] if R['sub'] else ('none', {})
    hist = H.hist()
    res = dict(sub='ok' if sub[0] == 'PASS' else 'bad', subWhy=sub[1].get('why') or sub[1].get('what'), held=H.has(qid), inHist=qint in hist,
               quests=H.qids(), kicked=R.get('kicked'))
    if sub[0] == 'PASS' and not H.has(qid) and qint in hist:
        if qid == 'wd.1visitTia':
            return verdict(True, 'talked to Tia in the swamp: the visit finished and the voodoo doll quests started',
                           **res)
        return verdict(True, 'talked to Tia: %s finished and is in the history' % qid, **res)
    verdict(False, 'the visit to Tia did not finish', **res)


def pastIt(H, qid, qint):
    """Generator (11-21 02:29): a quest this pirate already finished can't be turned in again (the server keeps the
    re-given copy). Drop a stray copy and FAIL with why; True = the check can't run on this pirate."""
    if qint not in H.hist():
        return False
    if H.has(qid):
        H.mw('dropQuest %s' % qid)
        yield 2
    verdict(False, 'cannot recheck on this pirate: %s is already in his history, so a re-given copy never turns in; '
            'run it on a pirate before that quest' % qid, quests=H.qids())
    return True


def item_dropvisits(H):
    """11-21 games: LIVE-tia/tpt/iron re-gave quests claude2 had already finished (places' doll and story runs took
    him past them); drop the stray copies so those chains see only their own quests."""
    qs = ['wd.1visitTia', 'tpt.1visitTia', 'dd1.recoveriron']
    before = H.qids()
    for q in qs:
        if H.has(q):
            H.mw('dropQuest %s' % q)
            yield ('until', lambda q=q: not H.has(q), 15, 'drop ' + q)
    left = [q for q in qs if H.has(q)]
    verdict(not left, 'the stray visit quests are gone' if not left else 'still held: %s' % left, before=before,
            after=H.qids())


def item_iron(H):
    qid, nxt = 'dd1.recoveriron', 'dd1.recovercopper'
    from pirates.quest import QuestDB
    qint = QuestDB.QuestDict[qid].getQuestInt()
    if (yield from pastIt(H, qid, qint)):
        return
    yield from give(H, qid)
    yield 3
    g0, h0 = gold(H), set(H.hist())
    H.ev('LIVE-STEP', step='iron held, turning it in', gold=g0, quests=H.qids())
    H.mw('skipQuest %s' % qid)
    yield ('until', lambda: (not H.has(qid) and H.has(nxt)) or 'kicked' in R, 30, 'iron turned in')
    yield 5
    g1 = gold(H)
    res = dict(gold0=g0, gold1=g1, held=H.has(qid), nextHeld=H.has(nxt), inHist=qint in H.hist(),
               newHist=sorted(set(H.hist()) - h0), quests=H.qids(), kicked=R.get('kicked'), up=connected(H))
    ok = 'kicked' not in R and not H.has(qid) and H.has(nxt) and qint in H.hist() and connected(H) \
        and isinstance(g0, int) and isinstance(g1, int) and g1 > g0
    verdict(ok, "Darby's iron quest turned in: reward paid, the copper quest given, no kick" if ok
            else "Darby's iron quest turn-in went wrong", **res)


def hookContainers(H, log):
    from pirates.interact import DistributedSearchableContainer as M
    C = M.DistributedSearchableContainer
    for name in ('startSearching', 'stopSearching', 'rejectInteraction'):
        orig = getattr(C, name)

        def w(self, *a, _o=orig, _n=name):
            log.append((_n, self.doId, a))
            H.ev('LIVE-CONTAINER', call=_n, container=self.doId, uid=getattr(self, 'uniqueId', None), args=a,
                 quests=H.quests())
            return _o(self, *a)
        setattr(C, name, w)
    gm = H.la.guiMgr
    ow = gm.createWarning

    def warn(text, *a, **k):
        log.append(('warning', None, (text,)))
        H.ev('LIVE-WARNING', text=text)
        return ow(text, *a, **k)
    gm.createWarning = warn


def walkGo(H, st):
    """Do the walk container() asked for (it leaves it in st['go'] for run(); these items have no run() loop)."""
    from s_story import go
    g = st.pop('go', None)
    if g is not None:
        obj, arrive, face, ref, tag = g
        yield from go(H, obj, arrive, face, ref, tag)


def item_crate(H):
    """Search Port Royal's crates for the very-rare ship's log until one search finds nothing (a miss)."""
    from s_story import container
    qid = 'sd2.findShipLog'
    log = []
    hookContainers(H, log)
    yield from give(H, qid)
    yield from tp(H, PORT_ROYAL, 'Port Royal')
    st = {}
    t0 = time.time()
    misses, accepts, denies = 0, 0, 0
    while time.time() - t0 < 360 and 'kicked' not in R and H.has(qid):
        q = next(q for q in H.la.getQuests() if q.getQuestId() == qid)
        r = container(H, q, q.questDNA.getTasks()[0], st)
        if isinstance(r, str) and r.startswith('search '):
            n = len(log)
            yield ('upto', lambda: any(e[0] in ('stopSearching', 'rejectInteraction') for e in log[n:]), 12)
            new = [e[0] for e in log[n:]]
            if 'startSearching' in new:
                accepts += 1
                if 'shotDone' not in st:
                    st['shotDone'] = 1
                    shot(H, 'crate_search_bar')
            if 'rejectInteraction' in new:
                denies += 1
            yield ('upto', lambda: any(e[0] == 'stopSearching' for e in log[n:]), 10)
            yield 1
            if H.has(qid) and 'startSearching' in [e[0] for e in log[n:]]:
                misses += 1
                H.ev('LIVE-STEP', step='a search found nothing and still played the search bar', n=misses)
                if misses >= 1:
                    break
        else:
            H.ev('LIVE-STEP', step='crate', r=str(r))
            if isinstance(r, tuple):
                break
            yield from walkGo(H, st)
        yield 1
    warns = [e[2][0] for e in log if e[0] == 'warning']
    res = dict(misses=misses, accepts=accepts, denies=denies, warnings=warns[-5:], held=H.has(qid),
               kicked=R.get('kicked'))
    if H.has(qid):
        H.mw('dropQuest %s' % qid)
        yield 2
    ok = misses >= 1 and denies == 0 and 'kicked' not in R
    verdict(ok, 'a crate search that found nothing still played the search bar' if ok
            else 'no crate miss with a search bar seen', **res)


CARVER_DESK = '1186512896.0dxschafe'   # tortuga_building_int_14, models/props/desk_gov
PIRATE_RADIUS = 1.4                    # LocalPirate walk collision sphere


def item_carver(H):
    """Steal Carver's list from his desk the way a kid does: walk up to the desk, and search only where a kid's Search
    prompt would show, i.e. his pirate (radius 1.4) touching the desk's prompt sphere (radius = the sphereScale the AI
    sends). The solid desk stops a pirate about 4.95 ft from its centre (11-20 20:03 run), so two stuck walks next to
    it settle it: FAIL at once with both numbers when the prompt cannot show (sphereScale 1.0 before carver-0001),
    never walking on into the 480 s watchdog."""
    from s_story import container, hdist, near
    from pirates.quest import QuestDB
    qid = 'c3r2r1.11stealList'
    qint = QuestDB.QuestDict[qid].getQuestInt()
    log = []
    if (yield from pastIt(H, qid, qint)):
        return
    hookContainers(H, log)
    yield from give(H, qid)
    yield from tp(H, TORTUGA, 'Tortuga')
    inv = H.la.getInventory()
    rep0 = inv.getAccumulator(OVERALL_REP) if inv else None
    st = {}
    t0 = time.time()
    stuck, closest, reach, searched, why = 0, None, None, 0, None
    while time.time() - t0 < 240 and 'kicked' not in R and H.has(qid):
        desk = next((o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedSearchableContainer'
                     and getattr(o, 'uniqueId', None) == CARVER_DESK), None)
        if desk is None:
            # not inside Carver's room yet: container() walks to the building's door and through it
            q = next(q for q in H.la.getQuests() if q.getQuestId() == qid)
            r = container(H, q, q.questDNA.getTasks()[0], st)
            H.ev('LIVE-STEP', step='carver', r=str(r))
            if isinstance(r, tuple):
                why = 'route %s' % (r,)
                break
            yield from walkGo(H, st)
            yield 1
            continue
        reach = round(float(desk.getSphereScale() or 0) + PIRATE_RADIUS, 2)
        d = round(hdist(H, desk), 2)
        closest = d if closest is None else min(closest, d)
        H.ev('LIVE-STEP', step='carver desk', dist=d, reach=reach, sphereScale=desk.getSphereScale(), stuck=stuck)
        if d <= reach:
            if searched:
                yield ('upto', lambda: not H.has(qid), 10)
                why = 'searched, quest still held'
                break
            searched = 1
            n = len(log)
            H.ev('SEARCH', container=desk.doId, uid=CARVER_DESK, dist=d, reach=reach)
            desk.requestInteraction(H.la.doId)
            yield ('upto', lambda: any(e[0] in ('startSearching', 'rejectInteraction') for e in log[n:]), 5)
            if any(e[0] == 'startSearching' for e in log[n:]):
                shot(H, 'carver_desk_search', 1.5)
            yield ('upto', lambda: not H.has(qid), 15)
            continue
        if stuck >= 2:
            why = ("kids can't search it: the desk stops a pirate %.2f ft from its centre and the Search prompt only "
                   "reaches %.2f ft (sphereScale %s)" % (closest, reach, desk.getSphereScale()))
            break
        before = d
        if not near(H, desk, reach - 0.3, st, tag='container'):
            yield from walkGo(H, st)
        if hdist(H, desk) > reach and hdist(H, desk) > before - 0.5:
            stuck += 1
        yield 1
    yield ('upto', lambda: qint in H.hist(), 15)
    yield 3
    inv = H.la.getInventory()
    rep1 = inv.getAccumulator(OVERALL_REP) if inv else None
    res = dict(held=H.has(qid), inHist=qint in H.hist(), rep0=rep0, rep1=rep1, kicked=R.get('kicked'),
               closest=closest, reach=reach, searched=searched, why=why, secs=round(time.time() - t0, 1),
               quests=H.qids(), area=H.area())
    ok = not H.has(qid) and qint in H.hist() and 'kicked' not in R and rep0 is not None and rep1 > rep0
    verdict(ok, "Carver's list stolen from the desk: the quest finished and paid" if ok
            else "Carver's list quest did not finish and pay" + (': ' + why if why else ''), **res)


def item_grenade(H):
    from pirates.battle import WeaponBase as WB
    la = H.la
    seen = {'suggest': [], 'result': []}
    W = WB.WeaponBase
    oSug, oRes = W.sendSuggestProjectileSkillResult, W.setProjectileSkillResult

    def sug(self, *a, **k):
        seen['suggest'].append(time.time())
        H.ev('LIVE-GRENADE', step='landed: the game sent the landing to the server', args=a[:3])
        return oSug(self, *a, **k)

    def res_(self, *a, **k):
        seen['result'].append(time.time())
        H.ev('LIVE-GRENADE', step="the server's landing result arrived", args=a[:3])
        return oRes(self, *a, **k)
    W.sendSuggestProjectileSkillResult, W.setProjectileSkillResult = sug, res_
    inv = la.getInventory()
    if not inv.getStackQuantity(GRENADE_WEAPON) or not inv.getStackQuantity(GRENADE_AMMO):
        H.mw('maxWeapons')
        yield ('until', lambda: inv.getStackQuantity(GRENADE_WEAPON) > 0, 20, 'grenade given')
        yield 3
    H.ev('LIVE-STEP', step='grenade stock', weapon=inv.getStackQuantity(GRENADE_WEAPON),
         ammo=inv.getStackQuantity(GRENADE_AMMO), area=H.area())
    # Draw it the way a kid does (number key or GRENADE slot): the combat tray's toggleWeapon sets tray.weaponId,
    # which trySkill needs. la.toggleWeapon alone draws the weapon but leaves tray.weaponId at 0, so every throw
    # was refused before it reached the game.
    # 11-20 20:13: the draw worked, then the grenade was put away again within 2.5 s and every throw was refused
    # (trySkill needs the Battle state). Whatever puts it away is named by `by` in the 'put away' and 'game state'
    # lines below (a short call stack), so the next run says which game code did it.
    import traceback
    from direct.showbase.DirectObject import DirectObject
    from pirates.battle import WeaponGlobals as WG
    tray = la.guiMgr.combatTray

    def where():
        return ['%s:%s %s' % (f.filename.replace('\\', '/').split('/')[-1], f.lineno, f.name)
                for f in traceback.extract_stack()[-10:-2]]
    oLSet, oBState = la.l_setCurrentWeapon, la.b_setGameState

    def lSet(wid, drawn, *a, **k):
        if la.isWeaponDrawn and not drawn:
            H.ev('LIVE-GRENADE', step='put away', weapon=wid, gs=la.getGameState(), by=where())
        return oLSet(wid, drawn, *a, **k)

    def bState(state, *a, **k):
        if state != la.getGameState():
            H.ev('LIVE-GRENADE', step='game state change', frm=la.getGameState(), to=state, by=where())
        return oBState(state, *a, **k)
    la.l_setCurrentWeapon, la.b_setGameState = lSet, bState
    ears = DirectObject()
    for e in ('escape', 'weaponSheathed', 'requestGearExit', 'localAvatarEnterWater'):
        ears.accept(e, lambda *a, e=e: H.ev('LIVE-GRENADE', step='heard ' + e, gs=la.getGameState(),
                                            drawn=la.isWeaponDrawn))

    def gates():
        g = dict(gs=la.getGameState(), drawn=la.isWeaponDrawn, cur=la.currentWeaponId, trayWeapon=tray.weaponId,
                 accepting=tray.isAcceptingInput, hasWeapon=bool(la.currentWeapon), queue=tray.weaponQueue,
                 busy=[tray.isDrawingWeapon, tray.isUsingSkill, tray.isCharging], rep=tray.rep, hp=la.hp,
                 mode=tray.weaponMode, ammoSkill=getattr(tray, 'ammoSkillId', None),
                 action=(tray.skillMapping.get('action') or [None])[0], volley=getattr(tray, 'volley', None),
                 ammo=inv.getStackQuantity(GRENADE_AMMO), ignoreKeys=la.guiMgr.ignoreAllKeys)
        for key, f in (('maxVolley', lambda: WG.getWeaponVolley(la.currentWeaponId)),
                       ('skillRep', lambda: WG.getSkillReputationCategoryId(GRENADE_THROW)),
                       ('recharge', lambda: la.skillDiary.getTimeRemaining(GRENADE_THROW)),
                       ('stunned', lambda: WG.C_STUN in la.getSkillEffects()), ('airborne', la.isAirborne),
                       ('popup', lambda: getattr(getattr(base, 'tPanel', None), 'mode', None))):
            try:
                g[key] = f()
            except Exception as e:
                g[key] = 'err %s' % e
        return g

    def ready():
        return (la.getGameState() == 'Battle' and la.isWeaponDrawn and la.currentWeaponId == GRENADE_WEAPON
                and tray.weaponId == GRENADE_WEAPON and not tray.isDrawingWeapon)

    def draw(why):
        # The kid's grenade key: CombatTray.toggleWeapon (F-key hotkey). If the grenade is already out but the game
        # is not in Battle, the key would put it away (LocalPirate.toggleWeapon's last branch): ask for Battle only.
        H.ev('LIVE-STEP', step='grenade draw (%s)' % why, **gates())
        if la.isWeaponDrawn and la.currentWeaponId == GRENADE_WEAPON:
            if tray.weaponId != GRENADE_WEAPON:
                tray.weaponId, tray.rep = GRENADE_WEAPON, WG.getRepId(GRENADE_WEAPON)
            if la.getGameState() != 'Battle':
                la.b_setGameState('Battle')
        else:
            tray.toggleWeapon(GRENADE_WEAPON)
    try:
        # The tutorial pop-up on his screen (11-20 shot: "Walk towards the light ray... OK"): press its OK.
        tp = getattr(base, 'tPanel', None)
        if tp is not None and not tp.isEmpty() and not tp.isHidden():
            H.ev('LIVE-STEP', step='closing the pop-up with its OK', mode=getattr(tp, 'mode', None))
            yes = getattr(tp, 'yesTutorial', None)
            if yes is not None and yes['command']:
                yes['command'](*(yes['extraArgs'] or []))
            elif getattr(tp, 'closeMessage', None):
                messenger.send(tp.closeMessage)
            yield 1
        if tray.weaponQueue:
            H.ev('LIVE-STEP', step='a weapon switch was queued: cleared', queue=tray.weaponQueue)
            tray.clearQueues()
        throws = 0
        for n in range(4):
            if not ready():
                draw('try %d' % n)
                yield ('upto', ready, 10)
                yield ('upto', lambda: not ready(), 1.5)   # the 20:13 run lost it within 2.5 s: wait to see it stay
                if not ready():
                    H.ev('LIVE-STEP', step='grenade not ready after the draw', **gates())
                    continue
            k = len(seen['result'])
            a0 = inv.getStackQuantity(GRENADE_AMMO)
            # The kid's throw: the left click (mouse1 -> CombatTray.actionDown -> 'action'), then release.
            tray.actionDown()
            yield 0.4
            tray.actionUp()
            yield ('upto', lambda: len(seen['suggest']) > 0 or inv.getStackQuantity(GRENADE_AMMO) < a0, 3)
            how = 'click'
            if not seen['suggest'] and inv.getStackQuantity(GRENADE_AMMO) >= a0:
                g = gates()
                r = tray.trySkill(g['action'] or GRENADE_THROW, g['ammoSkill'] or GRENADE_AMMO)
                how = 'trySkill -> %s' % r
                H.ev('LIVE-STEP', step='the click threw nothing: trySkill', tried=r, **g)
            throws += 1
            H.ev('LIVE-STEP', step='throw', n=n, how=how, ammoBefore=a0, ammo=inv.getStackQuantity(GRENADE_AMMO),
                 gs=la.getGameState(), drawn=la.isWeaponDrawn)
            if throws == 1:
                shot(H, 'grenade_blast', 2.5)
            yield ('upto', lambda: len(seen['result']) > k, 12)
            if len(seen['result']) > k:
                break
            H.ev('LIVE-STEP', step='no blast result for that throw', **gates())
            yield 2
    finally:
        ears.ignoreAll()
        la.__dict__.pop('l_setCurrentWeapon', None)
        la.__dict__.pop('b_setGameState', None)
    lag = None
    if seen['suggest'] and seen['result']:
        lag = round(seen['result'][-1] - seen['suggest'][0], 2)
    res = dict(landings=len(seen['suggest']), results=len(seen['result']), lag=lag, kicked=R.get('kicked'),
               up=connected(H))
    ok = bool(seen['result']) and 'kicked' not in R
    verdict(ok, "a thrown grenade landed and the server's blast result reached the game" if ok
            else 'no blast result from the server after a throw', **res)


def jailed(H):
    a = H.area()
    return (a is not None and a[0] == 'DistributedJailInterior') or getattr(H.la, 'jailCellIndex', 100) < 100


def item_kings(H):
    from s_fighter import foeRows
    la = H.la
    seen = []
    H.B.accept('localAvatar-setJailCellIndex', lambda *a: seen.append(('cell', a)))
    yield from tp(H, KINGSHEAD, 'Kingshead')
    H.ev('LIVE-STEP', step='on Kingshead', area=H.area(), hp=la.hp)
    H.mw('hp 1')
    yield ('upto', lambda: la.hp <= 1, 10)
    H.drawSword()
    yield 2
    # A foe gets 2 min to knock him out, with a progress line every 15 s (the runner calls 240 s with no line a hang).
    # If none does (on 11-20 his game showed no foe at all in 240 s), the server's own knock-out path does it:
    # `hp -1` sets his hp to 0, which is the same setHp -> Death -> jail as a foe's last hit. The jail is what is
    # tested here; `how` in the verdict says which knock-out it was.
    def down():
        return la.hp <= 0 or la.getGameState() in ('Death', 'Dying', 'ThrownInJail')
    t0 = tLog = time.time()
    koT, how, seenMax, near, last = None, None, 0, None, None
    while time.time() - t0 < 120 and 'kicked' not in R:
        if down():
            koT, how = time.time(), 'foe'
            break
        rows = sorted(foeRows(H), key=lambda r: r[1])
        seenMax = max(seenMax, len(rows))
        if rows:
            near = (rows[0][0], round(rows[0][1]), rows[0][3])
            last = H.engage(rows[0][0])
        if time.time() - tLog >= 15:
            tLog = time.time()
            H.ev('LIVE-STEP', step='waiting for a foe', secs=round(tLog - t0), foes=len(rows), nearest=near,
                 engage=last, hp=la.hp, gs=la.getGameState(), la=H.P(la))
        yield 1
    if koT is None and 'kicked' not in R:
        H.ev('LIVE-STEP', step='no foe knocked him out: knock-out by the server instead', foesSeen=seenMax,
             nearest=near)
        H.mw('hp -1')
        yield ('upto', down, 15)
        if down():
            koT, how = time.time(), 'hp -1'
    if koT is None:
        return verdict(False, 'never knocked out on Kingshead', hp=la.hp, gs=la.getGameState(), area=H.area(),
                       foesSeen=seenMax, kicked=R.get('kicked'))
    H.ev('LIVE-STEP', step='knocked out', how=how, hp=la.hp, gs=la.getGameState(), area=H.area(), foesSeen=seenMax)
    yield ('until', lambda: jailed(H) or 'kicked' in R, 90, 'jail cell')
    yield ('upto', lambda: la.getGameState() == 'LandRoam', 30)
    yield 3
    if jailed(H):
        shot(H, 'kingshead_jail_cell')
    yield 20
    res = dict(jailed=jailed(H), area=H.area(), cell=getattr(la, 'jailCellIndex', None), gs=la.getGameState(),
               hp=la.hp, up=connected(H), kicked=R.get('kicked'), cellEvents=len(seen), how=how, foesSeen=seenMax)
    ok = jailed(H) and connected(H)
    verdict(ok, 'knocked out on Kingshead (%s), woke in a jail cell and stayed connected' % how if ok
            else 'after the knock-out on Kingshead he did not reach a jail cell', **res)


def item_howto(H):
    import builtins
    from pirates.quest import QuestDB
    la = H.la
    yield ('until', lambda: la.getGameState() == 'LandRoam', 60, 'LandRoam')
    q = next(iter(la.getQuests()), None)
    if q is None:
        yield from give(H, 'sd2.findShipLog')
        q = next(iter(la.getQuests()), None)
    qint = QuestDB.QuestDict[q.getQuestId()].getQuestInt()
    from otp.chat import ChatAssistant as CA  # noqa: F401
    ca = builtins.base.chatAssistant
    sent = []
    for name in ('sendAvatarSCQuestChat', 'sendAvatarOpenSpeedChat', 'sendAvatarCrewSCQuestChat'):
        if hasattr(ca, name):
            o = getattr(ca, name)

            def w(*a, _o=o, _n=name):
                sent.append(_n)
                H.ev('LIVE-CHAT', call=_n, args=a)
                return _o(*a)
            setattr(ca, name, w)
    entry = None
    for owner in (getattr(builtins.base, 'chatMgr', None), getattr(la, 'chatMgr', None),
                  getattr(getattr(la, 'guiMgr', None), 'chatMgr', None)):
        entry = getattr(owner, 'speedEntry', None)
        if entry is not None:
            break
    if entry is None:
        return verdict(False, 'no SpeedChat entry found on this game', quest=q.getQuestId())
    err = None
    try:
        entry.handleQuestMsg(qint, 0, 2, 0)      # the quest menu's "How do I..." line
    except Exception as e:
        import traceback
        err = traceback.format_exc()[-600:]
    yield 5
    shot(H, 'howto_line')
    res = dict(quest=q.getQuestId(), sent=sent, err=err, up=connected(H), mode=getattr(entry, 'mode', None))
    ok = err is None and 'sendAvatarSCQuestChat' in sent and 'sendAvatarOpenSpeedChat' not in sent and connected(H)
    verdict(ok, 'the quest "How do I..." line went out as a quest line and the game stayed up' if ok
            else 'the quest "How do I..." line did not go out cleanly', **res)


RELOG_SHIPS_BY = 200.0   # s from the item's start to have an enemy ship in view (the relog itself ~60 s; runner 360 s)


def item_relog(H):
    """Back to pick-a-pirate with enemy ships in view, then back in: the case Player2's game crashed on 11-19 18:58
    (NPCShip.disable -> cleanupAggroCollisions at the logout, crash 8 of the crash sweep; every enemy ship the game has
    loaded is torn down then). Kings runs just before this and leaves the bot in the Tortuga jail, where no ship is in
    view (20:19 run: 0 ships, so the case was never tried). So, like a kid: teleport to Port Royal; if no enemy ship
    shows from the town, launch this pirate's ship at the dinghy (enemy ships sail just outside the harbour: BATTLE3
    and BATTLE5 saw them as the ship came out), wait for one, then step off the wheel and log out from the deck and
    back in. Finding a ship is capped at RELOG_SHIPS_BY s, with a LIVE-STEP every 15 s while waiting."""
    import s_relog, s_shipquest
    t0 = time.time()
    la = H.la
    yield ('until', lambda: la.getGameState() == 'LandRoam', 60, 'LandRoam')
    yield from tp(H, PORT_ROYAL, 'Port Royal')
    la = H.la
    where = 'Port Royal town'
    yield ('upto', lambda: H.objs('NPCShip'), 10)
    ships = H.objs('NPCShip')
    H.ev('LIVE-STEP', step='enemy ships in view from Port Royal town', n=len(ships), secs=round(time.time() - t0))
    if not ships and 'kicked' not in R:
        ship = yield from s_shipquest.launchShip(H)
        if ship is None:
            return verdict(False, 'could not launch the ship at Port Royal to sail where enemy ships are',
                           area=H.area(), secs=round(time.time() - t0), kicked=R.get('kicked'))
        where = 'aboard its ship off Port Royal'
        sid = ship.doId
        nudged = False
        while 'kicked' not in R and time.time() - t0 < RELOG_SHIPS_BY:
            ships = H.objs('NPCShip')
            H.ev('LIVE-STEP', step='waiting for an enemy ship in view', n=len(ships), secs=round(time.time() - t0),
                 ship=H.P(ship), gs=la.getGameState())
            if ships:
                break
            if not nudged and la.getGameState() == 'ShipPilot':
                messenger.send('w'); messenger.send('w-up')     # one sail level: out of the harbour
                nudged = True
            yield ('upto', lambda: H.objs('NPCShip'), 15)
        # a kid walks off the wheel and logs out from the deck (the logout waits for LandRoam, which the wheel is not)
        wheel = next((o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedSteeringWheel'
                      and getattr(o, 'shipId', None) == sid), None)
        if la.getGameState() == 'ShipPilot' and wheel is not None:
            wheel.requestExit()
        yield ('upto', lambda: la.getGameState() == 'LandRoam', 10)
        H.ev('LIVE-STEP', step='off the wheel', gs=la.getGameState(), secs=round(time.time() - t0))
    ships = H.objs('NPCShip')
    H.ev('LIVE-STEP', step='enemy ships in view before the logout', where=where, n=len(ships), ships=ships[:6],
         secs=round(time.time() - t0))
    if not ships:
        return verdict(False, 'no enemy ship came into view in %d s (%s), so the logout with enemy ships loaded was '
                       'not tried' % (round(time.time() - t0), where), npcShips=0, area=H.area(), kicked=R.get('kicked'))
    diffs = yield from s_relog.relog(H, 'live')
    res = dict(npcShips=len(ships), where=where, back=diffs is not None, diffs=len(diffs or []), up=connected(H),
               kicked=R.get('kicked'), secs=round(time.time() - t0))
    if diffs is None:
        return verdict(False, 'did not come back from pick-a-pirate', **res)
    verdict(connected(H), 'went back to pick-a-pirate with %d enemy ships in view (%s) and came back, game up'
            % (len(ships), where) if connected(H) else 'came back from pick-a-pirate but the game is not up', **res)


def item_smoke(H):
    """Before the batch: every hook and helper the items use resolves on this game (no quest, no teleport)."""
    import builtins
    la = H.la
    got, bad = [], []

    def chk(name, fn):
        try:
            v = fn()
            (got if v is not None and v is not False else bad).append(name)
        except Exception as e:
            bad.append('%s: %r' % (name, e))
    from pirates.battle import WeaponBase as WB
    from pirates.interact import DistributedSearchableContainer as DSC
    chk('s_story.container', lambda: __import__('s_story').container)
    chk('s_fighter.foeRows', lambda: __import__('s_fighter').foeRows(H) is not None)
    chk('s_relog.relog', lambda: __import__('s_relog').relog)
    chk('s_tia_cuba', lambda: os.path.exists(os.path.join(os.path.dirname(os.path.abspath(
        os.environ['PROOF_SCRIPT'])), 's_tia_cuba.py')))
    chk('WeaponBase hooks', lambda: WB.WeaponBase.sendSuggestProjectileSkillResult and
        WB.WeaponBase.setProjectileSkillResult)
    chk('container hooks', lambda: DSC.DistributedSearchableContainer.startSearching and
        DSC.DistributedSearchableContainer.stopSearching and DSC.DistributedSearchableContainer.rejectInteraction)
    chk('createWarning', lambda: la.guiMgr.createWarning)
    chk('combatTray.trySkill', lambda: la.guiMgr.combatTray.trySkill)
    chk('toggleWeapon', lambda: la.toggleWeapon)
    chk('speedEntry.handleQuestMsg', lambda: la.chatMgr.speedEntry.handleQuestMsg)
    chk('chatAssistant.sendAvatarSCQuestChat', lambda: builtins.base.chatAssistant.sendAvatarSCQuestChat)
    chk('handleGoGetLost', lambda: H.cr.handleGoGetLost)
    chk('inventory', lambda: la.getInventory().getGoldInPocket() is not None and
        la.getInventory().getAccumulator(OVERALL_REP) is not None)
    chk('cr.isConnected', lambda: H.cr.isConnected())
    shot(H, 'smoke')
    yield 3
    ok = not bad and os.path.exists(os.path.join(SHOTS, 'smoke.png'))
    verdict(ok, 'every live-check hook resolves on the real game and the picture saves' if ok
            else 'some live-check hooks do not resolve', resolved=got, missing=bad,
            png=os.path.exists(os.path.join(SHOTS, 'smoke.png')), gold=gold(H), area=H.area())


def item_mini(H):
    """For item 7's launcher: does the game keep running with no picture? 320x240, then minimized, then a teleport to
    Port Royal while minimized. PASS = frames keep coming, the teleport lands and the connection stays."""
    from panda3d.core import WindowProperties
    la = H.la
    wp = WindowProperties()
    wp.setSize(320, 240)
    H.B.win.requestProperties(wp)
    yield 3
    shot(H, 'mini_320')
    yield 2
    wp = WindowProperties()
    wp.setMinimized(True)
    H.B.win.requestProperties(wp)
    yield 3
    f0 = globalClock.getFrameCount()
    mini = H.B.win.getProperties().getMinimized()
    H.ev('LIVE-MINI', minimized=mini, size=(H.B.win.getXSize(), H.B.win.getYSize()), frame=f0)
    there = H.area() and H.area()[1] == '1150922126.8dzlu'
    if there:
        H.mw('areaTeleport 1156207188.95dzlu')     # Tortuga, so the check always includes a teleport
        uid, label = '1156207188.95dzlu', 'tp Tortuga (minimized)'
    else:
        H.mw('areaTeleport 1150922126.8dzlu')
        uid, label = '1150922126.8dzlu', 'tp Port Royal (minimized)'
    yield ('upto', lambda: H.area() is not None and H.area()[1] == uid and la.getGameState() == 'LandRoam', 120)
    landed = H.area() is not None and H.area()[1] == uid and la.getGameState() == 'LandRoam'
    yield 20
    frames = globalClock.getFrameCount() - f0
    ok = bool(mini) and landed and frames > 50 and connected(H)
    verdict(ok, 'a minimized game keeps running: teleport landed, frames kept coming, still connected' if ok
            else 'a minimized game did not keep running normally', minimized=mini, landed=landed, frames=frames,
            connected=connected(H), area=H.area())

def item_ships(H):
    """0397 (batch 3 part, 11-20): a pirate with two ships sees both of them under "Own" in the dock rowboat's list.
    Run on claude1 (100000001, Red Leopard + Riptide Cutter); claude2 owns no ship. Opens the list only, launches nothing."""
    import sailing
    la = H.la
    mine = list(la.getInventory().getShipDoIdList())
    H.ev('LIVE-STEP', what='own ships', ships=mine)
    if len(mine) < 2:
        return verdict(False, 'this test pirate owns %d ship(s); the check needs two' % len(mine), ships=mine)
    yield from tp(H, PORT_ROYAL, 'Port Royal')
    d = yield from sailing.to_dinghy(H, PORT_ROYAL)
    if d is None:
        return verdict(False, 'could not reach a Port Royal rowboat', area=H.area())
    d.requestInteraction(la.doId)
    yield ('until', lambda: la.getGameState() == 'DinghyInteract' and getattr(d, 'shipSelection', None) is not None,
           20, 'rowboat list open')
    p = getattr(d, 'shipSelection', None)

    def own():
        try:
            return [f['shipId'] for f in p.shipFrames.get(p.OWN, [])]
        except Exception:
            return []
    yield ('upto', lambda: p is not None and all(s in own() for s in mine), 30)
    yield 2
    rows = own()
    shot(H, 'ships_two')
    yield 2
    seen = [s for s in mine if s in rows]
    ok = p is not None and len(seen) == len(mine) and connected(H)
    verdict(ok, 'both ships show under Own at the rowboat' if ok else 'a ship is missing from the rowboat list',
            ships=mine, ownRows=rows, seen=seen, connected=connected(H))


def item_ship1(H):
    """0408 with a one-ship pirate: log back in normally, then log out again at once (while his ships still load) and
    back in; his ship is still his at the rowboat and the game stays up. That a ship loads only once is read from the
    server logs after the run (no 'already-active' for it)."""
    import s_relog, sailing
    la = H.la
    mine = list(la.getInventory().getShipDoIdList())
    H.ev('LIVE-STEP', what='own ships', ships=mine)
    if not mine:
        return verdict(False, 'this test pirate owns no ship', ships=mine)
    diffs = yield from s_relog.relog(H, 'ship1')
    if diffs is None:
        return verdict(False, 'the normal re-login did not come back', ships=mine)
    import sys; __main__ = sys.modules.get('pir_walker') or sys.modules['__main__']
    old = H.la
    __main__.NEXT_PICK[0] = old.doId          # straight back out, no settle: the ship loader is still busy
    if not (yield from s_relog.logout(H)):
        __main__.NEXT_PICK[0] = None
        return verdict(False, 'the quick logout never reached pick-a-pirate', ships=mine)
    if not (yield from s_relog.login(H, old)):
        return verdict(False, 'did not come back after the quick logout', ships=mine)
    la = H.la
    yield ('until', lambda: la.getInventory() is not None, 30, 'inventory')
    after = list(la.getInventory().getShipDoIdList())
    H.ev('LIVE-STEP', what='own ships after both re-logins', ships=after)
    yield from tp(H, PORT_ROYAL, 'Port Royal')
    d = yield from sailing.to_dinghy(H, PORT_ROYAL)
    if d is None:
        return verdict(False, 'could not reach a Port Royal rowboat', area=H.area(), ships=after)
    d.requestInteraction(la.doId)
    yield ('until', lambda: la.getGameState() == 'DinghyInteract' and getattr(d, 'shipSelection', None) is not None, 20, 'rowboat list open')
    p = getattr(d, 'shipSelection', None)
    def own():
        try: return [f['shipId'] for f in p.shipFrames.get(p.OWN, [])]
        except Exception: return []
    yield ('upto', lambda: p is not None and all(s in own() for s in mine), 30)
    yield 2
    rows = own(); shot(H, 'ship1_rowboat'); yield 2
    ok = sorted(after) == sorted(mine) and all(s in rows for s in mine) and connected(H)
    verdict(ok, 'after a normal and a quick re-login his ship is still his at the rowboat' if ok
            else 'his ship is missing after the re-logins', ships=mine, after=after, ownRows=rows, connected=connected(H))


UPGRADE_SHIP = 100000750      # claude2's ship
UPGRADE_SAIL_SECS = 10.0      # time at the wheel before stepping off


def item_upgrade(H):
    """boats-0001 (0413 + client v479): the shipwright's Upgrade answers after a sail. Host's case: a ship he sailed and
    walked off is 'PutAway' for the rest of the session, and the picker's Upgrade did nothing. Like a kid: launch the
    ship at the Port Royal rowboat, take the wheel, step off and go back to town (areaTeleport), walk to the shipwright,
    open his menu, press Upgrade, then press the ship's own Upgrade. The game must answer: the Yes/No trade question, or
    a line saying why not. The question is answered No (nothing sent) and no gold is spent: every shop sale this NPC
    would send (requestMakeSale) is held back while the item runs. A damaged ship is not sailed (the launch would pay
    the shipwright), and the press is still checked, with sailed=False in the result."""
    import sailing, s_activities
    from panda3d.core import Point3
    from pirates.distributed import InteractGlobals as IG
    t0 = time.time()
    la = H.la
    yield from tp(H, PORT_ROYAL, 'Port Royal')
    la = H.la
    mine = list(la.getInventory().getShipDoIdList())
    if not mine:
        return verdict(False, 'this test pirate owns no ship', ships=mine)
    sid = mine[0]
    ov = H.cr.getOwnerView(sid)
    hp, maxHp = getattr(ov, 'Hp', None), getattr(ov, 'maxHp', None)
    gold0 = gold(H)
    H.ev('LIVE-STEP', step='own ships', ships=mine, ship=sid, expected=sid == UPGRADE_SHIP, cls=getattr(ov, 'shipClass', None),
         state=getattr(ov, 'state', None), hp=hp, maxHp=maxHp, gold=gold0)
    said = []
    gm = la.guiMgr
    origWarn = gm.createWarning

    def warn(text, *a, **kw):
        said.append(str(text))
        return origWarn(text, *a, **kw)
    gm.createWarning = warn
    npc = None
    held = []
    try:
        # 1. sail: launch at the rowboat, take the wheel, one sail level, step off, back to town
        sailed = hp is not None and maxHp and hp >= maxHp
        if not sailed:
            H.ev('LIVE-STEP', step='ship is damaged: not sailed (the launch would pay the shipwright)', hp=hp, maxHp=maxHp)
        else:
            try:
                ship = yield from sailing.launch(H, sailing.hereUid(H), sailing.onShip(H))
            except RuntimeError as e:
                ship = None
                H.ev('LIVE-STEP', step='launch refused', why=str(e))
            if ship is None:
                return verdict(False, 'could not launch the ship at the Port Royal rowboat', ship=sid, area=H.area(),
                               secs=round(time.time() - t0), kicked=R.get('kicked'))
            if la.getGameState() == 'ShipPilot':
                messenger.send('w'); messenger.send('w-up')     # one sail level
            yield UPGRADE_SAIL_SECS
            H.ev('LIVE-STEP', step='sailed', gs=la.getGameState(), ship=H.P(ship), secs=round(time.time() - t0))
            wheel = next((o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedSteeringWheel'
                          and getattr(o, 'shipId', None) == sid), None)
            if la.getGameState() == 'ShipPilot' and wheel is not None:
                wheel.requestExit()
            yield ('upto', lambda: la.getGameState() == 'LandRoam', 10)
            H.ev('LIVE-STEP', step='off the wheel', gs=la.getGameState(), secs=round(time.time() - t0))
            H.mw('areaTeleport %s' % PORT_ROYAL)
            yield ('upto', lambda: sailing.hereUid(H) == PORT_ROYAL and la.getGameState() == 'LandRoam'
                   and not sailing.onShip(H), 120)
            if sailing.hereUid(H) != PORT_ROYAL or sailing.onShip(H) or la.getGameState() != 'LandRoam':
                return verdict(False, 'could not get off the ship and back to Port Royal town', area=H.area(),
                               gs=la.getGameState(), onShip=sailing.onShip(H), secs=round(time.time() - t0),
                               kicked=R.get('kicked'))
            yield 5
        yield ('upto', lambda: getattr(H.cr.getOwnerView(sid), 'state', None) in ('Off', 'PutAway', 'Sunk'), 20)
        state = getattr(H.cr.getOwnerView(sid), 'state', None)
        H.ev('LIVE-STEP', step='back in town', sailed=bool(sailed), state=state, gold=gold(H), secs=round(time.time() - t0))

        # 2. walk to the shipwright (as sailing.repair does)
        R_ = H.render
        sw = sailing.shipwrights(H)
        if sw:
            goals = [tuple(o.getPos(R_)) for o in sw]
        else:
            isl = sailing.islandObj(H, PORT_ROYAL)
            goals = [tuple(R_.getRelativePoint(isl, Point3(*s))) for s in sailing.shipwrightSpots(PORT_ROYAL)] if isl is not None else []
        if not goals:
            return verdict(False, 'no Port Royal shipwright to walk to', area=H.area(), secs=round(time.time() - t0))
        g = yield from sailing.paths.walk_route(H, goals, sailing.SHIPWRIGHT_REACH, sailing.SHIPWRIGHT_REACH - 2,
                                                tag='to-shipwright', max_goals=len(goals))
        yield ('upto', lambda: sailing.shipwrights(H), 15)
        p = la.getPos(R_)
        sw = sorted(sailing.shipwrights(H), key=lambda o: sailing.paths.dist(p, o.getPos(R_)))
        npc = sw[0] if sw else None
        if npc is None or sailing.paths.dist(p, npc.getPos(R_)) > sailing.SHIPWRIGHT_REACH + 15 or \
                not (yield from sailing.near(H, npc, sailing.SHIPWRIGHT_REACH)):
            return verdict(False, 'could not walk up to the Port Royal shipwright', walked=g is not None,
                           shipwright=None if npc is None else npc.doId, la=H.P(la), secs=round(time.time() - t0))
        t1 = time.time()
        origSend = npc.sendUpdate

        def send(fieldName, *a, **kw):
            if fieldName == 'requestMakeSale':
                held.append(fieldName)
                H.ev('LIVE-STEP', step='a shop sale was about to go out and was held back', field=fieldName)
                return None
            return origSend(fieldName, *a, **kw)
        npc.sendUpdate = send

        # 3. his menu: Upgrade lit, press it
        yield from s_activities.talk(H, npc, lambda: getattr(npc, 'interactGUI', None) is not None
                                     and getattr(npc.interactGUI, 'optionButtons', None), 25)
        btns = list(getattr(npc.interactGUI, 'optionButtons', None) or [])
        up = next((b for b in btns if (b['extraArgs'] or [None])[0] == IG.UPGRADE), None)
        menuState = None if up is None else up['state']
        H.ev('LIVE-STEP', step='shipwright menu', npc=npc.doId, options=[(b['extraArgs'] or [None])[0] for b in btns],
             upgrade=menuState)
        if up is None or menuState != 'normal':
            shot(H, 'upgrade_menu')
            yield 2
            return verdict(False, "the shipwright's menu has no lit Upgrade", upgrade=menuState, state=state,
                           secs=round(time.time() - t0))
        yield 1.5
        up['command'](*(up['extraArgs'] or []))

        # 4. the ship picker: the ship's own Upgrade, press it
        def frame():
            pk = getattr(npc, 'pickShipGUI', None)
            f = pk.getFrame(sid) if pk is not None else None
            return f if f is not None and getattr(f, 'button', None) is not None else None
        yield ('upto', frame, 10)
        yield 1.0
        f = frame()
        if f is None:
            shot(H, 'upgrade_menu')
            yield 2
            return verdict(False, 'Upgrade pressed, but no ship list with this ship came up', state=state,
                           picker=getattr(npc, 'pickShipGUI', None) is not None, secs=round(time.time() - t0))
        b = f.button
        pickState = b['state']
        H.ev('LIVE-STEP', step='ship list', button=pickState, text=str(b['text']), state=getattr(H.cr.getOwnerView(sid), 'state', None))
        n0 = len(said)
        yield 1.0
        if b['extraArgs']:
            b['command'](*b['extraArgs'])
        else:
            b['command'](sid)

        # 5. the answer: a Yes/No question or a why-not line
        yield ('upto', lambda: getattr(npc, 'confirmDialog', None) is not None or len(said) > n0, 10)
        dlg = getattr(npc, 'confirmDialog', None)
        lines = said[n0:]
        if dlg is not None:
            try:
                q = str(dlg['text'])
            except Exception as e:
                q = 'err %r' % e
            kind, text = 'Yes/No trade question', q
        elif lines:
            kind, text = 'why-not line', lines[0]
        else:
            kind, text = None, None
        shot(H, 'upgrade_answer', 0.5)
        yield 3
        if dlg is not None:
            npc.sendRequestUpgradeShip(sid, 0)      # No: shuts the question, sends nothing
        yield from s_activities.leaveNpc(H, npc, IG)
        yield 2
        gold1 = gold(H)
        res = dict(answer=kind, text=text, sailed=bool(sailed), state=state, menuUpgrade=menuState,
                   shipButton=pickState, ship=sid, gold0=gold0, gold1=gold1, held=len(held),
                   answerSecs=round(time.time() - t1), secs=round(time.time() - t0), up=connected(H))
        if kind is None:
            return verdict(False, 'pressed the ship\'s Upgrade and the game said nothing in 10 s', **res)
        if gold1 != gold0:
            return verdict(False, 'the game answered (%s) but the gold changed' % kind, **res)
        verdict(connected(H), 'the shipwright answered Upgrade with the %s%s' % (
            kind, '' if sailed else ' (without a sail first: the ship is damaged)') if connected(H)
            else 'the shipwright answered but the game is not up', **res)
    finally:
        gm.createWarning = origWarn
        if npc is not None and 'sendUpdate' in npc.__dict__:
            del npc.sendUpdate


def run(H):
    wrapEv(H)
    hookKick(H)
    la = H.la
    if la.doId in NEVER:
        return verdict(False, 'refused: pirate %d is not a test pirate' % la.doId)
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    H.ev('LIVE-START', item=ITEM, av=la.doId, area=H.area(), quests=H.qids(), gold=gold(H))
    if ITEM == 'tia':
        yield from item_tia(H, 'wd.1visitTia', 23100, 'tia_talk')
    elif ITEM == 'tpt':
        yield from item_tia(H, 'tpt.1visitTia', 21001, 'tia_talk_tpt')
    elif ITEM == 'dropvisits':
        yield from item_dropvisits(H)
    elif ITEM == 'iron':
        yield from item_iron(H)
    elif ITEM == 'crate':
        yield from item_crate(H)
    elif ITEM == 'carver':
        yield from item_carver(H)
    elif ITEM == 'grenade':
        yield from item_grenade(H)
    elif ITEM == 'kings':
        yield from item_kings(H)
    elif ITEM == 'howto':
        yield from item_howto(H)
    elif ITEM == 'relog':
        yield from item_relog(H)
    elif ITEM == 'smoke':
        yield from item_smoke(H)
    elif ITEM == 'mini':
        yield from item_mini(H)
    elif ITEM == 'ship1':
        yield from item_ship1(H)
    elif ITEM == 'ships':
        yield from item_ships(H)
    elif ITEM == 'upgrade':
        yield from item_upgrade(H)
    else:
        verdict(False, 'unknown LIVE_ITEM %s' % ITEM)
