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

**BCS lane (branch `feature/boq-bcs`, dev2):** slice **BCS-6b** took main in (CAT-1, CAT-1b, CAT-M, CAT-2: HVAC v89 / v90 /
v91 loaded on dev2; Electrical stays v75; no migrate was needed) and built the slice-6 screens (rules:
`.claude/context/domain/boq-pricing-editor.md` § "The slice-6 screens - BCS-6b"): Electrical Pricing opens on the
Calculator, the Spreadsheet behind the `spreadsheet` switch in `pricingWorkbooks.ts`; the chosen tab no longer carried across
Pricing pages; "Previously priced" shows the past row's BCS supply / install / combined to Admin and Estimates (server-side);
the BoQ summary's ticked sheets as one tinted "Electrical installation block" band with its "Block total" directly under them;
point 4 shown alone carries no "4.". The merge needed one main-file change the final merge must carry:
`services/boq_rate_master/catalogue_prose_allowlist.json` (the G-PROSE baseline re-keyed to Electrical v74 / v75's point-wiring
BCS steps). Before it, **BCS-6a** made every BCS margin work from the amount on screen, and **BCS-5** built the BoQ summary.
Left for the BCS phase: the final fix slice (the full test sets, the final reconciliation with main incl. SRS-1). Open:
point 4 still lists rows whose quantity reads 0 although the uploaded file shows a number (BOQ-26-00012 'HVAC - Low side' row
48 is one; the owner's read-only investigation N9).

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
