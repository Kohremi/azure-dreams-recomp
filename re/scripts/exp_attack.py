"""Timeline experiments on save state 3 (1F: Koh at 55,40, Pulunpa at 54,40, Kewne at 55,39)."""
import sys, json, time
from attach import *
from timeline import Tracker
import os
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PUL = 0x801EC920
KEWNE = 0x801EC490
OUT = os.path.join(REPO_ROOT, r're\timelines')


def setup(acc=True, pul_hp=None, koh_exp=None, koh_hp=None):
    g.load_state(3)
    g.wait_frames(3)
    if acc:
        g.write(KOH + 0x84, [127])
    if pul_hp is not None:
        g.write(PUL + 0x28, [pul_hp])
    if koh_exp is not None:
        g.write(KOH + 0x18, list(int(koh_exp).to_bytes(4, 'little')))
    if koh_hp is not None:
        g.write(KOH + 0x28, [koh_hp, max(koh_hp, g.u8(KOH + 0x29))])


def run(name, actions, frames=260, shots=()):
    t = Tracker(mon1=PUL, mon2=KEWNE)
    f0 = g.frame()
    marks = []
    shot_at = sorted(shots)
    for a in actions:
        marks.append((g.frame() - f0, a[0]))
        if a[0] == 'tap':
            g.tap(*a[1], frames=3, gap=2)
        elif a[0] == 'hold':
            g.hold(*a[1]); g.wait_frames(a[2]); g.release()
        elif a[0] == 'wait':
            g.wait_frames(a[1])
        elif a[0] == 'attack':
            g.hold(a[1]); g.wait_frames(2); g.tap('cross', frames=3, gap=2); g.release()
    shot_paths = []
    while g.frame() - f0 < frames:
        el = g.frame() - f0
        if shot_at and el >= shot_at[0]:
            shot_at.pop(0)
            p = g.shot('%s_%03d' % (name, el))
            shot_paths.append((el, p))
        time.sleep(0.005)
    rows = t.dump(f0, f0 + frames - 2, quiet=True)
    with open('%s\%s.txt' % (OUT, name), 'w') as f:
        for m in marks:
            f.write('MARK +%d %s\n' % m)
        for el, p in shot_paths:
            f.write('SHOT +%d %s\n' % (el, p))
        for fr, n, v in rows:
            f.write('%6d +%4d %-4s st %02x.%02x seq %s m%d\n' % (fr, fr - f0, n, v['state'], v['sub'], v['seq'], v['mirror']))
    print('wrote', name, len(rows), 'rows')


if __name__ == '__main__':
    which = sys.argv[1]
    if which == 'hit':
        setup()
        run('hit', [('wait', 10), ('attack', 'left')], frames=300, shots=range(40, 200, 6))
    elif which == 'kill':
        setup(pul_hp=1)
        run('kill', [('wait', 10), ('attack', 'left')], frames=360, shots=range(40, 340, 8))
    elif which == 'levelup':
        setup(pul_hp=1, koh_exp=7)
        run('levelup', [('wait', 10), ('attack', 'left')], frames=480, shots=range(40, 470, 8))
