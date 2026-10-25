"""Monsters' steps up and down, frame by frame, on the dev build (re/NOTES.md "Monster steps"): Koh
waits turn after turn while the monster most likely to change height (heading onto a different
height, not next to Koh) is tracked through the snapshot slots (its record from +0x88: height, +0x90
lift, state, step counter, sprite sequence and flags; its position object; the phase word 0x80083462).
Any step that changes its height is printed.

    python test_encounters.py 2=21/1        (then launch, ride up from slot 4 to 2F)
    python monster_steps.py [SPECIES]       (default 21, Pulunpa)
"""
import struct, sys
from psx import Game
import attach
import melee_measure as M

SP = int(sys.argv[1]) if len(sys.argv) > 1 else 21
gg = Game(); attach.g = gg


def h88(a):
    h = gg.u16(a + 0x88)
    return h - 0x10000 if h & 0x8000 else h


def bank_of(u):
    spr = u + 0xD4
    bank = gg.u32(gg.u32(spr + 0x28))
    n = gg.u32(bank + 4)
    table = gg.read(gg.u32(bank), n * 4)
    return sorted((struct.unpack_from('<I', table, i * 4)[0], i) for i in range(n))


def seq_of(bank, ptr):
    best = None
    for s, i in bank:
        if s <= ptr:
            best = (i, (ptr - s) // 8)
        else:
            break
    return best


def rf(addr, n, f):
    return bytes.fromhex(gg.cmd('read_frame_ram', addr='0x%08X' % addr, len=n, frame=f)['hex'])


def dump(u, pm, f0, f1):
    bank = bank_of(u)
    prev = None
    for f in range(f0, f1):
        t = rf(u + 0x88, 0x70, f)
        h = struct.unpack_from('<h', t, 0)[0]
        off = struct.unpack_from('<i', t, 8)[0] / 65536
        st, sub = t[0x12], t[0x13]
        cnt = struct.unpack_from('<h', t, 0x0E)[0]
        seq = seq_of(bank, struct.unpack_from('<I', t, 0x4C)[0])
        x, z, y = struct.unpack('<iii', rf(pm, 12, f))
        sflags = struct.unpack_from('<H', t, 0x4C + 0x14)[0]
        glob = struct.unpack_from('<H', rf(0x80083460, 4, f), 2)[0]
        key = (st, sub, seq, round(x / 65536), round(z / 65536), round(y / 65536), round(off), h, sflags, glob)
        if key != prev:
            print('%4d st %02x.%02x %-9s cnt %3d h %4d x %7.1f z %7.1f y %6.1f off %6.1f spr %04x 3462 %04x' % (
                f - f0, st, sub, seq, cnt, h, x / 65536, z / 65536, y / 65536, off, sflags, glob), flush=True)
            prev = key


M.setup_familiar(gg)
got = 0
LAST = {}
for turn in range(60):
    us = M.units(gg)
    mons = [u for u in us if u['sp'] == SP and not (u['f14'] & 0x4000) and u['hp'] > 0]
    for u in mons:
        M.calm(gg, u['addr'])
    M.tough(gg)
    m = attach.tile_map()

    koh = us[0]

    def score(u):
        p = (u['x'], u['y'])
        if max(abs(p[0] - koh['x']), abs(p[1] - koh['y'])) <= 1:
            return -9
        sc = 0
        q = LAST.get(u['addr'])
        if q and q != p:
            nx = (2 * p[0] - q[0], 2 * p[1] - q[1])
            if nx in m and m[nx] < 100 and m[nx] != m.get(p) and abs(m[nx] - m.get(p, 0)) <= 32:
                sc += 4
            sc += 1
        sc += sum(1 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if (p[0] + dx, p[1] + dy) in m and m[(p[0] + dx, p[1] + dy)] < 100 and m[(p[0] + dx, p[1] + dy)] != m.get(p))
        return sc
    pick = sorted(mons, key=score, reverse=True)[:1]
    for u in mons:
        LAST[u['addr']] = (u['x'], u['y'])
    slots = []
    for k, u in enumerate(pick):
        pm = gg.u32(u['addr'] - 0x18)
        gg.cmd('set_snapshot', slot=2 * k, addr='0x%08X' % (u['addr'] + 0x88), size=128)
        gg.cmd('set_snapshot', slot=2 * k + 1, addr='0x%08X' % pm, size=16)
        slots.append((u['addr'], pm, h88(u['addr']), (u['x'], u['y'])))
    gg.cmd('set_snapshot', slot=2, addr='0x80083460', size=16)
    f0 = gg.frame()
    t0 = gg.u16(0x8008347E)
    gg.hold('triangle', 'circle'); gg.wait_frames(10); gg.release()
    for _ in range(60):
        gg.wait_frames(20)
        if gg.u16(0x8008347E) != t0 and (gg.u16(0x80083462) & 0x7E1A) == 0:
            break
    f1 = gg.frame()
    res = [(hex(a), h, p, h88(a), attach.unit_grid(a)) for a, pm, h, p in slots]
    print('turn', turn, res, flush=True)
    for a, pm, h, p in slots:
        if h88(a) != h:
            print('== %s height %d -> %d' % (hex(a), h, h88(a)), flush=True)
            dump(a, pm, f0, min(f1, f0 + 300))
            got += 1
    if got >= 4:
        break
print('done', got, flush=True)
