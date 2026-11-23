# pbots (11-22): the PROTOCOL BOT prototype - talks Astron's client protocol straight to the server, no game.
# Hello, login on a bot account, ask for the avatar list, measure the process, hang up. It never picks an avatar
# (nothing of the bot ever enters the world from here) and it only ever uses a bot login from accounts.local.json
# (never claude1/claude2, never Host's). The login name is a credential: this file prints its slot number only.
# Run from PowerShell: & C:\Panda3D-1.11.0-x64\python\ppython.exe C:\PiratesBots\pbot\proto_login.py
# Output: C:\PiratesBots\out\pbots\proto-login.json (memory at three points + the message trace, no login name).
import os, sys, json, time, socket, struct, hmac, ctypes, traceback
from ctypes import wintypes

CLIENT = r'C:\PiratesOnline\pirates-online-classic'
HOST, PORT = '127.0.0.1', 7100                     # config/personal.prc server-port 7100 (wins over general.prc 6667)
VERSION = 'pirates-dev'                            # config/general.prc server-version
CSM_DOID = 4665                                    # ClientServicesManager, a DistributedObjectGlobal
LOGIN_KEY = b'cd09ed406383f3d3ebb62b9ce23d41dd'    # the client's own login hmac key (pirates/uberdog/ClientServicesManager.py)
# Astron client message numbers (direct/distributed/MsgTypes.py in the Panda install)
CLIENT_HELLO, CLIENT_HELLO_RESP, CLIENT_DISCONNECT, CLIENT_EJECT, CLIENT_HEARTBEAT = 1, 2, 3, 4, 5
CLIENT_OBJECT_SET_FIELD, CLIENT_OBJECT_SET_FIELDS, CLIENT_OBJECT_LEAVING, CLIENT_OBJECT_LOCATION = 120, 121, 132, 140
CLIENT_ENTER_OBJECT_REQUIRED, CLIENT_ENTER_OBJECT_REQUIRED_OTHER = 142, 143
CLIENT_ADD_INTEREST, CLIENT_DONE_INTEREST_RESP = 200, 204
OUT = r'C:\PiratesBots\out\pbots\proto-login.json'
SLOT = int(os.environ.get('PBOT_SLOT', '1'))


class _PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t), ('PrivateUsage', ctypes.c_size_t)]


_k32 = ctypes.windll.kernel32; _k32.GetCurrentProcess.restype = wintypes.HANDLE
_psapi = ctypes.windll.psapi
_psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
_psapi.GetProcessMemoryInfo.restype = wintypes.BOOL


def proc_mem():
    pmc = _PMC(); pmc.cb = ctypes.sizeof(pmc)
    # argtypes matter: without them the -1 pseudo-handle goes over as a 32-bit int and the call quietly returns zeros
    if not _psapi.GetProcessMemoryInfo(_k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        return {'error': 'GetProcessMemoryInfo failed'}
    mb = 1048576.0
    return {'ws_mb': round(pmc.WorkingSetSize / mb, 1), 'private_mb': round(pmc.PrivateUsage / mb, 1),
            'peak_ws_mb': round(pmc.PeakWorkingSetSize / mb, 1)}


trace = []
def log(what, **kw):
    kw['t'] = round(time.time() - T0, 2); kw['what'] = what
    trace.append(kw); print(json.dumps(kw, default=str))


class Recorder:
    """Any field the server sends on an object lands here by name (dclass.receiveUpdate calls the method)."""
    def __init__(self, doId, dclass):
        self.doId, self.dclass, self.got = doId, dclass, []
    def __getattr__(self, name):
        def f(*args):
            self.got.append((name, args))
            log('field', doId=self.doId, dclass=self.dclass.getName(), field=name,
                args=[(a if not isinstance(a, (bytes, bytearray)) else '<%d bytes>' % len(a)) for a in args][:6])
        return f


def main():
    global T0
    T0 = time.time()
    mem0 = proc_mem()
    accounts = json.load(open(os.path.join(os.path.dirname(__file__), 'accounts.local.json')))
    bot = [b for b in accounts['bots'] if b['slot'] == SLOT][0]
    token = bot['login']
    if token in ('claude1', 'claude2', 'Host', 'Player1', 'Player2', 'Player3') or not token.startswith('pb'):
        raise SystemExit('REFUSED: slot %d is not a bot login' % SLOT)
    from panda3d.core import Datagram, DatagramIterator, Filename
    from panda3d.direct import DCFile
    dc = DCFile()
    # otp.dc first: pirates.dc inherits from it (the prc lists pirates.dc then otp.dc, but ConfigVariableList hands them
    # back last-first). Field numbers depend on this order, so it must match the game's.
    for f in ('otp.dc', 'pirates.dc'):
        if not dc.read(Filename.fromOsSpecific(os.path.join(CLIENT, 'astron', 'dclass', f))):
            raise SystemExit('cannot read ' + f)
    csm = dc.getClassByName('ClientServicesManager')
    mem1 = proc_mem()
    log('dc-loaded', classes=dc.getNumClasses(), hash=dc.getHash(), mem=mem1)
    objs = {CSM_DOID: Recorder(CSM_DOID, csm)}

    s = socket.create_connection((HOST, PORT), timeout=10)
    def send(dg):
        b = bytes(dg.getMessage()) if hasattr(dg, 'getMessage') else dg
        s.sendall(struct.pack('<H', len(b)) + b)
    def recv():
        hdr = b''
        while len(hdr) < 2:
            c = s.recv(2 - len(hdr))
            if not c: raise ConnectionError('closed')
            hdr += c
        n = struct.unpack('<H', hdr)[0]
        body = b''
        while len(body) < n:
            c = s.recv(n - len(body))
            if not c: raise ConnectionError('closed')
            body += c
        return Datagram(body)

    hello = Datagram(); hello.addUint16(CLIENT_HELLO); hello.addUint32(dc.getHash()); hello.addString(VERSION)
    send(hello); log('sent', msg='CLIENT_HELLO', version=VERSION)
    state = {'login': None, 'avatars': None}
    deadline = time.time() + 40
    lastHb = time.time()
    while time.time() < deadline:
        s.settimeout(max(0.5, deadline - time.time()))
        try:
            dg = recv()
        except socket.timeout:
            break
        di = DatagramIterator(dg)
        mt = di.getUint16()
        if mt == CLIENT_HELLO_RESP:
            log('recv', msg='CLIENT_HELLO_RESP')
            key = hmac.new(LOGIN_KEY, digestmod='md5'); key.update(token.encode('utf-8'))
            send(csm.clientFormatUpdate('login', CSM_DOID, [token, '', key.hexdigest()]))
            log('sent', msg='login', on='ClientServicesManager', slot=SLOT)
        elif mt == CLIENT_EJECT:
            code = di.getUint16(); why = di.getString()
            log('recv', msg='CLIENT_EJECT', code=code, why=why); break
        elif mt == CLIENT_OBJECT_SET_FIELD:
            doId = di.getUint32()
            rec = objs.get(doId)
            if rec is None:
                log('recv', msg='SET_FIELD on unknown object', doId=doId); continue
            before = len(rec.got)
            rec.dclass.receiveUpdate(rec, di)
            for name, args in rec.got[before:]:
                if name == 'acceptLogin':
                    state['login'] = 'accepted'
                    send(csm.clientFormatUpdate('requestAvatars', CSM_DOID, []))
                    log('sent', msg='requestAvatars')
                elif name == 'setAvatars':
                    state['avatars'] = len(args[0]) if args else 0
                    log('avatars', count=state['avatars'], note='slots in use on the bot account (none picked, ever, from here)')
                    deadline = min(deadline, time.time() + 1.5)   # one more pass for stragglers, then hang up
        elif mt in (CLIENT_ENTER_OBJECT_REQUIRED, CLIENT_ENTER_OBJECT_REQUIRED_OTHER):
            doId = di.getUint32(); parent = di.getUint32(); zone = di.getUint32(); clsId = di.getUint16()
            cls = dc.getClass(clsId)
            objs[doId] = Recorder(doId, cls)
            log('recv', msg='ENTER_OBJECT', doId=doId, dclass=cls.getName(), parent=parent, zone=zone)
        elif mt == CLIENT_OBJECT_LEAVING:
            log('recv', msg='OBJECT_LEAVING', doId=di.getUint32())
        elif mt == CLIENT_DONE_INTEREST_RESP:
            log('recv', msg='DONE_INTEREST_RESP', context=di.getUint32(), interest=di.getUint16())
        else:
            log('recv', msg='other', type=mt, size=dg.getLength())
        if time.time() - lastHb > 10:
            hb = Datagram(); hb.addUint16(CLIENT_HEARTBEAT); send(hb); lastHb = time.time()
    mem2 = proc_mem()
    try:
        bye = Datagram(); bye.addUint16(CLIENT_DISCONNECT); send(bye)
    except Exception:
        pass
    s.close()
    verdict = 'PASS' if state['login'] == 'accepted' and state['avatars'] is not None else 'FAIL'
    out = {'verdict': verdict, 'login': state['login'], 'avatar_slots_in_use': state['avatars'], 'slot': SLOT,
           'mem_start': mem0, 'mem_after_dc': mem1, 'mem_end': mem2, 'python_modules': len(sys.modules), 'trace': trace}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, 'w'), indent=1, default=str)
    print(verdict, 'login=%s avatars=%s mem start %s / after dc %s / end %s' % (state['login'], state['avatars'], mem0, mem1, mem2))
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(2)
