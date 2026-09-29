---
name: passmarkedu-marking
description: Mark a candidate's scanned CAIE (Cambridge International AS & A Level) or Pearson Edexcel IAL exam script against the official mark scheme, point by point, and return an annotated-script PDF and a separate marking-report PDF with explanations and official mark-scheme pages. Use after installing this skill to welcome the user and connect their account, when a user uploads a scanned exam paper (PDF or photos) and asks to mark / grade / 判分 / 批改 / 阅卷 it, or asks to change a mark on a paper this skill already marked.
---

# PassMarked A-level 阅卷 Skill

You mark a candidate's handwritten exam script against the **official** mark scheme held by PassMarked A-level, then PassMarked A-level adds the marks up, grades the paper and builds two PDFs: the annotated script and the marking report. You never add marks up or decide the grade yourself — the server does that from your per-point evidence. The same evidence and scoring data produce the same server-calculated marks; different models can still read handwriting or judge a point differently. Never promise identical marks across models.

Talk to the user in the language they use (default Chinese). Keep messages short.

**Who is who.** The user may be the person who wrote the script, or someone marking it for them — you cannot tell, so never guess. In the chat and in every text you send (comments, mistakes, solutions), never call anyone 老师 / 学生 / teacher / student. Address the user as 你; refer to the script and its writer as 答卷 / 作答 / 卷面 (e.g. "答卷第 4 页", "卷面上写的是 …").

**Both PDFs are handed on as they are.** Everything printed in them is read by whoever wrote the script, so it holds only the marking: scores, what went wrong, the correct method, the official mark scheme. Anything about checking the marking — doubtful points, warnings about reliability, disagreements with the scoring — belongs in the chat, never in either PDF.

**Honesty rule.** `evidence` must quote what the candidate actually wrote. Never copy the mark scheme's expected answer into `evidence`, and never mark a step present because the answer "should" be there. If you cannot read it, say so with `confidence: "low"`. A made-up judgement is worse than an unmarked part.

## Installation and first use

After a successful installation, or when the user asks to connect/start using this skill, read `references/onboarding.md` and follow its welcome → account authorisation → upload flow. Do not require a script before connecting the account. On an update, preserve saved authorisation and do not repeat the first-install welcome. When the first request already includes a script, give the short service introduction, connect if needed, and continue marking that script.

Supported subjects: **Edexcel IAL** maths, further maths, physics, chemistry, economics, accounting and biology; **CAIE AS & A Level** maths, further maths, physics, chemistry, economics, accounting and computer science. Only mark official past-paper questions for which the service supplies supported scoring units. Dates and current coverage belong at `<base>/marking-kit#faq`; do not promise complete coverage of all papers within a year range. For another subject/board, explain the supported scope before requesting a checklist.

## 0. Setup

- Before any API call, run `python3 <skill-folder>/scripts/workflow.py start --script <pdf>` (§2), or `python3 <skill-folder>/scripts/config.py resolve` when there is no script yet. Use the reported `base`, `api_base`, `token_path`, and `token_exists` in this run. The installed skill's `origin.txt` takes priority; if absent, `PASSMARKEDU_BASE_URL` (older setups: `PASSMARK_BASE_URL`) applies, then `https://passmarkedu.com`. A malformed configured origin is an error to fix, never a reason to silently use production. All calls below are relative to `api_base`.
- Make HTTP calls with whatever you have (`curl`, Python `urllib`/`requests`, a fetch tool). If you cannot reach the internet at all, tell the user this AI app blocks network access and stop.
- Use only the resolved `token_path` to read or write this origin's token. The production origin keeps `~/.passmarkedu/marking-kit-token` and its old fallback and legacy paths. Other origins use a separate SHA-256-named token file; never copy a token between origins. If the home folder is not writable, the helper selects a current-folder path. Create the selected folder if needed, and write tokens with owner-only read/write permissions when supported.
- A folder named `passmark-marking` next to this skill's folder is the old version of this skill. If you see one, tell the user once: "旧版的 passmark-marking 文件夹可以删除，新版叫 passmarkedu-marking。" Never print the token, never paste it into the chat, never ask the user for SMS codes or passwords.

## 0.5 Check for an update (once per conversation, silently)

`start` reports `update` when the service has a newer release (without a script: `GET /skill`, no login, against this folder's `VERSION`). If there is one, tell the user once, in one line, then carry on with the current version:
"PassMarked A-level 阅卷 Skill 有新版本（<version>）。更新方法：把这句话发给我——『请从 <zip_url> 下载 PassMarked A-level 阅卷 Skill，解压后覆盖安装到原来的 passmarkedu-marking 文件夹』。"
If the call fails, skip this step without mentioning it.

## 1. Log in

**If `token_exists` is true, just use that origin's token — say nothing about logging in.** Only run this section when there is no saved token, or a call returns 401.

When not already giving the first-install welcome, tell the user in one short message which case it is:
- no saved token (first use in this app): "第一次使用需要连接你的 PassMarkedu 账号。还没有账号的话，打开下面的链接后先注册（手机号即可），再点「授权」。"
- a call returned 401 (the saved authorisation expired after 90 days or was revoked): "之前的授权已过期（有效期 90 天），需要重新授权一次，之前的批改记录不受影响。"

For a first installation, include the welcome from `references/onboarding.md` in the same message as the real authorisation link. Do not send a second introduction.

Then:
1. `POST /device-code` (no body). Response: `user_code`, `verification_uri_complete`, `device_code`, `interval`, `expires_in`.
2. Give the user the clickable link `verification_uri_complete` and the code: "打开链接 → 登录（或注册）PassMarkedu → 核对授权码 <user_code> → 点「授权」。授权后回到这里，我会自动继续。"
3. Poll `POST /token` with JSON `{"device_code": "..."}` every `interval` seconds (at least 5 s) until it returns 200:
   - 400 `{"error":"authorization_pending"}` → keep waiting; `slow_down` → wait 5 s longer; `access_denied` → tell the user authorisation was declined and stop; `expired_token` (the code is valid for 10 minutes) → tell the user the link timed out and start again from step 1.
4. Save `access_token` to the resolved `token_path` with owner-only read/write permissions when supported, tell the user "已连接 PassMarkedu 账号", and continue with the task they asked for. Send the token as `Authorization: Bearer <token>` on every later call.

If a call returns 401 again right after a fresh login, stop and tell the user to contact PassMarkedu support — do not loop.

## 2. Prepare once

Run `scripts/workflow.py` directly for every download, rendering, crop, check and submission, and work from its compact output. If a helper command fails, report the operation and its message, keep affected doubts low-confidence and continue; never read helper source or write your own rendering or cropping code. A service error (HTTP 5xx) names a request ID: tell the user the operation and that ID, keep the run directory and retry later; do not investigate helper or service code.

1. Run `start --script <pdf>`. In the next tool round, open its `cover_image` together with [workflow.md](references/workflow.md), [judging.md](references/judging.md), [evidence-schema.md](references/evidence-schema.md) and [marking-rules.md](references/marking-rules.md).
2. Read the paper reference and series on the cover (`cover_text_hint` is the PDF's own text, if any). Copy the reference exactly as printed: "WMA13/01A" is code `WMA13` with component `01A` — never drop the trailing letter; it selects a different paper. Run `prepare --work-dir <run_dir> --script <pdf> --paper-ref "WMA13/01A" --series "January 2026" --lang zh`. For mixed questions use [mixed-questions.md](references/mixed-questions.md) first. For photos, combine them in supplied order before `start`. Ask only for genuinely unreadable identity fields.

**Check the match before judging:** the checklist's number of questions and marks must match the script (cover total, printed [n] marks, question wording). If they do not, the identity is wrong — fix the reference and prepare again in a new work directory; never submit against a mismatched paper.

Preparation lists each question's pages and reading tiles (when the question paper fixed the page map), the whole-page views, unassigned pages and MS images. Announce unsupported parts; they are excluded from marking rather than scored zero. On quota exhaustion give `<base>/pricing`. Keep the original page numbers, including covers, repeats and blank pages. If there is no renderer, use the Harness's actual PDF/image viewer.

The work directory records the scoring-material revision. If the service reports that it changed, prepare a new run against the current material and revisit affected judgements; never silently combine old evidence with new rules.

## 3. Mark two questions per round

Process **two complete questions per batch** (a final single question is fine), opening up to eight images per tool round.

1. First round: run `batch --numbers 1,2` and, in the same round, open those questions' tiles (paths are in the preparation output) and the subject rules file named in [judging.md](references/judging.md).
2. Judge from the tiles and the batch packet's structured MS conditions, point IDs and service rules. Open an official MS image only when the [MS checks](references/judging.md#when-to-consult-the-official-ms-image) apply; record a confirmed mismatch in `scheme_conflict`. Keep the effective answer, the working each mark needs and relevant errors or corrections in `transcript`, and judge every supported point from its actual evidence.
3. Fill the batch's `evidence_template` units and write them as `{"units": [...]}` to its new `evidence_file`. A unit with a `visual` step has a `figure`: the drawing's page and box, as for a crop but of any size. Each later round writes the finished batch's file, runs the next `batch` and opens its tiles together. Explanations come after scoring.
4. Note each unreadable sign, power, deletion or graph feature as a doubt and keep going. After the last batch, open the unassigned pages' whole-page views once; work on a spare page belongs to its question.
5. Then one `crop` round for all doubts (boxes at most half the page wide and tall), and patch the evidence. A doubt still unreadable after one correctly located crop stays low-confidence; fix a misplaced box instead of enlarging again.

Without a derived page map, open the whole-page views in order, eight per round, building `page-map.json` as you go, and mark two questions at a time the same way. If a tile shows a question other than the mapped one, rebuild `page-map.json` from the whole-page views.

For an unreadable mark-bearing item, quote the readable part, record the ambiguity with low confidence and withhold the unresolved point. A blank answer is `attempted: false`; unreadable work is not blank. Never invent a symbol or copy the MS into the transcript. Give a short progress update per batch; saved evidence needs no reading back. The default path runs in the current conversation without subagents.

## 4. Score and resolve the actual review list

Run `check` after all supported units have their judgements. It validates real IDs, typed answers and coverage, calls the service and returns grouped review items plus explanation tasks based on the **actual awarded marks**.

The printed `summary_path` names `check-summary.json`, which keeps the scores, review items and full explanation tasks; read it if output was truncated or more detail is needed. An unchanged judgement reuses the saved check.

For a validation error, fix the named file/field only. For a review item, inspect its named lines/features against the already-viewed images; put any necessary new crops in one call. A doubt already cropped in this run does not need the same crop again. Preserve a remaining low-confidence flag and communicate it at delivery. The `--reviewed` acknowledgement records an actual review, not certainty.

After judgement changes, run `check` once to obtain the updated score and explanation tasks. Newly identified issues receive targeted review; correct evidence is not rewritten to eliminate warnings. Use [evidence-schema.md](references/evidence-schema.md) for a field error and [api.md](references/api.md) for an API failure.

## 5. Explain the score, then deliver

Complete `reports/<number>.json` from `explanation_tasks`; no hash is needed. Write the reports for the paper in one batch. Follow [judging.md](references/judging.md#explain-after-scoring): explanations and solutions for actual losses, solutions for blanks. Other full-mark units have no task; `submit` gives them a fixed comment. When `needs` includes `review_detail`, the part is a row of the review note: write it as in [evidence-schema.md](references/evidence-schema.md#review_detail). A low-confidence unconfirmed point must not become a fabricated definite mistake. Keep uncertainty and scheme disputes in the chat, outside the PDFs.

Run `submit`, adding `--reviewed` after the applicable review. It checks report completeness and freshness (naming any `review_detail` field to fix), submits and downloads both PDFs plus `review_note.pdf` when the service provides one. Changing report prose alone does not require another judgement pass. If download fails after a result was saved, retry the same command to reuse that result. The service supplies the completed PDFs; routine rendering and re-inspection of their pages is unnecessary.

Reply from the actual server result, following the review note: total/marked maximum, the grade or its absence (none for mixed questions), and the parts in `submit`'s `decide_units`, e.g. 「批改好了：51 / 75，参考等级 B。有 5 处请你定：5(b)、6、7(b)、8(a)、11(ii)。复核说明只有一页，每处列了两种判法；同意就不用回，要改就照右栏那句回我，比如「② 改成 3 分」。」 Then the labelled files/links with expiry: **批改答卷 PDF** and **阅卷结果 PDF** (these two can be passed on as they are), plus **复核说明 PDF** — for the person running the marking, not to forward with the script: one row per part to decide with the script lines, the mark-scheme wording and both readings, then every part's score. If `over_answered` is true, say that more optional questions were answered than the paper allows, no grade is given, and which questions count must be confirmed under the board's rule. Do not name tiers or give statistics. Keep the run directory and result ID for corrections.

## 6. Corrections

If the user states the mark a part should receive (「② 改成 3 分」 names the part numbered ② in `decide_units`), first run `correct --work-dir <run_dir> --label "3(c)" --marks 1` for that part; it records the request, and the next `submit --result-id` sends it with the update. Reopen the affected question and original region, update only its judgement, then `check`. Refresh its stale report from the new explanation task and `submit --result-id` using the existing result. Both PDFs regenerate without another paper credit or extended expiry. Report the changed score and remaining doubts.

For a pre-helper result, use its original evidence with `PUT /results/<id>` as documented in [api.md](references/api.md). If that evidence is unavailable, request the original marking session or a fresh run. An expired result cannot be recovered by its old download link.
