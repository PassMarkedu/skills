"""Batch packets and judgement evidence validation."""
from __future__ import annotations

import math
from pathlib import Path

import blanks
from common import WorkflowError, read
from rendering import validate_box

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


def merged(work: Path, state: dict, repairs: list[str] | None = None) -> dict:
    """All judgement files as one payload; every supported unit exactly once, in checklist order.

    Type slips the helper can read without changing a judgement are repaired in the payload (never in
    the files) and listed in ``repairs``."""
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
        validate_unit(f'{name}: {uid}', unit, spec, page_count, repairs)
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


def _boolean(value: object) -> bool | None:
    """``true``/``false`` written as text or as 1/0."""
    if type(value) is int and value in (0, 1):
        return bool(value)
    text = value.strip().lower() if isinstance(value, str) else None
    return {'true': True, 'false': False, '1': True, '0': False}.get(text) if text else None


def validate_unit(uid: str, unit: dict, spec: dict, page_count: int, repairs: list[str] | None = None) -> None:
    repairs = repairs if repairs is not None else []
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
            present = _boolean(step.get('present'))
            if present is None:
                raise WorkflowError(f'{uid}/{sid}: present must be a JSON boolean')
            repairs.append(f'{uid}/{sid}: present {step["present"]!r} read as {str(present).lower()}')
            step['present'] = present
        if step.get('confidence') not in ('high', 'medium', 'low') or not isinstance(step.get('evidence'), str):
            raise WorkflowError(f'{uid}/{sid}: complete confidence and evidence')
        if step['confidence'] != 'high' and (step.get('reason') not in STEP_REASONS
                                             or not isinstance(step.get('note'), str) or not step['note'].strip()):
            raise WorkflowError(f'{uid}/{sid}: {step["confidence"]} confidence needs a reason ({", ".join(STEP_REASONS)}) '
                                'and a one-sentence note')
        kind_spec = scheme[sid]
        kind = kind_spec.get('type', 'point')
        if kind == 'numeric' and type(step.get('value')) in (int, float) and math.isfinite(step['value']):
            repairs.append(f'{uid}/{sid}: numeric value {step["value"]!r} sent as the text "{step["value"]!r}"')
            step['value'] = repr(step['value'])
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
