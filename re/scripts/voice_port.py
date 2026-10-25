"""Port the Japanese voice acting into the US town scripts.

The Japanese release (SLPM-86047) voices town dialogue: before each voiced line its scripts run
`30 1D a b` (yield; op 0x1D = FUN_8003F540(channel, LBA_TABLE[DAT_800721C0[(a>>19)&31]], a & 0xFF07FFFF, b)).
The US release has the same engine but its scripts drop those ops, and its stream LBA table
(EXE 0x8006CD50, 24 entries) points entries 3..18 (the voice files STRT/A..O and STR/P) at MERGE.STR.

This script
  1. pairs every US town script chunk with its Japanese counterpart (same overlay order, same
     descriptor order) and aligns the two op streams on structural ops (speaker/actor/choice/branch
     ops; text and box breaks differ because the translation re-flowed the text);
  2. attaches each Japanese voice op to the text it is played for and maps it to the US box at the
     same place (later voices of a US box that joins several Japanese boxes become follow-ups);
  3. pairs the overlay pointer tables through which native code picks voice clip subroutines
     (`30 1D a b 16`; the US tables point at bare `16`s);
  4. writes re/events/voices.json and mods_src/azure_voice_data.h (rows + snippet bytes) used by the
     "Japanese Voices" plugin, which patches each voiced US line in RAM with a jump to its snippet.

The disc side (appending the voice files to a US image) is build_voice_disc.py.
"""
import json, os, struct, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import town_script_dis as tsd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
US_TOWN = os.path.join(ROOT, r"extracted\TOWN\TOWN.BIN")
JP_TOWN = os.path.join(ROOT, r"extracted_jp\TOWN\TOWN.BIN")
US_LBA, JP_LBA = 3077, 3846
DEBUG_PAGES = set()      # page addresses whose gap align_chunk prints (debugging)
OUT_JSON = os.path.join(ROOT, r"re\events\voices.json")
OUT_H = os.path.join(ROOT, r"mods_src\azure_voice_data.h")

# ops that carry the script's structure (identical in both releases)
STRUCT_OPS = {0x0F, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1C, 0x2A, 0x2B, 0x2C, 0x2E, 0x2F, 0x0C, 0x0D,
              0x34, 0x3E, 0x3F, 0x4C, 0x53, 0x57, 0x24, 0x25, 0x26, 0x27, 0x12, 0x13, 0x1E, 0x54, 0x55}


class Town:
    def __init__(self, path, lba0):
        self.D = open(path, "rb").read()
        self.LO = lba0
        self.HI = lba0 + len(self.D) // 2048

    def u32(self, off):
        return struct.unpack_from("<I", self.D, off)[0]

    def overlays(self):
        out = []
        for s in range(0, len(self.D), 2048):
            w0, w1, _, w3 = struct.unpack_from("<4I", self.D, s)
            if w0 == 0 and w1 == 0x4C070707 and w3 == 1:
                out.append(s // 2048 + self.LO)
        return out

    def is_script(self, lba):
        if not self.LO <= lba < self.HI:
            return False
        o = (lba - self.LO) * 2048
        w = self.u32(o)
        return 1 <= w < 0x100 and self.D[o + 4] != 0

    def overlay_info(self, lba, nxt):
        o = (lba - self.LO) * 2048
        data = self.D[o:min((nxt - self.LO) * 2048, o + 0x14000)]
        n = len(data) // 4
        W = struct.unpack("<%dI" % n, data[:n * 4])
        bases = []
        for i, w in enumerate(W):
            if w >> 26 == 0x2B and w & 0xFFFF == 44:
                rt = (w >> 16) & 31
                lo = hi = None
                for j in range(i - 1, max(0, i - 6), -1):
                    x = W[j]
                    if x >> 26 == 9 and (x >> 16) & 31 == rt and lo is None:
                        lo = (x & 0xFFFF) - (0x10000 if x & 0x8000 else 0)
                    if x >> 26 == 0xF and (x >> 16) & 31 == rt:
                        hi = x & 0xFFFF
                        break
                if lo is not None and hi is not None:
                    bases.append(((hi << 16) + lo) & 0xFFFFFFFF)
        chunks, k = [], 0
        while k + 8 <= len(data):
            z, l = struct.unpack_from("<II", data, k)
            if z == 0 and self.is_script(l):
                if l not in chunks:
                    chunks.append(l)
                k += 8
            else:
                k += 4
        if not chunks:
            # event overlays list their chunks as {lba, sectors << 20} (like the exterior's door list)
            for k in range(0, len(data) - 8, 4):
                l, w = struct.unpack_from("<II", data, k)
                if self.is_script(l) and w & 0xFFFFF == 0 and 1 <= w >> 20 <= 0x100 and l not in chunks:
                    chunks.append(l)
        return bases, chunks

    def starts(self):
        """Every overlay and every script chunk any overlay refers to (chunk boundaries)."""
        ovs = self.overlays()
        out = set(ovs)
        for i, o in enumerate(ovs):
            out.update(self.overlay_info(o, (ovs + [self.HI])[i + 1])[1])
        return sorted(out)

    def chunk_bytes(self, lba, limit_lba):
        o = (lba - self.LO) * 2048
        data = self.D[o:(limit_lba - self.LO) * 2048][:0x8000]
        e = len(data)
        while e and data[e - 1] == 0:
            e -= 1
        return data[:e]


_TOKEN_CACHE = {}
_ENTRIES = {}          # (base, len, hash) -> script entry points known from outside (overlay tables)


def register_entries(data, base, entries):
    """Tell tokens() where scripts of this chunk start (pointers in its overlay program): op 0x01 ends
    a script and the next one may start a byte or two later, reached only through such a pointer."""
    _ENTRIES[(base, len(data), hash(data))] = {e for e in entries if base + 4 <= e < base + len(data)}


def tokens(data, base):
    """Bytecode tokens (until the chunk's MIPS helpers). Tokens that cannot be script (unknown
    opcodes, text that does not decode) are kept but marked junk so alignment skips them.

    The decode resyncs at jump targets: scripts leave dead bytes the VM never runs (e.g. after a
    button wait, before the `page` op that the branches jump to), and a plain linear decode reads
    them as ops or text and loses step. So: decode, collect every jump/call/switch target, decode
    again restarting at any target that falls inside a token, until the targets stop changing."""
    key = (base, hash(data), len(data))
    if key in _TOKEN_CACHE:
        return _TOKEN_CACHE[key]
    ch = tsd.Chunk(data, base)
    natives = tsd.mips_ranges(ch)
    end = base + len(data)
    entries = sorted(_ENTRIES.get((base, len(data), hash(data)), ()))
    targets = set()
    for _ in range(4):
        out = decode(ch, base + 4, end, natives, targets, entries)
        new = set()
        for op, a, ins in out:
            if ins["junk"] or op not in (0x15, 0x17, 0x18, 0x2B, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x1A):
                continue
            for t in (ins.get("targets") or []) + [x for x in ins.get("args", []) if isinstance(x, int)]:
                if base + 4 <= t < end:
                    new.add(t)
        if new <= targets:
            break
        targets |= new
    _TOKEN_CACHE[key] = out
    return out


ENDS = {0x01, 0x16, 0x17, 0x48}      # end of script, ret, goto, jmp_v: what follows starts elsewhere


def decode(ch, start, end, natives, targets, entries=()):
    """Linear decode that restarts at every address in `targets` (cutting the token across it) and,
    right after a script-ending op, at an entry point within the next 8 bytes."""
    out, a, last_choice = [], start, 0
    tlist = sorted(targets)
    import bisect
    while a < end:
        if any(lo <= a < hi for lo, hi in natives):
            break
        if out and out[-1][0] in ENDS:
            # After a script ends, the next one may start a few bytes later: the US pads with leftover
            # bytes (JP: zeros), and the plain decode then swallows the next script's first op.
            # Restart only where the plain decode would cut across that start (or reads garbage):
            # at a known entry point within 8 bytes, else at a speaker op `57 xx`.
            probe = ch.insn(a)
            reach = a + max(1, probe["size"])
            garbage = probe["name"].startswith("bad") or (probe["name"] == "text" and (
                "{" in probe["text"] or len(visible(probe["text"])) <= 2))
            nxt_start = None
            speaker_here = ch.u8(a) == 0x57 and a + 1 < end and ch.u8(a + 1) < 0x60
            if entries and not speaker_here:
                k = bisect.bisect_right(entries, a)
                if k < len(entries) and entries[k] - a <= 8 and (entries[k] < reach or garbage):
                    nxt_start = entries[k]
            if nxt_start is None and ch.u8(a) != 0x57:
                for p in range(a + 1, min(a + 7, end - 1)):
                    if ch.u8(p) == 0x57 and ch.u8(p + 1) < 0x60 and (p < reach or garbage):
                        nxt_start = p
                        break
            if nxt_start is not None and nxt_start > a:
                out.append((None, a, dict(op=None, name="dead", size=nxt_start - a, junk=True)))
                a = nxt_start
                continue
        ins = ch.insn(a)
        op = ins.get("op")
        if op in tsd.CHOICE:
            last_choice = ins["args"][0]
        if op == 0x1A:
            n = last_choice or 2
            ins["targets"] = [ch.u32(a + 1 + 4 * i) for i in range(n) if ch.inside(a + 4 + 4 * i)]
            ins["size"] = 1 + 4 * len(ins["targets"])
        nxt = a + max(1, ins["size"])
        k = bisect.bisect_right(tlist, a)
        if k < len(tlist) and tlist[k] < nxt:          # a jump target inside: these bytes are dead
            out.append((None, a, dict(op=None, name="dead", size=tlist[k] - a, junk=True)))
            a = tlist[k]
            continue
        junk = ins["name"].startswith("bad")
        if ins["name"] == "text":
            t = ins["text"]
            bad = t.count("{")
            junk = bad >= 3 and bad * 6 > len(t)
        ins["junk"] = junk
        out.append((op, a, ins))
        a = nxt
    return out


FLOW_STOP = {0x01, 0x16, 0x18, 0x19, 0x1A, 0x2A, 0x2B, 0x2C, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x48, 0x4B}


def voiced_text(jt, at, i):
    """Index of the text a voice op at jt[i] is played for: the next text the script reaches
    (following call/goto), or None when a branch comes first."""
    j, steps = i + 1, 0
    while j < len(jt) and steps < 40:
        op, a, ins = jt[j]
        steps += 1
        if ins["junk"] or op in FLOW_STOP:
            return None
        if ins["name"] == "text" and ins["text"].replace("<end>", "").strip():
            return j
        if op in (0x15, 0x17):
            j = at.get(ins["args"][0])
            if j is None:
                return None
            continue
        j += 1
    return None


def is_voice_op(jt, i):
    """A real Japanese voice op: `30 1D a b` with a sane file index / channel."""
    op, a, ins = jt[i]
    if op != 0x1D or i == 0 or jt[i - 1][0] != 0x30:
        return False
    va, vb = ins["args"]
    return ((va >> 19) & 31) < 16 and (va >> 24) < 32 and (vb & 0xFFFFF) > (va & 0x7FFFF)


def struct_key(op, ins):
    """Structural token key: op plus its non-address operands."""
    if op in (0x15, 0x17, 0x4C):
        return (op,)
    if op in (0x18, 0x2B):
        return (op, ins["args"][0])
    if op in (0x3E, 0x3F):
        return (op, ins["args"][0])
    if op == 0x1A:
        return (op, len(ins.get("targets", [])))
    return (op,) + tuple(x for x in ins.get("args", []) if isinstance(x, int))


def visible(t):
    return t.replace("<end>", "").strip()


def us_text_ok(t):
    """A real US dialogue text: no kana/kanji and nothing undecodable (those are bytes of other ops or
    data that a linear decode read as text)."""
    v = visible(t)
    return (bool(v) and "{" not in v and not any(ord(c) >= 0x3000 for c in v)
            and any(c.isalnum() or c in ".!?-" for c in v))    # not a lone choice icon (○ ×)


def align_chunk(jd, jbase, ud, ubase, struct_ops=None):
    """Map the Japanese voices of one chunk onto the US script.

    Both op streams are aligned on structural ops (difflib); between two structural ops (a gap) the
    Japanese text is cut into segments (a new one at every voiced text and after every button wait)
    and the US text into pages (cut after every button wait, which is what the player sees as a box).
    Same counts map one to one; otherwise each US page goes to the segment that holds its middle
    (by share of the gap's text). A voiced segment's voice plays at its first US page; further pages
    of the same segment are continuations (the voice keeps playing through their button waits); a
    voiced segment that holds no page's middle joins the page it starts in (a follow-up voice).

    Returns (voices, stats): voices = one dict per voiced US page (us_text, a, b, jp_text, us_line,
    jp_op, wait, more = follow-up voices, cont = continuation wait addresses)."""
    import difflib
    struct_ops = STRUCT_OPS if struct_ops is None else struct_ops
    jt, ut = tokens(jd, jbase), tokens(ud, ubase)
    at = {a: i for i, (op, a, ins) in enumerate(jt)}
    targets, n_voices = defaultdict(list), 0
    for i, (op, a, ins) in enumerate(jt):
        if ins["junk"] or op != 0x1D or not is_voice_op(jt, i):
            continue
        if i + 1 < len(jt) and jt[i + 1][0] == 0x16:
            continue                  # a clip subroutine `30 1D a b 16`: see table_voices
        n_voices += 1
        k = voiced_text(jt, at, i)
        if k is None:
            k = next((j for j in range(i + 1, min(len(jt), i + 12)) if jt[j][2]["name"] == "text"), i)
        targets[k].append((ins["args"][0], ins["args"][1], jt[i - 1][1]))
    # Japanese segments per gap (with the speaker: the last `page` op before the text)
    jkeys, jsegs, cur, spk, fresh = [], defaultdict(list), None, None, True
    for i, (op, a, ins) in enumerate(jt):
        if i in targets and ins["name"] != "text":
            cur = dict(voices=list(targets[i]), chars=0, text="", speaker=spk, box=fresh)  # voice with no text found
            jsegs[len(jkeys)].append(cur)
            fresh = False
        if ins["junk"]:
            continue
        if op == 0x57:
            spk = ins["args"][0]
        if op in BOX_BREAK:                   # the JP game stops the voice here: what follows is a new box
            fresh = True
        if op in struct_ops:
            jkeys.append(struct_key(op, ins))
            cur = None
        elif op == 0x11:
            cur = None
        elif ins["name"] == "text" and (visible(ins["text"]) or i in targets):
            if i in targets or cur is None:
                cur = dict(voices=list(targets.get(i, [])), chars=0, text=ins["text"], speaker=spk, box=fresh)
                jsegs[len(jkeys)].append(cur)
                fresh = False
            cur["chars"] += max(1, len(visible(ins["text"])))
    # US pages per gap
    ukeys, upages, cur, spk = [], defaultdict(list), None, None
    for op, a, ins in ut:
        if ins["junk"]:
            continue
        if op == 0x57:
            spk = ins["args"][0]
        if op in struct_ops:
            ukeys.append(struct_key(op, ins))
            cur = None
        elif op == 0x11:
            if cur is not None:
                cur["wait"] = a
            cur = None
        elif ins["name"] == "text" and us_text_ok(ins["text"]):
            if cur is None:
                cur = dict(addr=a, wait=None, chars=0, text=ins["text"], speaker=spk, lines=[])
                upages[len(ukeys)].append(cur)
            cur["lines"].append((a, len(visible(ins["text"])), ins["text"]))
            cur["chars"] += len(visible(ins["text"]))
    sm = difflib.SequenceMatcher(None, jkeys, ukeys, autojunk=False)
    jmap = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size + 1):
            jmap[blk.a + k] = blk.b + k
    out, lost, joined, conts, missing = [], 0, 0, 0, []
    # JP gaps that land on the same US gap (the US dropped a structural op between them) share its pages
    groups = defaultdict(list)
    for g in sorted(jsegs):
        u = jmap.get(g)
        groups[u if u is not None and upages.get(u) else ("lost", g)].append(g)
    for key, gs in sorted(groups.items(), key=lambda kv: kv[1][0]):
        g = gs[0]
        segs = []
        for gg in gs:
            for sg in jsegs[gg]:
                if segs and not sg["voices"] and not sg["box"]:
                    segs[-1] = dict(segs[-1], chars=segs[-1]["chars"] + sg["chars"])   # same box, same voice
                else:
                    segs.append(sg)
        nv = sum(len(sg["voices"]) for sg in segs)
        if not nv:
            continue
        pages = [] if isinstance(key, tuple) else upages[key]
        if not pages:
            lost += nv
            near = next((jmap[k] for k in range(g, -1, -1) if k in jmap), None)
            us_near = [] if near is None else [pg["text"] for k in range(max(0, near - 1), near + 3)
                                                for pg in upages.get(k, [])][:4]
            for sg in segs:
                for a, b, jop in sg["voices"]:
                    missing.append(dict(reason="no US text at that place" if g in jmap else "scene differs",
                                        jp_text=sg["text"], jp_op=jop, a=a, b=b, us_near=us_near,
                                        jp_speaker=sg["speaker"]))
            continue
        if DEBUG_PAGES & {pg["addr"] for pg in pages}:
            print("gap", [(sg["text"].strip()[:10], len(sg["voices"]), sg["chars"], sg.get("box")) for sg in segs])
            print("   pages", [("%x" % pg["addr"], pg["text"].strip()[:12], pg["chars"], pg["wait"] and "%x" % pg["wait"]) for pg in pages])
        TJ = float(sum(sg["chars"] for sg in segs)) or 1.0
        TU = float(sum(pg["chars"] for pg in pages)) or 1.0
        jcum = [0.0]
        for sg in segs:
            jcum.append(jcum[-1] + sg["chars"] / TJ)
        ucum = [0.0]
        for pg in pages:
            ucum.append(ucum[-1] + pg["chars"] / TU)

        def seg_at(x):
            return max(k for k in range(len(segs)) if jcum[k] <= x + 1e-9)

        def page_at(x):
            return max(k for k in range(len(pages)) if ucum[k] <= x + 1e-9)
        if len(segs) == len(pages) and all(sg["box"] for sg in segs):
            seg_of_page = list(range(len(pages)))      # box for box (voices that share a JP box: by text)
        else:
            seg_of_page = [seg_at((ucum[q] + ucum[q + 1]) / 2) for q in range(len(pages))]
        pages_of_seg = defaultdict(list)
        for q, sidx in enumerate(seg_of_page):
            pages_of_seg[sidx].append(q)
        by_page = {}
        for sidx, sg in enumerate(segs):
            if not sg["voices"]:
                continue
            qs = pages_of_seg.get(sidx) or [page_at(jcum[sidx])]
            if sg["box"] and len(qs) > 1 and qs[0] in by_page and len(pages[qs[0]]["lines"]) < 2:
                qs = qs[1:]                   # a new JP box that would only follow a one-line box's voice and
                                              # also fills later pages: start it on its own page
            q = qs[0]
            owner = None
            for a, b, jop in sg["voices"]:
                v = dict(a=a, b=b, jp_text=sg["text"], jp_op=jop, jp_speaker=sg["speaker"], jp_chars=sg["chars"],
                         cont=[], box=sg["box"])
                if q not in by_page:
                    by_page[q] = owner = dict(v, us_text=pages[q]["addr"], us_line=pages[q]["text"],
                                              us_speaker=pages[q]["speaker"], wait=pages[q]["wait"], more=[],
                                              lines=pages[q]["lines"])
                else:
                    by_page[q]["more"].append(v)
                    owner = v
                    joined += 1
            for qq in qs[1:]:                 # the segment's last voice keeps playing through these waits
                if pages[qq - 1]["wait"] is not None:
                    owner["cont"].append(pages[qq - 1]["wait"])
        for q, v in by_page.items():          # a page that has its own voice is no continuation
            for m in [v] + v["more"]:
                m["cont"] = [w for w in m["cont"] if not any(pages[k]["wait"] == w and k + 1 in by_page
                                                             for k in range(len(pages)))]
        for q, v in list(by_page.items()):
            for extra in split_lines(v):
                conts += len(extra["cont"])
                out.append(extra)
        for q, v in by_page.items():
            conts += sum(len(m["cont"]) for m in [v] + v["more"])
            out.append(v)
    out.sort(key=lambda v: v["us_text"])
    return out, dict(jp_voices=n_voices, mapped=len(out), dropped=joined, lost=lost, conts=conts,
                     ratio=round(sm.ratio(), 3), missing=missing)


# ops after which the Japanese script shows a new box (button wait, speaker change, choice, script end)
BOX_BREAK = {0x11, 0x57, 0x19, 0x2A, 0x2C, 0x01, 0x16, 0x17, 0x48}

PATCH = 5                                   # `17 addr`: goto the snippet
# ops the patch may move into the snippet: all but those that call native code (it could read bytes
# after the op); addresses in operands are absolute, so moved ops behave the same
SPAN_BLOCK = {0x4C, 0x2E, 0x2F}


def references(ut):
    """Addresses the chunk refers to: (code, data). code = jump/call/branch targets and switch tables
    (the VM arrives there and runs the goto); data = text fragments and data operands (read as bytes,
    so a patch must not touch them at all)."""
    code, data = set(), set()
    for op, a, ins in ut:
        if ins["junk"]:
            continue
        code.update(ins.get("targets", []) or [])
        data.update(ins.get("frags", []) or [])
        spec = tsd.OPS.get(op, ("", ""))[1] if op is not None else ""
        args = [x for x in ins.get("args", []) if isinstance(x, int)]
        for k, x in zip([k for k in spec if k != "A"], args):
            if k == "a":
                code.add(x)
            elif k == "d":
                data.add(x)
    return code, data


def patch_span_why(ut, refs, text_addr):
    """Why patch_span refuses a line (for the missing-voices report)."""
    idx = next((i for i, t in enumerate(ut) if t[1] == text_addr), None)
    if idx is None or idx + 1 >= len(ut):
        return "line not found"
    end, i = ut[idx + 1][1], idx + 1
    while end - text_addr < PATCH:
        if i + 1 >= len(ut) or ut[i][0] in SPAN_BLOCK or ut[i][2]["junk"]:
            return "line shorter than 5 bytes, followed by a native call"
        end, i = ut[i + 1][1], i + 1
    code, data = refs
    if any(text_addr < r < end for r in code):
        return "a jump lands inside the line"
    if any(text_addr <= r < end for r in data):
        return "the line is also used as a text fragment / data"
    return "?"


def patch_span(ut, refs, text_addr):
    """Bytes from text_addr the plugin overwrites with `17 snippet`: the whole text run (copied into
    the snippet as is), extended over operand-less ops while shorter than the goto. None when the
    span cannot be moved (something refers into it, or the run is cut by other ops)."""
    idx = next((i for i, t in enumerate(ut) if t[1] == text_addr), None)
    if idx is None or idx + 1 >= len(ut):
        return None
    end = ut[idx + 1][1]
    i = idx + 1
    while end - text_addr < PATCH:
        if i + 1 >= len(ut) or ut[i][0] in SPAN_BLOCK or ut[i][2]["junk"]:
            return None
        end = ut[i + 1][1]
        i += 1
    code, data = refs
    if any(text_addr < r < end for r in code) or any(text_addr <= r < end for r in data):
        return None
    return end - text_addr


OVL_BASE = 0x80016000           # every location overlay program loads here


def overlay_words(T, ovl, limit):
    """{address: word} of a location overlay program as loaded (below its scripts' load base `limit`,
    and before its first script chunk on disc)."""
    o = (ovl - T.LO) * 2048
    end = o + 2048
    while end < len(T.D) and end - o < 0x40000 and not T.is_script(end // 2048 + T.LO) and             not (T.u32(end) == 0 and T.u32(end + 4) == 0x4C070707):
        end += 2048
    return {OVL_BASE + k: T.u32(o + k) for k in range(0, min(end - o, limit - OVL_BASE), 4)}


def overlay_pointers(T, ovl, limit):
    """Addresses an overlay program refers to: data words, and lui/addiu (or lui/ori) pairs in its
    code (script functions build the address of the script they start that way)."""
    w = overlay_words(T, ovl, limit)
    out = set(w.values())
    items = sorted(w.items())
    hi = {}
    for a, x in items:
        if x >> 26 == 0x0F:                                    # lui rt, imm
            hi[(x >> 16) & 31] = (x & 0xFFFF) << 16
        elif x >> 26 in (0x09, 0x0D) and (x >> 21) & 31 in hi:  # addiu / ori rt, rs, imm
            lo = x & 0xFFFF
            if x >> 26 == 0x09 and lo & 0x8000:
                lo -= 0x10000
            out.add((hi[(x >> 21) & 31] + lo) & 0xFFFFFFFF)
    return out


def table_voices(us, jp, uovl, jovl, ubase, ud, jbase, jd):
    """Voice clips the Japanese scripts keep as subroutines `30 1D a b 16` picked through a pointer
    table in the overlay program (gift reactions, random remarks: native code returns table[k] and the
    script runs call_v on it). The US kept the table and the subroutines as bare `16` (ret). Pair the
    Japanese table entries with the US ones (same layout, entries pointing at a ret in the US chunk);
    the plugin points each US entry at a snippet `30 1D a b 16`."""
    import re
    subs = {}
    for m in re.finditer(rb"0.{8}", jd, re.S):
        a, b = struct.unpack_from("<II", jd, m.start() + 2)
        if ((a >> 19) & 31) < 16 and (a >> 24) < 32 and (b & 0xFFFFF) > (a & 0x7FFFF):
            subs[jbase + m.start()] = (a, b)
    if not subs:
        return []
    jw = sorted((a, w) for a, w in overlay_words(jp, jovl, jbase).items() if w in subs)
    if not jw:
        return []
    uw = {a: w for a, w in overlay_words(us, uovl, ubase).items()
          if ubase <= w < ubase + len(ud) and ud[w - ubase] == 0x16}
    rel = [a - jw[0][0] for a, _ in jw]
    anchors = [A for A in sorted(uw) if all(A + r in uw for r in rel)]
    if len(anchors) != 1:
        print("  table: JP %d entries, %d US anchors - skipped" % (len(jw), len(anchors)))
        return []
    out = []
    for (ja, sub), r in zip(jw, rel):
        a, b = subs[sub]
        out.append(dict(kind="ptr", entry=anchors[0] + r, orig_ptr=uw[anchors[0] + r], a=a, b=b, jp_sub=sub))
    return out


US_DUNGEON = os.path.join(ROOT, r"extracted\DUNGEON\DUNGEON.BIN")
JP_DUNGEON = os.path.join(ROOT, r"extracted_jp\DUNGEON\DUNGEON.BIN")
DUNGEON_ROW = 0xFFFFFFFF          # chunk number of rows with absolute addresses (dungeon)
ALWAYS_ROW = 0xFFFFFFFE           # rows with absolute addresses checked everywhere (EXE, overlay programs)
US_EXE = os.path.join(ROOT, "extracted", "SLUS_006.14")
JP_EXE = os.path.join(ROOT, "extracted_jp", "SLPM_860.47")
# Voiced dungeon scripts: (name, US file range, its RAM address, JP file range, its RAM address,
# copies). The familiar talk lives in the dungeon module image (US DUNGEON.BIN 0x7D0800 is at
# 0x800F8000); Beldo's appearance is in species 55's code chunk, 7 copies linked for code slots
# k = 0..6 (12 sectors each, loaded to 0x80170800 - k*0x6000, re/NOTES.md -> Monster spawning).
DUNGEON_SCRIPTS = [
    ("familiar talk", (0x7D0800, 0x7D5000), 0x800F8000, (0x7D1000, 0x7D5800), 0x800FA000, 1),
    ("Beldo", (0x1271000, 0x1277000), 0x80170800, (0x1271800, 0x1277800), 0x80170800, 7),
]


def exe_ram(D, off):
    """RAM address of a PS-X EXE file offset (t_addr at header +0x18, text at file 0x800)."""
    return struct.unpack_from("<I", D, 0x18)[0] + off - 0x800


def region_sources(us, jp):
    """Script regions outside the town chunks: (name, US bytes, RAM, JP bytes, RAM, copies, row class).
    Copies (the Beldo chunk) sit 0x6000 apart on disc and 0x6000 lower in RAM per code slot."""
    U, J = open(US_DUNGEON, "rb").read(), open(JP_DUNGEON, "rb").read()
    out = []
    for name, (ulo, uhi), uram, (jlo, jhi), jram, copies in DUNGEON_SCRIPTS:
        out.append(("tower: " + name, U[ulo:uhi + (copies - 1) * 0x6000], uram, J[jlo:jhi], jram, copies,
                    DUNGEON_ROW, uhi - ulo))
    # gift reactions: scripts in the EXE (JP 0x3FF80.. ; US 0x3EA80..)
    UE, JE = open(US_EXE, "rb").read(), open(JP_EXE, "rb").read()
    for name, (ulo, uhi), (jlo, jhi) in EXE_SCRIPTS:
        out.append(("EXE: " + name, UE[ulo:uhi], exe_ram(UE, ulo), JE[jlo:jhi], exe_ram(JE, jlo), 1,
                    ALWAYS_ROW, uhi - ulo))
    # Kewne's item tips: the JP keeps them in the dungeon module (familiar talk), the US moved them into
    # the EXE; paired tip by tip (JP DUNGEON.BIN 0x7D1000 is at 0x800FA000)
    for name, (ulo, uhi), (jlo, jhi) in TIP_SCRIPTS:
        out.append(("EXE: " + name, UE[ulo:uhi], exe_ram(UE, ulo), J[jlo:jhi], 0x800FA000 + jlo - 0x7D1000, 1,
                    ALWAYS_ROW, uhi - ulo))
    # scripts inside location overlay programs (loaded at 0x80016000 with the location)
    uo, jo = us.overlays(), jp.overlays()
    for i in OVERLAY_SCRIPTS:
        ub = us.overlay_info(uo[i], (uo + [us.HI])[i + 1])[0]
        jb = jp.overlay_info(jo[i], (jo + [jp.HI])[i + 1])[0]
        uw = overlay_words(us, uo[i], ub[0] if ub else 0x8001DCD0)
        jw = overlay_words(jp, jo[i], jb[0] if jb else 0x8001DCD0)
        ud = b"".join(x.to_bytes(4, "little") for _, x in sorted(uw.items()))
        jd = b"".join(x.to_bytes(4, "little") for _, x in sorted(jw.items()))
        out.append(("overlay %d (JP %d)" % (uo[i], jo[i]), ud, OVL_BASE, jd, OVL_BASE, 1, ALWAYS_ROW, len(ud)))
    return out


# EXE script regions (US file range, JP file range): the gift reactions.
EXE_SCRIPTS = [("gift reactions", (0x3E900, 0x40400), (0x3FE00, 0x41400))]
# Kewne's tips the US moved from the dungeon module into the EXE: (name, US EXE file range, JP DUNGEON.BIN
# file range), each starting 4 bytes before the tip's first op (decoding starts at +4). Only the egg tip
# is voiced ("No problem. It's a dirty hovel, right?"); familiar talk drops its copy of that voice.
TIP_SCRIPTS = [("Kewne's egg tip", (0x437B3, 0x43BD9), (0x7D4305, 0x7D452B))]
# Location overlays (index in overlay order) whose program carries voiced scripts: Koh's house.
OVERLAY_SCRIPTS = [1]


def region_voices(us, jp, missing, overrides):
    """Voiced lines of the script regions outside the town chunks, as absolute-address rows."""
    out, report = [], []
    for name, U, uram, jd, jram, copies, row, ulen in region_sources(us, jp):
        ud = U[:ulen]
        vs, st = align_chunk(jd, jram, ud, uram)
        recover_lost(vs, st, jd, jram, ud, uram)
        ut = tokens(ud, uram)
        apply_overrides(vs, st, ut, overrides.get(name), name)
        prune_conts(vs, ut)
        for m in st["missing"]:
            m.update(where=name)
            missing.append(m)
        refs = references(ut)
        hooked = 0
        for v in vs:
            n = patch_span(ut, refs, v["us_text"])
            if not n:
                missing.append(dict(v, where=name,
                                    reason="cannot patch: " + patch_span_why(ut, refs, v["us_text"])))
                continue
            more = v.pop("more", [])
            w = box_wait(ut, v["us_text"]) if more else None
            if more and w is None:
                for m in more:
                    missing.append(dict(m, where=name, us_line=v["us_line"],
                                        reason="second voice of a box that does not end in a plain wait"))
            hooked += 1
            for k in range(copies):
                shift = k * 0x6000            # copy k: 0x6000 further on disc, 0x6000 lower in RAM
                o = v["us_text"] - uram
                ck = U[shift + o:shift + o + n]
                if ck != ud[o:o + n]:
                    continue
                c = dict(v, kind="text", us_lba=None, dungeon=name, base=0, number=row, orig=ck.hex(),
                         us_text=v["us_text"] - shift, cont=[x - shift for x in v["cont"]])
                if w is not None:
                    c["follow"] = [dict(a=m["a"], b=m["b"], wait=w - shift, jp_text=m["jp_text"],
                                        cont=[x - shift for x in m.get("cont", [])]) for m in more]
                out.append(c)
        st.update(name=name, hooked=hooked)
        report.append(st)
    return out, report


OUT_MISSING = os.path.join(ROOT, "re", "events", "voices_missing.md")


def write_missing(missing):
    """re/events/voices_missing.md: every Japanese voice that does not play yet, by cause and chunk."""
    by_reason = defaultdict(list)
    for m in missing:
        by_reason[m["reason"]].append(m)
    L = ["# Japanese voices not played yet", "",
         "Generated by `re/scripts/voice_port.py`. Each entry: where (US chunk lba / JP chunk lba), the",
         "address of the Japanese voice op, its stream args, the Japanese line, and the US text at or",
         "near that place.", "",
         "| Cause | Voices |", "|---|---|"]
    order = sorted(by_reason.items(), key=lambda kv: -len(kv[1]))
    for r, ms in order:
        L.append("| %s | %d |" % (r, len(ms)))
    L.append("| **total** | **%d** |" % len(missing))
    for r, ms in order:
        L += ["", "## %s (%d)" % (r, len(ms)), ""]
        for m in sorted(ms, key=lambda m: (m["where"], m.get("us_lba") or 0, m.get("jp_op") or 0)):
            where = m["where"]
            if m.get("us_lba"):
                where = "town %s (US %s)" % (m["jp_lba"], m["us_lba"])
            us = m.get("us_line") or " / ".join(t.replace("<end>", "").strip()[:30] for t in m.get("us_near", []))
            L.append("- %s · `%08x` %08x %08x · %s → US: %s" % (
                where, m.get("jp_op") or 0, m["a"], m["b"], m["jp_text"].strip()[:40], us.strip()[:70]))
    with open(OUT_MISSING, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def pair_chunks(us, jp, with_overlays=False):
    """[(us_lba, us_base, jp_lba, jp_base)] by overlay order and descriptor order (with the two
    overlays' lbas appended when with_overlays)."""
    uo, jo = us.overlays(), jp.overlays()
    pairs = []
    if len(uo) != len(jo):
        print("warning: overlay counts differ", len(uo), len(jo))
    for i in range(min(len(uo), len(jo))):
        ub, uc = us.overlay_info(uo[i], (uo + [us.HI])[i + 1])
        jb, jc = jp.overlay_info(jo[i], (jo + [jp.HI])[i + 1])
        for k in range(min(len(uc), len(jc))):
            p = (uc[k], ub[0] if ub else 0x8001DCD0, jc[k], jb[0] if jb else 0x8001DCD0)
            pairs.append(p + (uo[i], jo[i]) if with_overlays else p)
    return pairs


# Second pass for voices the first one loses: actor/face/sound/delay ops are often reordered between
# the releases (the US interleaves them with the speaker changes), so align on speaker, flow and flag
# ops only, and accept a voice only for a US page nobody voices yet whose speaker matches.
LOOSE_STRUCT_OPS = STRUCT_OPS - {0x0F, 0x1C, 0x53, 0x24, 0x25, 0x26, 0x27, 0x12, 0x13, 0x1E}
SPEAKER_OPS = {0x57}      # last resort: speaker changes only (routines whose choices were rewritten)


def sentence_end(t):
    """The US line ends a sentence (so the next one starts one)."""
    t = visible(t).rstrip().rstrip("”’\"')")
    return t.endswith((".", "!", "?"))


def split_lines(v):
    """Several Japanese voices on one US box: JP plays them in sequence (the second `stream` op waits
    for the first voice), its text appearing as each one starts. Put each later voice on the US line
    of the box where its share of the text begins, as a line of its own; voices that would land on
    the same line as the previous one stay follow-ups. Returns the new line rows."""
    lines = v.get("lines") or []
    if not v["more"] or len(lines) < 2:
        return []
    voices = [v] + v["more"]
    total_j = float(sum(max(1, x.get("jp_chars", 1)) for x in voices))
    total_u = float(sum(max(1, n) for _, n, _ in lines))
    ucum, c = [], 0.0
    for _, n, _ in lines:
        ucum.append(c / total_u)
        c += max(1, n)
    out, keep, jc, last = [], [], 0.0, 0
    for k, m in enumerate(voices):
        if k == 0:
            jc += max(1, m.get("jp_chars", 1))
            continue
        frac = jc / total_j
        jc += max(1, m.get("jp_chars", 1))
        j = max(i for i in range(len(lines)) if ucum[i] <= frac + 1e-9)
        if frac - ucum[j] > 0.5 * ((ucum[j + 1] if j + 1 < len(lines) else 1.0) - ucum[j]) and j + 1 < len(lines):
            j += 1                        # nearer the next line's start
        if j <= last and m.get("box"):       # a new JP box: the next line that starts a sentence
            j = next((i for i in range(last + 1, len(lines)) if sentence_end(lines[i - 1][2])), j)
        if j <= last:
            keep.append(m)
            continue
        last = j
        a, _, text = lines[j]
        out.append(dict(m, us_text=a, us_line=text, us_speaker=v.get("us_speaker"), wait=v["wait"], more=[],
                        cont=list(m.get("cont", [])), lines=[], line_split=True))
    v["more"] = keep
    return out


def recover_lost(vs, st, jd, jbase, ud, ubase):
    """Add voices lost by the first alignment that the loose one places on a free US page with the
    same speaker (or a speaker pair the first alignment already pairs in this chunk). Returns the
    number recovered; recovered voices leave st["missing"]."""
    total = 0
    for ops in (LOOSE_STRUCT_OPS, SPEAKER_OPS):
        total += recover_pass(vs, st, jd, jbase, ud, ubase, ops)
    st["recovered"] = total
    return total


def recover_pass(vs, st, jd, jbase, ud, ubase, struct_ops):
    if not st["missing"]:
        return 0
    pairs_ok = {(v["jp_speaker"], v["us_speaker"]) for v in vs}
    used = {v["us_text"] for v in vs}
    vs2, _ = align_chunk(jd, jbase, ud, ubase, struct_ops)
    place = {}
    for v in vs2:
        place[v["jp_op"]] = (v, v)
        for m in v["more"]:
            place[m["jp_op"]] = (v, m)
    added, keep = {}, []
    for m in st["missing"]:
        hit = place.get(m["jp_op"])
        if hit is None:
            keep.append(m)
            continue
        v2, src = hit
        same = m.get("jp_speaker") == v2["us_speaker"] or (m.get("jp_speaker"), v2["us_speaker"]) in pairs_ok
        if v2["us_text"] in used or not same:
            keep.append(m)
            continue
        voice = dict(a=m["a"], b=m["b"], jp_text=m["jp_text"], jp_op=m["jp_op"], jp_speaker=m.get("jp_speaker"),
                     cont=list(src.get("cont", [])))
        if v2["us_text"] not in added:
            added[v2["us_text"]] = dict(voice, us_text=v2["us_text"], us_line=v2["us_line"], recovered=True,
                                        us_speaker=v2["us_speaker"], wait=v2["wait"], more=[])
        else:
            added[v2["us_text"]]["more"].append(voice)
    vs.extend(added.values())
    vs.sort(key=lambda v: v["us_text"])
    n = len(st["missing"]) - len(keep)
    st["missing"] = keep
    st["lost"] -= n
    st["mapped"] += len(added)
    return n


OVERRIDES = os.path.join(ROOT, "re", "events", "voice_overrides.toml")


def load_overrides():
    """re/events/voice_overrides.toml: [[voice]] source = "town 7335" | region name, jp_op = "8001xxxx",
    us = text prefix or "0x8001xxxx", as = "line" (default) | "follow" | "drop"."""
    import tomllib
    if not os.path.exists(OVERRIDES):
        return {}
    out = defaultdict(list)
    with open(OVERRIDES, "rb") as f:
        for o in tomllib.load(f).get("voice", []):
            out[o["source"]].append(o)
    return out


def us_line_at(ut, us):
    """US text address for an override target: "0x..." or the first text starting with that prefix."""
    if us.lower().startswith("0x"):
        return int(us, 16)
    want = us.replace("’", "'").strip()
    for op, a, ins in ut:
        if ins["name"] == "text" and visible(ins["text"]).replace("’", "'").startswith(want):
            return a
    return None


def apply_overrides(vs, st, ut, overrides, source):
    """Move, add or drop voices as the overrides say. vs: align_chunk output (primaries with `more`)."""
    if not overrides:
        return
    # flatten: jp_op -> (voice, page address); pages keep their continuation waits
    voices, page_of, page_info = {}, {}, {}
    for v in vs:
        page_info[v["us_text"]] = (v["us_line"], v.get("us_speaker"), v["wait"])
        for m in [v] + v["more"]:
            voices[m["jp_op"]] = dict((k, m[k]) for k in ("a", "b", "jp_text", "jp_op") if k in m)
            voices[m["jp_op"]]["jp_speaker"] = m.get("jp_speaker")
            voices[m["jp_op"]]["cont"] = list(m.get("cont", []))
            page_of[m["jp_op"]] = v["us_text"]
    lost = {m["jp_op"]: m for m in st["missing"]}
    roles = {}
    for o in overrides:
        jop = int(o["jp_op"], 16)
        voice = voices.get(jop) or (dict((k, lost[jop][k]) for k in ("a", "b", "jp_text", "jp_op"))
                                    if jop in lost else None)
        if voice is None:
            print("  override %s %s: no such voice" % (source, o["jp_op"]))
            continue
        lost.pop(jop, None)
        page_of.pop(jop, None)
        if o.get("as", "line") == "drop":
            voices.pop(jop, None)
            continue
        addr = us_line_at(ut, o["us"])
        if addr is None:
            print("  override %s %s: US line %r not found" % (source, o["jp_op"], o["us"]))
            continue
        voices[jop] = dict(voice, cont=waits_after(ut, addr, int(o.get("through", 0))))
        page_of[jop] = addr
        roles[jop] = o.get("as", "line")
        if addr not in page_info:
            text = next(ins["text"] for op, a, ins in ut if a == addr)
            page_info[addr] = (text, None, box_wait(ut, addr))
    st["missing"] = list(lost.values())
    st["lost"] = len(st["missing"])
    st["dropped_by_override"] = sum(1 for o in overrides if o.get("as") == "drop")
    by_page = defaultdict(list)
    for jop, addr in page_of.items():
        by_page[addr].append(jop)
    new = []
    for addr, jops in by_page.items():
        jops.sort(key=lambda j: (roles.get(j) == "follow", j))
        first = voices[jops[0]]
        line, spk, wait = page_info[addr]
        new.append(dict(first, us_text=addr, us_line=line, us_speaker=spk, wait=wait,
                        more=[voices[j] for j in jops[1:]], override=any(j in roles for j in jops)))
    new.sort(key=lambda v: v["us_text"])
    vs[:] = new
    st["mapped"] = len(new)


def next_text(ut, wait):
    """Address of the first US text the script shows after the button wait at `wait`."""
    idx = next((i for i, t in enumerate(ut) if t[1] == wait), None)
    if idx is None:
        return None
    for op, a, ins in ut[idx + 1:idx + 40]:
        if ins["name"] == "text" and not ins["junk"] and us_text_ok(ins["text"]):
            return a
        if op in (0x01, 0x16, 0x17, 0x18, 0x48):
            return None
    return None


def waits_after(ut, addr, n):
    """The first n button waits after the line at addr (an override's `through = n`)."""
    idx = next((i for i, t in enumerate(ut) if t[1] == addr), None)
    out = []
    if idx is None or n <= 0:
        return out
    for op, a, ins in ut[idx:idx + 200]:
        if ins["junk"]:
            continue
        if op == 0x11:
            out.append(a)
            if len(out) == n:
                break
        elif op in BOX_FLOW:
            break
    return out


def prune_conts(vs, ut):
    """Drop continuation waits right before a voiced line (its `stream` op would wait for the old voice
    to end before the box even shows): returns the pruned count."""
    voiced = {v["us_text"] for v in vs}
    n = 0
    for v in vs:
        for m in [v] + v.get("more", []):
            keep = [w for w in m.get("cont", []) if next_text(ut, w) not in voiced]
            n += len(m.get("cont", [])) - len(keep)
            m["cont"] = keep
    return n


BOX_FLOW = {0x01, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x2A, 0x2B, 0x2C, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x48,
            0x4B, 0x57}


def box_wait(ut, text_addr):
    """Address of the button-wait op (0x11) that ends the box starting at text_addr, or None when the
    box does not end in a plain wait (a branch, call or speaker change first)."""
    idx = next((i for i, t in enumerate(ut) if t[1] == text_addr), None)
    if idx is None:
        return None
    for op, a, ins in ut[idx:idx + 40]:
        if ins["junk"] or op in BOX_FLOW:
            return None
        if op == 0x11:
            return a
    return None


def snippet(v):
    """Text row: `30 1D a b <displaced bytes> 17 back` - yield, stream request (as the Japanese scripts
    do right before a voiced line), the line itself, and back to the bytes after it.
    Table row: `30 1D a b 16` - the Japanese voice subroutine.
    Follow-up row: `1D a b 17 wait` - the next voice of a joined box, then back to its button wait."""
    if v["kind"] == "more":
        return bytes([0x1D]) + struct.pack("<II", v["a"], v["b"]) + b"\x17" + struct.pack("<I", v["wait"])
    head = bytes([0x30, 0x1D]) + struct.pack("<II", v["a"], v["b"])
    if v["kind"] == "ptr":
        return head + b"\x16"
    return head + bytes.fromhex(v["orig"]) + b"\x17" + struct.pack("<I", v["us_text"] + len(v["orig"]) // 2)


def write_header(voices):
    """C table for the plugin: rows sorted by (chunk number, address) plus the snippet blob."""
    def addr(v):
        return v["us_text"] if v["kind"] == "text" else v["entry"]
    rows = []
    for v in sorted(voices, key=lambda v: (v["number"], addr(v))):
        rows.append(v)
        fl = [dict(m, kind="more", number=v["number"], base=v["base"], parent=v, first=k == 0)
              for k, m in enumerate(v.get("follow", []))]
        rows += fl
        for p in [v] + fl:
            for w in p.get("cont", []):
                rows.append(dict(kind="cont", number=v["number"], base=v["base"], wait=w, parent=p))
    blob = bytearray()
    for v in rows:
        if v["kind"] == "cont":
            continue
        v["snip"] = len(blob)
        blob += snippet(v)
        v["snip_len"] = len(blob) - v["snip"]
        blob += bytes(-len(blob) % 4)
    # a continuation wait that a short line's patch moved into its snippet (`<player>.` + wait): the VM
    # waits at the snippet's copy of it
    spans = defaultdict(list)
    for v in rows:
        if v["kind"] == "text":
            spans[(v["number"], v["base"], v.get("us_lba"), v.get("dungeon"))].append(v)
    for v in rows:
        if v["kind"] != "cont":
            continue
        p = v["parent"]
        while p.get("kind") == "more":
            p = p["parent"]
        for t in spans[(p["number"], p["base"], p.get("us_lba"), p.get("dungeon"))]:
            n = len(t["orig"]) // 2
            if t["us_text"] <= v["wait"] < t["us_text"] + n:
                v["in_snip"] = t["snip"] + 10 + (v["wait"] - t["us_text"]) + 1
    lines = ["/* Generated by re/scripts/voice_port.py - do not edit. Japanese voice ops mapped onto the US",
             " * town scripts. Row: chunk number (first word of the loaded chunk), its load base, the address",
             " * to patch, the snippet's offset in VOICE_SNIPPETS, and",
             " *   kind 0 (a voiced line): how many bytes at addr the plugin replaces with `17 snippet`",
             " *          (snippet: `30 1D a b`, the replaced bytes, `17 addr+len`);",
             " *   kind 1 (a voice clip picked through an overlay pointer table): the table entry's US value",
             " *          (a bare `16`), replaced with the snippet's address (snippet: `30 1D a b 16`);",
             " *   kind 2 (the next voice of a US box that joins several Japanese boxes; follows its line's",
             " *          row): addr = the VM pointer while it waits at the box's button wait, orig/len =",
             " *          the line's snippet (first follow-up) or 0/0 (a later one); snippet:",
             " *          `1D a b 17 wait`, run once the previous voice has played;",
             " *   kind 3 (a button wait inside one Japanese voice that the US split into several boxes):",
             " *          addr = the VM pointer while it waits there, orig/len = the snippet of the voice",
             " *          (its line's, or a follow-up's); while",
             " *          that voice plays, the wait is switched to one that does not stop it;",
             " *   kind 4 (the same, for a wait that a short line's patch moved into a snippet): addr = the",
             " *          VM pointer's offset in VOICE_SNIPPETS while it waits at the snippet's copy. */",
             "#pragma once", "#include <stdint.h>", "",
             "typedef struct { uint32_t number, base, addr, snip, orig; uint16_t len; uint8_t kind; } VoiceRow;",
             "static const VoiceRow VOICE_ROWS[%d] = {" % len(rows)]
    for v in rows:
        if v["kind"] == "text":
            lines.append("    { %du, 0x%08Xu, 0x%08Xu, %du, 0u, %d, 0 }," % (
                v["number"], v["base"], v["us_text"], v["snip"], len(v["orig"]) // 2))
        elif v["kind"] == "ptr":
            lines.append("    { %du, 0x%08Xu, 0x%08Xu, %du, 0x%08Xu, 0, 1 }," % (
                v["number"], v["base"], v["entry"], v["snip"], v["orig_ptr"]))
        elif v["kind"] == "cont" and "in_snip" in v:
            lines.append("    { %du, 0x%08Xu, %du, 0u, %du, %d, 4 }," % (
                v["number"], v["base"], v["in_snip"], v["parent"]["snip"], v["parent"]["snip_len"]))
        elif v["kind"] == "cont":
            lines.append("    { %du, 0x%08Xu, 0x%08Xu, 0u, %du, %d, 3 }," % (
                v["number"], v["base"], v["wait"] + 1, v["parent"]["snip"], v["parent"]["snip_len"]))
        else:
            lines.append("    { %du, 0x%08Xu, 0x%08Xu, %du, %du, %d, 2 }," % (
                v["number"], v["base"], v["wait"] + 1, v["snip"], v["parent"]["snip"] if v["first"] else 0,
                v["parent"]["snip_len"] if v["first"] else 0))
    lines.append("};")
    lines.append("#define VOICE_ROW_COUNT %du" % len(rows))
    lines.append("")
    lines.append("static const uint8_t VOICE_SNIPPETS[%d] = {" % len(blob))
    for k in range(0, len(blob), 24):
        lines.append("    " + ",".join("0x%02X" % x for x in blob[k:k + 24]) + ",")
    lines.append("};")
    with open(OUT_H, "w", encoding="ascii") as f:
        f.write("\n".join(lines) + "\n")
    return len(blob)


def main():
    us, jp = Town(US_TOWN, US_LBA), Town(JP_TOWN, JP_LBA)
    pairs = pair_chunks(us, jp, with_overlays=True)
    ustarts, jstarts = us.starts(), jp.starts()
    allv, report, skipped, missing = [], [], [], []
    overrides = load_overrides()
    for ul, ubase, jl, jbase, uovl, jovl in pairs:
        unext = min([s for s in ustarts if s > ul] + [ul + 16])
        jnext = min([s for s in jstarts if s > jl] + [jl + 16])
        ud, jd = us.chunk_bytes(ul, unext), jp.chunk_bytes(jl, jnext)
        num_u, num_j = us.u32((ul - us.LO) * 2048), jp.u32((jl - jp.LO) * 2048)
        register_entries(ud, ubase, overlay_pointers(us, uovl, ubase))
        register_entries(jd, jbase, overlay_pointers(jp, jovl, jbase))
        vs, st = align_chunk(jd, jbase, ud, ubase)
        recover_lost(vs, st, jd, jbase, ud, ubase)
        ut = tokens(ud, ubase)
        apply_overrides(vs, st, ut, overrides.get("town %d" % jl), "town %d" % jl)
        prune_conts(vs, ut)
        refs = references(ut)
        hooked = followed = conts = 0
        for m in st["missing"]:
            m.update(where="town", us_lba=ul, jp_lba=jl)
            missing.append(m)
        for v in vs:
            n = patch_span(ut, refs, v["us_text"])
            if not n:
                missing.append(dict(v, where="town", us_lba=ul, jp_lba=jl,
                                    reason="cannot patch: " + patch_span_why(ut, refs, v["us_text"])))
                for m in v.get("more", []):
                    missing.append(dict(m, where="town", us_lba=ul, jp_lba=jl, us_line=v["us_line"],
                                        reason="follow-up of a line that cannot be patched"))
                continue
            o = v["us_text"] - ubase
            v.update(kind="text", us_lba=ul, base=ubase, number=num_u, orig=ud[o:o + n].hex())
            more = v.pop("more", [])
            conts += len(v["cont"])
            w = box_wait(ut, v["us_text"]) if more else None
            if w is not None:
                v["follow"] = [dict(a=m["a"], b=m["b"], wait=w, jp_text=m["jp_text"], cont=m.get("cont", []))
                               for m in more]
                conts += sum(len(m.get("cont", [])) for m in more)
                followed += len(more)
            else:
                for m in more:
                    missing.append(dict(m, where="town", us_lba=ul, jp_lba=jl, us_line=v["us_line"],
                                        reason="second voice of a box that does not end in a plain wait"))
            allv.append(v)
            hooked += 1
        tv = table_voices(us, jp, uovl, jovl, ubase, ud, jbase, jd)
        for v in tv:
            v.update(us_lba=ul, base=ubase, number=num_u)
            allv.append(v)
        st.update(us_lba=ul, jp_lba=jl, base="%08x" % ubase, number=num_u, jp_number=num_j, hooked=hooked,
                  table=len(tv), followed=followed, conts=conts)
        report.append(st)
    dv, dreport = region_voices(us, jp, missing, overrides)
    allv += dv
    write_missing(missing)
    for r in dreport:
        print("  %-28s voices %d -> %d lines, %d follow-ups, %d dropped (no US text), %d lost" % (
            r["name"], r["jp_voices"], r["hooked"], r["jp_voices"] - r["hooked"] - r["lost"] -
            r.get("dropped_by_override", 0), r.get("dropped_by_override", 0), r["lost"]))
    for v in allv:
        v.pop("lines", None)
    json.dump(dict(chunks=report, dungeon=dreport, voices=allv, skipped=skipped), open(OUT_JSON, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    blob = write_header(allv)
    tot_j = sum(r["jp_voices"] for r in report)
    print("recovered by the second/third alignment pass: %d; dropped by voice_overrides.toml (no US text): %d"
          % (sum(r.get("recovered", 0) for r in report + dreport),
             sum(r.get("dropped_by_override", 0) for r in report + dreport)))
    print("pairs %d, Japanese voiced lines %d: %d hooked, %d more in joined boxes (of %d), %d kept playing"
          " through split boxes; %d table clips; unhookable %d, lost in alignment %d;"
          " snippets %d bytes" % (
              len(pairs), tot_j, sum(r["hooked"] for r in report), sum(r["followed"] for r in report),
              sum(r["dropped"] for r in report), sum(r["conts"] for r in report), sum(r["table"] for r in report),
              sum(r["mapped"] - r["hooked"] for r in report),
              sum(r["lost"] for r in report), blob))
    for r in report:
        if r["jp_voices"]:
            print("  US %d / JP %d  ratio %.2f  voices %d -> %d mapped, %d hooked, %d table (lost %d)" % (
                r["us_lba"], r["jp_lba"], r["ratio"], r["jp_voices"], r["mapped"], r["hooked"], r["table"],
                r["lost"]))


if __name__ == "__main__":
    main()
