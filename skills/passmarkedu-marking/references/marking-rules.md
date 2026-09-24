# Marking rules for every subject

The step `description` is the official wording; apply it literally. **Every condition in the description must be met** before `present: true` — watch for sentences such as "just stating the values is insufficient", "must be seen in context", "must be in the form …", "cao", "from correct working only", "do not ISW". Example: "A1 both A = 3 and B = −7, seen in context e.g. 3 − 7/(x+2); just stating A and B is insufficient" is A0 when the candidate only wrote A = 3, B = −7. These notes explain the shorthand.

## A marks and correct work (all subjects)

- An accuracy/answer mark is only for correct work: a right-looking value reached through a wrong method or wrong data earns nothing, even if the step lists no prerequisite.
- Over-awarding is the most common AI marking error. When unsure, choose "not earned" with `confidence: "low"` — the user reviews low-confidence steps.

## Drawings (steps marked `"visual": true`)

- Check each feature the description lists (end-points, whiskers, outliers, intercepts, turning points, asymptotes, shape, labels) against the candidate's drawing.
- Use the tolerance in `final_answer.tolerance` (e.g. "within half a small square"); read values off the grid.
- If the drawing is faint, partly cut off or ambiguous, set `confidence: "low"`. These steps are always listed for the user to check.

## Crossed-out and repeated work

- Crossed-out work that is not replaced is still marked (CAIE and Pearson both mark it if nothing else is offered).
- If two different final answers are given without one crossed out, do not award the accuracy mark unless the scheme says otherwise.

## Labels and restarts

- Judge by content, not by the candidate's handwritten part labels: if a label was crossed out and reused, or an answer sits under the wrong label, match the work to the part whose question it answers.

## Numbers

- Accept the required accuracy stated in the step (3 s.f. by default for CAIE, 1 d.p. for angles in degrees) or better.
- Do not award marks for answers from a calculator with no working when the step or the question requires working ("show that", "hence", "you must show all your working").
