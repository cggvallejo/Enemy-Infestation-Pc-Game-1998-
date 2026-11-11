#!/usr/bin/env python3
"""Export structured world, database, text, scenario, and annotated map assets from Enemy Infestation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blk0 import (  # noqa: E402
    Blk0Archive,
    Blk0Chunk,
    decode_cbmp,
    decode_pal0,
    decode_structured,
)


def _find_case_insensitive(directory: Path, filename: str) -> Path | None:
    target = filename.lower()
    for p in directory.iterdir():
        if p.is_file() and p.name.lower() == target:
            return p
    return None


def _list_archives(game_dir: Path, prefix: str) -> list[Path]:
    seen: dict[str, Path] = {}
    for p in sorted(game_dir.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() == ".res" and p.name.lower().startswith(prefix.lower()):
            seen.setdefault(p.name.lower(), p)
    return list(seen.values())


def _chunk_record(chunk: Blk0Chunk) -> dict[str, Any]:
    decoded = decode_structured(chunk)
    rec: dict[str, Any] = {
        "id": chunk.chunk_id,
        "sub_id": chunk.sub_id,
        "size": len(chunk.body),
        "crc_ok": chunk.crc_ok,
    }
    if isinstance(decoded, dict):
        rec.update(decoded)
    elif decoded is not None:
        rec["value"] = decoded
    return rec


def export_database(game_dir: Path) -> dict[str, Any]:
    std_path = _find_case_insensitive(game_dir, "Stdres.res")
    if std_path is None:
        raise FileNotFoundError(f"Stdres.res not found in {game_dir}")
    arc = Blk0Archive(std_path)
    tags = ("wtyp", "patr", "pobj", "weft", "mind", "load", "view", "sprt")
    out: dict[str, Any] = {"source": std_path.name, "tables": {}}
    for tag in tags:
        chunks = arc.find_chunks(tag)
        out["tables"][tag] = [_chunk_record(c) for c in chunks]
    return out


def export_text_table(game_dir: Path) -> dict[str, Any]:
    txt_path = _find_case_insensitive(game_dir, "Text.res")
    if txt_path is None:
        raise FileNotFoundError(f"Text.res not found in {game_dir}")
    arc = Blk0Archive(txt_path)
    entries = {}
    for c in arc.find_chunks("text"):
        entries[str(c.chunk_id)] = decode_structured(c)
    return {"source": txt_path.name, "count": len(entries), "entries": entries}


def export_scenarios(game_dir: Path) -> dict[str, Any]:
    scenarios = []
    for sp in _list_archives(game_dir, "Scen"):
        arc = Blk0Archive(sp)
        scen_chunks = arc.find_chunks("scen")
        alie_chunks = arc.find_chunks("alie")
        entry: dict[str, Any] = {
            "file": sp.name,
            "scen": _chunk_record(scen_chunks[0]) if scen_chunks else None,
            "alie": [_chunk_record(c) for c in alie_chunks],
            "goals": [_chunk_record(c) for c in arc.find_chunks("goal")],
            "lply": [_chunk_record(c) for c in arc.find_chunks("lply")],
            "lwea": [_chunk_record(c) for c in arc.find_chunks("lwea")],
            "lpob": [_chunk_record(c) for c in arc.find_chunks("lpob")],
        }
        scenarios.append(entry)
    return {"count": len(scenarios), "scenarios": scenarios}


def _export_single_map(map_path: Path) -> tuple[dict[str, Any], Blk0Archive]:
    arc = Blk0Archive(map_path)
    mapd_chunks = arc.find_chunks("mapd")
    mapd = _chunk_record(mapd_chunks[0]) if mapd_chunks else None

    rooms = []
    for c in arc.find_chunks("room"):
        rec = _chunk_record(c)
        origin = rec.get("origin")
        pts = rec.get("points") or []
        rec["polygon"] = ([origin] + pts) if origin is not None else pts
        rooms.append(rec)

    data: dict[str, Any] = {
        "file": map_path.name,
        "mapd": mapd,
        "rooms": rooms,
        "roofs": [_chunk_record(c) for c in arc.find_chunks("roof")],
        "doors": [_chunk_record(c) for c in arc.find_chunks("door")],
        "elevators": [_chunk_record(c) for c in arc.find_chunks("elev")],
        "exits": [_chunk_record(c) for c in arc.find_chunks("exit")],
    }
    return data, arc


def _render_map_images(
    map_data: dict[str, Any],
    arc: Blk0Archive,
    out_dir: Path,
    roof_layer_idx: int = 0,
) -> tuple[Path, Path]:
    stem = Path(map_data["file"]).stem
    pal_chunks = arc.find_chunks("pal0")
    if not pal_chunks:
        raise ValueError(f"{arc.path.name}: missing pal0")
    pal = decode_pal0(pal_chunks[0].body)

    floor_chunks = arc.find_chunks("cbmp", 0)
    if not floor_chunks:
        raise ValueError(f"{arc.path.name}: missing cbmp id=0")
    floor_img = decode_cbmp(floor_chunks[0].body).to_image(pal).convert("RGBA")

    composited = floor_img.copy()
    mask_lut = [0] + [255] * 255
    if 0 <= roof_layer_idx < 6:
        for roof in map_data["roofs"]:
            layers = roof.get("cbmp_layers") or []
            if len(layers) <= roof_layer_idx:
                continue
            cid = layers[roof_layer_idx]
            rc = arc.find_chunks("cbmp", cid)
            if not rc:
                continue
            rcb = decode_cbmp(rc[0].body)
            mask = Image.frombytes("L", (rcb.width, rcb.height), rcb.pixels).point(mask_lut)
            layer_rgba = rcb.to_image(pal).convert("RGBA")
            composited.paste(layer_rgba, (roof["x"], roof["y"]), mask)

    base_path = out_dir / f"{stem}_base.png"
    composited.convert("RGB").save(base_path)

    annotated = composited.copy()
    draw = ImageDraw.Draw(annotated)

    # Draw room polygons and labels
    for rm in map_data["rooms"]:
        poly = rm.get("polygon") or []
        if len(poly) >= 3:
            xy = [(int(px), int(py)) for px, py in poly]
            draw.polygon(xy, outline=(0, 255, 128, 255))
            cx = sum(p[0] for p in xy) // len(xy)
            cy = sum(p[1] for p in xy) // len(xy)
            label = f"{rm.get('code', '')} {rm.get('name', '')}".strip()
            draw.text((cx - 24, cy - 6), label, fill=(220, 255, 220, 255))

    # Draw exit links (tile coords -> 16x8 px center)
    for ex in map_data["exits"]:
        t1 = ex.get("tile1")
        t2 = ex.get("tile2")
        if t1 and t2:
            p1 = (t1[0] * 16 + 8, t1[1] * 8 + 4)
            p2 = (t2[0] * 16 + 8, t2[1] * 8 + 4)
            draw.line([p1, p2], fill=(0, 220, 255, 255), width=2)
            draw.ellipse([p1[0] - 3, p1[1] - 3, p1[0] + 3, p1[1] + 3], fill=(0, 220, 255, 255))
            draw.ellipse([p2[0] - 3, p2[1] - 3, p2[0] + 3, p2[1] + 3], fill=(0, 220, 255, 255))

    # Draw door markers
    for d in map_data["doors"]:
        dx, dy = int(d["x"]), int(d["y"])
        draw.rectangle([dx - 4, dy - 4, dx + 4, dy + 4], outline=(255, 220, 0, 255), width=2)

    # Draw elevator shafts
    for el in map_data["elevators"]:
        pts = [(int(fl["px"][0]), int(fl["px"][1])) for fl in el.get("floors", [])]
        if len(pts) >= 2:
            draw.line(pts, fill=(255, 80, 255, 255), width=2)
        for idx, (px, py) in enumerate(pts):
            draw.ellipse([px - 5, py - 5, px + 5, py + 5], outline=(255, 80, 255, 255), width=2)
            if idx == 0:
                draw.text((px + 7, py - 6), f"E{el['id']}", fill=(255, 160, 255, 255))

    ann_path = out_dir / f"{stem}_annotated.png"
    annotated.convert("RGB").save(ann_path)
    return base_path, ann_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export Enemy Infestation world, scenarios, database, and maps")
    ap.add_argument("game_dir", type=Path, help="Directory containing Ei.exe and .res files")
    ap.add_argument("-o", "--out", type=Path, default=Path("extracted/world"), help="Output directory")
    ap.add_argument("--render-maps", action="store_true", help="Render composited and annotated PNGs for all maps")
    ap.add_argument("--roof-layer", type=int, default=0, help="Roof cbmp layer index 0..5, or -1 to omit roofs (default: 0)")
    args = ap.parse_args(argv)

    game_dir: Path = args.game_dir
    out_dir: Path = args.out
    maps_dir = out_dir / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    db = export_database(game_dir)
    (out_dir / "database.json").write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")

    txt = export_text_table(game_dir)
    (out_dir / "text_table.json").write_text(json.dumps(txt, indent=2, ensure_ascii=False), encoding="utf-8")

    scens = export_scenarios(game_dir)
    (out_dir / "scenarios.json").write_text(json.dumps(scens, indent=2, ensure_ascii=False), encoding="utf-8")

    map_paths = _list_archives(game_dir, "Map")
    for mp in map_paths:
        mdata, arc = _export_single_map(mp)
        stem = mp.stem
        (maps_dir / f"{stem}.json").write_text(json.dumps(mdata, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.render_maps:
            base_p, ann_p = _render_map_images(mdata, arc, maps_dir, roof_layer_idx=args.roof_layer)
            print(f"{mp.name}: rooms={len(mdata['rooms'])} doors={len(mdata['doors'])} exits={len(mdata['exits'])} -> {base_p.name}, {ann_p.name}")
        else:
            print(f"{mp.name}: rooms={len(mdata['rooms'])} doors={len(mdata['doors'])} exits={len(mdata['exits'])}")

    print(
        f"Exported database ({ {k: len(v) for k, v in db['tables'].items()} }), "
        f"text={txt['count']}, scenarios={scens['count']}, maps={len(map_paths)} -> {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

