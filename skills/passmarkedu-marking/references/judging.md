# Judge a batch from its images and official packets

Read this once before the first batch, plus the common and subject rules below. Read the work and judge it in the same processing step. Use the real IDs in the batch packet. Write each batch's evidence file in one go, each unit's explanation with its judgement ([Explain with the judgement](#explain-with-the-judgement)).

Use the supplied official allowances and mark-code rules consistently. Distinguish “cannot read the work” from “the work does not meet this point”; unreadable work carries low confidence. Preserve the actual answer and uncertainty rather than adjusting evidence to a desired total or another model’s score.

## Read the actual work first

Page numbers: page 1 = first page of the uploaded PDF, counting every page including the cover and blank pages. For every scoring unit of the question (`scoring_units[].label`, e.g. `1(a)`, `2(c.ii)`), write down:

- `page`: the page where the answer to that part **starts** (if the working continues or a drawing sits on a later page, still give the starting page and mention the other page in your transcription);
- `y`: how far down that page the answer starts, as a fraction 0–1 (0 = top edge, 0.5 = middle);
- a faithful transcription of the mark-bearing working and effective final answer, including relevant errors and corrections (label deleted content as deleted). Preserve the lines required to assess every mark; unrelated scratch need not be deciphered or transcribed. **Copy mistakes as they are — never correct the working while transcribing.** If a line looks mathematically wrong, it probably is: write `8y·y² dy = x·e dx` if that is what is on the page, not the correct `8y e^(y²) dy = x dx`. Every mark is judged from this transcript;
- whether the part was attempted at all.

For drawings (graphs, sketches, box plots, histograms, diagrams), describe what is drawn precisely: axes and scales, plotted points/end-points/intercepts, shape, labels, and read values off the grid. A value you cannot read off the tile is judged with low confidence; zoom on it only if a mark turns on it. For a unit with a `visual: true` step, set `figure` to the drawing's page and box (`[left, top, right, bottom]` of the upright page, as for `crop`, any size); the review note shows that region next to your judgement.

Ignore any ticks, crosses or marks that are already on the scan — mark the candidate's work afresh. For unclear mark-bearing content, judge the step with `confidence: "low"`, reason `legibility` and a note naming the doubt, and keep marking: it goes on the review list for the person running the marking. Zoom only when a mark turns on a symbol you genuinely cannot read on the tile — a paper has 4 zoom regions in all, cropped in one call after the last batch and viewed together. If a correctly located crop still cannot resolve a symbol, retain low confidence, quote the readable part and withhold that point — unless the scheme lets a correct final answer imply it (see `marking-rules.md`, Implied marks). Read and judge in one pass; do not chase unrelated scratch.

Read a coefficient's sign separately from its exponent and the sign before its bracket. Preserve a written result even when it contradicts the preceding arithmetic; do not silently repair its digits from that calculation or from the MS.

## When to consult the official MS image

Use the structured MS for routine judging. Open the relevant official MS image when:

- a mark depends on a graph, diagram, shading or another visual reference (`visual: true`), or the text refers to a figure/table whose required content is missing;
- a condition is missing or ambiguous, or `check`, `description`, mark codes, dependencies or alternative routes contradict each other;
- an applicable special case cannot be represented by the supplied rules, a supplied material note flags an unresolved issue, or the user disputes the marking condition.

Read only the affected question's official conditions and reuse an image already seen. The original MS is authoritative when it conflicts with the structured packet. Preserve real point IDs and report the discrepancy in `scheme_conflict`; do not silently change service rules or invent points. If the source is unavailable or the condition remains unresolved, retain low confidence and explain the unresolved condition in chat. Structured data is not a claim that every official condition has been verified.

Unclear handwriting alone calls for the answer-page crop, not the MS image; the MS cannot establish what the candidate wrote.

## Then judge each mark-scheme step

Before your first paper, read `references/marking-rules.md` (all subjects) and the one subject file matching the checklist's `subject`:

| `subject` | read |
|---|---|
| maths, further-maths | `references/rules-maths.md` |
| physics, chemistry, biology | `references/rules-sciences.md` |
| economics, business | `references/rules-economics-business.md` |
| accounting | `references/rules-accounting.md` |
| computer-science | `references/rules-computer-science.md` |

If the paper has `level` steps (or `LOR` points), also read the one file matching the board and subject: `references/levels/<board>-<subject>.md` (e.g. `edexcel-accounting.md`, `caie-economics.md`; business: `<board>-business.md`). Read it once, before judging the first such step.

For each scoring unit, go through its `steps` in order. Each step has a `type`; answer only what that type asks, using ONLY your transcription:

| `type` | what you send | what you must NOT do |
|---|---|---|
| `point` (default) | `present`: answer the step's `check` question if it has one (otherwise the `description`) — yes → `true` | do not guess; every condition in the question must hold |
| `numeric` | `value`: the candidate's final answer copied exactly as written (e.g. `"-0.945"`, `"3/8"`), and `present: true` if they wrote one | do not judge whether it is right — PassMarkedu compares it |
| `pick_n` | `matched`: the indices (0-based) of the `pick.options` the candidate's answer states; ignore anything on `pick.reject`; `present: true` if any matched | do not count marks yourself |
| `level` | `level`: the level whose descriptor fits best (0 if none), `awarded`: marks within that level's band, and the reason in `note` | do not skip the reason |

For every step also send:
- `confidence`:
  - `high`: every symbol the mark needs is legible, the condition is clearly met or clearly not met, and no competing attempt or deletion is involved;
  - `medium`: legible, but a judgement call: the condition's wording, whether a form is acceptable, or which attempt counts;
  - `low`: unreadable, or the condition cannot be settled.
- `reason` (medium and low only): `legibility`, `condition`, `deletion`, `alternative_method`, `follow_through`, `drawing`, `levels` or `scheme_gap`.
- `evidence`: the specific line(s) of your transcription that earn or fail **this** step, copied character for character, ≤150 characters. Never the whole transcript — the same long quote pasted into several steps is flagged as not judged one by one. Never the mark scheme's words, and never the correct answer when the candidate wrote something else.
- `note`: for medium and low steps, one sentence on what is uncertain; also for special cases ("SC"), `level` steps (the reason) and user corrections. In the user's language, about the candidate's work (no point IDs): it appears in the review note.
- `awarded`: only for `point` steps whose `step_marks` is more than 1 (M2, K2 …) and for `level` steps.

Rules:
- Judge each step on what is written; do not skip later steps because an earlier one failed — the server applies dependencies (`depends_on`) itself, including dependencies on earlier parts. If a dependent step's content is present but its prerequisite was not earned, still send `present: true`; the server decides.
- Where a unit has several `alternative_group` routes ("Way 1", "Way 2"), judge the steps of the route(s) the candidate actually used; you may leave out the steps of routes they clearly did not use. The server picks the best route.
- Special cases ("SC B1 if …", "SC M1M0A0"): when the candidate's work matches a special case, set `present`/`awarded` on the listed steps so that the total equals what the special case gives, and say "SC" in the `note`.
- Steps with `"visual": true` are judged on a drawing. Judge them from your reading of the original diagram; they are always shown to the user for review.
- Blank or unattempted parts: send `"attempted": false` and no steps.
## Explain with the judgement

Write each unit's explanation in the same evidence unit, when you judge it, in the user's language, while the work is in front of you; there is no second pass over the questions. What to write follows from your own judgement:

- the part loses marks: `comment`, `headline`, `mistakes`, `solution` — or only `comment` and `solution` when every lost mark is a low-confidence reading;
- the part is blank: `solution`;
- the part will be on the review note — it earns some but not all of its marks, has a low-confidence step, has a medium-confidence step and earns marks, or has a visual or level step: also `review_detail`;
- full marks: nothing (`submit` adds a fixed comment).

The service scores the judgement and may apply a dependency or route you did not expect. `check` then lists only the parts whose explanation does not fit the actual score — missing, unusable, or written for an earlier score after a judgement change — naming the fields; fill just those. The field meanings are:

- `transcript`: the relevant mark-bearing working of this unit, as written (line breaks allowed, ≤4000 characters).
- `final_answer`: the last expression or statement the candidate offers that is not crossed out, copied literally from your transcript (e.g. `"17ln3 − 4/3"`); do not simplify or change its notation. If the work ends in an equation such as `2y(x + 1) = 3x`, copy that equation, not a tidied `y = …`. Use `""` when there is no written final answer, including a drawing-only answer; keep your description of that drawing in `transcript`. PassMarkedu checks that values in the final answer appear in the transcript and compares it with the expected answer.
- `comment`: one sentence: the overall verdict (e.g. "分部积分方向对，但求导 ln(3x) 出错，原函数和答案都错了。").
- `headline` (units that lost marks): the main reason, ≤20 Chinese characters (or ~10 English words), e.g. "没有积分到 tanθ，也没代入上下限". Used in the report’s main lost-point overview. The annotated script shows red scores and mark codes, while explanations belong in the report.
- `mistakes` (units that lost marks): 1–4 items `{"wrote", "why", "should"}`, one per **actual error in the candidate's work**, in the order it happened — not one per lost mark. If one early error costs five marks, that is one item. `wrote`: the candidate's words from the transcript; `why`: what is wrong, plainly (no "condone", "o.e.", "dM1"); `should`: the correct line. Formulas readable, not LaTeX.
- `solution` (units that lost marks, and unattempted units): 2–6 key lines of a correct method, ending with the correct answer.
- `review_detail` (parts the review note lists): the two readings of the part for the review note — how you judged it, the most plausible other mark and why, where on the script (`crop`: only the lines in dispute plus one line of context, a third of the page height or less), and the mark-scheme words it turns on ([evidence-schema.md](evidence-schema.md#review_detail)). Say what is in doubt plainly; it is not shown to the script's writer.
- `scheme_conflict` (rare): if you believe PassMarkedu's scoring of this unit contradicts the official mark scheme (for example a mark blocked by the wrong prerequisite), say so here in one or two sentences. Only the user sees it. **Never** put such disputes, step ids (`main.s3`), or words about PassMarkedu's server or configuration into the candidate-facing fields — those submissions are rejected with 422.

Full-mark units need no report prose: `submit` adds a fixed comment. Unattempted units need a solution. For a withheld unreadable point, use a neutral comment and correct solution; do not invent an error, headline or mistake to explain an uncertain reading. The precise ambiguity belongs in chat. One actual error may explain several lost points; do not duplicate it per mark.
