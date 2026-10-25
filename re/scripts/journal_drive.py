"""Drive the Story Journal (or any town script) from the harness.

VM context 0x80082AC4: +0x10 state fn, +0x1C script pointer. States: 0x80038478 waiting for a
button, 0x80038588 choice menu open, 0x80038A10 running/typing.
"""
from psx import Game

CTX_STATE, CTX_PTR = 0x80082AD4, 0x80082AE0
WAITBTN, CHOICE, RUNNING = 0x80038478, 0x80038588, 0x80038A10


def state(g):
    return g.u32(CTX_STATE)


def to_choice(g, max_steps=80):
    """Press X through text boxes until a choice menu is open."""
    for _ in range(max_steps):
        s = state(g)
        if s == CHOICE:
            g.wait_frames(6)
            return True
        if s == WAITBTN:
            g.tap('cross')
        g.wait_frames(10)
    return False


CTX_CURSOR = 0x8008235D    # live highlighted option of the open menu


def choose(g, n):
    assert to_choice(g), "no choice menu"
    for _ in range(30):
        if g.u8(CTX_CURSOR) != 0xFF:
            break
        g.wait_frames(4)
    for _ in range(12):
        if g.u8(CTX_CURSOR) == n:
            break
        g.tap('down', frames=3, gap=8)
        g.wait_frames(4)
    assert g.u8(CTX_CURSOR) == n, "cursor at %d, wanted %d" % (g.u8(CTX_CURSOR), n)
    g.tap('cross')
    g.wait_frames(20)


def flag(g, f):
    return bool(g.u32(0x80012D70 + 4 * (f >> 5)) & (1 << (f & 31)))


def open_journal(g):
    g.tap('select')
    g.wait_frames(60)
