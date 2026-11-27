# BoQ status

Where BoQ work stands now. Rewrite this file in place; keep it under 200 lines. What was built goes in
the commit message, not here.

## Active work

**The catalogue-link fix (CAT).** The catalogue decides every list the screens and the AI offer, and
nothing types a catalogue name. The rules are in `.claude/context/domain/boq-rate-master.md` §
Load-bearing invariants, "THE CATALOGUE DECIDES ...".

- **CAT-1 (HVAC v89), built:** the lists rebuilt from the catalogue and merged at both read points; the
  `{{cat:}}` / `{{item:}}` fill; the load gate; the guards (C1, G-PROSE, prompt words, spec_reader, G2);
  On-Off declared; the VAV share parts by item id; the four ruled rules-page lines (ADP x3, Piping x1).
- **CAT-1b (HVAC v90), built:** the HVAC wording converted to placeholders (494 in 228 texts; 15
  whole-value texts and the mixed-case mentions kept as words); the TypeScript fill for the rate-file
  test readers, pinned to the Python fill by a parity test; the replay dump reads the served configs; C1
  in the commit hook. Nothing a pricer sees changes except the four rules-page lines.
- **CAT-M (the merge), built:** origin's develop sync 31d29db45 is merged over CAT-1 + CAT-1b as one
  merge commit (no conflict; our commits keep their hashes), and main dev is migrated for it. The re-test
  set, the replay (0 figure / 0 wording moves) and the 21 AI requests are unchanged on the merged code.
- **Pushed:** CAT-1 + CAT-1b + the merge (owner, 2026-11-26 20:35).
- **CAT-2 (HVAC v91), built, awaiting review (not pushed):** the HVAC values code rules picked from
  typed constants (the Valve Package review-net families, the VRF frame / controller families, the GI
  framework cladding, CPVC / PVC) are `list_spec.code_targets` roles the load gate checks; the code
  reads the roles and the constants are deleted (C1 115 -> 95 entries); the rules page's Paint reads
  `paint_row.family`; the "Change to..." picker offers only families an SKU carries. Nothing a pricer
  sees changes (replay 0 / 0, 21 AI requests byte-identical). The owner pushes after the review.
- **Left:** CAT-3a / CAT-3b (Electrical, incl. its 53 placeholders, the Electrical lists, the labels;
  and the four Electrical rules-page words CAT-2 left: ARMOURED / UNARMOURED, Switch, Bus bar), CAT-4
  (item notes, the deactivate warning, Rate Master screens), the Suggest run store. Still a candidate:
  the raw readers (CSV export `category_display`, the load validators) filling, so the 15 whole-value
  texts can become references.

Before CAT: **DU-3**, the fix slice from the DU-2 review of the Ducting rows (the last `## Slice DU-3`
section of `boq-upload-plan.md`).

The last recorded main-line slice is **DU-3**, the fix slice from the DU-2 review of the Ducting rows. Its
record is the last `## Slice DU-3` section of `boq-upload-plan.md`.

**BCS lane (branch `feature/boq-bcs`, dev2):** slice **BCS-6a** made every BCS margin (the sheet's % Margin column, its
Summary panel, the BoQ summary) work from the amount on screen: the BOQ Total choice found by its real column, the Summary's
amount fallback, one-sided rows counted (and shown in their Amount (Total) cell), the calculated amount as the default where the
file's amount differs, no-rate rows without an amount left out, only priceable rows counted; plus the note "How the BoQ amount
was taken on this sheet" and the BoQ summary's exception lines, and the note's point 4 - rows whose rates appear incorrect,
shown on every sheet's Summary to every viewer (rules: `.claude/context/domain/boq-pricing-editor.md` § "Every margin from the
amount on screen"). It did NOT take main in: main's ten commits past `31d29db45` (HVAC v89 / v90 rate files,
rate-master guards) wait for the next BCS slice, whose merge meets a `boq-status.md` conflict. Before it, slice **BCS-5** built the BoQ
summary: for Admin and Estimates, a foldable box at the top of a BoQ's main page with one line per priceable sheet
(BoQ amount, BCS supply, BCS installation, margin), the ticked sheets as one clubbed block with one installation
figure (area x the live Rs per sq ft + floor cutting at our cost, both parts editable / removable), stored per BoQ
in the new `BoQ Summary Inputs` and carried to a revision; plus one line on a ticked sheet's own Summary (rules:
`.claude/context/domain/boq-pricing-editor.md` § "The BoQ summary on the BoQ's main page"). Left for the BCS phase:
slice 6b ("Previously priced" with BCS, the BoQ summary's band layout, the Electrical Spreadsheet removal), then the final fix
slice (the full test sets). Open from BCS-6a: point 4 still lists rows whose quantity reads 0 although the uploaded file shows
a number (BOQ-26-00012 'HVAC - Low side' row 48 is one); why the quantity is lost is the owner's read-only investigation N9.

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
