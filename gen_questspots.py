"""Builds pirates-harness/quest_spots.json from the client's own world data (same files as the server's): where the
quest things are inside each game area, and how the areas join, so s_story can walk to a chest, a container or an
enemy spawn that is not in view yet.

  areas: area uid -> [island uid, kind ('island' | 'gamearea' | 'interior'), file]
  objs:  uid -> [area uid, x, y, z, type, spawnables]      positions are area-local (the area object's own frame,
         composed through every parent's Pos/Hpr/Scale); types: 'Searchable Container', 'Spawn Node' (enemies,
         'Buried Treasure' spawnables = dig spots)
  exits: area uid -> [[to area, x, y, z, 'door' | 'tunnel' | 'link', via uid], ...]   x, y, z = the mouth / door in
         the FROM area's frame (None for an interior's way out: the interior door object is always in view there)

Interiors are named the way the server names them (GameAreaBuilderAI.createBuildingExterior: the exterior's 'ExtUid'),
game areas by their 'Island Game Area' uid (= the area file's top object), tunnels from 'Locator Links' (island
locator <-> tunnel portal_connector_1, portal_connector_2 <-> game-area locator, collapsed to one edge).
Run: cd C:\\Games\\pirates-online\\pirates-online-classic; C:\\Panda3D-1.11.0-x64\\python\\ppython.exe <this file>"""
import os, sys, json, builtins
builtins.__dev__ = False
C = r'C:\PiratesOnline\pirates-online-classic'
sys.path.insert(0, C)
os.chdir(C)
from panda3d.core import TransformState, VBase3   # noqa: E402

areas, objs, exits, locs, links, tunnels = {}, {}, {}, {}, [], {}
loaded = {}


def load(stem):
    if stem not in loaded:
        try:
            loaded[stem] = __import__('pirates.leveleditor.worldData.%s' % stem, fromlist=['objectStruct']).objectStruct
        except Exception as e:
            print('!! world file %s does not load: %s' % (stem, e))
            loaded[stem] = None
        else:
            links.extend(loaded[stem].get('Locator Links', []) or [])
    return loaded[stem]


def xf(ts, o):
    return ts.compose(TransformState.makePosHprScale(VBase3(*o.get('Pos', (0, 0, 0))), VBase3(*o.get('Hpr', (0, 0, 0))),
                                                     VBase3(*o.get('Scale', (1, 1, 1)))))


def r1(v):
    return [round(v[0], 1), round(v[1], 1), round(v[2], 1)]


def fileTop(stem):
    s = load(stem)
    tops = list((s or {}).get('Objects', {}).items())
    return tops[0] if tops else (None, None)


def addArea(uid, island, kind, stem, children):
    if uid in areas:
        return
    areas[uid] = [island, kind, stem]
    walk(children or {}, uid, island, stem, TransformState.makeIdentity(), None)


def walk(children, area, island, stem, ts, owner):
    for uid, o in children.items():
        if not isinstance(o, dict):
            continue
        t = o.get('Type', '')
        here = xf(ts, o)
        pos = r1(here.getPos())
        if t == 'Island Game Area' and o.get('File'):
            # its locators in this file are in the game area's own frame; the area itself is its own file
            gtop, go = fileTop(o['File'])
            walk(o.get('Objects', {}), uid, island, stem, TransformState.makeIdentity(), None)
            addArea(uid, island, 'gamearea', o['File'], (go or {}).get('Objects', {}))
            if gtop and gtop != uid:
                print('!! game area %s: file %s top is %s' % (uid, o['File'], gtop))
            continue
        if t == 'Building Exterior' and o.get('File') and o.get('ExtUid'):
            inner = o['ExtUid']
            doors = [(du, d) for du, d in (o.get('Objects') or {}).items() if isinstance(d, dict) and d.get('Type') == 'Door Locator Node']
            for du, d in doors or [(uid, {})]:
                exits.setdefault(area, []).append([inner] + r1(xf(here, d).getPos()) + ['door', du])
            itop, io = fileTop(o['File'])
            exits.setdefault(inner, []).append([area, None, None, None, 'door', uid])
            addArea(inner, island, 'interior', o['File'], (io or {}).get('Objects', {}))
            continue
        if t == 'Connector Tunnel':
            tunnels[uid] = area
            walk(o.get('Objects', {}), area, island, stem, here, uid)
            continue
        if t == 'Locator Node':
            locs[uid] = (owner, area, pos)
        elif t == 'Searchable Container' or (t in ('Spawn Node', 'Dormant NPC Spawn Node', 'Object Spawn Node') and o.get('Spawnables')):
            objs[uid] = [area] + pos + [t, o.get('Spawnables', '')]
        walk(o.get('Objects', {}) or {}, area, island, stem, here, owner)


world = load('piratesWorld')
for iuid, io in world['Objects'].items():
    for uid, o in (io.get('Objects') or {}).items():
        if o.get('Type') == 'Island' and o.get('File'):
            top, to = fileTop(o['File'])
            if top != uid:
                print('!! island %s: file %s top is %s' % (uid, o['File'], top))
            addArea(uid, uid, 'island', o['File'], (to or {}).get('Objects', {}))

# tunnels: area locator <-> tunnel locator ... tunnel locator <-> area locator  =>  one edge each way
other = {}
for a, b, *rest in links:
    other.setdefault(a, []).append(b)
    other.setdefault(b, []).append(a)
nT = nL = 0
for luid, (owner, area, pos) in locs.items():
    if owner is not None:
        continue
    for ouid in other.get(luid, []):
        if ouid not in locs:
            continue
        o2, a2, p2 = locs[ouid]
        if o2 is None:
            if a2 != area:
                exits.setdefault(area, []).append([a2] + pos + ['link', ouid]); nL += 1
            continue
        # into tunnel o2: its other locator, then that one's area end
        for tl, (to, ta, tp) in locs.items():
            if to != o2 or tl == ouid:
                continue
            for far in other.get(tl, []):
                if far in locs and locs[far][0] is None and locs[far][1] != area:
                    exits.setdefault(area, []).append([locs[far][1]] + pos + ['tunnel', o2]); nT += 1

# dedupe
for a in exits:
    seen, out = set(), []
    for e in exits[a]:
        k = (e[0], e[4], e[5])
        if k not in seen:
            seen.add(k)
            out.append(e)
    exits[a] = out

dst = r'C:\PiratesBots\quest_spots.json'
json.dump({'areas': areas, 'objs': objs, 'exits': exits}, open(dst, 'w'), indent=0, sort_keys=True)
kinds = {}
for v in areas.values():
    kinds[v[1]] = kinds.get(v[1], 0) + 1
print('areas', kinds, 'objs', len(objs), 'containers', sum(1 for v in objs.values() if v[4] == 'Searchable Container'),
      'treasure spots', sum(1 for v in objs.values() if v[5] == 'Buried Treasure'), 'tunnel edges', nT, 'link edges', nL,
      'links', len(links), 'locators', len(locs))
