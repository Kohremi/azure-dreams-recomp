# Azure Dreams Recompiled (with mods)

**Azure Dreams** (PlayStation, 1998) running natively on PC, with gameplay mods, tower tuning, a
story journal and the Japanese release's voice acting. It is built on
[azure-dreams-recomp](https://github.com/alexbeavs-ps1-ports/azure-dreams-recomp), a static
recompilation of the game, and keeps that project's history. The reverse-engineering notes and tools
the mods were made with are included.

> [!IMPORTANT]
> **You must own the game and provide your own copy.** This repository contains no game disc,
> BIOS, game code, graphics, audio or script text. Everything the game and the mods need from it is
> generated on your computer from discs you dumped yourself. Do not ask for, share or link game
> files in issues or pull requests.

## What you need

| | Required? |
|---|---|
| **Azure Dreams (USA)** disc image, SLUS-00614 (BIN/CUE, the standard Redump dump) | **Yes** |
| **SCPH-1001** PlayStation BIOS, dumped from your own console | **Yes** |
| **Other Life: Azure Dreams (Japan)** disc image, SLPM-86047 | **Only for the Japanese Voices mod**. Every other mod works without it. |
| Windows 10/11, [Git](https://git-scm.com/), [Python 3.11+](https://www.python.org/) | Yes. The build tools download themselves. |

You do not need both discs unless you want the Japanese voices.

## Install (short version)

In a folder with a short path (for example `C:\Games`):
```
git config --global core.longpaths true
git clone --recursive https://github.com/Kohremi/azure-dreams-recomp.git
cd azure-dreams-recomp
```
Copy your files to `disc\Azure Dreams (USA).bin` + `.cue`, `bios\SCPH1001.BIN` and, optionally,
`disc\Azure Dreams (Japan).bin`. Then:
```
python re\scripts\prepare.py
python psxrecomp\psxrecomp_cli.py generate --config game.toml --project-root . --disc "disc\Azure Dreams (USA).cue" --bios bios\SCPH1001.BIN
python psxrecomp\psxrecomp_cli.py rebuild --config game.toml --project-root . --build-dir build-release --target psx-runtime --exe-basename Azure_Dreams --no-pgo
```
Run `build-release\Azure_Dreams.exe`, pick your disc (the `(JP Voices).cue` for voices), switch on
mods under **Mods**, and press **PLAY**.

**Step-by-step guide, dumping and CHD conversion, updating and troubleshooting: [docs/INSTALL.md](docs/INSTALL.md).**

## The mods

All are off until you switch them on in the launcher. Every option is listed in
**[docs/MODS.md](docs/MODS.md)**.

- **Gameplay:** Second Wind (HP regeneration in the tower), EXP Rate, Familiar Growth, Spell Growth,
  Spell MP Cost, Talent Inheritance (fusions keep all talents), Fusion Absorption, Monster Strength,
  Melee Damage, Spell Damage, Critical Strikes, Elemental Affinity, Fair Level Down (fixes the level
  down underflow and the frog dodge).
- **Monster Tower:** monster density, item rarity, items and traps per floor, room grid, frequency
  and size, open floors, floor elevation, Deeper Encounters, and fixes for three original bugs
  (Strength Increased familiars, Gaia Shoot's element, Barong item rarity).
- **Story Journal:** talk to Weedy in Koh's house and pick *[Show me your story journal.]*. Each
  girl's story beats are listed, marked `+` passed, `>` next, `-` later. Pick the next beat or an
  ending and the town plays it out when you step outside. It changes your save, so use it knowingly.
- **Japanese Voices:** the Japanese voice acting in town and in the voiced tower scenes, on the
  matching English lines (2114 of the 2124 voiced lines). Needs the Japanese disc. Scenes Japan never
  voiced (for example Wreath's "selling items" talk after a tower run) stay silent.

## Documentation

| | |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | installing, updating, troubleshooting |
| [docs/MODS.md](docs/MODS.md) | every mod and option (generated from the manifests) |
| [docs/TOOLS.md](docs/TOOLS.md) | every script in `re/scripts`: setup, generators, analysis, test harness |
| [re/MODDING.md](re/MODDING.md) | how the mods work, how to change them and write new ones, testing |
| [re/NOTES.md](re/NOTES.md) | what is known about the game's internals: units, combat, AI, magic, floors, town events, voices, sprites, input |

## Repository layout

| Path | What |
|---|---|
| `mods_src/` | the mods' C plugins, compiled into the game |
| `mods/preloaded/packages/` | the mods' manifests: features, options, declarative patches |
| `patches/psxrecomp/` | a small addition to the framework's mod API (`psx_mod_disc_sector_count()`), applied automatically when CMake configures |
| `re/scripts/`, `re/ghidra/scripts/` | setup, generators, research and test tools |
| `re/events/journal.toml`, `re/events/voice_overrides.toml` | hand-written inputs for the Story Journal and the voice placement |
| `docs/` | user documentation |
| everything else | the upstream recompilation kit |

Generated from your discs and ignored by git: `disc/`, `bios/`, `extracted/`, `extracted_jp/`,
`generated/`, `mods_src/azure_*_data.h`, the rest of `re/events/`, `saves/`, `build-*`.

## Legal

- Azure Dreams is © Konami. This is an unofficial fan project, not affiliated with or endorsed by
  Konami. It is meant for people who own the game.
- Use it only with discs and a BIOS you dumped yourself from hardware you own.
- No copyrighted game content is distributed. The mod patches contain the new values plus the few
  original bytes needed to check where they apply, as any patch does. A few code comments quote a
  single line of dialogue to identify where a voice belongs.

## Credits and licenses

- **Mods, tools and notes:** Kohremi. GPL-3.0-only, like the kit they build on ([LICENSE](LICENSE)).
- **Recompilation kit:** [azure-dreams-recomp](https://github.com/alexbeavs-ps1-ports/azure-dreams-recomp)
  by Alexbeav, GPL-3.0-only.
- **Framework:** [psxrecomp](https://github.com/mstan/psxrecomp) (fork pinned by the `psxrecomp`
  submodule), PolyForm Noncommercial 1.0.0. `patches/psxrecomp/` modifies it under that license:
  noncommercial use only.
- **Launcher:** [recomp-ui](https://github.com/RetroPortingToolKit/recomp-ui), MIT.
- Third-party notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- Earlier community work this drew on: the decompilation project
  [forestbelton/azure](https://github.com/forestbelton/azure) and the
  [Azure Dreams encyclopedia at adrando.com](https://adrando.com/guide).
- Developed with AI assistance (Claude). The mods were tested in game; the results are recorded in
  `re/NOTES.md`.
