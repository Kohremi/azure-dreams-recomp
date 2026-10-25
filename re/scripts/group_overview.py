"""Compact per-species overview: one row per animation group (front-diagonal sequence g*5+1)."""
import sys
from PIL import Image, ImageDraw
from sprite_banks import monster_bank, compose_frame, SPECIES

def overview(s, maxf=7, cw=46, ch=50):
    b = monster_bank(s)
    page = b.page_indices()
    ng = b.seq_count // 5
    out = Image.new('RGBA', (64 + maxf * cw, ng * ch + 14), (50, 56, 72, 255))
    dr = ImageDraw.Draw(out)
    dr.text((2, 1), '%d %s' % (s, SPECIES[s]), fill=(255, 160, 80))
    for gi in range(ng):
        steps, loop = b.sequence(gi * 5 + 1)
        y = 14 + gi * ch
        dr.text((2, y + 2), 'g%d' % gi, fill=(255, 255, 0))
        dr.text((2, y + 14), ('L' if loop >= 0 else '1') + '%d' % sum(t for t, o in steps), fill=(180, 200, 255))
        for j, (t, off) in enumerate(steps[:maxf]):
            im, ax, ay = compose_frame(b, off, page)
            if im.width > cw or im.height > ch:
                im = im.resize((max(1, im.width * 2 // 3), max(1, im.height * 2 // 3)))
                ax, ay = ax * 2 // 3, ay * 2 // 3
            out.alpha_composite(im, (max(0, 64 + j * cw + cw // 2 - ax), max(0, y + ch - 4 - ay)))
    return out

if __name__ == '__main__':
    sps = [int(a) for a in sys.argv[2:]]
    ims = [overview(s) for s in sps]
    W = sum(i.width for i in ims) + 6 * len(ims)
    H = max(i.height for i in ims)
    sheet = Image.new('RGBA', (W, H), (20, 20, 30, 255))
    x = 0
    for im in ims:
        sheet.alpha_composite(im, (x, 0)); x += im.width + 6
    sheet.save(sys.argv[1])
