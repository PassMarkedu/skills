"""Is a question judged blank really blank? Its pages against the printed booklet.

A unit marked ``attempted: false`` is safe only if its pages carry no writing.
Each page of a question left wholly blank is rendered small in grey by poppler
next to the same page of the question paper's answer booklet. Scans are often
cropped and rescaled, so the two are lined up on the answer frame (the extent
of the long printed rules) and the booklet's print, slightly widened, is
laid over the scan. Ink left over in strokes at least two pixels tall is what
the candidate wrote; stray pixels along a misregistered rule are not. A part that
shares its pages with an answered part is ``unknown``: the answer space is
shared, so ink there proves nothing. Pure Python on PGM bytes; no image package.
"""
from __future__ import annotations

import operator
import re
import shutil
import subprocess
from pathlib import Path

import pagemap
from common import WorkflowError, ensure_dir, read

WIDTH, HEIGHT = 420, 594  # ~50 dpi on A4; both pages are drawn to exactly this grid
WRITTEN, PRINTED = 75, 30  # grey levels below the paper: the scan's pen ink, and all the booklet's print
RULE = 0.45  # a printed rule runs at least this share of the page width
EDGE = 0.03  # scan edges ignored when looking for rules (scanner borders)
INSET = 0.015  # the frame's own border is left out of the comparison
SPREAD_X, SPREAD_Y = 2, 1  # pixels the booklet's print is widened by, for residual misalignment
# Leftover stroke ink, as a share of the frame, that reads as writing. Bench scripts (2026-09-29):
# pages of questions left blank reach 0.00014, pages holding an answer start from 0.0022.
INK = 0.0004


def _pgm(path: Path) -> tuple[int, int, bytes] | None:
    data = path.read_bytes()
    header = re.match(rb'P5\s+(\d+)\s+(\d+)\s+255\s', data)
    if not header:
        return None
    width, height = int(header[1]), int(header[2])
    body = data[header.end():header.end() + width * height]
    return (width, height, body) if len(body) == width * height else None


def _paper(pixels: bytes) -> int:
    counts = [0] * 256
    for value in pixels[:: max(1, len(pixels) // 20000)]:
        counts[value] += 1
    return max(range(128, 256), key=counts.__getitem__)


def _masks(width: int, height: int, pixels: bytes, darker: int) -> list[bytes]:
    """Each row as bytes of 0/1: 1 where the pixel is at least ``darker`` below the paper."""
    cut = _paper(pixels) - darker
    table = bytes(1 if value < cut else 0 for value in range(256))
    return [pixels[y * width:(y + 1) * width].translate(table) for y in range(height)]


_BITS = bytes.maketrans(b'\x00\x01', b'01')


def _int(row: bytes) -> int:
    return int(row.translate(_BITS)[::-1], 2)  # bit x = column x


def _runs(row: int, length: int) -> int:
    """Bits where a run of at least ``length`` ones starts."""
    done = 1
    while done < length:
        step = min(done, length - done)
        row &= row >> step
        done += step
    return row


def _frame(rows: list[bytes], width: int) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) of the long printed rules: the answer frame."""
    length = int(RULE * width)
    tops, starts, ends = [], [], []
    for y in range(int(EDGE * len(rows)), int((1 - EDGE) * len(rows))):
        runs = _runs(_int(rows[y]), length)
        if runs:
            tops.append(y)
            starts.append((runs & -runs).bit_length() - 1)
            ends.append(runs.bit_length() - 1 + length - 1)
    if len(tops) < 2 or tops[-1] - tops[0] < 0.2 * len(rows):
        return None
    starts.sort()
    ends.sort()
    return starts[len(starts) // 10], tops[0], ends[-1 - len(ends) // 10], tops[-1]


def leftover(scan: tuple[int, int, bytes], printed: tuple[int, int, bytes]) -> float | None:
    """Share of the scan's answer frame covered by ink the booklet does not print there."""
    width, height = scan[0], scan[1]
    frame_s = _frame(_masks(*scan, PRINTED), width)
    booklet = _masks(*printed, PRINTED)
    frame_p = _frame(booklet, printed[0])
    if frame_s is None or frame_p is None:
        return None
    (l1, t1, r1, b1), (l2, t2, r2, b2) = frame_s, frame_p
    sx, sy = (r2 - l2) / max(1, r1 - l1), (b2 - t2) / max(1, b1 - t1)
    if not (0.7 < sx < 1.4 and 0.7 < sy < 1.4):
        return None  # not the same page layout
    inset_x, inset_y = int(INSET * width), int(INSET * height)
    left, right, top, bottom = l1 + inset_x, r1 - inset_x, t1 + inset_y, b1 - inset_y
    if right - left < 20 or bottom - top < 20:
        return None
    columns = [min(printed[0] - 1, max(0, round(l2 + (x - l1) * sx))) for x in range(width)]
    gather = operator.itemgetter(*columns)
    window = ((1 << (right - left)) - 1) << left
    written = _masks(*scan, WRITTEN)
    rows = []
    for y in range(top, bottom):
        source = round(t2 + (y - t1) * sy)
        cover = 0
        for near in range(source - SPREAD_Y, source + SPREAD_Y + 1):
            if 0 <= near < len(booklet):
                cover |= _int(bytes(gather(booklet[near])))
        wide = cover
        for step in range(1, SPREAD_X + 1):
            wide |= (cover << step) | (cover >> step)
        rows.append(_int(written[y]) & ~wide & window)
    # pen strokes are at least two pixels tall; a misregistered rule leaves one-pixel slivers
    strokes = sum((row & ((rows[i - 1] if i else 0) | (rows[i + 1] if i + 1 < len(rows) else 0))).bit_count()
                  for i, row in enumerate(rows))
    return strokes / ((right - left) * (bottom - top))


def _render(pdf: Path, page: int, target: Path) -> Path | None:
    if not target.is_file():
        subprocess.run(['pdftoppm', '-gray', '-f', str(page), '-l', str(page), '-scale-to-x', str(WIDTH),
                        '-scale-to-y', str(HEIGHT), '-singlefile', str(pdf), str(target.with_suffix(''))],
                       capture_output=True)
    return target if target.is_file() else None


def page_ink(work: Path, pages: list[int], booklet_start: int) -> dict[int, float | None]:
    """Leftover ink of each scan page against booklet page ``booklet_start + page``."""
    if not pages or not shutil.which('pdftoppm'):
        return {page: None for page in pages}
    folder = ensure_dir(work / 'tiles' / 'blank-check')
    out: dict[int, float | None] = {}
    for page in pages:
        scan = _render(work / 'script.pdf', page, folder / f'scan-{page}.pgm')
        booklet = _render(work / 'question-paper.pdf', booklet_start + page, folder / f'booklet-{booklet_start + page}.pgm')
        a, b = (_pgm(scan) if scan else None), (_pgm(booklet) if booklet else None)
        out[page] = leftover(a, b) if a and b else None
    return out


def for_run(work: Path, state: dict, questions: list[dict], attempted: dict[str, bool]) -> dict[str, str]:
    """Blank checks of a run whose page map came from the question paper; ``unknown`` otherwise."""
    derived = state.get('page_map') or {}
    blank = {uid: 'unknown' for uid, done in attempted.items() if not done}
    if not blank or derived.get('source') != 'question_paper' or not (work / 'page-map.json').is_file():
        return blank
    start = derived.get('booklet_start')
    if type(start) is not int:  # prepared by an earlier 1.10 helper
        texts = pagemap.page_texts(work / 'question-paper.pdf')
        start = pagemap.booklet_start(texts) if texts else None
    try:
        mapping = read(work / 'page-map.json')
    except (ValueError, WorkflowError):
        return blank
    # A question the model re-mapped by hand no longer sits on its booklet pages: no verdict for it.
    trusted = {n for n, pages in (derived.get('map') or {}).items() if mapping.get(n) == pages}
    return {**blank, **unit_checks(work, mapping, start, questions, attempted, trusted)}


def unit_checks(work: Path, mapping: dict, booklet_start: int | None, questions: list[dict],
                attempted: dict[str, bool], trusted: set[str] | None = None) -> dict[str, str]:
    """``empty`` / ``ink`` / ``unknown`` for every unit judged not attempted."""
    blank = [uid for uid, done in attempted.items() if not done]
    if not blank:
        return {}
    if booklet_start is None:
        return {uid: 'unknown' for uid in blank}
    owner = {u['unit_id']: str(q['number']) for q in questions for u in q.get('scoring_units', []) if u.get('supported')}
    answered = {owner[uid] for uid, done in attempted.items() if done and uid in owner}
    busy = {p for number in answered for p in (mapping.get(number) or [])}
    wanted = {}
    for uid in blank:
        number = owner.get(uid)
        pages = [p for p in (mapping.get(number) or []) if type(p) is int and p not in busy]
        # A part whose question has an answered part shares that answer space: no verdict.
        usable = number not in answered and (trusted is None or number in trusted)
        wanted[uid] = pages if usable and pages else None
    needed = sorted({p for pages in wanted.values() if pages for p in pages})
    ink = page_ink(work, needed, booklet_start) if needed else {}
    out = {}
    for uid, pages in wanted.items():
        values = [ink.get(p) for p in pages or []]
        if not pages or any(v is None for v in values):
            out[uid] = 'unknown'
        else:
            out[uid] = 'ink' if max(values) >= INK else 'empty'
    return out
