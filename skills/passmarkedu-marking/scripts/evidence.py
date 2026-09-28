"""Validate judgement evidence and assemble report explanations."""
from __future__ import annotations

import math
from pathlib import Path

from common import WorkflowError, digest, read


def merged(work: Path, state: dict) -> dict:
    checklist = read(work / 'checklist.json')
    all_units = []
    seen_units = set()
    page_count = len(state['pages'])
    for q in checklist['questions']:
        number = str(q['number'])
        supported = {u['unit_id']: u for u in q['scoring_units'] if u.get('supported')}
        raw = read(work / 'evidence' / f'{number}.json')
        units = raw.get('units')
        if not isinstance(units, list):
            raise WorkflowError(f'Question {number}: units must be a list')
        found = set()
        for unit in units:
            if not isinstance(unit, dict):
                raise WorkflowError(f'Question {number}: invalid unit')
            uid = unit.get('unit_id')
            if uid not in supported or uid in found or uid in seen_units:
                raise WorkflowError(f'Question {number}: unknown or duplicate unit_id {uid}')
            found.add(uid)
            seen_units.add(uid)
            attempted = unit.get('attempted')
            if type(attempted) is not bool:
                raise WorkflowError(f'{uid}: attempted must be a JSON boolean')
            if attempted:
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
                scheme = {s['step_id']: s for s in supported[uid]['steps']}
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
                    spec = scheme[sid]
                    kind = spec.get('type', 'point')
                    if kind == 'numeric' and not isinstance(step.get('value'), str):
                        raise WorkflowError(f'{uid}/{sid}: numeric value must be text')
                    if kind == 'pick_n' and (not isinstance(step.get('matched'), list) or any(type(i) is not int for i in step['matched'])):
                        raise WorkflowError(f'{uid}/{sid}: matched must be integer indices')
                    if kind == 'pick_n':
                        options = (spec.get('pick') or {}).get('options') or []
                        if len(set(step['matched'])) != len(step['matched']) or any(i < 0 or i >= len(options) for i in step['matched']):
                            raise WorkflowError(f'{uid}/{sid}: matched option index is invalid')
                    if kind == 'level' and (type(step.get('level')) is not int or type(step.get('awarded')) is not int or not isinstance(step.get('note'), str)):
                        raise WorkflowError(f'{uid}/{sid}: complete level, awarded, and note')
                    if kind == 'point' and int(spec.get('step_marks', 1)) > 1 and type(step.get('awarded')) is not int:
                        raise WorkflowError(f'{uid}/{sid}: complete awarded marks')
                    if 'awarded' in step and step['awarded'] is not None and (type(step['awarded']) is not int or not 0 <= step['awarded'] <= int(spec.get('step_marks', 1))):
                        raise WorkflowError(f'{uid}/{sid}: awarded marks outside step range')
                    if kind == 'level' and step['level'] < 0:
                        raise WorkflowError(f'{uid}/{sid}: level must be nonnegative')
                common = {sid for sid, s in scheme.items() if s.get('alternative_group') is None}
                if not common <= seen_steps:
                    raise WorkflowError(f'{uid}: missing common steps {sorted(common - seen_steps)}')
                if groups and not any(route <= seen_steps for route in groups.values()):
                    raise WorkflowError(f'{uid}: complete at least one alternative route')
            elif unit.get('steps') not in ([], None):
                raise WorkflowError(f'{uid}: unattempted unit must have no steps')
            all_units.append(unit)
        if found != set(supported):
            raise WorkflowError(f'Question {number}: missing units {sorted(set(supported) - found)}')
    result = {**state['identity'], 'lang': state['lang'], 'units': all_units}
    if read(work / 'checklist.json').get('scheme_revision'):
        result['scheme_revision'] = read(work / 'checklist.json')['scheme_revision']
    return result


REPORT_FIELDS = ('comment', 'headline', 'mistakes', 'solution')


def judgement_hash(unit: dict) -> str:
    return digest({key: value for key, value in unit.items() if key not in REPORT_FIELDS})


def judging_payload(evidence: dict) -> dict:
    return {**evidence, 'units': [{k: v for k, v in u.items() if k not in REPORT_FIELDS} for u in evidence['units']]}


def scored_units(work: Path, score: dict) -> dict:
    result = {u['unit_id']: u for u in score.get('units', []) if u.get('unit_id')}
    if result:
        return result
    # Older score endpoints returned ordered units without their IDs.
    specs = [u for q in read(work / 'checklist.json')['questions'] for u in q['scoring_units']]
    if len(specs) == len(score.get('units', [])):
        return {spec['unit_id']: item for spec, item in zip(specs, score['units']) if spec.get('supported')}
    return result


def with_reports(work: Path, evidence: dict, *, require_complete: bool) -> dict:
    checklist = read(work / 'checklist.json')
    by_id = {u['unit_id']: u for u in evidence['units']}
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
            if entry.get('judgement_sha256') != judgement_hash(by_id[uid]):
                raise WorkflowError(f'Question {number}/{uid}: report judgement_sha256 stale; rerun check and update this explanation')
            for field in REPORT_FIELDS:
                if field in entry:
                    if field in ('mistakes', 'solution'):
                        if not isinstance(entry[field], list):
                            raise WorkflowError(f'Question {number}/{uid}: report {field} must be a list')
                    elif not isinstance(entry[field], str):
                        raise WorkflowError(f'Question {number}/{uid}: report {field} must be text')
                    by_id[uid][field] = entry[field]
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
                needs = report_needs(unit, awarded, max_marks, scores[uid].get('steps', []))
                for field in needs:
                    value = unit.get(field)
                    if field in ('comment', 'headline'):
                        valid = isinstance(value, str) and bool(value.strip())
                    elif field == 'solution':
                        valid = isinstance(value, list) and bool(value) and all(isinstance(x, str) and x.strip() for x in value)
                    else:
                        valid = isinstance(value, list) and bool(value) and all(isinstance(x, dict) and all(isinstance(x.get(k), str) and x[k].strip() for k in ('wrote', 'why', 'should')) for x in value)
                    if not valid:
                        raise WorkflowError(f'Question {number}/{uid}: report {field} required after scoring')
    return evidence


def report_needs(unit: dict, awarded: int, max_marks: int, scored_steps: list[dict]) -> list[str]:
    if not unit['attempted']:
        return ['solution']
    if awarded < max_marks:
        losses = [s for s in scored_steps if s.get('status') != 'not_in_chosen_route'
                  and (s.get('awarded') or 0) < (s.get('step_marks') or 0)]
        if losses and all(s.get('confidence') == 'low' for s in losses):
            return ['comment', 'solution']
        return ['comment', 'headline', 'mistakes', 'solution']
    return ['comment']


def explanation_tasks(work: Path, evidence: dict, score: dict) -> list[dict]:
    scored = scored_units(work, score)
    specs = {}
    for q in read(work / 'checklist.json')['questions']:
        for u in q['scoring_units']:
            if u.get('supported'):
                specs[u['unit_id']] = (str(q['number']), u)
    output = []
    for unit in evidence['units']:
        uid = unit['unit_id']
        number, spec = specs[uid]
        scored_unit = scored.get(uid, {})
        awarded = scored_unit.get('awarded')
        maximum = scored_unit.get('max_marks', spec.get('marks'))
        if awarded is None:
            continue
        scored_steps = scored_unit.get('steps', [])
        task = {'unit_id': uid, 'question': number, 'label': spec.get('label'),
                'awarded': awarded, 'max_marks': maximum, 'attempted': unit['attempted'],
                'needs': report_needs(unit, awarded, maximum, scored_steps),
                'judgement_sha256': judgement_hash(unit),
                'report_file': str(work / 'reports' / f'{number}.json')}
        if awarded < maximum or not unit['attempted']:
            task['transcript'] = unit.get('transcript')
            task['final_answer'] = unit.get('final_answer')
            task['scored_steps'] = [{k: step.get(k) for k in ('step_id', 'mark_code', 'awarded', 'step_marks', 'status', 'confidence', 'evidence')}
                                    for step in scored_steps]
        output.append(task)
    return output

def score_summary(score: dict, work: Path | None = None, evidence: dict | None = None) -> dict:
    locations = {}
    if work is not None:
        for question in read(work / 'checklist.json')['questions']:
            number = str(question['number'])
            evidence_file = work / 'evidence' / f'{number}.json'
            page_by_id = {u.get('unit_id'): u.get('page') for u in read(evidence_file).get('units', [])}
            for unit in question['scoring_units']:
                locations[unit['unit_id']] = {'question': number, 'page': page_by_id.get(unit['unit_id']),
                                               'evidence_file': str(evidence_file)}
    totals = {}
    for unit in score.get('units', []):
        if unit.get('status') == 'unsupported':
            continue
        number = str(unit.get('question_number', '?'))
        item = totals.setdefault(number, {'awarded': 0, 'max_marks': 0})
        item['awarded'] += unit.get('awarded') or 0
        item['max_marks'] += unit.get('max_marks') or 0
    return {'total': score.get('total'), 'max_total': score.get('max_total'),
            'grade': score.get('grade'), 'grade_range': score.get('grade_range'),
            'marked_max_total': sum(item['max_marks'] for item in totals.values()),
            'unsupported': score.get('unsupported') or [], 'questions': totals,
            'reliability': score.get('reliability'),
            'review_items': [{k: x.get(k) for k in ('label', 'page', 'reasons', 'notes', 'final_answer', 'scheme_conflict')} for x in score.get('review_items', [])],
            'recheck': [{**locations.get(x.get('unit_id'), {}), **{k: x.get(k) for k in ('unit_id', 'label', 'step_id', 'mark_code', 'reasons', 'check')}} for x in score.get('recheck', [])],
            'score_path': str(work / 'score.json') if work else 'score.json',
            'explanation_tasks': explanation_tasks(work, evidence, score) if work and evidence else []}


def compact_summary(summary: dict, work: Path) -> dict:
    path = str(work / 'check-summary.json')
    fields = ('unit_id', 'question', 'label', 'awarded', 'max_marks', 'needs',
              'judgement_sha256', 'report_file')
    return {**{key: value for key, value in summary.items() if key != 'explanation_tasks'},
            'summary_path': path, 'explanation_details_path': path,
            'explanation_tasks': [{key: task.get(key) for key in fields}
                                  for task in summary.get('explanation_tasks', [])]}
