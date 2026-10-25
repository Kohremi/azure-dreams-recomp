"""Helpers for driving an already-running dev build from one-off scripts."""
import sys, time
from psx import Game, mask, BTN

g = Game()

def seq(*steps):
    """steps: ('tap', 'start'), ('wait', 60), ('shot', 'name'), ('hold', 'up', 30)"""
    for st in steps:
        op = st[0]
        if op == 'tap':
            g.tap(*st[1:])
        elif op == 'wait':
            g.wait_frames(st[1])
        elif op == 'shot':
            print(g.shot(st[1]))
        elif op == 'hold':
            g.hold(st[1]); g.wait_frames(st[2]); g.release()


def pos():
    b = g.read(0x80083780, 8)
    return int.from_bytes(b[2:4], 'little', signed=True), int.from_bytes(b[6:8], 'little', signed=True)


def walk_axis(axis, target, tol=6, max_steps=40):
    """Walk along x (axis=0) or z (axis=1) toward target; returns final position."""
    for _ in range(max_steps):
        p = pos()
        d = target - p[axis]
        if abs(d) <= tol:
            return p
        btn = ('right' if d > 0 else 'left') if axis == 0 else ('down' if d > 0 else 'up')
        g.hold(btn)
        g.wait_frames(max(2, min(20, abs(d) // 6)))
        g.release()
        q = pos()
        if q == p:
            return q  # blocked
    return pos()


def walk_to(x=None, z=None):
    if x is not None:
        walk_axis(0, x)
    if z is not None:
        walk_axis(1, z)
    return pos()


# ---- dungeon helpers -------------------------------------------------------
KOH = 0x800834B8


def unit_grid(u):
    mo = g.u32(u - 0x14)
    b = g.read(mo + 0x24, 2)
    return b[0], b[1]


def find_units(ram=None):
    """Scan RAM for live unit records (species 1..47, level 1..99, HP>0)."""
    import struct
    r = ram or g.ram()
    out = []
    for o in range(0x10000, 0x200000 - 0x80, 4):
        sp, lv, hp = r[o + 0x13], r[o + 0x11], r[o + 0x28]
        if not (1 <= sp <= 47 and 1 <= lv <= 99 and hp and r[o + 0x29] >= hp):
            continue
        mo = struct.unpack_from('<I', r, o - 0x14)[0]
        if not (0x80010000 <= mo < 0x80200000):
            continue
        mo_o = mo - 0x80000000
        if r[o + 0x34] not in (0x81, 0x82):   # name present
            continue
        out.append(dict(addr=0x80000000 + o, sp=sp, lv=lv, hp=hp, x=r[mo_o + 0x24], y=r[mo_o + 0x25]))
    return out


DIRS = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}


def step_toward(tx, ty, stuck=[0]):
    import random
    x, y = unit_grid(KOH)
    dx, dy = tx - x, ty - y
    prefs = []
    if abs(dx) >= abs(dy):
        prefs = [('right' if dx > 0 else 'left'), ('down' if dy > 0 else 'up')]
    else:
        prefs = [('down' if dy > 0 else 'up'), ('right' if dx > 0 else 'left')]
    if stuck[0] > 1:
        prefs = random.sample(list(DIRS), 4)
    for d in prefs:
        g.tap(d, frames=4, gap=12)
        if unit_grid(KOH) != (x, y):
            stuck[0] = 0
            return d
    stuck[0] += 1
    return None


def chase(unit_addr, max_steps=120):
    """Walk Koh next to a unit; returns True when adjacent."""
    for _ in range(max_steps):
        tx, ty = unit_grid(unit_addr)
        x, y = unit_grid(KOH)
        if abs(tx - x) + abs(ty - y) <= 1:
            return True
        step_toward(tx, ty)
    return False


def face_and_attack(unit_addr, hits=1):
    tx, ty = unit_grid(unit_addr)
    x, y = unit_grid(KOH)
    d = {(1, 0): 'right', (-1, 0): 'left', (0, 1): 'down', (0, -1): 'up'}.get((tx - x, ty - y))
    if not d:
        return False
    for _ in range(hits):
        g.hold(d); g.wait_frames(2); g.tap('cross', frames=3, gap=4); g.release(); g.wait_frames(20)
    return True


def tile_map():
    import struct
    base = g.u32(0x8008333C)
    w = 1 << (g.u32(0x80083350) & 31)
    raw = g.read(base, w * 64 * 6)
    m = {}
    for y in range(64):
        for x in range(64):
            n, h = struct.unpack_from('<hh', raw, (x + y * w) * 6)
            if n:
                m[(x, y)] = h
    return m


def path_to(goal, m=None, max_dh=0x20, avoid=()):
    """BFS over tiles; returns list of directions from Koh to a tile adjacent to goal."""
    from collections import deque
    m = m or tile_map()
    start = unit_grid(KOH)
    goals = {(goal[0] + dx, goal[1] + dy) for dx, dy in DIRS.values()}
    prev = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        if c in goals:
            out = []
            while prev[c]:
                p, d = prev[c]
                out.append(d)
                c = p
            return out[::-1]
        for d, (dx, dy) in DIRS.items():
            n = (c[0] + dx, c[1] + dy)
            if n in prev or n not in m or n in avoid or n == tuple(goal):
                continue
            if abs(m[n] - m[c]) > max_dh:
                continue
            prev[n] = (c, d)
            q.append(n)
    return None


def go_next_to(unit_addr, max_legs=60, blocked=None):
    """Walk next to a unit. Tiles that refuse a step are avoided for a few re-plans
    (props like hedges are not in the height map; familiars wander into the way)."""
    blocked = {} if blocked is None else blocked     # tile -> remaining re-plans
    m = tile_map()
    for _ in range(max_legs):
        tx, ty = unit_grid(unit_addr)
        x, y = unit_grid(KOH)
        if abs(tx - x) + abs(ty - y) == 1:
            return True
        for t in list(blocked):
            blocked[t] -= 1
            if blocked[t] <= 0:
                del blocked[t]
        p = path_to((tx, ty), m=m, avoid=set(blocked))
        if not p:
            blocked.clear()
            g.tap('cross', frames=3, gap=14)
            continue
        for d in p[:8]:             # re-plan often; monsters move
            before = unit_grid(KOH)
            g.tap(d, frames=4, gap=12)
            if unit_grid(KOH) == before:
                g.tap('cross', frames=3, gap=14)   # dismiss a message box if one is up
                g.tap(d, frames=4, gap=12)
                if unit_grid(KOH) == before:
                    dx, dy = DIRS[d]
                    blocked[(before[0] + dx, before[1] + dy)] = 8
                break
    return False


def order_familiar_spell(dirs=('left', 'down'), menu_steps_from_top=None):
    """Square -> Command -> Direct:<spell> toward dirs (one or two d-pad buttons)."""
    g.tap('square', frames=4, gap=30)
    for _ in range(8):                    # cursor memory varies: go to the top first
        g.tap('up', frames=3, gap=6)
    for _ in range(4):                    # Items, Select, Line up, Fuse -> Command
        g.tap('down', frames=3, gap=8)
    g.tap('cross', frames=4, gap=30)      # Command -> familiar submenu
    g.tap('down', frames=3, gap=8)        # Move -> Direct
    g.tap('down', frames=3, gap=8)        # Direct -> Direct:<spell>
    g.tap('cross', frames=4, gap=30)
    g.hold(*dirs); g.wait_frames(6); g.release(); g.wait_frames(6)
    g.tap('cross', frames=4, gap=10)


def brid_test(sleep_target=True, hp=200):
    """From save slot 3: turn the Pulunpa into a frog (status 0x0A, so it cannot act; also halves its DEF),
    order Kewne Direct:Brid down-left, pass a turn.
    Returns (hp_lost, kewne_mp_spent, traced damage writes)."""
    g.load_state(3); g.wait_frames(20)
    pul = 0x801EC920; kew = g.u32(KOH + 0xAC)
    if sleep_target:
        g.write(pul + 0x2C, bytes([10, 60]))
    g.write(pul + 0x05, bytes([hp])); g.write(pul + 0x28, bytes([hp])); g.write(pul + 0x29, bytes([hp]))
    mp0 = g.read(kew + 0x25, 1)[0]
    g.tap('square', frames=4, gap=30)
    for _ in range(6): g.tap('up', frames=3, gap=8)
    for _ in range(4): g.tap('down', frames=3, gap=8)
    g.tap('cross', frames=4, gap=30)
    g.tap('down', frames=3, gap=8); g.tap('down', frames=3, gap=8)
    g.tap('cross', frames=4, gap=30)
    g.cmd('wtrace_clear'); g.cmd('wtrace_range', lo=hex(pul + 0x64), hi=hex(pul + 0x66))
    g.hold('left', 'down'); g.wait_frames(6); g.release(); g.wait_frames(6)
    g.tap('cross', frames=4, gap=10)
    g.tap('right', frames=4, gap=10)
    g.wait_frames(200)
    writes = [(e['new'], e['pc']) for e in g.cmd('wtrace_dump', count=20, newest=1)['entries']]
    return hp - g.read(pul + 0x28, 1)[0], mp0 - g.read(kew + 0x25, 1)[0], writes


def stairs():
    """Stairs on the current floor: list of (x, y) from 0x800E3CD8 (4 x {type, x, y, height})."""
    import struct
    out = []
    for k in range(4):
        t, x, y, h = struct.unpack('<4H', g.read(0x800E3CD8 + 8 * k, 8))
        if t:
            out.append((x, y))
    return out


def path_to_tile(goal, m=None, max_dh=0x20, avoid=()):
    from collections import deque
    m = m or tile_map()
    start = unit_grid(KOH)
    prev = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        if c == tuple(goal):
            out = []
            while prev[c]:
                p, d = prev[c]
                out.append(d)
                c = p
            return out[::-1]
        for d, (dx, dy) in DIRS.items():
            n = (c[0] + dx, c[1] + dy)
            if n in prev or n in avoid:
                continue
            if n not in m and n != tuple(goal):
                continue
            if n in m and abs(m[n] - m[c]) > max_dh and n != tuple(goal):
                continue
            prev[n] = (c, d)
            q.append(n)
    return None


def go_to_tile(goal, max_legs=80):
    blocked = {}
    m = tile_map()
    for _ in range(max_legs):
        if unit_grid(KOH) == tuple(goal):
            return True
        for t in list(blocked):
            blocked[t] -= 1
            if blocked[t] <= 0:
                del blocked[t]
        p = path_to_tile(goal, m=m, avoid=set(blocked))
        if not p:
            blocked.clear(); g.tap('cross', frames=3, gap=14); continue
        for d in p[:8]:
            before = unit_grid(KOH)
            g.tap(d, frames=4, gap=12)
            if unit_grid(KOH) == before:
                g.tap('cross', frames=3, gap=14)
                g.tap(d, frames=4, gap=12)
                if unit_grid(KOH) == before:
                    dx, dy = DIRS[d]
                    blocked[(before[0] + dx, before[1] + dy)] = 8
                break
    return unit_grid(KOH) == tuple(goal)


def floor_number():
    return g.u16(0x8008146C)


def take_elevator():
    """Stand on the elevator, answer Yes to 'Wanna go up?' and No to 'QUIT?'."""
    f0 = floor_number()
    g.tap('cross', frames=4, gap=40)          # "An elevator. Wanna go up?"
    g.tap('cross', frames=4, gap=60)          # Yes
    g.wait_frames(150)                        # ride
    g.tap('down', frames=3, gap=10)           # "QUIT?" -> No
    g.tap('cross', frames=4, gap=30)
    for _ in range(40):
        g.wait_frames(30)
        if floor_number() != f0 and g.read(0x80083780, 1) is not None:
            break
    g.wait_frames(90)
    return floor_number()


def live_units():
    """Units in the game's circular unit list (head at 0x800814A8): (addr, species, level, hp, x, y)."""
    head = g.u32(0x800814A8)
    u = head
    out = []
    for _ in range(64):
        b = g.read(u, 0x30)
        x, y = unit_grid(u)
        out.append((u, b[0x13], b[0x11], b[0x28], x, y))
        u = g.u32(u + 0x5C) + 0x20
        if u == head:
            break
    return out
