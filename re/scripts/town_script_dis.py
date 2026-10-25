"""Disassembler for Azure Dreams town event scripts (EXE VM FUN_80038AB8, opcode table 0x8006AA90).

A script chunk is a sector-aligned block in TOWN.BIN: u32 chunk number, then bytecode + text, then
(sometimes) MIPS helper functions called with op 0x4C. The town loader always moves the running
chunk to 0x8001DCD0 (cache slot 0), so code/jump addresses inside it are absolute from that base.

Text: a byte < 0x01 (signed <= 0) in opcode position starts text. Inside text:
  0x81..0xFC xx  Shift-JIS full-width char      0xFD rr  number from var rr
  0xFE nn        named string nn (0 = player)    0xFF a32 call a text fragment at a32
  0x00           return (end of fragment / script)
Text runs until the next byte in 0x01..0x7F, which is an opcode.

Usage:  python town_script_dis.py <TOWN.BIN offset hex> [base hex]
"""
import os, struct, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
TOWN = os.path.join(ROOT, r"extracted\TOWN\TOWN.BIN")
TOWN_LBA = 3077
BASE = 0x8001DCD0

# operand kinds: b=u8 h=u16 f=flag(u16) a=code addr(u32) w=u32 d=data addr(u32) n=native fn(u32)
# 0x01 ("wait" in the dumps) ends the script: the VM goes to its idle state 0x80038A00 and a playing
# voice is stopped (FUN_80053DA8(0xC4)); what follows starts another script (the US pads the gap with
# leftover bytes). The US VM also has op 0x58 (handler 0x8003B470), not decoded here.
OPS = {
    0x01: ("wait", ""), 0x02: ("nop02", ""), 0x03: ("nop03", ""), 0x04: ("nop04", ""),
    0x05: ("op05", "b"), 0x06: ("op06", ""), 0x07: ("nop07", ""), 0x08: ("clear", ""),
    0x09: ("op09", "b"), 0x0A: ("nl", ""), 0x0B: ("op0b", ""), 0x0C: ("set", "f"),
    0x0D: ("clr", "f"), 0x0E: ("nop0e", ""), 0x0F: ("actor", "A"), 0x10: ("nop10", ""),
    0x11: ("waitbtn", ""), 0x12: ("delay", "h"), 0x13: ("op13", "h"), 0x14: ("nop14", ""),
    0x15: ("call", "a"), 0x16: ("ret", ""), 0x17: ("goto", "a"), 0x18: ("if_set", "fa"),
    0x19: ("choice", "b"), 0x1A: ("switch", "S"), 0x1B: ("nop1b", ""), 0x1C: ("op1c", "bb"),
    0x1D: ("stream", "ww"), 0x1E: ("sound", "h"), 0x1F: ("nop1f", ""), 0x20: ("nop20", ""),
    0x21: ("nop21", ""), 0x22: ("nop22", ""), 0x23: ("op23", ""), 0x24: ("op24", "b"),
    0x25: ("op25", "b"), 0x26: ("op26", "b"), 0x27: ("op27", "bb"), 0x28: ("nop28", ""),
    0x29: ("nop29", ""), 0x2A: ("choice2", "b"), 0x2B: ("if_clr", "fa"), 0x2C: ("choice3", "b"),
    0x2D: ("nop2d", ""), 0x2E: ("ovlcall", "b"), 0x2F: ("tblcall", "bd"), 0x30: ("yield", ""),
    0x31: ("vzero", "b"), 0x32: ("vfill", "b"), 0x33: ("vcopy", "bb"), 0x34: ("vset", "bw"),
    0x35: ("vload_g", "bb"), 0x36: ("vload_tab", "bbd"), 0x37: ("vcopy2", "bb"), 0x38: ("skip1", ""),
    0x39: ("vstore_g", "bb"), 0x3A: ("vstore_tab", "bbd"), 0x3B: ("vadd", "bb"), 0x3C: ("vsub", "bb"),
    0x3D: ("vcmp", "bb"), 0x3E: ("if_v0", "ba"), 0x3F: ("if_vnz", "ba"), 0x40: ("if_vle0", "ba"),
    0x41: ("if_vlt0", "ba"), 0x42: ("if_vge0", "ba"), 0x43: ("if_vgt0", "ba"), 0x44: ("vcopy3", "bb"),
    0x45: ("vset2", "bw"), 0x46: ("vload_tab2", "bbd"), 0x47: ("op47", "bbd"), 0x48: ("jmp_v", "b"),
    0x49: ("vmul", "bb"), 0x4A: ("vdiv", "bb"), 0x4B: ("call_v", "b"), 0x4C: ("native", "n"),
    0x4D: ("vload_ind", "bbd"), 0x4E: ("vstore_b", "bbd"), 0x4F: ("vload_idx", "bbd"),
    0x50: ("vstore_idx", "bbd"), 0x51: ("nop51", ""), 0x52: ("nop52", ""), 0x53: ("op53", "bb"),
    0x54: ("loopn", "b"), 0x55: ("loop", ""), 0x56: ("op56", ""), 0x57: ("page", "b"),
}
CONDJ = {0x18, 0x2B, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43}
STOPS = {0x16, 0x17, 0x1A, 0x48}
CHOICE = {0x19, 0x2A, 0x2C}

SPEAKERS = ("Guy Wreath Weedy Ghosh Selfi Patty Fur Mia Nico Vivian Cherrl Pen Fon Barry Beldo Okami "
            "Barten Wotta Silver Jorda Dr.Hal Tonka Hush Nadia Coppe NcsDad Angel Issac Jacof Etto Romi Shin").split()


def sjis_char(b1, b2):
    try:
        c = bytes([b1, b2]).decode("cp932")
    except UnicodeDecodeError:
        return "{%02x%02x}" % (b1, b2)
    c = unicodedata.normalize("NFKC", c)
    return {"\u3000": " "}.get(c, c)


class Chunk:
    def __init__(self, data, base=BASE, resolver=None):
        self.data, self.base = data, base
        self.resolver = resolver          # addr -> bytes for text fragments outside the chunk

    def inside(self, a):
        return self.base <= a < self.base + len(self.data)

    def u8(self, a):
        o = a - self.base
        return self.data[o] if 0 <= o < len(self.data) else 0

    def u16(self, a):
        return self.u8(a) | self.u8(a + 1) << 8

    def u32(self, a):
        return self.u16(a) | self.u16(a + 2) << 16

    def text(self, a, depth=0):
        """Decode a text run starting at a. Returns (string, next address, fragments called)."""
        out, frags = [], []
        while self.inside(a):
            b = self.u8(a)
            if 0x01 <= b <= 0x7F:
                break
            if b == 0x00:
                out.append("<end>"); a += 1; break
            if b == 0xFF:
                t = self.u32(a + 1) if self.inside(a + 4) else 0
                frags.append(t)
                out.append(self.fragment(t, depth))
                a += 5; continue
            if b == 0xFE:
                n = self.u8(a + 1)
                out.append("<player>" if n == 0 else "<name%d>" % n); a += 2; continue
            if b == 0xFD:
                out.append("<v%d>" % self.u8(a + 1)); a += 2; continue
            if b == 0x80:
                out.append("{80%02x}" % self.u8(a + 1)); a += 2; continue
            out.append(sjis_char(b, self.u8(a + 1))); a += 2
        return "".join(out), a, frags

    def fragment(self, t, depth):
        if depth > 4:
            return "<frag %08x>" % t
        if self.inside(t):
            s, _, _ = self.text(t, depth + 1)
            return s.replace("<end>", "")
        if self.resolver:
            blob = self.resolver(t)
            if blob:
                s, _, _ = Chunk(blob, t, self.resolver).text(t, depth + 1)
                return s.replace("<end>", "")
        return "<frag %08x>" % t

    def insn(self, a):
        """Decode one instruction at a: (op, name, operands dict/list, size, text or None)."""
        op = self.u8(a)
        if op == 0x00 or op >= 0x80:
            s, nxt, frags = self.text(a)
            return dict(op=None, name="text", text=s, size=nxt - a, frags=frags)
        if op not in OPS:
            return dict(op=op, name="bad%02x" % op, args=[], size=1)
        name, spec = OPS[op]
        p = a + 1
        args = []
        for k in spec:
            if k == "b":
                args.append(self.u8(p)); p += 1
            elif k in "hf":
                args.append(self.u16(p)); p += 2
            elif k in "awdn":
                args.append(self.u32(p)); p += 4
            elif k == "A":
                act = self.u8(p); p += 1
                args.append(act)
                if act:
                    args.append(self.u8(p)); p += 1
            elif k == "S":
                args.append("S")   # filled by caller (needs the choice count)
        return dict(op=op, name=name, args=args, size=p - a)


def fmt(ins, choice_n=None, chunk=None, a=None):
    if ins["name"] == "text":
        return '"' + ins["text"] + '"'
    op, args = ins["op"], ins["args"]
    if op in (0x0C, 0x0D):
        return "%s flag %d" % (ins["name"], args[0])
    if op in (0x18, 0x2B):
        return "%s flag %d -> %08x" % (ins["name"], args[0], args[1])
    if op in (0x15, 0x17):
        return "%s %08x" % (ins["name"], args[0])
    if op == 0x4C:
        return "native %08x" % args[0]
    if op == 0x1A:
        return "switch [%s]" % ", ".join("%08x" % t for t in ins.get("targets", []))
    if op in (0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43):
        return "%s v%d -> %08x" % (ins["name"], args[0], args[1])
    return ins["name"] + (" " + " ".join(("%x" % x) if isinstance(x, int) else str(x) for x in args) if args else "")


def disasm_linear(chunk, start, end, natives=()):
    """Linear sweep. Returns list of (addr, ins)."""
    out = []
    a = start
    last_choice = 0
    while a < end:
        if any(lo <= a < hi for lo, hi in natives):
            hi = max(h for l, h in natives if l <= a < h)
            out.append((a, dict(op=None, name="mips", size=hi - a)))
            a = hi; continue
        ins = chunk.insn(a)
        if ins["op"] in CHOICE:
            last_choice = ins["args"][0]
        if ins["op"] == 0x1A:
            n = last_choice or 2
            ins["targets"] = [chunk.u32(a + 1 + 4 * i) for i in range(n) if chunk.inside(a + 4 + 4 * i)]
            ins["size"] = 1 + 4 * len(ins["targets"])
        out.append((a, ins))
        a += max(1, ins["size"])
    return out


def mips_ranges(chunk):
    """MIPS helper functions embedded in the chunk: decode the bytecode linearly until reaching the
    lowest in-chunk op 0x4C target; MIPS runs from there to the last `jr ra` + delay slot."""
    first = None
    a, end = chunk.base + 4, chunk.base + len(chunk.data)
    last_choice = 0
    while a < end and (first is None or a < first):
        ins = chunk.insn(a)
        if ins["op"] == 0x4C:
            t = ins["args"][0]
            if chunk.inside(t) and (t - chunk.base) % 4 == 0 and t > a:
                first = t if first is None else min(first, t)
        if ins["op"] in CHOICE:
            last_choice = ins["args"][0]
        if ins["op"] == 0x1A:
            ins["size"] = 1 + 4 * (last_choice or 2)
        a += max(1, ins["size"])
    if first is None:
        return []
    hi = first
    off = first - chunk.base
    while off + 8 <= len(chunk.data):
        if struct.unpack_from("<I", chunk.data, off)[0] == 0x03E00008:
            hi = chunk.base + off + 8
        off += 4
    return [(first, hi)]


def load_chunk(off, size=None):
    D = open(TOWN, "rb").read()
    if size is None:
        # until the next sector that starts with a different chunk number or the data runs out
        size = 0x8000
    return D[off:off + size]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    off = int(sys.argv[1], 16)
    data = load_chunk(off)
    # trim trailing zero sectors
    end = len(data)
    while end > 0 and data[end - 1] == 0:
        end -= 1
    data = data[:end]
    ch = Chunk(data)
    nat = mips_ranges(ch)
    print("; chunk TOWN+%06x  number %d  size %d  mips %s" % (off, ch.u32(BASE), len(data),
          ["%08x-%08x" % r for r in nat]))
    for a, ins in disasm_linear(ch, BASE + 4, BASE + len(data), nat):
        print("%08x  %s" % (a, fmt(ins) if ins["name"] != "mips" else "<mips %d bytes>" % ins["size"]))


if __name__ == "__main__":
    main()
