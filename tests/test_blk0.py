#!/usr/bin/env python3
"""Unit and integration tests for Enemy Infestation BLK0 parser, decoders, and world exporter."""

from __future__ import annotations

import os
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import blk0  # noqa: E402
import export_world  # noqa: E402
import save_tool  # noqa: E402


def _crc16_arc_bitloop(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc


def _encode_zrle(width: int, height: int, pixels: bytes, stride: int | None = None) -> bytes:
    """Encode an 8-bit indexed image using Ei.exe mode-2 ZRLE row format (0x00 transparent runs)."""
    stride = stride or width
    rows: list[bytes] = []
    for y in range(height):
        row = pixels[y * stride : y * stride + width]
        out = bytearray()
        x = 0
        while x < width:
            if row[x] == 0:
                run = 1
                while x + run < width and row[x + run] == 0 and run < 127:
                    run += 1
                out.append(run << 1)
                x += run
            else:
                run = 1
                while x + run < width and row[x + run] != 0 and run < 127:
                    run += 1
                out.append((run << 1) | 1)
                out.extend(row[x : x + run])
                x += run
        rows.append(bytes(out))

    table_size = height * 4
    offsets = []
    cursor = table_size
    for r in rows:
        offsets.append(cursor)
        cursor += len(r)
    return struct.pack(f"<{height}I", *offsets) + b"".join(rows)


class Crc16ArcTests(unittest.TestCase):
    def test_known_ei_exe_vectors(self) -> None:
        self.assertEqual(blk0.crc16_arc(b""), 0x0000)
        self.assertEqual(blk0.crc16_arc(b"123456789"), 0xBB3D)
        # Observed directly in Ei.exe CRC16 table initialization vector
        self.assertEqual(blk0.crc16_arc(b"SeRiAlNu"), 0xF201)

    def test_slicing8_matches_bitloop_random_lengths(self) -> None:
        rng = random.Random(1998)
        for length in list(range(0, 33)) + [64, 127, 255, 513, 1024]:
            sample = rng.randbytes(length)
            self.assertEqual(blk0.crc16_arc(sample), _crc16_arc_bitloop(sample))


class CbmpDecoderTests(unittest.TestCase):
    def test_raw_modes_0_and_1(self) -> None:
        pixels = bytes([0, 1, 2, 3, 4, 5])
        for mode in (0, 1):
            body = struct.pack("<4sIHHHHII", b"cbmp", len(pixels), 3, 2, mode, 8, 0, 0) + pixels
            img = blk0.decode_cbmp(body)
            self.assertEqual((img.width, img.height, img.mode), (3, 2, mode))
            self.assertEqual(img.pixels, pixels)

    def test_zrle_modes_2_and_3(self) -> None:
        w, h = 140, 3  # exercises runs > 127 and alternating literal/skip runs
        src = bytes([0] * 135 + [42, 43, 0, 99, 0] + [7] * 140 + [0, 5, 0, 0, 12] * 28)
        zrle = _encode_zrle(w, h, src)
        for mode in (2, 3):
            body = struct.pack("<4sIHHHHII", b"cbmp", len(zrle), w, h, mode, 8, 0, 0) + zrle
            img = blk0.decode_cbmp(body)
            self.assertEqual((img.width, img.height, img.mode), (w, h, mode))
            self.assertEqual(img.pixels, src)

    def test_pal0_and_to_image(self) -> None:
        pal_raw = bytes([(i * 3) % 256 for i in range(768)])
        pal = blk0.decode_pal0(pal_raw)
        self.assertEqual(len(pal), 256)
        raw_px = bytes([0, 1, 2, 3])
        body = struct.pack("<4sIHHHHII", b"cbmp", 4, 2, 2, 0, 8, 0, 0) + raw_px
        pil_img = blk0.decode_cbmp(body).to_image(pal)
        self.assertEqual(pil_img.mode, "P")
        self.assertEqual(pil_img.size, (2, 2))


class CbmpFontEncoderTests(unittest.TestCase):
    def test_encode_cbmp_all_modes_synthetic(self) -> None:
        w, h = 140, 3
        src = bytes([0] * 135 + [42, 43, 0, 99, 0] + [7] * 140 + [0, 5, 0, 0, 12] * 28)
        for mode in (0, 1, 2, 3):
            img = blk0.CbmpImage(w, h, mode, 8 if mode < 2 else 776, 0, 0, src)
            encoded = blk0.encode_cbmp(img)
            decoded = blk0.decode_cbmp(encoded)
            self.assertEqual(decoded, img)

    def test_encode_text_and_patch_cstr_cp1252(self) -> None:
        self.assertEqual(blk0.encode_text("¡Alerta, comandante!"), "¡Alerta, comandante!".encode("cp1252") + b"\x00")
        buf = bytearray(b"A" * 16)
        patched = blk0.patch_cstr(buf, 2, 8, "Ñoño")
        self.assertEqual(patched[:2], b"AA")
        self.assertEqual(patched[2:10], b"\xd1o\xf1o\x00\x00\x00\x00")
        self.assertEqual(patched[10:], b"AAAAAA")
        with self.assertRaises(ValueError):
            blk0.patch_cstr(buf, 0, 5, "12345")

    def test_real_stdres_cbmp_and_font_roundtrip(self) -> None:
        stdres = Path(r"C:\Program Files (x86)\Enemy Infestation\Stdres.res")
        if not stdres.exists():
            self.skipTest("Stdres.res not present")
        arc = blk0.Blk0Archive(stdres)
        cbmp_chunks = arc.find_chunks("cbmp")
        self.assertGreater(len(cbmp_chunks), 1000)
        for c in cbmp_chunks:
            img = blk0.decode_cbmp(c.body)
            re_body = blk0.encode_cbmp(img)
            img2 = blk0.decode_cbmp(re_body)
            self.assertEqual(img2, img, f"cbmp {c.chunk_id} mode={img.mode}")

        font_chunks = arc.find_chunks("font")
        self.assertEqual(len(font_chunks), 8)
        for c in font_chunks:
            f = blk0.decode_font(c.body)
            re_font = blk0.encode_font(
                f["cbmp_id"],
                f["default_spacing"],
                f["glyphs"],
                pad=f["pad"],
                min_slots=f["slot_count"],
            )
            # Zero-terminated prefix up to first NUL code matches exactly; unused trailing slots are 0 in Stdres too
            self.assertEqual(re_font, c.body, f"font {c.chunk_id} exact byte roundtrip failed")


class Blk0RoundtripTests(unittest.TestCase):
    def test_synthetic_archive_roundtrip_and_tamper_detection(self) -> None:
        pal_bytes = bytes(range(256)) * 3
        text_bytes = b"Mission Briefing\x00"
        scen_buf = bytearray(3640)
        struct.pack_into("<I", scen_buf, 0, 0)
        scen_buf[4:16] = b"Test Mission"
        scen_buf[44:47] = b"1.0"
        scen_buf[300:312] = b"Stay frosty."
        scen_buf[2348:2359] = b"Track01.wav"
        scen_buf[2364:2372] = b"Map1.res"
        struct.pack_into("<4H", scen_buf, 2380, 100, 200, 11, 12)

        goal_buf = bytearray(1330)
        struct.pack_into("<H", goal_buf, 0, 10)
        goal_buf[2:14] = b"Secure Airlk"
        struct.pack_into("<2H", goal_buf, 102, 5, 1)
        struct.pack_into("<3H", goal_buf, 110, 21, 1, 0)
        goal_buf[116:120] = b"RM40"
        struct.pack_into("<2H", goal_buf, 370, 39, 10)

        blob = blk0.build_blk0(
            [
                ("IDAT", 0, 0, 0, 0, b"pal0textscengoal"),
                ("pal0", 0, 1, 0, 2, pal_bytes),
                ("text", 1, 1, 0, 2, text_bytes),
                ("scen", 0, 1, 0, 2, bytes(scen_buf)),
                ("goal", 11, 1, 0, 2, bytes(goal_buf)),
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.res"
            p.write_bytes(blob)
            arc = blk0.Blk0Archive(p)
            self.assertEqual(arc.verify(), [])
            self.assertEqual(arc.idat_types(), ["pal0", "text", "scen", "goal"])
            self.assertEqual(blk0.decode_structured(arc.find_chunks("text", 1)[0]), "Mission Briefing")

            sc_dec = blk0.decode_structured(arc.find_chunks("scen")[0])
            self.assertEqual(sc_dec["title"], "Test Mission")
            self.assertEqual(sc_dec["version"], "1.0")
            self.assertEqual(sc_dec["music_track"], "Track01.wav")
            self.assertEqual(sc_dec["map_file"], "Map1.res")
            self.assertEqual(sc_dec["start_pos"], [100, 200])
            self.assertEqual(sc_dec["goal_ids"], [11, 12])

            gl_dec = blk0.decode_structured(arc.find_chunks("goal", 11)[0])
            self.assertEqual(gl_dec["flags"], 10)
            self.assertEqual(gl_dec["title"], "Secure Airlk")
            self.assertEqual(gl_dec["prereq_goal_id"], 5)
            self.assertEqual(gl_dec["cond_cmp"], "!=")
            self.assertEqual(gl_dec["cond_str"], "RM40")
            self.assertEqual(gl_dec["action_op"], 39)

            # Flip 1 byte in text payload -> CRC check must report mismatch
            tampered = bytearray(blob)
            text_chunk = arc.find_chunks("text", 1)[0]
            tampered[text_chunk.offset + 20] ^= 0xFF
            tp = Path(tmp) / "tampered.res"
            tp.write_bytes(bytes(tampered))
            errs = blk0.Blk0Archive(tp).verify()
            self.assertTrue(any("CRC mismatch on text id=1" in e for e in errs), errs)


GAME_DIR = Path(os.environ.get("EI_GAME_DIR", r"C:\Program Files (x86)\Enemy Infestation"))


@unittest.skipUnless(GAME_DIR.exists(), f"Enemy Infestation game dir not present at {GAME_DIR}")
class LiveGameArchiveTests(unittest.TestCase):
    def test_verify_key_archives_and_world_exporters(self) -> None:
        for name in ("Stdres.res", "Text.res", "Map1.res", "Scen00.res", "Scen01.res"):
            arc = blk0.Blk0Archive(GAME_DIR / name)
            self.assertEqual(arc.verify(), [], f"{name} verification failed")

        sc0 = blk0.decode_structured(blk0.Blk0Archive(GAME_DIR / "Scen00.res").find_chunks("scen")[0])
        self.assertEqual(len(sc0["goal_ids"]), 152)
        self.assertEqual(sc0["map_file"], "map7.res")

        db = export_world.export_database(GAME_DIR)
        self.assertGreaterEqual(len(db["tables"]["wtyp"]), 20)
        self.assertGreaterEqual(len(db["tables"]["patr"]), 20)

        txt = export_world.export_text_table(GAME_DIR)
        self.assertGreaterEqual(txt["count"], 200)

        scens = export_world.export_scenarios(GAME_DIR)
        self.assertEqual(scens["count"], 41)

        mdata, _arc = export_world._export_single_map(GAME_DIR / "Map1.res")
        self.assertEqual(len(mdata["rooms"]), 38)
        self.assertEqual(len(mdata["elevators"]), 3)

    def test_save_inspect_and_patch_roundtrip(self) -> None:
        save_src = GAME_DIR / "save0000.res"
        info = save_tool.inspect_save(save_src)
        self.assertEqual(info["verify_errors"], [])
        self.assertGreaterEqual(len(info["units"]), 10)
        self.assertEqual(info["units"][0]["actor_code"], "CO07")
        self.assertGreater(len(info["exits"]), 0)
        self.assertGreater(len(info["rooms"]), 0)
        self.assertEqual(info["chunk_counts"]["sgpl"], len(info["units"]))

        with tempfile.TemporaryDirectory() as tmp:
            patched = Path(tmp) / "save_patched.res"
            errs = save_tool.patch_save(
                save_src,
                patched,
                title="Patched Test Save",
                heal_colonists=True,
                goal_flags={18: 0x0101},
            )
            self.assertEqual(errs, [])
            after = save_tool.inspect_save(patched)
            self.assertEqual(after["sggm"]["title"], "Patched Test Save")
            for u in after["units"]:
                if u["actor_code"].startswith("CO") and u["hp"] > 0:
                    self.assertEqual(u["hp"], u["max_hp"])
            g18 = next(g for g in after["goals"] if g["goal_id"] == 18)
            self.assertEqual(g18["state_flags"], 0x0101)
            self.assertTrue(g18["active"])
            self.assertTrue(g18["triggered"])

    def test_auto_idat_and_lply_lwea_decoders(self) -> None:
        lply_buf = bytearray(70)
        struct.pack_into("<2H", lply_buf, 0, 23, 152)
        lply_buf[4:8] = b"RM10"
        struct.pack_into("<H", lply_buf, 8, 4)
        lply_buf[10:20] = b"Steve Hani"
        lply_buf[42:46] = b"COMM"
        struct.pack_into("<4H", lply_buf, 46, 26, 12181, 12301, 0)
        struct.pack_into("<H", lply_buf, 54, 100)
        lply_buf[66] = 0
        lply_buf[67] = 3
        struct.pack_into("<H", lply_buf, 68, 5)

        lwea_buf = bytearray(32)
        struct.pack_into("<H", lwea_buf, 0, 5)
        lwea_buf[2:6] = b"WP01"
        lwea_buf[6:10] = b"RM09"
        struct.pack_into("<2H", lwea_buf, 10, 84, 96)
        struct.pack_into("<H", lwea_buf, 22, 10)
        struct.pack_into("<2H", lwea_buf, 28, 1, 1)

        blob = blk0.build_blk0(
            [
                ("lply", 1, 1, 0, 2, bytes(lply_buf)),
                ("lwea", 1, 1, 0, 2, bytes(lwea_buf)),
            ],
            auto_idat=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "auto_idat.res"
            p.write_bytes(blob)
            arc = blk0.Blk0Archive(p)
            self.assertEqual(arc.verify(), [])
            self.assertEqual(arc.idat_types(), ["lply", "lwea"])
            self.assertEqual(arc.find_chunks("IDAT")[0].flags_or_count, 2)

            p_dec = blk0.decode_structured(arc.find_chunks("lply", 1)[0])
            self.assertEqual(p_dec["actor_code"], "COMM")
            self.assertEqual(p_dec["patr_id"], 26)
            self.assertEqual(p_dec["hp"], 100)
            self.assertTrue(p_dec["is_colonist"])
            self.assertTrue(p_dec["is_npc"])
            self.assertEqual(p_dec["slot68"], 5)

            w_dec = blk0.decode_structured(arc.find_chunks("lwea", 1)[0])
            self.assertEqual(w_dec["code"], "WP01")
            self.assertEqual(w_dec["effect_id"], 10)
            self.assertTrue(w_dec["active"])
            self.assertEqual(w_dec["flag30"], 1)

        scen1 = blk0.Blk0Archive(GAME_DIR / "Scen01.res")
        real_lply = blk0.decode_structured(scen1.find_chunks("lply")[0])
        self.assertIn("is_colonist", real_lply)
        self.assertIn("patr_id", real_lply)
        real_lwea = blk0.decode_structured(scen1.find_chunks("lwea")[0])
        self.assertIn("active", real_lwea)


if __name__ == "__main__":
    unittest.main()
