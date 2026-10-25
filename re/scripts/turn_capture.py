"""Turn scenarios from the running dev build, for checking the Godot port's turn loop
(azure-tower-godot/scripts/tests/turn_test.gd) against the game:

    python turn_capture.py STATE OUT.json [moves] [koh_hp]

moves: comma list; 'elevator' first rides up to a fresh floor, 'spawn:N' makes the game spawn a
monster on each of the first N turns, 'auto:N' plays N turns toward the nearest monster.
koh_hp: Koh starts with this HP, and between turns Koh and familiars get theirs back below half.

loads save state STATE, then for each move (a d-pad name, or 'cross' for a swing; default:
'right') records the floor, the rooms (with their exit lists), every unit and the random state
before Koh acts, performs the move, waits for the turn to finish, and records the units and the
random state after. OUT.json = {"floor": {...}, "turns": [{"before", "action", "after"}, ...]}.

Unit fields (re/NOTES.md "Full unit record layout", "Dungeon turn loop"): species +0x13, level
+0x11, HP +0x28/+0x29, MP +0x24 (8.8) / max +0x66, ATK/DEF +0x26/+0x27, accuracy +0x03, element
+0x14 & 7, flags +0x14 / +0x1C, talents +0x54, spells +0x08.., status slots +0x2C.., mode +0x12,
+0x43, formation slot +0x45, plan +0x46, action counter +0x6C, speed +0x6E, step count +0x71,
target exit +0x72/+0x73, facing +0x2A, +0x98 (control flags), +0x9C (room of its last step),
tile/room/last exit from the map object (+0x24/+0x25/+0x26/+0x27)."""
import sys, json, struct, time
from attach import g, KOH

RNG = 0x8008335C
FLAGS = 0x80083462


def s8(v):
    return v - 256 if v >= 128 else v


def floor_state():
    base = g.u32(0x8008333C)
    w = 1 << (g.u32(0x80083350) & 31)
    raw = g.read(base, w * 64 * 6)
    tiles = []
    for y in range(64):
        for x in range(64):
            t, h, a = struct.unpack_from('<hhH', raw, (x + y * w) * 6)
            if t:
                tiles.append([x, y, t, h, a])
    n = g.u16(0x8008146E)
    rooms = []
    rec = g.read(0x800E2970, 0x14 * n)
    for i in range(n):
        x, y, rw, rh, _4, active, flags, count = struct.unpack_from('<8H', rec, i * 0x14)
        ptr = struct.unpack_from('<I', rec, i * 0x14 + 0x10)[0]
        exits = []
        if ptr and count:
            e = g.read(ptr, 4 * count)
            exits = [[e[k * 4], e[k * 4 + 1], struct.unpack_from('<H', e, k * 4 + 2)[0]] for k in range(count)]
        rooms.append({'x': x, 'y': y, 'w': rw, 'h': rh, 'active': active, 'flags': flags, 'exits': exits})
    # Floor objects (FUN_80018464 / the generator): items 0x40 x {4 bytes at 0x800E3548, x/y at
    # 0x800E36C8 + i*12}; traps 0x20 x {4 bytes at 0x800E3648, x/y at 0x800E39C8 + i*0x18 + 6}.
    it = g.read(0x800E3548, 0x100)
    ip = g.read(0x800E36C8, 0x40 * 12)
    items = [[ip[i * 12], ip[i * 12 + 1]] + list(it[i * 4:i * 4 + 4]) for i in range(0x40) if it[i * 4 + 1]]
    tr = g.read(0x800E3648, 0x80)
    tp = g.read(0x800E39C8, 0x20 * 0x18)
    traps = [[tp[i * 0x18 + 6], tp[i * 0x18 + 7]] + list(tr[i * 4:i * 4 + 4]) for i in range(0x20) if tr[i * 4] or tr[i * 4 + 1]]
    ptr = g.u32(0x80083478)                    # the floor's spawn table: 16 x {species, level}
    t = g.read(ptr, 32)
    table = [[t[i * 2], t[i * 2 + 1]] for i in range(16)]
    return {'tiles': tiles, 'rooms': rooms, 'spawn_table': table, 'floor': g.u16(0x8008146C),
            'items': items, 'traps': traps}


def unit(u):
    b = g.read(u, 0x130)
    mo = g.u32(u - 0x14)
    m = g.read(mo, 0x30)
    st = [[b[0x2C + 2 * i], s8(b[0x2D + 2 * i])] for i in range(4) if b[0x2C + 2 * i]]
    return {
        'addr': '%08X' % u, 'species': b[0x13], 'level': b[0x11], 'hp': b[0x28], 'max_hp': b[0x29],
        'mp': struct.unpack_from('<H', b, 0x24)[0], 'max_mp': b[0x66], 'atk': b[0x26], 'def': b[0x27],
        'acc': b[0x03], 'f14': struct.unpack_from('<I', b, 0x14)[0], 'f1c': struct.unpack_from('<I', b, 0x1C)[0],
        'talents': struct.unpack_from('<I', b, 0x54)[0],
        'spells': [[b[8 + 3 * i], b[9 + 3 * i]] for i in range(3) if b[8 + 3 * i]],
        'status': st, 'mode': b[0x12], 'b43': b[0x43], 'slot': b[0x45],
        'plan': struct.unpack_from('<H', b, 0x46)[0], 'ap': struct.unpack_from('<H', b, 0x6C)[0],
        'speed': struct.unpack_from('<H', b, 0x6E)[0], 'n71': b[0x71], 'exit_target': [b[0x72], b[0x73]],
        'dir': struct.unpack_from('<h', b, 0x2A)[0], 'f98': struct.unpack_from('<H', b, 0x98)[0], 'w48': b[0x48],
        'prev_room': s8(b[0x9C]), 'h88': struct.unpack_from('<h', b, 0x88)[0],
        'x': m[0x24], 'y': m[0x25], 'room': s8(m[0x26]), 'last_exit': s8(m[0x27]),
        'raw': g.read(u - 0x20, 0x150).hex(), 'mraw': m.hex(),    # object (unit - 0x20) and map object
    }


def units():
    head = g.u32(0x800814A8)
    out = []
    u = head
    for _ in range(64):
        out.append(unit(u))
        u = g.u32(u + 0x5C) + 0x20
        if u == head:
            break
    return out


def globals_():
    return {'rng': g.u32(RNG), 'turn': g.u16(0x8008347E), 'flags': g.u16(FLAGS), 'floor': g.u16(0x8008146C),
            'turn_time': g.u16(0x80083460), 'koh_rand': g.u32(KOH + 0x128), 'koh_wave': g.u16(KOH + 0xF8),
            'regen': [g.u32(0x800E3D70), g.u32(0x800E3D74), g.u32(0x800E3D78)],
            'spawn_timer': struct.unpack('<h', g.read(0x80083466, 2))[0], 'floor_flags': g.u32(0x800E296C),
            'koh_acc': g.u8(KOH + 3), 'koh_weapon': g.u32(KOH + 0x4C), 'koh_shield': g.u32(KOH + 0x50),
            'familiars': ['%08X' % g.u32(KOH + 0xAC), '%08X' % g.u32(KOH + 0xB0)]}


def idle():
    """The turn is over: no phase flags but 'turn taken' cleared, nobody walking or acting."""
    f = g.u16(FLAGS)
    return (f & 0x3E0A) == 0 and g.u32(0x80083468) == 0 and g.u32(0x8008346C) == 0 and g.u32(0x80083470) == 0


def _signature():
    """Everything that moves while a turn plays: phase flags, counters, the random state, every
    unit's action state and sprite sequence. Unchanged for long = the game waits for a button."""
    sig = [g.u16(FLAGS), g.u32(0x80083468), g.u32(0x8008346C), g.u32(0x80083470), g.u32(RNG)]
    head = g.u32(0x800814A8)
    u = head
    for _ in range(40):
        sig.append(g.u16(u + 0x9A))
        sig.append(g.u32(g.u32(u - 0x14) + 0x2C))
        u = g.u32(u + 0x5C) + 0x20
        if u == head:
            break
    return sig


def wait_idle(timeout=1500):
    """Waits for the turn to end. A turn stuck on a message (a familiar fainting, a level-up) --
    nothing changing for 150 frames -- gets a Cross tap to move it along."""
    f0 = g.frame()
    last, since = None, f0
    while g.frame() - f0 < timeout:
        if idle() and g.frame() - f0 > 4:
            g.wait_frames(2)
            if idle():
                return True
        sig = _signature()
        if sig != last:
            last, since = sig, g.frame()
        elif g.frame() - since > 150:
            g.tap('cross', frames=3, gap=4)
            since = g.frame()
        time.sleep(0.01)
    return False


TRACE_FIELDS = ((0x28, 1, 'hp'), (0x2A, 2, 'dir'), (0x46, 2, 'plan'), (0x6C, 2, 'ap'), (0x24, 2, 'mp'),
                (0x64, 2, 'pend'))


def arm_trace():
    """Write trace for the next turn: the random state (one write per draw, with the drawing code's
    return address) and one range per unit (+0x24..+0x6F: MP, HP, facing, plan, pending damage,
    action counter); the server takes 64 ranges."""
    ranges = [(RNG, RNG + 4, 'rng', 0)]
    for i, u in enumerate(units()[:63]):
        a = int(u['addr'], 16)
        ranges.append((a + 0x24, a + 0x70, str(i), a))
    g.cmd('wtrace_disarm_all')
    g.cmd('wtrace_clear')
    for lo, hi, _, _ in ranges:
        g.cmd('wtrace_arm', lo=hex(lo), hi=hex(hi))
    return ranges


FIELD = {0x24: 'mp', 0x25: 'mp', 0x28: 'hp', 0x2A: 'dir', 0x46: 'plan', 0x64: 'pend', 0x6C: 'ap', 0x6D: 'ap'}


def read_trace(ranges, f0):
    d = g.cmd('wtrace_dump', count=2000)
    g.cmd('wtrace_disarm_all')
    out = []
    for e in sorted(d.get('entries', []), key=lambda e: e.get('seq', 0)):
        addr = int(str(e.get('addr', '0')), 16) | 0x80000000
        hit = next(((n, base) for lo, hi, n, base in ranges if lo <= addr < hi), None)
        if hit is None:
            continue
        name, base = hit
        if name != 'rng':
            fld = FIELD.get(addr - base)
            if fld is None:
                continue
            name = '%s.%s' % (name, fld)
            if e.get('old') == e.get('new'):
                continue
        out.append([e.get('frame', 0) - f0, name, e.get('old'), e.get('new'), e.get('ra')])
    return out


def traps_now():
    tr = g.read(0x800E3648, 0x80)
    tp = g.read(0x800E39C8, 0x20 * 0x18)
    return [[tp[i * 0x18 + 6], tp[i * 0x18 + 7]] + list(tr[i * 4:i * 4 + 4]) for i in range(0x20) if tr[i * 4] or tr[i * 4 + 1]]


def snapshot():
    return {'globals': globals_(), 'units': units(), 'traps': traps_now()}


def act(move, tries=4):
    """One turn of Koh's: a short d-pad tap may only turn him, so tap until the turn counter moves.
    Returns when the tap that took the turn was made (the caller waits for the turn to end)."""
    t0 = g.u16(0x8008347E)
    for _ in range(tries):
        if move == 'cross':
            g.tap('cross', frames=5, gap=4)
        else:
            g.tap(move, frames=4, gap=4)
        f0 = g.frame()
        while g.frame() - f0 < 40:
            if g.u16(0x8008347E) != t0 or (g.u16(FLAGS) & 0x3E1A):
                return True
            time.sleep(0.01)
        if g.u16(0x8008347E) != t0:
            return True
    return False


def pokes(moves):
    """Leading 'status:WHO:ID:VALUE' tokens (WHO = koh or a unit-list index): writes the status into
    the unit's first free slot (+0x2C) and sets the +0x1C flag the AI tests. Returns the rest."""
    while moves and (moves[0].startswith('status:') or moves[0].startswith('poke:')):
        if moves[0].startswith('poke:'):
            # poke:WHO:OFFSET:HEXBYTES (little-endian bytes written at unit + offset)
            _, who, off, hx = moves[0].split(':')
            us = units()
            a = KOH if who == 'koh' else int(us[int(who)]['addr'], 16)
            g.write(a + int(off, 16), bytes.fromhex(hx))
            print('poke', who, off, hx)
            moves = moves[1:]
            continue
        _, who, sid, val = moves[0].split(':')
        us = units()
        a = KOH if who == 'koh' else int(us[int(who)]['addr'], 16)
        b = g.read(a + 0x2C, 8)
        k = next(i for i in range(4) if b[2 * i] == 0)
        g.write(a + 0x2C + 2 * k, bytes([int(sid), int(val) & 0xFF]))
        bit = {1: 0x200, 2: 0x400, 3: 0x10, 4: 0x20, 5: 0x40, 6: 0x80}.get(int(sid), 0)
        if bit:
            f = g.u32(a + 0x1C) | bit
            g.write(a + 0x1C, f.to_bytes(4, 'little'))
        print('status', who, sid, val)
        moves = moves[1:]
    return moves


PAD = {(0, -1): 'up', (0, 1): 'down', (-1, 0): 'left', (1, 0): 'right'}   # default camera


def auto_move():
    """The next move toward a fight: face and swing at an awake monster next to Koh (straight
    across), else step toward the nearest one (breadth-first over the tile map, 4 ways)."""
    from collections import deque
    from attach import tile_map
    us = units()
    k = us[0]
    kx, ky = k['x'], k['y']
    mons = [(u['x'], u['y']) for u in us[1:] if not (int(u['f14']) & 0x4000) and u['hp'] > 0]
    occ = {(u['x'], u['y']) for u in us[1:]}
    kdir = (k['dir'] >> 9) & 7
    dirvec = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    for (dx, dy), pad in PAD.items():
        if (kx + dx, ky + dy) in mons:
            if dirvec[kdir] == (dx, dy):
                return 'cross'
            g.tap(pad, frames=2, gap=6)       # turn to it (no turn taken), then swing
            return 'cross'
    m = tile_map()
    goals = set(mons)
    prev = {(kx, ky): None}
    q = deque([(kx, ky)])
    while q:
        c = q.popleft()
        if any((c[0] + dx, c[1] + dy) in goals for dx, dy in PAD):
            while prev[c] and prev[c] != (kx, ky):
                c = prev[c]
            return PAD.get((c[0] - kx, c[1] - ky), 'up') if c != (kx, ky) else 'up'
        for dx, dy in PAD:
            n = (c[0] + dx, c[1] + dy)
            if n in prev or n not in m or n in occ or abs(m[n] - m[c]) > 0x20:
                continue
            prev[n] = c
            q.append(n)
    return ['up', 'left', 'down', 'right'][g.u16(0x8008347E) & 3]


def top_up(hp):
    """Between turns: Koh and familiars below half their HP get it back (Koh to `hp`), so long runs
    last. Each turn's replay starts from its own 'before' snapshot, so this changes nothing compared."""
    for u in units():
        a = int(u['addr'], 16)
        if u['species'] == 0 and u['hp'] < hp // 2:
            g.write(a + 0x28, bytes([hp]))
        elif u['species'] and (u['f14'] & 0x4000) and 0 < u['hp'] < u['max_hp'] // 2:
            g.write(a + 0x28, bytes([u['max_hp']]))


def main():
    state = int(sys.argv[1])
    out = sys.argv[2]
    moves = sys.argv[3].split(',') if len(sys.argv) > 3 else ['right']
    koh_hp = int(sys.argv[4]) if len(sys.argv) > 4 else 0     # optional: raise Koh's HP so he lasts
    g.turbo(True)
    g.tap("triangle", frames=3, gap=10)
    g.load_state(state)
    g.wait_frames(3)
    for i in range(3):
        g.tap('cross', frames=3, gap=8)    # clear any message window
    wait_idle()
    if moves and moves[0] == 'elevator':      # ride up first: a freshly generated floor
        from attach import take_elevator
        print('floor', take_elevator())
        moves = moves[1:]
        for i in range(3):
            g.tap('cross', frames=3, gap=8)
        wait_idle()
    spawn_turns = 0
    if moves and moves[0].startswith('spawn:'):
        # spawn:N: the spawn timer (0x80083466) is set to 0 before each of the first N turns, so the
        # game spawns a monster every turn (the 'before' snapshot holds the poked value).
        spawn_turns = int(moves[0].split(':')[1])
        moves = moves[1:]
    moves = pokes(moves)
    if koh_hp:
        g.write(KOH + 0x28, bytes([koh_hp]))
        g.write(KOH + 0x29, bytes([koh_hp]))
        g.write(KOH + 0x05, bytes([koh_hp]))
    doc = {'state': state, 'floor': floor_state(), 'turns': []}
    if moves and moves[0].startswith('auto:'):
        moves = ['auto'] * int(moves[0].split(':')[1]) + moves[1:]
    for n, mv in enumerate(moves):
        if koh_hp:
            top_up(koh_hp)
        if n < spawn_turns:
            g.write(0x80083466, bytes(2))
        if mv == 'auto':
            mv = auto_move()
        before = snapshot()
        ranges = arm_trace()
        f0 = g.frame()
        act(mv)
        ok = wait_idle()
        trace = read_trace(ranges, f0)
        after = snapshot()
        doc['turns'].append({'action': mv, 'before': before, 'after': after, 'settled': ok, 'trace': trace})
        k0 = before['units'][0]
        k1 = after['units'][0]
        print('%s: Koh %d,%d -> %d,%d  rng %08X -> %08X  turn %d -> %d%s' % (
            mv, k0['x'], k0['y'], k1['x'], k1['y'], before['globals']['rng'], after['globals']['rng'],
            before['globals']['turn'], after['globals']['turn'], '' if ok else '  (did not settle)'))
    json.dump(doc, open(out, 'w'), indent=1)
    print('wrote', out)


if __name__ == '__main__':
    main()
