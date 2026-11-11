"""Text, struct-string, documentation, and Ei.exe localization validator and patcher."""

from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path
from typing import Any

import blk0

PRINTF_RE = re.compile(r"%(?:\d+(?:\.\d+)?)?[sdcxXf]")

TEXT_RES_STRUCTURAL_WS = {
    2000: ("", " "),    # "Number uses left: "
    8039: (". ", ""),   # ". Right click info"
    9031: (" ", ""),    # " - anyone at all"
    9033: (" ", " "),   # " and "
    11042: ("", " "),   # "Alien "
}

EI_EXE_STRUCTURAL_WS = {
    "0x05b088": ("", " "),   # "episode "
    "0x05c697": ("", " "),   # "Application Error: "
    "0x05c6ab": ("\n\n", ""),  # "\n\nClick on OK to terminate the application"
}


def printf_specs(s: str) -> list[str]:
    return PRINTF_RE.findall(s)


def _check_entry(
    issues: list[str],
    ctx: str,
    en: str,
    es: str,
    max_bytes: int | None = None,
    *,
    allow_empty: bool = False,
    req_ws: tuple[str, str] | None = None,
) -> None:
    if not en:
        if es:
            issues.append(f"{ctx}: expected empty translation for empty source, got {es!r}")
        return
    if not es and not allow_empty:
        issues.append(f"{ctx}: empty translation for {en!r}")
        return
    try:
        enc = es.encode("cp1252")
    except UnicodeEncodeError as exc:
        issues.append(f"{ctx}: non-CP1252 char in {es!r}: {exc}")
        return
    if max_bytes is not None and len(enc) > max_bytes:
        issues.append(f"{ctx}: encoded length {len(enc)} > max_bytes={max_bytes} ({es!r})")
    if printf_specs(en) != printf_specs(es):
        issues.append(
            f"{ctx}: format specifiers mismatch en={printf_specs(en)} vs es={printf_specs(es)}"
        )
    if req_ws is not None:
        pfx, sfx = req_ws
        if pfx and not es.startswith(pfx):
            issues.append(f"{ctx}: missing required prefix {pfx!r} in {es!r}")
        if sfx and not es.endswith(sfx):
            issues.append(f"{ctx}: missing required suffix {sfx!r} in {es!r}")


def load_catalogs(loc_dir: str | Path = "loc/es") -> dict[str, Any]:
    root = Path(loc_dir)
    return {
        "ei_exe": json.loads((root / "ei_exe.json").read_text("utf-8")),
        "text_res": json.loads((root / "text_res.json").read_text("utf-8")),
        "std_structs": json.loads((root / "std_structs.json").read_text("utf-8")),
        "maps": json.loads((root / "maps.json").read_text("utf-8")),
        "scenarios": json.loads((root / "scenarios.json").read_text("utf-8")),
    }


def validate_catalogs(loc_dir: str | Path = "loc/es") -> list[str]:
    """Return list of validation errors across all JSON catalogs and .txt docs."""
    root = Path(loc_dir)
    cats = load_catalogs(root)
    issues: list[str] = []

    for row in cats["ei_exe"]:
        _check_entry(
            issues,
            f"ei_exe:{row['raw_offset']}",
            row["en"],
            row["es"],
            row["max_bytes"],
            req_ws=EI_EXE_STRUCTURAL_WS.get(row["raw_offset"]),
        )

    for row in cats["text_res"]:
        _check_entry(
            issues,
            f"text_res:{row['id']}",
            row["en"],
            row["es"],
            None,
            req_ws=TEXT_RES_STRUCTURAL_WS.get(row["id"]),
        )

    std = cats["std_structs"]
    for key in ("patr", "wtyp", "weft"):
        for row in std[key]:
            _check_entry(issues, f"{key}:{row['id']}", row["en"], row["es"], row["max_bytes"])
    for row in std["pobj"]:
        _check_entry(
            issues, f"pobj:{row['id']}.name", row["name_en"], row["name_es"], row["name_max_bytes"]
        )
        _check_entry(
            issues, f"pobj:{row['id']}.desc", row["desc_en"], row["desc_es"], row["desc_max_bytes"]
        )
    for idx, row in enumerate(std["view_tooltips"]):
        _check_entry(
            issues, f"view_tooltips:{idx}", row["en"], row["es"], row["max_bytes"]
        )

    maps = cats["maps"]
    for row in maps["mapd"]:
        ctx = f"mapd:{row['file']}#{row['chunk_index']}"
        _check_entry(issues, f"{ctx}.name", row["name_en"], row["name_es"], row["name_max_bytes"])
        _check_entry(issues, f"{ctx}.base", row["base_en"], row["base_es"], row["base_max_bytes"])
    for idx, row in enumerate(maps["room_names"]):
        _check_entry(issues, f"room_names:{idx}", row["en"], row["es"], row["max_bytes"])

    scen = cats["scenarios"]
    for row in scen["scen"]:
        ctx = f"scen:{row['file']}"
        _check_entry(issues, f"{ctx}.title", row["title_en"], row["title_es"], row["title_max_bytes"])
        _check_entry(
            issues, f"{ctx}.briefing", row["briefing_en"], row["briefing_es"], row["briefing_max_bytes"]
        )
    for idx, row in enumerate(scen["goal_titles"]):
        _check_entry(issues, f"goal:{idx}", row["en"], row["es"], row["max_bytes"])
    for idx, row in enumerate(scen["lply_names"]):
        _check_entry(issues, f"lply:{idx}", row["en"], row["es"], row["max_bytes"])
    for row in scen["scen_texts"]:
        _check_entry(
            issues, f"scen_text:{row['file']}:{row['id']}", row["en"], row["es"], None
        )

    for txt_name in ("Help.txt", "ReadMe.txt", "Credits.txt"):
        p = root / txt_name
        if not p.exists():
            issues.append(f"{txt_name}: missing {p}")
            continue
        raw = p.read_bytes()
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError as exc:
            issues.append(f"{txt_name}: invalid CP1252 byte sequence: {exc}")
            continue
        if not text.strip():
            issues.append(f"{txt_name}: empty file")
        if b"\n" in raw and raw.count(b"\r\n") != raw.count(b"\n"):
            issues.append(f"{txt_name}: expected Windows CRLF line endings matching originals")

    return issues


def build_lookup_tables(cats: dict[str, Any]) -> dict[str, Any]:
    std = cats["std_structs"]
    maps = cats["maps"]
    scen = cats["scenarios"]

    view_tip_by_id: dict[int, str] = {}
    for row in std["view_tooltips"]:
        for cid in row["ids"]:
            view_tip_by_id[cid] = row["es"]

    return {
        "text_res": {r["id"]: r["es"] for r in cats["text_res"]},
        "patr": {r["id"]: r["es"] for r in std["patr"]},
        "wtyp": {r["id"]: r["es"] for r in std["wtyp"]},
        "weft": {r["id"]: r["es"] for r in std["weft"]},
        "pobj": {r["id"]: (r["name_es"], r["desc_es"]) for r in std["pobj"]},
        "view_tip": view_tip_by_id,
        "mapd": {(r["file"], r["chunk_index"]): (r["name_es"], r["base_es"]) for r in maps["mapd"]},
        "room": {r["en"]: r["es"] for r in maps["room_names"]},
        "scen": {r["file"]: (r["title_es"], r["briefing_es"]) for r in scen["scen"]},
        "goal": {r["en"]: r["es"] for r in scen["goal_titles"]},
        "lply": {r["en"]: r["es"] for r in scen["lply_names"]},
        "scen_text": {(r["file"], r["id"]): r["es"] for r in scen["scen_texts"]},
    }


def apply_text_and_structs(
    filename: str,
    chunks: list[blk0.Blk0Chunk],
    tables: dict[str, Any],
) -> list[blk0.ChunkSpec]:
    """Return updated chunk list with localized strings/structs for a .res archive."""
    out: list[blk0.ChunkSpec] = []

    for idx, c in enumerate(chunks):
        tag = c.tag
        cid = c.chunk_id
        body = c.body

        if filename == "Text.res" and tag == "text" and cid != 0:
            es = tables["text_res"][cid]
            body = blk0.encode_text(es, "cp1252")
        elif filename == "Stdres.res":
            if tag == "patr":
                body = blk0.patch_cstr(body, 2, 32, tables["patr"][cid], "cp1252")
            elif tag == "wtyp":
                body = blk0.patch_cstr(body, 0, 32, tables["wtyp"][cid], "cp1252")
            elif tag == "weft":
                body = blk0.patch_cstr(body, 2, 32, tables["weft"][cid], "cp1252")
            elif tag == "pobj":
                name_es, desc_es = tables["pobj"][cid]
                body = blk0.patch_cstr(body, 0, 32, name_es, "cp1252")
                body = blk0.patch_cstr(body, 36, 80, desc_es, "cp1252")
            elif tag == "view" and cid in tables["view_tip"]:
                body = blk0.patch_cstr(body, 116, 80, tables["view_tip"][cid], "cp1252")
        elif filename.startswith("Map"):
            if tag == "mapd":
                name_es, base_es = tables["mapd"][(filename, idx)]
                body = blk0.patch_cstr(body, 8, 32, name_es, "cp1252")
                body = blk0.patch_cstr(body, 40, 40, base_es, "cp1252")
            elif tag == "room":
                room_en = blk0._cstr(body[4:36])
                if room_en:
                    body = blk0.patch_cstr(body, 4, 32, tables["room"][room_en], "cp1252")
        elif filename.startswith("Scen"):
            if tag == "scen":
                title_es, brief_es = tables["scen"][filename]
                body = blk0.patch_cstr(body, 4, 40, title_es, "cp1252")
                body = blk0.patch_cstr(body, 300, 2048, brief_es, "cp1252")
            elif tag == "goal":
                flags = struct.unpack_from("<H", body, 0)[0]
                if (flags & 0x0A) != 0:
                    goal_en = blk0._cstr(body[2:66])
                    if goal_en:
                        body = blk0.patch_cstr(body, 2, 64, tables["goal"][goal_en], "cp1252")
            elif tag == "lply":
                lply_en = blk0._cstr(body[10:42])
                if lply_en:
                    body = blk0.patch_cstr(body, 10, 32, tables["lply"][lply_en], "cp1252")
            elif tag == "text" and cid != 0 and (filename, cid) in tables["scen_text"]:
                body = blk0.encode_text(tables["scen_text"][(filename, cid)], "cp1252")

        if body is c.body:
            out.append(c)
        else:
            out.append((tag, cid, c.flags_or_count, c.reserved, c.sub_id, body))

    return out


def patch_ei_exe(exe_bytes: bytes, ei_exe_entries: list[dict[str, Any]]) -> bytes:
    """Safely patch verified DGROUP UI strings inside Ei.exe without shifting code/data layout."""
    buf = bytearray(exe_bytes)
    for row in ei_exe_entries:
        off = int(row["raw_offset"], 16)
        mb = int(row["max_bytes"])
        en = row["en"]
        es = row["es"]
        slot_len = mb + 1

        orig_actual = buf[off:].split(b"\x00", 1)[0].decode("cp1252")
        if orig_actual != en:
            raise ValueError(
                f"Ei.exe mismatch at {row['raw_offset']}: expected {en!r}, found {orig_actual!r}"
            )
        if not all(b == 0 for b in buf[off + len(en.encode("cp1252")) : off + slot_len]):
            raise ValueError(f"Ei.exe slot {row['raw_offset']} has non-zero padding inside {slot_len}B")

        enc = es.encode("cp1252")
        if len(enc) > mb:
            raise ValueError(
                f"Ei.exe {row['raw_offset']}: {es!r} ({len(enc)}B) exceeds max_bytes={mb}"
            )
        buf[off : off + slot_len] = enc + b"\x00" * (slot_len - len(enc))
    return bytes(buf)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or inspect EI Spanish text catalogs.")
    parser.add_argument("cmd", choices=["check", "stats"])
    parser.add_argument("--loc-dir", default="loc/es")
    args = parser.parse_args(argv)

    if args.cmd == "check":
        issues = validate_catalogs(args.loc_dir)
        if issues:
            print(f"Found {len(issues)} validation issue(s):")
            for item in issues[:50]:
                print(" -", item)
            if len(issues) > 50:
                print(f" ... and {len(issues) - 50} more")
            return 1
        print("OK: all localization JSON catalogs and text documents are valid CP1252 within bounds.")
        return 0

    cats = load_catalogs(args.loc_dir)
    print("Catalog summary:")
    print("  ei_exe:", len(cats["ei_exe"]))
    print("  text_res:", len(cats["text_res"]))
    print("  std_structs:", {k: len(v) for k, v in cats["std_structs"].items()})
    print("  maps:", {k: len(v) for k, v in cats["maps"].items()})
    print("  scenarios:", {k: len(v) for k, v in cats["scenarios"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

