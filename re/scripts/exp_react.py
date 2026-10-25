"""When does Koh get control back after a monster's blow? (save state 5: 2F, Koh facing a Baloon.)

Koh attacks the Baloon (which survives), then the d-pad is held away from it from +60 on; the first
frame Koh reacts (turns/steps) is the first frame the game takes input again. Screenshots give the
message lines. Result (re/timelines/react.txt): the Baloon's blow at +226, its lines at ~+246/+258,
Koh reacts at +286, i.e. blow + 60."""
import sys, time
from attach import *
from timeline import Tracker
from exp_attack import OUT

PUL = 0x801EF10C     # the Baloon in slot 5 (named as in exp_attack)
KEWNE = 0x801EB374


def setup():
    g.tap('triangle', frames=3, gap=10)
    g.load_state(5); g.wait_frames(3)
    for i in range(3):
        g.tap('cross', frames=3, gap=8)
    g.write(KOH + 0x84, [200])           # accuracy: always hit
    g.write(KOH + 0x2A, [0x00, 0x0C])    # face the Baloon
    g.write(PUL + 0x28, [200])           # it survives
    g.wait_frames(4)


def main(name='react', away='right', frames=460, shots=range(150, 440, 4)):
    setup()
    g.write(KEWNE + 0x28, [200, 200])
    t = Tracker(mon1=PUL, mon2=KEWNE)
    f0 = g.frame()
    g.wait_frames(10)
    g.tap('cross', frames=3, gap=2)
    while g.frame() - f0 < 60:
        time.sleep(0.005)
    g.hold(away)
    todo = sorted(shots)
    paths = []
    while g.frame() - f0 < frames:
        el = g.frame() - f0
        if todo and el >= todo[0]:
            todo.pop(0)
            paths.append((el, g.shot('%s_%03d' % (name, el))))
        time.sleep(0.003)
    g.release()
    rows = t.dump(f0, f0 + frames - 2, quiet=True)
    with open(r'%s\%s.txt' % (OUT, name), 'w') as f:
        f.write('MARK +10 attack\nMARK +60 hold %s\n' % away)
        for el, p in paths:
            f.write('SHOT +%d %s\n' % (el, p))
        for fr, n, v in rows:
            f.write('%6d +%4d %-4s st %02x.%02x seq %s m%d\n' % (fr, fr - f0, n, v['state'], v['sub'], v['seq'], v['mirror']))
    print('wrote', name, len(rows), 'rows')


if __name__ == '__main__':
    main(*sys.argv[1:2])
