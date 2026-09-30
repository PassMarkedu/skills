"""`review_detail` for the parts the review note lists: which parts, and the checks the service applies.

The service lists a part when its `review.tier` is `check` or `glance` and draws one row per
part from the part's `review_detail`. It never refuses a bad piece (it falls back on its own),
so these checks run before submit: what carries the decision (the two views, alt_marks, the
mark-scheme quote) is refused naming the exact field to fix; what only places things on the
note (crop, circles, underline, the MS page) is repaired or left out with a warning. The wording
normalisation mirrors the service's (render._plain, review_note._display/_squash/_in_order):
a quote matches with spacing and punctuation aside. `circles` is optional (the note no longer
draws them).
"""
from __future__ import annotations

import math
import re
import unicodedata

from common import WorkflowError

LISTED = ('check', 'glance')
MAX_VIEW = 120  # the note shows one sentence per column, clipped here
MAX_QUOTE = 300
MAX_CIRCLES = 6
TALL_CROP = 0.4  # of the page height: the note shows a crop near life size, so a tall one adds pages

_SYMBOLS = {
    r'\times': '×', r'\div': '÷', r'\leqslant': '≤', r'\geqslant': '≥', r'\leq': '≤', r'\geq': '≥',
    r'\le': '≤', r'\ge': '≥', r'\neq': '≠', r'\ne': '≠', r'\approx': '≈', r'\pm': '±', r'\cdot': '·',
    r'\Rightarrow': '⇒', r'\rightarrow': '→', r'\to': '→', r'\infty': '∞', r'\pi': 'π', r'\theta': 'θ',
    r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ', r'\lambda': 'λ', r'\mu': 'μ',
    r'\sigma': 'σ', r'\rho': 'ρ', r'\Sigma': 'Σ', r'\sum': 'Σ', r'\ldots': '…', r'\dots': '…',
    r'\circ': '°', r'\degree': '°', r'\%': '%', r'\int': '∫', r'\sqrt': '√',
}
_SUPERSCRIPT = str.maketrans('0123456789-+', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺')
_SUBSCRIPT = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')
_ELISION = re.compile(r'…|\.\.\.')
# Sentence punctuation never decides whether a quote matches: "correct." is "correct;". As the service
# compares: full-width forms become these under NFKC; one between two digits is part of a number (4.8).
_MARKS = r'[.,;:!?。、"“”‘’「」『』]'
_PUNCTUATION = re.compile(rf'(?<!\d){_MARKS}|{_MARKS}(?!\d)')


def listed(scored_unit: dict) -> bool:
    return (scored_unit.get('review') or {}).get('tier') in LISTED


def circled(n: int) -> str:
    """The row number the note prints: ① … ㊿."""
    if 1 <= n <= 20:
        return chr(0x2460 + n - 1)
    if 21 <= n <= 35:
        return chr(0x3251 + n - 21)
    if 36 <= n <= 50:
        return chr(0x32B1 + n - 36)
    return f'({n})'


def _group(term: str) -> str:
    term = term.strip()
    return term if re.fullmatch(r'[-\w.²³⁰¹⁴⁵⁶⁷⁸⁹√()]+', term) else f'({term})'


def _plain(text: object) -> str:
    out = str(text or '')
    for _ in range(4):
        out = re.sub(r'\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}', lambda m: f'{_group(m.group(1))}/{_group(m.group(2))}', out)
        out = re.sub(r'\\sqrt\{([^{}]*)\}', r'√(\1)', out)
        out = re.sub(r'\\(?:text|mathrm|mathbf|operatorname|textbf)\{([^{}]*)\}', r'\1', out)
        out = re.sub(r'\\(?:bar|overline)\{([^{}]*)\}', '\\1\u0304', out)
        out = re.sub(r'\^\{([0-9+\-]{1,4})\}', lambda m: m.group(1).translate(_SUPERSCRIPT), out)
        out = re.sub(r'\^\{([^{}]*)\}', r'^(\1)', out)
        out = re.sub(r'_\{([^{}]*)\}', r'_\1', out)
    out = re.sub(r'\^([0-9])', lambda m: m.group(1).translate(_SUPERSCRIPT), out)
    for command, symbol in sorted(_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(re.escape(command) + r'(?![A-Za-z])', symbol, out)
    out = re.sub(r'\\(?:left|right|displaystyle|quad|qquad)(?![A-Za-z])', ' ', out)
    out = re.sub(r'\\[,;:! ]', ' ', out)
    out = out.replace('$', '').replace('{', '').replace('}', '')
    return re.sub(r'[ \t]{2,}', ' ', out).strip()


def display(text: object) -> str:
    out = _plain(str(text or '').replace(r'\{', '(').replace(r'\}', ')'))
    return re.sub(r'(?<=[A-Za-z])_(\d+)', lambda m: m.group(1).translate(_SUBSCRIPT), out)


def squash(text: object) -> str:
    """Wording compared with spacing, Unicode forms, dashes and LaTeX markup aside."""
    text = unicodedata.normalize('NFKC', display(text))
    for dash in '−–—':
        text = text.replace(dash, '-')
    return re.sub(r'\s+', '', text)


def bare(text: object) -> str:
    """Wording as the quote comparison sees it on both sides: the service's _squash(text, punctuation=False)."""
    text = unicodedata.normalize('NFKC', display(text))
    for dash in '−–—':
        text = text.replace(dash, '-')
    return re.sub(r'\s+', '', _PUNCTUATION.sub('', text))


def _mismatch(pieces: list[str], source: str) -> tuple[str, str] | None:
    """(the first piece not found after the previous one, its longest leading words that are), or None."""
    source, at = bare(source), 0
    for piece in pieces:
        found = source.find(bare(piece), at)
        if found < 0:
            words = piece.split()
            fits = next((' '.join(words[:n]) for n in range(len(words) - 1, 0, -1)
                         if source.find(bare(' '.join(words[:n])), at) >= 0), '')
            return piece, fits
        at = found + len(bare(piece))
    return None


def _box(value: object, field: str, page_count: int) -> tuple[int, list[float]]:
    """(page, box) with the box clamped to the page as the service clamps it."""
    if not isinstance(value, dict):
        raise WorkflowError(f'{field} must be {{"page": N, "box": [left, top, right, bottom]}}')
    page, box = value.get('page'), value.get('box')
    if type(page) is not int or page < 1 or (page_count and page > page_count):
        raise WorkflowError(f'{field}.page must be an original 1-based script page' + (f' (1..{page_count})' if page_count else ''))
    if not isinstance(box, list) or len(box) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in box):
        raise WorkflowError(f'{field}.box must be four fractions [left, top, right, bottom]')
    box = [min(1.0, max(0.0, float(x))) for x in box]
    if box[2] - box[0] < 0.01 or box[3] - box[1] < 0.01:
        raise WorkflowError(f'{field}.box must lie inside 0..1 with left < right and top < bottom')
    return page, box


def _view(detail: dict, key: str) -> None:
    value = detail.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f'review_detail.{key} must be one sentence in the user\'s language')
    if len(re.sub(r'\s+', ' ', value).strip()) > MAX_VIEW:
        raise WorkflowError(f'review_detail.{key} is longer than {MAX_VIEW} characters; shorten it to one sentence')


def _quote(quote: object, scored_unit: dict) -> None:
    """Refuse a quote that is not its step's own wording (punctuation and spacing aside)."""
    if not isinstance(quote, dict):
        raise WorkflowError('review_detail.ms_quote must be {"step_id", "text", "underline"}')
    steps = {s.get('step_id'): s for s in scored_unit.get('steps') or []}
    step = steps.get(quote.get('step_id'))
    if step is None or not step.get('description'):
        raise WorkflowError(f'review_detail.ms_quote.step_id must be one of this part\'s steps: {", ".join(map(str, steps))}')
    text = quote.get('text')
    if not isinstance(text, str) or not text.strip() or len(display(text)) > MAX_QUOTE:
        raise WorkflowError(f'review_detail.ms_quote.text must be a verbatim excerpt of step {step["step_id"]}, at most {MAX_QUOTE} characters')
    pieces = [piece.strip() for piece in _ELISION.split(display(text)) if squash(piece)]
    if sum(len(squash(piece)) for piece in pieces) < 4:
        raise WorkflowError('review_detail.ms_quote.text is too short to show the rule')
    missing = _mismatch(pieces, step['description'])
    if missing is not None:
        piece, fits = missing
        where = f'; it departs from the wording after {fits!r}' if fits else ''
        raise WorkflowError(f'review_detail.ms_quote.text: {piece!r} is not in step {step["step_id"]}\'s description{where} '
                            '(copy its wording; "…" may stand for words left out, pieces in order)')


def _placement(detail: dict, clean: dict, page_count: int) -> list[str]:
    """Repair or drop the pieces that only place things on the note (crop, circles, underline, MS page)."""
    dropped = []
    crop = None
    try:
        crop = _box(detail.get('crop'), 'review_detail.crop', page_count)
        clean['crop'] = {'page': crop[0], 'box': crop[1]}
        if crop[1][3] - crop[1][1] > TALL_CROP:
            dropped.append(f'review_detail.crop is {crop[1][3] - crop[1][1]:.2f} of the page tall: kept, but frame only the lines '
                           'in dispute plus one line of context (a third of the page or less) to keep the review note short')
    except WorkflowError as exc:
        clean.pop('crop', None)
        dropped.append(f'{exc}: left out, the note shows the answer\'s area instead')
    circles = detail.get('circles')  # optional: the note no longer draws them
    clean.pop('circles', None)
    if circles is not None and (not isinstance(circles, list) or not 1 <= len(circles) <= MAX_CIRCLES):
        dropped.append(f'review_detail.circles must list 1..{MAX_CIRCLES} {{"page", "box"}}: left out')
    elif circles:
        kept = []
        for index, circle in enumerate(circles):
            field = f'review_detail.circles[{index}]'
            try:
                page, box = _box(circle, field, page_count)
                inside = crop is not None and page == crop[0] and box[0] < crop[1][2] and box[2] > crop[1][0] \
                    and box[1] < crop[1][3] and box[3] > crop[1][1]
                if not inside:
                    raise WorkflowError(f'{field} is outside review_detail.crop')
                kept.append({'page': page, 'box': box})
            except WorkflowError as exc:
                dropped.append(f'{exc}: left out')
        if kept:
            clean['circles'] = kept
    quote, text = detail['ms_quote'], detail['ms_quote']['text']
    underline = quote.get('underline')
    shown = bare(text)  # spacing and punctuation aside, as the quote
    kept = []
    for index, phrase in enumerate(underline if isinstance(underline, list) else []):
        wanted = bare(phrase) if isinstance(phrase, str) else ''
        if not wanted or wanted not in shown:
            dropped.append(f'review_detail.ms_quote.underline[{index}] must be a phrase copied from ms_quote.text: left out')
        elif len(kept) < 6:
            kept.append(phrase)
    if not isinstance(underline, list) or not underline or len(underline) > 6:
        dropped.append('review_detail.ms_quote.underline must list 1..6 key phrases from the quote'
                       + (': kept the first 6' if isinstance(underline, list) and len(underline) > 6 else ': nothing is underlined'))
    clean['ms_quote']['underline'] = kept
    page = quote.get('page')
    if page is not None and (type(page) is not int or page < 1):
        clean['ms_quote'].pop('page', None)
        dropped.append('review_detail.ms_quote.page must be the mark scheme page number: left out')
    return dropped


def validate(detail: object, scored_unit: dict, page_count: int = 0) -> tuple[dict, list[str]]:
    """The detail as the service will draw it, and what was repaired or left out of it.

    Raise WorkflowError naming the `review_detail.<field>` that carries the decision (the two views,
    alt_marks, the mark-scheme quote) when the service could not use it. Pieces that only place things
    on the note (crop, circles, underline, the MS page) are repaired or left out with a warning
    instead: the service draws the row without them.
    """
    if not isinstance(detail, dict):
        raise WorkflowError('review_detail is required for this part and must be an object')
    _view(detail, 'ai_view')
    _view(detail, 'alt_view')
    alt, awarded, most = detail.get('alt_marks'), scored_unit.get('awarded'), scored_unit.get('max_marks') or 0
    if type(alt) is not int or not 0 <= alt <= most:
        raise WorkflowError(f'review_detail.alt_marks must be an integer 0..{most}')
    if alt == awarded:
        raise WorkflowError(f'review_detail.alt_marks equals the awarded {awarded}; give the other plausible mark')
    _quote(detail.get('ms_quote'), scored_unit)
    clean = {**detail, 'ms_quote': dict(detail['ms_quote'])}
    return clean, _placement(detail, clean, page_count)
