# Maths and further maths (CAIE 9709/9231, Edexcel IAL WMA/WFM/WST/WME/WDM)

## Mark codes

- **M** (method): a correct method applied to the problem, even with arithmetic slips, unless the step says otherwise. Quoting a formula without using it is not enough. The method must use the *right quantities*: a correct-looking formula with unrelated numbers plugged in (e.g. using a different probability than the one the scheme names) does **not** earn M unless the step says "ft their …" and the numbers are the candidate's own earlier results. An incomplete method (stopping before the step the scheme describes, or leaving out cases) does not earn M. When unsure between M1 and M0, choose M0 with `confidence: "low"` — the user reviews low-confidence steps; over-awarding is the most common AI marking error.
- **A** (accuracy): a correct answer or intermediate value. Normally needs the M it depends on (the server enforces `depends_on`). **A marks are only for correct work**: a right-looking value or form reached through a wrong method earns A0, even if the step lists no prerequisite (e.g. simplifying ln6 − ln3 = ln2 inside a wrongly integrated expression does not earn the simplification A1).
- **B**: an independent correct result or statement.
- **dM / DM / ddM**: a method mark that depends on earlier M marks (server enforces).
- **\*M / \*B**: the starred mark others depend on.
- **ft / FT** (follow through): award if the candidate's work is correct *given their own earlier wrong value*. Check their arithmetic from their value.
- **cao / cso**: correct answer only / correct solution only — no errors anywhere in that part.
- **awrt**: "answers which round to" — e.g. awrt 0.745 accepts 0.7449 and 0.745 but not 0.74.
- **isw**: ignore subsequent working — a correct answer followed by extra wrong working still earns the mark.
- **oe**: or equivalent form.
- **SC** (special case): only when the candidate's route matches the special-case description.
- **implied / may be implied / SOI (seen or implied)**: the mark is earned if a later correct result could only have come from it, even if not written. Example (CAIE 9709/13 June 2024 Q1): writing −150x² and 810x² implies the terms 30x and 405x², so both B1 marks are earned. When several steps are run together, earlier marks are implied.
- **WWW** (without wrong working): the result must not come from incorrect working.

- **B1ft**, **A1ft**: as ft above, on the candidate's own earlier value.

## Proofs

- Judge a deduction exactly as the step's `check` (or description) states it. Some schemes accept a bare "p² = 4q − 2, so p² is even, so p is even" (WMA14 June 2025 Q10: "it is not necessary to factorise 4q − 2"); do not demand more than the scheme does.
- Rearranging must reach the form the step names (e.g. `p² = 4q − 2`, p² the subject); an equivalent line in another form (`p² − 4q = −2`) does not earn that M unless the step allows it.
- A final mark that needs "all previous marks awarded" is enforced by PassMarkedu: judge only whether the conclusion itself is complete (contradiction stated and the original statement concluded).
