"""Tiny client for the psxrecomp native debug server (TCP 4370, JSON lines).

Typical use:
    from psx import Game
    g = Game.launch()          # starts build-dev/Azure_Dreams.exe with the debug server
    g.wait_frames(600)
    g.tap('start')
    g.shot('title')            # re/shots/title.png
    ram = g.read(0x80000000, 0x200000)
"""
import json, os, socket, subprocess, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
EXE = os.path.join(ROOT, r"build-dev\Azure_Dreams.exe")
DISC = os.path.join(ROOT, r"disc\Azure Dreams (USA).cue")
VOICE_DISC = os.path.join(ROOT, r"disc\Azure Dreams (USA) (JP Voices).cue")   # build_voice_disc.py
BIOS = os.path.join(ROOT, "bios", "SCPH1001.BIN")
SHOTS = os.path.join(ROOT, r"re\shots")

# PS1 digital pad bits; the server wants the inverted (active-low) mask.
BTN = {
    'select': 0x0001, 'l3': 0x0002, 'r3': 0x0004, 'start': 0x0008,
    'up': 0x0010, 'right': 0x0020, 'down': 0x0040, 'left': 0x0080,
    'l2': 0x0100, 'r2': 0x0200, 'l1': 0x0400, 'r1': 0x0800,
    'triangle': 0x1000, 'circle': 0x2000, 'cross': 0x4000, 'square': 0x8000,
}


def mask(*names):
    m = 0
    for n in names:
        m |= BTN[n]
    return 0xFFFF & ~m


class Game:
    def __init__(self, port=4370, proc=None):
        self.proc = proc
        self.port = port
        self.sock = None
        self.buf = b''
        self.next_id = 1

    @classmethod
    def launch(cls, port=4370, extra_args=(), timeout=60, disc=DISC):
        args = [EXE, '--no-launcher', '--disc', disc, '--bios', BIOS,
                '--debug-port', str(port), *extra_args]
        proc = subprocess.Popen(args, cwd=os.path.dirname(EXE),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        g = cls(port, proc)
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                g.cmd('frame')
                return g
            except OSError:
                time.sleep(0.5)
        proc.kill()
        raise RuntimeError('debug server never came up')

    def cmd(self, name, **params):
        # The server answers exactly one request per connection, then closes it.
        rid = self.next_id
        self.next_id += 1
        msg = {'id': rid, 'cmd': name, **params}
        with socket.create_connection(('127.0.0.1', self.port), timeout=60) as s:
            s.sendall((json.dumps(msg) + '\n').encode())
            buf = b''
            while b'\n' not in buf:
                chunk = s.recv(1 << 20)
                if not chunk:
                    break
                buf += chunk
        line = buf.split(b'\n', 1)[0]
        if not line.strip():
            raise OSError(f'{name}: empty response')
        resp = json.loads(line)
        if not resp.get('ok', False):
            raise RuntimeError(f'{name}: {resp.get("error") or resp.get("err")}')
        return resp

    # --- time ---------------------------------------------------------------
    def frame(self):
        return self.cmd('frame')['frame']

    def wait_frames(self, n, poll=0.05):
        start = self.frame()
        while self.frame() - start < n:
            time.sleep(poll)

    def turbo(self, on=True):
        self.cmd('turbo', enabled=1 if on else 0)

    # --- input --------------------------------------------------------------
    def hold(self, *names):
        self.cmd('set_input', buttons=f'{mask(*names):04x}')

    def release(self):
        self.cmd('clear_input')

    def tap(self, *names, frames=4, gap=8):
        self.hold(*names)
        self.wait_frames(frames)
        self.release()
        self.wait_frames(gap)

    # --- memory -------------------------------------------------------------
    def read(self, addr, length):
        r = self.cmd('read_ram', addr=f'0x{addr:08X}', len=length)
        hexs = r.get('hex') or r.get('data')
        return bytes.fromhex(hexs)

    def write(self, addr, data):
        for i, b in enumerate(data):
            self.cmd('write_ram', addr=f'0x{addr + i:08X}', val=f'{b:02x}')

    def u8(self, a):
        return self.read(a, 1)[0]

    def u16(self, a):
        return int.from_bytes(self.read(a, 2), 'little')

    def u32(self, a):
        return int.from_bytes(self.read(a, 4), 'little')

    def ram(self):
        return self.read(0x80000000, 0x200000)

    # --- capture / state ----------------------------------------------------
    def shot(self, name):
        os.makedirs(SHOTS, exist_ok=True)
        path = os.path.join(SHOTS, name + '.png')
        for _ in range(20):
            try:
                self.cmd('screenshot', path=path)
                return path
            except RuntimeError as e:
                if 'display disabled' not in str(e):
                    raise
                self.wait_frames(5)  # mid scene transition
        return None

    def save_state(self, slot):
        self.cmd('savestate', op='save', slot=slot)
        time.sleep(0.5)

    def load_state(self, slot):
        self.cmd('savestate', op='load', slot=slot)
        time.sleep(0.5)

    def quit(self):
        try:
            self.cmd('quit')
        except Exception:
            pass
        if self.proc:
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
