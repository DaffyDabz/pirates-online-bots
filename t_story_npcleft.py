"""Offline test of s_story.npcTick (MAIN27, 11-21): bribing Pauper Pedro moved the quest on to c3r3r1.18visitFernando
with Pedro's talk still open. The new step was not done, so the bot waited NPC_HARD (121 s, NPC-STUCK) on a talk that
belonged to the step before. A talk the quest moved on from is ended like a finished one, within NPC_LIMIT.
Run: python3.9 t_story_npcleft.py <dir holding s_story.py>"""
import importlib, os, sys, types

D = os.path.abspath(sys.argv[1])
os.environ['PROOF_SCRIPT'] = os.path.join(D, 'x.py')
stub = lambda n: sys.modules.setdefault(n, types.ModuleType(n))
lanes = stub('s_lanes')
lanes.PR, lanes.TORTUGA = 'pr', 'tg'
for n in ('sailing', 'paths', 's_shipquest', 's_cards', 's_guards', 's_earn'):
    stub(n)
sys.modules['s_cards'].playTypes = lambda: ()
sys.modules['s_cards'].TYPES = {}
os.environ.update(STORY_START='x', STORY_STOP='x')
os.environ['STORY_LADDER'] = ','          # no ladder walked: the game's quest tables are not loaded offline
for n in ('pirates', 'pirates.quest', 'pirates.quest.QuestLadderDB', 'pirates.quest.QuestDNA'):
    stub(n)
sys.modules['pirates.quest.QuestDNA'].QuestDNA = type('QuestDNA', (), {})
sys.path.insert(0, D)
S = importlib.import_module('s_story')
import time, types as T
S.taskDone = lambda q: False
S.clickDialog = lambda H: None
exits = []
S.npcExit = lambda H, npc: exits.append(1) or ['handleEndInteractKey']
S.talkingTo = lambda H, sobj=None: T.SimpleNamespace(doId=401000035, name='Pauper Pedro')
H = T.SimpleNamespace(ev=lambda *a, **k: None, la=T.SimpleNamespace(questStep=None, getGameState=lambda: 'NPCInteract'),
                      cr=T.SimpleNamespace(doId2do={}))
clock = [1000.0]
time.time = lambda: clock[0]
cur = {}
assert S.npcTick(H, None, cur, 'c3r3r1.17bribePedro') is None      # talk opens on the bribe step
clock[0] += 4
assert S.npcTick(H, None, cur, 'c3r3r1.17bribePedro') is None      # bribe step not done yet: wait
clock[0] += 4
r = S.npcTick(H, None, cur, 'c3r3r1.18visitFernando')               # quest moved on, Pedro's talk still open
assert r == 'exit', r
assert exits == [1]
# a talk that never finishes on its own step still waits NPC_HARD (unchanged)
cur, exits[:] = {}, []
assert S.npcTick(H, None, cur, 'c3r3r1.18visitFernando') is None
clock[0] += S.NPC_HARD - 10
assert S.npcTick(H, None, cur, 'c3r3r1.18visitFernando') is None
clock[0] += 11
assert S.npcTick(H, None, cur, 'c3r3r1.18visitFernando') == 'exit'
print('npcleft ok')
