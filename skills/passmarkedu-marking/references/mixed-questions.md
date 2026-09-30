# Identify questions without a cover

Read when the upload is photos, combines questions from different official papers, or has no cover with a whole-paper identity. Identify every question only through PassMarkedu's own search below — never web search or any other source. After identification, save the ordered IDs (and any `parts`, below) as JSON for `workflow.py prepare --question-ids-json`; use the common per-question workflow.

## Find the sources

Split the script into questions (each printed question with the answer under it). At most 20 questions per submission; if there are more, tell the user to split the script into several PDFs or batches of photos.

1. **See the pages.** For photos, `start` already reported `page_images`. For a PDF, run `identify --work-dir "$RUN" --script "<pdf>"`: it lists each page's `image` and, for a typed or digital script, the PDF's own `text` and any printed `reference`.
2. **Read the printed question, not the answer**: the first 2–4 sentences of its printed text (keep numbers and symbols), and any printed reference with the question number as a locator (e.g. "9709/13/M/J/24" in the footer → `9709/13 June 2024 Q1`; `WST01 June 2014 Q1`).
3. **Search**, every question in one call; `page` is the page the question is printed on:

```bash
python3 "$SKILL/scripts/workflow.py" identify --work-dir "$RUN" --script "<pdf>" \
  --items '[{"key":"Q1","page":1,"text":"A biologist is studying the noises made by dolphins. …"},
            {"key":"Q2","page":2,"locator":"9709/13 June 2024 Q1","text":"Find the coefficient of …"}]'
```

   The helper asks PassMarkedu's question search (no charge). An item it cannot match goes on, by its `page`, to PassMarkedu's photo identification (`photo` in the output, with the `extracted_text` it read). A page with no printed question text (an answer-only page) takes just `{"key", "page"}` and goes straight to photo identification. Each returns up to 3 `candidates` (`question_id`, `board`, `unit_code`, `year`, `session`, `paper_number`, `question_number`, `preview`).
4. **Confirm**: pick the candidate whose `preview` matches the printed question. The same question is sometimes reused in two papers (e.g. an old paper and a later variant); pick the one matching any printed reference, otherwise the most recent, and mention the alternative to the user. If text candidates came back but none fits, run `identify … --photo-pages N` for that page. Photo identification has a daily allowance per account (not the user's photo-search allowance); once an error names `marking_kit_photo_daily_limit`, continue from the printed text.
5. **Still nothing** → ask the user which paper and question it is, or leave it out and say so. Never guess.

Keep the list of chosen `question_id`s **in the order the questions appear in the script**. `prepare` numbers them 1, 2, … in that order; save `page-map.json` with the pages you found (e.g. `{"1":[1],"2":[2,3]}`).

## Record the printed sub-parts

Teachers often print only some parts of a question. For each question, note which of its sub-parts the script actually contains: a part whose question text is not printed on the script, or whose printed text is crossed out, is not included. Compare against the source question's parts (the `preview`, or the checklist later if in doubt).

- Question printed in full → leave it out of `parts`.
- Only some parts printed → list them under `parts` by that question's id, with the source's own labels (`"a"`, `"c(ii)"`).

```json
{"question_ids": ["<id of Q1>", "<id of Q2>"], "parts": {"<id of Q2>": ["a", "b", "c"]}}
```

Here Q1 is printed whole and only (a)–(c) of Q2 are on the script, so the maximum counts only those parts. Pass this file as `--question-ids-json`; a plain array of ids still works when every question is printed in full.
