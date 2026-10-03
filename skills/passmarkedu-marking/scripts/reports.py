"""Explanations after scoring: judgement freshness, explanation tasks, the checks before submit, and summaries.

From 1.10.1 the model writes each part's explanation with its judgement, in the evidence file;
after `check` only what the actual score still needs is asked for. `reports/<number>.json`
sidecars from earlier helpers are still applied.
"""
from __future__ import annotations

import copy
from pathlib import Path

import review_detail
from common import WorkflowError, digest, read
from evidence import _kept, unit_files

AUTO_COMMENT = {'zh': '本小问全部得分。', 'en': 'Full marks for this part.'}
# Printed with every batch: the explanation each unit takes, written with its judgement (judging.md).
EXPLAIN = ('In each unit, with its judgement: comment, headline, mistakes, solution when it loses marks (comment and '
           'solution only when every lost mark is low confidence); solution when blank; also review_detail when it '
           'earns some but not all marks, has a low step, a medium step and earns marks, or a visual or level step '
           '(its crop: the lines in dispute plus one line, a third of the page or less). Full marks: none. For evidenced mechanical mistakes, add kind (calculation, rounding, transcription, '
           'notation, mixed or other) and affected_steps containing this unit’s actual checklist IDs; no counts. '
           'Tag only in this judging pass; preserve the score and explanation rules.')


REPORT_FIELDS = ('comment', 'headline', 'mistakes', 'solution')
EXPLANATION = REPORT_FIELDS + ('review_detail',)
# Neither report prose, the review note's detail, where the drawing sits, nor the helper's own
# blank-page check is a judgement.
NOT_JUDGEMENT = EXPLANATION + ('figure', 'blank_check')
LOSS_PROSE = ('comment', 'headline', 'mistakes')  # what the marks lost were: rewritten when the score changes
LOSS_ONLY = ('headline', 'mistakes', 'solution')  # written only for a part that lost marks or is blank


def judgement_hash(unit: dict) -> str:
    return digest({key: value for key, value in unit.items() if key not in NOT_JUDGEMENT})


def judging_payload(evidence: dict) -> dict:
    return {**evidence, 'units': [{k: v for k, v in u.items() if k not in NOT_JUDGEMENT} for u in evidence['units']]}


def scoring_payload(evidence: dict) -> dict:
    """What `/score` gets: the judgement with `figure` and `blank_check`; explanations go with the result."""
    return {**evidence, 'units': [{k: v for k, v in u.items() if k not in EXPLANATION} for u in evidence['units']]}


def _outcome(scored: dict) -> str:
    return digest([scored.get('awarded'), [[s.get('step_id'), s.get('awarded')] for s in scored.get('steps') or []]])


def _prose(unit: dict) -> str:
    return digest([unit.get(key) for key in LOSS_PROSE])


def unit_hashes(evidence: dict, previous: dict, now_ns: int, scores: dict | None = None) -> dict:
    """Per unit: its judgement hash and since when (ns) it has had it, carried over from the last check.

    With the scores, also its score (`outcome`) and, from the check that changed that score, the loss
    explanation the unit had then (`prose_before`): written for the earlier score until it is rewritten."""
    out = {}
    for unit in evidence['units']:
        sha = judgement_hash(unit)
        before = previous.get(unit['unit_id']) or {}
        since = before.get('since_ns') if before.get('sha256') == sha and type(before.get('since_ns')) is int else now_ns
        record = {'sha256': sha, 'since_ns': since}
        scored = (scores or {}).get(unit['unit_id'])
        if scored is not None:
            outcome = _outcome(scored)
            changed = before.get('outcome') not in (None, outcome)
            record.update(outcome=outcome, prose_before=_prose(unit) if changed else
                          (before.get('prose_before') if before.get('outcome') == outcome else None))
        out[unit['unit_id']] = record
    return out


def _stale(unit: dict, record: object) -> bool:
    pinned = record.get('prose_before') if isinstance(record, dict) else None
    return pinned is not None and _prose(unit) == pinned and any(_kept(unit.get(key)) for key in LOSS_PROSE)


def scored_units(work: Path, score: dict) -> dict:
    result = {u['unit_id']: u for u in score.get('units', []) if u.get('unit_id')}
    if result:
        return result
    # Older score endpoints returned ordered units without their IDs.
    specs = [u for q in read(work / 'checklist.json')['questions'] for u in q['scoring_units']]
    if len(specs) == len(score.get('units', [])):
        return {spec['unit_id']: item for spec, item in zip(specs, score['units']) if spec.get('supported')}
    return result


def _supported(checklist: dict):
    for question in checklist['questions']:
        for spec in question['scoring_units']:
            if spec.get('supported'):
                yield str(question['number']), spec


def _entry_problem(number: str, entry: object, allowed: set, seen: set, by_id: dict, checked: dict, mtime_ns: int) -> str | None:
    if not isinstance(entry, dict) or entry.get('unit_id') not in allowed or entry['unit_id'] in seen:
        return f'Question {number}: unknown or duplicate report unit_id'
    uid = entry['unit_id']
    seen.add(uid)
    current = judgement_hash(by_id[uid])
    if entry.get('judgement_sha256') is None:
        # No hash to copy: the report belongs to the judgement it was written after.
        record = checked.get(uid) if isinstance(checked.get(uid), dict) else {}
        if record.get('sha256') != current or not (type(record.get('since_ns')) is int and mtime_ns >= record['since_ns']):
            return (f'Question {number}/{uid}: report stale, written before the latest judgement change; '
                    'rerun check and update this explanation')
    elif entry['judgement_sha256'] != current:
        return f'Question {number}/{uid}: report judgement_sha256 stale; rerun check and update this explanation'
    for field in REPORT_FIELDS:
        if field in entry and not isinstance(entry[field], list if field in ('mistakes', 'solution') else str):
            return f'Question {number}/{uid}: report {field} must be ' + ('a list' if field in ('mistakes', 'solution') else 'text')
    return None


def _apply_reports(work: Path, checklist: dict, by_id: dict, checked: dict, *, strict: bool) -> set[str]:
    """Apply `reports/<number>.json` sidecars (the explanation file of helpers before 1.10.1) to the units.

    Returns the units whose loss explanation a current sidecar supplies. A bad or stale entry is refused
    when strict, else skipped."""
    supplied = set()
    for question in checklist['questions']:
        number = str(question['number'])
        path = work / 'reports' / f'{number}.json'
        if not path.exists():
            continue
        try:
            units = read(path).get('units')
            if not isinstance(units, list):
                raise WorkflowError(f'Question {number}: report units must be a list')
        except (ValueError, WorkflowError):
            if strict:
                raise
            continue
        allowed = {u['unit_id'] for u in question['scoring_units'] if u.get('supported')}
        seen = set()
        for entry in units:
            problem = _entry_problem(number, entry, allowed, seen, by_id, checked, path.stat().st_mtime_ns)
            if problem:
                if strict:
                    raise WorkflowError(problem)
                continue
            by_id[entry['unit_id']].update({field: entry[field] for field in EXPLANATION if field in entry})
            if any(field in entry for field in LOSS_PROSE):
                supplied.add(entry['unit_id'])
    return supplied


def _settle(unit: dict, scored: dict, maximum: int, lang: object) -> list[str]:
    """A full-mark part gets the fixed comment in place of none, or of an explanation written for a loss
    the service did not take; `review_detail` stays on the parts the review note lists only."""
    if not review_detail.listed(scored):
        unit.pop('review_detail', None)
    if not unit['attempted'] or scored['awarded'] < maximum:
        return []
    fixed = AUTO_COMMENT.get(lang, AUTO_COMMENT['en'])
    if any(_kept(unit.get(key)) for key in LOSS_ONLY):
        for key in LOSS_ONLY:
            unit.pop(key, None)
        unit['comment'] = fixed
        return ['scored full marks, so its explanation of a loss was replaced by the fixed full-mark comment']
    if not (isinstance(unit.get('comment'), str) and unit['comment'].strip()):
        unit['comment'] = fixed
    return []


def _complete(field: str, value: object) -> bool:
    if field in ('comment', 'headline'):
        return isinstance(value, str) and bool(value.strip())
    if field == 'solution':
        return isinstance(value, list) and bool(value) and all(isinstance(x, str) and x.strip() for x in value)
    return isinstance(value, list) and bool(value) and all(
        isinstance(x, dict) and all(isinstance(x.get(k), str) and x[k].strip() for k in ('wrote', 'why', 'should')) for x in value)


def _explained(unit: dict, scored: dict, maximum: int, page_count: int, stale: bool) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """(the explanation fields the part needs, (field, problem) for each missing, unusable or written for an
    earlier score, the repairs made to its `review_detail`)."""
    needs = report_needs(unit, scored['awarded'], maximum, scored.get('steps', []), review_detail.listed(scored))
    problems, repairs = [], []
    for field in needs:
        value = unit.get(field)
        if field == 'review_detail':
            try:
                unit['review_detail'], dropped = review_detail.validate(value, scored, page_count)
                repairs.extend(dropped)
            except WorkflowError as exc:
                problems.append((field, str(exc)))
        elif not _complete(field, value):
            problems.append((field, f'{field} required after scoring'))
        elif stale and field in LOSS_PROSE:
            problems.append((field, f'{field} was written for an earlier score; rewrite it for {scored["awarded"]}/{maximum}'))
    return needs, problems, repairs


def with_reports(work: Path, evidence: dict, *, require_complete: bool, page_count: int = 0,
                 repairs: list[str] | None = None) -> dict:
    """The evidence with its explanations settled against the saved score (see `_settle`), `review_detail`
    repaired as the note needs, and legacy report sidecars applied. With require_complete, refuse the
    first part whose explanation is missing, unusable or written for an earlier score."""
    checklist = read(work / 'checklist.json')
    checked = (read(work / 'check.json').get('units') or {}) if (work / 'check.json').is_file() else {}
    scores = scored_units(work, read(work / 'score.json'))
    by_id = {u['unit_id']: u for u in evidence['units']}
    stale = {uid for uid, unit in by_id.items() if _stale(unit, checked.get(uid))}
    stale -= _apply_reports(work, checklist, by_id, checked, strict=True)
    for number, spec in _supported(checklist):
        uid, scored = spec['unit_id'], scores.get(spec['unit_id'], {})
        if scored.get('awarded') is None:
            raise WorkflowError(f'Question {number}/{uid}: score lacks unit marks; rerun check')
        maximum = scored.get('max_marks', spec.get('marks'))
        notes = _settle(by_id[uid], scored, maximum, evidence.get('lang'))
        _, problems, dropped = _explained(by_id[uid], scored, maximum, page_count, uid in stale)
        if repairs is not None:
            repairs.extend(f'Question {number}/{uid}: {note}' for note in notes + dropped)
        if require_complete and problems:
            raise WorkflowError(f'Question {number}/{uid}: report {problems[0][1]}')
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


def explanation_tasks(work: Path, evidence: dict, score: dict, records: dict | None = None) -> tuple[list[dict], int, int, list[str]]:
    """What is left to explain after scoring: the parts whose explanation (written with the judgement) is
    missing, unusable or written for an earlier score, with the fields to fill; the number of full-mark parts
    that need none; the number whose explanation already fits the score; and what submit will repair."""
    checklist = read(work / 'checklist.json')
    scored = scored_units(work, score)
    if records is None:
        records = (read(work / 'check.json').get('units') or {}) if (work / 'check.json').is_file() else {}
    units = copy.deepcopy(evidence['units'])
    by_id = {u['unit_id']: u for u in units}
    stale = {uid for uid, unit in by_id.items() if _stale(unit, records.get(uid))}
    stale -= _apply_reports(work, checklist, by_id, records, strict=False)
    page_count = len(read(work / 'manifest.json').get('pages') or []) if (work / 'manifest.json').is_file() else 0
    files = unit_files(work)
    output, automatic, done, notes = [], 0, 0, []
    for number, spec in _supported(checklist):
        uid = spec['unit_id']
        unit, scored_unit = by_id[uid], scored.get(uid, {})
        if scored_unit.get('awarded') is None:
            continue
        maximum = scored_unit.get('max_marks', spec.get('marks'))
        automatic += unit['attempted'] and scored_unit['awarded'] >= maximum
        settled = _settle(unit, scored_unit, maximum, evidence.get('lang'))
        needs, problems, dropped = _explained(unit, scored_unit, maximum, page_count, uid in stale)
        notes.extend(f'Question {number}/{uid}: {note}' for note in settled + dropped)
        if not problems:
            done += bool(needs)
            continue
        fields = list(dict.fromkeys(field for field, _ in problems))
        # A listed part's steps carry their mark-scheme wording, for the review_detail quote.
        keys = ('step_id', 'mark_code', 'awarded', 'step_marks', 'status', 'confidence', 'evidence') + (
            ('description',) if 'review_detail' in fields else ())
        task = {'unit_id': uid, 'question': number, 'label': spec.get('label'),
                'awarded': scored_unit['awarded'], 'max_marks': maximum, 'attempted': unit['attempted'],
                'needs': fields, 'judgement_sha256': judgement_hash(unit),
                'evidence_file': str(files[uid][0]) if uid in files else None,
                'transcript': unit.get('transcript'), 'final_answer': unit.get('final_answer'),
                'scored_steps': [{k: step.get(k) for k in keys} for step in scored_unit.get('steps', [])]}
        fixes = [problem for field, problem in problems if unit.get(field) is not None]
        if fixes:
            task['fix'] = fixes
        if 'review_detail' in fields:
            task.update(page=unit.get('page'), review_reasons=(scored_unit.get('review') or {}).get('reasons') or [])
        output.append(task)
    return output, automatic, done, notes


def score_summary(score: dict, work: Path | None = None, evidence: dict | None = None, records: dict | None = None) -> dict:
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
    tasks, automatic, done, notes = explanation_tasks(work, evidence, score, records) if work and evidence else ([], 0, 0, [])
    return {'total': score.get('total'), 'max_total': score.get('max_total'),
            'grade': score.get('grade'), 'grade_range': score.get('grade_range'),
            'marked_max_total': sum(item['max_marks'] for item in totals.values()),
            'unsupported': score.get('unsupported') or [], 'questions': totals,
            'reliability': score.get('reliability'),
            'review_items': [{k: x.get(k) for k in ('label', 'page', 'reasons', 'notes', 'final_answer', 'scheme_conflict')} for x in score.get('review_items', [])],
            'recheck': [{**locations.get(x.get('unit_id'), {}), **{k: x.get(k) for k in ('unit_id', 'label', 'step_id', 'mark_code', 'reasons', 'check')}} for x in score.get('recheck', [])],
            'score_path': str(work / 'score.json') if work else 'score.json',
            'explanation_tasks': tasks, 'auto_comment_units': automatic, 'explained_units': done,
            **({'repairs': notes} if notes else {})}


def compact_summary(summary: dict, work: Path) -> dict:
    path = str(work / 'check-summary.json')
    fields = ('unit_id', 'question', 'label', 'awarded', 'max_marks', 'needs', 'fix',
              'judgement_sha256', 'evidence_file')
    return {**{key: value for key, value in summary.items() if key != 'explanation_tasks'},
            'summary_path': path, 'explanation_details_path': path,
            'explanation_tasks': [{key: task[key] for key in fields if key in task}
                                  for task in summary.get('explanation_tasks', [])]}
