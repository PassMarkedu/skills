# Workflow helper 1.9

Use Python 3 and the bundled helper for files and HTTP. Existing `pdfinfo`/`pdftoppm` or PyMuPDF supplies rendering; no new package is required. Set `SKILL` to the installed skill directory and `RUN` to a new directory for this script, next to it: `<script folder>/passmarkedu-runs/<script name>-<YYYYMMDD-HHMM>` (never inside a code repository or the skill folder). Quote paths. The helper reads the origin-scoped saved token itself; tokens never belong in arguments, JSON or output.

## Prepare

Read the cover, then save `paper.json`, for example `{"board":"edexcel","code":"WMA11","series":"January 2026"}`. Mixed sets use an ordered array of source question IDs instead.

```bash
python3 "$SKILL/scripts/workflow.py" prepare --work-dir "$RUN" \
  --script "/path/to/answer.pdf" --paper-json "/path/to/paper.json" --lang zh
```

For mixed sets replace `--paper-json` with `--question-ids-json /path/to/ids.json`. Preparation downloads the checklist and official question MS images, renders original pages once and supplies real-ID evidence templates. It does not guess where a question occurs in the scan. Read original page images in order, up to four per tool round, keeping continuation pages. Retain this reading for judgement rather than doing a second full-paper pass.

Input files such as `paper.json` and a cover image may already be inside the new run directory; preparation preserves them. Existing helper outputs without a manifest are rejected to prevent overwriting another run. Repeated preparation for the same input resumes assets without erasing evidence. A changed scoring revision is an explicit error; use a new run and revisit affected judgements. Entirely unsupported papers and quota failures are surfaced before marking. Without a renderer, view the reported original PDF through the Harness; actual visual inspection is still required.

## Batch

Save a page map from the actual scan, for example `{"1":[2],"2":[3,4]}`. Then fetch two complete questions together:

```bash
python3 "$SKILL/scripts/workflow.py" batch --work-dir "$RUN" \
  --numbers 1,2 --pages-map "$RUN/page-map.json"
```

The page map may retain entries for other known questions as it grows; every selected question needs its original pages. The packet includes scoring units, official MS image paths, original answer paths and evidence paths. View answer pages not yet seen; consult MS images only under the [MS checks](judging.md#when-to-consult-the-official-ms-image). Downloaded MS files remain available for those checks; downloading them does not require loading them into model context. Fill `evidence/<number>.json` for both questions in one writing round. The existing single-question command remains available for corrections:

```bash
python3 "$SKILL/scripts/workflow.py" question --work-dir "$RUN" --number 1 --pages 2
```

`null` template fields mean unfinished work. Keep common steps and one complete applicable alternative route, remove unused route placeholders, and judge every required point. An absent point is `present: false`; a blank unit is explicitly `attempted: false` with no steps. For a missing numeric answer use `value: ""`, `present: false`. Save the mark-bearing transcript, final answer, position and typed point judgements now. Explanations follow scoring. See `judging.md` for the field meanings.

## Crop the batch's doubts once

Save all specific regions in one JSON list:

```json
[{"id":"q1-sign","page":2,"box":[0.25,0.25,0.85,0.40]}]
```

`page` is the original 1-based page; `box` is `[left, top, right, bottom]` as fractions of the upright original page, from its top-left corner. The helper converts coordinates and handles rotation. Use a box with enough surrounding work to interpret a sign or deletion.

```bash
python3 "$SKILL/scripts/workflow.py" crop --work-dir "$RUN" --regions-json "$RUN/regions.json"
```

It returns ordered image paths and original locations, rendering local regions at 300 dpi and reusing identical crops. Open the resulting images together. If the crop was misplaced, correct the box. After one correctly located enlargement, a still-unreadable mark remains low-confidence and unearned, to be explained as pending in chat. Enlarging a scan repeatedly does not create source detail.

## Score, review, explain

```bash
python3 "$SKILL/scripts/workflow.py" check --work-dir "$RUN"
```

This validates and merges all question judgements, calls `/score` and stores the raw response in `score.json` and the full review/explanation packet in **`check-summary.json`**. Stdout prints compact scores, actionable review items and tasks with their hashes; `summary_path` and `explanation_details_path` name the saved packet. Read that file for lost-point detail or truncated output. `score.json` does not contain explanation tasks. Repeated `check` with unchanged judgements reuses the saved result without another API call. Fix a validation error only in the named file/field. Review actual flagged content, reusing inspected regions; keep unresolved flags. A genuine judgement edit needs one new `check` so explanations use its actual score.

Write `reports/<number>.json` for the paper in one batch, using this shape:

```json
{"units":[{"unit_id":"REAL_ID","judgement_sha256":"HASH_FROM_EXPLANATION_TASK","comment":"...","headline":"...","mistakes":[{"wrote":"...","why":"...","should":"..."}],"solution":["..."]}]}
```

Use each task's `needs` fields and `judgement_sha256`; omit unneeded fields. Full-mark units need a brief comment. Actual mistakes need a headline, grouped errors and correct solution; blanks need a solution. Unconfirmed low-confidence losses need a neutral comment and solution, not a fabricated mistake. Sidecars change only explanation fields; their hash prevents attaching an old explanation to changed judgements. Legacy inline explanations remain readable.

## Submit and download

```bash
python3 "$SKILL/scripts/workflow.py" submit --work-dir "$RUN" --reviewed
```

Use `--reviewed` only after reviewing the actual list; omit it when no review was required. The helper merges reports, checks freshness and completeness, submits and downloads `annotated_script.pdf` and `marking_report.pdf`. Report-only edits do not require another judgement pass. New review issues after changed judgements stop submission for inspection. A scoring revision mismatch requires new preparation.

If a PDF download fails after the result is saved, repeat `submit`: it reuses the result. If the initial create request times out before saving a result, the outcome is unknown; do not blindly recreate it. Inspect any returned result ID and report what is known. Tool error messages identify the failed operation; use `api.md` for API failures, not application-source investigation during marking.

## Corrections and capabilities

For a correction, edit only the affected question, `check`, refresh its explanation task, then `submit --result-id ACTUAL_UUID --reviewed`. Both files refresh; expiry and paper credit stay the same. Never overwrite other questions to change one mark.

The default workflow uses a single conversation with batched tool calls. Writing files checkpoints progress without clearing model context. If Python execution is unavailable, explain that the helper cannot run; the documented API/manual workflow is available only when the Harness has the required image, file and network tools, and may use more calls. Never claim a helper operation ran when it did not.
