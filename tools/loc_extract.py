#!/usr/bin/env python3
"""Extract all localizable strings from Enemy Infestation .res archives and Ei.exe."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blk0  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GAME_DIR = Path(r"C:\Program Files (x86)\Enemy Infestation")
DEFAULT_OUT_DIR = ROOT / "loc" / "es"

# Curated UI/player-facing string entries inside Ei.exe DGROUP (raw file offset, max safe bytes, expected English).
# Every entry has been verified against DGROUP PE bounds (0x05AA00..0x061600) with zero next-VA references.
EI_EXE_STRINGS: list[tuple[int, int, str]] = [
    (0x05AA00 + 0x0040, 19, "Unauthorised Copy!"),
    (0x05AA00 + 0x006C, 31, "Lobby Init failed, DX6 required"),
    (0x05AA00 + 0x0190, 15, "Fatal Error: %s"),
    (0x05AA00 + 0x01C8, 19, "Please Insert CDROM"),
    (0x05AA00 + 0x05A0, 7, "Trooper"),
    (0x05AA00 + 0x05EC, 7, "Hello."),
    (0x05AA00 + 0x05F8, 15, "Aliens stopped"),
    (0x05AA00 + 0x0608, 15, "Aliens started"),
    (0x05AA00 + 0x0624, 23, "%s: click to move here"),
    (0x05AA00 + 0x063C, 27, "Click to cancel Move mode"),
    (0x05AA00 + 0x066C, 15, "The Party..."),
    (0x05AA00 + 0x067C, 11, "is over."),
    (0x05AA00 + 0x0688, 11, "episode "),
    (0x05AA00 + 0x06E8, 7, "(M)ove"),
    (0x05AA00 + 0x06F0, 7, "Grow"),
    (0x05AA00 + 0x06F8, 7, "Spin"),
    (0x05AA00 + 0x0780, 7, "Send"),
    (0x05AA00 + 0x07A0, 27, "Cannot open file 'help.txt'"),
    (0x05AA00 + 0x07E8, 15, "General error"),
    (0x05AA00 + 0x07F8, 23, "Receive buffer overflow"),
    (0x05AA00 + 0x0810, 23, "Sending buffer overflow"),
    (0x05AA00 + 0x087C, 23, "Unable to join session"),
    (0x05AA00 + 0x0894, 39, "Failed to init network, DX6 required"),
    (0x05AA00 + 0x08D0, 7, "Serial"),
    (0x05AA00 + 0x08D8, 7, "Modem"),
    (0x05AA00 + 0x18C0, 15, "Game Message"),
    (0x05AA00 + 0x18D0, 15, "Session Lost"),
    (0x05AA00 + 0x18E0, 15, "Player Created"),
    (0x05AA00 + 0x18F0, 19, "Player Destroyed"),
    (0x05AA00 + 0x1C97, 19, "Application Error: "),
    (0x05AA00 + 0x1CAB, 44, "\n\nClick on OK to terminate the application"),
    (0x05AA00 + 0x48F0, 63, "This is the base view"),
]


def _verify_exe_slots(exe: bytes) -> list[dict]:
    items = []
    for raw_off, max_b, expected in EI_EXE_STRINGS:
        end_nul = exe.index(0, raw_off)
        actual = exe[raw_off:end_nul].decode("ascii")
        if actual != expected:
            raise ValueError(f"Ei.exe mismatch at 0x{raw_off:06x}: expected {expected!r}, got {actual!r}")
        # Verify padding bytes [end_nul .. raw_off + max_b] are strictly 0x00 so no neighbor byte is touched.
        pad_slice = exe[end_nul : raw_off + max_b + 1]
        if any(b != 0 for b in pad_slice):
            raise ValueError(f"Ei.exe slot 0x{raw_off:06x} ({expected!r}) lacks {max_b}B zero-padded room")
        items.append(
            {
                "raw_offset": f"0x{raw_off:06x}",
                "va": f"0x{0x00400000 + 0x0005C000 + (raw_off - 0x05AA00):08x}",
                "max_bytes": max_b,
                "en": actual,
                "es": "",
            }
        )
    return items


def extract_all(game_dir: Path, out_dir: Path, overwrite: bool = False) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    def _write(name: str, data: object) -> None:
        p = out_dir / name
        if p.exists() and not overwrite:
            return
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 1. Text.res
    arc_t = blk0.Blk0Archive(game_dir / "Text.res")
    text_entries = []
    for c in arc_t.chunks:
        if c.tag != "text":
            continue
        s = blk0.decode_structured(c)
        if c.chunk_id == 0 and isinstance(s, str) and s.startswith("$Id:"):
            continue
        text_entries.append({"id": c.chunk_id, "en": s, "es": ""})
    _write("text_res.json", text_entries)
    counts["text_res"] = len(text_entries)

    # 2. Stdres.res structured records
    arc_std = blk0.Blk0Archive(game_dir / "Stdres.res")
    patr, wtyp, weft, pobj = [], [], [], []
    tips_map: dict[str, list[int]] = defaultdict(list)
    for c in arc_std.chunks:
        d = blk0.decode_structured(c)
        if not isinstance(d, dict):
            continue
        if c.tag == "patr":
            patr.append({"id": c.chunk_id, "is_alien": d["is_alien"], "max_bytes": 31, "en": d["name"], "es": ""})
        elif c.tag == "wtyp":
            wtyp.append({"id": c.chunk_id, "max_bytes": 31, "en": d["name"], "es": ""})
        elif c.tag == "weft":
            weft.append({"id": c.chunk_id, "max_bytes": 31, "en": d["name"], "es": ""})
        elif c.tag == "pobj":
            pobj.append(
                {
                    "id": c.chunk_id,
                    "name_max_bytes": 31,
                    "name_en": d["name"],
                    "name_es": "",
                    "desc_max_bytes": 79,
                    "desc_en": d["desc"],
                    "desc_es": "",
                }
            )
        elif c.tag == "view" and d.get("tooltip"):
            tips_map[d["tooltip"]].append(c.chunk_id)
    view_tooltips = [{"max_bytes": 79, "ids": ids, "en": k, "es": ""} for k, ids in sorted(tips_map.items())]
    _write(
        "std_structs.json",
        {"patr": patr, "wtyp": wtyp, "weft": weft, "pobj": pobj, "view_tooltips": view_tooltips},
    )
    counts["std_structs"] = len(patr) + len(wtyp) + len(weft) + len(pobj) + len(view_tooltips)

    # 3. Map*.res
    mapd_list = []
    rooms_map: dict[str, list[str]] = defaultdict(list)
    for rf in sorted(game_dir.glob("Map*.res")):
        arc = blk0.Blk0Archive(rf)
        for idx, c in enumerate(arc.chunks):
            d = blk0.decode_structured(c)
            if not isinstance(d, dict):
                continue
            if c.tag == "mapd":
                mapd_list.append(
                    {
                        "file": rf.name,
                        "chunk_index": idx,
                        "id": c.chunk_id,
                        "name_max_bytes": 31,
                        "name_en": d["name"],
                        "name_es": "",
                        "base_max_bytes": 39,
                        "base_en": d["base"],
                        "base_es": "",
                    }
                )
            elif c.tag == "room" and d.get("name"):
                rooms_map[d["name"]].append(f"{rf.name}:{c.chunk_id}")
    room_names = [{"max_bytes": 31, "en": k, "es": "", "refs": refs} for k, refs in sorted(rooms_map.items())]
    _write("maps.json", {"mapd": mapd_list, "room_names": room_names})
    counts["maps"] = len(mapd_list) + len(room_names)

    # 4. Scen*.res
    scen_list = []
    goals_map: dict[str, list[str]] = defaultdict(list)
    lply_map: dict[str, int] = defaultdict(int)
    scen_texts = []
    for rf in sorted(game_dir.glob("Scen*.res")):
        arc = blk0.Blk0Archive(rf)
        for c in arc.chunks:
            if c.tag == "text":
                s = blk0.decode_structured(c)
                if not (c.chunk_id == 0 and isinstance(s, str) and s.startswith("$Id:")):
                    scen_texts.append({"file": rf.name, "id": c.chunk_id, "en": s, "es": ""})
                continue
            d = blk0.decode_structured(c)
            if not isinstance(d, dict):
                continue
            if c.tag == "scen":
                scen_list.append(
                    {
                        "file": rf.name,
                        "id": c.chunk_id,
                        "title_max_bytes": 39,
                        "title_en": d["title"],
                        "title_es": "",
                        "briefing_max_bytes": 2047,
                        "briefing_en": d.get("briefing", ""),
                        "briefing_es": "",
                    }
                )
            elif c.tag == "goal" and d.get("title"):
                # Flags with bits 0x02 or 0x08 represent visible mission objectives in the Goals UI.
                if (d["flags"] & 0x0A) != 0:
                    goals_map[d["title"]].append(f"{rf.name}:{c.chunk_id}:f{d['flags']}")
            elif c.tag == "lply" and d.get("name"):
                lply_map[d["name"]] += 1
    goal_titles = [{"max_bytes": 63, "en": k, "es": "", "refs": refs} for k, refs in sorted(goals_map.items())]
    lply_names = [{"max_bytes": 31, "en": k, "es": "", "count": cnt} for k, cnt in sorted(lply_map.items())]
    _write(
        "scenarios.json",
        {"scen": scen_list, "goal_titles": goal_titles, "lply_names": lply_names, "scen_texts": scen_texts},
    )
    counts["scenarios"] = len(scen_list) + len(goal_titles) + len(lply_names) + len(scen_texts)

    # 5. Ei.exe safe UI strings
    exe_bytes = (game_dir / "Ei.exe").read_bytes()
    exe_items = _verify_exe_slots(exe_bytes)
    _write("ei_exe.json", exe_items)
    counts["ei_exe"] = len(exe_items)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extract clean English source catalogs for Spanish localization.")
    ap.add_argument("--src-dir", type=Path, default=DEFAULT_GAME_DIR)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing JSON files in loc/es")
    args = ap.parse_args(argv)
    counts = extract_all(args.src_dir, args.out_dir, overwrite=args.overwrite)
    print("Extracted catalogs:", json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
