"""Route check: why the planner finds no walk from the governor's mansion down to Darby. STORY16 (11-16) walked UP to
the mansion door on a planned route, handed c2.5deliverOrders in, then planned 9 times from the mansion yard to Darby
(745 ft, down the same hill) and every plan was None (~7240 checks each); it stalled and the quest was skipped.
At Port Royal (the pirate is put at the mansion door, logged SETUP-POS, diagnosis only, never in play) it logs:
  rd-ground  every floor under the door, the yard spot and Darby, as the planner probes them
  rd-trail   STORY16's way-up route walked backwards (down), leg by leg: open, or why not
  rd-plan    plans to Darby from the door, the yard spot, the middle and the bottom of the trail, each with the default
             grid, the grid shifted half a cell, and the wide box: the route or None, and where the search stopped
             (paths.LAST: points expanded, the point nearest Darby, ran dry or out of budget)
PASS when everything is logged (the goal is the data)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import sailing, paths   # noqa: E402
from s_pocket import why_not   # noqa: E402

PR = '1150922126.8dzlu'
DOOR, YARD = (-260.6, -769.5, 57.3), (-261.8, -688.0, 47.0)
DARBY = (-274.3, 57.3, 2.7)
UP = [(323.5, 34.5, 3.7), (290.6, -9.5, 10.5), (150.6, -69.5, 11.7), (70.6, -89.5, 13.7), (50.6, -229.5, 11.6),
      (-49.4, -349.5, 19.0), (-169.4, -689.5, 44.4), (-259.4, -779.5, 59.9)]     # STORY16's route up, start first
SHORT = 6.0                                                                    # as s_story's approach walk


def run(H):
    la, R = H.la, H.render
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if sailing.hereUid(H) != PR:
        H.mw('areaTeleport %s' % PR)
        yield ('until', lambda: sailing.hereUid(H) == PR and la.getGameState() == 'LandRoam', 90, 'tp Port Royal')
        yield 5
    H.ev('SETUP-POS', to=list(DOOR), frm=H.P(la), why='diagnosis: plan from the mansion door as STORY16 did')
    la.setPos(R, *DOOR)
    yield 3
    legs_ok, ground = paths.live(H, SHORT)
    H.ev('rd-ground', **{k: [round(z, 1) for z in zs] for k, zs in
                         zip(('door', 'yard', 'darby'), ground.floors([DOOR, YARD, DARBY]))})
    down = list(reversed(UP))
    legs = []
    for p, q in zip(down, down[1:]):
        legs.append([[round(v, 1) for v in p], [round(v, 1) for v in q], why_not(legs_ok, ground, p, q)])
        yield 0
    H.ev('rd-trail', legs=legs)
    for name, a in (('door', DOOR), ('yard', YARD), ('mid', UP[4]), ('bottom', UP[0])):
        for how, kw in (('grid', {}), ('shift', {'offset': (paths.GRID / 2, paths.GRID / 2)}),
                        ('wide', {'margin': paths.WIDE * paths.MARGIN, 'max_expand': paths.WIDE * paths.MAX_EXPAND})):
            r, checks = yield from paths.plan_g(a, DARBY, legs_ok, ground, (), SHORT, **kw)
            H.ev('rd-plan', frm=name, how=how, checks=checks,
                 path=[[round(v, 1) for v in w] for w in r] if r else None,
                 length=round(paths.length(a, r), 1) if r else None, search=dict(paths.LAST))
            yield 0
    H.ev('PASS', what='mansion-to-Darby routes measured')
