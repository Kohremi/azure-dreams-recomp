PUT YOUR PLAYSTATION BIOS HERE
==============================

  SCPH1001.BIN

The BIOS of a North American PlayStation (model SCPH-1001), dumped from your own console.
Nothing in this folder except this file is ever uploaded: git ignores everything else here.

  Size:    524288 bytes
  SHA-256: 71af94d1e47a68c11e8fdb9f8368040601514a42a5a399cda48c7d3bff1e99d3

It is used once, by the "generate" step, which recompiles it into the game:
  python psxrecomp\psxrecomp_cli.py generate ... --bios bios\SCPH1001.BIN

If your file has a different name, rename it to SCPH1001.BIN, or change the --bios path in that
command.

Full guide: docs\INSTALL.md
