"""GP0 frame probe for the running dev build: who draws which textured primitive, from where in VRAM.

    python gpu_probe.py              newest frame: textured prims grouped by guest function
    python gpu_probe.py --frame N    a past frame still in the ring

Uses the framework decoder (psxrecomp/tools/psx_gpu_frame.py).
"""
import os, sys, json, argparse
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, os.path.join(REPO_ROOT, r"psxrecomp\tools"))
from psx_gpu_frame import DebugConn, capture  # noqa: E402


def tpage_xy(tp):
    """tpage word -> (x, y, bpp)."""
    return (tp & 0xF) * 64, ((tp >> 4) & 1) * 256, {0: 4, 1: 8, 2: 16}.get((tp >> 7) & 3, 16)


def clut_xy(c):
    return (c & 0x3F) * 16, (c >> 6) & 0x1FF


def textured(frame=None):
    with DebugConn(port=4370) as conn:
        dump = capture(conn, frame=frame)
    out = []
    tp = 0
    for p in dump["prims"]:
        if p.get("tpage") is not None:
            tp = p["tpage"]
        if not p["textured"] or not p["verts"]:
            continue
        xs = [v[0] for v in p["verts"]]
        ys = [v[1] for v in p["verts"]]
        us = [u[0] for u in p["uvs"]] or [0]
        vs = [u[1] for u in p["uvs"]] or [0]
        if p["kind"] == "rect" and p.get("size"):
            xs.append(xs[0] + p["size"][0]); ys.append(ys[0] + p["size"][1])
            us.append(us[0] + p["size"][0]); vs.append(vs[0] + p["size"][1])
        out.append(dict(func=p["func"], ra=p["ra"], op=p["op_name"], ot=p["ot"], tpage=tpage_xy(tp),
                        clut=clut_xy(p["clut"]) if p["clut"] is not None else None,
                        uv=p["uvs"], verts=p["verts"], scr=(min(xs), min(ys), max(xs), max(ys)), semi=p["semi"]))
    return dump["frame"], out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", type=int)
    ap.add_argument("--func")
    a = ap.parse_args()
    fr, prims = textured(a.frame)
    by = {}
    for p in prims:
        by.setdefault(p["func"], []).append(p)
    print("frame", fr, "textured prims", len(prims))
    for f, lst in sorted(by.items(), key=lambda kv: -len(kv[1])):
        tps = sorted({(p["tpage"], p["clut"]) for p in lst})
        print(f"{f}: {len(lst)} prims, ra {lst[0]['ra']}, tpage/clut {tps[:6]}{' ...' if len(tps) > 6 else ''}")
        if a.func and a.func.lower() == f.lower():
            for p in lst:
                print("   ", p["op"], "uv", p["uv"], "scr", p["scr"], "tp", p["tpage"], "clut", p["clut"])
