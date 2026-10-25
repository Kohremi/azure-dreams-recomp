r"""Run with the repository's .venv Python (needs Pillow).

From save slot 0 (town, at the tower stairs) play the Kewne event and enter 1F,
so the dungeon module is freshly read from disc (needed to test disc_user code patches
on the dungeon module, which a later save state would otherwise carry unpatched)."""
from attach import *


def naming_screen_up():
    """The naming screen's letter-mode panel draws red icons at (186,64) and (186,82)."""
    from PIL import Image
    p = g.shot('_naming_probe')
    if not p:
        return False
    im = Image.open(p).convert('RGB')
    return all(im.getpixel(xy) == (216, 64, 64) for xy in ((186, 64), (186, 82)))


def enter_tower(name_letters=3):
    g.load_state(0); g.wait_frames(20)
    for _ in range(150):                    # dialogue until the naming screen is up
        if naming_screen_up():
            break
        g.tap('cross', frames=3, gap=16)
    g.wait_frames(30)
    for b in ['up', 'up', 'up', 'up']:      # cursor onto the letter grid
        g.tap(b, gap=6)
    g.tap('cross', frames=6, gap=20)        # first letter
    for _ in range(name_letters - 1):
        g.tap('right', frames=6, gap=10); g.tap('cross', frames=6, gap=20)
    g.tap('triangle', frames=6, gap=20); g.tap('cross', frames=6, gap=40)   # Go End, confirm
    for _ in range(40):
        g.tap('cross', frames=3, gap=16)
    for _ in range(40):
        g.wait_frames(40)
        if floor_number() == 1 and g.u32(0x8009BFF8) == 0x27BDFFC8:
            break
    g.wait_frames(60)
    return floor_number()


if __name__ == '__main__':
    print('floor', enter_tower())
