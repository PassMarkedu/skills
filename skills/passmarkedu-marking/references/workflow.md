# Workflow helper 1.10

Use Python 3 and the bundled helper for files and HTTP. Existing `pdfinfo`/`pdftoppm`/`pdftotext` or PyMuPDF supplies rendering; no new package is required. Set `SKILL` to the installed skill directory and `RUN` to the `run_dir` that `start` reports. Quote paths. The helper reads the origin-scoped saved token itself; tokens never belong in arguments, JSON or output. Every image it produces for you is at most 1080 pixels on its long side, so it arrives unshrunk.

## Start

```bash
python3 "$SKILL/scripts/workflow.py" start --script "/path/to/answer.pdf"
```

It resolves the origin and token path, checks for a newer skill (`update`, or `null`), creates the run directory `<script folder>/passmarkedu-runs/<script name>-<YYYYMMDD-HHMM>` (under `~/passmarkedu-runs` when the script sits in a code repository or the skill folder), renders page 1 as `cover_image` and reports `page_count`, `token_exists`, `token_path`, `api_base` and `cover_text_hint` (a paper reference found in the PDF's own text layer, else `null`). `--run-dir DIR` uses a given directory instead, which may already hold the input files.

## Prepare

```bash
python3 "$SKILL/scripts/workflow.py" prepare --work-dir "$RUN" \
  --script "/path/to/answer.pdf" --paper-ref "WMA13/01A" --series "January 2026" --lang zh
```

Give the reference exactly as printed on the cover: Edexcel `WMA13/01A`, CAIE `9709/13`. The board follows from it (`--board edexcel|caie` only confirms it); the series is the printed one. A saved `--paper-json` object still works, and mixed sets use `--question-ids-json /path/to/ids.json` instead.

Preparation downloads the checklist, the official question MS images and the question paper, and renders every original page once: a whole-page view and two overlapping half-page reading tiles, `top` and `bottom`, trimmed to the written and printed area (`tile_dpi` reports their resolution; without tiles, use the whole-page views). When the scan has exactly the printed answer booklet's pages, it also writes `RUN/page-map.json` from the question paper (`page_map_source: "question_paper"`): each question then lists its `pages` and `tiles` in reading order, and `unassigned_pages` are pages printed for no question, such as the cover, blank and spare pages. When `page_map` is `null`, `page_map_reason` says why; open the `whole_pages` views in order, up to eight per round, and save the map yourself with continuation pages, for example `{"1":[2],"2":[3,4]}`. It does not guess where a question occurs in a scan it cannot match.

Input files such as `paper.json` and the cover image may already be inside the run directory; preparation preserves them. Existing helper outputs without a manifest are rejected to prevent overwriting another run. Repeated preparation for the same input resumes assets without erasing evidence. A changed scoring revision is an explicit error; use a new run and revisit affected judgements. Entirely unsupported papers and quota failures are surfaced before marking. Without a renderer, view the reported original PDF through the Harness; actual visual inspection is still required.

## Batch

```bash
python3 "$SKILL/scripts/workflow.py" batch --work-dir "$RUN" --numbers 1,2
```

It reads `RUN/page-map.json` (or `--pages-map FILE`); the map may hold every question. For each question it prints `pages`, `ms_image`, the scoring `units` (step IDs, mark codes, types, checks and descriptions, dependencies, alternative routes, visual flags, pick options and levels, final-answer tolerances; empty fields are left out) and an `evidence_template` with real IDs. Write both questions' completed units as `{"units":[...]}` to the reported `evidence_file` (`evidence/batch-1-2.json`, a file that does not exist yet). Consult MS images only under the [MS checks](judging.md#when-to-consult-the-official-ms-image). For a correction, `question --number 1 --pages 2` prints the same for one question and names the evidence file that already holds it.

A `medium` or `low` step also needs `reason` and a one-sentence `note` (judging.md); `check` names the step that lacks them. `null` template fields mean unfinished work, except `figure` (units with a `visual` step): `{"page": N, "box": [left, top, right, bottom]}` around the drawing, in crop coordinates and of any size, or `null` when nothing was drawn. The review note shows that region beside your judgement. Keep common steps and one complete applicable alternative route, remove unused route placeholders, and judge every required point. An absent point is `present: false`; a blank unit is explicitly `attempted: false` with no steps. For a missing numeric answer use `value: ""`, `present: false`. Save the mark-bearing transcript, final answer, position and typed point judgements now. Explanations follow scoring. See `judging.md` for the field meanings. Every `evidence/*.json` file is read, and each supported unit belongs in exactly one of them.

## Crop the collected doubts once

After the last batch and the unassigned pages, crop every doubt in one call:

```bash
python3 "$SKILL/scripts/workflow.py" crop --work-dir "$RUN" \
  --regions '[{"id":"q1-sign","page":2,"box":[0.25,0.25,0.55,0.40]}]'
```

(`--regions-json FILE` reads the same list from a file.) `page` is the original 1-based page; `box` is `[left, top, right, bottom]` as fractions of the upright original page, from its top-left corner. The helper converts coordinates and handles rotation. Give each box enough surrounding work to interpret a sign or deletion, but at most half the page width and half its height. Each crop renders at the resolution that fills 1080 pixels (at most 300 dpi, reported as `dpi`); a box too large to show more than the tiles is refused, so split it into narrower boxes. Identical crops are reused. Open the resulting images together. If the crop was misplaced, correct the box. After one correctly located crop, a still-unreadable mark remains low-confidence and unearned, to be explained as pending in chat. Enlarging a scan repeatedly does not create source detail.

## Score, review, explain

```bash
python3 "$SKILL/scripts/workflow.py" check --work-dir "$RUN"
```

This validates and merges all judgement files, checks the pages of questions judged wholly blank against the printed booklet (`blank_check`), calls `/score` and stores the raw response in `score.json` and the full review/explanation packet in **`check-summary.json`**. Stdout prints compact scores, actionable review items and explanation tasks; `summary_path` and `explanation_details_path` name the saved packet. Read that file for lost-point detail or truncated output. `score.json` does not contain explanation tasks. Repeated `check` with unchanged judgements reuses the saved result without another API call. Fix a validation error only in the named file/field. Review actual flagged content, reusing inspected regions; keep unresolved flags. A genuine judgement edit needs one new `check` so explanations use its actual score.

Write `reports/<number>.json` for the paper in one batch, using this shape:

```json
{"units":[{"unit_id":"REAL_ID","comment":"...","headline":"...","mistakes":[{"wrote":"...","why":"...","should":"..."}],"solution":["..."],"review_detail":{...}}]}
```

Use each task's `needs` fields; omit unneeded fields. Actual mistakes need a comment, headline, grouped errors and correct solution; blanks need a solution. Unconfirmed low-confidence losses need a neutral comment and solution, not a fabricated mistake. A part the review note lists (`needs` includes `review_detail`, even at full marks) gets its `review_detail` ([evidence-schema.md](evidence-schema.md#review_detail)); its task adds `page`, `review_reasons` and each step's `description` to quote from. Other full-mark units have no task (`auto_comment_units` counts every full-mark unit); `submit` gives them "本小问全部得分。" or "Full marks for this part." in the run language. Sidecars change only explanation fields and need no hash: a report written before the unit's latest judgement change is refused as stale. Legacy inline explanations and copied hashes still work.

## Submit and download

```bash
python3 "$SKILL/scripts/workflow.py" submit --work-dir "$RUN" --reviewed
```

Use `--reviewed` only after reviewing the actual list; omit it when no review was required. The helper merges reports, checks freshness and completeness, submits and downloads `annotated_script.pdf` and `marking_report.pdf`. It refuses a listed part's missing or unusable `review_detail`, naming the field. Its output lists `decide_units`: the review note's rows (`number` ①…, `label`, original `page`), the parts to name in the reply; `check_units` is the subset the service marks `check`. Report-only edits do not require another judgement pass. New review issues after changed judgements stop submission for inspection. A scoring revision mismatch requires new preparation.

If a PDF download fails after the result is saved, repeat `submit`: it reuses the result. If the initial create request times out before saving a result, the outcome is unknown; do not blindly recreate it. Inspect any returned result ID and report what is known. Tool error messages identify the failed operation; report them and use `api.md` for API failures, never helper-source investigation or home-made rendering during marking. For HTTP 5xx the message carries the service's error code and request ID: give the user the operation and request ID, keep the run directory and retry later.

## Corrections and capabilities

When the user states the mark a part should get, record it before changing that part's judgement:

```bash
python3 "$SKILL/scripts/workflow.py" correct --work-dir "$RUN" --label "3(c)" --marks 1
```

`correct` checks the label against the checklist and the mark against that part's maximum, then appends the request to `RUN/corrections.json`; it changes no judgement or score. The next `submit` that updates the saved result sends the pending requests with the evidence and clears them once the update succeeds.

For a correction, edit only the affected question, `check`, refresh its explanation task, then `submit --result-id ACTUAL_UUID --reviewed`. Both files refresh; expiry and paper credit stay the same. Never overwrite other questions to change one mark.

The default workflow uses a single conversation with batched tool calls. Writing files checkpoints progress without clearing model context. If Python execution is unavailable, explain that the helper cannot run; the documented API/manual workflow is available only when the Harness has the required image, file and network tools, and may use more calls. Never claim a helper operation ran when it did not.
