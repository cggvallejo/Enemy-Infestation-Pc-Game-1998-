
#!/usr/bin/env python3
"""Font extension (CP1252 Spanish) and Stdres.res UI cbmp localization generator."""

from __future__ import annotations

import argparse
import dataclasses
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import blk0  # noqa: E402

# Extra CP1252 Spanish characters to append to every Stdres bitmap UI font
# (keeping total glyph slots <= 128 so original 1284B chunk layout holds cleanly)
EXTRA_GLYPHS: list[tuple[int, str, str, str]] = [
    # (cp1252_code, base_char, diacritic_kind, glyph_name)
    (0xA1, "!", "inv_excl", "¡"),
    (0xBF, "?", "inv_ques", "¿"),
    (0xAA, "a", "ord_fem", "ª"),
    (0xBA, "o", "ord_msc", "º"),
    (0xB0, "o", "degree", "°"),
    (0x93, "\"", "qopen", "“"),
    (0x94, "\"", "qclose", "”"),
    (0x96, "-", "endash", "–"),
    (0xC1, "A", "acute", "Á"),
    (0xC9, "E", "acute", "É"),
    (0xCD, "I", "acute", "Í"),
    (0xD1, "N", "tilde", "Ñ"),
    (0xD3, "O", "acute", "Ó"),
    (0xDA, "U", "acute", "Ú"),
    (0xDC, "U", "umlaut", "Ü"),
    (0xE1, "a", "acute", "á"),
    (0xE9, "e", "acute", "é"),
    (0xED, "i", "acute_dotless", "í"),
    (0xF1, "n", "tilde", "ñ"),
    (0xF3, "o", "acute", "ó"),
    (0xFA, "u", "acute", "ú"),
    (0xFC, "u", "umlaut", "ü"),
]

# Font sheet palette roles under Stdres pal0 20
FONT_STYLES = {
    15002: {"bg": 0, "core": 44, "shadow": 133, "ramp": [44], "accent_mode": "shadow_yellow"},
    15010: {"bg": 0, "core": 64, "shadow": 0, "ramp": [73, 68, 64], "accent_mode": "green_aa"},
    15011: {"bg": 0, "core": 133, "shadow": 0, "ramp": [74, 67, 133], "accent_mode": "dark_aa"},
    15012: {"bg": 0, "core": 134, "shadow": 0, "ramp": [103, 105, 117, 114, 97, 62, 134], "accent_mode": "white_aa"},
    15013: {"bg": 0, "core": 64, "shadow": 0, "ramp": [71, 67, 66, 65, 64], "accent_mode": "green_big_aa"},
    15014: {"bg": 133, "core": 66, "shadow": 133, "ramp": [71, 67, 66, 64], "accent_mode": "green_med"},
}

TTF_PATHS = {
    "arialbd": r"C:\Windows\Fonts\arialbd.ttf",
    "arialnb": r"C:\Windows\Fonts\ARIALNB.TTF",
    "arialn": r"C:\Windows\Fonts\ARIALN.TTF",
    "arial": r"C:\Windows\Fonts\arial.ttf",
    "consolab": r"C:\Windows\Fonts\consolab.ttf",
    "consola": r"C:\Windows\Fonts\consola.ttf",
    "impact": r"C:\Windows\Fonts\impact.ttf",
}

_TTF_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def load_ttf(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _TTF_CACHE:
        _TTF_CACHE[key] = ImageFont.truetype(TTF_PATHS[name], size)
    return _TTF_CACHE[key]


def _clamp_box_coords(w: int, h: int, x: int, y: int) -> int:
    return y * w + x


def _find_ink_bounds(grid: list[list[int]], bg: int) -> tuple[int, int, int, int] | None:
    ys = [y for y, row in enumerate(grid) for v in row if v != bg]
    xs = [x for row in grid for x, v in enumerate(row) if v != bg]
    if not xs:
        return None
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _extract_glyph(pixels: bytearray | bytes, sheet_w: int, g: dict[str, int]) -> list[list[int]]:
    return [
        [pixels[(g["y"] + dy) * sheet_w + (g["x"] + dx)] for dx in range(g["w"])]
        for dy in range(g["h"])
    ]


def _squash_vertical(grid: list[list[int]], target_body_h: int, top_pad: int, bg: int) -> list[list[int]]:
    """Shift or gently compress an uppercase glyph vertically inside fixed height `len(grid)` to fit accents."""
    h = len(grid)
    w = len(grid[0]) if h else 0
    bounds = _find_ink_bounds(grid, bg)
    if not bounds:
        return [row[:] for row in grid]
    _, y0, _, y1 = bounds
    src_rows = grid[y0:y1]
    src_h = len(src_rows)
    out = [[bg] * w for _ in range(h)]
    dest_h = min(target_body_h, h - top_pad)
    if src_h <= dest_h:
        # Just shift down to top_pad without dropping rows!
        start_y = min(top_pad, h - src_h)
        for dy, row in enumerate(src_rows):
            out[start_y + dy] = row[:]
        return out
    # Drop least-informative interior repeat rows (preserving top/middle bars and bottom row)
    keep_rows = list(range(src_h))
    # Prioritize removing interior duplicate stem rows (indices 1..src_h-2 excluding exact middle)
    mid = src_h // 2
    while len(keep_rows) > dest_h:
        best_idx = None
        best_score = 10**9
        for pos in range(1, len(keep_rows) - 1):
            r_idx = keep_rows[pos]
            if r_idx in (1, mid, src_h - 2):
                continue
            # similarity to neighbor row
            prev_row = src_rows[keep_rows[pos - 1]]
            cur_row = src_rows[r_idx]
            diff = sum(1 for a, b in zip(prev_row, cur_row) if a != b)
            if diff < best_score:
                best_score = diff
                best_idx = pos
        if best_idx is None:
            best_idx = 1
        keep_rows.pop(best_idx)
    for dy, r_idx in enumerate(keep_rows):
        out[top_pad + dy] = src_rows[r_idx][:]
    return out


def _draw_pixel(grid: list[list[int]], x: int, y: int, val: int, bg: int | None = None, only_if_bg: bool = False) -> None:
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        if only_if_bg and bg is not None and grid[y][x] != bg:
            return
        grid[y][x] = val


def _apply_halo_15002(grid: list[list[int]], core: int = 44, shadow: int = 133, bg: int = 0) -> None:
    """Add 15002's signature 1px dark outline (idx 133) around `core` pixels on `bg`."""
    h = len(grid)
    w = len(grid[0]) if h else 0
    core_pts = [(x, y) for y in range(h) for x in range(w) if grid[y][x] == core]
    for y in range(h):
        for x in range(w):
            if grid[y][x] == shadow:
                grid[y][x] = bg
    for x, y in core_pts:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == bg:
                    grid[ny][nx] = shadow


def _synthesize_glyph(
    fid: int,
    base_grid: list[list[int]],
    kind: str,
    style: dict,
    gmap: dict[int, list[list[int]]],
) -> list[list[int]]:
    bg = style["bg"]
    core = style["core"]
    ramp = style["ramp"]
    h = len(base_grid)
    w = len(base_grid[0]) if h else 1
    big = h >= 18

    if kind == "inv_excl":
        g = [row[:] for row in reversed(base_grid)]
        bounds = _find_ink_bounds(g, bg)
        if bounds:
            # Shift down by 1-2px so upside-down ! sits slightly lower like lowercase ¡
            _, y0, _, y1 = bounds
            shift = min(2 if big else 1, h - y1)
            if shift > 0:
                g = [[bg] * w for _ in range(shift)] + g[: h - shift]
        return g

    if kind == "inv_ques":
        g = [list(reversed(row)) for row in reversed(base_grid)]
        bounds = _find_ink_bounds(g, bg)
        if bounds:
            _, y0, _, y1 = bounds
            shift = min(3 if big else 1, h - y1)
            if shift > 0:
                g = [[bg] * w for _ in range(shift)] + g[: h - shift]
        return g

    if kind in ("qopen", "qclose"):
        # Double curly-ish quote or angled ASCII '"'
        q = gmap.get(ord('"')) or gmap.get(ord("'"))
        if q:
            return [row[:] for row in q]
        return [row[:] for row in base_grid]

    if kind == "endash":
        out = [[bg] * w for _ in range(h)]
        ymid = h // 2
        thick = 2 if big else 1
        for yy in range(ymid, ymid + thick):
            for xx in range(0, w):
                out[yy][xx] = core
        if fid == 15002:
            _apply_halo_15002(out, core, style["shadow"], bg)
        return out

    if kind in ("ord_fem", "ord_msc", "degree"):
        # Small raised circle/a/o near top of cap-height
        mw = max(3, min(w, 6 if big else 3))
        out = [[bg] * mw for _ in range(h)]
        y0 = 2 if big else 1
        if kind == "degree":
            pts = (
                [(1, 0), (2, 0), (0, 1), (3, 1), (0, 2), (3, 2), (1, 3), (2, 3)]
                if big
                else [(1, 0), (0, 1), (2, 1), (1, 2)]
            )
            for px, py in pts:
                _draw_pixel(out, px, y0 + py, core)
        else:
            src = gmap[ord("a" if kind == "ord_fem" else "o")]
            sb = _find_ink_bounds(src, bg) or (0, 0, len(src[0]), len(src))
            sw, sh = max(1, sb[2] - sb[0]), max(1, sb[3] - sb[1])
            tw = 5 if big else 3
            th = 5 if big else 3
            out = [[bg] * tw for _ in range(h)]
            for dy in range(th):
                for dx in range(tw):
                    sx = sb[0] + int(dx * sw / tw)
                    sy = sb[1] + int(dy * sh / th)
                    if src[sy][sx] != bg:
                        _draw_pixel(out, dx, y0 + dy, core)
            # underline
            uy = y0 + th + (1 if big else 0)
            if uy < h:
                for dx in range(tw):
                    _draw_pixel(out, dx, uy, ramp[0])
        if fid == 15002:
            _apply_halo_15002(out, core, style["shadow"], bg)
        return out

    # Accented uppercase vs lowercase
    is_upper = False
    bounds = _find_ink_bounds(base_grid, bg)
    top_y = bounds[1] if bounds else 2

    if kind == "acute_dotless":
        # Remove the dot on 'i' (usually highest thin ink cluster separated by >=1 blank row)
        cleaned = [row[:] for row in base_grid]
        # Find first blank row after top ink cluster
        seen_ink = False
        cut_end = None
        for y in range(h):
            has_ink = any(v != bg for v in cleaned[y])
            if has_ink:
                seen_ink = True
            elif seen_ink:
                cut_end = y
                break
        if cut_end is not None and cut_end < h - 3:
            for y in range(cut_end):
                cleaned[y] = [bg] * w
        grid = cleaned
        bounds = _find_ink_bounds(grid, bg)
        top_y = bounds[1] if bounds else (5 if big else 3)
        # Ensure minimum width of 3 (or 5 for big fonts) so acute slash reads cleanly
        min_w = 5 if big else 3
        if w < min_w:
            pad_l = (min_w - w) // 2
            pad_r = min_w - w - pad_l
            grid = [[bg] * pad_l + row + [bg] * pad_r for row in grid]
            w = min_w
    else:
        grid = [row[:] for row in base_grid]
        # Detect uppercase by checking top_y vs font cap height
        cap_top = (_find_ink_bounds(gmap[ord("E")], bg) or (0, 0, 1, h))[1]
        is_upper = top_y <= cap_top + (1 if big else 0)
        if is_upper:
            if big:
                # 21px fonts have 4 blank rows at bottom (y=17..20); reserve rows 0..3 for diacritics, body y=4..18 (15px or compressed from 16px)
                target_h = 15 if h >= 21 else max(5, h - 4)
                top_pad = 4 if h >= 21 else 3
                grid = _squash_vertical(grid, target_h, top_pad, bg)
                top_y = top_pad
            elif fid == 15014:
                # 13px font: body typically y=1..9, leave y=0..2 for diacritics, body y=3..11 (9px shifted/squashed 1px)
                grid = _squash_vertical(grid, 9, 3, bg)
                top_y = 3
            elif fid in (15010, 15011):
                # 10px font: normal E is y=1..7 (7px) with 2 blank bottom rows; push down to y=2..8 (7px intact) or 2..7!
                grid = _squash_vertical(grid, 7, 2, bg)
                top_y = 2
            elif fid == 15002:
                # 11px font: E is y=0..9 (10px), shift/squash to 8px on y=2..9 so y=0..1 hold crisp 1px/2px accent
                grid = _squash_vertical(grid, 8, 2, bg)
                top_y = 2

    # Ensure shadow halo room if needed on left/right/top for 15002
    cx = max(1, (w - 1) // 2)
    accent_color = core if fid not in (15012, 15013) else ramp[-1]
    soft_color = ramp[max(0, len(ramp) // 2 - 1)]

    if kind in ("acute", "acute_dotless"):
        if big:
            # Diagonal acute stroke sitting comfortably above top_y
            ay = max(0, top_y - 3)
            for dx, dy in [(1, 0), (2, 0), (0, 1), (1, 1), (-1, 2), (0, 2)]:
                _draw_pixel(grid, cx + dx, ay + dy, accent_color)
            _draw_pixel(grid, cx, ay, soft_color, bg, only_if_bg=True)
            _draw_pixel(grid, cx + 2, ay + 1, soft_color, bg, only_if_bg=True)
        else:
            ay_bot = max(0, top_y - 2)
            if top_y <= 1:
                # Very tight (1px headroom): draw 2px diagonal at row 0..1
                _draw_pixel(grid, min(w - 1, cx + 1), 0, accent_color)
                _draw_pixel(grid, max(0, cx), 0, soft_color)
            else:
                _draw_pixel(grid, min(w - 1, cx + 1), max(0, ay_bot - 1), accent_color)
                _draw_pixel(grid, max(0, cx), ay_bot, accent_color)
                if ay_bot >= 2:
                    _draw_pixel(grid, min(w - 1, cx + 1), ay_bot - 1, accent_color)
    elif kind == "umlaut":
        if big:
            ay = max(0, top_y - 3)
            off = max(2, w // 4)
            for sx in (cx - off, cx + off):
                _draw_pixel(grid, sx, ay, accent_color)
                _draw_pixel(grid, sx + 1, ay, accent_color)
                _draw_pixel(grid, sx, ay + 1, accent_color)
                _draw_pixel(grid, sx + 1, ay + 1, accent_color)
        else:
            ay = max(0, top_y - 2)
            lx = max(0, cx - max(1, w // 4))
            rx = min(w - 1, cx + max(1, w // 4))
            if rx == lx and w >= 3:
                lx, rx = 0, w - 1
            _draw_pixel(grid, lx, ay, accent_color)
            _draw_pixel(grid, rx, ay, accent_color)
    elif kind == "tilde":
        if big:
            ay = max(0, top_y - 3)
            # Crisp 6-7px wave ~
            for dx, dy in [(-3, 1), (-2, 0), (-1, 0), (0, 1), (1, 1), (2, 0), (3, 0)]:
                _draw_pixel(grid, cx + dx, ay + dy, accent_color)
                _draw_pixel(grid, cx + dx, ay + dy + 1, soft_color, bg, only_if_bg=True)
        else:
            ay = max(0, top_y - 2)
            pts = [(-2, 1), (-1, 0), (0, 0), (1, 1), (2, 0)] if w >= 5 else [(-1, 0), (0, 1), (1, 0)]
            for dx, dy in pts:
                yy = max(0, min(top_y - 1 if top_y > 0 else 0, ay + dy))
                _draw_pixel(grid, cx + dx, yy, accent_color)

    if fid == 15002:
        _apply_halo_15002(grid, core, style["shadow"], bg)
    return grid


def extend_fonts(arc: blk0.Blk0Archive) -> tuple[dict[int, blk0.CbmpImage], dict[int, bytes]]:
    """Extend UI fonts 15002, 15010..15014 with Latin-1 Spanish glyphs inside their existing slot tables."""
    cbmps = {c.chunk_id: blk0.decode_cbmp(c.body) for c in arc.chunks if c.tag == "cbmp"}
    fonts = {c.chunk_id: blk0.decode_font(c.body) for c in arc.chunks if c.tag == "font"}

    new_cbmps: dict[int, blk0.CbmpImage] = {}
    new_fonts: dict[int, bytes] = {}

    for fid in (15002, 15010, 15011, 15012, 15013, 15014):
        f = fonts[fid]
        img = cbmps[f["cbmp_id"]]
        style = FONT_STYLES[fid]
        bg = style["bg"]

        gmap = {g["code"]: _extract_glyph(img.pixels, img.width, g) for g in f["glyphs"]}
        new_glyphs = [dict(g) for g in f["glyphs"]]
        extras: list[tuple[int, list[list[int]]]] = []
        extra_w = 0

        # For 15011 (dark shadowed duplicate of 15010), synthesize on 15010 geometry then remap indices cleanly
        if fid == 15011:
            img10 = cbmps[fonts[15010]["cbmp_id"]]
            gmap10 = {g["code"]: _extract_glyph(img10.pixels, img10.width, g) for g in fonts[15010]["glyphs"]}
            style10 = FONT_STYLES[15010]
            remap_10_to_11 = {0: 0, 64: 133, 68: 67, 73: 74}
            for code, base_ch, kind, _ in EXTRA_GLYPHS:
                if code in gmap:
                    continue
                base_grid = gmap10.get(ord(base_ch)) or gmap10[ord("?")]
                synth10 = _synthesize_glyph(15010, base_grid, kind, style10, gmap10)
                synth = [[remap_10_to_11.get(v, 133) for v in row] for row in synth10]
                gw = len(synth[0]) if synth else 1
                extras.append((code, synth))
                extra_w += gw + 1
        else:
            for code, base_ch, kind, _ in EXTRA_GLYPHS:
                if code in gmap:
                    continue
                base_code = ord(base_ch)
                base_grid = gmap.get(base_code) or gmap[ord("?")]
                synth = _synthesize_glyph(fid, base_grid, kind, style, gmap)
                gw = len(synth[0]) if synth else 1
                extras.append((code, synth))
                extra_w += gw + 1

        new_w = img.width + extra_w + 2
        sheet = bytearray([bg] * (new_w * img.height))
        for y in range(img.height):
            src_start = y * img.width
            dst_start = y * new_w
            sheet[dst_start : dst_start + img.width] = img.pixels[src_start : src_start + img.width]

        cursor_x = img.width + 1
        for code, grid in extras:
            gh = len(grid)
            gw = len(grid[0]) if gh else 1
            for dy in range(gh):
                for dx in range(gw):
                    sheet[dy * new_w + cursor_x + dx] = grid[dy][dx]
            new_glyphs.append(
                {
                    "code": code,
                    "advance": 0,
                    "x": cursor_x,
                    "y": 0,
                    "w": gw,
                    "h": gh,
                }
            )
            cursor_x += gw + 1

        new_img = blk0.CbmpImage(
            new_w,
            img.height,
            img.mode,
            img.pixel_format,
            img.field16,
            img.field20,
            bytes(sheet),
        )
        new_cbmps[f["cbmp_id"]] = new_img
        new_fonts[fid] = blk0.encode_font(
            f["cbmp_id"],
            f["default_spacing"],
            new_glyphs,
            pad=f["pad"],
            min_slots=f["slot_count"],
        )

    return new_cbmps, new_fonts


# ---------------- Pixel & Palette Helpers for UI Cbmps ----------------

class PaletteQuantizer:
    """Fast RGB -> nearest allowed palette index cache."""

    def __init__(self, palette: list[tuple[int, int, int]], allowed: Iterable[int]):
        self.allowed = list(dict.fromkeys(allowed))
        self.palette = palette
        self._cache: dict[tuple[int, int, int], int] = {}

    def map_rgb(self, rgb: tuple[int, int, int]) -> int:
        hit = self._cache.get(rgb)
        if hit is not None:
            return hit
        r, g, b = rgb
        best_idx = self.allowed[0]
        best_dist = 10**12
        for idx in self.allowed:
            pr, pg, pb = self.palette[idx]
            dr, dg, db = r - pr, g - pg, b - pb
            d = dr * dr * 3 + dg * dg * 4 + db * db * 2
            if d < best_dist:
                best_dist = d
                best_idx = idx
        self._cache[rgb] = best_idx
        return best_idx


class CanvasIdx:
    """Mutable 8-bit indexed bitmap helper wrapping CbmpImage."""

    def __init__(self, img: blk0.CbmpImage):
        self.w = img.width
        self.h = img.height
        self.mode = img.mode
        self.fmt = img.pixel_format
        self.f16 = img.field16
        self.f20 = img.field20
        self.px = bytearray(img.pixels)

    def get(self, x: int, y: int) -> int:
        return self.px[y * self.w + x]

    def put(self, x: int, y: int, val: int) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y * self.w + x] = val

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, val: int) -> None:
        for y in range(max(0, y0), min(self.h, y1)):
            start = y * self.w + max(0, x0)
            end = y * self.w + min(self.w, x1)
            if end > start:
                self.px[start:end] = bytes([val]) * (end - start)

    def restore_h_strips(self, x0: int, y0: int, x1: int, y1: int, clean_x_ranges: list[tuple[int, int]]) -> None:
        """Restore horizontal stripe/gradient rows by taking row mode from clean neighbor X columns."""
        for y in range(max(0, y0), min(self.h, y1)):
            samples = [self.px[y * self.w + cx] for a, b in clean_x_ranges for cx in range(a, b) if 0 <= cx < self.w]
            if not samples:
                continue
            val = Counter(samples).most_common(1)[0][0]
            self.fill_rect(x0, y, x1, y + 1, val)

    def inpaint_dark_mask(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        pal: list[tuple[int, int, int]],
        is_text_fn,
    ) -> None:
        """Replace pixels matching `is_text_fn(idx, pal[idx])` inside rect using nearest horizontal clean neighbors."""
        for y in range(max(0, y0), min(self.h, y1)):
            row = [self.px[y * self.w + x] for x in range(max(0, x0), min(self.w, x1))]
            bad = [is_text_fn(idx, pal[idx]) for idx in row]
            if all(bad):
                continue
            for i, is_b in enumerate(bad):
                if not is_b:
                    continue
                # search outward for nearest clean pixel
                rep = None
                for d in range(1, len(row)):
                    if i - d >= 0 and not bad[i - d]:
                        rep = row[i - d]
                        break
                    if i + d < len(row) and not bad[i + d]:
                        rep = row[i + d]
                        break
                if rep is not None:
                    self.px[y * self.w + x0 + i] = rep

    def blit_ttf(
        self,
        text: str,
        rect: tuple[int, int, int, int],
        ttf_name: str,
        max_size: int,
        fg_rgb: tuple[int, int, int],
        quantizer: PaletteQuantizer,
        pal: list[tuple[int, int, int]],
        *,
        align: str = "center",
        valign: str = "center",
        aa: bool = True,
        min_size: int = 7,
        bg_override: int | None = None,
        outline_idx: int | None = None,
        bold_x: int = 0,
    ) -> None:
        """Render text sized to fit cleanly inside `rect=(x0,y0,x1,y1)` blending over existing canvas pixels."""
        x0, y0, x1, y1 = rect
        rw, rh = max(1, x1 - x0), max(1, y1 - y0)

        font = load_ttf(ttf_name, max_size)
        for sz in range(max_size, min_size - 1, -1):
            f_try = load_ttf(ttf_name, sz)
            tmp = Image.new("L", (rw * 3, rh * 3), 0)
            dr = ImageDraw.Draw(tmp)
            bb = dr.textbbox((0, 0), text, font=f_try)
            tw, th = (bb[2] - bb[0]) + bold_x, bb[3] - bb[1]
            if tw <= rw and th <= rh:
                font = f_try
                break

        mask_img = Image.new("L", (rw, rh), 0)
        dr = ImageDraw.Draw(mask_img)
        if not aa:
            dr.fontmode = "1"
        bb = dr.textbbox((0, 0), text, font=font)
        tw, th = (bb[2] - bb[0]) + bold_x, bb[3] - bb[1]
        if align == "center":
            ox = (rw - tw) // 2 - bb[0]
        elif align == "right":
            ox = rw - tw - bb[0]
        else:
            ox = -bb[0]

        if valign == "center":
            oy = (rh - th) // 2 - bb[1]
        elif valign == "bottom":
            oy = rh - th - bb[1]
        else:
            oy = -bb[1]

        dr.text((ox, oy), text, fill=255, font=font)
        if bold_x > 0:
            dr.text((ox + 1, oy), text, fill=255, font=font)

        mpx = mask_img.tobytes()
        if outline_idx is not None:
            for py in range(rh):
                for px_x in range(rw):
                    if mpx[py * rw + px_x] >= 96:
                        continue
                    # 4-neighbor shadow/outline
                    has_nb = any(
                        0 <= px_x + dx < rw and 0 <= py + dy < rh and mpx[(py + dy) * rw + px_x + dx] >= 128
                        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
                    )
                    if has_nb:
                        self.put(x0 + px_x, y0 + py, outline_idx)

        fr, fg, fb = fg_rgb
        for py in range(rh):
            for px_x in range(rw):
                a = mpx[py * rw + px_x]
                if aa:
                    if a < 48:
                        continue
                    alpha = min(1.0, a / 255.0)
                else:
                    if a < 128:
                        continue
                    alpha = 1.0
                cx, cy = x0 + px_x, y0 + py
                if not (0 <= cx < self.w and 0 <= cy < self.h):
                    continue
                if alpha >= 0.88:
                    target_rgb = fg_rgb
                else:
                    bidx = bg_override if bg_override is not None else self.get(cx, cy)
                    br, bgc, bb_c = pal[bidx]
                    target_rgb = (
                        int(br * (1.0 - alpha) + fr * alpha),
                        int(bgc * (1.0 - alpha) + fg * alpha),
                        int(bb_c * (1.0 - alpha) + fb * alpha),
                    )
                self.put(cx, cy, quantizer.map_rgb(target_rgb))

    def blit_bitfont(
        self,
        text: str,
        x: int,
        y: int,
        font_data: dict,
        font_img: blk0.CbmpImage,
        *,
        transparent_bg: int = 0,
        remap: dict[int, int] | None = None,
        center_in_w: int | None = None,
    ) -> int:
        """Render string with one of Stdres's own BITFONT glyph tables."""
        gmap = {g["code"]: g for g in font_data["glyphs"]}
        sp_adv = max(1, font_data["default_spacing"])
        raw = text.encode("cp1252")
        total_w = 0
        for i, code in enumerate(raw):
            g = gmap.get(code) or gmap.get(32)
            if not g:
                continue
            step = g["advance"] if g["advance"] > 0 else (g["w"] + sp_adv)
            total_w += step if i < len(raw) - 1 else g["w"]
        cx = x + max(0, (center_in_w - total_w) // 2) if center_in_w is not None else x
        for code in raw:
            g = gmap.get(code) or gmap.get(32)
            if not g:
                continue
            if code != 32:
                for dy in range(g["h"]):
                    for dx in range(g["w"]):
                        v = font_img.pixels[(g["y"] + dy) * font_img.width + (g["x"] + dx)]
                        if v == transparent_bg:
                            continue
                        if remap and v in remap:
                            v = remap[v]
                        self.put(cx + dx, y + dy, v)
            cx += g["advance"] if g["advance"] > 0 else (g["w"] + sp_adv)
        return cx

    def to_cbmp(self) -> blk0.CbmpImage:
        return blk0.CbmpImage(self.w, self.h, self.mode, self.fmt, self.f16, self.f20, bytes(self.px))


# ---------------- Tiny crisp 3x5 / 4x6 Bitmap Microfont for tight HUD badges ----------------

MINI_3X5: dict[str, list[str]] = {
    "A": [".#.", "#.#", "###", "#.#", "#.#"],
    "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"],
    "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"],
    "F": ["###", "#..", "##.", "#..", "#.."],
    "G": [".##", "#..", "#.#", "#.#", ".##"],
    "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"],
    "J": ["..#", "..#", "..#", "#.#", ".#."],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"],
    "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#.#", "###", "###", "#.#", "#.#"],
    "N": ["#.#", "###", "###", "#.#", "#.#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."],
    "P": ["##.", "#.#", "##.", "#..", "#.."],
    "Q": [".#.", "#.#", "#.#", ".#.", "..#"],
    "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."],
    "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"],
    "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."],
    "Z": ["###", "..#", ".#.", "#..", "###"],
    ":": [".", "#", ".", "#", "."],
    ".": [".", ".", ".", ".", "#"],
    "/": ["..#", "..#", ".#.", "#..", "#.."],
    " ": [".", ".", "."],
}


def draw_mini_3x5(canvas: CanvasIdx, text: str, x: int, y: int, fg: int, *, spacing: int = 1, center_in_w: int | None = None) -> None:
    glyphs = [MINI_3X5.get(ch, MINI_3X5[" "]) for ch in text]
    total_w = sum(len(g[0]) for g in glyphs) + max(0, len(glyphs) - 1) * spacing
    cx = x + (center_in_w - total_w) // 2 if center_in_w is not None else x
    for g in glyphs:
        gw = len(g[0])
        for dy, row in enumerate(g):
            for dx, ch in enumerate(row):
                if ch == "#":
                    canvas.put(cx + dx, y + dy, fg)
        cx += gw + spacing


# ---------------- Localized Stdres UI Cbmp Builder ----------------

def _button_remap_pair(
    cbmps: dict[int, blk0.CbmpImage],
    ids: list[int],
    label: str,
    inner_rect: tuple[int, int, int, int],
    *,
    ttf: str = "arialnb",
    max_sz: int = 13,
    fg_idx: int = 133,
    bg_stripe_cols: list[tuple[int, int]] | None = None,
    pal: list[tuple[int, int, int]],
    quantizer: PaletteQuantizer,
    outline_idx: int | None = None,
) -> dict[int, blk0.CbmpImage]:
    out = {}
    x0, y0, x1, y1 = inner_rect
    for cid in ids:
        cv = CanvasIdx(cbmps[cid])
        if bg_stripe_cols:
            cv.restore_h_strips(x0, y0, x1, y1, bg_stripe_cols)
        else:
            # Clear dark text pixels using horizontal neighbor fill inside box
            cv.inpaint_dark_mask(x0, y0, x1, y1, pal, lambda idx, rgb: sum(rgb) < 120 or idx in (31, 32, 33, 133))
        cv.blit_ttf(label, inner_rect, ttf, max_sz, pal[fg_idx], quantizer, pal, aa=False if outline_idx is None else True, outline_idx=outline_idx)
        out[cid] = cv.to_cbmp()
    return out


def localize_ui_cbmps(
    arc: blk0.Blk0Archive,
    ext_cbmps: dict[int, blk0.CbmpImage],
    ext_fonts: dict[int, bytes],
) -> dict[int, blk0.CbmpImage]:
    """Generate localized Spanish versions of every English-text UI cbmp in Stdres.res."""
    pals = {c.chunk_id: blk0.decode_pal0(c.body) for c in arc.chunks if c.tag == "pal0"}
    cbmps = {c.chunk_id: blk0.decode_cbmp(c.body) for c in arc.chunks if c.tag == "cbmp"}
    fonts = {cid: blk0.decode_font(body) for cid, body in ext_fonts.items()}
    p20 = pals[20]
    p100 = pals[100]
    p6001 = pals[6001]
    p6002 = pals[6002]

    q_hud_green = PaletteQuantizer(p20, [133, 74, 71, 67, 68, 66, 65, 64])
    q_hud_black = PaletteQuantizer(p20, [133, 71, 67, 66])
    q_hud_steel = PaletteQuantizer(p20, [133, 103, 104, 105, 118, 119, 120, 121, 122, 114, 115, 116, 117, 97, 62, 134])
    q_hud_red = PaletteQuantizer(p20, [133, 85, 86, 81, 80, 79])
    q_start_btn = PaletteQuantizer(p100, [133, 71, 67, 65, 114, 115, 116, 117, 118, 120, 103, 105, 241])
    q_start_hdr = PaletteQuantizer(p100, [133, 102, 103, 105, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122])
    q_load_grn = PaletteQuantizer(p100, [133, 246, 232, 237, 25, 12, 13, 67, 65, 64])
    q_p6001_red = PaletteQuantizer(p6001, list(range(193, 206)))
    q_p6001_amb = PaletteQuantizer(p6001, [205, 204, 88, 91, 85, 83, 81, 79, 78, 77])
    q_p6002_grn = PaletteQuantizer(p6002, [0, 114, 188, 214, 215, 216, 217, 221, 223, 226])
    q_p6002_term = PaletteQuantizer(p6002, [113, 114, 188, 160, 182, 170, 255, 158])

    out: dict[int, blk0.CbmpImage] = {}

    # 1. Left HUD 6 tabs baked into 11110 (800x165) + individual 11117..11128 buttons (69x23)
    # Exact tab text row centers in 11110 are y = 26, 49, 73, 98, 122, 147 (inside 69x23 button frames)
    tab_defs = [
        (26, "EQUIPO", 11117, 11118),
        (49, "ARMAS", 11119, 11120),
        (73, "COMUN.", 11121, 11122),
        (98, "OBJETOS", 11125, 11126),
        (122, "METAS", 11123, 11124),
        (147, "MENÚ", 11127, 11128),
    ]
    cv10 = CanvasIdx(cbmps[11110])
    for yc, label, id_dark, id_lit in tab_defs:
        cv10.restore_h_strips(9, yc - 5, 64, yc + 6, [(6, 9), (64, 66)])
        cv10.blit_ttf(label, (9, yc - 6, 62, yc + 7), "arialnb", 11, p20[134], q_hud_steel, p20, aa=True)

        for cid, fg in ((id_dark, p20[97]), (id_lit, p20[134])):
            cv = CanvasIdx(cbmps[cid])
            cv.restore_h_strips(8, 4, 62, 18, [(5, 8), (62, 65)])
            cv.blit_ttf(label, (8, 4, 62, 18), "arialnb", 11, fg, q_hud_steel, p20, aa=True)
            out[cid] = cv.to_cbmp()
    out[11110] = cv10.to_cbmp()

    # 2. 11111 Crew Stats Panel (ATTACK, STRENGTH, DEFENSE, HEALTH, REACTION)
    cv11 = CanvasIdx(cbmps[11111])
    stat_rows = [
        ((308, 7, 393, 20), "ATAQUE"),
        ((308, 22, 393, 35), "FUERZA"),
        ((308, 37, 393, 50), "DEFENSA"),
        ((308, 52, 393, 65), "SALUD"),
    ]
    for box, txt in stat_rows:
        cv11.fill_rect(*box, 133)
        cv11.blit_ttf(txt, box, "arialn", 10, p20[67], q_hud_green, p20, align="left", aa=True)
    # REACTION box at (261, 92, 306, 102)
    cv11.fill_rect(261, 92, 306, 102, 133)
    draw_mini_3x5(cv11, "REACC.", 261, 95, 67, spacing=1, center_in_w=45)
    out[11111] = cv11.to_cbmp()

    # 3. 11114 Overview status bar: preserve exact box holes
    cv14 = CanvasIdx(cbmps[11114])
    bar14_items = [
        ((10, 88, 60, 103), "Aliens:", "left"),
        ((99, 88, 192, 103), "Sin desc.:", "right"),
        ((211, 88, 241, 103), "Equip.", "right"),
        ((267, 88, 322, 103), "Armas", "right"),
        ((347, 88, 391, 103), "Objetos", "right"),
    ]
    for box, txt, al in bar14_items:
        cv14.fill_rect(*box, 67)
        cv14.blit_ttf(txt, (box[0], box[1] - 1, box[2], box[3]), "arialnb", 11, p20[133], q_hud_black, p20, align=al, aa=False)
    out[11114] = cv14.to_cbmp()

    # 4. 11115 Options panel: Float Weapons / Show Subtitles / Track
    cv15 = CanvasIdx(cbmps[11115])
    cv15.fill_rect(54, 49, 159, 77, 133)
    cv15.blit_bitfont("Armas flotantes", 56, 48, fonts[15014], ext_cbmps[15014], transparent_bg=133, remap={66: 134, 67: 97, 71: 74, 68: 62})
    cv15.blit_bitfont("Ver subtítulos", 56, 63, fonts[15014], ext_cbmps[15014], transparent_bg=133, remap={66: 134, 67: 97, 71: 74, 68: 62})
    cv15.fill_rect(161, 56, 209, 70, 67)
    cv15.blit_ttf("Pista", (161, 55, 209, 71), "arialnb", 11, p20[133], q_hud_black, p20, aa=False)
    out[11115] = cv15.to_cbmp()

    # 5. 11129 FIGHT / HIDE / GUARD matrix (108x52 = 4 strips of 13px)
    cv29 = CanvasIdx(cbmps[11129])
    cells29 = [(2, 35, "LUCHA"), (37, 67, "OCULT."), (69, 106, "GUARD.")]
    for row_i in range(4):
        ry0 = row_i * 13
        ry1 = ry0 + 13
        for col_i, (cx0, cx1, word) in enumerate(cells29):
            is_active = (row_i == col_i + 1)
            fg = 133 if is_active else 114
            if is_active:
                cv29.fill_rect(cx0 + 1, ry0 + 2, cx1 - 1, ry1 - 2, 66)
                draw_mini_3x5(cv29, word, cx0 + 1, ry0 + 4, fg, spacing=1, center_in_w=(cx1 - cx0 - 2))
            else:
                cv29.restore_h_strips(cx0 + 1, ry0 + 2, cx1 - 1, ry1 - 2, [(cx0 + 1, cx0 + 2), (cx1 - 2, cx1 - 1)])
                draw_mini_3x5(cv29, word, cx0 + 1, ry0 + 4, fg, spacing=1, center_in_w=(cx1 - cx0 - 2))
    out[11129] = cv29.to_cbmp()

    # 6. 11150 Radar crest (109x747 = 9 frames of 109x83): bottom strip y=77..82
    cv150 = CanvasIdx(cbmps[11150])
    for fi in range(9):
        by = fi * 83 + 76
        cv150.fill_rect(0, by, 109, by + 7, 0)
        draw_mini_3x5(cv150, "CLIC PARA CERRAR", 0, by + 1, 66, spacing=1, center_in_w=109)
    out[11150] = cv150.to_cbmp()

    # 7. Volume sliders 11151..11154 + Stat meters 11170..11173
    # NOTE: 11151 & 11153 are bright green striped bars with black text (133);
    #       11152 & 11154 are black interior bars (133) with white/silver text (134)!
    for cid, label in ((11151, "Volumen de música"), (11153, "Volumen general")):
        cv = CanvasIdx(cbmps[cid])
        cv.restore_h_strips(12, 2, cv.w - 12, cv.h - 2, [(6, 12), (cv.w - 12, cv.w - 6)])
        cv.blit_ttf(label, (12, 1, cv.w - 12, cv.h - 1), "arialbd", 12, p20[133], q_hud_black, p20, aa=False)
        out[cid] = cv.to_cbmp()
    for cid, label in ((11152, "Volumen de música"), (11154, "Volumen general")):
        cv = CanvasIdx(cbmps[cid])
        cv.fill_rect(12, 3, cv.w - 12, cv.h - 3, 133)
        cv.blit_ttf(label, (12, 1, cv.w - 12, cv.h - 1), "arialbd", 12, p20[134], q_hud_steel, p20, aa=True)
        out[cid] = cv.to_cbmp()

    for cid, label in ((11170, "FUERZA"), (11171, "ATAQUE"), (11172, "DEFENSA"), (11173, "SALUD")):
        cv = CanvasIdx(cbmps[cid])
        cv.restore_h_strips(4, 2, cv.w - 4, cv.h - 2, [(cv.w - 22, cv.w - 4)])
        cv.blit_ttf(label, (6, 0, cv.w - 6, cv.h), "arialn", 10, p20[133], q_hud_black, p20, align="left", aa=False)
        out[cid] = cv.to_cbmp()

    # 8. Vertical LIFE FORCE bars 11177 (black bg + white rotated text) & 11178 (red bar + black rotated text)
    for cid, is_red in ((11177, False), (11178, True)):
        cv = CanvasIdx(cbmps[cid])
        if is_red:
            for x in range(5, 18):
                col_s = [cv.get(x, cy) for cy in (4, 5, 6, 95, 96, 97)]
                col_val = Counter(col_s).most_common(1)[0][0]
                cv.fill_rect(x, 7, x + 1, 94, col_val)
            fg_rgb, qz, do_aa = p20[133], q_hud_red, False
        else:
            cv.fill_rect(4, 6, 19, 95, 133)
            fg_rgb, qz, do_aa = p20[134], q_hud_steel, True
        tmp = Image.new("L", (86, 15), 0)
        tdr = ImageDraw.Draw(tmp)
        if not do_aa:
            tdr.fontmode = "1"
        f_lf = load_ttf("arialbd", 12)
        bb = tdr.textbbox((0, 0), "VITALIDAD", font=f_lf)
        ox = (86 - (bb[2] - bb[0])) // 2 - bb[0]
        oy = (15 - (bb[3] - bb[1])) // 2 - bb[1]
        tdr.text((ox, oy), "VITALIDAD", fill=255, font=f_lf)
        rot = tmp.rotate(90, expand=True)
        rpx = rot.tobytes()
        for ry in range(86):
            for rx in range(15):
                a = rpx[ry * 15 + rx]
                if (do_aa and a >= 64) or (not do_aa and a >= 128):
                    alpha = 1.0 if not do_aa or a >= 200 else a / 255.0
                    cx, cy = 4 + rx, 7 + ry
                    br, bgc, bbc = p20[cv.get(cx, cy)]
                    tr = (int(br * (1 - alpha) + fg_rgb[0] * alpha), int(bgc * (1 - alpha) + fg_rgb[1] * alpha), int(bbc * (1 - alpha) + fg_rgb[2] * alpha))
                    cv.put(cx, cy, qz.map_rgb(tr))
        out[cid] = cv.to_cbmp()

    # 9. Menu/Dialog green buttons: replace every non-bright-green pixel inside safe button core with fill 66
    green_btns = [
        ([11180, 11181], "SALIR", (4, 3, 55, 17)),
        ([11182, 11183], "GUARDAR", (3, 3, 56, 17)),
        ([11184, 11185], "CARGAR", (3, 3, 56, 17)),
        ([11195, 11196], "AYUDA", (4, 3, 55, 17)),
        ([11241, 11242], "ACEPTAR", (4, 3, 55, 17)),
        ([11243, 11244], "CANCEL.", (4, 3, 55, 17)),
        ([11245, 11246], "BORRAR", (9, 3, 50, 16)),
        ([11251, 11252], "ENVIAR", (4, 2, 55, 14)),
    ]
    for ids, lbl, box in green_btns:
        x0, y0, x1, y1 = box
        for cid in ids:
            cv = CanvasIdx(cbmps[cid])
            for y in range(y0, y1):
                for x in range(x0, x1):
                    if cv.get(x, y) not in (64, 65, 66, 67):
                        cv.put(x, y, 66)
            # Clear bottom 1px dark edge residue of DELETE/QUIT/SEND inside safe central x
            if cid in (11245, 11246):
                for y in range(6, y1):
                    for x in range(5, x1):
                        if cv.get(x, y) not in (64, 65, 66, 67):
                            cv.put(x, y, 66)
            cv.blit_ttf(lbl, box, "arialnb", 11, p20[133], q_hud_black, p20, aa=False)
            out[cid] = cv.to_cbmp()

    # 10. Mini reaction icon squares 11213..11218 (13x13) & reaction toggle buttons 11223..11230
    for ids, letter in (([11213, 11214], "L"), ([11215, 11216], "G"), ([11217, 11218], "O")):
        for idx_i, cid in enumerate(ids):
            cv = CanvasIdx(cbmps[cid])
            bg_c = 67 if idx_i == 0 else 114
            cv.fill_rect(3, 3, 10, 10, bg_c)
            cv.blit_ttf(letter, (2, 2, 11, 11), "arialbd", 8, p20[133], q_hud_black, p20, aa=False)
            out[cid] = cv.to_cbmp()

    react_btns = [
        (11223, 11224, "LUCHA", 34),
        (11225, 11226, "GUARD.", 36),
        (11227, 11228, "OCULT.", 31),
        (11229, 11230, "NADA", 31),
    ]
    for cid_dark, cid_grn, lbl, w_btn in react_btns:
        cv_d = CanvasIdx(cbmps[cid_dark])
        cv_d.restore_h_strips(2, 2, w_btn - 2, 9, [(1, 2), (w_btn - 2, w_btn - 1)])
        draw_mini_3x5(cv_d, lbl, 2, 3, 114, spacing=1, center_in_w=w_btn - 4)
        out[cid_dark] = cv_d.to_cbmp()

        cv_g = CanvasIdx(cbmps[cid_grn])
        cv_g.fill_rect(2, 2, w_btn - 2, 9, 66)
        draw_mini_3x5(cv_g, lbl, 2, 3, 133, spacing=1, center_in_w=w_btn - 4)
        out[cid_grn] = cv_g.to_cbmp()

    # 11. Weapon Range strips 11202 & 11203 (10 frames of 70x100)
    cv202 = CanvasIdx(cbmps[11202])
    cv203 = CanvasIdx(cbmps[11203])
    for f in range(10):
        fy = f * 100
        cv202.fill_rect(31, fy + 2, 67, fy + 12, 133)
        draw_mini_3x5(cv202, "ALCANCE", 31, fy + 4, 67, spacing=1, center_in_w=36)
        cv203.fill_rect(35, fy + 3, 64, fy + 13, 71)
        draw_mini_3x5(cv203, "RANGO", 35, fy + 5, 134, spacing=1, center_in_w=29)
    out[11202] = cv202.to_cbmp()
    out[11203] = cv203.to_cbmp()

    # 12. Start & Multiplayer Menu buttons 11302..11333 (pal 100)
    # Clamp boxes inside safe flat button polygons so no letter ever crosses dark/magenta curved bevels,
    # and clean strictly to pure green (idx 65) or brushed steel (idx 114,115,116) per interior scanline.
    start_btns = [
        (11302, 11303, "UN JUGADOR", (30, 12, 204, 43), (30, 236)),
        (11305, 11306, "MULTIJUGADOR", (18, 12, 196, 43), (18, 222)),
        (11308, 11309, "CARGAR PARTIDA", (18, 12, 200, 43), (16, 212)),
        (11311, 11312, "SALIR DEL JUEGO", (24, 12, 198, 43), (22, 218)),
        (11314, 11315, "CREAR PARTIDA", (15, 12, 180, 43), (12, 184)),
        (11322, 11323, "ATRÁS", (48, 12, 128, 43), (48, 134)),
        (11324, 11325, "INICIAR", (64, 12, 140, 43), (64, 140)),
        (11330, 11331, "PUERTO SERIE", (26, 12, 208, 43), (24, 216)),
        (11332, 11333, "MÓDEM", (18, 12, 192, 43), (16, 206)),
    ]
    clean_steel = (114, 115, 116)
    for cid_ev, cid_od, lbl, box, (cx0, cx1) in start_btns:
        # Even (green idx 65 flat interior)
        cv_e = CanvasIdx(cbmps[cid_ev])
        for y in range(13, 42):
            greens = [x for x in range(max(8, cx0), min(cv_e.w - 8, cx1)) if cv_e.get(x, y) == 65]
            if len(greens) >= 2:
                gx0, gx1 = max(cx0, greens[0]), min(cx1, greens[-1] + 1)
                for x in range(gx0, gx1):
                    if cv_e.get(x, y) not in (65, 0):
                        cv_e.put(x, y, 65)
        cv_e.blit_ttf(lbl, box, "arialnb", 19, p100[133], q_start_btn, p100, aa=True)
        out[cid_ev] = cv_e.to_cbmp()

        # Odd (brushed steel idx 114,115,116 interior — remove 112/113/117..120 ghost text AA completely)
        cv_o = CanvasIdx(cbmps[cid_od])
        for y in range(13, 42):
            steels = [x for x in range(max(8, cx0), min(cv_o.w - 8, cx1)) if cv_o.get(x, y) in clean_steel]
            if len(steels) >= 2:
                sx0, sx1 = max(cx0, steels[0] + 1), min(cx1, steels[-1])
                orig_row = [cv_o.get(x, y) for x in range(cv_o.w)]
                for x in range(sx0, sx1):
                    if orig_row[x] not in clean_steel and orig_row[x] != 0:
                        rep = 115
                        for d in range(1, 55):
                            if x - d >= sx0 and orig_row[x - d] in clean_steel:
                                rep = orig_row[x - d]
                                break
                            if x + d < sx1 and orig_row[x + d] in clean_steel:
                                rep = orig_row[x + d]
                                break
                        cv_o.put(x, y, rep)
        cv_o.blit_ttf(lbl, box, "arialnb", 19, p100[133], q_start_btn, p100, aa=True)
        out[cid_od] = cv_o.to_cbmp()

    # 13. Animated Multiplayer headers 11404..11409 (21 frames each)
    # Frame 0 holds the clean text-free wireframe background for every pixel changed by the fade-in!
    anim_specs = [
        (11404, 51, "ELIGE PARTIDA.", (14, 12, 210, 38)),
        (11405, 52, "ELIGE PROVEEDOR.", (6, 10, 210, 38)),
        (11406, 52, "POR FAVOR ELIGE.", (6, 10, 210, 38)),
        (11407, 51, "INGRESA NÚMERO.", (24, 12, 274, 38)),
        (11408, 51, "INGRESA DIRECCIÓN.", (24, 12, 274, 38)),
        (11409, 52, "INGRESA NOMBRE.", (6, 10, 210, 38)),
    ]
    for cid, fh, lbl, box in anim_specs:
        src_m = cbmps[cid]
        cv = CanvasIdx(src_m)
        w = src_m.width
        x0, y0, x1, y1 = box
        last_base = 20 * fh
        letter_px = [
            (x, y)
            for y in range(fh)
            for x in range(w)
            if src_m.pixels[(last_base + y) * w + x] != src_m.pixels[y * w + x]
        ]

        t_mask = Image.new("L", (x1 - x0, y1 - y0), 0)
        tdr = ImageDraw.Draw(t_mask)
        font_sz = 20
        f_hdr = load_ttf("arialnb", font_sz)
        while font_sz > 10:
            f_hdr = load_ttf("arialnb", font_sz)
            bb = tdr.textbbox((0, 0), lbl, font=f_hdr)
            if bb[2] - bb[0] <= (x1 - x0) - 4:
                break
            font_sz -= 1
        bb = tdr.textbbox((0, 0), lbl, font=f_hdr)
        tdr.text(((x1 - x0 - (bb[2] - bb[0])) // 2 - bb[0], (y1 - y0 - (bb[3] - bb[1])) // 2 - bb[1]), lbl, fill=255, font=f_hdr)
        tbytes = t_mask.tobytes()

        for f in range(21):
            fy = f * fh
            orig_lums = [sum(p100[src_m.pixels[(fy + ly) * w + lx]]) / 3.0 for (lx, ly) in letter_px]
            ref_lums = [sum(p100[src_m.pixels[(last_base + ly) * w + lx]]) / 3.0 for (lx, ly) in letter_px]
            ratio = min(1.0, (statistics.mean(orig_lums) / max(1.0, statistics.mean(ref_lums)))) if orig_lums else (f / 20.0)
            if f == 0:
                ratio = 0.0

            # Restore pure Frame 0 pixel wherever any frame altered a text pixel
            for y in range(fh):
                for x in range(w):
                    if src_m.pixels[(fy + y) * w + x] != src_m.pixels[y * w + x]:
                        cv.put(x, fy + y, src_m.pixels[y * w + x])

            if f >= 1:
                tw, th = x1 - x0, y1 - y0
                for dy in range(th):
                    vert_shade = 0.85 + 0.15 * math.sin((dy / max(1, th - 1)) * math.pi)
                    for dx in range(tw):
                        a = tbytes[dy * tw + dx]
                        if a < 52:
                            continue
                        px_x, px_y = x0 + dx, fy + y0 + dy
                        base_rgb = (128, 134, 178)
                        alpha = (a / 255.0) * min(1.0, ratio * 1.15)
                        if alpha < 0.08:
                            continue
                        br, bgc, bbc = p100[cv.get(px_x, px_y)]
                        fr = int(base_rgb[0] * vert_shade)
                        fgc = int(base_rgb[1] * vert_shade)
                        fbc = int(base_rgb[2] * vert_shade)
                        tr = (int(br * (1 - alpha) + fr * alpha), int(bgc * (1 - alpha) + fgc * alpha), int(bbc * (1 - alpha) + fbc * alpha))
                        cv.put(px_x, px_y, q_start_hdr.map_rgb(tr))
        out[cid] = cv.to_cbmp()

    # 14. Loading screen elements 16011, 16018, 16019, 16020 (pal 100)
    cv611 = CanvasIdx(cbmps[16011])
    # Erase LOAD SEQUENCE INITIATED strictly right of the curved emblem (x >= 211) OR green pixels inside 185..455
    for y in range(0, 32):
        for x in range(185, 455):
            idx = cv611.get(x, y)
            r, g, b = p100[idx]
            if (g > r + 20 and g > b + 20 and idx != 0) or (x >= 211 and y < 29 and idx in (133, 246, 237)):
                cv611.put(x, y, 0)
    cv611.blit_ttf("SECUENCIA DE CARGA INICIADA", (212, 2, 482, 26), "arialnb", 20, p100[65], q_load_grn, p100, aa=True, bg_override=133, outline_idx=133)
    out[16011] = cv611.to_cbmp()

    load_boxes = [
        (16018, (505, 22, 695, 50), ["Invertir polos D-el.", "Fijar Gimb Oid 1002b"]),
        (16019, (414, 38, 557, 64), ["Eco GSA detectado.", "Flujo de datos listo."]),
        (16020, (405, 62, 554, 77), ["Ds 33%, nivel estable."]),
    ]
    for cid, (bx0, by0, bx1, by1), lines in load_boxes:
        cv = CanvasIdx(cbmps[cid])
        cv.fill_rect(bx0, by0, bx1, by1, 133)
        lh = (by1 - by0) // len(lines)
        for li, line in enumerate(lines):
            cv.blit_ttf(line, (bx0 + 3, by0 + li * lh + 1, bx1 - 2, by0 + (li + 1) * lh), "consola", 10, p100[65], q_load_grn, p100, align="left", aa=True)
        out[cid] = cv.to_cbmp()

    # 15. Defeat Screen 6001 (pal 6001) & Victory Screen 6002 (pal 6002)
    cv6001 = CanvasIdx(cbmps[6001])
    cv6001.fill_rect(10, 2, 222, 72, 0)
    cv6001.blit_ttf("EMERGENCIA", (10, 4, 218, 42), "arialbd", 24, p6001[193], q_p6001_red, p6001, aa=True)
    cv6001.blit_ttf("BASE INVADIDA", (10, 44, 218, 69), "arialbd", 15, p6001[193], q_p6001_red, p6001, aa=True)
    cv6001.fill_rect(101, 72, 226, 214, 0)
    para_6001 = [
        "Contacto con Tyranny Prime.",
        "Sin señal de los colonos.",
        "Lecturas biológicas críticas.",
        "Es una colmena completa.",
        "",
        "Ya no pueden hacer nada allí.",
        "Retírense de inmediato.",
        "Es una orden.",
        "",
        "Retirada general en todo el",
        "sector. Reagrupar en",
        "Havenpoint en dos días, 23:00.",
    ]
    for li, line in enumerate(para_6001):
        if line:
            cv6001.blit_ttf(line, (101, 73 + li * 11, 225, 85 + li * 11), "arialn", 9, p6001[194], q_p6001_red, p6001, align="left", aa=True)

    # Amber tablet: erase ONLY amber text pixels next to blonde hair (228..247), solid clear right of 247!
    cv6001.inpaint_dark_mask(226, 353, 248, 396, p6001, lambda idx, rgb: 75 <= idx <= 95)
    cv6001.fill_rect(247, 353, 326, 396, 205)
    cv6001.fill_rect(210, 397, 326, 495, 205)
    amb_lines = [
        (249, 354, "Transcribiendo."),
        (249, 368, "¿Hay alguien ahí?"),
        (249, 379, ">Son demasiados."),
        (225, 398, ">¿Hola?"),
        (224, 409, ">Colonia TFB2."),
        (223, 419, ">Repito."),
        (222, 429, ">Colonia TFB2."),
        (221, 439, ">Bajo ataque."),
        (220, 449, ">¿Alguien puede"),
        (219, 459, " ayudarnos?"),
        (215, 474, ">Perdimos conta"),
    ]
    for lx, ly, line in amb_lines:
        cv6001.blit_ttf(line, (lx, ly, 326, ly + 12), "arialn", 9, p6001[77], q_p6001_amb, p6001, align="left", aa=True)
    out[6001] = cv6001.to_cbmp()

    cv6002 = CanvasIdx(cbmps[6002])
    # Top-left green scan: erase green text AND green-over-blue flare pixels (where G > B - 4 and G > R + 12) keeping pure blue lens flare intact!
    cv6002.inpaint_dark_mask(
        116, 22, 240, 220, p6002,
        lambda idx, rgb: (214 <= idx <= 228) or (rgb[1] > rgb[2] - 4 and rgb[1] > rgb[0] + 15 and idx != 114 and idx != 0),
    )
    scan_lines = [
        (24, 9, "ESCANEO DEL SECTOR"),
        (44, 8, "Ataques extraterrestres en"),
        (55, 8, "colonias cercanas. Datos de"),
        (66, 8, "inteligencia escasos."),
        (84, 8, "Fuerzas marinas al 42%."),
        (95, 8, "Solicitar apoyo del"),
        (106, 8, "USS Andromeda."),
        (117, 8, "Fin del mensaje."),
    ]
    for ly, fsz, line in scan_lines:
        cv6002.blit_ttf(line, (122, ly, 236, ly + 13), "arialn", fsz, p6002[221], q_p6002_grn, p6002, align="left", aa=True)
    cv6002.fill_rect(0, 152, 114, 214, 0)
    cv6002.blit_ttf("199 Reco. Gamga", (2, 160, 108, 172), "arialn", 8, p6002[221], q_p6002_grn, p6002, align="left", aa=True)
    cv6002.blit_ttf("presente.", (2, 178, 108, 190), "arialn", 8, p6002[221], q_p6002_grn, p6002, align="left", aa=True)
    cv6002.blit_ttf("17 en fase Molek 2", (2, 196, 108, 208), "arialn", 8, p6002[221], q_p6002_grn, p6002, align="left", aa=True)

    # Bottom-left ALIEN PRESENCE TERMINATED glowing tablet: erase white text + bright phosphor halo (>=430 RGB sum)
    # and reconstruct smooth oval green CRT glow from nearby clean green-pad pixels only (never dark bezel 0/114).
    orig6002 = bytes(cv6002.px)
    offsets_2d = sorted(
        [(dx, dy) for dy in range(-10, 11) for dx in range(-10, 11) if dx or dy],
        key=lambda d: d[0] * d[0] + d[1] * d[1],
    )
    def _is_pad_bg(idx: int) -> bool:
        r, g, b = p6002[idx]
        return g > r + 25 and 160 <= (r + g + b) < 430

    for y in range(346, 396):
        for x in range(142, 270):
            idx = orig6002[y * cv6002.w + x]
            if idx in (255, 129) or sum(p6002[idx]) >= 430:
                samples = []
                for dx, dy in offsets_2d:
                    nx, ny = x + dx, y + dy
                    if 142 <= nx < 270 and 344 <= ny < 398:
                        nidx = orig6002[ny * cv6002.w + nx]
                        if _is_pad_bg(nidx):
                            samples.append(nidx)
                            if len(samples) >= 5:
                                break
                if samples:
                    cv6002.put(x, y, Counter(samples).most_common(1)[0][0])
    cv6002.blit_ttf("PRESENCIA ALIENÍGENA", (142, 348, 268, 374), "arialbd", 13, p6002[255], q_p6002_term, p6002, aa=True)
    cv6002.blit_ttf("EXTERMINADA", (142, 374, 268, 400), "arialbd", 13, p6002[255], q_p6002_term, p6002, aa=True)
    out[6002] = cv6002.to_cbmp()

    return out


def save_previews(arc: blk0.Blk0Archive, ext_cbmps: dict[int, blk0.CbmpImage], ui_cbmps: dict[int, blk0.CbmpImage], out_dir: Path) -> None:
    """Export zoomed visual verification sheets for extended fonts and localized UI cbmps."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pals = {c.chunk_id: blk0.decode_pal0(c.body) for c in arc.chunks if c.tag == "pal0"}
    p20, p100, p6001, p6002 = pals[20], pals[100], pals[6001], pals[6002]

    # 1. Extended fonts sheet (3x zoom on tail showing all newly synthesized Spanish glyphs + neighbors)
    f_tiles = []
    for cid, im in sorted(ext_cbmps.items()):
        tail_x = max(0, im.width - 280)
        pil = im.to_image(p20).convert("RGB").crop((tail_x, 0, im.width, im.height))
        f_tiles.append((cid, pil.resize((pil.width * 3, pil.height * 3), Image.NEAREST)))
    fw = max(t[1].width for t in f_tiles) + 20
    fh = sum(t[1].height + 22 for t in f_tiles) + 12
    fcanvas = Image.new("RGB", (fw, fh), (34, 34, 42))
    fdr = ImageDraw.Draw(fcanvas)
    yy = 6
    for cid, im in f_tiles:
        fdr.text((8, yy), f"Extended font cbmp {cid}", fill=(255, 255, 150))
        fcanvas.paste(im, (8, yy + 14))
        yy += im.height + 22
    fcanvas.save(out_dir / "fonts_extended_tail_3x.png")

    # 2. HUD localized cbmps (pal 20)
    hud_ids = sorted(cid for cid in ui_cbmps if 11110 <= cid < 11300)
    _save_grid(ui_cbmps, hud_ids, p20, out_dir / "ui_hud_es_pal20.png", scale=2, max_w=960)

    # 3. Start / Multi buttons & last frames of 11404..11409 (pal 100)
    start_ids = sorted(cid for cid in ui_cbmps if 11300 <= cid < 11400)
    tiles = []
    for cid in start_ids:
        pil = ui_cbmps[cid].to_image(p100).convert("RGB")
        tiles.append((cid, pil))
    for cid in range(11404, 11410):
        if cid in ui_cbmps:
            m = ui_cbmps[cid]
            fh_frame = m.height // 21
            pil = m.to_image(p100).convert("RGB").crop((0, 20 * fh_frame, m.width, m.height))
            tiles.append((cid, pil))
    _save_tiles(tiles, out_dir / "ui_start_es_pal100.png", max_w=960)

    # 4. Loading banners (pal 100) + End screens (6001/6002)
    load_tiles = []
    for cid, box in [(16011, (160, 0, 486, 55)), (16018, (490, 10, 699, 53)), (16019, (395, 25, 559, 65)), (16020, (385, 45, 556, 78))]:
        pil = ui_cbmps[cid].to_image(p100).convert("RGB").crop(box)
        load_tiles.append((cid, pil.resize((pil.width * 2, pil.height * 2), Image.NEAREST)))
    _save_tiles(load_tiles, out_dir / "ui_loading_es_pal100.png", max_w=900)

    ui_cbmps[6001].to_image(p6001).convert("RGB").crop((0, 0, 360, 540)).save(out_dir / "ui_6001_es.png")
    ui_cbmps[6002].to_image(p6002).convert("RGB").crop((0, 0, 300, 440)).save(out_dir / "ui_6002_es.png")


def _save_grid(cbmps: dict[int, blk0.CbmpImage], ids: list[int], pal: list[tuple[int, int, int]], path: Path, scale: int = 1, max_w: int = 1000) -> None:
    tiles = []
    for cid in ids:
        m = cbmps[cid]
        pil = m.to_image(pal).convert("RGB")
        if pil.height > 200:
            pil = pil.crop((0, 0, pil.width, 100))
        if scale != 1 and pil.width * scale <= max_w - 20:
            pil = pil.resize((pil.width * scale, pil.height * scale), Image.NEAREST)
        tiles.append((cid, pil))
    _save_tiles(tiles, path, max_w=max_w)


def _save_tiles(tiles: list[tuple[int, Image.Image]], path: Path, max_w: int = 1000) -> None:
    if not tiles:
        return
    rows = []
    cur, cw, ch = [], 10, 0
    for cid, pil in tiles:
        if cur and cw + pil.width + 12 > max_w:
            rows.append((cur, ch))
            cur, cw, ch = [], 10, 0
        cur.append((cid, pil))
        cw += pil.width + 12
        ch = max(ch, pil.height)
    if cur:
        rows.append((cur, ch))
    tot_h = sum(rh + 24 for _, rh in rows) + 12
    canvas = Image.new("RGB", (max_w, tot_h), (34, 34, 42))
    dr = ImageDraw.Draw(canvas)
    y = 8
    for row, rh in rows:
        x = 10
        for cid, pil in row:
            dr.text((x, y), str(cid), fill=(255, 255, 140))
            canvas.paste(pil, (x, y + 14))
            x += pil.width + 12
        y += rh + 24
    canvas.save(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate extended Spanish fonts and UI cbmps for Stdres.res")
    ap.add_argument("--src", type=Path, default=Path(r"C:\Program Files (x86)\Enemy Infestation\Stdres.res"))
    ap.add_argument("--preview-dir", type=Path, default=ROOT / "analysis" / "ui_loc_preview")
    args = ap.parse_args(argv)

    arc = blk0.Blk0Archive(args.src)
    ext_cbmps, ext_fonts = extend_fonts(arc)
    ui_cbmps = localize_ui_cbmps(arc, ext_cbmps, ext_fonts)
    save_previews(arc, ext_cbmps, ui_cbmps, args.preview_dir)
    print(f"Generated {len(ext_fonts)} extended fonts, {len(ext_cbmps)} font cbmps, {len(ui_cbmps)} localized UI cbmps.")
    print(f"Previews saved to {args.preview_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
