r"""Try floor-layout mod configurations end to end (venv Python).

For each config: write build-dev/mods/state.toml, launch the dev build, load save slot 4
(Koh on the 1F elevator), ride to 2F, print stats and render re/shots/layout_<name>.png.

    python layout_test.py                 # all configs below
    python layout_test.py big_rooms open  # just these
"""
import os, subprocess, sys, time

from psx import Game, EXE, DISC, BIOS
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATE = os.path.join(os.path.dirname(EXE), "mods", "state.toml")


def state_toml(package, features):
    out = ["format_version = 2", "", "[[package]]", 'id = "%s"' % package, 'version = "1.0.0"']
    for fid, values in features.items():
        out += ["", "[[feature]]", 'package_id = "%s"' % package, 'id = "%s"' % fid, "enabled = true"]
        if values:
            out += ["", "[feature.values]"]
            for k, v in values.items():
                out.append('%s = %s' % (k, ('"%s"' % v) if isinstance(v, str) else v))
    return "\n".join(out) + "\n"


CONFIGS = {
    "vanilla": {},
    "big_rooms": {"room-grid": {"columns": 3, "rows": 3}, "room-frequency": {"chance": "100"},
                  "room-size": {"width_bonus": 4, "height_bonus": 4}, "floor-elevation": {"style": "flat"}},
    "maze": {"room-frequency": {"chance": "50"}, "items-per-floor": {"amount": "lots"},
             "traps-per-floor": {"amount": "more"}},
    "open": {"open-floors": {"chance": "100"}, "traps-per-floor": {"amount": "none"}},
    "traps_lots": {"traps-per-floor": {"amount": "lots"}, "floor-elevation": {"style": "gentle"},
                   "room-size": {"width_bonus": 1, "height_bonus": 1}, "room-frequency": {"chance": "100"}},
    "extreme": {"room-grid": {"columns": 2, "rows": 2}, "room-frequency": {"chance": "100"},
                "room-size": {"width_bonus": 10, "height_bonus": 10}, "items-per-floor": {"amount": "lots"}},
}


def run(name, features):
    with open(STATE, "w", newline="\n") as fh:
        fh.write(state_toml("azure.dungeon", features))
    log = open(os.path.join(os.path.join(REPO_ROOT, r""), "devrun_%s.log" % name), "w")
    proc = subprocess.Popen([EXE, "--no-launcher", "--disc", DISC, "--bios", BIOS, "--debug-port", "4370"],
                            cwd=os.path.dirname(EXE), stdout=log, stderr=subprocess.STDOUT)
    try:
        g = Game(proc=proc)
        for _ in range(60):
            try:
                g.cmd("frame"); break
            except OSError:
                time.sleep(0.5)
        import attach
        attach.g = g
        import floor_render
        floor_render.g = g
        g.load_state(4); g.wait_frames(20)
        t0 = time.time()
        floor = attach.take_elevator()
        stats, prev = floor_render.floor_stats(), None
        for _ in range(20):                       # big floors finish populating later
            if stats == prev and stats["items"]:
                break
            prev = stats
            g.wait_frames(45)
            stats = floor_render.floor_stats()
        stats["secs_to_arrive"] = round(time.time() - t0, 1)
        st = attach.stairs()
        stats["elevator_reachable"] = bool(st) and attach.path_to_tile(st[0]) is not None
        path = floor_render.render_floor("layout_" + name)
        print(name, stats, path, flush=True)
        return stats
    finally:
        try:
            Game(proc=proc).cmd("quit")
        except Exception:
            pass
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(2)


if __name__ == "__main__":
    names = sys.argv[1:] or list(CONFIGS)
    for n in names:
        run(n, CONFIGS[n])
    with open(STATE, "w") as fh:
        fh.write("format_version = 2\n")
