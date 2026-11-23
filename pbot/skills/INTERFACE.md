# Player-bot skills: how a skill plugs into the brain

pbots, 2026-11-22 (Round 2 of PLAYERBOTS.md). Owner of this file and of `pbot\b_brain.py`: pbots. One skill per area,
one file per lane: `quests.py` = places, `sea.py` = boats, `games.py` = games, `land.py` = roblox-tray, `crew.py` = pbots.
Nobody edits another lane's file; brain changes are asked of pbots (STATUS line "PLAYERBOTS <skill>: NEED brain ...").

The shape below is the one quests.py, games.py and land.py already have. It is THE interface: nothing to rewrite.
Section 10 lists what brain builds 2026-11-22h and 22i added to drive it (done; the offline sims are green).

## 1. The brain as it is (b_brain.py, BUILD pbot-brain 2026-11-22i)

- One game process, one brain: `Brain(H)` where `H` is the walker's helper (`walker.py`, the step-script protocol).
  The brain IS the step script (`PROOF_SCRIPT = pbot\b_brain.py`); `run(H)` → `Brain(H).main()`.
- `main()` loops every BEAT 0.25 s: `crewWatch()` → `pick()` → `switch()` → `step()`. `step()` calls `st_<state>()`;
  a generator result is `yield from`'d, so a state may hand the main loop walker items (section 4) for a while.
- States and what each may press (`LET`): DOWN (nothing), WAIT (nothing), IDLE (look), LOST (look, walk), STAND (look),
  FOLLOW (walk), BOARD (walk, dinghy), DECK (look), CANNON (cannon), FIGHT (walk, sword, tonic), PLAY (walk, sword,
  tonic, look, dinghy, cannon, sail). `bot.may(press)` is the gate every action goes through. A skill flow runs in
  PLAY.
- `pick()` order (22h): down → DOWN. A running skill keeps PLAY whatever gs is (st_play's `cutReason()` is the only way
  out: limit, crew, safety, error). A SAFETY-band want (score ≥ 100) → PLAY from anywhere. A live BOARD flow keeps BOARD
  (IDLE if the crew is gone); a live DECK flow keeps DECK (the mate putting its own ship away). Emote/AFK: no crew and a
  want ≥ 10 → wake up and WAIT one beat, else IDLE 'asleep'; crewed → wake up. gs not in `ACTIVE_GS` (LandRoam, Battle,
  ShipPilot, WaterRoam, Cannon) → WAIT. No captain: on foot (LandRoam/Battle) and a want ≥ WANT_MIN 10 → PLAY; on my own
  launched ship → DECK (put it away); any other gs (WaterRoam, ShipPilot...) → WAIT 'no crew' (st_wait recovers from the
  water); else IDLE. Crewed, on deck: on my OWN ship and no cannon → DECK put-away; a manned cannon or a target in reach
  → CANNON; else DECK. Crewed, not on land → WAIT. Captain launched and > 60 ft → BOARD (or STAND until the next try);
  captain object not seen → a `crewOwn` want ≥ 10 → PLAY (crew.py's teleport to him, 22i), else LOST; a fight target →
  FIGHT; captain > 10 ft (> 6 ft while following) → FOLLOW; a `crewOk` want ≥ 10 → PLAY; else STAND.
- Flows: `flowStart(gen, name)` + `drive(item)`; a brain flow is cut at FLOW_MAX 180 s with a stuck BOT bug. That cap is
  the BRAIN's crew flows only; a skill flow has its own `limit` (section 2). `release(frm)` on every state change:
  closes the fighter, leaves a cannon, `.close()`s the flow (event flow-cut), closes a stray dinghy list, lifts the
  look key, `H.walk_cancel()`.
- Shared state lives on the brain object: `bot.H`, `bot.la` (localAvatar), `bot.cr`, `bot.B` (base), `bot.state`,
  `bot.since` (when the state began), `bot.why`, `bot.hist` (last 40 transitions), `bot.gs()` (gameFSM state name),
  `bot.down()`, `bot.onDeck()`, `bot.captain()` → `(captainId, band)` or None, `bot.wasInBand` (crewWatch's last
  in-a-band reading), `bot.lastCap` (the captain pick() last saw, 22i), `bot.dist(obj)`, `bot.where()` (one
  string for bug files: `'Port Royal at (323, 24), game state LandRoam, brain STAND'`, or `'aboard
  DistributedPlayerShip 100000750 (Sea) at (x, y), ...'`), `bot.ev(name, **kw)`, `bot.bug(...)` (section 6),
  `bot.world()` (section 5), `bot.ran`, `bot.results`, `bot.hold` (section 3), `bot.skills` (name → instance).
- Events go to `PROOF_EVOUT` (`walk-<TAG>-events.jsonl`, TAG = PBOT<slot>) as JSON lines through `bot.ev`/`H.ev`.

## 2. The skill shape

```python
# pbot/skills/<area>.py            (one class per file; the brain imports the module and makes ONE instance)
class Quests:
    name = 'quests'                 # the area; STATUS lines say "PLAYERBOTS quests"
    limit = 600                     # seconds one flow() may run before the brain cuts it (section 4); default 300
    crewOk = False                  # True = may run while crewed, in the brain's STAND state only (section 8)
    crewOwn = False                 # True = the crew's own skill (crew.py only, 22i): polled while crewed with the
                                    # captain out of view, spared the crew cut (limit, safety, error, down still cut it)

    def __init__(self, bot):        # bot = the brain (section 1 / 5). Keep it cheap: no scans, no caches.
        self.bot = bot

    def tick(self):                 # optional (22i): called every WANT_EVERY 2 s in every state but DOWN, crewed or
        pass                        # not. A watch (cheap reads, no presses); a raise = a BOT bug, 3 of them = unloaded.

    def want(self):                 # asked every WANT_EVERY 2 s when the brain is free (section 3)
        return (50, 'main story quest open')     # (score, why) or None. Cheap: reads, no walking, no network.

    def flow(self):                 # a generator of walker items (section 4); its return value is the result
        H = PlayerH(self.bot.H)     # the wrapper the three lanes already have: no H.mw, 'until' → 'upto', no PASS/FAIL
        yield from s_story.go(H, ...)
        return 'quest step done'

    def cut(self, why):             # optional. Called when the brain stops the flow early (limit, crew, safety, down).
        return self._leave()        # None, or a cleanup generator the brain drives for at most CUT_MAX 60 s
                                    # (games: leave the game; sea: drop the wheel). A closed generator cannot yield,
                                    # so the cleanup is a NEW generator.
```

- `limit` by area (seconds): games 1800 (a game runs up to 1590 s), sea 1200, quests 600, land 600. The brain's own
  crew flows keep 180. Over the limit = `skill-cut why=limit` + a stuck BOT bug on the skill's key (that is a BOT bug
  of the skill's: trim the flow or raise the limit with a reason).
- A skill holds no game objects across flows (doIds go stale on every teleport). Re-find what it needs at flow start.
- Memory: the bot's floor is ~1.5 GB per game; every skill together may add at most ~20 MB. No image/model loads,
  no big lists kept, no per-frame allocation storms. `want()` runs 30 times a minute: it must not walk, scan the
  whole doId2do or build a route.

## 3. How a skill says it wants to run (data-driven priority)

`want()` returns `(score, why)` or None. The brain picks the highest score. Same score: the skill that ran longest ago
first (`bot.ran[name]` = when its last flow ended). The bands:

| band | score | who | asked when |
|---|---|---|---|
| SAFETY | 100 and up | land.py: jail (gs ThrownInJail / jail interior / cell index), out-of-world recovery | everywhere: free, crewed, during another skill's flow (a higher safety score cuts the running flow) |
| UPKEEP | 60-99 | land.py: tonic when hp low (60), a skill point to spend, a friend/guild invitation panel to answer (70) | free, and crewed when `crewOk` |
| STORY | 40-59 | quests.py: the main story and side quests (50) | free |
| FREE PLAY | 10-39 | sea.py (sail, hunt NPC ships, repair, shipwright), land.py (hunt, loot), games.py (fishing, potions, benches, cards, shops, musician, treasure) | free |
| never | 0-9 | reserved: a score under 10 is ignored | |

- games.py's present scores (0.1-1.2) scale into the band as `10 + 20 * s` (so 0.1 → 12, 1.2 → 34). Every lane keeps
  its own weighting inside its band; the band order is fixed by this table.
- Free = no crew, on foot (gs LandRoam or Battle), not DOWN, no brain flow live. Crewed: the brain's crew states run
  (follow, board, cannon, fight beside the captain); a `crewOk` skill is asked only in STAND, and its flow is capped at
  CREW_SKILL_MAX 30 s, because the boys come first (PLAYERBOTS.md crew rule).
- A skill whose flow just ended or was cut is not asked again for one WANT_EVERY (`bot.hold[name]` = when it may be
  asked again); after a crash in `flow()` the hold is SKILL_RETRY 5 s. So a flow that returns at once cannot spin.
- Streaks are the skill's business: a skill that just ran lowers its own score (`bot.ran[name]` = when its last flow
  ended, `bot.results[name]` = `('end', result)` or `('cut', why)`) so one area does not play all day. The brain does
  not round-robin.
- The brain reads the wants at WANT_EVERY 2 s, never inside a running flow except the SAFETY band (every 2 s, cheap).
  A `want()` that raises is a BOT bug on the key `<name>-want`; after WANT_ERRORS 3 crashes the skill is unloaded for
  the run (`skill-unloaded name why`). A want that is not `(number, str)` logs `skill-want-bad` and counts as None.
- Events: `skill-loaded name module cls limit crewOk cut` / `skill-import-failed name module err tb` at load;
  `skill-want name score why wants` (only when the winner changes; `skill-want name=None wants=0` when no skill wants);
  `STATE PLAY why='<name>: <why>'`; `skill-start name score why limit crew gs la generator`;
  `skill-end name result secs gs la`; `skill-cut name why secs gs la` (why = limit|crew|safety|error, from the flow's
  own beat) or `skill-cut name why secs state to cleanup='closed'` (why = down|end|error, from a state change: knocked
  out, the game closing, a brain error); `skill-cleanup name why max` when `cut()` returned a generator, then
  `skill-cleanup-done name secs result gs`; `skill-cut-error` / `skill-close-error` when `cut()` or `.close()` raised.

## 4. Step, finish, fail (the yield protocol)

`flow()` yields walker items; the main loop drives them exactly as a brain flow is driven:

| yield | meaning |
|---|---|
| `secs` (number) | wait that long (the game keeps running; the bot's clock follows the work: 20 fps while a leg walks or a flow plans, 5 fps idle) |
| `('upto', fn, secs[, what])` | wait at most `secs`, end as soon as `fn()` is truthy (0.25 s poll). Timing out is normal, no STALL. **Use this, never `until`.** |
| `('until', fn, timeout[, what])` | strict wait: a timeout logs a STALL event, which the proof readers count as a fail. Only a skill's own `run(H)` step script may use it. `PlayerH` turns `until` into `upto`. |
| `yield from H.walk_to(...)` / `s_story.go(...)` / `paths.walk_route(...)` / `sailing.sail_to(...)` | walking and sailing are generators of the same items: hand them straight through |

- Finish: `return <result>` (a short string or a small dict). The brain logs `skill-end` and stores it in
  `bot.results[name]`. None is a fine result; a falsy result is not a failure.
- Fail: raise. Any exception out of `flow()` → the brain logs `skill-cut why=error`, files a BOT bug
  (`bug('traceback', '<name>-<where it was>', 'BOT', ..., tb=...)`) on the skill's behalf, releases everything,
  and asks the wants again 5 s later. A skill that knows its own failure reports it itself (section 6) and returns.
- Being cut: the brain `.close()`s the generator (your `finally:` runs; it may not yield), then drives `cut(why)`'s
  cleanup generator for at most CUT_MAX 60 s (over it: the cleanup is closed and a stuck BOT bug `<name>: the cleanup
  ran over 60 s` is filed). Cut reasons from the flow's own beat: `limit`, `crew` (a captain invited us, or a `crewOk`
  flow outlived CREW_SKILL_MAX 30 s, or the captain launched, left view or is > FOLLOW_ROUTE 40 ft away; never for a
  `crewOwn` skill, 22i, nor for a flow running in the SAFETY band, 22j: the jail escape finishes in a boy's crew too),
  `safety` (a
  SAFETY-band want with a higher score than the running skill's), `error` (the flow raised). From a state change the
  brain calls `cut(why)` once with `down` (hp 0 / Death / Dying), `end` (the game or the brain closing) or `error` (a
  brain error) and does NOT drive its generator (no beats are left): make those cuts synchronous (drop the wheel, leave
  the game at once) and do the slow part next flow.
- Reserved event names a skill never emits under the brain: `PASS`, `FAIL`, `STALL`, `MILESTONE`, `STATE`, `BUG`,
  `BRAIN`, `CREW-*`, `PBOT-*` (`CREW-*` is pbots' own prefix: crew.py emits CREW-TELE, CREW-TELE-GIVEUP,
  CREW-LEAVE-DEAD, CREW-QUEST-PROG, CREW-CUT). The runner reads PASS/FAIL as the whole run's verdict. Prefix your events with your
  area (`QUEST-STEP`, `SEA-DOCKED`, `GAME-START`, `LAND-LOOT`). A skill's own `run(H)` proof script (section 9) does
  write PASS/FAIL: that is its verdict.
- Every press goes through the same gates as the brain's own: `H.walk_to` / `H.walk_poll` (walk), `H.drawSword` /
  `H.hit` / `H.engage` (sword), the tonic key (tonic), `sailing.*` (sail, dinghy), the cannon helpers (cannon). In
  PLAY the brain lets all of them; in a `crewOk` flow only look, walk, sword, tonic.
- `H.fast(reason, on)` is fine (the brain uses it too); `H.snap()` is not (no pictures in play: the proof pictures
  are the brain's milestones only).

## 5. The shared bot state

Today a skill reads the game directly through the brain: `bot.la` (hp `la.hp`, `la.maxHp`, gold through the
inventory, `la.ship`, `la.getBandId()`), `bot.cr` (`cr.doId2do`, `cr.teleportMgr`, `cr.activeWorld`), `bot.H.area()`
(a tuple: class, ?, name), `bot.H.qids()` / `bot.H.quests()` / `bot.H.has(qid)`, `bot.gs()`, `bot.captain()`,
`bot.onDeck()`, `bot.down()`, `bot.state`, `bot.since`. The three lanes' `_Solo` stand-ins mirror exactly this, so a
skill tested solo runs unchanged under the brain.

Since 22h: `bot.world()` → one dict, rebuilt at most once a second (cached 1 s), so `want()` stays cheap:

```python
{'t': 1763830000.0, 'gs': 'LandRoam', 'state': 'IDLE', 'since': 12.5,
 'island': '1150922126.8dzlu', 'area': 'Port Royal', 'areaClass': 'DistributedGAIsland', 'pos': [x, y, z],
 'hp': 118, 'maxHp': 120, 'gold': 35, 'level': 4,
 'crew': {'captain': 0, 'members': []},          # captain 0 = not crewed; else the captain's doId
 'onDeck': False, 'ship': 0, 'myShip': 0,         # ship = the ship I stand on; myShip = my own launched ship
 'quests': ['c1.q1', ...], 'jailed': False, 'jailCell': -1}
```

- Every read is guarded: a field the game cannot answer holds its default, never an exception. Defaults: `gs` '?',
  `island` / `area` / `areaClass` / `pos` / `hp` / `maxHp` / `gold` / `level` None, `crew` `{'captain': 0,
  'members': []}`, `onDeck` False, `ship` / `myShip` 0, `quests` `[]`, `jailCell` -1. `island` = `s_lanes.islandOf(H)`
  or the sea's `hereUid`; `area` = the area's name (falls back to its class); `pos` = `H.P(la)`, a rounded `[x, y, z]`
  LIST (not a tuple; it may also be the string `'err ...'`); `ship` = the ship I stand on (parent object with Ship in
  its class name); `myShip` = `ship` only when it is my own launched ship; `jailCell` = `la.jailCellIndex` when 0..99,
  else -1; `jailed` = gs in JAIL (`ThrownInJail`) or areaClass `DistributedJailInterior` or `jailCell ≥ 0`.

Rule: skills READ the shared state, never write it. A skill keeps its own memory on `self`.

## 6. How a skill reports a bug

`bot.bug(kind, key, tag, what, tb='')`:

- `kind` in `bugfile.KINDS` = `traceback`, `disconnect`, `stuck`, `missing`, `other`.
- `key`: a stable short slug for THIS bug (`quests-npc-missing-<npcName>`, `sea-dock-refused`), so repeats merge.
  Same key at most 3 times per game; the first one gets a picture.
- `tag`: `GAME` = the game or server did wrong (a traceback out of the game's own code, an NPC that never answers,
  a reward not paid, a kick). `BOT` = the bot's own logic, time, path or a magic word asked. Unsure = `BOT`
  (bulbs triages GAME files; a wrong GAME costs them a read).
- `what`: one sentence a reader without the events can act on. Include ids and names, never the login name
  (POC_TOKEN / pocUsername / BOT_ACCOUNT never appear in events or bug files).
- The brain adds: `where` (`bot.where()`: island, area, gs, state, position), the pirate (id + name, not the
  account), `source='pbot <BUILD>'`, the last 12 transitions as events, and the picture.
- Files: `C:\PiratesBots\out\bugs\inbox\BUG-<kind>-<slug>-<hash6>.md` (bugfile.report). GAME files go bulbs → READY →
  sink; BOT files go to the skill's owner (the file names the skill in its key: name your keys `<area>-...`).
- A skill's own `run(H)` proof script has no brain: call `bugfile.report(kind, key, tag, what, where=..., pirate=...,
  source='<area> run', tb=..., events=...)` directly, or just let the runner's Start-BugReport watcher file the
  traceback (it watches the .err file).

## 7. Calling the s_*.py helpers from the light bot

- The light bot is the full client with `strip-gl.prc` (tiny textures, no reflections/shadows), window off, 5 fps,
  Idle priority, on the hidden desktop. Every helper that works in a plain harness run works here too, at 5 fps:
  anything that counts frames must count seconds instead.
- Imports: the harness dir is on `sys.path` (the brain adds it). `import s_story` already happens at brain import
  (s_lanes imports it at module top), so importing it lazily inside `flow()` costs nothing and keeps your module
  importable by a sim without the game. Import `sailing`, `paths`, `s_lanes`, `s_fighter`, `s_cannonpass`,
  `s_crew2` the same way, inside the flow or at the top of your file behind a try.
- Walking: `H.walk_to(pos, ref=None, arrive=2.0, timeout=None, face=False, tag='')` (one leg, a generator),
  `H.walk_poll(target, ...)` = one straight leg per call (True arrived / False walking / None no way),
  `paths.walk_route(H, goals, arrive, short=0.0, tag='route', tries=3)` (round buildings and along piers; never a
  goal farther than ~3000 ft: the grid build has no yield and hangs the game), `s_story.go(H, obj, arrive, face, ref,
  tag)`. `H.face(obj)`, `H.walk_cancel()`.
- Fighting: `H.drawSword()`, `H.hit(doId, reach=3.5)`, `H.engage(doId, reach=3.5)`, `s_fighter.Fighter` (the brain's
  crew fight uses it). Never target a pirate or a player ship (section 8).
- Sea (sailing.py): `hereUid(H)`, `onShip(H)`, `dinghy_in_reach(H)`, `to_dinghy(H, here)`, `launch(H, here, aboard)`,
  `sail_to(H, uid, why='', via=None)`, `shipwrights`, `live_dinghies`, `repair`, `route`. Cannons at sea:
  `s_cannonpass` (the brain's `Track()` leads a moving target; the deck gun reaches ~3500 ft at 24 deg).
- Islands: `s_lanes.islandOf(H)`, `s_lanes.hereUid`. Teleports in PLAY are the GAME's own only:
  `cr.teleportMgr.requestTeleportToIsland(uid)`; `s_lanes.onIsland(H, step, uid)` uses the `areaTeleport` MAGIC WORD
  and is the brain's SETUP only. A skill never calls `H.mw(...)`: `PlayerH` raises `Blocked` on it, the brain files a
  BOT bug `<area>-mw-blocked`. A player has no magic words; the bot plays like a player.
- Quests: `H.quests()`, `H.qids()`, `H.has(qid)`, `s_story.PR`, `s_story.questSpots()` (falls back to the file beside
  s_story.py), the s_story steppers.
- SpeedChat only: `bot.la.b_setSC(idx)` (SC_HI 100, SC_HELLO_Q 109, SC_THANKS 500 are the brain's). Never typed chat.
- A `PlayerH` wrapper (the lanes have one each; keep yours) does three things: refuses `H.mw`, turns `until` into
  `upto`, and renames PASS/FAIL/STALL/MILESTONE events to `<AREA>-...`. Everything else passes through.

## 8. Rules for every skill

1. Host's pirate 100000170 and his ship 100000173, Player1 100000656, Player2 100000665: never a target, never invited,
   never followed unless they crewed us. The bot only ACCEPTS crew invites (from those three + `PBOT_CAPTAINS`).
2. Never attack a player's ship or a pirate. No PvP. Never board a ship we were not invited to.
3. The boys come first: a crew invite cuts a running skill flow (`cut('crew')`) unless `crewOk`; a `crewOk` flow in a
   crew is capped at 30 s and runs only in STAND. A flow that started in the SAFETY band (land's jail escape) is the one
   exception: it runs to its end crewed or not (22j), since a bot stuck in a cell is no use to the crew either. When the bot stands on ITS OWN launched ship with no skill running
   (crewed or alone), the brain goes DECK and runs sea.py's `putAway(why)` generator as a DECK flow (why = `crew` when
   crewed, `idle` when alone; up to 60 s; events `putaway-go ship why gs`, `putaway-done ok gs onDeck la`,
   `putaway-error`), retried every PUTAWAY_RETRY 60 s until the bot is off the ship. Without sea.py (or a `putAway`
   that returns no generator) one `putaway-none why ship sea` event and the brain waits on deck. The put-away is NOT a
   cut: sea's own flow was already cut (`cut('crew')`) before.
4. SpeedChat only. Never typed chat. No pictures in play.
5. Never `H.mw`. Never a teleport except the game's own island teleport.
6. The login name never appears anywhere (events, bugs, STATUS, commits, command lines). Pirate id + name instead.
7. Time: `want()` under a millisecond; one flow under its `limit`; yields at least every 2 s of game time so a cut
   lands (a `yield 0.5` inside loops).
8. Memory: section 2. No `loader.loadModel`, no texture reads, no `doId2do` copies kept across flows.
9. Down (hp 0 / Death / Dying) is the brain's: nothing acts. Jail (gs ThrownInJail or the jail interior) is land.py's
   SAFETY flow: get out, drink Vitae if there is one, walk to the door. The brain asks the SAFETY band in both
   `ThrownInJail` and `LandRoam` inside the cell.
10. A GAME bug is filed once and the skill moves on (another row, another NPC); it never retries the same broken
    thing more than twice per game (that makes the file count climb and the night useless).
11. Every `ev` wrapper a skill hands to the s_*.py helpers (its `PlayerH.ev`, a hunt hook, a sim's fake H) is
    positional-only, exactly like `walker.ev(name, /, **kw)`: `def ev(self, name, /, **kw)`. Engine events carry
    their own `name=` field (s_shipfight HOME-PICK on every repairAt, s_everyship EVERY-WRIGHT / EVERY-FOE /
    EVERY-START, s_activities ACT-STEP / GUILD-NAME, s_flagship DECK-FOE, TARGET-GONE); without the `/` the first
    one raises `TypeError: ev() got multiple values for argument 'name'` inside the flow, a BOT bug and a quiet
    spell for nothing (places' PBOT1-quests 13:01, fix b916dcf; sea.py:151 found in the 11-22 13:58 review).

## 9. Proving a skill: a sim, then one proof run

1. Sim first (fail-before / pass-after): your `sim_<area>.py` runs the skill's logic against a stand-in `H` without
   the game; it fails on the bug you fix and passes after. Keep it under the WSL/ppython caps.
2. Proof run on the light bot, behind run.lock, through pbots' runner, one at a time, in the plan's order (crew proof,
   then places' MAIN story runs, then one skill proof at a time). The skill's own `run(H)` step script (the one that
   refuses the family's pirates and writes PASS/FAIL) is the PROOF_SCRIPT:

   ```powershell
   & C:\PiratesBots\pbot\run_bot.ps1 -Slot 1 -Script C:\PiratesBots\pbot\skills\<area>.py -Proof -Once -Secs 1800 -Island <uid>
   ```

   `-Script` (added 11-22 with this file) swaps the brain for your script in the same stripped game, same account slot,
   same Idle/hidden/sound-off rules. `-Proof` keeps the strike rule: no PASS by the end = a strike for the bot, a
   crash exit too, a kick (exit 3) never. Events: `walk-PBOT1-<leaf>-events.jsonl`; log/err beside it.
3. Under the brain: `PBOT_SKILLS=<area>` loads only your skill, so a brain run plays nothing else. Unset = every
   registered skill; set but empty = none (the v1 crew-only brain); `a,b` or `a b` = that subset. A name not in
   `SKILLS` logs `skill-import-failed ... err='not a registered skill'`. The module is imported by path as
   `pbskill_<module>` (no package, no `__init__.py`; `pbot\skills` is on `sys.path` for `simctl`-style helpers).
   `run_bot.ps1` passes the variable through unchanged.
4. Results go in your lane's STATUS line as `PLAYERBOTS <area>: ...`; a BOT bug file in a proof is yours; a GAME one
   goes to bulbs.

## 10. Brain builds 2026-11-22h and 22i: what they added (done, 2026-11-22)

- The `PLAY` state: `LET['PLAY'] = {'walk','sword','tonic','look','dinghy','cannon','sail'}`; `st_play` starts the
  picked skill's `flow()` (a plain return = done at once; a generator is driven through `flowStart`/`drive`); while it
  runs `pick()` keeps PLAY whatever gs is (a game, a ship, the water); `cutReason()` ends it: `limit` (the skill's
  `limit`, read live), `crew`, `safety`, `error`. DOWN / the game closing / a brain error cut it from `release()`
  (section 4).
- Wants every WANT_EVERY 2 s when free (on foot, no crew) and in STAND for `crewOk` skills; the SAFETY band (≥ 100)
  everywhere, ThrownInJail included; a want under WANT_MIN 10 is ignored; the hold after a flow (section 3).
- Registration + env switch: `SKILLS = {'quests': ('quests','Quests'), 'sea': ('sea','Sea'), 'games': ('games','Games'),
  'land': ('land','Land'), 'crew': ('crew','Crew')}`; `PBOT_SKILLS` (section 9.3); an import or constructor failure
  logs `skill-import-failed name module err tb` and the brain runs on without it (never a crash).
- `bot.world()`, `bot.ran`, `bot.results`, `bot.hold`, `bot.skills` (sections 1, 3, 5); `CUT_MAX` 60, `CREW_SKILL_MAX`
  30, `SKILL_RETRY` 5, `WANT_ERRORS` 3, `JAIL = ('ThrownInJail',)`; `ACTIVE_GS` is the old PLAY tuple, renamed so the
  state and the tuple no longer share a name.
- Events skill-loaded / skill-import-failed / skill-want / STATE PLAY / skill-start / skill-end / skill-cut /
  skill-cleanup / skill-cleanup-done / skill-unloaded (section 3).
- The mate on its own launched ship puts it away through sea.py's `putAway(why)` as a DECK flow (rule 8.3), crewed or
  alone, before it follows; alone in the water (WaterRoam, no crew) the brain WAITs and st_wait recovers.
- The run-8 BOT bug (crew proof, 10:4x): the brain filed 'never put the mate at it' after the mate had manned the
  captain's cannon and then left it when the ship docked. Now `cannonManned` is set on the first manned beat
  (`cannon-manned` event); leaving later is `cannon-left shots=<n>`, no bug; the BOT bug stays only when the mate was
  never at the cannon within CANNON_MAN_WAIT 10 s.
- `bot.where()` for bug files: `'<area> at (x, y), game state <gs>, brain <state>'`, or `'aboard <ShipClass> <doId>
  (<area>) at (x, y), ...'` on a ship.
- `run_bot.ps1 -Script <path>`: done with this file (11-22).
- Proven offline: `sim_brain22h.py` (pbots' scratch), 19 scenarios A-T against stub skills (load/subset/import
  failure, want bands and ties, hold, limit cut + stuck bug, crew cut + cleanup generator, cleanup over CUT_MAX, safety
  preempt, flow crash + retry hold, want() crash ×3 → unloaded, world() fields, put-away as a DECK flow, cannon
  manned-then-left, DOWN/END cuts): 19 PASS on 22h; the cannon scenario fails on 22g (no `cannon-manned`).
- 22i (pbots, with crew.py): `crewOwn` on a skill (crew.py only) marks the crew's own: `poll(..., own=True)` keeps only
  those; `pick()`'s 'captain not in view' branch polls them first (→ PLAY) and goes LOST only without a want;
  `cutReason()` spares a `crewOwn` skill the crew cut (limit, safety, error, down still cut it). `crewWatch`'s
  CREW-LEFT carries `why` = `left` (I asked: leaveCrew within 5 s) | `kicked` (the captain's pirate still in view) |
  `captain gone` (logged off, dissolved, or out of view) and `captain=`, from `bot.lastCap` (set by pick()).
  `tickSkills()` beside `crewWatch()` in `main()`: every skill's optional `tick()` every WANT_EVERY 2 s in every state
  but DOWN; a raise = a BOT bug `<name>-tick`, WANT_ERRORS 3 of them → `skill-unloaded why='tick() crashed 3 times'`.
  `skill-loaded` reports `crewOwn` and `tick`.
- crew.py (pbots' own) wraps the brain's proven crew states (invite, FOLLOW, BOARD, CANNON, FIGHT, the kick) and adds
  rows 32 (the game's own 'go to' teleport to a captain out of view for TELE_AFTER 8 s, through
  `cr.teleportMgr.queryAvatarForTeleport`, retried every 90 s, 3 refusals in one lost spell → give up until he is seen
  again; `CREW-TELE`), 33 (leave a band whose manager is out of view for DEAD_AFTER 90 s; `CREW-LEAVE-DEAD`) and 10
  (`CREW-QUEST-PROG` when one of my quest task states rises while crewed; tick()). Proven offline: `sim_brain22i.py`
  (pbots' scratch, a copy at C:\PiratesBots\out\pbots\sim22i): 24 scenarios A-Y PASS on 22i with the real crew.py loaded;
  U-Y all five fail on 22h (DESIGN.md has the lines). Not yet seen in the real game.
- Next (pbots): the first live brain run with the lanes' skills behind run.lock, then the 8-hour soak (row 70).

## 11. Answers to the lanes' questions

- games (round-2 map): a game needs up to 1590 s, so `limit = 1800` for games.py; FLOW_MAX 180 never applies to a
  skill. After a cut the brain drives `cut(why)` → your `leave(H, g)` generator for up to 60 s, then checks LandRoam.
- roblox-tray (round-2 map): Q1 the brain keeps DOWN (nothing can act); land.py owns the jail through the SAFETY band
  and is asked in `ThrownInJail` too; the crew FIGHT beside the captain stays the brain's (later crew.py), land.py owns
  free-play fights. Q2 lazy `import s_story` inside the flow is fine (already imported). Q3 section 5 (`bot.la` /
  `bot.cr` / `bot.H` direct, or `bot.world()` since 22h). Q4 section 6. The JAILED preempt hook = a SAFETY-band want (score
  100) from land.py; no brain hook needed beyond the band.
- boats (round-2 map): sea.py owns rows 11-28 on the bot's OWN ship (launch, sail, hunt NPC ships, dock, repair,
  shipwright) with `limit = 1200`; the deck cannon on the CAPTAIN's ship stays the brain's CANNON state (crew.py).
  `sail` and `dinghy` are PLAY presses. Rule 8.3 asks sea.py for a `putAway(why)` generator (the ship away, the mate
  on land, ≤ 60 s) that the brain runs as a DECK flow whenever the bot stands on its own launched ship with no skill
  running (why = `crew` or `idle`), after sea's own flow was cut.
- places (round-2 map): quests.py at 50 wins over free play and loses to upkeep and safety; a quest step that needs a
  sail or a fight may run past SLICE 150 inside `limit = 600`; the MAIN story proof runs are second in the run order.
- crew (pbots' own, 22i): crew.py wraps the brain's crew states instead of replacing them (the invite, FOLLOW, BOARD,
  CANNON, FIGHT and the kick stay the brain's, proven in run 8); it adds the teleport to an out-of-view captain, leaving
  a dead band, and the quest-credit witness. A lane that needs the crew to do more asks pbots (STATUS "PLAYERBOTS crew:
  NEED ...").
