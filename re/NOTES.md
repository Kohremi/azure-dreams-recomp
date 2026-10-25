# Azure Dreams RE notes

All addresses are PS1 RAM (KSEG0). "EXE" = SLUS_006.14, loaded at 0x8002D000
(text 0x8002D000–0x80081800, BSS after it up to ~0x80088760).

## Disc

| File | LBA | Size | Contents |
|---|---|---|---|
| SLUS_006.14 | 24 | 512 KB (header says 340 KB) | boot EXE: engine, PsyQ libs, CD loader |
| OVMOVIE.BIN | 280 | 3 MB | movie-player overlay (loaded at 0x80176800) |
| MAIN/MAIN.BIN | 1817 | 2.5 MB | title/boot module + shared data |
| TOWN/TOWN.BIN | 3077 | 16 MB | town module, town maps, event scripts, NPC data |
| DUNGEON/DUNGEON.BIN | 12310 | 27 MB | dungeon module, monster code+data, floors |
| STR/*.STR, STRT/*.STR | — | — | FMVs |

The three `.BIN` archives have no table of contents in their headers (all start
with the same `KCET`/`TSDB`/`KDT2` sound bank). Offsets come from tables in code.
Code inside them is stored **raw / uncompressed**.

## Loader

Game loads are queued by EXE `FUN_8003F6D4(sectors, dest, &req, lba)` and serviced by the CD state
machine `FUN_8003E758`; the actual sector DMA happens in PsyQ `CD_getsector` (PC **0x80062970**, which
is the `pc` every entry of the debug server's `dma_cdrom_history` shows). Data sectors are read in
2340-byte mode (12-byte header skipped). Many loads land in a staging buffer at 0x80126804 and get
parsed/copied from there. Archive offsets are computed from constant LBAs in code (no TOC).

## Module map (from CD-DMA tracing, `re/scripts/cdmap.py`)

| Module | Source | RAM |
|---|---|---|
| title | MAIN.BIN +0x21800..+0x28800 (28 KB) | 0x80088760 |
| town | TOWN.BIN +0x00B000..+0x096000 (556 KB) | 0x80088760 |
| dungeon | DUNGEON.BIN +0x0A3000..+0x100800 (374 KB) | 0x80088760 |
| event/script overlays | TOWN.BIN +0x3E5000, +0x3FE000, +0x6F4800 … | 0x80016000 (≤40 KB) |
| dungeon overlays | DUNGEON.BIN +0x2A3000, +0x51E800 (38 KB) | 0x80016000 |
| naming screen (Go End/Back/Forward + name dictionary) | DUNGEON.BIN +0x1830000 (18 KB) | 0x80025000 |
| per-species code (24 KB, see Monster spawning) | DUNGEON.BIN +0xCEF000, +0xD5B000, … | 0x80170800 − slot·0x6000 |
| per-species sprite banks (0x15800 each; see Sprites below) | DUNGEON.BIN +0x1375800 + (species-2) x 0x15800 | 0x800FC000…, 0x8014A000 |
| fusion | DUNGEON.BIN +0x182C000 (16 KB) | 0x80025000 |
| spell effects (72 × 24 KB) | DUNGEON.BIN +0x1834800 | 0x80024000 |
| floor generator | DUNGEON.BIN +0x2A3000 / +0x51E800 (38 KB, identical) | 0x80016000 |
| movie player | OVMOVIE.BIN +0 | 0x80176800 |

The town module begins with a Shift-JIS (full-width) location-name table
("Ｈｏｕｓｅ　６", "Ｗｉｎｄｍｉｌｌ", …); code follows the data.
Monster AI looks modular: each monster type brings its own code chunk
(captured executing at 0x80152000–0x8016E000).

All of this module code currently runs in the psxrecomp **interpreter**
(`overlay_loader_status.dispatch_interp_fallback` in the millions); only the EXE
is native. AOT-compiling the modules is a known next step (psxrecomp
`docs/AOT_SHARDING.md`).

## Game state found so far

| Address | Type | Meaning | How found |
|---|---|---|---|
| 0x80083780 | s32 16.16 | player X (town) — authoritative; writing it teleports Koh | walk-diff + wtrace + write test |
| 0x80083784 | s32 16.16 | player Z (town), "down" = +Z | same |
| 0x80100D98 / +4 | s32 16.16 | Koh's town actor position copy (rewritten every frame by town fn 0x800A48B0 from 0x80083780) | wtrace |
| 0x80100D80.. | struct | Koh town actor: +0x10 next ptr, +0x54/+0x58 callbacks into town code (0x800A5340, 0x800A51CC) | dump |
| 0x80083250 | ptr | → 0x80100DE8 (actor list / player actor) | dump |

### Unit records (Koh, familiars, monsters)

Same leading layout for Koh's record and monster/familiar entities:

| Offset | Type | Meaning |
|---|---|---|
| +0x28 | u8 | current HP (Koh: confirmed by write → HUD) |
| +0x29 | u8 | max HP (confirmed → HUD "MAX") |
| +0x34 | 12 bytes | name, full-width Shift-JIS, padded with `81 40` |
| +0x50 | ptr | status/effect record (first byte 0x0B checked by drain logic) |
| +0x64 | s16 | HP adjustment; dungeon code treats `u8[+0x28] + s16[+0x64]` as effective HP |
| +0xAC | ptr[] | (Koh) familiar entity pointers; [0] = Kewne |
| -0x14 | ptr | map object; its +0x24/+0x25 are grid tile x/y |

- **Koh = 0x800834B8** (fixed, EXE BSS). The dungeon module keeps this pointer in `DAT_800E3D7C`.
- Kewne (first familiar) was at 0x801EC490 on 1F (heap; read it via Koh+0xAC).
- Natural HP regen ≈ +1 per several steps.

### Full unit record layout (familiars, monsters, Koh)

From the species constructor (EXE `FUN_80042640`), the level-up routine, the stat
recompute (EXE `FUN_80041E70`) and the unit copier (EXE `FUN_80042710`):

| Off | Type | Field |
|---|---|---|
| +0x00 | u8 | base ATK |
| +0x01 | u8 | base DEF |
| +0x02 | u8 | stat2 (grows with level; role not yet confirmed) |
| +0x03 | u8 | stat3 (grows with level; role not yet confirmed) |
| +0x04 | u8 | base max MP |
| +0x05 | u8 | base max HP |
| +0x06 | u16 | EXP this unit gives when killed (recomputed each level) |
| +0x08/+0x09/+0x0A | u8×3 | spell slot 1: spell id, effective level, base level |
| +0x0B/+0x0C/+0x0D | u8×3 | spell slot 2 |
| +0x0E/+0x0F/+0x10 | u8×3 | spell slot 3 |
| +0x11 | u8 | level (1..99) |
| +0x13 | u8 | species id (0 = Koh) |
| +0x14 | u32 | flags: bits 0-2 element (1 fire, 2 water, 4 wind), 0x4000 party member, 0x2000 … |
| +0x18 | u32 | total EXP; levels up while `T[level] <= exp` |
| +0x1C | u32 | status flags |
| +0x20 | s16 | attack power (transient, built per attack) |
| +0x22 | s16 | defense value (transient, DEF + armor) |
| +0x24 | u8 | 0xFF |
| +0x25 | u8 | current MP |
| +0x26 | u8 | current ATK |
| +0x27 | u8 | current DEF |
| +0x28 | u8 | current HP |
| +0x29 | u8 | max HP (= base HP, ×2 with HP+ talent) |
| +0x2C..+0x33 | 4×(u8 id, u8 value) | active status effects (lookup: EXE `FUN_80042900(unit, id)`) |
| +0x34 | 13 bytes | name |
| +0x41/+0x42 | u16 BE | pending EXP, folded into +0x18 by the game shortly after |
| +0x54 | u32 | talents (see below), seeded from species table 2 |
| +0x5C | ptr | next unit − 0x20 (circular list; head pointer at 0x800814A8 = Koh) |
| +0x60 | ptr | current target / last attacker |
| +0x64 | s16 | pending HP change from the current hit |
| +0x66 | u8 | max MP (×2 with MP+) |
| +0x68 | u8 | max ATK (×2 with Strength+) |
| +0x69 | u8 | max DEF (×2 with Hard) |
| +0x9A/+0x9B | u8 | action state / sub-state (0x28 = fusing) |
| +0xAC/+0xB0 | ptr | (Koh) familiar slots |
| −0x14 | ptr | map object: +0x24/+0x25 grid x/y |

Talent bits (+0x54), from the fusion overlay's "Talented with" list and the recompute:
0x1 Quick · 0x2 HP Increased (max HP ×2) · 0x4 MP Increased · 0x8 Strength Increased (ATK ×2) ·
0x10 Hard (DEF ×2) · 0x20 Growth Promoted (double EXP when it scores the kill) ·
0x40 victim gives double EXP · 0x80 Magic Attack increased (spell level ×2) ·
0x100 MP Consumption Decreased · 0x4000 "Lowering ATK may not work" · 0x8000 Electric Shock ·
0x10000 Rustproof · 0x100000 Unbrainwashable · 0x200000 Atrocious ·
0x400000 always absorbed in fusion · 0x800000 always survives fusion (Kewne) ·
0x2000000 Sleep-proof · 0x4000000 Confusion-proof · 0x8000000 Blinder-proof ·
0x10000000 Paralysis-proof · 0x20000000 Poison-proof · 0x40000000 Spell-proof.

### Species / growth / spells / EXP (dumped by `re/scripts/dump_tables.py` → `re/data/*.csv`)

- **Species table** EXE 0x8006D168, 0x18 bytes × 48: the first 0x14 bytes are copied verbatim into a new
  unit (base ATK/DEF/stat2/stat3/MP/HP, EXP value, innate spell, level 1, species id), +0x14 flags.
- **Species talents** EXE 0x8006D6D8, u32 × 48.
- **Species names**: egg item entries at EXE 0x80072794 + id×0x14 (+4 name, +8 description).
  0 Koh, 1 HIKEWNE, 2 KEWNE, 3 DRAGON, 4 KID, 5 IFRIT, 6 FLAME, 7 GRINEUT, 8 GRIFFON, 9 SABER,
  10 SNOWMAN, 11 ASHRA, 12 ARACHNE, 13 BATTNEL, 14 NYUEL, 15 DEATH, 16 CLOWN, 17 UNIVERN, 18 UNICORN,
  19 METAL, 20 BLOCK, 21 PULUNPA, 22 TROLL, 23 NOISE, 24 U-BOAT, 25 BALOON, 26 DREAMIN, 27 BLUME,
  28 VOLCANO, 29 CYCLONE, 30 MANOEVA, 31 BARONG, 32 PICKET, 33 KRAKEN, 34 WEADOG, 35 STEALTH, 36 VIPER,
  37 NAPLASS, 38 ZU, 39 MANDARA, 40 KILLER, 41 GARUDA, 42 GLACIER, 43 TYRANT, 44 GOLEM, 45 MAXIMUM.
- **Growth table** dungeon module 0x800DDCBC, 8 bytes × species: g_atk, g_def, g_2, g_3, g_mp, g_hp, g_exp, —.
  (On disc: DUNGEON.BIN +0xA3000 + 0x5555C + id×8.)
- **Spell table** EXE 0x8006DE24, 0x14 bytes × id: +0 name, +4 description, +0x10 byte = category<<4 | element
  (category 1 attack, 2 "De-" support, 4 status; element 1 fire, 2 water, 4 wind). Spells come in triples
  X / NeaX / NoaX = fire / water / wind (ids 3k+1, 3k+2, 3k+3).
- **EXP curve** built at boot by EXE `FUN_80043674` into 0x800835E8 (u32 × 100):
  `T[L] = T[L-1] + (L+3)^3 / 8 + (L > 20 ? 32·(L-20)^2 : 0)`.

### Leveling (dungeon `FUN_800A1D4C(unit, show_message)`)

For old level L (new = L+1), species base b[] and growth g[], each stat follows a curve and gains `f(L) − f(L−1)`:
- max HP: `b5 + g5·L/16 + g5·sqrt12(L·g5·2048)/32768`  (applied to +0x05 and +0x28)
- max MP: `g4·b4·L/1024` (+0x04, +0x25) · ATK: `g0·b0·L/64` (+0x00, +0x26) · DEF: `g1·b1·L/64` (+0x01, +0x27)
- stat2: `g2·b2·L/64` · stat3: `g3·b3·L/1024`
- EXP value: `e + L·e + L²·(e + g6·L)/512` with e = species EXP value
- each spell whose category matches the unit's element bits gains a level, plus `(99−lv)/(100−L)` more
  (so low-level units gain spell levels faster).
- Wild monsters are created at level 1 and pushed through the same routine, so changing the growth table
  also changes monsters. `re/scripts/levelcalc.py` reproduces the curve.

**Level down** — dungeon `FUN_800A2424(unit, show_message)` (LoDown hit `0x8002410C` in spell overlay 41,
and `0x800C33EC`): level −1 (not below 1), EXP = T[level]−1 (T at 0x800835E8), each base stat (+5 HP, +4 MP,
+0 ATK, +1 DEF, +2, +3) loses f(L)−f(L−1) of the **current** species (+0x13) — the level-up gain of the
level taken back — guarded only against a result of exactly 0 (so it wraps), EXP value +0x06 recomputed,
elemental spells −1 level, `FUN_80041E70` max stats, current HP/MP/ATK/DEF clamped. LoDown's hit roll:
`FUN_800A6DA4(0, unit+0x03) − 16 < spell level` (level 255 always lands), after the `FUN_8009D218` immunity
check. Frog status (10) swaps the species byte to FROG (46, zero growth) and keeps the real species at
**+0xA8** (restored by status-off handler EXE 0x80042E6C), so frogs lost nothing; Battnel (13) gains ~2.2
ATK/level vs Nyuel (14) ~1.2, so an evolved Battnel wraps to 255 (community bug list). Fixed by the
Fair Level Down feature.

EXP flow: kill → dungeon `FUN_800A2DB8` splits the victim's EXP value (×2 per Growth/victim talents)
evenly between Koh and living familiars (rounded up; ×2 for a unit lower-level than the victim) →
`FUN_800A2D68` adds it to pending +0x41/+0x42 → the game folds pending into +0x18 and runs level-ups.

### Fusion (overlay DUNGEON.BIN +0x182C000, 16 KB, loaded to 0x80025000; Square menu → Fuse)

Fuses the two familiars currently with Koh. State machine `FUN_800253C0` (Koh+0x9A = 0x28, sub-state +0x9B).
- `FUN_800280F4(A, B, &element)`: both have 0x800000 → "rejected each other". Survivor = the one with 0x800000,
  or the other one if one has 0x400000, else higher level, then higher total EXP, then coin flip.
  Element = dominant one (water beats fire, wind beats water, fire beats wind).
- `FUN_800277F4(A, B, preview)`: survivor W keeps its level and stats. Element ← result. Spells: up to 2 (3 if
  either has a third slot) picked alternately from W and L; matching families keep the higher level; every
  kept spell is converted to W's element variant. No spells at all → species starter spell from 0x800287B4.
  Talents: `W = (W & innate[W]) | (innate[L] & L)` (so fused-in talents don't stack). MP averaged.
  Loser destroyed. The Fuse menu shows a preview first (same function with a scratch unit).
- `FUN_80028208` prints "Talented with …".

### Combat (dungeon melee `FUN_8009C12C(attacker, …)`; reached through an action table)

- defense = DEF(+0x27) + armor (`FUN_80098250`), halved if the defender is a frog (status 0x0A), min 1.
- attack power (+0x20, built earlier; weapon element enchant in `FUN_800B3D10`).
- element modifier m (eighths): advantage +1, disadvantage −2; element shields quarter the attack.
  height: d = attacker +0x88 − target +0x88 (s16, down positive); d ≥ 0x20 (attacker a step lower) −1,
  d ≤ −0x20 (attacker a step higher) +1 (re-read 2026-10-23; the port's `Combat.melee` matches). No
  other height term, and no species handler changes the damage by height (their height reads move the
  sprite: Golem's slam, Battnel's swoop; see "Monster steps"). attack += attack·m/8, then
  + (attack/8)·k from `FUN_800C82B8`.
- hit roll first, `FUN_8009C93C(attacker, …)`: finds the target in front (`FUN_8009B25C`, which skips
  units failing `FUN_800A41F0`: HP(+0x28) + pending(+0x64) must be > 0, so a live unit at 0 HP cannot be
  hit), then hits when attacker+0x84 (weapon accuracy, tables 0x800DD2C4 / 0x800DD2E0, set on equip)
  + 4·(rand % attacker+0x03) > 127, or always when the target sleeps/is bound (+0x1C & 0x238). +0x03 is
  the species table's 4th byte (accuracy: Koh/Hikewne 100, Pulunpa 50), growth 0 except Barong. A miss
  leaves attacker+0x14 bit 0x4000000 set and melee prints MISS. Critical: rand & 0x7F ≤ +0x03 >> 6
  (>> 1 with +0x1C & 0x1000). The attack power and mixture magic are only applied on a hit.
- pending HP change (+0x64) = (defense − attack)/2, ×1.5 on a critical (+0x1C & 0x1000000); ≥ 0 → −1.
- then `FUN_80042900(defender, 0x1D)` is called from 0x8009C65C (our mod hook point), message
  "<name> received N damage", popup `FUN_800B4C7C(3, …)`.
- Poison tick: dungeon `FUN_800A5DFC` — lose (maxHP+15)/16 per turn, never below 1 HP.

**Melee, exact order** (checked draw for draw against the dev build, `azure-tower-godot` combat_test):
`FUN_8009C93C` draws (a chaos unit's random direction first, then) r1 hit: acc = +0x84 + 4·(r1 % +0x03);
Koh's Leather Shield (item 17/2) on the defender takes acc −= acc>>2; hit if acc > 127 or the target is
helpless (+0x1C & 0x238 = paralysed 0x20 / asleep 0x200 / blind 0x10 / out of MP 0x08). r2: attack =
(r2&1) + ((r2&2)≠0) + 2·(ATK + weapon power), weapon power = `FUN_800981F8` (+0x85 + the weapon's +N,
0..99). r3: critical. A helpless target costs one more draw. The target turns to face the attacker.
Accuracy/power on equip (`FUN_800982A8`): swords 0x800DD2C4 / 0x800DD2B4, wands 0x800DD2E0 / 0x800DD2D4,
shield 0x800DD2EC → +0x86. Monsters store +0x84/+0x85 in their own chunk right before the swing
(`re/scripts/species_accuracy.py`): 124/0 for most; Death and Golem 124/4, Killer 124/8, Troll by its
weapon (+0x48: 13 club 120/8, 14 hammer 112/2, 15 bow gun 116/1); Dreamin 16/16 and Mandara 40/16 specials.
Damage (`FUN_8009C12C`): mixture magic (`FUN_800B3D10`) first, then defense (Troll's club 0xF0D skips the
shield), elements fire/water/wind in order (wall statuses 0x13/0x14/0x12 → attack>>2, else weak +1 /
resist −2), height ±1 at 0x20, attack += attack·m>>3, d = (def−atk)/2 truncated, crit d += d/2, d ≥ 0 → −1.

### Dungeon turn loop (decompiled 2026-10-10)

Everything runs from Koh's object update `FUN_80089AA0` (task list `FUN_800897E4`), driven by phase flags
`DAT_80083462` and counters 0x80083468 (units still walking), 0x8008346C (unit holding the exclusive
action: an attack, a cast), 0x80083470, 0x8008346A (pending animations), 0x80083474.

**Action points.** Each unit has an 8.8 counter at +0x6C (whole actions = +0x6D) and a speed at +0x6E:
0x100, ×2 with the Quick talent (+0x54 & 1), then ×2 with status 7 > 0 (fast) or ÷2 when < 0 (slow) (EXE
`FUN_80041E70`). When Koh *starts* an action (every turn-taking Koh handler, e.g. the step at
`FUN_8008B9FC`), `FUN_80099F70` then `FUN_80099F04` refill the party (+0x14 & 0x4000) then everyone else, in
list order: `FUN_80099EA4` sets +0x71 = 0x80 ("must decide"), clears +0x41/+0x42, +0x1C bit 31 (deferred
this turn) and +0x14 bits 31/0x10000/0x8000 (once-a-turn rolls), and adds `speed × DAT_80083460 >> 8`.
DAT_80083460 is Koh's turn length, set at the end of each turn from Koh's status 7: 0x80 fast, 0x100
normal, 0x200 slow — so a slowed Koh gives everyone two actions, a fast one half.

**Phases** (Koh's update; units are visited in list order through +0x5C, the unit's update at object +0x10):
1. Koh's action sets 0x812 (2 = turn taken, 0x800 = decide pending). A **swing** is different: its start
   (`FUN_8008C8BC`) takes the exclusive slot, sets 0x400 and refills only the party (a familiar can join
   with mixture magic); its end refills the monsters and sets 0x412. With 0x400 the unit loop runs in
   normal mode first — an **act-first phase**: every unit with actions that can hit or cast does so at
   once (one at a time), sleepers and exhausted units pass, units that would move wait (their plan
   choice still runs: rolls are drawn here) — and only when a whole loop starts no action does 0x400
   become 0x800. A move plan set here (0x800B) is kept, so in the decide phase the unit walks it without
   choosing again.
   Koh's **flat step** (`FUN_8008C13C`, `FUN_8009ABA0` = 1) goes to state 0x1D and sets 0x812 at once,
   refilling everyone, so the others decide and walk *during* his 16-frame step and a held direction
   walks on without a pause until a unit acts (a blow or a spell holds the turn); a step up or down
   (2-4) plays state 0x1E first unless DAT_80083462 & 0x80 is set (Circle held and no awake unit
   within 5 tiles, or demo mode). The port plays every walk at once and waits for them only before a
   blow / spell and at the turn's end.
2. 0x800 and nothing busy → 0x2000 **decide**: each unit's update is called, pass after pass, while any
   unit still has +0x71 bit 7 and action points. A unit without a plan first moves itself to the end of
   the list once a turn (`FUN_8009A180`, +0x1C bit 31) and decides when the pass reaches it there; units
   that don't (asleep, out of MP, standing on Koh's tile, holding a plan) stay put, so the list order
   changes for good (sleepers drift forward). A pass with a deferral always forces one more pass, in
   which everyone with actions left re-runs its plan choice (no new draws). Deciding units *plan*
   their steps — the map object's tile changes at once (so later units see it), the path goes into the
   +0x74/+0x7C history, +0x71 low bits count the steps, +0x6D−1, 0x80083468+1 — and a unit with two
   actions plans two steps. Units that can attack/cast clear bit 7 and wait. Then `FUN_800A9AFC` puts
   each walker back on its first tile and the phase becomes 0x1000.
3. 0x1000 **walk**: every planned path is walked at the same time (+0x96 = 8 ticks / steps, state 0xF;
   a step up is a hop, state 0x10, and when it lands a monster chasing Koh turns to him). Each step costs
   4/256 MP and a status tick. Koh and familiars set off traps they end on (monsters were not seen to);
   traps 15/16 reshape the floor polygons — the tile grid's height field (s16[1]) is not updated, units'
   +0x88 follows the polygons.
4. When the walkers are done (0x80083468 = 0) → 0x4000 **act**: units that still have action points act
   one at a time in list order, round after round (a unit with two actions left acts again after the
   others): the plan is chosen again on the new positions; melee (state 0x11, costs 0x100 = 1 MP, then
   a status tick) or a spell; a unit that would move now attacks what it faces or passes. Passing (`FUN_800A9A0C`) burns every remaining action point, each costing 4/256 MP (not when
   already out of MP) and a status tick.
5. Everything idle and flag 2 → **end of turn** (top of `FUN_80089AA0`): spawn tick (0x800A0DD8); Koh's turn
   length from status 7; turn counter 0x8008347E +1; Koh's HP regen: acc 0x800E3D70 += max HP, +1 HP per
   0x100 while acc > 0x100 (capped at max); familiars likewise (accumulators 0x800E3D78 for slot 1,
   0x800E3D74 for slot 0) but only while their MP (+0x25) ≠ 0; Koh+0x03 (the accuracy byte) =
   (rsin(t)>>7)+64 (cursed, +0x1C & 0x800: (rsin(t)>>8)+48), t = Koh+0xF8 counter (+1 per turn; 4096 = one
   cycle; checked: t 525 → 87); Koh+0x128 = rand & 0xFFFF (tie-breaks below); Koh+0x118 +1; Koh's status tick
   `FUN_800A4ACC`; the frog control swap.

**Status slots** (+0x2C..+0x33, 4×{id, value}): `FUN_800A4ACC` moves each value one toward 0 per tick
(value 0 = permanent) and clears the slot at 0 (`FUN_80042BDC`, status-off). Id 5 (poison) deals its
damage in the tick. Ids → +0x1C bits: 1 sleep 0x200, 2 chaos 0x400, 3 blind 0x10, 4 paralysis 0x20,
5 poison 0x40, 6 seal 0x80, 7 speed (±), 8 0x800, 9 critical 0x1000, 10 frog. +0x1C 0x08 = out of MP.
Monsters tick once per action point spent (step, swing, pass), Koh once per turn.

**MP** (u16 8.8 at +0x24, `FUN_800AD594(unit, cost)`): every non-Koh unit pays — wild monsters too (a
Pulunpa read live at 0x1DF3/40) — 4 per step or passed action, 0x100 per melee swing; at 0 the unit goes
to state 5 (+0x1C |= 8): it stands passing until fed. Units with MP < 64 walk to a food item in their
room (`FUN_800A6E8C`, item class 0x60C = Meat, 12/6) and eat it on arrival (`FUN_800A70E4`; the MP it gives
isn't found yet). (The plan's direction toward it is overwritten by the move code, so only standing on it
matters.) Exception: the 1F tutorial's Kewne runs chunk 0x39, whose hit reaction puts HP back to 1.
Level-up (`FUN_800A1D4C`): each base stat grows (capped at 255) and the current value gains what the base
actually gained, as a byte, without talent doubling; max HP is capped at 255 even with HP+. Troll: its
constructor (chunk 22 `FUN_80171D64`) arms it by spawn level — hammer 0xE below 10 (accuracy 112, power
2), bow gun 0xF at 10-12 (116/1; its shot down a line, `FUN_80173734`), club 0xD from 13 (120/8, ignores
shields). Fixed floors (0x800E296C & 0x10000000, the tutorial) have no random spawns.

### Dungeon AI (generic code; each species chunk has a copy of the control function)

Control (Pulunpa `FUN_80170F28`, object +0x8C; the update `FUN_80170AE0` only calls it during 0x2000):
MP 0 → exhausted; asleep (+0x1C & 0x200) → state 0xD: passes, and each turn wakes with rand&7 == 0 when
in Koh's room or within 1 tile of Koh; paralysed (0x20) → pass; else, with action points left and no
plan: plan choice `FUN_800ADE74` →
- 0: pass. 1: plan set (+0x46 = 0x8000 | code: 1–3 spell slot, 5–7 mix slot, 8 melee, 9 special,
  0xB move, 0xC pass) — waits for the act phase. 2: move (`FUN_80171468`).

**Chase flag** +0x1C & 0x20000 (`FUN_800A19E4(obj, unit, 3, 6)`): set when the unit is in Koh's room or
within 2 tiles (Chebyshev < 3); cleared when it is outside Koh's room and ≥ 6 away, or blind.

**Plan choice** `FUN_800ADE74` for a monster: MP 0 → 0; hungry (MP < 64) and food in the room → walk to it;
blind or in a "sealed" room (room flag 2) → move; low HP (HP ≤ maxHP/((level>>1)+2)) and a heal spell →
heal itself (4); species special (switch on +0x13, mostly a once-a-turn roll `FUN_800ADD20(unit, n)`:
rand % n == 0); then the **target** `FUN_800A3D18(obj, unit, 2)`: the nearest hostile unit in the same
room (any distance; in a corridor only adjacent), or any hostile adjacent across a room edge — Koh is
compared separately: the nearer of Koh and the best other is taken; on a tie the other wins unless it is
out of MP or (Koh+0x128 + unit+0x43) & 3 == 0. With a target, `FUN_800A384C(unit, target, &dir, 1)`:
- height difference ≥ 0x40 → nothing (move);
- once a turn (+0x14 & 0x10000) the cast mode +0x98 bit 0 is rolled: within 16 tiles of Koh, and (a party
  unit, or never cast before (+0x98 & 0x10 clear), or rand&0xF == 0), and rand&3 == 0, and not sealed;
- cast mode: slots from (turn counter & 3) (3 wraps to 0); a spell qualifies when its effect (+0x11) < 0x12,
  the target doesn't already have that status, distance ≤ range (+0x13), and for line spells (+0x12 == 1)
  the target is in one of the 8 lines with no unit of the caster's own side in between; best element score
  `FUN_800A35D8(spell element, caster's own element)` wins;
- adjacent (Chebyshev 1, diagonal corners open) → the chosen spell if any, else melee 8.
No usable action → plan 0xB, move.

Familiars (+0x1C & 0x2410 == 0x2000) by mode +0x12 (order command 0x78; default 2): heal Koh / the other
familiar when their HP is low and in range; mode 0 fights anything in the room (melee or spells, target
range 4 in corridors), 1 melee only within 3, 2 follows and **mixes its best spell (highest level, then
element advantage over the target) into each of Koh's swings at a monster** (plan 5–7, one familiar per
swing), 4 only hits adjacent enemies and otherwise passes, others just follow. +0x45 = formation slot
around Koh (command 0x90), +0x46 one-shot order (command 0x80, "Direct:<spell>").

**Movement** `FUN_80171468` (decide phase): direction +0x2A (0x200 per 45°; dir 0 = +x, 2 = +y; dx/dy
tables EXE 0x8006CCD8/0x8006CCE8). Chasing monster → face Koh (`FUN_800A0818`: ratan2 rounded to 8
directions; bit 2 of +0x98 set when the true angle is on the counter-clockwise side). Not chasing →
**wander** `FUN_800A0E6C`: in a corridor turn to dir−1 if that tile is open; on entering a room pick a
random exit (rand % count, scanning on) other than the one entered by; on reaching it pick the next by
turn counter; otherwise head for the exit with the three backward directions barred. Familiar following
Koh → head for Koh's tile + offset (formation slot + Koh's facing). Then try the direction and its
rotations 0, +45°, −45°, +90°, −90°, +135°, −135°, 180° (EXE 0x8006CD00; negated with +0x98 bit 2), the
first open tile wins (`FUN_8009A66C`, see the ground rule below; no unit there; a monster can't step from
a corridor into a sealed room); a familiar next to Koh gives up after the first three. All eight blocked
→ pass. Confused (0x400): attacks any adjacent unit (scan from turn counter & 7), else turns randomly
once a turn and walks. Blind (0x10): attacks what it faces, else walks on.

**Ground rule** (`FUN_800BCB04(x, y, ref)`: the highest floor surface on the tile not more than 0x20 above
ref, else 0x400): a step may go up one step at most and down any height (pillar pits are barred by their
tile flag 0x8000; flags 0x8402 bar a tile); a diagonal (`FUN_8009A540`) is blocked only by a side tile
that *exists* and has no ground within a step — a wall; empty space beside a corridor doesn't block. The
corridor wander's "open" is the same probe. Koh moves by the same rule (`FUN_8009ABA0`), and may step onto a
party member that isn't helpless/confused (+0x1C & 0x628) and will have an action this turn: it doesn't
move; it is on Koh's tile when the decide phase reaches it, skips the deferral and steps off (following
him), spending that action.

**Hit routine extras** (`FUN_8009C93C`): a confused attacker (Koh too) swings in a random direction once
a turn (dir += (rand & 7)·45°, +0x14 bit 31) at whatever stands there; the target turns to face the blow
(attacker's direction + 180°) unless it is Koh, helpless or holding a plan. Koh's hit reaction
(`FUN_8008CAA0`, state 7) draws once and on an even result shakes off sleep, paralysis and confusion;
other units' reactions draw nothing, and a hit doesn't wake a sleeping monster.

**Species switch** (`FUN_800ADE74`, after the self-heal check): Saber/Snowman, Pulunpa (floor 10+ form,
+0xA7), Noise (roll 16), U-Boat (2+ tiles from Koh: roll 8 → plan 0xA, a dive that changes how it moves
— its own chunk), Baloon (roll 16, Koh in front and its HP low → 0xA), Dreamin (roll 2, marks its blow),
Blume (4), Volcano (32, chasing), Cyclone (8), Picket (2), Weadog (32), Stealth (4), Viper (eggs in the
room), Naplass (32), Zu (2), Mandara (16), Killer (64, marks its blow), Garuda (16), Glacier (4), Tyrant
(32), Golem (4) → plan 9 (usually) or 0xA. The roll (`FUN_800ADD20`) is drawn once a turn whenever the
switch is reached, so it matters to the random sequence even when the move doesn't happen.

Room records (0x800E2970, 0x14 bytes, from the floor generator): x, y, w, h, —, active, flags (1 visited,
2 sealed), exit count, exit list ptr (0x800E2C40 + room·0x40, 4 bytes each: x, y, u16 kind). On generated
floors the exits are the corridor door points, added by the corridor digger (floorgen `FUN_8001AC4C` →
`FUN_800177D8`, kind 0), in digging order; fixed floors (the 1F tutorial) load hand-made lists with kinds
(`FUN_80018464`). Kinds: from a kind-0 exit any of kind 0/1 will do, from 1 only 2, from 2 only 0.

**Spawns** (`FUN_800A08A0(kind)`): unit count < 0x20; up to 16 tries: a random free tile (`FUN_800A4E2C`:
room = rand % count, x = rand % w, y = rand % h, 256 tries; flags & 0xF720 clear — no unit, item, trap,
stairs or pit); the periodic spawn (kind 0) must be more than 32 tiles (|dx|+|dy|) from Koh; slot =
rand & 15 of the floor table (pointer 0x80083478, 16 × {species, level}); the species constructor sends it
to sleep half the time (rand & 1, then (rand & 0x3F) | 0x20 ticks; facing 0); +0x43 = rand (the target
tie-break byte); levelled up to the slot's level. Floor start (`FUN_800A69E4`): n = rand 4..8; 16 hidden
preloads (kind 2..17, one per slot) then n × kind 1 (no distance rule). The spawn timer (0x80083466) starts
at rand & 0xF (floorgen `FUN_80018A70`, the first draw after seeding) and is reset to (rand & 0x1F) | 0x20
when it runs out (end of turn, `0x800A0DD8`).

**Checked against the game** (`re/scripts/turn_capture.py` records turns on the dev build — floor, rooms
and exits, spawn table, every unit, random state — before and after each of Koh's moves;
`turn_replay.py` replays each turn through the Godot port from the game's own "before" and compares tiles,
HP, MP (8.8), action points, facing and the random state): 1F tutorial, a modded 2F and fresh 2F floors,
with Koh slowed, confused and blind monsters, a Quick monster, familiar orders 0/2/4, Koh's swings with
mixture magic, kills and level-ups, spawns. Result (2026-10-10, 15 captures): **308 of 332 turns match**
(tiles, HP, MP, action points, facing and the random state all equal); the 24 others are species code —
the U-Boat's dive mode (21), the Noise's special (2) — and one trap turn from a capture made before traps
were recorded; 6 more differ only after a trap reshaped the floor. Each capture turn also carries the
game's write trace (`trace`: every random draw with its call site, HP/plan/action/MP writes), and
`--rng-trace` prints Godot's draws with their callers, so a mismatch can be lined up draw by draw;
`turn_wtrace.py` traces one turn by hand.

### Magic

**Casting** — dungeon `FUN_800A94A0(caster, {spell id, effective level}, mode, target)`:
- Sets `DAT_800E3D68` = spell level, `FUN_800A982C` loads the spell overlay and returns its handler.
- **mode 0 = normal cast** ("Direct:<spell>" familiar command): costs `DAT_800DD880[id]` whole MP,
  message "<caster> chanted <spell name>".
- **mode 1 = mixture magic** ("Mix.:<spell>"): the familiar mixes its spell into Koh's attack. Costs
  `DAT_800DD8B4[id]` quarter-MP; uses the spell's alternate name (+8 in the spell entry: Flay/Ice/Thunder
  Finger, Flame/Blizzard Sword, Wind Cutter, Mt. Burn, Aqua Wheel, Earth Shaker, Heat/Snow/Thunder Wave;
  "Finger" vs "Sword" depends on Koh's weapon, `FUN_800A9400`). The effect (`FUN_800B3D10`) adds the
  spell's element to the attack and attack += attack·L/(L+1) (more with a matching elemental weapon).
- MP is u16 8.8 fixed point at +0x24 (MP = high byte +0x25). Spend: dungeon `FUN_800AD594(unit, cost)`:
  talent 0x100 halves, status 0x0F doubles, status 0x20 makes it free.

**Spell overlays** — `FUN_800A982C` loads 12 sectors from LBA `0x607F + index·12` to 0x80024000:
index = id − 1 for normal casts, i.e. **DUNGEON.BIN +0x1834800 + (id−1)·0x6000** (24 KB each);
indexes 50+ are the mixture-magic variants (`FUN_800A9390` maps spell → index). The first word of an
overlay is its handler. All 72 dumped to `re/modules/spells/`.

**Magic damage** — dungeon `FUN_8009CE1C(target, power, level, element, dir, caster, msg)`:
- `FUN_8009D218` reflect/immunity check (mirrors, Spell-proof) can cancel the hit.
- attack = (power + level)·2; defense = DEF + armor (halved for frogs, min 1) — same as melee.
- element (vs target element): advantage → attack ×2, disadvantage → attack −25%, element shield → ¼.
- pending HP change (+0x64) = (defense − attack)/2, min 1 damage; then +0x1C |= 0x20000000 and
  `FUN_80042900(target, 0x1D)` from 0x8009D0A4 (**our hook, ra 0x8009D0AC**; s0 target, s4 power,
  s2 final attack, s5 element, s7 caster or 0 for traps/items).
- Spell power is an immediate in each overlay's call: Breath family 16, Sled 8 (NeaSled second hit 10),
  Brid 10, Rise/NeaRise 19 (NoaRise 10), Grave 24, Acid Rain 32 → `re/data/spell_damage_calls.csv`
  (`re/scripts/spell_powers.py`; disc offsets of each call included, so powers can be patched).
- Example (verified): Kewne Brid Lv1 vs a frogged Pulunpa (harness wrote status 0x0A; water, DEF 4 → 2): (10+1)·2 = 22, −25% → 17,
  (2−17)/2 = −7.
- Monster special attacks call the same routine from their per-species code chunks.

Spell table fields (EXE 0x8006DE24 + id·0x14): +0 name, +4 description, +8 mixture name, +0xC mixture
description, +0x10 family<<4 | element, +0x11 effect type (0x11 damage, 0x05 poison, 0x12–0x17
walls/mirrors, 0x1E heal/forth, 0x01 sleep, 0x02/0x03 blind, 0x04 bind, 0x1F special), +0x12 target scope
(1 single, 3 room), +0x13 ?. Full table with costs/powers: `re/data/spells.csv`.

Familiar command menu (Square → Command): Move / Direct / Direct:<spell> / Mix.:<spell> / Stay.
Orders execute on the familiar's next turn (Koh has to act).

### Community references

`refs/adrando/` holds pro_grammar's Azure Dreams encyclopedia (adrando.com/guide): damage, spell
and stat formula images, bug list, floor/egg/talent/unit tables. Everything checked so far agrees
with the code: damage roll {0,1,1,2}, attack = 2·ATK + roll + weapon·2 (+ mix-magic term), the
eighths-based element/height modifier, protections dividing by 4, spell base (power+level)·2,
Koh's ball spell level = level·4 (max 99), the stat-growth formulas above, and the EXP popup
crash at 32,767+. Their unit/species ids equal ours.

### Dungeon: floors, monsters, items

**Floor overlay** — DUNGEON.BIN +0x2A3000 and +0x51E800 (identical copies), 38 KB, loaded to
0x80016000 on tower entry and on every floor change (`re/ghidra/floor_decomp.c`).
- `FUN_80018A70` per-floor driver: seed RNG, set up the spawn table, then either a random layout or
  one of the fixed layouts (floor 1 tutorial / alternates, floor 2 first visit, floor 40 Beldo).
- `FUN_800194C4(floor)` reads **sector `0x3F5E + floor`** = DUNGEON.BIN +0x7A4800 + (floor−1)·0x800
  into 0x8014A000: bytes 0x00–0x1F = 16 (species, level) spawn slots → `0x800DDC7C`
  (pointer `DAT_80083478`); 0x20–0x3F = 32-species egg pool → `0x800DDC9C`; +0x40 = layout seed.
  Slots are drawn uniformly (rand & 15), so the community "likelihood" = number of slots.
  All 39 tables dumped to `re/data/floors.csv`. Random-dungeon mode (`DAT_80012090 == 2`) builds
  tables from random species instead.
- `FUN_80019AF8` random layout: room grid 4×4 (1/32 → 3×3, 1/128 → 2×2 per axis), rooms of random
  size, corridors; writes the 64×64 tile grid at 0x800EA000.
- Stairs/exits list `0x800E3CD8` (4 × {type, x, y, height}; type 2 = elevator). The elevator asks
  "Wanna go up?" then "QUIT?" (quit = save and leave).
- Items: `FUN_8001E194` places (rooms/2 + rand 0–3) items into the floor item list
  (`0x800E3548`, 64 × {id, category, charges, flags}; positions `0x800E36C8`, 12 bytes each);
  story items forced on floors 12/15/20/28 (`FUN_8001E660`). Normal picks via `FUN_8001EAA4`:
  category by weighted total, then item by **rarity tier** = item flags bits 12–13 →
  weight 128 / 85 / 32 / 1 (`li` immediates at 0x8001EA40/4C/58 + `move` at 0x8001EA54 in the
  totals builder, same at 0x8001EBD0/DC/E8/E4 in the picker). Flag 0x10 = never spawns,
  0x40 = random-dungeon only. Eggs: category 0x12 with species from the floor's egg pool.
- Traps: floor trap list `0x800E3648` (32 × 4 bytes, positions at `0x800E39C8` + 6, 0x18 each);
  `FUN_8001EF0C` also turns "monster" trap entries into units.

**Floor layout generator** — floor overlay `FUN_80019AF8` (called in a retry loop by
`FUN_80018A70` until it returns 0 and at least one room exists). Python port of the placement step:
`re/scripts/layout_sim.py` (uses the game RNG, statistically matches the game).
1. Grid: per axis `r = rand()`; `(r & 0x7F) == 0` → 2, else `(r & 0x1F) == 0` → 3, else 4 cells
   (`li v0,2/3/4` at 0x80019B4C/5C/60 for columns, 0x80019B78/94/98 for rows; columns →
   `0x8001F660`, rows → `0x8001F664`). **Max 4×4**: per-cell state lives in stack arrays sized for
   16 cells (sp+0x20 flags, sp+0x30 4 door counters per cell).
2. Open floor: `rand(0, 512) < 2` (`slti v0,v0,2` at 0x80019BE0) → one 60×60 room.
3. Each cell is a room if `(rand & 3) != 0` (`andi v0,v0,3` at 0x80019C34), otherwise a corridor
   junction point.
4. Room in cell (c, r), cell size `cw = 64/cols`, `ch = 64/rows`:
   `x0 = rand(0, cw/2−1) + c·cw`, `y0 = rand(0, ch/2−1) + r·ch`, `w = rand(0, cw/2−1)`
   (`move s8,v0` at 0x80019DE8), `h = rand(0, ch/2−1) + 5` (`addiu v0,v0,5` at 0x80019E04).
   It claims `(x0−2, y0−2, w+9, h+4)` in the tile-claim grid; `FUN_80017584` rejects it if that rect
   touches x or y < 1, reaches 64, or overlaps an earlier claim → the cell becomes a junction instead.
   Accepted room = `(x0+1, y0+1, w+3, h−2)`, height `rand & 0x60` (0/32/64/96).
   Height masks: 0x80019EF0 (room), 0x80019FDC / 0x8001A0B0 (junctions), 0x8001A19C (open floor).
5. Fewer than 2 rooms → open floor anyway. Otherwise rooms are carved (`FUN_8001CE44`) and
   connected with corridors (`FUN_8001A768` picks a neighbour, `FUN_8001AC4C` digs); up to 0x400
   attempts, and a failed dig makes the whole function return 1 → regenerate. Unconnected junctions
   are removed (`FUN_8001DC34`); `FUN_800176EC` compacts the room list and stores the count in
   `0x8008146E`.
- Room list `0x800E2970`: 36 × 20 bytes {x, y, w, h, height, active, connected, …} (s16 each).
- Vanilla averages (simulated, 5,000 floors): 6.6 rooms of area 40; 0.5% open floors.
  Live floor 2 samples: 7–8 rooms of area 33–46.
- Items per floor `FUN_8001E194`: `rooms/2 + (rand & 3)` (`andi` 0x8001E298, `sra a0,a0,1`
  0x8001E2AC); open floor `(rand & 7) + 8` (0x8001E280 / 0x8001E288); max 64.
- Traps per floor `FUN_8001EF0C`: `rooms/2 + (rand & 3)` slots (0x8001F090 / 0x8001F0A4,
  `addu s5,a0,v0` 0x8001F0A8); open floor `(rand & 3) + 4` (0x8001F078 / 0x8001F080); max 32.
  A budget `floor/2 + (rand & 0x3F)` (`andi` 0x8001F0E0) is spent at `4 + rarity·4` per trap and
  limits how many slots fill on shallow floors.
- The floor seed changes on every launch, so the same save state gives a different 2F each run.

**Item database** — EXE category table 0x80073410 (0x14 bytes each: +6 count, +0x10 item array);
each item 0x14 bytes: +0 flags (rarity bits 12–13, 0x10 never, 0x40 random-mode, bits 0–2 element),
+2 kind, +4 name, +8 description, +0x10 buy price, +0x12 value. Dumped to `re/data/items.csv`
(categories 1 herbs, 2 fruits, 3 seeds, 4 balls, 5 scrolls, 6 crystals, 7 bells, 8 glasses,
9 loupes, 10 sands, 11 gifts, 12/13 key items, 14 coins, 15 swords, 16 wands, 17 shields,
18 eggs, 19 egg names, 20/21 trap/terrain entries).

**Monster spawning** (dungeon module)
- `FUN_800A08A0(mode)`: picks a random room tile; mode 0 (periodic) requires distance > 32 from Koh;
  takes a random slot of the floor table, loads the species code chunk if needed, creates the unit
  at level 1 and levels it up to the slot level. Cap: fewer than 32 loaded units (`DAT_8008347C`).
- Floor start (`0x800A69E4`): `rand(4, 8)` monsters (`li a0,4` / `li a1,8` at 0x800A69E8/EC), after
  preloading the code of all 16 slots.
- Periodic: timer `0x80083466` counts down each turn; at <0 it resets to `(rand & 0x1F) | 0x20`
  (code at 0x800A0E1C/20 → 32–63 turns) and spawns one monster.
- **Species code chunks**: `FUN_800A0B94` loads species `s` into code slot k from LBA
  `(s−1)·0x54 + k·0xC + 0x4340` (12 sectors, 7 slot-linked copies per species) to
  `0x80170800 − k·0x6000`. First words = handler table. Barong = species 31
  (`re/ghidra/barong_decomp.c`).

**Bugs confirmed in code** (from the community list; fixes in `azure.dungeon`):
- Strength Increased: `FUN_800C82B8` does `lw v0,0x54(a0)` (Koh) instead of `(v0)` (familiar)
  at 0x800C82E4. Fixed: Koh's hit 88 → 99 with one Strength+ familiar (verified).
- Gaia Shoot (DeoRock mixture, spell overlay 68) passes element 10 (water) at 0x80025340; its fire
  (overlay 54) and water (61) siblings pass 9 / 10, wind should be 12.
- Barong (`0x801745B4` in its chunk): both rarity comparisons reload the thrown item
  (`lbu a0,0(s1)` + `lw v1,12(v1)`) instead of the candidate (`a1`, `s0`).
- Not yet addressed: Mazarr-on-empty-MP U-Boat softlock, level > 99 spawn infinite loop, EXP popup
  crash at 32,767+ (our EXP Rate mod caps below it), cursed status persisting after De-curse.

### Dungeon map & units (for tooling)

- Tile grid: 6-byte entries at `*0x8008333C` (= 0x800EA000), row width `1 << *0x80083350` (64); s16[0] = tile
  type (0 = none), s16[1] = height (Y-down), s16[2] = attributes. Steps of more than 32 are walls.
  Types seen on 2F: room floor 0x19 / checker 0x23 and 24/34, 26/36 pairs; ring corners 0x0E/0x0B/0x0D/0x0C,
  ring edges top 0x12, bottom 0x10, left 0x11, right 0x0F (attribute 9); ring tiles where a corridor
  enters (82, 97, 45, 75, 65/66, 92) at floor height; corridors 104; pillars 102/103 three or four steps up;
  the map border 3 at height 1024; empty cells height 16384. `FUN_8001D5D8` lays a room's tiles at
  height - 0x80 (type 0x19, attribute 6) and `FUN_8001D9CC` its ring at height + 0x40. Heights point up:
  the ring is a wall six steps above the floor (2F: rooms -32/-64, rings 128/160), and `FUN_8001CEC0`
  sinks every other tile of a "pillar" room three steps (height - 0x60, type attr/2 + 99 = 102/103).
  Terrace steps `FUN_8001DD08`/`DD48` move a tile one step up/down and its type with it (24/25/26...).
  Check against the 2F frame (re/shots/terrain_ref_2f.png): far walls stand behind the room with gaps
  at the floor-level door tiles; the near wall is cut at the floor line (dark cap, face below) and its
  primitives are at the back of the order table. Units' +0x88 is the opposite sign (melee gives +1
  when attacker+0x88 - defender+0x88 <= -0x20, i.e. to the higher unit).
- Unit list: circular via +0x5C starting at `*0x800814A8`; monsters lack flag 0x4000.
- `re/scripts/attach.py`: `find_units`, `tile_map`, `path_to`, `go_next_to`, `face_and_attack`.
- Test bench for fusion: put any monster in Koh's second familiar slot (`Koh+0xB0 = unit`,
  `unit+0x14 |= 0x4000`) and use Square → Fuse.

### Useful functions

| Address | Where | What |
|---|---|---|
| 0x8003F6D4 | EXE | queue a sector load (sectors, dest, req, lba); 0x80062970 = PsyQ CD_getsector |
| 0x8003AD08 | EXE | number → full-width Shift-JIS digits (message text) |
| 0x8004E4C0 / 0x8004E5A0 | EXE | number → ASCII with padding |
| 0x800B4C7C | dungeon | floating combat popup (damage / "MISS" / "+N EXP") |
| 0x8009BFF8 | dungeon | drain effect: moves HP between units, prints "… N damage" |
| 0x800A2DB8, 0x8009C12C | dungeon | damage/EXP application paths (callers of the popup) |
| 0x80099194 / 0x80099734 / 0x80099290 | dungeon | message builder: append fragment / append unit name / flush |
| 0x800A48B0 | town | copies player pos 0x80083780 into Koh's town actor |

### Text / data tables in the EXE

- Item & trap names + descriptions around 0x8002F000–0x80031800 (e.g. "Oleem", "Sleep", "Slam", "Bomb").
- Monster names (e.g. "NOISE" at 0x800309E8).
- Spell names (e.g. "Flay" at 0x8006D7C0).
- Koh's default name at 0x80080AB4.
- All in-game text is full-width Shift-JIS with control bytes 0x03/0x08/0x0A/0x11 and 0xFE 0x00/0x01.

## Town events (mapped 2026-10-05)

Tools: `re/scripts/town_script_dis.py` (disassembler), `town_events.py` (catalog of every location,
script chunk and flag → `re/events/town_events.json`, `flags.txt`, `chunks/<lba>.txt`), `town_stages.py`
(event chains → `re/events/stages.json`, `stories.md`), `town_script_asm.py` (assembler),
`make_journal.py` (Story Journal).

**Story flags**: bit array at 0x80012D70, flag n = bit (n & 31) of word n >> 5. EXE helpers: set
0x80033AA8, clear 0x80033AE8, test 0x80033B2C (flag 0 always false, flag 1 always true). Every location
overlay carries its own copies (signatures in `town_events.HELPER_SIGS`) working on `*(API+0x18)`.

**Locations**: 54 overlay programs in TOWN.BIN, header `{0, 0x4C070707, entry, 1}`, loaded at 0x80016000.
The header is itself bytecode (`nop×3; native entry; wait; end`). The exterior is lba 4444
(TOWN+0x2AB800); its door list (`{lba, size<<20 | 0x016000}` at 0x8001C1E8) names 38 interiors. Monster Hut
= lba 6628 (TOWN+0x6EF800), Nico's house 6317, Koh's house 5071, Cherrl's house 6287, inn 5801, library
5236. Town API struct 0x801131B8 (`*0x80016000`): +8 location id (0x25 in the hut, 0 outside), +0x18 flag
array, +0x28 object buffer, +0x2C script load base, +0x34 event table (`{key, ptr→{size, lba}}`), +0x40
`ovlcall` function table.

**Script chunks**: sector-aligned in TOWN.BIN, `u32 n` then bytecode/text, sometimes MIPS helpers at the
end (called with op 0x4C). Each overlay lists its chunks as `{u32 size (filled at runtime), u32 lba}` and
sets its own load base (exterior 0x8001DCD0, Nico's house 0x80018FF8, hut 0x80018D30, …: `sw r,44(api)` in
the overlay init). The loader (town `FUN_8008AFB0` → EXE `FUN_80053CFC`) keeps a 32 KB cache and always
moves the running chunk to the base, so jump addresses are absolute from it. Cache table 0x800CF720:
8-byte entries `{u8 flag, u8 id (0xFF ends), u16 variant, u32 size}`, newest first, the chunks back to back
from the base. `FUN_8008B0E8`: a miss reads the chunk from CD to the base after shifting the others up; a
hit (`FUN_8008AE4C`) copies it out, shifts the newer ones up and copies it to the base. The shift
(`FUN_8008ACAC`, backward word copy) is off by one word: it copies `src+4 … src+size`, so a cached chunk
never gets its own first word (its number) and keeps stale bytes there; vanilla never reads it. The
exterior loads five chunks on arrival within ~15 frames (4513, 4516, 4538, 4540, 4543 from the owner's
save), so its conversations run from cache copies. An event key is
`id<<24 | flag<<23 | variant<<16 | entry`: (flag, id, variant) selects the chunk, `0x80016000 + entry` is
where the script starts.

**Script VM** (EXE `FUN_80038AB8`, opcode table 0x8006AA90, operand table in the header of
`town_script_dis.py`). Text = bytes < 0x01 in opcode position: SJIS pairs, `FD r` number from var r,
`FE n` name (0 = Koh), `FF a32` text fragment call, `00` return/end. Lines ≤ ~30 chars, 3 per box.
Speaker/actor ids = speaker-name-table index + 3 (Koh 1, Kewne 2, Ghosh 6, Weedy 5, Selfi 7, Patty 8,
Fur 9, Mia 10, Nico 11, Vivian 12, Cherrl 13). Menus: `page 1` (Koh), `op 0x0B` + `[text]` per line,
`choice n` (0x19), `switch` (0x1A, n absolute targets). `op 0x36 r,i,a` reads any RAM word into a var.
Scripts start through EXE `FUN_80035208(addr)` (creates the VM task; block 0x80082A38, +0x38 = last start).

**Event chains (the story structure)**: each overlay has an actor list of 28-byte entries
(`+0` key, `+8` → chunk descriptor, `+0x10` → stage table, `+0x18` (count, flag)). A stage is 16 bytes:
`+0` condition fn, `+4` script fn (returns the script to run, usually via a picker table
`{u16 actor, i16 pos, u32 script}`), `+8` data, `+0xC` i16 completion flag. Exterior `FUN_80019F94`
picks the current stage: skip stages whose flag is set; the first one whose condition returns 0 plays.
A stage with flag 0 and condition `return 0` is the idle end. Condition functions test/set other flags
(requirements, "once per town visit" latches such as 5208/5209; the exterior clears 3410/3446/3447 on
each visit). 48 chains / 330 stages extracted; per-girl view in `re/events/stories.md`.

Nico (worked example): square slot 4/1 (chunk 4516, donation drive: 3405, 3467; first-donor test 3409,
Ghosh's alternating visit 3411), square slot 5/1 (chunk 4521: fountain finished 3431 → sets 5212, then
3432–3435 incl. Selfi's egg (sets 5211) and Chero the cellist (sets 5213)), her house slot 34 (chunk 6358,
flags 2434–2445 + 2457; needs 5202 = donated, 5212, 5211, 5208/5209, 5205, sets 5230 at the end).

**Player control in town**: Koh's town object is his unit record 0x800834B8; state fn at +0 (idle
0x80090C68, walking 0x80091260, entering 0x80090D44, event 0x80097D2C). All call the input function
0x80090A74: button edges at 0x80083170 (△ 0x10, × 0x40), held 0x80083168 (SELECT 0x100); on idle frames it
calls `FUN_8009567C` (0x80090BC4) for touch events and starts them with `FUN_80094C1C(obj)`,
`FUN_80098868(obj, a1, a2)`, `obj+0x2C = 0`, `FUN_8008B158(target)`. (The handler at 0x800927EC with the
`0x800FE5D8` mode pointer is a different, unused-in-town path.) Dead EXE code usable for trampolines
(no jal, pointer or lui/addiu reference anywhere on the disc): 0x8005C130 (400 bytes; the Story
Journal's SELECT trampoline until 2026-10-08, free again), 0x8006778C (284; first 32 bytes used by Japanese Voices), 0x80066994 (276), 0x8005C784 (264), 0x8004DE88 (260), 0x80036A70 (160).

**Weedy (Koh's house, location id 1)**: her lines are bytecode in the house's overlay program (TOWN lba
5071 at 0x80016000; Wreath's safe/save menu, speaker 4, is there too at 0x800161F9). "Do you want to read
my Monster Book?" starts at 0x80017774 (speaker 5); its menu at 0x800177C5 is `page 0`, two `op 0x0B`
options, `choice 2`, `switch [0x80017852 (Sure: opens the book via ovlcalls c7/a1/a2/c8), 0x80017851
(Too busy: end)]`. The Story Journal redirects that menu (see Mods).
Code written there with `psx_mod_write_code_word` runs interpreted (the dispatcher refuses compiled
code whose bytes changed).

## Japanese voices (mapped 2026-10-05/06)

The Japanese release (SLPM-86047, image in `disc/Azure Dreams (Japan).bin`, files in `extracted_jp/`)
voices the town dialogue and a few tower scenes; the US engine kept the whole path but its scripts
and disc dropped it.
- **Script op 0x1D** `a b` (handler 0x800398BC): waits (re-runs every frame) until `FUN_80053EF0(4)` is 0,
  then `FUN_8003F540(ch, LBA_TABLE[DAT_800721C0[(a>>19)&31]], a & 0xFF07FFFF, b)` (just stores the request
  at 0x8006CE34) and `FUN_80053DA8(0x300)`. `a`: top byte = XA channel, bits 19–23 = file, low bits =
  start sector; `b` low 20 bits = end sector. Status `FUN_80053EF0(4)`: 0x100 if `0x800847D4 & 0x200`,
  2 if `0x800847D0 & 0x4000`, 3 if `0x8008485C == 2`, else `(0x800847D0 & 0x400) != 0`; 0 = idle.
- **What stops a voice**: the button-wait state 0x80038478 — when the press flag ctx+0x84 is set it calls
  `FUN_80053DA8(0xB4)` (stop) and sets the state to running; a speaker change stops it too. A second
  `stream` op waits until the first voice is over (so JP plays two voices in one box in sequence).
- **Stream LBA table** EXE 0x8006CD50 (US) / 0x8006F38C (JP), 24 entries; 3..18 = voice files
  STRT/A02301AK.STR … O00601FE.STR, STR/P00104AB.STR (US: all point at MERGE.STR, 0x6524).
- **JP placement**: `30 1D a b` (yield, stream) right before the voiced text, usually after the `page`
  op. Short clips are subroutines `30 1D a b 16` picked by native overlay code through pointer tables
  (hospital 0x80019144 / JP 0x8001916C, restaurant structs at stride 0x18, gift reactions at stride 8);
  the US kept those tables pointing at bare `16`s. Not every line is voiced in JP (e.g. Nadia: only
  her first line).
- **VM internals used**: context 0x80082AC4, the same in town and tower (+0x10 state fn, +0x1C ptr,
  +0x7C call stack ptr, +0x80 → vars at +0x48 + 4n, +0x84 button pressed). States: running 0x80038A10,
  ended 0x80038A00, button wait 0x80038478, page countdown 0x80038368, actor action 0x80038408 (re-runs
  op 0x0F until the actor is done), text typing 0x800387D0. `call_v n` (0x4B) pushes the return
  address and jumps to var n.
- **US/JP chunk pairing**: same overlay order (54 each), same chunk descriptor order. A chunk's first
  word is not unique (most are 8). TOWN.BIN also carries unreferenced leftovers of JP chunks (US lba
  5184/5188/5195/5199, listed by the unused overlays 5103/5112) that still contain `30 1D` ops.
- **Tower**: the townspeople you meet in the tower (Ghosh, the girls) and Kewne's tutorial have their
  scripts in the dungeon module image (US DUNGEON.BIN 0x7D0800 → 0x800F8000; JP 0x7D1000 →
  0x800FA000), 67 voices. Beldo's appearance is in species 55's code chunk (US DUNGEON.BIN 0x1271000 +
  k·0x6000 → code slot k at 0x80170800 − k·0x6000; JP 0x1271800), 15 voices.
- **Other voiced scripts**: the gift reactions live in the EXE (JP SLPM 0x3FF80.., US SLUS 0x3EA80..,
  RAM = t_addr + file − 0x800), 51 voices; Koh's house overlay program (US 5071 / JP 5847, at
  0x80016000) holds Wreath's lines at the door, 46 voices. Kewne's item tips: JP in the dungeon module
  (familiar talk, e.g. the egg tip at 0x800FD309), US moved into the EXE (egg tip at SLUS 0x437B7 =
  0x8006FFB7; "No problem. It's a dirty hovel, right?" at 0x800702EE); only the egg tip is voiced, paired
  by `TIP_SCRIPTS` in voice_port.py. Event overlays #43/#44 (US 6638/6643, JP
  7331/7336: the naming scene, the flashback with Nico) list their chunks as `{lba, n << 20}` instead
  of `{0, lba}`. JP-only content: the unused overlays 5877/5886 (US 5103/5112 point at leftovers) carry
  ~28 voices of scenes the US does not have.
- **Script decoding facts found on the way**: op 0x01 ends the script (VM idle state 0x80038A00, stops
  the voice); in text, `00` is a return (pops the call stack). Scripts start right after the previous
  one's end, reached through overlay data words or `lui/addiu` pairs in the overlay's script functions;
  the US pads the gap with leftover bytes (`11 01 a4 57 09`, `11 01 00 70 92 57 09`; JP pads with
  zeros), which a linear decode reads as a 2-byte character and loses the next script's `page` op.

`re/scripts/voice_port.py` aligns every JP script with its US twin on structural ops (difflib over
speaker/actor/flag/branch keys; the decoder resyncs after each script end at a known entry point or at
the next `page` op, and at jump targets — but keeps a valid `page` op that directly follows the end,
since stray overlay words look like entry points). Between two structural ops it cuts the JP text into
voice segments and the US text into pages (button waits); JP stretches that land on the same US
stretch (the US dropped an op between them) are merged. Segments map to pages one to one when every
segment is a whole JP box (it follows a button wait, speaker change, choice or script end) and the
counts match; otherwise by share of text: a segment spanning several US pages keeps playing through
their waits ("continuations", owned by the voice that is playing there); several segments on one US
page go to the later line of the page where their share of the text begins (a new JP box prefers a line
that starts a sentence; the VM waits there for the previous voice, as in JP), else play after it at the
box's wait ("follow-ups"); a new JP box that would only follow a one-line box's voice starts on its next
page instead. No continuation is kept into a box that has its own voice (that voice's `stream` op would
hold the box until the old voice ends). Voices the first pass loses are retried aligning without
actor/face/sound ops (the releases reorder those), then on speaker changes alone, accepted only on a
free US page with the same speaker. `re/events/voice_overrides.toml` places (or drops, with the reason)
the rest, optionally keeping a voice playing `through` n waits; `re/events/voices_missing.md` lists
whatever is still unplaced (now nothing), `re/scripts/voice_where.py` shows both scripts around a
voice, and `re/scripts/voice_review.py` lists every placement (or the changes against an older
voices.json). Result → `re/events/voices.json` and `mods_src/azure_voice_data.h`: 1945 JP voiced town
lines → 1936 placed (3 of them follow-ups), 9 dropped; 86 clip-table entries; gift reactions 51/51;
Wreath at the door 46/46; tower 66/67 + Kewne's egg tip (moved to the EXE in the US) and Beldo 14/15 —
2114 of 2124 voiced lines. The 10 dropped: 6 with no US line (Ghosh's "tasteless fountain" remark, the
arcade welcome twice — a placeholder script, untranslated or emptied in the US — Fur's "顔?" before a
rewritten choice, Nico's "うそ!" for the "doesn't matter" answer, which the US rewrote, Beldo's
"その時、全てを教えてやる"), 4 second copies of a line whose voice already plays.
Review 2026-10-06: every placement read against the English; 47 overrides fixed voices one box off
(mostly where the US re-flowed a JP box over two pages, or merged two JP boxes). Plugin row kinds: 0
line, 1 clip-table entry, 2 follow-up, 3 continuation wait, 4 a continuation wait that a short line's
patch moved into its snippet (`<player>.` + wait, e.g. Wreath's thank-you speech).
`re/scripts/build_voice_disc.py` appends the JP voice files (raw XA sectors, MSF headers rewritten)
to the US image and patches the table in the disc's EXE (EDC/ECC recomputed) →
`disc/Azure Dreams (USA) (JP Voices).cue`, 203,986 sectors.

## Sprites (decoded 2026-10-09, `re/scripts/sprite_banks.py`)

- **Part record (12 bytes):** `flags, GP0 code, s8 x, s8 y, u16 tpage, u16 clut, u, v, w, h`. Flags: 0x80 last
  record of the frame, 0x40 static page, 0x20 marker (w = h = 0, draws nothing; its clut field is a
  parameter), 0x08 relocated, 0x01 part drawn mirrored at `[1-x-w, 1-x)`, 0x02 the same vertically (draw
  routine `FUN_8004C36C`). A whole mirrored sprite puts each part at `x' = -x - w`.
- **Per-frame parts** (`(flags & 0x60) == 0`, most attack/hurt frames; all of Kewne's): not on the static
  page. `FUN_800475A4` reads one u16 per such part from just before the frame list (first part at list-2,
  next at list-4...), an offset from header +0x0C; `FUN_80047338` allocates (w+3)>>2 words x h+1 rows in
  the unit's dynamic page (writing the record's u/v) and `FUN_80047270` decodes with `FUN_800407C0` and
  uploads. `FUN_800407C0` (4bpp nibble RLE): byte 0 odd = row-major stream; even = column-major with
  byte0>>1 bytes per row, then a u16 byte count (byte 0 = 0: raw copy). Stream byte c: `c & 0xF0` = run of
  (c>>4)+1 nibbles of c&0xF; else c literal bytes (high nibble first); c = 0 ends a row-major stream.
- **Palettes:** a record's clut field k picks the 16-colour palette at CLUT +32k (0..3 used; 4..7 repeat
  them recoloured): e.g. Troll's club is palette 1, Kewne's palette 1 is palette 0 with STP set.
- **Bank header:** +0 sequence table offset (0x28), +4 sequence count, +8 record offset, +0xC pixel offset,
  +0x10 record count, +0x18 bpp, +0x1C CLUT offset (Koh). A sequence is steps `{u16 ticks, u16 op, u32 off}`:
  op 2 show the frame at `off`, op 1 loop to step, op 0 end (hold the last frame). Ticks are VBlanks
  (60 Hz; stepper `FUN_800477F4`, divisor `DAT_80080A84` = 2, verified live).
- **Monster banks:** DUNGEON.BIN `0x1375800 + (s-2) x 0x15800`. The static 4bpp 256x256 page is at +0xD000 as
  four 0x2000 chunks (32 words x 128 rows at x0/y0, x0/y128, x32/y0, x32/y128); the CLUTs are at +0x15000.
- **Koh's bank:** +0x4DB800, 216 sequences. Frames are 8bpp, LZ-compressed (`FUN_8004068C`) then
  run-expanded (`FUN_80048764`); the palette is at +0x41824; image offsets are the u32s before each list.
- **Koh's equipment overlay** (`re/scripts/weapon_gfx.py`, 2026-10-21): his frame records with flags 0x40
  draw from the page at VRAM 896,0 (4bpp): CLUT 0x7A40 (VRAM 0,489) = the sword or rod, 16x16 cells at
  u 128-255 / v 128-255; CLUT 0x7A41 (16,489) = the shield, 24x24 cells at u 128-223 / v 0-119 (0x7A42,
  only in the lying sequences 31/32, is not from these files). The dungeon's equip code
  (`FUN_800982A8`) calls EXE `FUN_80048500(id, kind)` (kind 0 sword, 1 rod, 2 shield): the record at
  `*(0x800710E4 + 4 kind) + 8 id` = {u32 size<<12, u32 absolute disc LBA} (swords 0x42AC + 2(id-1),
  2 sectors; rods 0x42C4 + id, shields 0x42CE + id, 1 sector), read and run by `FUN_80041344`: 16-byte
  commands {u16 type, u16 next, u32 data offset, params}, type 1 = LZ (`FUN_8004068C`) + LoadImage to
  {x, y, w words, h} (swords/rods 928,128 32x128; shields 928,0 24x120), type 2 = CLUT upload. Nothing
  equipped: `FUN_800483AC` clears the area (the parts draw transparent). Records draw bottom-up like the
  body parts; flag 0x01/0x02 parts mirror as in `part_rect`.
- **Koh's hop** (measured on the dev build, 2F slot 5, 2026-10-23): a step to a tile 32 up or down is Koh's
  state 0x10: sub 0 for 2 frames in the approach pose (0x800DD030), sub 1 the jump (0x800DD040, Koh
  sequences 105/98/91..., steps of 4 frames): across the tile in 16 frames, the height following the same
  throw every time, up 16, 31, 43, 52, 55 (frame 10), 53, 42, 23, -6, -37 ... at 2-frame steps, until it
  comes back down to the new tile's height (a step up lands at about frame 16, a step down at about 18-20);
  a drop then plays the landing, state 0x16: 0x800DD050 for 2 frames and 0x800DD058 for 14. A step up
  goes straight back to idle. Flat steps stay 16 frames (state 0x0F). Running (Circle held, no awake unit
  near) skips the hop. The step-height limit is the ground rule above (one step up, any drop).
- **Monster steps** (measured on the dev build 2026-10-23: 2F full of level-1 Pulunpas via
  test_encounters, Koh waiting, the monster's record tail and position object in the snapshot slots;
  `re/scripts/monster_steps.py`, frames from the state change): a walk step is state 0x0F, 8 ticks = 16
  frames, linear across the tile, the walk table from the step function (Pulunpa `FUN_80171BB0`,
  0x801762C8 = **g1**; the scan's "state 0x10" groups were the hop's, not the walk). A **step down**
  sets +0x88 to the new height at once and +0x90 to the old one (−32), held for 8 frames, then falls
  (−30.8, −27, −19.5 at frames 10, 12, 14) and lands at 16. A **step up** (`FUN_8009A66C` = 3) is the
  hop, state 0x10 (`FUN_80171DF4` → `FUN_801721B0`), only when the sprite's sequence has not ended
  (sprite +0x14 & 0x8000 clear, i.e. a looping idle was playing) and not in fast mode (0x80083462 &
  0x80); otherwise it is an ordinary walk step that pops onto the new height on the first tick. The hop:
  on the new height from frame 2; sub 0 the approach table (0x801762D0 = g2) for 3 ticks; sub 1 the jump
  (0x801762D8 = g3), across the tile in 5 ticks (frames 4-14) with +0x90 = −32·sin(cnt·0x199) for
  cnt 5..1: up 0.1, 18.9, 30.5, 30.4, 18.8 at frames 6-14; the step counter runs out at 16 with the unit
  still 18.8 up, so the landing table (0x801762E0 = g4) is cut and it falls in idle: 17.5, 13.8, 6.3, 0
  by frame 24. Every walker chunk has the same four tables in a row (walk, approach, jump, land;
  `species_anims.hop_groups`: mostly g1-g4, Grineut / Griffon g2-g5, Weadog g9-g11, Ifrit / Volcano one
  jump group); flyers and Troll / Golem / Kraken / Zu etc. have no state 0x10 handler. Flyers glide to
  the new height (Kewne: 8 units per 2 frames). Two-step units get 4 ticks a step, which cuts the hop.
- **Height in species swings:** Golem's slam (`FUN_80172D08`, state 0x11 sub 2) lands on the target's
  height: +0x90 gains (target y − own +0x88)·0x2000 per tick for the 8 rising ticks plus the arc scaled
  by the target species' size (0x800DDC40 + 0x20); with a wall or a drop of more than 63 ahead it jumps
  in place. Battnel's swoop (`FUN_801725D0`) aims at the target's position y − 52: 2 ticks closing a third
  of the gap a tick, a tile forward in 4, 10 ticks over the target with the blow 8 in (frame 28 from the
  start; g6, 50 frames), then back (8 units a tick, thrown up 8 with gravity 1.5) until g6 ends. The other
  state 0x11 height reads are ground probes; state 0x17 (U-Boat, Baloon, Blume, Volcano, Manoeva, Picket,
  Viper, Garuda: 1-8 reads) is the bump-and-turn after being pushed, not an attack.
- **1F tile set** (captured on the dev build, slot 2, 2026-10-23): floors from the 8bpp page at VRAM 512,256
  through CLUT 0,448 (blue marble 3,6 and cream marble 3,7 are the checks, the most drawn cells; the
  chain pentagram of the elevator circle is in cells 0-1 x 4-7; the same page through CLUTs 449 / 450 is
  the red and grey variants), walls from 576,256 through CLUT 0,453 (stone balustrade 2,1, green marble,
  brick), backdrop VRAM 768,0 through CLUT 0,495. Saved as azure-tower-godot/assets/original/f1_*.png and
  backdrop_f1.png; TowerTheme "Entrance Hall". Which tile set the other floors use is still not mapped.
- **Floor items and traps** (`azure-tower-godot/tools/object_extract.py`, 2026-10-21): both are
  screen-facing sprites on the 4bpp page at VRAM 960,0, filled by two upload lists in DUNGEON.BIN:
  0x4BE800 (LZ images for 960,0 / 960,128 / 448,256 / 480,256 / 960,256 / 952,0, item palettes 0x7B40-4F,
  the 0x7A42 palette) and 0x4BD000 (992,128 = page texels u 128-255 / v 128-255, trap palettes 0x7F00-0F
  with STP). Item icon: EXE `FUN_8004A658(category, id)`: category table 0x80073414 (20 bytes: +0 entry
  size flag, 12 / 20 bytes an item; +0xC the list), icon index at item +2, record pointer at
  0x8007361C + 4 index (one icon per category plus specials: money, meat, collar, balloon...); eggs use
  the record at 0x8006E240 (page 896,0, palette 0x7A42; dungeon `FUN_800A7A38`). The EXE file holds
  these at address - 0x8002C800. Traps: `*(0x800DF258 + 4 id)` (`FUN_800B60B8`): 0 = not drawn (ids 6,
  19), a frame list (32x24 urn markers, palettes 0x7F03-0x7F09), or a sequence (top byte 0x80 / 0xA0;
  the colour-cycling circles, 4-tick or 2-tick frames, looping); drawn by `FUN_800B51C8` unless hidden
  (+3 & 0x80, or the floor's reveal bit 0x800E296C & 8).
- **Melee blow timing** (`re/scripts/melee_chains.py`): most species' melee handlers (state 0x11) call
  the hit routine `FUN_8009C12C` when the attack sequence reaches step N (sprite +0x04, +0x14 & 0x1000)
  or ends (+0x14 & 0x8000): Dragon 2, Ifrit 4, Grineut / Griffon 3 (and 5), Ashra 6, Pulunpa 6 (= 14
  frames, as measured), Naplass 6, Mandara 3, Maximum 6. The others count frames (+0x96): Flame 9 from
  the sequence start, Clown 8, Manoeva 2, Cyclone 5 into its lunge, Troll 4 then its weapon sequence and
  5 more, Noise 4 + 11, Blume 4 + 4 (read by hand); Kewne (familiar, state 0x18, measured
  `re/timelines/kewne_direct.txt`): g12 20 frames, g7 44 with the blow 24 in, g14 18.
  **The +0x96 counters tick at 30 Hz** (the object update runs every other frame): frames are twice
  the counts (Flame 9 -> blow 18 frames in, Troll 4 + 5 -> 8 + 10; both confirmed live).
- **Measured swings** (`re/scripts/melee_measure.py`, 2026-10-21): per species, a dev-build floor with
  it (test_encounters on 2F, launched fresh per group from slot 4 since a second elevator ride can
  quit the tower), Kewne put to sleep, Koh at 200 HP walking next to it and waiting; frame-exact state
  / sub-state / sequence (timeline.Tracker), the position object (pointer at unit - 0x18; x, z, y as
  16.16 at +0/+4/+8; 64 units a tile) and the blow = the first write to Koh's record from
  `FUN_8009C12C` (pc 0x8009C12C..0x8009C93C; it writes even on a miss; the random draws at the
  swing's start are `FUN_8009C93C` preparing the hit). Results in `re/timelines/melee_NN.txt` (first
  pass in `melee_v1/`), used by `tools/sprite_extract.py` as attack chains + movement.

| Species | Swing (group:frames, in order) | Blow (frames from start) | Total | Moves |
|---|---|---|---|---|
| 2 Kewne | g12:20 g7:44 g14:18 | 44 | 82 | yes |
| 3 Dragon | step [2] | 14 | | |
| 5 Ifrit | step [4] | 14 | | |
| 6 Flame | g3:28 | 18 | 28 |  |
| 7 Grineut | step [3, 5] | 14+20 | | |
| 8 Griffon | step [3, 5] | 14+30 | | |
| 10 Snowman | g0:8 g8:34 | 22 | 42 |  |
| 11 Ashra | step [6] | 22 | | |
| 12 Arachne | g1:16 g9:62 g1:10 | 42 | 88 | yes |
| 14 Nyuel | g15:18 g16:10 g17:8 g18:20 | 32 | 56 | yes |
| 16 Clown | g6:32 | 16 | 32 |  |
| 18 Unicorn | g8:8 g9:26 g10:12 | 32 | 46 | yes |
| 20 Block | g8:42 | 14 | 42 |  |
| 21 Pulunpa | g8:24 | 14 | 24 |  |
| 22 Troll | g10:8 g4:28 | 18 | 36 |  |
| 23 Noise | g0:8 g8:32 g0:36 | 30 | 76 |  |
| 24 U-Boat | g0:28 g7:18 g0:26 | 46 | 72 |  |
| 25 Baloon | g8:16 g9:40 g10:18 | 36 | 74 |  |
| 26 Dreamin | g5:40 | 20 | 40 |  |
| 27 Blume | g0:8 g8:20 | 16 | 28 |  |
| 28 Volcano | g6:44 | 30 | 44 |  |
| 29 Cyclone | g7:14 g8:20 | 24 | 34 | yes |
| 30 Manoeva | timer | 4 | | |
| 31 Barong | g0:6 g7:38 | 26 | 44 |  |
| 32 Picket | g8:21 | 1 | 21 |  |
| 33 Kraken | g4:12 g5:34 | 28 | 46 | yes |
| 34 Weadog | g0:52 | 24 | 52 |  |
| 35 Stealth | g7:36 | 4 | 36 |  |
| 36 Viper | g2:4 g3:10 g8:20 g9:10 | 28 | 44 | yes |
| 37 Naplass | step [6] | 16 | | |
| 38 Zu | g1:16 g5:36 g1:2 | 36 | 54 | yes |
| 39 Mandara | step [3] | 18 | | |
| 40 Killer | g7:34 | 14 | 34 |  |
| 41 Garuda | g10:40 | 4 | 40 |  |
| 42 Glacier | g0:8 g3:22 | 16 | 30 |  |
| 43 Tyrant | g8:22 | 8 | 22 |  |
| 44 Golem | g7:86 | 48 | 86 | yes |
| 45 Maximum | step [6] | 20 | | |

  Kewne measured as a familiar (state 0x18, `re/scripts/melee_familiar.py`). Not measured (familiar-only
  evolutions and Frog): Hikewne, Kid, Saber, Battnel, Death, Univern, Metal. Movement: the hovering
  species descend onto the target (Kewne 43 units, Baloon 36); the port draws flyers on the ground, so
  only rises are kept.
- **Direction:** `r = (cam_yaw + facing + 0x100) >> 9 & 7`; sequence `group*5 + [2,1,0,1,2,3,4,3][r]`,
  mirrored for r in {0, 1, 7}. The base side and diagonal frames face **left**.
- **Species code chunks:** `(0x132A + (s-1) x 0x54) x 0x800`, linked at 0x80170800. Handler table by state:
  0x0E idle, 0x10 walk, 0x11 melee, 0x12 spell (familiar mixing too), 0x07 hurt, 0x08 death, 0x05 sleep,
  0x19 Koh's menu. Unit state is at +0x9A (state, sub-state) and the sprite at +0xD4 (`re/scripts/timeline.py`).
  Groups seen live: Pulunpa hurt/death g10, melee g8; Kewne hurt g9, cast/mix g8, fainted g10; Baloon hurt
  g12, melee g8 (11.00, 16 frames) -> g9 (blow 20 in, phase 40) -> g10 (18). Noise's and Kraken's hit
  handlers only use their idle group (a flash and the knock-back). Troll's groups come in threes, one
  per weapon (club, mace, sword).

### Tower HUD, message window, backdrop (GPU frame dump on 2F, 2026-10-09)

- **Backdrop:** the first primitives of a tower frame (OT slot 7) are ~76 Gouraud-textured quads from the
  8bpp page at VRAM 768,0 (CLUT 0,495): each shows a 32x64-texel strip (u 0/32/64/96 across, v 0/64
  alternating down), in six rows whose top colours are 96, 80, 64, 48, 32, 16 (/128) fading to the next
  row's. It is the tower's inner wall seen around the floor. The page is uploaded at floor load as two
  64-row halves; the dumps hold 13 tile-set variants (palette hash per set); 2F = 91dffbd2 (dark green).
- **HUD:** OT slot 527, eight PolyFT4 (all colour 128) from texture pages 384,256 and 448,256 (rows 128+,
  i.e. VRAM 384,384 and 448,384, CLUT 0,496), screen <- uv: (115,26) 112x8 <- (8,208); (4,2) 112x32 <-
  (8,176) floor box; (223,2) 96x40 <- (8,216) gold box; (118,30) 104x24 <- page 448 (0,128) HP tube;
  (198,32) 8x16 <- (0,176); (147,11) 64x24 <- page 448 (0,152) HP box; (219,-36) 8x48 <- (0,192) pipe;
  (101,4) 128x48 <- (0,128) orb housing; then PolyF4 (204,40) 9x4 colour 112,32,32 and 176,176,0. The
  digits are copied into those pages: big 8x16 cells from page-448 row v=176, small 8x8 from v=192; the
  HP box text is the template at v=200 ("000/MAX 000").
- **Message window:** x 28-299, y 138-209 of the 320x224 frame (frame body 30-298 x 140-207, rivets
  8x8 in the corners), fill dark grey at the left to navy at the right, darker in the bottom 12 rows.
  Text: the 4bpp font page at VRAM 960,256 (ASCII from 0x20, 16 columns of 8x16 cells, CLUT 0,498),
  fixed 8-pixel advance, lines 18 pixels apart, first letter 12 pixels in. Page 960,0 holds the menu
  glyphs (digits, Yes/No, HP/MP).

### Combat timing (measured on the dev build, 60 Hz frames; `re/timelines/*.txt`)

| Event | Frames |
|---|---|
| Walk | 16 per tile |
| Koh's swing (state 0x11 sub-states) | approach 20, B0 8, B1 2, B8 16, B9 8, B4 2 (blow at 56), B5 22, B6 4, B7 12 |
| Koh swinging at nothing | B0 8, B1 2, B8 10, B9 8, B5 22, B6 4, B7 12; monsters act 16 after it ends |
| Lines | "<X>'s attack" at blow +20, damage at +36; 16 apart; the window keeps 3 |
| After the party's action | next unit 80 after the last line (Koh's swing start -> monster's swing: 174-178) |
| After a monster's blow | Koh's control back at blow +60 (last line +24) |
| Monster swing | per species: Pulunpa blow 14 into its sequence (64%); Baloon 11.00 wind-up 14 + 11.01 2, blow 20 into the strike sequence (36 from the start), hold 20, recover 18, end +22 |
| Kill | the victim holds until blow +102, fades 32; "Defeated X." at +156, then EXP lines |
| Level-up | Koh's sequence 36 (46 frames) at blow +140; lines after the EXP lines, then a button prompt |
| Mixed magic | "<Koh> chanted <mix>." during B8; the familiar sits in state 0x12 during the swing |
| Koh hit | no animation, a flash; faint = sequence 47 (72) then lying sequence 32 |
| Item use | sequence 204 (60) |

## VRAM layout (traced 2026-10-07)

Traced with a texture-upload tracker built for an HD texture experiment (not part of this repository):

| What | VRAM | How it gets there |
|---|---|---|
| Title background (8bpp 384x512, every texel STP) | 512,0 192x512 words, CLUT 0,496 | one upload |
| Menu font/frames (4bpp 128x128, 6 palettes) | 704,384, CLUTs 0..80,487 | one upload |
| Town tile pages (4bpp 128x128, several palettes each) | 320..640 x 256..512 | one upload per page |
| Character frames (Koh, girls; 8bpp ~12-18 words x 41-48 rows) | 896,0 / 896,43.. | uploaded every animation frame into a fixed slot, CLUT 0,488 / 0,510 |
| Character/item sheets (4bpp 128x128) | e.g. 480,384 / 544,384 / 768,384 | one upload each |
| Tower floor/wall/monster pages (8bpp) | 448..832 x 0..512 | uploaded at floor load in 32- or 64-word x 128-row blocks |
| Tower palettes | rows 448..463 (256 entries) and 485..497 (16) | uploaded one row at a time at floor load, then **re-lit every frame**: one primitive redraws (1..255, 448..462) mid-frame (after ~114 of ~500 textured draws), so the GPU holds the live palettes |
| Tower animated texture | 624,256 and 624,288 (16x32 words) | VRAM copy every frame from a strip |
| Tower HUD/minimap | 384..479 x 400..495 | assembled from 4x16 / 4x8 VRAM copies; 16bpp image at 768,192 also drawn by the GPU |
| HUD orb | CLUT 0,461 | palette cycled through 12 states |
| Animated 32x32 4bpp texture (title/menus) | 808,128 | uploaded every frame |

About 500 textured primitives per drawn frame in the tower, ~640 in Koh's house; the game draws
every other VBlank.

## Mods

In this repository:
- `mods_src/azure_gameplay.c` — native plugins, linked via `target_sources` in CMakeLists.txt.
- `mods_src/azure_journal.c`, `mods_src/azure_voice.c` — the Story Journal and Japanese Voices plugins.
- `mods/preloaded/packages/azure.gameplay/1.0.0/manifest.toml` — 14 features:
  - **Second Wind**: 5 → 10 → 15 → 16 HP over 300 frames at 30 frames/HP.
  - **EXP Rate** 200%: Pulunpa kill gave Koh 2 EXP and Kewne 2 (vanilla 1 each).
  - **Familiar Growth** 200%: Kewne L1→L2 base ATK/DEF/HP 8/8/26 (vanilla 7/7/19).
  - **Talent Inheritance**: Kewne × Pulunpa(talents 0x18) → Kewne 0x00900018 (vanilla 0x00900000); game
    printed "Strength Increased and Hard and Unbrainwashable".
  - **Fusion Absorption** 50%: Kewne ATK/DEF/HP/MP 6/6/12/100 → 8/8/18/120.
  - **Monster Strength** HP 150%: Pulunpa 8 → 12 HP. Rewritten 2026-10-08 after the owner found
    unhittable monsters at 25% HP: the old seen-list missed monsters the game was re-queuing
    (`FUN_8009A180` unlinks them for a moment) and scaled them again (2 → 0 HP; at 0 HP a live monster
    cannot be targeted but still attacks). Now a monster is scaled while its base ATK/DEF/HP equal the
    vanilla spawn values (base + curve(level−1), matched all 16 live spawns checked: 4 species, levels 1–60), so never
    twice, HP ≥ 1. Tested at 25%: six 2F monsters scaled once, unchanged after an exe restart + state
    reload, Koh killed one in one swing; a Pulunpa forced to 0 HP took no hits (symptom reproduced).
  - **Melee Damage** party 200%: Koh's hit −4 → −8 (traced write at the hook); enemy 50%: 2 → 1.
  - **Critical Strikes** 100%/300%: Koh's hit 4 → 12.
  - **Spell Damage** party 200% + **Elemental Affinity** +50%: Kewne Brid −7 → −21 (traced).
  - **Spell MP Cost** 50%: Brid cost 10 → 5 MP (tables read back 5 / 1).
  - **Spell Growth** 200%: Kewne L1→L2, Brid Lv1 → Lv3 (vanilla Lv2).
  - **Fair Level Down** (Gameplay Corrections), `re/scripts/lodown_test.py` from slot 3 (Kewne casts LoDown
    at effective level 255 on the Pulunpa set to level 10/30): normal 14/14/HP 39 → 13/13/37 (same as vanilla);
    frogged: vanilla kept 14/14/39, fixed → 13/13/37; Battnel at ATK/DEF 1: vanilla → 255/255, fixed → 1/1.
  - **Story Journal** (`mods_src/azure_journal.c` + generated `azure_journal_data.h`): the third answer
    of Weedy's Monster Book menu in Koh's house, [Show me your story journal.], opens it (SELECT in the
    Monster Hut until 2026-10-08); pick a girl, then a story beat (it becomes the next thing that
    happens) or an ending ("Complete", Cherrl has two). Applying sets/clears her chains' flags and her
    default portrait face (op 0x53); the town picks it up when the next location loads. Selfi set to
    Complete → portrait record 00000404 (default face 4 = in love); Close returns Koh to his idle state.
    Moved to Weedy 2026-10-08, tested from the owner's save after talking to her. The menu showed the
    three answers with her original text. The journal ran from plugin memory and Close returned Koh to
    idle. Sure still opened the Monster Book, and Too busy still ended the talk. SELECT in the hut (slot
    8) did nothing. The old SELECT `jal`, planted by hand, was put back (with the feature off it stayed).
    Driver for tests: `re/scripts/journal_drive.py`.
    2026-10-25: the summary box and the full beat list are gone. The +/>/- markers sit inside the
    picker's options: `option "["`, then flag tests choose the marker text, then the title. Op 0x0B
    only marks the cursor line, so text after it can branch like any other text. The picker opens
    on the page with her next beat, and a confirmed change returns to the girl list. Tested on the
    dev build from slot 11 (walked in, talked to Weedy). Nico opened on "> Meet Nico at home".
    Setting "Fountain drive starts" set 2434, and reopening showed "+ Meet…" / "> Fountain…".
    Setting beat 7 reopened on page 3 ("+ Nico after the fountain" / "> Square after the
    fountain"). The last page, Back to her first beat, and Close (Koh idle) all worked. The blob
    went from 73 KB to 57 KB.
  - **Japanese Voices** (group Audio, `mods_src/azure_voice.c` + generated `azure_voice_data.h`, needs
    the voice disc; detected by its size through `psx_mod_disc_sector_count()`, a small addition to the
    framework's mod API, so a save state loaded right after boot works): the constructor writes all
    snippets into plugin memory (fixed address, also with the feature off, so save states holding
    patched scripts stay valid); each VBlank it re-asserts the stream table, then for the loaded town
    chunk (`*(API+0x2C)` = base, first word) or, outside town, the absolute-address tower rows:
    replaces each voiced line's first bytes with `17 snippet` (snippet `30 1D a b <line bytes> 17 back`,
    skipped while the VM is inside that line), points overlay table entries at `30 1D a b 16` clips,
    plays follow-ups (`1D a b 17 <waitbtn>`, VM state set to running) once the line's voice has played
    while the VM still waits at that box, and at continuation waits swaps the button-wait state for a
    copy without the stop (MIPS at 0x8006778C). Tested with `re/scripts/voice_test.py` (dev build):
    slot 10 send-off 16 of 20 boxes voiced (the rest: on screen at load, unvoiced in JP ("Bonk!"), or
    continuation pages, where the voice carried over when Cross was pressed early); follow-up = two voice
    starts in one box; Cherrl's house (door swap) Nadia's "Welcome." voiced; a hospital clip called
    through its table snippet played and returned; on 1F all 64 tower-encounter lines patched and
    Ghosh's line played with its continuation wait; a save state loaded at frame 103 still voiced.
    Rows come in three classes: the loaded town chunk (base + first word), tower (absolute, outside
    town) and always (absolute: EXE gift reactions, overlay-program scripts). Wreath's door line and a
    gift reaction were run in slot 10 and voiced.
    Fixed 2026-10-09 (owner: no voices for Nico's fountain drive or Ghosh): a chunk brought back from the
    loader's cache has a stale first word (see Town events → Script chunks), so the plugin never
    recognised it, and it was voiced only if a VBlank had caught it at the base during the arrival
    loads (4516 did once, 4513 did not). Now a chunk whose first word names nothing is recognised by
    its voiced lines (original bytes or our patch; no two chunks of a base share one, checked over all
    51 chunk/base pairs), and the chunks waiting in the cache are patched in place, so a conversation's
    first line is voiced too. Owner's save, real flow (walk out of the house, talk to Nico, donate 1G):
    old plugin 0 of 12 boxes voiced; fixed 11 of 12 with CD audio, including all six of Ghosh's
    boxes (box 2 is the tail of voice 1). Slot 10 send-off unchanged (21 voiced of 30, 7 carried).
- `game.toml` `[recompiler] mod_function_entry_funcs = ["0x80042900"]` (needed by the combat hooks;
  requires `generate` + rebuild).
- Enable without the launcher by writing `build-dev/mods/state.toml` (format 2; example in `re/MODDING.md`).
- `mods/preloaded/packages/azure.dungeon/1.0.0/manifest.toml` (generated by
  `re/scripts/make_dungeon_mod.py`, declarative disc patches):
  - **Monster Density** 15/15, base 5, spread 0: 16 monsters on floor 2 (vanilla 4–8), spawn timer 5.
  - **Item Rarity** rare/very rare 400: patched weights live in the floor overlay; the generator's
    category totals reflect them (balls category 448 → 5,600).
  - **Deeper Encounters**: floor 2 got floor 7's table (U-Boat 7, Baloon 5, Blume 6, Manoeva 5).
  - **Fix: Strength Increased**: patched word present after a fresh tower entry; Koh 88 → 99 damage.
  - **Fix: Gaia Shoot**, **Fix: Barong rarity**: bytes verified on disc in every copy; not play-tested.
  - **Floor Layout** group (Room Grid, Room Frequency, Room Size, Open Floors, Floor Elevation,
    Items per Floor, Traps per Floor), tested with `re/scripts/layout_test.py` on 2F
    (renders: `re/shots/layout_*.png`, side by side in `layout_presets.png`):
    vanilla 7–8 rooms / 10–12 items / 4 traps · grid 3×3 + always rooms + size +4: 2–5 rooms of area
    110–132, flat · room chance 50% + items lots + traps more: 4–7 rooms, 10–12 items, 3–9 traps ·
    always rooms + size +1 + traps lots + gentle: 8–11 rooms, 11–14 traps, heights {0, 32} ·
    open floors 100% + no traps: one 60×60 room, 14 items, 0 traps · grid 2×2 + size +10: open floor
    (as the simulator predicts), 27 items. Elevator reachable in every case; Koh walked a modded 2F,
    rode up and 3F generated with the same settings.

Mod primitives available (psxrecomp `runtime/include/mod_plugins.h`): VBlank and activation
callbacks, function-entry hooks for EXE functions listed in `game.toml`
`[recompiler] mod_function_entry_funcs`, guest memory read/write, `psx_mod_write_code_word`,
extra guest memory from Expansion 1, launcher-rendered options. Declarative manifests can also
patch EXE bytes (`main_exe`) and disc bytes (`disc_user`/`disc_raw`, which is how module code
in TOWN.BIN/DUNGEON.BIN can be patched).

Town landmarks (x, z in whole units): Koh's house front ≈ (0x0E00, 0x0E20);
north road x ≈ 0x1020; tower stairs reached at ≈ (0x101A, 0x043D); central square pond ≈ (0x0F00–0x1200,
0x1000–0x1400); during the fountain drive Nico (slot 4/1) stands at (0x11E0, 0x11E0) and a townswoman
(slot 4/0, chunk 4513) at (0x1020, 0x1020). Teleport Koh by writing 16.16 x/z to 0x80083780/0x80083784 (the
camera follows); town actors keep 16.16 `{x, z, y}` in the heap around 0x801E0000.

## Save states (dev build, slots 0–11)

Files: `saves/scph1001/state_80033930_slotNN.pst` (survive rebuilds). They hold the game's RAM, so they
are not in the repository: make your own at the places listed with the harness (`g.save_state(n)`).
A state holds RAM as it was, including any module code loaded at the time.

| Slot | Where |
|---|---|
| 0 | town, at the tower stairs before the Kewne event (start point of `enter_tower.py`) |
| 1 | 1F tutorial start |
| 2 | 1F, free control, Kewne collared |
| 3 | 1F, Koh at (55,40) next to a level-1 Pulunpa at (54,40), unit 0x801EC920 |
| 4 | 1F, Koh standing on the elevator (start point of `layout_test.py`) |
| 5 | 2F (made while Deeper Encounters was enabled); Koh next to a Baloon (unit 0x801EF10C), Kewne (0x801EB374) on a Mix order (Flay Finger); used by `exp_react.py` |
| 6 | 1F tutorial start after a fresh entry with the dungeon fixes enabled |
| 7 | Koh's bedroom, in control |
| 8 | Monster Hut |
| 9 / 10 | house, before the send-off event |
| 11 | outside the house |

## Known runtime quirks

- Title menu text flickers grey in some screenshots (capture timing, unconfirmed on screen).
- One unreproduced freeze: walking into the house's east doorway at a diagonal
  left Koh invisible with input ignored. Replaying straight right worked.

## Koh's tower controls (input handlers)

Pad words: held 0x80083168, new presses 0x80083170. Bits: L2 0x1, R2 0x2, L1 0x4, R1 0x8,
Triangle 0x10, Circle 0x20, Cross 0x40, Square 0x80, Select 0x100, Start 0x800, Up 0x1000,
Right 0x2000, Down 0x4000, Left 0x8000. Koh's handler pointer is his control object +0x8C:
`FUN_8008ACDC` normally, `FUN_8008EAC8` while he carries something (+0x1C & 0x100000).
His state table (indexed state + 1 from 0x800DD160): 0x1A bag throw `FUN_8008E700`, 0x1B lift
`FUN_8008F428`, 0x1C wait `FUN_8008EA40`, 0x1F set down `FUN_8008F878`, 0x20 throw `FUN_8008FA7C`.
Koh's actions are recorded with `FUN_8009F644(koh, code)`: 8 step, 0x10 wait, 0x20 lift, 0x28 set
down, 0x30 throw. A state ends Koh's turn by setting DAT_80083462 |= 0x412 and refilling action
points (`FUN_80099F70` / `FUN_80099F04`).

- D-pad: `FUN_8009074C` turns the camera-relative pad into a facing; with Triangle held Koh only
  turns. Chaos adds a random facing to a step (`FUN_800A6D30() & 0xE00`).
- Square held: command menu (`FUN_80050CAC`; bound Koh: `FUN_8004F5F4`, else he just waits).
- R2 / L2 (Triangle not held): `FUN_8008D024(slot)`, slot = (pad >> 1 ^ 1) & 1, so R2 = familiar
  slot 0, L2 = slot 1: that familiar's order ring (state 0x27).
- Triangle+Circle held (0x30): wait (`FUN_8008C7B4`, state 0x1C). With Circle held and no unit
  within 5 tiles that is awake, not party and not out of MP (+0x1C & 0x2208, `FUN_800A5C70`),
  DAT_80083462 |= 0x80 skips the wait's pause (back-to-back resting).
- Cross: attack (`FUN_8008C8BC`); Circle+Cross: lift (`FUN_8008C5C4`). While carrying: Cross =
  set down (`FUN_8008F6EC`), Circle+Cross = throw (`FUN_8008FA14`, 6-frame wind-up).
- Lift (`FUN_8009B5AC`): the unit on the tile ahead at Koh's height (`FUN_8009A540`), else the item
  lying there (made into a held object, DAT_80081484 = its record; a unit in hand is recorded as
  category 0x13). No unit: nothing happens. A unit without +0x14 & 0x80000 (species flags bit
  0x80000): 16 frames, "<X> was too heavy to lift." (0x800E0683), no turn. 1F tutorial
  (DAT_80012090 == 1) Kewne / chunk 0x39: "<X> cannot be lifted on this floor." (0x800E0495).
  Otherwise the unit gets +0x1C |= 0x80000, Koh 0x100000, unit +0x60 = Koh; then (`FUN_8008F428`)
  if the unit is party (+0x1C & 0x2000) or helpless (& 0x228) or `FUN_800A6DA4(0, 16)` (rand % 17)
  > 5 he holds it with no turn spent; else it shakes for 16 frames, "<X> didn't like being lifted."
  (0x800E0523), drops back and the turn ends.
- Set down: a unit goes to the tile ahead if it could step there (`FUN_8009A66C(dir, .., 0x20)`);
  the unit's +0x6D (action points, high byte) = 0, so it can't act this turn. An item goes where
  `FUN_800A7234` puts it. Turn ends.
- Throw distance `FUN_8009AF18(dir, 8)`: tile by tile, stop before a blocked tile or one with no
  passage (`FUN_800A0548`, `FUN_8009A350`), at the first tile with units (0x3300; that unit is hit,
  except a Barong (0x1F) awake catches a thrown item: +0x14 |= 0x800000), or before ground too high
  (`FUN_800BCB04` >= 0x200). 0 = no throw (no turn). The thrown object gets +0x1C |= 0x200000,
  +0x8A = distance, accuracy +0x84 = 0x78, power +0x85 = 2. Bag Throw (`FUN_8008E700`) is the same
  with the item lifted and thrown at once.
- Camera (`FUN_80096100`): L1 held +0x200 / R1 held -0x200 yaw (45 degrees) whenever the last turn
  is done (DAT_800832B4), Triangle not held. Triangle+L2: pitch preset DAT_800120A2 of
  {-640, -704, -544, -384} (0x800DD264, 4096 = full turn) into 0x800DCE60. Triangle+L1: distance
  preset DAT_800120A0 of {1024, 512, 800, 1088} (0x800DD26C) into 0x800DCE66. Triangle+R2:
  0x800DC888, the status display object's mode (saved at 0x800133A0) steps 0 -> 1 -> 2: both
  layers / the first / hidden (+0x54 bits 1, 2).
- Select+Start held about 120 frames: soft reset (`FUN_8003D92C`).

## Familiar orders (checked on the dev build 2026-10-21, slots 2 and 5)

R2 (slot 0, +0xAC) / L2 (slot 1, +0xB0) held opens the familiar's ring (Koh state 0x27, `FUN_80091430`;
only for a familiar that is out and following, +0x1C & 0x20000, not held 0x80000). While the trigger
is held: the d-pad turns the familiar (action 0x70; no turn), and the face buttons open:
- Triangle **COMMAND** (`0x8001EF2C`): one-shot orders, aimed by the familiar's facing (the menu marks
  the tile), written to +0x46 by action 0x80 without spending Koh's turn; they run in the familiar's next
  act: **Move** 0x800B ("Move to current direction only": the step code skips following Koh when +0x46
  has 0x8000 and tries its facing with the usual 8 turns), **Direct** 0x8008 ("Attack directly"),
  **Direct:<spell>** 0x8001+slot (casts along its facing even at nothing: MP spent, "<X> chanted
  <spell>."), **Mix.:<spell>** 0x8005+slot (mixed into Koh's next swing; a leftover plan passes),
  **Stay** 0x800C ("Stay and do nothing").
- Circle **LINE UP** (`0x80023C58`): "Change Line up" (pick one of the 8 tiles round Koh: +0x45, relative
  to his facing; immediate, no turn) and "Change AI" (5 cards, `FUN_80021760`: mode +0x12 = 4 - card
  index, action 0x78; no turn): 5 "Attack aggressively" = 0, 4 "Attack directly" = 1, 3 "Back up with
  magic" = 2 (default), 2 "Follow me" = 3, 1 "Stand-by" = 4. No card is locked (cards up to the cursor
  are lit, a level bar).
- Square **BACK** (`FUN_8009402C` / `FUN_8008DB0C`): "Red collar: <name> returned into the bag." The
  familiar leaves the floor and sits in the bag as an entry (KEWNE-type familiar; Select / Return /
  Name); Koh's turn passes.
- Cross **STATUS**.
Square menu: Items, Select (assign collared familiars to the R2 / L2 slots; "Collar" takes one out:
"<name> was taken out.", placed where it stood / next to Koh, the turn passes), Line up, Fuse, C'and,
Feet. Circle + d-pad = run (tutorial text "Run with Directional button while pressing ○ button!").
