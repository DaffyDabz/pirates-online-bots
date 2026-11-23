"""NEW PLAYER (pir-bot, 11-17, job 4): a fresh test pirate made in the pirate maker with random choices, named, the
tutorial played, then logged out (and with NEWPLAYER_RELOG=1 logged back in and checked, s_relog).

Run with walker BOT_NEW_PIRATE=1 on a test account with a free slot (BOT_ACCOUNT, never Host's account; the run
makes the pirate in the first empty slot). Needs THIS folder's walker.py copy (after the first login its avatar list
picks only what s_relog asks for, so the logout never makes a second pirate).

The pirate maker: every choice goes through the maker's own buttons and calls, like a player clicking:
  gender = MakeAPirate.makeRandomGender (the gender page's random pick), then on every page the page's Random
  button (guiRandomButton -> handleRandom: body / head / mouth / eyes / nose / ears / hair / clothes / name; the
  name page's Random = makeRandomName, a pick-a-name, so no name review), Next to the next page, Done at the end.
  Python's random is seeded from NEWPLAYER_SEED (default: the clock), logged, so a run's pirate can be made again.
Then the rest of s_tutorial (out of the jail, the sea chest, Bo Beck's boat, the cannon, the Jolly Roger scene,
Port Royal), with s_tutorial's own PASS renamed TUTORIAL-PASS (this step's PASS needs the logout too).
At the end it writes newplayer-last.json beside the step (avId, name, seed, account, dna, time) for the next
runs (s_relog, s_storychain: BOT_AVID = that avId), and the first story checkpoint (s_storychain.writeCheckpoint).

Lines: NEWPLAYER-START (seed, account), MAP-OPEN, MAP-GENDER, MAP-RANDOM (page, shop) for each page, MAP-NEXT,
MAP-NAME, MAP-DONE, PIRATE-MADE, the tutorial's own lines, TUTORIAL-PASS, NEWPLAYER-SAVED, RELOG-* (with
NEWPLAYER_RELOG=1), NEWPLAYER-LOGGED-OUT, PASS / FAIL.
PASS = a new pirate (not 100000170) finished the tutorial in Port Royal and logged out (and, with NEWPLAYER_RELOG=1,
came back unchanged). env: NEWPLAYER_SEED, NEWPLAYER_RELOG (0), NEWPLAYER_FILE (newplayer-last.json)."""
import os, sys, time, json, random

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_tutorial   # noqa: E402
import s_relog      # noqa: E402

HOST_AV = 100000170
HERE = os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT']))
SEED = int(os.environ.get('NEWPLAYER_SEED') or int(time.time()))
RELOG = os.environ.get('NEWPLAYER_RELOG') == '1'
FILE = os.environ.get('NEWPLAYER_FILE') or os.path.join(HERE, 'newplayer-last.json')


def pageName(m):
    try:
        from pirates.piratesbase import PLocalizer
        return PLocalizer.MakeAPiratePageNames[m.currPageIndex]
    except Exception:
        return m.currPageIndex


def mapName(m):
    """The name the maker will give the pirate (its name page), best effort."""
    for get in (lambda: m.nameGui.getNumericName(), lambda: m.nameGui._getName(), lambda: m.nameGui.getName(),
                lambda: m.pirate.getName(), lambda: m.pirate.style.getName()):
        try:
            n = get()
            if n:
                return n
        except Exception:
            pass
    return None


def randomMaker(H):
    """Generator (in place of s_tutorial.makeAPirate): random gender, Random on every page, Done -> True when made."""
    ok = yield from s_tutorial.wait(H, lambda: s_tutorial.tstate(H) == 'Act1MakeAPirate'
                                    and getattr(s_tutorial.tut(H), 'map', None), 300, 'make-a-pirate')
    if not ok:
        return False
    m = s_tutorial.tut(H).map
    ok = yield from s_tutorial.wait(H, lambda: getattr(m, 'guiNextButton', None) is not None
                                    and m.currPageIndex is not None, 60, 'map-loaded')
    if not ok:
        return False
    random.seed(SEED)
    H.ev('MAP-OPEN', page=m.currPageIndex, pages=m.numShops, seed=SEED)
    yield 3.0
    if hasattr(m, 'makeRandomGender'):
        m.makeRandomGender()
        H.ev('MAP-GENDER', gender=getattr(getattr(m.pirate, 'style', None), 'gender', None))
        yield 2.0
    pages = []
    for i in range(m.numShops + 2):
        if not m.guiRandomButton.isHidden():
            m.guiRandomButton['command']()
            pages.append(pageName(m))
            H.ev('MAP-RANDOM', page=pageName(m), index=m.currPageIndex, shop=getattr(m, 'shop', None))
            yield 1.5
        if not m.guiDoneButton.isHidden() or m.currPageIndex >= m.numShops - 1:
            break
        m.guiNextButton['command']()
        H.ev('MAP-NEXT', page=m.currPageIndex)
        yield 2.0
    name = mapName(m)
    H.ev('MAP-NAME', name=name, randomPages=pages)
    H.snap('make-a-pirate')
    try:
        dna = str(m.pirate.style)[:600]
    except Exception:
        dna = None
    m.guiDoneButton['command']()
    H.ev('MAP-DONE', status=getattr(m, 'doneStatus', None), name=name, dna=dna)
    RESULT['dna'] = dna
    ok = yield from s_tutorial.wait(H, lambda: s_tutorial.tstate(H) == 'EscapeFromLA', 90, 'populated')
    H.ev('PIRATE-MADE', pirate=H.la.getName(), **s_tutorial.info(H))
    return ok


RESULT = {}


def record(avId, name, seed, account, dna, t):
    """Pure: the newplayer-last.json record."""
    return {'avId': avId, 'name': name, 'seed': seed, 'account': account, 'dna': dna, 'made': t}


def early(ev):
    s_tutorial.early(ev)


def run(H):
    acct = os.environ.get('BOT_ACCOUNT') or os.environ.get('pocUsername')
    H.ev('NEWPLAYER-START', seed=SEED, account=acct, relog=RELOG, new=os.environ.get('BOT_NEW_PIRATE'))
    if os.environ.get('BOT_NEW_PIRATE') != '1':
        H.ev('FAIL', why='needs BOT_NEW_PIRATE=1 (log in to an empty slot and make a pirate)'); return
    if H.la.doId == HOST_AV:
        H.ev('FAIL', why='refused: %d is the pirate of Host' % HOST_AV); return
    os.environ.pop('TUT_THEN_STORY', None)      # this step ends at Port Royal; the story is s_storychain's
    s_tutorial.makeAPirate = randomMaker
    ev0 = H.ev
    passed = {}

    def ev(_ev, /, **kw):         # not "name": MAP-NAME passes name=
        if _ev == 'PASS':                       # the tutorial's PASS is a part of this step, not its end
            passed['tut'] = kw
            _ev = 'TUTORIAL-PASS'
        return ev0(_ev, **kw)
    H.ev = ev
    try:
        yield from s_tutorial.run(H)
    finally:
        H.ev = ev0
    if 'tut' not in passed:
        H.ev('FAIL', why='the tutorial did not reach Port Royal (TUTORIAL-STOPPED says where)'); return
    la = H.la
    rec = record(la.doId, la.getName(), SEED, acct, RESULT.get('dna'), time.strftime('%Y-%m-%dT%H:%M:%S'))
    try:
        with open(FILE, 'w') as f:
            json.dump(rec, f, indent=1)
        H.ev('NEWPLAYER-SAVED', file=FILE, **rec)
    except Exception as e:
        H.ev('NEWPLAYER-SAVE-ERR', file=FILE, err=repr(e))
    try:
        import s_storychain
        s_storychain.writeCheckpoint(H, 'tutorial-done')
    except Exception as e:
        H.ev('act', step='newplayer', a='first story checkpoint not written', err=repr(e))
    if RELOG:
        diffs = yield from s_relog.relog(H, 'newplayer')
        if diffs is None:
            return
        if diffs:
            H.ev('FAIL', why='%d field(s) changed across the relog' % len(diffs), fields=[d[0] for d in diffs]); return
    import sys; __main__ = sys.modules.get('pir_walker') or sys.modules['__main__']   # the walker, not PiratesStart
    __main__.NEXT_PICK[0] = None                 # stay at the avatar list: never a second pirate
    if not (yield from s_relog.logout(H)):
        H.ev('FAIL', why='the logout never reached the avatar list'); return
    H.ev('NEWPLAYER-LOGGED-OUT', avId=rec['avId'], name=rec['name'])
    H.ev('PASS', what='new pirate %s (%d) made with random choices, tutorial done, logged out%s'
         % (rec['name'], rec['avId'], ', relog unchanged' if RELOG else ''), seed=SEED)
