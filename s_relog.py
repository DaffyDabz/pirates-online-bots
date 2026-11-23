"""RELOG (pir-bot, 11-17, job 4): log out and back in, and check nothing about the pirate changed.

Run on its own (BOT_AVID = a test pirate, never Host's 100000170) or from s_newplayer (NEWPLAYER_RELOG=1) right
after the tutorial. Needs THIS folder's walker.py copy: after the first login its avatar list only picks the pirate
a step puts in walker NEXT_PICK (else it would pick again, or in a new-pirate run make a second pirate).

1. Stand still in LandRoam, then snapshot (snap): position (render frame) + heading, area (type, uid, name),
   gold, every inventory stack (gear, weapons, tonics, skills, tokens), every accumulator (reputation), the
   inventory's object ids by category (ships, clothing, quests), active ship, quests held (id, complete, task states),
   tracked quest, quest history.
2. Log out the player's way: the logout hotkey message (PiratesGlobals.LogoutHotkey; PiratesClientRepository.logout
   -> gameFSM closeShard -> waitForAvatarList), the same thing the options page's Logout button sends after Yes.
3. Walker NEXT_PICK = this pirate is set before the logout; wait for the old avatar to go (RELOG-AVLIST), then for the new localAvatar in
   LandRoam, point H.la at it and put the tripwire on it again.
4. Wait RELOG_SETTLE s (inventory and quests arrive after the avatar), snapshot again, compare (compareSnap).

Lines: RELOG-START, RELOG-SNAP (before / after), RELOG-LOGOUT, RELOG-AVLIST, RELOG-BACK, RELOG-DIFF (one per
changed field), RELOG-SAME, PASS / FAIL. PASS = no field changed (position within RELOG_POS_TOL ft, heading within
RELOG_H_TOL deg). env: RELOG_POS_TOL (5), RELOG_H_TOL (20), RELOG_SETTLE (8), RELOG_SECS (240: logout + login),
RELOG_IGNORE (comma field names left out of the compare, e.g. 'h')."""
import os, sys, time, math, json

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))

HOST_AV = 100000170
POS_TOL = float(os.environ.get('RELOG_POS_TOL', '5'))
H_TOL = float(os.environ.get('RELOG_H_TOL', '20'))
SETTLE = float(os.environ.get('RELOG_SETTLE', '8'))
SECS = float(os.environ.get('RELOG_SECS', '240'))
IGNORE = set(s for s in os.environ.get('RELOG_IGNORE', '').split(',') if s)


def _plain(d):
    """Pure: a dict with str keys and sortable plain values (JSON-safe, so a snapshot can be saved and compared)."""
    return dict((str(k), v) for k, v in sorted((d or {}).items(), key=lambda kv: str(kv[0])))


def snap(H):
    """The pirate as plain values (no live objects), so it can be compared after the old avatar is gone."""
    la = H.la
    inv = la.getInventory()
    p = la.getPos(H.render)
    out = {'avId': la.doId, 'name': la.getName(),
           'pos': [round(p[0], 2), round(p[1], 2), round(p[2], 2)], 'h': round(la.getH(H.render) % 360, 1),
           'area': list(H.area() or []), 'gameState': la.getGameState()}
    if inv is not None:
        out['gold'] = inv.getGoldInPocket()
        out['stacks'] = _plain(getattr(inv, 'stacks', {}))
        out['accumulators'] = _plain(getattr(inv, 'accumulators', {}))
        out['objects'] = _plain(dict((str(c), sorted(ids)) for c, ids in getattr(inv, 'doIdsInCategory', {}).items()))
        out['ships'] = sorted(inv.getShipDoIdList())
    else:
        out['inventory'] = None
    out['activeShip'] = la.getActiveShipId() if hasattr(la, 'getActiveShipId') else None
    qs = []
    for q in la.getQuests():
        ts = None
        try:
            ts = [[getattr(t, 'progress', None), getattr(t, 'goal', None)] for t in q.getTaskStates()]
        except Exception:
            ts = None
        qs.append([q.getQuestId(), bool(q.isComplete()), ts])
    out['quests'] = sorted(qs, key=lambda r: r[0])
    out['tracked'] = getattr(la, 'activeQuestId', None)
    out['history'] = sorted(H.hist())
    return out


def _hd(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def compareSnap(before, after, posTol=POS_TOL, hTol=H_TOL, ignore=()):
    """Pure: [(field, before, after)] for every field that changed. pos: horizontal distance over posTol, or more than
    posTol up/down; h: heading over hTol deg; dict fields are compared key by key (field 'stacks.<key>');
    gameState is left out (it is LandRoam both times by the time snap runs)."""
    out = []
    skip = set(ignore) | {'gameState'}
    for k in sorted(set(before) | set(after)):
        if k in skip:
            continue
        a, b = before.get(k), after.get(k)
        if k == 'pos' and a and b:
            if _hd(a, b) > posTol or abs(a[2] - b[2]) > posTol:
                out.append(('pos', a, b))
        elif k == 'h' and a is not None and b is not None:
            d = abs((a - b + 180) % 360 - 180)
            if d > hTol:
                out.append(('h', a, b))
        elif isinstance(a, dict) and isinstance(b, dict):
            for kk in sorted(set(a) | set(b)):
                if a.get(kk) != b.get(kk):
                    out.append(('%s.%s' % (k, kk), a.get(kk), b.get(kk)))
        elif a != b:
            out.append((k, a, b))
    return out


def _la():
    import builtins
    return getattr(getattr(builtins, 'base', None), 'localAvatar', None)


def _ready(old):
    """The new localAvatar is up (not the old object), in LandRoam, with its inventory."""
    try:
        la = _la()
        return la is not None and la is not old and not la.isEmpty() and la.getGameState() == 'LandRoam' \
            and la.getInventory() is not None
    except Exception:
        return False


def _gone(old):
    """The old localAvatar is gone (LocalPirate.delete removes base.localAvatar), or a new one replaced it."""
    try:
        return _la() is not old
    except Exception:
        return False


def _sentRow(cr, data, t0):
    """One sent datagram as plain values: message name, size, and for a field update the object, class, field and
    whether its bytes unpack cleanly against the .dc (left = bytes over, short = the server's 'truncated datagram')."""
    import struct
    from otp.distributed import MsgTypes
    names = dict((v, k) for k, v in vars(MsgTypes).items() if k.startswith('CLIENT_') and isinstance(v, int))
    row = {'dt': round(time.time() - t0, 3), 'len': len(data)}
    if len(data) < 2:
        row['msg'] = 'short'; return row
    mt = struct.unpack('<H', data[:2])[0]
    row['msg'] = names.get(mt, mt)
    if row['msg'] == 'CLIENT_OBJECT_SET_FIELD' and len(data) >= 8:
        doId, fid = struct.unpack('<IH', data[2:8])
        do = cr.doId2do.get(doId)
        row.update(doId=doId, fid=fid, cls=type(do).__name__ if do else None)
        try:
            from panda3d.direct import DCPacker
            f = cr.getDcFile().getFieldByIndex(fid)
            row['field'] = f.getName() if f else None
            if f:
                p = DCPacker()
                p.setUnpackData(data[8:])
                p.beginUnpack(f)
                p.unpackSkip()
                row['ok'] = bool(p.endUnpack())
                row['left'] = len(data) - 8 - p.getNumUnpackedBytes()
        except Exception as e:
            row['err'] = repr(e)[:120]
    elif len(data) > 2:
        row['hex'] = data[2:26].hex()
    return row


def _recordSends(H, secs=6.0, cap=120):
    """Wrap cr.send for secs: every datagram the client sends goes into a list (RELOG-SENT after the logout).
    Harness only: the datagram itself still goes out unchanged. -> (rows, undo)."""
    cr, rows, t0 = H.cr, [], time.time()
    orig = cr.send

    def send(dg, _o=orig):
        try:
            if time.time() - t0 < secs and len(rows) < cap:
                rows.append(_sentRow(cr, bytes(dg.getMessage()), t0))
        except Exception as e:
            rows.append({'err': repr(e)[:120]})
        return _o(dg)

    def undo():
        try:
            if cr.__dict__.get('send') is send:
                del cr.send
        except Exception:
            pass
    cr.send = send
    return rows, undo


def logout(H):
    """Generator: log out like the player (the logout hotkey message) -> True once the old avatar is gone."""
    from pirates.piratesbase import PiratesGlobals
    la = H.la
    yield ('until', lambda: la.getGameState() == 'LandRoam', 60, 'land-roam before logout')
    can = la.getCanLogout() if hasattr(la, 'getCanLogout') else None
    H.ev('RELOG-LOGOUT', canLogout=can, gameState=la.getGameState(), area=H.area())
    if can is False:
        H.ev('act', step='relog', a='the game says this pirate cannot log out now; waiting 30 s')
        yield ('until', lambda: la.getCanLogout(), 30, 'can logout')
    rows, undo = _recordSends(H)       # 11-21 02:37: Astron ejected the client (109, truncated datagram) at this logout
    base.messenger.send(PiratesGlobals.LogoutHotkey)
    t0 = time.time()
    yield ('until', lambda: _gone(la) or time.time() - t0 > 6, 7, 'sends after logout')
    undo()
    bad = [r for r in rows if r.get('ok') is False or (r.get('left') or 0) != 0 or 'err' in r]
    H.ev('RELOG-SENT', n=len(rows), bad=bad, rows=rows[:60])
    yield ('until', lambda: _gone(la), SECS / 2, 'logged out')
    try:
        lstate = H.cr.loginFSM.getCurrentState().getName()
    except Exception:
        lstate = None
    H.ev('RELOG-AVLIST', ok=_gone(la), secs=round(time.time() - t0), loginState=lstate)
    return _gone(la)


def login(H, old):
    """Generator: wait for the walker copy to pick NEXT_PICK at the avatar list -> True when that pirate is up."""
    import sys; __main__ = sys.modules.get('pir_walker') or sys.modules['__main__']   # the walker, not PiratesStart
    t0 = time.time()
    yield ('until', lambda: _ready(old) or __main__.NEXT_PICK[0] is None, 30, 'avatar list pick')
    if __main__.NEXT_PICK[0] is not None:
        # the list came up before the pick was set, or never came: ask for it again (waitForAvatarList -> pick)
        try:
            H.ev('act', step='relog', a='avatar list again', loginState=H.cr.loginFSM.getCurrentState().getName())
            H.cr.loginFSM.request('waitForAvatarList')
        except Exception as e:
            H.ev('act', step='relog', a='avatar list re-request failed', err=repr(e))
    yield ('until', lambda: _ready(old), SECS / 2, 'logged back in')
    if not _ready(old):
        H.ev('FAIL', why='did not log back in as %d in %d s' % (old.doId, SECS / 2)); return False
    H.la = _la()
    try:
        __main__.install_tripwire(H.la)
    except Exception as e:
        H.ev('act', step='relog', a='tripwire not put back', err=repr(e))
    H.ev('RELOG-BACK', avId=H.la.doId, secs=round(time.time() - t0), area=H.area())
    if H.la.doId != old.doId:
        H.ev('FAIL', why='logged back in as %d, not %d' % (H.la.doId, old.doId)); return False
    return True


def relogStart(H):
    """None when this walker can relog this pirate, else why not."""
    import sys; __main__ = sys.modules.get('pir_walker') or sys.modules['__main__']   # the walker, not PiratesStart
    if H.la.doId == HOST_AV:
        return 'refused: %d is the pirate of Host' % HOST_AV
    if not hasattr(__main__, 'NEXT_PICK'):
        return 'this walker.py has no NEXT_PICK: use the pir-bot job 4 walker copy'
    return None


def relog(H, tag='relog'):
    """Generator: snapshot, log out, log back in, snapshot, compare -> the diff list (None when it could not relog)."""
    import sys; __main__ = sys.modules.get('pir_walker') or sys.modules['__main__']   # the walker, not PiratesStart
    la = H.la
    why = relogStart(H)
    if why:
        H.ev('FAIL', why=why); return None
    yield ('until', lambda: la.getGameState() == 'LandRoam', 60, 'land-roam')
    yield 3                                   # stand still: the last position update reaches the server
    before = snap(H)
    H.ev('RELOG-SNAP', when='before', tag=tag, snap=before)
    __main__.NEXT_PICK[0] = la.doId           # the walker copy picks this pirate at the avatar list
    if not (yield from logout(H)):
        __main__.NEXT_PICK[0] = None
        H.ev('FAIL', why='the logout never reached the avatar list'); return None
    if not (yield from login(H, la)):
        return None
    yield SETTLE
    after = snap(H)
    H.ev('RELOG-SNAP', when='after', tag=tag, snap=after)
    diffs = compareSnap(before, after, ignore=IGNORE)
    for f, a, b in diffs:
        H.ev('RELOG-DIFF', field=f, before=a, after=b)
    if not diffs:
        H.ev('RELOG-SAME', fields=sorted(k for k in before if k not in IGNORE))
    return diffs


def run(H):
    H.ev('RELOG-START', avId=H.la.doId, posTol=POS_TOL, hTol=H_TOL, ignore=sorted(IGNORE), area=H.area())
    diffs = yield from relog(H)
    if diffs is None:
        return
    if diffs:
        H.ev('FAIL', why='%d field(s) changed across the relog' % len(diffs), fields=[d[0] for d in diffs]); return
    H.ev('PASS', what='logged out and back in: position, gear, gold, quests and ships unchanged', avId=H.la.doId)
