"""KID MAKER (pir-test, 11-18): a brand-new pirate made the way a kid's client makes one. The kids' config has
skip-tutorial #t, so after "new pirate" on the avatar list the client opens the standalone pirate maker
(PiratesClientRepository.enterCreateAvatar -> base.cr.avCreate) before the pirate exists, and Done sends
csm.sendCreateAvatar with the look and the picked name; then the pirate goes straight into the world.
s_newplayer.py drives the tutorial's maker (skip-tutorial #f, this PC's config), which a kid never sees.

early(ev) puts a task in at login that drives the standalone maker: random gender, Random on every page (the name
page's Random is a picked name), Next, Done. run(H) starts once the pirate is in the world.
Events: KM-OPEN, KM-GENDER, KM-RANDOM, KM-NEXT, KM-NAME, KM-DONE, KM-ERR, KM-INWORLD, PASS / FAIL.
PASS = a new pirate (not 100000170) is in the world, with the name the maker picked on it.
env: KIDMAKER_SEED."""
import os, sys, time, random

HOST_AV = 100000170
SEED = int(os.environ.get('KIDMAKER_SEED') or int(time.time()))
# walker runs early() from its own exec of this file and run(H) from another load, so the two share STATE through builtins
import builtins
STATE = builtins.__dict__.setdefault('_KIDMAKER_STATE', {'name': None, 'done': False, 'steps': 0})


def _page(m):
    try:
        from pirates.piratesbase import PLocalizer
        return PLocalizer.MakeAPiratePageNames[m.currPageIndex]
    except Exception:
        return getattr(m, 'currPageIndex', None)


def _name(m):
    for get in (lambda: m.nameGui._getName(), lambda: m.pirate.style.getName(), lambda: m.pirate.style.name):
        try:
            n = get()
            if n:
                return n
        except Exception:
            pass
    return None


def early(ev):
    from direct.task import Task
    random.seed(SEED)
    plan = {'stage': 'wait', 'i': 0, 'pages': [], 't0': time.time()}

    def step(task):
        try:
            cr = base.cr
            m = getattr(cr, 'avCreate', None)
            st = plan['stage']
            if st == 'wait':
                if m is not None and getattr(m, 'guiNextButton', None) is not None and m.currPageIndex is not None:
                    ev('KM-OPEN', page=m.currPageIndex, pages=getattr(m, 'numShops', None), seed=SEED,
                       skipTutorial=getattr(cr, 'skipTutorial', None))
                    plan['stage'] = 'gender'
                    task.delayTime = 3.0
                    return Task.again
                if time.time() - plan['t0'] > 900:
                    ev('KM-ERR', why='the standalone pirate maker never opened in 900 s')
                    return Task.done
                task.delayTime = 1.0
                return Task.again
            if m is None:
                return Task.done
            if st == 'gender':
                if hasattr(m, 'makeRandomGender'):
                    m.makeRandomGender()
                    ev('KM-GENDER', gender=getattr(getattr(m.pirate, 'style', None), 'gender', None))
                plan['stage'] = 'pages'
                task.delayTime = 2.0
                return Task.again
            if st == 'pages':
                if plan['i'] > m.numShops + 2:
                    plan['stage'] = 'done'
                    return Task.again
                plan['i'] += 1
                if not m.guiRandomButton.isHidden():
                    m.guiRandomButton['command']()
                    plan['pages'].append(_page(m))
                    ev('KM-RANDOM', page=_page(m), index=m.currPageIndex)
                if not m.guiDoneButton.isHidden() or m.currPageIndex >= m.numShops - 1:
                    plan['stage'] = 'done'
                else:
                    m.guiNextButton['command']()
                    ev('KM-NEXT', page=m.currPageIndex)
                task.delayTime = 2.0
                return Task.again
            if st == 'done':
                STATE['name'] = _name(m)
                ev('KM-NAME', name=STATE['name'], pages=plan['pages'], custom=getattr(m.nameGui, 'customName', None))
                m.guiDoneButton['command']()
                STATE['done'] = True
                ev('KM-DONE', status=getattr(m, 'doneStatus', None))
                return Task.done
        except Exception as e:
            import traceback
            ev('KM-ERR', tb=traceback.format_exc()[-500:])
            return Task.done
        return Task.done

    taskMgr.doMethodLater(1.0, step, 'kidmaker-step')


def run(H):
    la = H.la
    H.ev('KM-INWORLD', avId=la.doId, name=la.getName(), maker=STATE['name'], done=STATE['done'], area=H.area())
    if la.doId == HOST_AV:
        H.ev('FAIL', why='refused: %d is the pirate of Host' % HOST_AV); return
    if not STATE['done']:
        H.ev('FAIL', why='in the world without the standalone pirate maker (not a new pirate on the kid path)'); return
    yield 5.0
    name = la.getName()
    if STATE['name'] and name != STATE['name']:
        H.ev('FAIL', why='the pirate is named %r in the world, the maker picked %r' % (name, STATE['name'])); return
    H.snap('kid-in-world')
    H.ev('PASS', what='kid path: new pirate %s (%d) made in the standalone pirate maker, in the world'
         % (name, la.doId), seed=SEED)
