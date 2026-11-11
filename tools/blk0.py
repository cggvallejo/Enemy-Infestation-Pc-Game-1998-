"""BLK0 resource container inspector, verifier, and asset extractor for Enemy Infestation (1998)."""

from __future__ import annotations

import argparse
import dataclasses
import functools
import glob
import json
import os
import struct
import sys
import wave
from pathlib import Path
from typing import Iterable

from PIL import Image

CONTAINER_META_TAGS = frozenset({"IDAT", "DIR ", "END "})


def _make_crc16_arc_tables() -> tuple[list[int], ...]:
    t0: list[int] = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
        t0.append(crc)
    tables = [t0]
    for _ in range(7):
        prev = tables[-1]
        tables.append([(c >> 8) ^ t0[c & 0xFF] for c in prev])
    return tuple(tables)


_CRC16_T0, _CRC16_T1, _CRC16_T2, _CRC16_T3, _CRC16_T4, _CRC16_T5, _CRC16_T6, _CRC16_T7 = _make_crc16_arc_tables()


def crc16_arc(data: bytes) -> int:
    """Compute CRC-16/ARC (poly 0xA001 reflected, init 0) matching Ei.exe CRC16.C."""
    crc = 0
    t0, t1, t2, t3 = _CRC16_T0, _CRC16_T1, _CRC16_T2, _CRC16_T3
    t4, t5, t6, t7 = _CRC16_T4, _CRC16_T5, _CRC16_T6, _CRC16_T7
    n8 = len(data) // 8
    if n8:
        for w0, w1 in struct.iter_unpack("<II", memoryview(data)[: n8 * 8]):
            w0 ^= crc
            crc = (
                t7[w0 & 0xFF]
                ^ t6[(w0 >> 8) & 0xFF]
                ^ t5[(w0 >> 16) & 0xFF]
                ^ t4[w0 >> 24]
                ^ t3[w1 & 0xFF]
                ^ t2[(w1 >> 8) & 0xFF]
                ^ t1[(w1 >> 16) & 0xFF]
                ^ t0[w1 >> 24]
            )
    for b in data[n8 * 8 :]:
        crc = (crc >> 8) ^ t0[(crc ^ b) & 0xFF]
    return crc


def _cstr(data: bytes) -> str:
    raw = data.split(b"\x00", 1)[0]
    return raw.decode("cp1252", errors="replace")


@dataclasses.dataclass(frozen=True)
class Blk0Header:
    magic: bytes
    version: int
    dir_offset: int
    reserved0: int
    reserved1: int


@dataclasses.dataclass(frozen=True)
class DirEntry:
    tag: str
    chunk_id: int
    offset: int


@dataclasses.dataclass(frozen=True)
class Blk0Chunk:
    tag: str
    chunk_id: int
    offset: int
    payload_size: int
    flags_or_count: int
    reserved: int
    sub_id: int
    stored_crc: int | None
    body: bytes

    @functools.cached_property
    def computed_crc(self) -> int | None:
        if self.stored_crc is None:
            return None
        return crc16_arc(self.body)

    @property
    def crc_ok(self) -> bool:
        return self.stored_crc is None or self.stored_crc == self.computed_crc


@dataclasses.dataclass(frozen=True)
class CbmpImage:
    width: int
    height: int
    mode: int
    pixel_format: int
    field16: int
    field20: int
    pixels: bytes

    def to_image(self, palette_rgb: list[tuple[int, int, int]] | None = None) -> Image.Image:
        img = Image.frombytes("P", (self.width, self.height), self.pixels)
        if palette_rgb is not None:
            flat: list[int] = []
            for r, g, b in palette_rgb[:256]:
                flat.extend((r, g, b))
            if len(flat) < 768:
                flat.extend([0] * (768 - len(flat)))
            img.putpalette(flat)
        else:
            img = Image.frombytes("L", (self.width, self.height), self.pixels)
        return img


class Blk0Archive:
    """Reader and validator for Enemy Infestation BLK0 .res archives."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._data = self.path.read_bytes()
        if len(self._data) < 32:
            raise ValueError(f"{self.path}: file too small ({len(self._data)} bytes)")
        magic, ver, dir_off, r0, r1 = struct.unpack_from("<4sHIHI", self._data, 0)
        if magic != b"BLK0":
            raise ValueError(f"{self.path}: bad magic {magic!r}")
        self.header = Blk0Header(magic, ver, dir_off, r0, r1)
        self.dir_entries: list[DirEntry] = []
        self.chunks: list[Blk0Chunk] = []
        self.end_header: tuple[str, int, int, int, int] | None = None
        self._parse()

    def _parse(self) -> None:
        d = self._data
        off = self.header.dir_offset
        if off + 16 > len(d):
            raise ValueError(f"{self.path}: dir_offset {off} out of bounds")
        dtag_b, dsize, did, dcnt, dres = struct.unpack_from("<4sIHHI", d, off)
        dtag = dtag_b.decode("ascii", errors="replace")
        if dtag != "DIR ":
            raise ValueError(f"{self.path}: expected 'DIR ' at {off:#x}, got {dtag!r}")
        if dcnt * 10 != dsize:
            raise ValueError(f"{self.path}: DIR count {dcnt}*10 != size {dsize}")
        if off + 16 + dsize > len(d):
            raise ValueError(f"{self.path}: truncated DIR table")

        for i in range(dcnt):
            t_b, cid, coff = struct.unpack_from("<4sHI", d, off + 16 + i * 10)
            entry = DirEntry(t_b.decode("ascii", errors="replace"), cid, coff)
            self.dir_entries.append(entry)
            self.chunks.append(self._read_chunk(coff))

        end_off = off + 16 + dsize
        if end_off + 16 <= len(d):
            et, esz, eid, efc, eres = struct.unpack_from("<4sIHHI", d, end_off)
            self.end_header = (et.decode("ascii", errors="replace"), esz, eid, efc, eres)

    def _read_chunk(self, offset: int) -> Blk0Chunk:
        d = self._data
        if offset + 16 > len(d):
            raise ValueError(f"{self.path}: chunk offset {offset:#x} out of bounds")
        ctag_b, psize, cid, fc, res = struct.unpack_from("<4sIHHI", d, offset)
        ctag = ctag_b.decode("ascii", errors="replace")
        if offset + 16 + psize > len(d):
            raise ValueError(f"{self.path}: chunk {ctag}:{cid} exceeds EOF")
        payload = d[offset + 16 : offset + 16 + psize]
        if ctag not in CONTAINER_META_TAGS and len(payload) >= 4:
            sub_id, stored_crc = struct.unpack_from("<HH", payload, 0)
            body = payload[4:]
        else:
            sub_id, stored_crc = 0, None
            body = payload
        return Blk0Chunk(
            tag=ctag,
            chunk_id=cid,
            offset=offset,
            payload_size=psize,
            flags_or_count=fc,
            reserved=res,
            sub_id=sub_id,
            stored_crc=stored_crc,
            body=body,
        )

    def verify(self) -> list[str]:
        """Return a list of integrity errors (empty when valid)."""
        errors: list[str] = []
        if self.header.version != 10:
            errors.append(f"unexpected BLK0 version {self.header.version}")
        if self.end_header is None or self.end_header[0] != "END ":
            errors.append(f"missing END chunk after DIR: {self.end_header!r}")
        for entry, chunk in zip(self.dir_entries, self.chunks):
            if entry.tag != chunk.tag or entry.chunk_id != chunk.chunk_id:
                errors.append(
                    f"DIR mismatch at {entry.offset:#x}: dir=({entry.tag},{entry.chunk_id}) "
                    f"hdr=({chunk.tag},{chunk.chunk_id})"
                )
            if not chunk.crc_ok:
                errors.append(
                    f"CRC mismatch on {chunk.tag} id={chunk.chunk_id}: "
                    f"stored={chunk.stored_crc:#06x} computed={chunk.computed_crc:#06x}"
                )
        return errors

    def find_chunks(self, tag: str | None = None, chunk_id: int | None = None) -> list[Blk0Chunk]:
        return [
            c
            for c in self.chunks
            if (tag is None or c.tag == tag) and (chunk_id is None or c.chunk_id == chunk_id)
        ]

    def idat_types(self) -> list[str]:
        idat = self.find_chunks("IDAT")
        if not idat:
            return []
        body = idat[0].body
        return [body[i : i + 4].decode("ascii", errors="replace") for i in range(0, len(body), 4)]


ChunkSpec = Blk0Chunk | tuple[str, int, int, int, int, bytes]


def build_blk0(chunks: Iterable[ChunkSpec], *, auto_idat: bool = False) -> bytes:
    """Serialize chunks into a valid BLK0 v10 archive with CRC-16/ARC checksums, DIR, and END."""
    normalized: list[tuple[str, int, int, int, int, bytes]] = []
    has_idat = False
    seen_tags: list[str] = []

    for item in chunks:
        if isinstance(item, Blk0Chunk):
            tag = item.tag
            spec = (tag, item.chunk_id, item.flags_or_count, item.reserved, item.sub_id, item.body)
        else:
            spec = item
            tag = spec[0]
        if tag in ("DIR ", "END "):
            continue
        if tag == "IDAT":
            has_idat = True
        elif tag not in seen_tags:
            seen_tags.append(tag)
        normalized.append(spec)

    if auto_idat and not has_idat:
        idat_body = b"".join(t.encode("ascii") for t in seen_tags)
        normalized.insert(0, ("IDAT", 0, len(seen_tags), 0, 0, idat_body))

    buf = bytearray(b"BLK0" + struct.pack("<HIHI", 10, 0, 0, 0))
    dir_entries: list[tuple[bytes, int, int]] = []

    for tag, cid, fc, res, sub_id, body in normalized:
        tag_b = tag.encode("ascii")
        if len(tag_b) != 4:
            raise ValueError(f"Chunk tag must be 4 ASCII chars, got {tag!r}")
        offset = len(buf)
        dir_entries.append((tag_b, cid, offset))
        if tag in CONTAINER_META_TAGS:
            payload = body
        else:
            payload = struct.pack("<HH", sub_id, crc16_arc(body)) + body
        buf.extend(struct.pack("<4sIHHI", tag_b, len(payload), cid, fc, res))
        buf.extend(payload)

    dir_off = len(buf)
    struct.pack_into("<I", buf, 6, dir_off)
    buf.extend(struct.pack("<4sIHHI", b"DIR ", len(dir_entries) * 10, 0, len(dir_entries), 0))
    for tag_b, cid, coff in dir_entries:
        buf.extend(struct.pack("<4sHI", tag_b, cid, coff))
    buf.extend(struct.pack("<4sIHHI", b"END ", 0, 0, 0, 0))
    return bytes(buf)


def decode_pal0(body: bytes) -> list[tuple[int, int, int]]:
    if len(body) < 768:
        raise ValueError(f"pal0 too short: {len(body)}")
    return [(body[i * 3], body[i * 3 + 1], body[i * 3 + 2]) for i in range(256)]


def decode_cbmp(body: bytes) -> CbmpImage:
    if len(body) < 24:
        raise ValueError(f"cbmp too short: {len(body)}")
    magic, data_size, w, h, mode, fmt, f16, f20 = struct.unpack_from("<4sIHHHHII", body, 0)
    if magic != b"cbmp":
        raise ValueError(f"bad cbmp magic {magic!r}")
    data = body[24:]
    if len(data) != data_size:
        raise ValueError(f"cbmp data_size {data_size} != body tail {len(data)}")
    if mode in (0, 1):
        if len(data) != w * h:
            raise ValueError(f"raw cbmp len {len(data)} != {w}*{h}")
        pixels = data
    elif mode in (2, 3):
        if len(data) < h * 4:
            raise ValueError(f"zrle row table truncated ({len(data)} < {h * 4})")
        offs = struct.unpack_from(f"<{h}I", data, 0)
        out = bytearray(w * h)
        for y in range(h):
            p = offs[y]
            x = 0
            while x < w:
                op = data[p]
                p += 1
                cnt = op >> 1
                if op & 1:
                    out[y * w + x : y * w + x + cnt] = data[p : p + cnt]
                    p += cnt
                x += cnt
            if x != w:
                raise ValueError(f"zrle row {y} decoded {x} px, expected {w}")
        pixels = bytes(out)
    else:
        raise ValueError(f"unsupported cbmp mode {mode}")
    return CbmpImage(w, h, mode, fmt, f16, f20, pixels)


def encode_cbmp(img: CbmpImage) -> bytes:
    """Encode a CbmpImage back into BLK0 'cbmp' chunk bytes (modes 0, 1, 2, 3)."""
    w, h, mode = img.width, img.height, img.mode
    if len(img.pixels) != w * h:
        raise ValueError(f"cbmp pixels len {len(img.pixels)} != {w}*{h}")
    if mode in (0, 1):
        data = bytes(img.pixels)
    elif mode in (2, 3):
        rows: list[bytes] = []
        px = img.pixels
        for y in range(h):
            row = px[y * w : (y + 1) * w]
            out = bytearray()
            x = 0
            while x < w:
                if row[x] == 0:
                    run = 1
                    while x + run < w and row[x + run] == 0 and run < 127:
                        run += 1
                    out.append(run << 1)
                    x += run
                else:
                    run = 1
                    while x + run < w and row[x + run] != 0 and run < 127:
                        run += 1
                    out.append((run << 1) | 1)
                    out.extend(row[x : x + run])
                    x += run
            rows.append(bytes(out))
        offsets: list[int] = []
        cursor = h * 4
        for r in rows:
            offsets.append(cursor)
            cursor += len(r)
        data = struct.pack(f"<{h}I", *offsets) + b"".join(rows)
    else:
        raise ValueError(f"unsupported cbmp mode {mode}")
    hdr = struct.pack("<4sIHHHHII", b"cbmp", len(data), w, h, mode, img.pixel_format, img.field16, img.field20)
    return hdr + data


def decode_font(body: bytes) -> dict:
    """Decode BITFONT chunk (<HBB header + zero-terminated <BBHHHH glyph records)."""
    if len(body) < 4:
        raise ValueError(f"font chunk too short: {len(body)}")
    cbmp_id, default_spacing, pad = struct.unpack_from("<HBB", body, 0)
    slot_count = (len(body) - 4) // 10
    glyphs: list[dict[str, int]] = []
    for i in range(slot_count):
        code, advance, x, y, w, h = struct.unpack_from("<BBHHHH", body, 4 + i * 10)
        if code == 0:
            break
        glyphs.append({"code": code, "advance": advance, "x": x, "y": y, "w": w, "h": h})
    return {
        "cbmp_id": cbmp_id,
        "default_spacing": default_spacing,
        "pad": pad,
        "slot_count": slot_count,
        "glyphs": glyphs,
    }


def encode_font(
    cbmp_id: int,
    default_spacing: int,
    glyphs: list[dict[str, int]],
    *,
    pad: int = 0,
    min_slots: int = 0,
) -> bytes:
    """Encode a BITFONT chunk preserving the zero-terminated fixed-slot table."""
    seen: set[int] = set()
    for g in glyphs:
        c = int(g["code"])
        if not (1 <= c <= 255):
            raise ValueError(f"invalid font glyph code {c}")
        if c in seen:
            raise ValueError(f"duplicate font glyph code {c}")
        seen.add(c)
    slots = max(min_slots, len(glyphs) + 1)
    buf = bytearray(4 + slots * 10)
    struct.pack_into("<HBB", buf, 0, cbmp_id, default_spacing, pad)
    for i, g in enumerate(glyphs):
        struct.pack_into(
            "<BBHHHH",
            buf,
            4 + i * 10,
            int(g["code"]),
            int(g["advance"]),
            int(g["x"]),
            int(g["y"]),
            int(g["w"]),
            int(g["h"]),
        )
    return bytes(buf)


def encode_text(text: str, encoding: str = "cp1252") -> bytes:
    """Encode a NUL-terminated text chunk string."""
    return text.encode(encoding) + b"\x00"


def patch_cstr(buf: bytearray | bytes, offset: int, size: int, text: str, encoding: str = "cp1252") -> bytes:
    """Write a NUL-terminated string into a fixed-size structured field, failing if too long."""
    raw = text.encode(encoding)
    if len(raw) >= size:
        raise ValueError(f"string {text!r} ({len(raw)}B) exceeds fixed {size - 1}B slot at offset {offset}")
    out = bytearray(buf)
    out[offset : offset + size] = b"\x00" * size
    out[offset : offset + len(raw)] = raw
    return bytes(out)


def write_wav_pcm8(path: Path, pcm: bytes, sample_rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def decode_structured(chunk: Blk0Chunk) -> dict | str | None:
    """Decode known structured/text BLK0 chunk bodies into JSON-friendly Python values."""
    t = chunk.tag
    b = chunk.body
    if t == "IDAT":
        return [b[i : i + 4].decode("ascii", errors="replace") for i in range(0, len(b), 4)]
    if t == "text":
        return _cstr(b)
    if t == "digs":
        return b.rstrip(b"\x00").decode("cp1252", errors="replace")
    if t == "pal0":
        return {"colors": decode_pal0(b)}
    if t == "font" and len(b) >= 4:
        return decode_font(b)
    if t == "sprt" and len(b) >= 10:
        x, y, z, sseq_id, count = struct.unpack_from("<5h", b, 0)
        return {"x": x, "y": y, "z": z, "sseq_id": sseq_id, "count": count}
    if t == "sseq" and len(b) >= 22:
        hdr = struct.unpack_from("<11H", b, 0)
        raw_ops = b[22:]
        frames = list(raw_ops.split(b"\xff", 1)[0])
        return {
            "cbmp_id": hdr[0],
            "unk1": hdr[1],
            "delay_ms": hdr[2],
            "unk3": hdr[3],
            "unk4": hdr[4],
            "frame_w": hdr[5],
            "frame_h": hdr[6],
            "hotspot_x": hdr[7],
            "hotspot_y": hdr[8],
            "unk9": hdr[9],
            "unk10": hdr[10],
            "frames": frames,
            "ops": list(raw_ops),
        }
    if t == "mapd" and len(b) >= 80:
        w, h, gw, gh = struct.unpack_from("<4H", b, 0)
        return {"width_px": w, "height_px": h, "grid_w": gw, "grid_h": gh, "name": _cstr(b[8:40]), "base": _cstr(b[40:80])}
    if t == "room" and len(b) >= 42:
        code = _cstr(b[0:4])
        name = _cstr(b[4:36])
        nv, x0, y0 = struct.unpack_from("<Hhh", b, 36)
        pts = []
        max_pts = min(max(nv - 1, 0), (len(b) - 42) // 4)
        for i in range(max_pts):
            dx, dy = struct.unpack_from("<hh", b, 42 + i * 4)
            pts.append([x0 + dx, y0 + dy])
        return {"code": code, "name": name, "n_verts": nv, "origin": [x0, y0], "points": pts}
    if t == "roof" and len(b) >= 16:
        layers = list(struct.unpack_from("<6H", b, 0))
        x, y = struct.unpack_from("<2H", b, 12)
        return {"cbmp_layers": layers, "x": x, "y": y}
    if t == "door" and len(b) >= 16:
        vals = struct.unpack_from("<8H", b, 0)
        return {"raw_u16": list(vals), "x": vals[5], "y": vals[6], "door_id": vals[7]}
    if t == "elev" and len(b) >= 6:
        id0, id1, nfl = struct.unpack_from("<3H", b, 0)
        floors = []
        for i in range(min(nfl, (len(b) - 6) // 12)):
            rm = _cstr(b[6 + i * 12 : 10 + i * 12])
            tx, ty, px, py = struct.unpack_from("<4H", b, 10 + i * 12)
            if rm:
                floors.append({"room": rm, "tile": [tx, ty], "px": [px, py]})
        return {"id0": id0, "id1": id1, "floors": floors}
    if t == "exit" and len(b) >= 20:
        tx1, ty1 = struct.unpack_from("<2H", b, 8)
        tx2, ty2 = struct.unpack_from("<2H", b, 16)
        return {"code": _cstr(b[0:4]), "room1": _cstr(b[4:8]), "tile1": [tx1, ty1], "room2": _cstr(b[12:16]), "tile2": [tx2, ty2]}
    if t == "rmsk":
        return {"height": len(b), "depth_rows": list(struct.unpack(f"<{len(b)}b", b))}
    if t == "load" and len(b) >= 6:
        cbmp_id, x, y = struct.unpack_from("<3H", b, 0)
        return {"cbmp_id": cbmp_id, "x": x, "y": y}
    if t == "weft" and len(b) >= 34:
        return {"u16_0": struct.unpack_from("<H", b, 0)[0], "name": _cstr(b[2:34])}
    if t == "mind" and len(b) >= 62:
        tokens = [_cstr(b[i : i + 6]) for i in range(2, len(b) - 5, 6)]
        return {"u16_0": struct.unpack_from("<H", b, 0)[0], "states": [x for x in tokens if x]}
    if t == "scen" and len(b) >= 48:
        kind = struct.unpack_from("<I", b, 0)[0]
        if len(b) >= 2384:
            sx, sy = struct.unpack_from("<2H", b, 2380)
            goal_ids: list[int] = []
            for off in range(2384, len(b) - 1, 2):
                gid = struct.unpack_from("<H", b, off)[0]
                if gid == 0:
                    break
                goal_ids.append(gid)
            return {
                "kind": kind,
                "title": _cstr(b[4:44]),
                "version": _cstr(b[44:64]),
                "briefing": _cstr(b[300:2348]),
                "music_track": _cstr(b[2348:2364]),
                "map_file": _cstr(b[2364:2380]),
                "start_pos": [sx, sy],
                "goal_ids": goal_ids,
            }
        return {"kind": kind, "title": _cstr(b[4:44]), "version": _cstr(b[44:64])}
    if t == "lply" and len(b) >= 50:
        tx, ty = struct.unpack_from("<2H", b, 0)
        patr_id, voice_base, voice_alt = struct.unpack_from("<3H", b, 46)
        out_lply: dict[str, object] = {
            "tile": [tx, ty],
            "room": _cstr(b[4:8]),
            "unk8": struct.unpack_from("<H", b, 8)[0],
            "name": _cstr(b[10:42]),
            "actor_code": _cstr(b[42:46]),
            "patr_id": patr_id,
            "voice_base": voice_base,
            "voice_alt": voice_alt,
        }
        if len(b) >= 70:
            flags67 = b[67]
            out_lply.update(
                {
                    "hp": struct.unpack_from("<H", b, 54)[0],
                    "extra_i16": list(struct.unpack_from("<5h", b, 56)),
                    "flags66": b[66],
                    "flags67": flags67,
                    "is_colonist": bool(flags67 & 1),
                    "is_npc": bool(flags67 & 2),
                    "slot68": struct.unpack_from("<H", b, 68)[0],
                }
            )
        return out_lply
    if t == "lwea" and len(b) >= 14:
        wtype = struct.unpack_from("<H", b, 0)[0]
        tx, ty = struct.unpack_from("<2H", b, 10)
        out_lwea: dict[str, object] = {
            "weapon_type": wtype,
            "code": _cstr(b[2:6]),
            "room": _cstr(b[6:10]),
            "tile": [tx, ty],
        }
        if len(b) >= 32:
            tail_u16 = list(struct.unpack_from("<9H", b, 14))
            out_lwea.update(
                {
                    "effect_id": tail_u16[4],
                    "tail_u16": tail_u16,
                    "active": bool(tail_u16[7]),
                    "flag30": tail_u16[8],
                }
            )
        return out_lwea
    if t == "goal" and len(b) >= 66:
        flags = struct.unpack_from("<H", b, 0)[0]
        out: dict[str, object] = {"flags": flags, "title": _cstr(b[2:66])}
        if len(b) >= 380:
            prereq_id, prereq_state = struct.unpack_from("<2H", b, 102)
            cond_op, cond_flag, cond_param, cond_val = struct.unpack_from("<4H", b, 110)
            action_op, action_arg = struct.unpack_from("<2H", b, 370)
            raw_cs = _cstr(b[116:148])
            cond_str = raw_cs if (len(raw_cs) >= 2 and all(32 <= ord(c) < 127 for c in raw_cs)) else ""
            cond_cmp = {0: "==", 1: "!=", 2: ">", 3: "<"}.get(cond_flag, str(cond_flag))
            out.update(
                {
                    "prereq_goal_id": prereq_id,
                    "prereq_state": prereq_state,
                    "cond_op": cond_op,
                    "cond_flag": cond_flag,
                    "cond_cmp": cond_cmp,
                    "cond_param": cond_param,
                    "cond_val": cond_val,
                    "cond_str": cond_str,
                    "action_op": action_op,
                    "action_arg": action_arg,
                }
            )
        return out
    if t == "wtyp" and len(b) >= 68:
        w = struct.unpack_from("<18h", b, 32)
        return {
            "name": _cstr(b[0:32]),
            "kind": w[0],
            "icon_cbmp": w[1],
            "icon2_cbmp": w[2],
            "hud_cbmp": w[3],
            "sfx_id": w[13],
            "raw_i16": list(w),
        }
    if t == "patr" and len(b) >= 88:
        u0 = struct.unpack_from("<H", b, 0)[0]
        w = struct.unpack_from("<27h", b, 34)
        return {
            "is_alien": bool(u0),
            "name": _cstr(b[2:34]),
            "base_id": w[0],
            "portrait_base": w[15],
            "dims": [w[18], w[19]],
            "raw_i16": list(w),
        }
    if t == "pobj" and len(b) >= 172:
        u32, u34 = struct.unpack_from("<HH", b, 32)
        w = struct.unpack_from("<14h", b, 116)
        return {
            "name": _cstr(b[0:32]),
            "u32": u32,
            "u34": u34,
            "desc": _cstr(b[36:116]),
            "size_px": [w[3], w[4]],
            "raw_i16": list(w),
        }
    if t == "lpob" and len(b) >= 76:
        pobj_id = struct.unpack_from("<H", b, 0)[0]
        flags, x, y = struct.unpack_from("<3H", b, 6)
        tail = list(struct.unpack_from("<32h", b, 12))
        return {
            "pobj_id": pobj_id,
            "code": _cstr(b[2:6]),
            "flags": flags,
            "pos": [x, y],
            "tail_i16": tail,
        }
    if t == "view" and len(b) >= 296:
        w = struct.unpack_from("<16h", b, 196)
        return {
            "name": _cstr(b[0:32]),
            "sub": _cstr(b[32:64]),
            "class_name": _cstr(b[64:116]),
            "tooltip": _cstr(b[116:196]),
            "rect": [w[0], w[1], w[2], w[3]],
            "cbmp_id": w[8],
            "raw_i16": list(w),
        }
    if t == "sgex" and len(b) >= 10:
        return {"code": _cstr(b[0:4]), "raw_u16": list(struct.unpack_from("<3H", b, 4))}
    if t == "sgrm" and len(b) >= 18:
        return {"code": _cstr(b[0:4]), "raw_u16": list(struct.unpack_from("<7H", b, 4))}
    if t == "clut" and len(b) >= 256:
        return {"tables_256": len(b) // 256, "size": len(b), "first_256": list(b[:256])}
    if t == "alie" and len(b) >= 26:
        return {"values_u16": list(struct.unpack_from("<13H", b, 0))}
    if t == "sgpl" and len(b) >= 254:
        hp, max_hp = struct.unpack_from("<2H", b, 80)
        patr_id = struct.unpack_from("<H", b, 124)[0]
        voice_base = struct.unpack_from("<H", b, 154)[0]
        tx, ty = struct.unpack_from("<2H", b, 182)
        return {
            "name": _cstr(b[0:32]),
            "actor_code": _cstr(b[32:36]),
            "tag": _cstr(b[36:40]),
            "weapon_code": _cstr(b[48:52]),
            "hp": hp,
            "max_hp": max_hp,
            "role": _cstr(b[92:124]),
            "patr_id": patr_id,
            "voice_base": voice_base,
            "room": _cstr(b[178:182]),
            "tile": [tx, ty],
        }
    if t == "sgwp" and len(b) >= 62:
        return {
            "code": _cstr(b[0:4]),
            "room": _cstr(b[4:8]),
            "owner": _cstr(b[22:26]),
            "raw_i16": list(struct.unpack_from("<7h", b, 8)),
        }
    if t == "sgpo" and len(b) >= 442:
        return {
            "code": _cstr(b[0:4]),
            "u16_vals": list(struct.unpack_from("<5H", b, 4)),
            "rooms": [x for x in (_cstr(b[14:18]), _cstr(b[24:28]), _cstr(b[28:32])) if x],
        }
    if t == "sgmd" and len(b) >= 606:
        code = _cstr(b[0:4])
        count = struct.unpack_from("<H", b, 4)[0]
        slots = []
        for off in range(6, len(b) - 29, 30):
            sname = _cstr(b[off : off + 4])
            if sname:
                target = _cstr(b[off + 8 : off + 12])
                entity = _cstr(b[off + 12 : off + 16])
                slots.append({"state": sname, "target": target, "entity": entity})
        return {"code": code, "count": count, "slots": slots}
    if t == "sggl" and len(b) >= 332:
        gid, gflags, a0, a1 = struct.unpack_from("<4H", b, 0)
        return {
            "goal_id": gid,
            "state_flags": gflags,
            "active": bool(gflags & 0x01),
            "triggered": bool(gflags & 0x0100),
            "raw_u16": [gid, gflags, a0, a1],
        }
    if t == "sggm" and len(b) >= 0x990:
        logs = []
        for off in range(0x940, min(len(b), 0x15C0) - 0x4F, 0x50):
            entry = _cstr(b[off : off + 0x50])
            if not entry:
                break
            logs.append(entry)
        return {"title": _cstr(b[0xCE:0x130]), "log_entries": logs}
    return None


def _resolve_palette(arc: Blk0Archive, pal_spec: str | None) -> list[tuple[int, int, int]] | None:
    if pal_spec:
        if ":" in pal_spec:
            pfile, pid_s = pal_spec.rsplit(":", 1)
            pid: int | None = int(pid_s)
        else:
            pfile, pid = pal_spec, None
        pal_arc = Blk0Archive(pfile)
        matches = pal_arc.find_chunks("pal0", pid)
        if not matches:
            raise ValueError(f"Palette pal0:{pid} not found in {pfile}")
        return decode_pal0(matches[0].body)
    pals = arc.find_chunks("pal0")
    if pals:
        return decode_pal0(pals[0].body)
    stdres_candidate = arc.path.parent / "Stdres.res"
    if stdres_candidate.exists():
        std = Blk0Archive(stdres_candidate)
        m = std.find_chunks("pal0", 6001) or std.find_chunks("pal0")
        if m:
            return decode_pal0(m[0].body)
    return None


def _expand_paths(patterns: Iterable[str]) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            out.extend(Path(h) for h in hits)
        else:
            out.append(Path(pat))
    return out


def cmd_verify(args: argparse.Namespace) -> int:
    paths = _expand_paths(args.paths)
    total_chunks = 0
    total_errors = 0
    for p in paths:
        arc = Blk0Archive(p)
        errs = arc.verify()
        total_chunks += len(arc.chunks)
        total_errors += len(errs)
        status = "OK" if not errs else f"FAIL ({len(errs)} errors)"
        print(f"{p.name}: ver={arc.header.version} chunks={len(arc.chunks)} types={arc.idat_types()} -> {status}")
        for e in errs:
            print(f"  ERROR: {e}")
    print(f"Total files: {len(paths)}, total chunks: {total_chunks}, errors: {total_errors}")
    return 1 if total_errors else 0


def cmd_list(args: argparse.Namespace) -> int:
    arc = Blk0Archive(args.path)
    print(f"File: {arc.path} | ver={arc.header.version} dir={arc.header.dir_offset:#x} chunks={len(arc.chunks)}")
    print(f"IDAT types: {arc.idat_types()}")
    if args.tag:
        for c in arc.find_chunks(args.tag):
            print(f"  {c.tag} id={c.chunk_id:5d} sub={c.sub_id} fc={c.flags_or_count:3d} len={len(c.body):7d} crc_ok={c.crc_ok}")
    else:
        counts: dict[str, int] = {}
        for c in arc.chunks:
            counts[c.tag] = counts.get(c.tag, 0) + 1
        for k, v in sorted(counts.items()):
            print(f"  {k:4s}: {v}")
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    arc = Blk0Archive(args.path)
    for c in arc.find_chunks(args.tag, args.id):
        dec = decode_structured(c) if args.decode else None
        rec = {
            "tag": c.tag,
            "id": c.chunk_id,
            "sub_id": c.sub_id,
            "flags_or_count": c.flags_or_count,
            "body_len": len(c.body),
            "crc_ok": c.crc_ok,
            "decoded": dec if dec is not None else c.body[:64].hex(),
        }
        print(json.dumps(rec, ensure_ascii=False))
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    arc = Blk0Archive(args.path)
    out_root = Path(args.outdir)
    out_root.mkdir(parents=True, exist_ok=True)
    pal = _resolve_palette(arc, args.pal)
    chunks = arc.find_chunks(args.tag, args.id)
    count = 0
    for c in chunks:
        tag_dir = out_root / c.tag.strip()
        tag_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{c.chunk_id:05d}_sub{c.sub_id}"
        if args.raw:
            (tag_dir / f"{stem}.bin").write_bytes(c.body)
        if args.decode:
            if c.tag == "cbmp":
                cbmp = decode_cbmp(c.body)
                img = cbmp.to_image(pal)
                img.save(tag_dir / f"{stem}.png")
                if args.split_frames and cbmp.mode in (1, 3) and cbmp.field16 > 1 and cbmp.height % cbmp.field16 == 0:
                    frame_h = cbmp.height // cbmp.field16
                    for fi in range(cbmp.field16):
                        crop = img.crop((0, fi * frame_h, cbmp.width, (fi + 1) * frame_h))
                        crop.save(tag_dir / f"{stem}_f{fi:02d}.png")
            elif c.tag == "snd8":
                write_wav_pcm8(tag_dir / f"{stem}.wav", c.body, args.sample_rate)
            elif c.tag == "digs":
                (tag_dir / f"{stem}.dig").write_text(_cstr(c.body + b"\x00"), encoding="utf-8")
            elif c.tag == "text":
                (tag_dir / f"{stem}.txt").write_text(_cstr(c.body), encoding="utf-8")
            else:
                dec = decode_structured(c)
                if dec is not None:
                    (tag_dir / f"{stem}.json").write_text(json.dumps(dec, indent=2, ensure_ascii=False), encoding="utf-8")
                elif not args.raw:
                    (tag_dir / f"{stem}.bin").write_bytes(c.body)
        count += 1
    print(f"Extracted {count} chunk(s) from {arc.path.name} -> {out_root}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Enemy Infestation BLK0 resource tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("verify", help="Verify BLK0 structure and CRC-16/ARC checksums")
    pv.add_argument("paths", nargs="+", help=".res files or glob patterns")
    pv.set_defaults(func=cmd_verify)

    pl = sub.add_parser("list", help="List chunk summary or entries in a .res file")
    pl.add_argument("path")
    pl.add_argument("--tag", help="Filter by 4-char chunk tag")
    pl.set_defaults(func=cmd_list)

    pd = sub.add_parser("dump", help="Dump chunks as JSON lines")
    pd.add_argument("path")
    pd.add_argument("--tag", help="Filter by 4-char chunk tag")
    pd.add_argument("--id", type=int, help="Filter by chunk ID")
    pd.add_argument("--decode", action="store_true", help="Decode known structured chunk types")
    pd.set_defaults(func=cmd_dump)

    pe = sub.add_parser("extract", help="Extract chunks and decoded assets from a .res file")
    pe.add_argument("path")
    pe.add_argument("-o", "--outdir", required=True)
    pe.add_argument("--tag", help="Filter by 4-char chunk tag")
    pe.add_argument("--id", type=int, help="Filter by chunk ID")
    pe.add_argument("--pal", help="Palette spec: path.res[:chunk_id]")
    pe.add_argument("--raw", action="store_true", help="Write raw .bin chunk bodies")
    pe.add_argument("--decode", action="store_true", help="Export PNG/WAV/DIG/TXT/JSON where supported")
    pe.add_argument("--split-frames", action="store_true", help="Split mode 1/3 cbmp strips into per-frame PNGs")
    pe.add_argument("--sample-rate", type=int, default=22050, help="WAV sample rate for snd8 (default 22050)")
    pe.set_defaults(func=cmd_extract)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
