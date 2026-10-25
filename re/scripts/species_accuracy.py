"""Per-species melee accuracy (+0x84) and weapon power (+0x85), as each species' code chunk sets them
right before an attack (e.g. Pulunpa: li v0,124 / sb v0,132(a0) / sb zero,133(a0) in its state 0x11
handler). The hit roll (dungeon FUN_8009C93C) is +0x84 + 4 * (rand % +0x03) > 127; weapon power
feeds attack = roll + (ATK + +0x85) * 2 (FUN_800981F8).

    python species_accuracy.py            print every store found, per species
"""
import struct, sys
from species_anims import chunk, BASE, SIZE
from sprite_banks import SPECIES


def scan(s):
    c = chunk(s)
    n = len(c) // 4
    words = struct.unpack_from('<%dI' % n, c)
    out = []
    for i, w in enumerate(words):
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op != 0x28 or imm not in (0x84, 0x85):      # sb rt, 0x84/0x85(rs)
            continue
        val = 0 if rt == 0 else None
        for k in range(1, 8):                             # nearest li rt, imm before it
            p = words[i - k] if i - k >= 0 else 0
            pop, prs, prt, pimm = p >> 26, (p >> 21) & 31, (p >> 16) & 31, p & 0xFFFF
            if prt == rt and pop == 0x09 and prs == 0:    # addiu rt, zero, imm
                val = pimm - 0x10000 if pimm & 0x8000 else pimm
                break
            if prt == rt and pop not in (0x28, 0x29, 0x2B):
                break                                     # rt written by something else
        out.append((BASE + i * 4, 'acc' if imm == 0x84 else 'pow', val))
    return out


def table():
    """species -> {"acc": [...], "pow": [...]} in code order."""
    res = {}
    for s in range(1, 47):
        d = {"acc": [], "pow": []}
        for a, kind, v in scan(s):
            d[kind].append(v)
        res[s] = d
    return res


if __name__ == '__main__':
    for s in [int(a) for a in sys.argv[1:]] or range(1, 47):
        st = scan(s)
        print('%2d %-10s %s' % (s, SPECIES[s], ' '.join('%s=%s@%x' % (k, v, a) for a, k, v in st)))
