---
name: passmarkedu-marking
description: Mark a student's scanned CAIE (Cambridge International AS & A Level) or Pearson Edexcel IAL exam script against the official mark scheme, point by point, and return a marked PDF with per-part scores, comments, the official grade and the mark-scheme pages. Use when a teacher uploads a scanned exam paper (PDF or photos) and asks to mark / grade / 判分 / 批改 / 阅卷 it, or asks to change a mark on a paper this skill already marked.
---

# PassMarkedu 阅卷 Skill

You mark a student's handwritten exam script against the **official** mark scheme held by PassMarkedu, then PassMarkedu adds the marks up, grades the paper and builds the marked PDF. You never add marks up or decide the grade yourself — the server does that from your per-point evidence. This keeps results consistent even for weaker models.

Talk to the teacher in the language they use (default Chinese). Keep messages short.

**Honesty rule.** `evidence` must quote what the student actually wrote. Never copy the mark scheme's expected answer into `evidence`, and never mark a step present because the answer "should" be there. If you cannot read it, say so with `confidence: "low"`. A made-up judgement is worse than an unmarked part.

## 0. Setup

- API base: `PASSMARKEDU_BASE_URL` if set (older setups: `PASSMARK_BASE_URL`), otherwise `https://passmarkedu.com`. All calls below are relative to `<base>/api/v1/marking-kit`.
- Make HTTP calls with whatever you have (`curl`, Python `urllib`/`requests`, a fetch tool). If you cannot reach the internet at all, tell the teacher this AI app blocks network access and stop.
- The token lives in `~/.passmarkedu/marking-kit-token` (create the folder if needed). If the home folder is not writable in this app's sandbox, use `.passmarkedu-marking-token` in the current working folder instead, and check both places when looking for a saved token.
- Older versions of this skill saved the token in `~/.passmark/marking-kit-token` or `.passmark-marking-token`. If you find one there and none in the new places, move it to the new place and use it; the teacher does not need to log in again.
- A folder named `passmark-marking` next to this skill's folder is the old version of this skill. If you see one, tell the teacher once: "旧版的 passmark-marking 文件夹可以删除，新版叫 passmarkedu-marking。" Never print the token, never paste it into the chat, never ask the teacher for SMS codes or passwords.

## 0.5 Check for an update (once per conversation, silently)

`GET /skill` (no login needed) returns `{version, zip_url, npx_command}`. Compare `version` with the `VERSION` file next to this SKILL.md. If the server's is newer, tell the teacher once, in one line, then carry on with the current version:
"PassMarkedu 阅卷 Skill 有新版本（<version>）。更新方法：把这句话发给我——『请从 <zip_url> 下载 PassMarkedu 阅卷 Skill，解压后覆盖安装到原来的 passmarkedu-marking 文件夹』；WorkBuddy 用户也可以在 SkillHub 里更新。"
If the call fails, skip this step without mentioning it.

## 1. Log in

**If a saved token exists, just use it — say nothing about logging in.** Only run this section when there is no saved token, or a call returns 401.

Tell the teacher first, in one short message, which case it is:
- no saved token (first use in this app): "第一次使用需要连接你的 PassMarkedu 账号。还没有账号的话，打开下面的链接后先注册（手机号即可），再点「授权」。"
- a call returned 401 (the saved authorisation expired after 90 days or was revoked): "之前的授权已过期（有效期 90 天），需要重新授权一次，之前的批改记录不受影响。"

Then:
1. `POST /device-code` (no body). Response: `user_code`, `verification_uri_complete`, `device_code`, `interval`, `expires_in`.
2. Give the teacher the clickable link `verification_uri_complete` and the code: "打开链接 → 登录（或注册）PassMarkedu → 核对授权码 <user_code> → 点「授权」。授权后回到这里，我会自动继续。"
3. Poll `POST /token` with JSON `{"device_code": "..."}` every `interval` seconds (at least 5 s) until it returns 200:
   - 400 `{"error":"authorization_pending"}` → keep waiting; `slow_down` → wait 5 s longer; `access_denied` → tell the teacher authorisation was declined and stop; `expired_token` (the code is valid for 10 minutes) → tell the teacher the link timed out and start again from step 1.
4. Save `access_token` to the token file, tell the teacher "已连接 PassMarkedu 账号", and continue with the task they asked for. Send the token as `Authorization: Bearer <token>` on every later call.

If a call returns 401 again right after a fresh login, stop and tell the teacher to contact PassMarkedu support — do not loop.

## 2. Decide the mode

- **Whole paper**: the script starts with an official cover page (Cambridge / Pearson answer booklet with syllabus or unit code and series), and the questions follow in that paper's order. → section 2A, then 3A.
- **Mixed questions**: no official cover, or the questions come from different papers (a teacher's worksheet, a revision pack, questions cut from several past papers). → section 2B, then 3B.

If unsure, look at 2–3 question pages: a real answer booklet prints "Question 1", "Question 2"… in order under one paper reference.

## 2A. Whole paper — read the cover

Look at the first page(s) of the script and read:

- **board**: `caie` (Cambridge International) or `edexcel` (Pearson Edexcel International Advanced Level).
- **code**: CAIE syllabus code (e.g. `9709`), or the Edexcel unit code (e.g. `WST01`, `WMA11`, `WPH11`).
- **component** (CAIE only): the two-digit paper/variant after the slash, e.g. `9709/13` → `13`.
- **variant** (Edexcel only, optional): a letter printed after the paper reference such as `WST01/01A` → `A`. Omit if there is none.
- **series**: month and year of the sitting, taken from the cover — never guessed; a wrong series gives a wrong grade. CAIE prints it directly (`May/June 2024`, `October/November 2023`, `February/March 2025`). Edexcel prints the exam date (e.g. "Friday 17 October 2025") — use its month and year: `October 2025`.

If any of these is unreadable, ask the teacher before continuing.

## 2B. Mixed questions — find where each question comes from

Split the script into questions (each printed question with the student's answer under it). At most 20 questions per submission; if there are more, tell the teacher to split the script into several PDFs.

For every question, in this order, stop at the first that works:

1. **The PDF already has text** (try extracting text from the page; typed or digital scripts): use that text.
2. **A printed reference** on the page (e.g. "9709/13/M/J/24" in the footer, "WST01/01", a question number): build a locator like `9709/13 June 2024 Q3` or `WST01 June 2014 Q1`.
3. **Read the printed question text** off the page image yourself (the question, not the student's answer; the first 2–4 sentences are enough, keep numbers and symbols).

Send all questions in one call: `POST /identify` with `{"items": [{"key": "Q1", "locator": "...", "text": "..."}, ...]}` (give whichever of `locator`/`text` you have). Each item returns up to 3 `candidates` (`question_id`, `unit_code`, `year`, `session`, `paper_number`, `question_number`, `preview`).

- Pick the candidate whose `preview` matches the printed question. The same question is sometimes reused in two papers (e.g. an old paper and a later variant); pick the one matching any printed reference, otherwise the most recent, and mention the alternative to the teacher.
- **No candidate** for a question → crop that question's area into a JPEG (under 8 MB) and call `POST /identify-photo` with `{"image_base64": "...", "mime_type": "image/jpeg"}`. This uses PassMarkedu's image recognition and does not use the teacher's photo-search allowance. Use it only for questions the text step could not match.
- Still nothing → ask the teacher where that question comes from (paper and question number), or leave it out and say so.

Keep the list of chosen `question_id`s **in the order the questions appear in the script**.

## 3A. Fetch the checklist (whole paper)

`GET /papers?board=..&code=..&component=..&variant=..&series=..` (URL-encode the series).

- 200 → the checklist (see `references/api.md`). The first fetch of a paper uses one of the account's paper credits; fetching the same paper again is free.
- 404 → tell the teacher PassMarkedu has no such paper and ask them to double-check the cover values.
- 429 with `"code": "quota_exceeded"` → say: "免费额度已用完（免费账号可批 1 份试卷）。订阅 PassMarkedu 后可不限次使用：<base>/pricing" and stop.
- If `paper.supported` is false, some parts have no structured mark scheme yet. Tell the teacher those parts will show "未自动判分", then continue with the rest.

## 3B. Fetch the checklist (mixed questions)

`POST /question-sets` with `{"question_ids": [...]}`. The response has the same `questions[].scoring_units` as 3A, numbered 1..N in your order, each question with a `source` ("WST01 June 2014 Q1"). `grade_boundaries` is a *folded indicative* grade line built from each source paper's official thresholds (`"folded": true`), or null. The same 429 / 404 handling as 3A applies; 400 means the set is too large or an id is wrong. There is no single QP/MS PDF — use each question's `ms_image_url`.

## 3C. Using the checklist (both modes)

Use `scoring_units` (not anything else) as the list of parts to mark. Open a question's `ms_image_url` (official mark-scheme screenshot) when a step description is unclear; the steps are the source of truth for marks. Some answers need data that is only in the question paper (a table, a given diagram or box plot): open `qp_pdf_url` for that question instead of guessing.

## 4. Work one question at a time — and keep the teacher informed

Marking a paper takes several minutes. **Post a short progress line in the chat as you go** so the teacher can see it is working, for example:

- after identifying: "已识别试卷：WST01 October 2025（共 7 题），开始逐题批改。" / "已识别 12 道题，来自 4 份真题，开始逐题批改。"
- after each question: "已完成 3/7：第 3 题 7/11。"
- before submitting: "7 题已全部判完，正在生成批改 PDF……"

Keep each update to one line; do not paste transcriptions or JSON into the chat.

Papers are long. Do NOT try to hold the whole paper in your head. Loop over the questions in the checklist, and for each question:

1. find its pages in the script, do **pass 1** (transcribe) for its scoring units,
2. then **pass 2** (judge every step) for those units,
3. append that question's units to your evidence file (`evidence.json` in your working folder) before moving on.

Every question in the checklist must be processed before you submit — never stop early or leave a question out because the paper is long. If a question is truly unreadable, still write its units with `confidence: "low"` judgements for what you can see, rather than dropping them.

### Pass 1 — transcribe

Page numbers: page 1 = first page of the uploaded PDF, counting every page including the cover and blank pages. For every scoring unit of the question (`scoring_units[].label`, e.g. `1(a)`, `2(c.ii)`), write down:

- `page`: the page where the answer to that part **starts** (if the working continues or a drawing sits on a later page, still give the starting page and mention the other page in your transcription);
- `y`: how far down that page the answer starts, as a fraction 0–1 (0 = top edge, 0.5 = middle);
- a faithful transcription of what the student wrote, line by line, including crossed-out work (mark it as crossed out) and final answers;
- whether the part was attempted at all.

For drawings (graphs, sketches, box plots, histograms, diagrams), describe what is drawn precisely: axes and scales, plotted points/end-points/intercepts, shape, labels, and read values off the grid. Zoom in on the page image if your tool allows it.

Ignore any ticks, crosses or marks that are already on the scan — mark the student's work afresh. If handwriting is small, render the page at a higher resolution (200–300 dpi) or crop to the answer area before reading. Do not judge marks in this pass.

### Pass 2 — judge each mark-scheme step

Before your first paper, read `references/marking-rules.md` (all subjects) and the one subject file matching the checklist's `subject`:

| `subject` | read |
|---|---|
| maths, further-maths | `references/rules-maths.md` |
| physics, chemistry, biology | `references/rules-sciences.md` |
| economics, business | `references/rules-economics-business.md` |
| accounting | `references/rules-accounting.md` |

For each scoring unit, go through its `steps` in order. Each step has a `type`; answer only what that type asks, using ONLY your transcription:

| `type` | what you send | what you must NOT do |
|---|---|---|
| `point` (default) | `present`: answer the step's `check` question if it has one (otherwise the `description`) — yes → `true` | do not guess; every condition in the question must hold |
| `numeric` | `value`: the student's final answer copied exactly as written (e.g. `"-0.945"`, `"3/8"`), and `present: true` if they wrote one | do not judge whether it is right — PassMarkedu compares it |
| `pick_n` | `matched`: the indices (0-based) of the `pick.options` the student's answer states; ignore anything on `pick.reject`; `present: true` if any matched | do not count marks yourself |
| `level` | `level`: the level whose descriptor fits best (0 if none), `awarded`: marks within that level's band, and the reason in `note` | do not skip the reason |

For every step also send:
- `confidence`: `high`, `medium` or `low` (`low` whenever the handwriting is unclear or you are unsure).
- `evidence`: the student's exact words/numbers for this step, copied from your transcription in the student's own language (short). Never the mark scheme's words.
- `label`: a few words naming the step, in the teacher's language, for a student to read (≤10 Chinese characters or ~5 English words), e.g. "求 dx/dθ", "代入上下限", "最终答案".
- `note`: when the step is not earned, one short sentence saying what is wrong, in plain words a student understands — no mark-scheme jargon (no "condone", "o.e.", "dM1").
- `should`: when the step is not earned, what the correct working or answer is (e.g. "∫sec²θ dθ = tanθ，得到 (1/16)tanθ"). Write formulas readably, not in LaTeX.
- `awarded`: only for `point` steps whose `step_marks` is more than 1 (M2, K2 …) and for `level` steps.

Rules:
- Judge each step on what is written; do not skip later steps because an earlier one failed — the server applies dependencies (`depends_on`) itself, including dependencies on earlier parts. If a dependent step's content is present but its prerequisite was not earned, still send `present: true`; the server decides.
- Where a unit has several `alternative_group` routes ("Way 1", "Way 2"), judge the steps of the route(s) the student actually used; you may leave out the steps of routes they clearly did not use. The server picks the best route.
- Special cases ("SC B1 if …", "SC M1M0A0"): when the student's work matches a special case, set `present`/`awarded` on the listed steps so that the total equals what the special case gives, and say "SC" in the `note`.
- Steps with `"visual": true` are judged on a drawing. Judge them from your description in pass 1; they are always shown to the teacher for review.
- Blank or unattempted parts: send `"attempted": false` and no steps.
- Add a short `comment` per unit (in the teacher's language): what earned marks, what lost marks, and the correct key step. Keep it to 1–3 sentences, in words a student understands.
- Add a `headline` per unit that lost marks: the main reason, ≤20 Chinese characters (or ~10 English words), e.g. "没有积分到 tanθ，也没代入上下限". It is written in red beside the score on the student's answer page.

### Look again at the doubtful steps (once)

When every question is judged, send the evidence JSON to `POST /score` (plain JSON body, same content you will submit; no PDF is made, nothing is charged again). The response has `recheck`: a short list of steps (low confidence, drawings, unclear dependencies, numbers PassMarkedu could not compare, missing judgements, parts left unmarked) with the reason and the step's question.

Look at **only those steps** again on the page images, zooming in, and correct your evidence where you were wrong. For reason `correctness_required` (an accuracy mark whose scheme demands correct work, cao or cso): compare the student's expression or value **symbol by symbol** with the one in the step description — a right-looking form with a wrong term, power, sign or function (e.g. `3cos²t` where the scheme has `3sin²t cos t`) is not earned. Do this once; do not loop. Then submit (section 5). Tell the teacher in one line: "正在复核 N 个不确定的得分点……".

## 5. Submit and hand back the PDF

Build the evidence JSON exactly as in `references/evidence-schema.md` (whole paper: the same `paper` fields you used in 3A; mixed questions: `"question_set": {"question_ids": [...]}` instead of `paper`; plus `"lang": "zh"` or `"en"` matching the teacher). Then:

`POST /results` as `multipart/form-data` with fields `script` (the uploaded PDF file; if the teacher sent photos, first combine them into one PDF in page order) and `evidence` (the JSON **text** as a form value, not a file upload). With curl:

```bash
curl -sS -X POST "$BASE/api/v1/marking-kit/results" \
  -H "Authorization: Bearer $(cat ~/.passmarkedu/marking-kit-token)" \
  -F "script=@script.pdf;type=application/pdf" \
  -F "evidence=<evidence.json"
```

(`<file` sends the file's content as a text field; `@file` would send it as a file and is rejected.)

Before submitting, check: every `unit_id` of every question appears once; every attempted unit has its steps. A unit sent as attempted but with no steps comes back as "未判分" and the paper gets no grade.

- 201 → reply with: total `total/max_total`, `grade` (or say no grade if `grade` is null), a one-line score per question, the 3–6 most important places marks were lost, the `flagged` list ("需老师复核"), and the `download_url` link to the marked PDF (valid until `expires_at`). Also give the teacher `ms_pdf_url` from the checklist as the original mark scheme. Keep the `result_id`.
- 422 → your evidence JSON does not match the checklist; fix the field it names and resubmit.
- 413 → the scan is over 50 MB; ask the teacher for a smaller scan.

If `reliability.level` is `"low"`, say so plainly first: "这次判分可信度偏低（几乎全部判为得分，或证据与评分标准雷同），建议换用更强的模型重新批改，或请老师逐题复核。"

Remind the teacher in one line that this is AI pre-marking against the official mark scheme and that flagged items should be checked. For mixed questions, say the grade is a folded indicative grade (not an official grade) and list each question's source.

## 6. Teacher corrections

When the teacher says a mark is wrong (e.g. "6(b) 应该给 1 分，因为…"), update the affected steps in your evidence JSON (set `present`/`awarded`, put the teacher's reason in `note`, `confidence: "high"`) and `PUT /results/<result_id>` with the multipart field `evidence` only (`-F "evidence=<evidence.json"`). Reply with the new total, grade and the new `download_url`. Corrections never use a paper credit.

## Files

- `references/api.md` — endpoints, response fields, errors.
- `references/evidence-schema.md` — the evidence JSON with a worked example.
- `references/marking-rules.md` — rules for every subject.
- `references/rules-maths.md`, `rules-sciences.md`, `rules-economics-business.md`, `rules-accounting.md` — read only the one for the paper's subject.
