"""LoDown test bench (dev build, save slot 3): Kewne casts LoDown (spell 42) at the Pulunpa.
case: 'normal' | 'frog' (species FROG, real species at +0xA8) | 'battnel' (species 13 with Nyuel-like
low stats at level 30, the community underflow case). Returns (before, after) dicts."""
import os, struct, sys
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from attach import g, KOH
import levelcalc

PUL = 0x801EC920
FIELDS = dict(lv=0x11, sp=0x13, atk=0x00, dfn=0x01, s2=0x02, s3=0x03, mp=0x04, hp=0x05,
              maxhp=0x29, curhp=0x28, curatk=0x26, maxatk=0x68)


def read(u):
    return {k: g.read(u + o, 1)[0] for k, o in FIELDS.items()}


def setup(case):
    g.load_state(3); g.wait_frames(20)
    kew = g.u32(KOH + 0xAC)
    g.write(kew + 0x08, bytes([42, 255, 99]))       # spell slot 1 = LoDown, effective level 255 = never resisted
    g.write(kew + 0x24, bytes([0xFF, 99])); g.write(kew + 0x66, bytes([99]))
    bat = case.startswith("battnel")
    lv = 30 if bat else 10
    sp = 13 if bat else 21
    st = levelcalc.stats(14 if bat else 21, lv)        # Battnel cases: stats it got as a Nyuel
    vals = [min(255, v) for v in (st["atk"], st["def"], st["s2"], st["s3"], st["mp"], st["hp"])]
    if case == "battnel":
        vals[0] = 20; vals[1] = 20                     # below 29 levels of Battnel gains
    if case == "battnel_low":
        vals[0] = 1; vals[1] = 1                       # less than one Battnel level-up gain
    g.write(PUL + 0x00, bytes(vals))
    g.write(PUL + 0x11, bytes([lv])); g.write(PUL + 0x13, bytes([sp]))
    g.write(PUL + 0x18, struct.pack("<I", g.u32(0x800835E8 + 4 * lv)))
    g.write(PUL + 0x29, bytes([vals[5]])); g.write(PUL + 0x28, bytes([vals[5]]))
    g.write(PUL + 0x26, bytes([vals[0]])); g.write(PUL + 0x68, bytes([vals[0]]))
    g.write(PUL + 0x27, bytes([vals[1]])); g.write(PUL + 0x69, bytes([vals[1]]))
    if case == "frog":
        g.write(PUL + 0xA8, bytes([21])); g.write(PUL + 0x13, bytes([46]))
        g.write(PUL + 0x2C, bytes([10, 60]))
    g.wait_frames(10)


def cast():
    g.tap('square', frames=4, gap=30)
    for _ in range(6): g.tap('up', frames=3, gap=8)
    for _ in range(4): g.tap('down', frames=3, gap=8)
    g.tap('cross', frames=4, gap=30)
    g.tap('down', frames=3, gap=8); g.tap('down', frames=3, gap=8)
    g.tap('cross', frames=4, gap=30)
    g.hold('left', 'down'); g.wait_frames(6); g.release(); g.wait_frames(6)
    g.tap('cross', frames=4, gap=10)
    g.tap('right', frames=4, gap=10)
    for _ in range(12):                     # wait for the cast and the level-down message
        g.wait_frames(60)
        if g.read(PUL + 0x11, 1)[0] != LV0[0]:
            g.wait_frames(30)
            break


LV0 = [0]


def run(case):
    setup(case)
    before = read(PUL)
    LV0[0] = before["lv"]
    cast()
    after = read(PUL)
    return before, after


if __name__ == "__main__":
    for case in sys.argv[1:] or ["normal", "frog", "battnel", "battnel_low"]:
        b, a = run(case)
        print(case)
        print("  before", b)
        print("  after ", a)
