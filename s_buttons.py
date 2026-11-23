"""Gap 10 (11-20, games lane): the every-button walk. One test pirate presses the buttons a kid can reach that no other
walk presses, each the game's own way, and each step checks the server answered.

Steps (BTN_STEPS, in this order):
  1 emote     a chat emote ('dance' or the first one his gender may do): the server's playEmote comes back for it.
  2 code      "/code bottest" (what the chat command calls): the code service answers "Code Redemption Failed" or
              "Code Redeemed" within BTN_CODE_SECS. Before code-0001 is live it answers nothing (FAIL).
  3 musician  Port Royal tavern 2's musician: talk to him, buy a song for 5 gold. The server's playMusic comes back
              and 5 gold is gone. (Sound is off in a hidden game; the song's name is logged instead.)
  4 respec    Port Royal blacksmith 1's trainer: Respec -> Cutlass -> Yes. Gold falls by the respec cost and the
              cutlass skills go back to their base. If no weapon has a point to take back, one cutlass point is
              given first (magic word givePlayerStack), and gold for the cost.

Not walked, and why (logged as BTN-SKIP): crew buffs (a ship skill in a sea battle: boats' lane), lockpicks (no lock
objects in the world data), Vitae (set on a knockout in combat: the combat walks see it).

The run's verdict is the final PASS / FAIL line; each step's own is BTN-STEP. Never Host's pirate: a run logged in
as 100000170 FAILs at once and does nothing.
Env: BTN_STEPS (emote,code,musician,respec), BTN_CODE (bottest), BTN_CODE_SECS (15).
Lines: BTN-START, BTN-SKIP, BTN-STEP, EMOTE-PICK/BACK, CODE-SENT/ANSWER, MUSIC-NPC/MENU/BUY/PLAY/DONE,
RESPEC-GIVE/NPC/MENU/PICK/CONFIRM/DONE, sys-msg, ACT-SUB / ACT-STALL / ACT-ERROR (as s_activities)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes        # noqa: E402
import s_story        # noqa: E402
import s_activities as A   # noqa: E402

HOST = 100000170
ORDER = ['emote', 'code', 'musician', 'respec']
STEPS = [s.strip() for s in os.environ.get('BTN_STEPS', ','.join(ORDER)).split(',') if s.strip()]
CODE = os.environ.get('BTN_CODE', 'bottest')
CODE_SECS = float(os.environ.get('BTN_CODE_SECS', '15'))
TALK = A.TALK
PR = '1150922126.8dzlu'                                            # Port Royal
MUSIC_AREA, MUSIC_UID, MUSIC_POS = '1153419634.08dzlu0', '1181610880.0dchiappe', (-18.4, 32.3, 1.0)
TRAIN_AREA, TRAIN_UID, TRAIN_POS = '1153423464.2dzlu0', '1213222099.15aapatel', (-5.0, 8.0, 0.0)
SKIPPED = {'crew buffs': 'a ship skill in a sea battle (boats lane)',
           'lockpicks': 'no lock objects in the world data, so no kid can reach one',
           'Vitae': 'set on a knockout in combat; the combat walks see it'}


def toNpcIn(H, step, area, uid, pos, who):
    """Generator: to Port Royal, through the doors into area, to the NPC's spot, then up to him.
    -> (npc, None) / (None, why)."""
    if not (yield from s_lanes.onIsland(H, step, PR)):
        return None, 'could not get to Port Royal'
    npc = A.byUid(H, uid)
    if npc is None or s_story.hereArea(H) != area:
        r = yield from s_lanes.walkTo(H, step, lambda st: s_story.goto(H, st, area, pos=pos, arrive=TALK * 2,
                                                                         tag='to-' + step), 300, who)
        if r is None:
            return None, 'could not walk to %s (in %s)' % (who, area)
        yield ('until', lambda: A.byUid(H, uid) is not None, 20, who + ' in view')
        npc = A.byUid(H, uid)
        if npc is None:
            return None, '%s is not in view at his spot' % who
    r = yield from s_lanes.walkTo(H, step, lambda st: True if s_story.near(H, npc, TALK, st, tag=step)
                                  else 'walk-to-' + step, 120, who)
    if r is None:
        return None, 'could not reach %s (%.0f ft)' % (who, s_story.hdist(H, npc))
    H.walk_cancel()
    return npc, None


# ---------------- 1 emote

def emote(H):
    from pirates.piratesbase import PLocalizer
    from otp.otpbase import OTPLocalizer
    from otp.speedchat import SpeedChatGlobals
    la = H.la
    yield from A.landRoam(H, 20, 'emote roam')
    H.walk_cancel()
    yield 1
    pick = None
    names = ['dance'] + sorted(k for k in PLocalizer.EmoteCommands if k != 'dance')
    for name in names:
        eid = PLocalizer.EmoteCommands.get(name)
        e = la.getEmote(eid) if eid in OTPLocalizer.Emotes else None
        if e and (not e[4] or e[4] == la.style.gender):
            pick = (name, eid)
            break
    if pick is None:
        H.ev('FAIL', why='no chat emote his gender may do'); return
    name, eid = pick
    H.ev('EMOTE-PICK', name=name, id=eid, gs=la.getGameState(), weapon=bool(la.isWeaponDrawn))
    if la.isWeaponDrawn:
        H.ev('FAIL', why='his weapon is out, so the game plays no emote'); return
    got, saved = [], []
    A.wrapInst(la, 'playEmote', lambda i, *a: got.append(i), saved)
    try:
        messenger.send(SpeedChatGlobals.SCEmoteMsgEvent, [eid])        # what typing /dance sends
        yield ('until', lambda: eid in got, 10, 'emote back')
    finally:
        A.unwrap(saved)
    gs = la.getGameState()
    H.ev('EMOTE-BACK', got=got, gs=gs)
    if gs == 'Emote':
        la.b_setGameState('LandRoam')
    yield from A.landRoam(H, 20, 'emote end')
    if eid not in got:
        H.ev('FAIL', why='/%s: the server never played the emote back (10 s, state %s)' % (name, gs)); return
    H.ev('PASS', what='/%s played (the server sent playEmote %d back)' % (name, eid))


# ---------------- 2 code

def code(H):
    from pirates.piratesbase import PLocalizer
    la = H.la
    good, bad = str(PLocalizer.CodeRedemptionGood), str(PLocalizer.CodeRedemptionBad)
    msgs, saved = [], []
    ca = getattr(H.B, 'chatAssistant', None)
    if ca is None:
        H.ev('FAIL', why='no chat assistant to show the answer'); return
    A.wrapInst(ca, 'receiveGameMessage', lambda m, *a, **k: msgs.append(str(m)), saved)
    t0 = time.time()
    try:
        la.submitCodeToServer(CODE)                    # what "/code X" in chat calls
        H.ev('CODE-SENT', code=CODE)
        yield ('until', lambda: any(good in m or bad in m for m in msgs), CODE_SECS, 'code answer')
    finally:
        A.unwrap(saved)
    ans = next((m for m in msgs if good in m or bad in m), None)
    H.ev('CODE-ANSWER', answer=ans, msgs=msgs[-4:], secs=round(time.time() - t0, 1))
    if ans is None:
        H.ev('FAIL', why='"/code %s" got no answer in %d s' % (CODE, CODE_SECS)); return
    H.ev('PASS', what='"/code %s" answered: %s' % (CODE, ans[:60]))


# ---------------- 3 musician

def buySong(H, npc, song, played, g0, PGG):
    """Generator: talk to the musician and buy song. -> None, or why it could not (the caller leaves him)."""
    la = H.la
    yield from A.talk(H, npc, lambda: getattr(npc, 'storeMenuGUI', None) is not None, 25)
    gui = getattr(npc, 'storeMenuGUI', None)
    cur = getattr(getattr(H.B, 'musicMgr', None), 'current', None)
    H.ev('MUSIC-MENU', gui=type(gui).__name__ if gui else None, gs=la.getGameState(),
         playing=getattr(cur, 'name', None))
    if gui is None:
        return 'no song list after talking to the musician (25 s, state %s)' % la.getGameState()
    yield 1.5
    before = len(played)
    gui.handleBuyItem((song,), PGG.InventoryAdd)              # the song's Buy button
    H.ev('MUSIC-BUY', song=song, via='button')
    yield ('until', lambda: len(played) > before, 10, 'music back')
    if len(played) == before and getattr(npc, 'storeMenuGUI', None) is not None:
        # the button refused (it plays only over the tavern's own tune, and a hidden game has no sound): send his
        # request the way the button does, to check the server side
        H.ev('MUSIC-BUY', song=song, via='requestMusic', why='the button sent nothing',
             playing=getattr(getattr(H.B.musicMgr, 'current', None), 'name', None))
        messenger.send('requestMusic', [song])
        yield ('until', lambda: len(played) > before, 10, 'music back')
    yield ('until', lambda: s_lanes.gold(H) == g0 - 5, 5, 'music paid')
    return None


def musician(H):
    from pirates.economy import EconomyGlobals as EG
    from pirates.piratesgui import PiratesGuiGlobals as PGG
    from pirates.distributed import InteractGlobals as IG
    la = H.la
    if s_lanes.gold(H) < 5:
        H.mw('gold 20')
        yield ('until', lambda: s_lanes.gold(H) >= 5, 10, 'music gold')
    npc, why = yield from toNpcIn(H, 'musician', MUSIC_AREA, MUSIC_UID, MUSIC_POS, 'the musician')
    if npc is None:
        H.ev('FAIL', why=why); return
    H.ev('MUSIC-NPC', npc=npc.doId, d=round(s_story.hdist(H, npc), 1), here=H.area())
    played, saved = [], []
    A.wrapInst(npc, 'playMusic', lambda s, *a: played.append(s), saved)
    song = EG.MUSIC_SHELF[0]
    g0 = s_lanes.gold(H)
    try:
        why = yield from buySong(H, npc, song, played, g0, PGG)
    finally:
        A.unwrap(saved)
    yield from A.leaveNpc(H, npc, IG)
    if why:
        H.ev('FAIL', why=why); return
    g1 = s_lanes.gold(H)
    H.ev('MUSIC-DONE', played=played, gold=[g0, g1])
    if not played:
        H.ev('FAIL', why='bought a song, the server never played it back (gold %d -> %d)' % (g0, g1)); return
    if g0 - g1 != 5:
        H.ev('FAIL', why='the song played, but gold %d -> %d (cost 5)' % (g0, g1)); return
    H.ev('PASS', what='the musician played song %d for 5 gold' % played[0])


# ---------------- 4 respec

def cutlassPts(H, IT):
    inv = H.la.getInventory()
    return {s: inv.getStackQuantity(s) for s in range(IT.begin_WeaponSkillCutlass, IT.end_WeaponSkillCutlass)
            if s not in IT.DontResetSkills}


def overBase(pts, IT):
    return sum(max(0, q - (2 if s in IT.StartingSkills else 1)) for s, q in pts.items())


def pressRespec(H, npc, IG, IT, g0, cost, extra):
    """Generator: talk to the trainer, Respec -> Cutlass -> Yes. -> None, or why it could not (the caller leaves)."""
    la = H.la
    yield from A.talk(H, npc, lambda: la.getGameState() == 'NPCInteract' and
                      getattr(npc, 'interactGUI', None) is not None, 25)
    inMenu, lit, ids = A.menuOn(npc, IG.RESPEC, IG)
    H.ev('RESPEC-MENU', options=ids, respec=[inMenu, lit], gs=la.getGameState())
    if not inMenu:
        return 'the trainer has no Respec button (menu %s, state %s)' % (ids, la.getGameState())
    if not lit:
        return 'the Respec button is not lit, with %d cutlass points to take back' % extra
    yield 1.5
    npc.selectOptionConfirm(IG.RESPEC)
    yield ('until', lambda: getattr(npc, 'respecMenuGUI', None) is not None, 10, 'respec menu')
    if getattr(npc, 'respecMenuGUI', None) is None:
        return 'Respec pressed, no weapon list'
    st = npc.isRespecAvailable(IG.RESPEC_CUTLASS)
    H.ev('RESPEC-PICK', weapon='cutlass', state=st)
    if st != IG.NORMAL:
        return 'the Cutlass line is not lit (state %s)' % st
    yield 1
    npc.selectRespecOptionConfirm(IG.RESPEC_CUTLASS)
    yield ('until', lambda: getattr(npc, 'confirmDialog', None) is not None, 10, 'respec confirm')
    dlg = getattr(npc, 'confirmDialog', None)
    if dlg is None:
        return 'Cutlass pressed, no Yes/No window'
    H.ev('RESPEC-CONFIRM', gold=s_lanes.gold(H))
    dlg['command'](1)                                          # Yes
    yield ('until', lambda: s_lanes.gold(H) == g0 - cost and overBase(cutlassPts(H, IT), IT) == 0, 15,
           'respec done')
    return None


def respec(H):
    from pirates.economy import EconomyGlobals as EG
    from pirates.distributed import InteractGlobals as IG
    from pirates.uberdog.UberDogGlobals import InventoryType as IT, getNumRespecType
    la = H.la
    inv = la.getInventory()
    pts = cutlassPts(H, IT)
    if overBase(pts, IT) == 0:
        H.ev('RESPEC-GIVE', why='no cutlass point to take back', skill=IT.CutlassSlash,
             had=pts.get(IT.CutlassSlash))
        H.mw('givePlayerStack %d %d' % (IT.CutlassSlash, pts.get(IT.CutlassSlash, 2) + 1))
        yield ('until', lambda: overBase(cutlassPts(H, IT), IT) > 0, 10, 'cutlass point')
        pts = cutlassPts(H, IT)
        if overBase(pts, IT) == 0:
            H.ev('FAIL', why='could not give him a cutlass point to take back'); return
    nResp = inv.getStackQuantity(getNumRespecType(IT.CutlassRep))
    cost = EG.getRespecCost(nResp)
    if s_lanes.gold(H) < cost:
        H.mw('gold %d' % (cost + 10))
        yield ('until', lambda: s_lanes.gold(H) >= cost, 10, 'respec gold')
    npc, why = yield from toNpcIn(H, 'respec', TRAIN_AREA, TRAIN_UID, TRAIN_POS, 'the trainer')
    if npc is None:
        H.ev('FAIL', why=why); return
    H.ev('RESPEC-NPC', npc=npc.doId, d=round(s_story.hdist(H, npc), 1), here=H.area(), cost=cost, respecs=nResp)
    g0, un0 = s_lanes.gold(H), inv.getStackQuantity(IT.UnspentCutlass)
    extra = overBase(pts, IT)
    why = yield from pressRespec(H, npc, IG, IT, g0, cost, extra)
    try:
        if getattr(npc, 'respecMenuGUI', None):
            npc.respecMenuGUI.destroy()
            npc.respecMenuGUI = None
    except Exception:
        pass
    yield from A.leaveNpc(H, npc, IG)
    if why:
        H.ev('FAIL', why=why); return
    g1, un1 = s_lanes.gold(H), inv.getStackQuantity(IT.UnspentCutlass)
    left = overBase(cutlassPts(H, IT), IT)
    H.ev('RESPEC-DONE', gold=[g0, g1], cost=cost, unspent=[un0, un1], back=extra, left=left,
         respecs=[nResp, inv.getStackQuantity(getNumRespecType(IT.CutlassRep))])
    if left:
        H.ev('FAIL', why='Yes pressed, %d cutlass points still over base (gold %d -> %d)' % (left, g0, g1)); return
    if g0 - g1 != cost:
        H.ev('FAIL', why='skills reset, but gold %d -> %d (cost %d)' % (g0, g1, cost)); return
    if un1 - un0 != extra:
        H.ev('FAIL', why='skills reset, but unspent points %d -> %d (want +%d)' % (un0, un1, extra)); return
    H.ev('PASS', what='the trainer reset his cutlass for %d gold, %d points back' % (cost, extra))


FN = {'emote': emote, 'code': code, 'musician': musician, 'respec': respec}


def run(H):
    la = H.la
    H.ev('BTN-START', me=la.doId, steps=STEPS, gold=s_lanes.gold(H), here=H.area())
    if la.doId == HOST:
        H.ev('FAIL', why="logged in as Host's pirate %d: this run uses only the test pirate" % HOST); return
    bad = [s for s in STEPS if s not in FN]
    if bad:
        H.ev('FAIL', why='unknown BTN_STEPS %s' % bad); return
    for what, why in SKIPPED.items():
        H.ev('BTN-SKIP', what=what, why=why)
    box = []
    undo = A.sysHook(H, box)
    results = []
    oldFar = A.wideOn(H)
    try:
        for n, name in enumerate(ORDER, 1):
            if name not in STEPS:
                continue
            got = yield from A.capture(H, FN[name](H), n, name)
            ok = got['kind'] == 'PASS'
            why = got['kw'].get('what' if ok else 'why') or ('no verdict' if got['kind'] is None else '')
            H.ev('BTN-STEP', n=n, name=name, ok=ok, why=why)
            results.append((n, name, ok, why))
            H.walk_cancel()
            if la.getGameState() != 'LandRoam':
                yield from A.landRoam(H, 30, 'between steps')
    finally:
        A.wideOff(oldFar)
        undo()
    allOk, text = A.summary(results)
    H.ev('PASS' if allOk else 'FAIL', **{('what' if allOk else 'why'): text,
                                         'steps': [list(r) for r in results]})
