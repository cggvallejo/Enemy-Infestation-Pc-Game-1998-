# Enemy Infestation (1998) — Reverse Engineering Notes

Target directory: `C:\Program Files (x86)\Enemy Infestation`  
Primary executable: `Ei.exe` (`426,498` bytes, SHA-256 `0047ab87c27253c22e784e7c61e1332cf0c5e10e9bde63e161773969703c790f`)

---

## 1. Executable Overview (`Ei.exe`)

- **Format:** Win32 PE (`x86`, Machine `0x14c`), `ImageBase = 0x00400000`, `EntryRVA = 0x0004f15c` (`0x0044f15c`), PE `TimeDateStamp = 0x36430f4f`.
- **Toolchain:** Watcom C/C++32 (`WATCOM C/C++32 Run-Time system. (c) Copyright by WATCOM International Corp. 1988-1995`).
- **PE Sections (6 + Headers):**
  - `BEGTEXT`: `0x00401000..0x0045ba00` (code + immediate constants)
  - `DGROUP`: `0x0045c000..0x00462c00` (initialized data, strings, RCS tags)
  - `.bss`: `0x00463000..0x00472c00` (uninitialized globals)
  - `.idata`: `0x00473000..0x00474000` (imports)
  - `.reloc`: `0x00474000..0x00479000`
  - `.rsrc`: `0x00479000..0x00479c00` (version info: MicroForte `1, 0, 0, 1`)
- **Ghidra 12.1.4 baseline (`ei-inspect.json` / `analysis/`):** `1,964` procedures (`1,825` local, `139` external), `634` defined strings (`ei-strings.json`).

### External Dependencies (IAT)
- **Graphics & Video:** `DDRAW.dll` (`DirectDrawCreate`), `GDI32.dll` (`GetStockObject`), `USER32.dll` (`26` total imports across `USER32.dll`/`USER32.DLL`), `smackw32.dll` (`19` imports: `_SmackOpen`, `_SmackBlit*`, `_SmackDDSurfaceType`, `_SmackSoundUseDirectSound`, etc.)
- **Audio:** `DSOUND.dll` (`Ordinal#1` = `DirectSoundCreate`), `WINMM.dll` (`11` imports: `mciSendStringA` / `mciGetErrorStringA` for Red Book CD audio `Track01.wav`–`Track05.wav`, `mmio*`)
- **Networking / COM:** `ole32.dll` (`3` imports: `CoInitialize`, `CoCreateInstance`, `CoUninitialize`)
- **OS / Runtime:** `KERNEL32.dll` (`77` total imports across `KERNEL32.dll`/`KERNEL32.DLL`)

### Original Source Modules (61 RCS `$Id:` Tags)
Authors observed in RCS headers (and `Credits.txt`): `sjh` (Simon Hayes), `shams` (Michael Shamgar), `carl` (Carl Sandland), `matt` (Matthew Cairns), `maus` (Daniel Vidoni). Latest observed timestamp: `main.c v1.388` (`1998/11/06 03:23:01`).

- **Core / Engine / Memory / Containers:** `main.c`, `GAME.C`, `VERSION.C`, `CONFIG.C`, `TIMER.C`, `STDERROR.C`, `STDUTIL.C`, `LLIST.C`, `ringbuf.c`, `debug.c`, `CRC16.C`, `CODEC.C`, `BLOCK.C`, `RESMGR.C`, `RESALLOC.C`
- **Graphics / UI / Video:** `VIDEO.C`, `VIEW.C`, `BITMAP.C`, `BITFONT.C`, `SPRITE.C`, `mysprite.c`, `palette.c`, `COLORCYC.C`, `MAPDRAW.C`, `MINIMAP.C`, `POINT.C`, `POINTER.C`, `RECT.C`, `POLY.C`, `circle.c`, `line.c`, `FLOOD.C`, `cpanel.c`, `dialogs.c`, `dlgstart.c`, `movie.c`, `pop.c`, `misc.c`
- **Audio:** `MFSNDW.C`, `bisnd.c`, `volume.c`
- **Networking:** `Binet.c`, `net.c`, `request.c`
- **World / Gameplay / Savegames:** `Scenario.c`, `map.c`, `room.c`, `DOOR.C`, `ELEVATOR.C`, `EXIT.C`, `teleport.c`, `Pobj.c`, `player.c`, `Weapon.c`, `Goal.c`, `goalfn.c`, `MIND.C`, `mop.c`, `VEHSTD.C`, `vehmap.c`, `savegame.c`

---

## 2. Boot Flow, Copy Protection & Subsystems (`Ei.exe`)

### `entry` -> `WinMain` (`0x401040..0x401838`) & Copy Protection
1. **Serial/Binary Tamper Check (`0x43f9ce..0x43fa80`):**
   - Calls `0x452891` (`GetLocalTime` -> `tm`) + `0x4528f6` (`mktime`), seeds PRNG via `0x43fa2b` (`srand`), and runs CRC-16/ARC (`0x43fa40`, table at `0x4619f6`) over `"SeRiAlNu"` (`0x45e12a`).
   - Compares result against `word [0x45e132] == 0xf201` (`crc16_arc(b"SeRiAlNu") == 0xf201`); mismatch displays `"Unauthorised Copy!"` and terminates.
2. **Configuration & CLI Switches (`0x40226c` `CONFIG.C`):**
   - Parses `ei.cfg` for `[Scrolling]`, `[Debug]`, and `[Install]` path (`DAT_004633d0`).
   - Resolves resolution flags (`320x200`, `640x480`, `800x600`, `1024x768` -> `DAT_0045e100..4`) and primary audio format (`22050/8/1`, `22050/16/1`, `22050/16/2`, `44100/16/2` -> `DAT_0045e108..10`).
3. **CD-ROM & Disk Check (`0x403464` -> `0x444f28`):**
   - Checks `"COPYPROTECTION"`, truncates `DAT_004633d0` to drive root (`"X:\\"`), probes `X:\autorun.inf`, `X:\EI`, and `X:\DirectX`. If missing, loops `MessageBoxA(..., "Please Insert CDROM", "Enemy Infestation", MB_RETRYCANCEL)` (`5`), exiting via `0x43fa6b` on Cancel.
   - Calls `0x444f28`, which calls `GetDiskFreeSpaceA` and returns free bytes (`FreeClusters * SectorsPerCluster * BytesPerSector`).
4. **Intro Video Sequence (`movie.c` `0x43bddc`, `0x43be5c`, `0x43be88`):**
   - Plays `panasoni.smk`, `ripcord.smk`, `clock.smk`, `intro.smk` via `DirectDrawCreate` + `_SmackOpen` (`640x480x16`).
5. **Subsystem & Resource Initialization (`0x401b0c`):**
   - Checks `GlobalMemoryStatus` (`DAT_004635fe = dwTotalPhys < 0x800001`).
   - Resolves files via `0x402e84` (`LocateFile`: checks CWD first via `0x444db4`, falling back to `DAT_004633d0` `[Install]` path) and opens `stdres.res` -> `DAT_004635ec` and `text.res` -> `DAT_004633cc` via `0x443208`.
   - Initializes subsystems in sequence: `TIMER.C` (`0x443c40`), `VIDEO.C` (`0x43ff40`, `DirectDrawCreate`, `SetCooperativeLevel`, `SetDisplayMode`, primary+back flipping surface, `SetPalette`), `BITMAP.C` (`0x440a00`), `SPRITE.C` (`0x444f68`), `VIEW.C` (`0x446b60`), `vehmap.c` (`0x426b40`), `map.c` (`0x4045d8`), `room.c` (`0x40f880`), `player.c` (`0x413880`), `volume.c` (`0x432920`), `Weapon.c` (`0x41b8f0`), `EXIT.C` (`0x4036a0`), `ELEVATOR.C` (`0x412d40`), `DOOR.C` (`0x411970`), `teleport.c` (`0x43f700`), `Scenario.c` (`0x41f550`), `Pobj.c` (`0x423308`), `Goal.c` (`0x406f40`), `Binet.c` (`0x4339ec`), `BITFONT.C` (`0x4494e0`/`0x449530` x8), `POINTER.C` (`0x420470`), `COLORCYC.C` (`0x449a40`), `VEHSTD.C` (`0x438110`), `savegame.c` (`0x43c3a0`), `bisnd.c` (`0x422700` `sound.res`).
6. **Main Loop (`0x4015e1..0x401827`):**
   - Loads `savegame` / `scen` / `alie` (`0x434df8`) / `clut` (`0x4408fc`), runs per-frame simulation & UI tick `0x401f3c` (cursor/map/sprite/audio/network/UI views), periodically syncs `ei.cfg` (`0x4021dc`), shows `credits.txt` (`0x4030f4`), and plays `final.smk` (`800x600x16`) on victory/exit.

### Audio Subsystem (`MFSNDW.C` `0x450240`, `0x45056c`)
- `0x450240`: `InitializeCriticalSection(&DAT_004726b0)`, calls `DirectSoundCreate`, `SetCooperativeLevel`, creates primary sound buffer (`DAT_004726d4`), and sets primary format (`SetFormat`).
- `0x45056c`: Loads `snd8` (`0x38646e73`) via `RESMGR.C` (`0x44334c`), builds a hard-coded PCM `WAVEFORMATEX` (`wFormatTag=1`, `nChannels=1`, `nSamplesPerSec=22050 [0x5622]`, `nAvgBytesPerSec=22050`, `nBlockAlign=1`, `wBitsPerSample=8`, `cbSize=0`), locks DirectSound secondary buffer (`0x4504b4` `Lock`/`rep movsd/movsb`/`Unlock`), and duplicates up to `clamp(voices, 1, 8)` voice buffers (stamped `0x98070510`).

### Resource Manager & `BLK0` (`RESMGR.C` `0x44334c`, `BLOCK.C` `0x452daf` / `0x453214` / `0x453448`)
- `0x44334c` checks `RMGR` (`0x52474d52`) handle validity, searches cached nodes by `(id, sub_id)`, otherwise calls `0x453410` + `0x453448` to read raw chunk bytes and records `0x1a`-byte cache entries.
- `0x453214` serializes writable `BLK0` files: rewinds and writes `BLK0` v10 header + `IDAT` FourCC inventory + `DIR ` entry table (`10` bytes/entry) + `END ` marker.
- `0x453448` (`__watcall` stream read helper): checks buffer-ready bit `0x08` at `[stream+0x38]`, decrements remaining byte count `[stream+0x30]`, clears flag bit on depletion, and refills via `0x451bfb` (or error handler `0x44abe0`).

### Gameplay, AI, Scenario & Networking (`BITMAP.C`, `Weapon.c`, `Scenario.c`, `Goal.c`, `goalfn.c`, `MIND.C`, `player.c`/`mop.c`, `savegame.c`, `Binet.c`)
- **`BITMAP.C` (`0x440dcc` / `0x441974`):** Locks source and destination DirectDraw surfaces (`0x441164`) and clips source/dest rectangles (`0x44b0b0`, `0x44b2bc`) before blitting:
  - ZRLE path (`*(int *)(bmp + 20) == 3`): uses row offset table + skip/literal opcodes (`cnt = op >> 1`; `op & 1 == 0` skips transparent pixels; `op & 1 == 1` aligns destination to 4 bytes and copies via `rep`/DWORD + byte tail). Separate path handles left/right horizontal clipping.
  - Raw path: `param_3 == 0` performs opaque copy; `param_3 == 1` skips palette index `0` pixels (transparent color key). Unlocks surfaces via `0x440500`.
- **`Weapon.c` (`0x41bbc0`):** Loads `23` (`0x17`) `wtyp` chunks (`0x70797477`) sequentially into `DAT_00464ec0` using `0x48`-byte runtime structs (`0x44`-byte disk payload expanded by inserting runtime weapon index `(short)slot` at `+0x22` and `0x11` at `+0x44`), calling `0x41bd70(slot, *(ushort*)(wtyp + 0x2e))` on each entry.
- **`Scenario.c` (`0x41f9d4`):** Scenario loader parsing `scen`, placed props (`lpob`), weapons (`lwea`, `32` B with active short at `+0x1c`), actors (`lply`, `70` B with colonist-vs-alien bit `byte[0x43] & 1` at offset `67`), alien settings (`alie`), and the mission's `goal_ids` (`0x407324` -> `0x40702c`, `0x4073c8`).
- **`Goal.c` & `goalfn.c` (`0x406f68`, `0x407408`, `0x4075ec`, `0x407654`, `0x407764`, `0x40acd8`):**
  - `0x406f68` clears `32` `goalvar` entries (`DAT_004643a0` via `0x40acd8`/`0x40ace4`), evaluates goals (`0x407544`), allocates a `2,000`-byte goal state buffer (`DAT_00464384`) when `Binet` role != `1`, and registers timer callback `0x407484` at period `2000`.
  - `0x407408` resolves a `Goal*` by `uint16` ID in linked list `DAT_00464390`.
  - `0x407654` checks `2` prerequisite slots (`Goal+0x7a`, stride `8`), requiring each non-null prerequisite goal's runtime state (`*(short*)(prereq + 2)`) to match its expected state.
  - `0x4075ec` evaluates linked condition nodes (`*(Goal + 0x90)`) via AND short-circuiting: invokes `(*(code*)*node)()` and compares against `node[2]` (`cond_param`) using `node[1]` (`cond_flag`: `0` `==`, `1` `!=`, `2` `>`, `3` `<`).
  - `goalfn.c` jump/dispatch tables in `DGROUP`: `0x45e318` maps `35` `cond_op` handlers (`{uint32 id, fn}`, `1..37` with gaps; `31` distinct opcodes used across `Scen*.res`) and `0x45e438` maps `59` `action_op` handlers (`{uint32 id, fn, uint32 mode}`, `1..59`; `47` distinct opcodes used across `Scen*.res`). Delayed actions schedule `delay_s * 1000` timers via `0x443c5c` and thunk `0x4077c4`.
- **`player.c` / `mop.c` Order Executor (`0x40bf70`):** `20`-case command dispatcher (`jump table 0x40bf20`, cases `1..20`) processing unit order queues (`in_EAX[3]`, `LLIST.C` helpers `0x44e670`/`0x44e708`/`0x44e804`): movement (`1..3`), prop/weapon use (`5`), facing/targeting (`6`, `20`), special/network actions (`7`, `12`, `18` -> `Binet` `0x434900` + `misc.c` SFX), rotation smoothing (`in_EAX[0x35]`), client/host check (`0x433f38() == 2`), and sprite update (`0x418a2c`).
- **`MIND.C` (`0x437610`):** 16-state AI dispatcher keyed by FourCC token, registering `{ tick_cb, init_cb, cleanup_cb, state_bytes }` via `0x437ec4`: `'null'` (`0`), `'buld'` (`4`), `'spin'` (`6`, gated on `0x416d0c() == 0xb`), `'grow'` (`8`), `'nest'` (`8`, gated on `0x416d0c() == 0xb`), `'lure'` (`10`), `'wand'`/`'lock'`/`'suck'`/`'heal'` (`12`), `'weap'` (`16`), `'atck'` (`26`), `'grab'`/`'expl'`/`'hunt'` (`28`), `'ambu'` (`32`).
- **`savegame.c` (`0x43cba0`, `0x43c718`):** Symmetric write (`0x43cba0`) and load (`0x43c718`) paths assembling/restoring the `5,836`-byte (`0x16cc`) `sggm` stack snapshot via `0x4438f0`, followed sequentially by `sgpl` (`0x41729c`/`0x43cfd0`), `sgwp` (`0x43d048`), `sgpo` (`0x43d0ec`), `sgex` (`0x43d19c`), `sgrm` (`0x43d268`), `sggl` (`0x43d350`), and `sgmd` (`0x43d3f4`).
- **`Binet.c` (`0x433f50`):** Network role dispatcher checking `DAT_00461434` (`0` -> `0x433f40()`, `1` -> `0x433f48()`, `2` -> standalone return `1`).

---

## 3. `BLK0` Resource Archive Format (`.res`)

Verified across **52/52 `.res` files** (`13,116` chunks, `0` errors) in `C:\Program Files (x86)\Enemy Infestation\`: `Text.res`, `Stdres.res`, `Sound.res`, `Map{1,2,3,5,6,7}.res`, `Scen{00..27,30..39,61..63}.res`, and `save{0000,0001}.res`.

### File Header (16 bytes)
```c
struct Blk0Header {
    char     magic[4];    // "BLK0"
    uint16_t version;     // 10 (0x000a)
    uint32_t dir_offset;  // byte offset to the "DIR " chunk
    uint16_t reserved1;   // 0
    uint32_t reserved2;   // 0
};
```

### Chunk Layout
Each chunk starts with a 16-byte header:
```c
struct Blk0ChunkHeader {
    char     tag[4];      // FourCC ("cbmp", "pal0", "font", "snd8", "DIR ", "IDAT", "END ", ...)
    uint32_t size;        // payload byte length (following this 16-byte header)
    uint16_t id;          // resource ID
    uint16_t flags_or_cnt;// varies (e.g. entry count in DIR/IDAT, 2 in data chunks)
    uint32_t reserved;    // 0
};
```

- Every data chunk payload (except `IDAT`, `DIR `, `END `) begins with a 4-byte prefix:
  - `uint16_t sub_id` (`0` for primary entries; e.g., `2` for secondary `mapd`/`rmsk`/`cbmp` entries)
  - `uint16_t crc16` — **CRC-16/ARC** (reflected poly `0xA001`, init `0x0000`) computed over `payload[4:]`.
- Near the end of the archive:
  - `IDAT` listing all 4-byte FourCC tags present (`flags_or_cnt` = tag count).
  - `DIR ` at `dir_offset`: `n_entries` 10-byte directory records `{ char tag[4]; uint16_t id; uint32_t file_offset; }`.
  - `END ` (16 bytes, `size = 0`) at EOF.

---

## 4. Decoded Resource Chunk Formats (38 Unique Tags Observed)

### `cbmp` (`2,442` chunks across `48` files)
Verified **2,442/2,442** chunks decoded without error (`Modes: {0: 1201, 1: 11, 2: 215, 3: 1015}`; `Formats: {0x0008: 1212, 0x0308: 1230}`). Verified in `BITMAP.C` (`0x440dcc` creates `0x30`-byte `BMAP` wrapper; `0x441974` / `0x441b80` executes ZRLE decompression):
```c
// Starts at payload[4:] (after sub_id + crc16)
struct CbmpHeader {
    char     magic[4];    // "cbmp"
    uint32_t data_size;   // compressed/pixel payload size after the 24-byte CbmpHeader
    uint16_t width;
    uint16_t height;      // total height (for strips: frame_height * frame_count)
    uint16_t mode;        // bit 0: strip (multi-frame), bit 1: ZRLE compressed
    uint16_t format;      // 0x0008 (raw 8bpp) or 0x0308 (ZRLE 8bpp)
    uint32_t field16;     // frame_count for mode 1/3 strips (all 1,026 satisfy height % field16 == 0); also 354 in 800 Map*.res sub_id=2 mode=0 chunks
    uint32_t field20;     // mostly 0; occasionally 0x00d7d01e / 0x0042007e
};
```
- **Modes `0` / `1` (Raw 8bpp):** `width * height` uncompressed 8-bit palette indices.
- **Modes `2` / `3` (ZRLE 8bpp):** `height` `uint32_t` row offsets relative to the start of the row-offset table (`body[24:]`), followed by scanlines of command bytes `cmd`:
  - `cmd & 1 == 0`: skip `cmd >> 1` transparent pixels (palette index `0`).
  - `cmd & 1 == 1`: copy `cmd >> 1` literal pixels immediately following `cmd`.

### Graphics, Audio & Text Tags
- `pal0` (`10`): `768` bytes = `256 * (R, G, B)` 8-bit-per-channel VGA palette (`6001` in `Stdres.res` is the shared UI/sprite palette).
- `clut` (`60`, 10/map): 256-byte palette remap/shading lookup tables (sizes `256`, `512`, `4096`, `4352`).
- `font` (`8` in `Stdres.res`): `uint16_t cbmp_id, flag` + `10`-byte glyph entries `{ uint16_t code, x, y, w, h }`.
- `sprt` (`184`): `5 x int16` (`x, y, z, start_sseq_id, count`).
- `sseq` (`1,735`): `11 x uint16` (`cbmp_id, unk1, delay_ms, unk3, unk4, frame_w, frame_h, hotspot_x, hotspot_y, unk9, unk10`) + byte frame-index sequence terminated by `0xFF` (e.g. door open `00..0c ff`, close `0c..00 ff`).
- `snd8` (`1,588`): Raw `22050 Hz`, 8-bit unsigned mono PCM wave data.
- `text` (`836`): Null-terminated CP1252/Latin-1 string.
- `digs` (`3` in `Stdres.res`): Plain-text Lisp-like S-expression scripts (`bogdrop.dig`, `commsdev.dig`, `bookc.dig`) exposing script symbols including `debugMsg`, `weaponMakeNew`, `playerMakeNew`, `PLYR_ATTR_MTROOPER`, `WPNTYPE_bog`, `WPNEFCT_kill5`, and `CBM_RES_*`.

### World Maps (`Map{1,2,3,5,6,7}.res`)
All maps use a `16 x 8` pixel-to-tile scale (`width_px == grid_w * 16`, `height_px == grid_h * 8`):
- `Map1.res`: *The greenhouse* (`2752 x 1472`, grid `172 x 184` — `38` rooms, `32` roofs, `52` doors, `3` elevators, `55` exits)
- `Map2.res`: *The lagoon* (`2304 x 1664`, grid `144 x 208` — `44` rooms, `41` roofs, `49` doors, `8` elevators, `57` exits)
- `Map3.res`: *The Ice Mine* (`2304 x 1664`, grid `144 x 208` — `43` rooms, `37` roofs, `41` doors, `16` elevators, `57` exits)
- `Map5.res`: *Space* (`2304 x 1664`, grid `144 x 208` — `38` rooms, `33` roofs, `43` doors, `0` elevators, `44` exits)
- `Map6.res`: *Luna* (`2304 x 1664`, grid `144 x 208` — `13` rooms, `10` roofs, `12` doors, `0` elevators, `12` exits)
- `Map7.res`: *Fora* (`1792 x 1344`, grid `112 x 168` — `10` rooms, `7` roofs, `8` doors, `1` elevator, `9` exits)
- `mapd` (`12`, identical `sub_id` `0`/`2` pairs of `296` bytes): `{ width, height, grid_w, grid_h, char name[32], char base[40], ... }`.
- `cbmp 0` / `cbmp 1` / `cbmp 9997, 9999` / `rmsk` (`6`): Full-size base terrain images (`Map1` mean luma `39.10` vs darker `21.25`), `grid_w x grid_h` tile-resolution masks (`172 x 184` on `Map1`), and `int8_t[height]` row depth table (`rmsk`).
- `room` (`186`): `{ char code[4], char name[32], uint16_t nv, int16_t x0, y0 }` + `nv - 1` relative `(dx, dy)` polygon vertices (forming the `nv`-vertex closed polygon `[origin] + points`).
- `roof` (`160`), `door` (`205`), `elev` (`28`), `exit` (`234`): 6-layer roof `cbmp` IDs + pixel `(x, y)` (palette index `0` transparent), doors (`x, y, door_id`), elevator shafts (stops with `room[4], tile_x, tile_y, px_x, px_y`), and room exits (`room1, tile1 -> room2, tile2`).

### Database (`Stdres.res`), Scenarios (`Scen*.res`), Text (`Text.res`) & Savegames (`save*.res`)
- `Stdres.res` (`3,513` chunks): `sseq` (`1,668`), `cbmp` (`1,360`), `view` (`167`, `296` B UI widgets with `name`, `class_name` e.g. `vehMain`/`vehTabButton`, tooltip, `rect`, `cbmp_id`), `sprt` (`145`), `pobj` (`72`, `172` B interactive props), `wtyp` (`23`, `68` B weapons/items), `patr` (`21`, `88` B alien/colonist templates; `patr[2:88]` embeds directly into runtime `sgpl[92:178]`), `weft` (`18`, weapon effects, IDs `0..18` except `15`), `mind` (`13`, AI state sequences), `load` (`10`, loading screen coordinates), `font` (`8`), `pal0` (`4`), `digs` (`3`).
- `Text.res`: `210` `text` string chunks (of `836` total `text` chunks across all `.res` files).
- `Scen*.res` (`41` scenarios):
  - `scen` (`41`, `3,640` B): `u32 kind` (`0`=SP, `2`=MP, `4`=Demo), `title[40]` (`4..44`), `version[20]` (`44..64`), `briefing` (`300..2348`), `music_track` (`2348..2364`, e.g. `Track04.wav`), `map_file` (`2364..2380`, e.g. `Map1.res`/`map2.res`), `u16 start_x, start_y` (`2380..2384`), and zero-terminated `u16 goal_ids[]` list (`2384..`).
  - `goal` (`1,026`, `1,330` B): `u16 flags` (`10`=visible objective, `0`=hidden trigger), `title[64]` (`2..66`), `prereq_goal_id, prereq_state` (`102..106`), `cond_op` (`110`), `cond_flag` (`112`, comparison operator `0: ==`, `1: !=`, `2: >`, `3: <`), `cond_param` (`114`), `cond_val / cond_str` (`116..148`), `action_op, action_arg` (`370..374`).
  - `alie` (`41`, `13 x uint16`), `lply` (`2,338`, `70` B: `tile` `0..4`, `room[4]` `4..8`, `u16 unk8` `8..10`, `name[32]` `10..42`, `actor_code[4]` `42..46`, `patr_id` `46..48`, `voice_base`/`voice_alt` `48..52`, `hp` `54..56`, `extra_i16[5]` `56..66`, `flags66` `66`, `flags67` `67` where `flags67 & 1` = colonist/human and `& 2` = NPC, `slot68` `68..70`), `lwea` (`847`, `32` B: `weapon_type` `0..2`, `code[4]` `2..6`, `room[4]` `6..10`, `tile` `10..14`, `tail_u16[9]` `14..32` with `effect_id` (`weft`) at `+22` = `tail_u16[4]`, `active` boolean at `+0x1c` = `tail_u16[7]`, and `flag30` at `+0x1e` = `tail_u16[8]`), `lpob` (`433` in `Scen*.res`, `76` B placed `pobj`).
- `save*.res` (`save0000.res`, `save0001.res`):
  - `sggm` (`5,836` B, stack layout verified in `0x43cba0`): `0x0006` (`23` `uint16` weapon slots/flags), `0x0034` (`23` `uint16` entries), `0x0066` (scenario ID + `100`-byte name), `0x00ce` (`128`-byte save title), `0x014e` (`32` bytes), `0x016e` (`10 x 200`-byte arrays), `0x0940..0x15c0` (last `40` radio log entries of `80` bytes each), `0x15c0` (elapsed ticks + 4 `uint16` globals).
  - `sgpl` (`24`, `254` B): `[0..32]` name, `[32..36]` `actor_code`, `[36..40]` `tag`, `[48..52]` `weapon_code`, `[80..84]` `hp` (`255` sentinel observed on dead aliens in `save0000`/`save0001`) & `max_hp`, `[92..178]` embedded copy of `patr[2:88]` (`role[32]`, `patr_id` at `+124`, `voice_base` at `+154`), `[178..186]` runtime `room[4], tile_x, tile_y`.
  - `sgwp` (`14`, `62` B), `sgpo` (`6`, `442` B), `sgmd` (`7`, `606` B), `sgex` (`114`), `sgrm` (`88`), `sggl` (`22`, `332` B: `goal_id`, `state_flags` where `0x0001` = active and `0x0100` = triggered, `a0, a1`).
- `defaults.dat` (`1024` bytes): Default network/game config (`127.0.0.1` stored at offset `0x67`).

---

## 5. Tooling & Verification ([`blk0.py`](../tools/blk0.py), [`export_world.py`](../tools/export_world.py), [`save_tool.py`](../tools/save_tool.py), [`test_blk0.py`](../tests/test_blk0.py))

- **[`tools/blk0.py`](../tools/blk0.py):** Python 3 CLI and library (with Pillow, slicing-by-8 CRC-16/ARC, and [`build_blk0`](../tools/blk0.py) with `auto_idat`) providing `verify`, `list`, `dump --decode` (including full `scen`, `goal` with `cond_cmp`, `lply` 70 B, `lwea` 32 B with `effect_id`/`active`, `sgpl`, and `sggl` metadata), and `extract` (`--decode --split-frames`, WAV, `.dig`, `.txt`, `.json`).
- **[`tools/export_world.py`](../tools/export_world.py):** Exports `database.json` (`Stdres.res`), `text_table.json` (`Text.res`), `scenarios.json` (`41` `Scen*.res`), `maps/<Map>.json` (`6` maps), and with `--render-maps` composites `cbmp 0` + index-`0`-transparent `roof` layers (`<Map>_base.png`) and draws `room` polygons, `door` boxes, `exit` links, and `elev` shafts (`<Map>_annotated.png`) into `extracted/world/`.
- **[`tools/save_tool.py`](../tools/save_tool.py):** Savegame CLI & library providing `inspect` (`--json`, `chunk_counts`, `sggm`, `sgpl`, `sgwp`, `sgpo`, `sgmd`, `sggl`, `sgex`, `sgrm`) and CRC-16/ARC-recalculating `patch` (`--title`, `--heal-colonists`, `--goal-flag ID=FLAGS`, refusing writes under `Program Files`).
- **[`tests/test_blk0.py`](../tests/test_blk0.py):** `unittest` suite (`9` tests) covering CRC-16/ARC vectors and random-length equivalence, `cbmp` modes `0..3` & `pal0`, synthetic `BLK0` roundtrip (`build_blk0` & `auto_idat`) + CRC tamper detection, `lply`/`lwea` decoders, `save_tool` inspect/patch roundtrips, and live verification/exporter checks against the installed game files.
