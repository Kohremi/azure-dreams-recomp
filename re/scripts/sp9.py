"""Species plan-9 / 0xA code: the control switch's case 9 / case 10 bodies and the functions they
call, then the special states (0x17 and up):  python sp9.py SPECIES [--states]"""
import re, sys
from species_roles import roles

s = int(sys.argv[1])
r, f = roles(s)
ctl = f.get(r.get('control'), '')
k = ctl.find('switch(*(ushort *)(param_4 + 0x46)')
sw = ctl[k:]
seen = set()
for case in ('case 9:', 'case 10:'):
    i = sw.find(case)
    if i < 0:
        continue
    j = sw.find('case ', i + 6)
    body = sw[i:j if j > 0 else i + 800]
    print('//// control', body.strip())
    for m in re.findall(r'FUN_(8017[0-9a-f]{4})\(', body):
        a = int(m, 16)
        if a not in seen and a in f:
            seen.add(a)
            print('//// %x' % a)
            print(f[a])
if '--states' in sys.argv:
    for st in sorted(x for x in r if x.startswith('state_') and int(x[6:], 16) >= 0x17):
        print('//// %s %x' % (st, r[st]))
        print(f[r[st]])
