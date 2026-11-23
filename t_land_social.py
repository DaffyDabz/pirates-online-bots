"""Offline test of pbot\\skills\\land.py step 4 (11-22): FRIENDS / GUILD INVITES, TITLES, GUILD, HELLOS and TELEPORT (rows 34-39).
Fake world: no game. A pirate on an island with the game's invitation panels (FriendInvitee / GuildInvitee: avId, avName, OK and
No buttons that are DirectGui-like: ['state'] and commandFunc, destroy() sets .destroyed and the GuiManager attribute goes), a
Titles page (panels with titleId, rank, landActive, landToggle), a guild page (createGuild, the confirm box, renameGuild, the
name entry), boys' pirates at known distances, a SpeedChat recorder (b_setSC) and a typed-chat recorder that must stay empty,
and a teleport manager (TeleportOut, then LandRoam on another island).
BEFORE: each duty replaced by one that does nothing: the invitations stay open, no badge goes on, no guild is made, no hello is
said. AFTER: a captain's invitation is answered OK (and thanked in SpeedChat), a stranger's is declined, a panel that will not
close is one BOT bug and the duty quiet; the best earned badge goes on (rank 0 needs a magic word: left alone); the opt-in guild
is made and named, never with an invite; one hello per boy per 900 s; the friend teleport refuses Host's pirate, a stranger and
a friend close by. No magic word anywhere, want() is read-only and cheap.
Run: python3 t_land_social.py <harness dir, e.g. C:\\Dev\\Toontown\\pirates-harness>"""
import math, os, re, sys, time as _time, types

D = os.path.abspath(sys.argv[1])
sys.path.insert(0, D)
sys.path.insert(0, os.path.join(D, 'pbot', 'skills'))


class Clock:
    t = 1000.0

    def time(self):
        return self.t


CLK = Clock()

# ---- the game's names (fakes of the few the skill reads)
KINDS5 = ('Cutlass', 'Dagger', 'Pistol', 'Doll', 'Wand')


class InventoryType:
    UseItem = 7
    Vitae_Level = 99


for _i, _k in enumerate(KINDS5):
    setattr(InventoryType, 'Unspent' + _k, 13750 + _i)

ug = types.ModuleType('pirates.uberdog.UberDogGlobals')
ug.InventoryType = InventoryType
tg = types.ModuleType('pirates.pirate.TitleGlobals')
tg.LandPVPTitle = 4
pp = types.ModuleType('pirates.pirate')
pp.TitleGlobals = tg
for _n in ('pirates', 'pirates.uberdog'):
    sys.modules[_n] = types.ModuleType(_n)
sys.modules['pirates.uberdog.UberDogGlobals'] = ug
sys.modules['pirates.pirate'], sys.modules['pirates.pirate.TitleGlobals'] = pp, tg

PLAYER1, PLAYER2, HOST, TEST_CAPTAIN, STRANGER = 100000656, 100000665, 100000170, 100000004, 100000777


class Btn:
    """A DirectGui button as s_kidfriends presses it: ['state'] and commandFunc(None)."""

    def __init__(self, act, state='normal'):
        self.act, self.state, self.presses = act, state, 0

    def __getitem__(self, k):
        return self.state if k == 'state' else None

    def commandFunc(self, ev):
        self.presses += 1
        self.act()


class Invitee:
    """FriendInvitee / GuildInvitee: OK = sendRequestInvite, No = decline; either closes the panel (destroy())."""

    def __init__(self, w, kind, avId, closes=True, state='normal'):
        self.w, self.kind, self.avId, self.avName, self.destroyed, self.closes = w, kind, avId, 'Pirate %d' % avId, False, closes
        self.bOk, self.bNo = Btn(self.ok, state), Btn(self.no, state)
        setattr(w.gm, kind + 'Invitee', self)

    def ok(self):
        self.w.answers.append((self.kind, self.avId, 'ok'))
        if self.closes:
            self.destroy()

    def no(self):
        self.w.answers.append((self.kind, self.avId, 'no'))
        if self.closes:
            self.destroy()

    def destroy(self):
        self.destroyed = True
        if hasattr(self.w.gm, self.kind + 'Invitee'):
            delattr(self.w.gm, self.kind + 'Invitee')        # GuiManager: del self.friendInvitee


class TPanel:
    def __init__(self, w, rank, title=4, active=False):
        self.w, self.rank, self.titleId, self.landActive = w, rank, title, active
        if title == tg.LandPVPTitle:
            self.landToggle = self.toggle

    def toggle(self):
        w = self.w
        w.toggled.append(self.rank)
        if w.badgeBroken == 'raise':
            raise RuntimeError('landToggle blew up')
        if not w.badgeBroken:
            self.landActive = True
            w.la.badge = (self.titleId, self.rank)


class TitlesPage:
    def __init__(self, panels):
        self.titles = panels


class Box:
    def __init__(self, w):
        self.w = w

    def _PiratesConfirm__handleOk(self):
        if not self.w.guildBroken:
            self.w.guildId, self.w.guildName = 5000, 'Pirate Guild 5000'


class GuildPage:
    def __init__(self, w):
        self.w, self.confirmBox, self.nameEntry = w, None, types.SimpleNamespace(enterText=self.enter)
        self.entered = None

    def createGuild(self):
        self.w.gcalls.append('createGuild')
        if not self.w.noBox:
            self.confirmBox = Box(self.w)

    def renameGuild(self):
        self.w.gcalls.append('renameGuild')

    def enter(self, name):
        self.entered = name

    def _typedAName(self):
        self.w.gcalls.append('_typedAName')
        self.w.guildName = self.entered

    def revertGui(self):
        self.w.gcalls.append('revertGui')


class Boy:
    def __init__(self, x, y):
        self.pos = (x, y, 0.0)

    def getPos(self, R=None):
        return self.pos


class Inv:
    def __init__(self, w):
        self.w = w

    def getTonics(self):
        return {1: self.w.tonics}

    def getStackQuantity(self, k):
        return self.w.stacks.get(k, 0)

    def getGoldInPocket(self):
        return 0


class Diary:
    def getTimeRemaining(self, sid):
        return 0.0


class Tele:
    def __init__(self, w):
        self.w = w

    def queryAvatarForTeleport(self, avId):
        self.w.teleQ.append(avId)
        self.w.teleAt = CLK.t


class World:
    def __init__(self, hp=1000, tonics=3, stacks=None, titles=None, guildId=0):
        self.tonics, self.stacks, self.gsBase = tonics, dict(stacks or {}), 'LandRoam'
        self.events, self.bugs, self.answers, self.toggled, self.sc, self.typed = [], [], [], [], [], []
        self.gcalls, self.teleQ, self.teleAt, self.teleStuck = [], [], None, False
        self.titlesOpen, self.badgeBroken, self.guildBroken, self.noBox = False, False, False, False
        self.guildId, self.guildName, self.areaT, self.shown = guildId, '', ('DistributedIsland', 'isl1'), []
        self.doId2do = {}
        la = self.la = types.SimpleNamespace()
        la.hp, la.maxHp, la.doId, la.name, la.pos = hp, 1000, 100000999, 'Test Pirate', [0.0, 0.0, 0.0]
        la.jailCellIndex, la.badge = 100, None
        la.isWeaponDrawn, la.currentWeaponId = False, None
        la.getGameState = self.curGs
        la.getInventory = lambda: Inv(self)
        la.skillDiary = Diary()
        la.getPos = lambda R=None: tuple(la.pos)
        la.getGuildId = lambda: self.guildId
        la.getGuildName = lambda: self.guildName
        la.b_setSC = lambda i: self.sc.append(i)
        la.b_setTalk = la.setTalk = la.sendChat = lambda *a: self.typed.append(a)      # typed chat: must stay unused
        self.tp = TitlesPage(titles) if titles is not None else None
        gm = self.gm = types.SimpleNamespace(titlesPage=self.tp, guildPage=GuildPage(self))
        gm.pageOpen = lambda p: self.titlesOpen if p is self.tp else False
        gm.showTitlesPanel = lambda: setattr(self, 'titlesOpen', True) or self.shown.append('open')
        gm.hideSeaChest = lambda: setattr(self, 'titlesOpen', False) or self.shown.append('close')
        gm.socialPanel = types.SimpleNamespace(show=lambda: self.gcalls.append('show'), hide=lambda: self.gcalls.append('hide'),
                                               setPage=lambda p: self.gcalls.append('setPage'))
        la.guiMgr = gm
        self.cr = types.SimpleNamespace(doId2do=self.doId2do, teleportMgr=Tele(self))
        self.H = types.SimpleNamespace(la=la, cr=self.cr, render='R',
                                       ev=lambda name, /, **kw: self.events.append((name, kw)), area=lambda: self.areaT,
                                       P=lambda a: [round(v, 1) for v in a.pos])

    def curGs(self):
        """TeleportOut for 3..10 s after a teleport query (never, when it is stuck), then LandRoam on another island."""
        if self.teleAt is not None and not self.teleStuck:
            n = CLK.t - self.teleAt
            if 3 <= n < 10:
                return 'TeleportOut'
            if n >= 10:
                self.areaT = ('DistributedIsland', 'isl2')
        return self.gsBase

    def names(self):
        return [e[0] for e in self.events]

    def count(self, name):
        return self.names().count(name)

    def evs(self, name):
        return [e[1] for e in self.events if e[0] == name]

    def boy(self, doId, x, y):
        self.doId2do[doId] = Boy(x, y)


def drive(gen, limit=60000):
    steps = 0
    try:
        item = next(gen)
        while True:
            steps += 1
            assert steps < limit, 'driver limit'
            if isinstance(item, tuple):
                _, fn, secs, _what = item
                t0 = CLK.t
                while not fn() and CLK.t - t0 < secs:
                    CLK.t += 1
            else:
                CLK.t += item
            item = next(gen)
    except StopIteration as e:
        return e.value


class Bot:
    def __init__(self, w):
        self.H, self.w = w.H, w

    def bug(self, kind, key, tag, what, tb=''):
        self.w.bugs.append((kind, key, tag, what))


fails = []
LANDS = []
WORLDS = []


def check(name, ok, info=''):
    print(('PASS ' if ok else 'FAIL ') + name + (' ' + str(info) if info and not ok else ''))
    if not ok:
        fails.append(name)


import land            # noqa: E402
land.time = CLK


def world(**kw):
    w = World(**kw)
    WORLDS.append(w)
    return w


def mkland(w):
    L = land.Land(Bot(w))
    L.greeted = {i: 1e12 for i in land.CAPTAINS}          # no boy needs a hello unless the test wants one
    L.titlesT = CLK.t                                     # the Titles page was just looked at, unless the test says so
    LANDS.append(L)
    return L


def nothing():
    return None
    yield


def wantName(L):
    x = L.want()
    return None if x is None else x[1].split(':')[0]


# ---- 1. pure helpers
caps = land.captains('')
check('captains: Player1, Player2 and Host\'s pirate; PBOT_CAPTAINS adds a test captain',
      caps == {PLAYER1, PLAYER2, HOST} and land.captains('100000004, 100000005') == caps | {TEST_CAPTAIN, 100000005}
      and land.captains('abc') == caps, caps)
check('inviteAnswer: a captain gets OK, anyone else No', land.inviteAnswer(PLAYER1, caps) == 'ok' and land.inviteAnswer(PLAYER2, caps) == 'ok'
      and land.inviteAnswer(STRANGER, caps) == 'no' and land.inviteAnswer(None, caps) == 'no')
check('titlePick: none earned (rank 0) = None, no magic word; the highest rank wins; one already on = None; tie = first',
      land.titlePick([]) is None and land.titlePick([(0, 0, False), (1, 0, False)]) is None
      and land.titlePick([(0, 1, False), (1, 3, False), (2, 2, False)]) == 1
      and land.titlePick([(0, 1, False), (1, 3, True)]) is None and land.titlePick([(0, 2, False), (1, 2, False)]) == 0)
check('greetDue: the first boy never greeted, or greeted GREET_GAP s ago; none = None',
      land.greetDue([1, 2], {1: 100.0}, 150.0) == 2 and land.greetDue([1], {1: 100.0}, 150.0) is None
      and land.greetDue([1], {1: 100.0}, 100.0 + land.GREET_GAP) == 1 and land.greetDue([], {}, 0.0) is None)
check('teleOk: never Host\'s pirate (even as a listed captain), a non-captain refused, one close refused, far or unseen ok',
      land.teleOk(HOST, caps | {HOST}, None)[0] is False and land.teleOk(STRANGER, caps, None) == (False, 'not a captain')
      and land.teleOk(PLAYER1, caps, 50.0)[0] is False and land.teleOk(PLAYER1, caps, 500.0) == (True, 'ok')
      and land.teleOk(PLAYER2, caps, None) == (True, 'ok'))
d = land.duty
check('duty order: jail > invite > tonic > skill > guild > titles > greet > hunt',
      d({'jailed': True, 'invite': ('friend', 1), 'hpf': 1.0})[0] == 'jail'
      and d({'invite': ('friend', 1), 'hpf': 0.4, 'tonics': 3, 'ready': True, 'gs': 'LandRoam', 'unspent': 1, 'hunt': True})[0] == 'invite'
      and d({'hpf': 0.4, 'tonics': 3, 'ready': True, 'gs': 'LandRoam', 'unspent': 1, 'guild': True, 'titles': True, 'greet': 5,
             'hunt': True})[0] == 'tonic'
      and d({'hpf': 1.0, 'gs': 'LandRoam', 'unspent': 1, 'guild': True, 'titles': True, 'greet': 5, 'hunt': True})[0] == 'skill'
      and d({'hpf': 1.0, 'gs': 'LandRoam', 'guild': True, 'titles': True, 'greet': 5, 'hunt': True})[0] == 'guild'
      and d({'hpf': 1.0, 'gs': 'LandRoam', 'titles': True, 'greet': 5, 'hunt': True})[0] == 'titles'
      and d({'hpf': 1.0, 'gs': 'LandRoam', 'greet': 5, 'hunt': True})[0] == 'greet'
      and d({'hpf': 1.0, 'gs': 'LandRoam', 'hunt': True})[0] == 'hunt')
check('duty: an invitation is answered in a fight too; guild / titles / hello only sheathed (LandRoam); quiet silences each',
      d({'gs': 'Battle', 'invite': ('guild', 1), 'hunt': True})[0] == 'invite'
      and d({'gs': 'Battle', 'guild': True, 'titles': True, 'greet': 5, 'hunt': True})[0] == 'hunt'
      and d({'gs': 'LandRoam', 'invite': ('friend', 1), 'quiet': {'invite': True}, 'hunt': True})[0] == 'hunt'
      and d({'gs': 'LandRoam', 'guild': True, 'quiet': {'guild': True}, 'titles': True})[0] == 'titles'
      and d({'gs': 'LandRoam', 'titles': True, 'quiet': {'titles': True}, 'greet': 5})[0] == 'greet'
      and d({'gs': 'LandRoam', 'greet': 5, 'quiet': {'greet': True}}) is None)
S = land.SCORE
check('scores: invite in the UPKEEP band (60-99, above the tonic), guild > titles > greet > hunt in the FREE PLAY band (10-39)',
      60 <= S['invite'] <= 99 and S['invite'] > S['tonic'] and S['jail'] > S['invite']
      and 10 <= S['hunt'] < S['greet'] < S['titles'] < S['guild'] <= 39)

# ---- 2. invitations. BEFORE: the duty does nothing
w = world()
Invitee(w, 'friend', PLAYER1)
L = mkland(w)
check('a friend invitation from Player1: the duty asks at 70, "invite"', (L.want() or (0, ''))[0] == 70 and wantName(L) == 'invite', L.want())
L.invite = nothing
r = drive(L.flow())
check('BEFORE (the duty does nothing): the panel stays open, no answer, nothing said', w.answers == [] and hasattr(w.gm, 'friendInvitee')
      and w.sc == [], (w.answers, w.sc))

# AFTER: a captain's friend invitation: OK, panel closed, thanked in SpeedChat
w = world()
Invitee(w, 'friend', PLAYER1)
L = mkland(w)
r = drive(L.flow())
check('AFTER: Player1\'s friend invitation answered OK, the panel closed, the GuiManager attribute gone',
      w.answers == [('friend', PLAYER1, 'ok')] and not hasattr(w.gm, 'friendInvitee'), (w.answers,))
check('AFTER: result ok, one LAND-INVITE line (answer ok, pressed, closed), no bug, no quiet',
      r == {'duty': 'invite', 'ok': True, 'kind': 'friend', 'avId': PLAYER1, 'answer': 'ok'} and w.count('LAND-INVITE') == 1
      and w.evs('LAND-INVITE')[0]['pressed'] and w.evs('LAND-INVITE')[0]['closed'] and not w.bugs and not L.quietUntil, (r, w.bugs))
check('AFTER: "thanks" said once in SpeedChat (id 500), nothing typed', w.sc == [500] and w.typed == [], (w.sc, w.typed))
check('AFTER: the next want() is not the invite (free play: hunt)', wantName(L) == 'hunt', L.want())

# a guild invitation from Player2, from Host's pirate and from the test captain
for kind, who in (('guild', PLAYER2), ('friend', HOST), ('guild', TEST_CAPTAIN)):
    os.environ['PBOT_CAPTAINS'] = str(TEST_CAPTAIN)
    w = world()
    Invitee(w, kind, who)
    L = mkland(w)
    r = drive(L.flow())
    check('a %s invitation from captain %d: OK' % (kind, who), w.answers == [(kind, who, 'ok')] and r and r['ok'], (w.answers, r))
os.environ.pop('PBOT_CAPTAINS', None)

# a stranger: declined, never ignored, not thanked
for kind in ('friend', 'guild'):
    w = world()
    Invitee(w, kind, STRANGER)
    L = mkland(w)
    r = drive(L.flow())
    check('a %s invitation from a stranger: No button, panel closed, ok, nothing said' % kind,
          w.answers == [(kind, STRANGER, 'no')] and r and r['ok'] and r['answer'] == 'no' and w.sc == [] and not w.bugs,
          (w.answers, r, w.sc))
w = world()
Invitee(w, 'friend', TEST_CAPTAIN)
L = mkland(w)
drive(L.flow())
check('the test captain is a stranger without PBOT_CAPTAINS: declined', w.answers == [('friend', TEST_CAPTAIN, 'no')], w.answers)

# a panel that will not close
w = world()
Invitee(w, 'friend', PLAYER1, closes=False)
L = mkland(w)
r = drive(L.flow())
check('a panel that stays open after OK: ok False, ONE BOT bug land-invite-friend-open (stuck), the invite duty quiet',
      r and not r['ok'] and len(w.bugs) == 1 and w.bugs[0][:3] == ('stuck', 'land-invite-friend-open', 'BOT')
      and 'invite' in L.quietUntil and w.count('LAND-QUIET') == 1, (r, w.bugs))
check('... and the next want() is not the invite (quiet) until INVITE_QUIET s are over, then it asks again',
      wantName(L) != 'invite' and (CLK.__setattr__('t', CLK.t + land.INVITE_QUIET + 1) or True) and wantName(L) == 'invite', L.want())

w = world()
Invitee(w, 'guild', PLAYER1, state='disabled')
L = mkland(w)
r = drive(L.flow())
check('buttons that cannot be pressed: ok False, ONE BOT bug land-invite-guild-nopress, quiet, no answer, no thanks',
      r and not r['ok'] and len(w.bugs) == 1 and w.bugs[0][1] == 'land-invite-guild-nopress' and w.answers == [] and w.sc == []
      and 'invite' in L.quietUntil, (r, w.bugs))

# the panel vanished between want() and flow()
w = world()
p = Invitee(w, 'friend', PLAYER1)
L = mkland(w)
p.destroy()
r = drive(L.invite())
check('the panel closed by itself before the duty ran: ok ("gone"), nothing pressed, no bug',
      r == {'duty': 'invite', 'ok': True, 'why': 'gone'} and w.answers == [] and not w.bugs, r)

# ordering with the real state: jail > invite > tonic
w = world(hp=400, tonics=3)
Invitee(w, 'friend', PLAYER1)
L = mkland(w)
check('hurt (40%) with 3 tonics and an invitation: the invitation first (70), then the tonic (60)',
      (L.want() or (0,))[0] == 70 and (drive(L.flow()) or {}).get('ok') and (L.want() or (0,))[0] == 60 and wantName(L) == 'tonic', L.want())
w = world(hp=400, tonics=3)
w.la.jailCellIndex = 3
Invitee(w, 'friend', PLAYER1)
L = mkland(w)
check('in a jail cell with an invitation: the jail first (100)', (L.want() or (0,))[0] == 100 and wantName(L) == 'jail', L.want())

# ---- 3. titles
# no Titles page in this client (want-titles-page off)
w = world(titles=None)
L = mkland(w)
L.titlesT = -1e9
ws = [wantName(L) for _ in range(5)]
check('no Titles page: the titles duty is never asked, ONE LAND-TITLES-OFF event in 5 reads, the hunt instead',
      ws == ['hunt'] * 5 and w.count('LAND-TITLES-OFF') == 1, (ws, w.names()))

# rank 0 only: left alone (a magic word is the only way), the page closed again
w = world(titles=[])
w.tp.titles = [TPanel(w, 0), TPanel(w, 0)]
L = mkland(w)
L.titlesT = -1e9
check('a Titles page, due: the duty asks at 35', (L.want() or (0,))[0] == 35 and wantName(L) == 'titles', L.want())
r = drive(L.flow())
check('rank 0 only: nothing toggled, no badge, LAND-TITLES-NONE once, the page opened and closed, no magic word',
      w.toggled == [] and w.la.badge is None and w.count('LAND-TITLES-NONE') == 1 and w.shown == ['open', 'close']
      and not w.titlesOpen and L.PH.blocked is None and r and r['ok'], (w.toggled, w.shown, r))
check('... and the next want() is not the titles (looked at just now)', wantName(L) == 'hunt', L.want())

# BEFORE: the duty does nothing; AFTER: the best earned badge goes on
w = world(titles=[])
w.tp.titles = [TPanel(w, 1), TPanel(w, 3), TPanel(w, 2), TPanel(w, 5, title=9)]
L = mkland(w)
L.titlesT = -1e9
L.titles = nothing
drive(L.flow())
check('BEFORE (the duty does nothing): no badge, the page never opened', w.la.badge is None and w.shown == [], (w.la.badge, w.shown))
w = world(titles=[])
w.tp.titles = [TPanel(w, 1), TPanel(w, 3), TPanel(w, 2), TPanel(w, 5, title=9)]
L = mkland(w)
L.titlesT = -1e9
r = drive(L.flow())
check('AFTER: the Land PvP panel of rank 3 toggled (not the rank 5 of another title); the badge is (4, 3)',
      w.toggled == [3] and w.la.badge == (4, 3) and r == {'duty': 'titles', 'ok': True, 'badge': (4, 3)}, (w.toggled, w.la.badge, r))
check('AFTER: LAND-TITLES, LAND-TITLES-PICK and LAND-TITLES-BADGE (ok) once, the page closed, no bug, no magic word',
      w.count('LAND-TITLES') == 1 and w.count('LAND-TITLES-PICK') == 1 and w.evs('LAND-TITLES-BADGE')[0]['ok'] and not w.titlesOpen
      and not w.bugs and L.PH.blocked is None, (w.names(), w.bugs))
check('AFTER: not asked again within TITLES_EVERY s; asked again after, finds the badge on, toggles nothing',
      wantName(L) == 'hunt' and (CLK.__setattr__('t', CLK.t + land.TITLES_EVERY + 1) or True) and wantName(L) == 'titles'
      and (drive(L.flow()) or {}).get('ok') and w.toggled == [3] and w.evs('LAND-TITLES-NONE')[-1]['why'] == 'already on', (w.toggled, w.evs('LAND-TITLES-NONE')))

# the badge is not saved: a GAME bug, the duty quiet, the page closed
w = world(titles=[])
w.tp.titles = [TPanel(w, 2)]
w.badgeBroken = True
L = mkland(w)
L.titlesT = -1e9
r = drive(L.flow())
check('the badge is pressed and not saved: ok False, ONE GAME bug land-titles-badge-not-saved (missing), titles quiet, page closed',
      r and not r['ok'] and len(w.bugs) == 1 and w.bugs[0][:3] == ('missing', 'land-titles-badge-not-saved', 'GAME')
      and 'titles' in L.quietUntil and not w.titlesOpen, (r, w.bugs))

# the toggle crashes: one BOT bug, quiet, the page closed in the finally
w = world(titles=[])
w.tp.titles = [TPanel(w, 2)]
w.badgeBroken = 'raise'
L = mkland(w)
L.titlesT = -1e9
r = drive(L.flow())
check('landToggle raises: ok False (bot), ONE BOT traceback bug, titles quiet, the page closed again',
      r and not r['ok'] and len(w.bugs) == 1 and w.bugs[0][0] == 'traceback' and w.bugs[0][1].startswith('land-crash-')
      and w.bugs[0][2] == 'BOT' and 'titles' in L.quietUntil and not w.titlesOpen, (r, w.bugs))

# cut() while the page is open (the brain stopped the flow): the page is closed at once
w = world(titles=[])
w.tp.titles = [TPanel(w, 2)]
L = mkland(w)
L.titlesT = -1e9
g = L.flow()
next(g)
was = w.titlesOpen
c = L.cut('limit')
check('cut() with the Titles page open: the page is closed at once, no cleanup generator, one LAND-CUT',
      was and not w.titlesOpen and c is None and w.count('LAND-CUT') == 1, (was, w.titlesOpen, c))
g.close()
check('... and closing the cut flow afterwards does not close it twice', w.shown == ['open', 'close'], w.shown)

# only sheathed on land: drawn weapon = no titles duty
w = world(titles=[])
w.tp.titles = [TPanel(w, 2)]
w.gsBase = 'Battle'
L = mkland(w)
L.titlesT = -1e9
check('in a fight (Battle): the titles duty is not asked', wantName(L) != 'titles', L.want())

# ---- 4. guild (opt-in)
w = world()
L = mkland(w)
check('LAND_GUILD_CREATE off (the default): no guild duty, ever', land.GUILD_CREATE is False and wantName(L) == 'hunt', L.want())
land.GUILD_CREATE = True
try:
    w = world()
    L = mkland(w)
    check('opt-in on, no guild: the guild duty asks at 36', (L.want() or (0,))[0] == 36 and wantName(L) == 'guild', L.want())
    L.guildMake = nothing
    drive(L.flow())
    check('BEFORE (the duty does nothing): no guild, the page never touched', w.guildId == 0 and w.gcalls == [], (w.guildId, w.gcalls))
    w = world()
    L = mkland(w)
    r = drive(L.flow())
    check('AFTER: a guild made and named ("Bot Crew ..."), once; the duty is done for the run',
          r and r['ok'] and w.guildId == 5000 and w.guildName.startswith('Bot Crew ') and L.guildDone and wantName(L) == 'hunt', (r, w.guildName))
    check('AFTER: only create, rename, name and the revert (never an invite); the social panel shown then hidden; LAND-GUILD-NAMED ok',
          [c for c in w.gcalls if c not in ('show', 'hide', 'setPage')] == ['createGuild', 'renameGuild', '_typedAName', 'revertGui']
          and w.gcalls[0] == 'show' and w.gcalls[-1] == 'hide' and w.evs('LAND-GUILD-NAMED')[0]['ok'] and not w.bugs, (w.gcalls, w.bugs))
    w = world(guildId=77)
    L = mkland(w)
    check('already in a guild: no guild duty', wantName(L) == 'hunt', L.want())
    L.guildDone = False
    r = drive(L.guildMake())
    check('... and guildMake itself touches nothing', r and r['ok'] and r['why'] == 'already in a guild' and w.gcalls == [], (r, w.gcalls))
    w = world()
    w.noBox = True
    L = mkland(w)
    r = drive(L.flow())
    check('Create Guild gives no confirm window: ok False, ONE BOT bug land-guild-no-confirm, not asked again',
          r and not r['ok'] and len(w.bugs) == 1 and w.bugs[0][1] == 'land-guild-no-confirm' and w.bugs[0][2] == 'BOT'
          and wantName(L) == 'hunt', (r, w.bugs))
    w = world()
    w.guildBroken = True
    L = mkland(w)
    r = drive(L.flow())
    check('OK pressed, no guild after 20 s: ok False, ONE GAME bug land-guild-not-made, the page reverted',
          r and not r['ok'] and len(w.bugs) == 1 and w.bugs[0][:3] == ('missing', 'land-guild-not-made', 'GAME') and 'revertGui' in w.gcalls, (r, w.bugs))
finally:
    land.GUILD_CREATE = False

# ---- 5. hello (SpeedChat only)
w = world()
w.boy(PLAYER1, 10.0, 0.0)
L = mkland(w)
L.greeted = {}
check('Player1 10 ft away: the greet duty asks at 34', (L.want() or (0,))[0] == 34 and wantName(L) == 'greet', L.want())
L.greet = lambda: None
r = drive(L.flow())
check('BEFORE (the duty does nothing): nothing said, still asked for', r is None and w.sc == [] and wantName(L) == 'greet', (r, w.sc))
w = world()
w.boy(PLAYER1, 10.0, 0.0)
w.boy(PLAYER2, 20.0, 5.0)
L = mkland(w)
L.greeted = {}
r = drive(L.flow())
check('AFTER: one "hi" (SpeedChat %d) to Player1, booked; nothing typed' % land.SC['hi'], r == {'duty': 'greet', 'ok': True, 'boy': PLAYER1, 'sent': True}
      and w.sc == [land.SC['hi']] and w.typed == [] and PLAYER1 in L.greeted, (r, w.sc))
r = drive(L.flow())
check('AFTER: Player2 next: booked, but the same line is held back for SC_GAP s (sent False), so no spam; both greeted, no more asks',
      r and r['boy'] == PLAYER2 and r['sent'] is False and w.sc == [land.SC['hi']] and wantName(L) == 'hunt', (r, w.sc, L.want()))
CLK.t += land.GREET_GAP + 1
check('after GREET_GAP s the boys are greeted again', wantName(L) == 'greet', L.want())
w = world()
w.boy(PLAYER1, 100.0, 0.0)
L = mkland(w)
L.greeted = {}
check('Player1 100 ft away: no hello', wantName(L) == 'hunt', L.want())
w = world()
w.boy(STRANGER, 5.0, 0.0)
w.doId2do[w.la.doId] = w.la
L = mkland(w)
L.greeted = {}
check('a stranger close by, the bot itself in the table: no hello', wantName(L) == 'hunt', L.want())

# ---- 6. friend teleport (row 37)
w = world()
L = mkland(w)
r = drive(L.toFriend(HOST))
check('toFriend(Host\'s pirate): refused, no query, one LAND-TELE-SKIP', r == {'duty': 'tele', 'ok': False, 'why': "Host's pirate: never"}
      and w.teleQ == [] and w.count('LAND-TELE-SKIP') == 1, (r, w.teleQ))
keep = land.teleOk
land.teleOk = lambda avId, caps, dist: (True, 'ok')
w = world()
L = mkland(w)
drive(L.toFriend(HOST))
land.teleOk = keep
check('BEFORE (no guard): the query WOULD go out for Host\'s pirate', w.teleQ == [HOST], w.teleQ)
w = world()
L = mkland(w)
r = drive(L.toFriend(STRANGER))
check('toFriend(a stranger): refused, no query', r['why'] == 'not a captain' and w.teleQ == [], (r, w.teleQ))
w = world()
w.boy(PLAYER1, 50.0, 0.0)
L = mkland(w)
r = drive(L.toFriend(PLAYER1))
check('toFriend(Player1 50 ft away): refused (walk), no query', not r['ok'] and r['why'].startswith('already 50 ft') and w.teleQ == [], (r, w.teleQ))
w = world()
L = mkland(w)
r = drive(L.toFriend(PLAYER1))
check('toFriend(Player1, not in view): one query, TeleportOut then LandRoam on another island, ok',
      r == {'duty': 'tele', 'ok': True, 'why': 'ok'} and w.teleQ == [PLAYER1] and w.areaT == ('DistributedIsland', 'isl2')
      and w.evs('LAND-TELE')[0]['out'] and w.evs('LAND-TELE')[0]['landed'], (r, w.teleQ, w.areaT))
w = world()
w.teleStuck = True
L = mkland(w)
r = drive(L.toFriend(PLAYER2))
check('the game never starts the teleport: ok False "never left" after 30 s (no bug filed here: pbots decides)',
      r == {'duty': 'tele', 'ok': False, 'why': 'never left'} and w.teleQ == [PLAYER2], r)

# ---- 7. the whole skill: no magic word, reserved names, read-only and cheap want()
src = open(os.path.join(D, 'pbot', 'skills', 'land.py'), encoding='utf-8').read()
check('no call of a magic word anywhere in land.py (the PlayerH shortcut only refuses)', re.findall(r'\.mw\(', src) == [], re.findall(r'.{20}\.mw\(', src))
check('no magic word reached the wrapper in any run above', all(L.PH.blocked is None for L in LANDS), [L.PH.blocked for L in LANDS if L.PH.blocked])
allNames = [n for w in WORLDS for n in w.names()]
check('every event the skill emitted is LAND-... (never a reserved brain name)', all(n.startswith('LAND') for n in allNames)
      and not any(n in land.RESERVED for n in allNames), sorted({n for n in allNames if not n.startswith('LAND')}))
check('nothing was ever typed in chat in any run above', all(w.typed == [] for w in WORLDS))

w = world(titles=None)
w.boy(PLAYER1, 100.0, 0.0)
Invitee(w, 'friend', STRANGER)
L = mkland(w)
t0 = _time.perf_counter()
for _ in range(500):
    L.want()
per = (_time.perf_counter() - t0) / 500
check('want() with an invitation, a boy and no Titles page: 500 reads, no press, no word said, under 1 ms each',
      w.answers == [] and w.sc == [] and w.toggled == [] and w.gcalls == [] and hasattr(w.gm, 'friendInvitee') and per < 0.001
      and w.count('LAND-TITLES-OFF') == 1, (per, w.names()))

print('ALL PASS (%d)' % 0 if False else ('ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
