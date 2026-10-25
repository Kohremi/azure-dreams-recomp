"""Prepare the mod data from YOUR OWN discs (run once after cloning, and again after editing the
journal or the voice overrides).

    python re/scripts/prepare.py                       # discs in disc/ (see docs/INSTALL.md)
    python re/scripts/prepare.py --us PATH.bin --jp PATH.bin

Nothing this writes may be committed: it is all derived from the game (.gitignore covers it).

  1. checks the disc images against the dumps the mods were made for (Redump SHA-1)
  2. extracts the US disc's files to extracted/ (and the Japanese disc's to extracted_jp/)
  3. catalogs the town scripts (re/events/) and builds the Story Journal
     -> mods_src/azure_journal_data.h
  4. with the Japanese disc: builds the voice disc (disc/Azure Dreams (USA) (JP Voices).bin/.cue)
     and maps the Japanese voices onto the US script -> mods_src/azure_voice_data.h
  5. touches the plugin sources so the next build compiles them against the new data

Then generate and build the game (docs/INSTALL.md, step 6). Without step 3 or 4 the build still works; the Story
Journal or the Japanese Voices simply do nothing.
"""
import argparse, glob, hashlib, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DISC = os.path.join(ROOT, "disc")

US_SHA1 = "fab68454be5e4e48f7a43ac797cc8c47325c6a20"     # Redump "Azure Dreams (USA)" (SLUS-00614)
JP_SHA1 = "51c7eff6c516ed21dae58fcaf29711dace9b5e1a"     # "Other Life: Azure Dreams" (SLPM-86047), the dump tested
US_NAMES = ["Azure Dreams (USA).bin"]
JP_NAMES = ["Azure Dreams (Japan).bin", "Other Life - Azure Dreams (Japan).bin",
            "Other Life Azure Dreams (Japan).bin"]


def find(names, given):
    if given:
        return given if os.path.isfile(given) else sys.exit("not found: " + given)
    for n in names:
        p = os.path.join(DISC, n)
        if os.path.isfile(p):
            return p
    return None


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def run(script, *args):
    print("\n>> %s %s" % (script, " ".join(args)), flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, script), *args], cwd=ROOT)
    if r.returncode:
        sys.exit("%s failed (exit %d)" % (script, r.returncode))


def extract(bin_path, out_dir, marker):
    if os.path.isfile(os.path.join(out_dir, marker)):
        print("already extracted:", out_dir)
        return
    print("\nextracting %s -> %s" % (os.path.basename(bin_path), out_dir), flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "iso_extract.py"), bin_path, out_dir],
                       cwd=ROOT, stdout=subprocess.DEVNULL)
    if r.returncode:
        sys.exit("extraction failed: " + bin_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--us", help="US disc image (.bin, MODE2/2352)")
    ap.add_argument("--jp", help="Japanese disc image (.bin), for the Japanese Voices mod")
    ap.add_argument("--force", action="store_true", help="continue although the US disc is not the expected dump")
    a = ap.parse_args()
    if sys.version_info < (3, 11):
        sys.exit("Python 3.11 or newer is needed (tomllib)")

    us = find(US_NAMES, a.us)
    if not us:
        sys.exit("Put your own dump of Azure Dreams (USA) in disc/ as \"Azure Dreams (USA).bin\" + .cue "
                 "(a CHD can be converted with chdman: chdman extractcd -i game.chd -o game.cue), "
                 "or pass --us PATH. See docs/INSTALL.md.")
    print("US disc:", us)
    digest = sha1(us)
    if digest != US_SHA1:
        print("warning: SHA-1 %s is not the Redump dump the mods were made for (%s);" % (digest, US_SHA1))
        print("         the patches use fixed file offsets and may not apply.")
        if not a.force:
            sys.exit("stopping (use --force to continue anyway)")
    jp = find(JP_NAMES, a.jp)
    if jp:
        print("Japanese disc:", jp)
        if sha1(jp) != JP_SHA1:
            print("warning: the Japanese disc is not the dump that was tested; the voice mapping may be off.")
    else:
        print("no Japanese disc: skipping Japanese Voices (optional)")

    extract(us, os.path.join(ROOT, "extracted"), "SLUS_006.14")
    run("town_events.py")
    run("town_stages.py")
    run("make_journal.py")

    if jp:
        extract(jp, os.path.join(ROOT, "extracted_jp"), "SLPM_860.47")
        build_voice_disc(us, jp)
        run("voice_port.py")

    for f in ("azure_journal.c", "azure_voice.c"):
        os.utime(os.path.join(ROOT, "mods_src", f))
    print("\nDone. Next: generate and build the game (docs/INSTALL.md, step 6). Play from")
    print('  disc/Azure Dreams (USA) (JP Voices).cue' if jp else '  your US disc', "to use every mod.")


def build_voice_disc(us, jp):
    """US disc + the Japanese voice files -> disc/Azure Dreams (USA) (JP Voices).bin/.cue."""
    import build_voice_disc as bvd
    bvd.US_BIN, bvd.JP_BIN = us, jp
    print("\n>> build_voice_disc.py", flush=True)
    bvd.main()


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    main()
