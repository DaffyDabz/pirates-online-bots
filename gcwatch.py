# games lane 11-22: catch the RenderState garbage_collect crash live (C:\PiratesBots\out\gcstates\FINDINGS.md, bug cfc4ee).
# The game closes with an AssertionError out of ShowBase.__garbageCollectStates (RenderState.garbageCollect, ShowBase.py
# 2142): Panda's state table already holds damage when the sweep starts (82-194 failed removes in one sweep). No offline
# repro, so this watches every bot run instead (walker.py installs it unless GC_WATCH=0). It changes nothing the game
# does: the same two sweeps run in the same task, and a crash still closes the game.
# - Once a second, before the RenderState sweep, RenderState.validateStates() checks the table. The first time it fails
#   (damage found before any crash), the table goes to a catch file and the events get GC-STATES-BROKEN.
# - If the sweep itself raises, the table goes to a catch file, the events get GC-STATES-CRASH, then it raises again.
# A catch file (C:\PiratesBots\out\gcstates\catches\<tag>-<kind>-<time>.txt) holds the counts, the TWINS (two stored states
# with equal contents, compareTo 0, but different hashes: the cause FINDINGS names, with each one's attribute objects)
# and Panda's own listStates. Every probe step is in try/except: a probe fault is logged once and never stops the game.
import os, sys, time, traceback
from panda3d.core import RenderState, TransformState, RenderAttribRegistry, StringStream

RS, TS = RenderState, TransformState          # module names so the sim can stand in for Panda
CHECK_SECS = 1.0
OUT = os.environ.get('GC_WATCH_DIR', r'C:\PiratesBots\out\gcstates\catches')
MAX_TWINS = 40
st = {'ev': None, 'tag': 'bot', 'last': 0.0, 'broken': False, 'dumped': set(), 'checks': 0, 'slow': 0.0,
      'fault': False}


def _ev(name, **kw):
    try:
        if st['ev']:
            st['ev'](name, **kw)
    except Exception:
        pass


def _fault(where):
    if not st['fault']:
        st['fault'] = True
        sys.stderr.write('gcwatch: probe fault in %s (probe off for the table check)\n%s' % (where, traceback.format_exc()))
        _ev('GC-WATCH-FAULT', where=where)


def _attribs(s):
    out = []
    reg = RenderAttribRegistry.getGlobalPtr()
    for slot in range(1, reg.getNumSlots()):
        a = s.getAttrib(slot)
        if a is not None:
            out.append('%s@%x %s' % (type(a).__name__, a.this, str(a).strip()))
    return out


def twins():
    """Stored states with equal contents and different hashes, grouped by their printed contents."""
    groups = {}
    for s in RS.getStates():
        groups.setdefault(str(s).strip(), []).append(s)
    found = []
    for k, g in groups.items():
        if len(g) < 2:
            continue
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                a, b = g[i], g[j]
                if a.this != b.this and a.compareTo(b) == 0:
                    found.append((a, b))
    return found


def dump(kind, err=None):
    if kind in st['dumped']:
        return None
    st['dumped'].add(kind)
    path = None
    try:
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, '%s-%s-%s.txt' % (st['tag'], kind, time.strftime('%m%d-%H%M%S')))
        tw = []
        with open(path, 'w') as f:
            f.write('%s %s tag=%s\n' % (kind, time.strftime('%Y-%m-%d %H:%M:%S'), st['tag']))
            if err:
                f.write('error: %s\n' % err)
            f.write('states %d unused %d checks %d slowest validate %.1f ms\n'
                    % (RS.getNumStates(), RS.getNumUnusedStates(), st['checks'], st['slow'] * 1000))
            try:
                tw = twins()
                f.write('\nTWINS %d (equal contents, compareTo 0, different objects)\n' % len(tw))
                for a, b in tw[:MAX_TWINS]:
                    f.write('- hash %d @%x / hash %d @%x: %s\n' % (a.getHash(), a.this, b.getHash(), b.this, str(a).strip()))
                    f.write('    a: %s\n    b: %s\n' % (' | '.join(_attribs(a)), ' | '.join(_attribs(b))))
            except Exception:
                f.write('twins failed:\n%s' % traceback.format_exc())
            f.write('\nlistStates follows\n')
            try:
                o = StringStream()
                RS.listStates(o)
                f.write(o.getData().decode('latin-1'))
            except Exception:
                f.write('listStates failed:\n%s' % traceback.format_exc())
        _ev('GC-STATES-' + kind, file=path, states=RS.getNumStates(), twins=len(tw), err=err)
    except Exception:
        _fault('dump')
    return path


def sweep(base, task):
    TS.garbageCollect()
    if not st['broken'] and not st['fault']:
        try:
            now = time.time()
            if now - st['last'] >= CHECK_SECS:
                st['last'] = now
                t = time.perf_counter()
                ok = RS.validateStates()
                st['slow'] = max(st['slow'], time.perf_counter() - t)
                st['checks'] += 1
                if st['checks'] == 1:
                    _ev('GC-WATCH-ON', states=RS.getNumStates(), ms=round((time.perf_counter() - t) * 1000, 1), ok=ok)
                if not ok:
                    st['broken'] = True
                    dump('BROKEN')
        except Exception:
            _fault('validate')
    try:
        RS.garbageCollect()
    except AssertionError as e:
        dump('CRASH', err=str(e))
        raise
    return task.cont


def install(ev=None, tag=None):
    """Swap ShowBase's state sweep task body for sweep(); call before ShowBase is made. Returns True when installed."""
    st['ev'] = ev
    st['tag'] = tag or 'bot'
    try:
        from direct.showbase import ShowBase as SB
        SB.ShowBase._ShowBase__garbageCollectStates = sweep
        return True
    except Exception:
        _fault('install')
        return False
