r"""Render the current dungeon floor of the running dev build to a PNG and print stats.
Run with the repository's .venv Python (needs Pillow).

    >>> from floor_render import floor_stats, render_floor
    >>> print(floor_stats()); render_floor('f2_vanilla')       # -> re/shots/f2_vanilla.png
"""
import os, struct
from attach import g, KOH, unit_grid, tile_map, stairs, floor_number
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOMS = 0x800E2970        # 36 x 20 bytes: x, y, w, h, height, active, connected, ...
ITEMS = 0x800E3548        # 64 x {id, category, charges, flags}; positions 0x800E36C8 (12 bytes each)
ITEM_POS = 0x800E36C8
TRAPS = 0x800E3648        # 32 x 4 bytes; positions 0x800E39C8 + 6 (24 bytes each)
TRAP_POS = 0x800E39C8


def rooms():
    out = []
    raw = g.read(ROOMS, 36 * 20)
    for i in range(36):
        x, y, w, h, hgt, active, conn = struct.unpack_from('<7h', raw, i * 20)
        if active:
            out.append(dict(x=x, y=y, w=w, h=h, height=hgt, connected=conn))
    return out


def items():
    raw, pos = g.read(ITEMS, 64 * 4), g.read(ITEM_POS, 64 * 12)
    return [(raw[i * 4 + 1], raw[i * 4], pos[i * 12], pos[i * 12 + 1]) for i in range(64) if raw[i * 4 + 1]]


def traps():
    raw, pos = g.read(TRAPS, 32 * 4), g.read(TRAP_POS, 32 * 24)
    return [(raw[i * 4], pos[i * 24 + 6], pos[i * 24 + 7]) for i in range(32) if raw[i * 4 + 1]]


def monsters():
    head = g.u32(0x800814A8)
    u, n = head, 0
    for _ in range(96):
        b = g.read(u, 0x30)
        if not (b[0x15] & 0x40) and 1 <= b[0x13] < 48 and b[0x28]:
            n += 1
        u = g.u32(u + 0x5C) + 0x20
        if u == head:
            break
    return n


def floor_stats():
    m = tile_map()
    r = rooms()
    return dict(floor=floor_number(), rooms=len(r), room_count_var=g.u16(0x8008146E),
                walkable_tiles=len(m), items=len(items()), traps=len(traps()), monsters=monsters(),
                avg_room_area=round(sum(x['w'] * x['h'] for x in r) / max(1, len(r)), 1),
                heights=sorted({x['height'] for x in r}))


def render_floor(name, scale=6):
    from PIL import Image, ImageDraw
    m = tile_map()
    im = Image.new('RGB', (64 * scale, 64 * scale), (16, 16, 20))
    d = ImageDraw.Draw(im)
    if m:
        lo, hi = min(m.values()), max(m.values())
    for (x, y), h in m.items():
        t = 0 if hi == lo else (h - lo) / (hi - lo)
        c = (int(70 + 120 * t), int(90 + 110 * t), int(110 + 60 * t))
        d.rectangle([x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1], fill=c)
    for r in rooms():
        d.rectangle([r['x'] * scale, r['y'] * scale, (r['x'] + r['w']) * scale - 1, (r['y'] + r['h']) * scale - 1],
                    outline=(240, 200, 60))

    def dot(x, y, col, rad=None):
        rad = rad or scale // 2
        cx, cy = x * scale + scale // 2, y * scale + scale // 2
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=col)

    for _, _, x, y in items():
        dot(x, y, (80, 220, 90))
    for _, x, y in traps():
        dot(x, y, (230, 60, 60))
    for x, y in stairs():
        dot(x, y, (250, 250, 250), scale)
    kx, ky = unit_grid(KOH)
    dot(kx, ky, (80, 160, 255), scale)
    path = os.path.join(os.path.join(REPO_ROOT, r"re\shots"), name + '.png')
    im.save(path)
    return path


if __name__ == '__main__':
    print(floor_stats())
    print(render_floor('floor_now'))
