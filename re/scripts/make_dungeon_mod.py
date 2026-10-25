"""Generate the declarative `azure.dungeon` mod package (no C code).

Everything here is a guarded `disc_user` patch: bytes are replaced as sectors are
read from DUNGEON.BIN, so code/data that is loaded and run immediately (the floor
generator overlay) is already modded when it executes. Launcher options are
written straight into MIPS immediates with `replace_from`.

    python make_dungeon_mod.py            # writes the manifest + re/data/floors.csv
    python make_dungeon_mod.py --custom re/data/floors_custom.csv

Sources (re/NOTES.md "Dungeon"): floor sectors at DUNGEON.BIN +0x7A4800 + (floor-1)*0x800
(16 x species/level spawn slots, then 32 egg-pool species); dungeon module at +0xA3000
(loaded to 0x80088760); floor overlay copies at +0x2A3000 and +0x51E800 (loaded to 0x80016000).
"""
import argparse, csv, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
D = open(os.path.join(ROOT, r"extracted\DUNGEON\DUNGEON.BIN"), "rb").read()
OUT = os.path.join(ROOT, r"mods\preloaded\packages\azure.dungeon\1.0.0\manifest.toml")
DUNGEON_LBA = 12310
FLOOR_BASE = 0x7A4800
FLOORS = 39                     # 40 is Beldo's fixed floor
DUNGEON_MODULE = (0xA3000, 0x80088760)
FLOOR_OVERLAYS = [(0x2A3000, 0x80016000), (0x51E800, 0x80016000)]


def disc_off(file_off):
    return DUNGEON_LBA * 2048 + file_off


def hexb(b):
    return " ".join("%02x" % x for x in b)


def stock(file_off, n):
    return D[file_off:file_off + n]


def code_patch(feature, region, addr, nbytes=4, at=0, replace=None, option=None, when=None, comment="",
               addend=0):
    file_off = region[0] + (addr - region[1]) + at
    exp = stock(file_off, nbytes)
    out = ["", "[[patch]]" + ("  # " + comment if comment else ""),
           'feature = "%s"' % feature, 'target = "disc_user"',
           "offset = 0x%X" % disc_off(file_off), 'expected = "%s"' % hexb(exp)]
    if option:
        out.append('replace_from = { option = "%s", encoding = "u16le", offset = 0%s }'
                   % (option, ", addend = %d" % addend if addend else ""))
    else:
        out.append('replace = "%s"' % hexb(replace))
    if when:
        out.append("when = { %s }" % ", ".join('%s = "%s"' % kv for kv in when.items()))
    return out


def floor_tables():
    rows = []
    for f in range(1, FLOORS + 1):
        o = FLOOR_BASE + (f - 1) * 0x800
        spawn = [(D[o + 2 * k], D[o + 2 * k + 1]) for k in range(16)]
        eggs = list(D[o + 0x20:o + 0x40])
        rows.append((f, spawn, eggs))
    return rows


def write_floors_csv(rows, path):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["floor"] + ["slot%d_species" % k for k in range(16)] + ["slot%d_level" % k for k in range(16)]
                   + ["egg%d" % k for k in range(32)])
        for f, spawn, eggs in rows:
            w.writerow([f] + [s for s, _ in spawn] + [l for _, l in spawn] + eggs)


def read_floors_csv(path):
    rows = []
    for r in csv.DictReader(open(path)):
        f = int(r["floor"])
        spawn = [(int(r["slot%d_species" % k]), int(r["slot%d_level" % k])) for k in range(16)]
        eggs = [int(r["egg%d" % k]) for k in range(32)]
        rows.append((f, spawn, eggs))
    return rows


def floor_patches(feature, new_rows, stock_rows):
    out = []
    for (f, spawn, eggs), (_, s_spawn, s_eggs) in zip(new_rows, stock_rows):
        o = FLOOR_BASE + (f - 1) * 0x800
        new = bytes(b for pair in spawn for b in pair) + bytes(eggs)
        old = bytes(b for pair in s_spawn for b in pair) + bytes(s_eggs)
        if new != old:
            out += ["", "[[patch]]  # floor %d spawn table + egg pool" % f, 'feature = "%s"' % feature,
                    'target = "disc_user"', "offset = 0x%X" % disc_off(o),
                    'expected = "%s"' % hexb(old), 'replace = "%s"' % hexb(new)]
    return out


def int_option(feature, oid, label, lo, hi, default, step=1, desc=None):
    out = ["", "[[option]]", 'feature = "%s"' % feature, 'id = "%s"' % oid, 'label = "%s"' % label]
    if desc:
        out.append('description = "%s"' % desc)
    out += ['type = "integer"', "min = %d" % lo, "max = %d" % hi, "step = %d" % step, "default = %d" % default]
    return out


def feature(fid, name, desc, group):
    return ["", "[[feature]]", 'id = "%s"' % fid, 'name = "%s"' % name, 'description = "%s"' % desc,
            'group = "%s"' % group, "default_enabled = false", 'channel = "experimental"']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--custom", help="floors CSV (same columns as re/data/floors.csv) for a Custom Encounters feature")
    args = ap.parse_args()

    stock_rows = floor_tables()
    write_floors_csv(stock_rows, os.path.join(ROOT, r"re\data\floors.csv"))

    m = ['format_version = 6', 'id = "azure.dungeon"', 'version = "1.0.0"', 'name = "Azure Dreams Dungeon Mods"',
         'author = "Kohremi"',
         'description = "Monster Tower tuning: monster density, item rarity and encounter tables. Generated by re/scripts/make_dungeon_mod.py."',
         'license = "GPL-3.0"', 'resolver = "declarative"', "", "[[target]]", 'game_id = "SLUS-00614"']

    # ---- Monster Density -------------------------------------------------
    m += feature("monster-density", "Monster Density",
                 "How many monsters a floor starts with and how often new ones appear (vanilla: 4-8 at start, one more every 32-63 turns, at most 32).",
                 "Dungeon")
    m += int_option("monster-density", "start_min", "Monsters at floor start (min)", 0, 30, 4)
    m += int_option("monster-density", "start_max", "Monsters at floor start (max)", 0, 30, 8)
    m += int_option("monster-density", "spawn_base", "Turns between spawns (minimum)", 1, 999, 32)
    m += ["", "[[option]]", 'feature = "monster-density"', 'id = "spawn_spread"', 'label = "Extra random turns between spawns"',
          'type = "choice"', 'default = "31"']
    for v in ("0", "7", "15", "31", "63", "127"):
        m += ["", "[[option.choice]]", 'value = "%s"' % v, 'label = "0-%s"' % v]
    # floor start: rand(li a0,MIN ; li a1,MAX) at 0x800A69E8 / 0x800A69EC
    m += code_patch("monster-density", DUNGEON_MODULE, 0x800A69E8, 2, option="start_min", comment="li a0,4 (start min)")
    m += code_patch("monster-density", DUNGEON_MODULE, 0x800A69EC, 2, option="start_max", comment="li a1,8 (start max)")
    # spawn timer reset: andi v0,v0,0x1f ; ori v0,v0,0x20  ->  andi v0,v0,SPREAD ; addiu v0,v0,BASE
    for v in ("0", "7", "15", "63", "127"):
        m += code_patch("monster-density", DUNGEON_MODULE, 0x800A0E1C, 1, replace=bytes([int(v)]),
                        when={"spawn_spread": v}, comment="andi v0,v0,0x1f -> spread %s" % v)
    m += code_patch("monster-density", DUNGEON_MODULE, 0x800A0E20, 2, at=2, replace=bytes([0x42, 0x24]),
                    comment="ori v0,v0,.. -> addiu v0,v0,..")
    m += code_patch("monster-density", DUNGEON_MODULE, 0x800A0E20, 2, option="spawn_base", comment="spawn base turns")

    # ---- Item Rarity -----------------------------------------------------
    m += feature("item-rarity", "Item Rarity",
                 "Weights used when the floor generator picks items by rarity tier (vanilla 128 / 85 / 32 / 1). Raise the rare tiers to find Dark/Holy swords, Bow Guns, Roche and Big Pita more often.",
                 "Dungeon")
    m += int_option("item-rarity", "common", "Common items", 1, 400, 128)
    m += int_option("item-rarity", "uncommon", "Uncommon items", 1, 400, 85)
    m += int_option("item-rarity", "rare", "Rare items", 1, 400, 32)
    m += int_option("item-rarity", "very_rare", "Very rare items", 1, 400, 1)
    for region in FLOOR_OVERLAYS:
        tag = "overlay @+0x%X" % region[0]
        # category-total builder (0x8001E994..)
        m += code_patch("item-rarity", region, 0x8001EA40, 2, option="common", comment=tag + " builder li a0,128")
        m += code_patch("item-rarity", region, 0x8001EA4C, 2, option="uncommon", comment=tag + " builder li a0,85")
        m += code_patch("item-rarity", region, 0x8001EA58, 2, option="rare", comment=tag + " builder li a0,32")
        m += code_patch("item-rarity", region, 0x8001EA54, 2, at=2, replace=bytes([0x04, 0x24]),
                        comment=tag + " builder move a0,v0 -> li a0,..")
        m += code_patch("item-rarity", region, 0x8001EA54, 2, option="very_rare", comment=tag + " builder very rare")
        # picker (FUN_8001EAA4)
        m += code_patch("item-rarity", region, 0x8001EBD0, 2, option="common", comment=tag + " picker li a1,128")
        m += code_patch("item-rarity", region, 0x8001EBDC, 2, option="uncommon", comment=tag + " picker li a1,85")
        m += code_patch("item-rarity", region, 0x8001EBE8, 2, option="rare", comment=tag + " picker li a1,32")
        m += code_patch("item-rarity", region, 0x8001EBE4, 2, at=2, replace=bytes([0x05, 0x24]),
                        comment=tag + " picker move a1,v0 -> li a1,..")
        m += code_patch("item-rarity", region, 0x8001EBE4, 2, option="very_rare", comment=tag + " picker very rare")

    # ---- Floor layout (floor overlay FUN_80019AF8 / FUN_8001E194 / FUN_8001EF0C) ----------
    def choice_option(fid, oid, label, default, choices, desc=None):
        out = ["", "[[option]]", 'feature = "%s"' % fid, 'id = "%s"' % oid, 'label = "%s"' % label]
        if desc:
            out.append('description = "%s"' % desc)
        out += ['type = "choice"', 'default = "%s"' % default]
        for v, lab in choices:
            out += ["", "[[option.choice]]", 'value = "%s"' % v, 'label = "%s"' % lab]
        return out

    def li(v, reg):          # addiu reg,zero,v
        return (0x24000000 | (reg << 16) | (v & 0xFFFF)).to_bytes(4, "little")

    def ovl(fid, addr, nbytes=4, **kw):
        out = []
        for region in FLOOR_OVERLAYS:
            kw2 = dict(kw)
            kw2["comment"] = "floor ovl @+0x%X: %s" % (region[0], kw.get("comment", ""))
            out += code_patch(fid, region, addr, nbytes, **kw2)
        return out

    m += feature("room-grid", "Room Grid",
                 "Sets how many room cells the floor generator lays out across and down (vanilla: 4x4 almost always, rarely 3 or 2). Fewer cells = fewer, bigger rooms with longer corridors. Simulated averages: 4x4 6.6 rooms of area 40; 3x3 4.8 rooms of area 54; 2x2 2.6 rooms of area 105 (23% of 2x2 floors collapse into one open room).",
                 "Floor Layout")
    m += int_option("room-grid", "columns", "Cells across", 2, 4, 4)
    m += int_option("room-grid", "rows", "Cells down", 2, 4, 4)
    for a, lab in ((0x80019B4C, "cols rare 2"), (0x80019B5C, "cols rare 3"), (0x80019B60, "cols 4")):
        m += ovl("room-grid", a, 2, option="columns", comment="li v0 (%s)" % lab)
    for a, lab in ((0x80019B78, "rows rare 2"), (0x80019B94, "rows rare 3"), (0x80019B98, "rows 4")):
        m += ovl("room-grid", a, 2, option="rows", comment="li v0 (%s)" % lab)

    m += feature("room-frequency", "Room Frequency",
                 "Chance that a grid cell holds a room instead of a bare corridor junction (vanilla 75%). Simulated averages: 50% 4.8 rooms, 75% 6.6, 94% 8.0, always 8.4.",
                 "Floor Layout")
    m += choice_option("room-frequency", "chance", "Room chance", "75",
                       [("50", "50%"), ("75", "75% (vanilla)"), ("88", "88%"), ("94", "94%"), ("100", "Always")])
    for v, mask in (("50", 1), ("88", 7), ("94", 15)):
        m += ovl("room-frequency", 0x80019C34, 1, replace=bytes([mask]), when={"chance": v},
                 comment="andi v0,v0,3 -> %d" % mask)
    m += ovl("room-frequency", 0x80019C34, 4, replace=bytes.fromhex("01000234"), when={"chance": "100"},
             comment="andi v0,v0,3 -> ori v0,zero,1")

    m += feature("room-size", "Room Size",
                 "Makes rooms larger. A room that no longer fits in its cell becomes a bare corridor junction, so size trades against count. Simulated averages (4x4): +1/+1 5.7 rooms of area 54; +2/+2 4.9 of 69; +3/+3 4.2 of 87. Combine with Room Frequency Always to keep the count up (+1/+1: 7.1 rooms of area 53).",
                 "Floor Layout")
    m += int_option("room-size", "width_bonus", "Extra width (tiles)", 0, 10, 1)
    m += int_option("room-size", "height_bonus", "Extra height (tiles)", 0, 10, 1)
    m += ovl("room-size", 0x80019DE8, 2, at=2, replace=bytes.fromhex("5e24"),
             comment="move s8,v0 -> addiu s8,v0,.. (opcode)")
    m += ovl("room-size", 0x80019DE8, 2, option="width_bonus", comment="width bonus")
    m += ovl("room-size", 0x80019E04, 2, option="height_bonus", addend=5,
             comment="addiu v0,v0,5 -> 5 + height bonus")

    m += feature("open-floors", "Open Floors",
                 "Chance that a floor is generated as one huge open room (vanilla 2 in 513, about 0.4%). Open floors get 8-15 items and 4-7 traps.",
                 "Floor Layout")
    m += choice_option("open-floors", "chance", "Open floor chance", "5",
                       [("0", "Never"), ("5", "5%"), ("10", "10%"), ("25", "25%"), ("50", "50%"), ("100", "Every floor")])
    for v, n in (("0", 0), ("5", 26), ("10", 51), ("25", 128), ("50", 257), ("100", 513)):
        m += ovl("open-floors", 0x80019BE0, 2, replace=n.to_bytes(2, "little"), when={"chance": v},
                 comment="slti v0,v0,2 -> %d (of 513)" % n)

    m += feature("floor-elevation", "Floor Elevation",
                 "Height differences between rooms (vanilla: rooms sit at one of 4 heights).",
                 "Floor Layout")
    m += choice_option("floor-elevation", "style", "Elevation", "flat",
                       [("flat", "Flat (all rooms level)"), ("gentle", "Gentle (2 heights)")])
    for a in (0x80019EF0, 0x80019FDC, 0x8001A0B0, 0x8001A19C):
        for v, mask in (("flat", 0x00), ("gentle", 0x20)):
            m += ovl("floor-elevation", a, 1, replace=bytes([mask]), when={"style": v},
                     comment="andi v0,v0,0x60 -> 0x%02x" % mask)

    m += feature("items-per-floor", "Items per Floor",
                 "How many items the generator places (vanilla: rooms/2 + 0-3, open floors 8-15; at most 64).",
                 "Floor Layout")
    m += choice_option("items-per-floor", "amount", "Items", "more",
                       [("fewer", "Fewer (rooms/4 + 0-3)"), ("more", "More (rooms + 0-3)"),
                        ("lots", "Lots (rooms + 0-7)")])
    sra = {"fewer": "83200400", "more": "03200400", "lots": "03200400"}      # sra a0,a0,{2,0,0}
    for v, single in (("fewer", 4), ("more", 12), ("lots", 16)):
        m += ovl("items-per-floor", 0x8001E2AC, 4, replace=bytes.fromhex(sra[v]), when={"amount": v},
                 comment="sra a0,a0,1 (rooms/2)")
        m += ovl("items-per-floor", 0x8001E288, 2, replace=single.to_bytes(2, "little"), when={"amount": v},
                 comment="open floor base 8 -> %d" % single)
    m += ovl("items-per-floor", 0x8001E298, 1, replace=bytes([7]), when={"amount": "lots"},
             comment="andi v0,v0,3 -> 7")

    m += feature("traps-per-floor", "Traps per Floor",
                 "How many traps the generator places (vanilla: rooms/2 + 0-3 slots, open floors 4-7, limited by a budget of floor/2 + 0-63 where each trap costs 4-12). More/Lots also raise the budget (0-127 / 0-255).",
                 "Floor Layout")
    m += choice_option("traps-per-floor", "amount", "Traps", "fewer",
                       [("none", "None"), ("fewer", "Fewer (rooms/4 + 0-3)"), ("more", "More (rooms + 0-3)"),
                        ("lots", "Lots (rooms + 0-7)")])
    m += ovl("traps-per-floor", 0x8001F0A8, 4, replace=bytes.fromhex("21a80000"), when={"amount": "none"},
             comment="addu s5,a0,v0 -> move s5,zero")
    m += ovl("traps-per-floor", 0x8001F080, 4, replace=li(0, 21), when={"amount": "none"},
             comment="addiu s5,v0,4 -> li s5,0")
    for v, single in (("fewer", 2), ("more", 6), ("lots", 8)):
        m += ovl("traps-per-floor", 0x8001F0A4, 4, replace=bytes.fromhex(sra[v]), when={"amount": v},
                 comment="sra a0,a0,1 (rooms/2)")
        m += ovl("traps-per-floor", 0x8001F080, 2, replace=single.to_bytes(2, "little"), when={"amount": v},
                 comment="open floor base 4 -> %d" % single)
    m += ovl("traps-per-floor", 0x8001F090, 1, replace=bytes([7]), when={"amount": "lots"},
             comment="andi v0,v0,3 -> 7")
    for v, mask in (("more", 0x7F), ("lots", 0xFF)):     # trap budget floor/2 + (rand & 0x3f)
        m += ovl("traps-per-floor", 0x8001F0E0, 1, replace=bytes([mask]), when={"amount": v},
                 comment="trap budget andi 0x3f -> 0x%02x" % mask)

    # ---- Deeper Encounters (example table edit) --------------------------
    shift = 5
    deeper = []
    for f, spawn, eggs in stock_rows:
        src = stock_rows[min(f - 1 + shift, FLOORS - 1)]
        deeper.append((f, src[1], eggs))
    m += feature("deeper-encounters", "Deeper Encounters",
                 "Every floor uses the monster table of the floor %d levels higher (egg pools unchanged). Example of an encounter-table edit; make your own with re/scripts/make_dungeon_mod.py --custom." % shift,
                 "Dungeon")
    m += floor_patches("deeper-encounters", deeper, stock_rows)

    # ---- Bug fixes (community-documented, confirmed in code) ------------
    def raw_patch(fid, file_off, new, comment):
        old = stock(file_off, len(new))
        return ["", "[[patch]]  # " + comment, 'feature = "%s"' % fid, 'target = "disc_user"',
                "offset = 0x%X" % disc_off(file_off), 'expected = "%s"' % hexb(old), 'replace = "%s"' % hexb(new)]

    m += feature("fix-strength-talent", "Fix: Strength Increased familiars",
                 "Each collared familiar with the Strength Increased talent was meant to add 1/8 to Koh's melee and sword mix-magic damage, but the check (dungeon FUN_800C82B8) reads Koh's talents instead of the familiar's, so it never applies. One-instruction fix.",
                 "Gameplay Corrections")
    off = DUNGEON_MODULE[0] + (0x800C82E4 - DUNGEON_MODULE[1])
    m += raw_patch("fix-strength-talent", off, bytes.fromhex("5400428c"),
                   "lw v0,0x54(a0) -> lw v0,0x54(v0)")

    m += feature("fix-gaia-shoot", "Fix: Gaia Shoot element",
                 "DeoRock's mixture magic Gaia Shoot deals water damage although DeoRock is a wind spell (its fire/water siblings use their own element). Makes its damage wind-elemental.",
                 "Gameplay Corrections")
    m += raw_patch("fix-gaia-shoot", 0x1834800 + 68 * 0x6000 + 0x1340, bytes.fromhex("0c000724"),
                   "spell overlay 68: li a3,10 (water) -> li a3,12 (wind)")

    m += feature("fix-barong-rarity", "Fix: Barong item rarity",
                 "Barongs are meant to give back an item of the same rarity as the one thrown in (or lower after a few tries), but the check compares the thrown item with itself and always passes. Fixed to compare the candidate item.",
                 "Gameplay Corrections")
    for slot in range(7):
        base = ((31 - 1) * 0x54 + slot * 0xC + 0x4340 - DUNGEON_LBA) * 2048
        for rel, new, what in ((0x3EC0, "ff00a430", "andi a0,a1,0xff"), (0x3EDC, "0c00038e", "lw v1,12(s0)"),
                               (0x3F08, "ff00a430", "andi a0,a1,0xff"), (0x3F24, "0c00038e", "lw v1,12(s0)")):
            m += raw_patch("fix-barong-rarity", base + rel, bytes.fromhex(new),
                           "Barong code slot %d +0x%X -> %s" % (slot, rel, what))

    if args.custom:
        m += feature("custom-encounters", "Custom Encounters",
                     "Monster tables and egg pools from %s." % os.path.basename(args.custom), "Dungeon")
        m += floor_patches("custom-encounters", read_floors_csv(args.custom), stock_rows)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="\n") as fh:
        fh.write("\n".join(m) + "\n")
    print("wrote", OUT, "(%d lines)" % len(m))


if __name__ == "__main__":
    main()
