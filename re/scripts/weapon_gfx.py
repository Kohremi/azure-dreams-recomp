"""Koh's sword / rod / shield graphics, as the game uploads them on equip.

EXE FUN_80048500(id, kind) (kind 0 sword, 1 rod, 2 shield; called from the dungeon's equip code
FUN_800982A8 via FUN_80048568 / FUN_80048590 / FUN_800485B8) reads the record listed at
*(0x800710E4 + 4 kind) + 8 id: {u32 size << 12 | buffer, u32 LBA} (absolute disc sectors; swords 2
sectors each, rods and shields 1), then FUN_80041344 runs its upload commands, 16-byte records
{u16 type, u16 next, u32 data offset, params}: type 1 = LZ (FUN_8004068C) then LoadImage to the rect
{x, y, w words, h}; type 2 = 16-colour CLUT upload to the CLUT id. Swords and rods fill VRAM 928,128
(32 words x 128 rows: texels u 128-255, v 128-255 of the overlay page at 896,0) with CLUT 0x7A40;
shields fill 928,0 (24 words x 120 rows: u 128-223, v 0-119) with CLUT 0x7A41. Koh's frame records
with flags 0x40 draw from that page: clut 0x7A40 = the weapon (16x16 cells), 0x7A41 = the shield
(24x24 cells). No weapon: the area is cleared (FUN_800483AC).

    python weapon_gfx.py            sheet of everything -> re/shots/weapon_gfx.png
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sprite_banks import lz_decode  # noqa: E402
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DISC_BIN = os.path.join(REPO_ROOT, r'disc\Azure Dreams (USA).bin')
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shots')

# First LBA of each kind's id 0 record and sectors per record (the EXE table at 0x800710E4).
TABLES = {'sword': (0x42AB, 2, 12), 'rod': (0x42C4, 1, 9), 'shield': (0x42CE, 1, 11)}


def lba_of(kind, item_id):
    first, per, _n = TABLES[kind]
    if kind == 'sword':
        return first + 1 + 2 * (item_id - 1) if item_id > 0 else first
    return first + item_id


def read_sectors(lba, n):
    out = b''
    with open(DISC_BIN, 'rb') as f:
        for k in range(n):
            f.seek((lba + k) * 2352 + 24)
            out += f.read(2048)
    return out


def records(data):
    p = 0
    while True:
        typ, nxt, off = struct.unpack_from('<HHI', data, p)
        if not 1 <= typ <= 9:
            break
        yield typ, data[p:p + 16], off
        if nxt == 0:
            break
        p += nxt


def load(kind, item_id):
    """(width, height, colour indices row-major, palette [(r, g, b, a)] * 16)."""
    data = read_sectors(lba_of(kind, item_id), TABLES[kind][1])
    image = None
    pal = None
    for typ, rec, off in records(data):
        if typ == 1:
            x, y, w, h = struct.unpack_from('<4H', rec, 8)
            raw = lz_decode(data, off)
            idx = bytearray(w * 4 * h)
            for i in range(min(len(raw), w * 2 * h)):
                idx[i * 2] = raw[i] & 15
                idx[i * 2 + 1] = raw[i] >> 4
            image = (w * 4, h, bytes(idx))
        elif typ == 2:
            pal = []
            for i in range(16):
                c = struct.unpack_from('<H', data, off + i * 2)[0]
                r, g, b = (c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3
                pal.append((r | r >> 5, g | g >> 5, b | b >> 5, 0 if c == 0 else 255))
    return image[0], image[1], image[2], pal


def to_image(kind, item_id):
    from PIL import Image
    w, h, idx, pal = load(kind, item_id)
    im = Image.new('RGBA', (w, h))
    im.putdata([pal[i] for i in idx])
    return im


def main():
    from PIL import Image
    tiles = []
    for kind, (_f, _p, n) in TABLES.items():
        for i in range(1, n + 1):
            tiles.append(to_image(kind, i))
    cols = 8
    cw, ch = 130, 130
    sheet = Image.new('RGBA', (cols * cw, ((len(tiles) + cols - 1) // cols) * ch), (40, 40, 60, 255))
    for k, im in enumerate(tiles):
        sheet.alpha_composite(im, ((k % cols) * cw, (k // cols) * ch))
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, 'weapon_gfx.png')
    sheet.save(path)
    print(path)


if __name__ == '__main__':
    main()
