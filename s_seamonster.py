"""SEAMONSTER (pir-bot job 25, 11-19): live smoke of the Kraken (server-tree patches 0220 client + 0221 AI) and the Sea
Serpent (0222 client + 0223 AI) on the test pirate's own crewed ship. Asked by pir-test through the brain; the magic
words and lines are from pir-quests' README ("The Kraken", "The Sea Serpent") and the 0221/0223 diffs.

Order (each monster logs MON- lines with mon=kraken|serpent; SEAMONSTER_ONLY=kraken or serpent runs one):
  0  MON-START     guard (FAIL at once for pirate 100000170 or a pirate owning ship 100000173), then aboard: if not
                   on a ship, to Port Royal's open island if needed (s_lanes.onIsland) and launch from the dinghy
                   (s_shipquest.launchShip). MON-LAUNCH ship=. No sailing needed: both words work in the starter
                   waters. SEAMONSTER_SAIL=n taps W for n s first (out to open water), then stops.
  1  MON-WHY       '<kind> why' -> "Kraken on ship N: <why or 'it may attack now'>" / "Sea Serpent on ship N: ...".
  2  MON-SUMMON    'kraken' -> "The Kraken attacks ship N with K tentacles"; 'serpent' -> "A Sea Serpent attacks ship
                   N". "No Kraken: <why>" / "No Sea Serpent: <why>" is retried every 10 s up to 6 times when the why
                   names the other monster (the Kraken still leaving), else FAIL with the text. The crew message
                   ("The Kraken is attacking! ..." / "A Sea Serpent is coming! ...") is logged as MON-CREW-MSG.
  3  MON-UP        the client objects (GrabberTentacle / DistributedSeaSerpent) with hp > 0: count, hp, maxHp, ft.
  4  MON-HIT       fire the broadside that lines up on a target (s_shipquest.linedUp) until one target's hp drops:
                   before, after, drop (a cannonball takes 100: a quarter of a 400 tentacle, a twelfth of a 1200
                   serpent). After LINEUP_WAIT s with nothing lined up both broadsides fire anyway. MON-HULL logs the
                   ship's hp from the summon to here (the squeeze / bites).
  5  MON-BEAT      '<kind> beat' -> "Knocked down N tentacles" / "Knocked the Sea Serpent down".
  6  MON-GOLD      the gold before the summon and after the beat: gain, expect (kraken 500, serpent 400), ok (gain ==
                   expect), the "You beat the ...! N gold each, and a treasure chest in the hold!" message and its N.
  7  MON-PLUNDER   the beat message (it names the chest) and the ship's cargo before and after, when the client ship
                   has it (getCargo / cargo); ok = the message came (the cargo is reported, not judged).
  8  MON-GONE      the monster's client objects gone within GONE_WAIT s.
Then PASS (every monster: summon, up, hit, beat, gold ok) or FAIL naming what is missing. The serpent runs after the
Kraken is gone (a ship never gets both at once). Every system message is logged as sys-msg. Our ship sinking or the
pirate leaving the wheel ends the run with FAIL. It never docks.
Pure functions first (unit_job25.py); the generator below runs in the game (no game import at module load)."""
import os
import re
import time

NEVER_PIRATE, NEVER_SHIP = 100000170, 100000173
ONLY = os.environ.get('SEAMONSTER_ONLY', '').strip().lower()
SAIL = float(os.environ.get('SEAMONSTER_SAIL', '0'))
ANSWER_WAIT = 15.0       # s for a magic word's answer
SUMMON_TRIES = 6
SUMMON_GAP = 10.0        # s between summon tries while the other monster leaves
UP_WAIT = 20.0           # s for the monster to rise (0221/0223: 3 s)
HIT_SECS = 90.0          # s of firing for one hit
LINEUP_WAIT = 15.0       # s with nothing lined up before both broadsides fire anyway
GOLD_WAIT = 20.0         # s after the beat for the gold
GONE_WAIT = 30.0         # s for the monster's objects to go
BEAT = 0.5

KINDS = {
    'kraken': {'name': 'Kraken', 'cls': ('GrabberTentacle',), 'gold': 500, 'word': 'kraken',
               'crew': 'The Kraken is attacking!', 'won': 'You beat the Kraken!', 'other': 'serpent'},
    'serpent': {'name': 'Sea Serpent', 'cls': ('DistributedSeaSerpent',), 'gold': 400, 'word': 'serpent',
                'crew': 'A Sea Serpent is coming!', 'won': 'You beat the Sea Serpent!', 'other': 'kraken'},
}
ORDER = ('kraken', 'serpent')

_WHY = re.compile(r'^(?:Kraken|Sea Serpent) on ship (\d+): (.*)$')
_KRAKEN = re.compile(r'^The Kraken attacks ship (\d+) with (\d+) tentacles')
_SERPENT = re.compile(r'^A Sea Serpent attacks ship (\d+)')
_NO = re.compile(r'^No (?:Kraken|Sea Serpent): (.*)$')
_BEAT_K = re.compile(r'^Knocked down (\d+) tentacles')
_WON = re.compile(r'You beat the (?:Kraken|Sea Serpent)! (\d+) gold each')


# ------------------------------------------------------------------------------------------------ pure
def kinds(only=ONLY):
    """The monsters to run, in order."""
    if only in KINDS:
        return [only]
    return list(ORDER)


def guard(doId, ships):
    if doId == NEVER_PIRATE:
        return 'pirate %d is never touched' % NEVER_PIRATE
    if NEVER_SHIP in (ships or []):
        return 'ship %d is never touched' % NEVER_SHIP
    return None


def whyAnswer(text):
    """'<kind> why' -> (shipId, why) or None."""
    m = _WHY.match((text or '').strip())
    return (int(m.group(1)), m.group(2)) if m else None


def summonAnswer(kind, text):
    """-> ('ok', shipId, tentacles or None) / ('no', why) / ('refused', text) / None (not an answer to this word)."""
    t = (text or '').strip()
    m = (_KRAKEN if kind == 'kraken' else _SERPENT).match(t)
    if m:
        return ('ok', int(m.group(1)), int(m.group(2)) if kind == 'kraken' else None)
    m = _NO.match(t)
    if m and t.startswith('No %s:' % KINDS[kind]['name']):
        return ('no', m.group(1))
    if t in ('You are not on a ship', 'Valid: attack, why, beat, off'):
        return ('refused', t)
    return None


def retryable(kind, why):
    """A 'No <kind>: why' worth waiting out: the other monster is still on this ship."""
    w = (why or '').lower()
    other = KINDS[KINDS[kind]['other']]['name'].lower()
    return other in w or ('kraken' in w if kind == 'serpent' else 'serpent' in w)


def beatAnswer(kind, text):
    """-> ('ok', n) / ('none', text) / None."""
    t = (text or '').strip()
    if kind == 'kraken':
        m = _BEAT_K.match(t)
        if m:
            return ('ok', int(m.group(1)))
    elif t == 'Knocked the Sea Serpent down':
        return ('ok', 1)
    if t.startswith('No %s on ship' % KINDS[kind]['name']) or t == 'The Sea Serpent is already down':
        return ('none', t)
    return None


def wonGold(text):
    m = _WON.search(text or '')
    return int(m.group(1)) if m else None


def goldOk(before, after, expect):
    gain = after - before
    return gain, gain == expect


def firstHit(hp0, hpNow):
    """{doId: hp} at the start and now -> (doId, before, after) of the first target whose hp dropped, or None."""
    for k, v in hpNow.items():
        b = hp0.get(k)
        if b is not None and v is not None and v < b:
            return (k, b, v)
    return None


def passed(marks):
    """marks[kind] = {summon, up, hit, beat, gold} -> (ok, missing list)."""
    miss = []
    for k, m in marks.items():
        for s in ('summon', 'up', 'hit', 'beat', 'gold'):
            if not m.get(s):
                miss.append('%s %s' % (k, s))
    return (not miss and bool(marks)), miss


# ------------------------------------------------------------------------------------------------ in the game
def hookMessages(H, box):
    """Log every system message (sys-msg) and keep its text in box. -> the undo function."""
    from otp.avatar import DistributedPlayer as DPm
    cls = DPm.DistributedPlayer
    orig = cls.__dict__['setSystemMessage']

    def setSystemMessage(av, aboutId, chatString, *a, **kw):
        box.append((time.time(), chatString))
        try:
            H.ev('sys-msg', text=chatString, av=getattr(av, 'doId', None), about=aboutId)
        except Exception:
            pass
        return orig(av, aboutId, chatString, *a, **kw)
    cls.setSystemMessage = setSystemMessage

    def undo():
        cls.setSystemMessage = orig
    return undo


def hpOf(o):
    for a in ('getHp',):
        f = getattr(o, a, None)
        if f is not None:
            try:
                return f()
            except Exception:
                pass
    for a in ('hp', 'Hp'):
        v = getattr(o, a, None)
        if v is not None:
            return v
    return None


def maxHpOf(o):
    f = getattr(o, 'getMaxHp', None)
    if f is not None:
        try:
            return f()
        except Exception:
            pass
    return getattr(o, 'maxHp', None)


def monsters(H, kind):
    """The monster's client objects now."""
    names = KINDS[kind]['cls']
    return [o for o in list(H.cr.doId2do.values()) if type(o).__name__ in names]


def cargoOf(ship):
    for a in ('getCargo', 'getCargoList'):
        f = getattr(ship, a, None)
        if f is not None:
            try:
                return list(f() or [])
            except Exception:
                pass
    c = getattr(ship, 'cargo', None)
    try:
        return list(c) if c is not None else None
    except TypeError:
        return None


def answer(H, i0, parse):
    """The first parsed answer in H.resp after index i0, or None."""
    for t in H.resp[i0:]:
        a = parse(t)
        if a is not None:
            return a, t
    return None


def ask(H, word, parse, wait=ANSWER_WAIT):
    """Generator: send word, wait for an answer parse() knows. -> (parsed, text) or (None, None)."""
    i0 = len(H.resp)
    H.mw(word)
    box = {}

    def got():
        r = answer(H, i0, parse)
        if r is not None:
            box['r'] = r
        return r is not None
    yield ('upto', got, wait, word)
    return box.get('r', (None, None))


def aboard(H, la, sid):
    return la.getGameState() == 'ShipPilot' and H.cr.doId2do.get(sid) is not None


def fight(H, kind, ship, box, marks):
    """Generator: one monster from 'why' to gone. Fills marks[kind]. -> None, or a reason the run must stop."""
    import s_lanes
    import s_shipquest as Q
    la, R = H.la, H.render
    K = KINDS[kind]
    m = marks.setdefault(kind, {})
    sid = ship.doId
    w = K['word']

    a, t = yield from ask(H, w + ' why', whyAnswer)
    H.ev('MON-WHY', mon=kind, answer=t, ship=a[0] if a else None, why=a[1] if a else None)

    # summon (retried while the other monster is still leaving)
    g0 = s_lanes.gold(H)
    cargo0 = cargoOf(ship)
    hull0 = Q.hpOf(ship)
    nBox = len(box)
    res = None
    for n in range(SUMMON_TRIES):
        a, t = yield from ask(H, w, lambda x: summonAnswer(kind, x))
        if a is not None and a[0] == 'no' and retryable(kind, a[1]) and n + 1 < SUMMON_TRIES:
            H.ev('MON-SUMMON-WAIT', mon=kind, why=a[1], n=n + 1)
            yield SUMMON_GAP
            continue
        res = (a, t)
        break
    a, t = res if res else (None, None)
    ok = a is not None and a[0] == 'ok'
    m['summon'] = ok
    H.ev('MON-SUMMON', mon=kind, ok=ok, answer=t, ship=a[1] if ok else None, tentacles=a[2] if ok else None,
         gold=g0, hull=hull0)
    if not ok:
        return '%s summon: %s' % (kind, t or 'no answer to the magic word')
    yield ('upto', lambda: any(K['crew'] in s for _, s in box[nBox:]), 10.0, 'crew message')
    crew = next((s for _, s in box[nBox:] if K['crew'] in s), None)
    H.ev('MON-CREW-MSG', mon=kind, ok=crew is not None, msg=crew)

    # up
    t0 = time.time()
    yield ('upto', lambda: any((hpOf(o) or 0) > 0 for o in monsters(H, kind)), UP_WAIT, kind + ' up')
    objs = [o for o in monsters(H, kind) if (hpOf(o) or 0) > 0]
    m['up'] = bool(objs)
    p = ship.getPos(R)
    H.ev('MON-UP', mon=kind, ok=bool(objs), n=len(objs), ids=[o.doId for o in objs],
         hp=[hpOf(o) for o in objs], maxHp=[maxHpOf(o) for o in objs],
         ft=[round((o.getPos(R) - p).length()) for o in objs if hasattr(o, 'getPos')],
         want=a[2], secs=round(time.time() - t0, 1))
    if not objs:
        return None if aboard(H, la, sid) else 'left the ship'

    # hit: fire the broadside that lines up on a target until one target's hp drops
    keys = Q.broadsideKeys()
    hp0 = {o.doId: hpOf(o) for o in objs}
    t0 = time.time()
    fired, hit, lineT = [], None, None
    if not keys:
        H.ev('NO-BROADSIDE', mon=kind, why='the pirate has no broadside skill at rank 2+')
    while keys and time.time() - t0 < HIT_SECS:
        if not aboard(H, la, sid):
            return 'our ship sank' if (Q.hpOf(ship) or 0) <= 0 else 'left the ship'
        live = [o for o in monsters(H, kind) if (hpOf(o) or 0) > 0]
        hit = firstHit(hp0, {o.doId: hpOf(o) for o in monsters(H, kind)})
        if hit is not None or not live:
            break
        for o in live:
            hp0.setdefault(o.doId, hpOf(o))
        lined = {}
        for o in live:
            try:
                brg = Q.bearing(H, ship, o.getPos(R))
                sk = Q.linedUp(H, ship, o, brg)
            except Exception:
                sk = None
            if sk is not None and sk in keys:
                lined.setdefault(sk, o)
        if lined:
            lineT = None
        else:
            lineT = lineT or time.time()
            if time.time() - lineT >= LINEUP_WAIT:
                lined = {sk: None for sk in keys}
        for sk, o in lined.items():
            if Q.recharging(H, sk):
                continue
            messenger.send(keys[sk]); messenger.send(keys[sk] + '-up')
            fired.append(sk)
            H.ev('MON-FIRE', mon=kind, side=Q.sideName(sk), at=o.doId if o is not None else None,
                 lined=o is not None, n=len(fired))
        yield BEAT
    if hit is None:
        hit = firstHit(hp0, {o.doId: hpOf(o) for o in monsters(H, kind)})
    m['hit'] = hit is not None
    H.ev('MON-HIT', mon=kind, ok=hit is not None, foe=hit[0] if hit else None, before=hit[1] if hit else None,
         after=hit[2] if hit else None, drop=(hit[1] - hit[2]) if hit else None, fired=len(fired),
         secs=round(time.time() - t0, 1))
    hull1 = Q.hpOf(ship)
    H.ev('MON-HULL', mon=kind, before=hull0, now=hull1, lost=(hull0 - hull1) if None not in (hull0, hull1) else None,
         maxHp=getattr(ship, 'maxHp', None))
    if not aboard(H, la, sid):
        return 'our ship sank' if (Q.hpOf(ship) or 0) <= 0 else 'left the ship'

    # beat
    nBox = len(box)
    a, t = yield from ask(H, w + ' beat', lambda x: beatAnswer(kind, x))
    ok = a is not None and a[0] == 'ok'
    m['beat'] = ok
    H.ev('MON-BEAT', mon=kind, ok=ok, answer=t, n=a[1] if ok else None)

    # gold and plunder
    want = K['gold']
    t0 = time.time()
    yield ('upto', lambda: s_lanes.gold(H) - g0 >= want and any(K['won'] in s for _, s in box[nBox:]),
           GOLD_WAIT, kind + ' gold')
    g1 = s_lanes.gold(H)
    gain, gok = goldOk(g0, g1, want)
    won = next((s for _, s in box[nBox:] if K['won'] in s), None)
    m['gold'] = gok
    H.ev('MON-GOLD', mon=kind, before=g0, after=g1, gain=gain, expect=want, ok=gok, msg=won, each=wonGold(won),
         secs=round(time.time() - t0, 1))
    cargo1 = cargoOf(ship)
    added = None
    if cargo0 is not None and cargo1 is not None:
        added = [c for c in cargo1 if c not in cargo0] if len(cargo1) >= len(cargo0) else []
    m['plunder'] = won is not None and 'chest' in won
    H.ev('MON-PLUNDER', mon=kind, ok=m['plunder'], msg=won, cargoBefore=cargo0, cargoAfter=cargo1, added=added)

    # gone
    t0 = time.time()
    yield ('upto', lambda: not monsters(H, kind), GONE_WAIT, kind + ' gone')
    left = monsters(H, kind)
    H.ev('MON-GONE', mon=kind, ok=not left, left=[o.doId for o in left], secs=round(time.time() - t0, 1))
    return None


def run(H):
    import s_lanes
    import sailing
    import s_shipquest as Q
    la = H.la
    try:
        ships = list(la.getInventory().getShipDoIdList())
    except Exception:
        ships = []
    todo = kinds(ONLY)
    H.ev('MON-START', pirate=la.doId, ships=ships, kinds=todo, here=H.area(), gs=la.getGameState(),
         gold=s_lanes.gold(H))
    no = guard(la.doId, ships)
    if no:
        H.ev('FAIL', why=no); return
    if not ships and la.getGameState() != 'ShipPilot':
        H.ev('FAIL', why='the pirate owns no ship'); return
    t0 = time.time()
    box = []
    undo = hookMessages(H, box)
    marks = {}
    stop = None
    try:
        if la.getGameState() != 'ShipPilot' and not sailing.onShip(H):
            if sailing.hereUid(H) is None:
                yield from s_lanes.onIsland(H, 'seamonster', s_lanes.PR)
        ship = yield from Q.launchShip(H)
        if ship is None:
            H.ev('FAIL', why='could not launch the ship'); return
        sid = ship.doId
        if sid == NEVER_SHIP:
            H.ev('FAIL', why='ship %d is never touched' % NEVER_SHIP); return
        H.ev('MON-LAUNCH', ship=sid, hp=Q.hpOf(ship), gs=la.getGameState())
        if SAIL > 0:
            messenger.send('w'); messenger.send('w-up')
            yield SAIL
            messenger.send('s'); messenger.send('s-up')
        for kind in todo:
            stop = yield from fight(H, kind, ship, box, marks)
            if stop:
                break
        ok, miss = passed({k: marks.get(k, {}) for k in todo})
        H.ev('MON-END', marks=marks, stop=stop, secs=round(time.time() - t0))
        if stop:
            H.ev('FAIL', why=stop, marks=marks)
        elif ok:
            H.ev('PASS', step='seamonster', kinds=todo,
                 gold={k: marks[k].get('gold') for k in todo}, secs=round(time.time() - t0))
        else:
            H.ev('FAIL', why='sea monster steps not proven: %s' % ', '.join(miss), marks=marks)
    finally:
        undo()
