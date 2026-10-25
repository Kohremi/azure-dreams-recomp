"""Play a town conversation box by box on the dev build and report which boxes were voiced.

    python voice_test.py <save slot> [max boxes] [--walk dir:frames,...] [--talk] [--shots name] [--read N]

Needs the dev build running on the JP Voices disc with jp-voices enabled. Per box it logs the VM
pointer at the button wait, whether the VM ran through a voice snippet (plugin memory 0x9F000000+)
since the previous box, and the CD-audio (cd_in) samples that became audible while the box was shown.
It waits at each box until the stream is idle (or a timeout) before pressing Cross, so voices play out;
with --read N it presses after N frames instead (a reader), so voices that continue through split boxes
show up as "carried" (the stream still busy when the next box appears).
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from psx import Game

VM_STATE, VM_PTR = 0x80082AD4, 0x80082AE0
WAITBTN, CHOICE, RUNNING, PAGE, END = 0x80038478, 0x80038588, 0x80038A10, 0x80038368, 0x80038A00
ACTWAIT = 0x80038408                    # waiting for an actor action (op 0x0F)
NOSTOP = 0x8006778C                     # the plugin's button wait that keeps the voice playing
WAITS = (WAITBTN, NOSTOP)
VOICES = json.load(open(os.path.join(ROOT, "re", "events", "voices.json"), encoding="utf-8"))["voices"]
SNIP_LO, SNIP_HI = 0x9F000000, 0x9F100000


def cdin(g):
    return {x["name"]: x for x in g.cmd("audio_stats")["taps"]}["cd_in"]["audible"]


def stream_busy(g):
    w0, w1, w2 = g.u32(0x800847D0), g.u32(0x800847D4), g.u32(0x8008485C)
    return bool((w1 & 0x200) or (w0 & 0x4000) or w2 == 2 or (w0 & 0x400))


def line_for(base, lo, hi):
    """The mapped voiced line (English | Japanese) whose text lies between two waits, if any."""
    for v in VOICES:
        if v.get("kind") == "text" and v["base"] == base and lo < v["us_text"] < hi:
            return "%s | %s" % (v["us_line"][:30], v["jp_text"].strip()[:14])
    return "-"


def play(g, max_boxes=30, idle_timeout=600, shots=None, read=None):
    boxes, saw_snip, last_ptr, a0, quiet = [], False, 0, cdin(g), 0
    base = g.u32(0x801131B8 + 0x2C)
    t0 = g.frame()
    stuck_ptr, stuck_since = None, g.frame()
    while len(boxes) < max_boxes and g.frame() - t0 < 20000:
        st, ptr = g.u32(VM_STATE), g.u32(VM_PTR)
        if st in (ACTWAIT, RUNNING) and ptr == stuck_ptr and g.frame() - stuck_since > 150                 and g.u8(ptr) == 0x0F:
            # an actor action that never completes (actors out of place after a door swap): skip it
            size = 2 if g.u8(ptr + 1) == 0 else 3
            new = ptr + size
            print("      skipping actor op at %08x" % ptr, flush=True)
            g.write(VM_PTR, bytes([new & 0xFF]) if (new ^ ptr) < 0x100 else new.to_bytes(4, "little"))
            continue
        if ptr != stuck_ptr:
            stuck_ptr, stuck_since = ptr, g.frame()
        if SNIP_LO <= ptr < SNIP_HI:
            saw_snip = True
        if st in WAITS and ptr != last_ptr and not SNIP_LO <= ptr < SNIP_HI:
            carried = stream_busy(g) and not saw_snip
            f0 = g.frame()
            seen_busy, nostop, starts, was, idle_since = False, st == NOSTOP, 0, carried, g.frame()
            while g.frame() - f0 < (read or idle_timeout):
                b = stream_busy(g)
                if b and not was:
                    starts += 1               # a voice started while this box is shown (follow-ups)
                was = b
                seen_busy |= b
                if b:
                    idle_since = g.frame()
                s2 = g.u32(VM_STATE)
                nostop |= s2 == NOSTOP
                if SNIP_LO <= g.u32(VM_PTR) < SNIP_HI:
                    saw_snip = True
                if s2 not in WAITS and not SNIP_LO <= g.u32(VM_PTR) < SNIP_HI:
                    break
                if read is None and not b and g.frame() - idle_since > 45 and (seen_busy or g.frame() - f0 > 90):
                    break
                g.wait_frames(3)
            a1 = cdin(g)
            boxes.append(dict(ptr=ptr, snip=saw_snip, audible=a1 - a0, carried=carried, nostop=nostop,
                              starts=starts))
            print("box %2d  ptr %08x  %-7s %-7s %-6s starts %d  cd_in +%-7d  %s" % (
                len(boxes), ptr, "voice" if saw_snip else "", "carried" if carried else "",
                "nostop" if nostop else "", starts, a1 - a0, line_for(base, last_ptr, ptr)), flush=True)
            if shots:
                g.shot("%s_%02d" % (shots, len(boxes)))
            a0, saw_snip, last_ptr = a1, False, ptr
            g.tap("cross")
            quiet = 0
        elif st == CHOICE:
            print("      choice menu: picking the first option", flush=True)
            g.tap("cross")
            g.wait_frames(10)
        elif st in (0, END) or st not in WAITS + (CHOICE, RUNNING, PAGE, ACTWAIT):
            quiet += 1
            if quiet > 60 and boxes:
                break
        g.wait_frames(2)
    return boxes


def main():
    args = sys.argv[1:]
    slot = int(args[0])
    max_boxes = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30
    g = Game()
    g.load_state(slot)
    g.wait_frames(20)
    if "--walk" in args:
        for step in args[args.index("--walk") + 1].split(","):
            d, f = step.split(":")
            g.hold(d)
            g.wait_frames(int(f))
            g.release()
            g.wait_frames(10)
    if "--talk" in args:
        g.tap("cross")
    shots = args[args.index("--shots") + 1] if "--shots" in args else None
    read = int(args[args.index("--read") + 1]) if "--read" in args else None
    boxes = play(g, max_boxes, shots=shots, read=read)
    print("boxes %d: voice started %d, voice carried over %d, kept-playing waits %d, with CD audio %d" % (
        len(boxes), sum(b["snip"] for b in boxes), sum(b["carried"] for b in boxes),
        sum(b["nostop"] for b in boxes), sum(1 for b in boxes if b["audible"] > 1000)))


if __name__ == "__main__":
    main()
