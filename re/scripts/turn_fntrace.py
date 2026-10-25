"""Which dungeon functions run during one turn, in order (debug server fntrace):

    python turn_fntrace.py STATE setup_moves move [targets...]

loads STATE, plays setup_moves (comma list, '-' for none) with turn_capture.act, arms fntrace on
the targets (default: the RNG, the hit routine, melee damage, target choice, attack choice, plan
choice, the step), plays `move` and prints every recorded call with its caller and arguments."""
import sys
from attach import g
import turn_capture as tc

DEFAULT = {
    0x800A6D30: 'rand', 0x8009C93C: 'hit', 0x8009C12C: 'melee_dmg', 0x800A3D18: 'pick_target',
    0x800A384C: 'attack_choice', 0x800ADE74: 'choose_plan', 0x80171468: 'move(sp21)',
    0x800A9A0C: 'pass', 0x800A0E6C: 'wander', 0x800A19E4: 'chase', 0x80099EA4: 'refill',
    0x800A9AFC: 'commit', 0x800AD594: 'spend_mp', 0x800A4ACC: 'status_tick',
}


def main():
    state = int(sys.argv[1])
    setup = [] if sys.argv[2] == '-' else sys.argv[2].split(',')
    move = sys.argv[3]
    targets = {int(a, 16): a for a in sys.argv[4:]} or DEFAULT
    g.tap('triangle', frames=3, gap=10)
    g.load_state(state)
    g.wait_frames(3)
    for i in range(3):
        g.tap('cross', frames=3, gap=8)
    tc.wait_idle()
    for mv in setup:
        tc.act(mv)
        tc.wait_idle()
    g.cmd('fntrace_arm_clear')
    for t in targets:
        g.cmd('fntrace_arm', target='0x%08X' % t)
    g.cmd('fntrace_clear')
    before = tc.snapshot()
    f0 = g.frame()
    tc.act(move)
    tc.wait_idle()
    after = tc.snapshot()
    d = g.cmd('fntrace_dump', count=4000)
    g.cmd('fntrace_arm_clear')
    rows = sorted(d['entries'], key=lambda e: e['seq'])
    print('rng %08X -> %08X, %d calls' % (before['globals']['rng'], after['globals']['rng'], len(rows)))
    for e in rows:
        t = int(e['target'], 16)
        print('%5d %-14s ra %s a0 %s a1 %s a2 %s a3 %s' % (e['frame'] - f0, targets.get(t, e['target']),
              e['ra'], e['a0'], e['a1'], e['a2'], e['a3']))
    for u in after['units']:
        print('  sp%2d %s (%d,%d) hp %d ap %04X mp %04X plan %04X dir %d' % (u['species'], u['addr'], u['x'], u['y'],
              u['hp'], u['ap'], u['mp'], u['plan'], u['dir']))


if __name__ == '__main__':
    main()
