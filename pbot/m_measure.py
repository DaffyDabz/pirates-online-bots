# pbots (11-22): MEASURE step for walker.py - where the bot game's memory goes, run with pbot/run_measure.ps1.
# Not a bot game test: it never writes a strike. It logs the test pirate in (BOT_AVID from the runner, never
# 100000170), then samples the process from the inside three times:
#   A  8 s after the pirate is in the world, window drawing (tinydisplay when BOT_PRC = prc/strip.prc)
#   B  MEASURE_SECS later with the window switched off (base.win.setActive(False): nothing culled or drawn)
#   C  after a 20 ft walk out and back, still switched off
# and writes C:\PiratesBots\out\pbots\measure-<MEASURE_TAG>.json. The runner samples the same numbers from the
# outside every 10 s (measure-<tag>-ext.csv). PASS = three samples written; the walk result is a field, not the verdict.
import os, sys, time, json, gc, ctypes, builtins, traceback
from ctypes import wintypes

OUT_DIR = r'C:\PiratesBots\out\pbots'
TAG = os.environ.get('MEASURE_TAG', 'MEAS')
SECS = float(os.environ.get('MEASURE_SECS', '20'))
INACTIVE = os.environ.get('MEASURE_INACTIVE', '1') == '1'
# MEASURE_EARLY_OFF=1: the window goes off at the avatar chooser, before the world loads, so no texture or vertex
# buffer is ever uploaded to the GPU (MEAS3 had 11195 vertex + 14772 index buffers prepared; the driver keeps a
# copy of each in the process). Sample A is then "in world, window off" instead of "drawing".
EARLY_OFF = os.environ.get('MEASURE_EARLY_OFF') == '1'


class _PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t),
                ('PrivateUsage', ctypes.c_size_t)]


_k32 = ctypes.windll.kernel32; _k32.GetCurrentProcess.restype = wintypes.HANDLE
_psapi = ctypes.windll.psapi
_psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
_psapi.GetProcessMemoryInfo.restype = wintypes.BOOL


def proc_mem():
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(pmc)
    # argtypes matter: without them the -1 pseudo-handle is passed as a 32-bit int and the call quietly returns zeros
    if not _psapi.GetProcessMemoryInfo(_k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        return {'error': 'GetProcessMemoryInfo failed %d' % ctypes.get_last_error()}
    mb = 1024.0 * 1024.0
    return {'ws_mb': round(pmc.WorkingSetSize / mb, 1), 'peak_ws_mb': round(pmc.PeakWorkingSetSize / mb, 1),
            'private_mb': round(pmc.PrivateUsage / mb, 1), 'page_faults': pmc.PageFaultCount}


def _try(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return default if default is not None else 'ERR %s' % (str(e)[:80],)


def sample(label):
    from panda3d.core import TexturePool, VertexDataPage, SceneGraphAnalyzer, ConfigVariableString, ConfigVariableInt
    B = builtins.base
    s = {'label': label, 't': time.time(), 'mem': proc_mem()}
    # textures: how many the pool holds and what they would cost (with fake-texture-image they are all 8x8)
    def tex():
        tc = TexturePool.findAllTextures()
        n = tc.getNumTextures()
        est = 0; ram = 0; withram = 0; biggest = []
        for i in range(n):
            t = tc.getTexture(i)
            e = t.estimateTextureMemory(); est += e
            if t.hasRamImage():
                withram += 1; ram += t.getRamImageSize()
            biggest.append((e, t.getName()[-60:], t.getXSize(), t.getYSize()))
        biggest.sort(reverse=True)
        return {'count': n, 'estimate_mb': round(est / 1048576.0, 1), 'with_ram_image': withram,
                'ram_image_mb': round(ram / 1048576.0, 1), 'pool_fake': TexturePool.hasFakeTextureImage(),
                'top8': biggest[:8]}
    s['textures'] = _try(tex)
    # vertex data: the three LRU pools (resident / compressed / disk); 1.11 has no independent LRU getter
    def vtx():
        d = {}
        for name, rc in (('resident', VertexDataPage.RCResident), ('compressed', VertexDataPage.RCCompressed),
                         ('disk', VertexDataPage.RCDisk)):
            lru = VertexDataPage.getGlobalLru(rc)
            d[name + '_mb'] = round(lru.getTotalSize() / 1048576.0, 1)
            d[name + '_max_mb'] = round(lru.getMaxSize() / 1048576.0, 1)
        return d
    s['vertex_data'] = _try(vtx)
    # the scene graph under render (what the game keeps loaded for the area)
    def sga():
        a = SceneGraphAnalyzer()
        a.addNode(builtins.render.node())
        return {'nodes': a.getNumNodes(), 'geoms': a.getNumGeoms(), 'vertex_datas': a.getNumGeomVertexDatas(),
                'vertices': a.getNumVertices(), 'vertex_data_mb': round(a.getVertexDataSize() / 1048576.0, 1),
                'texture_mb': round(a.getTextureBytes() / 1048576.0, 1)}
    s['render'] = _try(sga)
    def gsg():
        g = B.win.getGsg()
        po = g.getPreparedObjects()
        return {'gsg': g.getType().getName(), 'pipe': B.pipe.getType().getName(),
                'win': '%dx%d active=%s' % (B.win.getXSize(), B.win.getYSize(), B.win.isActive()),
                'prepared_textures': _try(po.getNumPreparedTextures), 'prepared_geoms': _try(po.getNumPreparedGeoms),
                'prepared_vbuffers': _try(po.getNumPreparedVertexBuffers), 'prepared_ibuffers': _try(po.getNumPreparedIndexBuffers)}
    s['gsg'] = _try(gsg)
    s['python'] = {'alloc_blocks': sys.getallocatedblocks(), 'gc_objects': len(gc.get_objects()),
                   'modules': len(sys.modules), 'doId2do': _try(lambda: len(B.cr.doId2do))}
    s['prc'] = {'fake_texture_image': ConfigVariableString('fake-texture-image').getValue(),
                'max_resident_vertex_data': ConfigVariableInt('max-resident-vertex-data').getValue(),
                'max_disk_vertex_data': ConfigVariableInt('max-disk-vertex-data').getValue(),
                'load_display': ConfigVariableString('load-display').getValue(),
                'texture_scale': _try(lambda: ConfigVariableString('texture-scale').getValue())}
    return s


def early(ev):
    # before the pirate is picked: shrink the window (the game sizes it from its options, not a prc page)
    # (only when MEASURE_RESIZE=1: MEAS1 asked for 64x64 here and the game died at the pick with a vertex-buffer
    # assertion; the resize is one of the two suspects, so it is off until the other is cleared)
    try:
        from panda3d.core import WindowProperties
        B = builtins.base
        if os.environ.get('MEASURE_RESIZE') == '1':
            wp = WindowProperties()
            wp.setSize(64, 64)
            B.win.requestProperties(wp)
        if EARLY_OFF:
            B.win.setActive(False)
        ev('measure-early', win='%dx%d' % (B.win.getXSize(), B.win.getYSize()), pipe=B.pipe.getType().getName(),
           gsg=B.win.getGsg().getType().getName(), mem=proc_mem(), early_off=EARLY_OFF)
    except Exception:
        ev('measure-early-error', tb=traceback.format_exc()[-400:])


def _island_pos(H):
    la = H.la
    isl = la.getParentObj()
    while isl is not None and 'Island' not in type(isl).__name__ and 'GameArea' not in type(isl).__name__:
        isl = isl.getParentObj() if hasattr(isl, 'getParentObj') else None
    ref = isl if isl is not None else H.render
    return ref, la.getPos(ref), la.getQuat(ref).getForward()


def run(H):
    B = builtins.base
    out = {'tag': TAG, 'pid': os.getpid(), 'inactive': INACTIVE, 'early_off': EARLY_OFF,
           'bot_prc': os.environ.get('BOT_PRC'), 'fps': os.environ.get('BOT_FPS'), 'samples': []}
    yield 1
    out['samples'].append(sample('A-in-world-window-off' if EARLY_OFF else 'A-in-world-drawing'))
    H.ev('measure', **{k: out['samples'][-1][k] for k in ('label', 'mem', 'vertex_data', 'gsg', 'textures', 'render')})
    if INACTIVE and not EARLY_OFF:
        B.win.setActive(False)
    yield SECS
    out['samples'].append(sample('B-window-off' if INACTIVE else 'B-drawing'))
    H.ev('measure', **{k: out['samples'][-1][k] for k in ('label', 'mem', 'vertex_data', 'gsg')})
    # a short walk out and back: the game streams nothing new, so this shows the cost of moving, not of loading
    walk = {'ok': None}
    try:
        ref, p, fwd = _island_pos(H)
        tgt = p + fwd * 20.0
        walk['from'] = [round(v, 1) for v in p]; walk['to'] = [round(v, 1) for v in tgt]; walk['ref'] = type(ref).__name__
        ok1 = yield from H.moveTo(tgt.x, tgt.y, tgt.z)
        ok2 = yield from H.moveTo(p.x, p.y, p.z)
        walk['ok'] = bool(ok1 and ok2); walk['out'] = bool(ok1); walk['back'] = bool(ok2)
    except Exception:
        walk['error'] = traceback.format_exc()[-400:]
    out['walk'] = walk
    yield 3
    out['samples'].append(sample('C-after-walk'))
    H.ev('measure', **{k: out['samples'][-1][k] for k in ('label', 'mem', 'vertex_data', 'gsg', 'textures', 'render')})
    if INACTIVE or EARLY_OFF:
        B.win.setActive(True)   # back on, so the walker's end snapshot and the last frames behave as usual
        yield 2
        out['samples'].append(sample('D-window-back-on'))   # what one drawn frame costs after a window-off run
        H.ev('measure', **{k: out['samples'][-1][k] for k in ('label', 'mem', 'gsg')})
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, 'measure-%s.json' % TAG)
    with open(path, 'w') as f:
        json.dump(out, f, indent=1, default=str)
    a, b, c = (s['mem'] for s in out['samples'][:3])
    H.ev('PASS', what='measured: A %.0f/%.0f MB (ws/private) %s, B %.0f/%.0f window off, C %.0f/%.0f after walk, peak ws %.0f'
         % (a['ws_mb'], a['private_mb'], 'window off' if EARLY_OFF else 'drawing', b['ws_mb'], b['private_mb'],
            c['ws_mb'], c['private_mb'], c['peak_ws_mb']),
         walk=walk.get('ok'), json=path)
