"""Bug reporter sim gate (games, 11-22, PLAYERBOTS): plants a game traceback, a disconnect and a stuck bot in a
throwaway harness + server log folder, then checks the bug inbox.
  before: the check runs on the planted logs with no reporter run -> FAIL (nothing is filed today)
  after:  bugreport.py --once -> PASS: one bug file each (client traceback GAME, client disconnect, stuck BOT, AI
          traceback, astrond eject); a bot that keeps walking is not stuck; a kick at a server restart is not filed.
  then:   a repeat bumps the count (no new file, the old traceback is not filed again); a traceback still being
          written is held until its last line comes.
Usage: python t_bugreport.py   exit 0 = PASS, 1 = FAIL. Writes only under %TEMP%\\bugreport-sim."""
import os, sys, time, json, glob, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.environ.get('TEMP', '/tmp'), 'bugreport-sim')
H, S, B = (os.path.join(ROOT, d) for d in ('harness', 'srv', 'bugs'))
shutil.rmtree(ROOT, ignore_errors=True)
for d in (H, S, B):
    os.makedirs(d)
NOW = time.time()
stamp = lambda e: time.strftime('%m-%d-%Y %H:%M:%S', time.localtime(e))
iso = lambda e: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(e))


def write(path, text, mode='w'):
    with open(path, mode, encoding='utf-8', newline='\n') as f:
        f.write(text)


# ---- the planted logs
write(os.path.join(H, 'walk-SIM.err'), '\n'.join([
    ':%s DistributedInventoryBase(warning): inventory timed out.' % stamp(NOW - 300),
    'Traceback (most recent call last):',
    '  File "C:\\Panda3D-1.11.0-x64\\direct\\showbase\\ShowBase.py", line 3339, in run',
    '    self.taskMgr.run()',
    '  File "C:\\Games\\pirates-online\\pirates-online-classic\\pirates\\quest\\QuestStatus.py", line 212, in createLadders',
    '    ladder = self.ladders[ladderId]',
    'KeyError: 401000016',
    ':%s :task(error): Exception occurred in PythonTask createLadders' % stamp(NOW - 300),
    'Traceback (most recent call last):',               # Panda prints it a second time: one bug, one sighting
    '  File "C:\\Games\\pirates-online\\pirates-online-classic\\pirates\\quest\\QuestStatus.py", line 212, in createLadders',
    '    ladder = self.ladders[ladderId]',
    'KeyError: 401000016', '']))
write(os.path.join(H, 'walk-SIM.log'), '\n'.join([
    ':%s ActorInterval(warning): Unknown animation for actor: bayonet_idle_to_fight_idle' % stamp(NOW - 200),
    ':%s PiratesClientRepository(warning): Server is booting us out (153): An unexpected problem has occured.' % stamp(NOW - 200),
    ':%s PiratesClientRepository(warning): Lost connection to gameserver.' % stamp(NOW - 200),
    ':%s PiratesClientRepository(warning): Lost connection to server. Notifying user.' % stamp(NOW - 200), '']))
# a kick 60 s before the AI restarted (sink's restart): not a bug
write(os.path.join(H, 'walk-KICK.log'),
      ':%s PiratesClientRepository(warning): Lost connection to gameserver.\n' % stamp(NOW - 1260))
area = ['DistributedIsland', '1150922126.8dzlu', 'Port Royal']
stuck_ev = [{'t': NOW - 760, 'ev': 'start'}]
moving_ev = [{'t': NOW - 760, 'ev': 'start'}]
for k in range(26):                                     # 12.5 minutes of heartbeats, 30 s apart
    t = NOW - 750 + 30 * k
    hb = {'t': t, 'ev': 'heartbeat', 'q': 'c3r3r1.26deliverRum', 'gs': 'LandRoam', 'area': area,
          'ts': [{'id': 'c3r3r1.26deliverRum', 'complete': False, 'ts': [[0, 1, 0]]}]}
    stuck_ev += [hb, {'t': t + 1, 'ev': 'stuck', 'tag': 'approach', 'la': [331.6 + k % 2, 30.7, 4.4], 'tries': 3}]
    moving_ev += [hb, {'t': t + 1, 'ev': 'walk-leg', 'frm': [331.6 + 20 * k, 30.7, 4.4], 'ok': True}]
write(os.path.join(H, 'walk-SIM-events.jsonl'), ''.join(json.dumps(e) + '\n' for e in stuck_ev))
# FLAGSHIP1 (bulbs 11-22): one STAGE line with a run-relative t, the rest clock time; 3 minutes standing at the wheel
# is not stuck (it was filed as 29922675 minutes)
flag_ev = [{'t': NOW - 200, 'ev': 'start'}, {'t': 54, 'ev': 'STAGE', 'what': 'flagship', 'launched': True}]
flag_ev += [{'t': NOW - 190 + 30 * k, 'ev': 'heartbeat', 'area': ['DistributedSimpleShip', '-', 'Scarlet Hawk'],
             'pos': [12.0, 3.0, 20.0]} for k in range(6)]
write(os.path.join(H, 'walk-FLAG-events.jsonl'), ''.join(json.dumps(e) + '\n' for e in flag_ev))
write(os.path.join(H, 'walk-MOVE-events.jsonl'), ''.join(json.dumps(e) + '\n' for e in moving_ev))
write(os.path.join(S, 'ai.log'), '\n'.join([
    ":prc(warning): changing default value for ConfigVariable check-language from '1' to '0'.",
    ':%s PiratesAIRepository: Using connect method \'native\'' % stamp(NOW - 1200),
    ':%s PlayerShipAI(warning): TEMP-DIAG ship 100000667 setLocation 401000017 2810' % stamp(NOW - 100),
    'Assertion failed: !is_empty() at line 1982 of panda/src/pgraph/nodePath.cxx',
    'Traceback (most recent call last):',
    '  File "/opt/pirates-online/pirates-online-classic/pirates/pirate/BattleNPCGameFSMAI.py", line 298, in walkToPoint',
    '    self.avatar.lookAt(walkPointNode)',
    'AssertionError: !is_empty() at line 1982 of panda/src/pgraph/nodePath.cxx', '']))
write(os.path.join(S, 'astrond.log'), '\n'.join([
    '\x1b[37;2m[%s] \x1b[32mINFO: \x1b[0mMain: Loading configuration file...' % iso(NOW - 7200),
    '\x1b[37;2m[%s] \x1b[31mERROR: \x1b[0mClient (127.0.0.1:57324, 1000000992): Ejecting client (153): The session '
    'object with id 100000004 has been unexpectedly deleted.' % iso(NOW - 90), '']))

# a low-memory bot game on TinyPanda: Panda's own C++ assert in the renderer is ours, not the game's (bulbs 11-22 MEAS1)
write(os.path.join(H, 'walk-TINY.err'), '\n'.join([
    ':%s PiratesBase: Default graphics pipe is TinyWinGraphicsPipe (TinyPanda).' % stamp(NOW - 400),
    'Assertion failed: _contexts == nullptr at line 279 of C:\\panda3d\\panda\\src\\gobj\\geomVertexArrayData.cxx',
    'Traceback (most recent call last):',
    '  File "C:\\Panda3D-1.11.0-x64\\direct\\showbase\\ShowBase.py", line 2197, in __igLoop',
    '    self.graphicsEngine.renderFrame()',
    'AssertionError: _contexts == nullptr at line 279 of C:\\panda3d\\panda\\src\\gobj\\geomVertexArrayData.cxx', '']))
# a low-memory bot game on pbots' strip-gl.prc (Start-BugReport leaves walk-<run>.prc): stand-in textures lose their
# names, so a texture lookup in game code fails; ours, under its own key (bulbs 11-22)
write(os.path.join(H, 'walk-STRIP.err'), '\n'.join([
    'Traceback (most recent call last):',
    '  File "C:\\Games\\pirates-online\\pirates-online-classic\\pirates\\pirate\\PirateFemale.py", line 640, in generateShirtSets',
    '    tex.setMinfilter(Texture.FTLinear)',
    "TypeError: 'NoneType' object is not subscriptable", '']))
write(os.path.join(H, 'walk-STRIP.prc'), 'C:\\Dev\\Toontown\\pirates-harness\\pbot\\prc\\strip-gl.prc\n')
write(os.path.join(H, 'walk-SIM.acct'), 'claude2\n')   # what Start-BugReport leaves next to a run
ENV = dict(os.environ, BUGS_DIR=B, BUG_HARNESS=H, BUG_SERVER_LOGS=S)
NOWIN = 0x08000000 if sys.platform == 'win32' else 0


def reporter():
    r = subprocess.run([sys.executable, os.path.join(HERE, 'bugreport.py'), '--once'], env=ENV, capture_output=True,
                       text=True, timeout=120, creationflags=NOWIN)
    if r.returncode:
        print(r.stdout, r.stderr)
    return r.returncode


def bugs():
    out = {}
    for p in glob.glob(os.path.join(B, 'inbox', 'BUG-*.md')):
        text = open(p, encoding='utf-8').read()
        field = lambda n: (text.split('\n- %s: ' % n, 1)[1].split('\n', 1)[0] if '\n- %s: ' % n in text else '')
        out[os.path.basename(p)] = dict(kind=field('kind'), tag=field('tag'), count=int(field('count') or 0),
                                        key=field('key'), source=field('source'), text=text)
    return out


WANT = [  # (name, kind, tag, words in the key)
    ('client game traceback', 'traceback', 'GAME', ('client KeyError', 'QuestStatus.py:createLadders')),
    ('client disconnect', 'disconnect', 'GAME', ('client booted 153',)),
    ('stuck bot', 'stuck', 'BOT', ('stuck Port Royal', 'c3r3r1.26deliverRum')),
    ('AI traceback', 'traceback', 'GAME', ('ai AssertionError', 'BattleNPCGameFSMAI.py:walkToPoint')),
    ('astrond eject', 'disconnect', 'GAME', ('astrond eject 153',)),
    ('TinyPanda renderer assert', 'traceback', 'BOT', ('client AssertionError', 'ShowBase.py:__igLoop')),
    ('stripped-settings game error', 'traceback', 'BOT', ('client stripped TypeError', 'PirateFemale.py:generateShirtSets')),
]


def check(label):
    have, bad = bugs(), []
    for name, kind, tag, words in WANT:
        hit = [b for b in have.values() if b['kind'] == kind and b['tag'] == tag and all(w in b['key'] for w in words)]
        if len(hit) != 1:
            bad.append('%s: %d files' % (name, len(hit)))
    if any('walk-MOVE' in b['source'] for b in have.values()):
        bad.append('a bot that keeps walking was filed as stuck')
    if any('walk-FLAG' in b['source'] for b in have.values()):
        bad.append('a run-relative STAGE time made a false stuck')
    if any('KICK' in b['source'] for b in have.values()):
        bad.append('a kick at a server restart was filed')
    if len(have) != len(WANT):
        bad.append('%d bug files, want %d' % (len(have), len(WANT)))
    print('%s: %s' % (label, 'PASS' if not bad else 'FAIL - ' + '; '.join(bad)))
    return not bad, have


ok_before, _ = check('before (no reporter run)')
assert reporter() == 0
ok_after, have = check('after bugreport.py --once')
for n, b in sorted(have.items()):
    print('  %-60s %s %s x%d' % (n[:60], b['kind'], b['tag'], b['count']))
stuck = [b for b in have.values() if b['kind'] == 'stuck']
rich = bool(stuck) and all(s in stuck[0]['text'] for s in ('## Last bot events', 'Port Royal at (', '- pirate: claude2\n',
                                                           '## What happened'))
tb = [b for b in have.values() if b['key'].startswith('client KeyError')]
rich = rich and bool(tb) and '## Traceback' in tb[0]['text'] and '- where: ' in tb[0]['text']
print('bug files carry what happened, where, pirate, events, traceback: %s' % ('yes' if rich else 'NO'))

# repeat: the same kick again later in the same log -> count 2, nothing else changes
write(os.path.join(H, 'walk-SIM.log'), ':%s PiratesClientRepository(warning): Server is booting us out (153): An '
      'unexpected problem has occured.\n' % stamp(NOW - 30), 'a')
# a traceback the game is still writing: no exception line yet
write(os.path.join(H, 'walk-SIM.err'), 'Traceback (most recent call last):\n  File "C:\\Games\\pirates-online\\'
      'pirates-online-classic\\pirates\\ship\\DistributedSimpleShip.py", line 77, in fireCannon\n', 'a')
assert reporter() == 0
have2 = bugs()
counts = {n: b['count'] for n, b in have2.items()}
dis = [b for b in have2.values() if b['key'].startswith('client booted 153')]
ok_repeat = (len(have2) == len(WANT) and dis and dis[0]['count'] == 2 and
             all(b['count'] == 1 for b in have2.values() if not b['key'].startswith('client booted 153')))
print('repeat bumps the count, old lines not filed twice, unfinished traceback held: %s %s' % (
    'PASS' if ok_repeat else 'FAIL', sorted(counts.values())))
write(os.path.join(H, 'walk-SIM.err'), '    self.cannon.fire()\nAttributeError: \'NoneType\' object has no attribute '
      '\'fire\'\n', 'a')
assert reporter() == 0
have3 = bugs()
ok_held = len(have3) == len(WANT) + 1 and any('DistributedSimpleShip.py:fireCannon' in b['key'] for b in have3.values())
print('held traceback filed once its last line came: %s' % ('PASS' if ok_held else 'FAIL'))
print('BUGS.md:')
print(open(os.path.join(B, 'BUGS.md'), encoding='utf-8').read())
ok = (not ok_before) and ok_after and rich and ok_repeat and ok_held
print('RESULT: %s (before FAIL, after PASS)' % ('PASS' if ok else 'FAIL'))
sys.exit(0 if ok else 1)
