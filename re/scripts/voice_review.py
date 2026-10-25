"""Review the Japanese Voices mapping: every voiced line as the Japanese text next to the English box it
plays on (with follow-ups and the boxes it keeps playing through), or what changed against an older
voices.json.

    python voice_review.py [out.txt]               # full listing (default re/events/voices_review.txt)
    python voice_review.py --diff old_voices.json  # voices whose placement changed since old_voices.json

Copy re/events/voices.json aside before changing voice_port.py or voice_overrides.toml, rerun
voice_port.py, then --diff against the copy and read every changed voice. Tags in the listing: R = placed
by the second/third alignment pass, S = a later line of a box (the Japanese box held several voices),
O = placed by voice_overrides.toml.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import voice_port as vp


def sources():
    """{("town", us_lba) | ("region", name): (JP tokens, US tokens, JP chunk lba | name)}"""
    us, jp = vp.Town(vp.US_TOWN, vp.US_LBA), vp.Town(vp.JP_TOWN, vp.JP_LBA)
    ust, jst = us.starts(), jp.starts()
    src = {}
    for ul, ubase, jl, jbase, uovl, jovl in vp.pair_chunks(us, jp, with_overlays=True):
        jd = jp.chunk_bytes(jl, min([s for s in jst if s > jl] + [jl + 16]))
        ud = us.chunk_bytes(ul, min([s for s in ust if s > ul] + [ul + 16]))
        vp.register_entries(ud, ubase, vp.overlay_pointers(us, uovl, ubase))
        vp.register_entries(jd, jbase, vp.overlay_pointers(jp, jovl, jbase))
        src[("town", ul)] = (vp.tokens(jd, jbase), vp.tokens(ud, ubase), jl)
    for name, U, uram, jd, jram, copies, row, ulen in vp.region_sources(us, jp):
        src[("region", name)] = (vp.tokens(jd, jram), vp.tokens(U[:ulen], uram), name)
    return src


def box(t, addr, us):
    """Text of the box starting at addr: its text runs up to the button wait (flow ops end it too)."""
    idx = next((i for i, x in enumerate(t) if x[1] == addr), None)
    if idx is None:
        return "?"
    out = []
    for op, a, ins in t[idx:idx + 60]:
        if ins["junk"]:
            continue
        if ins["name"] == "text":
            v = vp.visible(ins["text"])
            if v and (not us or vp.us_text_ok(ins["text"])):
                out.append(v)
        elif op == 0x11:
            break
        elif op in vp.BOX_FLOW and out:
            out.append("<%02x>" % op)
            if op != 0x57 or not us:
                break
    return " ".join(out)


def key(v):
    return ("town", v["us_lba"]) if v.get("us_lba") else ("region", v["dungeon"])


def listing(d, src):
    L = []
    for n, v in enumerate((v for v in d["voices"] if v["kind"] == "text"), 1):
        s = key(v)
        jt, ut, jname = src[s]
        jaddr = next((a for op, a, ins in jt if a > v["jp_op"] + 1 and ins["name"] == "text"
                      and vp.visible(ins["text"])), None)
        tag = "".join(c for c, k in (("R", "recovered"), ("S", "line_split"), ("O", "override")) if v.get(k))
        where = "US %d/JP %d" % (s[1], jname) if s[0] == "town" else s[1]
        L.append("#%d %s %08x voice %08x spk %s/%s %s" % (n, where, v["us_text"], v["jp_op"], v.get("jp_speaker"),
                                                         v.get("us_speaker"), tag))
        L.append("  JP: " + (box(jt, jaddr, False) if jaddr else v["jp_text"]))
        L.append("  US: " + box(ut, v["us_text"], True))
        for f in v.get("follow", []):
            L.append("  +JP: " + f["jp_text"].strip())
            for w in f.get("cont", []):
                a = vp.next_text(ut, w)
                L.append("  ..US: " + (box(ut, a, True) if a else "?"))
        for w in v["cont"]:
            a = vp.next_text(ut, w)
            L.append("  ..US: " + (box(ut, a, True) if a else "?"))
    return L


def placements(d):
    out = {}
    for v in d["voices"]:
        if v["kind"] != "text":
            continue
        s = key(v)
        if s == ("region", "tower: Beldo") and v["us_text"] < 0x80174000:
            continue                      # Beldo's other code-slot copies
        out[(s, v["jp_op"])] = dict(line=v["us_text"], how="line", cont=tuple(v["cont"]), jp=v["jp_text"])
        for f in v.get("follow", []):
            out[(s, "f:%s:%x" % (f["jp_text"], v["us_text"]))] = dict(line=v["us_text"], how="follow",
                                                                     cont=tuple(f.get("cont", [])), jp=f["jp_text"])
    return out


def diff(old, new, src):
    a, b = placements(old), placements(new)
    L, last = [], None
    for k in sorted(set(a) | set(b), key=lambda k: (str(k[0]), str(k[1]))):
        x, y = a.get(k), b.get(k)
        if x and y and (x["line"], x["how"], x["cont"]) == (y["line"], y["how"], y["cont"]):
            continue
        jt, ut, jname = src[k[0]]
        if k[0] != last:
            L.append("=== %s %s" % k[0])
            last = k[0]

        def desc(p):
            if not p:
                return "(none)"
            c = " +%d cont" % len(p["cont"]) if p["cont"] else ""
            return "%s %08x %s%s" % (p["how"], p["line"], box(ut, p["line"], True)[:60], c)
        L += ["  " + (x or y)["jp"].strip()[:40], "     was: " + desc(x), "     now: " + desc(y)]
    L.append("%d changed" % sum(1 for l in L if l.startswith("     now")))
    return L


def main():
    d = json.load(open(vp.OUT_JSON, encoding="utf-8"))
    src = sources()
    if "--diff" in sys.argv:
        old = json.load(open(sys.argv[sys.argv.index("--diff") + 1], encoding="utf-8"))
        print("\n".join(diff(old, d, src)))
        return
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(vp.ROOT, "re", "events", "voices_review.txt")
    L = listing(d, src)
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(sum(1 for l in L if l.startswith("#")), "voiced lines ->", out)


if __name__ == "__main__":
    main()
