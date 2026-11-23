"""Bug reporter (games, 11-22, PLAYERBOTS item 1): ONE python process that files every bug the bots and the server show.
Every 60 s (never less) it reads only the bytes that are new since its last look:
  - the bot games' logs here (walk-*.err, walk-*.log): tracebacks, "Lost connection", "Server is booting us out (N)"
  - the server logs on /opt (ai.log, uberdog.log, astrond.log), read as files over \\\\wsl.localhost; tracebacks and
    astrond "Ejecting client (N)". Read only, never server.prc, never anything from the kid PCs.
  - the bot event files (walk-*-events.jsonl) while a run writes them: stuck = 10 minutes with no progress
    (same spot within 50 ft, same quest step, same script stage)
Each sighting goes through bugfile.report: one D:\\scratch\\lanes\\bugs\\inbox\\BUG-<sig>.md per bug, a repeat bumps
its count, BUGS.md is rebuilt. Offsets live in <bugs>\\state.json so a restart never files a line twice.
No subprocesses, no windows: run_walk.ps1 starts it with pythonw at Idle priority if bugreport.pid is not alive.
  pythonw bugreport.py            the watcher (one copy only; a second copy exits at once)
  python bugreport.py --once      one scan, then exit (the sim test uses this)
Env: BUGS_DIR (default D:\\scratch\\lanes\\bugs), BUG_HARNESS (default this folder), BUG_SERVER_LOGS (default the /opt
logs folder; '-' = none)."""
import os, re, sys, json, time, glob, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bugfile

HARNESS = os.environ.get('BUG_HARNESS', HERE)
SERVER_LOGS = os.environ.get('BUG_SERVER_LOGS', r'\\wsl.localhost\Ubuntu\opt\pirates-online\logs')
SERVER_FILES = ('ai.log', 'uberdog.log', 'astrond.log')
INTERVAL = 60
STUCK_SECS = 600
STUCK_FT = 50.0
ACTIVE_SECS = 900          # an events file written to in the last 15 min belongs to a run that is still going
READ_CAP = 16 << 20        # at most 16 MB of one log per scan; the rest waits for the next scan
FP_BYTES = 256             # the first bytes of a log name it; new first bytes = the log was rotated by a restart
HARNESS_HINTS = ('pirates-harness', 'walker.py', 'sailing.py')

STATE = os.path.join(bugfile.BUGS, 'state.json')
PIDFILE = os.path.join(bugfile.BUGS, 'bugreport.pid')
LOG = os.path.join(bugfile.BUGS, 'bugreport.log')

TB_START = 'Traceback (most recent call last):'
RE_FRAME = re.compile(r'^\s*File "([^"]+)", line (\d+), in (\S+)')
RE_EXC = re.compile(r'^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Failure|Fault)|[A-Za-z_][\w.]*Error)\b:?\s?(.*)$')
RE_STAMP = re.compile(r'(\d\d)-(\d\d)-(\d{4}) (\d\d:\d\d:\d\d)')
RE_BOOT = re.compile(r'Server is booting us out \((\d+)\):\s*(.*)')
RE_EJECT = re.compile(r'Client \(([\d.]+):\d+, \d+\): Ejecting client \((\d+)\):\s*(.*)')
RE_ANSI = re.compile(r'\x1b\[[0-9;]*m|\[[0-9;]*m')


def log(msg):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 2 << 20:
            os.replace(LOG, LOG + '.old')
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%m-%d %H:%M:%S'), msg))
    except OSError:
        pass


def norm(s):
    """A message with its ids, numbers, hex and paths taken out, so the same bug always gets the same signature."""
    s = RE_ANSI.sub('', s)
    s = re.sub(r'0x[0-9a-fA-F]+', 'X', s)
    s = re.sub(r'[A-Za-z]:\\[^\s"\']+|/[\w./-]+/', '', s)
    s = re.sub(r'\d+(\.\d+)?', 'N', s)
    return ' '.join(s.split())[:140]


def stamp_of(line):
    """'11-21-2026 02:49:51' or '[2026-11-21 20:53:37]' in a log line -> 'YYYY-MM-DD HH:MM:SS'."""
    m = RE_STAMP.search(line)
    if m:
        return '%s-%s-%s %s' % (m.group(3), m.group(1), m.group(2), m.group(4))
    m = re.search(r'(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)', line)
    return '%s %s' % m.groups() if m else ''


# ---------------------------------------------------------------- the bot run each client log belongs to

def run_tag(path):
    m = re.match(r'walk-(.+?)(?:-events)?\.(?:err|log|jsonl)$', os.path.basename(path))
    return m.group(1) if m else ''


def prc_of(tag):
    """pbots' low-memory settings page the run loaded (walk-<tag>.prc from Start-BugReport), or ''."""
    try:
        with open(os.path.join(HARNESS, 'walk-%s.prc' % tag), encoding='utf-8-sig') as f:
            return f.read().strip()
    except OSError:
        return ''


def pirate_of(tag):
    """Who the run plays as, as the runner wrote it next to the run's logs (Start-BugReport in HiddenDesktop.ps1): a test
    account name, or for a player bot its pirate id + name (never a bot's account login: that login is its credential)."""
    try:
        with open(os.path.join(HARNESS, 'walk-%s.acct' % tag), encoding='utf-8-sig') as f:
            return f.read().strip()
    except OSError:
        return os.environ.get('BUG_PIRATE', '')


def run_context(tag, when_epoch=None):
    """where / last 30 events / screenshot for a client bug, from that run's events file."""
    ev = os.path.join(HARNESS, 'walk-%s-events.jsonl' % tag)
    lines, area, pos = [], '', None
    try:
        with open(ev, 'rb') as f:
            f.seek(max(0, os.path.getsize(ev) - (400 << 10)))
            tail = f.read().decode('utf-8', 'replace').splitlines()[1:]
    except OSError:
        tail = []
    for ln in tail:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if when_epoch and e.get('t', 0) > when_epoch + 5:
            break
        lines.append(ln)
        if e.get('area'):
            area = e['area'][2] if len(e['area']) > 2 else str(e['area'])
        p = _pos(e)
        if p:
            pos = p
    where = area + (' at (%.0f, %.0f)' % pos if pos else '')
    return where, lines[-30:], nearest_shot(when_epoch)


def nearest_shot(when_epoch):
    if not when_epoch:
        return ''
    best = None
    for p in glob.glob(os.path.join(HARNESS, 'shots', '**', '*.png'), recursive=True):
        try:
            d = abs(os.path.getmtime(p) - when_epoch)
        except OSError:
            continue
        if d <= 120 and (best is None or d < best[0]):
            best = (d, p)
    return best[1] if best else ''


RESTARTS = []


def restart_epochs():
    """When each server program last started (the first stamp in each log and its .prev copy). A kick within 3 minutes
    before a start is the restart itself (sink's FORCE restarts), not a bug."""
    out = []
    if SERVER_LOGS == '-':
        return out
    for n in SERVER_FILES:
        for name in (n, n.replace('.log', '.prev.log')):
            try:
                with open(os.path.join(SERVER_LOGS, name), 'rb') as f:
                    e = epoch_of(stamp_of(RE_ANSI.sub('', f.read(400).decode('utf-8', 'replace'))))
            except OSError:
                continue
            if e:
                out.append(e)
    return out


def restart_kick(when):
    e = epoch_of(when)
    return bool(e) and any(r - 180 <= e <= r + 60 for r in RESTARTS)


def epoch_of(stamp):
    try:
        return time.mktime(time.strptime(stamp, '%Y-%m-%d %H:%M:%S'))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- reading only new lines

class Reader:
    """New complete lines of a file since the last scan. A rotated or shrunk file is read again from the start; a file
    first seen before this watcher started (old history) is read from its end."""

    def __init__(self, state, started):
        self.state, self.started = state.setdefault('files', {}), started
        self.sizes, self.prev_n = {}, {}

    def new_lines(self, path, prev_path=None):
        try:
            size, mtime = os.path.getsize(path), os.path.getmtime(path)
        except OSError:
            return []
        st = self.state.get(path)
        if st is None and mtime < self.started - 120:
            self.state[path] = {'off': size, 'fp': '', 'mt': mtime}      # old history: start at its end, read nothing
            return []
        if st is not None and size == st['off'] and mtime == st.get('mt'):
            return []                                                     # unchanged: not even opened
        try:
            with open(path, 'rb') as f:
                fp = f.read(FP_BYTES).hex()
        except OSError:
            return []
        out = []
        if st is None:
            st = {'off': 0, 'fp': fp}
        elif size < st['off'] or (len(st['fp']) == 2 * FP_BYTES and st['fp'] != fp):
            # rotated by a restart: the old copy is now prev_path (ai.log -> ai.prev.log); finish its tail first
            if prev_path:
                out = [t for t, n in self._read(prev_path, st['off'])[0]]
            st = {'off': 0, 'fp': fp}
        got, st['off'] = self._read(path, st['off'])
        st['fp'], st['mt'] = fp, mtime
        self.state[path] = st
        self.sizes[path], self.prev_n[path] = [n for t, n in got], len(out)
        return out + [t for t, n in got]

    def hold(self, path, index):
        """Give lines[index:] back (an unfinished traceback): the next scan reads them again."""
        index -= self.prev_n.get(path, 0)
        if index >= 0:
            self.state[path]['off'] -= sum(self.sizes.get(path, [])[index:])

    def _read(self, path, off):
        try:
            with open(path, 'rb') as f:
                f.seek(off)
                data = f.read(READ_CAP)
        except OSError:
            return [], off
        cut = data.rfind(b'\n')
        if cut < 0:
            return [], off
        raw = data[:cut + 1].split(b'\n')[:-1]
        return [(r.decode('utf-8', 'replace').rstrip('\r'), len(r) + 1) for r in raw], off + cut + 1


def tracebacks(lines):
    """[(start index, end index, frames, exception line)] for each complete traceback in lines."""
    out, i = [], 0
    while i < len(lines):
        if TB_START not in lines[i]:
            i += 1
            continue
        j, frames, exc = i + 1, [], None
        while j < len(lines) and j - i < 400:
            s = RE_ANSI.sub('', lines[j])
            m = RE_FRAME.match(s)
            if m:
                frames.append(m.groups())
            elif s.startswith((' ', '\t')) or not s.strip():
                pass
            elif TB_START in s:
                break
            else:
                exc = s.strip()
                break
            j += 1
        if exc is not None:
            out.append((i, j, frames, exc))
            i = j + 1
        else:
            # cut off at the end of what is written so far: Reader.hold makes the next scan read it again
            out.append((i, None, frames, None))
            break
    return out


def tb_key(frames, exc):
    m = RE_EXC.match(exc)
    etype, msg = (m.group(1), m.group(2)) if m else (exc.split(':')[0][:60], exc)
    last = frames[-1] if frames else ('?', '?', '?')
    return etype, last, '%s in %s:%s: %s' % (etype, os.path.basename(last[0].replace('\\', '/')), last[2], norm(msg))


def is_harness(path):
    p = path.replace('\\', '/').lower()
    b = os.path.basename(p)
    return any(h in p for h in HARNESS_HINTS) or b.startswith('s_')


RE_CXX = re.compile(r'at line \d+ of \S+\.(cxx|cpp|h|I)\b')
_tiny = {}


def tiny_run(path):
    """A bot game on TinyPanda, the software renderer (low-memory runs). The boys never use it, so a Panda C++
    assertion in such a run is ours (bulbs 11-22: MEAS1's renderFrame assert in geomVertexArrayData.cxx)."""
    if path not in _tiny:
        try:
            with open(path, 'rb') as f:
                _tiny[path] = b'Default graphics pipe is Tiny' in f.read(65536)
        except OSError:
            return False
    return _tiny[path]


# ---------------------------------------------------------------- the three sources

def scan_client(reader, path, found):
    lines = reader.new_lines(path)
    if not lines:
        return
    tag = run_tag(path)
    tbs = tracebacks(lines)
    if tbs and tbs[-1][1] is None and time.time() - os.path.getmtime(path) < 300:
        reader.hold(path, tbs[-1][0])      # unfinished traceback while the game still writes: read it next scan
        tbs = tbs[:-1]
    last_sig = None
    for i, j, frames, exc in tbs:
        exc = exc or '(the traceback was cut off: the game closed)'
        etype, last, key = tb_key(frames, exc)
        if key == last_sig:        # Panda prints a task's traceback twice (the task, then the main loop)
            continue
        last_sig = key
        when = stamp_of(' '.join(lines[max(0, i - 3):i + 1][::-1])) or time.strftime('%Y-%m-%d %H:%M:%S',
                                                                                     time.localtime(os.path.getmtime(path)))
        bot = is_harness(last[0])
        where, evs, shot = run_context(tag, epoch_of(when))
        what = ('The bot\'s own code hit an error (%s in %s). The game is fine; our bot needs fixing.'
                if bot else 'The game hit an error (%s in %s) while the bot was playing.') % (
            etype, last[2])
        prc = prc_of(tag)
        if not bot and RE_CXX.search(exc) and tiny_run(path):
            bot = True
            what = ('The software renderer our low-memory bot games use (TinyPanda) failed (%s in %s). Real players '
                    'never use it; our bot setup needs fixing.') % (etype, last[2])
        elif not bot and prc:
            # bulbs 11-22: strip-gl.prc's stand-in textures lose their names, so game code that looks a texture up
            # by name fails (generateShirtSets). Its own key: the same error in a normal run is still filed GAME.
            bot = True
            key = 'stripped ' + key
            what = ('The game hit an error (%s in %s) in a low-memory bot game (%s: stand-in textures and other '
                    'shortcuts real players never have). Our bot setup needs fixing; if a normal bot game hits the '
                    'same error it is filed again as a GAME bug.') % (etype, last[2], os.path.basename(prc))
        found.append(dict(kind='traceback', key='client ' + key, tag='BOT' if bot else 'GAME', what=what, where=where,
                          pirate=pirate_of(tag), source='bot game %s (%s)' % (
                              tag, os.path.basename(path)), tb='\n'.join(lines[i:(j if j is not None else i + 60) + 1]),
                          events=evs, shot=shot, when=when))
    last_lost = -99
    for n, ln in enumerate(lines):
        m = RE_BOOT.search(ln)
        lost = 'Lost connection to gameserver' in ln
        if not (m or lost) or n - last_lost < 30:
            continue
        last_lost = n
        if not m:      # the boot line comes just before the lost-connection lines
            for back in lines[max(0, n - 6):n][::-1]:
                m = RE_BOOT.search(back) or m
        code, why = (m.group(1), m.group(2).strip()) if m else ('', '')
        when = stamp_of(ln) or time.strftime('%Y-%m-%d %H:%M:%S')
        if restart_kick(when):
            log('restart kick, not filed: %s %s' % (os.path.basename(path), when))
            continue
        where, evs, shot = run_context(tag, epoch_of(when))
        what = ('The server kicked the pirate out of the game (code %s: %s).' % (code, why) if code else
                'The pirate lost its connection to the game server and was sent back to the start.')
        found.append(dict(kind='disconnect', key='client %s' % ('booted %s %s' % (code, norm(why)) if code
                                                               else 'lost connection'),
                          tag='GAME', what=what, where=where, pirate=pirate_of(tag),
                          source='bot game %s (%s)' % (tag, os.path.basename(path)),
                          tb='\n'.join(lines[max(0, n - 8):n + 3]), events=evs, shot=shot, when=when))


def scan_server(reader, name, found):
    path = os.path.join(SERVER_LOGS, name)
    prev = os.path.join(SERVER_LOGS, name.replace('.log', '.prev.log'))
    lines = reader.new_lines(path, prev)
    if not lines:
        return
    proc = name.split('.')[0]
    tbs = tracebacks(lines)
    if tbs and tbs[-1][1] is None:
        reader.hold(path, tbs[-1][0])
        tbs = tbs[:-1]
    for i, j, frames, exc in tbs:
        etype, last, key = tb_key(frames, exc)
        when = stamp_of(' '.join(lines[max(0, i - 3):i + 1][::-1])) or time.strftime('%Y-%m-%d %H:%M:%S')
        found.append(dict(kind='traceback', key='%s %s' % (proc, key), tag='GAME',
                          what='The %s server hit an error (%s in %s). Pirates near it may have seen something break '
                               'or not happen.' % (proc.upper() if proc == 'ai' else proc, etype, last[2]),
                          where='server (%s)' % name, source='server %s' % name, tb='\n'.join(lines[i:j + 1]),
                          when=when))
    for ln in lines:
        m = RE_EJECT.search(RE_ANSI.sub('', ln))
        if not m:
            continue
        ip, code, why = m.groups()
        if restart_kick(stamp_of(ln)):
            continue
        who ='a bot game on this PC' if ip.startswith('127.') else 'a family PC'
        found.append(dict(kind='disconnect', key='astrond eject %s %s' % (code, norm(why)), tag='GAME',
                          what='The server kicked a pirate out of the game (code %s: %s).' % (code, why.strip()),
                          where='server (%s), %s' % (name, who), source='server %s' % name,
                          tb=RE_ANSI.sub('', ln).strip(), when=stamp_of(ln) or time.strftime('%Y-%m-%d %H:%M:%S')))


def _pos(e):
    for k in ('pos', 'la', 'frm'):
        v = e.get(k)
        if isinstance(v, (list, tuple)) and len(v) >= 2 and all(isinstance(x, (int, float)) for x in v[:2]):
            return (float(v[0]), float(v[1]))
    return None


class StuckWatch:
    """Per events file: the last point of progress (anchor). Progress = moved 50 ft from the anchor, a new quest step
    (q or its task state), a new script stage, or a PASS. 10 minutes of events without progress = stuck, filed once
    per anchor."""

    def __init__(self, state):
        self.files = {}
        self.done = state.setdefault('stuck', {})

    def scan(self, path, found):
        try:
            size, mtime = os.path.getsize(path), os.path.getmtime(path)
        except OSError:
            return
        if time.time() - mtime > ACTIVE_SECS:
            self.files.pop(path, None)
            return
        f = self.files.get(path)
        if f is None or size < f['off']:
            f = self.files[path] = dict(off=0, anchor=None, ring=collections.deque(maxlen=30), area='', pos=None,
                                        q=None, stage=None, tstate=None, last_t=None)
        try:
            with open(path, 'rb') as fh:
                fh.seek(f['off'])
                data = fh.read(READ_CAP)
        except OSError:
            return
        cut = data.rfind(b'\n')
        if cut < 0:
            return
        f['off'] += cut + 1
        for ln in data[:cut + 1].decode('utf-8', 'replace').splitlines():
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            t = e.get('t')
            if not isinstance(t, (int, float)):
                continue
            if t < 1e9:
                # a run-relative time (FLAGSHIP1's STAGE line said t=54): it still counts as progress, at the last real
                # clock time in this file; never the anchor time itself (bulbs 11-22: 29922675 minutes stuck)
                if f['last_t'] is None:
                    continue
                t = f['last_t']
            f['last_t'] = t
            f['ring'].append(ln)
            if e.get('area'):
                f['area'] = e['area'][2] if len(e['area']) > 2 else str(e['area'])
            p = _pos(e)
            if p:
                f['pos'] = p
            moved = False
            if e.get('q') and e['q'] != f['q']:
                f['q'], moved = e['q'], True
            if e.get('ts') is not None and e.get('ev') == 'heartbeat':
                ts = json.dumps(e['ts'], sort_keys=True)
                if ts != f['tstate']:
                    f['tstate'], moved = ts, True
            if e.get('ev') == 'STAGE' and e.get('what') != f['stage']:
                f['stage'], moved = e.get('what'), True
            if e.get('ev') in ('PASS', 'start'):
                moved = True
            a = f['anchor']
            if a is None or moved or (p and a['pos'] and
                                      ((p[0] - a['pos'][0]) ** 2 + (p[1] - a['pos'][1]) ** 2) ** 0.5 >= STUCK_FT):
                f['anchor'] = dict(t=t, pos=p or f['pos'])
                continue
            if a['pos'] is None and p:
                a['pos'] = p
            if t - a['t'] >= STUCK_SECS:
                mark = '%s|%.2f' % (path, a['t'])
                if self.done.get(path) == mark:
                    continue
                self.done[path] = mark
                tag = run_tag(path)
                pos = f['pos']
                grid = '(%d, %d)' % (pos[0] // 100 * 100, pos[1] // 100 * 100) if pos else 'no position'
                where = f['area'] + (' at (%.0f, %.0f)' % pos if pos else '')
                found.append(dict(
                    kind='stuck', key='stuck %s q=%s stage=%s near %s' % (f['area'] or '?', f['q'] or '-',
                                                                         f['stage'] or '-', grid),
                    tag='BOT', what='The pirate stood still%s for %d minutes and did not finish its quest step '
                                    '(%s). Something may block the way, or the bot does not know what to do next.' % (
                        ' on ' + f['area'] if f['area'] else '', int((t - a['t']) // 60), f['q'] or 'none'),
                    where=where, pirate=pirate_of(tag), source='bot game %s (%s)' % (
                        tag, os.path.basename(path)), events=list(f['ring']), shot=nearest_shot(t),
                    when=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t))))


# ---------------------------------------------------------------- one scan, the loop, one copy only

def load_state():
    try:
        with open(STATE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f)
    os.replace(tmp, STATE)


def scan(state, reader, stuck):
    found = []
    RESTARTS[:] = restart_epochs()
    for p in sorted(glob.glob(os.path.join(HARNESS, 'walk-*.err')) + glob.glob(os.path.join(HARNESS, 'walk-*.log'))):
        try:
            scan_client(reader, p, found)
        except Exception as e:  # one bad file never stops the watcher
            log('client %s: %r' % (p, e))
    if SERVER_LOGS != '-':
        for n in SERVER_FILES:
            try:
                scan_server(reader, n, found)
            except Exception as e:
                log('server %s: %r' % (n, e))
    for p in glob.glob(os.path.join(HARNESS, 'walk-*-events.jsonl')):
        try:
            stuck.scan(p, found)
        except Exception as e:
            log('stuck %s: %r' % (p, e))
    for b in found:
        sig, path, count = bugfile.report(**b)
        log('%s x%d %s' % (b['kind'], count, sig))
    save_state(state)
    return found


def alive(pid):
    if sys.platform != 'win32':
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        buf = ctypes.create_unicode_buffer(520)
        n = ctypes.c_ulong(520)
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
        return code.value == 259 and 'python' in buf.value.lower()   # STILL_ACTIVE and a python: a reused pid is not us
    finally:
        k.CloseHandle(h)


def main():
    once = '--once' in sys.argv
    os.makedirs(os.path.join(bugfile.BUGS, 'inbox'), exist_ok=True)
    if not once:
        try:
            if alive(int(open(PIDFILE).read().strip())):
                return 0
        except (OSError, ValueError):
            pass
        with open(PIDFILE, 'w') as f:
            f.write(str(os.getpid()))
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x40)  # Idle
        log('watcher up, pid %d, harness %s, server logs %s' % (os.getpid(), HARNESS, SERVER_LOGS))
    state = load_state()
    reader, stuck = Reader(state, time.time()), StuckWatch(state)
    while True:
        found = scan(state, reader, stuck)
        if once:
            for b in found:
                print('%s %s %s' % (b['kind'], b['tag'], bugfile.sig_of(b['kind'], b['key'])))
            return 0
        time.sleep(INTERVAL)


if __name__ == '__main__':
    sys.exit(main())
