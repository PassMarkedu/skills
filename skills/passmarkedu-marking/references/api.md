# PassMarkedu marking-kit API

Base: `api_base` from `scripts/config.py resolve` (see SKILL.md §0). All endpoints except login and the signed PDF links need `Authorization: Bearer <token>` read from its `token_path`.

## Login (device code)

| call | result |
|---|---|
| `POST /device-code` | `{device_code, user_code, verification_uri, verification_uri_complete, expires_in, interval}` |
| `POST /token` `{"device_code": "..."}` | 200 `{access_token, token_type, expires_in, user:{id, display_name, is_premium}}`; 400 `{"error": "authorization_pending" \| "slow_down" \| "expired_token" \| "access_denied"}` |
| `GET /me` | who is logged in |
| `POST /logout` | revokes the token |

Tokens last 90 days. A 401 on any call means: delete the saved token and log in again.

## Checklist

`GET /papers?board=caie&code=9709&component=13&series=May%2FJune%202024`
`GET /papers?board=edexcel&code=WST01&series=October%202025&variant=A`

```text
paper            {exam_paper_id, board, code, component, variant, series, title, max_marks, supported}
questions[]      {number, marks, ms_image_url, scoring_units[]}
  scoring_units[] {unit_id, label, marks, supported, steps[], final_answer}
    steps[]       {step_id, mark_code, step_marks, type, check?, description, depends_on[], alternative_group, visual, copy?, pick?, levels?}
ms_pdf_url       official mark scheme PDF (full link, may expire after ~30 min)
qp_pdf_url       official question paper PDF (for data/diagrams the script does not repeat)
subject          e.g. maths, further-maths, physics, chemistry, economics, accounting (mixed sets: per question)
grade_boundaries {series, raw_max_mark, thresholds:[{grade, mark}], official_url} or null
scheme_revision  SHA-256 of the normalized scoring rules and grade thresholds
usage            {is_premium, free_papers_total, free_papers_used, free_papers_remaining, subscribe_url}
```

`paper.unsupported[]` (`{label, marks}`) lists parts with no structured mark scheme yet: announce them before marking and leave them out.

Errors: 400 bad cover values; 404 no such paper, or `detail` starting `paper_not_supported` when no part of the paper can be auto-marked (nothing is charged); 429 `{"code":"quota_exceeded", "meter":"marking_papers", ...}` → free credit used up, point the user to `usage.subscribe_url` / `<base>/pricing`.

## Mixed questions (§546)

| call | body | result |
|---|---|---|
| `POST /identify` | `{"items":[{"key","locator"?,"text"?}], "scope"?:[course keys]}` (≤40 items) | `{"items":[{"key","matched_by":"locator"\|"text"\|"none","candidates":[{question_id, board, unit_code, year, session, paper_number, question_number, course_key, match, preview}]}]}` — no charge |
| `POST /identify-photo` | `{"image_base64","mime_type"}` (one question crop, ≤8 MB) | `{"matched_by","extracted_text","candidates":[…]}` — daily cap per account; 429 `marking_kit_photo_daily_limit` |
| `POST /question-sets` | `{"question_ids":[…], "parts"?:{"<id>":["a","c(ii)"]}}` (≤20, script order) | checklist like `/papers` but `question_set` instead of `paper`, `questions[].source`, folded `grade_boundaries`; charges one paper credit per distinct set of ids |

`parts` (optional) lists the sub-parts printed on the script for a question that is only partly included; a question id absent from `parts` is marked whole. A label selects every step at or below it (`"c"` = c, c(i), c(ii); `"c(ii)"`, `"c.ii"` or `"cii"` = c(ii) only). The checklist then holds only those parts, its `max_marks`, question `marks` and folded grade lines count only them, and `question_set.parts` is echoed back. A label matching no part of that question, or an id not in `question_ids`, is 400. Send the same `question_set` object (with `parts`) in `/score` and `/results` evidence; changing `parts` for the same ids is not charged again.

## Dry run

`POST /score` — JSON body = the evidence JSON. Scores without making a PDF and returns `{total, max_total, grade, grade_range, unsupported[], units[], flagged[], review_items[], recheck[], reliability}`. `recheck[]`: `{unit_id, label, step_id, mark_code, reasons[], check}` — the steps worth one more look. `reliability`: `{level: "ok"|"low", reasons[]}`.

Include the checklist’s `scheme_revision` in evidence. `/score` and result responses return it; HTTP 409 `scheme_changed` means the scoring material changed. Prepare current material in a new run and revisit affected judgements. Older clients without a revision are accepted for compatibility. HTTP 422 `scheme_dependency_unresolved` means an explicit official prerequisite could not be resolved; report the material issue instead of guessing marks.

## Results

| call | body | result |
|---|---|---|
| `POST /results` | multipart: `script` (PDF file), `evidence` (JSON string) | 201 result |
| `PUT /results/<result_id>` | multipart: `evidence` | 200 result (re-marked, not charged) |
| `GET /results/<result_id>` | — | the stored result |
| `GET /results/<result_id>/pdf?token=...` | — | the annotated script PDF (`script_download_url`; legacy `download_url` aliases it; no header needed) |
| `GET /results/<result_id>/pdf?kind=report&token=...` | — | the separate marking report PDF (`report_download_url`; no header needed) |
| `GET /results/<result_id>/pdf?kind=review&token=...` | — | the review note PDF for the person running the marking, not to forward (`review_download_url`; null for older results) |

Result: `{result_id, paper, total, max_total, grade, grade_range, grade_boundaries, unsupported[], not_chosen[], over_answered, complete, units[], flagged[], review_items[], reliability, script_download_url, report_download_url, review_download_url, download_url, expires_at}`.

- `max_total` is the paper's official maximum (the grade table's raw maximum when optional questions make the question marks add up to more). `not_chosen[]`: optional questions left blank, not in `max_total`. `over_answered`: more optional questions answered than allowed — no grade is given; which count is the board's rule.

- Both PDFs are regenerated on correction, keeping the original expiry and paper credit. `report_download_url` is null for older results that have not yet been regenerated into two documents. Present mixed-question results as score/maximum only, even if legacy scoring fields include a folded grade.
- `unsupported[]`: `{label, marks}` — parts with no structured mark scheme; not marked, not in `total`. `max_total` is the whole paper; the marked part is `max_total` minus their marks.
- `grade_range`: `[low, high]` when the unsupported marks could change the grade (then `grade` is null); otherwise `grade` is set and `grade_range` is null.
- `review_items[]`: `{label, page, reasons[], notes[], final_answer, scheme_conflict}` — what to check before passing the PDF on; `notes` are ready-to-say sentences in the result's language. Say them in the chat; they are never printed on the PDF.
`units[]`: `{unit_id, label, question_number, status: scored|unsupported|not_attempted, awarded, max_marks, flags[], steps[], comment, page, y}`.
`flags`: `low_confidence`, `visual`, `missing_evidence`, `dependency_conflict`, `dependency_uncertain`, `numeric_unchecked`, `level_judgement`, `awarded_clamped`, `capped`, `unmarked`.
The result also carries `recheck[]` and `reliability` as in the dry run.
`grade` is null when the series has no official thresholds or some parts are not yet supported.

Errors: 413 scan over 50 MB; 422 evidence does not match the checklist (the message names the field); 404 result expired (results are kept 7 days).

Notes on steps: `depends_on` lists prerequisite step ids; when it names steps from several alternative routes, only the prerequisites on the route the candidate followed count. `visual: true` marks a step judged on a drawing.
