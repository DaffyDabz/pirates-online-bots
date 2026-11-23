"""FPS census (games lane, 11-20): why the boys get 14-30 fps outdoors in Pirates (crash-report frame-rate lines) while
the same PCs ran Toontown at 60-120. Both boys play on Intel built-in graphics; our Panda build reports GPU vendor 0,
so the original game's low-end downgrade for Intel never runs and they get every setting at max (r1s1s1t1c1e2c2t2m0)
at the full desktop resolution.
For each area: the game's own areaTeleport, wait for LandRoam, settle, then measure the uncapped frame rate (frames /
real seconds over FPS_SECS) standing still with:
  base       the boys' settings (everything on) at FPS_W x FPS_H
  refl-off   water reflection off           shadow-off  avatar shadows off
  fx-low     special effects Low            all-off     the three above together
  res720     1280x720                        res600      800x600
Pass 2 ('low'): the original game's low-end card settings that can change while playing (effects, character and
terrain detail Low; detail applies on the next area load, so pass 2 revisits every area), measured at base and res720.
Events: FPS (area, pass, tag, fps, ms, win, geoms), FPS-SKIP, PASS (the goal is the numbers).
env: FPS_SECS (default 6), FPS_W / FPS_H (default 1920x1080), FPS_AREAS (comma list of keys)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))

SECS = float(os.environ.get('FPS_SECS', '6'))
W, HT = int(os.environ.get('FPS_W', '1920')), int(os.environ.get('FPS_H', '1080'))
AREAS = [
    ('portroyal', '1150922126.8dzlu'),
    ('tortuga', '1156207188.95dzlu'),
    ('cuba', '1160614528.73sdnaik'),
    ('avaricia', '1196970035.53sdnaik'),
]
if os.environ.get('FPS_AREAS'):
    keep = os.environ['FPS_AREAS'].split(',')
    AREAS = [a for a in AREAS if a[0] in keep]


def size(w, h):
    from panda3d.core import WindowProperties
    wp = WindowProperties()
    wp.setSize(w, h)
    base.win.requestProperties(wp)


def refl(on):
    from pirates.seapatch.Water import Water
    if on:
        Water.all_reflecttions_show_through_only()
    else:
        Water.all_reflections_off()


def shadows(on):
    tod = getattr(base.cr, 'timeOfDayManager', None)
    if tod is None:
        return
    if on:
        tod.enableAvatarShadows()
    else:
        tod.disableAvatarShadows()


def fx(level):
    base.options.special_effects = level
    base.options.setRuntimeSpecialEffects()


def code():
    o = base.options
    return 'r%ds%ds%de%dc%dt%d' % (o.reflection, o.shader, o.shadow, o.special_effects, o.character_detail_level,
                                  o.terrain_detail_level)


def measure(H, area, pas, tag):
    yield 2
    f0, t0 = globalClock.getFrameCount(), globalClock.getRealTime()
    yield SECS
    f1, t1 = globalClock.getFrameCount(), globalClock.getRealTime()
    fps = (f1 - f0) / max(t1 - t0, 0.001)
    try:
        geoms = render.findAllMatches('**/+GeomNode').getNumPaths()
    except Exception:
        geoms = None
    H.ev('FPS', area=area, pas=pas, tag=tag, fps=round(fps, 1), ms=round(1000.0 / max(fps, 0.01), 2),
         win=(base.win.getXSize(), base.win.getYSize()), geoms=geoms, opts=code())


def run(H):
    from panda3d.core import ClockObject
    la = H.la
    globalClock.setMode(ClockObject.MNormal)          # walker caps the bot at 30 fps; measure uncapped
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    o = base.options
    fx0 = o.special_effects
    gsg = base.win.getGsg()
    H.ev('FPS-START', opts=code(), vendor=gsg.getDriverVendor(), renderer=gsg.getDriverRenderer(),
         version=gsg.getDriverVersion(), shadow=o.shadow, reflection=o.reflection, area=H.area())
    size(W, HT)
    done = 0
    for pas in ('max', 'low'):
        if pas == 'low':
            o.character_detail_level = o.option_low
            o.terrain_detail_level = o.option_low
            o.setRuntimeGridDetailLevel(o.option_low)
            o.setRuntimeAvatarDetailLevel(o.option_low)
            fx(o.SpecialEffectsLow)
        for key, uid in AREAS:
            if H.area() is None or H.area()[1] != uid or pas == 'low':
                if H.area() is not None and H.area()[1] == uid:
                    # pass 2 needs a fresh load of this area for the detail levels: hop away first
                    other = AREAS[0][1] if uid != AREAS[0][1] else AREAS[-1][1]
                    H.mw('areaTeleport %s' % other)
                    yield ('until', lambda: H.area() is not None and H.area()[1] == other and la.getGameState() == 'LandRoam', 90, 'hop')
                H.mw('areaTeleport %s' % uid)
                yield ('until', lambda: H.area() is not None and H.area()[1] == uid and la.getGameState() == 'LandRoam', 90, 'tp ' + key)
            if H.area() is None or H.area()[1] != uid:
                H.ev('FPS-SKIP', area=key, got=H.area(), gs=la.getGameState())
                continue
            yield 8                                   # let the area finish loading
            size(W, HT)
            yield from measure(H, key, pas, 'base')
            if pas == 'max':
                refl(False)
                yield from measure(H, key, pas, 'refl-off')
                refl(True)
                shadows(False)
                yield from measure(H, key, pas, 'shadow-off')
                shadows(True)
                fx(o.SpecialEffectsLow)
                yield from measure(H, key, pas, 'fx-low')
                refl(False); shadows(False)
                yield from measure(H, key, pas, 'all-off')
                refl(True); shadows(True); fx(fx0)
            size(1280, 720)
            yield from measure(H, key, pas, 'res720')
            if pas == 'max':
                size(800, 600)
                yield from measure(H, key, pas, 'res600')
            size(W, HT)
            done += 1
    H.ev('PASS', what='fps census', areas=done)
