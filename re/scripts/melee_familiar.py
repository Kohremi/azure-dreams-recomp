"""Kewne's swing (the familiar's melee, state 0x18) with its movement, on the dev build: save slot 5
has Kewne (0x801EB374) facing a Baloon (0x801EF10C); its plan is set to Direct (0x8008) and Koh waits.
The blow is FUN_8009C12C's first write to the Baloon's record. Writes re/timelines/melee_02.txt in
melee_measure.py's format.

    python melee_familiar.py      (dev build running)
"""
import json
import os
import struct

import melee_measure as M
from psx import Game
from timeline import Tracker

KEWNE, BALOON = 0x801EB374, 0x801EF10C


def main():
    g = Game()
    out = []
    for _try in range(3):
        g.release()
        g.load_state(5)
        g.wait_frames(90)
        g.write(KEWNE + 0x46, struct.pack('<H', 0x8008))
        t = Tracker(mon1=KEWNE)
        motion = g.u32(KEWNE - 0x18)
        g.cmd('set_snapshot', slot=3, addr='0x%08X' % motion, size=16)
        g.cmd('wtrace_disarm_all')
        g.cmd('wtrace_clear')
        g.cmd('wtrace_arm', lo=hex(BALOON), hi=hex(BALOON + 0x130))
        f0 = g.frame()
        g.hold('triangle', 'circle')
        g.wait_frames(10)
        g.release()
        g.wait_frames(260)
        f1 = g.frame()
        d = g.cmd('wtrace_dump', count=4000)
        g.cmd('wtrace_disarm_all')
        hits = sorted({e['frame'] - f0 for e in d.get('entries', [])
                       if M.HIT_LO <= (int(e['pc'], 16) | 0x80000000) < M.HIT_HI})
        rows = t.dump(f0, f1, quiet=True)
        rows = [(f, n, dict(v, state=0x11 if v['state'] == 0x18 else 0)) for f, n, v in rows]
        pos = {}
        for f in range(f0, f1):
            b = bytes.fromhex(g.cmd('read_frame_ram', addr='0x%08X' % motion, len=12, frame=f)['hex'])
            x, z, y = struct.unpack('<iii', b)
            pos[f - f0] = (x / 65536.0, z / 65536.0, y / 65536.0)
        bm = g.u32(BALOON - 0x18)
        bx, bz = struct.unpack('<hh', g.read(bm + 2, 2) + g.read(bm + 6, 2))
        for s in M.swings(rows, hits, f0, pos, (bx, bz)):
            out.append(s)
            print(json.dumps(s)[:300])
        if out:
            break
    with open(os.path.join(M.OUT, 'melee_02.txt'), 'w') as f:
        f.write('\n'.join(json.dumps(s) for s in out) + '\n')


if __name__ == '__main__':
    main()
