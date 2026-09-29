"""Map answer-booklet pages to questions from the official question paper's text.

The printed booklet fixes where each question's answer space is. When a scan
has exactly the booklet's pages, its page N is booklet page N, so the map comes
from the question paper instead of from viewing every scanned page.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

BOOKLET_COVER = re.compile(r'candidate\s+surname|centre\s+number', re.I)
MARKERS = (
    (re.compile(r'Write the answer to Question\s+(\d+)\b'), 'start'),
    (re.compile(r'^\s*Question\s+(\d+)\s*$'), 'start'),
    (re.compile(r'Source material for Question\s+(\d+)\b'), 'start'),
    (re.compile(r'If you answer Question\s+(\d+)\b'), 'start'),
    (re.compile(r'Question\s+(\d+)\s+continued'), 'continued'),
    (re.compile(r'Total for Question\s+(\d+)\b'), 'end'),
    (re.compile(r'end of Question\s+(\d+)\s+answer space'), 'end'),
)
# A question number in the left margin: "3.", "3 (a)", "3  Find", or a bare "3" above question text.
# Some fonts extract the dot as ":"; a starred number marks an extended-response question.
MARGIN_NUMBER = re.compile(r'^(\s*)\*?(\d{1,2})([.:]?)(?:\s+(.*))?$')
LETTERS = re.compile(r'[A-Za-z]{2}')
BLANK = re.compile(r'\bBLANK PAGE\b')
ADDITIONAL = re.compile(r'additional page|following lined page', re.I)
# Earlier work on a page: an answer line, a mark allocation or a question total.
EARLIER_WORK = re.compile(r'\.{10,}|_{10,}|\[\d+\]|\(\d+\)\s*$|\[Total')
REFERENCE = re.compile(r'\b([A-Z]{3}\d{2})\s*/\s*(\d{2}[A-Z]?)\b|\b(\d{4})\s*/\s*(\d{2})\b')


def page_texts(pdf: Path, first: int | None = None, last: int | None = None) -> list[str] | None:
    """Layout-preserving text of each page; None when no text extractor is installed."""
    if shutil.which('pdftotext'):
        command = ['pdftotext', '-layout', '-enc', 'UTF-8']
        if first:
            command += ['-f', str(first)]
        if last:
            command += ['-l', str(last)]
        run = subprocess.run([*command, str(pdf), '-'], capture_output=True)
        if run.returncode == 0:
            text = run.stdout.decode('utf-8', 'replace')
            return (text[:-1] if text.endswith('\f') else text).split('\f')
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        with fitz.open(pdf) as doc:
            pages = range((first or 1) - 1, min(last or len(doc), len(doc)))
            return [_fitz_layout(doc[index]) for index in pages]
    except Exception:
        return None


def _fitz_layout(page) -> str:
    """Upright lines top to bottom, indented by their position (one column per 1 % of width)."""
    width = page.rect.width or 1
    lines = []
    for block in page.get_text('dict').get('blocks', []):
        for line in block.get('lines', []):
            if abs(line['dir'][1]) > 0.1:
                continue  # rotated margin text
            text = ''.join(span['text'] for span in line['spans']).strip()
            if text:
                lines.append((round(line['bbox'][1], 1), line['bbox'][0], text))
    return '\n'.join(' ' * int(x / width * 100) + text for _, x, text in sorted(lines))


def cover_reference(text: str) -> str | None:
    found = REFERENCE.search(text or '')
    if not found:
        return None
    return f'{found[1]}/{found[2]}' if found[1] else f'{found[3]}/{found[4]}'


def _margin_numbers(lines: list[str]) -> list[tuple[int, str]]:
    """(line index, number) of question numbers at the page's left text margin."""
    indents = []
    for line in lines:
        if line.strip() and 'DO NOT WRITE' not in line.upper() and (LETTERS.search(line) or MARGIN_NUMBER.match(line)):
            indents.append(len(line.expandtabs()) - len(line.expandtabs().lstrip()))
    if not indents:
        return []
    margin = min(indents)
    found = []
    for index, line in enumerate(lines):
        match = MARGIN_NUMBER.match(line.expandtabs())
        if not match or len(match.group(1)) > margin + 1 or 'DO NOT WRITE' in line.upper():
            continue
        rest = (match.group(4) or '').strip()
        if rest:
            # Question text follows; page numbers, codes, barcodes and answer dots do not qualify.
            ok = match.group(3) or rest.startswith('(') or re.search(r'[a-z]', rest[:24])
        else:
            # A bare number is a question only when question text follows it on the page.
            ok = match.group(3) or any(re.search(r'[a-z]{2}', x) for x in lines[index + 1:] if 'DO NOT WRITE' not in x.upper())
        if ok:
            found.append((index, str(int(match.group(2)))))
    return found


def booklet_start(texts: list[str]) -> int:
    """Index of the answer booklet's cover in the question paper: scan page N is paper page start + N."""
    return next((index for index, text in enumerate(texts) if BOOKLET_COVER.search(text)), 0)


def derive(texts: list[str], numbers: list[str], script_pages: int | None) -> tuple[dict | None, list[int], str]:
    """Return (map of question -> 1-based script pages, unassigned pages, reason when no map)."""
    if not numbers or not all(re.fullmatch(r'[1-9]\d?', n) for n in numbers):
        return None, [], 'question numbers are not plain printed numbers'
    start = booklet_start(texts)
    booklet = [text.splitlines() for text in texts[start:]]
    if script_pages != len(booklet):
        return None, [], f'the scan has {script_pages} pages but the printed answer booklet has {len(booklet)}'
    events = []
    for page, lines in enumerate(booklet):
        for index, line in enumerate(lines):
            for pattern, kind in MARKERS:
                events.extend((page, index, kind, str(int(m))) for m in pattern.findall(line))
        events.extend((page, index, 'start', n) for index, n in _margin_numbers(lines))
    events.sort()
    blank = [bool(BLANK.search('\n'.join(lines)) or ADDITIONAL.search('\n'.join(lines))) for lines in booklet]
    wanted = set(numbers)
    starts, ends = {}, {}
    cursor = (-1, -1)
    for n in map(str, range(1, max(map(int, numbers)) + 2)):
        found = next(((p, i) for p, i, kind, m in events if kind == 'start' and m == n and (p, i) > cursor), None)
        if found is None:
            if n in wanted:
                return None, [], f'question {n} was not found in the question paper'
            continue
        starts[n] = found
        after = [(p, i, kind) for p, i, kind, m in events if m == n and kind in ('end', 'continued') and (p, i) > found]
        # The question total closes it; without one, its last "continued" page does.
        closing = next(((p, i) for p, i, kind in after if kind == 'end'), None) or (after[-1][:2] if after else None)
        if closing:
            ends[n] = closing
        cursor = closing or found
    order = sorted(starts, key=lambda n: starts[n])
    mapping = {}
    for position, n in enumerate(order):
        first = starts[n][0]
        following = starts[order[position + 1]] if position + 1 < len(order) else None
        if n in ends:
            last = ends[n][0]
            if following and following[0] < last:
                return None, [], f'question {order[position + 1]} starts before question {n} ends'
        elif following:
            above = booklet[following[0]][:following[1]]
            last = following[0] if following[0] == first or any(EARLIER_WORK.search(x) for x in above) else following[0] - 1
        else:
            last = len(booklet) - 1
        # A printed blank page inside a question's closed answer space ("continues on the next
        # page") stays with it; other blank and additional pages are left unassigned.
        pages = [page + 1 for page in range(first, last + 1) if not blank[page] or (n in ends and first < page < last)]
        if n in wanted:
            if not pages:
                return None, [], f'question {n} has no answer page'
            mapping[n] = pages
    used = {page for pages in mapping.values() for page in pages}
    return {n: mapping[n] for n in numbers}, [p for p in range(1, len(booklet) + 1) if p not in used], ''
