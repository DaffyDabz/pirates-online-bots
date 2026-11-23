"""FIGHTER (pir-bot, 11-17, job 6): fight on land like a competent player, for s_landfight (and anyone else).

Why: LAND1 (11-17 18:22) walked 30 spawn nodes in 480 s and never picked one enemy (no FOE-PICK line), then was
knocked out at the Mid Navy / Navy - Sergeant camps on the hill and woke in jail. Two causes:
  1. the enemy filter asked each object for getAvatarType(); on the client only the server side (…AI.py) and bosses
     have that method, so every enemy was thrown away. The client keeps it as the attribute .avatarType, and
     .isBattleable() tells an enemy from a townsperson (DistributedNPCTownfolk says no).
  2. with no enemy "seen", it walked to the nearest spawn node of ANY kind, so it went up into the strong camps
     where the enemies jumped him while he walked on.

What a competent player does, and what this does (each decision is one event line):
  pick   a weak enemy: alive, battleable, at most his level + LVL_OVER, in view, not standing in a crowd; the
         lowest level first, then the nearest (FOE-PICK, with the reason the others were left: FOE-SKIP).
         Spawn nodes are walked weakest camp first (Noob, then Low, Mid only from level 6, the ranked camps
         -- Sergeant, Veteran, ... -- from level 11) (SPAWN-PICK).
  attack the weapon drawn the player's way (LocalPirate.toggleWeapon -> Battle state), then the left click
         (CombatTray.actionDown/actionUp -> processInput -> the combo chain Hack, Slash, Cleave, Flourish, Stab as
         far as he has them), and his best ready skill from the skill tray (CombatTray.triggerSkillTraySkill: Blade
         Storm, then Brawl, then Sweep, when he has the skill, it is recharged and he has the mojo) (ATTACK, SKILL).
         If 4 clicks in reach are all refused by the tray, it falls back to the old direct swing (ATTACK-FALLBACK).
  tonic  under TONIC_HP of his health, the T key's call (CombatTray.trySkill(UseItem, best tonic)) when he has a
         tonic and it is recharged (TONIC, TONIC-REFUSED).
  back   under RUN_HP with no tonic ready: walk away (back to where he stood before the fight, or straight away from
  off    the enemy), rest until BACK_HP, drinking a tonic as soon as one is ready (RETREAT, REST), then come back to
         the same enemy if it is still alive, else pick again (RETURN).
  done   enemy hp 0 or it leaves the client after our hits (KILL); the caller then waits for the gold (LOOT-SHOWN).

Pure functions at the top (tested offline in unit_job6.py on the LAND1 positions); Fighter below runs in the game."""
import math
import time

VIEW = 150.0          # ft: an enemy further than this is not "in view"
LVL_OVER = 1          # fight enemies up to his level + this
CROWD_R = 25.0        # ft: other live enemies this close to a candidate make it a crowd
CROWD_MAX = 1         # at most this many others near it (a lone one, or one with one friend)
DANGER_R = 60.0       # ft: a too-strong enemy this close while seeking = walk on to another camp
REACH = 3.5           # ft: cutlass reach (walker.engage)
TONIC_HP = 0.45       # health fraction: drink below this
RUN_HP = 0.30         # health fraction: back off below this when no tonic is ready
BACK_HP = 0.75        # health fraction: come back at or above this
RUN_DIST = 45.0       # ft: how far to back off when there is no earlier safe spot
REST_MAX = 60.0       # s: longest rest before going back anyway (patch 0118+ regenerates health)
CLICK_GAP = 0.6       # s between left clicks (the combo needs the last swing to land first)
FALLBACK_AFTER = 4    # refused clicks in reach before the direct swing is used

# camp names in quest_spots.json 'Spawn Node' objects (Port Royal: Noob Navy 22, Mid Navy 7, Noob Skeleton 4,
# Low Navy 3, Navy - Sergeant 3, Navy - Veteran 3, Low EITC 2, Mid EITC 1)
_TIERS = (('noob', 0), ('low', 1), ('mid', 2))
_RANKS = ('sergeant', 'veteran', 'lieutenant', 'captain', 'officer', 'elite', 'boss', 'high', 'marine', 'guard')

# cutlass skill-tray skills, best first (InventoryType ids; Taunt 12109 is left out: it only pulls more enemies)
SKILLS = ((12110, 'Blade Storm'), (12108, 'Brawl'), (12107, 'Sweep'))
USE_ITEM = None       # InventoryType.UseItem, filled in at Fighter start (the game's module is not here offline)


def tier(name):
    """Pure: camp name -> 0 Noob, 1 Low, 2 Mid, 3 a ranked or unknown camp."""
    n = (name or '').lower()
    for k, t in _TIERS:
        if n.startswith(k) or (' %s' % k) in n:
            return t
    return 3


def maxTier(lvl):
    """Pure: the strongest camp tier a pirate of this level walks into."""
    lvl = lvl or 1
    return 1 if lvl <= 5 else (2 if lvl <= 10 else 3)


def spawnPick(nodes, me, tried, lvl):
    """Pure: nodes = (x, y, z, name) in the area frame. -> the node to walk to next: not tried yet, a camp tier he can
    take, weakest tier first, then the nearest. None when every such node was tried."""
    top = maxTier(lvl)
    left = [n for n in nodes if tuple(n[:3]) not in tried and tier(n[3]) <= top]
    if not left:
        return None
    return min(left, key=lambda n: (tier(n[3]), (n[0] - me[0]) ** 2 + (n[1] - me[1]) ** 2))


def _d2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def pickFoe(rows, lvl, view=VIEW, maxlvl=99, over=LVL_OVER):
    """Pure: rows = (doId, dist, hp, level, (x, y)) for every live battleable enemy. -> (picked, skipped):
    picked = doIds worth fighting, best first (no crowd, lowest level, nearest); skipped = {doId: why}."""
    lvl = lvl or 1
    cap = min(maxlvl, lvl + over)
    alive = [r for r in rows if (r[2] or 0) > 0]
    keep, skip = [], {}
    for r in alive:
        if r[1] > view:
            skip[r[0]] = 'far'
            continue
        if (r[3] or 0) > cap:
            skip[r[0]] = 'level %s > %s' % (r[3], cap)
            continue
        crowd = sum(1 for o in alive if o[0] != r[0] and _d2(o[4], r[4]) <= CROWD_R)
        if crowd > CROWD_MAX:
            skip[r[0]] = 'crowd %d' % crowd
            continue
        keep.append((r[3] or 0, r[1], r[0]))
    if not keep:                       # every weak one is in a crowd: take the least crowded weak one anyway
        weak = [r for r in alive if r[1] <= view and (r[3] or 0) <= cap]
        if weak:
            weak.sort(key=lambda r: (sum(1 for o in alive if o[0] != r[0] and _d2(o[4], r[4]) <= CROWD_R),
                                     r[3] or 0, r[1]))
            for r in weak:
                skip.pop(r[0], None)
            return [r[0] for r in weak], skip
    keep.sort()
    return [k[2] for k in keep], skip


def danger(rows, lvl, near=DANGER_R, over=LVL_OVER):
    """Pure: the doIds of live enemies above his level + over within near ft (walk on, do not fight here)."""
    cap = (lvl or 1) + over
    return [r[0] for r in rows if (r[2] or 0) > 0 and (r[3] or 0) > cap and r[1] <= near]


def hpFrac(hp, mx):
    return max(0.0, min(1.0, float(hp or 0) / mx)) if mx else 1.0


def decide(hpf, tonics, tonicReady, resting):
    """Pure: what to do this beat. -> 'tonic' / 'retreat' / 'rest' / 'return' / 'fight'."""
    if resting:
        if hpf >= BACK_HP:
            return 'return'
        return 'tonic' if (tonics > 0 and tonicReady) else 'rest'
    if hpf < TONIC_HP and tonics > 0 and tonicReady:
        return 'tonic'
    if hpf < RUN_HP:
        return 'retreat'
    return 'fight'


def retreatPoint(me, foe, safe=None, dist=RUN_DIST):
    """Pure: where to back off to (render frame x, y, z). The spot he came from when it is further from the enemy than
    he is now (by 10 ft or more); else dist ft straight away from the enemy."""
    if safe is not None and _d2(safe, foe) >= _d2(me, foe) + 10.0:
        return tuple(safe)
    dx, dy = me[0] - foe[0], me[1] - foe[1]
    n = math.hypot(dx, dy)
    if n < 0.1:
        dx, dy, n = 1.0, 0.0, 1.0
    return (me[0] + dx / n * dist, me[1] + dy / n * dist, me[2])


def bestSkill(ranks, recharge, mojo, costs):
    """Pure: ranks {skillId: inventory stack quantity} (the game's 'has it' test is quantity > 1), recharge {skillId:
    secs left or None}, mojo now, costs {skillId: mojo cost >= 0}. -> the best skill ready to use, or None."""
    for sid, _ in SKILLS:
        if (ranks.get(sid) or 0) <= 1:
            continue
        if (recharge.get(sid) or 0) > 0:
            continue
        if (costs.get(sid) or 0) > (mojo or 0):
            continue
        return sid
    return None


# ---------------------------------------------------------------------------------------------- live (in the game)
def isEnemy(H, o):
    """A live enemy the pirate can fight: battleable, has an avatar type, not a player pirate, not a townsperson."""
    if o is H.la or not hasattr(o, 'isBattleable'):
        return False
    n = type(o).__name__
    if 'PlayerPirate' in n or 'LocalPirate' in n or 'Townfolk' in n:
        return False
    try:
        return bool(o.isBattleable()) and getattr(o, 'avatarType', None) is not None
    except Exception:
        return False


def foeRows(H):
    lp = H.la.getPos(H.render)
    rows = []
    for o in list(H.cr.doId2do.values()):
        if not isEnemy(H, o):
            continue
        try:
            p = o.getPos(H.render)
            lvl = o.getLevel() if hasattr(o, 'getLevel') else getattr(o, 'level', 0)
            rows.append((o.doId, (p - lp).length(), getattr(o, 'hp', 0), lvl or 0, (p[0], p[1])))
        except Exception:
            continue
    return rows


def myLevel(H):
    try:
        return H.la.getLevel() or 1
    except Exception:
        return 1


class Fighter:
    """One enemy at a time. step() is called every beat (0.25 s) by the caller's loop and returns a short word:
    'fight' / 'walk' / 'tonic' / 'retreat' / 'rest' / 'return' / 'kill' / 'lost' (enemy lost, pick again) / 'stuck'."""

    def __init__(self, H, foe, safe):
        from pirates.uberdog.UberDogGlobals import InventoryType
        global USE_ITEM
        USE_ITEM = InventoryType.UseItem
        self.H, self.la, self.foe = H, H.la, foe
        self.safe = tuple(safe) if safe is not None else None     # render (x, y, z) he stood at before the fight
        self.hits, self.refused, self.clicks, self.skills = 0, 0, 0, 0
        self.resting, self.restT0, self.point, self.lastClick, self.down = False, None, None, 0.0, False
        self.tray = getattr(getattr(self.la, 'guiMgr', None), 'combatTray', None)
        self.tries = []                    # (skillId, ammoId, result) of every trySkill the tray ran since start
        self._orig, self._had = None, False
        if self.tray is not None:
            self._had = 'trySkill' in getattr(self.tray, '__dict__', {})   # already wrapped by someone else
            self._orig = self.tray.trySkill
            tries = self.tries

            def trySkill(skillId, ammoSkillId, combo=0, charge=0, _o=self._orig):
                r = _o(skillId, ammoSkillId, combo, charge)
                tries.append((skillId, ammoSkillId, r))
                return r
            self.tray.trySkill = trySkill

    def close(self):
        if self.tray is not None and self._orig is not None:
            if self._had:
                self.tray.trySkill = self._orig
            else:
                self.tray.__dict__.pop('trySkill', None)      # back to the class's own method
            self._orig = None
        if self.down and self.tray is not None:
            try:
                self.tray.actionUp()
            except Exception:
                pass
            self.down = False

    # -- what he has
    def hp(self):
        la = self.la
        return hpFrac(getattr(la, 'hp', 0), getattr(la, 'maxHp', 0) or (la.getMaxHp() if hasattr(la, 'getMaxHp') else 0))

    def tonics(self):
        inv = self.la.getInventory()
        try:
            return sum(v for v in inv.getTonics().values() if v) if inv else 0
        except Exception:
            return 0

    def ready(self, sid):
        try:
            t = self.la.skillDiary.getTimeRemaining(sid)
            return t is None or t <= 0
        except Exception:
            return True

    def skillState(self):
        from pirates.battle import WeaponGlobals
        inv = self.la.getInventory()
        ranks, rech, costs = {}, {}, {}
        for sid, _ in SKILLS:
            try:
                ranks[sid] = inv.getStackQuantity(sid) if inv else 0
                rech[sid] = self.la.skillDiary.getTimeRemaining(sid)
                costs[sid] = -1 * WeaponGlobals.getMojoCost(sid)
            except Exception:
                ranks[sid] = 0
        return ranks, rech, costs

    # -- player actions
    def drawWeapon(self):
        """The player's draw (weapon wheel / Ctrl): LocalPirate.toggleWeapon puts him in the Battle state."""
        la = self.la
        if getattr(la, 'isWeaponDrawn', False) and la.getGameState() == 'Battle':
            return
        if time.time() - getattr(self, '_drawT', 0) < 2.0:      # the state change takes a moment; ask once per 2 s
            return
        self._drawT = time.time()
        if getattr(la, 'isWeaponDrawn', False):
            # drawn but not in Battle: toggleWeapon would SHEATHE it (its last branch), so only change the state
            la.b_setGameState('Battle')
            self.H.ev('WEAPON-DRAWN', weapon=getattr(la, 'currentWeaponId', None), how='state only', gs=la.getGameState())
            return
        from pirates.uberdog.UberDogGlobals import InventoryType
        from pirates.battle import WeaponGlobals
        wid = getattr(la, 'currentWeaponId', 0) or 0
        if not wid or WeaponGlobals.getWeaponCategory(wid) != WeaponGlobals.COMBAT:
            wid = InventoryType.CutlassWeaponL1
        try:
            la.toggleWeapon(wid)
            self.H.ev('WEAPON-DRAWN', weapon=wid, gs=la.getGameState())
        except Exception as e:
            self.H.drawSword()
            self.H.ev('WEAPON-DRAWN', weapon=wid, how='server request (toggleWeapon failed: %s)' % e)

    def tonic(self):
        tid = None
        tb = getattr(self.tray, 'tonicButton', None) if self.tray is not None else None
        try:
            tid = tb.getBestTonic() if tb is not None else None
        except Exception:
            tid = None
        if tid is None:
            inv = self.la.getInventory()
            have = sorted(k for k, v in (inv.getTonics().items() if inv else []) if v)
            tid = have[0] if have else None
        n0, hp0 = len(self.tries), getattr(self.la, 'hp', None)
        ok = 0
        if tid is not None and self.tray is not None:
            ok = self.tray.trySkill(USE_ITEM, tid, 0)
        if ok:
            self.H.ev('TONIC', tonic=tid, hp=hp0, maxHp=getattr(self.la, 'maxHp', None), left=self.tonics() - 1)
        else:
            self.H.ev('TONIC-REFUSED', tonic=tid, hp=hp0, gs=self.la.getGameState(), tried=len(self.tries) - n0)
        return ok

    def click(self):
        """One left click: press now, release on the next beat (CombatTray.actionDown / actionUp, like the mouse)."""
        if self.down:
            self.tray.actionUp()
            self.down = False
            return
        if time.time() - self.lastClick < CLICK_GAP:
            return
        n0 = len(self.tries)
        self.tray.actionDown()
        self.down, self.lastClick = True, time.time()
        self.clicks += 1
        used = [t for t in self.tries[n0:] if t[2]]
        if used:
            self.hits += 1
            self.refused = 0
            self.H.ev('ATTACK', foe=self.foe.doId, skill=used[0][0], chain=getattr(self.tray, 'combatChainLvl', None),
                      foeHp=getattr(self.foe, 'hp', None), myHp=getattr(self.la, 'hp', None), n=self.hits)
        else:
            self.refused += 1

    def attack(self):
        ranks, rech, costs = self.skillState()
        sid = bestSkill(ranks, rech, getattr(self.la, 'mojo', 0), costs)
        if sid is not None and self.tray is not None and not self.down:
            n0 = len(self.tries)
            try:
                self.tray.triggerSkillTraySkill(sid)
            except Exception:
                pass
            if any(t[2] for t in self.tries[n0:]):
                self.skills += 1
                self.hits += 1
                self.H.ev('SKILL', foe=self.foe.doId, skill=sid, skillName=dict(SKILLS)[sid], rank=ranks.get(sid),
                          foeHp=getattr(self.foe, 'hp', None), mojo=getattr(self.la, 'mojo', None))
                return
        if self.tray is None or self.refused >= FALLBACK_AFTER:
            if self.refused == FALLBACK_AFTER:
                self.H.ev('ATTACK-FALLBACK', foe=self.foe.doId, why='the tray refused %d clicks' % self.refused,
                          gs=self.la.getGameState(), tray=self.tray is not None,
                          lastTries=[list(t) for t in self.tries[-4:]])
                self.refused += 1
            if time.time() - self.lastClick >= CLICK_GAP and self.H._swing(self.foe.doId):
                self.lastClick = time.time()
                self.hits += 1
            return
        self.click()

    # -- one beat
    def step(self):
        H, la, foe = self.H, self.la, self.foe
        if foe.doId not in H.cr.doId2do or (getattr(foe, 'hp', 0) or 0) <= 0:
            return 'kill' if self.hits else 'lost'
        hpf = self.hp()
        what = decide(hpf, self.tonics(), self.ready(USE_ITEM), self.resting)
        if what == 'tonic':
            if self.tonic():
                return 'tonic'
            what = 'rest' if self.resting else ('retreat' if hpf < RUN_HP else 'fight')
        if what == 'retreat':
            me, fp = la.getPos(H.render), foe.getPos(H.render)
            self.point = retreatPoint((me[0], me[1], me[2]), (fp[0], fp[1], fp[2]), self.safe)
            self.resting, self.restT0 = True, time.time()
            if self.down:
                self.tray.actionUp()
                self.down = False
            H.ev('RETREAT', foe=foe.doId, hp=getattr(la, 'hp', None), frac=round(hpf, 2), tonics=self.tonics(),
                 to=[round(v, 1) for v in self.point], usedSafe=self.point == self.safe)
            return 'retreat'
        if what == 'rest':
            r = H.walk_poll(self.point, arrive=4.0, face=False, tag='retreat')
            if r is True and int(time.time() - self.restT0) % 10 == 0:
                H.ev('REST', hp=getattr(la, 'hp', None), frac=round(hpf, 2), secs=round(time.time() - self.restT0))
            if time.time() - self.restT0 < REST_MAX:
                return 'rest'
            what = 'return'
        if what == 'return':
            self.resting = False
            H.ev('RETURN', foe=foe.doId, hp=getattr(la, 'hp', None), frac=round(hpf, 2),
                 rested=round(time.time() - self.restT0) if self.restT0 else 0)
            return 'return'
        self.drawWeapon()
        r = H.walk_poll(foe, arrive=REACH, face=True, tag='engage')
        if r is None:
            return 'stuck'
        if r is False:
            return 'walk'
        self.attack()
        return 'fight'
