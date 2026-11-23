"""Bug files for the player bots and the bug reporter (games, 11-22, PLAYERBOTS item 1). Stdlib only, any Python 3.
One file per bug: D:\\scratch\\lanes\\bugs\\inbox\\BUG-<sig>.md. A repeat bumps count + last seen and never makes a new file.
D:\\scratch\\lanes\\bugs\\BUGS.md is rebuilt from the files after every write: one line per open bug, newest first.
The bug file is the source of truth: its '- state:' line goes NEW -> READY -> LIVE -> PROVEN (bulbs, sink and the
retesting bot edit that line by hand, and '- patch:'); BUGS.md is only a view of it.
    import bugfile; bugfile.report('missing', 'npc Tia Dalma not in her shack', 'GAME', 'Tia Dalma is not there', ...)
Several processes can write at once (the bug reporter and every player bot): writes take bugs\\.lock."""
import os, re, json, time, hashlib, contextlib

BUGS = os.environ.get('BUGS_DIR', r'C:\PiratesBots\out\bugs')
KINDS = ('traceback', 'disconnect', 'stuck', 'missing', 'other')
STATES = ('NEW', 'READY', 'LIVE', 'PROVEN')
SEEN_KEEP = 10


def sig_of(kind, key):
    """kind-slug-hash: the slug is readable, the hash keeps two different keys with the same slug apart."""
    key = ' '.join(str(key).split())
    slug = re.sub(r'[^a-z0-9]+', '-', key.lower()).strip('-')[:40].strip('-')
    return '%s-%s-%s' % (kind, slug or 'x', hashlib.sha1(key.encode('utf-8')).hexdigest()[:6])


def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


@contextlib.contextmanager
def _lock():
    os.makedirs(os.path.join(BUGS, 'inbox'), exist_ok=True)
    path = os.path.join(BUGS, '.lock')
    t0 = time.time()
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            # a writer that died mid-write leaves the lock; nobody holds it for more than a second or two
            try:
                if time.time() - os.path.getmtime(path) > 60:
                    os.remove(path)
                    continue
            except OSError:
                pass
            if time.time() - t0 > 120:
                raise TimeoutError('bugs lock held for 2 minutes: ' + path)
            time.sleep(0.2)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _field(text, name):
    m = re.search(r'^- %s: (.*)$' % re.escape(name), text, re.M)
    return m.group(1).strip() if m else ''


def _set_field(text, name, value):
    return re.sub(r'^- %s: .*$' % re.escape(name), lambda m: '- %s: %s' % (name, value), text, count=1, flags=re.M)


def _block(lines):
    out = []
    for e in lines or []:
        s = e if isinstance(e, str) else json.dumps(e)
        out.append(s if len(s) <= 300 else s[:300] + ' ...')
    return '\n'.join(out)


def report(kind, key, tag, what, where='', pirate='', source='', tb='', events=None, shot='', when=None):
    """File one sighting. Returns (sig, path, count)."""
    assert kind in KINDS, kind
    tag = 'BOT' if str(tag).upper() == 'BOT' else 'GAME'
    sig = sig_of(kind, key)
    when = when or _now()
    path = os.path.join(BUGS, 'inbox', 'BUG-%s.md' % sig)
    seen = '- %s %s %s %s' % (when, source or '?', pirate or '', where or '')
    with _lock():
        if os.path.exists(path):
            text = open(path, encoding='utf-8').read()
            count = int(_field(text, 'count') or 0) + 1
            text = _set_field(text, 'count', str(count))
            text = _set_field(text, 'last', when)
            head, _, tail = text.partition('## Seen\n')
            rows = [r for r in tail.splitlines() if r.startswith('- ')]
            rows = (rows + [seen])[-SEEN_KEEP:]
            text = head + '## Seen\n' + '\n'.join(rows) + '\n'
        else:
            count = 1
            parts = ['# BUG-%s' % sig, '',
                     '- sig: %s' % sig, '- kind: %s' % kind, '- tag: %s' % tag, '- state: NEW', '- patch: ',
                     '- count: 1', '- first: %s' % when, '- last: %s' % when,
                     '- pirate: %s' % pirate, '- where: %s' % where, '- source: %s' % source,
                     '- key: %s' % ' '.join(str(key).split())[:300], '',
                     '## What happened', what, '']
            if shot:
                parts += ['## Picture', shot, '']
            if tb:
                parts += ['## Traceback', '```', tb.rstrip()[-6000:], '```', '']
            if events:
                parts += ['## Last bot events', '```', _block(events[-30:]), '```', '']
            parts += ['## Seen', seen, '']
            text = '\n'.join(parts)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        os.replace(tmp, path)
        rebuild()
    return sig, path, count


def rebuild():
    """BUGS.md from the inbox: open bugs (NEW, READY, LIVE) newest first, then the last 20 PROVEN."""
    inbox = os.path.join(BUGS, 'inbox')
    rows = []
    for n in os.listdir(inbox) if os.path.isdir(inbox) else []:
        if not (n.startswith('BUG-') and n.endswith('.md')):
            continue
        try:
            text = open(os.path.join(inbox, n), encoding='utf-8').read()
        except OSError:
            continue
        what = text.partition('## What happened\n')[2].split('\n', 1)[0].strip()
        state = (_field(text, 'state') or 'NEW').split()[0].upper()
        patch = _field(text, 'patch')
        rows.append((_field(text, 'last'), state, _field(text, 'tag'), _field(text, 'count'), what,
                     patch, n, _field(text, 'source')))
    rows.sort(reverse=True)
    open_rows = [r for r in rows if r[1] != 'PROVEN']
    done = [r for r in rows if r[1] == 'PROVEN'][:20]
    line = lambda r: '- %s %s x%s last %s | %s%s | %s | inbox/%s' % (
        r[1], r[2], r[3], r[0][5:16], r[4][:160], (' | patch ' + r[5]) if r[5] else '', r[7], r[6])
    out = ['# Open bugs (rebuilt from inbox/ by bugfile.py; edit the bug file, never this list)',
           '', 'Updated %s. %d open, newest first. State: NEW -> READY -> LIVE -> PROVEN. Tag: GAME or BOT.' % (
               _now(), len(open_rows)), '']
    out += [line(r) for r in open_rows] or ['(none)']
    out += ['', '## Proven (last 20)', ''] + ([line(r) for r in done] or ['(none)']) + ['']
    tmp = os.path.join(BUGS, 'BUGS.md.tmp')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out))
    os.replace(tmp, os.path.join(BUGS, 'BUGS.md'))
