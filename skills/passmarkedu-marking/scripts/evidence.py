"""Batch packets, judgement evidence validation and report explanations."""
from __future__ import annotations

import math
from pathlib import Path

import blanks
import review_detail
from common import WorkflowError, digest, read
from rendering import validate_box

AUTO_COMMENT = {'zh': '本小问全部得分。', 'en': 'Full marks for this part.'}
# Why a step is not high confidence (judging.md, Confidence).
STEP_REASONS = ('legibility', 'condition', 'deletion', 'alternative_method', 'follow_through', 'drawing', 'levels', 'scheme_gap')


def _kept(value: object) -> bool:
    return value is not None and value is not False and value != [] and value != {} and value != ''


def unit_template(unit: dict) -> dict:
    """Real-ID judgement fields of one supported unit, all still unfinished (null)."""
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
    template = {'unit_id': unit['unit_id'], 'attempted': None, 'page': None, 'y': None}
    if any(step.get('visual') for step in unit.get('steps', [])):
        template['figure'] = None  # {"page": N, "box": [...]} around the drawing; stays null without one
    return {**template, 'transcript': None, 'final_answer': None, 'steps': steps}


def question_view(work: Path, number: str, pages: list[int]) -> dict:
    """One question's judging material: scoring units without empty fields, and its evidence template."""
    packet = read(work / 'questions' / f'{number}.json')
    view = {key: packet[key] for key in ('number', 'marks', 'subject', 'source') if packet.get(key) is not None}
    view['pages'] = pages
    if packet.get('ms_image_path'):
        view['ms_image'] = packet['ms_image_path']
    view['units'] = []
    for unit in packet['scoring_units']:
        compact = {key: unit[key] for key in ('unit_id', 'label', 'marks') if _kept(unit.get(key))}
        final = unit.get('final_answer')
        final = {key: value for key, value in final.items() if _kept(value)} if isinstance(final, dict) else final
        if _kept(final):
            compact['final_answer'] = final
        compact['steps'] = [{key: value for key, value in step.items() if key == 'step_id' or _kept(value)}
                            for step in unit.get('steps', [])]
        view['units'].append(compact)
    view['evidence_template'] = [unit_template(unit) for unit in packet['scoring_units']]
    return view


def evidence_target(work: Path, numbers: list[str]) -> Path:
    return work / 'evidence' / f'batch-{"-".join(numbers)}.json'


def unit_files(work: Path) -> dict[str, tuple[Path, dict]]:
    """Units found in evidence/*.json, keyed by ID, with the file holding them (first file wins)."""
    found = {}
    for path in sorted((work / 'evidence').glob('*.json')):
        try:
            units = read(path).get('units')
        except (ValueError, WorkflowError):
            continue
        for unit in units if isinstance(units, list) else []:
            if isinstance(unit, dict) and isinstance(unit.get('unit_id'), str):
                found.setdefault(unit['unit_id'], (path, unit))
    return found


def merged(work: Path, state: dict) -> dict:
    """All judgement files as one payload; every supported unit exactly once, in checklist order."""
    checklist = read(work / 'checklist.json')
    supported = {}
    for q in checklist['questions']:
        for u in q['scoring_units']:
            if u.get('supported'):
                supported[u['unit_id']] = u
    found = {}
    for path in sorted((work / 'evidence').glob('*.json')):
        units = read(path).get('units')
        if not isinstance(units, list):
            raise WorkflowError(f'{path.name}: units must be a list')
        for unit in units:
            if not isinstance(unit, dict):
                raise WorkflowError(f'{path.name}: invalid unit')
            uid = unit.get('unit_id')
            if uid not in supported or (uid in found and found[uid][0] == path.name):
                raise WorkflowError(f'{path.name}: unknown or duplicate unit_id {uid}')
            if uid in found:
                raise WorkflowError(f'duplicate unit_id {uid} in {found[uid][0]} and {path.name}; keep each unit in one evidence file')
            found[uid] = (path.name, unit)
    for q in checklist['questions']:
        missing = [u['unit_id'] for u in q['scoring_units'] if u.get('supported') and u['unit_id'] not in found]
        if missing:
            raise WorkflowError(f'Question {q["number"]}: missing units {sorted(missing)}')
    all_units = []
    page_count = len(state['pages'])
    for uid, spec in supported.items():
        name, unit = found[uid]
        validate_unit(f'{name}: {uid}', unit, spec, page_count)
        all_units.append(unit)
    # A unit judged blank goes with a check of its pages against the printed booklet.
    checks = blanks.for_run(work, state, checklist['questions'], {u['unit_id']: u['attempted'] for u in all_units})
    for unit in all_units:
        if unit['attempted'] is False:
            unit['blank_check'] = checks.get(unit['unit_id'], 'unknown')
    result = {**state['identity'], 'lang': state['lang'], 'units': all_units}
    if checklist.get('scheme_revision'):
        result['scheme_revision'] = checklist['scheme_revision']
    return result


def validate_figure(uid: str, figure: object, page_count: int) -> None:
    """``figure`` marks where a unit's drawing is, for the review note: a page and a crop-style box of any size."""
    page = figure.get('page') if isinstance(figure, dict) else None
    if type(page) is not int or page < 1 or (page_count and page > page_count):
        raise WorkflowError(f'{uid}: figure needs the original 1-based page of the drawing and a box')
    try:
        validate_box(figure.get('box'), f'{uid}: figure')
    except ValueError as exc:
        raise WorkflowError(str(exc)) from None


def validate_unit(uid: str, unit: dict, spec: dict, page_count: int) -> None:
    if unit.get('figure') is not None:
        validate_figure(uid, unit['figure'], page_count)
    attempted = unit.get('attempted')
    if type(attempted) is not bool:
        raise WorkflowError(f'{uid}: attempted must be a JSON boolean')
    if not attempted:
        if unit.get('steps') not in ([], None):
            raise WorkflowError(f'{uid}: unattempted unit must have no steps')
        return
    page, y = unit.get('page'), unit.get('y')
    if type(page) is not int or page < 1 or (page_count and page > page_count):
        raise WorkflowError(f'{uid}: invalid 1-based page')
    if type(y) not in (float, int) or not math.isfinite(y) or not 0 <= y <= 1:
        raise WorkflowError(f'{uid}: y must be between 0 and 1')
    for field in ('transcript', 'final_answer'):
        if not isinstance(unit.get(field), str):
            raise WorkflowError(f'{uid}: {field} must be completed text')
    if not unit['transcript'].strip():
        raise WorkflowError(f'{uid}: transcript is empty')
    steps = unit.get('steps')
    if not isinstance(steps, list):
        raise WorkflowError(f'{uid}: steps must be a list')
    scheme = {s['step_id']: s for s in spec['steps']}
    seen_steps = set()
    groups = {}
    for s in scheme.values():
        group = s.get('alternative_group')
        if group is not None:
            groups.setdefault(group, set()).add(s['step_id'])
    for step in steps:
        if not isinstance(step, dict):
            raise WorkflowError(f'{uid}: invalid step')
        sid = step.get('step_id')
        if sid not in scheme or sid in seen_steps:
            raise WorkflowError(f'{uid}: unknown or duplicate step_id {sid}')
        seen_steps.add(sid)
        if type(step.get('present')) is not bool:
            raise WorkflowError(f'{uid}/{sid}: present must be a JSON boolean')
        if step.get('confidence') not in ('high', 'medium', 'low') or not isinstance(step.get('evidence'), str):
            raise WorkflowError(f'{uid}/{sid}: complete confidence and evidence')
        if step['confidence'] != 'high' and (step.get('reason') not in STEP_REASONS
                                             or not isinstance(step.get('note'), str) or not step['note'].strip()):
            raise WorkflowError(f'{uid}/{sid}: {step["confidence"]} confidence needs a reason ({", ".join(STEP_REASONS)}) '
                                'and a one-sentence note')
        kind_spec = scheme[sid]
        kind = kind_spec.get('type', 'point')
        if kind == 'numeric' and not isinstance(step.get('value'), str):
            raise WorkflowError(f'{uid}/{sid}: numeric value must be text')
        if kind == 'pick_n' and (not isinstance(step.get('matched'), list) or any(type(i) is not int for i in step['matched'])):
            raise WorkflowError(f'{uid}/{sid}: matched must be integer indices')
        if kind == 'pick_n':
            options = (kind_spec.get('pick') or {}).get('options') or []
            if len(set(step['matched'])) != len(step['matched']) or any(i < 0 or i >= len(options) for i in step['matched']):
                raise WorkflowError(f'{uid}/{sid}: matched option index is invalid')
        if kind == 'level' and (type(step.get('level')) is not int or type(step.get('awarded')) is not int or not isinstance(step.get('note'), str)):
            raise WorkflowError(f'{uid}/{sid}: complete level, awarded, and note')
        if kind == 'point' and int(kind_spec.get('step_marks', 1)) > 1 and type(step.get('awarded')) is not int:
            raise WorkflowError(f'{uid}/{sid}: complete awarded marks')
        if 'awarded' in step and step['awarded'] is not None and (type(step['awarded']) is not int or not 0 <= step['awarded'] <= int(kind_spec.get('step_marks', 1))):
            raise WorkflowError(f'{uid}/{sid}: awarded marks outside step range')
        if kind == 'level' and step['level'] < 0:
            raise WorkflowError(f'{uid}/{sid}: level must be nonnegative')
    common = {sid for sid, s in scheme.items() if s.get('alternative_group') is None}
    if not common <= seen_steps:
        raise WorkflowError(f'{uid}: missing common steps {sorted(common - seen_steps)}')
    if groups and not any(route <= seen_steps for route in groups.values()):
        raise WorkflowError(f'{uid}: complete at least one alternative route')


REPORT_FIELDS = ('comment', 'headline', 'mistakes', 'solution')
# Neither report prose, the review note's detail, where the drawing sits, nor the helper's own
# blank-page check is a judgement.
NOT_JUDGEMENT = REPORT_FIELDS + ('review_detail', 'figure', 'blank_check')


def judgement_hash(unit: dict) -> str:
    return digest({key: value for key, value in unit.items() if key not in NOT_JUDGEMENT})


def judging_payload(evidence: dict) -> dict:
    return {**evidence, 'units': [{k: v for k, v in u.items() if k not in NOT_JUDGEMENT} for u in evidence['units']]}


def unit_hashes(evidence: dict, previous: dict, now_ns: int) -> dict:
    """Each unit's judgement hash and since when (ns) it has had that hash, carried over from the last check."""
    out = {}
    for unit in evidence['units']:
        sha = judgement_hash(unit)
        before = previous.get(unit['unit_id']) or {}
        since = before.get('since_ns') if before.get('sha256') == sha and type(before.get('since_ns')) is int else now_ns
        out[unit['unit_id']] = {'sha256': sha, 'since_ns': since}
    return out


def scored_units(work: Path, score: dict) -> dict:
    result = {u['unit_id']: u for u in score.get('units', []) if u.get('unit_id')}
    if result:
        return result
    # Older score endpoints returned ordered units without their IDs.
    specs = [u for q in read(work / 'checklist.json')['questions'] for u in q['scoring_units']]
    if len(specs) == len(score.get('units', [])):
        return {spec['unit_id']: item for spec, item in zip(specs, score['units']) if spec.get('supported')}
    return result


def with_reports(work: Path, evidence: dict, *, require_complete: bool, page_count: int = 0) -> dict:
    checklist = read(work / 'checklist.json')
    by_id = {u['unit_id']: u for u in evidence['units']}
    checked_units = (read(work / 'check.json').get('units') or {}) if (work / 'check.json').is_file() else {}
    score = read(work / 'score.json')
    scores = scored_units(work, score)
    for question in checklist['questions']:
        number = str(question['number'])
        path = work / 'reports' / f'{number}.json'
        if not path.exists():
            continue
        report = read(path)
        units = report.get('units')
        if not isinstance(units, list):
            raise WorkflowError(f'Question {number}: report units must be a list')
        allowed = {u['unit_id'] for u in question['scoring_units'] if u.get('supported')}
        seen = set()
        for entry in units:
            if not isinstance(entry, dict) or entry.get('unit_id') not in allowed or entry['unit_id'] in seen:
                raise WorkflowError(f'Question {number}: unknown or duplicate report unit_id')
            uid = entry['unit_id']
            seen.add(uid)
            current = judgement_hash(by_id[uid])
            if 'judgement_sha256' not in entry or entry['judgement_sha256'] is None:
                # No hash to copy: the report belongs to the judgement it was written after.
                record = checked_units.get(uid) if isinstance(checked_units.get(uid), dict) else {}
                written_after = type(record.get('since_ns')) is int and path.stat().st_mtime_ns >= record['since_ns']
                if record.get('sha256') != current or not written_after:
                    raise WorkflowError(f'Question {number}/{uid}: report stale, written before the latest judgement change; '
                                        'rerun check and update this explanation')
            elif entry['judgement_sha256'] != current:
                raise WorkflowError(f'Question {number}/{uid}: report judgement_sha256 stale; rerun check and update this explanation')
            for field in REPORT_FIELDS:
                if field in entry:
                    if field in ('mistakes', 'solution'):
                        if not isinstance(entry[field], list):
                            raise WorkflowError(f'Question {number}/{uid}: report {field} must be a list')
                    elif not isinstance(entry[field], str):
                        raise WorkflowError(f'Question {number}/{uid}: report {field} must be text')
                    by_id[uid][field] = entry[field]
            if 'review_detail' in entry and review_detail.listed(scores.get(uid, {})):
                by_id[uid]['review_detail'] = entry['review_detail']  # only the review note reads it
    if require_complete:
        for question in checklist['questions']:
            number = str(question['number'])
            for spec in question['scoring_units']:
                if not spec.get('supported'):
                    continue
                uid = spec['unit_id']
                unit = by_id[uid]
                awarded = scores.get(uid, {}).get('awarded')
                max_marks = scores.get(uid, {}).get('max_marks', spec.get('marks'))
                if awarded is None:
                    raise WorkflowError(f'Question {number}/{uid}: score lacks unit marks; rerun check')
                if unit['attempted'] and awarded >= max_marks and not (isinstance(unit.get('comment'), str) and unit['comment'].strip()):
                    unit['comment'] = AUTO_COMMENT.get(evidence.get('lang'), AUTO_COMMENT['en'])
                needs = report_needs(unit, awarded, max_marks, scores[uid].get('steps', []), review_detail.listed(scores[uid]))
                for field in needs:
                    value = unit.get(field)
                    if field == 'review_detail':
                        try:
                            review_detail.validate(value, scores[uid], page_count)
                        except WorkflowError as exc:
                            raise WorkflowError(f'Question {number}/{uid}: report {exc}') from None
                        continue
                    if field in ('comment', 'headline'):
                        valid = isinstance(value, str) and bool(value.strip())
                    elif field == 'solution':
                        valid = isinstance(value, list) and bool(value) and all(isinstance(x, str) and x.strip() for x in value)
                    else:
                        valid = isinstance(value, list) and bool(value) and all(isinstance(x, dict) and all(isinstance(x.get(k), str) and x[k].strip() for k in ('wrote', 'why', 'should')) for x in value)
                    if not valid:
                        raise WorkflowError(f'Question {number}/{uid}: report {field} required after scoring')
    return evidence


def report_needs(unit: dict, awarded: int, max_marks: int, scored_steps: list[dict], listed: bool = False) -> list[str]:
    """The report fields a unit needs; a part the review note lists also needs its `review_detail`."""
    detail = ['review_detail'] if listed else []
    if not unit['attempted']:
        return ['solution'] + detail
    if awarded < max_marks:
        losses = [s for s in scored_steps if s.get('status') != 'not_in_chosen_route'
                  and (s.get('awarded') or 0) < (s.get('step_marks') or 0)]
        if losses and all(s.get('confidence') == 'low' for s in losses):
            return ['comment', 'solution'] + detail
        return ['comment', 'headline', 'mistakes', 'solution'] + detail
    return detail  # full marks: submit adds the fixed comment


def explanation_tasks(work: Path, evidence: dict, score: dict) -> tuple[list[dict], int]:
    """Report tasks for lost marks and blanks, and the number of full-mark units that need none."""
    scored = scored_units(work, score)
    specs = {}
    for q in read(work / 'checklist.json')['questions']:
        for u in q['scoring_units']:
            if u.get('supported'):
                specs[u['unit_id']] = (str(q['number']), u)
    output = []
    automatic = 0
    for unit in evidence['units']:
        uid = unit['unit_id']
        number, spec = specs[uid]
        scored_unit = scored.get(uid, {})
        awarded = scored_unit.get('awarded')
        maximum = scored_unit.get('max_marks', spec.get('marks'))
        if awarded is None:
            continue
        listed = review_detail.listed(scored_unit)
        if unit['attempted'] and awarded >= maximum:
            automatic += 1
            if not listed:
                continue
        scored_steps = scored_unit.get('steps', [])
        # A listed part's steps carry their mark-scheme wording, for the review_detail quote.
        keys = ('step_id', 'mark_code', 'awarded', 'step_marks', 'status', 'confidence', 'evidence') + (('description',) if listed else ())
        task = {'unit_id': uid, 'question': number, 'label': spec.get('label'),
                'awarded': awarded, 'max_marks': maximum, 'attempted': unit['attempted'],
                'needs': report_needs(unit, awarded, maximum, scored_steps, listed),
                'judgement_sha256': judgement_hash(unit),
                'report_file': str(work / 'reports' / f'{number}.json'),
                'transcript': unit.get('transcript'), 'final_answer': unit.get('final_answer'),
                'scored_steps': [{k: step.get(k) for k in keys} for step in scored_steps]}
        if listed:
            task.update(page=unit.get('page'), review_reasons=(scored_unit.get('review') or {}).get('reasons') or [])
        output.append(task)
    return output, automatic


def score_summary(score: dict, work: Path | None = None, evidence: dict | None = None) -> dict:
    locations = {}
    if work is not None:
        files = unit_files(work)
        for question in read(work / 'checklist.json')['questions']:
            number = str(question['number'])
            for unit in question['scoring_units']:
                path, found = files.get(unit['unit_id'], (None, {}))
                locations[unit['unit_id']] = {'question': number, 'page': found.get('page'),
                                               'evidence_file': str(path) if path else None}
    totals = {}
    for unit in score.get('units', []):
        if unit.get('status') == 'unsupported':
            continue
        number = str(unit.get('question_number', '?'))
        item = totals.setdefault(number, {'awarded': 0, 'max_marks': 0})
        item['awarded'] += unit.get('awarded') or 0
        item['max_marks'] += unit.get('max_marks') or 0
    tasks, automatic = explanation_tasks(work, evidence, score) if work and evidence else ([], 0)
    return {'total': score.get('total'), 'max_total': score.get('max_total'),
            'grade': score.get('grade'), 'grade_range': score.get('grade_range'),
            'marked_max_total': sum(item['max_marks'] for item in totals.values()),
            'unsupported': score.get('unsupported') or [], 'questions': totals,
            'reliability': score.get('reliability'),
            'review_items': [{k: x.get(k) for k in ('label', 'page', 'reasons', 'notes', 'final_answer', 'scheme_conflict')} for x in score.get('review_items', [])],
            'recheck': [{**locations.get(x.get('unit_id'), {}), **{k: x.get(k) for k in ('unit_id', 'label', 'step_id', 'mark_code', 'reasons', 'check')}} for x in score.get('recheck', [])],
            'score_path': str(work / 'score.json') if work else 'score.json',
            'explanation_tasks': tasks, 'auto_comment_units': automatic}


def compact_summary(summary: dict, work: Path) -> dict:
    path = str(work / 'check-summary.json')
    fields = ('unit_id', 'question', 'label', 'awarded', 'max_marks', 'needs',
              'judgement_sha256', 'report_file')
    return {**{key: value for key, value in summary.items() if key != 'explanation_tasks'},
            'summary_path': path, 'explanation_details_path': path,
            'explanation_tasks': [{key: task.get(key) for key in fields}
                                  for task in summary.get('explanation_tasks', [])]}
