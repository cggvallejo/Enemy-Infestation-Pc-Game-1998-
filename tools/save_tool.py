#!/usr/bin/env python3
"""Savegame inspector and CRC-safe patcher for Enemy Infestation save*.res files."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blk0 import Blk0Archive, Blk0Chunk, _cstr, build_blk0, decode_structured  # noqa: E402


def inspect_save(path: str | Path) -> dict[str, Any]:
    arc = Blk0Archive(path)
    errors = arc.verify()
    sggm_chunks = arc.find_chunks("sggm")
    header: dict[str, Any] = {}
    if sggm_chunks:
        b = sggm_chunks[0].body
        sggm_dec = decode_structured(sggm_chunks[0])
        header = {
            "scen_id": struct.unpack_from("<I", b, 0x66)[0] if len(b) >= 0x6A else None,
            "scen_name": _cstr(b[0x6A:0xCE]) if len(b) >= 0xCE else "",
            "title": sggm_dec["title"] if isinstance(sggm_dec, dict) else "",
            "ticks": struct.unpack_from("<I", b, 0x15C0)[0] if len(b) >= 0x15C4 else None,
            "weapon_flags": list(struct.unpack_from("<23H", b, 0x06)) if len(b) >= 0x34 else [],
            "weapon_counts": list(struct.unpack_from("<23H", b, 0x34)) if len(b) >= 0x62 else [],
            "log_entries": sggm_dec["log_entries"] if isinstance(sggm_dec, dict) else [],
        }

    units = [
        {"id": c.chunk_id, **(decode_structured(c) or {})}
        for c in arc.find_chunks("sgpl")
    ]
    weapons = [
        {"id": c.chunk_id, **(decode_structured(c) or {})}
        for c in arc.find_chunks("sgwp")
    ]
    objects = [
        {"id": c.chunk_id, **(decode_structured(c) or {})}
        for c in arc.find_chunks("sgpo")
    ]
    minds = [
        {"id": c.chunk_id, **(decode_structured(c) or {})}
        for c in arc.find_chunks("sgmd")
    ]
    goals = [
        {"id": c.chunk_id, **(decode_structured(c) or {})}
        for c in arc.find_chunks("sggl")
    ]
    exits = [
        {"id": c.chunk_id, **(decode_structured(c) or {})}
        for c in arc.find_chunks("sgex")
    ]
    rooms = [
        {"id": c.chunk_id, **(decode_structured(c) or {})}
        for c in arc.find_chunks("sgrm")
    ]
    chunk_counts: dict[str, int] = {}
    for c in arc.chunks:
        chunk_counts[c.tag] = chunk_counts.get(c.tag, 0) + 1
    return {
        "file": str(arc.path),
        "verify_errors": errors,
        "chunk_count": len(arc.chunks),
        "chunk_counts": chunk_counts,
        "sggm": header,
        "units": units,
        "weapons": weapons,
        "objects": objects,
        "minds": minds,
        "goals": goals,
        "exits": exits,
        "rooms": rooms,
    }


def _parse_goal_flag_specs(specs: list[str] | None) -> dict[int, int]:
    """Parse ['ID=FLAGS', ...] specs (decimal or 0x hex) into {goal_id: state_flags}."""
    parsed: dict[int, int] = {}
    for raw in specs or []:
        if "=" not in raw:
            raise ValueError(f"Expected GOAL_ID=FLAGS, got {raw!r}")
        gid_s, val_s = raw.split("=", 1)
        gid = int(gid_s, 0)
        val = int(val_s, 0)
        if not (0 <= val <= 0xFFFF):
            raise ValueError(f"state_flags out of uint16 range: {val}")
        parsed[gid] = val
    return parsed


def patch_save(
    in_path: str | Path,
    out_path: str | Path,
    *,
    title: str | None = None,
    heal_colonists: bool = False,
    goal_flags: dict[int, int] | None = None,
) -> list[str]:
    """Patch selected safe fields of a save*.res archive and write a verified BLK0 output."""
    src = Path(in_path)
    dst = Path(out_path)
    if "program files" in str(dst.resolve()).lower():
        raise PermissionError(f"Refusing to write inside Program Files: {dst}")

    arc = Blk0Archive(src)
    new_chunks: list[Blk0Chunk] = []

    for c in arc.chunks:
        body = bytearray(c.body)
        if c.tag == "sggm" and title is not None and len(body) >= 0x130:
            raw_t = title.encode("cp1252", errors="replace")[:0x61]
            body[0xCE:0x130] = raw_t.ljust(0x130 - 0xCE, b"\x00")
        elif c.tag == "sgpl" and heal_colonists and len(body) >= 254:
            actor = _cstr(body[32:36])
            if actor.startswith("CO"):
                hp, max_hp = struct.unpack_from("<2H", body, 80)
                if 0 < hp < max_hp:
                    struct.pack_into("<H", body, 80, max_hp)
        elif c.tag == "sggl" and goal_flags and len(body) >= 4:
            gid = struct.unpack_from("<H", body, 0)[0]
            if gid in goal_flags:
                struct.pack_into("<H", body, 2, goal_flags[gid])
        new_chunks.append(
            Blk0Chunk(
                tag=c.tag,
                chunk_id=c.chunk_id,
                offset=c.offset,
                payload_size=len(body) + 4,
                flags_or_count=c.flags_or_count,
                reserved=c.reserved,
                sub_id=c.sub_id,
                stored_crc=None,
                body=bytes(body),
            )
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(build_blk0(new_chunks))
    return Blk0Archive(dst).verify()


def cmd_inspect(args: argparse.Namespace) -> int:
    data = inspect_save(args.path)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    s = data["sggm"]
    print(f"Save: {data['file']} (chunks={data['chunk_count']}, errors={len(data['verify_errors'])})")
    print(f"Title: {s.get('title', '')!r} | scen_id={s.get('scen_id')} | ticks={s.get('ticks')}")
    cc = data.get("chunk_counts") or {}
    if cc:
        counts_line = " ".join(f"{k}={v}" for k, v in cc.items() if k not in ("IDAT", "DIR ", "END "))
        print(f"Chunks: {counts_line}")
    print(f"Units ({len(data['units'])}):")
    for u in data["units"]:
        print(
            f"  [{u.get('actor_code', ''):<4}] {u.get('name', ''):<18} {u.get('role', ''):<16} "
            f"HP={u.get('hp')}/{u.get('max_hp')} room={u.get('room', '')} tile={u.get('tile')} wep={u.get('weapon_code', '')!r}"
        )
    print(f"Goals ({len(data['goals'])}):")
    gline = ", ".join(
        f"#{g.get('goal_id')}[{'A' if g.get('active') else '-'}{'T' if g.get('triggered') else '-'}]"
        for g in data["goals"]
    )
    print(f"  {gline}")
    logs = s.get("log_entries") or []
    print(f"Radio logs ({len(logs)}):")
    for line in logs[-5:]:
        print(f"  {line}")
    return 0


def cmd_patch(args: argparse.Namespace) -> int:
    goal_flags = _parse_goal_flag_specs(args.goal_flag)
    errs = patch_save(
        args.path,
        args.out,
        title=args.title,
        heal_colonists=args.heal_colonists,
        goal_flags=goal_flags or None,
    )
    if errs:
        print(f"Verification errors after patching {args.out}: {errs}", file=sys.stderr)
        return 1
    print(f"Patched & verified -> {args.out} (0 errors)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Inspect and safely patch Enemy Infestation save*.res files")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("inspect", help="Display decoded savegame snapshot")
    pi.add_argument("path")
    pi.add_argument("--json", action="store_true", help="Print full JSON output")
    pi.set_defaults(func=cmd_inspect)

    pp = sub.add_parser("patch", help="Write a modified & re-checksummed copy of a savegame")
    pp.add_argument("path", help="Input save*.res path")
    pp.add_argument("-o", "--out", required=True, help="Output .res path (never inside Program Files)")
    pp.add_argument("--title", help="New save title written to sggm+0xce")
    pp.add_argument("--heal-colonists", action="store_true", help="Restore CO* unit HP to max_hp")
    pp.add_argument(
        "--goal-flag",
        action="append",
        metavar="ID=FLAGS",
        help="Override sggl state_flags for goal ID (repeatable, accepts decimal or 0x hex)",
    )
    pp.set_defaults(func=cmd_patch)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
