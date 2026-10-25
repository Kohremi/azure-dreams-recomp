"""Stock dev-build floors with chosen monsters, for capturing species code (turn_capture.py):

    python test_encounters.py 2=23/3,24/7,25/5,22/10 [3=...] [--start N]
    python test_encounters.py --off

Each FLOOR=SPECIES/LEVEL,... fills that floor's 16 spawn slots round-robin with the list. The
patches go into a throwaway package in build-dev/mods/bundled (build output, never shipped:
`test.encounters`), and build-dev/mods/state.toml enables it, plus azure.dungeon's monster-density
with N monsters at floor start when --start is given (spawning during the floor stays vanilla).
--off removes the package and resets state.toml to `format_version = 2`. Restart the exe after
either."""
import os, sys, shutil
from make_dungeon_mod import floor_tables, floor_patches
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEV = os.path.join(REPO_ROOT, r'build-dev\mods')
PKG = os.path.join(DEV, 'bundled', 'test.encounters')
STATE = os.path.join(DEV, 'state.toml')


def main():
    args = sys.argv[1:]
    if args == ['--off']:
        shutil.rmtree(PKG, ignore_errors=True)
        open(STATE, 'w', newline='\n').write('format_version = 2\n')
        print('test encounters off')
        return
    start = None
    if '--start' in args:
        i = args.index('--start')
        start = int(args[i + 1])
        del args[i:i + 2]
    stock = floor_tables()
    rows = [list(r) for r in stock]
    for a in args:
        f, spec = a.split('=')
        mons = [tuple(int(x) for x in m.split('/')) for m in spec.split(',')]
        rows[int(f) - 1][1] = [mons[k % len(mons)] for k in range(16)]
    m = ['format_version = 6', 'id = "test.encounters"', 'version = "1.0.0"', 'name = "Test encounters"',
         'author = "Kohremi"', 'description = "Dev-only floor tables for capturing species code."',
         'license = "GPL-3.0"', 'resolver = "declarative"', '', '[[target]]', 'game_id = "SLUS-00614"',
         '', '[[feature]]', 'id = "tables"', 'name = "Tables"', 'description = "Test floor tables."',
         'group = "Dungeon"', 'default_enabled = false', 'channel = "experimental"']
    m += floor_patches('tables', [tuple(r) for r in rows], stock)
    os.makedirs(os.path.join(PKG, '1.0.0'), exist_ok=True)
    open(os.path.join(PKG, '1.0.0', 'manifest.toml'), 'w', newline='\n').write('\n'.join(m) + '\n')
    st = ['format_version = 2', '', '[[package]]', 'id = "test.encounters"', '', '[[feature]]',
          'package_id = "test.encounters"', 'id = "tables"', 'enabled = true']
    if start is not None:
        st += ['', '[[package]]', 'id = "azure.dungeon"', '', '[[feature]]', 'package_id = "azure.dungeon"',
               'id = "monster-density"', 'enabled = true', '[feature.values]', 'start_min = "%d"' % start,
               'start_max = "%d"' % start, 'spawn_base = "32"', 'spawn_spread = "31"']
    open(STATE, 'w', newline='\n').write('\n'.join(st) + '\n')
    print('test encounters:', ' '.join(args), '(start %s)' % start if start is not None else '')


if __name__ == '__main__':
    main()
