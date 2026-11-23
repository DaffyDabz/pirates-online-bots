"""PAGES (pir-bot job 34, 11-19): two picture proofs for client patches 0302 and 0303.

0303 (pir-quests README): the sea chest's Collections page drew its set pictures down a staircase, because
CollectionMain.refreshList put picture n at row `1 + n / 4` (a float in Python 3: 1, 1.25, 1.5 ...). With 0303 it is
`n // 4`, so four pictures share a row.
0302: the store windows' page label read "Page 2.0 / 3" (`startIndex / buttonsPerPage + 1`); with 0302 "Page 2 / 3".
The same label code is in the tailor (AccessoriesStoreGUI), barber, tattoo and jewelry stores.

PAGES_DO picks the parts (default coll,store):
  coll   give the test pirate COLL_SETS collection sets when he holds fewer (the magic word givePlayerStack <set> 1,
         test pirates only, logged MW-COLL), open the sea chest on the Collections page, read where each set picture
         sits (COLL-PICS), judge the rows (COLL-ROWS: rowsOk), take a screenshot (PAGE-SHOT), close the chest.
  store  walk to Port Royal's tailor (in his shop: interior 1153417506.13dzlu0, Townsperson 1196896512.0dxschafe),
         talk, press Store, read the page label (STORE-LABEL), press the next-page arrow and read it again, take a
         screenshot each time, judge (labelOk: whole page numbers), close the store and say goodbye.
         Job 43: the same walk for each shop in PAGES_STORES (default tailor,jeweler,tattoo,barber; the STORES table:
         interior, keeper uid, spot, InteractGlobals option). Logs STORE-OPEN, STORE-LABEL store=<shop>, then
         STORE-SHOP store=<shop> ok why; one shop failing does not stop the next (0353: these four used to crash
         on open, so 'no store window' is the fail to look for).
  buy    (games lane 11-20) the same walk to each shop in PAGES_STORES; buy its cheapest unowned thing and wear it
         (buyIn: STORE-PICK, STORE-BUY, STORE-WORN, a screenshot bought and worn). Gives BUY_GOLD gold first if short.
PASS when every part asked for passed; each part's own line says ok / why.
Never on Host's pirate 100000170 (the magic word changes his inventory): the step refuses it before anything else.
env: PAGES_DO (coll,store), PAGES_STORES (tailor,jeweler,tattoo,barber), COLL_SETS (5), COLL_GIVE (1)."""
import os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0])))

DO = [p.strip() for p in os.environ.get('PAGES_DO', 'coll,store').lower().split(',') if p.strip()]
SETS = int(os.environ.get('COLL_SETS', '5'))
GIVE = os.environ.get('COLL_GIVE', '1') == '1'
HOST_AV = 100000170
# InventoryType.Collection_Sets (UberDogGlobals 688); read from the game when it loads, these are its numbers
COLL_SET_IDS = (15000, 15030, 15060, 15090, 15120, 15150, 15180, 15210, 15230)
try:
    from pirates.uberdog.UberDogGlobals import InventoryType as _IT
    COLL_SET_IDS = tuple(_IT.Collection_Sets)
except Exception:
    pass
TAILOR = ('1153417506.13dzlu0', '1196896512.0dxschafe', (-6.484, -2.836, 0.0))   # interior, his uid, his spot
# job 43: the four Port Royal shops whose store windows 0353 fixed (each sorted its list with a cmp function and
# crashed on open). name -> (interior uid, Townsperson uid, spot in the interior, InteractGlobals option, avatarType
# word). From worldData port_royal_building_int_tailor / _barber / _6 (jeweler) / _14 (tattoo).
STORES = {
    'tailor': TAILOR + ('ACCESSORIES_STORE', 'Tailor'),
    'jeweler': ('1155773612.45fxlara0', '1201109074.66dxschafe', (9.299, 40.271, 5.265), 'JEWELRY_STORE', 'Jeweler'),
    'tattoo': ('1155767402.81fxlara0', '1201028352.0dxschafe', (-0.627, 7.127, 0.0), 'TATTOO_STORE', 'Tattoo'),
    'barber': ('1153419342.98dzlu0', '1196897792.0dxschafe0', (8.038, -0.644, 0.0), 'BARBER_STORE', 'Barber'),
}
STORE_ORDER = ('tailor', 'jeweler', 'tattoo', 'barber')
SHOPS = [s.strip() for s in os.environ.get('PAGES_STORES', ','.join(STORE_ORDER)).lower().split(',') if s.strip()]
TALK = 8.0
FIND_R = 40.0
PER_ROW = 4


# ------------------------------------------------------------------------------------------------ pure
def rowsOk(zs, perRow=PER_ROW):
    """zs = each set picture's height in the list, in set order. -> (ok, why). Straight rows: ceil(n / perRow)
    different heights, perRow pictures to a row. The staircase (before 0303) gives every picture its own height."""
    n = len(zs)
    if n < 2:
        return False, 'need 2+ pictures to tell rows apart (have %d)' % n
    rows = []
    for z in zs:
        z = round(z, 3)
        if z not in rows:
            rows.append(z)
    want = -(-n // perRow)
    if len(rows) == want:
        return True, '%d pictures in %d straight row(s)' % (n, want)
    if len(rows) == n:
        return False, 'staircase: each of the %d pictures has its own height' % n
    return False, '%d pictures in %d heights, want %d rows' % (n, len(rows), want)


PAGE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)')


def labelOk(text):
    """A store page label ('Page 2 / 3'). -> (ok, why, (page, pages)). OK when both numbers are whole (no '.0')."""
    m = PAGE_RE.search(text or '')
    if not m:
        return False, 'no "a / b" in %r' % (text,), None
    a, b = m.group(1), m.group(2)
    if '.' in a or '.' in b:
        return False, 'a decimal page number in %r' % (text,), (a, b)
    return True, 'whole page numbers %s / %s' % (a, b), (int(a), int(b))


def setsToGive(held, want, ids=COLL_SET_IDS):
    """held = set ids the pirate holds. -> the set ids to give so he holds `want` (lowest ids first)."""
    have = [i for i in ids if i in held]
    need = max(0, min(want, len(ids)) - len(have))
    return [i for i in ids if i not in held][:need]


# ------------------------------------------------------------------------------------------------ in the game
def shot(H, name):
    """A screenshot next to the step: <step dir>/shots/PAGES-<name>-<time>.png."""
    from panda3d.core import Filename
    d = os.path.join(os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0])), 'shots')
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, 'PAGES-%s-%s.png' % (name, time.strftime('%H%M%S')))
    try:
        ok = bool(H.B.win.saveScreenshot(Filename.fromOsSpecific(f)))
    except Exception as e:
        ok = False
        H.ev('PAGE-SHOT', shot=name, ok=False, err=repr(e))
        return None
    H.ev('PAGE-SHOT', shot=name, file=f, ok=ok)
    return f if ok else None


def heldSets(inv):
    return [i for i in COLL_SET_IDS if (inv.getStackQuantity(i) or 0) > 0]


def coll(H):
    """Generator: the Collections page proof. -> (ok, why)."""
    la = H.la
    inv = la.getInventory()
    if inv is None:
        return False, 'no inventory'
    held = heldSets(inv)
    give = setsToGive(held, SETS)
    if give and GIVE:
        for sid in give:
            H.ev('MW-COLL', word='givePlayerStack %d 1' % sid, why='a test pirate with %d sets; the page needs %d'
                 % (len(held), SETS))
            H.mw('givePlayerStack %d 1' % sid)
        yield ('until', lambda: len(heldSets(inv)) >= min(SETS, len(COLL_SET_IDS)), 20, 'sets given')
    held = heldSets(inv)
    gm = la.guiMgr
    page = getattr(gm, 'collectionMain', None)
    if page is None:
        return False, 'no Collections page'
    yield ('until', lambda: la.getGameState() == 'LandRoam', 30, 'LandRoam for the sea chest')
    page.refreshList()                     # draws a picture for each set held (CollectionMain 80-112)
    gm.showSeaChest(page)
    gm.showCollectionMain()
    yield 1.5
    pics = [(k, page.setPics[k].getZ()) for k in held if k in getattr(page, 'setPics', {})]
    H.ev('COLL-PICS', held=held, pics=[(k, round(z, 3), round(page.setPics[k].getX(), 3)) for k, z in pics],
         open=bool(gm.chestPanel.isActive()) if hasattr(gm.chestPanel, 'isActive') else None)
    ok, why = rowsOk([z for _, z in pics])
    f = shot(H, 'collections')
    H.ev('COLL-ROWS', ok=ok, why=why, n=len(pics), shot=f)
    yield 1
    try:
        gm.hideSeaChest()
    except Exception as e:
        H.ev('COLL-CLOSE', err=repr(e))
    return ok, why


# games lane (11-20, gap 1): PAGES_DO=buy walks to each shop, buys its cheapest unowned thing and wears it. Proof is
# what the server sends back, not what the store window drew: the sale answer (makeSaleResponse 2, or the barber's
# makeBarberResponse), the wardrobe list holding it, the gold going down by its price, and the server's own field
# update for that slot (setClothesShirt, setJewelryZone3, setTattooChest, setHairHair...) still naming it after the
# store closes (the close sends the equip). BUY_GOLD: a test pirate with less is given that much first (magic word).
BUY_GOLD = int(os.environ.get('BUY_GOLD', '5000'))
CLOTH_FIELD = {'HAT': 'setHatIdx', 'SHIRT': 'setClothesShirt', 'VEST': 'setClothesVest', 'COAT': 'setClothesCoat',
               'BELT': 'setClothesBelt', 'PANT': 'setClothesPant', 'SHOE': 'setClothesShoe'}
ECHO_FIELDS = (tuple(CLOTH_FIELD.values()) + ('setHatTexture',) + tuple('setJewelryZone%d' % i for i in range(1, 9)) +
               ('setTattooChest', 'setTattooZone2', 'setTattooZone3', 'setTattooZone4',
                'setHairHair', 'setHairBeard', 'setHairMustache', 'setHairColor'))
SALE_FIELDS = ('makeSaleResponse', 'makeBarberResponse')


def cheapest(cands, owned, gold):
    """cands = [(cost, key, payload)]; owned = keys already owned. -> the cheapest unowned one gold covers, or None."""
    left = sorted((c for c in cands if c[1] not in owned and 0 < c[0] <= gold), key=lambda c: (c[0], str(c[1])))
    return left[0] if left else None


def lastSent(log, field):
    """log = [(field, args)] in arrival order. -> the last args the server sent for field, or None."""
    for f, a in reversed(log):
        if f == field:
            return tuple(a)
    return None


def listen(obj, names, log):
    """Wrap obj's handlers for the named fields so every update the server sends is logged (field, args) before the
    game handles it. -> undo()."""
    before = {}
    for n in names:
        f = getattr(obj, n, None)
        if f is None:
            continue
        before[n] = obj.__dict__.get(n)

        def w(*a, _n=n, _f=f):
            log.append((_n, a))
            return _f(*a)
        setattr(obj, n, w)

    def undo():
        for n, old in before.items():
            try:
                if old is None:
                    delattr(obj, n)
                else:
                    setattr(obj, n, old)
            except AttributeError:
                pass
    return undo


def buyPick(gui, name, la):
    """The store window's buy buttons. -> (cands, owned): cands = [(cost, key, (press, field, want, what))]."""
    from pirates.makeapirate import JewelryGlobals as JG, TattooGlobals as TG, BarberGlobals as BG
    cands, owned = [], set()
    ward = [e for e in (getattr(gui, 'currentWardrobe', None) or []) if e != -1]
    if name == 'barber':
        st = la.style
        cur = {BG.HAIR: st.getHairHair(), BG.BEARD: st.getHairBeard(), BG.MUSTACHE: st.getHairMustache()}
        field = {BG.HAIR: 'setHairHair', BG.BEARD: 'setHairBeard', BG.MUSTACHE: 'setHairMustache'}
        for b in getattr(gui, 'buttons', []):
            buy = getattr(b, 'buy', None)
            if buy is None or not hasattr(b, 'uid') or buy['state'] == 'disabled' or buy['command'] != gui.buyItem:
                continue
            item = BG.barber_id.get(b.uid)
            if not item or item[1] not in field:
                continue
            if item[0] == cur.get(item[1]):
                owned.add(b.uid)
            cands.append((int(item[4]), b.uid, ((lambda b=b: gui.buyItem(b.uid, b, True)), field[item[1]], (item[0],),
                                                '%s %s' % (item[2], b.uid))))
        return cands, owned
    for b in getattr(gui, 'buttons', []):
        add = getattr(b, 'addToCart', None)
        if add is None or add['state'] == 'disabled' or add['command'] != gui.addToCart:
            continue
        ea = list(add['extraArgs'])
        press = (lambda add=add: add['command'](*add['extraArgs']))
        if name == 'tailor':
            _, ctype, model, tex, color, cost, uid = ea
            if ctype not in CLOTH_FIELD:
                continue
            want = (model,) if ctype == 'HAT' else (model, tex)
            cands.append((int(cost), (uid, color), (press, CLOTH_FIELD[ctype], want, '%s %s/%s' % (ctype, uid, color))))
        elif name == 'jeweler':
            _, jtype, uid = ea
            item = JG.jewelry_id.get(uid)
            zone = {JG.LEAR: 1, JG.REAR: 2, JG.LBROW: 3, JG.RBROW: 4, JG.NOSE: 5, JG.MOUTH: 6, JG.LHAND: 7,
                    JG.RHAND: 8}.get(jtype)
            if not item or zone is None or not item[0]:
                continue
            cands.append((max(int(item[3]), 1), uid, (press, 'setJewelryZone%d' % zone, (item[0],), 'jewelry %s' % uid)))
        elif name == 'tattoo':
            _, zone, uid = ea
            item = TG.tattoos.get(uid)
            field = {TG.ZONE1: 'setTattooChest', TG.ZONE2: 'setTattooZone2', TG.ZONE3: 'setTattooZone3',
                     TG.ZONE4: 'setTattooZone4'}.get(zone)
            if not item or field is None or not item[1]:
                continue
            cands.append((int(item[4]), uid, (press, field, (item[1],), 'tattoo %s' % uid)))
    if name == 'tailor':
        owned = {(e[0], e[1]) for e in ward if isinstance(e, (list, tuple))}
    else:
        owned = set(ward)
    return cands, owned


def buyIn(H, npc, gui, name, log):
    """Generator, the store window open: buy the cheapest unowned thing and see the server sell it and dress him in
    it. -> (ok, why, check): check() runs after the store closed -> (ok, why)."""
    import s_lanes
    la = H.la
    yield ('until', lambda: getattr(gui, 'buttons', None), 10, name + ' buttons')
    yield 1.5                                  # the wardrobe list answers the open
    gold = s_lanes.gold(H)
    cands, owned = buyPick(gui, name, la)
    pick = cheapest(cands, owned, gold)
    H.ev('STORE-PICK', store=name, gold=gold, cands=len(cands), owned=len(owned),
         pick=None if pick is None else (pick[0], pick[2][3]))
    if pick is None:
        return False, '%d buy buttons, %d owned, gold %s: nothing to buy' % (len(cands), len(owned), gold), None
    cost, key, (press, field, want, what) = pick
    n0 = len(log)
    press()
    if name != 'barber':
        yield 0.5
        if not getattr(gui, 'purchaseInventory', None) or not gui.purchaseInventory.purchases:
            return False, 'pressed add-to-cart on %s, the cart is empty' % what, None
        gui.handleCommitPurchase()
    yield ('until', lambda: any(f in SALE_FIELDS for f, _ in log[n0:]), 15, name + ' sale answer')
    yield ('until', lambda: lastSent(log[n0:], field) is not None and lastSent(log[n0:], field)[:len(want)] == want,
           10, name + ' worn')
    if name != 'barber':
        yield ('until', lambda: key in buyPick(gui, name, la)[1], 10, name + ' wardrobe')
    sale = [(f, a) for f, a in log[n0:] if f in SALE_FIELDS]
    sent = lastSent(log[n0:], field)
    gold2 = s_lanes.gold(H)
    inWard = name == 'barber' or key in buyPick(gui, name, la)[1]
    H.ev('STORE-BUY', store=name, what=what, cost=cost, gold=(gold, gold2), sale=sale, field=field, sent=sent,
         want=want, wardrobe=inWard, shot=shot(H, name + '-bought'))
    bad = []
    if not sale or sale[-1][0] == 'makeSaleResponse' and sale[-1][1][:1] != (2,):
        bad.append('sale answer %s' % (sale or 'none'))
    if gold2 != gold - cost:
        bad.append('gold %s -> %s, price %d' % (gold, gold2, cost))
    if not inWard:
        bad.append('not in the wardrobe list')
    if sent is None or sent[:len(want)] != want:
        bad.append('server sent %s %s, want %s' % (field, sent, want))
    if bad:
        return False, '%s: %s' % (what, '; '.join(bad)), None

    def check():
        now = lastSent(log, field)
        ok = now is not None and now[:len(want)] == want
        return ok, ('%s bought for %d and still worn after the store closed' % (what, cost) if ok else
                    '%s bought, but after the store closed the server sent %s %s' % (what, field, now))
    return True, what, check


def shopsToRun(names=None):
    """-> (known shop names in order, unknown names). PAGES_STORES picks them; default all four."""
    names = SHOPS if names is None else names
    return [n for n in names if n in STORES], [n for n in names if n not in STORES]


def store(H, buy=False):
    """Generator: every shop in PAGES_STORES in turn (tailor, jeweler, tattoo, barber). -> (ok, why).
    Each shop logs STORE-SHOP with its own ok / why; one failing shop does not stop the next."""
    shops, unknown = shopsToRun()
    res = {}
    for name in unknown:
        res[name] = (False, 'unknown shop (know %s)' % ','.join(STORE_ORDER))
    for name in shops:
        try:
            res[name] = yield from shop(H, name, buy)
        except Exception:
            import traceback
            res[name] = (False, 'error')
            H.ev('STORE-ERROR', store=name, tb=traceback.format_exc()[-600:])
        H.ev('STORE-SHOP', store=name, ok=res[name][0], why=res[name][1])
    if not res:
        return False, 'no shop asked for'
    bad = ['%s: %s' % (n, res[n][1]) for n in res if not res[n][0]]
    if bad:
        return False, '; '.join(bad)
    return True, '; '.join('%s %s' % (n, res[n][1]) for n in res)


def shop(H, name, buy=False):
    """Generator: one shop's page label proof, or with buy its buy-and-wear proof (buyIn). -> (ok, why)."""
    import s_lanes, s_story
    from panda3d.core import Point3
    from pirates.distributed import InteractGlobals
    la, cr = H.la, H.cr
    area, uid, pos, optName, kind = STORES[name]
    option = getattr(InteractGlobals, optName)
    if not (yield from s_lanes.onIsland(H, 'pages', s_lanes.PR)):
        return False, 'could not get to Port Royal'
    r = yield from s_lanes.walkTo(H, 'pages', lambda st: s_story.goto(H, st, area, pos=pos, arrive=TALK,
                                                                      tag='to-' + name), 240, 'the ' + name)
    if r is None:
        return False, 'could not walk to the ' + name
    org = s_story.areaObj(H, area)
    spot = H.render.getRelativePoint(org, Point3(*pos)) if org else la.getPos(H.render)

    def keeper():
        live = [o for o in list(cr.doId2do.values()) if type(o).__name__ == 'DistributedNPCTownfolk'
                and hasattr(o, 'getPos')]
        byUid = [o for o in live if getattr(o, 'uniqueId', None) == uid]
        if byUid:
            return byUid[0]
        live = [o for o in live if kind in str(getattr(o, 'avatarType', '')) and
                (o.getPos(H.render) - spot).length() < FIND_R]
        return live[0] if live else None
    yield ('until', lambda: keeper() is not None, 20, name + ' in view')
    npc = keeper()
    if npc is None:
        return False, 'no %s within %d ft of the spot' % (name, FIND_R)
    r = yield from s_lanes.walkTo(H, 'pages', lambda st: True if s_story.near(H, npc, TALK, st, tag=name)
                                  else 'walk-to-' + name, 60, 'the ' + name)
    if r is None:
        return False, 'could not reach the ' + name
    H.walk_cancel()
    labels = []
    bought, log, undo = None, [], []
    if buy:
        if s_lanes.gold(H) < BUY_GOLD:
            H.ev('MW-GOLD', word='gold %d' % BUY_GOLD, why='a test pirate with %s gold buys at the %s' %
                 (s_lanes.gold(H), name))
            H.mw('gold %d' % BUY_GOLD)
            yield ('until', lambda: s_lanes.gold(H) == BUY_GOLD, 10, 'gold %d' % BUY_GOLD)
        undo = [listen(la, ECHO_FIELDS, log), listen(npc, SALE_FIELDS, log)]
    try:
        npc.requestInteraction(la.doId)
        yield ('until', lambda: la.getGameState() == 'NPCInteract' and getattr(npc, 'interactGUI', None) is not None,
               20, name + ' menu')
        if getattr(npc, 'interactGUI', None) is None:
            return False, 'no menu after the interact'
        yield 1.5
        H.ev('STORE-OPEN', store=name, option=optName, npc=npc.doId, uid=getattr(npc, 'uniqueId', None))
        npc.selectOptionConfirm(option)
        yield ('until', lambda: getattr(npc, 'storeMenuGUI', None) is not None, 15, 'store open')
        gui = getattr(npc, 'storeMenuGUI', None)
        if gui is None or not hasattr(gui, 'pageNumber'):
            return False, 'Store pressed, no store window with a page label (0353: did it crash on open?)'
        yield 2
        if buy:
            bought = yield from buyIn(H, npc, gui, name, log)
        for n in range(0 if buy else 2):
            text = gui.pageNumber['text']
            ok, why, nums = labelOk(text)
            labels.append((text, ok))
            H.ev('STORE-LABEL', n=n, text=text, ok=ok, why=why, nums=nums, store=name, gui=type(gui).__name__,
                 shot=shot(H, '%s-page%d' % (name, n + 1)))
            if n == 0:
                if nums is None or str(nums[1]) in ('1', '1.0'):
                    break                      # one page only: no next arrow to press
                gui.nextPage()
                yield 1.5
    finally:
        if bought is None:
            for u in undo:
                u()
        try:
            if getattr(npc, 'storeMenuGUI', None) is not None:
                npc.storeMenuGUI.closePanel()
        except Exception as e:
            H.ev('STORE-CLOSE', err=repr(e))
        try:
            if la.getGameState() == 'NPCInteract':
                npc.selectOptionConfirm(InteractGlobals.CANCEL)
        except Exception as e:
            H.ev('STORE-CLOSE', err=repr(e))
    yield ('until', lambda: la.getGameState() == 'LandRoam', 20, 'back to LandRoam')
    if buy:
        yield 3                                # the equip the close sent
        for u in undo:
            u()
        if bought is None:
            return False, 'no buy (the store window did not open?)'
        ok, why, check = bought
        if ok:
            ok, why = check()
        H.ev('STORE-WORN', store=name, ok=ok, why=why, shot=shot(H, name + '-worn'))
        return ok, why
    if not labels:
        return False, 'no page label read'
    bad = [t for t, ok in labels if not ok]
    if bad:
        return False, 'label %r' % bad[0]
    return True, 'labels %s' % [t for t, _ in labels]


def run(H):
    la = H.la
    H.ev('PAGES-START', me=la.doId, do=DO, sets=SETS)
    if la.doId == HOST_AV:
        H.ev('FAIL', why='PAGES never runs on Host\'s pirate %d' % HOST_AV); return
    res = {}
    for part in DO:
        fn = {'coll': coll, 'store': store, 'buy': lambda H: store(H, True)}.get(part)
        if fn is None:
            res[part] = (False, 'unknown part')
            continue
        try:
            res[part] = yield from fn(H)
        except Exception:
            import traceback
            res[part] = (False, 'error')
            H.ev('PAGES-ERROR', part=part, tb=traceback.format_exc()[-600:])
        H.ev('PAGES-PART', part=part, ok=res[part][0], why=res[part][1])
    bad = {k: v[1] for k, v in res.items() if not v[0]}
    if bad:
        H.ev('FAIL', why='; '.join('%s: %s' % kv for kv in sorted(bad.items())), parts=res)
    else:
        H.ev('PASS', what='Collections rows straight (0303) / store page label whole (0302)', parts=res)
