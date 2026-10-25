"""Build a US disc image that carries the Japanese voice files.

    python build_voice_disc.py   ->  disc/Azure Dreams (USA) (JP Voices).bin / .cue

The US engine still has the voice streaming path (script op 0x1D -> FUN_8003F540), but the US disc
lacks the voice files and the stream LBA table (EXE 0x8006CD50, entries 3..18) points them at MERGE.STR.
This copies the Japanese voice region (STRT/A02301AK.STR .. O00601FE.STR with their DUMMY spacers,
and STR/P00104AB.STR + DUMMYP) raw (XA sectors keep their subheaders) to the end of the US image,
rewrites each copied sector's address header, and patches the table in the disc's SLUS_006.14
(recomputing that sector's EDC/ECC). The game's file system is untouched; nothing else changes.
"""
import os, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
US_BIN = os.path.join(ROOT, r"disc\Azure Dreams (USA).bin")
JP_BIN = os.path.join(ROOT, r"disc\Azure Dreams (Japan).bin")
OUT_BIN = os.path.join(ROOT, r"disc\Azure Dreams (USA) (JP Voices).bin")
OUT_CUE = os.path.join(ROOT, r"disc\Azure Dreams (USA) (JP Voices).cue")
SECTOR = 2352

# Japanese stream table (SLPM 0x8006F38C) entries 3..18 = voice files A..P
JP_VOICE_LBAS = [11821, 18477, 24461, 29469, 34573, 40013, 47565, 57341, 59613, 72909, 76077,
                 78621, 83901, 85261, 87293, 107966]
JP_RANGES = [(11821, 88157), (107966, 108670)]   # A..O incl. DUMMY spacers; P + DUMMYP
US_EXE_LBA, US_EXE_T = 24, 0x8002D000
US_TABLE = 0x8006CD50


# ---------------------------------------------------------------- EDC / ECC (Mode 2 Form 1)
def _edc_table():
    t = []
    for i in range(256):
        e = i
        for _ in range(8):
            e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
        t.append(e)
    return t


EDC = _edc_table()
ECC_F = [0] * 256
ECC_B = [0] * 256
for i in range(256):
    j = (i << 1) ^ (0x11D if i & 0x80 else 0)
    ECC_F[i] = j & 0xFF
    ECC_B[i ^ j & 0xFF] = i


def edc(data):
    e = 0
    for b in data:
        e = EDC[(e ^ b) & 0xFF] ^ (e >> 8)
    return e


def ecc_block(src, major_count, minor_count, major_mult, minor_inc, dest, dest_off):
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = src[index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = ECC_F[a]
        a = ECC_B[ECC_F[a] ^ b]
        dest[dest_off + major] = a
        dest[dest_off + major + major_count] = a ^ b


def fix_mode2_form1(sec):
    """Recompute EDC and ECC of a raw Mode 2 Form 1 sector (bytearray of 2352)."""
    struct.pack_into("<I", sec, 0x818, edc(sec[16:0x818]))
    hdr = bytes(sec[12:16])
    sec[12:16] = b"\0\0\0\0"                       # Mode 2: ECC computed with a zero header
    src = sec[12:12 + 2340]
    ecc_block(src, 86, 24, 2, 86, sec, 0x81C)      # P parity
    src = sec[12:12 + 2340]
    ecc_block(src, 52, 43, 86, 88, sec, 0x8C8)     # Q parity
    sec[12:16] = hdr


def bcd(n):
    return ((n // 10) << 4) | (n % 10)


def set_msf(sec, lba):
    a = lba + 150
    sec[12], sec[13], sec[14] = bcd(a // 4500), bcd(a // 75 % 60), bcd(a % 75)


def main():
    us_size = os.path.getsize(US_BIN)
    n_us = us_size // SECTOR
    new_lba, starts = n_us, []
    for lo, hi in JP_RANGES:
        starts.append(new_lba)
        new_lba += hi - lo
    remap = {}
    for (lo, hi), st in zip(JP_RANGES, starts):
        for jl in JP_VOICE_LBAS:
            if lo <= jl < hi:
                remap[jl] = st + (jl - lo)
    table = [remap[j] for j in JP_VOICE_LBAS]
    print("US sectors %d; voice files at %s" % (n_us, table))
    with open(US_BIN, "rb") as f, open(OUT_BIN, "wb") as o:
        o.write(f.read())
    with open(JP_BIN, "rb") as j, open(OUT_BIN, "r+b") as o:
        o.seek(n_us * SECTOR)
        for (lo, hi), st in zip(JP_RANGES, starts):
            j.seek(lo * SECTOR)
            for k in range(hi - lo):
                sec = bytearray(j.read(SECTOR))
                set_msf(sec, st + k)
                o.write(sec)
        # patch the stream table in the US EXE on disc
        off = 0x800 + US_TABLE - US_EXE_T + 3 * 4
        for i, lba in enumerate(table):
            pos = off + 4 * i
            sl, so = US_EXE_LBA + pos // 2048, pos % 2048
            o.seek(sl * SECTOR)
            sec = bytearray(o.read(SECTOR))
            struct.pack_into("<I", sec, 24 + so, lba)
            fix_mode2_form1(sec)
            o.seek(sl * SECTOR)
            o.write(sec)
    with open(OUT_CUE, "w") as c:
        c.write('FILE "%s" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n' % os.path.basename(OUT_BIN))
    print("wrote", OUT_BIN, os.path.getsize(OUT_BIN) // SECTOR, "sectors")


if __name__ == "__main__":
    main()
