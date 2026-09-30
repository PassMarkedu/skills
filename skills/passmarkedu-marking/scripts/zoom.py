"""Zoomed crops: a small budget per paper, and boxes cut to a size that shows more than the tiles.

Owner 2026-09-29: a slow model spent 38 of 56 minutes on 18 zooms. A paper gets ZOOM_LIMIT
zoomed regions; a doubt beyond that is judged from the tiles with low confidence and goes on
the review list. One requested region is one unit of the budget, however many pieces a box
too large for one zoom is cut into.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from common import WorkflowError, digest, read
from rendering import MAX_DPI, crop_dpi

ZOOM_LIMIT = 4
MAX_SHARE = 0.5  # a zoom covers at most half the page width and half its height
OVERLAP = 0.02  # neighbouring pieces of a cut box share this much of the page, so no symbol is cut in half
MAX_PIECES = 4
SHARPER = 1.3  # a zoom renders at least this many times the tile resolution, or it shows nothing new
LEDGER = 'zooms.json'


def _count(length: float) -> int:
    n = 1
    while (length + (n - 1) * OVERLAP) / n > MAX_SHARE + 1e-9:
        n += 1
    return n


def _edges(start: float, length: float, n: int) -> list[tuple[float, float]]:
    part = (length + (n - 1) * OVERLAP) / n if n > 1 else length
    edges = [(start + i * (part - OVERLAP), start + i * (part - OVERLAP) + part) for i in range(n)]
    edges[-1] = (edges[-1][0], start + length)
    return [(round(a, 4), round(b, 4)) for a, b in edges]


def pieces(box: list[float], size: tuple[float, float], tile_dpi: int | None) -> list[list[float]] | None:
    """``box`` cut into the fewest overlapping pieces that each fit half the page and render sharper
    than the tiles (``box`` itself when it already does); None when that takes more than MAX_PIECES."""
    width, height = box[2] - box[0], box[3] - box[1]
    nx, ny = _count(width), _count(height)
    need = min(MAX_DPI, SHARPER * tile_dpi) if tile_dpi else 0
    while nx * ny <= MAX_PIECES:
        part_w = (width + (nx - 1) * OVERLAP) / nx if nx > 1 else width
        part_h = (height + (ny - 1) * OVERLAP) / ny if ny > 1 else height
        if crop_dpi(size, [0.0, 0.0, part_w, part_h]) >= need:
            if nx == ny == 1:
                return [box]
            return [[x0, y0, x1, y1] for y0, y1 in _edges(box[1], height, ny) for x0, x1 in _edges(box[0], width, nx)]
        # cut again along the side that holds the resolution down
        if part_w * size[0] >= part_h * size[1]:
            nx += 1
        else:
            ny += 1
    return None


def region_key(page: int, box: list[float]) -> str:
    return digest([page, [round(x, 4) for x in box]])[:24]


def _used(folder: Path) -> list[str]:
    path = folder / LEDGER
    if not path.is_file():
        return []
    regions = read(path).get('regions')
    return [key for key in regions if isinstance(key, str)] if isinstance(regions, list) else []


def budget(folder: Path, asked: list[str]) -> tuple[list[str], int]:
    """(the regions this call adds to the paper's zooms, the zooms left after it); refuse a call over the limit."""
    used = _used(folder)
    new = [key for key in dict.fromkeys(asked) if key not in used]
    if len(used) + len(new) > ZOOM_LIMIT:
        left = ZOOM_LIMIT - len(used)
        allowed = (f'Send at most {left}, only where a mark turns on a symbol you cannot read on the tile. '
                   if left > 0 else '')
        raise WorkflowError(
            f'Zoom limit: {ZOOM_LIMIT} zoomed regions per paper; {len(used)} used, this call asks for {len(new)} more. '
            f'{allowed}Stop zooming for the rest: judge each such step from the tiles with confidence "low", '
            'reason "legibility" and a one-sentence note (it goes on the review list for the person running '
            'the marking), and move on.')
    return new, ZOOM_LIMIT - len(used) - len(new)


def record(folder: Path, new: list[str]) -> None:
    if not new:
        return
    path = folder / LEDGER
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps({'regions': _used(folder) + new}) + '\n', encoding='utf-8')
    os.replace(temp, path)
