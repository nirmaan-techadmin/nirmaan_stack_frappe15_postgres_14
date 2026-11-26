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
- **Push:** CAT-1 + CAT-1b go together (owner 2026-11-26 10:37). Origin moved to a develop sync
  (31d29db45) after CAT-1 started, so the push needs a merge + migrate + re-test first, in its own
  slice (owner 2026-11-26 11:01, QR-ORIGIN (a)).
- **Left:** CAT-2 (HVAC code words, the family picker; the next free HVAC version), CAT-3a / CAT-3b
  (Electrical, incl. its 53 placeholders and the Electrical lists), CAT-4 (item notes, the deactivate
  warning, Rate Master screens), the Suggest run store. Candidate for CAT-2: the raw readers (CSV export
  `category_display`, the load validators) filling, so the 15 whole-value texts can become references.

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
