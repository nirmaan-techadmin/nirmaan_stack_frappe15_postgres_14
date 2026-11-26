# BoQ status

Where BoQ work stands now. Rewrite this file in place; keep it under 200 lines. What was built goes in
the commit message, not here.

## Active work

The last recorded main-line slice is **DU-3**, the fix slice from the DU-2 review of the Ducting rows. Its
record is the last `## Slice DU-3` section of `boq-upload-plan.md`.

**BCS lane (branch `feature/boq-bcs`, dev2):** slice **BCS-6a** made every BCS margin (the sheet's % Margin column, its
Summary panel, the BoQ summary) work from the amount on screen: the BOQ Total choice found by its real column, the Summary's
amount fallback, one-sided rows counted (and shown in their Amount (Total) cell), the calculated amount as the default where the
file's amount differs, no-rate rows without an amount left out, only priceable rows counted; plus the note "How the BoQ amount
was taken on this sheet" and the BoQ summary's exception lines (rules: `.claude/context/domain/boq-pricing-editor.md` § "Every
margin from the amount on screen"). It did NOT take main in: main's ten commits past `31d29db45` (HVAC v89 / v90 rate files,
rate-master guards) wait for the next BCS slice, whose merge meets a `boq-status.md` conflict. Before it, slice **BCS-5** built the BoQ
summary: for Admin and Estimates, a foldable box at the top of a BoQ's main page with one line per priceable sheet
(BoQ amount, BCS supply, BCS installation, margin), the ticked sheets as one clubbed block with one installation
figure (area x the live Rs per sq ft + floor cutting at our cost, both parts editable / removable), stored per BoQ
in the new `BoQ Summary Inputs` and carried to a revision; plus one line on a ticked sheet's own Summary (rules:
`.claude/context/domain/boq-pricing-editor.md` § "The BoQ summary on the BoQ's main page"). Left for the BCS phase:
slice 6b ("Previously priced" with BCS, the BoQ summary's band layout, the Electrical Spreadsheet removal), then the final fix
slice (the full test sets). Open owner point from BCS-6a: whether the calculated-amount default should apply only where a rate
was entered in the app (on badly read files with no quantity it shows 0 or far-off amounts until the user picks "Keep document").

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
