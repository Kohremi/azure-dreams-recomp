"""Build the in-game Story Journal (a third option in Weedy's menu in Koh's house).

    python make_journal.py            # draft re/events/journal.toml if missing, then build
    python make_journal.py --redraft  # overwrite journal.toml with a fresh draft

The journal shows each girl's story beats in order and lets you pick where her story stands:
choose a beat and it becomes the next thing that happens, or choose an ending to put her in her
resolved state. The picker opens on her next beat's page and marks each choice + passed, > next,
- later. The town picks it up the next time a location loads (e.g. when you step outside).

How it opens: when you talk to Weedy in Koh's house she asks "Do you want to read my Monster Book?"
with two answers (Koh's house overlay program, TOWN lba 5071 at 0x80016000; the menu starts at
WEEDY_MENU). The plugin replaces the first bytes of that menu with a jump to `weedy:` below, the same
menu with a third answer that runs the journal; the first two answers jump back to the game's own
branches.

How a story position is applied (see re/NOTES.md -> Town events): each girl's story is a few event
chains (actor slots in town locations, `re/events/stages.json`). A chain at position p has the flags
of stages 0..p-1 set and of stages p.. cleared. Passing a stage also implies the flags its condition
waited for (e.g. a tower event) and the story flags its scenes set; those are set for passed stages and
cleared for later ones. Per-visit gates, per-visit latches and counters are never touched; each chain's
"seen" marker is cleared so the chosen beat plays when you next talk to her.

journal.toml is the editable source: per girl her chains, her beats (`at` = chain:stage), and her
endings (`chains` = positions, `set`/`clear` = extra flags, `detect` = flags that identify it).
"""
import json, os, re, struct, sys, tomllib
sys.path.insert(0, os.path.dirname(__file__))
import town_script_asm as asm

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root
EVENTS = os.path.join(ROOT, r"re\events")
SRC = os.path.join(EVENTS, "journal.toml")
ASM_OUT = os.path.join(EVENTS, "journal.asm")
HEADER = os.path.join(ROOT, r"mods_src\azure_journal_data.h")
TITLE_MAX = 26

TOWN = os.path.join(ROOT, r"extracted\TOWN\TOWN.BIN")
HOUSE_OVERLAY_OFF = 0x3E5000   # Koh's house overlay program (TOWN lba 5071), loaded at 0x80016000
WEEDY_MENU = 0x800177C5        # `page 0` before "[Sure. Give me that cute book.]"
WEEDY_MENU_LEN = 0x8C          # through `choice 2; switch [sure, busy]`
JOURNAL_OPTION = "[Show me your story journal.]"


def weedy_menu():
    """Weedy's original menu bytes and the targets of its two answers, checked against the
    shape the plugin patches: page 0, two options, choice 2, switch."""
    with open(TOWN, "rb") as f:
        f.seek(HOUSE_OVERLAY_OFF + WEEDY_MENU - 0x80016000)
        orig = f.read(WEEDY_MENU_LEN)
    if orig[:3] != b"\x57\x00\x0B" or orig[-11:-8] != b"\x19\x02\x1A":
        raise SystemExit("Weedy's menu is not where expected (0x%08X)" % WEEDY_MENU)
    sure, busy = struct.unpack_from("<II", orig, WEEDY_MENU_LEN - 8)
    return orig, sure, busy


def weedy_source(orig, sure, busy):
    src = ("weedy:\n  page 0\n  option \"[Sure. Give me that cute book.]\"\n  nl\n"
           "  option \"[I'm too busy for that. Sorry.]\"\n  nl\n  option \"%s\"\n  choice 3\n"
           "  switch 0x%08X, 0x%08X, start\n" % (JOURNAL_OPTION, sure, busy))
    mine = asm.assemble(src + "start:\n", 0)[0]
    shared = len(orig) - 11   # up to the end of the second answer's text
    if mine[:shared] != orig[:shared]:
        raise SystemExit("Weedy's menu text does not re-assemble to the game's bytes")
    return src

PLACE = {4444: "Town square", 6287: "Cherrl's house", 5934: "Hospital", 5801: "Inn", 5236: "Library",
         5091: "Fur's house", 5442: "Theater", 6317: "Nico's house", 6431: "Bar", 5697: "Wotta's"}

# The game's own girl table (town module 0x800D1056 actor ids / 0x800D1064 resolved flags).
RESOLVED = {"Nico": 5230, "Selfi": 5234, "Fur": 5232, "Mia": 5236, "Patty": 5242, "Vivian": 5238, "Cherrl": 5240}
# Script actor ids. Portrait records: EXE list 0x8006B1EC -> 0x800135C4 + i*4 (+2 face, +3 default face),
# written by script op 0x53 (`face` in town_script_asm).
ACTOR = {"Nico": 0x0B, "Selfi": 7, "Patty": 8, "Fur": 9, "Mia": 0x0A, "Vivian": 0x0C, "Cherrl": 0x0D}
GIRL_ORDER = ["Nico", "Selfi", "Cherrl", "Mia", "Fur", "Vivian", "Patty"]

# ------------------------------------------------------------------------------- curated drafts
SQ_NICO, SQ_FOUNTAIN, NICO_HOUSE = "4444:8001b3a0", "4444:8001b3f4", "6317:80018b00"
SELFI = "4444:8001b7e4"
CH_SQ, CH_HOUSE, CH_HOSP = "4444:8001b6b0", "6287:80019008", "5934:8001910c"

CURATED = {
    "Nico": dict(chains=[SQ_NICO, SQ_FOUNTAIN, NICO_HOUSE], events=[
        (NICO_HOUSE, 0, "Meet Nico at home"),
        (SQ_NICO, 1, "Fountain drive starts"),
        (SQ_NICO, 2, "Donate to the fountain"),
        (NICO_HOUSE, 1, "Nico counts donations"),
        (NICO_HOUSE, 2, "Donations, part two"),
        (SQ_FOUNTAIN, 0, "The fountain is finished"),
        (NICO_HOUSE, 3, "Nico after the fountain"),
        (SQ_FOUNTAIN, 1, "Square after the fountain"),
        (SQ_FOUNTAIN, 2, "Selfi gives you her egg"),
        (NICO_HOUSE, 4, "Nico asks about Selfi"),
        (NICO_HOUSE, 5, "Nico and Ghosh's plans"),
        (SQ_FOUNTAIN, 3, "Ghosh and Nico, culture"),
        (SQ_FOUNTAIN, 4, "Chero the cellist"),
        (NICO_HOUSE, 6, "Nico: glad to see you"),
        (NICO_HOUSE, 7, "Nico warms up"),
        (NICO_HOUSE, 8, "Nico's feelings grow"),
        (NICO_HOUSE, 9, "Nico: pleasure to see you"),
        (NICO_HOUSE, 10, "Nico tries polite speech"),
        (NICO_HOUSE, 11, "Nico feels terrific"),
    ], endings=[dict(title="Complete", detect=[2445])]),
    "Selfi": dict(chains=[SELFI], events=[
        (SELFI, 1, "Selfi's tower training"),
        (SELFI, 3, "Rescue Selfi in the tower"),
        (SELFI, 4, "Selfi gives you her egg"),
        (SELFI, 5, "Selfi asks about Ghosh"),
        (SELFI, 6, "Rumor: frilly pink panties"),
        (SELFI, 7, "Rumor: a frog's brain"),
        (SELFI, 8, "Rumor: really 30 years old"),
        (SELFI, 9, "Rumor: scales on your back"),
        (SELFI, 10, "Selfi: you're a mystery"),
        (SELFI, 11, "Selfi wants to know you"),
        (SELFI, 12, "Why did I rescue you?"),
        (SELFI, 13, "Selfi's confession"),
        (SELFI, 15, "You came to see me, right?"),
    ], endings=[dict(title="Complete", detect=[3426])]),
    "Cherrl": dict(chains=[CH_HOUSE, CH_SQ, CH_HOSP], exclude=[4605, 4051, 4071, 4072, 4056], events=[
        (CH_HOUSE, 0, "Meet Cherrl at home"),
        (CH_SQ, 1, "Cherrl in the square"),
        (CH_HOUSE, 1, "Cherrl wants a friend"),
        (CH_HOUSE, 2, "Cherrl envies your energy"),
        (CH_HOUSE, 3, "Cherrl gets tired"),
        (CH_HOUSE, 4, "Walk outside, hand in hand"),
        (CH_HOUSE, 5, "Cherrl faints"),
        (CH_HOSP, 0, "Hush shows his hospital"),
        (CH_HOSP, 1, "Ask Hush about Cherrl"),
        (CH_HOSP, 2, "Hush and Cherrl's illness"),
        (CH_HOSP, 3, "Hospital visit"),
        (CH_HOSP, 5, "Cherrl is admitted"),
        (CH_HOUSE, 6, "Nadia: she's in hospital"),
        (CH_HOSP, 6, "Visit Cherrl in hospital"),
        (CH_HOSP, 7, "Her illness can be cured"),
        (CH_HOSP, 8, "Cherrl: I'll do my best"),
        (CH_HOSP, 9, "Cherrl recovers"),
        (CH_HOUSE, 7, "Cherrl is cured!"),
    ], endings=[
        dict(title="Complete: nurse", chains={CH_HOUSE: 8, CH_HOSP: "end", CH_SQ: "end"},
             set=[4605, 4071, 4072, 4056], clear=[4051], detect=[4605, 4057], face=7),
        dict(title="Complete: doll shop", chains={CH_HOUSE: "end", CH_HOSP: 10, CH_SQ: "end"},
             set=[4051], clear=[4605, 4071, 4072, 4056], detect=[2007], face=0),
    ]),
}
AUTO_CHAINS = {
    "Mia": ["4444:8001b448", "5236:80018d04"],
    "Fur": ["5091:8001abb0", "5091:8001ac04"],
    "Vivian": ["5442:80018ffc"],
    "Patty": ["5801:80019830"],
}


# ------------------------------------------------------------------------------- chain model
def load_chains():
    raw = json.load(open(os.path.join(EVENTS, "stages.json"), encoding="utf-8"))
    chains = {}
    for c in raw:
        cid = "%d:%s" % (c["location"], c["entry"])
        if cid not in chains:                # 6431 lists its table twice; keep the first
            chains[cid] = c
    return chains


def cleared_somewhere():
    flags = json.load(open(os.path.join(EVENTS, "town_events.json"), encoding="utf-8"))["flags"]
    return {int(k) for k, v in flags.items() if v["clr"]}


class Model:
    def __init__(self):
        self.chains = load_chains()
        self.stage_flags = {s["flag"] for c in self.chains.values() for s in c["stages"] if s["flag"] > 1}
        self.volatile = set(cleared_somewhere())
        for c in self.chains.values():
            self.volatile |= set(c["gates"]) | set(c["latches"])
            if c["slot_flag"] > 1:
                self.volatile.add(c["slot_flag"])
        self.volatile |= {0, 1}

    def external(self, girl):
        """Flags set by scenes of chains that are not this girl's."""
        mine = set(girl["chains"])
        ext = set()
        for cid, c in self.chains.items():
            if cid in mine:
                continue
            for s in c["stages"]:
                ext |= set(s["script_fn_flags"].get("set", []))
                for sc in s["scripts"]:
                    ext |= set(sc["flags"]["set"])
        return ext

    def stage_faces(self, cid, actor):
        """Stage -> default portrait face its scenes leave for `actor` (op 0x53). Each op is credited
        to the last stage whose scenes can reach it; a stage's result is its op at the highest address."""
        last = {}
        for s in self.chains[cid]["stages"]:
            for sc in s["scripts"]:
                for a, f, addr in sc.get("faces", []):
                    if a == actor:
                        last[addr] = (s["index"], f)
        out = {}
        for addr in sorted(last):
            i, f = last[addr]
            out[i] = f
        return out

    def position_face(self, girl, positions):
        """Default face after the passed stages: from the latest passed stage in her event order
        (0 = normal when none of her passed scenes set one)."""
        actor = ACTOR.get(girl["name"])
        if actor is None:
            return None
        evs = girl["event"]
        best = None
        for ci, cid in enumerate(girl["chains"]):
            for i, f in self.stage_faces(cid, actor).items():
                if i >= positions[cid]:
                    continue
                later = [k for k, e in enumerate(evs) if e["at"].rsplit(":", 1)[0] == cid
                         and int(e["at"].rsplit(":", 1)[1]) >= i]
                key = (later[0] if later else len(evs) + ci, i)
                if best is None or key > best[0]:
                    best = (key, f)
        return best[1] if best else 0

    def end(self, cid):
        st = self.chains[cid]["stages"]
        last = max((s["index"] for s in st if s["flag"] > 1), default=-1)
        return last + 1

    def effects(self, cid, exclude=()):
        """Per stage: flags that hold once the stage has been passed."""
        st = self.chains[cid]["stages"]
        bad = self.volatile | set(exclude)
        eff = {s["index"]: set() for s in st}
        side_at = {}
        for s in st:
            i = s["index"]
            if s["flag"] > 1:
                eff[i].add(s["flag"])
            eff[i] |= {f for f in s["cond_flags"].get("test", []) if f not in bad and f not in self.stage_flags}
            side = set(s["script_fn_flags"].get("set", []))
            for sc in s["scripts"]:
                side |= set(sc["flags"]["set"])
            for f in side:
                if f not in bad and f not in self.stage_flags:
                    side_at[f] = max(side_at.get(f, -1), i)    # set once every stage that can set it is passed
        for f, i in side_at.items():
            eff[i].add(f)
        return eff

    def assignment(self, girl, positions):
        """positions: chain id -> stage index that is next (stages before it are passed)."""
        on, off = set(), set()
        for cid in girl["chains"]:
            p = positions[cid]
            for i, fl in self.effects(cid, girl.get("exclude", [])).items():
                (on if i < p else off).update(fl)
        off -= on
        off -= self.external(girl)                     # set by other characters' scenes: leave alone
        for cid in girl["chains"]:
            sf = self.chains[cid]["slot_flag"]
            if sf > 1:
                off.add(sf)                          # the slot's "seen" marker
        return on, off


def event_positions(model, girl, k):
    """Positions for 'event k is next' (k == len(events): everything passed)."""
    pos = {}
    for cid in girl["chains"]:
        mine = [int(e["at"].rsplit(":", 1)[1]) for e in girl["event"] if e["at"].rsplit(":", 1)[0] == cid]
        later = [int(e["at"].rsplit(":", 1)[1]) for e in girl["event"][k:] if e["at"].rsplit(":", 1)[0] == cid]
        if later:
            pos[cid] = later[0]
        elif mine:
            pos[cid] = max(mine) + 1      # past her last listed beat; unlisted tails belong to endings
        else:
            pos[cid] = 0
    return pos


def ending_positions(model, girl, ending):
    pos = {cid: model.end(cid) for cid in girl["chains"]}
    for cid, v in ending.get("chains", {}).items():
        pos[cid] = model.end(cid) if v == "end" else int(v)
    return pos


# ------------------------------------------------------------------------------- drafting
def clean_title(line):
    t = re.sub(r"^[A-Za-z.]+: ", "", line).replace("<player>", "Koh").strip(" .!?,")
    t = re.sub(r"\s+", " ", t)
    return t if len(t) <= TITLE_MAX else t[:TITLE_MAX - 3].rstrip() + "..."


def auto_events(model, name, chains):
    """Order the girls' flagged stages: chain order, with cross-chain 'waits for' dependencies."""
    nodes = []
    for cid in chains:
        for s in model.chains[cid]["stages"]:
            if s["flag"] > 1:
                nodes.append((cid, s))
    setter = {}
    for cid in chains:
        for i, fl in model.effects(cid).items():
            for f in fl:
                setter.setdefault(f, (cid, i))
    order, done = [], set()
    pending = list(nodes)
    while pending:
        for n in pending:
            cid, s = n
            prev_ok = all((cid, t["index"]) in done for t in model.chains[cid]["stages"]
                          if t["index"] < s["index"] and t["flag"] > 1)
            deps_ok = all(setter[f] in done or setter[f][0] == cid for f in s["cond_flags"].get("test", [])
                          if f in setter and setter[f] != (cid, s["index"]))
            if prev_ok and deps_ok:
                order.append(n)
                done.add((cid, s["index"]))
                pending.remove(n)
                break
        else:
            order += pending
            break
    evs, titles = [], set()
    for cid, s in order:
        line = ""
        for sc in s["scripts"]:
            own = [l for l in sc["lines"] if l.startswith(name + ":")]
            if own:
                line = own[0]
                break
            if sc["lines"] and not line:
                line = sc["lines"][0]
        t = clean_title(line) if line else ""
        if not t or t in titles:
            t = "%s scene %d" % (name, len(evs) + 1)
        titles.add(t)
        evs.append(dict(at="%s:%d" % (cid, s["index"]), title=t))
    return evs


def draft(model):
    girls = []
    for name in GIRL_ORDER:
        if name in CURATED:
            c = CURATED[name]
            evs = [dict(at="%s:%d" % (cid, i), title=t) for cid, i, t in c["events"]]
            g = dict(name=name, resolved_flag=RESOLVED[name], chains=c["chains"], exclude=c.get("exclude", []),
                     event=evs, ending=c["endings"])
        else:
            chains = AUTO_CHAINS[name]
            g = dict(name=name, resolved_flag=RESOLVED[name], chains=chains, exclude=[],
                     event=auto_events(model, name, chains), ending=[dict(title="Complete")])
        for e in g["event"]:
            loc = int(e["at"].split(":")[0])
            e["where"] = PLACE.get(loc, "?")
        girls.append(g)
    return girls


def toml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def toml_list(v):
    return "[" + ", ".join(str(x) for x in v) + "]"


def write_toml(girls):
    with open(SRC, "w", encoding="utf-8") as f:
        f.write("""# Story Journal data (in game: talk to Weedy in Koh's house, third answer).
# Per girl: `chains` = her event chains ("location:actor-entry", see re/events/stories.md),
# [[girl.event]] = her story beats in order (`at` = chain:stage, `title` <= %d characters),
# [[girl.ending]] = resolved states. An ending puts every chain at its end unless `chains` says
# otherwise ({"chain" = stage | "end"}); `set`/`clear` = extra flags; `detect` = flags that are all
# set when the game is in this ending (used to show "Complete" in the journal); `face` = her default
# portrait face (otherwise taken from the last scene she has passed, e.g. Selfi 4 = in love,
# Cherrl 7 = nurse).
# `exclude` = flags this girl's story must never touch (e.g. branch choices handled by endings).
# Nico, Selfi and Cherrl are hand-written; Mia, Fur, Vivian and Patty are drafted - retitle freely.
# Rebuild with: python re/scripts/make_journal.py, then rebuild the game.

""" % TITLE_MAX)
        for g in girls:
            f.write("[[girl]]\nname = %s\nresolved_flag = %d\nchains = [%s]\nexclude = %s\n\n" % (
                toml_str(g["name"]), g["resolved_flag"], ", ".join(toml_str(c) for c in g["chains"]),
                toml_list(g.get("exclude", []))))
            for e in g["event"]:
                f.write("[[girl.event]]\nat = %s\ntitle = %s\nwhere = %s\n\n" % (
                    toml_str(e["at"]), toml_str(e["title"]), toml_str(e.get("where", ""))))
            for en in g["ending"]:
                f.write("[[girl.ending]]\ntitle = %s\n" % toml_str(en["title"]))
                if en.get("chains"):
                    f.write("chains = { %s }\n" % ", ".join("%s = %s" % (toml_str(k), toml_str(v) if isinstance(v, str) else v)
                                                           for k, v in en["chains"].items()))
                for k in ("set", "clear", "detect"):
                    if en.get(k):
                        f.write("%s = %s\n" % (k, toml_list(en[k])))
                if "face" in en:
                    f.write("face = %d\n" % en["face"])
                f.write("\n")


# ------------------------------------------------------------------------------- script generation
def fit(s, n=28):
    s = s.replace('"', "'")
    return s if asm.visible_len(s) <= n else s[:n - 3] + "..."


def build_source(model, girls):
    L = []
    emit = L.append
    tag = lambda g: re.sub(r"\W", "", g["name"]).lower()
    emit("start:")
    pages = [girls[i:i + 2] for i in range(0, len(girls), 2)]
    for pi, pg in enumerate(pages):
        last = pi == len(pages) - 1
        emit("menu%d:\n  clear\n  page 1" % pi)
        for g in pg:
            emit("  option \"[%s]\"\n  nl" % g["name"])
        emit("  option \"[%s]\"" % ("Close journal" if last else "More..."))
        emit("  choice %d" % (len(pg) + 1))
        emit("  switch %s, %s" % (", ".join("g_" + tag(g) for g in pg), "close" if last else "menu%d" % (pi + 1)))
    emit("close:\n  page 0\n  clear\n  end")
    for g in girls:
        t, evs, ends = tag(g), g["event"], g.get("ending") or [dict(title="Complete")]
        stage_flag = lambda e: next(s["flag"] for s in model.chains[e["at"].rsplit(":", 1)[0]]["stages"]
                                    if s["index"] == int(e["at"].rsplit(":", 1)[1]))
        flags = [stage_flag(e) for e in evs]
        # --- picker: two choices + More per page; beats first, then endings, then a page to leave.
        # Each choice is marked + passed, > next (first beat not passed), - later.
        items = [("e", i) for i in range(len(evs))] + [("x", j) for j in range(len(ends))]
        ppages = [items[i:i + 2] for i in range(0, len(items), 2)]
        page_of = {it: pi for pi, pg in enumerate(ppages) for it in pg}
        # open on the page holding her next beat (or her endings once every beat has passed)
        emit("g_%s:" % t)
        for i, f in enumerate(flags):
            emit("  if_clr %d, %s_p%d" % (f, t, page_of[("e", i)]))
        emit("  goto %s_p%d" % (t, page_of[("x", 0)]))
        for pi, pg in enumerate(ppages):
            nxt = "%s_p%d" % (t, pi + 1) if pi + 1 < len(ppages) else "%s_nav" % t
            emit("%s_p%d:\n  clear\n  page 1" % (t, pi))
            for kind, k in pg:
                lbl = "%s_%s%d" % (t, kind, k)
                emit("  option \"[\"")
                if kind == "e":
                    emit("  if_set %d, %s_d" % (flags[k], lbl))
                    for f in dict.fromkeys(flags[:k]):
                        emit("  if_clr %d, %s_m" % (f, lbl))
                    emit("  text \"> \"\n  goto %s_t" % lbl)
                    title = evs[k]["title"]
                else:
                    for f in ends[k].get("detect") or [g["resolved_flag"]]:
                        emit("  if_clr %d, %s_m" % (f, lbl))
                    emit("  goto %s_d" % lbl)
                    title = ends[k]["title"]
                emit("%s_m:\n  text \"- \"\n  goto %s_t\n%s_d:\n  text \"+ \"\n%s_t:\n  text \"%s]\"\n  nl" % (
                    lbl, lbl, lbl, lbl, fit(title, 26)))
            emit("  option \"[More...]\"")
            emit("  choice %d" % (len(pg) + 1))
            emit("  switch %s, %s" % (", ".join("%s_%s%d" % (t, kind, k) for kind, k in pg), nxt))
            for kind, k in pg:
                if kind == "e":
                    e = evs[k]
                    pos = event_positions(model, g, k)
                    ask = "[Yes, make it her next beat]"
                    done = (fit("Next: " + e["title"]), fit("Where: " + (e.get("where") or "?")),
                            "Step outside to play it.")
                else:
                    en = ends[k]
                    pos = ending_positions(model, g, en)
                    ask = "[Yes, end her story here]"
                    done = (fit(en["title"]), "Her story is resolved.", "Step outside to apply it.")
                on, off = model.assignment(g, pos)
                if kind == "x":
                    on |= set(en.get("set", [])) | {g["resolved_flag"]}
                    off -= on
                    off |= set(en.get("clear", [])) - on
                else:
                    off.add(g["resolved_flag"])
                    on.discard(g["resolved_flag"])
                emit("%s_%s%d:\n  clear\n  page 1\n  option \"%s\"\n  nl\n  option \"[No]\"\n  choice 2" % (
                    t, kind, k, ask))
                emit("  switch %s_%sy%d, %s_p%d" % (t, kind, k, t, pi))
                emit("%s_%sy%d:" % (t, kind, k))
                face = en["face"] if kind == "x" and "face" in en else model.position_face(g, pos)
                if face is not None:
                    emit("  face %d, %d" % (ACTOR[g["name"]], face))
                for f in sorted(on):
                    emit("  set %d" % f)
                for f in sorted(off):
                    emit("  clr %d" % f)
                emit("  page 0\n  clear\n  text \"%s\"\n  nl\n  text \"%s\"\n  nl\n  text \"%s\"\n  waitbtn\n"
                     "  goto menu0" % done)
        emit("%s_nav:\n  clear\n  page 1\n  option \"[Other girls]\"\n  nl\n  option \"[Back to her first beat]\"\n"
             "  nl\n  option \"[Close journal]\"\n  choice 3\n  switch menu0, %s_p0, close" % (t, t))
    return "\n".join(L) + "\n"


def write_header(blob, relocs, entry, weedy, orig):
    lines = ["/* Generated by re/scripts/make_journal.py from re/events/journal.toml - do not edit. */",
             "#pragma once", "#include <stdint.h>", "",
             "/* Weedy's two-answer menu in Koh's house (overlay program at 0x80016000) as the disc has",
             " * it; the plugin replaces its first 5 bytes with `goto` JOURNAL_WEEDY_OFFSET. */",
             "#define WEEDY_MENU_ADDR 0x%08Xu" % WEEDY_MENU,
             "static const uint8_t WEEDY_MENU_ORIG[%d] = {" % len(orig)]
    for i in range(0, len(orig), 16):
        lines.append("    " + ", ".join("0x%02X" % b for b in orig[i:i + 16]) + ",")
    lines += ["};", "",
              "/* Script VM bytecode assembled at base 0; add the load address at each JOURNAL_RELOCS offset. */",
              "#define JOURNAL_ENTRY_OFFSET 0x%Xu" % entry,
              "#define JOURNAL_WEEDY_OFFSET 0x%Xu" % weedy,
              "static const uint8_t JOURNAL_BLOB[%d] = {" % len(blob)]
    for i in range(0, len(blob), 16):
        lines.append("    " + ", ".join("0x%02X" % b for b in blob[i:i + 16]) + ",")
    lines.append("};")
    lines.append("static const uint32_t JOURNAL_RELOCS[%d] = {" % max(1, len(relocs)))
    for i in range(0, len(relocs), 12):
        lines.append("    " + ", ".join("%du" % r for r in relocs[i:i + 12]) + ",")
    if not relocs:
        lines.append("    0u,")
    lines.append("};")
    lines.append("#define JOURNAL_RELOC_COUNT %du" % len(relocs))
    with open(HEADER, "w", encoding="ascii") as f:
        f.write("\n".join(lines) + "\n")


def main():
    model = Model()
    if "--redraft" in sys.argv or not os.path.exists(SRC):
        write_toml(draft(model))
        print("drafted", SRC)
    with open(SRC, "rb") as f:
        girls = tomllib.load(f)["girl"]
    for g in girls:
        g.setdefault("event", [])
        g.setdefault("exclude", [])
        for e in g["event"]:
            cid = e["at"].rsplit(":", 1)[0]
            if cid not in g["chains"]:
                raise SystemExit("%s: event %r uses chain %s that is not in her chains" % (g["name"], e["title"], cid))
            if asm.visible_len(e["title"]) > TITLE_MAX:
                print("warning: title over %d chars, will be cut: %s" % (TITLE_MAX, e["title"]))
    orig, sure, busy = weedy_menu()
    src = weedy_source(orig, sure, busy) + build_source(model, girls)
    open(ASM_OUT, "w", encoding="utf-8").write(src)
    blob, labels, relocs = asm.assemble(src, 0)
    write_header(blob, relocs, labels["start"], labels["weedy"], orig)
    print("journal: %d girls, %d beats, %d bytes, %d relocations -> %s" % (
        len(girls), sum(len(g["event"]) for g in girls), len(blob), len(relocs), HEADER))


if __name__ == "__main__":
    main()
