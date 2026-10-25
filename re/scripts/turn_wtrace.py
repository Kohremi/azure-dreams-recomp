"""Who writes what during one turn (debug server write trace), in order:

    python turn_wtrace.py STATE setup_moves move

loads STATE, plays setup_moves (comma list, '-' for none), then traces writes to the random state
(0x8008335C: one write per draw, with the drawing code's return address) and, for every unit in
the list, HP +0x28, facing +0x2A, plan +0x46, action counter +0x6C, the map object's tile
(+0x24/+0x25) while `move` is played."""
import sys
from attach import g, KOH
import turn_capture as tc

NAMES = {0x28: 'hp', 0x2A: 'dir', 0x46: 'plan', 0x6C: 'ap', 0x24: 'mp'}


def main():
    state = int(sys.argv[1])
    setup = [] if sys.argv[2] == '-' else sys.argv[2].split(',')
    move = sys.argv[3]
    g.tap('triangle', frames=3, gap=10)
    g.load_state(state)
    g.wait_frames(3)
    for i in range(3):
        g.tap('cross', frames=3, gap=8)
    tc.wait_idle()
    for mv in tc.pokes(setup):
        tc.act(mv)
        tc.wait_idle()
    us = tc.units()
    ranges = [(0x8008335C, 0x80083360, 'rng')]
    for i, u in enumerate(us):
        a = int(u['addr'], 16)
        tag = 'sp%d' % u['species']
        for off, n in ((0x24, 2), (0x28, 1), (0x2A, 2), (0x46, 2), (0x6C, 2)):
            ranges.append((a + off, a + off + n, '%s.%s' % (tag, NAMES[off])))
        mo = g.u32(a - 0x14)
        ranges.append((mo + 0x24, mo + 0x26, '%s.tile' % tag))
    g.cmd('wtrace_disarm_all')
    g.cmd('wtrace_clear')
    for lo, hi, _ in ranges:
        g.cmd('wtrace_arm', lo=hex(lo), hi=hex(hi))
    f0 = g.frame()
    tc.act(move)
    tc.wait_idle()
    d = g.cmd('wtrace_dump', count=2000)
    g.cmd('wtrace_disarm_all')
    ents = d.get('entries', [])
    ents = sorted(ents, key=lambda e: e.get('seq', 0))
    print('%d writes' % len(ents))
    for e in ents:
        addr = int(str(e.get('addr', e.get('address', '0'))), 16) if isinstance(e.get('addr', e.get('address')), str) else e.get('addr', 0)
        name = '?'
        for lo, hi, n in ranges:
            if lo <= (addr | 0x80000000) < hi or lo <= addr < hi:
                name = n
        print('%5s %-10s %8s -> %8s  ra %s' % (e.get('frame', 0) - f0 if 'frame' in e else '', name,
                                            e.get('old'), e.get('new'), e.get('ra')))


if __name__ == '__main__':
    main()
