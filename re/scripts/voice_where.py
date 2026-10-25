"""Show where a Japanese voice should go, to write re/events/voice_overrides.toml entries.

    python voice_where.py "town 7335" 8001773a      # source as in voices_missing.md, JP voice op address
    python voice_where.py "town 7335"               # every missing voice of that source
    python voice_where.py "town 5921" --side 8001d9a8 8001dbb0 8001eec4 8001f150   # both scripts,
                                                    # JP voice op addresses and current placements

Prints the Japanese script around the voice (voiced lines marked V) and the US pages near the place
its neighbours were mapped to (address, already voiced or not), so the right US line can be picked.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import voice_port as vp


def source_bytes(src):
    us, jp = vp.Town(vp.US_TOWN, vp.US_LBA), vp.Town(vp.JP_TOWN, vp.JP_LBA)
    if src.startswith("town "):
        jl = int(src.split()[1])
        for ul, ubase, jl2, jbase, uovl, jovl in vp.pair_chunks(us, jp, with_overlays=True):
            if jl2 == jl:
                ust, jst = us.starts(), jp.starts()
                jd = jp.chunk_bytes(jl, min([s for s in jst if s > jl] + [jl + 16]))
                ud = us.chunk_bytes(ul, min([s for s in ust if s > ul] + [ul + 16]))
                vp.register_entries(ud, ubase, vp.overlay_pointers(us, uovl, ubase))
                vp.register_entries(jd, jbase, vp.overlay_pointers(jp, jovl, jbase))
                return jd, jbase, ud, ubase, ul
    for name, U, uram, jd, jram, copies, row, ulen in vp.region_sources(us, jp):
        if name == src:
            return jd, jram, U[:ulen], uram, None
    raise SystemExit("unknown source " + src)


def lines(t, us=False):
    """[(address, text, voiced-op-before)] of the text runs, one per page start."""
    out, voice = [], None
    for i, (op, a, ins) in enumerate(t):
        if ins["junk"]:
            continue
        if op == 0x1D and vp.is_voice_op(t, i):
            voice = a - 1
        elif ins["name"] == "text":
            ok = vp.us_text_ok(ins["text"]) if us else bool(vp.visible(ins["text"]))
            if ok:
                out.append((a, vp.visible(ins["text"]), voice))
                voice = None
        elif op == 0x57:
            out.append((a, "<page %d>" % ins["args"][0], None))
        elif op == 0x11:
            out.append((a, "--", None))
    return out


def show(src, jop, d, jd, jbase, ud, ubase, ul):
    jt, ut = vp.tokens(jd, jbase), vp.tokens(ud, ubase)
    jl_, ul_ = lines(jt), lines(ut, True)
    k = next((i for i, x in enumerate(jl_) if x[2] == jop), None)
    print("=== %s voice %08x" % (src, jop))
    if k is None:
        print("  (voice not found before a text)")
        return
    for a, t, v in jl_[max(0, k - 6):k + 8]:
        print("  JP %08x %s %s" % (a, "V" if v else " ", t[:40]))
    # US neighbourhood: the US page of the nearest mapped JP voice before/after
    mapped = {}
    for v in d["voices"]:
        if v.get("kind") == "text" and (v.get("us_lba") == ul if ul else v.get("dungeon") == src):
            mapped[v["jp_op"]] = v["us_text"]
            for f in v.get("follow", []):
                pass
    before = [x[2] for x in jl_[:k] if x[2] in mapped]
    after = [x[2] for x in jl_[k + 1:] if x[2] in mapped]
    lo = mapped[before[-1]] if before else ubase
    hi = mapped[after[0]] if after else ubase + len(ud)
    voiced = set(mapped.values())
    print("  US between the neighbours' lines %08x..%08x:" % (lo, hi))
    for a, t, _ in ul_:
        if lo <= a <= hi:
            print("  US %08x %s %s" % (a, "V" if a in voiced else " ", t[:50]))


def side(src, d, jd, jbase, ud, ubase, ul, jlo, jhi, ulo, uhi):
    placed = {}
    for v in d["voices"]:
        if v.get("kind") == "text" and (v.get("us_lba") == ul if ul else v.get("dungeon") == src):
            placed[v["us_text"]] = v["jp_text"].strip()[:16]
            for f in v.get("follow", []):
                placed[v["us_text"]] += " + " + f["jp_text"].strip()[:10]
    for a, t, v in lines(vp.tokens(jd, jbase)):
        if jlo <= a <= jhi:
            print("JP %08x %s %s" % (a, ("voice op %08x" % v) if v else " " * 17, t[:40]))
    print()
    for a, t, _ in lines(vp.tokens(ud, ubase), True):
        if ulo <= a <= uhi:
            print("US %08x %-36s %s" % (a, t[:36], ("<- " + placed[a]) if a in placed else ""))


def main():
    src = sys.argv[1]
    d = json.load(open(vp.OUT_JSON, encoding="utf-8"))
    jd, jbase, ud, ubase, ul = source_bytes(src)
    if "--side" in sys.argv:
        k = sys.argv.index("--side")
        side(src, d, jd, jbase, ud, ubase, ul, *[int(x, 16) for x in sys.argv[k + 1:k + 5]])
        return
    if len(sys.argv) > 2:
        ops = [int(sys.argv[2], 16)]
    else:
        miss = open(vp.OUT_MISSING, encoding="utf-8").read().splitlines()
        ops = [int(l.split("`")[1], 16) for l in miss if l.startswith("- ") and (l[2:].startswith(src + " ") or
                                                                              l[2:].startswith(src + " ·"))]
    for jop in ops:
        show(src, jop, d, jd, jbase, ud, ubase, ul)


if __name__ == "__main__":
    main()
