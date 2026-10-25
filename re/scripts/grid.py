"""grid.py out.png a.png b.png ... -> tile screenshots 3 per row for quick review."""
import sys
from PIL import Image
out, files = sys.argv[1], sys.argv[2:]
ims = [Image.open(f).convert('RGB') for f in files]
w, h = 320, 240
cols = min(3, len(ims))
rows = (len(ims) + cols - 1) // cols
g = Image.new('RGB', (w * cols, h * rows))
for i, im in enumerate(ims):
    g.paste(im.resize((w, h)), ((i % cols) * w, (i // cols) * h))
g.save(out)
