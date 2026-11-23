"""SKILL (pir-bot, 11-17, job 3): spend one skill point, like a player, on the skill page.

The player's path: open the skill page (the 'guiMgrToggleLevels' key event, the same as the Skills key / button:
GuiManager.showSkillPage), pick the weapon's tab (SkillPage.update(rep, fromUser=1), what clicking the tab does),
press the skill's + (SkillPage.addPoint(skillId), which sends spendSkillPoint). The server checks there is a point
to spend and that the skill is below 6, raises the skill, takes the point and answers spentSkillPoint.

No point to spend? One 'level <rep> <level+1>' magic word (MW-LEVEL, setup only, never in the middle of the step):
a level up gives one point of that weapon (RepChart level-up skills). SKILL_LEVELUP=0 turns that off (then FAIL).

Which skill: the first of SKILL_ORDER (default CutlassHack, CutlassSlash, CutlassCleave, ...) that the pirate has
learned (1..5 points in it) and whose combo order allows it (the client refuses Slash/Cleave/... until the skill
before it has 2+ points).

Lines: SKILL-START (unspent, the skill amounts), MW-LEVEL, STAGE step=skill what=has-point / page-open / tab /
pressed / point-spent / page-closed, SKILL-SPENT (the server's answer), SKILL-END, PASS / FAIL.
PASS = the skill went up by one AND the unspent points went down by one, within 20 s of the press.
env: SKILL_REP (CutlassRep), SKILL_ORDER (comma list of InventoryType names), SKILL_LEVELUP (1)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ['PROOF_SCRIPT'])))
import s_lanes   # noqa: E402

REP = os.environ.get('SKILL_REP', 'CutlassRep')
ORDER = [s for s in os.environ.get('SKILL_ORDER', 'CutlassHack,CutlassSlash,CutlassCleave,CutlassFlourish,'
                                   'CutlassStab,CutlassSweep,CutlassParry,CutlassBrawl,CutlassTaunt,'
                                   'CutlassBladestorm').split(',') if s]
LEVELUP = os.environ.get('SKILL_LEVELUP', '1') == '1'
UNSPENT = {'CutlassRep': 'UnspentCutlass', 'DaggerRep': 'UnspentDagger', 'PistolRep': 'UnspentPistol',
           'GrenadeRep': 'UnspentGrenade', 'DollRep': 'UnspentDoll', 'WandRep': 'UnspentWand',
           'CannonRep': 'UnspentCannon', 'SailingRep': 'UnspentSailing'}
COMBO = ('CutlassSlash', 'CutlassCleave', 'CutlassFlourish', 'CutlassStab', 'DaggerSwipe', 'DaggerGouge',
         'DaggerEviscerate')


def pickSkill(order, qty, ids, combo=COMBO):
    """Pure: order = skill names, qty = {name: points}, ids = {name: InventoryType id}. -> the first name the skill
    page's + would take: learned (1..5 points) and, for a combo skill, the skill before it (id - 1) at 2+ points."""
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


def run(H):
    from pirates.uberdog.UberDogGlobals import InventoryType
    from pirates.reputation import ReputationGlobals
    la = H.la
    inv = la.getInventory()
    rep = getattr(InventoryType, REP)
    un = getattr(InventoryType, UNSPENT[REP])
    ids = {n: getattr(InventoryType, n) for n in ORDER if hasattr(InventoryType, n)}

    def amounts():
        return {n: inv.getStackQuantity(i) for n, i in ids.items()}

    def level():
        return ReputationGlobals.getLevelFromTotalReputation(rep, inv.getAccumulator(rep))[0]

    H.ev('SKILL-START', rep=REP, unspent=inv.getStackQuantity(un), level=level(), skills=amounts(),
         tutorial=getattr(la.style, 'tutorial', None), gs=la.getGameState())
    yield ('until', lambda: la.getGameState() == 'LandRoam', 60, 'LandRoam')
    if inv.getStackQuantity(un) < 1:
        if not LEVELUP:
            H.ev('FAIL', why='no %s point to spend and SKILL_LEVELUP=0' % REP); return
        lv = level()
        H.ev('MW-LEVEL', why='the test pirate has no %s point; a level up gives one' % REP, frm=lv, to=lv + 1)
        H.mw('level %d %d' % (rep, lv + 1))
        yield ('until', lambda: inv.getStackQuantity(un) >= 1, 20, 'level-up point')
        if inv.getStackQuantity(un) < 1:
            H.ev('FAIL', why='the level magic word gave no point', level=level()); return
    u0 = inv.getStackQuantity(un)
    s_lanes.stage(H, 'skill', 'has-point', unspent=u0)
    name = pickSkill(ORDER, amounts(), ids)
    if name is None:
        H.ev('FAIL', why='no learned skill can take a point', skills=amounts()); return
    sid = ids[name]
    q0 = inv.getStackQuantity(sid)

    gm = la.guiMgr
    page = gm.skillPage
    if not gm.pageOpen(page):
        messenger.send('guiMgrToggleLevels')
        yield ('until', lambda: gm.pageOpen(page), 10, 'skill page')
    if not gm.pageOpen(page):
        H.ev('FAIL', why='the skill page did not open'); return
    s_lanes.stage(H, 'skill', 'page-open')
    page.update(rep, fromUser=1)
    yield 1
    s_lanes.stage(H, 'skill', 'tab', rep=REP, current=getattr(page, 'currentRep', None))

    got = []
    orig = la.spentSkillPoint

    def spent(category, *a):
        got.append(category)
        H.ev('SKILL-SPENT', skill=category, qty=inv.getStackQuantity(category), unspent=inv.getStackQuantity(un))
        return orig(category, *a)
    la.spentSkillPoint = spent
    try:
        s_lanes.stage(H, 'skill', 'pressed', skill=name, id=sid, qty=q0)
        page.addPoint(sid)
        yield ('until', lambda: inv.getStackQuantity(sid) > q0 and inv.getStackQuantity(un) < u0, 20, 'point spent')
    finally:
        del la.spentSkillPoint     # back to the class method
    q1, u1 = inv.getStackQuantity(sid), inv.getStackQuantity(un)
    ok = q1 == q0 + 1 and u1 == u0 - 1
    if ok:
        s_lanes.stage(H, 'skill', 'point-spent', skill=name, qty=q1, unspent=u1)
    if gm.pageOpen(page):
        messenger.send('guiMgrToggleLevels')
        yield 1
        s_lanes.stage(H, 'skill', 'page-closed', open=gm.pageOpen(page))
    H.ev('SKILL-END', skill=name, qtyBefore=q0, qtyAfter=q1, unspentBefore=u0, unspentAfter=u1, answer=got)
    if not ok:
        H.ev('FAIL', why='the press did not spend a point (%s %d->%d, unspent %d->%d)' % (name, q0, q1, u0, u1),
             answer=got, paid=None); return
    H.ev('PASS', what='spent one %s point on %s' % (REP, name), qty=q1, unspent=u1)
