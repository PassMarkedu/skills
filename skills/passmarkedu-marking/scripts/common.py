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


def ensure_dir(path: Path) -> Path:
    """Create a directory, level by level, and accept one that already exists.

    Some agent sandboxes broker ``Path.mkdir`` and raise EEXIST even with
    ``exist_ok=True``, so existence is checked first and EEXIST is tolerated.
    """
    if path.is_dir():
        return path
    if path.parent != path and not path.parent.is_dir():
        ensure_dir(path.parent)
    try:
        path.mkdir()
    except OSError:
        if not path.is_dir():
            raise
    return path
