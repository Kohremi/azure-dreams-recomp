"""Print functions from the dungeon module decompile (re/ghidra/dungeon_decomp_full.c) by address:

    python dfun.py 800c8788 800c8db0"""
import re, sys
import os
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SRC = os.path.join(REPO_ROOT, r're\ghidra\dungeon_decomp_full.c')


def funcs():
    src = open(SRC, encoding='utf-8', errors='replace').read()
    out = {}
    for m in re.finditer(r'(?m)^// ==== ([0-9a-f]{8}) \S+.*\n', src):
        j = src.find('\n// ==== ', m.end())
        out[int(m.group(1), 16)] = src[m.end():j if j > 0 else len(src)]
    return out


if __name__ == '__main__':
    f = funcs()
    for a in sys.argv[1:]:
        print(f.get(int(a, 16), 'no function at %s' % a))
