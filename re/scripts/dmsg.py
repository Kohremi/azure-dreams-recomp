"""Decode dungeon message strings ('Q' + one byte per character through the two-byte table at
*0x800DCF60, FUN_80099194) from the running dev build:  python dmsg.py ADDR [ADDR ...]"""
import sys
from psx import Game
import os
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

g = Game()
TABLE = g.u32(0x800DCF60)


def decode(a):
    out = ''
    q = False
    for _ in range(200):
        b = g.read(a, 1)[0]
        a += 1
        if b == 0:
            if q:
                q = False
                continue
            break
        if b == 0x51 and not q:
            q = True
            continue
        if q:
            pair = g.read(TABLE + (b - 1) * 2, 2)
            try:
                out += pair.decode('shift_jis')
            except UnicodeDecodeError:
                out += '<%s>' % pair.hex()
        elif b >= 0x80:
            pair = bytes([b]) + g.read(a, 1)
            a += 1
            out += pair.decode('shift_jis', 'replace')
        else:
            out += chr(b)
    return out


if __name__ == '__main__':
    for x in sys.argv[1:]:
        print(x, decode(int(x, 16)))


def decode_chunk(species, addr):
    """A string inside a species chunk (as linked at slot 0, 0x80170800)."""
    data = open(os.path.join(REPO_ROOT, r're\modules\species%02d_slot0_80170800.bin') % species, 'rb').read()
    o = addr - 0x80170800
    out = ''
    q = False
    while o < len(data):
        b = data[o]
        o += 1
        if b == 0:
            if q:
                q = False
                continue
            break
        if b == 0x51 and not q:
            q = True
            continue
        if q:
            pair = g.read(TABLE + (b - 1) * 2, 2)
            out += pair.decode('shift_jis', 'replace')
        elif b >= 0x80:
            out += bytes([b, data[o]]).decode('shift_jis', 'replace')
            o += 1
        else:
            out += chr(b)
    return out
