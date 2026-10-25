"""Write docs/MODS.md, the reference of every mod and option, from the mod manifests.

    python re/scripts/mods_doc.py

Run it after changing a manifest (features, options, defaults or descriptions) so the page matches
what the launcher shows.
"""
import os, tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACKAGES = [("azure.gameplay", "mods_src/azure_gameplay.c, azure_journal.c, azure_voice.c (C plugins)"),
            ("azure.dungeon", "declarative patches (no C code)")]
OUT = os.path.join(ROOT, "docs", "MODS.md")

# What a feature needs beyond the US disc (README.md -> What you need).
NEEDS = {
    "story-journal": "`prepare.py` run on your US disc (it builds the journal's data).",
    "jp-voices": "your Japanese disc, `prepare.py` (it builds the voice disc and the voice mapping), "
                 "and playing from `disc/Azure Dreams (USA) (JP Voices).cue`.",
}


def option_range(o):
    if o["type"] == "boolean":
        return "on / off"
    if o["type"] == "choice":
        return ", ".join(c["label"] for c in o["choice"])
    return "%s to %s (step %s)" % (o["min"], o["max"], o["step"])


def option_default(o):
    if o["type"] == "boolean":
        return "on" if str(o["default"]).lower() == "true" else "off"
    if o["type"] == "choice":
        return next((c["label"] for c in o["choice"] if c["value"] == str(o["default"])), str(o["default"]))
    return str(o["default"])


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def main():
    L = ["# Mod reference", "",
         "Every mod in this project, with its options as the launcher shows them. Generated from the",
         "mod manifests by `re/scripts/mods_doc.py`; do not edit by hand.", "",
         "All mods start switched off. Open the launcher, click **Mods**, switch on what you want and",
         "set its options. Unless noted, a mod only needs the US disc.", ""]
    for pkg, how in PACKAGES:
        m = tomllib.load(open(os.path.join(ROOT, "mods", "preloaded", "packages", pkg, "1.0.0", "manifest.toml"), "rb"))
        opts = {}
        for o in m.get("option", []):
            opts.setdefault(o["feature"], []).append(o)
        L += ["## %s (`%s`)" % (m["name"], pkg), "", "%s. Made with: %s." % (m["description"].rstrip("."), how), ""]
        groups = []
        for f in m["feature"]:
            if f["group"] not in groups:
                groups.append(f["group"])
        for gname in groups:
            L += ["### %s" % gname, ""]
            for f in (f for f in m["feature"] if f["group"] == gname):
                L += ["#### %s" % f["name"], "", f["description"], ""]
                if f["id"] in NEEDS:
                    L += ["**Needs:** " + NEEDS[f["id"]], ""]
                if f["id"] in opts:
                    L += ["| Option | Values | Default |", "|---|---|---|"]
                    for o in opts[f["id"]]:
                        label = o["label"] + (" — " + o["description"] if o.get("description") else "")
                        L.append("| %s | %s | %s |" % (cell(label), cell(option_range(o)), cell(option_default(o))))
                    L.append("")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L).rstrip() + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
