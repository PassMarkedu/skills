"""Where a run lives, what the user sees of it, and what is kept.

Owner 2026-09-29: a visible `passmarkedu-runs/` folder of hundreds of files next to the answer PDF
confused users. A run's working files now sit in a hidden `.passmarkedu/<run>` folder in the
answer PDF's own folder (host sandboxes allow only the workspace, and corrections must work for
the 7 days a result lives); the PDFs are copied next to the answer PDF under readable names.
After a submit the page renders are removed (script.pdf renders them again on demand), and
`start` removes helper runs created more than 7 days ago.
"""
from __future__ import annotations

import contextlib
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from common import WorkflowError, ensure_dir, read
from rendering import page_count, page_sizes, render_pages, render_tiles

HIDDEN = '.passmarkedu'
KEEP_DAYS = 7  # a result can be corrected for 7 days
MANIFEST_KEYS = {'origin', 'identity', 'script_sha256', 'created'}  # what marks a folder as a helper run
# The visible copies next to the answer PDF: <stem>-<name>.pdf
NAMES = {'zh': {'annotated_script': '批改答卷', 'marking_report': '阅卷结果', 'review_note': '复核说明'},
         'en': {'annotated_script': 'marked', 'marking_report': 'report', 'review_note': 'review-note'}}
# Rebuilt from script.pdf when needed again: whole pages, tiles (and the blank-check renders), crops, the cover,
# the identify views and uploads.
REGENERABLE = ('pages', 'tiles', 'crops', 'cover-page.png', 'identify')


def runs_root(script: Path) -> Path:
    """The hidden folder of runs for an answer PDF: beside it, except in a code repository or the skill."""
    folder = script.parent
    skill = config.SKILL_DIR.resolve()
    if folder == skill or skill in folder.parents or any((p / '.git').exists() for p in (folder, *folder.parents)):
        return Path.home() / HIDDEN / 'runs'
    return folder / HIDDEN


def created_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def expire(root: Path, now: datetime | None = None) -> int:
    """Remove the helper runs directly under ``root`` created more than KEEP_DAYS ago; nothing else."""
    if not root.is_dir():
        return 0
    now = now or datetime.now(timezone.utc)
    removed = 0
    for run in root.iterdir():
        if run.is_symlink() or not run.is_dir():
            continue
        try:
            manifest = read(run / 'manifest.json')
            created = datetime.fromisoformat(manifest['created'])
        except (OSError, ValueError, KeyError, TypeError, WorkflowError):
            continue
        if not MANIFEST_KEYS <= set(manifest) or created.tzinfo is None or now - created <= timedelta(days=KEEP_DAYS):
            continue
        shutil.rmtree(run, ignore_errors=True)
        removed += not run.exists()
    return removed


def deliver(state: dict, paths: dict[str, Path]) -> dict[str, str]:
    """Copy each PDF next to the answer PDF as ``<stem>-<name>.pdf`` (a later submit overwrites it).

    Returns each PDF's visible path, or its working path when there is no answer PDF on record
    (runs prepared by an earlier helper) or its folder cannot be written."""
    shown = {label: str(path) for label, path in paths.items()}
    original = state.get('script_path')
    if not isinstance(original, str) or not original:
        return shown
    answer = Path(original)
    names = NAMES.get(state.get('lang'), NAMES['en'])
    for label in set(names) - set(paths):  # e.g. no review note this time: the old copy would mislead
        with contextlib.suppress(OSError):
            answer.with_name(f'{answer.stem}-{names[label]}.pdf').unlink(missing_ok=True)
    for label, path in paths.items():
        target = answer.with_name(f'{answer.stem}-{names[label]}.pdf')
        temp = target.with_name(target.name + '.tmp')
        try:
            shutil.copyfile(path, temp)
            os.replace(temp, target)
            shown[label] = str(target)
        except OSError:
            with contextlib.suppress(OSError):
                temp.unlink(missing_ok=True)
    return shown


def tidy(work: Path) -> None:
    """After a submit: drop what script.pdf renders again on demand (`restore_views`, blanks, crop)."""
    for name in REGENERABLE:
        path = work / name
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def restore_views(work: Path, state: dict) -> bool:
    """Render again the whole pages and tiles a submit removed; True when ``state`` changed."""
    pages, tiles = state.get('pages') or [], state.get('tiles') or []
    if all(Path(p).is_file() for p in pages) and all(Path(t).is_file() for pair in tiles for t in pair):
        return False
    script = work / 'script.pdf'
    if pages:
        rendered, _ = render_pages(script, work, page_count(script))
        state['pages'] = rendered or pages
    if tiles:
        sizes = page_sizes(script)
        made = render_tiles(script, work, sizes, state.get('trim_box')) if sizes else None
        if made:
            state['tiles'] = made[0]  # the same sizes and trim box give the same tiles at the same dpi
    return True


def run_directory(script: Path, chosen: str | None, managed: tuple[str, ...]) -> Path:
    """The run folder: ``chosen`` (which must not hold another run's helper output), else a new one."""
    if chosen:
        run = Path(chosen).expanduser().resolve()
        if run.exists() and not (run / 'manifest.json').exists():
            collisions = [name for name in managed if (run / name).exists() or (run / name).is_symlink()]
            if collisions:
                raise WorkflowError(f'Run directory has helper output without a manifest: {", ".join(collisions)}')
        return ensure_dir(run)
    root = ensure_dir(runs_root(script))
    name = (re.sub(r'[^\w.-]+', '-', script.stem).strip('-.') or 'script') + datetime.now().strftime('-%Y%m%d-%H%M')
    for number in range(1, 1000):
        run = root / (name if number == 1 else f'{name}-{number}')
        try:
            run.mkdir()
            return run
        except FileExistsError:
            continue
    raise WorkflowError('Could not create a new run directory')
