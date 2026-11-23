"""List doors + tunnels loaded around the pirate (id, pos, building / interior uid), at spawn and after a short walk each
way, so a census run can pick the mansion / jail doors and the jungle tunnel by uid. Always PASS (hard stop 90 s)."""
import os, time
from panda3d.core import Vec3


def listing(H, tag):
    R, la = H.render, H.la
    lp = la.getPos(R)
    for o in list(H.cr.doId2do.values()):
        n = type(o).__name__
        if 'Door' in n or 'Tunnel' in n:
            try:
                p = o.getPos(R)
                H.ev('list-obj', tag=tag, cls=n, doId=o.doId, pos=[round(v) for v in p], dist=round((p - lp).length()),
                     bld=getattr(o, 'buildingUid', None), inter=getattr(o, 'interiorUid', None),
                     uid=getattr(o, 'uniqueId', None), objName=o.getName(), idx=getattr(o, 'doorIndex', None))
            except Exception as e:
                H.ev('list-err', cls=n, err=repr(e))


def run(H):
    la, R = H.la, H.render
    T0 = time.time()
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    yield 5
    H.ev('list-area', area=H.area(), pos=[round(v) for v in la.getPos(R)])
    listing(H, 'spawn')
    H.ev('PASS', note='list done')
