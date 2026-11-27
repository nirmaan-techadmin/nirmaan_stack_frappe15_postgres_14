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
  (item notes, the deactivate warning, Rate Master screens). Still a candidate:
  the raw readers (CSV export `category_display`, the load validators) filling, so the 15 whole-value
  texts can become references.

**The Suggest run store (SRS).** Every AI Suggest pass keeps, per row it reads, what was sent, what came
back and the final values; Admin only; purged after a year. The rules are in
`.claude/context/domain/boq-rate-master.md` § Load-bearing invariants, "EVERY ROW AN AI SUGGEST PASS READS
IS KEPT ...", and § The Suggest run store.

- **SRS-D0, the design:** accepted 2026-11-27 (three slices).
- **SRS-1 (store + write + purge), built, awaiting review (not pushed):** three DocTypes (Question, Run
  Record, Row Record) with the Admin-only hooks; the write from the one runner (carried rows untouched,
  never fails a run); the daily one-year purge. Main dev is migrated for it. One paid test pass (3 rows)
  matched the capture log byte for byte. Nothing a pricer sees changes. Abhishek is told of the hooks.py
  lines and the new DocTypes before the pull request.
- **Left:** SRS-2 (the suggested rates, through the server pricing step; `rates_status` is the only truth
  for "priced"), SRS-3 (the "AI Suggest Records" page and the Excel downloads).

Before CAT: **DU-3**, the fix slice from the DU-2 review of the Ducting rows (the last `## Slice DU-3`
section of `boq-upload-plan.md`).

## Open and owed items

Not yet moved out of the closed record. Find them there with
`grep -n -i -E '^#+ .*(owed|open items|deferred|parked|not built)' frontend/.claude/plans/boq-upload-plan.md`,
and open a GitHub issue for each one that is still open.

## The closed record

`boq-upload-plan.md` holds the design spec and every as-built record up to slice DU-3. It takes no new
text, and `.claude/hooks/guard_claude_md.py` refuses an Edit or Write tool call on it. List its headings with
`grep -n '^#' <file>`, then read one range.
