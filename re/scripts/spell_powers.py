"""Extract (power, element) arguments of every magic-damage call (FUN_8009CE1C) in
the per-spell overlays (DUNGEON.BIN +0x1834800 + i*0x6000, loaded at 0x80024000).

Spell id s (normal cast) uses overlay i = s-1."""
import csv, os, struct, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
D = open(os.path.join(ROOT, r"extracted\DUNGEON\DUNGEON.BIN"), "rb").read()
EXE = open(os.path.join(ROOT, r"extracted\SLUS_006.14"), "rb").read()
JAL = 0x0C000000 | ((0x8009CE1C >> 2) & 0x3FFFFFF)
EB = 0x8002D000 - 0x800


def spell_name(sid):
    a = struct.unpack_from("<I", EXE, 0x8006DE24 + sid * 0x14 - EB)[0]
    if not (0x8002D000 <= a < 0x80082000):
        return ""
    o = a - EB
    return unicodedata.normalize("NFKC", EXE[o:EXE.find(b"\0", o)].decode("shift-jis", "replace"))


def reg_imm(words, idx, reg):
    """Find the latest `addiu reg,zero,imm` / `ori reg,zero,imm` before idx (or in the delay slot)."""
    cands = list(range(idx - 1, max(0, idx - 16), -1))
    cands.insert(0, idx + 1)  # delay slot
    for j in cands:
        w = words[j]
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if rt == reg and rs == 0 and op in (0x09, 0x0D):
            return imm - 0x10000 if (op == 0x09 and imm & 0x8000) else imm
        if rt == reg and op not in (0x2B, 0x28, 0x29) and j != idx + 1:  # overwritten by something else
            return None
    return None


def scan():
    rows = []
    for i in range(72):
        base = 0x1834800 + i * 0x6000
        chunk = D[base:base + 0x6000]
        words = list(struct.unpack("<%dI" % (len(chunk) // 4), chunk))
        for k, w in enumerate(words):
            if w == JAL:
                rows.append(dict(overlay=i, spell_id=i + 1 if i < 51 else "", name=spell_name(i + 1) if i < 51 else "",
                                 call_pc="0x%08X" % (0x80024000 + k * 4),
                                 power=reg_imm(words, k, 5), element=reg_imm(words, k, 7),
                                 disc_offset="0x%07X" % (base + k * 4)))
    return rows


def main():
    rows = scan()
    out = os.path.join(ROOT, r"re\data\spell_damage_calls.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
