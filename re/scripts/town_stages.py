"""Extract every town event chain (actor slot -> ordered stages) from the location overlays.

Model (see re/NOTES.md -> Town events):
  actor entry (28 bytes): +0 key (id<<24 | variant<<16 | state byte), +8 -> {size, lba} script chunk
                          descriptor, +0x10 -> stage table, +0x14/+0x18 extra (per-slot data)
  stage (16 bytes):       +0 condition fn, +4 script fn (returns the script address to run),
                          +8 script address / data, +0xC i16 completion flag, +0xE i16
  The overlay's state selector (exterior FUN_80019F94) walks the stages: a stage whose flag is
  set is done; the first stage whose flag is clear and whose condition returns 0 is the current one.

Writes re/events/stages.json and re/events/stories.md (per character).
"""
import json, os, struct, sys
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(__file__))
import town_script_dis as tsd
import town_events as te

OUT = te.OUT
BASE = te.OVL_BASE


def u32(blob, off):
    return struct.unpack_from("<I", blob, off)[0] if 0 <= off <= len(blob) - 4 else 0


def s16(blob, off):
    return struct.unpack_from("<h", blob, off)[0] if 0 <= off <= len(blob) - 2 else -1


class Fn:
    """Summary of one overlay function (walked from its entry to the first jr ra + delay slot)."""
    def __init__(self, ov, addr):
        self.addr = addr
        self.flags = dict(set=[], clr=[], test=[])
        self.consts = []          # lui/addiu pairs loaded into v0 (candidate script addresses)
        self.calls = []
        self.returns_zero = False
        W = ov.w
        i = (addr - BASE) // 4
        hi = {}
        n = 0
        while 0 <= i < len(W) and n < 400:
            w = W[i]
            op = w >> 26
            if op == 0xF:                                   # lui
                hi[(w >> 16) & 31] = (w & 0xFFFF) << 16
            elif op == 9 and (w >> 21) & 31 in hi:          # addiu rt, rs, imm with rs from lui
                v = (hi[(w >> 21) & 31] + te.sx16(w & 0xFFFF)) & 0xFFFFFFFF
                self.consts.append(v)
            elif op == 3:
                tgt = 0x80000000 | ((w & 0x3FFFFFF) << 2)
                kind = ov.helpers.get(tgt) or te.FLAG_FNS.get(tgt)
                if kind:
                    imm = te.a0_imm(W, i)
                    if imm is not None and imm not in self.flags[kind]:
                        self.flags[kind].append(imm)
                else:
                    self.calls.append(tgt)
            if w == 0x03E00008:                             # jr ra
                if n == 0 and W[i + 1] == 0x00001021:
                    self.returns_zero = True
                break
            i += 1
            n += 1


def find_stage_tables(ov):
    """Runs of 16-byte stage records: two code pointers into the overlay and a sane flag."""
    data = ov.data
    lo, hi = BASE + 0x10, BASE + len(data)

    def is_code(p):
        return lo <= p < hi and p % 4 == 0

    def rec_ok(off):
        c, s = u32(data, off), u32(data, off + 4)
        f = s16(data, off + 12)
        return is_code(c) and is_code(s) and 0 <= f < 0x2000

    starts = set()
    for off in range(0, len(data) - 16, 4):
        if rec_ok(off) and rec_ok(off + 16):
            starts.add(off)
    return starts, rec_ok


def find_actor_entries(ov, rec_ok):
    """28-byte actor entries: +0x10 points at the start of a stage table (two valid records),
    +8 is 0 or points at a {size, lba} script descriptor, key = id<<24 | flag<<23 | variant<<16."""
    data = ov.data
    out = []
    for off in range(0, len(data) - 28, 4):
        st = u32(data, off + 16)
        if not BASE <= st < BASE + len(data) - 32:
            continue
        if not (rec_ok(st - BASE) and rec_ok(st - BASE + 16)):
            continue
        key = u32(data, off)
        if key & 0xC000FF00 or (key >> 24) == 0:
            continue
        desc = u32(data, off + 8)
        if desc and not (BASE <= desc < BASE + len(data) and te.is_script(u32(data, desc - BASE + 4))):
            continue
        out.append(off)
    return out


def script_candidates(ov, sf, base, cc):
    """Script addresses a stage's script fn can return: constants it loads into v0 directly, and
    entries of picker tables {u16 actor, i16 pos, u32 script} whose address it passes."""
    if not cc:
        return []
    ch = cc[0]
    out = []
    for v in sf.consts:
        if ch.inside(v):
            out.append(v)
        elif BASE <= v < BASE + len(ov.data) - 8:
            # picker table {u16 actor, i16 pos, u32 script}: the game (FUN_800194E4) takes the first
            # entry whose actor matches the one you talk to; tables of consecutive stages overlap
            o = v - BASE
            actors = set()
            for k in range(16):
                actor = struct.unpack_from("<H", ov.data, o + 8 * k)[0] if o + 8 * k + 8 <= len(ov.data) else 0xFFFF
                addr = u32(ov.data, o + 8 * k + 4)
                if actor >= 0x80 or not ch.inside(addr):
                    break
                if actor not in actors:
                    actors.add(actor)
                    out.append(addr)
    seen, res = set(), []
    for a in out:
        if a not in seen:
            seen.add(a)
            res.append(a)
    return res


def visit_gates(ov):
    """Per-location visit gate flags: the overlay init starts with
    `lui r,hi; addiu r2,r,lo; lh a0,lo(r); lh a1,2(r2); lh a2,4(r2); jal gate_fn` (exterior: 3377/3378)."""
    entry = u32(ov.data, 8)
    if not BASE <= entry < BASE + len(ov.data):
        return []
    W = ov.w
    i0 = (entry - BASE) // 4
    hi = {}
    for i in range(i0, min(i0 + 16, len(W))):
        w = W[i]
        if w >> 26 == 0xF:
            hi[(w >> 16) & 31] = (w & 0xFFFF) << 16
        elif w >> 26 == 0x21 and (w >> 16) & 31 == 4 and (w >> 21) & 31 in hi:   # lh a0,imm(r)
            a = (hi[(w >> 21) & 31] + te.sx16(w & 0xFFFF)) & 0xFFFFFFFF
            if BASE <= a < BASE + len(ov.data) - 6:
                fl = [s16(ov.data, a - BASE + 2 * k) for k in range(3)]
                return [f for f in fl if f > 1]
    return []


def chunk_for_desc(ov, desc):
    """Descriptor {size, lba} address -> lba."""
    if not desc:
        return None
    lba = u32(ov.data, desc - BASE + 4)
    return lba if te.is_script(lba) else None


def script_summary(chunk_cache, lba, addr, native_flags=None, native_consts=None):
    """Speakers, first lines and every flag set/cleared/tested by the script at addr: follows
    fall-through, branches, menus, calls and computed jumps (native fns' returned addresses)."""
    if lba not in chunk_cache or addr is None:
        return None
    ch, base = chunk_cache[lba]
    if not ch.inside(addr):
        return None
    speakers, lines, flags = [], [], dict(set=[], clr=[], test=[])
    faces = []                      # op 0x53: (actor, default portrait face, address)
    work, seen, steps = [addr], set(), 0
    first_path = True
    while work and steps < 4000:
        a = work.pop(0)
        speaker = None
        while ch.inside(a) and a not in seen and steps < 4000:
            seen.add(a)
            steps += 1
            ins = ch.insn(a)
            op = ins.get("op")
            if op == 0x57:
                speaker = ins["args"][0]
                nm = te.NAMES.get(speaker) if speaker else None
                if nm and nm not in speakers:
                    speakers.append(nm)
            elif op == 0x53:
                faces.append([ins["args"][0], ins["args"][1], "%08x" % a])
            elif op in (0x0C, 0x0D):
                k = "set" if op == 0x0C else "clr"
                if ins["args"][0] not in flags[k]:
                    flags[k].append(ins["args"][0])
            elif op in (0x18, 0x2B):
                if ins["args"][0] not in flags["test"]:
                    flags["test"].append(ins["args"][0])
                work.append(ins["args"][1])
            elif op in (0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43):
                work.append(ins["args"][1])
            elif op == 0x15:
                work.append(ins["args"][0])
            elif op == 0x4C:
                t = ins["args"][0]
                if native_flags:
                    for k, v in native_flags(t).items():
                        flags[k] += [f for f in v if f not in flags[k]]
                if native_consts:
                    work += [c for c in native_consts(t) if ch.inside(c)]
            elif op == 0x1A:
                # switch: targets follow the opcode; count from the last choice
                n = 0
                while n < 8 and ch.inside(ch.u32(a + 1 + 4 * n)) and ch.u32(a + 1 + 4 * n) != 0:
                    n += 1
                work += [ch.u32(a + 1 + 4 * i) for i in range(n)]
                break
            elif ins["name"] == "text":
                t = ins["text"].replace("<end>", "").strip()
                if t and len(lines) < 6 and first_path:
                    nm = te.NAMES.get(speaker) if speaker else ""
                    lines.append(((nm + ": ") if nm else "") + t)
                if ins["text"].endswith("<end>"):
                    break
            if op == 0x17:
                work.append(ins["args"][0])
                break
            if op in (0x16, 0x48):
                break
            a += max(1, ins["size"])
        first_path = False
    return dict(speakers=speakers, lines=lines, flags=flags, faces=faces)


def build():
    ovl_lbas = te.find_overlays()
    ovls = [te.Overlay(l, (ovl_lbas + [te.HI])[i + 1]) for i, l in enumerate(ovl_lbas)]
    catalog = json.load(open(os.path.join(OUT, "town_events.json"), encoding="utf-8"))
    loc_name = {l["lba"]: l["name"] for l in catalog["locations"]}
    chunk_base = {c["lba"]: int(c["base"], 16) for c in catalog["chunks"]}
    all_starts = sorted(set(ovl_lbas) | set(chunk_base))
    chunk_cache = {}
    for lba, base in chunk_base.items():
        data = te.chunk_bytes(lba, base, all_starts)
        chunk_cache[lba] = (tsd.Chunk(data, base, te.resolver), base)
    chains = []
    for ov in ovls:
        _, rec_ok = find_stage_tables(ov)
        fns = {}

        def fn(a):
            if a not in fns:
                fns[a] = Fn(ov, a)
            return fns[a]

        for off in find_actor_entries(ov, rec_ok):
            key = u32(ov.data, off)
            desc = u32(ov.data, off + 8)
            lba = chunk_for_desc(ov, desc)
            st = u32(ov.data, off + 16) - BASE
            stages = []
            for k in range(32):
                so = st + 16 * k
                if not rec_ok(so):
                    break
                c, s, x8 = u32(ov.data, so), u32(ov.data, so + 4), u32(ov.data, so + 8)
                flag = s16(ov.data, so + 12)
                cf, sf = fn(c), fn(s)
                cands = script_candidates(ov, sf, chunk_base.get(lba), lba and chunk_cache.get(lba))
                scripts = []
                for cand in cands:
                    sm = script_summary(chunk_cache, lba, cand,
                                        lambda t: fn(t).flags if BASE <= t < BASE + len(ov.data) else {},
                                        lambda t: fn(t).consts if BASE <= t < BASE + len(ov.data) else []) if lba else None
                    if sm and (sm["lines"] or any(sm["flags"].values())):
                        sm["addr"] = "%08x" % cand
                        scripts.append(sm)
                summ = scripts[0] if scripts else None
                stage = dict(index=k, flag=flag, cond="%08x" % c, script_fn="%08x" % s, data="%08x" % x8,
                             cond_always_zero=cf.returns_zero,
                             cond_flags={kk: v for kk, v in cf.flags.items() if v},
                             script_fn_flags={kk: v for kk, v in sf.flags.items() if v},
                             script=summ, scripts=scripts)
                stages.append(stage)
                if cf.returns_zero and flag == 0:
                    break                      # idle stage ends the chain
            chars = Counter()
            for sgi in stages:
                for sc in sgi["scripts"]:
                    for sp in sc["speakers"]:
                        if sp not in ("Koh", "Narrat", "Kewne"):
                            chars[sp] += 1
            x18 = u32(ov.data, off + 24)
            latches = []
            lt = u32(ov.data, off + 20)
            for k in range((x18 >> 16) & 0xFF):
                if BASE <= lt < BASE + len(ov.data):
                    for j in range(4):
                        f = s16(ov.data, lt - BASE + 8 * k + 2 * j)
                        if f > 1 and f not in latches:
                            latches.append(f)
            chains.append(dict(location=ov.lba, location_name=loc_name.get(ov.lba, "?"),
                               slot_flag=s16(ov.data, off + 24), latches=latches, gates=visit_gates(ov),
                               entry="%08x" % (BASE + off), key="%08x" % key, slot=(key >> 24) & 0x3F,
                               variant=(key >> 16) & 0x7F, chunk=lba,
                               extra=["%08x" % u32(ov.data, off + 20), "%08x" % u32(ov.data, off + 24)],
                               characters=[c for c, _ in chars.most_common()], stages=stages))
    with open(os.path.join(OUT, "stages.json"), "w", encoding="utf-8") as f:
        json.dump(chains, f, indent=1, ensure_ascii=False)
    write_stories(chains)
    print("chains", len(chains), "stages", sum(len(c["stages"]) for c in chains))
    return chains


def write_stories(chains):
    by = defaultdict(list)
    for c in chains:
        for ch in c["characters"][:2]:
            by[ch].append(c)
    order = list(te.GIRLS) + sorted(k for k in by if k not in te.GIRLS)
    with open(os.path.join(OUT, "stories.md"), "w", encoding="utf-8") as f:
        f.write("# Town event chains per character (generated by re/scripts/town_stages.py)\n\n")
        f.write("A chain is one actor slot in one location; its stages run in order. A stage is done when its\n"
                "flag is set; the first stage with a clear flag whose condition passes is what plays next.\n\n")
        for name in order:
            if name not in by:
                continue
            f.write("## %s\n\n" % name)
            for c in by[name]:
                f.write("### %s — slot %d/%d (entry %s, chunk %s)\n\n" % (c["location_name"], c["slot"], c["variant"],
                                                                        c["entry"], c["chunk"]))
                for s in c["stages"]:
                    sc = s["script"]
                    first = (sc["lines"][0] if sc and sc["lines"] else "")
                    req = []
                    for k, v in s["cond_flags"].items():
                        req.append("%s %s" % (k, ",".join(map(str, v))))
                    f.write("- stage %d: flag %s%s — %s%s\n" % (
                        s["index"], s["flag"] or "-", " (idle)" if s["cond_always_zero"] and not s["flag"] else "",
                        first[:80], ("  [cond: %s]" % "; ".join(req)) if req else ""))
                f.write("\n")


if __name__ == "__main__":
    build()
