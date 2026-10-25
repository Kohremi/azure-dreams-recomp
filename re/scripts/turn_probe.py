"""Turn-system fields of every unit in the game's unit list (dungeon), for checking the decompiled
turn loop against the running dev build:

    python turn_probe.py [state]      load save state (default: don't) and dump the list

Per unit: species +0x13, mode +0x12, flags +0x14 / +0x1C, talents +0x54, action counter +0x6C
(8.8; +0x6D = whole actions), speed +0x6E, MP +0x24 (8.8) / max +0x66, status slots +0x2C..+0x33,
formation slot +0x45, plan +0x46, step count +0x71, tile and room (map object +0x24/+0x25/+0x26).
Globals: Koh's turn time 0x80083460, turn counter 0x8008347E, phase flags 0x80083462."""
import sys, struct
from attach import g, KOH


def s16(b, o):
    return struct.unpack_from('<h', b, o)[0]


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def unit_row(u):
    b = g.read(u, 0x130)
    mo = u32(b, -0x14 + 0x14) if False else g.u32(u - 0x14)
    m = g.read(mo, 0x30)
    st = ' '.join('%02x:%d' % (b[0x2C + 2 * i], struct.unpack('b', bytes([b[0x2D + 2 * i]]))[0])
                  for i in range(4) if b[0x2C + 2 * i])
    return ('%08x sp%2d lv%2d hp%3d/%3d mode %d f14 %08x f1c %08x tal %08x ap %04x spd %04x mp %04x/%d '
            'st[%s] slot %d plan %04x n71 %02x dir %04x h %d pos %2d,%2d room %d acc %d' % (
                u, b[0x13], b[0x11], b[0x28], b[0x29], b[0x12], u32(b, 0x14), u32(b, 0x1C), u32(b, 0x54),
                u16(b, 0x6C), u16(b, 0x6E), u16(b, 0x24), b[0x66], st, b[0x45], u16(b, 0x46), b[0x71],
                u16(b, 0x2A), s16(b, 0x88), m[0x24], m[0x25], struct.unpack('b', bytes([m[0x26]]))[0], b[0x03]))


def dump():
    head = g.u32(0x800814A8)
    print('turn time %04x  turn %d  flags %04x  koh+03 %d  koh+f8 %d  koh+128 %04x  koh+118 %d' % (
        g.u16(0x80083460), g.u16(0x8008347E), g.u16(0x80083462), g.read(KOH + 3, 1)[0],
        g.u16(KOH + 0xF8), g.u32(KOH + 0x128), g.u16(KOH + 0x118)))
    u = head
    for _ in range(64):
        print(unit_row(u))
        u = g.u32(u + 0x5C) + 0x20
        if u == head:
            break


if __name__ == '__main__':
    if len(sys.argv) > 1:
        g.tap('triangle', frames=3, gap=10)
        g.load_state(int(sys.argv[1]))
        g.wait_frames(3)
    dump()
