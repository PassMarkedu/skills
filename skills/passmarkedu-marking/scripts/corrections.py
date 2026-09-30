"""Marks the user asked for, recorded by `correct` and sent with the next result update."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from common import WorkflowError, read

FILE = 'corrections.json'
DECIDED = 'decided.json'  # every mark the user has set in this run, kept after it is applied


def _key(label: object) -> str:
    return re.sub(r'\s+', '', str(label or '')).lower()


def pending(work: Path) -> list[dict]:
    path = work / FILE
    items = read(path).get('corrections') if path.exists() else []
    if not isinstance(items, list):
        raise WorkflowError(f'{FILE} must hold a corrections list')
    return items


def add(work: Path, label: str, marks: int) -> dict:
    """Append one request after checking the part label and its maximum against the checklist."""
    units = [u for q in read(work / 'checklist.json')['questions'] for u in q.get('scoring_units', [])]
    found = [u for u in units if _key(u.get('label')) == _key(label)]
    if len(found) != 1:
        known = ', '.join(str(u.get('label')) for u in units if u.get('supported'))
        raise WorkflowError(f'Part label {label!r} is not in the checklist; labels: {known}')
    unit = found[0]
    if not unit.get('supported'):
        raise WorkflowError(f'{unit["label"]} is not marked by the service, so its mark cannot be corrected')
    maximum = int(unit.get('marks') or 0)
    if not 0 <= marks <= maximum:
        raise WorkflowError(f'{unit["label"]} is worth {maximum} marks; --marks must be 0 to {maximum}')
    items = pending(work) + [{'label': unit['label'], 'requested_marks': marks, 'source': 'user'}]
    path = work / FILE
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps({'corrections': items}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)
    return {'corrections_file': str(path), 'pending': items}


def decided(work: Path) -> list[dict]:
    """The marks the user has set in this run, latest per part, pending ones included."""
    path = work / DECIDED
    kept = read(path).get('decided') if path.exists() else []
    latest = {_key(item.get('label')): item for item in (kept if isinstance(kept, list) else []) + pending(work)
              if isinstance(item, dict)}
    return [{'label': item['label'], 'requested_marks': item.get('requested_marks')} for item in latest.values()]


def attach(work: Path, evidence: dict) -> dict:
    """The evidence for an update, carrying the recorded requests as top-level `corrections` and every
    mark set so far as `decided` (the service stops listing those parts for the teacher to decide).

    Services that predate corrections ignore the extra keys (checked against the
    production image 13827f4cc)."""
    items, known = pending(work), decided(work)
    out = {**evidence, 'corrections': items} if items else dict(evidence)
    return {**out, 'decided': known} if known else out


def clear(work: Path) -> None:
    """After a successful update: the service has them now; keep them as decided for later updates."""
    known = decided(work)
    if known:
        path = work / DECIDED
        temp = path.with_name(path.name + '.tmp')
        temp.write_text(json.dumps({'decided': known}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(temp, path)
    (work / FILE).unlink(missing_ok=True)
