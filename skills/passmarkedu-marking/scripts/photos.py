"""Photos of an answer script as one PDF, built without image packages.

A JPEG goes into the PDF unchanged (DCTDecode). PDF readers ignore the EXIF Orientation inside
it, so the page's drawing matrix applies that orientation and every page shows upright. Other
formats become JPEG first through PyMuPDF, else macOS ``sips``. The service's photo search reads
the unchanged JPEG back out of a PDF built here when nothing can render pages.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from common import WorkflowError

IMAGE_SUFFIXES = ('.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp')
PRODUCER = b'PassMarkedu photos'
LONG_SIDE_PT = 842  # each page is A4-sized on its long side, so page renders match a scanned sheet
_FRAMES = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
_SPACES = {1: '/DeviceGray', 3: '/DeviceRGB', 4: '/DeviceCMYK'}
_IMAGE = re.compile(rb'/Subtype/Image/Width \d+/Height \d+/ColorSpace/\w+/BitsPerComponent 8(?:/Decode\[[\d ]+\])?'
                    rb'/Filter/DCTDecode/Length (\d+)>>stream\n')


def is_photo(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES


def _orientation(tiff: bytes) -> int:
    """EXIF Orientation (1-8) from the TIFF block of an APP1 Exif segment; 1 when absent."""
    order = {b'II': 'little', b'MM': 'big'}.get(tiff[:2])
    if order is None or len(tiff) < 8:
        return 1
    ifd = int.from_bytes(tiff[4:8], order)
    count = int.from_bytes(tiff[ifd:ifd + 2], order) if ifd + 2 <= len(tiff) else 0
    for index in range(count):
        entry = tiff[ifd + 2 + 12 * index:ifd + 14 + 12 * index]
        if len(entry) < 12:
            break
        if int.from_bytes(entry[:2], order) == 0x0112:
            value = int.from_bytes(entry[8:10], order)
            return value if 1 <= value <= 8 else 1
    return 1


def jpeg_info(data: bytes) -> dict:
    """Width, height, colour components, bit depth, Adobe marker and EXIF orientation from the headers."""
    if not data.startswith(b'\xff\xd8'):
        raise ValueError('not a JPEG file')
    info = {'orientation': 1, 'adobe': False}
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise ValueError('damaged JPEG file')
        marker = data[pos + 1]
        if marker == 0xFF:  # fill byte
            pos += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            pos += 2
            continue
        if marker in (0xD9, 0xDA):  # end of image, start of scan: the headers are over
            break
        length = int.from_bytes(data[pos + 2:pos + 4], 'big')
        body = data[pos + 4:pos + 2 + length]
        if marker in _FRAMES and 'width' not in info and len(body) >= 6:
            info.update(bits=body[0], height=int.from_bytes(body[1:3], 'big'), width=int.from_bytes(body[3:5], 'big'),
                        components=body[5])
        elif marker == 0xE1 and body.startswith(b'Exif\x00\x00') and 'exif' not in info:
            info['exif'] = True
            info['orientation'] = _orientation(body[6:])
        elif marker == 0xEE and body.startswith(b'Adobe'):
            info['adobe'] = True
        pos += 2 + length
    if not info.get('width') or not info.get('height'):
        raise ValueError('JPEG file has no image size')
    if info['bits'] != 8 or info['components'] not in _SPACES:
        raise ValueError('JPEG file is not an 8-bit grey, colour or CMYK image')
    return info


def placement(orientation: int, width: float, height: float) -> tuple[tuple[float, float], tuple[float, ...]]:
    """Upright page size and the matrix drawing a ``width`` x ``height`` stored image with that EXIF orientation."""
    turned = orientation in (5, 6, 7, 8)
    w, h = (height, width) if turned else (width, height)
    return (w, h), {1: (w, 0, 0, h, 0, 0), 2: (-w, 0, 0, h, w, 0), 3: (-w, 0, 0, -h, w, h), 4: (w, 0, 0, -h, 0, h),
                    5: (0, -h, -w, 0, w, h), 6: (0, -h, w, 0, 0, h), 7: (0, h, w, 0, 0, 0), 8: (0, h, -w, 0, w, 0)}[orientation]


def _number(value: float) -> str:
    return f'{value:.2f}'.rstrip('0').rstrip('.') or '0'


def build_pdf(jpegs: list[bytes]) -> bytes:
    """One upright page per JPEG, in order; the same JPEGs always give the same bytes."""
    objects = [b'<</Type/Catalog/Pages 2 0 R>>', b'', b'<</Producer(' + PRODUCER + b')>>']
    kids = []
    for data in jpegs:
        info = jpeg_info(data)
        scale = LONG_SIDE_PT / max(info['width'], info['height'])
        width, height = round(info['width'] * scale, 2), round(info['height'] * scale, 2)
        (page_w, page_h), matrix = placement(info['orientation'], width, height)
        page, content, image = len(objects) + 1, len(objects) + 2, len(objects) + 3
        kids.append(f'{page} 0 R')
        draw = ('q ' + ' '.join(_number(value) for value in matrix) + ' cm /Im0 Do Q').encode()
        decode = '/Decode[1 0 1 0 1 0 1 0]' if info['components'] == 4 and info['adobe'] else ''
        objects.append(f'<</Type/Page/Parent 2 0 R/MediaBox[0 0 {_number(page_w)} {_number(page_h)}]'
                       f'/Resources<</XObject<</Im0 {image} 0 R>>>>/Contents {content} 0 R>>'.encode())
        objects.append(b'<</Length %d>>stream\n' % len(draw) + draw + b'\nendstream')
        objects.append(f'<</Type/XObject/Subtype/Image/Width {info["width"]}/Height {info["height"]}'
                       f'/ColorSpace{_SPACES[info["components"]]}/BitsPerComponent 8{decode}'
                       f'/Filter/DCTDecode/Length {len(data)}>>stream\n'.encode() + data + b'\nendstream')
    objects[1] = ('<</Type/Pages/Kids[' + ' '.join(kids) + f']/Count {len(kids)}>>').encode()
    parts, offsets = [b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'], []
    for index, value in enumerate(objects, 1):
        offsets.append(sum(map(len, parts)))
        parts.append(f'{index} 0 obj\n'.encode() + value + b'\nendobj\n')
    start = sum(map(len, parts))
    parts.append(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode())
    parts.extend(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)
    parts.append(f'trailer\n<</Size {len(objects) + 1}/Root 1 0 R/Info 3 0 R>>\nstartxref\n{start}\n%%EOF\n'.encode())
    return b''.join(parts)


def embedded_jpegs(pdf: bytes) -> list[bytes] | None:
    """The unchanged JPEG of each page of a PDF built here; None for any other PDF."""
    if b'/Producer(' + PRODUCER + b')' not in pdf:
        return None
    return [pdf[match.end():match.end() + int(match[1])] for match in _IMAGE.finditer(pdf)]


def _fitz():
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return None
    return fitz


def _sips(arguments: list[str], source: Path, suffix: str = '.jpg') -> bytes | None:
    """Run macOS ``sips`` on ``source``; the JPEG it writes, or None."""
    if not shutil.which('sips'):
        return None
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / ('converted' + suffix)
        run = subprocess.run(['sips', *arguments, str(source), '--out', str(target)], capture_output=True)
        data = target.read_bytes() if run.returncode == 0 and target.is_file() else b''
    return data if data.startswith(b'\xff\xd8') else None


def as_jpeg(path: Path) -> bytes:
    """The photo as JPEG bytes: a JPEG as it is, anything else converted by PyMuPDF or macOS sips."""
    data = path.read_bytes()
    if data.startswith(b'\xff\xd8'):
        try:
            jpeg_info(data)
            return data
        except ValueError as exc:
            raise WorkflowError(f'{path.name}: {exc}') from None
    fitz = _fitz()
    if fitz is not None:
        try:
            pixmap = fitz.Pixmap(str(path))
            if pixmap.alpha:
                pixmap = fitz.Pixmap(pixmap, 0)
            if pixmap.n not in (1, 3):
                pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
            return pixmap.tobytes('jpeg', jpg_quality=90)
        except Exception:
            pass
    converted = _sips(['-s', 'format', 'jpeg'], path)
    if converted:
        return converted
    raise WorkflowError(f'{path.name}: this computer cannot convert {path.suffix or "this"} photos (that needs PyMuPDF or macOS). '
                        'JPEG photos (.jpg, .jpeg) and PDF scans work everywhere: send the pages in one of those.')


def shrink(jpeg: bytes, long_edge: int) -> bytes | None:
    """A smaller copy of a JPEG through macOS sips, or None where there is no sips."""
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / 'page.jpg'
        source.write_bytes(jpeg)
        return _sips(['-Z', str(long_edge)], source)


def combine(images: list[Path]) -> Path:
    """Write the photos, in the order given, as one PDF beside the first photo and return its path.

    A later start with the same photos reuses that PDF; a different file of that name is kept."""
    for image in images:
        if not image.is_file():
            raise WorkflowError(f'Photo not found: {image}')
        if not is_photo(image):
            raise WorkflowError(f'{image.name}: photos must be {", ".join(IMAGE_SUFFIXES)}; give a PDF on its own')
    data = build_pdf([as_jpeg(image) for image in images])
    first = images[0]
    for number in range(1, 100):
        target = first.with_name(first.stem + ('.pdf' if number == 1 else f'-{number}.pdf'))
        if target.exists():
            if target.is_file() and target.read_bytes() == data:
                return target
            continue
        temp = target.with_name(target.name + '.tmp')
        temp.write_bytes(data)
        os.replace(temp, target)
        return target
    raise WorkflowError(f'Could not name the combined PDF beside {first.name}')
