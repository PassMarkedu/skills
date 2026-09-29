"""Page views, reading tiles and crops without optional image-processing packages.

Every image the model opens is at most LONG_EDGE pixels on its long side: some
agent harnesses shrink larger images to that size, which only discards detail.
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from common import ensure_dir

LONG_EDGE = 1080
MAX_DPI = 300
TILE_SHARE = 0.52  # each tile holds 52 % of the content height, so top and bottom overlap by 4 %
PAD = 0.02  # of page width, around the union of written and printed content
ANALYSIS_DPI = 24
RENDERER_MISSING = 'Renderer unavailable: open the original PDF manually and use its 1-based page numbers, including blank pages.'


def _fitz():
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return None
    return fitz


def _has(*tools: str) -> bool:
    return all(shutil.which(tool) for tool in tools)


def _numbered(folder: Path, prefix: str) -> dict[int, Path]:
    """pdftoppm output files ``<prefix>-<page>.<ext>`` keyed by page number."""
    found = {}
    for path in folder.glob(f'{prefix}-*'):
        match = re.fullmatch(rf'{re.escape(prefix)}-(\d+)\.(png|pgm)', path.name)
        if match:
            found[int(match.group(1))] = path
    return found


def page_count(script: Path) -> int | None:
    if _has('pdfinfo'):
        info = subprocess.run(['pdfinfo', str(script)], capture_output=True, text=True)
        found = re.search(r'^Pages:\s*(\d+)', info.stdout, re.M) if info.returncode == 0 else None
        if found and int(found.group(1)) > 0:
            return int(found.group(1))
    fitz = _fitz()
    try:
        with fitz.open(script) as doc:  # type: ignore[union-attr]
            return len(doc)
    except Exception:
        return None


def page_sizes(script: Path) -> list[tuple[float, float]] | None:
    """Each page's displayed size in points, rotation applied."""
    if _has('pdfinfo'):
        info = subprocess.run(['pdfinfo', '-f', '1', '-l', '100000', str(script)], capture_output=True, text=True)
        sizes = {int(n): (float(w), float(h)) for n, w, h in
                 re.findall(r'^Page\s+(\d+)\s+size:\s+([\d.]+)\s+x\s+([\d.]+)', info.stdout, re.M)}
        turns = {int(n): int(r) for n, r in re.findall(r'^Page\s+(\d+)\s+rot:\s+(\d+)', info.stdout, re.M)}
        if info.returncode == 0 and sizes and sorted(sizes) == list(range(1, len(sizes) + 1)):
            return [sizes[n][::-1] if turns.get(n, 0) % 180 else sizes[n] for n in sorted(sizes)]
    fitz = _fitz()
    try:
        with fitz.open(script) as doc:  # type: ignore[union-attr]
            return [(page.rect.width, page.rect.height) for page in doc]
    except Exception:
        return None


def _fitz_save(page, scale: float, clip, target: Path) -> None:
    """Render ``clip`` (displayed points) at ``scale``, never beyond LONG_EDGE pixels."""
    fitz = _fitz()
    for shrink in (0, 0.5, 1.0):
        area = fitz.Rect(clip.x0, clip.y0, clip.x1 - shrink / scale, clip.y1 - shrink / scale)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=area)
        if max(pix.width, pix.height) <= LONG_EDGE:
            break
    pix.save(target)


def render_pages(script: Path, work: Path, count: int | None) -> tuple[list[str], str]:
    """Whole-page views, long edge LONG_EDGE pixels."""
    images = ensure_dir(work / 'pages')
    if count and _has('pdftoppm'):
        run = subprocess.run(['pdftoppm', '-png', '-scale-to', str(LONG_EDGE), str(script), str(images / 'page')], capture_output=True)
        files = _numbered(images, 'page')
        if run.returncode == 0 and sorted(files) == list(range(1, count + 1)):
            return [str(files[n].resolve()) for n in sorted(files)], ''
    fitz = _fitz()
    if fitz is not None:
        try:
            paths = []
            with fitz.open(script) as doc:
                width = len(str(len(doc)))
                for index, page in enumerate(doc, 1):
                    target = images / f'page-{index:0{width}d}.png'
                    _fitz_save(page, LONG_EDGE / max(page.rect.width, page.rect.height), page.rect, target)
                    paths.append(str(target.resolve()))
            return paths, ''
        except Exception:
            pass
    return [], RENDERER_MISSING


def render_cover(script: Path, target: Path) -> bool:
    """Page 1 as one image, long edge LONG_EDGE pixels."""
    if _has('pdftoppm'):
        run = subprocess.run(['pdftoppm', '-f', '1', '-l', '1', '-png', '-scale-to', str(LONG_EDGE), '-singlefile',
                              str(script), str(target.with_suffix(''))], capture_output=True)
        if run.returncode == 0 and target.is_file():
            return True
    fitz = _fitz()
    try:
        with fitz.open(script) as doc:  # type: ignore[union-attr]
            page = doc[0]
            _fitz_save(page, LONG_EDGE / max(page.rect.width, page.rect.height), page.rect, target)
        return True
    except Exception:
        return False


def _ink_box(width: int, height: int, pixels: bytes, stride: int) -> tuple[float, float, float, float] | None:
    """Bounding box (page fractions) of pixels clearly darker than the paper."""
    counts = Counter(pixels)
    paper = max((value for value in counts if value >= 128), key=lambda value: counts[value], default=255)
    cut = paper - 32
    dark = bytes(1 if value < cut else 0 for value in range(256))
    top = bottom = None
    left, right = width, -1
    for y in range(height):
        row = pixels[y * stride:y * stride + width].translate(dark)
        first = row.find(1)
        if first < 0:
            continue
        top = y if top is None else top
        bottom = y
        left = min(left, first)
        right = max(right, row.rfind(1))
    if top is None:
        return None
    return left / width, top / height, (right + 1) / width, (bottom + 1) / height


def content_box(script: Path, work: Path, sizes: list[tuple[float, float]]) -> list[float] | None:
    """Union of ink on every page from a low-resolution grey render, padded; None when unavailable."""
    boxes = []
    if _has('pdftoppm'):
        scratch = ensure_dir(work / 'tiles' / 'analysis')
        run = subprocess.run(['pdftoppm', '-gray', '-r', str(ANALYSIS_DPI), str(script), str(scratch / 'grey')], capture_output=True)
        files = _numbered(scratch, 'grey')
        if run.returncode or sorted(files) != list(range(1, len(sizes) + 1)):
            return None
        for number in sorted(files):
            data = files[number].read_bytes()
            header = re.match(rb'P5\s+(\d+)\s+(\d+)\s+255\s', data)
            if not header:
                return None
            width, height = int(header[1]), int(header[2])
            boxes.append(_ink_box(width, height, data[header.end():], width))
    else:
        fitz = _fitz()
        if fitz is None:
            return None
        try:
            with fitz.open(script) as doc:
                for page in doc:
                    pix = page.get_pixmap(dpi=ANALYSIS_DPI, colorspace=fitz.csGRAY, alpha=False)
                    boxes.append(_ink_box(pix.width, pix.height, pix.samples, pix.stride))
        except Exception:
            return None
    found = [box for box in boxes if box]
    if not found:
        return None
    width, height = max(sizes, key=lambda size: size[0] * size[1])
    pad_x, pad_y = PAD, PAD * width / height
    return [round(max(0.0, min(box[0] for box in found) - pad_x), 4), round(max(0.0, min(box[1] for box in found) - pad_y), 4),
            round(min(1.0, max(box[2] for box in found) + pad_x), 4), round(min(1.0, max(box[3] for box in found) + pad_y), 4)]


def tile_plan(size: tuple[float, float], box: list[float]) -> tuple[int, dict[str, tuple[int, int, int, int]]]:
    """DPI and pixel rectangles (x, y, w, h) of the top and bottom tiles of one page size."""
    width, height = size
    x0, y0, x1, y1 = box
    share = (y1 - y0) * TILE_SHARE
    dpi = int(min(MAX_DPI, LONG_EDGE * 72 / max((x1 - x0) * width, share * height)))
    scale = dpi / 72
    left, right = math.floor(x0 * width * scale), math.ceil(x1 * width * scale)
    rects = {}
    for name, top, bottom in (('top', y0, y0 + share), ('bottom', y1 - share, y1)):
        upper, lower = math.floor(top * height * scale), math.ceil(bottom * height * scale)
        rects[name] = (left, upper, min(LONG_EDGE, right - left), min(LONG_EDGE, lower - upper))
    return dpi, rects


def render_tiles(script: Path, work: Path, sizes: list[tuple[float, float]], box: list[float] | None) -> tuple[list[list[str]], list[int]] | None:
    """Top and bottom reading tiles of every page, and each page's tile DPI; None when unavailable."""
    folder = ensure_dir(work / 'tiles')
    box = box or [0.0, 0.0, 1.0, 1.0]
    plans = [tile_plan(size, box) for size in sizes]
    width = len(str(len(sizes)))
    names = [{name: folder / f'{name}-{page:0{width}d}.png' for name in ('top', 'bottom')} for page in range(1, len(sizes) + 1)]
    if _has('pdftoppm'):
        runs = []  # consecutive pages sharing one plan render in one call per tile position
        for page, plan in enumerate(plans, 1):
            if runs and runs[-1][2] == plan and runs[-1][1] == page - 1:
                runs[-1][1] = page
            else:
                runs.append([page, page, plan])
        for first, last, (dpi, rects) in runs:
            for name, (x, y, w, h) in rects.items():
                subprocess.run(['pdftoppm', '-f', str(first), '-l', str(last), '-r', str(dpi), '-x', str(x), '-y', str(y),
                                '-W', str(w), '-H', str(h), '-png', str(script), str(folder / name)], capture_output=True)
    else:
        fitz = _fitz()
        if fitz is None:
            return None
        try:
            with fitz.open(script) as doc:
                for page, (dpi, rects) in zip(doc, plans):
                    scale = dpi / 72
                    for name, (x, y, w, h) in rects.items():
                        clip = fitz.Rect(x / scale, y / scale, (x + w) / scale, (y + h) / scale)
                        _fitz_save(page, scale, clip, names[page.number][name])
        except Exception:
            return None
    if not all(path.is_file() for pair in names for path in pair.values()):
        return None
    return [[str(pair['top'].resolve()), str(pair['bottom'].resolve())] for pair in names], [dpi for dpi, _ in plans]


def crop_dpi(size: tuple[float, float], box: list[float]) -> int:
    """Resolution that renders ``box`` at LONG_EDGE pixels on its long side, capped at MAX_DPI."""
    width, height = size
    return int(min(MAX_DPI, LONG_EDGE * 72 / ((box[2] - box[0]) * width), LONG_EDGE * 72 / ((box[3] - box[1]) * height)))


def crop_page(script: Path, page: int, box: list[float], target: Path, dpi: int) -> None:
    """Render a normalized rectangle of the page's displayed orientation at ``dpi``."""
    fitz = _fitz()
    if fitz is not None:
        with fitz.open(script) as doc:
            if page > len(doc):
                raise ValueError(f'page {page} outside script')
            source = doc[page - 1]
            width, height = source.rect.width, source.rect.height
            shown = fitz.Rect(box[0] * width, box[1] * height, box[2] * width, box[3] * height)
            # PyMuPDF clips the displayed page, including its rotation.
            if shown.is_empty or shown.width <= 0 or shown.height <= 0:
                raise ValueError(f'page {page} has an empty crop')
            _fitz_save(source, dpi / 72, shown, target)
            if not target.is_file():
                raise ValueError(f'page {page} has an empty crop')
        return
    sizes = page_sizes(script) if _has('pdftoppm') else None
    if not sizes:
        raise ValueError('Crop needs installed PyMuPDF or pdfinfo/pdftoppm')
    if page > len(sizes):
        raise ValueError(f'page {page} outside script or unreadable')
    width, height = sizes[page - 1]
    scale = dpi / 72
    left, top = math.floor(box[0] * width * scale), math.floor(box[1] * height * scale)
    right, bottom = math.ceil(box[2] * width * scale), math.ceil(box[3] * height * scale)
    if right <= left or bottom <= top:
        raise ValueError(f'page {page} has an empty crop')
    run = subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-r', str(dpi), '-png', '-singlefile',
                          '-x', str(left), '-y', str(top), '-W', str(min(LONG_EDGE, right - left)),
                          '-H', str(min(LONG_EDGE, bottom - top)), str(script), str(target.with_suffix(''))], capture_output=True)
    if run.returncode or not target.is_file():
        raise ValueError(f'page {page} crop rendering failed')


def validate_box(value: object, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError(f'{label}: box must have four finite normalized numbers')
    box = [float(x) for x in value]
    if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise ValueError(f'{label}: box must be inside 0..1 with nonempty area')
    return box
