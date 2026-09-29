#!/usr/bin/env python3
"""Deterministic local staging for the PassMarkedu visual marking workflow."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

import config
import corrections
import pagemap
import review_detail
from common import WorkflowError, digest, ensure_dir, read
from evidence import (compact_summary, evidence_target, judging_payload, merged, question_view,
                      score_summary, unit_files, unit_hashes, with_reports)
from rendering import (MAX_DPI, content_box, crop_dpi, crop_page, page_count, page_sizes, render_cover,
                       render_pages, render_tiles, validate_box)


SAFE_TOKEN = re.compile(r'[A-Za-z0-9._:-]{1,80}')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def dump(path: Path, value: object) -> None:
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def token(origin: str) -> str:
    path = config.token_path(origin, Path.home(), Path.cwd())
    if not path.is_file():
        raise WorkflowError('Authentication token is missing; run skill login first')
    return path.read_text(encoding='utf-8').strip()


def api(origin: str, method: str, suffix: str, payload: object = None, multipart: bytes | None = None, content_type: str | None = None) -> dict:
    url = origin + '/api/v1/marking-kit' + suffix
    body = multipart if multipart is not None else (json.dumps(payload).encode() if payload is not None else None)
    headers = {'Authorization': 'Bearer ' + token(origin)}
    if content_type:
        headers['Content-Type'] = content_type
    elif body is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with build_opener(NoRedirect).open(req, timeout=90) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise WorkflowError('API returned an unexpected response')
        return result
    except HTTPError as exc:
        # Parse only known error markers; bodies can reflect evidence or signed URLs.
        classification = ''
        try:
            error = json.loads(exc.read(4096))
            if isinstance(error, dict):
                detail = error.get('detail')
                code = error.get('code')
                envelope = error.get('error') if isinstance(error.get('error'), dict) else {}
                if exc.code >= 500:
                    # The service's error code and request ID are what support needs; nothing else is echoed.
                    service_code, request_id = (value if isinstance(value, str) and SAFE_TOKEN.fullmatch(value) else None
                                                for value in (envelope.get('code'), envelope.get('request_id')))
                    classification = ', '.join(filter(None, (service_code, request_id and f'request_id {request_id}')))
                if isinstance(detail, str) and detail.startswith('paper_not_supported'):
                    classification = 'paper_not_supported (no credit charged)'
                elif exc.code == 409 and isinstance(detail, str) and detail.startswith('paper_variant_unclear'):
                    classification = detail + ' — re-read the paper reference on the cover and prepare again'
                elif exc.code == 409 and detail == 'scheme_changed':
                    classification = 'scheme_changed; reprepare in a new work directory'
                elif exc.code == 422 and detail == 'scheme_dependency_unresolved':
                    classification = 'scheme_dependency_unresolved; check the affected scoring unit and contact support'
                elif exc.code == 429 and 'quota_exceeded' in (code, envelope.get('code')):
                    classification = 'quota_exceeded'
        except (ValueError, OSError):
            pass
        if not classification and exc.code == 404 and suffix.split('?')[0] in {'/papers', '/question-sets'}:
            classification = 'paper_not_found'
        if not classification and exc.code == 401:
            classification = 'authentication_expired'
        detail = f' ({classification})' if classification else ''
        raise WorkflowError(f'API {method} {suffix.split("?")[0]} returned HTTP {exc.code}{detail}') from None
    except (URLError, TimeoutError) as exc:
        raise WorkflowError(f'API {method} {suffix.split("?")[0]} could not connect') from None


def asset(url: str, destination: Path, origin: str, pdf: bool = False) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise WorkflowError('Invalid asset URL')
    # Signed asset requests intentionally carry no marking-kit Authorization header.
    try:
        with urlopen(Request(url), timeout=90) as response:
            data = response.read()
    except (HTTPError, URLError, TimeoutError):
        raise WorkflowError(f'Could not download {destination.name}; retry submit later') from None
    if pdf and not data.startswith(b'%PDF'):
        raise WorkflowError(f'{destination.name} was not a PDF; retry submit later')
    ensure_dir(destination.parent)
    temp = destination.with_name(destination.name + '.tmp')
    temp.write_bytes(data)
    os.replace(temp, destination)


def ms_extension(url: str) -> str:
    parsed = urlsplit(url)
    extension = Path(parsed.path).suffix.lower()
    return extension if extension in {'.png', '.jpg', '.jpeg', '.webp', '.gif'} else '.img'


def image_extension(data: bytes, url: str) -> str:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return '.webp'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return '.gif'
    return ms_extension(url)


def work_state(work: Path) -> dict:
    state = read(work / 'manifest.json')
    if state['origin'] != config.resolve_origin():
        raise WorkflowError('Work directory belongs to a different API origin')
    return state


MANAGED_PATHS = (
    'manifest.json', 'checklist.json', 'script.pdf', 'pages', 'tiles', 'questions',
    'evidence', 'reports', 'crops', 'evidence.json', 'score.json',
    'check.json', 'check-summary.json', 'result.json', 'question-paper.pdf',
    'annotated_script.pdf', 'marking_report.pdf',
)


def is_pdf(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open('rb') as handle:
        return handle.read(4) == b'%PDF'


def version_key(value: object) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r'\d+', str(value or '')))


def update_available(origin: str) -> dict | None:
    """The service's newer skill release; any failure means no notice."""
    try:
        with urlopen(Request(origin + '/api/v1/marking-kit/skill'), timeout=5) as response:
            info = json.load(response)
        local = (config.SKILL_DIR / 'VERSION').read_text(encoding='utf-8').strip()
        if isinstance(info, dict) and version_key(info.get('version')) > version_key(local):
            return {'version': info.get('version'), 'zip_url': info.get('zip_url')}
    except Exception:
        pass
    return None


def run_directory(script: Path, chosen: str | None) -> Path:
    if chosen:
        run = Path(chosen).expanduser().resolve()
        if run.exists() and not (run / 'manifest.json').exists():
            collisions = [name for name in MANAGED_PATHS if (run / name).exists() or (run / name).is_symlink()]
            if collisions:
                raise WorkflowError(f'Run directory has helper output without a manifest: {", ".join(collisions)}')
        return ensure_dir(run)
    folder = script.parent
    skill = config.SKILL_DIR.resolve()
    if folder == skill or skill in folder.parents or any((p / '.git').exists() for p in (folder, *folder.parents)):
        folder = Path.home()  # never inside a code repository or the skill itself
    root = ensure_dir(folder / 'passmarkedu-runs')
    name = (re.sub(r'[^\w.-]+', '-', script.stem).strip('-.') or 'script') + datetime.now().strftime('-%Y%m%d-%H%M')
    for number in range(1, 1000):
        run = root / (name if number == 1 else f'{name}-{number}')
        try:
            run.mkdir()
            return run
        except FileExistsError:
            continue
    raise WorkflowError('Could not create a new run directory')


def start(args: argparse.Namespace) -> None:
    script = Path(args.script).expanduser().resolve()
    if not is_pdf(script):
        raise WorkflowError('Script must be an existing PDF')
    origin = config.resolve_origin()
    token_file = config.token_path(origin, Path.home(), Path.cwd())
    run = run_directory(script, args.run_dir)
    cover = run / 'cover-page.png'
    shown = cover.is_file() or render_cover(script, cover)
    texts = pagemap.page_texts(script, 1, 1)
    print(json.dumps({'run_dir': str(run), 'cover_image': str(cover) if shown else None,
                      'page_count': page_count(script), 'base': origin, 'api_base': origin + '/api/v1/marking-kit',
                      'token_path': str(token_file), 'token_exists': token_file.is_file(),
                      'update': update_available(origin),
                      'cover_text_hint': pagemap.cover_reference(texts[0]) if texts else None}, ensure_ascii=False))


def paper_from_ref(reference: str, series: str | None, board: str | None) -> dict:
    """``WMA13/01A`` / ``9709/13`` plus the printed series as the /papers query."""
    if not series or not series.strip():
        raise WorkflowError('--paper-ref needs --series as printed on the cover, e.g. "January 2026"')
    text = re.sub(r'\s+', '', reference).upper()
    caie = re.fullmatch(r'(\d{4})/(\d{2})(?:/[A-Z0-9/]*)?', text)
    edexcel = re.fullmatch(r'([A-Z]{3}\d{2})(?:/(\d{2}[A-Z]?))?', text)
    found = caie or edexcel
    inferred = 'caie' if caie else 'edexcel'
    if not found or (board and board != inferred):
        raise WorkflowError('Paper reference must be copied from the cover, e.g. WMA13/01A (Edexcel) or 9709/13 (CAIE)')
    code, component = found.groups()
    paper = {'board': inferred, 'code': code}
    if component:
        paper['component'] = component
    paper['series'] = series.strip()
    return paper


def derive_page_map(work: Path, checklist: dict, state: dict) -> dict:
    """Booklet page map from the official question paper, or the reason there is none."""
    url = checklist.get('qp_pdf_url')
    if not isinstance(url, str) or not url:
        return {'reason': 'the service supplied no question paper for this sitting'}
    paper = work / 'question-paper.pdf'
    try:
        if not is_pdf(paper):
            asset(url, paper, state['origin'], pdf=True)
    except WorkflowError:
        return {'reason': 'the question paper could not be downloaded'}
    texts = pagemap.page_texts(paper)
    if texts is None:
        return {'reason': 'no PDF text extractor (pdftotext or PyMuPDF) is installed'}
    count = len(state['pages']) or page_count(work / 'script.pdf')
    if not count:
        return {'reason': 'the scan page count is unknown'}
    mapping, unassigned, reason = pagemap.derive(texts, [str(q['number']) for q in checklist['questions']], count)
    if mapping is None:
        return {'reason': reason}
    if not (work / 'page-map.json').exists():
        dump(work / 'page-map.json', mapping)
    return {'source': 'question_paper', 'map': mapping, 'unassigned': unassigned, 'booklet_start': pagemap.booklet_start(texts)}


def render_views(work: Path, state: dict) -> None:
    """Whole-page views and reading tiles, once per work directory."""
    script = work / 'script.pdf'
    if not state['pages'] and state['render_guidance'] == 'Rendering pending':
        state['pages'], state['render_guidance'] = render_pages(script, work, page_count(script))
    if state['pages'] and 'tiles' not in state:
        sizes = page_sizes(script)
        box = content_box(script, work, sizes) if sizes else None
        tiles = render_tiles(script, work, sizes, box) if sizes else None
        state.update(tiles=tiles[0] if tiles else None, tile_dpi=tiles[1] if tiles else None, trim_box=box)


def prepare(args: argparse.Namespace) -> None:
    work = Path(args.work_dir).resolve()
    script = Path(args.script).resolve()
    if not is_pdf(script):
        raise WorkflowError('Script must be an existing PDF')
    if (args.series or args.board) and not args.paper_ref:
        raise WorkflowError('--series and --board belong with --paper-ref')
    origin = config.resolve_origin()
    if args.paper_ref or args.paper_json:
        paper = paper_from_ref(args.paper_ref, args.series, args.board) if args.paper_ref else read(Path(args.paper_json))
        identity = {'paper': paper}
        method, suffix, payload = 'GET', '/papers?' + urlencode(paper), None
    else:
        raw = json.loads(Path(args.question_ids_json).read_text(encoding='utf-8'))
        ids = raw['question_ids'] if isinstance(raw, dict) else raw
        if not isinstance(ids, list) or not ids or not all(isinstance(x, str) for x in ids):
            raise WorkflowError('question_ids_json must contain a nonempty list of IDs')
        question_set = {'question_ids': ids}
        parts = raw.get('parts') if isinstance(raw, dict) else None
        if parts is not None:
            if not isinstance(parts, dict) or not all(
                    key in ids and isinstance(labels, list) and labels and all(isinstance(x, str) and x.strip() for x in labels)
                    for key, labels in parts.items()):
                raise WorkflowError('parts must map question IDs from question_ids to nonempty lists of sub-part labels')
            if parts:
                question_set['parts'] = parts
        # Every later call (score, results) sends this same object from the manifest.
        identity = {'question_set': question_set}
        method, suffix, payload = 'POST', '/question-sets', question_set
    script_sha = hashlib.sha256(script.read_bytes()).hexdigest()
    manifest_path = work / 'manifest.json'
    resumed = manifest_path.exists()
    if resumed:
        state = work_state(work)
        if state['identity'] != identity or state['script_sha256'] != script_sha or state['lang'] != args.lang:
            raise WorkflowError('Work directory has a different paper, script, or language; use a new directory')
        checklist = read(work / 'checklist.json')
        fresh = api(origin, method, suffix, payload)
        if checklist.get('scheme_revision') != fresh.get('scheme_revision'):
            raise WorkflowError('Scheme changed; reprepare in a new work directory before judging')
    else:
        collisions = [name for name in MANAGED_PATHS
                      if (work / name).exists() or (work / name).is_symlink()]
        if collisions:
            raise WorkflowError(f'Work directory has helper output without a manifest: {", ".join(collisions)}')
        checklist = api(origin, method, suffix, payload)
        ensure_dir(work)
        dump(work / 'checklist.json', checklist)
    questions = checklist.get('questions')
    if not isinstance(questions, list) or not questions:
        raise WorkflowError('Checklist has no questions')
    local_script = work / 'script.pdf'
    if not local_script.exists():
        shutil.copyfile(script, local_script)
    numbers = [str(q['number']) for q in questions]
    if len(numbers) != len(set(numbers)) or any(not re.fullmatch(r'[A-Za-z0-9._-]+', n) for n in numbers):
        raise WorkflowError('Duplicate or unsafe question number')
    if not resumed:
        dump(manifest_path, {'origin': origin, 'identity': identity, 'script_sha256': script_sha,
                             'lang': args.lang, 'questions': numbers, 'pages': [], 'render_guidance': 'Rendering pending'})
    state = read(manifest_path)
    render_views(work, state)
    dump(manifest_path, state)
    if 'paper' in identity and 'page_map' not in state:
        state['page_map'] = derive_page_map(work, checklist, state)
        dump(manifest_path, state)
    packets = ensure_dir(work / 'questions')
    ensure_dir(work / 'evidence')
    ensure_dir(work / 'reports')
    for question in questions:
        number = str(question['number'])
        ms_path = None
        if question.get('ms_image_url'):
            found = [p for p in packets.glob(f'{number}-ms.*') if p.suffix != '.download']
            if found:
                ms_path = found[0]
            else:
                initial = packets / f'{number}-ms.download'
                asset(question['ms_image_url'], initial, origin)
                ms_path = packets / f'{number}-ms{image_extension(initial.read_bytes(), question["ms_image_url"])}'
                os.replace(initial, ms_path)
        supported = [unit for unit in question.get('scoring_units', []) if unit.get('supported')]
        packet = {k: v for k, v in question.items() if k != 'ms_image_url'}
        packet['scoring_units'] = supported
        packet['subject'] = question.get('subject', checklist.get('subject'))
        packet['ms_image_path'] = str(ms_path.resolve()) if ms_path else None
        packet['original_script_path'] = str(local_script.resolve())
        packet_path = packets / f'{number}.json'
        if not packet_path.exists():
            dump(packet_path, packet)
    print(json.dumps(preparation_summary(work, state, checklist, resumed), ensure_ascii=False))


def preparation_summary(work: Path, state: dict, checklist: dict, resumed: bool) -> dict:
    derived = state.get('page_map') or {}
    effective = derived.get('map')
    if (work / 'page-map.json').is_file():
        try:
            effective = read(work / 'page-map.json')
        except (ValueError, WorkflowError):
            effective = None
    tiles = state.get('tiles') or []
    count = len(state['pages'])
    index = []
    for q in checklist['questions']:
        number = str(q['number'])
        entry = {'number': number, 'subject': q.get('subject', checklist.get('subject')),
                 'supported_units': sum(bool(u.get('supported')) for u in q.get('scoring_units', [])),
                 'unsupported': [{'label': u.get('label'), 'marks': u.get('marks')} for u in q.get('scoring_units', []) if not u.get('supported')]}
        pages = (effective or {}).get(number)
        if isinstance(pages, list) and pages and all(type(p) is int and 1 <= p <= len(tiles) for p in pages):
            entry['pages'] = pages
            entry['tiles'] = [tile for page in pages for tile in tiles[page - 1]]
        elif isinstance(pages, list):
            entry['pages'] = pages
        index.append(entry)
    output = {'status': 'resumed' if resumed else 'prepared', 'questions': index}
    if effective:
        used = {p for pages in effective.values() if isinstance(pages, list) for p in pages}
        output['page_map_source'] = 'question_paper' if effective == derived.get('map') else 'page-map.json'
        output['unassigned_pages'] = [p for p in range(1, count + 1) if p not in used]
    else:
        output['page_map'] = None
        output['page_map_reason'] = derived.get('reason') or 'mixed questions: build the map from the whole-page views'
    output['whole_pages'] = {str(page): path for page, path in enumerate(state['pages'], 1)}
    if state.get('tile_dpi'):
        output['tile_dpi'] = min(state['tile_dpi'])
    if state['render_guidance']:
        output['render_guidance'] = state['render_guidance']
    return output


def selected_pages(state: dict, number: str, raw_pages: list, work: Path) -> list[int]:
    selected = []
    count = len(state['pages']) or page_count(work / 'script.pdf')
    for raw in raw_pages:
        if type(raw) is not int and (not isinstance(raw, str) or not re.fullmatch(r'[1-9]\d*', raw)):
            raise WorkflowError(f'Question {number}: pages must be 1-based integers')
        page = int(raw)
        if page < 1 or (count is not None and page > count):
            raise WorkflowError(f'Question {number}: page {page} outside rendered script')
        if selected and page <= selected[-1]:
            raise WorkflowError(f'Question {number}: pages must be ordered unique original pages')
        selected.append(page)
    return selected


def question(args: argparse.Namespace) -> None:
    work = Path(args.work_dir).resolve()
    state = work_state(work)
    number = str(args.number)
    if number not in state['questions']:
        raise WorkflowError('Unknown question number')
    view = question_view(work, number, selected_pages(state, number, args.pages.split(',') if args.pages else [], work))
    files = unit_files(work)
    held = [files[unit['unit_id']][0] for unit in view['evidence_template'] if unit['unit_id'] in files]
    target = held[0] if held else evidence_target(work, [number])
    print(json.dumps({'evidence_file': str(target), 'evidence_exists': target.exists(), 'questions': [view]}, ensure_ascii=False))


def batch(args: argparse.Namespace) -> None:
    work = Path(args.work_dir).resolve()
    state = work_state(work)
    numbers = args.numbers.split(',')
    if not numbers or len(numbers) > 2 or len(numbers) != len(set(numbers)) or any(n not in state['questions'] for n in numbers):
        raise WorkflowError('Batch needs one or two distinct known question numbers')
    map_path = Path(args.pages_map).resolve() if args.pages_map else work / 'page-map.json'
    if not map_path.is_file():
        raise WorkflowError('No page map yet: save page-map.json in the work directory from the whole-page views, then run batch')
    mapping = read(map_path)
    if not set(numbers) <= set(mapping):
        raise WorkflowError('pages-map is missing a selected batch question')
    if not set(mapping) <= set(state['questions']):
        raise WorkflowError('pages-map has an unknown question number')
    views = []
    for number in numbers:
        raw = mapping[number]
        if not isinstance(raw, list) or not raw:
            raise WorkflowError(f'Question {number}: pages-map needs a nonempty page list including continuations')
        views.append(question_view(work, number, selected_pages(state, number, raw, work)))
    target = evidence_target(work, numbers)
    output = {'evidence_file': str(target), 'evidence_exists': target.exists(), 'questions': views}
    if state['render_guidance']:
        output['render_guidance'] = state['render_guidance']
    print(json.dumps(output, ensure_ascii=False))


def crop(args: argparse.Namespace) -> None:
    work = Path(args.work_dir).resolve()
    state = work_state(work)
    raw = json.loads(args.regions if args.regions is not None else Path(args.regions_json).read_text(encoding='utf-8'))
    if not isinstance(raw, list) or not raw:
        raise WorkflowError('regions must be a nonempty JSON list')
    sizes = page_sizes(work / 'script.pdf')
    if not sizes:
        raise WorkflowError('Crop needs installed PyMuPDF or pdfinfo/pdftoppm')
    tile_dpi = state.get('tile_dpi') or []
    seen = set()
    regions, problems = [], []
    for item in raw:
        if not isinstance(item, dict):
            raise WorkflowError('Each crop region must be an object')
        ident = item.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', ident) or ident in seen:
            raise WorkflowError('Crop region id must be unique and filename-safe')
        seen.add(ident)
        page = item.get('page')
        if type(page) is not int or page < 1 or page > len(sizes):
            raise WorkflowError(f'Crop {ident}: page must be an original 1-based page')
        box = validate_box(item.get('box'), f'Crop {ident}')
        if box[2] - box[0] > 0.5 + 1e-9 or box[3] - box[1] > 0.5 + 1e-9:
            problems.append(f'Crop {ident}: a box may cover at most half the page width and half its height; split it into smaller boxes')
            continue
        dpi = crop_dpi(sizes[page - 1], box)
        tiles_at = tile_dpi[page - 1] if page <= len(tile_dpi) else None
        if tiles_at and dpi < min(MAX_DPI, 1.3 * tiles_at):
            problems.append(f'Crop {ident}: renders at {dpi} dpi, too close to the {tiles_at}-dpi tile to show more; split it into narrower boxes')
            continue
        key = digest([state['script_sha256'], page, box, dpi, 'oriented-v2'])[:24]
        regions.append((ident, page, box, dpi, work / 'crops' / f'{key}.png'))
    if problems:
        raise WorkflowError('; '.join(problems))
    ensure_dir(work / 'crops')
    output = []
    for ident, page, box, dpi, path in regions:
        if not path.is_file():
            try:
                crop_page(work / 'script.pdf', page, box, path, dpi)
            except ValueError as exc:
                raise WorkflowError(f'Crop {ident}: {exc}') from None
        output.append({'id': ident, 'page': page, 'box': box, 'dpi': dpi, 'image': str(path)})
    print(json.dumps({'regions': output}, ensure_ascii=False))


def do_check(work: Path, state: dict) -> tuple[dict, dict]:
    evidence = merged(work, state)
    checked_path = work / 'check.json'
    score_path = work / 'score.json'
    summary_path = work / 'check-summary.json'
    judgement_sha = digest(judging_payload(evidence))
    if checked_path.is_file() and score_path.is_file() and summary_path.is_file():
        checked = read(checked_path)
        if checked.get('judgement_sha256') == judgement_sha:
            read(summary_path)
            if 'units' not in checked:  # checked by an earlier 1.10 helper
                checked['units'] = unit_hashes(evidence, {}, score_path.stat().st_mtime_ns)
                dump(checked_path, checked)
            if not (work / 'evidence.json').is_file() or digest(read(work / 'evidence.json')) != digest(evidence):
                dump(work / 'evidence.json', evidence)
            return evidence, read(score_path)
    result = api(state['origin'], 'POST', '/score', evidence)
    previous = (read(checked_path).get('units') or {}) if checked_path.is_file() else {}
    dump(work / 'evidence.json', evidence)
    dump(score_path, result)
    dump(summary_path, score_summary(result, work, evidence))
    # score.json's own timestamp dates this check on the file-system clock that also dates the reports.
    dump(checked_path, {'judgement_sha256': judgement_sha, 'review_items': result.get('review_items') or [], 'recheck': result.get('recheck') or [],
                        'units': unit_hashes(evidence, previous, score_path.stat().st_mtime_ns)})
    return evidence, result


def check(args: argparse.Namespace) -> None:
    work = Path(args.work_dir).resolve()
    do_check(work, work_state(work))
    print(json.dumps(compact_summary(read(work / 'check-summary.json'), work), ensure_ascii=False))


def issue_ids(checked: dict) -> set[str]:
    ids = set()
    for item in checked.get('recheck', []):
        ids.add('step:' + digest([item.get('unit_id'), item.get('step_id'), sorted(item.get('reasons') or [])]))
    for item in checked.get('review_items', []):
        ids.add('review:' + digest([item.get('label'), item.get('page'), sorted(item.get('reasons') or [])]))
    return ids


def correct(args: argparse.Namespace) -> None:
    work = Path(args.work_dir).resolve()
    work_state(work)
    print(json.dumps(corrections.add(work, args.label, args.marks), ensure_ascii=False))


def multipart(fields: dict[str, str], file: Path | None = None) -> tuple[bytes, str]:
    boundary = 'passmark-' + uuid.uuid4().hex
    data = bytearray()
    for name, value in fields.items():
        data.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    if file:
        data.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="script"; filename="script.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode())
        data.extend(file.read_bytes())
        data.extend(b'\r\n')
    data.extend(f'--{boundary}--\r\n'.encode())
    return bytes(data), f'multipart/form-data; boundary={boundary}'


def submit(args: argparse.Namespace) -> None:
    if args.result_id:
        try:
            uuid.UUID(args.result_id)
        except ValueError:
            raise WorkflowError('result-id must be a UUID') from None
    work = Path(args.work_dir).resolve()
    state = work_state(work)
    if not (work / 'check.json').exists():
        raise WorkflowError('Run check and review its recheck/review items before submit')
    checked = read(work / 'check.json')
    evidence = merged(work, state)
    prior_issues = issue_ids(checked)
    if digest(judging_payload(evidence)) != checked.get('judgement_sha256'):
        _, rescored = do_check(work, state)
        checked = read(work / 'check.json')
        if issue_ids(checked) - prior_issues:
            print(json.dumps({'status': 'new_review_issues',
                              **compact_summary(read(work / 'check-summary.json'), work)}, ensure_ascii=False))
            return
        evidence = merged(work, state)
    elif 'units' not in checked:
        do_check(work, state)  # checked by an earlier 1.10 helper: record each unit's judgement, no new call
    evidence = with_reports(work, evidence, require_complete=True, page_count=len(state['pages']))
    if (checked.get('review_items') or checked.get('recheck')) and not args.reviewed:
        raise WorkflowError('Review listed items against page images, then submit with --reviewed')
    result_path = work / 'result.json'
    if result_path.exists():
        result = read(result_path)
        if args.result_id and args.result_id != result.get('result_id'):
            raise WorkflowError('result_id differs from saved result')
        if result.get('_evidence_sha256') != digest(evidence):
            body, content_type = multipart({'evidence': json.dumps(corrections.attach(work, evidence), ensure_ascii=False)})
            result = api(state['origin'], 'PUT', f"/results/{result['result_id']}", multipart=body, content_type=content_type)
            result['_evidence_sha256'] = digest(evidence)
            dump(result_path, result)
            corrections.clear(work)
            for stale in (work / 'annotated_script.pdf', work / 'marking_report.pdf'):
                stale.unlink(missing_ok=True)
    else:
        sent = corrections.attach(work, evidence) if args.result_id else evidence
        body, content_type = multipart({'evidence': json.dumps(sent, ensure_ascii=False)}, None if args.result_id else work / 'script.pdf')
        suffix = f'/results/{args.result_id}' if args.result_id else '/results'
        result = api(state['origin'], 'PUT' if args.result_id else 'POST', suffix, multipart=body, content_type=content_type)
        if not result.get('result_id'):
            raise WorkflowError('Result response lacks result_id')
        result['_evidence_sha256'] = digest(evidence)
        dump(result_path, result)
        if args.result_id:
            corrections.clear(work)
    paths = {}
    for label, key in (('annotated_script', 'script_download_url'), ('marking_report', 'report_download_url')):
        url = result.get(key)
        if not isinstance(url, str) or not url:
            raise WorkflowError(f'Result lacks {key}; saved result can be retried')
        target = work / f'{label}.pdf'
        if not target.exists() or not target.read_bytes()[:4] == b'%PDF':
            asset(url, target, state['origin'], pdf=True)
        paths[label] = str(target)
    review_url = result.get('review_download_url')  # optional: older services have no review note
    if isinstance(review_url, str) and review_url:
        target = work / 'review_note.pdf'
        if not target.exists() or not target.read_bytes()[:4] == b'%PDF':
            asset(review_url, target, state['origin'], pdf=True)
        paths['review_note'] = str(target)
    final_summary = score_summary(result, work)
    output = {'result_id': result['result_id'], 'total': result.get('total'), 'max_total': result.get('max_total'),
                      'marked_max_total': final_summary['marked_max_total'], 'unsupported': final_summary['unsupported'],
                      'questions': final_summary['questions'], 'reliability': result.get('reliability'),
                      'review_items': result.get('review_items'), 'expires_at': result.get('expires_at'),
                      'annotated_script': {'path': paths['annotated_script'], 'url': result.get('script_download_url')},
                      'marking_report': {'path': paths['marking_report'], 'url': result.get('report_download_url')},
                      'review_note': {'path': paths.get('review_note'), 'url': review_url or None},
                      'over_answered': bool(result.get('over_answered'))}
    if 'question_set' not in state['identity']:
        output.update(grade=result.get('grade'), grade_range=result.get('grade_range'))
    output['check_units'] = check_units(result, work)
    output['decide_units'] = decide_units(result, work)
    print(json.dumps(output, ensure_ascii=False))


def _first_page(unit: dict, mapping: object) -> int | None:
    pages = mapping.get(str(unit.get('question_number'))) if isinstance(mapping, dict) else None
    return unit.get('page') or (pages[0] if isinstance(pages, list) and pages else None)


def _page_map(work: Path) -> object:
    try:
        return read(work / 'page-map.json') if (work / 'page-map.json').is_file() else {}
    except (ValueError, WorkflowError):
        return {}


def check_units(result: dict, work: Path) -> list[dict]:
    """Parts the service says a person should check (review tier ``check``), with the page to open."""
    mapping = _page_map(work)
    return [{'label': unit.get('label'), 'page': _first_page(unit, mapping)}
            for unit in result.get('units') or [] if (unit.get('review') or {}).get('tier') == 'check']


def decide_units(result: dict, work: Path) -> list[dict]:
    """The rows of the review note (tier ``check`` or ``glance``), numbered as the note numbers them."""
    mapping = _page_map(work)
    listed = [unit for unit in result.get('units') or [] if review_detail.listed(unit)]
    return [{'number': review_detail.circled(index), 'label': unit.get('label'), 'page': _first_page(unit, mapping)}
            for index, unit in enumerate(listed, start=1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    begin = subs.add_parser('start')
    begin.add_argument('--script', required=True)
    begin.add_argument('--run-dir')
    prep = subs.add_parser('prepare')
    prep.add_argument('--work-dir', required=True)
    prep.add_argument('--script', required=True)
    source = prep.add_mutually_exclusive_group(required=True)
    source.add_argument('--paper-ref')
    source.add_argument('--paper-json')
    source.add_argument('--question-ids-json')
    prep.add_argument('--series')
    prep.add_argument('--board', choices=('edexcel', 'caie'))
    prep.add_argument('--lang', choices=('zh', 'en'), required=True)
    one = subs.add_parser('question')
    one.add_argument('--work-dir', required=True)
    one.add_argument('--number', required=True)
    one.add_argument('--pages', default='')
    many = subs.add_parser('batch')
    many.add_argument('--work-dir', required=True)
    many.add_argument('--numbers', required=True)
    many.add_argument('--pages-map')
    crops = subs.add_parser('crop')
    crops.add_argument('--work-dir', required=True)
    boxes = crops.add_mutually_exclusive_group(required=True)
    boxes.add_argument('--regions')
    boxes.add_argument('--regions-json')
    chk = subs.add_parser('check')
    chk.add_argument('--work-dir', required=True)
    send = subs.add_parser('submit')
    send.add_argument('--work-dir', required=True)
    send.add_argument('--reviewed', action='store_true')
    send.add_argument('--result-id')
    fix = subs.add_parser('correct')
    fix.add_argument('--work-dir', required=True)
    fix.add_argument('--label', required=True)
    fix.add_argument('--marks', type=int, required=True)
    args = parser.parse_args()
    try:
        {'start': start, 'prepare': prepare, 'question': question, 'batch': batch, 'crop': crop,
         'check': check, 'submit': submit, 'correct': correct}[args.command](args)
        return 0
    except (WorkflowError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f'Workflow error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
