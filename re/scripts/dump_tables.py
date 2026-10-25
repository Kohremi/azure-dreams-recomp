"""Dump Azure Dreams familiar/combat data tables to re/data/*.csv.

Sources (see re/NOTES.md):
  species base stats   EXE 0x8006D168, 0x18 bytes x species
  species talents      EXE 0x8006D6D8, u32 x species  (copied to unit +0x54)
  egg/species names    EXE 0x80072794, 0x14-byte item entries, index = species id
  growth rates         dungeon module 0x800DDCBC, 8 bytes x species
  spells               EXE 0x8006DE24, 0x14 bytes x spell id; MP costs + powers (dungeon/overlays)
  EXP curve            computed exactly like EXE FUN_80043674
"""
import csv, math, os, struct, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
EXE = open(os.path.join(ROOT, r"extracted\SLUS_006.14"), "rb").read()
DUN = open(os.path.join(ROOT, r"re\modules\dungeon_80088760.bin"), "rb").read()
OUT = os.path.join(ROOT, r"re\data")
os.makedirs(OUT, exist_ok=True)

EXE_BASE = 0x8002D000 - 0x800
DUN_BASE = 0x80088760
N_SPECIES = 48

TALENTS = ["Quick", "HP+", "MP+", "Strength+", "Hard", "Growth", "Bit6", "MagicAtk+",
           "Bit8", "Bit9", "Bit10", "Bit11", "Bit12", "Bit13", "Bit14", "Bit15",
           "Bit16", "Bit17", "Bit18", "Bit19", "Bit20", "Bit21", "Bit22", "Bit23",
           "Bit24", "Bit25", "Bit26", "Bit27", "Bit28", "Bit29", "Bit30", "Bit31"]


def exe(a, n):
    return EXE[a - EXE_BASE:a - EXE_BASE + n]


def u32(a):
    return struct.unpack("<I", exe(a, 4))[0]


def sjis(a):
    if not (0x8002D000 <= a < 0x80082000):
        return ""
    o = a - EXE_BASE
    j = EXE.find(b"\0", o)
    return unicodedata.normalize("NFKC", EXE[o:j].decode("shift-jis", "replace")).strip()


def species_name(sp):
    return sjis(u32(0x80072794 + sp * 0x14 + 4)) if sp else "KOH"


def spell_name(sid):
    return sjis(u32(0x8006DE24 + sid * 0x14)) if sid else ""


def exp_table():
    t = [0]
    for lvl in range(1, 100):
        n = lvl + 3
        v = t[-1] + (n ** 3 >> 3)
        if lvl > 20:
            v += (lvl - 20) ** 2 * 32
        t.append(v)
    return t


def main():
    with open(os.path.join(OUT, "species.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "atk", "def", "stat2", "stat3", "mp", "hp", "exp_reward",
                    "spell1", "spell1_lv", "level", "flags_u32", "talents_hex", "talents",
                    "g_atk", "g_def", "g_2", "g_3", "g_mp", "g_hp", "g_exp", "g_7", "raw"])
        for sp in range(N_SPECIES):
            r = exe(0x8006D168 + sp * 0x18, 0x18)
            tal = u32(0x8006D6D8 + sp * 4)
            g = DUN[0x800DDCBC - DUN_BASE + sp * 8: 0x800DDCBC - DUN_BASE + sp * 8 + 8]
            names = [TALENTS[b] for b in range(32) if tal >> b & 1]
            w.writerow([sp, species_name(sp), r[0], r[1], r[2], r[3], r[4], r[5],
                        struct.unpack_from("<H", r, 6)[0], spell_name(r[8]), r[10], r[0x11],
                        "%08x" % struct.unpack_from("<I", r, 0x14)[0], "%08x" % tal, " ".join(names),
                        *g, r.hex(" ")])
    # MP costs live in the dungeon module (0x800DD880 cast, whole MP; 0x800DD8B4 mixture/enchant,
    # quarter MP); attack powers are immediates in the per-spell overlays (see spell_powers.py).
    cast = DUN[0x800DD880 - DUN_BASE:0x800DD880 - DUN_BASE + 0x34]
    ench = DUN[0x800DD8B4 - DUN_BASE:0x800DD8B4 - DUN_BASE + 0x34]
    import spell_powers
    powers = {}
    for r in spell_powers.scan():
        if r["spell_id"]:
            powers.setdefault(r["spell_id"], []).append(str(r["power"]))
    with open(os.path.join(OUT, "spells.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "category", "element", "effect_type", "target_scope", "mp_cast",
                    "mp_mixture_quarters", "attack_power", "mixture_name", "description", "overlay_disc_offset"])
        for sid in range(1, 52):
            e = 0x8006DE24 + sid * 0x14
            r = exe(e, 0x14)
            cat_el = r[0x10]
            w.writerow([sid, spell_name(sid), {1: "X/NeaX/NoaX", 2: "De-", 4: "La/Le/Lo"}.get(cat_el >> 4, cat_el >> 4),
                        {1: "fire", 2: "water", 4: "wind"}.get(cat_el & 7, cat_el & 7), "0x%02x" % r[0x11], r[0x12],
                        cast[sid], ench[sid], "/".join(powers.get(sid, [])), sjis(u32(e + 8)),
                        sjis(u32(e + 4)).replace("\n", " "), "0x%07X" % (0x1834800 + (sid - 1) * 0x6000) if sid < 51 else ""])
    with open(os.path.join(OUT, "exp_curve.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["level", "total_exp_to_next"])
        for lvl, v in enumerate(exp_table()):
            w.writerow([lvl, v])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
