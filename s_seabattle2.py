"""SEABATTLE2 (pirates-bulbs, 11-21): gap 9 in D:\\scratch\\lanes\\mechanics\\MECHANICS.md, the Sea Battle the way the
original plays it: two pirates on the two teams, one ship sinks the other. No stand-in magic word (s_seabattle.py's
Plan A used one). NEEDS HOST'S OK: it is two games at once (run_two.ps1).

Roles (env CREW_ROLE, set by run_two.ps1):
  captain  claude1 / 100000001. Sails to the French dock (Ile d'Etable de Porc), launches there (team French), then
           hunts (s_shipquest.hunt) with only the Spanish team's player ship as a target, and sinks it.
  mate     claude2 / 100000004. Sails to the Spanish dock (Isla de la Avaricia), launches there (team Spanish) and
           holds at the wheel off the dock until the captain sinks him.
Steps (one SB2- line each):
  SB2-DOCK    at his team's dock, on land.
  SB2-LAUNCH  at the wheel; the "You sail for the French!" (Spanish!) message and la.getSiegeTeam() agree.
  SB2-FOE     captain: the other team's player ship in view (the target); hunt fires only at it.
  SB2-SINK    captain: "Score: French n, Spanish m." with the French count up by one.
  SB2-SUNK    mate: "Your ship sank in the Sea Battle" (or the French score going up while he is out).
PASS (each game its own): captain = dock + launch + sink; mate = dock + launch + sunk.
Guard: only 100000001 (captain) and 100000004 (mate); never Host's 100000170 or his ship 100000173, never the boys'
100000656 / 100000665.
Pure functions first (import-tested offline); the generators run in the game."""
import os
import time

import s_seabattle as SB

ROLE = os.environ.get('CREW_ROLE', 'captain').lower()
ROLES = {'captain': (100000001, SB.FRENCH_DOCK, SB.SPANISH_DOCK), 'mate': (100000004, SB.SPANISH_DOCK, SB.FRENCH_DOCK)}
SECS = float(os.environ.get('SB2_SECS', '1500'))
NEVER_PIRATES = (100000170, 100000656, 100000665)
NEVER_SHIP = 100000173
TEAM_WAIT = 30.0           # s after taking the wheel for the team message and siege team
SCORE_WAIT = 20.0          # s after the target sank for the score message
PLAYER_SHIP = 'PlayerShip'          # a pirate's own ship, as the client names it (near-ships logs it; NPC ships are NPCShip)
# boats 11-21 SB3: hunt's own patrol rings the captain's launch island, and the mate holds ~12500 ft away off the
# other dock, so the captain never saw him. The captain searches a ring round the other team's island instead.
RING_R = 3000.0            # ft from the other island's centre (pvpFoes sees a player ship within 6000)
RING_N = 6
HOLD_LOG = 60.0            # s: the mate logs SB2-HOLD at least this often (the walker calls 240 s quiet a HANG)


# ------------------------------------------------------------------------------------------------ pure
def dockRing(cx, cy, r=RING_R, n=RING_N):
    """Pure: n search points [(x, y, label)] on a ring of r ft round (cx, cy)."""
    import math
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n), 'other dock %d' % i)
            for i in range(n)]


def guard(doId, role, ships):
    """-> None when this pirate may play this role, else why not."""
    if role not in ROLES:
        return 'CREW_ROLE %r is not captain or mate' % role
    if doId in NEVER_PIRATES:
        return 'pirate %s is never touched' % doId
    if NEVER_SHIP in (ships or []):
        return 'ship %d is never touched' % NEVER_SHIP
    if doId != ROLES[role][0]:
        return 'the %s is pirate %d only (this is %s)' % (role, ROLES[role][0], doId)
    return None


def pvpFoes(rows, mine, team):
    """rows (cls, doId, dist, siegeTeam, hp) -> [(dist, doId)] nearest first: the other team's player ships afloat."""
    other = SB.otherTeam(team)
    out = [(r[2], r[1]) for r in rows if r[0] == PLAYER_SHIP and r[1] != mine and r[3] == other
           and (r[4] is None or r[4] > 0) and r[2] is not None and r[2] < 6000]
    return sorted(out)


def mateSunk(msgs, before):
    """The mate's proof: the sank message, or a score message with the French one up (vs the first score he saw)."""
    if any(SB.SANK_MSG in t for t in msgs):
        return True
    for t in msgs:
        sc = SB.parseScore(t)
        if sc is not None and SB.scoreUp(before, sc, SB.FRENCH) and before is not None:
            return True
    return False


def passed(role, marks):
    need = ('dock', 'launch', 'sink') if role == 'captain' else ('dock', 'launch', 'sunk')
    return all(marks.get(k) for k in need), [k for k in need if not marks.get(k)]


# ------------------------------------------------------------------------------------------------ in the game
def rowsOf(H, ship):
    import s_shipquest
    p = ship.getPos(H.render)
    out = []
    for o in list(H.cr.doId2do.values()):
        if not hasattr(o, 'getPos') or not hasattr(o, 'getSiegeTeam'):
            continue
        try:
            d = (o.getPos(H.render) - p).length()
        except Exception:
            d = None
        out.append((type(o).__name__, o.doId, d, SB.siegeTeam(o), s_shipquest.hpOf(o)))
    return out


class PvPPicker:
    """s_shipfight.Picker with one change: the only target is the other team's player ship (s_shipquest.npcShips keeps
    NPC ships only). Patrols round the other team's dock, where the mate holds."""

    def __init__(self, H, t0, SF, sq, sailing, team, port, marks):
        self.p = SF.Picker(H, t0)
        tbl = sailing.islands()
        self.ring = None
        if port in tbl:
            self.p.ports = [(port, tbl[port][0], tbl[port][1], tbl[port][2])]
            self.ring = dockRing(tbl[port][1], tbl[port][2])
        self.H, self.sq, self.team, self.marks = H, sq, team, marks
        self.target = None
        self.seenT = 0.0

    def __getattr__(self, k):
        return getattr(self.__dict__['p'], k)

    def __enter__(self):
        self.p.__enter__()              # saves hunt's PATROL_PTS first; its __exit__ puts them back
        self.sq.npcShips, self.sq.matches = self.npcShips, self.matches
        if self.ring:
            self.sq.PATROL_PTS = self.ring
            self.H.ev('SB2-SEARCH', pts=[[round(x), round(y)] for x, y, _ in self.ring], r=RING_R)
        return self

    def __exit__(self, *a):
        return self.p.__exit__(*a)

    def npcShips(self, H, ship):
        self.p.npcShips(H, ship)                # the Picker's own bookkeeping (leash, patrol)
        rows = rowsOf(H, ship)
        if time.time() - self.seenT >= HOLD_LOG:   # every player ship in view, so a miss shows class, team and range
            self.seenT = time.time()
            H.ev('SB2-SEEN', ships=[[r[0], r[1], None if r[2] is None else round(r[2]), r[3], r[4]] for r in rows
                                    if 'Ship' in r[0] and 'NPC' not in r[0]][:6])
        foes = pvpFoes(rows, ship.doId, self.team)
        out = [(d, H.cr.doId2do[i]) for d, i in foes if i in H.cr.doId2do]
        if out:
            d, o = out[0]
            if self.target != o.doId:
                self.target = o.doId
                self.marks['foe'] = o.doId
                H.ev('SB2-FOE', foe=o.doId, owner=getattr(o, 'ownerId', None), name=getattr(o, 'name', ''),
                     dist=round(d), team=SB.siegeTeam(o), hp=self.sq.hpOf(o))
            p = self.p
            p.allowed = {o.doId}
            p.top = p.want = o.doId
        return out

    def matches(self, task, o):
        if getattr(o, 'doId', None) == self.target:
            return True, 'the other team'
        return False, 'not the other team'


def teamProof(H, box, n0, team, tag, marks, t0):
    """Generator: at the wheel, then the team message + siege team within TEAM_WAIT. -> ok."""
    la = H.la
    yield ('upto', lambda: la.getGameState() == 'ShipPilot', 60, 'at the wheel')
    t1 = time.time()
    yield ('upto', lambda: any(SB.launchTeam(t) == team for _, t in box[n0:]) and SB.siegeTeam(la) == team,
           TEAM_WAIT, 'team')
    msg = next((t for _, t in box[n0:] if SB.launchTeam(t)), None)
    ok = SB.launchTeam(msg) == team and SB.siegeTeam(la) == team
    marks['launch'] = ok
    H.ev(tag, team=SB.siegeTeam(la), want=team, msg=msg, ok=ok, gs=la.getGameState(), secs=round(time.time() - t1),
         t=round(time.time() - t0))
    return ok


def captain(H, team, other, box, marks, t0):
    import s_shipquest
    import s_shipfight as SF
    import sailing
    import builtins
    la = H.la
    picker = PvPPicker(H, t0, SF, s_shipquest, sailing, team, other, marks)
    n0 = len(box)
    g = s_shipquest.hunt(H, None, SF.AnyShip(), max(1.0, SECS - (time.time() - t0)))
    teamDone, sankT, why = False, None, 'timeout'
    sunk = []
    orig = H.ev

    def ev(kind, /, **kw):
        if kind == 'FOE-SUNK':
            sunk.append(kw.get('foe'))
        return orig(kind, **kw)
    H.ev = ev
    with picker:
        try:
            while time.time() - t0 < SECS:
                try:
                    y = next(g)
                except StopIteration as e:
                    why = e.value
                    break
                msgs = [t for _, t in box[n0:]]
                if not teamDone and la.getGameState() == 'ShipPilot':
                    lt = next((SB.launchTeam(t) for t in msgs if SB.launchTeam(t)), None)
                    marks.setdefault('pilotT', time.time())
                    if (lt == team and SB.siegeTeam(la) == team) or time.time() - marks['pilotT'] > TEAM_WAIT:
                        teamDone = True
                        marks['launch'] = lt == team and SB.siegeTeam(la) == team
                        H.ev('SB2-LAUNCH', team=SB.siegeTeam(la), want=team, ok=marks['launch'],
                             msg=next((t for t in msgs if SB.launchTeam(t)), None))
                        if not marks['launch']:
                            why = 'no team'
                            break
                if picker.target is not None and sankT is None and picker.target in sunk:
                    sankT = time.time()
                sc = next((SB.parseScore(t) for t in reversed(msgs) if SB.parseScore(t)), None)
                if sc is not None and sc != marks.get('score') and picker.target is not None:
                    up = SB.scoreUp(marks.get('score'), sc, team)
                    marks['score'] = sc
                    if up:
                        marks['sink'] = True
                        H.ev('SB2-SINK', ok=True, score='%d-%d' % sc, foe=picker.target, sunkSeen=sankT is not None,
                             secs=round(time.time() - t0))
                        why = 'done'
                        break
                if sankT is not None and time.time() - sankT > SCORE_WAIT:
                    H.ev('SB2-SINK', ok=False, foe=picker.target, why='no score message %d s after the sink'
                         % SCORE_WAIT, msgs=msgs[-6:])
                    why = 'no score'
                    break
                yield y
        finally:
            g.close()
            H.ev = orig
            for k in SF.STEER_KEYS:
                builtins.messenger.send(k + '-up')
    return why


def mate(H, team, box, marks, t0):
    import s_shipquest
    import builtins
    la = H.la
    n0 = len(box)
    ship = yield from s_shipquest.launchShip(H)
    if ship is None:
        return 'launch-failed'
    if not (yield from teamProof(H, box, n0, team, 'SB2-LAUNCH', marks, t0)):
        return 'no team'
    before = next((SB.parseScore(t) for _, t in reversed(box) if SB.parseScore(t)), None)
    lastHp, lastT = None, 0.0
    while time.time() - t0 < SECS:
        msgs = [t for _, t in box[n0:]]
        gone = H.cr.doId2do.get(ship.doId) is None or (s_shipquest.hpOf(ship) or 0) <= 0
        frenchScored = any((SB.parseScore(t) or (0, 0))[0] >= 1 for t in msgs)
        if mateSunk(msgs, before) or (gone and before is None and frenchScored):
            marks['sunk'] = True
            H.ev('SB2-SUNK', ok=True, msg=next((t for t in msgs if SB.SANK_MSG in t), None),
                 score=next((t for t in reversed(msgs) if SB.parseScore(t)), None), gs=la.getGameState(),
                 secs=round(time.time() - t0))
            return 'done'
        hp = s_shipquest.hpOf(ship) if H.cr.doId2do.get(ship.doId) is not None else None
        if (hp != lastHp and time.time() - lastT > 10) or time.time() - lastT > HOLD_LOG:
            H.ev('SB2-HOLD', hp=hp, gs=la.getGameState(), siege=SB.siegeTeam(la))
            lastHp, lastT = hp, time.time()
        for k in ('w', 's'):                    # hold still at the wheel: no sail
            builtins.messenger.send(k + '-up')
        yield 2.0
    return 'timeout'


def run(H):
    import s_lanes
    import sailing
    la = H.la
    t0 = time.time()
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    no = guard(la.doId, ROLE, ships)
    H.ev('SB2-START', role=ROLE, pirate=la.doId, ships=ships, secs=SECS, here=H.area(), gs=la.getGameState(),
         siege=SB.siegeTeam(la))
    if no:
        H.ev('FAIL', why=no)
        return
    if not ships:
        H.ev('FAIL', why='the pirate owns no ship')
        return
    _, dock, other = ROLES[ROLE]
    team = SB.teamOfDock(dock)
    marks, box = {}, []
    undo = SB.hookMessages(H, box)
    why = None
    try:
        here = sailing.hereUid(H)
        if here != dock:
            if here is None or la.getGameState() != 'LandRoam':
                if not (yield from s_lanes.onIsland(H, 'seabattle2', s_lanes.PR)):
                    H.ev('FAIL', why='could not get onto land to start', area=H.area())
                    return
            yield from sailing.sail_to(H, dock, 'Sea Battle dock (%s)' % SB.TEAM_NAMES[team])
            if sailing.hereUid(H) != dock and la.getGameState() == 'LandRoam':
                # boats 11-21: SB2 00:36 the mate's game ran ~30x slow (route 162 s, the captain's 5 s on the same
                # path) and stuck on the way to the rowboat; one more go from where he stands, as a player would
                H.ev('SB2-DOCK-RETRY', here=sailing.hereUid(H), la=H.P(la))
                yield from sailing.sail_to(H, dock, 'Sea Battle dock (%s), second go' % SB.TEAM_NAMES[team])
        marks['dock'] = sailing.hereUid(H) == dock and la.getGameState() == 'LandRoam'
        H.ev('SB2-DOCK', island=dock, ok=marks['dock'], here=sailing.hereUid(H), gs=la.getGameState(),
             secs=round(time.time() - t0))
        if not marks['dock']:
            H.ev('FAIL', why='not at the %s dock' % SB.TEAM_NAMES[team])
            return
        if ROLE == 'captain':
            why = yield from captain(H, team, other, box, marks, t0)
        else:
            why = yield from mate(H, team, box, marks, t0)
        ok, missing = passed(ROLE, marks)
        marks.pop('pilotT', None)
        H.ev('SB2-END', role=ROLE, why=why, marks=marks, msgs=[t for _, t in box][-10:], secs=round(time.time() - t0))
        if ok:
            H.ev('PASS', step='seabattle2', role=ROLE, team=SB.TEAM_NAMES[team], score=marks.get('score'),
                 secs=round(time.time() - t0))
        else:
            H.ev('FAIL', why='%s steps not proven: %s (%s)' % (ROLE, ', '.join(missing), why), marks=marks)
    finally:
        undo()
