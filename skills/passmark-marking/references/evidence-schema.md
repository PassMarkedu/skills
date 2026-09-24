# Evidence JSON

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
      "comment": "二项式展开正确；系数 660 正确。",
      "steps": [
        {"step_id": "s1", "present": true, "confidence": "high", "evidence": "C(10,1)·3x → −150x²", "note": ""},
        {"step_id": "s4", "present": false, "confidence": "medium", "evidence": "wrote 7π/6", "note": "B 是第二个最小点，x = 19π/6"}
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
| `lang` | `zh` or `en` — language of the marked PDF. |
| `units[].unit_id` | Must be one of the checklist's `scoring_units[].unit_id`. Unknown ids are rejected (422). Units you leave out count as not attempted. |
| `attempted` | `false` for blank parts; then omit `steps`. |
| `page` | 1-based page of the uploaded PDF where the answer starts (count every page). |
| `y` | 0–1, how far down that page the answer starts. |
| `comment` | 1–3 sentences for the teacher, ≤1000 characters. |
| `steps[].step_id` | From the checklist. Give every step of the unit; for alternative routes, the steps of the route(s) the student used (other routes may be left out). Missing steps on the chosen route count as not earned and are flagged. |
| `steps[].present` | `true` / `false` (JSON booleans). |
| `steps[].awarded` | Integer: `point` steps with `step_marks` > 1, and `level` steps (marks within the level's band). |
| `steps[].value` | `numeric` steps: the student's final answer copied exactly as written (text). PassMarkedu compares it. |
| `steps[].matched` | `pick_n` steps: list of 0-based indices into `pick.options` that the student states. |
| `steps[].level` | `level` steps: the level reached (0 = none). |
| `steps[].confidence` | `high` / `medium` / `low`. |
| `steps[].evidence` | Short quote of the student's work, ≤1000 characters. |
| `steps[].note` | Short reason when not earned (or the teacher's correction reason). |
