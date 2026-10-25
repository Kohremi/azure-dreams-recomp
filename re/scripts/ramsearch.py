"""Snapshot-diff helpers for locating game variables in the running dev build."""
import struct
from psx import Game

g = Game()
BASE = 0x80000000


def snap():
    return g.ram()


def words(buf, size=2, signed=True):
    fmt = {1: 'b', 2: 'h', 4: 'i'}[size]
    if not signed:
        fmt = fmt.upper()
    n = len(buf) // size
    return struct.unpack('<%d%s' % (n, fmt), buf[:n * size])


def monotonic(snaps, size=2, direction=+1, min_step=1, region=(0x10000, 0x200000)):
    """Addresses whose value moves strictly in `direction` across every snapshot."""
    ws = [words(s, size) for s in snaps]
    lo, hi = region[0] // size, region[1] // size
    hits = []
    for i in range(lo, hi):
        ok = True
        for a, b in zip(ws, ws[1:]):
            d = (b[i] - a[i]) * direction
            if d < min_step:
                ok = False
                break
        if ok:
            hits.append((BASE + i * size, [w[i] for w in ws]))
    return hits


def unchanged(snaps, cands, size=2):
    ws = [words(s, size) for s in snaps]
    return [c for c in cands if len({w[(c - BASE) // size] for w in ws}) == 1]
