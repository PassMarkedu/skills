# Marking rules for every subject

The step `description` is the official wording; apply it literally. **Every condition in the description must be met** before `present: true` — watch for sentences such as "just stating the values is insufficient", "must be seen in context", "must be in the form …", "cao", "from correct working only", "do not ISW". Example: "A1 both A = 3 and B = −7, seen in context e.g. 3 − 7/(x+2); just stating A and B is insufficient" is A0 when the candidate only wrote A = 3, B = −7. A `check` is a concise question about that point; apply it together with the original conditions, not as permission to override them. These notes explain the shorthand.

## A marks and correct work (all subjects)

- An accuracy/answer mark is only for correct work: a right-looking value reached through a wrong method or wrong data earns nothing, even if the step lists no prerequisite.
- Over-awarding is the most common AI marking error. When unsure, choose "not earned" with `confidence: "low"` — the user reviews low-confidence steps.

## Own figure (OF, ft, "own figure", "cf")

When a step's description, `check` or official MS line carries OF / ✓OF / ft / own figure — check the MS line even when the `check` names only the scheme's figure:
1. Find in your transcript the earlier figure it builds on: the part it names ("from (b)(i)", "own figure must come from (d)"), otherwise the figures the line is made from.
2. Redo the line with the scheme's method and the candidate's own earlier figure. If their figure matches, the mark is earned although it differs from the scheme's figure. Write the basis in `note`, e.g. "OF: 46,200 = own capital from (b)(i), p.9".
3. Carrying an own figure unchanged into a later line or statement (capital into the statement of financial position, a closing balance into trade payables) is OF when that line is OF.
4. A split mark such as "(2/1of)" is stored as two steps: the OF mark, and a mark for the exact figure only. Conditions on the OF route ("no aliens for the OF mark") limit own figures only: **the scheme's correct figure earns both** ("correct figure gets 2").
5. A figure equal to the scheme's answer is not an OF case — judge it as correct, subject to the step's other conditions.

## Levels-based answers — `level` steps (all subjects)

1. **Best fit, not every phrase.** Read the descriptors from the top down and choose the level that best fits the answer as a whole; an answer does not have to meet every phrase of a level (examiners mark positively). Best fit works both ways: many short points do not stand in for the developed reasoning a higher level names ("developed chains of reasoning", "balanced", "decision").
   **Check your reason against the level.** If your `note` lists weaknesses that the next level down describes (chains short or undeveloped, one-sided, points contradicting the case, figures not used, no decision), choose that lower level.
2. **Apply the question's own examiner notes literally.** "A generic answer … should be given the lowest mark within the appropriate level" moves the mark to the bottom of the level you chose; do not also drop a level for it (double penalty). Whether missing context caps the level differs by board and subject — the board file says which.
3. Put the level, the marks and a one-sentence reason in `note`. Level judgements are always reviewed by the user.
4. If such an answer is stored as a plain `point` step (mark code `LOR`, no `levels`), read the level grid from the question's `ms_image_url`, apply these rules and send the marks in `awarded`.
5. Then read the board's subject file under `references/levels/` (table in `judging.md`) for how that board's examiners place answers in levels.

## Drawings (steps marked `"visual": true`)

- Check each feature the description lists (end-points, whiskers, outliers, intercepts, turning points, asymptotes, shape, labels) against the candidate's drawing.
- Use the tolerance in `final_answer.tolerance` (e.g. "within half a small square"); read values off the grid.
- If the drawing is faint, partly cut off or ambiguous, set `confidence: "low"`. These steps are always listed for the user to check.

## Crossed-out and repeated work

- Interpret corrections at their actual scope. A deleted term in an otherwise retained expression is removed from the effective answer; the remaining expression is the offered answer. This is different from crossing out an entire attempted solution without offering a replacement: apply that board’s original general marking guidance to the abandoned attempt. Preserve relevant deleted text as deleted in the evidence, never silently restore it into `final_answer`.
- If two different final answers are given without one crossed out, do not award the accuracy mark unless the scheme says otherwise.

## Labels and restarts

- Follow clearly continued work, corrected labels and genuine misplaced answers. Use work intended to answer the current part. Do not borrow a separate answer to another part to repair an omission here, unless the official scheme explicitly permits that cross-part credit or follow-through.

## Numbers

- Accept the required accuracy stated in the step (3 s.f. by default for CAIE, 1 d.p. for angles in degrees) or better.
- Do not award marks for answers from a calculator with no working when the step or the question requires working ("show that", "hence", "you must show all your working").

## Implied marks and unreadable figures (all subjects)

- **Implied marks.** When the scheme says a mark "may be implied", or that a correct final answer earns full marks ("calculate" questions; a check saying "a correct final answer earns this mark"), a clearly correct final answer earns the earlier marks even if an earlier line is missing or unreadable. Say in that step's `note` that the mark is implied by the correct answer on page N.
- **Unreadable is not wrong.** When a mark is withheld only because a figure cannot be read (e.g. the last digit of 2000 on page 23), keep `confidence: "low"`, write "unreadable: …" in `note`, and do **not** list it under `mistakes` or tell the reader they made an error there; it is shown as a point to check, not as a mistake.
