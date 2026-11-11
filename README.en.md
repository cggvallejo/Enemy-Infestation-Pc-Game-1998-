# Enemy Infestation (1998) — Spanish Localization, Remastered Audio & HD Bilingual Launcher

🌐 **Idioma / Language:** [Español](README.md) | **English**

> *"Some childhood games stay with you forever: dark corridors, colonists trying to survive, blast doors shutting just in time, and aliens lurking in every room."*

This project started out of pure nostalgia and love for **Enemy Infestation** (1998, Clockworks Entertainment / Micro Forte Pty. Ltd., published by Ripcord Games) — bringing this classic real-time tactical strategy game back to modern PCs and HD monitors with a **full Latin American Spanish localization & dub**, remastered retro SFX, crisp aspect-preserved HD scaling, and a **bilingual (`Español` / `English`) graphical launcher**.

Whether you want to replay *Enemy Infestation* in HD in its original English, experience the full Spanish dub, dissect its 1998 engine, or help build new community tools — **contributions, bug reports, and Pull Requests are warmly welcome!**

---

## What We Improved & What We Added

Everything here was built through clean reverse engineering of `Ei.exe` (`Watcom C/C++32`) and its proprietary `.res` (`BLK0`) resource archives, always leaving the user's original game installation untouched:

### 1. Full Reverse Engineering & `BLK0` Binary Repacker
- **Technical architecture documentation ([`docs/architecture.md`](docs/architecture.md)):** detailed breakdown of `Ei.exe` (61 original RCS source modules identified, resource loading, copy-protection checks, 16-state `'MIND'` AI dispatcher, goal condition/action VM tables, and `save*.res` snapshot layout).
- **Inspector, extractor & lossless container builder ([`tools/blk0.py`](tools/blk0.py)):**
  - Parses and rebuilds `BLK0` v10 containers (`auto_idat`, `DIR ` directory table, and automatic **CRC-16/ARC** `0xA001` checksums via slicing-by-8), verified across all **52 original `.res` archives** (**13,116 chunks**, zero errors).
  - Full two-way codec for 8-bit paletted **`cbmp`** sprites/images (Raw modes `0/1` and transparent **`ZRLE`** modes `2/3`, **2,442/2,442 chunks** decoded and re-encoded).
- **World & savegame utilities ([`tools/export_world.py`](tools/export_world.py), [`tools/save_tool.py`](tools/save_tool.py)):**
  - Exports structured JSON (`Stdres.res` database, `Text.res`, all `41` scenarios, `6` maps) and renders annotated map PNGs with roof layers, room polygons, doors, exits, and elevators.
  - CLI inspector and CRC-safe patcher for `save*.res` savegames.

### 2. Complete Latin American Spanish Localization ([`tools/loc_text_exe.py`](tools/loc_text_exe.py), `loc/es/`)
- **Executable [`loc/es/ei_exe.json`](loc/es/ei_exe.json):** `32` `DGROUP` strings patched safely inside `Ei.exe` within strict `CP1252` byte bounds without shifting code or pointers.
- **Core string table [`loc/es/text_res.json`](loc/es/text_res.json):** `209` `Text.res` entries validated against `printf` format specifiers (`%s`, `%d`) and required spacing.
- **Game database & UI tooltips [`loc/es/std_structs.json`](loc/es/std_structs.json):** `21` colonist/alien roles (`patr`), `23` weapons (`wtyp`), `18` weapon effects (`weft`), `72` interactive props (`pobj`), and `86` UI widget tooltips (`view_tooltips`).
- **Maps & rooms [`loc/es/maps.json`](loc/es/maps.json):** all `6` maps (`12` `mapd` chunks) and `159` room names translated.
- **All missions [`loc/es/scenarios.json`](loc/es/scenarios.json):** all `41` single-player, multiplayer & demo scenarios (`Scen*.res`), including `168` goal titles, `95` character names, and `619` mission dialogue/event lines.
- **Classic documentation:** translated [`loc/es/Help.txt`](loc/es/Help.txt), [`loc/es/ReadMe.txt`](loc/es/ReadMe.txt), and [`loc/es/Credits.txt`](loc/es/Credits.txt).

### 3. Extended Bitmap Fonts & Localized UI Graphics ([`tools/loc_fonts_ui.py`](tools/loc_fonts_ui.py))
- Extended all **6 main bitmap UI fonts** in `Stdres.res` (`15002`, `15010`, `15011`, `15012`, `15013`, `15014`) with **22 `CP1252` Spanish glyphs** (`¡ ¿ Á É Í Ñ Ó Ú Ü á é í ñ ó ú ü ª º ° “ ” –`), staying within the engine's `<= 128` glyph slot layout.
- Re-rendered and localized **97 UI `cbmp` graphics** (menus, tabs, buttons, overlays) matched to the game's VGA palette `pal0 6001`.

### 4. Spanish Dubbing & Remastered Retro SFX ([`tools/loc_audio.py`](tools/loc_audio.py))
- **Full `22050 Hz` 8-bit unsigned PCM dubbing:**
  - **709 character voice lines** dubbed in `Sound.res` and **611 mission dialogues/briefings** dubbed across all **41 `Scen*.res`** files.
  - Synthesized via Windows WinRT TTS (`Microsoft Raul` & `Microsoft Sabina`) with **12 role/bank profiles** and custom DSP filters (tactical radio, `PA` intercom, comms, robot) finished with **TPDF** dithering.
- **Retro SFX remastering:**
  - DSP cleanup applied to **265 sound effects** in `Sound.res` (DC offset removal, anti-clipping headroom, spectral cleanup, and TPDF quantization preserving exact original byte lengths).

### 5. Modern HD Display Support via `cnc-ddraw` ([`vendor/cnc-ddraw`](vendor/cnc-ddraw), [`tools/build_es.py`](tools/build_es.py))
- Bundles pre-configured **cnc-ddraw** (MIT License) + **libretro GLSL shaders** tuned for `1080p`/`1440p`+ monitors:
  - Borderless fullscreen (`fullscreen=true`, `windowed=true`), `4:3` aspect preservation (`maintas=true`), OpenGL rendering with `Catmull-Rom`, automatic scaled mouse speed (`adjmouse=true`), `Alt+Enter` toggle, and `[EI] hook_peekmessage=true`.
  - Supports both classic **`800×600`** and native **`1024×768` High View** (`Ei.exe -r1`, wider tactical battlefield view) cleanly upscaled on GPU.

### 6. Native Bilingual Graphical Launcher (`Configurar y Jugar.exe`, [`tools/launcher/EiLauncher.cs`](tools/launcher/EiLauncher.cs))
Added a standalone x86 Windows WinForms configurator (`.NET Framework 4.0`, compiled automatically during build with zero Python dependency required at runtime):
- **Live Language Selector (`Español (Latinoamérica)` / `English (Original)`):**
  - Translates the entire launcher UI on the fly and syncs `cnc-ddraw config.exe` (`spanish` / `english`).
  - Swaps the **54 language-specific files** (`Ei.exe`, `Text.res`, `Stdres.res`, `Sound.res`, `Map*.res`, `Scen*.res`, `*.txt`) cleanly between `lang/es/` and `lang/en/` while **keeping all savegames (`save*.res`)** and shared media (`Track*.wav`, `*.smk`) untouched.
- **Internal game resolution (`Ei.exe`):** `800×600` Classic or `1024×768` High View (`-r1`).
- **Display & scaling options:** Borderless, Exclusive Fullscreen, or Resizable Window (`0×0` Auto up to `2560×1440`), `4:3` aspect / Integer pixel-perfect / Stretch scaling, Renderer (`OpenGL`, `Direct3D 9`, `Auto`, `GDI`), **6 GLSL filters** (`Catmull-Rom`, `Nearest Neighbor`, `Lanczos2 Sharp`, `AMD FSR`, `CRT Lottes`, `xBRZ Freescale`), mouse scaling, and `VSync`.

---

## Repository Layout

| Path | Description |
| :--- | :--- |
| [`tools/blk0.py`](tools/blk0.py) | Python library & CLI to inspect, verify, extract, and rebuild `BLK0` / `cbmp` archives |
| [`tools/loc_text_exe.py`](tools/loc_text_exe.py) | `CP1252` / `printf` catalog validator and text/struct/`Ei.exe` patcher |
| [`tools/loc_fonts_ui.py`](tools/loc_fonts_ui.py) | Extended bitmap font generator (`+22` glyphs) and UI `cbmp` localizer |
| [`tools/loc_audio.py`](tools/loc_audio.py) | `es-MX` TTS synthesis, comms DSP filters, and PCM8 SFX remastering |
| [`tools/build_es.py`](tools/build_es.py) | Assembles standalone `dist/ei_es/` build with `lang/es` + `lang/en` packs & launcher `.exe` |
| [`tools/launcher/EiLauncher.cs`](tools/launcher/EiLauncher.cs) | C# (WinForms x86) source for `Configurar y Jugar.exe` |
| [`tools/export_world.py`](tools/export_world.py) | JSON/PNG exporter for maps, database, and scenarios |
| [`tools/save_tool.py`](tools/save_tool.py) | Savegame inspector & CRC-safe patcher for `save*.res` |
| [`loc/es/`](loc/es) | JSON localization catalogs and translated `.txt` docs |
| [`vendor/cnc-ddraw/`](vendor/cnc-ddraw) | `cnc-ddraw` HD wrapper (MIT) + GLSL shaders (`libretro`) |
| [`docs/architecture.md`](docs/architecture.md) | Reverse-engineering notes on `Ei.exe` and `.res` formats |
| [`tests/`](tests) | Automated `unittest` suite (`28` tests across `test_blk0.py` and `test_loc_es.py`) |

> Note: `dist/`, `extracted/`, `analysis/`, and `loc/es/audio_cache/` are listed in [`.gitignore`](.gitignore) so no copyrighted 1998 game assets or heavy generated caches are uploaded to Git.

---

## How to Build Locally

### Prerequisites
1. A **legal copy of *Enemy Infestation* (1998)** installed on disk (defaults to `C:\Program Files (x86)\Enemy Infestation`, or pass `--src-dir`).
2. **Windows 10 or 11** with `.NET Framework 4.0` (`csc.exe`, built into Windows) and the **Spanish (Mexico)** Windows speech package (`Microsoft Sabina` / `Microsoft Raul`) if regenerating the TTS audio cache from scratch.
3. **Python 3.10+** with `Pillow`:
   ```powershell
   pip install -r requirements.txt
   ```

### Build & Test Commands

```powershell
# 1. (Optional) Validate all CP1252 localization catalogs
python tools/loc_text_exe.py check

# 2. Build the bilingual HD edition into dist/ei_es (source install is never modified)
python tools/build_es.py

# 3. Run the full automated test suite (28 tests)
python -m unittest discover -s tests -v
```

Using a custom installation path:
```powershell
python tools/build_es.py --src-dir "D:\Games\Enemy Infestation"
```

Once finished, launch the game configurator from:
```text
dist\ei_es\Configurar y Jugar.exe
```

---

## Help Improve the Project!

If *Enemy Infestation* brings back great memories for you too, we'd love your help taking this project even further:

- **Real voice acting:** replace or enhance TTS lines with community-recorded voice lines using the DSP utilities in [`tools/loc_audio.py`](tools/loc_audio.py).
- **Additional languages & translation polish:** refine Spanish phrasing or contribute new language packs (`es-ES`, `pt-BR`, `fr`, `de`, etc.) using the modular `loc/` and `lang/` pack system.
- **Launcher enhancements:** separate text vs audio language selection, per-mission profiles, `Ei.cfg` tweaks, or extra custom icons.
- **Map & campaign editor:** with `Map*.res`, `Scen*.res`, `goal`, and `lply` formats fully documented, a visual mission editor would open the door to custom community campaigns.
- **Compatibility testing:** test across Windows 10/11 setups, ultrawide monitors (`21:9`), Steam Deck / Wine / Proton, and additional shaders.

To contribute:
1. **Fork** the repository.
2. Create a branch (`git checkout -b feature/my-improvement`).
3. Run `python -m unittest discover -s tests -v` to verify all checks pass.
4. Open a **Pull Request** or **Issue**!

---

## Credits & Legal Notice

- **Enemy Infestation (1998):** © Clockworks Entertainment / Micro Forte Pty. Ltd. / Ripcord Games. This repository **does not host or distribute any copyrighted game binaries or assets**; it provides open-source tooling and translation data to transform the user's own legitimate copy.
- **cnc-ddraw:** © FunkyFr3sh ([github.com/FunkyFr3sh/cnc-ddraw](https://github.com/FunkyFr3sh/cnc-ddraw)), licensed under the MIT License.
- **GLSL Shaders:** © contributors of [libretro/glsl-shaders](https://github.com/libretro/glsl-shaders).
