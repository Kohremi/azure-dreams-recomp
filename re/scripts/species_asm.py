"""Instruction-level comparison of the 46 species chunks: each role's function (species_roles.py)
is grouped with the identical copies in other chunks, and a species is listed only where its copy
is not the most common one (the template).

    python species_asm.py [species ...]          per species: roles that are not the template
    python species_asm.py --roles                per role: the variants and which species use them
    python species_asm.py --asm N ROLE           the function's disassembly
    python species_asm.py --vs N M ROLE          diff of species N's function against species M's

A function is what is reachable from its entry (branches and jumps inside the chunk followed,
calls not, ending at jr ra). Chunk addresses (jal/j targets, lui 0x8016/0x8017 and the low
halves built on them) and branch targets are masked, so relinked copies compare equal."""
import re, subprocess, sys, difflib
from collections import Counter, defaultdict
from species_roles import roles, BASE, END
from sprite_banks import SPECIES
import os
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OBJDUMP = os.path.join(REPO_ROOT, r're\tools\mipsel-gcc\bin\mipsel-none-elf-objdump.exe')
BIN = os.path.join(REPO_ROOT, r're\modules\species%02d_slot0_80170800.bin')
_cache = {}
BRANCH = re.compile(r'^(b\w*|beq\w*|bne\w*|bgez\w*|bltz\w*|blez\w*|bgtz\w*)\s')


def disasm(s):
    if s in _cache:
        return _cache[s]
    out = subprocess.run([OBJDUMP, '-D', '-b', 'binary', '-m', 'mips:3000', '-EL', '--adjust-vma=0x%X' % BASE,
                          BIN % s], capture_output=True, text=True).stdout
    ins = {}
    for line in out.splitlines():
        m = re.match(r'\s*([0-9a-f]{8}):\s+[0-9a-f]{8}\s+(.*)$', line)
        if m:
            ins[int(m.group(1), 16)] = re.sub(r'\s+', ' ', m.group(2).split('#')[0].strip())
    _cache[s] = ins
    return ins


def target(op):
    t = op.split(',')[-1].split()[-1]
    try:
        return int(t, 16)
    except ValueError:
        return None


def reach(ins, entry):
    """Addresses of the function's instructions, in address order."""
    seen, work = set(), [entry]
    while work:
        a = work.pop()
        while a in ins and a not in seen and BASE <= a < END:
            seen.add(a)
            op = ins[a]
            if BRANCH.match(op) and not op.startswith('bal'):
                t = target(op)
                seen.add(a + 4)
                if t is not None:
                    work.append(t)
                if op.startswith('b ') or op.startswith('beqz zero') or op.startswith('beq zero,zero'):
                    break
                a += 8
                continue
            if op.startswith('j ') :
                seen.add(a + 4)
                t = target(op)
                if t is not None and BASE <= t < END:
                    work.append(t)
                break
            if op.startswith('jr '):
                seen.add(a + 4)
                break
            a += 4
    return sorted(seen)


def norm_body(ins, addrs):
    hi = set()
    out = []
    sreg = {}

    def rename(m):
        # saved registers are allocated per copy: number them by first use
        return sreg.setdefault(m.group(0), 'S%d' % len(sreg))
    for a in addrs:
        op = re.sub(r"\bs[0-8]\b", rename, ins.get(a, '?'))
        if re.match(r'(sw|lw) S\d+,-?\d+\(sp\)$', op) or re.match(r'addiu sp,sp,-?\d+$', op):
            continue      # prologue/epilogue saves differ with the registers used
        m = re.match(r'lui (\w+),0x801[67]$', op)
        if m:
            hi.add(m.group(1))
            out.append('lui %s,HI' % m.group(1))
            continue
        mm = re.match(r'(\w+) (\w+),(\w+),(-?\d+)$', op)          # addiu rt,rs,imm
        if mm and mm.group(3) in hi:
            op = '%s %s,%s,LO' % mm.group(1, 2, 3)
        mm = re.match(r'(\w+) (\w+),(-?\d+)\((\w+)\)$', op)        # lw rt,imm(rs)
        if mm and mm.group(4) in hi:
            op = '%s %s,LO(%s)' % (mm.group(1), mm.group(2), mm.group(4))
        if BRANCH.match(op) or op.startswith('j ') or op.startswith('jal '):
            t = target(op)
            if t is not None and (BRANCH.match(op) or BASE <= t < END):
                op = op.rsplit(',', 1)[0] + ',L' if ',' in op else op.split()[0] + ' L'
        dst = re.match(r'\w+ (\w+)', op)
        if dst and not op.startswith('s') and not op.startswith('lui'):
            hi.discard(dst.group(1))
        out.append(op)
    return out


def body(s, role, raw=False):
    r, funcs = roles(s)
    a = r.get(role)
    if a is None:
        return None
    ins = disasm(s)
    addrs = reach(ins, a)
    return [(x, ins[x]) for x in addrs] if raw else norm_body(ins, addrs)


def variants():
    """role -> {normalised body tuple: [species]}"""
    v = defaultdict(lambda: defaultdict(list))
    for s in range(1, 47):
        try:
            r, _ = roles(s)
        except FileNotFoundError:
            continue
        for role in r:
            b = body(s, role)
            if b is not None:
                v[role][tuple(b)].append(s)
    return v


def main():
    args = sys.argv[1:]
    if args[:1] == ['--asm']:
        for x, op in body(int(args[1]), args[2], raw=True):
            print('%08X  %s' % (x, op))
        return
    if args[:1] == ['--vs']:
        a, b = body(int(args[2]), args[3]), body(int(args[1]), args[3])
        for l in difflib.unified_diff(a, b, SPECIES[int(args[2])], SPECIES[int(args[1])], n=3, lineterm=''):
            print(l)
        return
    v = variants()
    if args[:1] == ['--roles']:
        for role in sorted(v):
            groups = sorted(v[role].items(), key=lambda kv: -len(kv[1]))
            print('%-9s %s' % (role, ' | '.join('%d:%s' % (len(b), ','.join(str(s) for s in ss)) for b, ss in groups)))
        return
    tmpl = {role: max(g.items(), key=lambda kv: len(kv[1]))[0] for role, g in v.items()}
    for s in [int(a) for a in args] or range(1, 47):
        try:
            r, _ = roles(s)
        except FileNotFoundError:
            continue
        cells = []
        for role in sorted(r):
            b = body(s, role)
            if b is None or tuple(b) == tmpl[role]:
                continue
            sm = difflib.SequenceMatcher(None, list(tmpl[role]), b, autojunk=False)
            d = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != 'equal')
            others = [x for x in v[role][tuple(b)] if x != s]
            cells.append('%s:%d/%d%s' % (role, d, len(b), ('(=%s)' % ','.join(map(str, others))) if others else ''))
        print('%2d %-8s %s' % (s, SPECIES[s], '  '.join(cells) or 'template'))


if __name__ == '__main__':
    main()
