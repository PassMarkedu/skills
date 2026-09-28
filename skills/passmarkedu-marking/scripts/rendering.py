"""Original-page crop rendering without optional image-processing packages."""
from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path


def crop_page(script: Path, page: int, box: list[float], target: Path) -> None:
    """Render a normalized rectangle in the page's displayed orientation at 300 dpi."""
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        fitz = None
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
            pix = source.get_pixmap(dpi=300, clip=shown)
            if not pix.width or not pix.height:
                raise ValueError(f'page {page} has an empty crop')
            pix.save(target)
        return
    if not (shutil.which('pdfinfo') and shutil.which('pdftoppm')):
        raise ValueError('Crop needs installed PyMuPDF or pdfinfo/pdftoppm')
    info = subprocess.run(['pdfinfo', '-f', str(page), '-l', str(page), str(script)], capture_output=True, text=True)
    size = re.search(rf'^Page\s+{page}\s+size:\s+([\d.]+)\s+x\s+([\d.]+)', info.stdout, re.M)
    rotation = re.search(rf'^Page\s+{page}\s+rot:\s+(\d+)', info.stdout, re.M)
    if info.returncode or not size:
        raise ValueError(f'page {page} outside script or unreadable')
    width, height = float(size[1]), float(size[2])
    if rotation and int(rotation[1]) % 180:
        width, height = height, width
    scale = 300 / 72
    left, top = math.floor(box[0] * width * scale), math.floor(box[1] * height * scale)
    right, bottom = math.ceil(box[2] * width * scale), math.ceil(box[3] * height * scale)
    if right <= left or bottom <= top:
        raise ValueError(f'page {page} has an empty crop')
    prefix = target.with_suffix('')
    run = subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-r', '300', '-png',
                          '-singlefile', '-x', str(left), '-y', str(top), '-W', str(right-left),
                          '-H', str(bottom-top), str(script), str(prefix)], capture_output=True)
    if run.returncode or not target.is_file():
        raise ValueError(f'page {page} crop rendering failed')


def validate_box(value: object, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError(f'{label}: box must have four finite normalized numbers')
    box = [float(x) for x in value]
    if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise ValueError(f'{label}: box must be inside 0..1 with nonempty area')
    return box


def pages_for(script: Path, work: Path) -> tuple[list[str], str]:
    images = work / 'pages'
    images.mkdir(exist_ok=True)
    if shutil.which('pdfinfo') and shutil.which('pdftoppm'):
        info = subprocess.run(['pdfinfo', str(script)], capture_output=True, text=True)
        count = re.search(r'^Pages:\s*(\d+)', info.stdout, re.M) if info.returncode == 0 else None
        if count:
            run = subprocess.run(['pdftoppm', '-f', '1', '-l', count.group(1), '-r', '200', '-png', str(script), str(images / 'page')], capture_output=True)
            if run.returncode == 0:
                files = sorted(images.glob('page-*.png'))
                if len(files) == int(count.group(1)):
                    return [str(p.resolve()) for p in files], ''
    try:
        import fitz  # type: ignore[import-not-found]
        doc = fitz.open(script)
        paths = []
        for index in range(len(doc)):
            target = images / f'page-{index + 1:04d}.png'
            doc[index].get_pixmap(dpi=200).save(target)
            paths.append(str(target.resolve()))
        return paths, ''
    except Exception:
        return [], 'Renderer unavailable: open the original PDF manually and use its 1-based page numbers, including blank pages.'


def page_count(script: Path) -> int | None:
    if shutil.which('pdfinfo'):
        info = subprocess.run(['pdfinfo', str(script)], capture_output=True, text=True)
        found = re.search(r'^Pages:\s*(\d+)', info.stdout, re.M) if info.returncode == 0 else None
        if found and int(found.group(1)) > 0:
            return int(found.group(1))
    try:
        import fitz  # type: ignore[import-not-found]
        with fitz.open(script) as doc:
            return len(doc)
    except Exception:
        return None
