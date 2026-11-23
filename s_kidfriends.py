"""KID FRIENDS (pir-boat, 11-17): press every friends button that used to throw a kid back to the login screen, and
check he stays in the game. Proves patch 0132 (client: otp/friends/PlayerFriendsManager.py).

Why it crashed before 0132: the client's PlayerFriendsManager (doId 4687) is a client global, but no server object
answers to it on the family server (4687 is not an uberdog in astrond.yml). Astron disconnects a client that sends to
an object it does not know (CLIENT_DISCONNECT_MISSING_OBJECT). 0132 gives PlayerFriendsManager its own sendUpdate that
drops every send with a warning ('No player friends on this server: <field> dropped').

What it presses, in this order (each press is the button's own command, btn.commandFunc, only while it is NORMAL):
1. A pirate's Relationships panel (guiMgr.handleRelationships -> RelationshipChooser): the PLAYER FRIEND button
   (-> FriendInviter, isPlayerInvite -> playerFriendsManager.sendRequestInvite: 'requestInvite').
   The panel is opened for another player's pirate in view (never 100000170, never himself). With nobody else in
   view, or the button greyed out (no common chat), it opens on himself and sends the invite directly (path=direct).
2. The same panel again: the SECRETS button (-> PirateFriendSecret.showFriendSecret). When that opens the Secret
   Friends window (FriendSecret):
   a. GET A SECRET (getSecret -> 'requestUnlimitedSecret', or 'requestLimitedSecret' when a parent password is needed)
   b. a fresh window: type a secret into the box, press ENTER (ok1 -> 'requestUseUnlimitedSecret' / Limited), wait out
      the window's own 10 s answer timer, then CANCEL.
   If the game shows a chat warning or the parent-login window instead, those sends go directly (path=direct).
3. The other player-friend sends no button reaches today, directly: requestDecline, requestRemove, whisperTo,
   whisperWLTo, whisperSCTo, whisperSCCustomTo, whisperSCEmoteTo (all to the same target; all dropped by 0132).
The avatar-friend button is NOT pressed (it is not one of the crashers and it would invite a real kid); its state is
logged.

After every press it waits KID_FRIENDS_WAIT (6) s for a kick: the login FSM in 'noConnection', cr.isConnected() false,
or his pirate gone from doId2do. A kick is a FAIL at once (and the run ends there).

Guard: without 0132 in the loaded client (PlayerFriendsManager has no sendUpdate of its own) it presses nothing and
FAILs 'client lacks 0132 (patch-8 not installed)'. KID_RUN_UNPATCHED=1 presses anyway, to show the old kick.

env: KID_FRIENDS_AT (island uid to start on; default Tortuga; '' = stay where he logs in), KID_FRIENDS_WAIT (6),
     KID_RUN_UNPATCHED (0).
Lines: KID-FRIENDS-START, PATCH-CHECK, STAGE step=friends what=on-island / target / chooser / secret-window /
secret-sent / direct, PRESS (button, state), FRIENDS-SEND (field: every send the manager tried), FRIENDS-RESULT (one per
press: want, sent, online, path), CHAT-AFTER, then PASS / FAIL. Run time after boot: about 1.5 min."""
import os, sys, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402
import s_story   # noqa: E402

NEVER = 100000170
AT = os.environ.get('KID_FRIENDS_AT', s_lanes.TORTUGA)
WAIT = float(os.environ.get('KID_FRIENDS_WAIT', '6'))
RUN_UNPATCHED = os.environ.get('KID_RUN_UNPATCHED') == '1'
STEP = 'friends'


def hasPatch():
    """0132 is in the loaded client: PlayerFriendsManager defines its own sendUpdate (the stock one is inherited)."""
    from otp.friends.PlayerFriendsManager import PlayerFriendsManager as P
    return 'sendUpdate' in P.__dict__


def online(H):
    cr = H.cr
    try:
        if cr.loginFSM.getCurrentState().getName() == 'noConnection':
            return False
    except Exception:
        pass
    try:
        if not cr.isConnected():
            return False
    except Exception:
        pass
    la = H.la
    return la is not None and la.doId in cr.doId2do


def pickTarget(la, objs, never=NEVER):
    """Pure. objs = [(doId, class name, name)] in view -> (doId, name, why): the nearest-listed other player pirate
    (never `never`, never himself), else himself."""
    for doId, cls, name in objs:
        if cls == 'DistributedPlayerPirate' and doId not in (la[0], never):
            return doId, name, 'another player in view'
    return la[0], la[1], 'nobody else in view: his own panel, the sends go direct'


def verdict(results, err=None):
    """Pure. results = [{'press', 'want', 'sent', 'online', 'path'}], err = the step's own error line -> (ok, why)."""
    if err:
        return False, 'the step itself broke after %d presses: %s (see KID-STEP-ERROR)' % (len(results), err)
    if not results:
        return False, 'nothing was pressed'
    off = [r['press'] for r in results if not r['online']]
    if off:
        return False, 'pressing %s dropped him from the game' % off[0]
    miss = [r['press'] for r in results if not r['sent']]
    if miss:
        return False, 'no send for %s (the button did nothing: see FRIENDS-RESULT)' % ', '.join(miss)
    return True, 'every friends button / send that used to kick him was used; each send was dropped, he stayed in'


def run(H):
    la, cr = H.la, H.cr
    if la.doId == NEVER:
        H.ev('FAIL', why='refused: pirate 100000170 is never a test pirate'); return
    try:
        import s_fast
        if not s_fast.STATE.get('installed'):
            s_fast.install(H)
    except ImportError:
        pass
    from direct.gui import DirectGuiGlobals as DGG
    from pirates.friends import PirateFriendSecret as PFS

    def unloadSecret():
        # The window starts a 10 s 'timeoutSecretResponse' task after ENTER and never removes it itself;
        # unloading before it fires would let it write to a destroyed window and close the game.
        taskMgr.remove('timeoutSecretResponse')
        PFS.unloadFriendSecret()

    H.ev('KID-FRIENDS-START', at=AT or 'stay', wait=WAIT, runUnpatched=RUN_UNPATCHED)
    yield ('until', lambda: la.getGameState() == 'LandRoam', 90, 'LandRoam')
    if AT:
        ok = yield from s_lanes.onIsland(H, STEP, AT)
        if not ok:
            H.ev('FAIL', why='could not reach the test island %s' % AT, area=H.area()); return
    s_lanes.stage(H, STEP, 'on-island')

    pfm = cr.playerFriendsManager
    patched = hasPatch()
    H.ev('PATCH-CHECK', patch='0132', present=patched, cls=type(pfm).__name__,
         mro=[c.__name__ for c in type(pfm).__mro__[:4]])
    if not patched and not RUN_UNPATCHED:
        H.ev('FAIL', why='client lacks 0132 (patch-8 not installed): pressing would drop him to the login screen, '
                         'so nothing was pressed (KID_RUN_UNPATCHED=1 presses anyway)'); return

    sent = []
    orig = pfm.sendUpdate

    def su(fieldName, args=[], sendToId=None):
        sent.append(fieldName)
        H.ev('FRIENDS-SEND', field=fieldName, dropped=patched)
        return orig(fieldName, args, sendToId)
    pfm.sendUpdate = su            # instance attribute: every pfm.send* calls self.sendUpdate

    results = []
    err = []
    gm = la.guiMgr

    def press(btn, name):
        try:
            st = btn['state']
        except Exception as e:
            H.ev('PRESS', button=name, err=repr(e)); return False
        H.ev('PRESS', button=name, state=st, text=str(btn['text'])[:40] if btn['text'] else None)
        if st != DGG.NORMAL:
            return False
        btn.commandFunc(None)
        return True

    def after(name, want, mark, path):
        """Generator: wait for a kick, then one FRIENDS-RESULT. -> False when he was kicked (stop)."""
        yield ('upto', lambda: not online(H), WAIT, 'kick after ' + name)
        new = sent[mark:]
        r = {'press': name, 'want': want, 'sent': any(f in want.split('|') for f in new), 'online': online(H),
             'path': path, 'fields': new}
        results.append(r)
        H.ev('FRIENDS-RESULT', **r)
        return r['online']

    def direct(name, fn, args, want):
        mark = len(sent)
        H.ev('PRESS', button=name, path='direct', args=[str(a)[:30] for a in args])
        try:
            fn(*args)
        except Exception as e:
            H.ev('FRIENDS-ERR', press=name, err=repr(e))
        return (yield from after(name, want, mark, 'direct'))

    try:
        # 0. the pirate whose panel he opens
        objs = sorted(((o.doId, type(o).__name__, getattr(o, 'getName', lambda: '?')()) for o in list(cr.doId2do.values())
                       if type(o).__name__ == 'DistributedPlayerPirate'),
                      key=lambda t: s_story.hdist(H, cr.doId2do[t[0]]))
        tid, tname, why = pickTarget((la.doId, la.getName()), objs)
        if tid == NEVER:
            H.ev('FAIL', why='refused: the target would be 100000170'); return
        s_lanes.stage(H, STEP, 'target', target=tid, targetName=tname, why=why, others=len(objs))

        # 1. Relationships -> Player Friend
        gm.handleRelationships(tid, tname)
        rc = gm.relationshipChooser
        yield 1
        s_lanes.stage(H, STEP, 'chooser', avFriend=rc.avFriendButton['state'], plFriend=rc.plFriendButton['state'],
                      secrets=rc.secretsButton['state'])
        mark = len(sent)
        if press(rc.plFriendButton, 'player-friend'):
            yield 1
            inv = gm.friendInviter
            try:
                ist = inv.fsm.getCurrentState().getName() if inv else None
            except Exception as e:
                ist = repr(e)
            H.ev('INVITER', state=ist, target=tid)
            if not (yield from after('player-friend', 'requestInvite', mark, 'button')):
                return
            if 'requestInvite' not in sent[mark:]:
                results.pop()      # the button worked but sent nothing (his own panel): send it directly instead
                if not (yield from direct('player-friend', pfm.sendRequestInvite, (tid,), 'requestInvite')):
                    return
            try:
                if gm.friendInviter:
                    gm.friendInviter.destroy()
                    gm.friendInviter = None
            except Exception as e:
                H.ev('INVITER-CLOSE', err=repr(e))
        else:
            try:
                rc.destroy()
            except Exception:
                pass
            if not (yield from direct('player-friend', pfm.sendRequestInvite, (tid,), 'requestInvite')):
                return
        yield 1

        # 2. Relationships -> Secrets
        gm.handleRelationships(tid, tname)
        rc = gm.relationshipChooser
        yield 1
        secretWant = 'requestUnlimitedSecret|requestLimitedSecret'
        useWant = 'requestUseUnlimitedSecret|requestUseLimitedSecret'
        win = None
        if press(rc.secretsButton, 'secrets'):
            yield 1.5
            win = PFS.globalFriendSecret
            s_lanes.stage(H, STEP, 'secret-window', kind=type(win).__name__ if win else None,
                          chat=cr.isPaid() if hasattr(cr, 'isPaid') else None,
                          allowSecret=cr.allowSecretChat(), needParent=cr.needParentPasswordForSecretChat())
        else:
            try:
                rc.destroy()
            except Exception:
                pass
        if win is not None and type(win).__name__ == 'FriendSecret':
            mark = len(sent)
            if press(win.getSecret, 'get-secret'):
                if not (yield from after('get-secret', secretWant, mark, 'button')):
                    return
            unloadSecret()
            yield 1
            PFS.openFriendSecret(PFS.AccountSecret)       # a fresh window, the way a second press of Secrets opens it
            win = PFS.globalFriendSecret
            yield 1
            win.enterSecret.set('kid test secret')
            mark = len(sent)
            if press(win.ok1, 'enter-secret'):
                if not (yield from after('enter-secret', useWant, mark, 'button')):
                    return
                yield ('upto', lambda: not online(H), max(0.0, 11.0 - WAIT), 'the window answer timer (10 s)')
                s_lanes.stage(H, STEP, 'secret-sent', online=online(H))
                if not online(H):
                    results[-1]['online'] = False
                    H.ev('FAIL', why='he was dropped while the secret window waited for an answer'); return
                press(win.cancel, 'secret-cancel')
                yield 1
            unloadSecret()
        else:
            if win is not None:
                unloadSecret()
            H.ev('SECRETS-NO-WINDOW', kind=type(win).__name__ if win else None,
                 why='the game showed a warning or the parent login, not the Secret Friends window: sends go direct')
            if not (yield from direct('get-secret', pfm.sendRequestUnlimitedSecret, (), secretWant)):
                return
            if not (yield from direct('enter-secret', pfm.sendRequestUseUnlimitedSecret, ('kid test secret',), useWant)):
                return
        try:
            H.ev('CHAT-AFTER', chat=la.chatMgr.fsm.getCurrentState().getName())
        except Exception as e:
            H.ev('CHAT-AFTER', err=repr(e))

        # 3. the sends no button reaches today
        s_lanes.stage(H, STEP, 'direct')
        for name, fn, args, want in (
                ('limited-secret', pfm.sendRequestLimitedSecret, ('', ''), 'requestLimitedSecret'),
                ('use-limited-secret', pfm.sendRequestUseLimitedSecret, ('kid test secret', '', ''), 'requestUseLimitedSecret'),
                ('decline', pfm.sendRequestDecline, (tid,), 'requestDecline'),
                ('remove', pfm.sendRequestRemove, (tid,), 'requestRemove'),
                ('whisper', pfm.sendWhisper, (tid, 'hi'), 'whisperTo'),
                ('wl-whisper', pfm.sendWLWhisper, (tid, 'hi'), 'whisperWLTo'),
                ('sc-whisper', pfm.sendSCWhisper, (tid, 1), 'whisperSCTo'),
                ('sc-custom-whisper', pfm.sendSCCustomWhisper, (tid, 1), 'whisperSCCustomTo'),
                ('sc-emote-whisper', pfm.sendSCEmoteWhisper, (tid, 1), 'whisperSCEmoteTo')):
            if not (yield from direct(name, fn, args, want)):
                return
    except Exception as e:
        err.append('%s: %s' % (type(e).__name__, e))
        H.ev('KID-STEP-ERROR', err=err[0], tb=traceback.format_exc())
    finally:
        try:
            del pfm.sendUpdate
        except Exception:
            pass
        try:
            unloadSecret()
        except Exception:
            pass
        ok, why = verdict(results, err[0] if err else None)
        if ok:
            H.ev('PASS', what=why, presses=[(r['press'], r['path']) for r in results], sends=sent, patched=patched)
        else:
            H.ev('FAIL', why=why, presses=[(r['press'], r['path'], r['sent'], r['online']) for r in results],
                 sends=sent, patched=patched)
