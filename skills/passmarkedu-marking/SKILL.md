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

- Before the welcome, update check, or any API call, run `python3 <skill-folder>/scripts/config.py resolve`. Use its `base`, `api_base`, `token_path`, and `token_exists` in this run. The installed skill's `origin.txt` takes priority; if absent, `PASSMARKEDU_BASE_URL` (older setups: `PASSMARK_BASE_URL`) applies, then `https://passmarkedu.com`. A malformed configured origin is an error to fix, never a reason to silently use production. All calls below are relative to `api_base`.
- Make HTTP calls with whatever you have (`curl`, Python `urllib`/`requests`, a fetch tool). If you cannot reach the internet at all, tell the user this AI app blocks network access and stop.
- Use only the resolved `token_path` to read or write this origin's token. The production origin keeps `~/.passmarkedu/marking-kit-token` and its old fallback and legacy paths. Other origins use a separate SHA-256-named token file; never copy a token between origins. If the home folder is not writable, the helper selects a current-folder path. Create the selected folder if needed, and write tokens with owner-only read/write permissions when supported.
- A folder named `passmark-marking` next to this skill's folder is the old version of this skill. If you see one, tell the user once: "旧版的 passmark-marking 文件夹可以删除，新版叫 passmarkedu-marking。" Never print the token, never paste it into the chat, never ask the user for SMS codes or passwords.

## 0.5 Check for an update (once per conversation, silently)

`GET /skill` (no login needed) returns `{version, zip_url, npx_command}`. Compare `version` with the `VERSION` file next to this SKILL.md. If the server's is newer, tell the user once, in one line, then carry on with the current version:
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

Read [workflow.md](references/workflow.md) once for the bundled commands. Use `scripts/workflow.py` for material downloads, rendering, crops, validation, scoring and delivery. Execute it directly; its compact results are the working interface.

Read the uploaded cover to identify the board, code, printed series and component/variant. Copy the paper reference exactly as printed: "WMA13/01A" is code `WMA13` with component `01A` — never drop the trailing letter; it selects a different paper. Save `paper.json`, then run `prepare` in a new work directory next to the answer script (`<script folder>/passmarkedu-runs/<script name>-<YYYYMMDD-HHMM>`), never in the current directory when that is a code repository or the skill folder. For mixed questions use [mixed-questions.md](references/mixed-questions.md) first. For photos, combine them in supplied order before preparation. Ask only for genuinely unreadable identity fields.

**Check the match before judging:** the checklist's number of questions and marks must match the script (cover total, printed [n] marks, question wording). If they do not, the identity is wrong — fix `paper.json` and prepare again in a new work directory; never submit against a mismatched paper.

Preparation returns the question index, original-page paths, official MS images and evidence templates with real IDs. Announce unsupported parts; they are excluded from marking rather than scored zero. On quota exhaustion give `<base>/pricing`. Keep the original page numbers, including covers, repeats and blank pages. If there is no renderer, use the Harness's actual PDF/image viewer.

The work directory records the scoring-material revision. If the service reports that it changed, prepare a new run against the current material and revisit affected judgements; never silently combine old evidence with new rules.

## 3. Mark a batch, then save

Read [judging.md](references/judging.md), the common marking rules and the relevant subject rules once. Process **two complete questions per batch** by default; a final single question is fine.

1. Start at the next unread original page, opening **up to four images in the same tool round** when supported. Once two complete questions and their continuation pages are located, mark and save that batch before advancing to later questions. Build the page mapping as you go; do not first read the whole paper merely to build a map.
2. Get the batch packet with `batch`. Use its structured MS conditions, point IDs and service rules alongside the answer images for routine judging. Open the relevant official MS image only when the [MS checks](references/judging.md#when-to-consult-the-official-ms-image) apply. Reuse images already viewed; record a confirmed mismatch in `scheme_conflict`.
3. Read the effective answer, the working needed for each mark, and relevant errors or corrections. Preserve those lines in `transcript`; a faithful record of unrelated scratch is unnecessary. Judge every supported point, using its actual evidence. Save the batch's question evidence files together in one file-writing round. Report explanations come after scoring.
4. Collect specific unreadable signs, powers, deletions or graph features across the batch. Call `crop` once with their original-page normalized boxes, then open the returned crops together. After **one correctly located enlargement per doubt**, retain unresolved uncertainty and continue. Correct a misplaced crop's coordinates rather than increasing DPI. Extra enlargements need genuinely new source information, such as a replacement scan.
5. Give a short batch progress update, then continue. Full packets and finished evidence stay on disk; reading them back merely to verify a successful file write adds no evidence.

For an unreadable mark-bearing item, quote the readable part, record the ambiguity with low confidence and withhold the unresolved point. A blank answer is `attempted: false`; unreadable work is not blank. Never invent a symbol or copy the MS into the transcript. Saving a file does not clear context; batch tool calls and concise outputs reduce repeated history. The default path runs in the current conversation without subagents.

## 4. Score and resolve the actual review list

Run `check` after all supported units have their judgements. It validates real IDs, typed answers and coverage, calls the service and returns grouped review items plus explanation tasks based on the **actual awarded marks**.

The printed `summary_path` points to `check-summary.json`, which preserves scores, review items and full explanation tasks. Read this file if output was truncated or more detail is needed. An unchanged judgement reuses the saved check; there is no need to call the API or inspect helper source to recover report hashes.

For a validation error, fix the named file/field only. For a review item, inspect its named lines/features against the already-viewed images; batch any necessary new views or crops. A doubt already enlarged in this run does not need the same enlargement again. Preserve a remaining low-confidence flag and communicate it at delivery. The `--reviewed` acknowledgement records an actual review, not certainty.

After judgement changes, run `check` once to obtain the updated score and explanation tasks. Newly identified issues receive targeted review; correct evidence is not rewritten to eliminate warnings. Use [evidence-schema.md](references/evidence-schema.md) for a field error and [api.md](references/api.md) for an API failure. Tool errors should be reported with their operation and safe diagnostic; application source-code debugging is outside a marking run.

## 5. Explain the score, then deliver

Complete `reports/<number>.json` from `explanation_tasks`, copying each task's `judgement_sha256`. Write the reports for the paper in one batch. Follow [judging.md](references/judging.md#explain-after-scoring): one short comment for marked units, and explanations/solutions for actual losses or blanks. A low-confidence unconfirmed point must not become a fabricated definite mistake. Keep uncertainty and scheme disputes in the chat, outside the PDFs.

Run `submit`, adding `--reviewed` after the applicable review. It checks report completeness and freshness, merges files, submits and downloads both PDFs plus the review note (`review_note.pdf`) when the service provides one. Changing report prose alone does not require another judgement pass. If download fails after a result was saved, retry the same command to reuse that result. The service supplies the completed PDFs; routine rendering and re-inspection of their pages is unnecessary.

Reply using the actual server result: total/marked maximum, whole-paper grade or its absence (no grade for mixed questions), per-question scores, outstanding review items with original page numbers, and the labelled files/links with expiry: **批改答卷 PDF** and **阅卷结果 PDF** (these two can be passed on as they are), plus **复核说明 PDF** when present — say it is for the person running the marking and should not be forwarded with the script; it lists disputed mark-scheme rules, unreadable figures, levels judgements and why a grade is withheld. If `over_answered` is true, say that more optional questions were answered than the paper allows, no grade is given, and which questions count must be confirmed under the board's rule. State briefly that this is AI marking and identify what still needs checking. Keep the run directory and result ID for corrections.

## 6. Corrections

Reopen the affected question and original region, update only its judgement, then `check`. Refresh its stale report from the new explanation task and `submit --result-id` using the existing result. Both PDFs regenerate without another paper credit or extended expiry. Report the changed score and remaining doubts.

For a pre-helper result, use its original evidence with `PUT /results/<id>` as documented in [api.md](references/api.md). If that evidence is unavailable, request the original marking session or a fresh run. An expired result cannot be recovered by its old download link.
