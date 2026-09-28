"""Small local workflow primitives."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class WorkflowError(Exception):
    pass


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise WorkflowError(f'{path.name} must contain a JSON object')
    return value


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

