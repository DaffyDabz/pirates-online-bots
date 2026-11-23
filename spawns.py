import sys, os, builtins
sys.path.insert(0, os.getcwd())
from panda3d.core import *
ns = {'Point3': Point3, 'VBase3': VBase3, 'Vec3': Vec3, 'VBase4': VBase4, 'Vec4': Vec4, 'Point4': Point4}
src = open('pirates/leveleditor/worldData/PortRoyalIsland.py').read()
exec(src, ns)
od = ns['objectStruct']
isl = od['Objects']['1150922126.8dzlu']
m = Point3(177.9, -1115.3, 53.4)
rows = []
for k, v in isl['Objects'].items():
    if v.get('Type') == 'Spawn Node':
        p = v['Pos']
        rows.append(((p - m).length(), v.get('Spawnables'), k, tuple(round(x) for x in p)))
rows.sort()
for r in rows[:15]: print(r)
