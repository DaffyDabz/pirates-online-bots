"""Builds pirates-harness/dig_spots.json: area uid -> [(x, y, z), ...] of every 'Buried Treasure' spawn node that sits
directly under that area's top object (so its Pos is area-local), read from the client's own world data."""
import os, sys, json, importlib
C = r'C:\PiratesOnline\pirates-online-classic'
sys.path.insert(0, C)
os.chdir(C)
WD = os.path.join(C, 'pirates', 'leveleditor', 'worldData')
out, deep = {}, 0
for f in sorted(os.listdir(WD)):
    if not f.endswith('.py') or f.startswith('__'):
        continue
    try:
        src = open(os.path.join(WD, f), encoding='utf-8', errors='replace').read()
    except Exception:
        continue
    if "'Buried Treasure'" not in src:
        continue
    m = importlib.import_module('pirates.leveleditor.worldData.' + f[:-3])
    def walk(objs, top, depth):
        global deep
        for uid, o in objs.items():
            if not isinstance(o, dict):
                continue
            if o.get('Spawnables') == 'Buried Treasure':
                if depth == 1:
                    p = o['Pos']
                    out.setdefault(top, []).append([round(p[0], 1), round(p[1], 1), round(p[2], 1)])
                else:
                    deep += 1
            kids = o.get('Objects')
            if isinstance(kids, dict):
                walk(kids, top if depth else uid, depth + 1)
    walk(m.objectStruct.get('Objects', {}), None, 0)
dst = r'C:\PiratesBots\dig_spots.json'
json.dump(out, open(dst, 'w'), indent=1, sort_keys=True)
print('areas', len(out), 'spots', sum(map(len, out.values())), 'nested (left out)', deep)
print('Port Royal', out.get('1142018473.22dxschafe'))
