"""Offline test of s_story.leaveRoom (MAIN7, 11-21): inside the Tortuga tavern on c3r2.5.5visitOrinda the server gave
no quest step for 6 min (goal outdoors) and the bot only re-asked. With no step for NOSTEP_OUT s inside a building he
now walks out the room's nearest door; outdoors or in the jail it does nothing.
Run: python3.9 t_story_leaveroom.py <dir holding s_story.py>"""
import importlib, os, sys, tempfile, types

D = os.path.abspath(sys.argv[1])
T = tempfile.mkdtemp()
os.environ['PROOF_SCRIPT'] = os.path.join(T, 'x.py')
stub = lambda n: sys.modules.setdefault(n, types.ModuleType(n))
lanes = stub('s_lanes')
lanes.PR, lanes.TORTUGA = 'pr', 'tg'
for n in ('sailing', 'paths', 's_shipquest', 's_cards', 's_guards', 's_earn'):
    stub(n)
sys.modules['s_cards'].playTypes = lambda: ()
sys.modules['s_cards'].TYPES = {}
os.environ.update(STORY_START='x', STORY_STOP='x')
os.environ['STORY_LADDER'] = ','
for n in ('pirates', 'pirates.quest', 'pirates.quest.QuestLadderDB', 'pirates.quest.QuestDNA'):
    stub(n)
sys.modules['pirates.quest.QuestDNA'].QuestDNA = type('QuestDNA', (), {})
sys.path.insert(0, D)
S = importlib.import_module('s_story')

DistributedGAInterior = type('DistributedGAInterior', (), {})
DistributedJailInterior = type('DistributedJailInterior', (), {})
DistributedIsland = type('DistributedIsland', (), {})
DistributedInteriorDoor = type('DistributedInteriorDoor', (), {})


def obj(cls, doId, x=0.0, parentId=None):
    o = cls()
    o.doId, o.x, o.parentId = doId, x, parentId
    return o


now = [1000.0]
S.time = types.SimpleNamespace(time=lambda: now[0])
used = []
S.useDoor = lambda H, d, st, tag: (used.append((d.doId, tag)), '%s-door %s' % (tag, d.doId))[1]
S.hdist = lambda H, o, *a: abs(o.x - H.la.x)


def harness(room, doors):
    la = types.SimpleNamespace(x=0.0, getParentObj=lambda: room)
    evs = []
    H = types.SimpleNamespace(la=la, cr=types.SimpleNamespace(doId2do={d.doId: d for d in doors}),
                              area=lambda: (type(room).__name__, 'uid', 'name'),
                              ev=lambda k, **kw: evs.append(k))
    return H, evs


tavern = obj(DistributedGAInterior, 10)
shop = obj(DistributedGAInterior, 20)
doors = [obj(DistributedInteriorDoor, 11, 40.0, 10), obj(DistributedInteriorDoor, 12, -15.0, 10),
         obj(DistributedInteriorDoor, 21, 2.0, 20)]

# 1. in the tavern: nothing before NOSTEP_OUT, then the tavern's nearest door (12), never the shop's (21)
H, evs = harness(tavern, doors)
st = {}
assert S.leaveRoom(H, st) is None, 'walked out at once'
now[0] += S.NOSTEP_OUT - 1
assert S.leaveRoom(H, st) is None, 'walked out before NOSTEP_OUT'
now[0] += 2
r = S.leaveRoom(H, st)
assert r == 'leave-room-door 12' and used[-1] == (12, 'leave-room'), 'MAIN7: no walk out of the tavern (%r)' % r
assert S.roomExit(H).doId == 12
S.leaveRoom(H, st)
assert evs.count('NOSTEP-LEAVE-ROOM') == 1, 'event once per stretch'

# 2. outdoors, and 3. in the jail: leaveRoom does nothing (the jail has its own way out)
for room in (obj(DistributedIsland, 30), obj(DistributedJailInterior, 40)):
    H, evs = harness(room, doors + [obj(DistributedInteriorDoor, 41, 1.0, 40)])
    st = {'noStepT': now[0] - 999}
    n = len(used)
    assert S.leaveRoom(H, st) is None and len(used) == n, 'left a %s' % type(room).__name__

# 4. a room with no inside door generated yet: no walk, no crash
H, evs = harness(obj(DistributedGAInterior, 50), doors)
assert S.leaveRoom(H, {'noStepT': now[0] - 999}) is None
print('PASS')
