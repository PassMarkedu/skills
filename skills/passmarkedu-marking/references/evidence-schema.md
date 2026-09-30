# Evidence JSON

In workflow 1.10.1, `batch` prints real-ID templates; write each batch's completed units to its new `evidence/batch-*.json` file (every supported unit in exactly one evidence file). Each unit holds its judgement — `transcript`, `final_answer`, positions, `figure`, point judgements, `scheme_conflict` — and, written at the same time, its explanation: `comment`, `headline`, `mistakes`, `solution` for a part that loses marks or is blank, and `review_detail` for a part the review note will list. `check` scores the judgement and then asks only for the explanation fields the actual score still needs; full-mark units get a fixed comment at submit. `reports/<number>.json` sidecars from earlier helpers are still merged in. The helper sends the payload below.

When present, top-level `scheme_revision` is the opaque revision supplied by preparation; a different current revision is rejected with `409 scheme_changed`.

Sent as the `evidence` form field of `POST /results` and `PUT /results/<id>`.

```json
{
  "paper": {"board": "caie", "code": "9709", "component": "13", "series": "May/June 2024"},
  "lang": "zh",
  "units": [
    {
      "unit_id": "<scoring_units[].unit_id from the checklist>",
      "attempted": true,
      "page": 3,
      "y": 0.18,
      "transcript": "u = ln3x, dv/dx = 2x\nx²ln3x − ∫x²·1/(3x) dx\n= x²ln3x − x²/6\n= 9ln9 − 3/2 − ln3 + 1/6 = 17ln3 − 4/3",
      "final_answer": "17ln3 − 4/3",
      "comment": "分部积分方向对，但 ln(3x) 求导出错，原函数和答案都错了。",
      "headline": "ln(3x) 求导出错",
      "mistakes": [
        {"wrote": "du/dx = 1/(3x)", "why": "ln(3x) 的导数是 1/x，漏乘了 3", "should": "du/dx = 1/x"},
        {"wrote": "x²ln3x − x²/6", "why": "上一步的错误带进了原函数", "should": "x²ln(3x) − x²/2"}
      ],
      "solution": ["∫2x ln(3x) dx = x²ln(3x) − ∫x dx = x²ln(3x) − x²/2", "代入 3 和 1：(9ln9 − 9/2) − (ln3 − 1/2)", "= 17ln3 − 4"],
      "steps": [
        {"step_id": "main.s1", "present": true, "confidence": "high", "evidence": "x²ln3x − ∫x²·1/(3x) dx"},
        {"step_id": "main.s2", "present": true, "confidence": "medium", "reason": "deletion", "evidence": "x²ln3x − x²/6",
         "note": "第二行改写过，按未划掉的一行判断。"},
        {"step_id": "main.s3", "present": false, "confidence": "high", "evidence": "x²ln3x − x²/6"}
      ]
    },
    {"unit_id": "<another unit>", "attempted": false}
  ]
}
```

Field rules:

| field | rule |
|---|---|
| `question_set` | Mixed-question mode only, instead of `paper`: `{"question_ids": [...]}` exactly as sent to `POST /question-sets`. |
| `paper` | Same values used for `GET /papers`. Edexcel: `{"board":"edexcel","code":"WST01","series":"October 2025","variant":"A"}` (`variant` only if printed). |
| `lang` | `zh` or `en` — language of both PDFs. |
| `units[].unit_id` | Must be one of the checklist's `scoring_units[].unit_id`. Unknown ids are rejected (422). Units you leave out count as not attempted. |
| `attempted` | `false` for blank parts; then omit `steps`. |
| `page` | 1-based page of the uploaded PDF where the answer starts (count every page). |
| `y` | 0–1, how far down that page the answer starts. |
| `figure` | Units with a `visual` step: `{"page": 3, "box": [0.2, 0.55, 0.8, 0.9]}` around the drawing (fractions of the upright page, like `crop` boxes, any size); `null` or absent when nothing was drawn. Only the review note uses it. |
| `transcript` | Faithful mark-bearing working and relevant corrections from the unit, ≤4000 characters. Every value in `final_answer` must appear in it, or the unit is flagged for the user. For a part with a `level` step: the whole answer in reading order, verbatim (the candidate's wording, spelling and grammar, not corrected or summarised; `[?]` for an unreadable word, `[diagram: …]` for a diagram); the review note prints it for the teacher. |
| `final_answer` | The last expression or statement the candidate offers that is not crossed out, exactly as written; `""` if none. Compared with the transcript and the expected answer; not printed as a separate cover-page field. |
| `comment` | One sentence: the overall verdict, in words a candidate understands. |
| `headline` | Units that lost marks: the main reason in ≤20 Chinese characters; included in the marking report’s main lost-point overview. |
| `mistakes` | Units that lost marks: 1–4 `{"wrote", "why", "should"}`, one per actual error in the candidate's work (not per lost mark). |
| `solution` | Units that lost marks or were not attempted: 2–6 key lines of a correct method, ending with the answer. |
| `scheme_conflict` | Only when you think PassMarkedu's scoring contradicts the official mark scheme; user-only. Step ids or server wording in any other field → 422. |
| `steps[].step_id` | From the checklist. Give every step of the unit; for alternative routes, the steps of the route(s) the candidate used (other routes may be left out). Missing steps on the chosen route count as not earned and are flagged. |
| `steps[].present` | `true` / `false` (JSON booleans). |
| `steps[].awarded` | Integer: `point` steps with `step_marks` > 1, and `level` steps (marks within the level's band). |
| `steps[].value` | `numeric` steps: the candidate's final answer copied exactly as written (text). PassMarkedu compares it. |
| `steps[].matched` | `pick_n` steps: list of 0-based indices into `pick.options` that the candidate states. |
| `steps[].level` | `level` steps: the level reached (0 = none). |
| `steps[].confidence` | `high` / `medium` / `low`, as defined in judging.md. |
| `steps[].reason` | Medium and low steps: `legibility`, `condition`, `deletion`, `alternative_method`, `follow_through`, `drawing`, `levels` or `scheme_gap`. |
| `steps[].evidence` | Short quote of the candidate's work copied from `transcript`, ≤150 characters (the API accepts up to 1000; this skill uses a short, specific quote). |
| `steps[].note` | Medium and low steps: one sentence on what is uncertain. Also special cases ("SC"), `level` reasons and user corrections. In the user's language, no point IDs (shown in the review note). |
| `blank_check` | Set by the helper on `attempted: false` units: `empty`, `ink` or `unknown` from their pages against the printed booklet. Not written by hand. |

## review_detail

Written in the evidence unit, with the judgement, for each part the review note will list: it earns some but not all of its marks, has a low-confidence step, has a medium-confidence step and earns marks, or has a visual or level step. `check` asks for it on any other part the note lists. Only the review note, for the person running the marking, reads it; it never changes a mark. `alt_marks` must differ from the mark the service awards: if it does not, `check` names the field to fix.

```json
"review_detail": {
  "ai_view": "a = 0 算写出的答案，按评分标准扣最后 1 分",
  "alt_marks": 4,
  "alt_view": "a = 0 只是解方程的一步，答案只写了 −4.8",
  "crop": {"page": 6, "box": [0.55, 0.64, 0.79, 0.71]},
  "ms_quote": {"step_id": "b.s4", "text": "… If $a = 0$ is also given and not rejected, score A0", "underline": ["not rejected, score A0"], "page": 17}
}
```

| field | rule |
|---|---|
| `ai_view` | One sentence (≤120 characters) in the user's language: how the awarded mark was judged. |
| `alt_marks` | The most plausible other mark for the part: an integer 0..max, not the awarded mark. |
| `alt_view` | One sentence (≤120 characters): the reading that gives `alt_marks`. |
| `crop` | The decisive lines on the original page: `{page, box}`, box as for `crop` (fractions of the upright page). Frame only the lines in dispute plus one line of context — normally a third of the page height or less, never the whole answer space: the note shows the crop near life size, so a tall one adds pages. |
| `ms_quote` | `step_id`: the step the decision turns on (from the batch's `units[].steps`); `text`: copied from that step's `description` (spacing, punctuation and LaTeX markup aside; "…" may stand for words left out, pieces in order), ≤300 characters; `underline`: 1–6 key phrases copied from `text`; `page`: the mark-scheme page, when known. |

The views, `alt_marks` and the quote carry the decision: `submit` refuses them when unusable, naming the field. `crop`, `underline` and `page` only place things on the note: an unusable one is left out and listed under `repairs`.
