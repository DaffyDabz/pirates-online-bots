"""MECH CHECKS (pirates-bulbs, 11-21): live checks for the gaps in D:\\scratch\\lanes\\mechanics\\MECHANICS.md.
One item per run (env MECH_ITEM), on a test pirate only (claude2 / 100000004; never Host's 100000170, never the boys'
100000656 / 100000665). Start lines: D:\\scratch\\lanes\\mechanics\\RUN.md (run_mech.ps1, one game, run.lock).

Items:
  stores   gap 1: walk to Port Royal's tailor, jeweler, tattoo parlor and barber in turn; at each, open the store, put
           the cheapest thing he does not own in the cart the way the buy button does, press Purchase (barber: Buy,
           then Yes), and read the server's answer (makeSaleResponse 2 = sold). Worn = his look changed (the server
           wears what he bought). Between shops he walks out of the shop on a 4 ft route to its door (the PAGES4 fix:
           the straight walk from the tailor's counter to his door stuck on the stairwell; sim_shopexit.py).
           MECH_STORES picks the shops (default tailor,jeweler,tattoo,barber). MECH_GOLD (3000): when he holds less,
           the one magic word 'gold <n>' first, logged MW-GOLD.

  weapons  gap 6: the staff (Tia Dalma's quest ws.5deliverDoll, the swamp visit done for real), the doll
           (wdr6.4boneDustOfMuck) and the dagger (wk.7deliverKnives), the last two by skipQuest so the quest's own reward
           gives the weapon; givePlayerStack only if a reward never comes (WEAPON-FALLBACK, proof=False). The third skill
           comes the player's way (weapon level 2, then a skill point spent); then three skills at a weak enemy, each
           counted only when the server answers it. MECH_WEAPONS picks (default staff,doll,dagger).
  buttons  gap 10: emote (wave), respec (cutlass, costs gold), musician (Port Royal tavern, 5 gold a song), crew buff
           (Open Fire from his own ship's wheel). Lockpicks and code redemption are stubs: logged BUTTON-SKIPPED, never
           sent (the code handler's TypeError could take the UberDOG down). MECH_BUTTONS picks.
  vitae    gap 10: knocked out by an enemy at 1 hp; Vitae set on the way back up, then removeGroggy clears it.
  bpfort   gap 8: s_bpfort with the island's zones turned on first (bpstate skips the boarding step that does it) and
           no ~bpdestroy fallback: the forts must fall to cannon hits.

Lines: MECH-START, MECH-STEP, MECH-SHOT, KICKED, STORE-* per shop, EXIT-* for the walk out, then one PASS or FAIL.
Field values never hold the word in capitals (run_walk's strike check looks for it in the events file)."""
import os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))

ITEM = os.environ.get('MECH_ITEM', 'stores')
SHOTS = os.environ.get('MECH_SHOTS', r'C:\PiratesBots\out\mechanics\shots')
NEVER = (100000170, 100000656, 100000665)
TEST_PIRATE = int(os.environ.get('MECH_PIRATE', '100000004'))   # claude2; claude1 (100000001) while places walks
if TEST_PIRATE not in (100000004, 100000001):                     # claude2's doll chain (games, 11-21)
    TEST_PIRATE = 100000004
GOLD_MIN = int(os.environ.get('MECH_GOLD', '3000'))
STORE_ORDER = ('tailor', 'jeweler', 'tattoo', 'barber')
SHOPS = [s.strip() for s in os.environ.get('MECH_STORES', ','.join(STORE_ORDER)).lower().split(',') if s.strip()]
EXIT_GRID, EXIT_BOX, EXIT_EXPAND = 4.0, 80.0, 6000     # sim_shopexit.py: the tailor needs the 4 ft grid

R = {}        # the walker's own ev (PASS / FAIL count once per run)


def verdict(ok, what, **kw):
    R['ev']('PASS' if ok else 'FAIL', item=ITEM, what=what, **kw)


def wrapEv(H):
    """Sub-scripts end with their own PASS / FAIL: keep them as MECH-PASS / MECH-FAIL lines, so the verdict is ours."""
    R['ev'] = H.ev
    got = R.setdefault('sub', [])

    def ev(name, /, **kw):
        if name in ('PASS', 'FAIL'):
            got.append((name, kw))
            name = 'MECH-' + name
        R['ev'](name, **kw)
    H.ev = ev


def shot(H, name):
    from panda3d.core import Filename
    p = os.path.join(SHOTS, name + '.png')
    try:
        os.makedirs(SHOTS, exist_ok=True)
        ok = H.B.win.saveScreenshot(Filename.fromOsSpecific(p))
    except Exception as e:
        ok = 'err %r' % e
    H.ev('MECH-SHOT', name=name, path=p, ok=ok, area=H.area())
    return p


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
    except Exception:
        return None


def topUp(H, want):
    """The one magic word 'gold <n>' when he holds less than want (test pirates only: run() refused the rest)."""
    g = gold(H)
    if g is None or g >= want:
        return
    H.ev('MW-GOLD', why='the test pirate holds %s, the shops want %d' % (g, want), gold=g)
    H.mw('gold %d' % want)
    yield ('until', lambda: (gold(H) or 0) >= want, 20, 'gold')


# ------------------------------------------------------------------------------------------------ pure
def btnCost(b):
    """A store button's price: its cost label's last number, else the cost in its buy button's args (tailor)."""
    try:
        t = b.cost['text']
    except Exception:
        t = None
    nums = re.findall(r'\d+', str(t or ''))
    if nums:
        return int(nums[-1])
    try:
        a = list(b.addToCart['extraArgs'] or [])
    except Exception:
        a = []
    return a[5] if len(a) > 5 and isinstance(a[5], int) else None


def pickCart(buttons):
    """-> (cost, button) for the cheapest button whose buy button is live (buyState 1: not owned, sold here), or None."""
    cands = []
    for i, b in enumerate(buttons):
        atc = getattr(b, 'addToCart', None)
        if atc is None or not getattr(atc, 'buyState', 0):
            continue
        cost = btnCost(b)
        if cost is not None:
            cands.append((cost, i, b))
    if not cands:
        return None
    cost, _, b = min(cands, key=lambda c: (c[0], c[1]))
    return cost, b


def pickBarber(buttons, current, disabled='disabled'):
    """-> (cost, button) for the cheapest barber item he can buy that is not what he wears now (never bald: itemId 0).
    current = {type: itemId now}."""
    cands = []
    for i, b in enumerate(buttons):
        buy = getattr(b, 'buy', None)
        if buy is None or str(buy['state']) == disabled or getattr(b, 'itemId', 0) == 0:
            continue
        if current.get(getattr(b, 'type', None)) == b.itemId:
            continue
        cost = btnCost(b)
        cands.append((cost if cost is not None else 10 ** 6, i, b))
    if not cands:
        return None
    cost, _, b = min(cands, key=lambda c: (c[0], c[1]))
    return cost, b


def styleSnap(la):
    """His look as {field: repr}: the style's plain fields and its clothes' (what the server's wear updates change)."""
    out = {}
    s = getattr(la, 'style', None)
    for pre, obj in (('', s), ('clothes.', getattr(s, 'clothes', None))):
        if obj is None:
            continue
        try:
            items = vars(obj).items()
        except TypeError:
            continue
        for k, v in items:
            if isinstance(v, (int, float, str, tuple, list)) and len(repr(v)) < 200:
                out[pre + k] = repr(v)
    return out


def changed(a, b):
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


# ------------------------------------------------------------------------------------------------ walking
def leaveShop(H, tag):
    """Generator: out of the shop interior he is in, like a player: the 4 ft route to its door (the floor nearest the
    door on his side), then the door. -> True once in another area, else why."""
    import paths, s_story, s_lanes
    la, Rn = H.la, H.render
    here = s_story.hereArea(H)
    doors = [o for o in list(H.cr.doId2do.values()) if type(o).__name__ == 'DistributedInteriorDoor']
    if not doors:
        return 'no interior door in view'
    d = min(doors, key=lambda o: s_story.hdist(H, o))
    p, dp = la.getPos(Rn), d.getPos(Rn)
    a = (p[0], p[1], p[2])
    legs_ok, ground = paths.live(H, 0.0)
    lg, lr = paths.land_goal((dp[0], dp[1], dp[2]), ground, toward=a, max_r=10.0, step=1.0)
    goal = lg or (dp[0], dp[1], dp[2])
    t0 = time.time()
    route, checks = yield from paths.plan_g(a, goal, legs_ok, ground, (), 0.0, 0.0, EXIT_EXPAND, (0.0, 0.0),
                                            EXIT_GRID, EXIT_BOX)
    H.ev('EXIT-ROUTE', tag=tag, door=d.doId, frm=[round(v, 1) for v in a], goal=[round(v, 1) for v in goal],
         ring=lr, path=[[round(v, 1) for v in w] for w in route] if route else None, checks=checks,
         secs=round(time.time() - t0, 2))
    if route:
        for i, w in enumerate(route):
            ok = yield from H.walk_to(w, arrive=paths.TURN_ARRIVE, tag='%s exit %d' % (tag, i + 1))
            if not ok:
                H.ev('EXIT-STUCK', tag=tag, leg=i + 1, at=[round(v, 1) for v in la.getPos(Rn)])
                break
    r = yield from s_lanes.walkTo(H, 'mech', lambda st: True if s_story.hereArea(H) != here
                                  else s_story.useDoor(H, d, st, tag), 90, 'out of the ' + tag)
    H.ev('EXIT-DONE', tag=tag, ok=r is not None, frm=here, now=s_story.hereArea(H))
    return True if r is not None else 'still inside after the door'


def spots():
    import s_pages
    return dict(s_pages.STORES, **SPOTS)


def openStore(H, name):
    """Generator: walk to the shop's keeper, talk, press Store. -> (npc, gui) or (None, why)."""
    import s_lanes, s_story, s_pages
    from panda3d.core import Point3
    from pirates.distributed import InteractGlobals
    la, cr = H.la, H.cr
    sp = spots()
    area, uid, pos, optName, kind = sp[name]
    if not (yield from s_lanes.onIsland(H, 'mech', s_lanes.PR)):
        return None, 'could not get to Port Royal'
    here = s_story.hereArea(H)
    if here != area and here in [sp[n][0] for n in sp]:
        out = yield from leaveShop(H, 'from-' + [n for n in sp if sp[n][0] == here][0])
        if out is not True:
            return None, 'could not leave the last shop: %s' % out
    r = yield from s_lanes.walkTo(H, 'mech', lambda st: s_story.goto(H, st, area, pos=pos, arrive=s_pages.TALK,
                                                                     tag='to-' + name), 240, 'the ' + name)
    if r is None:
        return None, 'could not walk to the ' + name
    org = s_story.areaObj(H, area)
    spot = H.render.getRelativePoint(org, Point3(*pos)) if org else la.getPos(H.render)

    def keeper():
        live = [o for o in list(cr.doId2do.values()) if type(o).__name__ == 'DistributedNPCTownfolk'
                and hasattr(o, 'getPos')]
        byUid = [o for o in live if getattr(o, 'uniqueId', None) == uid]
        if byUid:
            return byUid[0]
        live = [o for o in live if kind in str(getattr(o, 'avatarType', '')) and
                (o.getPos(H.render) - spot).length() < s_pages.FIND_R]
        return live[0] if live else None
    yield ('until', lambda: keeper() is not None, 20, name + ' in view')
    npc = keeper()
    if npc is None:
        return None, 'no %s keeper near his spot' % name
    r = yield from s_lanes.walkTo(H, 'mech', lambda st: True if s_story.near(H, npc, s_pages.TALK, st, tag=name)
                                  else 'walk-to-' + name, 60, 'the ' + name)
    if r is None:
        return None, 'could not reach the ' + name
    H.walk_cancel()
    npc.requestInteraction(la.doId)
    yield ('until', lambda: la.getGameState() == 'NPCInteract' and getattr(npc, 'interactGUI', None) is not None,
           20, name + ' menu')
    if getattr(npc, 'interactGUI', None) is None:
        return None, 'no menu after the talk'
    yield 1.5
    npc.selectOptionConfirm(getattr(InteractGlobals, optName))
    yield ('until', lambda: getattr(npc, 'storeMenuGUI', None) is not None, 15, 'store open')
    gui = getattr(npc, 'storeMenuGUI', None)
    if gui is None:
        return None, 'Store pressed, no store window'
    yield 2.5           # the wardrobe list answer fills the buttons
    H.ev('STORE-OPEN', store=name, npc=npc.doId, gui=type(gui).__name__, buttons=len(getattr(gui, 'buttons', [])))
    return npc, gui


def closeStore(H, npc):
    from pirates.distributed import InteractGlobals
    try:
        if getattr(npc, 'storeMenuGUI', None) is not None:
            npc.storeMenuGUI.closePanel()
    except Exception as e:
        H.ev('STORE-CLOSE', err=repr(e))
    try:
        if H.la.getGameState() == 'NPCInteract':
            npc.selectOptionConfirm(InteractGlobals.CANCEL)
    except Exception as e:
        H.ev('STORE-CLOSE', err=repr(e))
    yield ('until', lambda: H.la.getGameState() == 'LandRoam', 20, 'back to LandRoam')


# ------------------------------------------------------------------------------------------------ items
def buyOne(H, name):
    """Generator: one shop: open, buy the cheapest thing he lacks, read the answer, see his look change. -> (ok, why)."""
    la = H.la
    npc, gui = yield from openStore(H, name)
    if npc is None:
        return False, gui
    resp = {}
    orig = npc.makeSaleResponse

    def msr(result, *a):
        resp['r'] = result
        H.ev('STORE-RESPONSE', store=name, result=result, sold=result == 2)
        return orig(result, *a)
    npc.makeSaleResponse = msr
    try:
        g0, look0 = gold(H), styleSnap(la)
        if name == 'barber':
            st = la.style
            BG = sys.modules[type(gui).__module__].BarberGlobals
            current = {BG.HAIR: st.getHairHair(), BG.BEARD: st.getHairBeard(), BG.MUSTACHE: st.getHairMustache()}
            pick = pickBarber(list(gui.buttons), current)
            if pick is None:
                return False, 'no barber item he can buy on the first page'
            cost, b = pick
            H.ev('STORE-PICK', store=name, cost=cost, uid=b.uid, type=b.type, itemId=b.itemId, gold=g0)
            gui.buyItem(b.uid, b, True)                     # Buy, then Yes on the confirm box
        else:
            pick = pickCart(list(gui.buttons))
            if pick is None:
                return False, 'no item he does not own on the first page'
            cost, b = pick
            args = list(b.addToCart['extraArgs'] or [])
            H.ev('STORE-PICK', store=name, cost=cost, args=repr(args[1:])[:160], gold=g0)
            b.addToCart['command'](*args)                   # the buy button's own click
            yield 0.5
            cart = getattr(getattr(gui, 'purchaseInventory', None), 'panels', None)
            if not cart:
                return False, 'the buy button put nothing in the cart (wardrobe full?)'
            gui.handleCommitPurchase()
        yield ('until', lambda: 'r' in resp, 20, name + ' answer')
        yield 3                                             # the wear updates follow the answer
        g1, look1 = gold(H), styleSnap(la)
        diff = changed(look0, look1)
        H.ev('STORE-BOUGHT', store=name, result=resp.get('r'), gold0=g0, gold1=g1, cost=cost, look=diff[:12])
        shot(H, 'mech-%s-bought' % name)
        if resp.get('r') != 2:
            return False, 'the server did not sell (answer %s)' % resp.get('r')
        if g0 is not None and g1 is not None and g1 >= g0 and cost:
            return False, 'sold but no gold taken (%s -> %s)' % (g0, g1)
        if not diff:
            return False, 'sold, gold taken, but his look did not change (not worn)'
        return True, 'bought for %s, wearing it (%s)' % (cost, ','.join(diff[:4]))
    finally:
        npc.makeSaleResponse = orig
        yield from closeStore(H, npc)


def item_stores(H):
    yield from topUp(H, GOLD_MIN)
    res = {}
    for name in SHOPS:
        if name not in STORE_ORDER:
            res[name] = (False, 'unknown shop')
            continue
        try:
            res[name] = yield from buyOne(H, name)
        except Exception:
            import traceback
            res[name] = (False, 'error')
            H.ev('STORE-ERROR', store=name, tb=traceback.format_exc()[-600:])
        H.ev('STORE-SHOP', store=name, ok=res[name][0], why=res[name][1])
        if 'kicked' in R:
            break
    bad = ['%s: %s' % (n, res[n][1]) for n in res if not res[n][0]]
    if 'kicked' in R:
        bad.append('kicked (code %s)' % R['kicked'])
    verdict(not bad and len(res) == len(SHOPS), 'bought and wore one thing at each shop',
            why='; '.join(bad) or None, shops={n: v[1] for n, v in res.items()})


# ------------------------------------------------------------------------------------------------ gap 8: the forts
def item_bpfort(H):
    """s_bpfort with the island's zones turned on first. 'bpstate StageTwo' skips handleBoardedPearl, the only code that
    turns the island's zones on (TreasureMapBlackPearl.py:439-442), so on 11-19 the forts were never in view."""
    os.environ.setdefault('BPFORT_FALLBACK', 'none')      # read at import: a ~bpdestroy fallback proves nothing
    import s_bpfort
    orig = s_bpfort.fight

    def fight(H2, inst, mode=None, log=None):
        isl = None
        try:
            isl = inst._getIsland()
            isl.setZoneLevel(0)
            isl.startProcessVisibility(H2.la)
        except Exception as e:
            H2.ev('BPFORT-ZONES', ok=False, err=repr(e))
        else:
            H2.ev('BPFORT-ZONES', ok=True, island=getattr(isl, 'doId', None),
                  why='bpstate skips handleBoardedPearl (TreasureMapBlackPearl.py:439-442): turned on here')
        yield 3
        return (yield from orig(H2, inst, mode, log))
    s_bpfort.fight = fight
    n0 = len(R.get('sub', []))
    try:
        yield from s_bpfort.run(H)
    finally:
        s_bpfort.fight = orig
    sub = R.get('sub', [])[n0:]
    last = sub[-1] if sub else ('FAIL', {'why': 'no verdict from s_bpfort'})
    verdict(last[0] == 'PASS', 'Black Pearl barricade forts fell to cannon hits with the zones on',
            why=last[1].get('why'), fight=last[1].get('fight'))


# ------------------------------------------------------------------------------------------------ enemies
def outdoors(H, tag):
    """Generator: on Port Royal's own ground (out of any shop or tavern first). -> True or why."""
    import s_lanes, s_story
    if not (yield from s_lanes.onIsland(H, 'mech', s_lanes.PR)):
        return 'could not get to Port Royal'
    if s_story.hereArea(H) != s_lanes.PR and s_story.hereArea(H) in [v[0] for v in spots().values()]:
        out = yield from leaveShop(H, tag)
        if out is not True:
            return out
    return True


def findFoe(H, secs, tag, avoid=()):
    """Generator: s_earn's way: a weak enemy in view, else walk the weakest spawn nodes of this island until one is.
    -> the enemy or None."""
    import s_fighter as F, s_story as story
    la = H.la
    tried, node, t0 = set(), None, time.time()
    while time.time() - t0 < secs:
        lvl = F.myLevel(H)
        ids, skip = F.pickFoe(F.foeRows(H), lvl, F.VIEW, 99, F.LVL_OVER)
        ids = [i for i in ids if i not in avoid]     # one he could not reach is not picked again
        o = H.cr.doId2do.get(ids[0]) if ids else None
        if o is not None:
            H.walk_cancel()
            H.ev('FOE-PICK', foe=o.doId, why=tag, kind=str(getattr(o, 'avatarType', None)),
                 lvl=getattr(o, 'level', None), myLvl=lvl, hp=getattr(o, 'hp', None))
            return o
        if node is None:
            here = story.hereArea(H)
            nodes = [tuple(v[1:4]) + (v[5],) for v in story.questSpots().get('objs', {}).values()
                     if v[0] == here and v[4] == 'Spawn Node']
            org = story.areaObj(H, here)
            me = la.getPos(org) if org is not None else la.getPos(H.render)
            pick = F.spawnPick(nodes, (me[0], me[1]), tried, lvl)
            if pick is None:
                if not nodes:
                    H.ev('FOE-NONE', why='no spawn nodes here', area=here)
                    return None
                tried.clear()
                yield 5
                continue
            H.ev('SPAWN-PICK', node=pick[3], why=tag, spot=[round(v, 1) for v in pick[:3]], myLvl=lvl)
            node = tuple(pick) + (org,)
        r = H.walk_poll(node[:3], ref=node[4], arrive=8.0, face=False, tag='mech-spawn')
        if r is True or r is None:
            tried.add(tuple(node[:3]))
            node = None
            yield 1.0
            continue
        yield 0.5
    H.walk_cancel()
    return None


def stack(H, sid):
    try:
        return H.la.getInventory().getStackQuantity(sid)
    except Exception:
        return None


# ------------------------------------------------------------------------------------------------ gap 6: weapons
# (name, weapon, rep, unspent points, its three skills, the original's quest, how that quest is done here)
WEAPONS = (
    ('staff', 'WandWeaponL1', 'WandRep', 'UnspentWand', ('StaffBlast', 'StaffSoulFlay', 'StaffPestilence'),
     'ws.5deliverDoll', 'tia'),                 # visit Tia Dalma in the Cuba swamp (StaffReward)
    ('doll', 'DollWeaponL1', 'DollRep', 'UnspentDoll', ('DollAttune', 'DollPoke', 'DollSwarm'),
     'wdr6.4boneDustOfMuck', 'skip'),           # the Muck's dust: the kill is skipped, the reward is the quest's own
    ('dagger', 'DaggerWeaponL1', 'DaggerRep', 'UnspentDagger', ('DaggerCut', 'DaggerSwipe', 'DaggerAsp'),
     'wk.7deliverKnives', 'skip'),              # knives to Elizabeth: skipped, the quest's own reward
)
WEAPON_PICK = [w.strip() for w in os.environ.get('MECH_WEAPONS', 'staff,doll,dagger').lower().split(',') if w.strip()]
SKILL_GAP = 4.0          # s between two skills (recharge)
ECHO_WAIT = 4.0          # s for the server's answer to a skill


def getWeapon(H, w):
    """Generator: the weapon the way the original gives it (its quest), else givePlayerStack (proof=False).
    -> (ok, how)."""
    from pirates.uberdog.UberDogGlobals import InventoryType as IT
    name, wname, _, _, _, qid, how = w
    wid = getattr(IT, wname)
    if (stack(H, wid) or 0) > 0:
        return True, 'owned already'
    H.ev('WEAPON-QUEST', weapon=name, quest=qid, how=how)
    if not H.has(qid):
        H.mw('giveQuest %s' % qid)
        yield ('until', lambda: H.has(qid), 20, 'give ' + qid)
    if how == 'tia':
        os.environ['TIA_QID'] = qid
        sys.modules.pop('s_tia_cuba', None)            # QID is read at import
        import s_tia_cuba
        yield from s_tia_cuba.run(H)
    else:
        H.mw('skipQuest %s' % qid)
    yield ('until', lambda: (stack(H, wid) or 0) > 0, 30, name + ' in his inventory')
    if (stack(H, wid) or 0) > 0:
        return True, 'quest %s (%s)' % (qid, 'turned in at Tia Dalma' if how == 'tia' else 'skipQuest, its own reward')
    H.ev('WEAPON-FALLBACK', weapon=name, proof=False, why='the quest reward never arrived', quest=qid,
         has=H.has(qid))
    H.mw('givePlayerStack %d 1' % wid)
    yield ('until', lambda: (stack(H, wid) or 0) > 0, 20, name + ' by givePlayerStack')
    return (stack(H, wid) or 0) > 0, 'FALLBACK givePlayerStack (quest reward missing)'.lower()


def thirdSkill(H, w):
    """Generator: the third skill unlocked the player's way: weapon level 2 (magic word), then a skill point spent on
    it (LocalPirate.spendSkillPoint). -> how."""
    from pirates.uberdog.UberDogGlobals import InventoryType as IT
    name, _, rep, unspent, skills, _, _ = w
    sid = getattr(IT, skills[2])
    if (stack(H, sid) or 0) > 0:
        return 'owned'
    H.mw('level %d 2' % getattr(IT, rep))
    yield ('until', lambda: (stack(H, getattr(IT, unspent)) or 0) > 0, 10, name + ' skill point')
    pts = stack(H, getattr(IT, unspent)) or 0
    if pts:
        H.la.spendSkillPoint(sid)
        yield ('until', lambda: (stack(H, sid) or 0) > 0, 10, skills[2])
    if (stack(H, sid) or 0) > 0:
        return 'level 2 + a skill point'
    H.ev('SKILL-FALLBACK', weapon=name, skill=skills[2], proof=False, points=pts,
         why='level 2 gave no skill point' if not pts else 'the skill point was not spent')
    H.mw('givePlayerStack %d 1' % sid)
    yield ('until', lambda: (stack(H, sid) or 0) > 0, 10, skills[2] + ' by givePlayerStack')
    return 'fallback givePlayerStack'


def hookSkills(H, echoes):
    """Count the server's answers to his skills (useTargetedSkill / useProjectileSkill without localSignal)."""
    la = H.la
    origs = {}
    for fn in ('useTargetedSkill', 'useProjectileSkill'):
        o = getattr(la, fn)
        origs[fn] = o

        def w(*a, _o=o, _fn=fn, **kw):
            if not kw.get('localSignal') and not (_fn == 'useTargetedSkill' and len(a) > 11 and a[11]):
                echoes.append((time.time(), _fn, a[0] if a else None))
            return _o(*a, **kw)
        setattr(la, fn, w)

    def undo():
        for fn, o in origs.items():
            setattr(la, fn, o)
    return undo


def draw(H, wid):
    """Generator: his weapon in hand the player's way (toggleWeapon; another drawn one is put away first)."""
    la = H.la
    if getattr(la, 'isWeaponDrawn', False) and getattr(la, 'currentWeaponId', None) != wid:
        la.toggleWeapon(la.currentWeaponId)
        yield ('until', lambda: not getattr(la, 'isWeaponDrawn', False), 6, 'put away')
    fresh = not getattr(la, 'isWeaponDrawn', False)
    if fresh:
        la.toggleWeapon(wid)
    yield ('until', lambda: getattr(la, 'isWeaponDrawn', False) and la.currentWeaponId == wid, 8, 'drawn')
    if fresh and not (getattr(la, 'isWeaponDrawn', False) and la.currentWeaponId == wid):
        # WEAPONS 11-21 01:0x: the staff pressed 1 s after login got no answer (the AI drops requestCurrentWeapon
        # while it has no weapon object for him); a player presses again
        H.ev('DRAW-RETRY', weapon=wid, current=getattr(la, 'currentWeaponId', None), gs=la.getGameState())
        yield 3.0
        la.toggleWeapon(wid)
        yield ('until', lambda: getattr(la, 'isWeaponDrawn', False) and la.currentWeaponId == wid, 8, 'drawn again')
    if fresh:
        yield 1.5                       # the draw animation: a skill pressed during it gets no answer (StaffBlast 11-21)
    return getattr(la, 'isWeaponDrawn', False) and la.currentWeaponId == wid


def sheathe(H):
    """Generator: the weapon put away the player's way, then back to LandRoam. A drawn weapon keeps gs 'Battle', and
    the next weapon's trip to Port Royal waits on LandRoam (WEAPONS 11-21: doll and dagger never left)."""
    la = H.la
    H.walk_cancel()
    if getattr(la, 'isWeaponDrawn', False):
        la.toggleWeapon(la.currentWeaponId)
        yield ('until', lambda: not getattr(la, 'isWeaponDrawn', False), 6, 'put away')
    yield ('until', lambda: la.getGameState() == 'LandRoam', 20, 'land roam')
    return la.getGameState() == 'LandRoam'


def fire(H, sid, foe, echoes):
    """Generator: one skill: the skill tray's call (CombatTray.trySkill), else the direct request walker uses.
    -> (echoed, how)."""
    from direct.distributed.ClockDelta import globalClockDelta
    la = H.la
    n0 = len(echoes)
    tray = getattr(getattr(la, 'guiMgr', None), 'combatTray', None)
    r = None
    try:
        la.currentTarget = foe
        r = tray.trySkill(sid, 0) if tray is not None else 'no tray'
    except Exception as e:
        r = 'err %r' % e
    yield ('until', lambda: len(echoes) > n0, ECHO_WAIT, 'skill %d answer' % sid)
    if len(echoes) > n0:
        return True, 'tray (%s)' % (r,)
    if H.cr.doId2do.get(foe.doId) is None:
        return False, 'the enemy is gone'
    la.sendRequestTargetedSkill(sid, 0, 1, foe.doId, [], globalClockDelta.getRealNetworkTime(bits=32),
                                list(la.getPos(H.render)), 0)
    yield ('until', lambda: len(echoes) > n0, ECHO_WAIT, 'skill %d answer (direct)' % sid)
    return len(echoes) > n0, 'direct (the tray said %s)' % (r,)


def useWeapon(H, w, echoes):
    """Generator: draw it, find a weak enemy, three skills on it. -> (ok, why, rows)."""
    from pirates.uberdog.UberDogGlobals import InventoryType as IT
    import paths
    name, wname, _, _, skills, _, _ = w
    wid = getattr(IT, wname)
    rows = []
    for sk in skills:
        sid = getattr(IT, sk)
        foe, unreached = None, set()
        for _ in range(3):
            foe = yield from findFoe(H, 180, 'weapon ' + name, unreached)
            if foe is None:
                return False, 'no enemy found', rows
            if not (yield from draw(H, wid)):
                return False, 'could not draw the %s (current %s)' % (name, getattr(H.la, 'currentWeaponId', None)), rows
            p = foe.getPos(H.render)
            if paths.dist(tuple(H.la.getPos(H.render)), tuple(p)) > 25:     # round the walls first, never straight at one
                yield from paths.walk_route(H, [(p[0], p[1], p[2])], arrive=12.0, short=12.0, tag='route-foe ' + name)
            ok = yield from H.walk_to(foe, arrive=5.0, face=True, timeout=40, tag='to-foe ' + name)
            if not ok:
                unreached.add(foe.doId)
            if ok and H.cr.doId2do.get(foe.doId) is not None and (getattr(foe, 'hp', 0) or 0) > 0:
                break
            foe = None
        if foe is None:
            return False, 'could not reach an enemy', rows
        got, how = yield from fire(H, sid, foe, echoes)
        rows.append((sk, got, how))
        H.ev('WEAPON-SKILL', weapon=name, skill=sk, id=sid, rank=stack(H, sid), ok=got, how=how, foe=foe.doId,
             foeHp=getattr(foe, 'hp', None), myHp=getattr(H.la, 'hp', None))
        if (getattr(H.la, 'hp', 1) or 0) < (getattr(H.la, 'maxHp', 100) or 100) * 0.5:
            H.mw('hp 0')                    # full heal: this check is about the skills, not the fight
        yield SKILL_GAP
    bad = [r[0] for r in rows if not r[1]]
    return not bad, 'no answer to %s' % ','.join(bad) if bad else '3 skills answered', rows


def item_weapons(H):
    out = yield from outdoors(H, 'weapons')
    if out is not True:
        return verdict(False, 'weapons: ' + out)
    echoes = []
    undo = hookSkills(H, echoes)
    res = {}
    try:
        for w in WEAPONS:
            name = w[0]
            if name not in WEAPON_PICK:
                continue
            got, how = yield from getWeapon(H, w)
            H.ev('WEAPON-GOT', weapon=name, ok=got, how=how)
            if not got:
                res[name] = (False, 'never got it: ' + how, [])
                continue
            out = yield from outdoors(H, 'weapons')      # Tia's visit ends in the Cuba swamp
            if out is not True:
                res[name] = (False, out, [])
                continue
            third = yield from thirdSkill(H, w)
            ok, why, rows = yield from useWeapon(H, w, echoes)
            res[name] = (ok, '%s; got: %s; third skill: %s' % (why, how, third), rows)
            H.ev('WEAPON-DONE', weapon=name, ok=ok, why=res[name][1], rows=rows)
            shot(H, 'mech-weapon-%s' % name)
            roam = yield from sheathe(H)
            H.ev('WEAPON-SHEATHE', weapon=name, ok=roam, gs=H.la.getGameState())
            if 'kicked' in R:
                break
    finally:
        undo()
        H.walk_cancel()
    bad = ['%s: %s' % (n, v[1]) for n, v in res.items() if not v[0]]
    if 'kicked' in R:
        bad.append('kicked (code %s)' % R['kicked'])
    fb = [n for n, v in res.items() if 'fallback' in v[1]]
    verdict(not bad and len(res) == len(WEAPON_PICK), 'got the staff, doll and dagger and used 3 skills with each',
            why='; '.join(bad) or None, fallback=fb or None, weapons={n: v[1] for n, v in res.items()})


# ------------------------------------------------------------------------------------------------ gap 10: buttons
# the musician in the Port Royal tavern (port_royal_building_int_tavern_2), as s_pages.STORES rows
SPOTS = {'music': ('1153419634.08dzlu0', '1181610880.0dchiappe', (-18.436, 32.326, 1.0), 'MUSICIAN', 'Music')}
BUTTONS = [b.strip() for b in os.environ.get('MECH_BUTTONS', 'emote,respec,music,crewbuff').lower().split(',')
           if b.strip()]
EMOTE_WAVE = 60664


def btn_emote(H):
    la = H.la
    if getattr(la, 'isWeaponDrawn', False):
        la.toggleWeapon(la.currentWeaponId)
        yield ('until', lambda: not getattr(la, 'isWeaponDrawn', False), 6, 'put away')
    H.walk_cancel()
    yield 1
    seen = []
    la.requestEmote(EMOTE_WAVE)
    t0 = time.time()
    while time.time() - t0 < 6:
        e = getattr(la, 'emoteId', None)
        seen.append((round(time.time() - t0, 1), la.getGameState(), e))
        if e == EMOTE_WAVE or la.getGameState() == 'Emote':
            return True, 'waved (state %s, emote %s)' % (la.getGameState(), e)
        yield 0.3
    return False, 'no wave (states %s)' % sorted(set(s[1] for s in seen))


def btn_respec(H):
    from pirates.uberdog.UberDogGlobals import InventoryType as IT
    la = H.la
    yield from topUp(H, 1000)
    before = dict(gold=gold(H), n=stack(H, IT.NumRespecCutlass), unspent=stack(H, IT.UnspentCutlass))
    la.resetSkillPoints(IT.CutlassRep)
    yield ('until', lambda: stack(H, IT.NumRespecCutlass) != before['n'] or gold(H) != before['gold'], 15, 'respec')
    yield 2
    after = dict(gold=gold(H), n=stack(H, IT.NumRespecCutlass), unspent=stack(H, IT.UnspentCutlass))
    H.ev('RESPEC', before=before, after=after)
    ok = (after['n'] or 0) > (before['n'] or 0) and (after['gold'] or 0) < (before['gold'] or 0)
    return ok, 'respec %s -> %s, gold %s -> %s, points %s -> %s' % (before['n'], after['n'], before['gold'],
                                                                   after['gold'], before['unspent'], after['unspent'])


def btn_music(H):
    la = H.la
    yield from topUp(H, 100)
    npc, gui = yield from openStore(H, 'music')
    if npc is None:
        return False, gui
    from pirates.economy import EconomyGlobals
    resp = {}
    orig = npc.makeSaleResponse

    def msr(result, *a):
        resp['r'] = result
        return orig(result, *a)
    npc.makeSaleResponse = msr
    import builtins
    mm = getattr(getattr(builtins, 'base', None), 'musicMgr', None)
    song0 = getattr(getattr(mm, 'current', None), 'name', None)
    g0 = gold(H)
    try:
        song = EconomyGlobals.MUSIC_SHELF[0]
        npc.sendRequestMusic(song)
        yield ('until', lambda: 'r' in resp or (gold(H) or 0) < (g0 or 0), 15, 'music answer')
        yield 3
    finally:
        npc.makeSaleResponse = orig
        if la.getGameState() == 'NPCInteract':
            yield from closeStore(H, npc)
    song1 = getattr(getattr(mm, 'current', None), 'name', None)
    H.ev('MUSIC', song=song, answer=resp.get('r'), gold0=g0, gold1=gold(H), music0=song0, music1=song1)
    ok = (g0 or 0) - (gold(H) or 0) == 5 and resp.get('r') in (None, 2)
    return ok, 'paid %s for song %s (answer %s, music %s -> %s)' % ((g0 or 0) - (gold(H) or 0), song, resp.get('r'),
                                                                   song0, song1)


def btn_crewbuff(H):
    """A captain's crew buff (Open Fire) from the wheel of his own ship, launched from Port Royal's dinghy."""
    from pirates.uberdog.UberDogGlobals import InventoryType as IT
    import s_shipquest
    la = H.la
    ship = yield from s_shipquest.launchShip(H)
    if ship is None:
        return False, 'could not launch his ship'
    yield ('until', lambda: la.getGameState() == 'ShipPilot', 30, 'at the wheel')
    sid = IT.SailOpenFire
    if not (stack(H, sid) or 0):
        pts = stack(H, IT.UnspentSailing) or 0
        if pts:
            la.spendSkillPoint(sid)
            yield ('until', lambda: (stack(H, sid) or 0) > 0, 10, 'Open Fire point')
        if not (stack(H, sid) or 0):
            H.ev('SKILL-FALLBACK', skill='SailOpenFire', proof=False, points=pts, why='he has no Open Fire rank')
            H.mw('givePlayerStack %d 1' % sid)
            yield ('until', lambda: (stack(H, sid) or 0) > 0, 10, 'Open Fire by givePlayerStack')
    echo = []
    orig = ship.useShipSkill

    def uss(*a, **kw):
        if not kw.get('localSignal'):
            echo.append(a[0] if a else None)
        return orig(*a, **kw)
    ship.useShipSkill = uss
    try:
        e0 = list(ship.getSkillEffects() or []) if hasattr(ship, 'getSkillEffects') else None
        la.composeRequestShipSkill(sid, 0)
        yield ('until', lambda: echo, 10, 'ship skill answer')
        yield 2
        e1 = list(ship.getSkillEffects() or []) if hasattr(ship, 'getSkillEffects') else None
    finally:
        ship.useShipSkill = orig
    H.ev('CREWBUFF', skill=sid, echo=echo, effects0=repr(e0)[:200], effects1=repr(e1)[:200],
         rank=stack(H, sid))
    ok = bool(echo) or (e1 is not None and e1 != e0)
    return ok, 'Open Fire %s (server answer %s, effects %s -> %s)' % ('used' if ok else 'not answered', echo,
                                                                     len(e0 or []), len(e1 or []))


BTNS = {'emote': btn_emote, 'respec': btn_respec, 'music': btn_music, 'crewbuff': btn_crewbuff}
NOT_TESTABLE = {
    'lockpicks': 'a stub: no lock is ever placed in the world data, so there is nothing to pick',
    'code': 'a stub: the UberDOG code handler raises a TypeError (could take the UberDOG down); never sent',
}


def item_buttons(H):
    res = {}
    for b in BUTTONS:
        if b in NOT_TESTABLE:
            H.ev('BUTTON-SKIPPED', button=b, why=NOT_TESTABLE[b])
            continue
        fn = BTNS.get(b)
        if fn is None:
            res[b] = (False, 'unknown button')
            continue
        if b in ('emote', 'respec'):
            out = yield from outdoors(H, b)
            if out is not True:
                res[b] = (False, out)
                continue
        try:
            res[b] = yield from fn(H)
        except Exception:
            import traceback
            res[b] = (False, 'error')
            H.ev('BUTTON-ERROR', button=b, tb=traceback.format_exc()[-600:])
        H.ev('BUTTON', button=b, ok=res[b][0], why=res[b][1])
        shot(H, 'mech-button-%s' % b)
        if 'kicked' in R:
            break
    bad = ['%s: %s' % (n, v[1]) for n, v in res.items() if not v[0]]
    if 'kicked' in R:
        bad.append('kicked (code %s)' % R['kicked'])
    verdict(not bad and bool(res), 'every testable button did its job', why='; '.join(bad) or None,
            buttons={n: v[1] for n, v in res.items()}, skipped=sorted(b for b in BUTTONS if b in NOT_TESTABLE) or None)


# ------------------------------------------------------------------------------------------------ gap 10: Vitae
def vitae(H):
    from pirates.uberdog.UberDogGlobals import InventoryType as IT
    return dict(level=stack(H, IT.Vitae_Level), cost=stack(H, IT.Vitae_Cost), left=stack(H, IT.Vitae_Left))


def reachFoe(H, unreached, tries=4):
    """Generator: a weak enemy he can walk up to (round the walls first); one he gets stuck on is skipped. -> it or None."""
    import paths
    for _ in range(tries):
        foe = yield from findFoe(H, 240, 'vitae', unreached)
        if foe is None:
            return None
        p = foe.getPos(H.render)
        if paths.dist(tuple(H.la.getPos(H.render)), tuple(p)) > 25:
            yield from paths.walk_route(H, [(p[0], p[1], p[2])], arrive=12.0, short=12.0, tag='route-foe vitae')
        if (yield from H.walk_to(foe, arrive=3.5, face=True, timeout=40, tag='to-foe vitae')):
            return foe
        unreached.add(foe.doId)
    return None


def item_vitae(H):
    """Knocked out by an enemy at 1 hp -> jail with Vitae (level 1, 36000 s, 75% health); removeGroggy clears it."""
    la = H.la
    out = yield from outdoors(H, 'vitae')
    if out is not True:
        return verdict(False, 'vitae: ' + out)
    v0 = vitae(H)
    H.ev('VITAE-BEFORE', **v0)
    if v0['level']:
        H.mw('removeGroggy')
        yield ('until', lambda: not vitae(H)['level'], 10, 'groggy off first')
    unreached = set()
    foe = yield from reachFoe(H, unreached)      # at full health: walking there at 1 hp, it heals back up
    if foe is None:
        return verdict(False, 'vitae: could not reach an enemy')
    # VITAE 11-21 01:28: H.hit sends a cutlass hack, and with no cutlass in hand the enemy never fought back
    from pirates.uberdog.UberDogGlobals import InventoryType as IT
    if not (yield from draw(H, IT.CutlassWeaponL1)):
        return verdict(False, 'vitae: could not draw the cutlass (current %s)' % getattr(la, 'currentWeaponId', None))
    H.mw('hp 1')
    yield ('until', lambda: (getattr(la, 'hp', 99) or 0) <= 10, 10, 'hp 1')
    t0, again = time.time(), time.time()
    while time.time() - t0 < 120 and (getattr(la, 'hp', 1) or 0) > 0 and la.getGameState() not in ('Death', 'Dying'):
        # the server heals him 8 hp every 2 s (DistributedPlayerPirateAI.toonUp), so 1 hp is set again every 4 s
        if (getattr(la, 'hp', 0) or 0) > 5 and time.time() - again > 4:
            H.ev('VITAE-HP-AGAIN', hp=getattr(la, 'hp', None))
            H.mw('hp 1')
            again = time.time()
        if H.cr.doId2do.get(foe.doId) is None or (getattr(foe, 'hp', 0) or 0) <= 0:
            foe = yield from reachFoe(H, unreached)
            if foe is None:
                break
        if not (yield from H.hit(foe.doId)):      # one swing: it fights back
            unreached.add(foe.doId)
            foe = yield from reachFoe(H, unreached)
            if foe is None:
                break
        yield 2
    H.ev('VITAE-KO', hp=getattr(la, 'hp', None), gs=la.getGameState(), secs=round(time.time() - t0))
    yield ('until', lambda: la.getGameState() == 'LandRoam' and (getattr(la, 'hp', 0) or 0) > 0, 180, 'up again')
    yield 3
    v1 = vitae(H)
    mx = getattr(la, 'maxHp', None)
    H.ev('VITAE-AFTER', area=H.area(), hp=getattr(la, 'hp', None), maxHp=mx, **v1)
    shot(H, 'mech-vitae')
    H.mw('removeGroggy')
    yield ('until', lambda: not vitae(H)['level'], 15, 'groggy off')
    v2 = vitae(H)
    H.ev('VITAE-CLEARED', **v2)
    ok = (v1['level'] or 0) >= 1 and (v1['left'] or 0) > 0 and not v2['level']
    verdict(ok, 'knocked out: Vitae set, then cleared', before=v0, after=v1, cleared=v2,
            why=None if ok else 'no Vitae after the knock-out' if not v1['level'] else 'removeGroggy left it on')


ITEMS = {'stores': item_stores, 'bpfort': item_bpfort, 'weapons': item_weapons, 'buttons': item_buttons,
         'vitae': item_vitae}


def run(H):
    wrapEv(H)
    hookKick(H)
    la = H.la
    if la.doId in NEVER or la.doId != TEST_PIRATE:
        return verdict(False, 'refused: pirate %d is not the test pirate %d' % (la.doId, TEST_PIRATE))
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    H.ev('MECH-START', item=ITEM, av=la.doId, area=H.area(), gold=gold(H))
    fn = ITEMS.get(ITEM)
    if fn is None:
        return verdict(False, 'unknown MECH_ITEM %s (know %s)' % (ITEM, ','.join(ITEMS)))
    try:
        yield from fn(H)
    except Exception:
        import traceback
        verdict(False, 'error', tb=traceback.format_exc()[-800:])
