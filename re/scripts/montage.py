import sys
from PIL import Image, ImageDraw
src, out = sys.argv[1], sys.argv[2]
lo = int(sys.argv[3]) if len(sys.argv) > 3 else 0
hi = int(sys.argv[4]) if len(sys.argv) > 4 else 99999
lines = open(src).read().splitlines()
shots = [(int(l.split()[1][1:]), l.split(None, 2)[2]) for l in lines if l.startswith('SHOT')]
shots = [s for s in shots if lo <= s[0] <= hi]
cols = 7; w, h = 320, 224; s = 0.5
im = Image.new('RGB', (int(cols * w * s), int(((len(shots) + cols - 1) // cols) * (h * s + 12))), (0, 0, 0))
dr = ImageDraw.Draw(im)
for i, (el, p) in enumerate(shots):
    t = Image.open(p).convert('RGB').resize((int(w * s), int(h * s)))
    x, y = (i % cols) * int(w * s), (i // cols) * int(h * s + 12)
    im.paste(t, (x, y + 12)); dr.text((x + 2, y), '+%d' % el, fill=(255, 255, 0))
im.save(out)
print(len(shots))
