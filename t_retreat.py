"""Offline test of s_shipfight.retreatVia (the sail home after a break-off goes round foes near the line home).
Run from the game folder: ppython t_retreat.py (needs the harness folder on sys.path)."""
import builtins, math, os, sys
builtins.__dev__ = False
sys.path[:0] = ['.', os.path.dirname(os.path.abspath(__file__))]
import s_shipfight as S

R = S.retreatVia
assert R((0, 0), (8000, 0), []) is None
assert R((0, 0), (8000, 0), [(-6000, 0)]) is None                      # far behind us: straight home
assert R((0, 0), (8000, 0), [(3000, 4000)]) is None                    # well off the line home
v = R((0, 0), (8000, 0), [(3000, 800)])                                # on the line home, left side -> turn right
assert v is not None and v[0] > 0 and v[1] < -1000, v
v = R((0, 0), (8000, 0), [(1200, -900), (1800, -1200)])               # DOLL4: two chasers on the right -> turn left
assert v is not None and v[0] > 0 and v[1] > 1000 and abs(math.hypot(*v) - S.RETREAT_LEG) < 1, v
v = R((0, 0), (500, 0), [(200, 100)])                                  # home closer than a leg: never past home
assert v is not None and math.hypot(*v) <= 501, v
import inspect, sailing
assert 'via' in inspect.signature(sailing.sail_to).parameters
print('t_retreat ok')
