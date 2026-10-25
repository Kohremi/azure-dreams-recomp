/*
 * Azure Dreams gameplay mods (trusted static plugins).
 *
 * Each plugin is selected by a feature in mods/preloaded/packages/azure.gameplay.
 * Everything here works on guest state documented in C:\CODE\AZURE_CLAUDE\re\NOTES.md:
 *
 *   Unit record (Koh, familiars, monsters; Koh is fixed at 0x800834B8)
 *     +0x00 u8 base ATK     +0x01 u8 base DEF     +0x04 u8 base MP    +0x05 u8 base HP
 *     +0x11 u8 level        +0x13 u8 species      +0x14 u32 flags (bits 0-2 element, 0x4000 party)
 *     +0x18 u32 total EXP   +0x25 u8 MP           +0x26 u8 ATK         +0x27 u8 DEF
 *     +0x28 u8 HP           +0x29 u8 max HP       +0x41/+0x42 pending EXP (big endian)
 *     +0x54 u32 talents     +0x5C next unit - 0x20 (circular list, head at *0x800814A8)
 *     +0x66 u8 max MP       +0x68 u8 max ATK      +0x69 u8 max DEF
 *     Koh +0xAC / +0xB0     familiar slots
 *   Dungeon module resident at 0x80088760 while in the tower; fusion overlay at 0x80025000.
 */
#include "mod_plugins.h"
#include "cpu_state.h"

#include <stdlib.h>

#define PKG "azure.gameplay"

#define KOH          0x800834B8u
#define UNIT_HEAD    0x800814A8u
#define MAX_UNITS    96

#define rb psx_mod_read_byte
#define wb psx_mod_write_byte
#define rw psx_mod_read_word
#define ww psx_mod_write_word

/* ---- shared helpers ------------------------------------------------------ */

/* First words of dungeon-module function 0x8009BFF8; the town module has
 * different code at the same address, so this tells the two apart. */
static int in_tower(void) {
    return rw(0x8009BFF8u) == 0x27BDFFC8u && rw(0x8009BFFCu) == 0xAFB10024u &&
           rw(0x8009C000u) == 0x00808821u && rw(0x8009C004u) == 0xAFBF0030u;
}

/* Fusion overlay (DUNGEON.BIN +0x182C000) resident at 0x80025000. */
static int fusion_overlay_resident(void) {
    return rw(0x8002534Cu) == 0x27BDFFE0u && rw(0x800253C0u) == 0x27BDFFB0u;
}

static int valid_ptr(uint32_t p) {
    return p >= 0x80010000u && p < 0x80200000u;
}

static long option_number(const char* feature, const char* id, long fallback) {
    char text[32] = "";
    if (!psx_mod_option_value(PKG, feature, id, text, sizeof text) || !text[0])
        return fallback;
    char* end = NULL;
    long v = strtol(text, &end, 10);
    return (end && *end == '\0' && v > 0) ? v : fallback;
}

static uint8_t clamp8(long v) {
    return (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
}

/* Port of the stat half of EXE FUN_80041E70: max values = base, doubled by
 * the HP+/MP+/Strength+/Hard talents. */
static void recompute_max_stats(uint32_t u) {
    uint32_t tal = rw(u + 0x54);
    wb(u + 0x29, clamp8(rb(u + 0x05) * ((tal & 0x02) ? 2 : 1)));
    wb(u + 0x66, clamp8(rb(u + 0x04) * ((tal & 0x04) ? 2 : 1)));
    wb(u + 0x68, clamp8(rb(u + 0x00) * ((tal & 0x08) ? 2 : 1)));
    wb(u + 0x69, clamp8(rb(u + 0x01) * ((tal & 0x10) ? 2 : 1)));
    /* spell slots: id at +8/+0xB/+0xE, effective level +1, base level +2;
     * effective = base, doubled by the Magic Attack talent, capped at 99 */
    for (uint32_t s = 0x08; s <= 0x0E; s += 3) {
        if (!rb(u + s)) continue;
        long eff = rb(u + s + 2) * ((tal & 0x80) ? 2 : 1);
        wb(u + s + 1, (uint8_t)(eff > 99 ? 99 : eff));
    }
}

/* Add to a stat that has a base byte and a current byte (both move together
 * on vanilla level-up). */
static void add_stat(uint32_t u, uint32_t base_off, uint32_t cur_off, long amount) {
    if (amount == 0) return;
    wb(u + base_off, clamp8(rb(u + base_off) + amount));
    wb(u + cur_off, clamp8(rb(u + cur_off) + amount));
}

static uint32_t familiar(int slot) {
    uint32_t p = rw(KOH + 0xACu + 4u * (uint32_t)slot);
    return valid_ptr(p) ? p : 0;
}

#define BASE_TABLE    0x8006D168u   /* EXE: species base stats, 0x18 bytes each   */
#define GROWTH_TABLE  0x800DDCBCu   /* dungeon module: species growth, 8 bytes each */

static uint32_t isqrt64(uint64_t x) {
    uint64_t r = 0, bit = (uint64_t)1 << 62;
    while (bit > x) bit >>= 2;
    while (bit) {
        if (x >= r + bit) { x -= r + bit; r = (r >> 1) + bit; }
        else r >>= 1;
        bit >>= 2;
    }
    return (uint32_t)r;
}

/* Stat curve of the level-up/level-down routines at n levels gained.
 * Offsets follow the unit record: 0 ATK, 1 DEF, 2, 3, 4 MP, 5 HP. */
static long stat_curve(int sp, int stat, long n) {
    uint32_t b = BASE_TABLE + (uint32_t)sp * 0x18u, g = GROWTH_TABLE + (uint32_t)sp * 8u;
    long bs = rb(b + (uint32_t)stat), gs = rb(g + (uint32_t)stat);
    if (n < 0) n = 0;
    switch (stat) {
    case 5: {   /* HP: b + g*n/16 + g*SquareRoot12(n*g*2048)/32768 */
        long sq = (long)isqrt64((uint64_t)(n * gs * 0x800) * 4096u);
        return bs + ((gs * n) >> 4) + ((gs * sq) >> 15);
    }
    case 4: case 3: return (gs * bs * n) >> 10;
    default:        return (gs * bs * n) >> 6;
    }
}

/* Base stat of a unit of species sp spawned at level lv: spawning creates it at level 1 from
 * the species table, then the level-up routine (dungeon FUN_800A1D4C) adds
 * curve(L) - curve(L-1) per level, capped at 255. */
static long spawn_stat(int sp, int stat, int lv) {
    long v = rb(BASE_TABLE + (uint32_t)sp * 0x18u + (uint32_t)stat) +
             stat_curve(sp, stat, lv - 1) - stat_curve(sp, stat, 0);
    return v > 255 ? 255 : v;
}

/* ---- Second Wind: Koh slowly regenerates HP while in the tower ---------- */

static unsigned s_regen_period;   /* guest frames per +1 HP */
static unsigned s_regen_counter;

static void second_wind_activate(void) {
    s_regen_period = (unsigned)option_number("second-wind", "frames_per_hp", 120);
    s_regen_counter = 0;
}

static void second_wind_vblank(void) {
    if (!psx_mod_game_started() || !in_tower())
        return;
    if (++s_regen_counter < s_regen_period)
        return;
    s_regen_counter = 0;
    uint8_t hp = rb(KOH + 0x28);
    uint8_t max = rb(KOH + 0x29);
    if (hp > 0 && hp < max)  /* never revive, never overheal */
        wb(KOH + 0x28, (uint8_t)(hp + 1));
}

/* ---- EXP Rate: scale EXP earned by Koh and familiars --------------------
 * Kills write EXP into a pending field (+0x41/+0x42, big endian) that the
 * game folds into the total a couple of frames later. Only the growth of the
 * pending value since our last write is scaled, so nothing is scaled twice. */

static long s_exp_pct;
static uint32_t s_exp_unit[3];
static unsigned s_exp_last[3];

static void exp_rate_activate(void) {
    s_exp_pct = option_number("exp-rate", "percent", 200);
    for (int i = 0; i < 3; i++) { s_exp_unit[i] = 0; s_exp_last[i] = 0; }
}

static void exp_rate_vblank(void) {
    if (!psx_mod_game_started() || !in_tower() || s_exp_pct == 100)
        return;
    for (int i = 0; i < 3; i++) {
        uint32_t u = i == 0 ? KOH : familiar(i - 1);
        if (u != s_exp_unit[i]) { s_exp_unit[i] = u; s_exp_last[i] = 0; }
        if (!u) continue;
        unsigned pending = ((unsigned)rb(u + 0x41) << 8) | rb(u + 0x42);
        if (pending == 0) { s_exp_last[i] = 0; continue; }
        if (pending <= s_exp_last[i]) continue;
        unsigned gained = pending - s_exp_last[i];
        unsigned scaled = s_exp_last[i] + (unsigned)((gained * s_exp_pct + 99) / 100);
        /* The "+N EXP" popup treats the amount as signed 16-bit: 32767+ shows
         * garbage or crashes (community-documented), so stay below that. */
        if (scaled > 32766) scaled = 32766;
        wb(u + 0x41, (uint8_t)(scaled >> 8));
        wb(u + 0x42, (uint8_t)scaled);
        s_exp_last[i] = scaled;
    }
}

/* ---- Familiar Growth: multiply the stats a familiar gains per level -----
 * Vanilla level-up (dungeon FUN_800A1D4C) adds a per-species curve delta to
 * base ATK/DEF/MP/HP. We watch each familiar slot, and when its level rises we
 * add (percent - 100)% of the gain it just got. */

typedef struct { uint32_t unit; uint8_t sp, lv, atk, def, mp, hp, spell_id[3], spell_lv[3]; } Snap;

static long s_growth_pct;
static Snap s_growth[2];

static void snap_unit(Snap* s, uint32_t u) {
    s->unit = u;
    s->sp = rb(u + 0x13); s->lv = rb(u + 0x11);
    s->atk = rb(u + 0x00); s->def = rb(u + 0x01); s->mp = rb(u + 0x04); s->hp = rb(u + 0x05);
    for (int k = 0; k < 3; k++) {
        s->spell_id[k] = rb(u + 0x08 + 3u * (uint32_t)k);
        s->spell_lv[k] = rb(u + 0x0A + 3u * (uint32_t)k);
    }
}

static void familiar_growth_activate(void) {
    s_growth_pct = option_number("familiar-growth", "percent", 150);
    s_growth[0].unit = s_growth[1].unit = 0;
}

static void familiar_growth_vblank(void) {
    if (!psx_mod_game_started() || !in_tower())
        return;
    for (int i = 0; i < 2; i++) {
        uint32_t u = familiar(i);
        Snap* s = &s_growth[i];
        if (!u) { s->unit = 0; continue; }
        if (s->unit != u || s->sp != rb(u + 0x13)) { snap_unit(s, u); continue; }
        uint8_t lv = rb(u + 0x11);
        if (lv > s->lv) {
            long extra = s_growth_pct - 100;
            add_stat(u, 0x00, 0x26, (rb(u + 0x00) - s->atk) * extra / 100);
            add_stat(u, 0x01, 0x27, (rb(u + 0x01) - s->def) * extra / 100);
            add_stat(u, 0x04, 0x25, (rb(u + 0x04) - s->mp) * extra / 100);
            add_stat(u, 0x05, 0x28, (rb(u + 0x05) - s->hp) * extra / 100);
            recompute_max_stats(u);
        }
        snap_unit(s, u);
    }
}

/* ---- Spell Growth: familiars' spells gain extra levels on level-up -------
 * Vanilla level-up raises each spell whose category matches the familiar's
 * element bits by 1 + (99-lv)/(100-L). We add (percent-100)% of that gain
 * (at least +1 when the spell grew at all and percent > 100). */

static long s_spell_growth_pct;
static Snap s_spell_growth[2];

static void spell_growth_activate(void) {
    s_spell_growth_pct = option_number("spell-growth", "percent", 200);
    s_spell_growth[0].unit = s_spell_growth[1].unit = 0;
}

static void spell_growth_vblank(void) {
    if (!psx_mod_game_started() || !in_tower())
        return;
    for (int i = 0; i < 2; i++) {
        uint32_t u = familiar(i);
        Snap* s = &s_spell_growth[i];
        if (!u) { s->unit = 0; continue; }
        if (s->unit != u || s->sp != rb(u + 0x13)) { snap_unit(s, u); continue; }
        if (rb(u + 0x11) > s->lv) {
            int changed = 0;
            for (int k = 0; k < 3; k++) {
                uint32_t slot = u + 0x08 + 3u * (uint32_t)k;
                uint8_t lv = rb(slot + 2);
                if (rb(slot) == 0 || rb(slot) != s->spell_id[k] || lv <= s->spell_lv[k]) continue;
                long extra = (long)(lv - s->spell_lv[k]) * (s_spell_growth_pct - 100) / 100;
                if (extra < 1 && s_spell_growth_pct > 100) extra = 1;
                long nlv = lv + extra;
                wb(slot + 2, (uint8_t)(nlv > 99 ? 99 : nlv));
                changed = 1;
            }
            if (changed) recompute_max_stats(u);
        }
        snap_unit(s, u);
    }
}

/* ---- Spell MP Cost: rescale the cast / enchant MP cost tables ------------
 * Dungeon-module data: 0x800DD880 = MP per normal cast (whole points),
 * 0x800DD8B4 = MP per enchant cast (quarter points), both indexed by spell id
 * 1..51. The module is reloaded from disc on every tower visit, so the tables
 * are rewritten whenever they read back as the stock values. */

#define MP_CAST_TABLE     0x800DD880u
#define MP_ENCHANT_TABLE  0x800DD8B4u
static const uint8_t MP_CAST_STOCK[52] = {
    0, 12, 12, 12, 8, 8, 8, 10, 10, 10, 16, 16, 16, 8, 8, 8, 8, 8, 8, 8, 8, 8, 6, 6, 6,
    10, 10, 10, 16, 16, 16, 8, 8, 8, 12, 12, 12, 10, 10, 10, 9, 9, 9, 12, 12, 12, 20, 20, 20, 32, 32, 32 };
static const uint8_t MP_ENCHANT_STOCK[52] = {
    0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 8, 8, 8,
    2, 2, 2, 2, 2, 2, 16, 16, 16, 16, 16, 16, 16, 16, 16, 3, 3, 3, 16, 16, 16, 32, 32, 32, 0, 0, 0 };

static long s_mp_cost_pct;

static void spell_mp_cost_activate(void) {
    s_mp_cost_pct = option_number("spell-mp-cost", "percent", 50);
}

static void spell_mp_cost_vblank(void) {
    if (!psx_mod_game_started() || !in_tower() || s_mp_cost_pct == 100)
        return;
    for (int s = 1; s < 52; s++)
        if (rb(MP_CAST_TABLE + (uint32_t)s) != MP_CAST_STOCK[s] ||
            rb(MP_ENCHANT_TABLE + (uint32_t)s) != MP_ENCHANT_STOCK[s])
            return;  /* already rescaled this visit, or not the data we expect */
    for (int s = 1; s < 52; s++) {
        long c = (MP_CAST_STOCK[s] * s_mp_cost_pct + 50) / 100;
        long e = (MP_ENCHANT_STOCK[s] * s_mp_cost_pct + 50) / 100;
        if (MP_CAST_STOCK[s] && c < 1) c = 1;
        if (MP_ENCHANT_STOCK[s] && e < 1) e = 1;
        wb(MP_CAST_TABLE + (uint32_t)s, clamp8(c));
        wb(MP_ENCHANT_TABLE + (uint32_t)s, clamp8(e));
    }
}

/* ---- Talent Inheritance: fusion keeps every talent from both familiars --
 * The fusion overlay computes
 *     W.talents = (W.talents & innate[W]) | (innate[L] & L.talents)
 * (0x80027E2C..0x80027E40). We rewrite three instructions so it becomes
 *     W.talents = W.talents | (L.talents & ~0x00C00000)
 * keeping the loser's "always survives"/"always absorbed" bits out. The game's
 * own recompute and "Talented with ..." message run afterwards unchanged. */

static const uint32_t TI_ADDR[3]  = { 0x80027E2Cu, 0x80027E34u, 0x80027E3Cu };
static const uint32_t TI_STOCK[3] = { 0x8C450000u,   /* lw   a1,0(v0)      innate[L]    */
                                      0x8C630000u,   /* lw   v1,0(v1)      innate[W]    */
                                      0x00431024u }; /* and  v0,v0,v1                   */
static const uint32_t TI_PATCH[3] = { 0x3C05FF3Fu,   /* lui  a1,0xFF3F                  */
                                      0x34A5FFFFu,   /* ori  a1,a1,0xFFFF  (~0x00C00000)*/
                                      0x00000000u }; /* nop                (keep W.tal) */

static void talent_inheritance_vblank(void) {
    if (!psx_mod_game_started() || !fusion_overlay_resident())
        return;
    for (int i = 0; i < 3; i++)
        if (rw(TI_ADDR[i]) != TI_STOCK[i])
            return;  /* already patched, or not the code we expect */
    for (int i = 0; i < 3; i++)
        psx_mod_write_code_word(TI_ADDR[i], TI_PATCH[i]);
}

/* ---- Fusion Absorption: the survivor absorbs part of the loser's stats ---
 * While both familiar slots are filled we keep a snapshot of each. When one
 * slot empties while the fusion overlay is resident, the remaining familiar
 * absorbed the other: add percent% of the loser's base stats to it. */

static long s_absorb_pct;
static Snap s_absorb[2];

static void fusion_absorb_activate(void) {
    s_absorb_pct = option_number("fusion-absorb", "percent", 25);
    s_absorb[0].unit = s_absorb[1].unit = 0;
}

static void fusion_absorb_vblank(void) {
    if (!psx_mod_game_started() || !in_tower())
        return;
    uint32_t a = familiar(0), b = familiar(1);
    if (a && b) {
        snap_unit(&s_absorb[0], a);
        snap_unit(&s_absorb[1], b);
        return;
    }
    if (s_absorb[0].unit && s_absorb[1].unit && fusion_overlay_resident()) {
        uint32_t w = a ? a : b;
        const Snap* loser = NULL;
        if (w == s_absorb[0].unit) loser = &s_absorb[1];
        else if (w == s_absorb[1].unit) loser = &s_absorb[0];
        if (w && loser) {
            add_stat(w, 0x00, 0x26, loser->atk * s_absorb_pct / 100);
            add_stat(w, 0x01, 0x27, loser->def * s_absorb_pct / 100);
            add_stat(w, 0x04, 0x25, loser->mp * s_absorb_pct / 100);
            add_stat(w, 0x05, 0x28, loser->hp * s_absorb_pct / 100);
            recompute_max_stats(w);
        }
    }
    s_absorb[0].unit = s_absorb[1].unit = 0;
}

/* ---- Monster Strength: scale wild monsters as they appear ----------------
 * A wild monster is scaled while its base ATK, DEF and HP are still exactly what
 * spawning gives its species at its level (spawn_stat). Once scaled they no longer
 * match, so nothing can scale a monster twice. An earlier version kept a list of
 * units it had seen instead; the game briefly unlinks a monster whose path is
 * blocked to re-queue it (FUN_800CA444 -> FUN_8009A180), the list walk missed it,
 * and the monster was scaled again: two rounds of 25% took 2 HP to 0, leaving a
 * monster that could attack but that attacks passed through (FUN_800A41F0 needs
 * HP > 0) and mixture magic never landed on. Scaled stats never drop below 1.
 * A monster is only scaled once it shows the same stats on two frames in a row,
 * so one caught halfway through its spawn level-ups is left for the next frame. */

typedef struct { uint32_t unit; uint8_t lv, atk, def, hp; } MonSnap;

static long s_mon_hp_pct, s_mon_atk_pct, s_mon_def_pct;
static MonSnap s_mon_wait[MAX_UNITS];   /* unscaled monsters seen last frame */
static int s_mon_nwait;

static void monster_strength_activate(void) {
    s_mon_hp_pct = option_number("monster-strength", "hp_percent", 150);
    s_mon_atk_pct = option_number("monster-strength", "atk_percent", 120);
    s_mon_def_pct = option_number("monster-strength", "def_percent", 120);
    s_mon_nwait = 0;
}

static long scaled_stat(long v, long pct) {
    v = v * pct / 100;
    return v < 1 ? 1 : v > 255 ? 255 : v;
}

static void scale_monster(uint32_t u, long atk, long def, long hp) {
    long old_max = rb(u + 0x29), cur = rb(u + 0x28);
    add_stat(u, 0x00, 0x26, atk - rb(u + 0x00));
    add_stat(u, 0x01, 0x27, def - rb(u + 0x01));
    wb(u + 0x05, (uint8_t)hp);
    recompute_max_stats(u);
    long max = rb(u + 0x29);
    cur = old_max ? cur * max / old_max : max;   /* keep the same share of max HP */
    wb(u + 0x28, (uint8_t)(cur < 1 ? 1 : cur > max ? max : cur));
}

static void monster_strength_vblank(void) {
    if (!psx_mod_game_started() || !in_tower())
        return;
    MonSnap wait[MAX_UNITS];
    int nwait = 0;
    uint32_t head = rw(UNIT_HEAD), u = head;
    for (int n = 0; n < MAX_UNITS && valid_ptr(u); n++) {
        uint8_t sp = rb(u + 0x13), lv = rb(u + 0x11);
        if (!(rw(u + 0x14) & 0x4000) && u != familiar(0) && u != familiar(1) &&
            sp >= 1 && sp < 48 && lv >= 1 && rb(u + 0x28) &&
            rb(u + 0x00) == spawn_stat(sp, 0, lv) && rb(u + 0x01) == spawn_stat(sp, 1, lv) &&
            rb(u + 0x05) == spawn_stat(sp, 5, lv)) {
            MonSnap s = { u, lv, rb(u + 0x00), rb(u + 0x01), rb(u + 0x05) };
            long atk = scaled_stat(s.atk, s_mon_atk_pct), def = scaled_stat(s.def, s_mon_def_pct),
                 hp = scaled_stat(s.hp, s_mon_hp_pct);
            if (atk != s.atk || def != s.def || hp != s.hp) {
                int settled = 0;
                for (int i = 0; i < s_mon_nwait && !settled; i++)
                    settled = s_mon_wait[i].unit == u && s_mon_wait[i].lv == s.lv &&
                              s_mon_wait[i].atk == s.atk && s_mon_wait[i].def == s.def &&
                              s_mon_wait[i].hp == s.hp;
                if (settled)
                    scale_monster(u, atk, def, hp);
                else
                    wait[nwait++] = s;
            }
        }
        u = rw(u + 0x5C) + 0x20;
        if (u == head) break;
    }
    for (int i = 0; i < nwait; i++) s_mon_wait[i] = wait[i];
    s_mon_nwait = nwait;
}

/* ---- Melee Damage / Critical Strikes ------------------------------------
 * The dungeon's melee routine (FUN_8009C12C) stores the pending HP change
 * (negative) in defender+0x64 and then calls the EXE status lookup
 * FUN_80042900(defender, 0x1D) from 0x8009C65C. That EXE function is listed in
 * game.toml [recompiler] mod_function_entry_funcs, so we get called on entry:
 * a0 = defender, s4 = attacker (callee-saved, still live), ra = 0x8009C664.
 * Whatever we leave in +0x64 is what the game prints and applies. Entry hooks
 * run whether or not their feature is enabled, hence the explicit flags. */

#define MELEE_STATUS_FN   0x80042900u
#define MELEE_RETURN_PC   0x8009C664u
/* The magic damage routine (dungeon FUN_8009CE1C: target, power, level,
 * element, dir, caster, ...) makes the same call from 0x8009D0A4 after storing
 * (defense - (power+level)*2*element_mod)/2 in target+0x64. There s0 = target,
 * s4 = power, s2 = final magic attack, s5 = element bits, s7 = caster (0 for
 * traps/items). */
#define MAGIC_RETURN_PC   0x8009D0ACu

static int s_spell_dmg_enabled, s_affinity_enabled;
static long s_spell_party_pct = 100, s_spell_enemy_pct = 100;
static long s_affinity_pct = 50, s_affinity_monsters = 0;

static void spell_damage_activate(void) {
    s_spell_dmg_enabled = 1;
    s_spell_party_pct = option_number("spell-damage", "party_percent", 125);
    s_spell_enemy_pct = option_number("spell-damage", "enemy_percent", 100);
}

static void elemental_affinity_activate(void) {
    char text[16] = "";
    s_affinity_enabled = 1;
    s_affinity_pct = option_number("elemental-affinity", "bonus_percent", 50);
    s_affinity_monsters = psx_mod_option_value(PKG, "elemental-affinity", "monsters", text, sizeof text) &&
                          text[0] == 't';
}

static void magic_hit(struct CPUState* cpu) {
    uint32_t target = cpu->gpr[4], caster = cpu->gpr[23];
    uint32_t element = cpu->gpr[21] & 7;
    if (!valid_ptr(target)) return;
    long dmg = (int16_t)psx_mod_read_half(target + 0x64);
    if (dmg >= 0) return;
    int party = valid_ptr(caster) && (rw(caster + 0x14) & 0x4000) != 0;
    if (s_spell_dmg_enabled)
        dmg = dmg * (party ? s_spell_party_pct : s_spell_enemy_pct) / 100;
    if (s_affinity_enabled && valid_ptr(caster) && (party || s_affinity_monsters) &&
        element && (rw(caster + 0x14) & 7 & element))
        dmg = dmg * (100 + s_affinity_pct) / 100;
    if (dmg > -1) dmg = -1;
    if (dmg < -32768) dmg = -32768;
    psx_mod_write_half(target + 0x64, (uint16_t)(int16_t)dmg);
}

static int s_melee_enabled, s_crit_enabled;
static long s_melee_party_pct = 100, s_melee_enemy_pct = 100;
static long s_crit_chance = 10, s_crit_pct = 200;
static uint32_t s_rng = 0x2F6B1D35u;

static uint32_t next_random(void) {
    s_rng = s_rng * 1103515245u + 12345u;
    return s_rng >> 16;
}

static void melee_damage_activate(void) {
    s_melee_enabled = 1;
    s_melee_party_pct = option_number("melee-damage", "party_percent", 125);
    s_melee_enemy_pct = option_number("melee-damage", "enemy_percent", 100);
}

static void critical_strikes_activate(void) {
    s_crit_enabled = 1;
    s_crit_chance = option_number("critical-strikes", "chance", 10);
    s_crit_pct = option_number("critical-strikes", "damage_percent", 200);
}

static void melee_status_entry(struct CPUState* cpu, uint32_t address) {
    (void)address;
    if ((cpu->gpr[5] & 0xFF) != 0x1D) return;
    if (cpu->gpr[31] == MAGIC_RETURN_PC) {
        if (s_spell_dmg_enabled || s_affinity_enabled) magic_hit(cpu);
        return;
    }
    if (!s_melee_enabled && !s_crit_enabled) return;
    if (cpu->gpr[31] != MELEE_RETURN_PC) return;
    uint32_t defender = cpu->gpr[4], attacker = cpu->gpr[20];
    if (!valid_ptr(defender) || !valid_ptr(attacker)) return;
    long dmg = (int16_t)psx_mod_read_half(defender + 0x64);
    if (dmg >= 0) return;  /* a miss / no damage: leave the game's handling alone */
    int party = (rw(attacker + 0x14) & 0x4000) != 0;
    if (s_melee_enabled)
        dmg = dmg * (party ? s_melee_party_pct : s_melee_enemy_pct) / 100;
    if (s_crit_enabled && party && (long)(next_random() % 100) < s_crit_chance)
        dmg = dmg * s_crit_pct / 100;
    if (dmg > -1) dmg = -1;        /* every hit still does at least 1 damage */
    if (dmg < -32768) dmg = -32768;
    psx_mod_write_half(defender + 0x64, (uint16_t)(int16_t)dmg);
}

/* ---- Fair Level Down (Gameplay Corrections) -------------------------------
 * Dungeon FUN_800A2424 (LoDown, level-down traps) lowers the level and takes
 * f(L) - f(L-1) of the unit's CURRENT species (+0x13) from each base stat,
 * guarding only against a result of exactly 0. Two exploits follow:
 *   - a frog's species byte is FROG (46, zero growth; the real species is kept
 *     at +0xA8), so a frogged unit loses nothing;
 *   - an evolved monster (Nyuel -> Battnel) loses its new species' larger
 *     gains for levels it gained as the old species, and the byte wraps to ~255.
 * We snapshot every unit each frame; when a unit's level drops by k with its EXP
 * reset to T[level]-1 (what that routine does), we redo its base stats from the
 * snapshot: each level taken back removes the gain the REAL species gets at that
 * level (same as vanilla for ordinary units), and no stat drops below the
 * species' level-1 value (or rises). Then max stats are recomputed and current
 * HP/MP/ATK/DEF clamped, as the routine does. */

#define SPECIES_FROG  46
#define EXP_TABLE     0x800835E8u   /* u32 T[level]: total EXP to reach a level */

typedef struct { uint32_t unit; uint8_t lv, sp, st[6]; } LvSnap;   /* st = base +0..+5 */
static LvSnap s_lv[MAX_UNITS];
static int s_fair_lv_enabled;

static void fair_level_down_activate(void) {
    s_fair_lv_enabled = 1;
    for (int i = 0; i < MAX_UNITS; i++) s_lv[i].unit = 0;
}

static void lv_snap(LvSnap* s, uint32_t u) {
    s->unit = u; s->lv = rb(u + 0x11); s->sp = rb(u + 0x13);
    for (int k = 0; k < 6; k++) s->st[k] = rb(u + (uint32_t)k);
}

static LvSnap* lv_find(uint32_t u, int make) {
    LvSnap* free_slot = 0;
    for (int i = 0; i < MAX_UNITS; i++) {
        if (s_lv[i].unit == u) return &s_lv[i];
        if (!s_lv[i].unit && !free_slot) free_slot = &s_lv[i];
    }
    if (make && free_slot) { lv_snap(free_slot, u); return 0; }
    return 0;
}

static void fair_level_down(uint32_t u, const LvSnap* s, int new_lv) {
    int sp = rb(u + 0x13);
    if (sp == SPECIES_FROG && rb(u + 0xA8)) sp = rb(u + 0xA8);   /* frogged: real species */
    if (sp < 0 || sp >= 48) return;
    for (int k = 0; k < 6; k++) {
        long v = s->st[k];
        long floor_v = rb(BASE_TABLE + (uint32_t)sp * 0x18u + (uint32_t)k);   /* level-1 value */
        for (int L = s->lv - 1; L >= new_lv; L--) {   /* each level given back: L+1 -> L */
            long gain = stat_curve(sp, k, L) - stat_curve(sp, k, L - 1);
            if (v <= floor_v) break;                  /* never push a stat below its floor */
            v -= gain;
            if (v < floor_v) v = floor_v;
        }
        if (v < 1) v = 1;
        wb(u + (uint32_t)k, clamp8(v));
    }
    recompute_max_stats(u);
    if (rb(u + 0x28) > rb(u + 0x29)) wb(u + 0x28, rb(u + 0x29));
    if (rb(u + 0x25) > rb(u + 0x66)) { wb(u + 0x25, rb(u + 0x66)); wb(u + 0x24, 0xFF); }
    if (rb(u + 0x26) > rb(u + 0x68)) wb(u + 0x26, rb(u + 0x68));
    if (rb(u + 0x27) > rb(u + 0x69)) wb(u + 0x27, rb(u + 0x69));
}

static void fair_level_down_vblank(void) {
    if (!s_fair_lv_enabled || !psx_mod_game_started() || !in_tower())
        return;
    uint32_t head = rw(UNIT_HEAD);
    if (!valid_ptr(head)) return;
    uint32_t live[MAX_UNITS];
    int nlive = 0;
    uint32_t u = head;
    for (int n = 0; n < MAX_UNITS; n++) {
        live[nlive++] = u;
        LvSnap* s = lv_find(u, 1);
        if (s) {
            int lv = rb(u + 0x11);
            int same = rb(u + 0x13) == s->sp ||
                       (rb(u + 0x13) == SPECIES_FROG && rb(u + 0xA8) == s->sp) ||
                       (s->sp == SPECIES_FROG && rb(u + 0x13) == rb(u + 0xA8));
            if (same && lv >= 1 && lv < s->lv && rw(u + 0x18) == rw(EXP_TABLE + 4u * (uint32_t)lv) - 1u)
                fair_level_down(u, s, lv);
            lv_snap(s, u);
        }
        u = rw(u + 0x5C) + 0x20;
        if (u == head || !valid_ptr(u)) break;
    }
    for (int i = 0; i < MAX_UNITS; i++) {   /* forget units that left the list */
        if (!s_lv[i].unit) continue;
        int alive = 0;
        for (int j = 0; j < nlive; j++) if (live[j] == s_lv[i].unit) { alive = 1; break; }
        if (!alive) s_lv[i].unit = 0;
    }
}

PSX_MOD_CONSTRUCTOR(azure_register_gameplay_plugins) {
    (void)psx_mod_register_activation_plugin("azure.fair-level-down", fair_level_down_activate);
    (void)psx_mod_register_vblank_plugin("azure.fair-level-down", fair_level_down_vblank);
    (void)psx_mod_register_activation_plugin("azure.spell-damage", spell_damage_activate);
    (void)psx_mod_register_activation_plugin("azure.elemental-affinity", elemental_affinity_activate);
    (void)psx_mod_register_activation_plugin("azure.spell-growth", spell_growth_activate);
    (void)psx_mod_register_vblank_plugin("azure.spell-growth", spell_growth_vblank);
    (void)psx_mod_register_activation_plugin("azure.spell-mp-cost", spell_mp_cost_activate);
    (void)psx_mod_register_vblank_plugin("azure.spell-mp-cost", spell_mp_cost_vblank);
    (void)psx_mod_register_activation_plugin("azure.melee-damage", melee_damage_activate);
    (void)psx_mod_register_activation_plugin("azure.critical-strikes", critical_strikes_activate);
    (void)psx_mod_register_function_entry_plugin("azure.melee-hook", MELEE_STATUS_FN,
                                                 melee_status_entry);
    (void)psx_mod_register_activation_plugin("azure.second-wind", second_wind_activate);
    (void)psx_mod_register_vblank_plugin("azure.second-wind", second_wind_vblank);
    (void)psx_mod_register_activation_plugin("azure.exp-rate", exp_rate_activate);
    (void)psx_mod_register_vblank_plugin("azure.exp-rate", exp_rate_vblank);
    (void)psx_mod_register_activation_plugin("azure.familiar-growth", familiar_growth_activate);
    (void)psx_mod_register_vblank_plugin("azure.familiar-growth", familiar_growth_vblank);
    (void)psx_mod_register_vblank_plugin("azure.talent-inheritance", talent_inheritance_vblank);
    (void)psx_mod_register_activation_plugin("azure.fusion-absorb", fusion_absorb_activate);
    (void)psx_mod_register_vblank_plugin("azure.fusion-absorb", fusion_absorb_vblank);
    (void)psx_mod_register_activation_plugin("azure.monster-strength", monster_strength_activate);
    (void)psx_mod_register_vblank_plugin("azure.monster-strength", monster_strength_vblank);
}
