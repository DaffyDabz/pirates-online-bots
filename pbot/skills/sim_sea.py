"""Sim for pbot/skills/sea.py (boats lane, 11-22): no game, no server. Run: python -I sim_sea.py

FAIL-BEFORE / PASS-AFTER (FLAGSHIP2, row 23 parked): the AnyShip hunt (s_shipfight.Picker + s_shipquest.matches)
counts a flagship as a target; sea.fairPicker's match refuses it, and s_shipquest is restored after the fight.
Then the skill's own parts: choose() bands and modes, nextPort, streakAfter, tradeDue, outingOk, PlayerH (renames,
Blocked), drive (until -> upto + SEA-WAIT, the monster look closes the hunt), flow() turning a crash into one BOT bug
and cut()."""
import os, sys, types

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, os.path.dirname(HERE), HARNESS):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ['PROOF_SCRIPT'] = os.path.join(HARNESS, 'x.py')

# --- stand-ins for the game-side helpers s_shipfight imports at the top (they need panda3d)
PR, TORTUGA = '1150922126.8dzlu', '1156207188.95dzlu'
lanes = types.ModuleType('s_lanes')
lanes.PR, lanes.TORTUGA = PR, TORTUGA
lanes.gold = lambda H: 0
sail = types.ModuleType('sailing')
sail.islands = lambda: {PR: ('Port Royal', 0.0, 0.0, 'pr'), TORTUGA: ('Tortuga', 9000.0, 0.0, 'tt')}
sail.hereUid = lambda H: getattr(H, 'here', None)
sail.onShip = lambda H: getattr(H, 'aboard', False)
sq = types.ModuleType('s_shipquest')


def matches(task, o):
    """s_shipquest.matches' own tests, minus the game's faction classes (o.faction stands in for factionOf)."""
    f = getattr(o, 'faction', None)
    if f is None:
        return False, 'no faction'
    tf = getattr(task, 'faction', None)
    if tf is not None and f != tf:
        return False, 'faction'
    if getattr(task, 'isFlagship', False) and not getattr(o, 'isFlagship', False):
        return False, 'not a flagship'
    return True, 'ok'


sq.matches = matches
sq.npcShips = lambda H, ship: []
sq.wantBearing = None
sq.PATROL_R = 5500
sq.LOST = None
for name, mod in (('s_lanes', lanes), ('sailing', sail), ('s_shipquest', sq)):
    sys.modules[name] = mod

import s_shipfight as SF    # noqa: E402
import sea                  # noqa: E402

fails = []


def check(name, ok, got=None):
    print('%-4s %s%s' % ('ok' if ok else 'FAIL', name, '' if ok else '   got %r' % (got,)))
    if not ok:
        fails.append(name)


class Ship:
    def __init__(self, doId, faction, flag=False):
        self.doId, self.faction, self.isFlagship = doId, faction, flag


fl = [(900, Ship(201, 'navy')), (1200, Ship(202, 'navy', flag=True)), (1500, Ship(203, 'ett')), (800, Ship(204, None))]

# --- 1. FAIL-BEFORE: the old AnyShip hunt counts the flagship
old = SF.questIds(fl, SF.AnyShip(), sq.matches)
check('before: AnyShip hunt counts flagship 202 (FLAGSHIP2, the bug)', 202 in old, old)
new = SF.questIds(fl, SF.AnyShip(), sea.fairMatch(sq.matches))
check('after: fairMatch leaves flagship 202 out', 202 not in new and new == {201, 203}, new)
check('after: the refusal says why', 'flagship' in sea.fairMatch(sq.matches)(SF.AnyShip(), fl[1][1])[1])


class FakeH:
    here, aboard = PR, False
    render = None

    def __init__(self):
        self.evs = []

    def ev(self, name, /, **kw):          # as walker.py's ev
        self.evs.append((name, kw))

    def area(self):
        return ('DistributedIsland', self.here)


H = FakeH()
plain = SF.Picker(H, 0, task=SF.AnyShip())
with plain:
    check('before: Picker without the fair test lets 202 through', sq.matches(SF.AnyShip(), fl[1][1])[0] in (True, False)
          and plain.saved[1](SF.AnyShip(), fl[1][1])[0], plain.saved[1](SF.AnyShip(), fl[1][1]))
fp = sea.fairPicker(SF)(H, 0, task=SF.AnyShip())
with fp:
    check('after: FairPicker swapped s_shipquest.matches', sq.matches == fp.matches)
    check('after: FairPicker refuses 202 inside the fight', not fp.saved[1](SF.AnyShip(), fl[1][1])[0])
    check('after: FairPicker still takes navy 201', fp.saved[1](SF.AnyShip(), fl[0][1])[0])
check('after: s_shipquest.matches restored on exit', sq.matches is matches, sq.matches)
check('after: fair pick is per fight (a second Picker still sees the real match)', fp.saved[1] is matches)

# --- 2. choose()
base = dict(crew=False, down=False, gs='LandRoam', island=PR, ships=[5], canBuy=False, canLaunch=True, bad=0,
            restLeft=0, dead=None)
c = sea.choose(base)
check('choose: hunt at 30 in the FREE PLAY band', c and c[0] == 30 and c[2] == 'hunt' and 10 <= c[0] <= 39, c)
check('choose: hop at 15 after 2 bad outings', (sea.choose(dict(base, bad=2)) or (0, 0, 0))[::2] == (15, 'hop'))
check('choose: buy when no ship and he can pay', (sea.choose(dict(base, ships=[], canBuy=True)) or (0, 0, 0))[2] == 'buy')
for k, v in (('crew', True), ('down', True), ('dead', 'x'), ('gs', 'ShipPilot'), ('island', None), ('restLeft', 30),
             ('canLaunch', False)):
    check('choose: None when %s=%r' % (k, v), sea.choose(dict(base, **{k: v})) is None)
check('choose: None with no ship and no gold', sea.choose(dict(base, ships=[], canBuy=False)) is None)

# --- 3. the small pure parts
check('nextPort PR->Tortuga->PR, elsewhere->PR', (sea.nextPort(PR), sea.nextPort(TORTUGA), sea.nextPort('x'))
      == (TORTUGA, PR, PR))
check('streakAfter: a sink resets, a timeout keeps, a break-off adds',
      (sea.streakAfter(1, 'foe-sunk'), sea.streakAfter(1, 'timeout'), sea.streakAfter(1, 'break-off'),
       sea.streakAfter(1, 'our-ship-sunk')) == (0, 1, 2, 2))
check('tradeDue: only at Tortuga with Sailing and gold',
      (sea.tradeDue(TORTUGA, True, 1000, 900, 500, 5, 5), sea.tradeDue(PR, True, 1000, 900, 500, 5, 5),
       sea.tradeDue(TORTUGA, True, 1000, 900, 500, 4, 5), sea.tradeDue(TORTUGA, False, 1000, 900, 500, 5, 5))
      == (True, False, False, False))
ok1 = dict(res='good', why='foe-sunk', launched=True, docked=True, flagPicks=0)
check('outingOk: launched, sank, docked', sea.outingOk(ok1))
check('outingOk: sunk then ashore counts', sea.outingOk(dict(ok1, why='our-ship-sunk', docked=False, ashore=True)))
check('outingOk: refuses a flagship pick', not sea.outingOk(dict(ok1, flagPicks=1)))
check('outingOk: refuses never launched', not sea.outingOk(dict(ok1, launched=False)))
check('outingOk: refuses still at sea', not sea.outingOk(dict(ok1, docked=False)))
check('outingOk: refuses a BOT crash', not sea.outingOk(dict(ok1, res='bot')))

# --- 4. PlayerH
H = FakeH()
PH = sea.PlayerH(H)
for n in ('PASS', 'FAIL', 'STALL', 'CREW-X', 'PBOT-Y', 'FOE-PICK'):
    PH.ev(n, why='w')
check('PlayerH: reserved names renamed SEA-', [e[0] for e in H.evs] ==
      ['SEA-PASS', 'SEA-FAIL', 'SEA-STALL', 'SEA-CREW-X', 'SEA-PBOT-Y', 'FOE-PICK'], [e[0] for e in H.evs])
check('PlayerH: verdict and stalls kept', PH.verdict == ('FAIL', 'w') and PH.stalls == 1, (PH.verdict, PH.stalls))
try:
    PH.mw('gold 500')
    check('PlayerH: mw raises Blocked', False)
except sea.Blocked:
    check('PlayerH: mw raises Blocked + SEA-MW-BLOCKED', PH.blocked == 'gold 500' and H.evs[-1][0] == 'SEA-MW-BLOCKED')
try:
    PH.ev('HOME-PICK', name='Port Royal', port=PR)          # s_shipfight.repairAt's own line
    check('PlayerH: an event with its own name= field', H.evs[-1] == ('HOME-PICK', {'name': 'Port Royal', 'port': PR}),
          H.evs[-1])
except TypeError as e:
    check('PlayerH: an event with its own name= field', False, repr(e))
PH.snap('x')
check('PlayerH: snap is only an event', H.evs[-1][0] == 'SEA-SNAP')


# --- 5. drive
def run_gen(g):
    """Drive a skill generator as the brain does: 'upto' waits are answered at once."""
    try:
        item = next(g)
        while True:
            item = g.send(None)
    except StopIteration as e:
        return e.value


def waiter():
    yield ('until', lambda: False, 5, 'never')
    yield 1
    return 'fine'


H = FakeH()
seen = []


def spy(g):
    for item in g:
        seen.append(item)
    return None


g = sea.drive(waiter(), H)
items = []
try:
    while True:
        items.append(next(g))
except StopIteration as e:
    res = e.value
check('drive: until becomes upto', items[0][0] == 'upto' and items[1] == 1, items)
check('drive: a run-out wait writes SEA-WAIT', ('SEA-WAIT', {'what': 'never', 'secs': 5}) in H.evs, H.evs)
check('drive: returns the value', res == ('done', 'fine'), res)

closed = []


def hunt():
    try:
        while True:
            yield 1
    finally:
        closed.append(1)


g = sea.drive(hunt(), H, look=lambda: 'Kraken', every=0)
res = run_gen(g)
check('drive: a monster in view stops the hunt', res == ('stopped', 'Kraken'), res)
check('drive: the hunt was closed', closed == [1])


# --- 6. flow(): a crash inside the outing is one BOT bug, the event hook is gone, the skill rests
class Inv:
    def getShipDoIdList(self):
        return [7]

    def getGoldInPocket(self):
        return 100


class La:
    doId = 100001076

    def getGameState(self):
        return 'LandRoam'

    def getInventory(self):
        return Inv()


class Bot:
    def __init__(self):
        self.H = FakeH()
        self.la = self.H.la = La()
        self.cr = None
        self.bugs = []

    def captain(self):
        return None

    def gs(self):
        return 'LandRoam'

    def down(self):
        return False

    def bug(self, kind, key, tag, what, tb=''):
        self.bugs.append((kind, key, tag))


bot = Bot()
sk = sea.Sea(bot)
sk.canLaunch = lambda la, sid: True


def boom(H, mode, out):
    H.ev = lambda *a, **k: None          # as _hunt does
    yield 1
    raise KeyError('x')


sk._outing = boom
out = run_gen(sk.flow())
check('flow: crash -> res bot', out['res'] == 'bot' and 'KeyError' in out['why'], out)
check('flow: one BOT traceback bug, key sea-crash-...', bot.bugs == [('traceback', 'sea-crash-keyerror-boom', 'BOT')],
      bot.bugs)
check('flow: the outing hook is gone', 'ev' not in sk.PH.__dict__)
check('flow: the skill rests after a crash', sk.want() is None and sk.restUntil > 0)
check('flow: SEA-OUTING start and end written', [e[0] for e in bot.H.evs if e[0] == 'SEA-OUTING'] ==
      ['SEA-OUTING', 'SEA-OUTING'])

# --- 7. cut()
sk2 = sea.Sea(Bot())
check('cut down: nothing acts', sk2.cut('down') is None)
g = sk2.cut('crew')
check('cut crew: a new cleanup generator', g is not None and hasattr(g, 'send'))
check('cut limit: the skill rests', (sk2.cut('limit') is not None) and sk2.restUntil > 0)
check('Sea: interface shape', (sea.Sea.name, sea.Sea.limit, sea.Sea.crewOk) == ('sea', 1200, False))

print('\n%s: %d failed' % ('PASS' if not fails else 'FAIL', len(fails)))
sys.exit(1 if fails else 0)
