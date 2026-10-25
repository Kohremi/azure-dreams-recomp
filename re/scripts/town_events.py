"""Catalog every town event: locations (overlays), their script chunks, blocks, speakers, text and
story flags (set / cleared / tested), both in the bytecode and in the overlays' native helpers.

Town structure (see re/NOTES.md -> Town events):
  * A location is an overlay program in TOWN.BIN loaded at 0x80016000; header {0, 0x4C070707, entry, 1}.
  * Each overlay lists its script chunks as {u32 size (filled at runtime), u32 lba} descriptors and sets
    the script load base (API struct +0x2C); chunks run from that base, absolute addresses inside.
  * Every overlay carries three flag helpers (set / clear / test on the bit array at *(API+0x18)) that
    native story logic calls with constant flag numbers; scripts reach that logic with op 0x4C.

Outputs (re/events/):
  chunks/<lba>.txt   annotated disassembly per script chunk
  town_events.json   locations -> chunks -> blocks, plus a flag index
  flags.txt          every flag: where it is set / cleared / tested, with speaker and a line
"""
import json, os, struct, sys
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(__file__))
import town_script_dis as tsd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
OUT = os.path.join(ROOT, r"re\events")
D = open(tsd.TOWN, "rb").read()
LO, HI = tsd.TOWN_LBA, tsd.TOWN_LBA + len(D) // 2048
EXE = open(os.path.join(ROOT, r"extracted\SLUS_006.14"), "rb").read()
EXE_T = 0x8002D000
OVL_BASE = 0x80016000

FLAG_FNS = {0x80033AA8: "set", 0x80033B9C: "set", 0x80033AE8: "clr", 0x80033B78: "clr", 0x80033B2C: "test"}
HELPER_SIGS = {"set": [0x1080001B, 0x3C028001, 0x8C426000, 0x04810002],
               "clr": [0x24020001, 0x1082001C, 0x3C028001, 0x8C426000, 0x04810002],
               "test": [0x10800018, 0x24020001, 0x10820014, 0x3C028001, 0x8C436000]}


def exe_cstr(a):
    o = 0x800 + a - EXE_T
    return EXE[o:EXE.index(b"\0", o)].decode("cp932")


def speaker_names():
    import unicodedata
    names = {}
    for i in range(80):
        p = struct.unpack_from("<I", EXE, 0x800 + 0x8006AC68 - EXE_T + 4 * i)[0]
        if not 0x80000000 <= p < 0x80200000:
            break
        names[i + 3] = unicodedata.normalize("NFKC", exe_cstr(p))
    names[1] = "Koh"
    names[2] = "Kewne"
    return names


NAMES = speaker_names()
GIRLS = {"Weedy": 5, "Selfi": 7, "Patty": 8, "Fur": 9, "Mia": 10, "Nico": 11, "Vivian": 12, "Cherrl": 13}


def resolver(addr):
    """Text fragments outside the chunk: EXE strings."""
    if EXE_T <= addr < EXE_T + len(EXE) - 0x800:
        o = 0x800 + addr - EXE_T
        return EXE[o:o + 0x400]
    return None


def words(blob):
    n = len(blob) // 4
    return struct.unpack("<%dI" % n, blob[:n * 4])


def sx16(x):
    return x - 0x10000 if x & 0x8000 else x


def a0_imm(W, i):
    """Constant in a0 for the jal at index i: the delay slot if it writes a0, else the nearest
    earlier instruction that writes a0 (must be li/ori a0,zero,imm), stopping at branches/calls."""
    def writes_a0(x):
        op = x >> 26
        if op in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x20, 0x21, 0x23, 0x24, 0x25, 0x22, 0x26):
            return (x >> 16) & 31 == 4
        if op == 0 and x != 0:
            return (x >> 11) & 31 == 4
        return False
    if i + 1 < len(W) and writes_a0(W[i + 1]):
        x = W[i + 1]
        return x & 0xFFFF if x >> 16 in (0x2404, 0x3404) else None
    for j in range(i - 1, max(-1, i - 8), -1):
        x = W[j]
        op = x >> 26
        if op in (2, 3, 4, 5, 6, 7, 1) or (op == 0 and (x & 0x3F) in (8, 9)):
            return None
        if writes_a0(x):
            return x & 0xFFFF if x >> 16 in (0x2404, 0x3404) else None
    return None


# ---------------------------------------------------------------- overlays

def find_overlays():
    """All location overlay programs: list of lba (header {0, 0x4C070707, entry, 1})."""
    out = []
    for s in range(0, len(D), 2048):
        w0, w1, w2, w3 = struct.unpack_from("<4I", D, s)
        if w0 == 0 and w1 == 0x4C070707 and w3 == 1:
            out.append(s // 2048 + LO)
    return out


def is_script(lba):
    if not LO <= lba < HI:
        return False
    o = (lba - LO) * 2048
    w = struct.unpack_from("<I", D, o)[0]
    return 1 <= w < 0x100 and D[o + 4] != 0


class Overlay:
    def __init__(self, lba, nxt):
        self.lba = lba
        o = (lba - LO) * 2048
        self.data = D[o:min((nxt - LO) * 2048, o + 0x14000)]
        self.w = words(self.data)
        self.helpers = self._helpers()
        self.bases = self._bases()
        self.chunks = self._descriptors()
        self.funcs = self._functions()

    def _helpers(self):
        h = {}
        for kind, sig in HELPER_SIGS.items():
            for i in range(len(self.w) - len(sig)):
                if list(self.w[i:i + len(sig)]) == sig:
                    h[OVL_BASE + 4 * i] = kind
                    break
        return h

    def _bases(self):
        """Script load bases: `lui r,hi; addiu r,r,lo; sw r,44(x)` (API struct +0x2C)."""
        found = []
        W = self.w
        for i, w in enumerate(W):
            if w >> 26 == 0x2B and w & 0xFFFF == 44:
                rt = (w >> 16) & 31
                lo = hi = None
                for j in range(i - 1, max(0, i - 6), -1):
                    x = W[j]
                    if x >> 26 == 9 and (x >> 16) & 31 == rt and lo is None:
                        lo = sx16(x & 0xFFFF)
                    if x >> 26 == 0xF and (x >> 16) & 31 == rt:
                        hi = x & 0xFFFF
                        break
                if lo is not None and hi is not None:
                    found.append(((hi << 16) + lo) & 0xFFFFFFFF)
        return found

    def _descriptors(self):
        out = []
        k = 0
        while k + 8 <= len(self.data):
            z, l = struct.unpack_from("<II", self.data, k)
            if z == 0 and is_script(l):
                if l not in out:
                    out.append(l)
                k += 8
            else:
                k += 4
        return out

    def _functions(self):
        """Native function address -> {'set': [...], 'clr': [...], 'test': [...]} via helper calls."""
        W = self.w
        funcs = {}
        start = 0
        for i, w in enumerate(W):
            if (w >> 16) == 0x27BD and w & 0x8000 and (i == 0 or W[i - 1] == 0 or W[i - 2] == 0x03E00008):
                start = i                       # addiu sp,sp,-N after a return: new function
            if w >> 26 == 3:
                tgt = 0x80000000 | ((w & 0x3FFFFFF) << 2)
                kind = self.helpers.get(tgt) or FLAG_FNS.get(tgt)
                if not kind:
                    continue
                imm = a0_imm(W, i)
                if imm is not None:
                    f = funcs.setdefault(OVL_BASE + 4 * start, dict(set=[], clr=[], test=[]))
                    if imm not in f[kind]:
                        f[kind].append(imm)
        return funcs

    def func_containing(self, addr):
        best = None
        for a in self.funcs:
            if a <= addr and (best is None or a > best):
                best = a
        return best if best is not None and addr - best < 0x400 else None


# ---------------------------------------------------------------- chunks

def _zero_tail_end(o, s, limit):
    """End (bytes from o) of the first sector >= s whose last 48 bytes are zero, trailing zeros trimmed."""
    while s < limit:
        sec = D[o + s * 2048:o + (s + 1) * 2048]
        if sec[-48:] == bytes(48):
            e = len(sec)
            while e > 0 and sec[e - 1] == 0:
                e -= 1
            return s * 2048 + e
        s += 1
    return limit * 2048


def _refs(listing):
    refs = []
    for a, ins in listing:
        op = ins.get("op")
        if op in (0x15, 0x17, 0x4C):
            refs.append(ins["args"][0])
        elif op in (0x18, 0x2B, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43):
            refs.append(ins["args"][1])
        elif op == 0x1A:
            refs += ins.get("targets", [])
    return refs


def chunk_bytes(lba, base, all_starts):
    """A chunk ends at a zero-padded sector; extend past one while the decoded part references
    addresses further on (scripts can have zero-tailed sectors in the middle)."""
    o = (lba - LO) * 2048
    limit = min([s for s in all_starts if s > lba] + [lba + 16]) - lba
    end = _zero_tail_end(o, 0, limit)
    while True:
        data = D[o:o + end]
        ch = tsd.Chunk(data, base, resolver)
        listing = tsd.disasm_linear(ch, base + 4, base + len(data), tsd.mips_ranges(ch))
        far = [r - base for r in _refs(listing) if end <= r - base < limit * 2048]
        if not far:
            break
        new_end = _zero_tail_end(o, max(far) // 2048, limit)
        if new_end <= end:
            new_end = _zero_tail_end(o, end // 2048 + 1, limit)
        if new_end <= end:
            break
        end = new_end
    return D[o:o + end + (-end % 4)]


def pick_base(lba, bases, all_starts):
    """Of an overlay's script bases, the one under which the chunk's jump targets hit instruction starts."""
    if len(bases) == 1:
        return bases[0]
    best, score = bases[0], -1
    for b in bases:
        data = chunk_bytes(lba, b, all_starts)
        ch = tsd.Chunk(data, b)
        lst = tsd.disasm_linear(ch, b + 4, b + len(data), tsd.mips_ranges(ch))
        starts = {a for a, _ in lst}
        n = sum(1 for r in _refs(lst) if r in starts)
        if n > score:
            best, score = b, n
    return best


def location_name(chunk_infos):
    c = Counter()
    for ci in chunk_infos:
        for b in ci["blocks"]:
            for s in b["speakers"]:
                if s not in ("Koh", "Narrat", "Kewne"):
                    c[s] += len(b["text"])
    return "/".join(n for n, _ in c.most_common(3)) or "?"


def build():
    ovl_lbas = find_overlays()
    ovls = [Overlay(l, (ovl_lbas + [HI])[i + 1]) for i, l in enumerate(ovl_lbas)]
    chunk_owner = {}
    for ov in ovls:
        for c in ov.chunks:
            chunk_owner.setdefault(c, ov)
    all_starts = sorted(set(ovl_lbas) | set(chunk_owner))
    os.makedirs(os.path.join(OUT, "chunks"), exist_ok=True)
    flag_ix = defaultdict(lambda: dict(set=[], clr=[], test=[]))
    catalog = dict(locations=[], chunks=[])
    chunk_infos = {}
    for lba in sorted(chunk_owner):
        ov = chunk_owner[lba]
        base = pick_base(lba, ov.bases or [0x8001DCD0], all_starts)
        data = chunk_bytes(lba, base, all_starts)
        ch = tsd.Chunk(data, base, resolver)
        nat = tsd.mips_ranges(ch)
        listing = tsd.disasm_linear(ch, base + 4, base + len(data), nat)
        targets = {base + 4}
        prev_term = False
        for a, ins in listing:
            if prev_term:
                targets.add(a)
            targets.update(r for r in _refs([(a, ins)]) if ch.inside(r) and ins.get("op") != 0x4C)
            op = ins.get("op")
            prev_term = op in tsd.STOPS or (ins["name"] == "text" and ins["text"].endswith("<end>"))
        blocks, cur, lines, speaker = [], None, [], None
        for a, ins in listing:
            if a in targets or cur is None:
                cur = dict(addr="%08x" % a, speakers=[], actors=[], set=[], clr=[], test=[],
                           natives=[], native_flags=dict(set=[], clr=[], test=[]), text=[])
                blocks.append(cur)
                lines += ["", "@%08x:" % a]
            op = ins.get("op")
            note = ""
            if op == 0x57:
                speaker = ins["args"][0]
                nm = NAMES.get(speaker, "#%d" % speaker) if speaker else "-"
                if speaker and nm not in cur["speakers"]:
                    cur["speakers"].append(nm)
                note = "   ; " + nm
            elif op == 0x0F and ins["args"][0]:
                nm = NAMES.get(ins["args"][0], "#%d" % ins["args"][0])
                if nm not in cur["actors"]:
                    cur["actors"].append(nm)
                note = "   ; " + nm
            elif op in (0x0C, 0x0D):
                cur["set" if op == 0x0C else "clr"].append(ins["args"][0])
            elif op in (0x18, 0x2B):
                cur["test"].append(ins["args"][0])
            elif op == 0x4C:
                t = ins["args"][0]
                cur["natives"].append("%08x" % t)
                fa = ov.func_containing(t) if t < base else None
                if fa is not None and fa == t or (fa is not None and t - fa < 8):
                    fl = ov.funcs[fa]
                    for k in ("set", "clr", "test"):
                        cur["native_flags"][k] += [f for f in fl[k] if f not in cur["native_flags"][k]]
                    note = "   ; " + " ".join("%s %s" % (k, ",".join(map(str, fl[k]))) for k in ("test", "set", "clr") if fl[k])
            elif op == 0x2E:
                cur["natives"].append("ovl[%d]" % ins["args"][0])
            elif ins["name"] == "text":
                spk = NAMES.get(speaker, "") if speaker else ""
                cur["text"].append((spk + ": " if spk else "") + ins["text"].replace("<end>", ""))
            if ins["name"] == "mips":
                lines.append("%08x  <mips %d bytes>" % (a, ins["size"]))
            else:
                lines.append("%08x  %s%s" % (a, tsd.fmt(ins), note))
        for b in blocks:
            line = next((t for t in b["text"] if t.strip()), "")
            for k in ("set", "clr", "test"):
                for f in b[k]:
                    flag_ix[f][k].append(dict(chunk=lba, block=b["addr"], via="script", speakers=b["speakers"], line=line))
                for f in b["native_flags"][k]:
                    flag_ix[f][k].append(dict(chunk=lba, block=b["addr"], via="native", speakers=b["speakers"], line=line))
        info = dict(lba=lba, town_offset="0x%06X" % ((lba - LO) * 2048), number=ch.u32(base), base="%08x" % base,
                    size=len(data), location=ov.lba, mips=["%08x-%08x" % r for r in nat],
                    blocks=[b for b in blocks if b["text"] or b["set"] or b["clr"] or b["test"]
                            or any(b["native_flags"].values())])
        chunk_infos[lba] = info
        catalog["chunks"].append(info)
        hdr = "; chunk lba %d (TOWN+%06X) number %d size %d base %08x, location overlay lba %d" % (
            lba, (lba - LO) * 2048, ch.u32(base), len(data), base, ov.lba)
        with open(os.path.join(OUT, "chunks", "%d.txt" % lba), "w", encoding="utf-8") as f:
            f.write(hdr + "\n" + "\n".join(lines) + "\n")
    for ov in ovls:
        cis = [chunk_infos[c] for c in ov.chunks if chunk_owner.get(c) is ov]
        # native flag use not reached from any script (spawn conditions etc.)
        for fa, fl in ov.funcs.items():
            for k in ("set", "clr", "test"):
                for f in fl[k]:
                    if not any(u["via"] == "native" and chunk_owner.get(u["chunk"]) is ov for u in flag_ix[f][k]):
                        flag_ix[f][k].append(dict(chunk=None, location=ov.lba, block="fn %08x" % fa,
                                                  via="overlay", speakers=[], line=""))
        catalog["locations"].append(dict(lba=ov.lba, town_offset="0x%06X" % ((ov.lba - LO) * 2048),
                                         name=location_name(cis), script_bases=["%08x" % b for b in ov.bases],
                                         helpers={k: "%08x" % a for a, k in ov.helpers.items()},
                                         chunks=ov.chunks,
                                         functions={"%08x" % a: v for a, v in sorted(ov.funcs.items())}))
    catalog["flags"] = {str(k): v for k, v in sorted(flag_ix.items())}
    with open(os.path.join(OUT, "town_events.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=1, ensure_ascii=False)
    loc_name = {l["lba"]: l["name"] for l in catalog["locations"]}
    with open(os.path.join(OUT, "flags.txt"), "w", encoding="utf-8") as f:
        for k, v in sorted(flag_ix.items()):
            f.write("flag %d\n" % k)
            for kind in ("set", "clr", "test"):
                for u in v[kind]:
                    where = ("chunk %d" % u["chunk"]) if u["chunk"] else ("ovl %d [%s]" % (u["location"], loc_name.get(u["location"], "")))
                    f.write("  %-4s %-6s %s %s %s %s\n" % (kind, u["via"], where, u["block"],
                                                          "/".join(u["speakers"]), u["line"][:70]))
    print("overlays", len(ovls), "chunks", len(chunk_owner), "flags", len(flag_ix))
    return catalog


if __name__ == "__main__":
    build()
