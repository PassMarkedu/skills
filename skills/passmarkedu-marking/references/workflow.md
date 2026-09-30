# Workflow helper 1.10.2

Use Python 3 and the bundled helper for files and HTTP. Existing `pdfinfo`/`pdftoppm`/`pdftotext` (Homebrew's folders are searched too) or PyMuPDF supplies rendering; no new package is required, and none is ever installed. Set `SKILL` to the installed skill directory and `RUN` to the `run_dir` that `start` reports. Quote paths. The helper reads the origin-scoped saved token itself; tokens never belong in arguments, JSON or output. Every image it produces for you is at most 1080 pixels on its long side, so it arrives unshrunk.

## Start

```bash
python3 "$SKILL/scripts/workflow.py" start --script "/path/to/answer.pdf"
```

For photos, give them in the user's page order: `start --script "/path/IMG_1.jpg" "/path/IMG_2.jpg"`. JPEG goes into the PDF as it is, turned upright from its EXIF orientation; PNG, HEIC and WebP are converted through PyMuPDF or macOS `sips` (elsewhere the error says to send JPEG or PDF). The combined PDF is written beside the first photo (`IMG_1.pdf`) and reported as `script`: use it as `--script` in every later command, and the marked PDFs are copied beside it. Photos have no cover (`cover_image` is `null`); `page_images` lists every page to read.

It resolves the origin and token path, checks for a newer skill (`update`, or `null`), creates the run directory `<script folder>/.passmarkedu/<script name>-<YYYYMMDD-HHMM>`, a hidden folder beside the answer PDF (under `~/.passmarkedu/runs` when the script sits in a code repository or the skill folder), removes that folder's runs created more than 7 days ago (`expired_runs`; only folders holding a helper `manifest.json`), renders page 1 as `cover_image` and reports `page_count`, `renderer` (`pymupdf`, `poppler` or `none`), `token_exists`, `token_path`, `api_base` and `cover_text_hint` (a paper reference found in the PDF's own text layer, else `null`). `--run-dir DIR` uses a given directory instead, which may already hold the input files.

## Identify (no cover)

```bash
python3 "$SKILL/scripts/workflow.py" identify --work-dir "$RUN" --script "/path/to/answer.pdf" \
  --items '[{"key":"Q1","page":1,"text":"<printed question text>"},{"key":"Q2","page":2,"locator":"9709/13 June 2024 Q1"}]'
```

For photos and mixed questions ([mixed-questions.md](mixed-questions.md)). Without `--items` it lists every page's view (`image`) and the PDF's own `text`. With items (`--items-json FILE` reads them from a file) it sends their printed `text`/`locator` to PassMarkedu's question search in one call; the `page` of an item it could not match, and every page in `--photo-pages 1,3`, goes to PassMarkedu's photo identification as an upright page image under 8 MB, one call per page. It prints each item's `candidates` and each photographed page's `candidates` with the `extracted_text`. A photo error (daily allowance `marking_kit_photo_daily_limit`, service unavailable) is reported on that page, and after the daily allowance no further page is sent.

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

`--numbers` takes one or two of the paper's question numbers (`5,6`, `Q5, Q6` and `5.` all mean the same); for three or more it names the pairs to run instead. It reads `RUN/page-map.json` (or `--pages-map FILE`); the map may hold every question. For each question it prints `pages`, `ms_image`, the scoring `units` (step IDs, mark codes, types, checks and descriptions, dependencies, alternative routes, visual flags, pick options and levels, final-answer tolerances; empty fields are left out) and an `evidence_template` with real IDs; its `explain` line says which explanation fields each unit takes. Write both questions' completed units, judgements and explanations together, as `{"units":[...]}` to the reported `evidence_file` (`evidence/batch-1-2.json`, a file that does not exist yet). Consult MS images only under the [MS checks](judging.md#when-to-consult-the-official-ms-image). For a correction, `question --number 1 --pages 2` prints the same for one question and names the evidence file that already holds it.

A `medium` or `low` step also needs `reason` and a one-sentence `note` (judging.md); `check` names the step that lacks them. `null` template fields mean unfinished work, except `figure` (units with a `visual` step): `{"page": N, "box": [left, top, right, bottom]}` around the drawing, in crop coordinates and of any size, or `null` when nothing was drawn. The review note shows that region beside your judgement. Keep common steps and one complete applicable alternative route, remove unused route placeholders, and judge every required point. An absent point is `present: false`; a blank unit is explicitly `attempted: false` with no steps. For a missing numeric answer use `value: ""`, `present: false`. Save the mark-bearing transcript, final answer, position and typed point judgements now, and in the same unit its explanation ([judging.md](judging.md#explain-with-the-judgement)): `comment`, `headline`, `mistakes`, `solution` when it loses marks (`comment` and `solution` only when every lost mark is low confidence), `solution` when blank, and `review_detail` when the review note will list it: it earns some but not all of its marks, has a low-confidence step, has a medium-confidence step and earns marks, or has a visual or level step. A full-mark unit needs none. See `judging.md` for the field meanings. Every `evidence/*.json` file is read, and each supported unit belongs in exactly one of them.

## Zoom only on what a mark turns on

A paper has **4 zoom regions in all**. Zoom only when a mark turns on a symbol you genuinely cannot read on the tile; judge every other doubt from the tiles with `confidence: "low"`, reason `legibility` and a one-sentence note, which puts it on the review list. After the last batch and the unassigned pages, crop the doubts that remain in one call:

```bash
python3 "$SKILL/scripts/workflow.py" crop --work-dir "$RUN" \
  --regions '[{"id":"q1-sign","page":2,"box":[0.25,0.25,0.55,0.40]}]'
```

(`--regions-json FILE` reads the same list from a file.) `page` is the original 1-based page; `box` is `[left, top, right, bottom]` as fractions of the upright original page, from its top-left corner. The helper converts coordinates and handles rotation. Give each box the lines around the doubt, enough to interpret a sign or deletion. Each crop renders at the resolution that fills 1080 pixels (at most 300 dpi, reported as `dpi`); a box larger than half the page, or too large to show more than the tiles, is cut into up to four overlapping crops (`<id>-1`, `<id>-2`, … listed under `repairs`), still one zoom region. `zooms_left` says how many regions the paper has left; a call that would go over is refused and renders nothing. Identical crops are reused and not counted again. Open the resulting images together. If the crop was misplaced, correct the box. After one correctly located crop, a still-unreadable mark remains low-confidence and unearned, to be explained as pending in chat. Enlarging a scan repeatedly does not create source detail.

## Score, review, explain

```bash
python3 "$SKILL/scripts/workflow.py" check --work-dir "$RUN"
```

This validates and merges all judgement files, checks the pages of questions judged wholly blank against the printed booklet (`blank_check`), calls `/score` with the judgements and stores the raw response in `score.json` and the full review/explanation packet in **`check-summary.json`**. Stdout prints compact scores, actionable review items and explanation tasks; `summary_path` and `explanation_details_path` name the saved packet. Read that file for lost-point detail or truncated output. `score.json` does not contain explanation tasks. Repeated `check` with unchanged judgements reuses the saved score without another API call and refreshes the tasks from the explanations as they now are. Type slips it can read without changing a judgement — a number for a numeric `value`, `"true"`/`"false"`/`1`/`0` for `present` — are read as meant (the file is left as written) and listed under `repairs`, together with what `submit` will repair or leave out of a `review_detail` and any `review_detail.crop` taller than 0.4 of the page (kept; none of these needs another turn). Fix a validation error only in the named file/field. Review actual flagged content, reusing inspected regions; keep unresolved flags. A genuine judgement edit needs one new `check` so explanations use its actual score.

`explanation_tasks` lists only the parts whose explanation, against the actual score, is still missing, unusable or written for an earlier score; `explained_units` counts those already complete. For each task, fill the fields in `needs` in that unit of its `evidence_file`; `fix` names what is wrong with a field already there. Actual mistakes need a comment, headline, grouped errors and correct solution; blanks need a solution. Unconfirmed low-confidence losses need a neutral comment and solution, not a fabricated mistake. A part the review note lists (`needs` includes `review_detail`, even at full marks) gets its `review_detail` ([evidence-schema.md](evidence-schema.md#review_detail)); its detailed task adds `page`, `review_reasons` and each step's `description` to quote from. Full-mark units need nothing (`auto_comment_units` counts them); `submit` gives them "本小问全部得分。" or "Full marks for this part." in the run language, also in place of an explanation of a loss the service did not take. When a judgement change changes a part's score, the next `check` asks for its `comment`, `headline` and `mistakes` again until they are rewritten. `reports/<number>.json` sidecars from earlier helpers are still applied.

## Submit and download

```bash
python3 "$SKILL/scripts/workflow.py" submit --work-dir "$RUN" --reviewed
```

Use `--reviewed` only after reviewing the actual list; omit it when no review was required. The helper checks that every needed explanation is complete and current, submits, downloads the PDFs and copies them next to the answer PDF as `<name>-批改答卷.pdf`, `<name>-阅卷结果.pdf` and `<name>-复核说明.pdf` (English runs: `<name>-marked.pdf`, `<name>-report.pdf`, `<name>-review-note.pdf`); each later submit, such as a correction, overwrites them. `annotated_script.path`, `marking_report.path` and `review_note.path` are those copies. It then removes the run's page renders, tiles and crops; `question`, `batch` and `prepare` render them again when a correction needs them, and the zoom regions start afresh. It refuses a listed part's missing `review_detail` or one whose views, `alt_marks` or quote are unusable, naming the field; a piece that only places things on the note (`crop`, `underline`, the MS `page`) is repaired or left out and listed under `repairs`. Its output lists `decide_units`: the review note's rows (`number` ①…, `label`, original `page`), the parts to name in the reply; `check_units` is the subset the service marks `check`. Report-only edits do not require another judgement pass. New review issues after changed judgements stop submission for inspection. A scoring revision mismatch requires new preparation.

If a PDF download fails after the result is saved, repeat `submit`: it reuses the result. If the initial create request times out before saving a result, the outcome is unknown; do not blindly recreate it. Inspect any returned result ID and report what is known. Tool error messages identify the failed operation; report them and use `api.md` for API failures, never helper-source investigation or home-made rendering during marking. For HTTP 5xx the message carries the service's error code and request ID: give the user the operation and request ID, keep the run directory and retry later.

## Corrections and capabilities

When the user states the mark a part should get, record it before changing that part's judgement:

```bash
python3 "$SKILL/scripts/workflow.py" correct --work-dir "$RUN" --label "3(c)" --marks 1
```

`correct` checks the label against the checklist and the mark against that part's maximum, then appends the request to `RUN/corrections.json`; it changes no judgement or score. The next `submit` that updates the saved result sends the pending requests with the evidence and clears them once the update succeeds.

For a correction, edit only the affected question, `check`, rewrite the explanation fields its task names, then `submit --result-id ACTUAL_UUID --reviewed`. Both files refresh; expiry and credit stay the same. Never overwrite other questions to change one mark.

The default workflow uses a single conversation with batched tool calls. Writing files checkpoints progress without clearing model context. If Python execution is unavailable, explain that the helper cannot run; the documented API/manual workflow is available only when the Harness has the required image, file and network tools, and may use more calls. Never claim a helper operation ran when it did not.
