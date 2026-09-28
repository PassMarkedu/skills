# Identify a mixed-question script

Read when the upload combines questions from different official papers or lacks a single whole-paper identity. Resolve the configured API origin and account first. After identification, save the ordered IDs (and any `parts`, below) as JSON for `workflow.py prepare --question-ids-json`; use the common per-question workflow.

## Find the sources

Split the script into questions (each printed question with the candidate's answer under it). At most 20 questions per submission; if there are more, tell the user to split the script into several PDFs.

For every question, in this order, stop at the first that works:

1. **The PDF already has text** (try extracting text from the page; typed or digital scripts): use that text.
2. **A printed reference** on the page (e.g. "9709/13/M/J/24" in the footer, "WST01/01", a question number): build a locator like `9709/13 June 2024 Q3` or `WST01 June 2014 Q1`.
3. **Read the printed question text** off the page image yourself (the question, not the candidate's answer; the first 2–4 sentences are enough, keep numbers and symbols).

Send all questions in one call: `POST /identify` with `{"items": [{"key": "Q1", "locator": "...", "text": "..."}, ...]}` (give whichever of `locator`/`text` you have). Each item returns up to 3 `candidates` (`question_id`, `unit_code`, `year`, `session`, `paper_number`, `question_number`, `preview`).

- Pick the candidate whose `preview` matches the printed question. The same question is sometimes reused in two papers (e.g. an old paper and a later variant); pick the one matching any printed reference, otherwise the most recent, and mention the alternative to the user.
- **No candidate** for a question → crop that question's area into a JPEG (under 8 MB) and call `POST /identify-photo` with `{"image_base64": "...", "mime_type": "image/jpeg"}`. This uses PassMarkedu's image recognition and does not use the user's photo-search allowance. Use it only for questions the text step could not match.
- Still nothing → ask the user where that question comes from (paper and question number), or leave it out and say so.

Keep the list of chosen `question_id`s **in the order the questions appear in the script**.

## Record the printed sub-parts

Teachers often print only some parts of a question. For each question, note which of its sub-parts the script actually contains: a part whose question text is not printed on the script, or whose printed text is crossed out, is not included. Compare against the source question's parts (the `preview`, or the checklist later if in doubt).

- Question printed in full → leave it out of `parts`.
- Only some parts printed → list them under `parts` by that question's id, with the source's own labels (`"a"`, `"c(ii)"`).

```json
{"question_ids": ["<id of Q1>", "<id of Q2>"], "parts": {"<id of Q2>": ["a", "b", "c"]}}
```

Here Q1 is printed whole and only (a)–(c) of Q2 are on the script, so the maximum counts only those parts. Pass this file as `--question-ids-json`; a plain array of ids still works when every question is printed in full.
