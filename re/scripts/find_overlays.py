"""Locate runtime-captured overlay code pages inside the disc's archive files."""
import base64, glob, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
caps = glob.glob(os.path.join(ROOT, r"build-dev\overlay_captures.json.d\*.json"))
files = {n: open(os.path.join(ROOT, "extracted", n), "rb").read()
         for n in [r"MAIN\MAIN.BIN", r"TOWN\TOWN.BIN", r"DUNGEON\DUNGEON.BIN", "OVMOVIE.BIN", "SLUS_006.14"]}
seen = set()
rows = []
for c in caps:
    for e in (json.load(open(c)) if True else []):
        pass
for c in caps:
    d = json.load(open(c))
    for e in (d if isinstance(d, list) else [d]):
        la = int(e["load_addr"], 16)
        data = base64.b64decode(e["bytes_b64"])
        for off in range(0, len(data) - 64, 512):
            probe = data[off:off + 64]
            if probe.count(0) > 48:
                continue
            hits = [(n, buf.find(probe)) for n, buf in files.items() if buf.find(probe) >= 0]
            if hits:
                for n, fo in hits:
                    key = (la + off, n, fo)
                    if key not in seen:
                        seen.add(key)
                        rows.append((la + off, n, fo, fo - off))
                break
rows.sort()
last = None
for ram, n, fo, base in rows:
    tag = (n, base - (ram - 0x80000000) if False else None)
    print(f"RAM 0x{ram:08X}  {n:22s} file+0x{fo:07X}  (page file base 0x{base:07X}, ram-file delta 0x{ram - fo:08X})")
