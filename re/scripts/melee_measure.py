"""Measure monsters' melee swings on the dev build: Koh walks next to a monster of each species
and waits until it swings at him; each swing's sub-states and sequences (timeline.Tracker, frame
exact) and the hit roll (the random draw from FUN_8009C93C, write trace with frame numbers) are
recorded. The blow is the first write to Koh's record made by FUN_8009C12C (it applies the hit
the roll in FUN_8009C93C prepared at the swing's start; it writes even on a miss).

    python melee_measure.py run FLOOR=SP,SP,SP,SP [FLOOR=...]   (dev build closed: sets the floors up,
                                                               launches it, rides up from slot 4)
    python melee_measure.py here SP [SP ...]                     (dev build on a floor with them)

Results go to re/timelines/melee_<species>.txt and a summary line per swing:
    SP name: start -> sub-states [(sub, group, frames)], blow at +N, swing ends at +M
"""
import json
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'timelines')
SAVES = r'C:\Users\caran\AppData\Local\Temp\claude\c--CODE-AZURE-CLAUDE\44338550-65ba-4fae-a9af-74ccaaba251a\scratchpad\saves_copy'
RNG = 0x8008335C
KOH = 0x800834B8
HIT_LO, HIT_HI = 0x8009C12C, 0x8009C93C   # FUN_8009C12C applies the blow (writes the target's flags)


def g():
    from psx import Game
    return Game()


def units(gg):
    head = gg.u32(0x800814A8)
    u, out = head, []
    for _ in range(64):
        b = gg.read(u, 0x30)
        mo = gg.u32(u - 0x14)
        xy = gg.read(mo + 0x24, 2)
        out.append(dict(addr=u, sp=b[0x13], hp=b[0x28], x=xy[0], y=xy[1], f14=struct.unpack_from('<I', gg.read(u + 0x14, 4))[0]))
        u = gg.u32(u + 0x5C) + 0x20
        if u == head:
            break
    return out


def calm(gg, u):
    """No sleep or other status (slots +0x2C..+0x33, flags +0x1C 0x200/0x400/0x10/0x20)."""
    gg.write(u + 0x2C, bytes(8))
    f = struct.unpack('<I', gg.read(u + 0x1C, 4))[0]
    gg.write(u + 0x1C, struct.pack('<I', f & ~0x630))


def nap(gg, u):
    """Permanent sleep (status 1, value 0) for the familiar, so it stays out of the fight."""
    gg.write(u + 0x2C, bytes([1, 0]) + bytes(6))
    f = struct.unpack('<I', gg.read(u + 0x1C, 4))[0]
    gg.write(u + 0x1C, struct.pack('<I', f | 0x200))


def tough(gg):
    gg.write(KOH + 0x28, bytes([200, 200]))


def turn(gg, mon):
    """Koh waits a turn while the tracker and the write trace run; returns (rows, hit frames, f0)."""
    from timeline import Tracker
    t = Tracker(mon1=mon)
    # Snapshot slot 3: the monster's position object (pointer at unit - 0x18; x, z, y as 16.16 at
    # +0, +4, +8) for the lunge, and Koh's for the direction of the swing.
    motion = gg.u32(mon - 0x18)
    gg.cmd('set_snapshot', slot=3, addr='0x%08X' % motion, size=16)
    gg.cmd('wtrace_disarm_all')
    gg.cmd('wtrace_clear')
    gg.cmd('wtrace_arm', lo=hex(KOH), hi=hex(KOH + 0x130))
    f0 = gg.frame()
    t0 = gg.u16(0x8008347E)
    gg.hold('triangle', 'circle')
    gg.wait_frames(10)
    gg.release()
    for _ in range(60):
        gg.wait_frames(20)
        if gg.u16(0x8008347E) != t0 and (gg.u16(0x80083462) & 0x7E1A) == 0:
            break
    f1 = gg.frame()
    d = gg.cmd('wtrace_dump', count=4000)
    gg.cmd('wtrace_disarm_all')
    hits = [e.get('frame', 0) - f0 for e in d.get('entries', [])
            if HIT_LO <= (int(str(e.get('pc', '0')), 16) | 0x80000000) < HIT_HI]
    rows = t.dump(f0, min(f1, f0 + 1200), quiet=True)
    pos = {}
    for f, name, v in rows:
        if name == 'm1' and v['state'] == 0x11:
            pos = None
            break
    pos = {}
    want = sorted({f for f, name, v in rows if name == 'm1'})
    if want:
        lo, hi = want[0], want[-1] + 120
        for f in range(lo, min(hi, f0 + 1200)):
            r = gg.cmd('read_frame_ram', addr='0x%08X' % motion, len=12, frame=f)
            b = bytes.fromhex(r['hex'])
            x, z, y = struct.unpack('<iii', b)
            pos[f - f0] = (x / 65536.0, z / 65536.0, y / 65536.0)
    kx, kz = struct.unpack('<hh', gg.read(0x80083780 + 2, 2) + gg.read(0x80083780 + 6, 2))
    return rows, sorted(set(hits)), f0, pos, (kx, kz)


def swings(rows, hits, f0, pos=None, koh=None):
    """Each run of the monster's state 0x11: [(sub, seq, frames)], blow frame, end frame (from start)."""
    out = []
    cur = None
    for f, name, v in rows:
        if name != 'm1':
            continue
        if v['state'] == 0x11:
            if cur is None:
                cur = dict(start=f - f0, parts=[])
            cur['parts'].append([f - f0, v['sub'], v['seq']])
        elif cur is not None:
            cur['end'] = f - f0
            out.append(cur)
            cur = None
    if cur is not None:
        cur['end'] = None
        out.append(cur)
    for s in out:
        blow = [h for h in hits if h >= s['start'] and (s['end'] is None or h <= s['end'])]
        s['blow'] = blow[0] - s['start'] if blow else None
        s['parts'] = [[p[0] - s['start'], p[1], p[2]] for p in s['parts']]
        if s['end'] is not None:
            s['end'] -= s['start']
        # The lunge: offset along the line to Koh (tiles, 64 units each) and height (game units, up
        # positive) from the swing's start, at each frame it changes.
        if pos and koh and (s['start']) in pos:
            x0, z0, y0 = pos[s['start']]
            dx, dz = koh[0] - x0, koh[1] - z0
            n = max(1e-6, (dx * dx + dz * dz) ** 0.5)
            ux, uz = dx / n, dz / n
            mv, last = [], None
            for k in range(0, (s['end'] or 60) + 1):
                p = pos.get(s['start'] + k)
                if p is None:
                    break
                cur = (round(((p[0] - x0) * ux + (p[1] - z0) * uz) / 64.0, 3), round(-(p[2] - y0), 1))
                if cur != last:
                    mv.append([k, cur[0], cur[1]])
                    last = cur
            s['move'] = mv
    return out


def measure(gg, species, want=2, max_turns=16):
    from sprite_banks import SPECIES
    import attach
    log = []
    got = []
    for _turn in range(max_turns):
        us = units(gg)
        koh = us[0]
        mons = [u for u in us if u['sp'] == species and not (u['f14'] & 0x4000) and u['hp'] > 0]
        if not mons:
            # Make the game spawn one (spawn timer 0x80083466 = 0 before Koh waits a turn).
            if _turn < max_turns - 1:
                gg.write(0x80083466, bytes(2))
                gg.hold('triangle', 'circle')
                gg.wait_frames(10)
                gg.release()
                gg.wait_frames(120)
                continue
            log.append('no %s on this floor' % SPECIES[species])
            break
        m = min(mons, key=lambda u: abs(u['x'] - koh['x']) + abs(u['y'] - koh['y']))
        calm(gg, m['addr'])
        tough(gg)
        if max(abs(m['x'] - koh['x']), abs(m['y'] - koh['y'])) > 1:
            try:
                attach.go_next_to(m['addr'], max_legs=30)
            except KeyError:
                # attach.path_to's height map misses a tile Koh stands on (a prop, a pit edge):
                # a random step and try again next round.
                gg.tap(['up', 'down', 'left', 'right'][_turn % 4], frames=4, gap=12)
            continue
        rows, hits, f0, pos, kpos = turn(gg, m['addr'])
        for s in swings(rows, hits, f0, pos, kpos):
            got.append(s)
            log.append(json.dumps(s))
        if len(got) >= want:
            break
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'melee_%02d.txt' % species), 'w') as f:
        f.write('\n'.join(log) + '\n')
    for s in got:
        print('%2d %-8s parts %s blow %s end %s' % (species, SPECIES[species], s['parts'], s['blow'], s['end']))
    if not got:
        print('%2d %-8s no swing recorded (%s)' % (species, SPECIES[species], '; '.join(log[-2:])))
    return got


def setup_familiar(gg):
    for u in units(gg)[1:]:
        if u['f14'] & 0x4000:
            nap(gg, u['addr'])


def run(floors):
    from psx import Game
    import attach
    results = {}
    # Each group gets its own launch with the group on 2F: slot 4 stands on the 1F elevator and the
    # 1F -> 2F ride is reliable (from higher floors take_elevator can answer the QUIT prompt wrong).
    for _f, sps in floors:
        subprocess.run([sys.executable, os.path.join(HERE, 'test_encounters.py'),
                        '2=' + ','.join('%d/1' % s for s in sps)], check=True)
        gg = Game.launch(extra_args=['--memcard-dir', SAVES])
        gg.wait_frames(240)
        attach.g = gg
        gg.load_state(4)
        gg.wait_frames(60)
        attach.take_elevator()
        gg.wait_frames(240)          # the floor's monsters appear a few seconds after arrival
        if attach.floor_number() != 2:
            print('did not reach 2F (floor %d); skipping %s' % (attach.floor_number(), sps))
        else:
            setup_familiar(gg)
            for s in sps:
                results[s] = measure(gg, s)
        gg.quit()
        time.sleep(3)
    subprocess.run([sys.executable, os.path.join(HERE, 'test_encounters.py'), '--off'], check=True)
    return results


def main():
    a = sys.argv[1:]
    if a and a[0] == 'run':
        floors = []
        for spec in a[1:]:
            f, sps = spec.split('=')
            floors.append((int(f), [int(x) for x in sps.split(',')]))
        run(floors)
    elif a and a[0] == 'here':
        gg = g()
        setup_familiar(gg)
        for s in a[1:]:
            measure(gg, int(s))


if __name__ == '__main__':
    main()
