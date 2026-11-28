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
- **CAT-2 (HVAC v91), pushed (on origin since 2026-11-27):** the HVAC values code rules picked from
  typed constants (the Valve Package review-net families, the VRF frame / controller families, the GI
  framework cladding, CPVC / PVC) are `list_spec.code_targets` roles the load gate checks; the code
  reads the roles and the constants are deleted (C1 115 -> 95 entries); the rules page's Paint reads
  `paint_row.family`; the "Change to..." picker offers only families an SKU carries. Nothing a pricer
  sees changes (replay 0 / 0, 21 AI requests byte-identical).
- **Left:** CAT-3a / CAT-3b (Electrical, incl. its 53 placeholders, the Electrical lists, the labels;
  and the four Electrical rules-page words CAT-2 left: ARMOURED / UNARMOURED, Switch, Bus bar), CAT-4
  (item notes, the deactivate warning, Rate Master screens). Still a candidate:
  the raw readers (CSV export `category_display`, the load validators) filling, so the 15 whole-value
  texts can become references.

**The Suggest run store (SRS).** Every AI Suggest pass keeps, per row it reads, what was sent, what came
back and the final values; Admin only; purged after a year. The rules are in
`.claude/context/domain/boq-rate-master.md` § Load-bearing invariants, "EVERY ROW AN AI SUGGEST PASS READS
IS KEPT ...", and § The Suggest run store.

- **SRS-D0, the design:** accepted 2026-11-27 (the page and the rates later combined into one SRS-2).
- **SRS-1 (store + write + purge), pushed (owner, 2026-11-27 17:15):** three DocTypes (Question, Run
  Record, Row Record) with the Admin-only hooks; the write from the one runner (carried rows untouched,
  never fails a run); the daily one-year purge. Abhishek is told of the hooks.py lines and the new DocTypes
  before the pull request.
- **SRS-2 (the rates + the page + the downloads), built, awaiting review (not pushed):** after every
  Suggest pass that wrote rows, a follow-up job prices them through the server pricing step (the panel's
  own code) and writes priced / not priced / rates not computed; the Admin-only "AI Suggest Records" page
  under Rate Master (filters, a 50-a-page list, the row detail) and its Summary / Full Excel downloads. No
  migrate, no DocType change. The pricing-step bundle must be built on a dev bench by hand (`node
  scripts/build_pricing_step.mjs` from `frontend/`). Nothing on the pricing page changes. Abhishek is told
  of the new page and route, the sidebar line, the rates job and the bundle before the pull request.
- **The BCS supply figure:** filled on `feature/boq-bcs` by BCS-FX (the rates job stores the suggested BCS supply from
  the same server-step call; old records read "not recorded (run before BCS)"); it reaches main with the BCS merge.
- **Left:** a store for historical matching (later, separate).

Before CAT: **DU-3**, the fix slice from the DU-2 review of the Ducting rows (the last `## Slice DU-3`
section of `boq-upload-plan.md`).

**BCS lane (branch `feature/boq-bcs`, dev2):** slice **BCS-FX**, the lane's final fix slice, took main in (SRS-1 + SRS-2;
dev2 migrated for SRS-1's three DocTypes; no rate file; Electrical v75, HVAC v91) and fixed the index manifest's miss of the
BCS-4 / BCS-5 indexes (`services/index_manifest.py`: the next migrate builds `BoQ_Row_Helper_Edit_boq_idx`). Built (rules:
`.claude/context/domain/boq-pricing-editor.md` § "The final fix slice - BCS-FX"; the store: `boq-rate-master.md` § The Suggest
run store): the AI Suggest Records' suggested BCS supply at the run; note point 5 (BoQ supply but no BCS supply) with the
margins' "*"; a cleared BCS cost box saved as "not entered" (every box cleared = the row's cost removed, kept in history); the
BCS-RV1 row-review display fixes (Indian numbers, the "BoQ amount" column, "RO" quantities, the merged block cell, "On summary",
the Calculator's folded BCS line, Pricing Inputs out of its picker) and six wordings. Next: the BCS merge into main and the
deploy (pre-pack, runbook). Open: a per-box blank beside a filled box needs a schema change (owner's call); the Admin reprice
of an old Suggest record fills its BCS supply (owner to confirm); a typed 0 beside a box the user then clears goes with it
(decided while the owner was away; owner to confirm); point 4's quantity-0 rows such as BOQ-26-00012 row 48 (N9).

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
