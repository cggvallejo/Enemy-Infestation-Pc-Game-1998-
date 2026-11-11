#!/usr/bin/env python3
"""End-to-end verification tests for Enemy Infestation Latin American Spanish localization."""

from __future__ import annotations

import io
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import blk0  # noqa: E402
import build_es  # noqa: E402
import loc_audio  # noqa: E402
import loc_fonts_ui  # noqa: E402
import loc_text_exe  # noqa: E402

SRC_DIR = Path(r"C:\Program Files (x86)\Enemy Infestation")
DIST_DIR = ROOT / "dist" / "ei_es"


def _make_test_wav_16k(freq_hz: float = 220.0, dur_s: float = 0.25) -> bytes:
    sr = 16000
    n = int(sr * dur_s)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        samples = bytearray()
        for i in range(n):
            v = int(16000 * math.sin(2.0 * math.pi * freq_hz * i / sr))
            samples.extend(struct.pack("<h", v))
        wf.writeframes(bytes(samples))
    return buf.getvalue()


class CatalogValidationTests(unittest.TestCase):
    def test_catalogs_and_docs_valid(self) -> None:
        issues = loc_text_exe.validate_catalogs(ROOT / "loc" / "es")
        self.assertEqual(issues, [])

    def test_technician_gender_consistency(self) -> None:
        cats = loc_text_exe.load_catalogs(ROOT / "loc" / "es")
        tables = loc_text_exe.build_lookup_tables(cats)
        self.assertEqual(tables["patr"][24], "Técnica")
        self.assertIn("La Técnica", tables["scen_text"][("Scen04.res", 13)])
        self.assertIn("La Técnica", tables["scen_text"][("Scen25.res", 5)])


class AudioDspUnitTests(unittest.TestCase):
    def test_remaster_removes_dc_and_avoids_clipping(self) -> None:
        # Synthetic 22050Hz clipped + DC-offset 8-bit transient
        n = 4410
        raw = bytes(
            max(0, min(255, int(128 + 18 + 145 * math.sin(2.0 * math.pi * 300.0 * i / 22050))))
            for i in range(n)
        )
        out = loc_audio.remaster_sfx_pcm8(raw, chunk_id=42)
        self.assertEqual(len(out), len(raw))
        mean = sum(out) / len(out)
        self.assertLess(abs(mean - 128.0), 2.5)
        self.assertGreater(min(out), 0)
        self.assertLess(max(out), 255)

    def test_remaster_preserves_tiny_silent_stub(self) -> None:
        stub = bytes([128] * 32)
        self.assertEqual(loc_audio.remaster_sfx_pcm8(stub, chunk_id=11), stub)

    def test_clean_tts_text_expands_abbreviations(self) -> None:
        cleaned = loc_audio.clean_tts_text("Ve a\n\x02COMUN. y luego al lab. químico con la Dra. Pincus.")
        self.assertIn("Comunicaciones", cleaned)
        self.assertIn("laboratorio químico", cleaned)
        self.assertIn("Doctora Pincus", cleaned)
        self.assertNotIn("\x02", cleaned)
        self.assertNotIn("\n", cleaned)

    def test_tts_wav_to_pcm8_all_filters(self) -> None:
        wav_bytes = _make_test_wav_16k()
        for mode in ("studio", "radio", "comms", "pa_intercom", "robot"):
            pcm = loc_audio.tts_wav_to_pcm8(wav_bytes, filter_mode=mode, seed=7)
            self.assertGreater(len(pcm), 3000)
            self.assertGreater(min(pcm), 0)
            self.assertLess(max(pcm), 255)


class DistBuildIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not DIST_DIR.exists():
            raise AssertionError(f"Expected built distribution at {DIST_DIR}; run tools/build_es.py first.")

    def test_required_runtime_and_media_files_present(self) -> None:
        expected = [
            "Ei.exe",
            "Text.res",
            "Stdres.res",
            "Sound.res",
            "Ei.cfg",
            "Enemy-Infestation_Fix_Win_EN_Copy-Protection-Workaround.cfg",
            "defaults.dat",
            "Smackw32.dll",
            "Help.txt",
            "ReadMe.txt",
            "Credits.txt",
            "Clock.smk",
            "Final.smk",
            "intro.smk",
            "Panasoni.smk",
            "Ripcord.smk",
            "Track01.wav",
            "Track02.wav",
            "Track03.wav",
            "Track04.wav",
            "Track05.wav",
            "save0000.res",
            "save0001.res",
        ]
        for name in expected:
            p = DIST_DIR / name
            self.assertTrue(p.is_file(), f"Missing {p}")
            self.assertGreater(p.stat().st_size, 0, f"Empty {p}")

        self.assertEqual(len(list(DIST_DIR.glob("Map*.res"))), 6)
        self.assertEqual(len(list(DIST_DIR.glob("Scen*.res"))), 41)

    def test_ei_exe_patched_in_place_without_touching_source(self) -> None:
        src_exe = (SRC_DIR / "Ei.exe").read_bytes()
        dst_exe = (DIST_DIR / "Ei.exe").read_bytes()
        self.assertEqual(len(dst_exe), len(src_exe))
        self.assertNotEqual(dst_exe, src_exe)

        cats = loc_text_exe.load_catalogs(ROOT / "loc" / "es")
        for row in cats["ei_exe"]:
            off = int(row["raw_offset"], 16)
            slot = dst_exe[off : off + int(row["max_bytes"]) + 1]
            self.assertEqual(slot.split(b"\x00", 1)[0].decode("cp1252"), row["es"])
            src_slot = src_exe[off : off + int(row["max_bytes"]) + 1]
            self.assertEqual(src_slot.split(b"\x00", 1)[0].decode("cp1252"), row["en"])

    def test_text_res_localized_and_valid(self) -> None:
        arc = blk0.Blk0Archive(DIST_DIR / "Text.res")
        self.assertEqual(arc.verify(), [])
        by_id = {c.chunk_id: blk0._cstr(c.body) for c in arc.chunks if c.tag == "text"}
        self.assertIn("Investigación", by_id[1])
        self.assertTrue(by_id[11042].endswith(" "))
        self.assertTrue(by_id[2000].endswith(" "))

    def test_stdres_fonts_cbmps_and_structs(self) -> None:
        arc = blk0.Blk0Archive(DIST_DIR / "Stdres.res")
        self.assertEqual(arc.verify(), [])

        needed_codes = {g[0] for g in loc_fonts_ui.EXTRA_GLYPHS}
        fonts = {c.chunk_id: blk0.decode_font(c.body) for c in arc.chunks if c.tag == "font"}
        for fid in (15002, 15010, 15011, 15012, 15013, 15014):
            codes = {g["code"] for g in fonts[fid]["glyphs"]}
            self.assertTrue(needed_codes.issubset(codes), f"Font {fid} missing Spanish glyphs")

        patr_names = {c.chunk_id: blk0._cstr(c.body[2:34]) for c in arc.chunks if c.tag == "patr"}
        self.assertEqual(patr_names[24], "Técnica")
        self.assertEqual(patr_names[33], "Bióloga")
        self.assertEqual(patr_names[35], "Robot de servicio")

        dup_11150 = [c for c in arc.chunks if c.tag == "cbmp" and c.chunk_id == 11150]
        self.assertEqual(len(dup_11150), 2)
        self.assertEqual(dup_11150[0].body, dup_11150[1].body)
        for cid in (11110, 11117, 11150, 16011, 6001, 6002):
            c = arc.find_chunks("cbmp", cid)[0]
            blk0.decode_cbmp(c.body)
            self.assertEqual(c.flags_or_count, (len(c.body) + 24575) // 24576 + 1)

    def test_sound_res_dubs_remaster_and_duplicate_204(self) -> None:
        src_arc = blk0.Blk0Archive(SRC_DIR / "Sound.res")
        dst_arc = blk0.Blk0Archive(DIST_DIR / "Sound.res")
        self.assertEqual(dst_arc.verify(), [])
        self.assertEqual(len(dst_arc.chunks), len(src_arc.chunks))

        src_204 = src_arc.find_chunks("snd8", 204)
        dst_204 = dst_arc.find_chunks("snd8", 204)
        self.assertEqual(len(dst_204), 2)
        self.assertEqual([len(c.body) for c in dst_204], [len(c.body) for c in src_204])

        # Verify Band 0 SFX remastered at exact length with low DC and no clipping
        for cid in (12, 23, 221, 600, 14130, 21130):
            s = src_arc.find_chunks("snd8", cid)[0]
            d = dst_arc.find_chunks("snd8", cid)[0]
            self.assertEqual(len(d.body), len(s.body))
            self.assertGreater(min(d.body), 0)
            self.assertLess(max(d.body), 255)
            self.assertLess(abs(sum(d.body) / len(d.body) - 128.0), 1.5)

        # Verify all spoken barks (including grp 90) are dubbed in Spanish & routed to sub_id=2
        dub_checked = 0
        for sc, dc in zip(src_arc.chunks, dst_arc.chunks):
            if dc.tag == "snd8" and 1000 <= dc.chunk_id < 13000:
                grp = ((dc.chunk_id % 1000) // 10) * 10
                if grp in loc_audio.SPOKEN_BARK_GROUPS:
                    self.assertEqual(dc.sub_id, 2)
                    self.assertGreater(len(dc.body), 2000)
                    self.assertNotEqual(dc.body, sc.body)
                    self.assertEqual(dc.flags_or_count, max(1, (len(dc.body) + 24575) // 24576))
                    dub_checked += 1
        self.assertEqual(dub_checked, 709)

    def test_maps_and_scenarios_valid_and_dubbed(self) -> None:
        for mp in sorted(DIST_DIR.glob("Map*.res")):
            arc = blk0.Blk0Archive(mp)
            self.assertEqual(arc.verify(), [], f"{mp.name} BLK0 error")

        total_dubs = 0
        for sp in sorted(DIST_DIR.glob("Scen*.res")):
            src_arc = blk0.Blk0Archive(SRC_DIR / sp.name)
            dst_arc = blk0.Blk0Archive(sp)
            self.assertEqual(dst_arc.verify(), [], f"{sp.name} BLK0 error")

            for sc, dc in zip(src_arc.chunks, dst_arc.chunks):
                if sc.tag == "snd8" and len(sc.body) <= 100:
                    self.assertEqual(dc.body, sc.body, f"{sp.name}:{dc.chunk_id} silent stub altered")
                elif sc.tag == "snd8" and len(sc.body) > 100:
                    self.assertGreater(len(dc.body), 1000)
                    self.assertNotEqual(dc.body, sc.body)
                    self.assertEqual(dc.flags_or_count, (len(dc.body) + 24575) // 24576 + 1)
                    total_dubs += 1

        self.assertEqual(total_dubs, 611)

        s04 = blk0.Blk0Archive(DIST_DIR / "Scen04.res")
        s04_texts = {c.chunk_id: blk0._cstr(c.body) for c in s04.chunks if c.tag == "text"}
        self.assertEqual(s04_texts[13], "La Técnica ha muerto. Has fracasado.")

    def test_cnc_ddraw_hd_wrapper_and_launchers(self) -> None:
        dll = (DIST_DIR / "ddraw.dll").read_bytes()
        pe_off = struct.unpack_from("<I", dll, 0x3C)[0]
        sig, machine = struct.unpack_from("<4sH", dll, pe_off)
        self.assertEqual(sig, b"PE\x00\x00")
        self.assertEqual(machine, 0x014C)

        for rel in (
            "cnc-ddraw config.exe",
            "ddraw.ini",
            "Shaders/interpolation/catmull-rom-bilinear.glsl",
            "Shaders/nearest-neighbor.glsl",
        ):
            self.assertTrue((DIST_DIR / rel).is_file(), f"Missing {rel} in dist")

        ini_text = (DIST_DIR / "ddraw.ini").read_text("utf-8")
        ddraw_cfg = _parse_ini_section(ini_text, "ddraw")
        ei_cfg = _parse_ini_section(ini_text, "EI")
        for key, val in build_es.DDRAW_ES_OVERRIDES.items():
            self.assertEqual(ddraw_cfg.get(key), val)
        self.assertEqual(ei_cfg.get("hook_peekmessage"), "true")

        for bat_name, _ in build_es.HD_LAUNCHERS:
            self.assertTrue((DIST_DIR / bat_name).is_file(), f"Missing launcher {bat_name}")
        self.assertIn('Ei.exe" -r1', (DIST_DIR / "Jugar (1024x768 Alta Vista).bat").read_text("ascii"))
        self.assertIn("cnc-ddraw config.exe", (DIST_DIR / "Configurar Pantalla HD.bat").read_text("ascii"))

        launcher_exe = DIST_DIR / build_es.LAUNCHER_EXE_NAME
        self.assertTrue(launcher_exe.is_file(), f"Missing GUI launcher {build_es.LAUNCHER_EXE_NAME}")
        exe_bytes = launcher_exe.read_bytes()
        exe_pe = struct.unpack_from("<I", exe_bytes, 0x3C)[0]
        exe_sig, exe_machine = struct.unpack_from("<4sH", exe_bytes, exe_pe)
        exe_opt_magic = struct.unpack_from("<H", exe_bytes, exe_pe + 24)[0]
        exe_subsystem = struct.unpack_from("<H", exe_bytes, exe_pe + 92)[0]
        self.assertEqual(exe_sig, b"PE\x00\x00")
        self.assertEqual(exe_machine, 0x014C)
        self.assertEqual(exe_opt_magic, 0x010B)
        self.assertEqual(exe_subsystem, 2)

        cs_src = build_es.LAUNCHER_SRC.read_text("utf-8")
        shader_refs = sorted(set(re.findall(r'Shaders\\[A-Za-z0-9_\\-]+\.glsl', cs_src)))
        self.assertGreaterEqual(len(shader_refs), 6)
        for rel_shader in shader_refs:
            self.assertTrue(
                (DIST_DIR / rel_shader.replace("\\", "/")).is_file(),
                f"Launcher shader preset missing in dist: {rel_shader}",
            )

        launcher_ini = _parse_ini_section((DIST_DIR / "launcher.ini").read_text("utf-8"), "Launcher")
        self.assertEqual(launcher_ini.get("gameresolution"), "800x600")
        self.assertEqual(launcher_ini.get("language"), "es")
        self.assertEqual(launcher_ini.get("installedlanguage"), "es")

        es_pack = DIST_DIR / "lang" / "es"
        en_pack = DIST_DIR / "lang" / "en"
        expected_pack_names = sorted(
            ["Ei.exe", "Text.res", "Stdres.res", "Sound.res", "Help.txt", "ReadMe.txt", "Credits.txt"]
            + [p.name for p in SRC_DIR.glob("Map*.res")]
            + [p.name for p in SRC_DIR.glob("Scen*.res")]
        )
        self.assertEqual(sorted(p.name for p in es_pack.iterdir() if p.is_file()), expected_pack_names)
        self.assertEqual(sorted(p.name for p in en_pack.iterdir() if p.is_file()), expected_pack_names)
        self.assertEqual((en_pack / "Ei.exe").read_bytes(), (SRC_DIR / "Ei.exe").read_bytes())
        self.assertEqual((en_pack / "Text.res").read_bytes(), (SRC_DIR / "Text.res").read_bytes())
        self.assertEqual((es_pack / "Ei.exe").read_bytes(), (DIST_DIR / "Ei.exe").read_bytes())
        self.assertEqual((es_pack / "Text.res").read_bytes(), (DIST_DIR / "Text.res").read_bytes())
        self.assertNotEqual((es_pack / "Text.res").read_bytes(), (en_pack / "Text.res").read_bytes())

    def test_hd_launcher_cli_apply_roundtrip(self) -> None:
        launcher_exe = DIST_DIR / build_es.LAUNCHER_EXE_NAME
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            ddraw_tmp = tmp_dir / "ddraw.ini"
            shutil.copy2(DIST_DIR / "ddraw.ini", ddraw_tmp)

            # 1. Switch to 1024x768 Alta Vista + windowed 1280x960 + integer scale + nearest-neighbor
            p1 = subprocess.run(
                [
                    str(launcher_exe),
                    "--apply",
                    "--dir", str(tmp_dir),
                    "--game-res", "1024x768",
                    "--mode", "windowed",
                    "--scale", "integer",
                    "--win-size", "1280x960",
                    "--renderer", "direct3d9",
                    "--shader", r"Shaders\nearest-neighbor.glsl",
                    "--adjmouse", "false",
                    "--vsync", "true",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(p1.returncode, 0, p1.stderr or p1.stdout)

            ini_1 = ddraw_tmp.read_text("utf-8")
            self.assertTrue(any(ln.lstrip().startswith(";") for ln in ini_1.splitlines()))
            dd_1 = _parse_ini_section(ini_1, "ddraw")
            ei_1 = _parse_ini_section(ini_1, "EI")
            ln_1 = _parse_ini_section((tmp_dir / "launcher.ini").read_text("utf-8"), "Launcher")
            self.assertEqual(dd_1.get("width"), "1280")
            self.assertEqual(dd_1.get("height"), "960")
            self.assertEqual(dd_1.get("fullscreen"), "false")
            self.assertEqual(dd_1.get("windowed"), "true")
            self.assertEqual(dd_1.get("maintas"), "true")
            self.assertEqual(dd_1.get("boxing"), "true")
            self.assertEqual(dd_1.get("renderer"), "direct3d9")
            self.assertEqual(dd_1.get("shader"), r"Shaders\nearest-neighbor.glsl")
            self.assertEqual(dd_1.get("adjmouse"), "false")
            self.assertEqual(dd_1.get("vsync"), "true")
            self.assertEqual(ei_1.get("hook_peekmessage"), "true")
            self.assertEqual(ln_1.get("gameresolution"), "1024x768")

            # 2. Switch back to 800x600 + borderless + stretch + opengl + fsr
            p2 = subprocess.run(
                [
                    str(launcher_exe),
                    "--apply",
                    "--dir", str(tmp_dir),
                    "--game-res", "800x600",
                    "--mode", "borderless",
                    "--scale", "stretch",
                    "--win-size", "0x0",
                    "--renderer", "opengl",
                    "--shader", r"Shaders\interpolation\fsr.glsl",
                    "--adjmouse", "true",
                    "--vsync", "false",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(p2.returncode, 0, p2.stderr or p2.stdout)

            ini_2 = ddraw_tmp.read_text("utf-8")
            dd_2 = _parse_ini_section(ini_2, "ddraw")
            ei_2 = _parse_ini_section(ini_2, "EI")
            ln_2 = _parse_ini_section((tmp_dir / "launcher.ini").read_text("utf-8"), "Launcher")
            self.assertEqual(dd_2.get("width"), "0")
            self.assertEqual(dd_2.get("height"), "0")
            self.assertEqual(dd_2.get("fullscreen"), "true")
            self.assertEqual(dd_2.get("windowed"), "true")
            self.assertEqual(dd_2.get("maintas"), "false")
            self.assertEqual(dd_2.get("boxing"), "false")
            self.assertEqual(dd_2.get("renderer"), "opengl")
            self.assertEqual(dd_2.get("shader"), r"Shaders\interpolation\fsr.glsl")
            self.assertEqual(dd_2.get("adjmouse"), "true")
            self.assertEqual(dd_2.get("vsync"), "false")
            self.assertEqual(ei_2.get("hook_peekmessage"), "true")
            self.assertEqual(ln_2.get("gameresolution"), "800x600")
            self.assertEqual(ln_2.get("language"), "es")
            self.assertEqual(dd_2.get("configlang"), "spanish")

            # 3. Invalid mode, invalid lang, or switching lang when pack is missing returns non-zero
            for bad_args in (
                ["--mode", "invalid"],
                ["--lang", "fr"],
                ["--lang", "en"],
            ):
                p_bad = subprocess.run(
                    [str(launcher_exe), "--apply", "--dir", str(tmp_dir), *bad_args],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(p_bad.returncode, 0)

    def test_hd_launcher_language_pack_switching(self) -> None:
        launcher_exe = DIST_DIR / build_es.LAUNCHER_EXE_NAME
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            shutil.copy2(DIST_DIR / "ddraw.ini", tmp_dir / "ddraw.ini")
            shutil.copy2(DIST_DIR / "launcher.ini", tmp_dir / "launcher.ini")
            shutil.copytree(DIST_DIR / "lang", tmp_dir / "lang")
            for p in (tmp_dir / "lang" / "es").iterdir():
                shutil.copy2(p, tmp_dir / p.name)
            custom_save = tmp_dir / "save0099.res"
            custom_save.write_bytes(b"SAVE_TEST_OK")

            # 1. Switch game + launcher + cnc-ddraw configlang to English (Original)
            p_en = subprocess.run(
                [
                    str(launcher_exe),
                    "--apply",
                    "--dir", str(tmp_dir),
                    "--lang", "en",
                    "--game-res", "1024x768",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(p_en.returncode, 0, p_en.stderr or p_en.stdout)

            dd_en = _parse_ini_section((tmp_dir / "ddraw.ini").read_text("utf-8"), "ddraw")
            ln_en = _parse_ini_section((tmp_dir / "launcher.ini").read_text("utf-8"), "Launcher")
            self.assertEqual(dd_en.get("configlang"), "english")
            self.assertEqual(ln_en.get("language"), "en")
            self.assertEqual(ln_en.get("installedlanguage"), "en")
            self.assertEqual(ln_en.get("gameresolution"), "1024x768")

            for fname in ("Ei.exe", "Text.res", "Stdres.res", "Sound.res", "Help.txt", "Scen04.res"):
                self.assertEqual(
                    (tmp_dir / fname).read_bytes(),
                    (DIST_DIR / "lang" / "en" / fname).read_bytes(),
                    f"{fname} was not switched to English pack",
                )
            self.assertEqual(
                (tmp_dir / "lang" / "es" / "Text.res").read_bytes(),
                (DIST_DIR / "lang" / "es" / "Text.res").read_bytes(),
            )
            self.assertEqual(custom_save.read_bytes(), b"SAVE_TEST_OK")

            # 2. Switch back to Español (Latinoamérica)
            p_es = subprocess.run(
                [
                    str(launcher_exe),
                    "--apply",
                    "--dir", str(tmp_dir),
                    "--lang", "es",
                    "--game-res", "800x600",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(p_es.returncode, 0, p_es.stderr or p_es.stdout)

            dd_es = _parse_ini_section((tmp_dir / "ddraw.ini").read_text("utf-8"), "ddraw")
            ln_es = _parse_ini_section((tmp_dir / "launcher.ini").read_text("utf-8"), "Launcher")
            self.assertEqual(dd_es.get("configlang"), "spanish")
            self.assertEqual(ln_es.get("language"), "es")
            self.assertEqual(ln_es.get("installedlanguage"), "es")
            self.assertEqual(ln_es.get("gameresolution"), "800x600")

            for fname in ("Ei.exe", "Text.res", "Stdres.res", "Sound.res", "Help.txt", "Scen04.res"):
                self.assertEqual(
                    (tmp_dir / fname).read_bytes(),
                    (DIST_DIR / "lang" / "es" / fname).read_bytes(),
                    f"{fname} was not switched back to Spanish pack",
                )
            self.assertEqual(custom_save.read_bytes(), b"SAVE_TEST_OK")


def _parse_ini_section(text: str, target_section: str) -> dict[str, str]:
    section = ""
    out: dict[str, str] = {}
    want = target_section.lower()
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1].strip().lower()
            continue
        if section == want and s and not s.startswith(";") and "=" in line:
            k, _sep, v = line.partition("=")
            out[k.strip().lower()] = v.strip()
    return out


class DdrawConfigUnitTests(unittest.TestCase):
    def test_configure_cnc_ddraw_ini_updates_ddraw_only_and_guards_missing_key(self) -> None:
        sample = (
            "[ddraw]\r\n"
            "fullscreen=false\r\n"
            "windowed=false\r\n"
            "[Other]\r\n"
            "fullscreen=false\r\n"
            "[EI]\r\n"
            "hook_peekmessage=true\r\n"
        )
        patched = build_es.configure_cnc_ddraw_ini(sample, {"fullscreen": "true"})
        self.assertEqual(_parse_ini_section(patched, "ddraw")["fullscreen"], "true")
        self.assertEqual(_parse_ini_section(patched, "Other")["fullscreen"], "false")
        self.assertEqual(_parse_ini_section(patched, "EI")["hook_peekmessage"], "true")
        with self.assertRaises(ValueError):
            build_es.configure_cnc_ddraw_ini(sample, {"nonexistent_key": "1"})


if __name__ == "__main__":
    unittest.main()

