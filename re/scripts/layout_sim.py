"""Python port of the room-placement half of the floor generator (floor overlay FUN_80019AF8),
using the game's RNG (dungeon FUN_800A6D30), to tune the Floor Layout mod options offline.

    python layout_sim.py                      # compare a few presets over 5000 floors each

Corridor digging is not simulated; floors with fewer than 2 placed rooms become one open room
(as in the game).
"""
import random, statistics


class Rng:
    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def next(self):                              # FUN_800A6D30
        self.s = (self.s * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
        return (self.s >> 16) & 0x7FFF

    def range(self, lo, hi):                     # FUN_800A6DA4
        if hi < lo:
            lo, hi = hi, lo
        return (self.next() & 0xFFFF) % (hi - lo + 1) + lo


def gen(seed, grid=None, room_mask=3, room_always=False, width_bonus=0, height_base=5, open_n=2):
    """Returns ('open', []) or ('rooms', [(x, y, w, h), ...])."""
    r = Rng(seed)
    def axis():
        v = r.next()
        if grid:
            return grid
        return 2 if (v & 0x7F) == 0 else 3 if (v & 0x1F) == 0 else 4
    cols = axis(); rows = axis()
    if r.range(0, 0x200) < open_n:
        return "open", []
    cells = rows * cols
    is_room = [True if room_always else (r.next() & room_mask) != 0 for _ in range(cells)]
    claimed = [[0] * 64 for _ in range(64)]
    rooms = []

    def region_free(x, y, w, h):                 # FUN_80017584
        if y < 1 or x < 1 or y + h >= 64 or x + w >= 64:
            return False
        return all(claimed[yy][xx] == 0 for yy in range(y, y + h) for xx in range(x, x + w))

    for row in range(rows):
        for c in range(cols):
            i = row * cols + c
            if not is_room[i]:
                r.next(); r.next(); r.next()
                continue
            cw, ch = 64 // cols, 64 // rows
            x0 = r.range(0, cw // 2 - 1) + c * cw
            y0 = r.range(0, ch // 2 - 1) + row * ch
            w = r.range(0, cw // 2 - 1) + width_bonus
            h = max(5, r.range(0, ch // 2 - 1) + height_base)
            if not region_free(x0 - 2, y0 - 2, w + 9, h + 4):
                r.next(); r.next(); r.next()
                continue
            for yy in range(y0 - 2, y0 + h + 2):
                for xx in range(x0 - 2, x0 + w + 7):
                    claimed[yy][xx] = i + 1
            rooms.append((x0 + 1, y0 + 1, w + 3, h - 2))
            r.next()
    if len(rooms) < 2:
        return "open", []
    return "rooms", rooms


def summarize(label, n=5000, **kw):
    counts, areas, opens = [], [], 0
    rnd = random.Random(1234)
    for _ in range(n):
        kind, rooms = gen(rnd.getrandbits(32), **kw)
        if kind == "open":
            opens += 1
            continue
        counts.append(len(rooms))
        areas += [w * h for _, _, w, h in rooms]
    print("%-34s rooms %4.1f (min %d, max %d)  room area %5.1f  open floors %4.1f%%" % (
        label, statistics.mean(counts), min(counts), max(counts), statistics.mean(areas), 100 * opens / n))


if __name__ == "__main__":
    summarize("vanilla")
    summarize("grid 3x3", grid=3)
    summarize("grid 2x2", grid=2)
    summarize("always rooms", room_always=True)
    summarize("always rooms, grid 3x3", grid=3, room_always=True)
    for wb, hb in ((1, 1), (2, 2), (3, 3), (4, 4)):
        summarize("size +%d/+%d" % (wb, hb), width_bonus=wb, height_base=5 + hb)
        summarize("size +%d/+%d, grid 3x3, always" % (wb, hb), width_bonus=wb, height_base=5 + hb, grid=3,
                  room_always=True)
        summarize("size +%d/+%d, grid 2x2, always" % (wb, hb), width_bonus=wb, height_base=5 + hb, grid=2,
                  room_always=True)
