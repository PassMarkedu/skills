"""Find the official questions on a script that has no cover: photos, or mixed questions.

``views`` shows every page (a view, plus any text the PDF itself holds) so the printed question
text can be read off it. ``identify`` then asks the service's question search with that text or a
printed reference (``POST /identify``, no charge). Only a page whose questions it could not find,
or a page named for it, goes to the service's photo identification (``POST /identify-photo``,
a daily allowance per account). Papers and questions are never looked up anywhere else.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Callable

import photos
from common import WorkflowError, ensure_dir
from pagemap import cover_reference, page_texts
from rendering import page_count, render_jpeg, render_pages

UPLOAD_EDGE = 2000  # pixels on the long side; the service reduces a photo to about one megapixel anyway
MAX_UPLOAD = 8 * 1024 * 1024
TEXT_CHARS = 600
SHOWN = ('question_id', 'board', 'unit_code', 'year', 'session', 'paper_number', 'question_number', 'preview')
DAILY_LIMIT = 'marking_kit_photo_daily_limit'
# Service errors of question search and photo identification, with what to do next (workflow.api).
ERRORS = {
    'marking_kit_photo_daily_limit': "today's photo identifications for this account are used up; "
                                     'identify from the printed question text, or ask the user which paper and question it is',
    'photo_search_disabled': 'photo identification is not available on this service; identify from the printed question text',
    'photo_search_unavailable': 'photo identification is unavailable right now; identify from the printed question text or retry later',
    'photo_too_large': 'the page image is over 8 MB',
    'photo_invalid_image': 'the service could not read the page image',
    'search_index_unavailable': 'question search is unavailable right now; retry later',
}


def pages_in(script: Path) -> int:
    """The script's page count, also where nothing reads PDFs but the PDF was built here from photos."""
    return page_count(script) or len(photos.embedded_jpegs(script.read_bytes()) or [])


def views(script: Path, work: Path) -> list[dict]:
    """Each page's view (at most 1080 pixels) and the printed text the PDF holds, if any."""
    folder = work / 'identify'
    count = pages_in(script)
    images, _ = render_pages(script, folder, count)
    if not images:  # nothing renders here: a PDF built from photos still holds each photo
        pictures = photos.embedded_jpegs(script.read_bytes()) or []
        if len(pictures) == count:
            pages = ensure_dir(folder / 'pages')
            for number, data in enumerate(pictures, 1):
                (pages / f'page-{number}.jpg').write_bytes(data)
            images = [str((pages / f'page-{number}.jpg').resolve()) for number in range(1, count + 1)]
    texts = page_texts(script) or []
    shown = []
    for page in range(1, count + 1):
        entry = {'page': page, 'image': images[page - 1] if page <= len(images) else None}
        raw = texts[page - 1] if page <= len(texts) else ''
        if ' '.join(raw.split()):
            entry['text'] = ' '.join(raw.split())[:TEXT_CHARS]
            if cover_reference(raw):
                entry['reference'] = cover_reference(raw)
        shown.append(entry)
    return shown


def _items(raw: object, count: int) -> list[dict]:
    if not isinstance(raw, list) or not raw or len(raw) > 40:
        raise WorkflowError('items must be a JSON list of 1-40 questions')
    seen, items = set(), []
    for item in raw:
        if not isinstance(item, dict):
            raise WorkflowError('Each item must be an object with key and text, locator or page')
        key = item.get('key')
        if not isinstance(key, str) or not key.strip() or len(key) > 40 or key in seen:
            raise WorkflowError('Each item needs its own key of at most 40 characters, e.g. "Q1"')
        seen.add(key)
        text, locator, page = item.get('text'), item.get('locator'), item.get('page')
        if text is not None and (not isinstance(text, str) or len(text) > 4000):
            raise WorkflowError(f'{key}: text must be the printed question text, at most 4000 characters')
        if locator is not None and (not isinstance(locator, str) or len(locator) > 80):
            raise WorkflowError(f'{key}: locator must be at most 80 characters, e.g. "WST01 January 2026 Q2"')
        if page is not None and (type(page) is not int or not 1 <= page <= count):
            raise WorkflowError(f'{key}: page must be a 1-based page of the script (1-{count})')
        if not (text or locator or page):
            raise WorkflowError(f'{key}: give the printed text, a printed reference (locator) or the page')
        items.append({'key': key, 'text': text, 'locator': locator, 'page': page})
    return items


def _pages(raw: str, count: int) -> list[int]:
    pages = []
    for token in (t for t in re.split(r'[,\s]+', raw or '') if t):
        if not re.fullmatch(r'[1-9]\d*', token) or int(token) > count:
            raise WorkflowError(f'--photo-pages: {token!r} is not a page of the script (1-{count})')
        if int(token) not in pages:
            pages.append(int(token))
    return pages


def upload(script: Path, work: Path, page: int) -> bytes:
    """The page as a JPEG under the service's 8 MB limit, upright where anything renders here."""
    target = ensure_dir(work / 'identify') / f'upload-{page}.jpg'
    if render_jpeg(script, page, UPLOAD_EDGE, target) and 0 < target.stat().st_size <= MAX_UPLOAD:
        return target.read_bytes()
    pictures = photos.embedded_jpegs(script.read_bytes()) or []
    if page <= len(pictures):  # the photo itself; the service turns it upright from its EXIF
        if len(pictures[page - 1]) <= MAX_UPLOAD:
            return pictures[page - 1]
        smaller = photos.shrink(pictures[page - 1], UPLOAD_EDGE)
        if smaller and len(smaller) <= MAX_UPLOAD:
            return smaller
    raise WorkflowError(f'Page {page} cannot be pictured here for photo identification (that needs PyMuPDF, poppler '
                        'or the page as a photo under 8 MB); identify it from its printed text instead, or ask the user')


def _candidates(found: object) -> list[dict]:
    return [{key: item.get(key) for key in SHOWN if item.get(key) is not None}
            for item in (found if isinstance(found, list) else []) if isinstance(item, dict)]


def identify(script: Path, work: Path, raw_items: object, photo_pages: str,
             api: Callable[..., dict], origin: str) -> dict:
    count = pages_in(script)
    items = _items(raw_items, count) if raw_items is not None else []
    forced = _pages(photo_pages, count)
    if not items and not forced:
        raise WorkflowError('identify needs --items (printed text or reference per question) or --photo-pages')
    output = {}
    if items:
        sent = [{k: item[k] for k in ('key', 'locator', 'text') if item[k]} for item in items if item['locator'] or item['text']]
        answers = {}
        if sent:
            response = api(origin, 'POST', '/identify', {'items': sent})
            answers = {entry.get('key'): entry for entry in response.get('items') or [] if isinstance(entry, dict)}
        output['items'] = []
        for item in items:
            answer = answers.get(item['key']) or {}
            row = {'key': item['key'], 'matched_by': answer.get('matched_by', 'none'), 'candidates': _candidates(answer.get('candidates'))}
            if item['page']:
                row['page'] = item['page']
            output['items'].append(row)
    # A page goes to photo identification when it was named for it, or when none of its questions was found by text.
    unmatched = [row['page'] for row in output.get('items', []) if row.get('page') and not row['candidates']]
    pages = forced + [page for page in dict.fromkeys(unmatched) if page not in forced]
    if pages:
        output['photo'] = []
        stopped = None
        for page in pages:
            if stopped:
                output['photo'].append({'page': page, 'error': stopped})
                continue
            try:
                data = upload(script, work, page)
                response = api(origin, 'POST', '/identify-photo',
                               {'image_base64': base64.b64encode(data).decode('ascii'), 'mime_type': 'image/jpeg'})
            except WorkflowError as exc:
                output['photo'].append({'page': page, 'error': str(exc)})
                if DAILY_LIMIT in str(exc):
                    stopped = str(exc)
                continue
            output['photo'].append({'page': page, 'matched_by': response.get('matched_by', 'none'),
                                    'extracted_text': str(response.get('extracted_text') or '')[:300],
                                    'candidates': _candidates(response.get('candidates'))})
    return output


def run(args, api: Callable[..., dict], origin: str) -> None:
    script = Path(args.script).expanduser().resolve()
    if not script.is_file() or script.read_bytes()[:4] != b'%PDF':
        raise WorkflowError('Script must be an existing PDF (for photos, the script that start reported)')
    work = Path(args.work_dir).expanduser().resolve()
    ensure_dir(work)
    if args.items is None and args.items_json is None and not args.photo_pages:
        print(json.dumps({'pages': views(script, work)}, ensure_ascii=False))
        return
    raw = json.loads(args.items if args.items is not None else Path(args.items_json).read_text(encoding='utf-8')) \
        if (args.items is not None or args.items_json is not None) else None
    print(json.dumps(identify(script, work, raw, args.photo_pages, api, origin), ensure_ascii=False))
