"""Assembler for Azure Dreams town event scripts (the bytecode run by EXE FUN_80038AB8).

Source format, one statement per line ('#' starts a comment):

    label:                     define a label
    text "Hello <player>!"     dialogue text (ASCII is converted to the game's full-width Shift-JIS;
                               tokens: <player> = Koh's name, <v0>..<v15> = number in a script var)
    nl                         next line in the box          waitbtn   wait for a button
    clear                      clear the box                 page N    speaker (actor id, 0 = none)
    option "[Text]"            one menu line (op 0x0B + text)
    choice N                   show the N options above, cursor menu (op 0x19)
    switch L1, L2, ...         jump to the label of the chosen option (op 0x1A)
    if_set FLAG, L             jump if story flag is set     if_clr FLAG, L   jump if clear
    set FLAG / clr FLAG        set / clear a story flag
    goto L / call L / ret      control flow
    vset R, VALUE              var R = VALUE                 native ADDR       call MIPS fn(var0..3) -> var15
    vload R, IDX, ADDR         var R = *(u32*)(ADDR + IDX*4) (op 0x36: read any RAM word)
    if_v0 R, L / if_vnz R, L   jump if var R == 0 / != 0     vcmp A, B   var15 = A - B
    vadd A, B / vsub A, B      var A += / -= var B
    face ACTOR, N              set a character's portrait face and her default face (op 0x53)
    end                        wait for the box to close and end the script (01 00)
    byte XX [XX ...]           raw bytes

Absolute addresses are emitted for labels; `assemble()` returns the bytes, the label map and the
offsets of every absolute address (so a plugin can relocate the blob to wherever it lands).
"""
import re, struct, unicodedata

OPC = dict(wait=0x01, clear=0x08, nl=0x0A, set=0x0C, clr=0x0D, waitbtn=0x11, call=0x15, ret=0x16,
           goto=0x17, if_set=0x18, choice=0x19, switch=0x1A, if_clr=0x2B, vset=0x34, vload=0x36,
           vcmp=0x3D, if_v0=0x3E, if_vnz=0x3F, native=0x4C, page=0x57, option=0x0B,
           vadd=0x3B, vsub=0x3C, face=0x53)
MAX_LINE = 28
MAX_OPTION = 31   # menu lines: the game's own run to 31 (Weedy's "[Sure. Give me that cute book.]")


def sjis_text(s):
    """ASCII/Unicode -> the game's text bytes (full-width SJIS, tokens for name/number)."""
    out = bytearray()
    for tok in re.split(r"(<player>|<v\d+>)", s):
        if not tok:
            continue
        if tok == "<player>":
            out += b"\xFE\x00"
            continue
        m = re.fullmatch(r"<v(\d+)>", tok)
        if m:
            out += bytes([0xFD, int(m.group(1))])
            continue
        for c in tok:
            if c == " ":
                u = "　"
            elif c == "'":
                u = "’"
            elif c == '"':
                u = "”"
            elif "!" <= c <= "~":
                u = chr(ord(c) + 0xFEE0)
            else:
                u = c
            try:
                b = u.encode("cp932")
            except UnicodeEncodeError:
                b = "？".encode("cp932")
            out += b
    return bytes(out)


def visible_len(s):
    return len(re.sub(r"<player>", "XXXXXXXX", re.sub(r"<v\d+>", "XXXXX", s)))


def parse_args(rest):
    """Split 'a, b, "c d"' respecting quotes."""
    args, cur, q = [], "", False
    for ch in rest:
        if ch == '"':
            q = not q
            cur += ch
        elif ch == "," and not q:
            args.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        args.append(cur.strip())
    return args


def num(s):
    return int(s, 0)


def assemble(src, base):
    """Two-pass assembly at address `base`. Returns (bytes, labels, reloc_offsets)."""
    stmts = []
    for ln, raw in enumerate(src.splitlines(), 1):
        line = raw.split("#", 1)[0].strip() if '"' not in raw else raw.strip()
        if '"' in line:
            # strip trailing comment outside quotes
            q = False
            for i, ch in enumerate(line):
                if ch == '"':
                    q = not q
                elif ch == "#" and not q:
                    line = line[:i].strip()
                    break
        if not line:
            continue
        if line.endswith(":") and " " not in line:
            stmts.append((ln, "label", [line[:-1]]))
            continue
        op, _, rest = line.partition(" ")
        stmts.append((ln, op, parse_args(rest)))
    labels, out, relocs = {}, bytearray(), []

    def emit_stmt(op, args, ln, pass2):
        def addr(lbl):
            if not pass2:
                return 0
            if lbl in labels:
                return labels[lbl]
            try:
                return num(lbl)
            except ValueError:
                raise SyntaxError("line %d: unknown label %s" % (ln, lbl))

        def u32_label(lbl):
            if pass2 and lbl in labels:
                relocs.append(len(out))
            out.extend(struct.pack("<I", addr(lbl)))

        if op == "label":
            labels[args[0]] = base + len(out)
        elif op in ("text", "option"):
            s = args[0].strip('"')
            limit = MAX_OPTION if op == "option" else MAX_LINE
            if visible_len(s) > limit:
                raise SyntaxError("line %d: text longer than %d: %s" % (ln, limit, s))
            if op == "option":
                out.append(OPC["option"])
            out.extend(sjis_text(s))
        elif op in ("nl", "waitbtn", "clear", "ret", "wait"):
            out.append(OPC[op])
        elif op == "end":
            out.extend(b"\x01\x00")
        elif op == "page":
            out.extend(bytes([OPC["page"], num(args[0])]))
        elif op == "choice":
            out.extend(bytes([OPC["choice"], num(args[0])]))
        elif op == "switch":
            out.append(OPC["switch"])
            for a in args:
                u32_label(a)
        elif op in ("set", "clr"):
            out.append(OPC[op])
            out.extend(struct.pack("<H", num(args[0])))
        elif op in ("if_set", "if_clr"):
            out.append(OPC[op])
            out.extend(struct.pack("<H", num(args[0])))
            u32_label(args[1])
        elif op in ("goto", "call"):
            out.append(OPC[op])
            u32_label(args[0])
        elif op == "vset":
            out.extend(bytes([OPC["vset"], num(args[0])]))
            out.extend(struct.pack("<I", num(args[1]) & 0xFFFFFFFF))
        elif op == "vload":
            out.extend(bytes([OPC["vload"], num(args[0]), num(args[1])]))
            out.extend(struct.pack("<I", num(args[2])))
        elif op in ("vcmp", "vadd", "vsub", "face"):
            out.extend(bytes([OPC[op], num(args[0]), num(args[1])]))
        elif op in ("if_v0", "if_vnz"):
            out.extend(bytes([OPC[op], num(args[0])]))
            u32_label(args[1])
        elif op == "native":
            out.append(OPC["native"])
            out.extend(struct.pack("<I", num(args[0])))
        elif op == "byte":
            out.extend(bytes(num(a) for a in " ".join(args).split()))
        else:
            raise SyntaxError("line %d: unknown statement %s" % (ln, op))

    for pass2 in (False, True):
        out.clear()
        relocs.clear()
        for ln, op, args in stmts:
            emit_stmt(op, args, ln, pass2)
    return bytes(out), labels, list(relocs)


def relocate(blob, relocs, old_base, new_base):
    b = bytearray(blob)
    for off in relocs:
        v = struct.unpack_from("<I", b, off)[0]
        struct.pack_into("<I", b, off, v - old_base + new_base)
    return bytes(b)


if __name__ == "__main__":
    import sys
    src = open(sys.argv[1], encoding="utf-8").read()
    base = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0
    blob, labels, relocs = assemble(src, base)
    print("%d bytes, %d labels, %d relocs" % (len(blob), len(labels), len(relocs)))
