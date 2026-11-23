"""crew.py - the crew skill (pbots' own): the three crew duties the brain's states do not cover.

Rows 10, 29b, 31-33 of PLAYERBOTS-activities.md. The brain (b_brain.py) already does the crew work that must run
every beat and is proven in the real game (run 8): accept an invite from a listed captain (row 31), follow him (29b),
board his ship (30), man a cannon and shoot (34-35), fight beside him (36), leave on a kick or his logoff (33,
crewWatch). This skill adds what those states leave out, as a skill of the same shape as quests.py / sea.py /
games.py / land.py (INTERFACE.md section 2):

- row 32, the teleport to the crew: crewed and the captain's pirate out of view for TELE_AFTER s (another island, the
  sea, a building) -> the game's own 'go to' teleport (GuiManager.handleGotoAvatar's path:
  cr.teleportMgr.queryAvatarForTeleport), retried every TELE_RETRY s, TELE_MAX refusals in one lost spell then give up
  until he is seen again. A refusal (same area, a flag, the family-server rules) shows no TeleportOut and clears the
  game's teleport lock, so a retry is safe.
- row 33, leaving a dead crew: in a band whose manager is not in view for DEAD_AFTER s (the band not dissolved: his
  logoff normally reaches us as setBandId(0, 0) at once, this is the stuck case) -> bot.leaveCrew, retried every
  LEAVE_RETRY s. The CREW-LEFT why (left / kicked / captain gone) is the brain's (crewWatch, 22i).
- row 10, crew quest credit: tick() (every WANT_EVERY s, 22i) watches my quests' task states; a step that rises while
  I am crewed is a CREW-QUEST-PROG event (qid, before, after, captain, aboard, gs): the witness that a crewmate's kill
  or sail counted for me. A watch: cheap reads, no presses.

Shape: name 'crew', limit 240, crewOk True and crewOwn True (22i: pick() polls it while crewed with the captain out
of view, before LOST; the crew cut spares it, limit / safety / error / down still cut it). want() is UPKEEP: 'tele'
80, 'leave' 70. Events (CREW-* is pbots' own prefix, so this file may emit it): CREW-TELE captain out landed secs
area fails, CREW-TELE-GIVEUP captain fails, CREW-LEAVE-DEAD secs out, CREW-QUEST-PROG qid before after captain aboard
gs, CREW-CUT why duty.
Env: PBOT_CREW_TELE_AFTER (8), PBOT_CREW_TELE_RETRY (90), PBOT_CREW_TELE_MAX (3), PBOT_CREW_DEAD_AFTER (90).
"""
import os
import time
import traceback

import s_crew2      # the harness dir is on sys.path (the brain put it there); the sim stubs it

TELE_AFTER = float(os.environ.get('PBOT_CREW_TELE_AFTER', '8'))     # s out of view before the teleport (LOST_WALK is 10)
TELE_RETRY = float(os.environ.get('PBOT_CREW_TELE_RETRY', '90'))    # s between tries
TELE_MAX = int(os.environ.get('PBOT_CREW_TELE_MAX', '3'))           # refusals in one lost spell before giving up
TELE_OUT = 30.0                                                     # s for the game to leave LandRoam (TeleportOut)
TELE_LAND = 120.0                                                   # s for the landing after it
DEAD_AFTER = float(os.environ.get('PBOT_CREW_DEAD_AFTER', '90'))    # s in a band with no manager in view before leaving
LEAVE_RETRY = 30.0                                                  # s between leave requests (leaveCrew debounces 30 too)
SCORE = {'tele': 80.0, 'leave': 70.0}                               # UPKEEP band (60-99)
LAND = ('LandRoam', 'Battle')


def rose(old, new):
    """True when a task state in new is past old's at the same index (progress or attempts)."""
    for (p0, a0), (p1, a1) in zip(old, new):
        if p1 > p0 or a1 > a0:
            return True
    return False


class Crew:
    name = 'crew'
    limit = 240
    crewOk = True
    crewOwn = True

    def __init__(self, bot):
        self.bot, self.H = bot, bot.H
        self.duty = None                  # what flow() does next: 'tele' | 'leave'
        self.lostAt = None                # when the captain's pirate left view (None = in view, or no captain)
        self.teleLast, self.teleFails, self.gaveUp = 0.0, 0, False
        self.deadAt = None                # when the band lost its manager from view (None = has one, or no band)
        self.leaveLast = 0.0
        self.quest = {}                   # qid -> [(progress, attempts), ...] as of the last tick
        self.ticks = 0

    # ---------- want ----------
    def want(self):
        bot, now = self.bot, time.time()
        inBand = bool(bot.wasInBand)
        cap = bot.captain() if inBand else None
        if inBand and cap is None:
            self.deadAt = self.deadAt or now
        else:
            self.deadAt = None
        if cap is not None and bot.cr.doId2do.get(cap[0]) is None:
            self.lostAt = self.lostAt or now
        else:
            self.lostAt, self.teleFails, self.gaveUp = None, 0, False
        if self.deadAt is not None and now - self.deadAt >= DEAD_AFTER and now - self.leaveLast >= LEAVE_RETRY:
            self.duty = 'leave'
            return SCORE['leave'], 'leave: no captain in the crew for %.0f s' % (now - self.deadAt)
        if (self.lostAt is not None and now - self.lostAt >= TELE_AFTER and not self.gaveUp
                and now - self.teleLast >= TELE_RETRY and bot.gs() in LAND and not bot.onMyShip() and not bot.down()):
            self.duty = 'tele'
            return SCORE['tele'], 'tele: captain %s out of view for %.0f s' % (cap[0], now - self.lostAt)
        return None

    # ---------- flow ----------
    def flow(self):
        duty = self.duty
        if duty == 'tele':
            return (yield from self.tele())
        if duty == 'leave':
            return (yield from self.leave())
        return {'duty': duty, 'ok': False, 'why': 'no duty'}

    def tele(self):
        """Row 32: the game's 'go to <crewmate>' teleport to the captain, then wait for the landing."""
        bot = self.bot
        cap = bot.captain()
        if cap is None:
            return {'duty': 'tele', 'ok': False, 'why': 'no captain'}
        cid, t0 = cap[0], time.time()
        self.teleLast = t0
        try:
            bot.cr.teleportMgr.queryAvatarForTeleport(cid)
        except Exception:
            self.teleFails += 1
            bot.bug('traceback', 'crew-tele', 'BOT', 'queryAvatarForTeleport(%s) raised' % cid, tb=traceback.format_exc())
            return {'duty': 'tele', 'ok': False, 'why': 'raised'}
        yield ('upto', lambda: bot.gs() not in LAND, TELE_OUT, 'teleport out')
        out = bot.gs() not in LAND
        landed = False
        if out:
            yield ('upto', self.landed, TELE_LAND, 'landed')
            landed = self.landed()
        else:
            self.teleFails += 1
        bot.ev('CREW-TELE', captain=cid, out=out, landed=landed, secs=round(time.time() - t0, 1), area=self.areaName(),
               fails=self.teleFails)
        if not out and self.teleFails >= TELE_MAX:
            self.gaveUp = True
            bot.ev('CREW-TELE-GIVEUP', captain=cid, fails=self.teleFails)
        why = 'ok' if (out and landed) else ('never left' if not out else 'did not land')
        return {'duty': 'tele', 'ok': bool(out and landed), 'why': why}

    def landed(self):
        bot = self.bot
        try:
            return bool(bot.onDeck() or (bot.gs() in LAND and self.H.area() is not None))
        except Exception:
            return False

    def areaName(self):
        try:
            a = self.H.area()
            return list(a) if isinstance(a, tuple) else a
        except Exception:
            return None

    def leave(self):
        """Row 33: leave a band whose manager has been out of view for DEAD_AFTER s."""
        bot, now = self.bot, time.time()
        secs = round(now - (self.deadAt or now), 0)
        self.leaveLast = now
        bot.leaveCrew('no captain in the crew for %.0f s' % secs)
        yield ('upto', lambda: not s_crew2.inBand(bot.la), 10, 'out of the crew')
        out = not s_crew2.inBand(bot.la)
        bot.ev('CREW-LEAVE-DEAD', secs=secs, out=out)
        if out:
            self.deadAt = None
        return {'duty': 'leave', 'ok': out, 'why': 'ok' if out else 'still in the crew'}

    # ---------- tick (22i) ----------
    def tick(self):
        """Row 10: a quest task state that rises while I am crewed = crew credit (CREW-QUEST-PROG). A watch only."""
        bot = self.bot
        self.ticks += 1
        try:
            inv = bot.la.getInventory()           # not la.getQuests(): that prints a line while the inventory loads
            quests = (inv.getQuestList() if inv is not None else None) or []
        except Exception:
            return
        seen = {}
        for q in quests:                          # client DistributedQuest: .questId, .taskStates (QuestTaskState ParamObjs)
            try:
                qid = q.questId
                st = [(int(s.getProgress()), int(s.getAttempts())) for s in (q.taskStates or [])]
            except Exception:
                continue
            seen[qid] = st
            old = self.quest.get(qid)
            if old is not None and bot.wasInBand and rose(old, st):
                bot.ev('CREW-QUEST-PROG', qid=qid, before=old, after=st, captain=bot.lastCap, aboard=bot.onDeck(),
                       gs=bot.gs())
        self.quest = seen           # always, so a rise seen only after joining is not credited to the crew

    # ---------- cut ----------
    def cut(self, why):
        self.bot.ev('CREW-CUT', why=why, duty=self.duty)     # nothing to clean: a teleport in flight cannot be recalled
