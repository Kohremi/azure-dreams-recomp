# Mod reference

Every mod in this project, with its options as the launcher shows them. Generated from the
mod manifests by `re/scripts/mods_doc.py`; do not edit by hand.

All mods start switched off. Open the launcher, click **Mods**, switch on what you want and
set its options. Unless noted, a mod only needs the US disc.

## Azure Dreams Gameplay Mods (`azure.gameplay`)

New mechanics for Azure Dreams familiars, fusion and combat, implemented as native plugins. Made with: mods_src/azure_gameplay.c, azure_journal.c, azure_voice.c (C plugins).

### Koh

#### Second Wind

Koh slowly regenerates HP over time while inside the Monster Tower. Never revives and never heals past max HP.

| Option | Values | Default |
|---|---|---|
| Frames per HP — How many frames (60 per second) it takes to regenerate 1 HP. | 10 to 3600 (step 10) | 120 |

### Familiars

#### EXP Rate

Scales the EXP Koh and his familiars earn from defeating monsters.

| Option | Values | Default |
|---|---|---|
| EXP earned (%) | 10 to 1000 (step 10) | 200 |

#### Familiar Growth

Multiplies the ATK, DEF, HP and MP a familiar gains each time it levels up.

| Option | Values | Default |
|---|---|---|
| Stat gain per level (%) | 100 to 500 (step 10) | 150 |

### Fusion

#### Talent Inheritance

Fused familiars keep every talent from both parents (Quick, Hard, immunities ...) instead of only their species' innate ones, so talents can be stacked over several fusions.

#### Fusion Absorption

The surviving familiar absorbs part of the other familiar's base ATK, DEF, HP and MP.

| Option | Values | Default |
|---|---|---|
| Stats absorbed (%) | 5 to 100 (step 5) | 25 |

### Combat

#### Monster Strength

Scales the HP, ATK and DEF of wild monsters in the tower when they appear.

| Option | Values | Default |
|---|---|---|
| Monster HP (%) | 25 to 400 (step 5) | 150 |
| Monster ATK (%) | 25 to 400 (step 5) | 120 |
| Monster DEF (%) | 25 to 400 (step 5) | 120 |

#### Melee Damage

Scales melee damage separately for attacks made by Koh and his familiars and attacks made by monsters. Every hit still deals at least 1 damage.

| Option | Values | Default |
|---|---|---|
| Damage dealt by your party (%) | 10 to 500 (step 5) | 125 |
| Damage dealt by monsters (%) | 10 to 500 (step 5) | 100 |

#### Critical Strikes

New mechanic: melee hits by Koh and his familiars have a chance to land a critical strike for extra damage.

| Option | Values | Default |
|---|---|---|
| Critical chance (%) | 1 to 100 (step 1) | 10 |
| Critical damage (%) | 110 to 500 (step 10) | 200 |

### Magic

#### Spell Damage

Scales damage from attack spells (Breath, Sled, Brid, Rise, Grave ...) separately for spells cast by your party and by monsters (and traps). Every hit still deals at least 1 damage.

| Option | Values | Default |
|---|---|---|
| Spell damage dealt by your party (%) | 10 to 500 (step 5) | 125 |
| Spell damage dealt by monsters and traps (%) | 10 to 500 (step 5) | 100 |

#### Elemental Affinity

New mechanic: a familiar casting an attack spell of its own element (a fire familiar casting Brid, a water familiar casting NeaBrid ...) deals bonus damage. Fusion picks the element, so this rewards planning fusions.

| Option | Values | Default |
|---|---|---|
| Bonus damage (%) | 5 to 200 (step 5) | 50 |
| Monsters get the bonus too | on / off | off |

#### Spell Growth

When a familiar levels up, the spells that grow gain extra spell levels. Spell level adds directly to spell power.

| Option | Values | Default |
|---|---|---|
| Spell level gain per level-up (%) | 100 to 500 (step 10) | 200 |

#### Spell MP Cost

Scales the MP every spell costs, for both normal casts and weapon enchants.

| Option | Values | Default |
|---|---|---|
| MP cost (%) | 10 to 300 (step 10) | 50 |

### Town

#### Story Journal

Talk to Weedy in Koh's house: her Monster Book question gets a third answer, [Show me your story journal.], which opens a journal of each girl's town story. It shows where each story stands and lets you pick the next event or an ending; the town plays it out once you step outside. Edit re/events/journal.toml and run re/scripts/make_journal.py to change or add entries.

**Needs:** `prepare.py` run on your US disc (it builds the journal's data).

### Gameplay Corrections

#### Fair Level Down

LoDown and level-down traps take back only what a level actually gave. Frogged monsters can no longer dodge the loss (their real species is used, not the frog's), and evolved monsters such as a Battnel raised from a Nyuel can no longer have stats wrap around to 255: no stat drops below the species' level-1 value.

### Audio

#### Japanese Voices

Plays the Japanese release's voice acting in town conversations and the voiced tower scenes (townspeople you meet in the tower, Beldo). Needs the voice disc image made by re/scripts/build_voice_disc.py from your US and Japanese discs (it adds the Japanese voice files to the US disc); with the plain US disc this does nothing.

**Needs:** your Japanese disc, `prepare.py` (it builds the voice disc and the voice mapping), and playing from `disc/Azure Dreams (USA) (JP Voices).cue`.

## Azure Dreams Dungeon Mods (`azure.dungeon`)

Monster Tower tuning: monster density, item rarity and encounter tables. Generated by re/scripts/make_dungeon_mod.py. Made with: declarative patches (no C code).

### Dungeon

#### Monster Density

How many monsters a floor starts with and how often new ones appear (vanilla: 4-8 at start, one more every 32-63 turns, at most 32).

| Option | Values | Default |
|---|---|---|
| Monsters at floor start (min) | 0 to 30 (step 1) | 4 |
| Monsters at floor start (max) | 0 to 30 (step 1) | 8 |
| Turns between spawns (minimum) | 1 to 999 (step 1) | 32 |
| Extra random turns between spawns | 0-0, 0-7, 0-15, 0-31, 0-63, 0-127 | 0-31 |

#### Item Rarity

Weights used when the floor generator picks items by rarity tier (vanilla 128 / 85 / 32 / 1). Raise the rare tiers to find Dark/Holy swords, Bow Guns, Roche and Big Pita more often.

| Option | Values | Default |
|---|---|---|
| Common items | 1 to 400 (step 1) | 128 |
| Uncommon items | 1 to 400 (step 1) | 85 |
| Rare items | 1 to 400 (step 1) | 32 |
| Very rare items | 1 to 400 (step 1) | 1 |

#### Deeper Encounters

Every floor uses the monster table of the floor 5 levels higher (egg pools unchanged). Example of an encounter-table edit; make your own with re/scripts/make_dungeon_mod.py --custom.

### Floor Layout

#### Room Grid

Sets how many room cells the floor generator lays out across and down (vanilla: 4x4 almost always, rarely 3 or 2). Fewer cells = fewer, bigger rooms with longer corridors. Simulated averages: 4x4 6.6 rooms of area 40; 3x3 4.8 rooms of area 54; 2x2 2.6 rooms of area 105 (23% of 2x2 floors collapse into one open room).

| Option | Values | Default |
|---|---|---|
| Cells across | 2 to 4 (step 1) | 4 |
| Cells down | 2 to 4 (step 1) | 4 |

#### Room Frequency

Chance that a grid cell holds a room instead of a bare corridor junction (vanilla 75%). Simulated averages: 50% 4.8 rooms, 75% 6.6, 94% 8.0, always 8.4.

| Option | Values | Default |
|---|---|---|
| Room chance | 50%, 75% (vanilla), 88%, 94%, Always | 75% (vanilla) |

#### Room Size

Makes rooms larger. A room that no longer fits in its cell becomes a bare corridor junction, so size trades against count. Simulated averages (4x4): +1/+1 5.7 rooms of area 54; +2/+2 4.9 of 69; +3/+3 4.2 of 87. Combine with Room Frequency Always to keep the count up (+1/+1: 7.1 rooms of area 53).

| Option | Values | Default |
|---|---|---|
| Extra width (tiles) | 0 to 10 (step 1) | 1 |
| Extra height (tiles) | 0 to 10 (step 1) | 1 |

#### Open Floors

Chance that a floor is generated as one huge open room (vanilla 2 in 513, about 0.4%). Open floors get 8-15 items and 4-7 traps.

| Option | Values | Default |
|---|---|---|
| Open floor chance | Never, 5%, 10%, 25%, 50%, Every floor | 5% |

#### Floor Elevation

Height differences between rooms (vanilla: rooms sit at one of 4 heights).

| Option | Values | Default |
|---|---|---|
| Elevation | Flat (all rooms level), Gentle (2 heights) | Flat (all rooms level) |

#### Items per Floor

How many items the generator places (vanilla: rooms/2 + 0-3, open floors 8-15; at most 64).

| Option | Values | Default |
|---|---|---|
| Items | Fewer (rooms/4 + 0-3), More (rooms + 0-3), Lots (rooms + 0-7) | More (rooms + 0-3) |

#### Traps per Floor

How many traps the generator places (vanilla: rooms/2 + 0-3 slots, open floors 4-7, limited by a budget of floor/2 + 0-63 where each trap costs 4-12). More/Lots also raise the budget (0-127 / 0-255).

| Option | Values | Default |
|---|---|---|
| Traps | None, Fewer (rooms/4 + 0-3), More (rooms + 0-3), Lots (rooms + 0-7) | Fewer (rooms/4 + 0-3) |

### Gameplay Corrections

#### Fix: Strength Increased familiars

Each collared familiar with the Strength Increased talent was meant to add 1/8 to Koh's melee and sword mix-magic damage, but the check (dungeon FUN_800C82B8) reads Koh's talents instead of the familiar's, so it never applies. One-instruction fix.

#### Fix: Gaia Shoot element

DeoRock's mixture magic Gaia Shoot deals water damage although DeoRock is a wind spell (its fire/water siblings use their own element). Makes its damage wind-elemental.

#### Fix: Barong item rarity

Barongs are meant to give back an item of the same rarity as the one thrown in (or lower after a few tries), but the check compares the thrown item with itself and always passes. Fixed to compare the candidate item.
