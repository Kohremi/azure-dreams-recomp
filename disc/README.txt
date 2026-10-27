PUT YOUR DISC IMAGES HERE
=========================

Use images you dumped yourself from discs you own. Nothing in this folder except this file is
ever uploaded: git ignores everything else here.

Required
--------
  Azure Dreams (USA).bin
  Azure Dreams (USA).cue

  Azure Dreams (USA), SLUS-00614, the standard Redump dump.
  SHA-1 of the .bin: fab68454be5e4e48f7a43ac797cc8c47325c6a20
  re\scripts\prepare.py checks it. The mods depend on this exact dump.
  The .cue must name the .bin: FILE "Azure Dreams (USA).bin" BINARY

Optional (only for the Japanese Voices mod)
-------------------------------------------
  Azure Dreams (Japan).bin

  Other Life: Azure Dreams (Japan), SLPM-86047, a single-track MODE2/2352 image.
  Only the .bin is needed. These names also work:
    Other Life - Azure Dreams (Japan).bin
    Other Life Azure Dreams (Japan).bin
  Without it, every other mod still works.

Have a .chd instead? Convert it with chdman (part of MAME):
  chdman extractcd -i "Azure Dreams (USA).chd" -o "Azure Dreams (USA).cue"

Files that will appear here later (made on your computer, never uploaded)
-----------------------------------------------------------------------
  Azure Dreams (USA) (JP Voices).bin / .cue
      made by prepare.py when the Japanese disc is present. Play from this .cue for the voices.
  disc.bin, disc.cue, disc.disc-receipt.json, SLUS_006.14, SYSTEM.CNF
      made by the "generate" step (a checked copy of your US disc)

Full guide: docs\INSTALL.md
