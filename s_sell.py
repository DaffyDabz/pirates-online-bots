"""SELL (games lane, 11-22, PLAYERBOTS row 49): sell spare stock back to a shopkeeper, like a player.

The store window of this client never sends a sell list (StoreGUI.handleCommitPurchase always sends
'makeSale' [cart, [], []]), but the server buys back: DistributedShopKeeperAI.requestMakeSale walks the selling list
through __sellItem (the item must be in the pirate's stack, never a ship; pays int(cost x quantity / 2), answers 2).
So the bot does what the store's Purchase button does, with the selling list filled: walk to the shopkeeper, talk,
press Store, then the same 'makeSale' message with [[], [[itemId, qty]], []].

What it sells: one pack (EconomyGlobals.getItemQuantity) of the item on that shopkeeper's shelf he can spare most
gold from, and only when he keeps at least one pack of it. Never a weapon, a pouch or a ship. A shopkeeper buys back
only what his own shelf sells (DistributedShopKeeper.announceGenerate): the gypsy tonics, the gunsmith shot, grenades
and cannon ammo (SHELVES). SELL_AT = gypsy / gunsmith (default: the shop that buys the most of what he can spare).

Lines: SELL-START (what he could sell where), STAGE step=sell what=at-island / at-shopkeeper / menu / store-open /
sold / left, SELL-PICK, SELL-OFFER, SELL-RESPONSE result=.., SELL-SOLD (gold and stack before/after), SELL-LEAVE,
then PASS / FAIL ('nothing to sell' = he has no spare pack: not a bug)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402
import s_story   # noqa: E402
import s_shop    # noqa: E402

# who buys what back: the EconomyGlobals shelf lists on his shelf (pouches and weapons left out)
SHELVES = {
    'gypsy': ('TONIC_SHELF_L1', 'TONIC_SHELF_L2'),
    'gunsmith': ('PISTOL_AMMO_SHELF_L1', 'PISTOL_AMMO_SHELF_L2', 'BOMB_AMMO_SHELF_L1', 'BOMB_AMMO_SHELF_L2',
                 'CANNON_AMMO_SHELF_L1', 'CANNON_AMMO_SHELF_L2'),
}
AT = os.environ.get('SELL_AT', '')


def pickSale(rows):
    """Pure. rows = [(itemId, stack, pack, cost)] -> (itemId, qty, price) worth the most gold, selling one pack and
    keeping at least one pack; None when nothing is spare."""
    best = None
    for itemId, stack, pack, cost in rows:
        pack = max(int(pack or 1), 1)
        if not cost or (stack or 0) < 2 * pack:
            continue
        price = int(cost * pack / 2)
        if price < 1:
            continue
        if best is None or (price, -itemId) > (best[2], -best[0]):
            best = (itemId, pack, price)
    return best


def stock(la, ids):
    """[(itemId, stack, pack, cost)] for the items of ids he holds that a shop may buy (no weapon, no ship)."""
    from pirates.economy import EconomyGlobals as EG
    inv = la.getInventory()
    if inv is None:
        return []
    out = []
    for it in ids:
        if it in getattr(EG, 'SHIP_SHELF', ()) or EG.getItemCategory(it) == EG.ItemType.WEAPON:
            continue
        n = inv.getStackQuantity(it) or 0
        if n:
            out.append((it, n, EG.getItemQuantity(it) or 1, EG.getItemCost(it)))
    return out


def shelf(at):
    from pirates.economy import EconomyGlobals as EG
    return [i for n in SHELVES.get(at, ()) for i in getattr(EG, n, [])]


def chooseShop(la, at=''):
    """-> (at, pick, {at: pick}): the shop that pays the most for one spare pack (or `at`)."""
    picks = {a: pickSale(stock(la, shelf(a))) for a in ([at] if at else SHELVES)}
    good = [(p[2], a) for a, p in picks.items() if p]
    a = max(good)[1] if good else (at or 'gypsy')
    return a, picks.get(a), picks


def run(H):
    from pirates.distributed import InteractGlobals
    la, cr = H.la, H.cr
    at, pick, picks = chooseShop(la, AT)
    H.ev('SELL-START', at=at, picks={a: list(p) if p else None for a, p in picks.items()}, gold=s_lanes.gold(H),
         here=H.area())
    if pick is None:
        H.ev('FAIL', why='nothing to sell (no spare pack of anything %s buys back)' % at, at=at); return
    isl, area, uid, pos = s_shop.SHOPS[at]
    if not (yield from s_lanes.onIsland(H, 'sell', isl)):
        H.ev('FAIL', why='could not get to the shop island %s' % isl, area=H.area()); return
    s_lanes.stage(H, 'sell', 'at-island', island=isl)

    # 1. walk to him (through the shop's door when he is inside), as s_shop does
    r = yield from s_lanes.walkTo(H, 'sell', lambda st: s_story.goto(H, st, area, pos=pos, arrive=s_shop.TALK,
                                                                      tag='to-shop'), 240, 'the shopkeeper')
    if r is None:
        H.ev('FAIL', why='could not walk to the shopkeeper', at=at, la=H.P(la), area=H.area()); return
    org = s_story.areaObj(H, area)
    spot = H.render.getRelativePoint(org, __import__('panda3d.core', fromlist=['Point3']).Point3(*pos)) if org else la.getPos(H.render)

    def keeper():
        live = [o for o in list(cr.doId2do.values()) if type(o).__name__ == 'DistributedNPCTownfolk'
                and getattr(o, 'shopInventory', None) and hasattr(o, 'getPos')]
        byUid = [o for o in live if getattr(o, 'uniqueId', None) == uid]
        if byUid:
            return byUid[0]
        live = [o for o in live if (o.getPos(H.render) - spot).length() < s_shop.FIND_R]
        return min(live, key=lambda o: (o.getPos(H.render) - spot).length()) if live else None
    yield ('until', lambda: keeper() is not None, 20, 'shopkeeper in view')
    npc = keeper()
    if npc is None:
        H.ev('FAIL', why='no shopkeeper with a shelf within %d ft of his spot' % s_shop.FIND_R, at=at); return
    r = yield from s_lanes.walkTo(H, 'sell', lambda st: True if s_story.near(H, npc, s_shop.TALK, st, tag='shopkeeper')
                                  else 'walk-to-shopkeeper', 60, 'the shopkeeper')
    if r is None:
        H.ev('FAIL', why='could not reach the shopkeeper', npc=npc.doId, d=round(s_story.hdist(H, npc), 1)); return
    H.walk_cancel()
    s_lanes.stage(H, 'sell', 'at-shopkeeper', npc=npc.doId, type=str(getattr(npc, 'avatarType', None)),
                  shelf=len(npc.shopInventory))

    # 2. what HIS shelf buys back (the live shelf decides)
    pick = pickSale(stock(la, [i for i in npc.shopInventory]))
    if pick is None:
        H.ev('FAIL', why='nothing to sell to this shopkeeper (no spare pack of his shelf)', npc=npc.doId); return
    itemId, qty, price = pick
    inv = la.getInventory()
    g0, s0 = s_lanes.gold(H), inv.getStackQuantity(itemId) or 0
    H.ev('SELL-PICK', item=itemId, qty=qty, price=price, gold=g0, stack=s0)

    resp = {}
    orig = npc.makeSaleResponse

    def msr(result, *a):
        resp['r'] = result
        H.ev('SELL-RESPONSE', result=result, sold=result == 2)
        return orig(result, *a)
    npc.makeSaleResponse = msr
    g1 = s1 = None
    try:
        # 3. talk, the Store button, then the store's own 'makeSale' message with the selling list filled
        npc.requestInteraction(la.doId)
        yield ('until', lambda: la.getGameState() == 'NPCInteract' and getattr(npc, 'interactGUI', None) is not None, 20, 'shop menu')
        if getattr(npc, 'interactGUI', None) is None:
            H.ev('FAIL', why='no menu after the interact (20 s)', gs=la.getGameState()); return
        s_lanes.stage(H, 'sell', 'menu', npc=npc.doId)
        yield 1.5
        npc.selectOptionConfirm(InteractGlobals.STORE)
        yield ('until', lambda: getattr(npc, 'storeMenuGUI', None) is not None, 10, 'store open')
        if getattr(npc, 'storeMenuGUI', None) is None:
            H.ev('FAIL', why='Store pressed, no store window', gs=la.getGameState()); return
        s_lanes.stage(H, 'sell', 'store-open', npc=npc.doId)
        yield 1
        H.ev('SELL-OFFER', item=itemId, qty=qty, price=price, gold=g0, stack=s0)
        messenger.send('makeSale', [[], [[itemId, qty]], []])   # noqa: F821 (the game's builtin)
        yield ('until', lambda: 'r' in resp, 15, 'sale answer')
        yield ('until', lambda: s_lanes.gold(H) != g0 or (inv.getStackQuantity(itemId) or 0) != s0, 5, 'gold / stack change')
        g1, s1 = s_lanes.gold(H), inv.getStackQuantity(itemId) or 0
        H.ev('SELL-SOLD', item=itemId, goldBefore=g0, goldAfter=g1, stackBefore=s0, stackAfter=s1, result=resp.get('r'))
        if resp.get('r') == 2 and g1 == g0 + price and s1 == s0 - qty:
            s_lanes.stage(H, 'sell', 'sold', item=itemId)
    finally:
        npc.makeSaleResponse = orig
        if la.getGameState() == 'NPCInteract':
            H.ev('SELL-LEAVE', npc=npc.doId)
            try:
                if getattr(npc, 'storeMenuGUI', None) is not None:
                    npc.storeMenuGUI.closePanel()
                npc.selectOptionConfirm(InteractGlobals.CANCEL)
            except Exception as e:
                H.ev('SELL-LEAVE', err=repr(e))
    yield ('until', lambda: la.getGameState() == 'LandRoam', 20, 'back to LandRoam')
    s_lanes.stage(H, 'sell', 'left', ok=la.getGameState() == 'LandRoam')
    if resp.get('r') != 2:
        H.ev('FAIL', why='the server did not buy it back (makeSaleResponse %s)' % resp.get('r'), item=itemId); return
    if not (g1 == g0 + price and s1 == s0 - qty):
        H.ev('FAIL', why='sold, but paid wrong: gold %d->%d (price %d) / stack %d->%d' % (g0, g1, price, s0, s1)); return
    H.ev('PASS', what='sold one spare pack back to a shop', at=at, item=itemId, qty=qty, price=price, gold=[g0, g1],
         stack=[s0, s1])
