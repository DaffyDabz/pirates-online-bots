# games 11-22: sim for gcwatch.py (the live catch of the RenderState garbage_collect crash). Plain Panda, no game, no
# window. Run: ppython -I t_gcwatch.py <harness dir>   -> "gcwatch ok", or the failed checks.
import os, sys, time, tempfile, shutil
sys.path.insert(0, os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.'))
from panda3d.core import loadPrcFileData, RenderState, ColorScaleAttrib, TransparencyAttrib
loadPrcFileData('', 'window-type none\naudio-library-name null\ngarbage-collect-states #t')
OUT = tempfile.mkdtemp(prefix='gcw-')
os.environ['GC_WATCH_DIR'] = OUT
bad = []
def check(n, ok, what):
    print('%2d %s %s' % (n, 'ok ' if ok else 'BAD', what))
    if not ok:
        bad.append(n)

try:
    import gcwatch
except ImportError:
    print('BAD gcwatch.py missing'); sys.exit(1)
EV = []
check(1, gcwatch.install(lambda name, **kw: EV.append((name, kw)), 'SIM'), 'install swaps the ShowBase sweep')
from direct.showbase.ShowBase import ShowBase
base = ShowBase()
check(2, base.taskMgr.hasTaskNamed('garbageCollectStates'), 'the game still has its garbageCollectStates task')
keep = [RenderState.make(ColorScaleAttrib.make((1, i / 300.0, 0.5, 1))) for i in range(300)]
gcwatch.st['last'] = 0
for i in range(3):
    base.taskMgr.step()
check(3, gcwatch.st['checks'] >= 1 and not gcwatch.st['broken'], 'a healthy table passes the check (%d checks)' % gcwatch.st['checks'])
check(4, not os.listdir(OUT) and [e[0] for e in EV] == ['GC-WATCH-ON'] and EV[0][1]['ok'],
      'a healthy table writes nothing; one GC-WATCH-ON event (%s)' % EV)

class Fake:                                    # Panda's RenderState with chosen calls swapped
    def __init__(self, **kw):
        self.kw = kw
    def __getattr__(self, n):
        return self.kw[n] if n in self.kw else getattr(RenderState, n)

# 5-7 damage found by the check before any crash
gcwatch.RS = Fake(validateStates=lambda: False)
gcwatch.st['last'] = 0
base.taskMgr.step()
files = [f for f in os.listdir(OUT) if 'BROKEN' in f]
check(5, gcwatch.st['broken'] and len(files) == 1, 'a damaged table writes one BROKEN catch file')
txt = open(os.path.join(OUT, files[0])).read() if files else ''
check(6, 'TWINS' in txt and 'listStates follows' in txt and 'ColorScaleAttrib' in txt, 'the catch file holds twins + Panda listStates')
check(7, [e for e in EV if e[0] == 'GC-STATES-BROKEN'] != [], 'event GC-STATES-BROKEN')

# 8-10 the sweep itself fails: the table is written, then the game closes as before
def boom():
    raise AssertionError('!_states.remove(this) at line 300 of simpleHashMap.I')
gcwatch.RS = Fake(garbageCollect=boom)
raised = False
try:
    gcwatch.sweep(base, type('T', (), {'cont': 1})())
except AssertionError:
    raised = True
check(8, raised, 'the crash still raises (the game closes as before)')
check(9, len([f for f in os.listdir(OUT) if 'CRASH' in f]) == 1, 'a CRASH catch file')
check(10, [e for e in EV if e[0] == 'GC-STATES-CRASH' and 'simpleHashMap' in str(e[1].get('err'))] != [], 'event GC-STATES-CRASH with the assert text')

# 11-12 a probe fault never stops the game
gcwatch.RS = RenderState
gcwatch.st.update(broken=False, fault=False, last=0)
def oops():
    raise RuntimeError('probe bug')
gcwatch.RS = Fake(validateStates=oops)
ok = True
try:
    for i in range(3):
        gcwatch.st['last'] = 0
        base.taskMgr.step()
except Exception:
    ok = False
check(11, ok, 'a fault inside the check never reaches the game')
check(12, len([e for e in EV if e[0] == 'GC-WATCH-FAULT']) == 1, 'the fault is logged once')

# 13 twins: two stored states with equal contents and different objects are named
class S:
    def __init__(self, p, h):
        self.this, self.h = p, h
    def __str__(self):
        return 'ColorScaleAttrib:(1 0.5 0.5 1)'
    def compareTo(self, o):
        return 0
    def getHash(self):
        return self.h
a, b, c = S(1, 11), S(2, 22), S(3, 33)
gcwatch.RS = Fake(getStates=lambda: [a, b])
check(13, len(gcwatch.twins()) == 1, 'twins finds the equal pair')
gcwatch.RS = Fake(getStates=lambda: [a, a])
check(14, gcwatch.twins() == [], 'one object twice is not a twin')

# 15 the check's cost at a game-sized table (the bots run at 5-20 fps)
gcwatch.RS = RenderState
many = [RenderState.make(ColorScaleAttrib.make((1 + i, 1, 1, 1))) for i in range(40000)]
t = time.perf_counter(); RenderState.validateStates(); ms = (time.perf_counter() - t) * 1000
check(15, ms < 50, 'validateStates over %d states takes %.1f ms (once a second)' % (RenderState.getNumStates(), ms))
t = time.perf_counter(); n = len(gcwatch.twins()); ms2 = (time.perf_counter() - t) * 1000
check(16, n == 0, 'twins over %d states: %d found, %.0f ms (only on a catch)' % (RenderState.getNumStates(), n, ms2))

shutil.rmtree(OUT, ignore_errors=True)
print('gcwatch ok' if not bad else 'gcwatch FAILED %s' % bad)
sys.stdout.flush()
os._exit(0 if not bad else 1)
