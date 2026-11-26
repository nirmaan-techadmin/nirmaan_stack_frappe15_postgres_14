# BoQ status

Where BoQ work stands now. Rewrite this file in place; keep it under 200 lines. What was built goes in
the commit message, not here.

## Active work

The last recorded main-line slice is **DU-3**, the fix slice from the DU-2 review of the Ducting rows. Its
record is the last `## Slice DU-3` section of `boq-upload-plan.md`.

**BCS lane (branch `feature/boq-bcs`, dev2):** slice **BCS-4** took main in at `c4a3d5fa1` (VAV-MT's parallel
plan) and built the carry: a field changed in any view of a row's rate helper (Supply, Install, Combined or the
BCS supply box) is saved for the row (`BoQ Row Helper Edit`) and shows in the row's other views, tagged
"changed by you" / "from ... helper" below the field; only suggestions change; a fresh Suggest run replaces the
edits of the rows it writes (owner R-BCS-140, superseding R-BCS-45) (rules:
`.claude/context/domain/boq-pricing-editor.md` § "A change carries to the row's other helpers"). Left for the
BCS phase: slice 5 (the BoQ summary), slice 6 ("Previously priced" and the spreadsheet removal), then the
final fix slice (the full test sets).

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
