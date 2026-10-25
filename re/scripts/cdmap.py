"""Pull the CD-DMA ring from the running dev build and merge it into re/cdlog.jsonl,
then print contiguous (file, sector range) -> RAM range runs."""
import json, os, sys
from psx import Game, ROOT

FILES = [  # (name, first LBA, size bytes) from the ISO directory
    ("SLUS_006.14", 24, 0x80000), ("OVMOVIE.BIN", 280, 0x300000),
    ("MAIN.BIN", 1817, 0x275800), ("TOWN.BIN", 3077, 0x101B800),
    ("STRT/M_GAME1.STR", 11325, 1359872), ("STRT/DUMMYM.STR", 11989, 655360),
    ("DUNGEON.BIN", 12310, 0x1A86800), ("STR/MERGE.STR", 25892, 10731520),
    ("STR/DUMMY_.STR", 31132, 655360), ("STR/Q_GUY_M.STR", 31452, 14106624),
    ("STR/JO001_WS.STR", 38340, 2377728), ("STR/JO002_WS.STR", 39501, 4079616),
    ("STR/JO003_WS.STR", 41493, 15847424), ("STR/LOP1_WS.STR", 49231, 30769152),
    ("STR/LOP2_WS.STR", 64255, 45731840), ("STR/TOP_WS.STR", 86585, 1945600),
    ("STR/KONAMI.STR", 87535, 2910208), ("STR/STAFROLL.STR", 88956, 77496320),
]
LOG = os.path.join(ROOT, "re", "cdlog.jsonl")


def file_of(lba):
    for n, start, size in FILES:
        if start <= lba < start + (size + 2047) // 2048:
            return n, (lba - start) * 2048
    return "?", lba * 2048


def pull():
    g = Game()
    seen = set()
    if os.path.exists(LOG):
        for line in open(LOG):
            seen.add(json.loads(line)["seq"])
    entries = g.cmd("dma_cdrom_history", count=100000)["entries"]
    new = 0
    with open(LOG, "a") as f:
        for e in entries:
            if e["seq"] in seen or not e.get("completed"):
                continue
            f.write(json.dumps({k: e[k] for k in ("seq", "frame_start", "start_addr", "moved_words",
                                                   "lba", "sector_read_pos_start", "sector_size", "pc")}) + "\n")
            new += 1
    return new


def runs():
    ents = sorted((json.loads(l) for l in open(LOG)), key=lambda e: e["seq"])
    out, open_runs = [], {}
    for e in ents:
        ln = e["moved_words"] * 4
        if ln < 64:  # per-sector header fragments
            continue
        n, foff = file_of(e["lba"])
        # 2340-byte reads carry a 12-byte header/subheader before the user data
        foff += e["sector_read_pos_start"] - (12 if e.get("sector_size") == 2340 else 0)
        ram = int(e["start_addr"], 16) | 0x80000000
        r = open_runs.pop((n, foff, ram), None)
        if r is None:
            r = dict(file=n, fstart=foff, fend=foff, rstart=ram, rend=ram,
                     frame=e["frame_start"], frame_end=e["frame_start"], pc=e["pc"])
            out.append(r)
        r["fend"] += ln
        r["rend"] += ln
        r["frame_end"] = e["frame_start"]
        open_runs[(n, r["fend"], r["rend"])] = r
    return out


if __name__ == "__main__":
    if "--no-pull" not in sys.argv:
        print("new entries:", pull())
    for r in runs():
        if r["fend"] - r["fstart"] < 0x800 and "--all" not in sys.argv:
            continue
        print(f'f{r["frame"]:>6}-{r["frame_end"]:<6} {r["file"]:18s} +0x{r["fstart"]:07X}..0x{r["fend"]:07X} '
              f'-> RAM 0x{r["rstart"]:08X}..0x{r["rend"]:08X} ({(r["fend"]-r["fstart"])//1024}K) pc={r["pc"]}')
