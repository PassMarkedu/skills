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

An implied method still needs the scheme's stated evidence. For example, a fraction does not establish a conditional-probability method if neither the correct events nor the numerator required to imply that method are shown. Do not infer a missing method from a coincidentally suitable number when the written working contradicts it.

- **B1ft**, **A1ft**: as ft above, on the candidate's own earlier value.

## Proofs

- Judge a deduction exactly as the step's `check` (or description) states it. Some schemes accept a bare "p² = 4q − 2, so p² is even, so p is even" (WMA14 June 2025 Q10: "it is not necessary to factorise 4q − 2"); do not demand more than the scheme does.
- Rearranging must reach the form the step names (e.g. `p² = 4q − 2`, p² the subject); an equivalent line in another form (`p² − 4q = −2`) does not earn that M unless the step allows it.
- A final mark that needs "all previous marks awarded" is enforced by PassMarkedu: judge only whether the conclusion itself is complete (contradiction stated and the original statement concluded).

## Examiner conventions (Examiner Reports 2024–2026; quotes and pages in the bench's `records/examiner-reports/`)

- **"Show that" / given answers:** every step to the printed result must be shown; a jump from substitution straight to the given answer loses the final mark (Edexcel), and verifying by substitution is not a proof (CAIE). Working backwards from a value given in a later part, or circular reasoning, earns nothing. A given answer reached through wrong working does not earn full marks.
- **Calculator warning** ("solutions relying on calculator technology are not acceptable", "show all necessary working"): a bare calculator answer earns 0 or only the first M. Quadratics need factorising, the formula with substitution, or completing the square written out; the factorisation must be convincing ((x−14)(x+2)=0 alone is not).
- **"Writing or using" a method:** a mark for "writing or using X" is earned when the candidate works with X's parts — e.g. computes the terms of P(S=3)+P(S=4)+P(S=5) one by one — even if the final addition or combination is missing. The accuracy mark still needs the finished result.
- **Specified method ("Hence", "use …"):** another method earns nothing, but correct use of the candidate's own wrong earlier answer is credited (CAIE; Edexcel only where the scheme marks ft).
- **Multiple answers:** a more accurate correct value written before a wrong rounding keeps the mark (isw, Edexcel). Two answers with no choice made, or a root that should have been rejected, is M1 A0; a repeated solution loses the final mark (CAIE 9231).
- **Penalise once:** the same slip (missing units, radians/degrees, over-accuracy) is penalised once per question (Edexcel).
- **Accuracy:** CAIE non-exact answers 3 s.f., angles in degrees 1 d.p., intermediate values to at least 4 s.f.; an exact answer given as a decimal loses the final A. Edexcel mechanics uses g = 9.8 and answers to 2 or 3 s.f. (a multiple of g is fine; more figures or a fraction of 9.8 loses the mark).
- **Statistics:** hypotheses in terms of the parameter (λ, μ, p) — hypotheses in words are not accepted (Edexcel); conclusions in context, non-assertive ("there is evidence …", never "proves") and not contradicting the test result; table z-values to 4 d.p.
- **Proof:** induction needs the basis with both sides evaluated, the assumption "true for some positive integer k", and the conclusion "true for all positive integers n"; contradiction starts by stating the assumption; every proof ends with a concluding statement. Do not work on both sides of an identity at once; mixing variables inside a proof loses the A mark (CAIE 9231).
- **Mechanics (9231, M1):** an equation with inconsistent dimensions or missing/extra terms earns nothing; suvat used where acceleration is not constant earns 0.
