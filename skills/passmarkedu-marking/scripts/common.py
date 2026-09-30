"""Small local workflow primitives."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

# Apps opened from the macOS Dock get a minimal PATH without Homebrew's folders, so
# pdftoppm/pdfinfo installed there go unseen. Appended, so the user's own tools still win.
for _folder in ('/opt/homebrew/bin', '/usr/local/bin'):
    _path = os.environ.get('PATH', '')
    if os.path.isdir(_folder) and _folder not in _path.split(os.pathsep):
        os.environ['PATH'] = _path + os.pathsep + _folder if _path else _folder


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
