# Scripts reference (`re/scripts`)

Everything here is Python 3.11+ and is run from the repository root (`python re\scripts\<name>.py`).
Each script's docstring has the details and the exact command line. Setup needs only the standard
library; the developer tools also need `pip install -r re\requirements-dev.txt` (Pillow).

Scripts marked **dev build** talk to the developer build's debug server (build it with
`--diagnostic-dir build-dev`, see [INSTALL.md](INSTALL.md)). They start it with `psx.Game.launch()`
or attach to a running one. **Save state N** means a save state you made yourself at the place
`re/NOTES.md` → *Save states* describes. Save states hold the game's RAM, so none are shipped.

## Setup and generators

| Script | What it does |
|---|---|
| `prepare.py` | One-step setup from your discs: checks the dumps, extracts the files, builds the Story Journal and (with the Japanese disc) the voice disc and voice mapping. |
| `iso_extract.py` | Extracts every file from a MODE2/2352 disc image (`extracted/`, `extracted_jp/`). |
| `town_events.py` | Catalogs every town location, script chunk, speaker, line and story flag → `re/events/town_events.json`, `flags.txt`, `chunks/<lba>.txt`. |
| `town_stages.py` | Extracts each character's event chains (stages, conditions, completion flags) → `re/events/stages.json`, `stories.md`. |
| `make_journal.py` | Builds the Story Journal from `re/events/journal.toml` → `mods_src/azure_journal_data.h`. |
| `town_script_dis.py`, `town_script_asm.py` | Disassembler and assembler for the town event script bytecode (used by the journal; usable for new scenes). |
| `build_voice_disc.py` | Your US disc + the Japanese voice files → `disc/Azure Dreams (USA) (JP Voices).bin/.cue`. |
| `voice_port.py` | Maps every Japanese voice line onto the US script (plus `re/events/voice_overrides.toml`) → `re/events/voices.json`, `mods_src/azure_voice_data.h`. |
| `voice_review.py` | Lists every voice placement (Japanese text next to the English box), or what moved since an older `voices.json`. |
| `voice_where.py` | Shows both scripts around a voice, for writing an override. |
| `make_dungeon_mod.py` | Generates the `azure.dungeon` manifest (floor, item and layout patches); `--custom` takes your own floor table CSV. |
| `mods_doc.py` | Regenerates [MODS.md](MODS.md) from the manifests. |

## Game data and analysis (from your extracted files)

| Script | What it does |
|---|---|
| `dump_tables.py` | Species stats, talents, growth, spells and the EXP curve → `re/data/*.csv` (also needs a dungeon module dump in `re/modules/`, made with the dev build). |
| `levelcalc.py` | Port of the level-up routine: vanilla stat curves per species. |
| `spell_powers.py` | Power and element of every magic damage call. |
| `find_event_tables.py` | Finds every town location's event table. |
| `layout_sim.py` | Port of the floor generator's room placement, for offline layout statistics. |
| `sprite_banks.py` | Decodes the monster and Koh sprite banks in DUNGEON.BIN. |
| `weapon_gfx.py` | Koh's weapon and shield graphics as the game uploads them. |
| `dfun.py`, `dmsg.py`, `species_roles.py`, `species_asm.py`, `species_anims.py`, `species_accuracy.py`, `sp9.py`, `melee_chains.py`, `group_overview.py` | Analysis of the dungeon module and the per-species code chunks. They read Ghidra exports in `re/ghidra/` and module dumps in `re/modules/`, which you make yourself (`re/ghidra/scripts`, the dev build). |

## Test harness (dev build)

| Script | What it does |
|---|---|
| `psx.py` | Client for the debug server: buttons, RAM read/write, screenshots, save states. |
| `attach.py` | Helpers for scripts: town walking, dungeon unit lists, path finding, attacking, the elevator. |
| `ramsearch.py` | Snapshot and diff helpers for finding variables. |
| `journal_drive.py` | Drives the Story Journal's menus in tests. |
| `voice_test.py` | Plays a conversation box by box and reports which boxes were voiced (run on the JP Voices disc). |
| `lodown_test.py` | Fair Level Down bench (save state 3). |
| `enter_tower.py` | Fresh tower entry from save state 0 (needed to test patches to the dungeon module). |
| `layout_test.py`, `floor_render.py` | Floor layout mod configurations end to end; renders the current floor to a PNG. |
| `test_encounters.py` | Dev-only floor tables with chosen monsters. |
| `timeline.py`, `exp_attack.py`, `exp_react.py`, `melee_measure.py`, `melee_familiar.py`, `monster_steps.py` | Frame-exact timing measurements of combat and movement. |
| `turn_capture.py`, `turn_probe.py`, `turn_fntrace.py`, `turn_wtrace.py` | The dungeon's turn system: scenarios, unit fields, function and write traces. |
| `cdmap.py`, `find_overlays.py` | Which disc sectors load where in RAM; locating overlay code inside the disc's archives. |
| `gpu_probe.py`, `vram.py` | Which code draws which primitive; VRAM captures. |
| `grid.py`, `montage.py`, `smoke_shot.ps1` | Screenshot sheets, and window captures of a running exe. |

## Ghidra (`re/ghidra/scripts`)

Headless Java scripts used with Ghidra 12 and the ghidra_psx_ldr loader: loading code modules at their
RAM address, applying symbols, creating and splitting functions, decompiling everything to C.
`re/NOTES.md` records the addresses and what was found.
