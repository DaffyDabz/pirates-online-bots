"""XPGRANT (pir-bot job 34, 11-19): lift a TEST pirate to a level, so the level-12 undead quests can be proven.

The story bot skips undead kill quests (STORY-TOO-WEAK) while the enemies are more than 3 levels above the pirate.
A fresh test pirate is level 1-5, so those quests never get proven. This step uses the server's admin magic word
`level <repType> <level>` (MagicWords, CATEGORY_SYSTEM_ADMIN: sets the invoker's reputation in that type to the
total needed for that level) on the bot's own pirate.
- Only raises: a rep already at or above XP_LEVEL is left alone (XP-SKIP); the word would LOWER it otherwise.
- Never on Host's pirate 100000170: refused before anything else, and the word only ever acts on the invoker.
- XP-GRANT before and after each word, PASS when every asked rep reads >= XP_LEVEL.
env: XP_LEVEL (12), XP_REPS (overall,cutlass,pistol; also dagger, grenade, doll, wand, sailing, cannon)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get('PROOF_SCRIPT') or globals().get('__file__') or sys.argv[0])))

LEVEL = int(os.environ.get('XP_LEVEL', '12'))
REPS = [r.strip() for r in os.environ.get('XP_REPS', 'overall,cutlass,pistol').lower().split(',') if r.strip()]
HOST_AV = 100000170
REP_NAME = {'overall': 'OverallRep', 'cutlass': 'CutlassRep', 'pistol': 'PistolRep', 'dagger': 'DaggerRep',
            'grenade': 'GrenadeRep', 'doll': 'DollRep', 'wand': 'WandRep', 'sailing': 'SailingRep',
            'cannon': 'CannonRep'}
REP_ID = {'overall': 13700, 'cutlass': 13703, 'pistol': 13704, 'dagger': 13706, 'sailing': 13712}   # if no game


# ------------------------------------------------------------------------------------------------ pure
def levelsToGrant(cur, target):
    """cur = {rep: level now}. -> [rep, ...] whose level is below target (only those get the word)."""
    return [r for r in cur if cur[r] is not None and cur[r] < target]


def judgeLevels(after, target):
    """after = {rep: level}. -> (ok, why)."""
    low = {r: l for r, l in after.items() if l is None or l < target}
    if low:
        return False, 'below %d: %s' % (target, ', '.join('%s %s' % kv for kv in sorted(low.items())))
    return True, 'all %d rep(s) at %d+' % (len(after), target)


def refuse(avId):
    """-> a reason when the step must not run on this pirate, else None."""
    if avId == HOST_AV:
        return 'XPGRANT never runs on Host\'s pirate %d' % HOST_AV
    return None


# ------------------------------------------------------------------------------------------------ in the game
def repIds(reps=None):
    reps = reps or REPS
    try:
        from pirates.uberdog.UberDogGlobals import InventoryType
        return {r: getattr(InventoryType, REP_NAME[r]) for r in reps if r in REP_NAME}
    except Exception:
        return {r: REP_ID[r] for r in reps if r in REP_ID}


def levelOf(H, repId):
    inv = H.la.getInventory()
    if inv is None:
        return None
    from pirates.reputation import ReputationGlobals
    return ReputationGlobals.getLevelFromTotalReputation(repId, inv.getReputation(repId))[0]


def grant(H, target=None, reps=None):
    """Generator: raise the asked reps to target. -> (ok, why, {rep: level after})."""
    target = target or LEVEL
    why = refuse(H.la.doId)
    if why:
        H.ev('XP-REFUSE', why=why)
        return False, why, {}
    ids = repIds(reps)
    cur = {r: levelOf(H, i) for r, i in ids.items()}
    H.ev('XP-BEFORE', me=H.la.doId, target=target, levels=cur)
    todo = levelsToGrant(cur, target)
    for r in ids:
        if r not in todo:
            H.ev('XP-SKIP', rep=r, level=cur[r], target=target, why='already there' if cur[r] is not None else 'no level')
    for r in todo:
        word = 'level %d %d' % (ids[r], target)
        H.ev('XP-GRANT', rep=r, word=word, before=cur[r], target=target)
        H.mw(word)
        yield ('until', lambda i=ids[r]: (levelOf(H, i) or 0) >= target, 15, 'level %s' % r)
        H.ev('XP-GRANT', rep=r, after=levelOf(H, ids[r]), target=target)
    after = {r: levelOf(H, i) for r, i in ids.items()}
    ok, why = judgeLevels(after, target)
    H.ev('XP-AFTER', ok=ok, why=why, levels=after)
    return ok, why, after


def run(H):
    H.ev('XPGRANT-START', me=H.la.doId, level=LEVEL, reps=REPS)
    if refuse(H.la.doId):
        H.ev('FAIL', why=refuse(H.la.doId)); return
    yield ('until', lambda: H.la.getInventory() is not None, 30, 'inventory')
    ok, why, after = yield from grant(H)
    H.ev('PASS' if ok else 'FAIL', why=why, levels=after)
