"""Find every town location overlay event table in TOWN.BIN.

A location overlay is a sector-aligned TOWN.BIN chunk loaded at 0x80016000. Its event table is a
list of {u32 key, u32 ptr} pairs (ends with ptr == 0); ptr points inside the same overlay at a
{u32 size_bytes, u32 lba} script descriptor; the script chunk (at lba) is loaded to the address the
overlay registers (0x8001DCD0 in the overlays seen so far). key: bits 24-29 = id (character),
bits 16-22 = variant, bit 23 = flag (see town FUN_8008AF2C).
"""
import json, os, struct
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
D = open(os.path.join(ROOT, r"extracted\TOWN\TOWN.BIN"), "rb").read()
TOWN_LBA = 3077
NSEC = len(D) // 2048
BASE = 0x80016000
WINDOW = 0xA000


def looks_like_script(lba, size):
    if not (TOWN_LBA <= lba < TOWN_LBA + NSEC and 8 <= size <= 0x8000):
        return False
    o = (lba - TOWN_LBA) * 2048
    hdr = struct.unpack_from("<I", D, o)[0]
    b = D[o + 4]
    return hdr < 0x400 and (b < 0x58 or b >= 0x81)


def main():
    n = len(D) // 4
    words = struct.unpack("<%dI" % n, D[:n * 4])
    descs = []
    for k in range(n - 1):
        size, lba = words[k], words[k + 1]
        if looks_like_script(lba, size):
            descs.append(k * 4)
    print("descriptor candidates:", len(descs))
    tables = {}
    for P in descs:
        for S in range((P // 0x800) * 0x800, max(-1, P - WINDOW), -0x800):
            ptr = BASE + (P - S)
            needle = struct.pack("<I", ptr)
            i = D.find(needle, S, S + WINDOW)
            while i >= 0:
                if (i - S) % 4 == 4 % 4 and i % 4 == 0:
                    # table entry = (key at i-4, ptr at i); walk back to the table start
                    t = i - 4
                    while t - 8 >= S and BASE <= struct.unpack_from("<I", D, t - 4)[0] < BASE + WINDOW \
                            and struct.unpack_from("<I", D, t - 4)[0] != 0:
                        p2 = struct.unpack_from("<I", D, t - 4)[0]
                        s2, l2 = struct.unpack_from("<II", D, S + (p2 - BASE))
                        if not looks_like_script(l2, s2):
                            break
                        t -= 8
                    tables.setdefault((S, t), None)
                i = D.find(needle, i + 1, S + WINDOW)
    out = []
    for (S, t) in sorted(tables):
        entries = []
        a = t
        while a + 8 <= len(D):
            key, ptr = struct.unpack_from("<II", D, a)
            if ptr == 0 or not (BASE <= ptr < BASE + WINDOW):
                break
            size, lba = struct.unpack_from("<II", D, S + (ptr - BASE))
            if not looks_like_script(lba, size):
                break
            entries.append(dict(key="0x%08X" % key, id=(key >> 24) & 0x3F, variant=(key >> 16) & 0x7F,
                                flag=(key >> 23) & 1, size=size, lba=lba,
                                town_offset="0x%06X" % ((lba - TOWN_LBA) * 2048)))
            a += 8
        if entries:
            out.append(dict(overlay_offset="0x%06X" % S, table_ram="0x%08X" % (BASE + t - S), entries=entries))
    # one overlay may yield the same table through several descriptors; dedupe
    seen, uniq = set(), []
    for o in out:
        k = (o["overlay_offset"], o["table_ram"])
        if k not in seen:
            seen.add(k); uniq.append(o)
    json.dump(uniq, open(os.path.join(ROOT, r"re\events\event_tables.json"), "w"), indent=1)
    print("tables:", len(uniq), " entries:", sum(len(o["entries"]) for o in uniq),
          " distinct scripts:", len({e["lba"] for o in uniq for e in o["entries"]}))
    for o in uniq[:12]:
        print(o["overlay_offset"], o["table_ram"], [(e["id"], e["variant"], e["town_offset"]) for e in o["entries"]][:8])


if __name__ == "__main__":
    main()
