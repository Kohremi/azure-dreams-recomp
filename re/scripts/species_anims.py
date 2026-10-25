r"""Which animation group each monster uses for each action state, read from its code chunk.

Species code chunks (slot 0 copy, linked at 0x80170800) sit at DUNGEON.BIN + (0x132A + (s-1)*0x54)*0x800.
Each has a state-indexed handler table (the update function calls handler[unit+0x9A]); a handler
starts an animation by loading an 8-byte direction table [g*5+2, g*5+1, g*5, g*5+1, g*5+2, g*5+3,
g*5+4, g*5+3] (lui/addiu pair) before calling the sprite functions. The default (idle) table is the
one stored into sprite+0x2C by the constructor (header word 0).

States observed live (timeline.py on save state 3): 0x0E waiting/idle, 0x11 melee attack,
0x12 spell, 0x07 hit reaction, 0x0F a step, 0x10 a step up (the hop, hop_groups below).

    python species_anims.py [species ...]
"""
import struct, sys, json
from sprite_banks import disc, monster_bank, SPECIES

BASE = 0x80170800
SIZE = 0x6000


def chunk(s):
    off = (0x132A + (s - 1) * 0x54) * 0x800
    return disc()[off:off + SIZE]


def u32(c, a):
    return struct.unpack_from('<I', c, a - BASE)[0]


def is_dir_table(c, a, nseq):
    o = a - BASE
    if o < 0 or o + 8 > len(c):
        return None
    t = c[o:o + 8]
    g0 = t[2]
    if g0 % 5 or g0 >= nseq:
        return None
    if list(t) == [g0 + 2, g0 + 1, g0, g0 + 1, g0 + 2, g0 + 3, g0 + 4, g0 + 3]:
        return g0 // 5
    if len(set(t)) == 1 and t[0] < nseq:       # one sequence for every direction
        return ('single', t[0])
    return None


def code_ptr(v):
    return BASE <= v < BASE + SIZE and v % 4 == 0


def find_handler_table(c):
    """Longest run of words that are 0, chunk code pointers or dungeon-module pointers."""
    best = (0, None)
    i = 0x40
    n = len(c) // 4
    while i < n:
        j = i
        good = 0
        while j < n:
            v = struct.unpack_from('<I', c, j * 4)[0]
            if v == 0 or code_ptr(v) or 0x80088760 <= v < 0x80100000:
                good += 1 if v else 0
                j += 1
            else:
                break
        if good >= 8 and j - i > best[0] and i * 4 >= 0x100 and code_ptr(struct.unpack_from('<I', c, i * 4)[0]):
            best = (j - i, BASE + i * 4)
        i = j + 1
    return best[1]


def func_refs(c, start, nseq, limit=0x600):
    """Direction tables referenced by lui/addiu pairs in the function at `start` (until jr ra)."""
    regs = {}
    found = []
    a = start
    end = min(BASE + SIZE, start + limit)
    while a < end:
        w = u32(c, a)
        op = w >> 26
        rs, rt, imm = (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 0x0F:                       # lui
            regs[rt] = imm << 16
        elif op == 0x09 and rs in regs:      # addiu
            v = (regs[rs] + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF
            g = is_dir_table(c, v, nseq)
            if g is not None:
                found.append((v, g))
        if w == 0x03E00008:                  # jr ra
            break
        a += 4
    return found


def analyse(s):
    c = chunk(s)
    nseq = monster_bank(s).seq_count
    ht = find_handler_table(c)
    states = {}
    if ht:
        k = 0
        while True:
            v = u32(c, ht + k * 4)
            if not (v == 0 or code_ptr(v) or 0x80088760 <= v < 0x80100000) or k > 64:
                break
            if code_ptr(v):
                refs = func_refs(c, v, nseq)
                if refs:
                    states[k] = [g for _, g in refs]
            k += 1
    ctor = u32(c, BASE)
    idle = [g for _, g in func_refs(c, ctor, nseq, 0x400)]
    return dict(species=s, name=SPECIES[s], handler_table=hex(ht) if ht else None, idle=idle, states=states)


if __name__ == '__main__':
    only = [int(a) for a in sys.argv[1:]] or range(1, 47)
    for s in only:
        r = analyse(s)
        print('%2d %-10s ht %s idle %s' % (s, r['name'], r['handler_table'], r['idle']))
        for st, gs in sorted(r['states'].items()):
            print('      state %02x: %s' % (st, gs))


def _refs_all(c, n):
    """Every lui/addiu pair in the chunk that points at a direction table: (insn addr, table, group)."""
    regs, out = {}, []
    for a in range(BASE, BASE + len(c) - 4, 4):
        w = u32(c, a)
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 0x0F:
            regs[rt] = imm << 16
        elif op == 0x09 and rs in regs:
            v = (regs[rs] + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF
            g = is_dir_table(c, v, n)
            if g is not None:
                out.append((a, v, g))
        if w == 0x03E00008:
            regs = {}
    return out


def _func_start(c, a):
    while a > BASE + 8:
        if u32(c, a - 8) == 0x03E00008:
            return a
        a -= 4
    return BASE


def hop_groups(s):
    """A walker's step animations: {walk, approach, jump, land} groups, or None for species without a
    hop. The step function (Pulunpa FUN_80171BB0: the walk table 0x801762C8 = g1, state 0x0F) calls the
    hop entry (FUN_80171DF4: state 0x10 sub 0, the approach table 0x801762D0 = g2) on a step up; the
    state 0x10 handler (FUN_801721B0) plays the jump (0x801762D8 = g3) and, on landing, 0x801762E0
    (g4). The approach table sits 8 bytes before the jump table in every chunk that has one."""
    import species_roles
    try:
        roles, _funcs = species_roles.roles(s)
    except Exception:
        return None
    h10 = roles.get('state_10')
    c = chunk(s)
    n = monster_bank(s).seq_count
    hr = func_refs(c, h10, n) if h10 else []
    if not hr or not isinstance(hr[0][1], int):
        return None
    jump_t = hr[0][0]
    allr = _refs_all(c, n)
    appr = [x for x in allr if x[1] == jump_t - 8 and isinstance(x[2], int)]
    out = dict(jump=hr[0][1])
    if len(hr) > 1 and isinstance(hr[1][1], int):
        out['land'] = hr[1][1]
    if appr:
        out['approach'] = appr[0][2]
        entry = _func_start(c, appr[0][0])
        for a in range(BASE, BASE + len(c) - 4, 4):
            w = u32(c, a)
            if w >> 26 == 3 and (((a + 4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2)) == entry:
                st = _func_start(c, a)
                walk = [g for at, v, g in allr if st <= at < a and v != jump_t - 8 and isinstance(g, int)]
                if walk:
                    out['walk'] = walk[0]
                    break
    return out


def labels(s):
    """Action -> animation group(s), from the handler scan plus a few rules:
    hurt prefers a group in the first half (the second half of some banks is an alternate set) and is
    the idle group when the hit handler only uses that (Noise, Kraken: a flash and the knock-back);
    death (state 0x08) defaults to hurt (Pulunpa's is its hurt group, re/timelines/kill.txt);
    walk falls back to idle for floating species; sleep = (fall asleep, sleeping loop): the looping
    group goes second."""
    r = analyse(s)
    bank = monster_bank(s)
    ngroups = bank.seq_count // 5
    ints = lambda lst: [g for g in lst if isinstance(g, int)]
    st = r['states']
    idle_list = ints(r['idle'])
    idle = idle_list[0] if idle_list else 0
    walk = ints(st.get(0x10, [])) or [idle]
    attack = (ints(st.get(0x11, [])) or [idle])[0]
    spell = next((g for g in ints(st.get(0x12, [])) if g != idle), attack)
    hurt_c = [g for g in ints(st.get(0x07, [])) if g != idle]
    hurt = next((g for g in hurt_c if g < ngroups / 2), hurt_c[0] if hurt_c else idle)
    death = next((g for g in ints(st.get(0x08, [])) if g != idle), hurt)
    sleep = ints(st.get(0x05, []))[:2] or [idle]
    if len(sleep) == 1:
        sleep = sleep * 2
    return dict(idle=idle, walk=walk, attack=attack, spell=spell, hurt=hurt, death=death,
                sleep=sleep_order(bank, sleep), groups=ngroups)


def sleep_order(bank, sleep):
    """(fall asleep, sleeping loop): swap when only the first group's sequence loops."""
    loops = lambda g: bank.sequence(min(bank.seq_count - 1, g * 5 + 2))[1] >= 0
    if len(sleep) == 2 and loops(sleep[0]) and not loops(sleep[1]):
        return [sleep[1], sleep[0]]
    return list(sleep)
