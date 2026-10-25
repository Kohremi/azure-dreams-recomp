/*
 * Japanese Voices: plays the Japanese release's voice acting in the US town conversations and in
 * the voiced dungeon scenes (familiar talk, Beldo).
 *
 * Needs the disc image built by re/scripts/build_voice_disc.py (US disc + the Japanese voice files
 * appended, stream LBA table entries 3..18 patched). The engine kept the whole voice path
 * (script op 0x1D -> FUN_8003F540 stream request; button presses and speaker changes stop a
 * playing voice); only the scripts' 0x1D ops and the files were dropped in the US release.
 *
 * re/scripts/voice_port.py aligned every Japanese voice op with the US line it belongs to and
 * wrote azure_voice_data.h. The Japanese scripts run `30 1D a b` (yield, stream request) right
 * before a voiced line; here, while a script chunk is loaded (its first word is the chunk number),
 * each voiced line's first bytes are replaced by `17 snippet` and the snippet does `30 1D a b`, the
 * replaced bytes, and jumps back. That catches the line however the script reaches it (after a
 * speaker op, a button wait, a call, a branch). Short clips the Japanese scripts keep as
 * subroutines `30 1D a b 16` picked through a pointer table in the location overlay (gift
 * reactions, random remarks; the US kept the tables, pointing at bare `16`s) are handled by pointing
 * the US table entries at such snippets. Where the US joined several Japanese boxes into one, the
 * later voices play one after another while the box waits for its button; where it split one
 * Japanese box into several, the voice keeps playing through those button waits.
 *
 * Town locations keep their recent script chunks in a 32 KB cache above the script base and copy a
 * chunk back to the base when one of its scripts starts. On arrival the exterior loads five chunks in
 * a few frames, so the chunk of a later conversation (Nico's fountain drive) comes from the cache,
 * without its first word. Chunks are therefore recognised by their voiced lines when the first word
 * does not name one, and the cached chunks are patched where they wait.
 *
 * The snippets are allocated and written by the constructor, before any activation allocates plugin
 * memory, so they sit at the same address in every session whether or not the feature is enabled:
 * a save state that holds a patched chunk always finds them.
 */
#include "mod_plugins.h"

/* Generated from your own US and Japanese discs by re/scripts/prepare.py (voice_port.py); it holds
 * the game's script bytes, so it is not in the repository. Without it the feature does nothing. */
#if __has_include("azure_voice_data.h")
#include "azure_voice_data.h"
#define AZURE_VOICE_DATA 1
#else
typedef struct { uint32_t number, base, addr, snip, orig; uint16_t len; uint8_t kind; } VoiceRow;
static const VoiceRow VOICE_ROWS[1];
#define VOICE_ROW_COUNT 0u
static const uint8_t VOICE_SNIPPETS[1];
#define AZURE_VOICE_DATA 0
#endif

#define VM_STATE      0x80082AD4u
#define VM_PTR        0x80082AE0u
#define ST_RUNNING    0x80038A10u
#define ST_BUTTON     0x80038478u   /* waiting for a button (op 0x11); on a press it stops the voice */
#define ST_NOSTOP     0x8006778Cu   /* our copy without the stop, in dead EXE code (re/NOTES.md) */
#define SCRIPT_BASE   (0x801131B8u + 0x2Cu)   /* town API struct: current script load base */
#define CHUNK_CACHE   0x800CF720u   /* town loader's cache: {u8 flag, u8 id (0xFF ends), u16 variant, u32 size},
                                     * newest first; the chunks lie back to back from the script base */
#define STREAM_TABLE  0x8006CD50u
#define DUNGEON_ROW   0xFFFFFFFFu                /* absolute-address rows, outside town (tower scripts) */
#define ALWAYS_ROW    0xFFFFFFFEu                /* absolute-address rows, everywhere (EXE, overlay programs) */
#define VOICE_DISC_SECTORS 203986u           /* the voice disc's size (build_voice_disc.py) */

/* Voice file LBAs on the voice disc (build_voice_disc.py) for stream table entries 3..18. */
static const uint32_t VOICE_LBAS[16] = {
    126946, 133602, 139586, 144594, 149698, 155138, 162690, 172466,
    174738, 188034, 191202, 193746, 199026, 200386, 202418, 203282,
};

static int s_enabled;        /* feature on */
static uint32_t s_snippets;  /* guest address of VOICE_SNIPPETS */
static int32_t s_follow = -1; /* kind 2 row armed: play it once the current voice has played */
static uint32_t s_last_snip = 0xFFFFFFFFu; /* offset in VOICE_SNIPPETS where the VM last ran */
static uint32_t s_prev_snip = 0xFFFFFFFFu; /* the same, one VBlank earlier */

/* Button-wait state fn without the voice stop: 0x80038478 calls FUN_80053DA8(0xB4) (stops the
 * stream) when the press flag ctx+0x84 is set and then resumes the VM; this only resumes it.
 *   lb v0,0x84(a0); nop; beq v0,zero,+3; lui v0,0x8004; addiu v0,v0,-0x75F0; sw v0,0x10(a0); jr ra; nop */
static const uint32_t NOSTOP_CODE[8] = {
    0x80820084u, 0x00000000u, 0x10400003u, 0x3C028004u, 0x24428A10u, 0xAC820010u, 0x03E00008u, 0x00000000u,
};
static int s_follow_busy;     /* the stream has been busy since arming */

static int town_module_resident(void) {
    return psx_mod_read_word(0x80090A74u) == 0x27BDFFD8u && psx_mod_read_word(0x80090C44u) == 0x8FBF0024u;
}

static void voice_activate(void) {
    s_enabled = 1;
}

/* FUN_80053EF0(4), the status op 0x1D waits on: nonzero while a stream is requested or playing. */
static int stream_busy(void) {
    uint32_t w0 = psx_mod_read_word(0x800847D0u), w1 = psx_mod_read_word(0x800847D4u);
    return (w1 & 0x200u) || (w0 & 0x4000u) || psx_mod_read_word(0x8008485Cu) == 2u || (w0 & 0x400u);
}

static void arm(int32_t i) {
    s_follow = i;
    s_follow_busy = 0;
}

/* A US box that joins several Japanese boxes: after the line's voice, play the next one while the
 * VM still waits at that box (a button press moves on and drops it, as with any voice). */
static void follow_up(uint32_t number, uint32_t base, uint32_t vm) {
    if (s_follow < 0) return;
    const VoiceRow* r = &VOICE_ROWS[s_follow];
    if (r->number != ALWAYS_ROW && (r->number != number || r->base != base)) { s_follow = -1; return; }
    if (stream_busy()) { s_follow_busy = 1; return; }
    if (psx_mod_read_word(VM_STATE) != ST_BUTTON) return;
    if (vm != r->addr) { s_follow = -1; return; }      /* waiting at another box: moved on */
    if (!s_follow_busy) return;
    psx_mod_write_word(VM_PTR, s_snippets + r->snip);
    psx_mod_write_word(VM_STATE, ST_RUNNING);
    s_last_snip = r->snip;          /* the VM runs it within one tick: its continuation rows look for it */
    uint32_t n = (uint32_t)s_follow + 1u;
    if (n < VOICE_ROW_COUNT && VOICE_ROWS[n].kind == 2 && VOICE_ROWS[n].orig == 0 && VOICE_ROWS[n].len == 0)
        arm((int32_t)n);
    else
        s_follow = -1;
}

static uint32_t read_le32(uint32_t at) {
    uint32_t v = 0;
    for (int k = 0; k < 4; k++)
        v |= (uint32_t)psx_mod_read_byte(at + (uint32_t)k) << (8 * k);
    return v;
}

static uint32_t first_row(uint32_t number) {
    uint32_t lo = 0, hi = VOICE_ROW_COUNT;
    while (lo < hi) {
        uint32_t mid = (lo + hi) / 2;
        if (VOICE_ROWS[mid].number < number) lo = mid + 1; else hi = mid;
    }
    return lo;
}

/* A voiced line (kind 0) of a chunk copy that starts at base + delta: its original bytes, or our patch. */
static int line_present(const VoiceRow* r, uint32_t delta) {
    uint32_t at = r->addr + delta;
    if (psx_mod_read_byte(at) == 0x17 && read_le32(at + 1) == s_snippets + r->snip)
        return 1;
    const uint8_t* orig = &VOICE_SNIPPETS[r->snip + 10];
    for (uint32_t k = 0; k < r->len; k++)
        if (psx_mod_read_byte(at + k) != orig[k])
            return 0;
    return 1;
}

/* The number of the chunk loaded for `base` whose copy starts at `at`. A chunk read from the disc
 * starts with it, but the loader's cache never moves a chunk's first word (FUN_8008ACAC, the backward
 * copy that shifts cached chunks up, is off by one word), so a chunk that comes back from the cache
 * (a conversation's chunk that the location already loaded on arrival) starts with stale bytes. Then
 * it is the chunk whose voiced lines are found there (no two chunks of a base share one). */
static uint32_t chunk_number(uint32_t base, uint32_t at) {
    uint32_t first = psx_mod_read_word(at), delta = at - base;
    for (uint32_t i = first_row(first); i < VOICE_ROW_COUNT && VOICE_ROWS[i].number == first; i++)
        if (VOICE_ROWS[i].base == base && VOICE_ROWS[i].kind == 0 && line_present(&VOICE_ROWS[i], delta))
            return first;
    uint32_t best = first, best_n = 0, cur = 0, n = 0;
    for (uint32_t i = 0; i < VOICE_ROW_COUNT && VOICE_ROWS[i].number < ALWAYS_ROW; i++) {
        const VoiceRow* r = &VOICE_ROWS[i];
        if (r->number != cur) { cur = r->number; n = 0; }
        if (r->base == base && r->kind == 0 && line_present(r, delta) && ++n > best_n) {
            best_n = n;
            best = cur;
        }
    }
    return best;
}

/* Patch the voiced lines of a loaded chunk (a reload brings the original bytes back). `at` is where
 * its copy starts: the script base, or its place in the loader's cache, where only the lines are
 * patched, so that a chunk brought back to the base already carries them when its script starts. */
static void patch_chunk(uint32_t base, uint32_t number, uint32_t at) {
    uint32_t delta = at - base;
    uint32_t vm = psx_mod_read_word(VM_PTR);
    for (uint32_t i = first_row(number); i < VOICE_ROW_COUNT && VOICE_ROWS[i].number == number; i++) {
        const VoiceRow* r = &VOICE_ROWS[i];
        if (r->base != base || (delta && r->kind != 0)) continue;
        uint32_t snip = s_snippets + r->snip;
        if (r->kind == 3 || r->kind == 4) {             /* a split box inside the line's voice */
            uint32_t wait = r->kind == 4 ? s_snippets + r->addr : r->addr;   /* 4: the wait's copy in a snippet */
            if (vm == wait && psx_mod_read_word(VM_STATE) == ST_BUTTON && stream_busy() &&
                s_last_snip - r->orig < r->len)
                psx_mod_write_word(VM_STATE, ST_NOSTOP);
            continue;
        }
        if (r->kind == 2) {                             /* arm when the VM enters its line's snippet */
            if (r->len && s_last_snip - r->orig < r->len && s_prev_snip - r->orig >= r->len)
                arm((int32_t)i);
            continue;
        }
        if (r->kind == 1) {                             /* overlay pointer table entry */
            if (psx_mod_read_word(r->addr) == r->orig)
                psx_mod_write_word(r->addr, snip);
            continue;
        }
        uint32_t line = r->addr + delta;
        if (psx_mod_read_byte(line) == 0x17 && read_le32(line + 1) == snip)
            continue;                                   /* already patched */
        if (vm > line && vm < line + r->len + 0x40u)
            continue;                                   /* the VM is in this line right now */
        const uint8_t* orig = &VOICE_SNIPPETS[r->snip + 10];
        int same = 1;
        for (uint32_t k = 0; k < r->len && same; k++)
            same = psx_mod_read_byte(line + k) == orig[k];
        if (!same) continue;
        for (int k = 0; k < 4; k++)
            psx_mod_write_byte(line + 1u + (uint32_t)k, (uint8_t)(snip >> (8 * k)));
        psx_mod_write_byte(line, 0x17);
    }
}

/* The chunks waiting in the loader's cache above the base (entry 0 is the one at the base). */
static void patch_cache(uint32_t base) {
    uint32_t at = base;
    for (uint32_t k = 0; k < 32u && psx_mod_read_byte(CHUNK_CACHE + 8u * k + 1u) != 0xFFu; k++) {
        uint32_t size = psx_mod_read_word(CHUNK_CACHE + 8u * k + 4u);
        if (k)
            patch_chunk(base, chunk_number(base, at), at);
        at += size;
        if (!size || at - base >= 0x8000u)
            break;
    }
}

static void voice_vblank(void) {
    if (!s_enabled || !s_snippets || !psx_mod_game_started())
        return;
    /* Only on the voice disc (the voice files end at its last sector); a plain US disc is left alone.
     * The EXE on the voice disc already carries the table, but save states restore the US one. */
    if (psx_mod_disc_sector_count() < VOICE_DISC_SECTORS)
        return;
    for (int i = 0; i < 16; i++)
        if (psx_mod_read_word(STREAM_TABLE + 12u + 4u * (uint32_t)i) != VOICE_LBAS[i])
            psx_mod_write_word(STREAM_TABLE + 12u + 4u * (uint32_t)i, VOICE_LBAS[i]);
    /* Town: rows of the script chunk loaded at *(API+0x2C) (see chunk_number) and of the chunks in
     * the loader's cache above it. Elsewhere
     * (dungeon): rows with absolute addresses (townspeople met in the tower, in the dungeon module;
     * Beldo in species 55's code chunk, one row per code slot). Everywhere: the gift reactions in the
     * EXE and scripts inside location overlay programs. A row applies only where its original bytes are. */
    uint32_t base = 0, number = DUNGEON_ROW;
    int town = town_module_resident();
    if (town) {
        base = psx_mod_read_word(SCRIPT_BASE);
        if ((base & 0xFFE00000u) != 0x80000000u)
            return;
        number = chunk_number(base, base);
    }
    for (uint32_t k = 0; k < 8; k++)                    /* save states may predate it */
        if (psx_mod_read_word(ST_NOSTOP + 4u * k) != NOSTOP_CODE[k])
            psx_mod_write_code_word(ST_NOSTOP + 4u * k, NOSTOP_CODE[k]);
    uint32_t vm = psx_mod_read_word(VM_PTR);
    s_prev_snip = s_last_snip;
    if (vm >= s_snippets && vm < s_snippets + sizeof(VOICE_SNIPPETS))
        s_last_snip = vm - s_snippets;
    patch_chunk(base, number, base);
    if (town)
        patch_cache(base);
    patch_chunk(0, ALWAYS_ROW, 0);
    follow_up(number, base, psx_mod_read_word(VM_PTR));
}

PSX_MOD_CONSTRUCTOR(azure_register_voice_plugin) {
    if (AZURE_VOICE_DATA)
        s_snippets = psx_mod_alloc_guest_memory(sizeof(VOICE_SNIPPETS), 4);
    if (s_snippets)
        for (uint32_t k = 0; k < sizeof(VOICE_SNIPPETS); k++)
            psx_mod_write_byte(s_snippets + k, VOICE_SNIPPETS[k]);
    (void)psx_mod_register_activation_plugin("azure.jp-voices", voice_activate);
    (void)psx_mod_register_vblank_plugin("azure.jp-voices", voice_vblank);
}
