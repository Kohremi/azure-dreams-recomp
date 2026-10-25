# Installing Azure Dreams Recompiled (with mods)

This guide takes you from nothing to playing, on Windows 10 or 11. You build the game yourself from
your own disc, so it takes a little setup. Plan for about 30 minutes the first time, most of it
waiting.

> [!IMPORTANT]
> This project contains no part of the game. You need your own copy (see step 2). Nobody here can
> send you disc images or BIOS files, and links to them are removed from issues.

## 1. Install the tools

| Tool | Where | Notes |
|---|---|---|
| **Git** | <https://git-scm.com/download/win> | Default options are fine. Also used by the build to apply a patch. |
| **Python 3.11 or newer** | <https://www.python.org/downloads/> | Tick **"Add python.exe to PATH"** in the installer. Tested with 3.14. |
| **Build tools** | downloaded automatically | The build step fetches the portable `cmake-clang-v1` pack the first time. If you already have CMake, Ninja and clang on `PATH`, those are used instead. |

Have a few GB of free disk space: the disc images, the extracted files, the generated game code and
the builds add up.

## 2. Get your game files ready

### What you need, and what each part is for

| File | Required? | Used for |
|---|---|---|
| **Azure Dreams (USA)**, SLUS-00614 | **Yes** | The game itself and every mod. |
| **SCPH-1001 BIOS** | **Yes** | The PlayStation BIOS. It is recompiled into the game during the build. |
| **Other Life: Azure Dreams (Japan)**, SLPM-86047 | Only for Japanese Voices | Its voice recordings are copied onto your US disc image. Without it, every other mod still works. |

You do **not** need both discs. The Japanese disc is optional and only adds the voice acting.

### Dumping them

- **Discs:** make a BIN/CUE image of your own disc with a PC CD drive. The
  [Redump](http://redump.org/) project's guides describe how to make an exact dump. The mods use
  fixed positions inside the game files, so the US disc must be the standard dump. The setup script
  checks it (SHA-1 `fab68454be5e4e48f7a43ac797cc8c47325c6a20` for `Azure Dreams (USA).bin`).
- **BIOS:** dump it from your own PlayStation (SCPH-1001, the original North American model). It must
  be 524288 bytes, SHA-256 `71af94d1e47a68c11e8fdb9f8368040601514a42a5a399cda48c7d3bff1e99d3`.
- **CHD images** work, but convert them to BIN/CUE first with `chdman`, which comes with
  [MAME](https://www.mamedev.org/):
  ```
  chdman extractcd -i "Azure Dreams (USA).chd" -o "Azure Dreams (USA).cue"
  chdman extractcd -i "Other Life Azure Dreams (Japan).chd" -o "Azure Dreams (Japan).cue"
  ```

## 3. Download the project

Open **Command Prompt** or **PowerShell** in the folder where you want it, then:

```
git clone --recursive https://github.com/Kohremi/azure-dreams-recomp.git
cd azure-dreams-recomp
```

`--recursive` matters: the project pulls in the recompilation framework and the launcher as
submodules, and they have submodules of their own. If you forgot it, run
`git submodule update --init --recursive`.

## 4. Put your files in place

Create the `disc` and `bios` folders inside `azure-dreams-recomp` and copy your files in with exactly
these names:

```
azure-dreams-recomp\
  disc\Azure Dreams (USA).bin
  disc\Azure Dreams (USA).cue
  disc\Azure Dreams (Japan).bin      <- optional, for Japanese Voices
  bios\SCPH1001.BIN
```

These folders are ignored by git, so your files can never be uploaded by accident. If your `.cue`
names the `.bin` differently, open it in Notepad and fix the `FILE "..."` line. The Japanese image may
also be called `Other Life - Azure Dreams (Japan).bin`, or you can pass any path with
`--jp "path\to\file.bin"` in the next step.

## 5. Prepare the mod data

```
python re\scripts\prepare.py
```

This reads only your discs, and writes only to ignored folders:

1. checks your disc images against the expected dumps;
2. extracts the game's files to `extracted\` (and `extracted_jp\`);
3. builds the Story Journal's data;
4. with the Japanese disc: builds `disc\Azure Dreams (USA) (JP Voices).bin` / `.cue` (your US disc
   with the Japanese voice files added) and maps every Japanese voice line onto the English script.

It takes a minute or two and ends with `Done.`

## 6. Generate and build the game

```
python psxrecomp\psxrecomp_cli.py generate --config game.toml --project-root . --disc "disc\Azure Dreams (USA).cue" --bios bios\SCPH1001.BIN
python psxrecomp\psxrecomp_cli.py rebuild --config game.toml --project-root . --build-dir build-release --target psx-runtime --exe-basename Azure_Dreams --no-pgo
```

`generate` translates the game's code into C, from your disc and BIOS (under a minute). `rebuild`
compiles it (several minutes the first time). A CMake warning saying
`BIOS generated/ is STALE vs the recompiler emitter` is expected and harmless.

## 7. Play

Run `build-release\Azure_Dreams.exe`. The launcher opens:

1. **Browse For Disc / SBI**: pick `disc\Azure Dreams (USA) (JP Voices).cue` if you made it, otherwise
   `disc\Azure Dreams (USA).cue`. The disc panel should say *Disc verified*.
2. **Mods** (top right): switch on the mods you want and set their options. Everything starts off.
   [MODS.md](MODS.md) explains each one.
3. **Controls**: Player 1 uses the keyboard by default; pick your controller in the Player 1 box
   (**Configure** sets the buttons). **Settings** (top right) holds the launcher's other options.
4. **PLAY**.

Memory cards are kept in the `saves\` folder (also ignored by git). Back it up now and then.

## Updating

```
git pull
git submodule update --init --recursive
python re\scripts\prepare.py
python psxrecomp\psxrecomp_cli.py generate --config game.toml --project-root . --disc "disc\Azure Dreams (USA).cue" --bios bios\SCPH1001.BIN
python psxrecomp\psxrecomp_cli.py rebuild --config game.toml --project-root . --build-dir build-release --target psx-runtime --exe-basename Azure_Dreams --no-pgo
```

Your memory cards in `saves\` are kept.

## Troubleshooting

| Problem | Fix |
|---|---|
| `prepare.py`: *SHA-1 ... is not the Redump dump the mods were made for* | Your US image is a different dump, region or revision. Make a fresh dump of the US release, or convert from a verified CHD. `--force` continues anyway, but mods may break. |
| `prepare.py`: *Put your own dump of Azure Dreams (USA) in disc/* | The file is missing or named differently. See step 4. |
| CMake: *no retcomm-rbengine snap-ring backend was found* | The submodules are incomplete: `git submodule update --init --recursive`. |
| CMake: *Could not apply patches/psxrecomp/...* | The framework checkout has other changes: `git submodule update --init --force psxrecomp`, then build again. |
| `git status` lists `psxrecomp` as modified | Expected: the build applies `patches\psxrecomp` to it. |
| Weedy has no *[Show me your story journal.]* answer | Switch on **Story Journal** under Mods. If it is on, run `prepare.py`, then the `rebuild` command again. |
| No Japanese voices | Play from the `(JP Voices).cue`, switch on **Japanese Voices**, and make sure `prepare.py` found your Japanese disc. Some scenes were never voiced in Japan (for example Wreath's talk about selling items after a tower run), so they stay silent. |
| The game crashes or misbehaves | Turn mods off one at a time to find the cause, then open an issue with what you did and which mods were on. The upstream kit's diagnostic mode is described in `psxrecomp/docs/DIAGNOSTIC_MODE.md`. |

## For developers

Add `--diagnostic-dir build-dev` to the `rebuild` command to also build the developer version. It
runs a debug server on TCP port 4370 that the test and research scripts in `re\scripts` use
([TOOLS.md](TOOLS.md)). Those scripts also need `pip install -r re\requirements-dev.txt`. How the mods
work and how to write new ones: [re/MODDING.md](../re/MODDING.md).
