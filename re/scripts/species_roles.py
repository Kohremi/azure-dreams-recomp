"""Which code each species chunk replaces: the chunks are copies of one template (Pulunpa's, chunk
21, is the one ported to Godot as the generic AI); this finds every chunk's functions by role and
says how far each one is from Pulunpa's.

    python species_roles.py [species ...]       report (default: all 46)
    python species_roles.py --dump N ROLE        print species N's decompiled function for ROLE
    python species_roles.py --diff N [ROLE ...]  diff species N's functions against Pulunpa's
    python species_roles.py --vs N M [ROLE ...]  ... against species M's

Roles: ctor (header word 0), update (ctor's object +0x10), control (ctor's +0xAC), alt_control
(+0xAC when +0xA7 is set), state_XX (the 24-entry state-handler table, entry 0xE is generic), and
what the control's switch calls: case_8, case_9, case_A, move (default). Similarity is difflib's
ratio on the decompiled C with chunk addresses and local names normalised (1.0 = same code)."""
import re, sys, struct, difflib
from species_anims import chunk
from sprite_banks import SPECIES
import os
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE, END = 0x80170800, 0x80176800
GHIDRA = os.path.join(REPO_ROOT, r're\ghidra\species%02d_decomp.c')


def load(s):
    src = open(GHIDRA % s, encoding='utf-8', errors='replace').read()
    funcs = {}
    for m in re.finditer(r'(?m)^// ==== ([0-9a-f]{8}) \S+\n', src):
        j = src.find('\n// ==== ', m.end())
        funcs[int(m.group(1), 16)] = src[m.end():j if j > 0 else len(src)]
    return funcs


def words(s):
    d = chunk(s)
    return struct.unpack_from('<%dI' % (len(d) // 4), d)


def state_table(w):
    """The state handlers: 24 entries, and U-Boat's (dive 0x18, surface 0x19) run on."""
    for i in range(len(w) - 24):
        if w[i + 0xE] == 0x800A9C10 and w[i + 0x14] == 0x800ACBE4:
            n = 24
            while i + n < len(w) and BASE <= w[i + n] < END:
                n += 1
            return list(w[i:i + n])
    return []


def func_at(funcs, addr):
    """The decompiled function starting at addr, or the one starting up to 8 bytes after it (entry
    points that load a global in their first two instructions decompile from +8)."""
    for a in (addr, addr + 8, addr + 4, addr + 0x10):
        if a in funcs:
            return a
    return None


def norm(body):
    b = re.sub(r'(FUN|LAB|DAT|PTR_LAB|switchD)_8017[0-9a-f]{4}(::\w+)?', 'CHUNK', body)
    b = re.sub(r'0x8017[0-9a-f]{4}', 'CADDR', b)
    b = re.sub(r'-0x7fe8[0-9a-f]{4}', 'CADDR', b)
    b = re.sub(r'\b(uVar|iVar|sVar|cVar|bVar|pcVar|puVar|piVar|psVar|pbVar|lVar|uStack|iStack|sStack|auStack|local)_?[0-9a-f_]+\b', 'V', b)
    b = re.sub(r'unaff_\w+', 'V', b)
    return b


def roles(s):
    funcs = load(s)
    w = words(s)
    out = {}
    ctor = w[0]
    out['ctor'] = func_at(funcs, ctor)
    body = funcs.get(out['ctor'], '')
    m = re.search(r'\+ 0x10\) = (?:\(code \*\))?(?:0x|FUN_|LAB_)?(8017[0-9a-f]{4})', body)
    if m:
        out['update'] = func_at(funcs, int(m.group(1), 16) | 0x80000000)
    acs = re.findall(r'\+ 0xac\) = (?:\(code \*\))?(?:&switchD_)?(?:0x|FUN_|LAB_)?(8017[0-9a-f]{4})(?:::caseD_\w+)?', body)
    if acs:
        out['control'] = func_at(funcs, int(acs[0], 16) | 0x80000000)
        alt = [a for a in acs if a != acs[0]]
        if alt:
            out['alt_control'] = func_at(funcs, int(alt[0], 16) | 0x80000000)
    st = state_table(w)
    for i, a in enumerate(st):
        if a and BASE <= a < END:
            out['state_%02X' % i] = func_at(funcs, a)
    cb = funcs.get(out.get('control'), '')
    k = cb.find('switch')
    if k >= 0:
        sw = cb[k:]
        for case, role in (('case 8:', 'case_8'), ('case 9:', 'case_9'), ('case 10:', 'case_A')):
            i = sw.find(case)
            if i >= 0:
                m = re.search(r'(FUN_8017[0-9a-f]{4})\(', sw[i:i + 300])
                if m:
                    out[role] = func_at(funcs, int(m.group(1)[4:], 16))
        m = re.search(r'default:\s*(?:goto (LAB_\w+)|(FUN_8017[0-9a-f]{4})\()', sw)
    # the move function: the one with the 8-way rotation loop
    for a, b in funcs.items():
        if 'DAT_8006cd00' in b and ('FUN_8009a66c' in b or 'func_0x8009a8c0' in b) and 'FUN_800a19e4' in b:
            out['move'] = a
            break
    return out, funcs


def calls(body):
    """External (dungeon module / EXE) functions a function calls."""
    found = re.findall(r'(?:FUN_|func_0x)(80[0-9a-f]{6})\(', body)
    return {a for a in found if int(a, 16) < 0x80150000}


def main():
    args = sys.argv[1:]
    if args[:1] in (['--diff'], ['--vs']):
        if args[0] == '--vs':
            # --vs N M [ROLE ...]: species N against species M
            base = int(args[2])
            args = ['--diff', args[1]] + args[3:]
        else:
            base = 21
        s = int(args[1])
        ref, rf = roles(base)
        r, funcs = roles(s)
        for role in args[2:] or sorted(r):
            a, b = rf.get(ref.get(role)), funcs.get(r.get(role))
            if b is None:
                continue
            if a is None:
                print('==== %s (new) ====' % role)
                print(b)
                continue
            d = list(difflib.unified_diff(norm(a).splitlines(), norm(b).splitlines(), SPECIES[base], SPECIES[s], n=2,
                                          lineterm=''))
            if d:
                print('==== %s ====' % role)
                print('\n'.join(d[2:]))
        return
    if args[:1] == ['--dump']:
        s, role = int(args[1]), args[2]
        r, funcs = roles(s)
        print(funcs.get(r.get(role), 'no %s' % role))
        return
    ref, rf = roles(21)
    ref_all = set().union(*(calls(b) for b in rf.values()))
    species = [int(a) for a in args] or range(1, 47)
    for s in species:
        try:
            r, funcs = roles(s)
        except FileNotFoundError:
            print('%2d %-8s (no decompile)' % (s, SPECIES[s]))
            continue
        cells = []
        for role in sorted(set(ref) | set(r)):
            a, b = rf.get(ref.get(role)), funcs.get(r.get(role))
            if b is None:
                continue
            ca, cb = calls(a or ''), calls(b)
            plus, minus = sorted(cb - ca), sorted(ca - cb)
            if plus or minus or a is None:
                cells.append('%s%s[%s%s]' % (role, '(new)' if a is None else '', ' '.join('+' + x[-5:] for x in plus),
                                             ' '.join(' -' + x[-5:] for x in minus)))
        extra = sorted(set().union(*(calls(b) for b in funcs.values())) - ref_all)
        print('%2d %-8s new calls: %s' % (s, SPECIES[s], ' '.join(x[-6:] for x in extra)))
        for c in cells:
            print('      ' + c)


if __name__ == '__main__':
    main()
