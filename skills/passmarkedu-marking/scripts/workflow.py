#!/usr/bin/env python3
"""Deterministic local staging for the PassMarkedu visual marking workflow."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

import config
from common import WorkflowError, digest, read
from evidence import compact_summary, merged, judging_payload, with_reports, score_summary
from rendering import crop_page, page_count, pages_for, validate_box


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
                if isinstance(detail, str) and detail.startswith('paper_not_supported'):
                    classification = 'paper_not_supported (no credit charged)'
                elif exc.code == 409 and isinstance(detail, str) and detail.startswith('paper_variant_unclear'):
                    classification = detail + ' — re-read the paper reference on the cover and prepare again'
                elif exc.code == 409 and detail == 'scheme_changed':
                    classification = 'scheme_changed; reprepare in a new work directory'
                elif exc.code == 422 and detail == 'scheme_dependency_unresolved':
                    classification = 'scheme_dependency_unresolved; check the affected scoring unit and contact support'
                elif exc.code == 429 and code == 'quota_exceeded':
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
    destination.parent.mkdir(parents=True, exist_ok=True)
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
    'manifest.json', 'checklist.json', 'script.pdf', 'pages', 'questions',
    'evidence', 'reports', 'crops', 'evidence.json', 'score.json',
    'check.json', 'check-summary.json', 'result.json',
    'annotated_script.pdf', 'marking_report.pdf',
)


def prepare(args: argparse.Namespace) -> None:
    work = Path(args.work_dir).resolve()
    script = Path(args.script).resolve()
    if not script.is_file() or not script.read_bytes()[:4] == b'%PDF':
        raise WorkflowError('Script must be an existing PDF')
    origin = config.resolve_origin()
    if args.paper_json:
        identity = {'paper': read(Path(args.paper_json))}
        query = urlencode(identity['paper'])
        method, suffix, payload = 'GET', '/papers?' + query, None
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
        work.mkdir(parents=True, exist_ok=True)
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
    page_paths, guidance = (state['pages'], state['render_guidance'])
    if not page_paths and guidance == 'Rendering pending':
        page_paths, guidance = pages_for(local_script, work)
        state.update(pages=page_paths, render_guidance=guidance)
        dump(manifest_path, state)
    packets = work / 'questions'
    packets.mkdir(exist_ok=True)
    evidence_dir = work / 'evidence'
    evidence_dir.mkdir(exist_ok=True)
    (work / 'reports').mkdir(exist_ok=True)
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
        units = []
        for unit in supported:
            steps = []
            for step in unit.get('steps', []):
                template = {'step_id': step['step_id'], 'present': None, 'confidence': None, 'evidence': None}
                if step.get('type') == 'numeric':
                    template['value'] = None
                elif step.get('type') == 'pick_n':
                    template['matched'] = None
                elif step.get('type') == 'level':
                    template.update(level=None, awarded=None, note=None)
                elif step.get('type', 'point') == 'point' and int(step.get('step_marks', 1)) > 1:
                    template['awarded'] = None
                steps.append(template)
            units.append({'unit_id': unit['unit_id'], 'attempted': None, 'page': None, 'y': None,
                          'transcript': None, 'final_answer': None, 'comment': None, 'steps': steps})
        evidence_path = evidence_dir / f'{number}.json'
        if not evidence_path.exists():
            dump(evidence_path, {'units': units})
    index = [{'number': str(q['number']), 'subject': q.get('subject', checklist.get('subject')),
              'supported_units': sum(bool(u.get('supported')) for u in q.get('scoring_units', [])),
              'unsupported': [{'label': u.get('label'), 'marks': u.get('marks')} for u in q.get('scoring_units', []) if not u.get('supported')]} for q in questions]
    print(json.dumps({'status': 'resumed' if resumed else 'prepared', 'questions': index,
                      'pages': page_paths, 'render_guidance': guidance, 'manifest': str(manifest_path)}, ensure_ascii=False))


def question(args: argparse.Namespace) -> None:
    work = Path(args.work_dir).resolve()
    state = work_state(work)
    number = str(args.number)
    if number not in state['questions']:
        raise WorkflowError('Unknown question number')
    selected = selected_pages(state, number, args.pages.split(',') if args.pages else [], work)
    packet_path = work / 'questions' / f'{number}.json'
    print(json.dumps({'packet': read(packet_path), 'packet_path': str(packet_path),
                      'evidence': str(work / 'evidence' / f'{number}.json'), 'pages': selected,
                      'original_script': str(work / 'script.pdf'), 'render_guidance': state['render_guidance']}, ensure_ascii=False))


def selected_pages(state: dict, number: str, raw_pages: list, work: Path) -> list[dict]:
    selected = []
    seen = set()
    count = len(state['pages']) or page_count(work / 'script.pdf')
    for raw in raw_pages:
        if type(raw) is not int and (not isinstance(raw, str) or not re.fullmatch(r'[1-9]\d*', raw)):
            raise WorkflowError(f'Question {number}: pages must be 1-based integers')
        page = int(raw)
        if page < 1 or (count is not None and page > count):
            raise WorkflowError(f'Question {number}: page {page} outside rendered script')
        if page in seen or (selected and page <= selected[-1]['page']):
            raise WorkflowError(f'Question {number}: pages must be ordered unique original pages')
        seen.add(page)
        selected.append({'page': page, 'image': state['pages'][page - 1] if state['pages'] else None})
    return selected


def batch(args: argparse.Namespace) -> None:
    work = Path(args.work_dir).resolve()
    state = work_state(work)
    numbers = args.numbers.split(',')
    if not numbers or len(numbers) > 2 or len(numbers) != len(set(numbers)) or any(n not in state['questions'] for n in numbers):
        raise WorkflowError('Batch needs one or two distinct known question numbers')
    mapping = read(Path(args.pages_map))
    if not set(numbers) <= set(mapping):
        raise WorkflowError('pages-map is missing a selected batch question')
    if not set(mapping) <= set(state['questions']):
        raise WorkflowError('pages-map has an unknown question number')
    output = []
    for number in numbers:
        raw = mapping[number]
        if not isinstance(raw, list) or not raw:
            raise WorkflowError(f'Question {number}: pages-map needs a nonempty page list including continuations')
        pages = selected_pages(state, number, raw, work)
        packet_path = work / 'questions' / f'{number}.json'
        packet = read(packet_path)
        output.append({'number': number, 'packet_path': str(packet_path), 'packet': packet,
                       'ms_image_path': packet.get('ms_image_path'), 'pages': pages,
                       'evidence': str(work / 'evidence' / f'{number}.json'),
                       'report': str(work / 'reports' / f'{number}.json')})
    print(json.dumps({'questions': output, 'original_script': str(work / 'script.pdf'),
                      'render_guidance': state['render_guidance']}, ensure_ascii=False))


def crop(args: argparse.Namespace) -> None:
    work = Path(args.work_dir).resolve()
    state = work_state(work)
    raw = json.loads(Path(args.regions_json).read_text(encoding='utf-8'))
    if not isinstance(raw, list) or not raw:
        raise WorkflowError('regions-json must contain a nonempty list')
    seen = set()
    regions = []
    for item in raw:
        if not isinstance(item, dict):
            raise WorkflowError('Each crop region must be an object')
        ident = item.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', ident) or ident in seen:
            raise WorkflowError('Crop region id must be unique and filename-safe')
        seen.add(ident)
        page = item.get('page')
        count = len(state['pages']) or page_count(work / 'script.pdf')
        if type(page) is not int or page < 1 or (count is not None and page > count):
            raise WorkflowError(f'Crop {ident}: page must be an original 1-based page')
        box = validate_box(item.get('box'), f'Crop {ident}')
        key = digest([state['script_sha256'], page, box, 300, 'oriented-v1'])[:24]
        path = work / 'crops' / f'{key}.png'
        regions.append((ident, page, box, path))
    (work / 'crops').mkdir(exist_ok=True)
    output = []
    for ident, page, box, path in regions:
        if not path.is_file():
            try:
                crop_page(work / 'script.pdf', page, box, path)
            except ValueError as exc:
                raise WorkflowError(f'Crop {ident}: {exc}') from None
        output.append({'id': ident, 'page': page, 'box': box, 'image': str(path)})
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
            if not (work / 'evidence.json').is_file() or digest(read(work / 'evidence.json')) != digest(evidence):
                dump(work / 'evidence.json', evidence)
            return evidence, read(score_path)
    result = api(state['origin'], 'POST', '/score', evidence)
    dump(work / 'evidence.json', evidence)
    dump(score_path, result)
    dump(summary_path, score_summary(result, work, evidence))
    dump(checked_path, {'judgement_sha256': judgement_sha, 'review_items': result.get('review_items') or [], 'recheck': result.get('recheck') or []})
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
    evidence = with_reports(work, evidence, require_complete=True)
    if (checked.get('review_items') or checked.get('recheck')) and not args.reviewed:
        raise WorkflowError('Review listed items against page images, then submit with --reviewed')
    result_path = work / 'result.json'
    if result_path.exists():
        result = read(result_path)
        if args.result_id and args.result_id != result.get('result_id'):
            raise WorkflowError('result_id differs from saved result')
        if result.get('_evidence_sha256') != digest(evidence):
            body, content_type = multipart({'evidence': json.dumps(evidence, ensure_ascii=False)})
            result = api(state['origin'], 'PUT', f"/results/{result['result_id']}", multipart=body, content_type=content_type)
            result['_evidence_sha256'] = digest(evidence)
            dump(result_path, result)
            for stale in (work / 'annotated_script.pdf', work / 'marking_report.pdf'):
                stale.unlink(missing_ok=True)
    else:
        body, content_type = multipart({'evidence': json.dumps(evidence, ensure_ascii=False)}, None if args.result_id else work / 'script.pdf')
        suffix = f'/results/{args.result_id}' if args.result_id else '/results'
        result = api(state['origin'], 'PUT' if args.result_id else 'POST', suffix, multipart=body, content_type=content_type)
        if not result.get('result_id'):
            raise WorkflowError('Result response lacks result_id')
        result['_evidence_sha256'] = digest(evidence)
        dump(result_path, result)
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
    print(json.dumps(output, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    prep = subs.add_parser('prepare')
    prep.add_argument('--work-dir', required=True)
    prep.add_argument('--script', required=True)
    source = prep.add_mutually_exclusive_group(required=True)
    source.add_argument('--paper-json')
    source.add_argument('--question-ids-json')
    prep.add_argument('--lang', choices=('zh', 'en'), required=True)
    one = subs.add_parser('question')
    one.add_argument('--work-dir', required=True)
    one.add_argument('--number', required=True)
    one.add_argument('--pages', default='')
    many = subs.add_parser('batch')
    many.add_argument('--work-dir', required=True)
    many.add_argument('--numbers', required=True)
    many.add_argument('--pages-map', required=True)
    crops = subs.add_parser('crop')
    crops.add_argument('--work-dir', required=True)
    crops.add_argument('--regions-json', required=True)
    chk = subs.add_parser('check')
    chk.add_argument('--work-dir', required=True)
    send = subs.add_parser('submit')
    send.add_argument('--work-dir', required=True)
    send.add_argument('--reviewed', action='store_true')
    send.add_argument('--result-id')
    args = parser.parse_args()
    try:
        {'prepare': prepare, 'question': question, 'batch': batch, 'crop': crop,
         'check': check, 'submit': submit}[args.command](args)
        return 0
    except (WorkflowError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f'Workflow error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
