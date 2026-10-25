"""When each species' melee blow lands, from its state-0x11 handler (species_roles.py role
'state_11'): most chunks wait for the attack sequence (sprite object +0x04 = step index, +0x14 &
0x1000 = the step just changed) to reach step N and then call the hit routine FUN_8009C12C (or call
it when the sequence ends, +0x14 & 0x8000); Pulunpa's form returns until the step is N. Some hit
twice (Grineut, Griffon: steps 3 and 5). Others count frames (+0x96) instead: Troll, Kewne, Baloon...
those are listed as 'timer' and need a live measurement (re/timelines).

Checked: Pulunpa's step 6 is 14 frames into its attack sequence, the blow measured live
(re/timelines/hit.txt).

    python melee_chains.py            table of all species
    python melee_chains.py --json     {species: [steps]} for tools/sprite_extract.py
"""
import json
import re
import sys

import species_roles as R
from sprite_banks import SPECIES

BS = chr(92)
STEP_EQ = re.compile(r"\(param_3 \+ 4\) == '" + BS + BS + "x([0-9a-f]{2})'")
STEP_NE = re.compile(r"(?:\(param_3 \+ 4\)|cVar\d) != '" + BS + BS + "x([0-9a-f]{2})'")
CVAR_READ = re.compile(r"(cVar\d) = \*\(char \*\)\(param_3 \+ 4\)")


def hit_steps(s):
    """(kind, [steps]) for species s: kind 'step', 'timer' or 'none'."""
    r, funcs = R.roles(s)
    b = funcs.get(r.get('state_11'), '')
    if not b:
        return 'none', []
    lines = b.splitlines()
    steps = []
    for i, l in enumerate(lines):
        if 'FUN_8009c12c' not in l:
            continue
        ctx = '\n'.join(lines[max(0, i - 3):i])
        m = STEP_EQ.search(ctx)
        if m:
            steps.append(int(m.group(1), 16))
            continue
        # Pulunpa's form: "if (cVar != N || !changed) && !ended) return;" a few lines up.
        ctx = '\n'.join(lines[max(0, i - 8):i])
        if CVAR_READ.search(b):
            m = STEP_NE.search(ctx)
            if m:
                steps.append(int(m.group(1), 16))
    if steps:
        return 'step', sorted(set(steps))
    if '(param_1 + 0x96)' in b:
        return 'timer', []
    return 'none', []


def main():
    out = {}
    for s in range(1, 47):
        try:
            kind, steps = hit_steps(s)
        except Exception as e:  # noqa: BLE001
            kind, steps = 'error %s' % e, []
        if kind == 'step':
            out[s] = steps
        if '--json' not in sys.argv:
            print('%2d %-8s %-6s %s' % (s, SPECIES[s], kind, steps))
    if '--json' in sys.argv:
        print(json.dumps(out))


if __name__ == '__main__':
    main()
