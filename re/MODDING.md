# Making Azure Dreams mods

How the mods in `mods_src/azure_gameplay.c` work, and how to add new ones.
Game facts referenced here are in `re/NOTES.md`; data tables are in `re/data/*.csv`.

## Where things live

| What | Path |
|---|---|
| Plugin code (C, compiled into the game exe) | `mods_src/azure_gameplay.c` |
| Feature list, options, labels | `mods/preloaded/packages/azure.gameplay/1.0.0/manifest.toml` |
| Hooked EXE functions | `game.toml` → `[recompiler] mod_function_entry_funcs` |
| Plugin API | `psxrecomp/runtime/include/mod_plugins.h` |
| Enable/configure without the launcher | `build-dev/mods/state.toml` (example below) |

Changes are on the kit's local `azure-mods` branch and are not committed.

## Current features

| Feature | System | Technique |
|---|---|---|
| Second Wind | Koh | VBlank: +1 HP every N frames in the tower |
| EXP Rate | leveling | VBlank: scales the pending-EXP field before the game folds it into total EXP |
| Familiar Growth | leveling | VBlank: on a familiar's level change, adds (pct−100)% of the stats it just gained |
| Talent Inheritance | fusion | VBlank + `psx_mod_write_code_word`: rewrites 3 instructions in the fusion overlay |
| Fusion Absorption | fusion | VBlank: snapshots both familiars; when one slot empties during fusion, adds % of the loser's base stats to the survivor |
| Monster Strength | combat | VBlank: walks the unit list, scales a wild monster while its base ATK/DEF/HP still equal the vanilla spawn values for its species and level (so never twice; HP ≥ 1) |
| Melee Damage | combat | function-entry hook on EXE `FUN_80042900`, filtered to the melee call site |
| Critical Strikes | combat | same hook; random chance to multiply party melee damage |
| Spell Damage | magic | same hook, magic call site (return address 0x8009D0AC); caster read from `s7` |
| Elemental Affinity | magic | same hook; bonus when caster element bits match the spell element |
| Spell Growth | magic | VBlank: on familiar level-up, adds extra levels to spells that grew |
| Spell MP Cost | magic | VBlank: rescales the cast/mixture MP tables in dungeon-module RAM when they read back stock |
| Fair Level Down | gameplay correction | VBlank: snapshot every unit; when a level-down happened (level −k, EXP = T[level]−1), redo the base stats from the snapshot with the real species (frogs: +0xA8), floored at the species' level-1 values |
| Story Journal | town | own script for the game's event VM in plugin memory; Weedy's two-answer menu in Koh's house is redirected (5-byte `goto`) to a copy with a third answer that runs it (`mods_src/azure_journal.c`) |
| Japanese Voices | audio | voice disc (JP voice files appended, stream table patched) + VBlank: patches each voiced US line in the loaded script (town chunk or tower module/species chunk) with a jump to a `yield; stream a b; <line>; goto back` snippet in plugin memory, repoints clip tables, chains the voices of joined boxes, keeps a voice playing through split boxes with a stop-less copy of the button wait (`mods_src/azure_voice.c`; disc check via the framework's new `psx_mod_disc_sector_count()`) |

All of them were verified in the dev build (see the numbers in `re/NOTES.md` → Mods).

### Story Journal (town events per girl)

Talk to Weedy in Koh's house. Her "Do you want to read my Monster Book?" gets a third answer,
**[Show me your story journal.]**, which opens a journal in the game's own dialogue boxes: pick a
girl, then pick where her story stands, either a story beat (it becomes the next thing that happens)
or an ending ("Complete"; Cherrl has two: nurse and doll shop). The picker opens on the page with
her next beat, and every choice carries its state: `+` passed, `>` next, `-` later (endings: `+` when
she is in it). After the page with her endings comes one with [Other girls], [Back to her first beat]
and [Close journal]. Confirming shows one box (the beat and where it plays) and returns to the girl
list. Her flags and default portrait face are set to match; the town picks it up when the next
location loads (step outside). This is saved with the game, so use it knowingly. (Until 2026-10-08
it opened with SELECT in the Monster Hut; until 2026-10-25 each girl first showed a summary box and
her whole beat list, before and after every change.)

- **How it hooks in**: Weedy's question and menu are bytecode in Koh's house overlay program
  (TOWN lba 5071, loaded at 0x80016000; the menu starts at 0x800177C5: `page 0`, two options,
  `choice 2`, `switch`). `make_journal.py` reads those bytes from the disc into the generated header
  and emits `weedy:`, the same menu with a third option, whose first two answers jump back to the
  game's own branches. While the original bytes are resident, the plugin writes `goto weedy` over the
  menu's first 5 bytes; a reload of the overlay restores them, and the next VBlank patches them again.
  The journal ends with `end`, as "too busy" does, so the conversation closes normally. Japanese Voices
  patches Weedy's question just before (up to 0x800177C3); the two don't overlap.

- **Edit the content** in `re/events/journal.toml` (per `[[girl]]`: `chains`, one `[[girl.event]]` per
  beat with `at` = chain:stage, `title` ≤ 26 characters, `where`; `[[girl.ending]]` with chain
  positions, extra `set`/`clear` flags, `detect` flags and `face`), then
  `python re/scripts/make_journal.py` and rebuild. Nico, Selfi and Cherrl are hand-written from their
  scenes; Mia, Fur, Vivian and Patty are drafted from `re/events/stages.json` — rename and reorder
  freely. `--redraft` regenerates the draft (overwrites your edits).
- **Where the data comes from**: `town_stages.py` extracts every event chain (location → actor slot →
  ordered stages with completion flags and the flags their conditions test). `re/events/stories.md` is
  the readable version; `flags.txt` lists where every flag is set, cleared and tested.
- **Writing scripts**: `town_script_asm.py` assembles a small text language (text, options, choices,
  flag tests/sets, jumps, var ops, native calls) into the VM's bytecode with relocations; the
  disassembler `town_script_dis.py` reads any chunk back (`chunks/<lba>.txt` are already dumped).
  `re/events/journal.asm` is a complete example.
- **New events (next step)**: the same pieces cover it. A new scene is an assembled script plus a way to
  start it: point an existing stage's script at it (stage tables are data in the overlay, e.g. replace
  an idle stage's script fn/picker entry with a runtime patch like Talent Inheritance), add an answer
  to an existing menu as the journal does, or start it from MIPS on a condition (location, flags; the
  old SELECT trampoline over dead EXE code worked that way). Gate it with a new story flag (pick one
  unused in `flags.txt`) so the journal and the game both see it.

### Japanese Voices

The Japanese release voices the town conversations and a few tower scenes; the US engine still has
the voice path, but its disc lacks the files and its scripts lack the `stream` ops. Two steps:

1. **Build the voice disc** (once): put `Azure Dreams (USA).bin` and `Azure Dreams (Japan).bin` (from
   your own discs) in `disc/`, then `python re/scripts/build_voice_disc.py` →
   `disc/Azure Dreams (USA) (JP Voices).cue`. It appends the Japanese voice files to the US image and
   points the EXE's stream table at them; nothing else on the disc changes. Play from that `.cue`.
2. **Enable "Japanese Voices"** (group Audio). With the plain US disc the feature does nothing (the
   plugin checks the mounted disc's size).

`python re/scripts/voice_port.py` regenerates the line mapping (`re/events/voices.json`, one entry per
voiced line with the Japanese and English text) and `mods_src/azure_voice_data.h`; rebuild afterwards.
Coverage: 2114 of the 2124 Japanese voiced lines plus all 86 clip-table entries — town lines, the short
clips (item gift reactions, restaurant orders, hospital remarks), the gift reactions, Wreath at the
door, the townspeople met in the tower, Kewne's egg tip and Beldo. The 10 left out are deliberate: 6
have no English line (the translation cut or rewrote them) and 4 are second copies of a line whose
voice already plays.
Where the translation split one Japanese box into several, the voice keeps playing through those
button presses; where it joined boxes, each voice starts on the line where its part begins. Every
placement was read against the English (2026-10-06); `re/events/voices_review.txt` is that listing.

**Fixing a voice** that plays on the wrong line or not at all:
1. Find it: `re/events/voices_review.txt` (`python re/scripts/voice_review.py` regenerates it: each
   voice's Japanese text next to the English box it plays on) or `re/events/voices.json` (`jp_op` is
   the voice); unplaced voices are in `re/events/voices_missing.md`.
2. Look at both scripts: `python re/scripts/voice_where.py "town 5921" --side <JP lo> <JP hi> <US lo>
   <US hi>` prints the Japanese lines with their voice-op addresses and the US lines with the voice
   each currently gets.
3. Add a `[[voice]]` to `re/events/voice_overrides.toml` (`source`, `jp_op`, `us` = the start of the
   English line or `"0x8001xxxx"`, `as` = line / follow / drop, `through = n` to keep it playing
   through the next n button waits), rerun `voice_port.py`, rebuild.
4. Before changing `voice_port.py` itself, copy `re/events/voices.json` aside; afterwards
   `python re/scripts/voice_review.py --diff <copy>` lists every voice that moved, to read through.

Testing: `python re/scripts/voice_test.py <slot> [boxes] [--read N]` plays a conversation box by box on
the dev build (launch it on the voice disc: `Game.launch(disc=VOICE_DISC)` in `psx.py`) and reports per
box whether a voice started, carried over or played a follow-up, with the CD-audio sample count. To
reach an interior without walking: from slot 11 overwrite the exterior's door entry 1 (Koh's house,
`0x8001C1F0` = `{lba, size<<20 | 0x16000}`, list in `re/NOTES.md` → Town events) and walk up; scripts
that wait on actor moves may stall (the driver skips those ops) and the hospital does not load this way.

### `azure.dungeon` (declarative, no C)

Generated by `re/scripts/make_dungeon_mod.py` into
`mods/preloaded/packages/azure.dungeon/1.0.0/manifest.toml` — do not hand-edit the manifest,
change the script and re-run it. Every feature is a guarded `disc_user` patch; option values are
written into MIPS immediates with `replace_from`.

| Feature | What it patches |
|---|---|
| Monster Density | dungeon module: floor-start `rand(4,8)` immediates and the periodic spawn timer (`andi`/`ori` → `andi`/`addiu`) |
| Item Rarity | floor overlay (both disc copies): the 128/85/32/1 tier weights in the category-total builder and the picker |
| Deeper Encounters | the 39 floor sectors: each floor gets the spawn slots of the floor 5 higher (example) |
| Custom Encounters | only with `--custom <csv>`: spawn slots + egg pools from a CSV shaped like `re/data/floors.csv` |
| Room Grid | floor overlay: the `li 2/3/4` grid-size results (2–4 cells per axis; 4×4 is the hard max) |
| Room Frequency | floor overlay: room-vs-junction mask `andi 3` (50% / 75% / 88% / 94% / always) |
| Room Size | floor overlay: `move s8,v0` → `addiu s8,v0,+w`; height base `addiu v0,v0,5` → 5+h |
| Open Floors | floor overlay: `slti v0,v0,2` (of 513) → 0–100% |
| Floor Elevation | floor overlay: 4 × `andi 0x60` → flat / gentle |
| Items per Floor | floor overlay: rooms/2 shift and `rand & 3`/open-floor base → fewer / more / lots |
| Traps per Floor | floor overlay: slot formula as above + trap budget `andi 0x3f` → none / fewer / more / lots |
| Fix: Strength Increased familiars | dungeon module, 1 instruction (verified 88 → 99 damage); group "Gameplay Corrections" like the other fixes |
| Fix: Gaia Shoot element | spell overlay 68, 1 instruction |
| Fix: Barong item rarity | Barong species code, 4 instructions × 7 slot copies |

**Make your own encounter tables:** copy `re/data/floors.csv`, edit species ids (see
`re/data/species.csv`) and levels per slot (16 slots per floor; repeat a species to make it more
common) and the 32-entry egg pools, then `python make_dungeon_mod.py --custom my_floors.csv` and rebuild.

**Floor layout tooling** (all in `re/scripts`, venv Python):
- `layout_sim.py` — offline port of the room-placement step with the game RNG; `summarize(...)` gives
  average room count/area and open-floor rate for any option combination in seconds. Use it before
  picking defaults: bigger rooms always mean fewer rooms, because a room that does not fit its cell
  becomes a junction.
- `layout_test.py [preset ...]` — end to end: writes `state.toml`, launches the dev build, rides the 1F
  elevator (save slot 4), waits until the floor is populated, prints stats (rooms, items, traps,
  monsters, elevator reachable) and renders `re/shots/layout_<preset>.png`.
- `floor_render.py` — `floor_stats()` / `render_floor(name)` for the floor currently loaded.

**Testing disc patches on module code:** save states carry the dungeon module that was in RAM when
they were made, so a patch to the dungeon module only shows up after a fresh tower entry:
`.venv\Scripts\python -c "from enter_tower import *; enter_tower()"` (from town save slot 0).
Floor sectors and the floor overlay are re-read on every floor change, so those patches show up on
the next floor (`take_elevator()` in `attach.py`).

Spell test: from save slot 3, `brid_test()` in `attach.py` frogs the Pulunpa (status 0x0A: it cannot act, DEF halved), orders Kewne
Direct:Brid at it and returns (HP lost, MP spent, traced damage writes). Vanilla result: (7, 10).

## Four ways to change the game

1. **Per-frame state (VBlank plugin).** Read and write guest RAM every emulated frame. Good for
   anything that can react to state changes: stats, inventories, EXP, spawned monsters. Most robust.
2. **Patch module code at runtime (`psx_mod_write_code_word`).** Town/dungeon/overlay code is loaded from
   disc into RAM, so patch it once it is resident: check signature words first, then that the target
   words are still stock, then write. Talent Inheritance is the worked example.
3. **Function-entry hooks on EXE code.** List the EXE function address in `game.toml`
   (`mod_function_entry_funcs`), regenerate (`psxrecomp_cli.py generate`) and rebuild. Your callback gets the
   CPU registers (`cpu->gpr[]`, see `psxrecomp/runtime/include/cpu_state.h`) on every call. Module code that
   calls EXE helpers can be intercepted this way: filter on `cpu->gpr[31]` (return address) to pick the call
   site. Entry hooks run whether or not their feature is enabled, so gate them on a flag set in the
   feature's activation callback.
4. **Declarative manifest patches.** `[[patch]] target = "main_exe"` for EXE bytes (applied before boot),
   `target = "disc_user"` for bytes inside TOWN.BIN/DUNGEON.BIN (applied as sectors are read; offset =
   `file_lba * 2048 + offset_in_file`, DUNGEON.BIN LBA 12310, TOWN.BIN 3077, MAIN.BIN 1817). See
   `psxrecomp/docs/MOD_PACKAGES.md`. No C needed; good for fixed data/code changes.

## Adding a feature

1. Write the callback(s) in `azure_gameplay.c` and register them in `PSX_MOD_CONSTRUCTOR` with a plugin id.
2. Add a `[[feature]]`, its `[[option]]`s and a `[[plugin]]` (that id) to the manifest.
3. Rebuild the dev build:
   ```
   set PATH=%USERPROFILE%\.local\share\retcomm\toolchains\cmake-clang-v1\latest\bin;%PATH%
   cmake --build build-dev --parallel 12 --target psx-runtime
   ```
   (If you added a function-entry address, run `psxrecomp_cli.py generate …` first; see README.md.)
4. Enable it in `build-dev/mods/state.toml`, launch the dev build, and test with the harness.

The framework copies manifests into `<build>/mods/bundled` only when the exe relinks;
`CMakeLists.txt` makes the plugin object depend on every manifest, so a manifest-only edit still
triggers that relink.

### Guard rails used throughout

- `in_tower()` checks dungeon-module code words, `fusion_overlay_resident()` checks the fusion overlay.
  Never touch module addresses without such a check: the same RAM holds the town module in town.
- Clamp byte stats to 0..255; keep "minimum 1 damage" and "never revive" style invariants.
- After changing base stats, call `recompute_max_stats()` (port of the stat half of EXE `FUN_80041E70`).

## Testing with the harness

```
cd re\scripts
python
>>> from attach import *            # talks to the running dev build on port 4370
>>> g.load_state(3)                 # 1F, next to a Pulunpa (slot 2: 1F start, 1: tutorial, 0: tower door)
>>> u = find_units()                # monsters/familiars with grid positions
>>> go_next_to(unit_addr)           # BFS walk next to a unit
>>> face_and_attack(unit_addr)      # melee it
>>> g.read(addr, n) / g.write(addr, bytes) / g.shot("name")
```

- **Fusion test bench:** `g.write(KOH+0xB0, struct.pack('<I', monster))` and
  `g.write(monster+0x14, struct.pack('<I', g.u32(monster+0x14) | 0x4000))`, then Square → Fuse
  (down ×3, Cross, Cross on "Fuse them").
- **Level-up test:** set a familiar's total EXP (+0x18) just under `T[level]` (`re/data/exp_curve.csv`)
  and get one kill.
- `python levelcalc.py <species>` prints vanilla stat curves; compare against what a mod produces.

## Example `build-dev/mods/state.toml`

```toml
format_version = 2

[[package]]
id = "azure.gameplay"
version = "1.0.0"

[[feature]]
package_id = "azure.gameplay"
id = "familiar-growth"
enabled = true

[feature.values]
percent = 200

[[feature]]
package_id = "azure.gameplay"
id = "critical-strikes"
enabled = true

[feature.values]
chance = 15
damage_percent = 200
```

## Good next targets

- Per-spell power edits: the `power` immediates in `re/data/spell_damage_calls.csv` (each row has the
  DUNGEON.BIN offset of its `jal`; the `li a1,N` is within a few instructions before it) — a
  `disc_user` patch can rebalance individual spells.
- Mixture magic strength (`FUN_800B3D10`: attack·L/(L+1)) and the support/status spell overlays.
- The fusion spell-merge rules (`FUN_800277F4`): e.g. sum spell levels instead of taking the max,
  or allow a third slot more often.
- Species data edits (base stats/growth/talents/innate spell) for rebalancing — EXE table at
  0x8006D168 (main_exe patches) and the growth table in DUNGEON.BIN (disc_user patches).
- Town Monster Hut fusion uses town-side code (not yet mapped); the in-tower Fuse command is what the
  fusion mods cover today.
- Dungeon: floor layout parameters in `FUN_80019AF8` (room grid size odds, room sizes), items per floor
  (`FUN_8001E194`), trap counts (`FUN_8001EF0C`), per-species monster AI (code chunks, see NOTES),
  the remaining community-listed bugs (U-Boat Mazarr softlock, level > 99 spawn loop).
