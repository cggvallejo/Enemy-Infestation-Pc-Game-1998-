#!/usr/bin/env python3
"""Assemble standalone Latin American Spanish Enemy Infestation distribution into dist/ei_es."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import blk0  # noqa: E402
import loc_audio  # noqa: E402
import loc_fonts_ui  # noqa: E402
import loc_text_exe  # noqa: E402

DEFAULT_SRC_DIR = Path(r"C:\Program Files (x86)\Enemy Infestation")
DEFAULT_OUT_DIR = ROOT / "dist" / "ei_es"
DEFAULT_LOC_DIR = ROOT / "loc" / "es"
DEFAULT_CACHE_DIR = DEFAULT_LOC_DIR / "audio_cache"
DEFAULT_DDRAW_DIR = ROOT / "vendor" / "cnc-ddraw"
LAUNCHER_SRC = ROOT / "tools" / "launcher" / "EiLauncher.cs"
LAUNCHER_EXE_NAME = "Configurar y Jugar.exe"

DDRAW_ES_OVERRIDES: dict[str, str] = {
    "fullscreen": "true",
    "windowed": "true",
    "maintas": "true",
    "boxing": "false",
    "renderer": "opengl",
    "adjmouse": "true",
    "configlang": "spanish",
}

HD_LAUNCHERS: tuple[tuple[str, str], ...] = (
    (
        "Jugar (HD 800x600 Escalado).bat",
        '@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0Ei.exe" %*\r\n',
    ),
    (
        "Jugar (1024x768 Alta Vista).bat",
        '@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0Ei.exe" -r1 %*\r\n',
    ),
    (
        "Configurar Pantalla HD.bat",
        '@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0cnc-ddraw config.exe"\r\n',
    ),
)

STATIC_RUNTIME_ASSETS = (
    "Ei.cfg",
    "Enemy-Infestation_Fix_Win_EN_Copy-Protection-Workaround.cfg",
    "defaults.dat",
    "Smackw32.dll",
    "save0000.res",
    "save0001.res",
)

DOC_FILES = ("Help.txt", "ReadMe.txt", "Credits.txt")


def _copy_writable(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        os.chmod(dst, stat.S_IWRITE | stat.S_IREAD)
    shutil.copyfile(src, dst)
    os.chmod(dst, stat.S_IWRITE | stat.S_IREAD)


def _write_bytes_writable(dst: Path, data: bytes) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        os.chmod(dst, stat.S_IWRITE | stat.S_IREAD)
    dst.write_bytes(data)


def _unpack_spec(item: blk0.ChunkSpec) -> tuple[str, int, int, int, int, bytes]:
    if isinstance(item, blk0.Blk0Chunk):
        return (item.tag, item.chunk_id, item.flags_or_count, item.reserved, item.sub_id, item.body)
    return item


def apply_stdres_visuals(
    specs: list[blk0.ChunkSpec],
    ext_cbmps: dict[int, blk0.CbmpImage],
    ext_fonts: dict[int, bytes],
    ui_cbmps: dict[int, blk0.CbmpImage],
) -> tuple[list[blk0.ChunkSpec], dict[str, int]]:
    """Patch extended Spanish fonts and localized UI cbmps into Stdres chunk list."""
    merged_cbmps = {**ext_cbmps, **ui_cbmps}
    encoded_cbmps: dict[int, bytes] = {}
    out: list[blk0.ChunkSpec] = []
    stats = {"fonts": 0, "cbmps": 0}

    for item in specs:
        tag, cid, fc, res, sub_id, body = _unpack_spec(item)
        if tag == "font" and cid in ext_fonts:
            body = ext_fonts[cid]
            fc = (len(body) + 24575) // 24576 + 1
            out.append((tag, cid, fc, res, sub_id, body))
            stats["fonts"] += 1
        elif tag == "cbmp" and cid in merged_cbmps:
            enc = encoded_cbmps.get(cid)
            if enc is None:
                enc = blk0.encode_cbmp(merged_cbmps[cid])
                encoded_cbmps[cid] = enc
            fc = (len(enc) + 24575) // 24576 + 1
            out.append((tag, cid, fc, res, sub_id, enc))
            stats["cbmps"] += 1
        else:
            out.append(item)

    return out, stats


def configure_cnc_ddraw_ini(
    raw_ini: str,
    overrides: dict[str, str] | None = None,
) -> str:
    """Apply overrides to the [ddraw] section while preserving upstream game presets."""
    target = DDRAW_ES_OVERRIDES if overrides is None else overrides
    pending = dict(target)
    section = ""
    has_ei_peekmessage = False
    out_lines: list[str] = []

    for line in raw_ini.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            out_lines.append(line)
            continue
        if section == "ddraw" and stripped and not stripped.startswith(";") and "=" in line:
            key, _sep, _val = line.partition("=")
            key_norm = key.strip().lower()
            if key_norm in target:
                out_lines.append(f"{key.strip()}={target[key_norm]}")
                pending.pop(key_norm, None)
                continue
        elif section == "ei" and stripped.lower() == "hook_peekmessage=true":
            has_ei_peekmessage = True
        out_lines.append(line)

    if pending:
        raise ValueError(f"Missing keys in [ddraw] section of ddraw.ini: {sorted(pending)}")
    if not has_ei_peekmessage:
        raise ValueError("Missing [EI] hook_peekmessage=true preset in ddraw.ini")
    return "\r\n".join(out_lines) + "\r\n"


def find_csc_exe() -> Path:
    """Locate the .NET Framework 4.x C# compiler (csc.exe) on Windows."""
    win_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        win_dir / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
        win_dir / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    found = shutil.which("csc.exe")
    if found:
        return Path(found)
    raise FileNotFoundError(
        "C# compiler (csc.exe) not found in .NET Framework v4.0.30319 or PATH"
    )


def compile_hd_launcher(
    out_dir: Path,
    src_path: Path = LAUNCHER_SRC,
    csc_path: Path | None = None,
) -> Path:
    """Compile the standalone x86 WinForms HD launcher & configurator executable."""
    if not src_path.is_file():
        raise FileNotFoundError(f"Launcher source not found: {src_path}")

    csc = csc_path if csc_path is not None else find_csc_exe()
    out_dir.mkdir(parents=True, exist_ok=True)
    exe_dst = out_dir / LAUNCHER_EXE_NAME
    if exe_dst.exists():
        os.chmod(exe_dst, stat.S_IWRITE | stat.S_IREAD)

    cmd = [
        str(csc),
        "/nologo",
        "/optimize+",
        "/codepage:65001",
        "/target:winexe",
        "/platform:x86",
        "/warnaserror+",
        f"/out:{exe_dst}",
        "/reference:System.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.Windows.Forms.dll",
        str(src_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        details = (proc.stdout + "\n" + proc.stderr).strip()
        raise RuntimeError(f"Failed compiling {LAUNCHER_EXE_NAME}: {details}")
    return exe_dst


def install_cnc_ddraw_and_launchers(ddraw_dir: Path, out_dir: Path) -> dict[str, int]:
    """Install cnc-ddraw wrapper, shaders, tuned ddraw.ini, and HD Windows launchers."""
    if not ddraw_dir.is_dir():
        raise FileNotFoundError(f"cnc-ddraw directory not found: {ddraw_dir}")

    copied = 0
    for name in ("ddraw.dll", "cnc-ddraw config.exe"):
        src = ddraw_dir / name
        if not src.is_file():
            raise FileNotFoundError(f"Missing cnc-ddraw asset: {src}")
        _copy_writable(src, out_dir / name)
        copied += 1

    shaders_src = ddraw_dir / "Shaders"
    if not shaders_src.is_dir():
        raise FileNotFoundError(f"Missing cnc-ddraw Shaders directory: {shaders_src}")
    for path in sorted(shaders_src.rglob("*")):
        if path.is_file():
            dst = out_dir / "Shaders" / path.relative_to(shaders_src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            _copy_writable(path, dst)
            copied += 1

    ini_src = ddraw_dir / "ddraw.ini"
    if not ini_src.is_file():
        raise FileNotFoundError(f"Missing cnc-ddraw ini template: {ini_src}")
    tuned_ini = configure_cnc_ddraw_ini(ini_src.read_text("utf-8"))
    ini_dst = out_dir / "ddraw.ini"
    if ini_dst.exists():
        os.chmod(ini_dst, stat.S_IWRITE | stat.S_IREAD)
    ini_dst.write_bytes(tuned_ini.encode("utf-8"))
    copied += 1

    for bat_name, bat_body in HD_LAUNCHERS:
        bat_dst = out_dir / bat_name
        if bat_dst.exists():
            os.chmod(bat_dst, stat.S_IWRITE | stat.S_IREAD)
        bat_dst.write_bytes(bat_body.encode("ascii"))

    compile_hd_launcher(out_dir)

    return {
        "ddraw_files": copied,
        "launchers": len(HD_LAUNCHERS),
        "launcher_exe": 1,
    }


def install_language_packs(src_dir: Path, out_dir: Path) -> dict[str, int]:
    """Install selectable Español ('es') and original English ('en') asset packs."""
    locale_files: list[str] = ["Ei.exe", "Text.res", "Stdres.res", "Sound.res", *DOC_FILES]
    locale_files.extend(p.name for p in sorted(src_dir.glob("Map*.res")))
    locale_files.extend(p.name for p in sorted(src_dir.glob("Scen*.res")))
    keep_set = set(locale_files)

    es_dir = out_dir / "lang" / "es"
    en_dir = out_dir / "lang" / "en"
    for lang_dir in (es_dir, en_dir):
        lang_dir.mkdir(parents=True, exist_ok=True)
        for existing in lang_dir.iterdir():
            if existing.is_file() and existing.name not in keep_set:
                os.chmod(existing, stat.S_IWRITE | stat.S_IREAD)
                existing.unlink()

    for name in locale_files:
        es_built = out_dir / name
        en_orig = src_dir / name
        if not es_built.is_file():
            raise FileNotFoundError(f"Missing built Spanish file for pack: {es_built}")
        if not en_orig.is_file():
            raise FileNotFoundError(f"Missing original English file for pack: {en_orig}")
        _copy_writable(es_built, es_dir / name)
        _copy_writable(en_orig, en_dir / name)

    _write_bytes_writable(
        out_dir / "launcher.ini",
        (
            "[Launcher]\r\n"
            "GameResolution=800x600\r\n"
            "Language=es\r\n"
            "InstalledLanguage=es\r\n"
        ).encode("utf-8"),
    )
    return {
        "lang_es_files": len(locale_files),
        "lang_en_files": len(locale_files),
    }


def build_distribution(
    src_dir: Path = DEFAULT_SRC_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
    loc_dir: Path = DEFAULT_LOC_DIR,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    ddraw_dir: Path = DEFAULT_DDRAW_DIR,
) -> dict[str, Any]:
    """Build complete localized Spanish distribution without touching src_dir."""
    t0 = time.monotonic()
    src_res = src_dir.resolve()
    out_res = out_dir.resolve()
    if src_res == out_res or src_res in out_res.parents or out_res in src_res.parents:
        raise ValueError(f"Unsafe build paths: src={src_res} vs out={out_res}")
    if not src_dir.exists():
        raise FileNotFoundError(f"Source game directory not found: {src_dir}")

    issues = loc_text_exe.validate_catalogs(loc_dir)
    if issues:
        raise RuntimeError(f"Catalog validation failed ({len(issues)} issues): {issues[0]}")

    cats = loc_text_exe.load_catalogs(loc_dir)
    tables = loc_text_exe.build_lookup_tables(cats)
    scen_en_map = {(r["file"], r["id"]): r["en"] for r in cats["scenarios"]["scen_texts"]}

    audio_prep = loc_audio.prepare_all_audio_cache(src_dir, tables, scen_en_map, cache_dir)
    f0_cache: dict[str, float] = audio_prep["f0_cache"]

    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "copied_static": 0,
        "copied_docs": 0,
        "maps": 0,
        "scenarios": 0,
        "scen_audio_dubs": 0,
        "sound_counts": {},
        "stdres_visuals": {},
    }

    # 1. Static runtime assets, SMK cinematics, CD-DA WAV tracks, starter saves
    static_paths = [src_dir / name for name in STATIC_RUNTIME_ASSETS]
    static_paths.extend(sorted(src_dir.glob("*.smk")))
    static_paths.extend(sorted(src_dir.glob("Track*.wav")))
    for sp in static_paths:
        if not sp.exists():
            raise FileNotFoundError(f"Missing required runtime asset: {sp}")
        _copy_writable(sp, out_dir / sp.name)
        summary["copied_static"] += 1

    # 2. Localized documentation (.txt)
    for name in DOC_FILES:
        _copy_writable(loc_dir / name, out_dir / name)
        summary["copied_docs"] += 1

    # 3. Patched Ei.exe
    exe_out = loc_text_exe.patch_ei_exe((src_dir / "Ei.exe").read_bytes(), cats["ei_exe"])
    _write_bytes_writable(out_dir / "Ei.exe", exe_out)

    # 4. Text.res
    text_arc = blk0.Blk0Archive(src_dir / "Text.res")
    text_specs = loc_text_exe.apply_text_and_structs("Text.res", text_arc.chunks, tables)
    _write_bytes_writable(out_dir / "Text.res", blk0.build_blk0(text_specs))

    # 5. Stdres.res (extended fonts + localized UI cbmps + struct names)
    std_arc = blk0.Blk0Archive(src_dir / "Stdres.res")
    ext_cbmps, ext_fonts = loc_fonts_ui.extend_fonts(std_arc)
    ui_cbmps = loc_fonts_ui.localize_ui_cbmps(std_arc, ext_cbmps, ext_fonts)
    std_specs = loc_text_exe.apply_text_and_structs("Stdres.res", std_arc.chunks, tables)
    std_specs, vis_stats = apply_stdres_visuals(std_specs, ext_cbmps, ext_fonts, ui_cbmps)
    summary["stdres_visuals"] = vis_stats
    _write_bytes_writable(out_dir / "Stdres.res", blk0.build_blk0(std_specs))

    # 6. Sound.res (es-MX speech dubs + remastered retro SFX)
    snd_arc = blk0.Blk0Archive(src_dir / "Sound.res")
    snd_specs, snd_counts = loc_audio.apply_sound_res_audio(snd_arc.chunks, cache_dir)
    summary["sound_counts"] = snd_counts
    _write_bytes_writable(out_dir / "Sound.res", blk0.build_blk0(snd_specs))

    # 7. Map*.res
    for mp in sorted(src_dir.glob("Map*.res")):
        map_arc = blk0.Blk0Archive(mp)
        map_specs = loc_text_exe.apply_text_and_structs(mp.name, map_arc.chunks, tables)
        _write_bytes_writable(out_dir / mp.name, blk0.build_blk0(map_specs))
        summary["maps"] += 1

    # 8. Scen*.res (localized scenario text/goals/roster + dubbed briefings & dialogue)
    for sp in sorted(src_dir.glob("Scen*.res")):
        scen_arc = blk0.Blk0Archive(sp)
        scen_specs = loc_text_exe.apply_text_and_structs(sp.name, scen_arc.chunks, tables)
        scen_specs, n_dub = loc_audio.apply_scen_audio(
            sp.name, scen_specs, tables, scen_en_map, f0_cache, cache_dir
        )
        _write_bytes_writable(out_dir / sp.name, blk0.build_blk0(scen_specs))
        summary["scenarios"] += 1
        summary["scen_audio_dubs"] += n_dub

    # 9. Language packs (es + original en) for instant switching from launcher
    summary.update(install_language_packs(src_dir, out_dir))

    # 10. HD scaling wrapper (cnc-ddraw) and Windows launchers
    summary.update(install_cnc_ddraw_and_launchers(ddraw_dir, out_dir))

    summary["elapsed_s"] = round(time.monotonic() - t0, 2)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build standalone es-MX localized Enemy Infestation distribution.")
    ap.add_argument("--src-dir", type=Path, default=DEFAULT_SRC_DIR)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--loc-dir", type=Path, default=DEFAULT_LOC_DIR)
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    ap.add_argument("--ddraw-dir", type=Path, default=DEFAULT_DDRAW_DIR)
    args = ap.parse_args(argv)

    summary = build_distribution(
        args.src_dir, args.out_dir, args.loc_dir, args.cache_dir, args.ddraw_dir
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

