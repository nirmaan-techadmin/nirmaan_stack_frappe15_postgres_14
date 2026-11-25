# BoQ status

Where BoQ work stands now. Rewrite this file in place; keep it under 200 lines. What was built goes in
the commit message, not here.

## Active work

The last recorded main-line slice is **DU-3**, the fix slice from the DU-2 review of the Ducting rows. Its
record is the last `## Slice DU-3` section of `boq-upload-plan.md`.

**BCS lane (branch `feature/boq-bcs`, dev2):** slice **BCS-3S** took main in at `f48ed5b77` (upstream
develop v2.11.61 + VAV-FIX, develop's background-operation rework of Suggest / Classify / Match) and built
the BCS switch-on: a complete Suggest run that read a row filed as Electrical turns BCS on for its sheet and
says "BCS is switched on for this sheet." (rules: `.claude/context/domain/boq-pricing-editor.md` § "A
Suggest run switches BCS on"). Left for the BCS phase: slice 4 (a change carries across rate columns),
slice 5 (the BoQ summary), slice 6 ("Previously priced" and the spreadsheet removal), then the final fix
slice (the full test sets).

The session that starts the next slice replaces this section with: the slice's name, what it must
deliver, and what is left.

## Open and owed items

Not yet moved out of the closed record. Find them there with
`grep -n -i -E '^#+ .*(owed|open items|deferred|parked|not built)' frontend/.claude/plans/boq-upload-plan.md`,
and open a GitHub issue for each one that is still open.

## The closed record

`boq-upload-plan.md` holds the design spec and every as-built record up to slice DU-3. It takes no new
text, and `.claude/hooks/guard_claude_md.py` refuses an Edit or Write tool call on it. List its headings with
`grep -n '^#' <file>`, then read one range.
