"""pbot skill LAND (roblox-tray lane, Round 2, 11-22): the player bot's life on land (PLAYERBOTS-activities.md rows 34-46).

Fits pbot/skills/INTERFACE.md (pbots 11-22): limit 600, crewOk False (in a boy's crew the brain's crew states play and the
boys come first), jail = SAFETY band (100), tonic / skill point = UPKEEP band, hunting = FREE PLAY band, bug keys 'land-...'
(GAME or BOT), events 'LAND-...', no magic word ever (H.mw is a test shortcut: refused, one BOT bug), every strict
('until', ...) wait turned into an ('upto', ...) one.

What it does (one state machine; duty() below is the one ordering, so nothing is decided twice):
- KNOCKED OUT (row 42). A dead pirate is thrown into a jail cell (hp 1, Vitae for 30 min, PlayerPirateGameFSMAI) and has to
  kick the cell door open and walk out. jail() runs s_story.jail (kick, out of the cell, the jail's door) one step at a time,
  as s_islandtour.jailOut does. SAFETY: asked everywhere, also inside the cell.
- TONICS (row 46). s_fighter.Fighter drinks inside a fight only (below 45% hp). A kid also drinks between fights: below
  OUT_TONIC_HP while sheathed, keeping one tonic for the next fight.
- VITAE (row 42). While Vitae runs the pirate's stats are cut: foes at or below its own level only (foeOver()).
- SKILL POINTS (row 45). An unspent point (a level-up gave it) is spent out of a fight on the skill page, the way a player
  does (Skills key, the weapon's tab, the skill's +): the first learned skill the page's + takes (pickSkill). No level-up
  magic word, no respec.
- WEAPONS (row 44). Use only (quests.py gets them): each hunt draws the next owned weapon (cutlass, dagger, pistol, doll,
  staff), the fight clicks with it (s_fighter) and fires its special skills through the tray between beats; a weapon that
  lands no hit in a whole fight is marked bad for the run. The weapon is put away when the hunt ends or is cut (cut()).
- INVITATIONS (rows 34, 36). A friend or guild invitation panel is answered at once, in a fight too (UPKEEP band, 70): OK
  from a captain (Player1, Player2, Host's pirate, PBOT_CAPTAINS in a test), No from anyone else; a panel that will not close is
  one BOT bug and the duty quiet for INVITE_QUIET s. The bot never invites anyone (the boys never get a request from it).
- TITLES (row 35). Hourly, sheathed: the Titles page's best earned Land PvP badge (rank 1+) goes on. Rank 0 needs a magic
  word, so it is left alone; no Titles page in this client (want-titles-page off) = one LAND-TITLES-OFF, no duty.
- GUILD (row 34). Opt-in (LAND_GUILD_CREATE=1): make a guild and name it, once. Off by default.
- HELLO (row 38). A SpeedChat "hi" to a boy's pirate within GREET_R ft, once per GREET_GAP s per boy (no typed chat, ever).
- FRIEND TELEPORT (row 37). toFriend(avId) is there (captains only, never Host's pirate, not when already close) but nothing
  schedules it: the brain / games decide. PvP lookout (row 39) is off by design.
The notes for every row are in side-session-notes land-round2-map.md.

Use (the INTERFACE shape): Land(bot).want() -> (score, why) or None (reads only); Land(bot).flow() is the generator the
brain drives (yields walker items, returns a small dict); Land(bot).cut(why) is called when the brain stops it.
bot = the brain (it has .H and .bug(kind, key, tag, what, tb)).
As a step script (PROOF_SCRIPT = this file, through pbots' runner): run(H) plays LAND for LAND_SECS."""
import math, os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PBOT = os.path.dirname(HERE)
HARNESS = os.path.dirname(PBOT)
for _p in (PBOT, HARNESS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import s_fighter       # noqa: E402  (pure helpers at the top; its game imports are inside Fighter)

OUT_TONIC_HP = float(os.environ.get('LAND_OUT_TONIC_HP', '0.60'))    # drink between fights below this health fraction
KEEP_TONICS = int(os.environ.get('LAND_KEEP_TONICS', '1'))           # tonics kept for the next fight
TONIC_GAP = 8.0                                                      # s between two drinks
JAIL_LIMIT = float(os.environ.get('LAND_JAIL_LIMIT', '420'))         # s one jail escape may take
SCORE = {'jail': 100, 'invite': 70, 'tonic': 60, 'skill': 65, 'guild': 36, 'titles': 35, 'greet': 34,
         'hunt': 30}                                                  # how loudly a duty asks the brain for the turn
INVITE_SECS = 15.0                                                   # s a friend / guild invitation panel has to close after its button
INVITE_QUIET = 60.0                                                  # s the invite duty stays quiet after a press that did nothing
TITLES_EVERY = 3600.0                                                # s between two looks at the Titles page (a rank may have risen)
GUILD_CREATE = os.environ.get('LAND_GUILD_CREATE', '0') == '1'       # opt-in: make and name a guild of its own (never invites)
GREET_R = 30.0                                                       # ft: a boy this close gets one SpeedChat hello
GREET_GAP = 900.0                                                    # s before the same boy is greeted again
TELE_FAR = 150.0                                                     # ft: a friend closer than this is walked to, not teleported to
SKILL_CHECK = 15.0                                                   # s between two reads of the unspent-point stacks
SKILL_PRESS_SECS = 20.0                                              # s the server has to answer one skill-page +
SKILL_MAX = 12                                                       # points spent in one flow
SKILL_TRIES = 3                                                      # presses per point (a page state that was wrong, a press nobody answered)
SKILL_BANNER_SECS = 8.0                                              # s to wait for the level-up banner (it shuts the page and re-tabs it)
TUT_GOT_CUTLASS = 4                                                  # PiratesGlobals.TUT_GOT_CUTLASS: below it the cutlass tab only takes Sweep
WSKILL_HOLD = 20.0                                                   # s a weapon skill the tray refused is left alone
TONIC_LOW_GAP = 300.0                                                # s between two LAND-TONIC-LOW events
HUNT_START_HP = float(os.environ.get('LAND_HUNT_START_HP', '0.75'))  # a hunt starts at or above this health fraction
HUNT_MIN_HP = 0.50                                                   # below this between fights: stand and recover first
HUNT_SECS = float(os.environ.get('LAND_HUNT_SECS', '540'))           # one hunt ends itself before the brain's 600 s limit
HUNT_REST = 120.0                                                    # s the hunt stays quiet after a hunt that fought
HUNT_REST_EMPTY = 300.0                                              # ... after one that found no enemy
HUNT_REST_NOSPAWN = 600.0                                            # ... after one in an area with no spawn camp
OFF_STATE_SECS = 20.0                                                # s out of LandRoam / Battle before a hunt gives up
SKIP_SECS = 30.0                                                     # s a foe we could not reach is left alone
BOY_R = 40.0                                                         # ft: no foe or camp this close to Player1, Player2 or Host
CAVE_ENGAGE_R = 12.0                                                 # ft: in a cave a foe further than this is walked to by the cave walker
LAND_ENGAGE_R = 60.0                                                 # ft: on open land a foe further than this is walked to round the buildings
SPAWN_ROUNDS = 2                                                     # spawn camps walked through with no enemy before the hunt ends
HUNT_RANGE = 1000.0                                                  # ft: a hunt only walks to camps this close to its home camp
NO_ROUTE_BUG_AT = 2                                                  # cave walker 'no open way' at one area this often = a BOT bug
BEAT = 0.25
VITAE_EVERY = 5.0                                                    # s between two reads of the Vitae level
SC = {'hi': 100, 'hello?': 109, 'thanks': 500}                       # the game's own SpeedChat ids (b_brain has the same)
SC_GAP = 60.0                                                        # s before the same line again
QUIET_BUG = 600.0                                                    # s a duty stays quiet after it filed a BOT bug
RESERVED = ('PASS', 'FAIL', 'STALL', 'MILESTONE', 'STATE', 'BUG', 'BRAIN')    # the brain's event names (INTERFACE 4)

# weapons and skill points: the game's own names (UberDogGlobals.InventoryType, read from the game source 11-22)
KINDS = ('Cutlass', 'Dagger', 'Pistol', 'Doll', 'Wand')              # rotation order = skill-spending order (grenade: draw bug
#                                                                      11-20; musket parked until its aiming is proven)
SKILL_ORDER = {                                                      # per weapon, the order points go into (learned ones only)
    'Cutlass': ('CutlassHack', 'CutlassSlash', 'CutlassCleave', 'CutlassFlourish', 'CutlassStab', 'CutlassSweep',
                'CutlassParry', 'CutlassBrawl', 'CutlassTaunt', 'CutlassBladestorm'),
    'Dagger': ('DaggerCut', 'DaggerSwipe', 'DaggerGouge', 'DaggerEviscerate', 'DaggerAsp', 'DaggerAdder', 'DaggerSidewinder',
               'DaggerViperNest'),
    'Pistol': ('PistolShoot', 'PistolLeadShot', 'PistolVenomShot', 'PistolBaneShot', 'PistolHexEaterShot', 'PistolSilverShot',
               'PistolSteelShot', 'PistolSharpShooter'),
    'Doll': ('DollAttune', 'DollPoke', 'DollSwarm', 'DollCurse', 'DollBurn', 'DollLifeDrain', 'DollShackles'),
    'Wand': ('StaffBlast', 'StaffSoulFlay', 'StaffPestilence', 'StaffWither', 'StaffHellfire', 'StaffBanish',
             'StaffDesolation'),
}
SKILL_COMBO = ('CutlassSlash', 'CutlassCleave', 'CutlassFlourish', 'CutlassStab', 'DaggerSwipe', 'DaggerGouge',
               'DaggerEviscerate')                                   # the page's + needs the skill before it at 2+ points
USE_SKILLS = {                                                       # special skills fired through the tray between clicks, best first
    'Dagger': ('DaggerViperNest', 'DaggerSidewinder', 'DaggerAdder', 'DaggerAsp'),
    'Doll': ('DollLifeDrain', 'DollBurn', 'DollCurse', 'DollShackles'),
    'Wand': ('StaffDesolation', 'StaffHellfire', 'StaffWither', 'StaffPestilence', 'StaffSoulFlay'),
}                                                                    # cutlass: s_fighter's own; pistol shots need an ammo choice: clicks only

CAPTAINS = (100000656, 100000665, 100000170)                         # Player1, Player2, Host's pirate: the only ones it crews with
NEVER = (100000170, 100000173, 100000656, 100000665)                 # a proof run never plays as one of these


class Blocked(Exception):
    pass


def slug(s):
    return ''.join(c if c.isalnum() else '-' for c in str(s).lower()).strip('-')[:40] or 'x'


# ---------------------------------------------------------------------------------------------- pure
def hpFrac(hp, mx):
    return s_fighter.hpFrac(hp, mx)


def foeOver(vitae):
    """Pure: how many levels over its own a foe may be. Vitae running (level > 0) = none."""
    return 0 if (vitae or 0) > 0 else s_fighter.LVL_OVER


def outTonic(hpf, tonics, ready, gs, since):
    """Pure: drink a tonic now, between fights? Sheathed on land (LandRoam), hurt, more than KEEP_TONICS left, the
    game's tonic timer ready, and TONIC_GAP s since the last one. Nothing in s_fighter does this outside a fight."""
    return (gs == 'LandRoam' and hpf < OUT_TONIC_HP and tonics > KEEP_TONICS and bool(ready)
            and (since is None or since >= TONIC_GAP))


def duty(s):
    """Pure: what land.py wants to do now, as (name, why) or None. s = {'jailed', 'hpf', 'tonics', 'ready', 'gs',
    'tonicAgo', 'hunt': True when a hunt may start (on land, sheathed or drawn, healthy), 'quiet': {duty: True while
    that duty is quiet}, 'unspent': skill points to spend (any weapon), 'invite': (kind, avId) of a friend / guild
    invitation panel on screen, 'guild': True when it should make its own guild, 'titles': True when the Titles page is
    due, 'greet': the doId of a boy standing close that has not been greeted}. One ordering: jail first, then an
    invitation (a boy asked: answered at once), a tonic, a skill point (sheathed on land only: the skill page opens
    in LandRoam), the guild, the titles, a hello, then (free play) a hunt."""
    quiet = s.get('quiet') or {}
    if s.get('jailed'):
        return 'jail', 'in a jail cell: kick the door open and walk out'
    if s.get('invite') and not quiet.get('invite'):
        return 'invite', 'a %s invitation from %s is waiting' % tuple(s['invite'])
    if not quiet.get('tonic') and outTonic(s.get('hpf', 1.0), s.get('tonics', 0), s.get('ready', True), s.get('gs'),
                                           s.get('tonicAgo')):
        return 'tonic', 'hp %d%% with %d tonics, not fighting' % (round(100 * s['hpf']), s['tonics'])
    if not quiet.get('skill') and (s.get('unspent') or 0) > 0 and s.get('gs') == 'LandRoam':
        return 'skill', '%d skill point(s) to spend, not fighting' % s['unspent']
    if s.get('gs') == 'LandRoam':
        if s.get('guild') and not quiet.get('guild'):
            return 'guild', 'no guild yet: make one and name it'
        if s.get('titles') and not quiet.get('titles'):
            return 'titles', 'the Titles page is due: put the best earned badge on'
        if s.get('greet') and not quiet.get('greet'):
            return 'greet', 'boy %s is standing close: one SpeedChat hello' % s['greet']
    if s.get('hunt') and not quiet.get('hunt'):
        return 'hunt', 'free play: hp %d%% on land, nothing else asks for the pirate' % round(100 * s.get('hpf', 1.0))
    return None


def huntOk(hpf, gs, area):
    """Pure: a hunt may start: healthy enough, on land (LandRoam or Battle) and in an island or a cave / interior area."""
    return hpf >= HUNT_START_HP and gs in ('LandRoam', 'Battle') and area in ('DistributedIsland', 'DistributedGAInterior')


def legFor(d, cave):
    """Pure: how to cover d ft to a foe or a camp. 'engage' = Fighter's straight walk (close up); 'cave' = the cave walker
    (the trail from the area's waypoints, backing up when stuck: s_cavewalk); 'route' = s_story.go (round the buildings)."""
    if cave:
        return 'engage' if d <= CAVE_ENGAGE_R else 'cave'
    return 'engage' if d <= LAND_ENGAGE_R else 'route'


def hdist2(a, b):
    """Pure: the flat (x, y) distance between two points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def awayFrom(p, boys, r=BOY_R):
    """Pure: p (x, y) is further than r ft from every boy point."""
    return all(hdist2(p, b) > r for b in boys)


def pickTarget(rows, lvl, vitae, skip, now, boys):
    """Pure: rows = s_fighter.foeRows. -> the doId of the foe to hunt, or None: s_fighter.pickFoe's best (no crowd, lowest
    level, nearest; one level over its own at most, none while Vitae runs), not left alone until skip[doId] runs out, and
    never one near a boy (the boys' kills and spot come first)."""
    ids, _ = s_fighter.pickFoe(rows, lvl, s_fighter.VIEW, 99, foeOver(vitae))
    pos = {r[0]: r[4] for r in rows}
    for i in ids:
        if skip.get(i, 0) > now or not awayFrom(pos[i], boys):
            continue
        return i
    return None


def attackerRow(rows, lvl, over):
    """Pure: the nearest live enemy within 12 ft (someone hitting it while it walks) -> (doId, weak?) or None."""
    near = sorted((r for r in rows if (r[2] or 0) > 0 and r[1] <= 12.0), key=lambda r: r[1])
    return None if not near else (near[0][0], (near[0][3] or 0) <= (lvl or 1) + over)


def spawnNodes(qs, area):
    """Pure: the (x, y, z, name) of every enemy spawn node in that area of quest_spots.json (s_landfight.spawnNodes)."""
    return [tuple(o[1:4]) + (o[5],) for o in qs.get('objs', {}).values() if o[0] == area and o[4] == 'Spawn Node']


def huntGround(nodes, here, home, lvl, rng=HUNT_RANGE):
    """Pure: nodes = spawnNodes, here = (x, y) in the area frame, home = the (x, y) the last hunt here was built round
    (None the first time). The home is the camp s_fighter.spawnPick would take from here; it stays until that camp is more
    than rng ft from the stored one (the pirate is somewhere else now). -> (home, the nodes within rng ft of it): a hunt
    that sweeps every camp of its level (LANDPROOF1: 1400 ft out to a hillside camp it could not reach, into level-3
    camps at level 1) now sweeps the ground round its home instead."""
    anchor = s_fighter.spawnPick(nodes, here, set(), lvl)
    if anchor is None:
        return home, []
    if home is None or hdist2(anchor, home) > rng:
        home = (anchor[0], anchor[1])
    return home, [n for n in nodes if hdist2(n, home) <= rng]


def restAfter(end):
    """Pure: seconds the hunt duty stays quiet after a hunt that ended this way."""
    return {'no-spawn': HUNT_REST_NOSPAWN, 'no-foe': HUNT_REST_EMPTY, 'ko': 30.0, 'state': 30.0, 'area': 5.0}.get(end, HUNT_REST)


def pickSkill(order, qty, ids, combo=SKILL_COMBO):
    """Pure (s_skill.pickSkill's rule): order = skill names, qty = {name: stack}, ids = {name: InventoryType id}. -> the
    first name the skill page's + would take: learned (stack 1..5) and, for a combo skill, the skill before it (id - 1)
    at 2+ points."""
    byId = {v: k for k, v in ids.items()}
    for n in order:
        q = qty.get(n, 0)
        if not (1 <= q <= 5):
            continue
        if n in combo:
            prev = byId.get(ids[n] - 1)
            if prev is None or qty.get(prev, 0) <= 1:
                continue
        return n
    return None


def spendPlan(unspent, qty, ids):
    """Pure: unspent = {kind: points}, qty / ids as pickSkill. -> (kind, skill name) for the first kind (KINDS order) that
    has a point and a skill that takes it, or None."""
    for k in KINDS:
        if (unspent.get(k) or 0) > 0:
            n = pickSkill(SKILL_ORDER[k], qty, ids)
            if n is not None:
                return k, n
    return None


def pressRefusal(st):
    """Pure: why SkillPage.addPoint would drop a press without a word, from the page's state (its own checks, its own order);
    None = it sends spendSkillPoint. st: open (the page is the chest's current page and active), tab (it has a tab bar),
    rep / want (the page's current tab / the weapon's tab), tutBlock (the tutorial gate of the cutlass tab), unspent (the
    unspent stack of `want` as the page sees it, local mods first), limit (the skill has a stack limit), cur (the skill's
    points as the page sees them). A missing key reads as fine. -> 'closed' / 'no-tab-bar' / 'wrong-tab' / 'tutorial' /
    'no-unspent' / 'no-limit' / 'maxed' / None."""
    if not st.get('open', True):
        return 'closed'
    if not st.get('tab', True):
        return 'no-tab-bar'
    if st.get('rep', st.get('want')) != st.get('want'):
        return 'wrong-tab'
    if st.get('tutBlock'):
        return 'tutorial'
    if st.get('unspent', 1) < 1:
        return 'no-unspent'
    if not st.get('limit', True):
        return 'no-limit'
    if st.get('cur', 0) > 5:
        return 'maxed'
    return None


def bannerUp(gm):
    """The level-up banner is playing (GuiManager.showLevelUpText shuts the skill page and re-tabs it). Never raises."""
    try:
        iv = getattr(gm, 'levelUpIval', None)
        return bool(iv and iv.isPlaying())
    except Exception:
        return False


def skillPageState(la, gm, page, IT, sid, rep, unId):
    """The skill page's state as SkillPage.addPoint will see it (the keys pressRefusal reads, plus extras for the event
    line). Every read is guarded: a field the client lacks is left out, never an exception."""
    def g(obj, attr, default=None):
        try:
            return getattr(obj, attr, default)
        except Exception:
            return default
    inv = None
    try:
        inv = la.getInventory()
    except Exception:
        pass

    def qty(i):
        try:
            return inv.getStackQuantity(i)
        except Exception:
            return 0
    mods = g(page, 'localMods', None)
    mods = dict(mods) if isinstance(mods, dict) else {}
    st = {'want': rep, 'rep': g(page, 'currentRep', rep), 'tab': g(page, 'tabBar', 1) is not None,
          'mods': {str(k): v for k, v in mods.items()}}
    try:
        st['open'] = bool(gm.pageOpen(page))
    except Exception:
        st['open'] = False
    st['unspent'] = mods.get(unId, qty(unId))
    st['cur'] = mods.get(sid, qty(sid))
    if inv is not None and hasattr(inv, 'getStackLimit'):
        try:
            st['limit'] = bool(inv.getStackLimit(sid))
        except Exception:
            st['limit'] = False
    tut = g(g(la, 'style'), 'tutorial')
    sweep = getattr(IT, 'CutlassSweep', None)
    if tut is not None:
        st['tutorial'] = tut
        st['tutBlock'] = bool(rep == getattr(IT, 'CutlassRep', None) and tut < TUT_GOT_CUTLASS and sweep is not None
                              and qty(sweep) < 2 and sid != sweep)
    st['banner'] = bannerUp(gm)
    frames = g(page, 'skillFrames')
    if isinstance(frames, dict):
        st['frame'] = sid in frames
    return st


def weaponNames(kind):
    """Pure: the game's weapon item names of a kind, best level first (WandWeaponL6 ... WandWeaponL1)."""
    return ['%sWeaponL%d' % (kind, n) for n in (6, 5, 4, 3, 2, 1)]


def ownedWeapons(qty):
    """Pure: qty = {item name: stack quantity} -> {kind: the best owned item name}."""
    out = {}
    for k in KINDS:
        for n in weaponNames(k):
            if (qty.get(n) or 0) > 0:
                out[k] = n
                break
    return out


def weaponKind(owned, bad, nth):
    """Pure: the weapon hunt number nth uses: the owned kinds not marked bad, in KINDS order, round robin (every weapon
    gets its turn; a pirate with only the cutlass always gets it)."""
    kinds = [k for k in KINDS if k in owned and k not in bad]
    return kinds[nth % len(kinds)] if kinds else 'Cutlass'


def pickWeaponSkill(order, ranks, recharge, mojo, costs, hold, now):
    """Pure (s_fighter.bestSkill's rule plus a hold-off): order = skill ids best first. -> the first one learned (stack
    > 1), recharged, affordable and not held off after a refusal, or None."""
    for sid in order:
        if (ranks.get(sid) or 0) <= 1 or (recharge.get(sid) or 0) > 0:
            continue
        if (costs.get(sid) or 0) > (mojo or 0) or hold.get(sid, 0) > now:
            continue
        return sid
    return None


def scDue(kind, last, now):
    """Pure: a SpeedChat line may go (the same line at most once per SC_GAP s). -> the SpeedChat id or None."""
    if kind not in SC:
        return None
    t = last.get(kind)
    return SC[kind] if t is None or now - t >= SC_GAP else None


def captains(raw=None):
    """Pure: the pirates it befriends, guilds and crews with: Player1, Player2 and Host's pirate, plus PBOT_CAPTAINS (a
    test captain's id: the stand-in boy of a proof run). raw = that env value (None = read it)."""
    raw = os.environ.get('PBOT_CAPTAINS', '') if raw is None else raw
    return set(CAPTAINS) | {int(x) for x in raw.replace(',', ' ').split() if x.isdigit()}


def inviteAnswer(avId, caps):
    """Pure: 'ok' for a friend / guild invitation from a captain, 'no' for anyone else (declined, never ignored: the
    other side's panel closes, and the boys' lists stay theirs)."""
    return 'ok' if avId in caps else 'no'


def titlePick(rows):
    """Pure: rows = [(index, rank, active)] for the Titles page's panels. -> the index of the panel to put on as the
    badge (the highest rank of those earned, rank >= 1: rank 0 needs a magic word, which a player bot never uses), or None
    when none is earned or one is already on."""
    if any(r[2] for r in rows):
        return None
    earned = [r for r in rows if (r[1] or 0) >= 1]
    return max(earned, key=lambda r: (r[1], -r[0]))[0] if earned else None


def greetDue(near, last, now):
    """Pure: near = [doId] of the boys inside GREET_R, last = {doId: time greeted}. -> the doId to say hello to, or None."""
    for i in near:
        t = last.get(i)
        if t is None or now - t >= GREET_GAP:
            return i
    return None


def teleOk(avId, caps, dist):
    """Pure: may the bot teleport to this pirate (row 37)? A captain, never Host's own pirate (that is his game), and not
    one already within TELE_FAR ft (dist None = not in view). -> (ok, why)."""
    if avId == 100000170:
        return False, "Host's pirate: never"
    if avId not in caps:
        return False, 'not a captain'
    if dist is not None and dist <= TELE_FAR:
        return False, 'already %d ft away: walk' % round(dist)
    return True, 'ok'


# ---------------------------------------------------------------------------------------------- the wrapper
class PlayerH:
    """The walker's H as a player bot's skill sees it: everything delegates, except magic words (refused: one BOT bug),
    the brain's own reserved event names (renamed LAND-..., so they never end the brain's run) and H.snap."""

    def __init__(self, H):
        self._H = H
        self.blocked = None
        self.stalls = 0
        self.noRoute = {}        # area uniqueId -> how often the cave walker found no open way there

    def __getattr__(self, k):
        return getattr(self._H, k)

    def ev(self, name, /, **kw):                       # positional-only: events may carry their own name=... field
        if name == 'STALL':
            self.stalls += 1
        if name == 'CAVE-NO-ROUTE' and str(kw.get('why', '')).startswith('no open way'):
            a = self._H.area()
            k = a[1] if a else None
            self.noRoute[k] = self.noRoute.get(k, 0) + 1
        if name in RESERVED or name.startswith(('CREW-', 'PBOT-')):
            return self._H.ev('LAND-' + name, **kw)
        return self._H.ev(name, **kw)

    def snap(self, tag):
        return self._H.ev('LAND-SNAP', tag=tag)

    def mw(self, word):
        self.blocked = str(word)
        self._H.ev('LAND-MW-BLOCKED', word=str(word).split(' ')[0], full=str(word)[:80])
        raise Blocked(word)


def strict(gen, H):
    """Drive gen, turning a strict ('until', ...) wait into an ('upto', ...) one (a STALL would end the brain's run):
    when it runs out the engine's own check decides. Returns gen's value."""
    send = None
    while True:
        try:
            item = gen.send(send)
        except StopIteration as e:
            return e.value
        send = None
        if isinstance(item, tuple) and item and item[0] == 'until':
            fn, secs = item[1], item[2]
            what = item[3] if len(item) > 3 else '?'
            yield ('upto', fn, secs, what)
            try:
                ok = fn()
            except Exception:
                ok = False
            if not ok:
                H.ev('LAND-WAIT', what=what, secs=secs)
        else:
            yield item


# ---------------------------------------------------------------------------------------------- live
def jailedNow(H):
    """In the jail interior, or the server gave a cell (jailCellIndex 100 = none). Same test as s_story.jailed."""
    a = H.area()
    return (a is not None and a[0] == 'DistributedJailInterior') or getattr(H.la, 'jailCellIndex', 100) < 100


def _gs(la):
    try:
        return la.getGameState()
    except Exception:
        return None


def tonicsLeft(H):
    try:
        inv = H.la.getInventory()
        return sum(v for v in inv.getTonics().values() if v) if inv else 0
    except Exception:
        return 0


def tonicReady(H):
    """The game's own tonic timer (the same skillDiary Fighter.ready reads). Unknown = ready."""
    try:
        from pirates.uberdog.UberDogGlobals import InventoryType
        t = H.la.skillDiary.getTimeRemaining(InventoryType.UseItem)
        return t is None or t <= 0
    except Exception:
        return True


def vitaeLevel(H):
    try:
        from pirates.uberdog.UberDogGlobals import InventoryType
        inv = H.la.getInventory()
        return inv.getStackQuantity(InventoryType.Vitae_Level) if inv else 0
    except Exception:
        return 0


def unspentNow(H):
    """{kind: unspent skill points} for the weapons that have any (the Unspent<Kind> stacks). Unknown = {}."""
    try:
        from pirates.uberdog.UberDogGlobals import InventoryType
        inv = H.la.getInventory()
        if not inv:
            return {}
        out = {}
        for k in KINDS:
            n = inv.getStackQuantity(getattr(InventoryType, 'Unspent' + k))
            if n and n > 0:
                out[k] = n
        return out
    except Exception:
        return {}


def goldNow(H):
    """The gold in the pocket (a kill pays straight into it: there is no loot pickup; s_lanes.gold reads the same)."""
    try:
        inv = H.la.getInventory()
        return inv.getGoldInPocket() if inv else 0
    except Exception:
        return 0


def boyPoints(H):
    """(x, y) render points of the boys' pirates (and Host's) that are on this client, for keeping clear of them."""
    pts = []
    for i in CAPTAINS:
        o = H.cr.doId2do.get(i)
        if o is not None:
            try:
                p = o.getPos(H.render)
                pts.append((p[0], p[1]))
            except Exception:
                pass
    return pts


def panelGone(p):
    """A GuiPanel that was destroyed (its own 'destroyed' flag, or its node removed)."""
    if p is None or getattr(p, 'destroyed', False):
        return True
    try:
        return bool(p.isEmpty())
    except Exception:
        return False


def inviteNow(H):
    """The friend or guild invitation panel on screen: (kind, panel) or None. Reads attributes only (GuiManager keeps
    friendInvitee / guildInvitee until the panel is destroyed, then deletes the attribute)."""
    try:
        gm = H.la.guiMgr
        for kind, attr in (('friend', 'friendInvitee'), ('guild', 'guildInvitee')):
            p = getattr(gm, attr, None)
            if p is not None and not panelGone(p) and getattr(p, 'bOk', None) is not None:
                return kind, p
    except Exception:
        pass
    return None


def press(btn):
    """Press a DirectGui button the way s_kidfriends does: only while it is NORMAL, through its own command. -> True when
    it was pressed."""
    try:
        if btn is None or btn['state'] != 'normal':
            return False
        if hasattr(btn, 'commandFunc'):
            btn.commandFunc(None)
        else:
            btn['command']()
        return True
    except Exception:
        return False


def boysNear(H, r=GREET_R):
    """The doIds of the captains' pirates inside r ft of us that this client can see (a few dict lookups)."""
    out = []
    try:
        me = H.la.getPos(H.render)
        for i in CAPTAINS:
            o = H.cr.doId2do.get(i)
            if o is not None and o is not H.la:
                p = o.getPos(H.render)
                if hdist2((p[0], p[1]), (me[0], me[1])) <= r:
                    out.append(i)
    except Exception:
        return []
    return out


def watched(gen, look, every=1.0):
    """Generator: drive a walker generator, calling look() every `every` s of game time. -> (its value, None), or
    (None, why) when look() answered with a reason (the walker is closed: the caller cancels the walk)."""
    last = time.time()
    try:
        while True:
            try:
                item = next(gen)
            except StopIteration as e:
                return e.value, None
            yield item
            if time.time() - last >= every:
                last = time.time()
                why = look()
                if why:
                    return None, why
    finally:
        gen.close()


class Land:
    """The skill as the brain holds it."""
    name = 'land'
    limit = 600                 # a hunt or a jail escape may run this long; the brain cuts it at this
    crewOk = False              # in a boy's crew the brain's crew states play (the boys come first)

    def __init__(self, bot):
        self.bot, self.H = bot, bot.H
        self.PH = PlayerH(bot.H)
        self.tonicT = None
        self.sc = {}
        self.quietUntil = {}     # duty -> time.time() until it stays quiet (after a BOT bug it filed)
        self.noData = set()      # area uniqueIds the cave walker has no waypoints for (walked the straight way)
        self.bugged = set()      # area uniqueIds a cave-no-route bug was filed for
        self.unspent, self.unspentT = {}, -1e9      # {kind: points}, read at most every SKILL_CHECK s
        self.hunts = 0           # hunts started: the weapon rotation's counter
        self.home = {}           # area uniqueId -> (x, y) the hunts there are built round (huntGround)
        self.bad = set()         # weapon kinds that landed no hit in a whole fight (left alone for the run)
        self.hold = {}           # weapon skill id -> time.time() until the tray's refusal is not asked again
        self.refused = {}        # weapon skill id -> how often the tray refused it
        self.lowT = None         # time.time() of the last LAND-TONIC-LOW
        self.titlesT = -1e9      # time.time() of the last look at the Titles page
        self.titlesOff = False   # the one LAND-TITLES-OFF event (no Titles page in this client) is out
        self.titlesOpen = False  # the Titles page was opened by us and not yet closed
        self.guildDone = False   # the opt-in guild errand ran (once per run)
        self.greeted = {}        # boy doId -> time.time() of the hello

    # -- state (cheap reads only: want() is asked every 2 s and must stay under a millisecond)
    def state(self):
        H, la = self.H, self.H.la
        hp, mx = getattr(la, 'hp', 0), getattr(la, 'maxHp', 0)
        now = time.time()
        hpf = hpFrac(hp, mx)
        gs, area = _gs(la), H.area()
        if now - self.unspentT >= SKILL_CHECK:      # the points: a few stack reads, cached
            self.unspent, self.unspentT = unspentNow(H), now
        s = {'jailed': jailedNow(H), 'hpf': hpf, 'gs': gs, 'tonics': 0, 'ready': True,
             'tonicAgo': None if self.tonicT is None else now - self.tonicT,
             'hunt': huntOk(hpf, gs, area[0] if area else None), 'unspent': sum(self.unspent.values()),
             'quiet': {d: True for d, t in self.quietUntil.items() if now < t}}
        if hpf < OUT_TONIC_HP:           # the inventory is read only when a drink could be due
            s['tonics'], s['ready'] = tonicsLeft(H), tonicReady(H)
        inv = inviteNow(H)               # social errands: attribute reads only
        if inv is not None:
            s['invite'] = (inv[0], getattr(inv[1], 'avId', None))
        if gs == 'LandRoam':
            s['titles'] = self.titlesDue(now)
            s['guild'] = GUILD_CREATE and not self.guildDone and self.noGuild()
            s['greet'] = greetDue(boysNear(H), self.greeted, now)
        return s

    def titlesDue(self, now):
        """The Titles page exists in this client (want-titles-page, off by default: a game config gap) and is due."""
        try:
            has = self.H.la.guiMgr.titlesPage is not None
        except Exception:
            has = False
        if not has:
            if not self.titlesOff:
                self.titlesOff = True
                self.H.ev('LAND-TITLES-OFF', why='no Titles page in this client (want-titles-page is off)')
            return False
        return now - self.titlesT >= TITLES_EVERY

    def noGuild(self):
        try:
            return (self.H.la.getGuildId() or 0) <= 0
        except Exception:
            return False

    def want(self):
        """-> (score, why) for what land.py wants to do now, or None."""
        d = duty(self.state())
        return None if d is None else (SCORE[d[0]], '%s: %s' % d)

    def quiet(self, name, secs, why):
        self.quietUntil[name] = time.time() + secs
        self.H.ev('LAND-QUIET', duty=name, secs=secs, why=why)

    def cut(self, why):
        """The brain stopped the flow (limit, crew, safety, down, error). Keys the walker holds go up with the brain's
        release(); a Fighter, a tray hook or a wrapped call is put back by the flow's own finally. Left to clean: the skill
        page (closed at once) and a drawn weapon (a new generator the brain drives, <= 60 s: the next skill expects LandRoam,
        and a drawn weapon keeps the Battle state). -> that generator, or None when there is nothing to put away."""
        self.H.ev('LAND-CUT', why=why)
        self.closeSkillPage()
        self.closeTitlesPage()
        la = self.H.la
        if getattr(la, 'isWeaponDrawn', False) and (getattr(la, 'hp', 1) or 0) > 0 and _gs(la) in ('Battle', 'LandRoam'):
            return self.sheathe()
        return None

    def closeSkillPage(self):
        """The skill page shut again (the Skills key), when a cut left it open. Never raises."""
        try:
            import builtins
            gm = self.H.la.guiMgr
            if gm.pageOpen(gm.skillPage):
                builtins.messenger.send('guiMgrToggleLevels')
        except Exception:
            pass

    def closeTitlesPage(self):
        """The Titles page (the sea chest) shut again, when we opened it and a cut left it open. Never raises."""
        if not self.titlesOpen:
            return
        self.titlesOpen = False
        try:
            self.H.la.guiMgr.hideSeaChest()
        except Exception:
            pass

    def flow(self):
        """Generator: do the duty that is due once; book it; file a BOT bug when it breaks. -> a small dict
        {duty, ok, ...} or None when nothing was due."""
        d = duty(self.state())
        if d is None:
            return None
        name, H = d[0], self.H
        try:
            if name == 'jail':
                out = yield from strict(self.jail(), self.PH)
            elif name == 'hunt':
                out = yield from strict(self.hunt(), self.PH)
            elif name == 'skill':
                out = yield from strict(self.skillPoints(), self.PH)
            elif name == 'invite':
                out = yield from strict(self.invite(), self.PH)
            elif name == 'titles':
                out = yield from strict(self.titles(), self.PH)
            elif name == 'guild':
                out = yield from strict(self.guildMake(), self.PH)
            elif name == 'greet':
                out = self.greet()
            else:
                out = self.drink()
            return out
        except Blocked as e:
            self.fileBug('other', 'land-mw-blocked', 'a land duty (%s) asked for the magic word %r' % (name, str(e).split(' ')[0]))
            if name != 'jail':          # SAFETY duties never go quiet: a pirate still in a cell is asked again
                self.quiet(name, INVITE_QUIET if name == 'invite' else QUIET_BUG, 'asked for a magic word')
        except Exception as e:
            tb = traceback.format_exc()
            frames = traceback.extract_tb(e.__traceback__)
            self.fileBug('traceback', 'land-crash-%s-%s' % (slug(type(e).__name__), slug(frames[-1].name if frames else '?')),
                         'a land duty (%s) crashed: %s' % (name, tb.strip().splitlines()[-1][:160]), tb=tb)
            if name != 'jail':
                self.quiet(name, INVITE_QUIET if name == 'invite' else QUIET_BUG, 'crashed')
            self.closeTitlesPage()
        return {'duty': name, 'ok': False, 'why': 'bot'}

    def fileBug(self, kind, key, what, tb='', tag='BOT'):
        try:
            self.bot.bug(kind, key, tag, what, tb=tb)
        except Exception:
            self.H.ev('LAND-BUG-FAILED', tb=traceback.format_exc()[-300:])

    def say(self, kind):
        """SpeedChat only (never typed chat), the same line at most once per SC_GAP s."""
        i = scDue(kind, self.sc, time.time())
        if i is None:
            return False
        try:
            self.H.la.b_setSC(i)
        except Exception:
            return False
        self.sc[kind] = time.time()
        return True

    def drink(self):
        """One tonic between fights, through the same call the fight uses (Fighter.tonic)."""
        f = s_fighter.Fighter(self.H, None, None)
        try:
            hp0 = getattr(self.H.la, 'hp', None)
            ok = f.tonic()
        finally:
            f.close()
        self.tonicT = time.time()
        self.H.ev('LAND-TONIC', ok=bool(ok), hp=hp0, maxHp=getattr(self.H.la, 'maxHp', None), left=tonicsLeft(self.H))
        return {'duty': 'tonic', 'ok': bool(ok), 'hp': hp0}

    def tonicLow(self, hpf):
        """Hurt with no tonic left (row 46): one LAND-TONIC-LOW event per TONIC_LOW_GAP s, for the brain and the games skill
        (the brew table / the shop are theirs). The hunt itself rests until it has recovered (HUNT_MIN_HP, REST_MAX)."""
        now = time.time()
        if self.lowT is None or now - self.lowT >= TONIC_LOW_GAP:
            self.lowT = now
            self.H.ev('LAND-TONIC-LOW', hp=getattr(self.H.la, 'hp', None), frac=round(hpf, 2), area=self.H.area())

    # -- skill points (row 45)
    def skillPoints(self):
        """Generator: spend the unspent skill points the way a player does: the skill page opens (the Skills key), the
        weapon's tab (SkillPage.update, what clicking the tab does), the skill's + (SkillPage.addPoint, which sends
        spendSkillPoint); a point is spent when the skill's stack went up by one and the unspent stack down by one within
        SKILL_PRESS_SECS. addPoint drops a press WITHOUT a word when the page is in a wrong state (no tab bar, another
        tab current, a stale local count, the level-up banner just re-tabbed it), so each press first reads the page's
        state (LAND-SKILL-STATE), repairs what a player's click would have (the tab, the stale counts), and only presses
        when pressRefusal finds nothing; an unanswered press is tried again, SKILL_TRIES times in all. Never a level-up
        magic word, never a respec. A point that could not be spent = one BOT bug (with the page's state in its text) and
        the duty quiet for QUIET_BUG. -> {duty, ok, spent, skills}."""
        import builtins
        from pirates.uberdog.UberDogGlobals import InventoryType as IT
        H, la = self.PH, self.H.la
        inv, gm = la.getInventory(), la.guiMgr
        page = gm.skillPage
        ids = {n: getattr(IT, n) for k in KINDS for n in SKILL_ORDER[k] if hasattr(IT, n)}
        spent, ok, why, aborted = [], True, None, False
        H.ev('LAND-SKILL', unspent=dict(self.unspent), gs=_gs(la))
        for _ in range(SKILL_MAX):
            if _gs(la) != 'LandRoam':
                break
            qty = {n: inv.getStackQuantity(i) for n, i in ids.items()}
            un = {k: inv.getStackQuantity(getattr(IT, 'Unspent' + k)) for k in KINDS}
            plan = spendPlan(un, qty, ids)
            if plan is None:
                break
            kind, name = plan
            sid, rep, unId = ids[name], getattr(IT, kind + 'Rep'), getattr(IT, 'Unspent' + kind)
            u0, q0 = un[kind], qty[name]
            got, last, st, done = [], None, {}, False
            for attempt in range(1, SKILL_TRIES + 1):
                if bannerUp(gm):                       # the level-up banner shuts the page and re-tabs it: let it end
                    yield ('upto', lambda: not bannerUp(gm), SKILL_BANNER_SECS, 'level-up banner')
                if _gs(la) != 'LandRoam':
                    aborted = True
                    break
                fixes = []
                mods = getattr(page, 'localMods', None)
                if isinstance(mods, dict):             # a count the page kept from an earlier press that the game never confirmed
                    for k in (unId, sid):
                        if k in mods and mods[k] != inv.getStackQuantity(k):
                            mods.pop(k, None)
                            fixes.append('localMods')
                if not gm.pageOpen(page):
                    builtins.messenger.send('guiMgrToggleLevels')
                    yield ('upto', lambda: gm.pageOpen(page), 10, 'skill page')
                    if not gm.pageOpen(page):
                        last = 'closed'
                        H.ev('LAND-SKILL-STATE', skill=name, attempt=attempt, refusal=last, fixes=fixes)
                        continue
                if getattr(page, 'tabBar', 1) is None and hasattr(page, 'show'):
                    page.show()                        # what the chest does when it turns to the page; makes the tab bar
                    fixes.append('show')
                page.update(rep, fromUser=1)
                yield 1
                st = skillPageState(la, gm, page, IT, sid, rep, unId)
                if st.get('rep', rep) != rep and hasattr(page, 'setRep'):
                    page.setRep(rep)                   # the tab a click would have chosen
                    fixes.append('setRep')
                    st = skillPageState(la, gm, page, IT, sid, rep, unId)
                last = pressRefusal(st)
                H.ev('LAND-SKILL-STATE', skill=name, attempt=attempt, refusal=last, fixes=fixes, **st)
                if last:
                    if last in ('closed', 'no-tab-bar') and gm.pageOpen(page):
                        builtins.messenger.send('guiMgrToggleLevels')      # shut it; the next try opens it afresh
                    yield 2
                    continue
                got, orig = [], la.spentSkillPoint

                def answer(category, *a, _o=orig, _got=got):
                    _got.append(category)
                    return _o(category, *a)
                la.spentSkillPoint = answer
                try:
                    page.addPoint(sid)
                    yield ('upto', lambda: inv.getStackQuantity(sid) > q0 and inv.getStackQuantity(unId) < u0,
                           SKILL_PRESS_SECS, 'point spent')
                finally:
                    la.__dict__.pop('spentSkillPoint', None)       # back to the class's own method
                if inv.getStackQuantity(sid) == q0 + 1 and inv.getStackQuantity(unId) == u0 - 1:
                    done = True
                    break
                last = 'press-unanswered' if not got else 'answered-no-change'
                if got:
                    break                              # the server answered and the stacks did not move: not a page problem
            if aborted:
                break
            if not done:
                q1, u1 = inv.getStackQuantity(sid), inv.getStackQuantity(unId)
                short = {k: st[k] for k in ('open', 'tab', 'rep', 'want', 'unspent', 'cur', 'limit', 'tutBlock', 'banner')
                         if k in st}
                ok, why = False, 'the press did not spend a point (%s %d->%d, unspent %d->%d, answer %s, last %s, page %s)' % (
                    name, q0, q1, u0, u1, got, last, short)
                break
            spent.append(name)
            H.ev('LAND-SKILL-SPENT', skill=name, kind=kind, qty=inv.getStackQuantity(sid), unspent=inv.getStackQuantity(unId))
        if gm.pageOpen(page):
            builtins.messenger.send('guiMgrToggleLevels')
            yield 1
        self.unspentT = -1e9                       # read the stacks again at the next want()
        if not ok:
            H.ev('LAND-SKILL-NOSPEND', why=why, spent=len(spent), gs=_gs(la))
            self.fileBug('other', 'land-skill-no-spend', 'a skill point could not be spent: %s' % why)
            self.quiet('skill', QUIET_BUG, 'no point spent')
        return {'duty': 'skill', 'ok': ok, 'spent': len(spent), 'skills': spent}

    # -- weapons (row 44)
    def ownedNow(self):
        """{kind: item name} for the weapons in the pirate's inventory (the best level of each). Unknown = {}."""
        try:
            from pirates.uberdog.UberDogGlobals import InventoryType as IT
            inv = self.H.la.getInventory()
            return ownedWeapons({n: inv.getStackQuantity(getattr(IT, n)) for k in KINDS for n in weaponNames(k)
                                 if hasattr(IT, n)})
        except Exception:
            return {}

    def holding(self, kind):
        """The pirate has a weapon of this kind drawn."""
        la = self.H.la
        try:
            from pirates.uberdog.UberDogGlobals import InventoryType as IT
            ids = {getattr(IT, n) for n in weaponNames(kind) if hasattr(IT, n)}
        except Exception:
            return False
        return bool(getattr(la, 'isWeaponDrawn', False)) and getattr(la, 'currentWeaponId', None) in ids

    def equip(self, kind, owned):
        """Generator: that weapon in hand the player's way (s_mech.draw: another drawn one is put away first, toggleWeapon,
        one press again when the AI dropped the first, the draw animation). -> True when it is drawn."""
        from pirates.uberdog.UberDogGlobals import InventoryType as IT
        la, H = self.H.la, self.PH
        wid = getattr(IT, owned[kind])
        if getattr(la, 'isWeaponDrawn', False) and getattr(la, 'currentWeaponId', None) != wid:
            la.toggleWeapon(la.currentWeaponId)
            yield ('upto', lambda: not getattr(la, 'isWeaponDrawn', False), 6, 'put away')
        fresh = not getattr(la, 'isWeaponDrawn', False)
        if fresh:
            la.toggleWeapon(wid)
        yield ('upto', lambda: getattr(la, 'isWeaponDrawn', False) and la.currentWeaponId == wid, 8, 'drawn')
        if fresh and not (getattr(la, 'isWeaponDrawn', False) and la.currentWeaponId == wid):
            H.ev('LAND-DRAW-RETRY', weapon=wid, current=getattr(la, 'currentWeaponId', None), gs=_gs(la))
            yield 3.0
            la.toggleWeapon(wid)
            yield ('upto', lambda: getattr(la, 'isWeaponDrawn', False) and la.currentWeaponId == wid, 8, 'drawn again')
        if fresh:
            yield 1.5                          # the draw animation: a skill pressed during it gets no answer
        return bool(getattr(la, 'isWeaponDrawn', False) and la.currentWeaponId == wid)

    def sheathe(self):
        """Generator: the weapon put away the player's way, then back to LandRoam (a drawn weapon keeps the Battle state,
        and the skill page, the shops and the doors expect LandRoam). No yield inside a finally: safe to close."""
        la, H = self.H.la, self.PH
        H.walk_cancel()
        if getattr(la, 'isWeaponDrawn', False):
            la.toggleWeapon(la.currentWeaponId)
            yield ('upto', lambda: not getattr(la, 'isWeaponDrawn', False), 6, 'put away')
        yield ('upto', lambda: _gs(la) == 'LandRoam', 20, 'land roam')
        H.ev('LAND-SHEATHE', gs=_gs(la), drawn=bool(getattr(la, 'isWeaponDrawn', False)))

    def weaponSkill(self, f, kind):
        """One special skill of the drawn weapon between the beats of a fight, through the same tray call s_fighter's cutlass
        skills use (triggerSkillTraySkill); the tray's refusal holds that skill off WSKILL_HOLD s. -> True when it fired."""
        if f.tray is None or f.down or not self.holding(kind):
            return False
        if time.time() - self.hold.get(('err', kind), -1e9) < 30.0:
            return False                         # it raised a moment ago: let Fighter fight alone for a while
        try:
            from pirates.uberdog.UberDogGlobals import InventoryType as IT
            from pirates.battle import WeaponGlobals
            order = [getattr(IT, n) for n in USE_SKILLS.get(kind, ()) if hasattr(IT, n)]
            if not order:
                return False
            la, inv, now = self.H.la, self.H.la.getInventory(), time.time()
            ranks, rech, costs = {}, {}, {}
            for sid in order:
                try:
                    ranks[sid] = inv.getStackQuantity(sid)
                    rech[sid] = la.skillDiary.getTimeRemaining(sid)
                    costs[sid] = -1 * WeaponGlobals.getMojoCost(sid)
                except Exception:
                    ranks[sid] = 0
            sid = pickWeaponSkill(order, ranks, rech, getattr(la, 'mojo', 0), costs, self.hold, now)
            if sid is None:
                return False
            if hdist2(la.getPos(self.H.render), f.foe.getPos(self.H.render)) > s_fighter.REACH + 2.0:
                return False                     # not at the foe yet: Fighter walks up first
            n0 = len(f.tries)
            la.currentTarget = f.foe
            try:
                f.tray.triggerSkillTraySkill(sid)
            except Exception:
                pass
            if any(t[2] for t in f.tries[n0:]):
                f.skills += 1
                f.hits += 1
                self.H.ev('LAND-WEAPON-SKILL', weapon=kind, skill=sid, foe=f.foe.doId, foeHp=getattr(f.foe, 'hp', None),
                          mojo=getattr(la, 'mojo', None))
                return True
            self.hold[sid] = now + WSKILL_HOLD
            self.refused[sid] = self.refused.get(sid, 0) + 1
            if self.refused[sid] == 1:
                self.H.ev('LAND-WEAPON-SKILL-REFUSED', weapon=kind, skill=sid, gs=_gs(la))
            return False
        except Exception:
            self.H.ev('LAND-WEAPON-SKILL-ERROR', weapon=kind, tb=traceback.format_exc()[-300:])
            self.hold[('err', kind)] = time.time()
            return False

    # -- hunting (rows 40, 43)
    def inCave(self):
        """In a jungle / cave area the cave walker knows (s_story.go uses it there too). An interior it has no waypoints
        for (a tavern) is walked the straight way once it said so."""
        a = self.PH.area()
        return a is not None and a[0] == 'DistributedGAInterior' and a[1] not in self.noData

    def goTo(self, pt, tag, arrive, obj=None):
        """Generator: walk to the render point pt (obj = the foe, so s_story.go can follow it) the way a player does:
        close up the straight walk, on an island beyond LAND_ENGAGE_R round the buildings (s_story.go), in a cave beyond
        CAVE_ENGAGE_R along the cave's trail (s_cavewalk.walk: Fighter's own straight walk sticks on the cave walls: the
        known bot routing bug). -> True there, 'area' (a tunnel / door took it elsewhere), False (no way, stuck) or
        None (a cave with no waypoints: nothing was walked, the caller goes straight)."""
        H = self.PH
        me = H.la.getPos(H.render)
        d = math.hypot(pt[0] - me[0], pt[1] - me[1])
        kind = legFor(d, self.inCave())
        if kind == 'cave':
            import s_cavewalk
            r = yield from s_cavewalk.walk(H, (pt[0], pt[1], pt[2]), max(arrive, 4.0), tag)
            if r is None:
                a = H.area()
                self.noData.add(a[1] if a else None)
                H.ev('LAND-CAVE-NODATA', tag=tag, area=a)
            return r
        if kind == 'route':
            import s_story
            return (yield from s_story.go(H, obj if obj is not None else pt, arrive, False, None, tag))
        return (yield from H.walk_to(pt, arrive=arrive, timeout=20.0 + d / 6.0, tag=tag))

    def fileNoRoute(self, uid, what):
        """The cave walker found no open way: the same area twice = one BOT bug (with the numbers), the foe or camp is
        left alone either way."""
        if self.PH.noRoute.get(uid, 0) >= NO_ROUTE_BUG_AT and uid not in self.bugged:
            self.bugged.add(uid)
            self.fileBug('stuck', 'land-cave-no-route-%s' % slug(uid),
                         'the cave walker found no open way to %s in area %s (%d times)' % (what, uid, self.PH.noRoute[uid]))

    def hunt(self):
        """Generator: one free-play hunt (<= HUNT_SECS): fight what is in view (Fighter: tonic below 45%, back off below
        30%), else walk to a spawn camp of its level and look again, as s_landfight does; every leg through goTo (caves);
        a tonic between fights; no foe or camp near a boy; foes at or below its own level while Vitae runs; never a magic
        word. -> {duty, ok, end, kills, gold, secs, ...}; end = time / no-foe / no-spawn / ko / state / area / hurt."""
        import s_story as s      # live only: s_story reads the quest ladder from the game at import
        H, la = self.PH, self.H.la
        t0 = time.time()
        g0, uid0 = goldNow(H), s.hereArea(H)
        nodes = spawnNodes(s.questSpots(), uid0)
        org0 = s.areaObj(H, uid0)
        pos0 = la.getPos(org0) if org0 is not None else la.getPos(H.render)
        far = len(nodes)
        self.home[uid0], nodes = huntGround(nodes, (pos0[0], pos0[1]), self.home.get(uid0), s_fighter.myLevel(H))
        far -= len(nodes)
        st = {'hits': 0, 'skills': 0, 'tonics': 0, 'retreats': 0, 'stuck': 0, 'lost': 0, 'legs': 0, 'wskills': 0}
        kills, skip, tried = 0, {}, set()
        fighter, node, end = None, None, None
        empty, offT, restT, dangerT, vitae, vitaeT = 0, None, None, 0.0, 0, 0.0
        owned = self.ownedNow()
        kind, equipTried = weaponKind(owned, self.bad, self.hunts), set()     # this hunt's weapon (row 44)
        self.hunts += 1
        H.ev('LAND-HUNT', area=H.area(), nodes=len(nodes), far=far, home=self.home[uid0], hp=getattr(la, 'hp', None), maxHp=getattr(la, 'maxHp', None),
             lvl=s_fighter.myLevel(H), gold=g0, cave=self.inCave())
        H.ev('LAND-WEAPON', weapon=kind, owned=sorted(owned), bad=sorted(self.bad), hunt=self.hunts)
        try:
            while time.time() - t0 < HUNT_SECS:
                now = time.time()
                gs = _gs(la)
                if (getattr(la, 'hp', 1) or 0) <= 0 or gs in ('Death', 'Dying'):
                    end = 'ko'
                    break
                if gs not in ('LandRoam', 'Battle'):
                    offT = offT or now
                    if now - offT > OFF_STATE_SECS:
                        end = 'state'
                        break
                    yield 1.0
                    continue
                offT = None
                if s.hereArea(H) != uid0:
                    end = 'area'                  # a tunnel / door took it elsewhere: the camps here mean nothing now
                    break
                if now - vitaeT >= VITAE_EVERY:
                    vitae, vitaeT = vitaeLevel(H), now
                lvl = s_fighter.myLevel(H)
                over = foeOver(vitae)
                if fighter is not None:
                    if kind != 'Cutlass' and self.weaponSkill(fighter, kind):
                        st['wskills'] += 1
                        yield BEAT
                        continue
                    a = fighter.step()
                    st['tonics'] += a == 'tonic'
                    st['retreats'] += a == 'retreat'
                    if a in ('kill', 'lost', 'stuck'):
                        foe = fighter.foe
                        st['hits'] += fighter.hits
                        st['skills'] += fighter.skills
                        if a != 'kill' and kind != 'Cutlass' and fighter.hits == 0:
                            # a whole fight with this weapon and nothing landed: not this weapon today, the cutlass instead
                            self.bad.add(kind)
                            H.ev('LAND-WEAPON-BAD', weapon=kind, why='no hit in a whole fight (%s)' % a, foe=foe.doId,
                                 gs=_gs(la))
                            kind = weaponKind(owned, self.bad, 0)
                        fighter.close()
                        fighter = None
                        if a == 'kill':
                            kills += 1
                            empty = 0
                            H.ev('LAND-KILL', foe=foe.doId, n=kills, gold=goldNow(H) - g0, lvl=getattr(foe, 'level', None))
                        elif a == 'stuck':
                            st['stuck'] += 1
                            skip[foe.doId] = time.time() + SKIP_SECS
                            H.ev('LAND-FOE-STUCK', foe=foe.doId, la=H.P(la), area=H.area())
                        else:
                            st['lost'] += 1
                    yield BEAT
                    continue
                # between fights: a tonic when hurt, then recover before the next one
                hpf = hpFrac(getattr(la, 'hp', 0), getattr(la, 'maxHp', 0))
                if hpf < OUT_TONIC_HP:
                    if outTonic(hpf, tonicsLeft(H), tonicReady(H), 'LandRoam',
                                None if self.tonicT is None else now - self.tonicT):
                        self.drink()
                        st['tonics'] += 1
                        yield 0.5
                        continue
                    if tonicsLeft(H) == 0:
                        self.tonicLow(hpf)               # row 46: out of tonics and hurt: the brain / games skill are told
                if hpf < HUNT_MIN_HP:
                    restT = restT or now
                    if now - restT >= s_fighter.REST_MAX:
                        end = 'hurt'
                        break
                    H.ev('LAND-REST', hp=getattr(la, 'hp', None), frac=round(hpf, 2), secs=round(now - restT))
                    yield 2.0
                    continue
                restT = None
                rows, boys = s_fighter.foeRows(H), boyPoints(H)
                fid = pickTarget(rows, lvl, vitae, skip, now, boys)
                if fid is None:
                    hit = attackerRow(rows, lvl, over)
                    if hit is not None and hpf < 1.0:
                        H.ev('LAND-HIT-WHILE-SEEKING', foe=hit[0], weak=hit[1], myLvl=lvl, hp=getattr(la, 'hp', None))
                        if hit[1]:
                            fid = hit[0]
                        else:
                            hf = H.cr.doId2do.get(hit[0])
                            if hf is not None:
                                me, fp = la.getPos(H.render), hf.getPos(H.render)
                                to = s_fighter.retreatPoint((me[0], me[1], me[2]), (fp[0], fp[1], fp[2]), None, 60.0)
                                st['retreats'] += 1
                                H.ev('LAND-FLEE', foe=hit[0], to=[round(v, 1) for v in to])
                                yield from self.goTo(to, 'flee', 4.0)
                                node = None
                                continue
                if fid is not None:
                    foe = H.cr.doId2do.get(fid)
                    if foe is None:
                        yield BEAT
                        continue
                    node = None
                    d = next((r[1] for r in rows if r[0] == fid), 0.0)
                    if legFor(d, self.inCave()) != 'engage':
                        hp0 = getattr(la, 'hp', 0)

                        def look(foe=foe, hp0=hp0):
                            if foe.doId not in H.cr.doId2do or (getattr(foe, 'hp', 1) or 0) <= 0:
                                return 'gone'
                            return 'hit' if (getattr(la, 'hp', 0) or 0) < hp0 else None
                        p = foe.getPos(H.render)
                        r, why = yield from watched(self.goTo((p[0], p[1], p[2]), 'to-foe', s_fighter.REACH + 1.0, foe), look)
                        H.walk_cancel()
                        st['legs'] += 1
                        left = hdist2(la.getPos(H.render), foe.getPos(H.render)) if foe.doId in H.cr.doId2do else 0.0
                        if r == 'area':
                            continue
                        if r is None and why is None:
                            pass                       # a cave with no waypoints: Fighter walks it the straight way below
                        elif why is None and (not r) and left > d - 5.0:
                            skip[fid] = time.time() + SKIP_SECS      # no closer: leave this one for a while
                            H.ev('LAND-FOE-NO-WAY', foe=fid, d=round(d, 1), left=round(left, 1), area=H.area())
                            self.fileNoRoute(uid0, 'a foe')
                            continue
                        else:
                            continue                   # a leg done or cut: look again from where it stands
                    H.walk_cancel()
                    if kind in owned and kind not in equipTried and not self.holding(kind):
                        equipTried.add(kind)
                        if not (yield from self.equip(kind, owned)) and kind != 'Cutlass':
                            self.bad.add(kind)
                            H.ev('LAND-WEAPON-BAD', weapon=kind, why='would not draw', gs=_gs(la))
                            kind = weaponKind(owned, self.bad, 0)
                        continue                         # look again from where it stands (the foe may have moved)
                    me = la.getPos(H.render)
                    fighter = s_fighter.Fighter(H, foe, (me[0], me[1], me[2]))
                    continue
                # nothing to fight in view: walk to a spawn camp and look again
                bad = s_fighter.danger(rows, lvl, s_fighter.DANGER_R, over)
                if bad and node is not None and time.time() - dangerT > 5:
                    dangerT = time.time()
                    H.ev('LAND-FOE-DANGER', near=len(bad), myLvl=lvl, node=node[3])
                    tried.add(tuple(node[:3]))
                    node = None
                if node is None:
                    org = s.areaObj(H, uid0)
                    me = la.getPos(org) if org is not None else la.getPos(H.render)
                    clear = nodes if not boys else [
                        q for q in nodes if awayFrom(s._render_pt(H, q[:3], org) if org is not None else q, boys)]
                    n = s_fighter.spawnPick(clear, (me[0], me[1]), tried, lvl)
                    if n is None:
                        if not nodes:
                            end = 'no-spawn'
                            break
                        empty += 1
                        H.ev('LAND-SPAWN-ROUND-DONE', nodes=len(nodes), round=empty)
                        if empty >= SPAWN_ROUNDS:
                            end = 'no-foe'
                            break
                        tried.clear()
                        yield 5.0
                        continue
                    node = tuple(n) + (org,)
                    H.ev('LAND-SPAWN-PICK', node=n[3], tier=s_fighter.tier(n[3]), myLvl=lvl, spot=[round(v, 1) for v in n[:3]])
                p = s._render_pt(H, node[:3], node[4])
                hp0 = getattr(la, 'hp', 0)

                def lookNode(hp0=hp0):
                    if (getattr(la, 'hp', 0) or 0) < hp0:
                        return 'hit'
                    return 'foe' if pickTarget(s_fighter.foeRows(H), lvl, vitae, skip, time.time(), boyPoints(H)) is not None else None
                r, why = yield from watched(self.goTo((p[0], p[1], p[2]), 'to-spawn', 8.0), lookNode)
                H.walk_cancel()
                st['legs'] += 1
                if why is not None or r == 'area':
                    continue                      # something to fight (or hit): top of the loop looks
                if r is not True:
                    H.ev('LAND-SPAWN-UNREACHABLE', node=node[3], spot=[round(v, 1) for v in node[:3]], r=str(r), area=H.area())
                    if r is False:
                        self.fileNoRoute(uid0, 'a spawn camp')
                tried.add(tuple(node[:3]))
                node = None
                yield 1.0                          # stand a second at the camp: enemies spawn and come into view
        finally:
            if fighter is not None:
                st['hits'] += fighter.hits
                st['skills'] += fighter.skills
                fighter.close()
            H.walk_cancel()
        end = end or 'time'
        gold, secs = goldNow(H) - g0, round(time.time() - t0, 1)
        H.ev('LAND-HUNT-END', end=end, kills=kills, gold=gold, secs=secs, weapon=kind, **st)
        self.quiet('hunt', restAfter(end), 'hunt ended: %s' % end)
        if end not in ('ko', 'state') and getattr(la, 'isWeaponDrawn', False):
            yield from self.sheathe()                    # the weapon away: the skill page, shops and doors want LandRoam
        return {'duty': 'hunt', 'ok': True, 'end': end, 'kills': kills, 'gold': gold, 'secs': secs}

    # -- friends, guild, titles, hellos, teleport (rows 34-39): the game's own panels and calls, SpeedChat only
    def invite(self):
        """Generator: answer the friend / guild invitation panel on screen the way a player does: its OK button for a
        captain (Player1, Player2, Host's pirate, PBOT_CAPTAINS), its No button for anyone else. The panel must close within
        INVITE_SECS. A press that did nothing = one BOT bug and the duty quiet for INVITE_QUIET. -> {duty, ok, kind, avId, answer}.
        Lines: LAND-INVITE (kind, avId, name, answer, pressed, closed)."""
        H = self.PH
        got = inviteNow(self.H)
        if got is None:
            return {'duty': 'invite', 'ok': True, 'why': 'gone'}
        kind, p = got
        avId = getattr(p, 'avId', None)
        ans = inviteAnswer(avId, captains())
        pressed = press(p.bOk if ans == 'ok' else p.bNo)
        if pressed:
            yield ('upto', lambda: panelGone(p), INVITE_SECS, '%s invitation closed' % kind)
        closed = panelGone(p)
        H.ev('LAND-INVITE', kind=kind, avId=avId, avName=getattr(p, 'avName', None), answer=ans, pressed=pressed, closed=closed)
        ok = pressed and closed
        if not ok:
            self.quiet('invite', INVITE_QUIET, 'the %s panel did not close' % kind)
            self.fileBug('stuck', 'land-invite-%s-%s' % (kind, 'nopress' if not pressed else 'open'),
                         'the %s invitation from %s was %s, but its panel %s' % (
                             kind, avId, 'answered ' + ans if pressed else 'not pressable',
                             'stayed open for %d s' % INVITE_SECS if pressed else 'has no usable %s button' % ans.upper()))
        elif ans == 'ok':
            self.say('thanks')
        return {'duty': 'invite', 'ok': ok, 'kind': kind, 'avId': avId, 'answer': ans}

    def greet(self):
        """One SpeedChat hello to a boy standing close (a captain's pirate inside GREET_R ft), the same boy at most once per
        GREET_GAP s. Booked even when the SpeedChat cooldown held the line back, so the duty never repeats. Never typed chat."""
        near = boysNear(self.H)
        i = greetDue(near, self.greeted, time.time())
        if i is None:
            return {'duty': 'greet', 'ok': True, 'why': 'gone'}
        self.greeted[i] = time.time()
        sent = self.say('hi')
        self.H.ev('LAND-GREET', boy=i, sent=sent)
        return {'duty': 'greet', 'ok': True, 'boy': i, 'sent': sent}

    def titles(self):
        """Generator: the Titles page (the B key): put on the highest earned badge (titlePick), when none is on. Rank 0
        needs a magic word, so an unearned title is left alone (no magic word, ever). Lines: LAND-TITLES (rows),
        LAND-TITLES-PICK, LAND-TITLES-BADGE, LAND-TITLES-NONE. -> {duty, ok, badge}."""
        from pirates.pirate import TitleGlobals as TG
        H, la = self.PH, self.H.la
        gm = la.guiMgr
        tp = gm.titlesPage
        self.titlesT = time.time()
        if tp is None:
            return {'duty': 'titles', 'ok': True, 'why': 'no page'}
        self.titlesOpen = True
        try:
            if not gm.pageOpen(tp):
                gm.showTitlesPanel()
            yield 1
            panels = [p for p in (tp.titles or []) if getattr(p, 'titleId', None) == TG.LandPVPTitle
                      and hasattr(p, 'landToggle')]
            rows = [(i, getattr(p, 'rank', 0), bool(getattr(p, 'landActive', False))) for i, p in enumerate(panels)]
            H.ev('LAND-TITLES', rows=rows, badge=getattr(la, 'badge', None))
            k = titlePick(rows)
            if k is None:
                H.ev('LAND-TITLES-NONE', why='already on' if any(r[2] for r in rows) else 'no rank earned')
                return {'duty': 'titles', 'ok': True, 'badge': getattr(la, 'badge', None)}
            p = panels[k]
            want = (p.titleId, p.rank)
            H.ev('LAND-TITLES-PICK', title=p.titleId, rank=p.rank)
            p.landToggle()
            yield ('upto', lambda: tuple(getattr(la, 'badge', None) or ()) == want, 15, 'badge saved')
            ok = tuple(getattr(la, 'badge', None) or ()) == want
            H.ev('LAND-TITLES-BADGE', ok=ok, badge=getattr(la, 'badge', None), want=want)
            if not ok:
                self.quiet('titles', QUIET_BUG, 'badge not saved')
                self.fileBug('missing', 'land-titles-badge-not-saved',
                             'the Land PvP badge was pressed on the Titles page, the server did not save it (badge %s)'
                             % (getattr(la, 'badge', None),), tag='GAME')
            return {'duty': 'titles', 'ok': ok, 'badge': getattr(la, 'badge', None)}
        finally:
            self.closeTitlesPage()

    def guildMake(self):
        """Generator (opt-in, LAND_GUILD_CREATE=1): make a guild of its own and name it, through the guild page (Create
        Guild, the confirm window's OK, the rename box). Never invites anyone; a pirate already in a guild does nothing.
        Once per run. Lines: LAND-GUILD (state), LAND-GUILD-NAMED. -> {duty, ok, guildId}."""
        H, la = self.PH, self.H.la
        gm = la.guiMgr
        gp = gm.guildPage
        self.guildDone = True
        if (la.getGuildId() or 0) > 0:
            return {'duty': 'guild', 'ok': True, 'why': 'already in a guild', 'guildId': la.getGuildId()}
        H.ev('LAND-GUILD', step='create', gs=_gs(la))
        try:
            gm.socialPanel.show()
            gm.socialPanel.setPage(gp)
            yield 1
            gp.createGuild()                                   # the Create Guild button
            box = getattr(gp, 'confirmBox', None)
            ok = getattr(box, '_PiratesConfirm__handleOk', None) if box is not None else None
            if box is None:
                self.fileBug('missing', 'land-guild-no-confirm', 'Create Guild was pressed, no confirm window came')
                return {'duty': 'guild', 'ok': False, 'why': 'no confirm'}
            ok() if ok is not None else box.bOk['command']()   # the confirm window's OK
            yield ('upto', lambda: (la.getGuildId() or 0) > 0, 20, 'guild made')
            gid = la.getGuildId() or 0
            if gid <= 0:
                self.fileBug('missing', 'land-guild-not-made', 'OK was pressed on Create Guild, no guild after 20 s', tag='GAME')
                return {'duty': 'guild', 'ok': False, 'why': 'no guild'}
            if la.getGuildName() and not str(la.getGuildName()).startswith('Pirate Guild'):
                return {'duty': 'guild', 'ok': True, 'guildId': gid, 'why': 'named already'}
            name = 'Bot Crew %04d' % (int(time.time()) % 10000)
            gp.renameGuild()                                   # the name box
            yield 1
            gp.nameEntry.enterText(name)
            gp._typedAName()                                   # Enter in the name box
            yield ('upto', lambda: la.getGuildName() == name, 20, 'guild named')
            named = la.getGuildName() == name
            H.ev('LAND-GUILD-NAMED', ok=named, name=name, guildId=gid)
            return {'duty': 'guild', 'ok': named, 'guildId': gid}
        finally:
            try:
                gp.revertGui()
                gm.socialPanel.hide()
            except Exception:
                pass

    def toFriend(self, avId):
        """Generator (row 37; NOT scheduled in free play: pbots' crew code decides when a boy is worth a trip): the game's own
        teleport to a friend (the friend-list path, teleportMgr.queryAvatarForTeleport, as s_friendtele leg F). Only a captain,
        never Host's pirate, never one already within TELE_FAR ft. Waits for TeleportOut, then for LandRoam on an island.
        -> {duty, ok, why}. Lines: LAND-TELE-SKIP, LAND-TELE (secs, area)."""
        H, la, cr = self.PH, self.H.la, self.H.cr
        o = cr.doId2do.get(avId)
        dist = None
        if o is not None:
            try:
                a, b = o.getPos(self.H.render), la.getPos(self.H.render)
                dist = hdist2((a[0], a[1]), (b[0], b[1]))
            except Exception:
                dist = None
        ok, why = teleOk(avId, captains(), dist)
        if not ok:
            H.ev('LAND-TELE-SKIP', avId=avId, why=why)
            return {'duty': 'tele', 'ok': False, 'why': why}
        t0 = time.time()
        cr.teleportMgr.queryAvatarForTeleport(avId)
        yield ('upto', lambda: _gs(la) == 'TeleportOut', 30, 'teleport out')
        out = _gs(la) == 'TeleportOut'
        if out:
            yield ('upto', lambda: _gs(la) == 'LandRoam' and H.area() is not None, 120, 'landed')
        landed = _gs(la) == 'LandRoam' and H.area() is not None
        H.ev('LAND-TELE', avId=avId, out=out, landed=landed, secs=round(time.time() - t0, 1), area=H.area())
        return {'duty': 'tele', 'ok': out and landed, 'why': 'ok' if out and landed else
                ('never left' if not out else 'did not land')}

    def jail(self):
        """Generator: out of the cell like a player (s_story.jail: kick our cell door, walk out, leave by the jail's door).
        -> {duty, ok, secs}. Lines: LAND-JAIL, LAND-JAIL-STEP, s_story's JAIL-*, LAND-JAIL-OUT."""
        import s_story as s      # live only: s_story reads the quest ladder from the game at import
        H, la = self.PH, self.H.la
        t0 = time.time()
        H.ev('LAND-JAIL', area=H.area(), cell=getattr(la, 'jailCellIndex', None), gs=_gs(la), hp=getattr(la, 'hp', None),
             vitae=vitaeLevel(H), la=H.P(la))
        st, last, n = {}, None, 0
        while time.time() - t0 < JAIL_LIMIT:
            jr = s.jail(H, st)
            if jr is None:
                if not jailedNow(H):
                    break
                yield 1           # jail() gave up (its own STALL); JAIL_LIMIT ends it
                continue
            if jr != last:
                n += 1
                H.ev('LAND-JAIL-STEP', a=jr, n=n, gs=_gs(la), la=H.P(la))
                last = jr
            g = st.pop('go', None)
            if g is not None and _gs(la) == 'LandRoam':
                obj, arrive, face, ref, tag = g
                yield from s.go(H, obj, arrive, face, ref, tag)
            else:
                yield 0.5
        yield ('upto', lambda: not jailedNow(H) and H.area() is not None and _gs(la) == 'LandRoam', 30, 'on the island after jail')
        ok = not jailedNow(H) and H.area() is not None
        secs = round(time.time() - t0, 1)
        H.ev('LAND-JAIL-OUT', ok=ok, secs=secs, gs=_gs(la), area=H.area(), vitae=vitaeLevel(H))
        if not ok:
            where = (H.area() or ('?',))[0]      # the area's class: a stable key, so the same stuck only bumps a count
            self.fileBug('stuck', 'land-stuck-jail-%s' % slug(where),
                         'the pirate could not get out of its jail cell in %d s (last step %s, area %s)' % (JAIL_LIMIT, last, where))
        return {'duty': 'jail', 'ok': ok, 'secs': secs}


class _Solo:
    """A stand-in brain for run(H): files bugs straight through bugfile (as the games skill does)."""

    def __init__(self, H):
        self.H = H

    def captain(self):
        return None

    def bug(self, kind, key, tag, what, tb=''):
        import bugfile
        la = self.H.la
        sig, path, count = bugfile.report(kind, key, tag, what, where=str(self.H.area()),
                                          pirate='%s %s' % (getattr(la, 'name', '') or '?', la.doId),
                                          source='pbot land', tb=tb)
        self.H.ev('BUG', sig=sig, kind=kind, tag=tag, what=what[:160], count=count)


def run(H):
    """Step script: LAND for LAND_SECS. Passes when every duty that came up was done and no BOT bug was filed."""
    la = H.la
    if la.doId in NEVER:
        H.ev('FAIL', why="refusing: pirate %s is Host's, his ship's or a boy's" % la.doId)
        return
    secs = float(os.environ.get('LAND_SECS', '900'))
    yield ('upto', lambda: _gs(la) in ('LandRoam', 'Battle'), 90, 'LandRoam')
    sk = Land(_Solo(H))
    t0, done, failed = time.time(), 0, 0
    H.ev('LAND', secs=secs, state=sk.state())
    while time.time() - t0 < secs:
        w = sk.want()
        if w is None:
            yield 2
            continue
        H.ev('LAND-WANT', score=w[0], why=w[1])
        r = yield from sk.flow()
        if r and r.get('ok'):
            done += 1
        else:
            failed += 1
        yield 1
    H.ev('PASS' if failed == 0 else 'FAIL', done=done, failed=failed, why='land duties')
