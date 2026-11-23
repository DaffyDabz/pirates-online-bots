"""Offline test of s_cargo (CARGO1, row 20, 11-22): the judge and the whole run against a stand-in game, once as the
server was before patch 0412 (leaving the ship by the map sells nothing, the hold stays full) and once with it (the
last pirate off is paid the hold). The pre-0412 game must FAIL ("paid nothing ... hold was kept"), the 0412 game PASS.
Run: python3.9 t_cargo.py <dir holding s_cargo.py>"""
import importlib, os, sys, types

D = os.path.abspath(sys.argv[1])
os.environ['PROOF_SCRIPT'] = os.path.join(D, 'x.py')

# EconomyGlobals' cargo table (client tree, read 11-22): good -> (value, container, rarity)
CRATE, CHEST, SKCHEST = 'crate', 'chest', 'skchest'
TABLE = {'wheat': (5, CRATE, 35), 'cotton': (7, CRATE, 25), 'rum': (9, CRATE, 20), 'iron': (15, CRATE, 10),
         'ivory': (25, CRATE, 5), 'silk': (40, CRATE, 3), 'spices': (90, CRATE, 2), 'copper': (25, CHEST, 75),
         'silver': (50, CHEST, 20), 'gold': (120, CHEST, 5), 'emeralds': (90, SKCHEST, 80),
         'rubies': (140, SKCHEST, 15), 'diamonds': (250, SKCHEST, 5)}
EG = types.ModuleType('pirates.economy.EconomyGlobals')
EG.getCargoValue = lambda g: TABLE.get(g, (0,))[0]
EG.getAllCargoType = lambda c: [g for g, v in TABLE.items() if v[1] == c]
pk = types.ModuleType('pirates'); ek = types.ModuleType('pirates.economy'); ek.EconomyGlobals = EG; pk.economy = ek

state = {'gold': 100, 'gs': 'LandRoam', 'here': 'PR', 'aboard': False}
lanes = types.ModuleType('s_lanes')
lanes.PR = 'PR'
lanes.gold = lambda H: state['gold']


def onIsland(H, step, uid):
    yield 0
    return True
lanes.onIsland = onIsland
sail = types.ModuleType('sailing')
sail.onShip = lambda H: state['aboard']
sail.hereUid = lambda H: state['here']
sf = types.ModuleType('s_shipfight')
sf.FROM = 'PR'
SHIP = types.SimpleNamespace(cargo=[])


def fightRun(H):
    state.update(gs='ShipPilot', aboard=True, here=None)
    yield 1
    H.ev('SHIP-TARGET', foe=5)
    H.ev('FOE-SUNK', foe=5)
    SHIP.cargo = [CRATE, CHEST]        # rollPlunder(level 12) -> addPlunder -> setCargo
    state['gold'] += 264               # 0200's sink gold, before the hold is looked at
    H.ev('PASS', what='sank one enemy ship')
sf.run = fightRun
sys.modules.update({'s_lanes': lanes, 'sailing': sail, 's_shipfight': sf, 'pirates': pk, 'pirates.economy': ek,
                    'pirates.economy.EconomyGlobals': EG})
sys.path.insert(0, D)
C = importlib.import_module('s_cargo')

# 1. the pure parts
assert C.holdRange([CRATE, CHEST], EG) == (5 + 25, 90 + 120)
assert C.holdRange([SKCHEST], EG) == (90, 250)
assert C.holdRange([], EG) == (0, 0)
assert C.soldGold(['hi', 'You sold your plunder for 57 gold!']) == [57]
R = (30, 210)
assert C.judge([CRATE, CHEST], 57, [57], R, []) == ('PASS', 'sold 2 containers for 57 gold')
assert C.judge([CRATE, CHEST], 0, [], R, [CRATE, CHEST])[1].startswith('left the ship with 2 containers aboard and was '
                                                                       'paid nothing')
assert C.judge([], 0, [], (0, 0), None)[1] == 'the sink put nothing in the hold'
assert C.judge([CRATE], 9, [], R, None)[0] == 'FAIL'                      # gold but no line
assert C.judge([CRATE], 9, [10], R, None)[1] == 'the line said 10 gold but the pocket went up 9'
assert C.judge([CRATE], 500, [500], (5, 90), None)[1] == 'paid 500 for 1 containers, whose goods are worth 5 to 90'
assert C.judge([CRATE], 9, [9], (5, 90), [CRATE])[0] == 'FAIL'           # paid but the hold still shows it
assert C.judge([CRATE], 9, [9], (5, 90), None)[0] == 'PASS'              # owner view gone: not judged
assert C.launchSale([CRATE], []) and C.launchSale([CRATE], [9]) is None and C.launchSale([], []) is None


# 2. the run against a stand-in game
def play(patched, how='leave'):
    state.update(gold=100, gs='LandRoam', here='PR', aboard=False)
    SHIP.cargo = []
    evs = []

    class La:
        doId = 100000001
        returnLocation = 'PR'

        def getInventory(self):
            return types.SimpleNamespace(getShipDoIdList=lambda: [42])

        def getGameState(self):
            return state['gs']

        def setSystemMessage(self, aboutId, text):
            pass

        def confirmIslandTeleport(self, why, islandUid=None):
            return islandUid == 'PR'
    la = La()

    def sell():
        if SHIP.cargo:
            got = sum(EG.getCargoValue(EG.getAllCargoType(c)[0]) for c in SHIP.cargo)   # wheat 5 + copper 25
            SHIP.cargo = []
            state['gold'] += got
            la.setSystemMessage(0, 'You sold your plunder for %d gold!' % got)

    def leave(uid):
        # DistributedShipAI._playerDeparted: before 0412 the ship is put away full; with it sellHoldTo pays first
        if patched:
            sell()
        state.update(gs='LandRoam', aboard=False, here=uid)
    cr = types.SimpleNamespace(doId2do={42: SHIP}, getOwnerView=lambda d: SHIP,
                               teleportMgr=types.SimpleNamespace(requestTeleportToIsland=leave))
    H = types.SimpleNamespace(la=la, cr=cr, area=lambda: ('PR',), ev=lambda k, **kw: evs.append((k, kw)))

    def sailTo(H2, uid, why=''):
        yield 1
        sell()                                       # Drop Anchor always sold (dropAnchor -> sellPlunder)
        state.update(gs='LandRoam', aboard=False, here=uid)
        H2.sailResult = True
    sail.sail_to = sailTo
    C.HOW = how
    g = C.run(H)
    try:
        y = next(g)
        for _ in range(200):
            if isinstance(y, tuple) and y and y[0] == 'until':
                y[1]()
            y = g.send(None)
    except StopIteration:
        pass
    C.HOW = 'leave'
    return evs

pre = play(False)
kinds = [k for k, _ in pre]
assert 'SHIPFIGHT-PASS' in kinds and 'CARGO-IN' in kinds, kinds
v = [kw for k, kw in pre if k in ('PASS', 'FAIL')]
assert len(v) == 1 and [k for k, _ in pre][-1] == 'FAIL', pre[-3:]
assert 'was paid nothing' in v[0]['why'], v
print('pre-0412 game: FAIL -', v[0]['why'])

post = play(True)
v = [(k, kw) for k, kw in post if k in ('PASS', 'FAIL')]
assert len(v) == 1 and v[0][0] == 'PASS', post[-4:]
sold = [kw for k, kw in post if k == 'SOLD'][0]
assert sold['gain'] == 30 and sold['sold'] == [30] and sold['cargoAfter'] == [], sold
cin = [kw for k, kw in post if k == 'CARGO-IN'][0]
assert cin['n'] == 2 and cin['worth'] == (30, 210), cin
assert [kw for k, kw in post if k == 'LAUNCH-SALE'][0]['ok'] is True
print('0412 game: PASS -', v[0][1]['why'])

anc = play(False, 'anchor')
v = [(k, kw) for k, kw in anc if k in ('PASS', 'FAIL')]
assert len(v) == 1 and v[0][0] == 'PASS', anc[-4:]
assert [kw for k, kw in anc if k == 'CARGO-HOME'][0]['how'] == 'anchor'
print('Drop Anchor: PASS -', v[0][1]['why'])
print('cargo ok')
