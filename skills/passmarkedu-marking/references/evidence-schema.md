# Evidence JSON

In workflow 1.9, fill the real-ID per-question judgement files in batches. `check` accepts judgement evidence before report prose is written. After scoring, put `comment`, `headline`, `mistakes` and `solution` in `reports/<number>.json`, with each task’s `judgement_sha256`. The helper merges them into the existing payload below; older inline explanations remain accepted. Keep `transcript`, `final_answer`, positions, point judgements and `scheme_conflict` in the evidence file.

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
| `transcript` | Faithful mark-bearing working and relevant corrections from the unit, ≤4000 characters. Every value in `final_answer` must appear in it, or the unit is flagged for the user. |
| `final_answer` | The candidate's final answer exactly as written; `""` if none. Used for transcript checks and review items; not printed as a separate cover-page field. |
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
| `steps[].confidence` | `high` / `medium` / `low`. |
| `steps[].evidence` | Short quote of the candidate's work copied from `transcript`, ≤150 characters (the API accepts up to 1000; this skill uses a short, specific quote). |
| `steps[].note` | Special cases ("SC"), `level` reasons and user corrections only. |
