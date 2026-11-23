"""SHOP (pir-bot, 11-17): buy one item at a shop, like a player. For the lanes that need a purchase in a run.

Walk to a shopkeeper (held keys, through doors), press the interact on him, press Store on his menu, add the cheapest
item he sells that the pirate may buy to the cart (the shop's own buy button: StoreGUI.handleBuyItem), press
Purchase (StoreGUI.handleCommitPurchase -> 'makeSale' -> DistributedShopKeeper.requestMakeSale), then Goodbye.

Client facts this rests on (client tree, read 11-17):
- Every townsperson is a DistributedNPCTownfolk (a DistributedShopKeeper). Its shop shelf (shopInventory) comes from
  its avatar type in DistributedShopKeeper.announceGenerate: Gypsy = tonics + mojo, Gunsmith = pistols / ammo /
  bombs, Blacksmith = blades, Bartender = level 1 weapons + bombs. The Store button is lit when the shelf is not empty.
- b_selectOption(STORE) opens the StoreGUI on the client (selectOption -> startShopping) and tells the server.
- The server's answer is makeSaleResponse(result): 2 = sold (gold taken, stack raised), OVERFLOW = no room,
  TIMEOUT = too dear / no inventory; anything else = failed.

SHOP_AT picks the shop (default gypsy: Port Royal's open ground, no door; tonics cost 3+ gold):
  gypsy      Port Royal open ground   1175553664.0dxschafe  (117.7, -1469.4, 19.7)
  gunsmith   Port Royal weapons shop  1169079172.34sdnaik   (15.3, -16.2, 0)    interior 1153423448.14dzlu0
  bartender  Port Royal tavern        1181348864.0dxschafe  (-12.9, 34.6, 1)    interior 1153419689.81dzlu0
  tgypsy     Tortuga open ground      1165199931.31Shochet  (-90.7, 4.1, 11.6)
SHOP_ITEM = an ItemId number to buy that one (else the cheapest allowed). SHOP_RESERVE = gold never spent (0).
SHOP_GOLD=1: when the pirate cannot pay for even the cheapest item, the one magic word 'gold <n>', logged MW-GOLD.

Lines: SHOP-START, STAGE step=shop what=at-island / at-shopkeeper / menu / store-open / in-cart / bought / left,
SHOP-ITEMS (the shelf, each with cost and why it can or cannot be bought), SHOP-PICK, SHOP-CART, SHOP-BUY,
SHOP-RESPONSE result=.., SHOP-BOUGHT (gold before/after, stack before/after), SHOP-LEAVE, then PASS / FAIL."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402
import s_story   # noqa: E402

PR, TORTUGA = s_lanes.PR, s_lanes.TORTUGA
# name -> (island uid, area uid where he stands, his world uid, his area-local pos)
SHOPS = {
    'gypsy': (PR, PR, '1175553664.0dxschafe', (117.7, -1469.4, 19.7)),
    'gunsmith': (PR, '1153423448.14dzlu0', '1169079172.34sdnaik', (15.3, -16.2, 0.0)),
    'bartender': (PR, '1153419689.81dzlu0', '1181348864.0dxschafe', (-12.9, 34.6, 1.0)),
    'tgypsy': (TORTUGA, TORTUGA, '1165199931.31Shochet', (-90.7, 4.1, 11.6)),
}
AT = os.environ.get('SHOP_AT', 'gypsy')
ITEM = int(os.environ.get('SHOP_ITEM', '0') or 0)
RESERVE = int(os.environ.get('SHOP_RESERVE', '0'))
WANT_GOLD = os.environ.get('SHOP_GOLD', '0') == '1'
TALK = 8.0         # ft: inside the townfolk's 12 ft interact sphere
FIND_R = 40.0      # ft round his spot: the live shopkeeper (he may patrol up to 12 ft)


def pickItem(rows, gold, reserve=0, want=0):
    """Pure. rows = [(itemId, cost, ok, why)] -> the row to buy, or None: `want` when it is on the shelf and allowed,
    else the cheapest allowed row the gold (above reserve) covers."""
    room = gold - reserve
    good = [r for r in rows if r[2] and r[1] is not None and r[1] <= room]
    if want:
        good = [r for r in good if r[0] == want]
    return min(good, key=lambda r: (r[1], r[0])) if good else None


def canBuy(la, itemId, cart=0):
    """(cost, ok, why) for one shelf item: the same checks StoreGUI.handleBuyItem makes before it adds to the cart
    (training, weapon level, already owned, stack full), plus the price."""
    from pirates.economy import EconomyGlobals as EG
    from pirates.battle import WeaponGlobals
    from pirates.reputation import ReputationGlobals
    ItemType = EG.ItemType   # ItemType lives in EconomyGlobals, not UberDogGlobals
    inv = la.getInventory()
    cost = EG.getItemCost(itemId)
    if cost is None:
        return None, False, 'no price'
    if inv is None:
        return cost, False, 'no inventory'
    tr = EG.getItemTrainingReq(itemId)
    if tr and not inv.getStackQuantity(tr):
        return cost, False, 'needs training %s' % tr
    try:
        repId = WeaponGlobals.getRepId(itemId)
        lvl = ReputationGlobals.getLevelFromTotalReputation(repId, inv.getAccumulator(repId))[0]
    except Exception:
        lvl = 99
    if EG.getItemMinLevel(itemId) > lvl:
        return cost, False, 'level %s < %s' % (lvl, EG.getItemMinLevel(itemId))
    stock = inv.getStackQuantity(itemId) or 0
    if EG.getItemCategory(itemId) == ItemType.WEAPON and stock >= 1:
        return cost, False, 'owns this weapon'
    if stock + cart >= inv.getStackLimit(itemId):
        return cost, False, 'stack full %s/%s' % (stock, inv.getStackLimit(itemId))
    return cost, True, 'ok'


def run(H):
    from pirates.piratesgui import PiratesGuiGlobals
    from pirates.piratesbase import PiratesGlobals  # noqa: F401  (the store GUI needs it loaded)
    from pirates.distributed import InteractGlobals
    la, cr = H.la, H.cr
    isl, area, uid, pos = SHOPS[AT]
    H.ev('SHOP-START', at=AT, shop=uid, area=area, gold=s_lanes.gold(H), here=H.area())
    if not (yield from s_lanes.onIsland(H, 'shop', isl)):
        H.ev('FAIL', why='could not get to the shop island %s' % isl, area=H.area()); return
    s_lanes.stage(H, 'shop', 'at-island', island=isl)

    # 1. walk to his spot (through the shop's door when he is inside)
    r = yield from s_lanes.walkTo(H, 'shop', lambda st: s_story.goto(H, st, area, pos=pos, arrive=TALK, tag='to-shop'),
                                  240, 'the shopkeeper')
    if r is None:
        H.ev('FAIL', why='could not walk to the shopkeeper', at=AT, la=H.P(la), area=H.area()); return
    org = s_story.areaObj(H, area)
    spot = H.render.getRelativePoint(org, __import__('panda3d.core', fromlist=['Point3']).Point3(*pos)) if org else la.getPos(H.render)

    def keeper():
        live = [o for o in list(cr.doId2do.values()) if type(o).__name__ == 'DistributedNPCTownfolk'
                and getattr(o, 'shopInventory', None) and hasattr(o, 'getPos')]
        byUid = [o for o in live if getattr(o, 'uniqueId', None) == uid]
        if byUid:
            return byUid[0]
        live = [o for o in live if (o.getPos(H.render) - spot).length() < FIND_R]
        return min(live, key=lambda o: (o.getPos(H.render) - spot).length()) if live else None
    yield ('until', lambda: keeper() is not None, 20, 'shopkeeper in view')
    npc = keeper()
    if npc is None:
        H.ev('FAIL', why='no shopkeeper with a shelf within %d ft of his spot' % FIND_R, at=AT, la=H.P(la)); return
    r = yield from s_lanes.walkTo(H, 'shop', lambda st: True if s_story.near(H, npc, TALK, st, tag='shopkeeper')
                                  else 'walk-to-shopkeeper', 60, 'the shopkeeper')
    if r is None:
        H.ev('FAIL', why='could not reach the shopkeeper', npc=npc.doId, d=round(s_story.hdist(H, npc), 1)); return
    H.walk_cancel()
    s_lanes.stage(H, 'shop', 'at-shopkeeper', npc=npc.doId, type=str(getattr(npc, 'avatarType', None)),
                  d=round(s_story.hdist(H, npc), 1), shelf=len(npc.shopInventory))

    # 2. what can be bought, and pick one (gold first, if asked and needed)
    rows = []
    for it in npc.shopInventory:
        c, ok, why = canBuy(la, it)
        rows.append((it, c, ok, why))
    H.ev('SHOP-ITEMS', npc=npc.doId, items=[list(r) for r in rows], gold=s_lanes.gold(H))
    pick = pickItem(rows, s_lanes.gold(H), RESERVE, ITEM)
    if pick is None and WANT_GOLD:
        cheap = pickItem(rows, 10 ** 9, 0, ITEM)
        if cheap is not None:
            H.ev('MW-GOLD', why='the test pirate cannot pay %d for item %s' % (cheap[1], cheap[0]), gold=s_lanes.gold(H))
            H.mw('gold %d' % (s_lanes.gold(H) + cheap[1] + RESERVE + 10))
            yield ('until', lambda: s_lanes.gold(H) >= cheap[1] + RESERVE, 10, 'shop gold')
            pick = pickItem(rows, s_lanes.gold(H), RESERVE, ITEM)
    if pick is None:
        H.ev('FAIL', why='nothing on the shelf he can buy (gold %d, reserve %d, want %s)' % (s_lanes.gold(H), RESERVE, ITEM or 'any'))
        return
    itemId, cost = pick[0], pick[1]
    inv = la.getInventory()
    g0, s0 = s_lanes.gold(H), inv.getStackQuantity(itemId) or 0
    H.ev('SHOP-PICK', item=itemId, cost=cost, gold=g0, stack=s0)

    resp = {}
    orig = npc.makeSaleResponse

    def msr(result, *a):
        resp['r'] = result
        H.ev('SHOP-RESPONSE', result=result, sold=result == 2)
        return orig(result, *a)
    npc.makeSaleResponse = msr

    try:
        # 3. talk, then the Store button
        npc.requestInteraction(la.doId)          # the interact key on his "talk" prompt
        yield ('until', lambda: la.getGameState() == 'NPCInteract' and getattr(npc, 'interactGUI', None) is not None, 20, 'shop menu')
        if getattr(npc, 'interactGUI', None) is None:
            H.ev('FAIL', why='no menu after the interact (20 s)', gs=la.getGameState()); return
        s_lanes.stage(H, 'shop', 'menu', npc=npc.doId)
        yield 1.5                                 # his greeting plays; a player reads it and clicks
        npc.selectOptionConfirm(InteractGlobals.STORE)
        yield ('until', lambda: getattr(npc, 'storeMenuGUI', None) is not None, 10, 'store open')
        gui = getattr(npc, 'storeMenuGUI', None)
        if gui is None:
            H.ev('FAIL', why='Store pressed, no store window', gs=la.getGameState()); return
        s_lanes.stage(H, 'shop', 'store-open', npc=npc.doId)
        yield 1

        # 4. the item's buy button, then Purchase
        qty = __import__('pirates.economy.EconomyGlobals', fromlist=['getItemQuantity']).getItemQuantity(itemId)
        gui.handleBuyItem([itemId, qty], PiratesGuiGlobals.InventoryAdd)
        cart = list(getattr(gui.purchaseInventory, 'inventory', []) or [])
        H.ev('SHOP-CART', cart=cart, balance=getattr(gui, 'balance', None))
        if not cart:
            H.ev('FAIL', why='the item did not go into the cart (a store warning says why)', item=itemId); return
        s_lanes.stage(H, 'shop', 'in-cart', item=itemId, cost=cost)
        yield 1
        H.ev('SHOP-BUY', item=itemId, qty=qty, cost=cost, gold=s_lanes.gold(H))
        gui.handleCommitPurchase()
        yield ('until', lambda: 'r' in resp, 15, 'sale answer')
        yield ('until', lambda: s_lanes.gold(H) != g0 or (inv.getStackQuantity(itemId) or 0) != s0, 5, 'gold / stack change')
        g1, s1 = s_lanes.gold(H), inv.getStackQuantity(itemId) or 0
        H.ev('SHOP-BOUGHT', item=itemId, goldBefore=g0, goldAfter=g1, stackBefore=s0, stackAfter=s1, result=resp.get('r'))
        if resp.get('r') == 2 and g1 == g0 - cost and s1 > s0:
            s_lanes.stage(H, 'shop', 'bought', item=itemId)
    finally:
        npc.makeSaleResponse = orig
        # Goodbye: the menu's Cancel button (the store already closed itself after the sale)
        if la.getGameState() == 'NPCInteract':
            H.ev('SHOP-LEAVE', npc=npc.doId)
            try:
                if getattr(npc, 'storeMenuGUI', None) is not None:
                    npc.storeMenuGUI.closePanel()
                npc.selectOptionConfirm(InteractGlobals.CANCEL)
            except Exception as e:
                H.ev('SHOP-LEAVE', err=repr(e))
    yield ('until', lambda: la.getGameState() == 'LandRoam', 20, 'back to LandRoam')
    s_lanes.stage(H, 'shop', 'left', ok=la.getGameState() == 'LandRoam')
    if resp.get('r') != 2:
        H.ev('FAIL', why='the server did not sell (makeSaleResponse %s)' % resp.get('r'), item=itemId); return
    if not (g1 == g0 - cost and s1 > s0):
        H.ev('FAIL', why='sold, but gold %d->%d (cost %d) / stack %d->%d' % (g0, g1, cost, s0, s1)); return
    H.ev('PASS', what='bought one item at a shop', at=AT, item=itemId, cost=cost, gold=[g0, g1], stack=[s0, s1])
