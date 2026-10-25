"""VRAM capture from the running dev build (vram_peek, 128x128 words per request).

    from vram import read_vram, page_png
    words = read_vram(320, 0, 64, 256)                 # 16-bit words, row-major
    page_png(320, 0, 4, (0, 466), 'kewne_page')        # 4bpp page through CLUT (x, y) -> re/shots/kewne_page.png
"""
import os, struct
from psx import Game, SHOTS

g = Game()


def read_vram(x, y, w, h):
    out = [[0] * w for _ in range(h)]
    for by in range(0, h, 128):
        for bx in range(0, w, 128):
            cw, ch = min(128, w - bx), min(128, h - by)
            r = g.cmd('vram_peek', x=x + bx, y=y + by, w=cw, h=ch)
            hx = r['hex']
            for j in range(ch):
                for i in range(cw):
                    k = (j * cw + i) * 4
                    out[by + j][bx + i] = int(hx[k:k + 4], 16)
    return out


def rgb15(c, stp_alpha=True):
    r, gg, b = (c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3
    a = 0 if c == 0 else 255
    return (r | r >> 5, gg | gg >> 5, b | b >> 5, a)


def clut(cx, cy, n):
    return [rgb15(c) for c in read_vram(cx, cy, n, 1)[0]]


def decode_page(x, y, bpp, clut_xy, w_texels=256, h=256):
    """Texels of a texture page as RGBA rows."""
    words_w = w_texels * bpp // 16
    words = read_vram(x, y, words_w, h)
    pal = clut(clut_xy[0], clut_xy[1], 16 if bpp == 4 else 256) if bpp < 16 else None
    rows = []
    for row in words:
        px = []
        for wd in row:
            if bpp == 4:
                px += [pal[(wd >> s) & 15] for s in (0, 4, 8, 12)]
            elif bpp == 8:
                px += [pal[wd & 255], pal[wd >> 8]]
            else:
                px.append(rgb15(wd))
        rows.append(px)
    return rows


def page_png(x, y, bpp, clut_xy, name, w_texels=256, h=256):
    from PIL import Image
    rows = decode_page(x, y, bpp, clut_xy, w_texels, h)
    im = Image.new('RGBA', (len(rows[0]), len(rows)))
    im.putdata([p for r in rows for p in r])
    path = os.path.join(SHOTS, name + '.png')
    im.save(path)
    return path
