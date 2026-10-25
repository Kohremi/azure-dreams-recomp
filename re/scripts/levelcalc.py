"""Python port of the dungeon module's level-up routine (FUN_800A1D4C) for checking
and designing growth changes. stats(species, level) gives base stats at a level."""
import math, os, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
_EXE = open(os.path.join(ROOT, r"extracted\SLUS_006.14"), "rb").read()
_DUN = open(os.path.join(ROOT, r"re\modules\dungeon_80088760.bin"), "rb").read()


def base_row(sp):
    o = 0x8006D168 - (0x8002D000 - 0x800) + sp * 0x18
    return _EXE[o:o + 0x18]


def growth_row(sp):
    o = 0x800DDCBC - 0x80088760 + sp * 8
    return _DUN[o:o + 8]


def sqrt12(x):
    """PsyQ SquareRoot12: sqrt of a 20.12 fixed value, result 20.12."""
    return int(math.isqrt(x * 4096)) if x > 0 else 0


def level_up(stats, sp, lvl):
    """Apply one level-up from `lvl` to lvl+1; stats = dict atk, def, s2, s3, mp, hp."""
    b, g = base_row(sp), growth_row(sp)
    L, P = lvl, lvl - 1
    hp_curve = lambda n: b[5] + ((g[5] * n) >> 4) + ((g[5] * sqrt12(n * g[5] * 0x800)) >> 15)
    s = dict(stats)
    s["hp"] = min(255, s["hp"] + hp_curve(L) - hp_curve(P))
    s["mp"] = min(255, s["mp"] + ((g[4] * b[4] * L) >> 10) - ((g[4] * b[4] * P) >> 10))
    s["atk"] = min(255, s["atk"] + ((g[0] * b[0] * L) >> 6) - ((g[0] * b[0] * P) >> 6))
    s["def"] = min(255, s["def"] + ((g[1] * b[1] * L) >> 6) - ((g[1] * b[1] * P) >> 6))
    s["s2"] = min(255, s["s2"] + ((g[2] * b[2] * L) >> 6) - ((g[2] * b[2] * P) >> 6))
    s["s3"] = min(255, s["s3"] + ((g[3] * b[3] * L) >> 10) - ((g[3] * b[3] * P) >> 10))
    return s


def stats(sp, level):
    b = base_row(sp)
    s = dict(atk=b[0], **{"def": b[1]}, s2=b[2], s3=b[3], mp=b[4], hp=b[5])
    for lvl in range(1, level):
        s = level_up(s, sp, lvl)
    return s


if __name__ == "__main__":
    import sys
    sp = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    print("growth row", list(growth_row(sp)))
    for lv in (1, 2, 3, 5, 10, 20, 50, 99):
        print(lv, stats(sp, lv))
