r"""Azure Dreams sprite banks in DUNGEON.BIN: the monster part-animation banks and Koh's per-frame bank.

Bank layout (offsets relative to the bank start; EXE FUN_80046F88 turns them into pointers at load):
  +00 sequence table offset (u32 per sequence)    +04 sequence count
  +08 sprite records offset                        +0C pixel data offset (per-frame banks)
  +10 record count                                 +14 static texture page offset (4bpp 256x256)
  +18 bits per pixel (4; 0 = per-frame 8bpp)       +1C CLUT offset          +20 CLUT colours
Sequence: 8-byte steps {u16 ticks, u16 op, u32 offset}. op 2 = show frame list `offset` for `ticks` VBlanks
  (60 Hz: the stepper EXE FUN_800477F4 runs every other VBlank and divides by DAT_80080A84 = 2),
  op 1 = loop to step `offset`, op 0 = end (the animation holds its last frame and reports finished).
Frame list: 12-byte records {flags, GP0 code, s8 x, s8 y, u16 tpage, u16 clut, u8 u, v, w, h} relative to
  the unit's anchor; flags 0x80 = last record, 0x40 = static page, 0x20 = keep CLUT, 0x08 = relocated (set
  at load by FUN_80047054), 0x01 = see `mirror_alt` below.
Direction: the game picks sequence `group*5 + [2,1,0,1,2,3,4,3][r]` for view-relative direction
  r = (camera yaw + facing + 0x100) >> 9 & 7 and mirrors for r in {0, 1, 7} (EXE table 0x8006CCF8):
  sequence 0 of a group faces the camera, 2 faces screen-left, 4 faces away.

    python sprite_banks.py            dump every species: re/sprites/sp_NN.png (atlas), sp_NN_sheet.png
"""
import os, struct, json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
DUNGEON = os.path.join(ROOT, r"extracted\DUNGEON\DUNGEON.BIN")
MONSTER_BASE = 0x1375800      # species 2 (Kewne); species s at MONSTER_BASE + (s - 2) * MONSTER_STRIDE
MONSTER_STRIDE = 0x15800
KOH_BANK = 0x4DB800
SPECIES = ['Koh', 'Hikewne', 'Kewne', 'Dragon', 'Kid', 'Ifrit', 'Flame', 'Grineut', 'Griffon', 'Saber', 'Snowman',
           'Ashra', 'Arachne', 'Battnel', 'Nyuel', 'Death', 'Clown', 'Univern', 'Unicorn', 'Metal', 'Block',
           'Pulunpa', 'Troll', 'Noise', 'U-Boat', 'Baloon', 'Dreamin', 'Blume', 'Volcano', 'Cyclone', 'Manoeva',
           'Barong', 'Picket', 'Kraken', 'Weadog', 'Stealth', 'Viper', 'Naplass', 'Zu', 'Mandara', 'Killer',
           'Garuda', 'Glacier', 'Tyrant', 'Golem', 'Maximum', 'Frog', 'Salamander']
DIR_SEQ = [2, 1, 0, 1, 2, 3, 4, 3]
DIR_MIRROR = [1, 1, 0, 0, 0, 0, 0, 1]

_disc = None


def disc():
    global _disc
    if _disc is None:
        _disc = open(DUNGEON, 'rb').read()
    return _disc


def s8(b):
    return b - 256 if b > 127 else b


class Bank:
    def __init__(self, offset, data=None):
        self.d = data or disc()
        self.base = offset
        h = struct.unpack_from('<9I', self.d, offset)
        (self.seq_off, self.seq_count, self.rec_off, self.pix_off, self.rec_count,
         self.page_off, self.bpp, self.clut_off, self.clut_n) = h
        self.valid = self.seq_off == 0x28 and 0 < self.seq_count < 400

    def u32(self, off):
        return struct.unpack_from('<I', self.d, self.base + off)[0]

    def frame_list(self, off):
        recs = []
        p = self.base + off
        for _ in range(64):
            b = self.d[p:p + 12]
            recs.append(dict(flags=b[0], code=b[1], x=s8(b[2]), y=s8(b[3]),
                             tpage=b[4] | b[5] << 8, clut=b[6] | b[7] << 8, u=b[8], v=b[9], w=b[10], h=b[11]))
            p += 12
            if b[0] & 0x80:
                break
        return recs

    def sequence(self, i):
        """[(ticks, frame_offset)], loop_step (-1 = plays once)."""
        start = self.u32(0x28 + i * 4)
        steps, loop = [], -1
        p = start
        for _ in range(256):
            ticks, op, arg = struct.unpack_from('<HHI', self.d, self.base + p)
            if op == 2:
                steps.append((ticks, arg))
            elif op == 1:
                loop = (arg - start) // 8
                break
            else:
                break
            p += 8
        return steps, loop

    # The static page is the second file of the pair: 4 upload chunks of 32 words x 128 rows at +0xD000
    # (x 0-31/rows 0-127, x 0-31/rows 128-255, x 32-63/rows 0-127, x 32-63/rows 128-255; EXE
    # FUN_8004713C), CLUT at +0x15000. The header's +0x14/+0x1C fields are not used for these.
    PAGE_AT = 0xD000
    CLUT_AT = 0x15000

    def palette(self, k=0):
        """16-colour palette k (a record's clut field picks it: the species' CLUTs sit side by side,
        clut += relocation at load, FUN_80047054). Colour 0x0000 is transparent."""
        out = []
        for i in range(16):
            c = struct.unpack_from('<H', self.d, self.base + self.CLUT_AT + (k & 0x3F) * 32 + i * 2)[0]
            r, g, b = (c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3
            out.append((r | r >> 5, g | g >> 5, b | b >> 5, 0 if c == 0 else 255))
        return out

    def page_indices(self):
        """Static 4bpp 256x256 page as 65536 colour indices (row-major)."""
        idx = bytearray(256 * 256)
        p = self.base + self.PAGE_AT
        for chunk in range(4):
            cx, cy = (chunk // 2) * 128, (chunk & 1) * 128
            for row in range(128):
                o = p + chunk * 0x2000 + row * 64
                for i in range(64):
                    b = self.d[o + i]
                    idx[(cy + row) * 256 + cx + i * 2] = b & 15
                    idx[(cy + row) * 256 + cx + i * 2 + 1] = b >> 4
        return idx

    def page_rgba(self, k=0):
        """Static page as a flat RGBA list in palette k."""
        pal = self.palette(k)
        return [pal[i] for i in self.page_indices()]

    def part_offsets(self, list_off, recs):
        """Pixel offsets (from header +0x0C) of a frame list's per-frame parts, (flags & 0x60) == 0:
        u16s stored just before the list, the first such part's nearest (EXE FUN_800475a4)."""
        out = {}
        k = 0
        for i, r in enumerate(recs):
            if r['flags'] & 0x60 == 0:
                k += 1
                out[i] = struct.unpack_from('<H', self.d, self.base + list_off - 2 * k)[0]
        return out

    def part_pixels(self, off, w, h):
        """A per-frame part's w x h colour indices. The game uploads it as (w+3)>>2 words x h+1 rows
        (FUN_80047338) after decoding it with FUN_800407c0 (rle4_decode)."""
        width = ((w + 3) >> 2) * 4
        nib = rle4_decode(self.d, self.base + self.pix_off + off, width, h + 1)
        return bytes(nib[y * width + x] for y in range(h) for x in range(w))


def rle4_decode(src, p, width, rows):
    """EXE FUN_800407c0: a 4bpp image as nibble runs; returns width x rows colour indices (row-major).
    Byte 0 odd: a row-major stream follows. Byte 0 even: column-major (pixel columns top to bottom) with
    byte0 >> 1 bytes per row, then a u16 byte count; byte 0 = 0 is a raw copy of that many bytes.
    Stream bytes: c & 0xF0 != 0 -> (c >> 4) + 1 nibbles of c & 0xF; else c literal bytes (high nibble
    first) follow, and c = 0 ends a row-major stream."""
    total = width * rows
    out = bytearray(total)
    b0 = src[p]
    if b0 == 0:
        n = src[p + 1] | src[p + 2] << 8
        for i in range(min(n * 2, total)):
            b = src[p + 3 + i // 2]
            out[i] = (b >> 4) if i & 1 else (b & 15)
        return out
    if b0 & 1:
        bw, bh, q = width, rows, p + 1
        order = list(range(total))
    else:
        bw = (b0 >> 1) * 2
        bh = (src[p + 1] | src[p + 2] << 8) // (b0 >> 1)
        q = p + 3
        order = [y * bw + x for x in range(bw) for y in range(bh)]
    buf = bytearray(bw * bh)
    k = 0
    while k < len(order):
        c = src[q]
        q += 1
        if c & 0xF0:
            for _ in range((c >> 4) + 1):
                if k < len(order):
                    buf[order[k]] = c & 15
                k += 1
        elif c == 0:
            if b0 & 1:
                break
        else:
            for _ in range(c):
                v = src[q]
                q += 1
                for nb in (v >> 4, v & 15):
                    if k < len(order):
                        buf[order[k]] = nb
                    k += 1
    for y in range(min(rows, bh)):
        for x in range(min(width, bw)):
            out[y * width + x] = buf[y * bw + x]
    return out


def lz_decode(src, p):
    """EXE FUN_8004068C: flag bits LSB-first; 0 = literal; 10 = 12-bit distance with 4-bit length
    (0 = an extra length byte), 11 = 2-bit length with an 8-bit distance (0 = 256); distance 0 ends."""
    out = bytearray()
    flags = 0
    cnt = 1

    def bit():
        nonlocal flags, cnt, p
        cnt -= 1
        if cnt == 0:
            flags = src[p]
            p += 1
            cnt = 8
        b = flags & 1
        flags >>= 1
        return b

    while True:
        if bit() == 0:
            out.append(src[p])
            p += 1
            continue
        if bit() == 0:
            v = src[p] << 8 | src[p + 1]
            if v == 0:
                return bytes(out)
            p += 2
            if src[p - 1] & 0xF == 0:
                n = src[p] + 1
                p += 1
            else:
                n = (v & 0xF) + 2
            dist = v >> 4
        else:
            a = bit()
            b = bit()
            n = a * 2 + 2 + b
            dist = src[p] or 0x100
            p += 1
        for _ in range(n):
            out.append(out[-dist])


def run_expand(data):
    """EXE FUN_80048764: each byte = (b >> 6) + 1 copies of colour index b & 0x3F; bytes 01 01 end."""
    out = bytearray()
    i = 0
    while i < len(data) and not (data[i] == 1 and i + 1 < len(data) and data[i + 1] == 1):
        b = data[i]
        out += bytes([b & 0x3F]) * ((b >> 6) + 1)
        i += 1
    return bytes(out)


def koh_palette(bank):
    out = []
    for i in range(256):
        c = struct.unpack_from('<H', bank.d, bank.base + bank.clut_off + i * 2)[0]
        r, g, b = (c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3
        out.append((r | r >> 5, g | g >> 5, b | b >> 5, 0 if c == 0 else 255))
    return out


def koh_part_image(bank, list_off, recs, pal):
    """Decoded images of a Koh frame list's per-frame (flags & 0x60 == 0) records, keyed by index."""
    from PIL import Image
    images = {}
    k = 0
    for i, r in enumerate(recs):
        if r['flags'] & 0x60:
            continue
        k += 1
        img_off = bank.u32(list_off - 4 * k)
        words = (r['w'] + 1) >> 1
        rows = r['h'] + 1
        raw = run_expand(lz_decode(bank.d, bank.base + bank.pix_off + img_off))
        im = Image.new('RGBA', (words * 2, rows))
        px = [pal[c] for c in raw[:words * 2 * rows]]
        px += [(0, 0, 0, 0)] * (words * 2 * rows - len(px))
        im.putdata(px)
        images[i] = im.crop((0, 0, r['w'], r['h']))
    return images


def monster_bank(species):
    return Bank(MONSTER_BASE + (species - 2) * MONSTER_STRIDE)


def part_rect(r):
    """Screen span of a record. Flag 0x01 parts are drawn flipped and reflected about the anchor,
    [1 - x - w, 1 - x): the front and back views pair each half with its mirror image (checked
    against GP0 captures of a Pulunpa back view and a Kewne front view). Flag 0x02 does the same
    vertically (the draw routine FUN_8004C36C negates y and flips the quad)."""
    x0, x1 = (1 - r['x'] - r['w'], 1 - r['x']) if r['flags'] & 1 else (r['x'], r['x'] + r['w'])
    y0, y1 = (1 - r['y'] - r['h'], 1 - r['y']) if r['flags'] & 2 else (r['y'], r['y'] + r['h'])
    return x0, y0, x1, y1


def compose_frame(bank, list_off, page_idx=None):
    """Compose one monster frame list. Static parts (flag 0x40) come from the species page; the others
    ((flags & 0x60) == 0) are decoded from the bank's pixel data, as the game uploads them each frame;
    each part uses its record's palette. Flag 0x20 records are markers (w = h = 0) and draw nothing.
    Records draw back to front (the list's first record is drawn last). Returns (image, ax, ay)."""
    from PIL import Image, ImageOps
    if page_idx is None:
        page_idx = bank.page_indices()
    recs = bank.frame_list(list_off)
    offs = bank.part_offsets(list_off, recs)
    parts = []
    for i, r in enumerate(recs):
        r = dict(r)
        if not (r['flags'] & 0x40 or i in offs):
            continue
        if r['flags'] & 0x40 and r['u'] + r['w'] > 0xFF:
            r['w'] -= 1                 # the draw routine trims a part that would wrap the page
        if r['flags'] & 0x40 and r['v'] + r['h'] > 0xFF:
            r['h'] -= 1
        if r['w'] > 0 and r['h'] > 0:
            parts.append((i, r))
    if not parts:
        return Image.new('RGBA', (1, 1)), 0, 0
    rects = [part_rect(r) for _, r in parts]
    x0 = min(q[0] for q in rects)
    y0 = min(q[1] for q in rects)
    x1 = max(q[2] for q in rects)
    y1 = max(q[3] for q in rects)
    im = Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0))
    pals = {}
    for (i, r), q in reversed(list(zip(parts, rects))):
        w, h = r['w'], r['h']
        if i in offs:
            idx = bank.part_pixels(offs[i], w, h)
        else:
            idx = bytes(page_idx[(r['v'] + y) * 256 + r['u'] + x] for y in range(h) for x in range(w))
        k = r['clut'] & 0x3F
        if k not in pals:
            pals[k] = bank.palette(k)
        piece = Image.new('RGBA', (w, h))
        piece.putdata([pals[k][c] for c in idx])
        if r['flags'] & 1:
            piece = ImageOps.mirror(piece)
        if r['flags'] & 2:
            piece = ImageOps.flip(piece)
        im.alpha_composite(piece, (q[0] - x0, q[1] - y0))
    return im, -x0, -y0


def compose(page_img, recs):
    """Compose one frame list into an image (records draw back to front: the list's first record
    is drawn last). Returns (PIL image, anchor_x, anchor_y)."""
    from PIL import Image, ImageOps
    parts = [r for r in recs if r['w'] and r['h']]
    if not parts:
        return Image.new('RGBA', (1, 1)), 0, 0
    rects = [part_rect(r) for r in parts]
    x0 = min(q[0] for q in rects)
    y0 = min(q[1] for q in rects)
    x1 = max(q[2] for q in rects)
    y1 = max(q[3] for q in rects)
    im = Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0))
    for r, q in reversed(list(zip(parts, rects))):
        piece = page_img.crop((r['u'], r['v'], r['u'] + r['w'], r['v'] + r['h']))
        if r['flags'] & 1:
            piece = ImageOps.mirror(piece)
        im.alpha_composite(piece, (q[0] - x0, q[1] - y0))
    return im, -x0, -y0


if __name__ == '__main__':
    import sys
    from PIL import Image, ImageDraw
    out_dir = os.path.join(ROOT, r're\sprites')
    os.makedirs(out_dir, exist_ok=True)
    only = [int(a) for a in sys.argv[1:]] or range(1, 48)
    for s in only:
        b = monster_bank(s)
        page = Image.new('RGBA', (256, 256))
        page.putdata(b.page_rgba())
        page.save(os.path.join(out_dir, 'sp_%02d_page.png' % s))
        idx = b.page_indices()
        # Contact sheet: one row per sequence, every frame with its tick count.
        rows = []
        for i in range(b.seq_count):
            steps, loop = b.sequence(i)
            rows.append([(compose_frame(b, off, idx), t) for t, off in steps])
        cw, ch = 64, 70
        cols = max(len(r) for r in rows)
        sheet = Image.new('RGBA', (60 + cols * cw, len(rows) * ch), (40, 44, 60, 255))
        dr = ImageDraw.Draw(sheet)
        for i, row in enumerate(rows):
            steps, loop = b.sequence(i)
            dr.text((2, i * ch + 2), '%d g%d.%d' % (i, i // 5, i % 5), fill=(255, 255, 0))
            dr.text((2, i * ch + 14), 'loop%d' % loop if loop >= 0 else 'once', fill=(180, 180, 255))
            for j, ((im, ax, ay), t) in enumerate(row):
                ox, oy = 60 + j * cw + 32, i * ch + 56
                sheet.alpha_composite(im, (max(0, ox - ax), max(0, oy - ay)))
                dr.text((60 + j * cw + 2, i * ch + 58), str(t), fill=(200, 255, 200))
        sheet.save(os.path.join(out_dir, 'sp_%02d_sheet.png' % s))
        print(s, SPECIES[s], 'sequences', b.seq_count, 'records', b.rec_count)
