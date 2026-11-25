// BCS-4 (design BCS-D0 P3c, the guarantees) -- A CURRENT SAVED EDIT OUTRANKS THE EXTRACTION IT IS COMPUTED OVER, through the
// compute's existing override precedence (no new pricing path). PURE: the REAL helper over the newest Electrical rate file (a
// latest-asset reader by file prefix: rate_master_electrical_all_v), the rate file's own golden DB row.
//
// READ UNDER OWNER R-BCS-140 (2026-11-26, replacing R-BCS-45): a fresh Suggest run REPLACES the saved edits of the rows it
// writes, server-side (helper_edits.supersede_edits_for_rows -- pinned by test_helper_edits.TestSuggestRunReplacesHelperEdits),
// so after a run such a row has NO current edit and shows the run's own output. What this file pins is the client half: while
// an edit IS current (made after the run, or on a row the run did not write), it wins over whatever extraction the page holds
// -- including a newer one -- because the seed rides the override map the compute already prefers.
//
// What each case protects:
//   (+) the seeded override wins over the extraction: the figures equal the helper's figures for the edited value and differ
//       from the extraction's own.
//   (+) the same seed wins over a NEW extraction that reads the field differently.
//   (-) no current edit (the run replaced it): the figures are the extraction's own.
//   (+/-) the page's overlay (helperEditsForRow): a change made this session lays over the read, a cleared row drops the
//       read, a cleared field drops its key, and a row with nothing reads `undefined` -- the read's own object when nothing
//       is laid over it (the panel's seed memo keeps its reference).
import path from "path";
import { readdirSync } from "fs";
import { pathToFileURL } from "url";
import { describe, expect, it } from "vitest";

import { seededOverrides, type SavedHelperEdits } from "./RateHelperPanel";
import { makePricingSheetHelper, PRICING_SHEET_HELPER_ID } from "./pricingSheetHelper";
import { mergeItemsByName } from "./rateHelperPlumbing";
import type { ExtractionRow, RateHelperRowContext, Suggestion } from "./rateHelperTypes";
import type { RateCategoryConfig, RateMasterItem } from "@/pages/pricing/rate-master/rateMasterTypes";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";
import { helperEditsForRow } from "../SheetPricingPage";

type Asset = { discipline: string; items: RateMasterItem[]; category_configs: RateCategoryConfig[] };
const DATA_DIR = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
const newest = readdirSync(DATA_DIR).filter((f) => /^rate_master_electrical_all_v\d+\.json$/.test(f))
  .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
const ELEC = readJsonFixture<Asset>(pathToFileURL(path.join(DATA_DIR, newest)));
const ITEMS: RateMasterItem[] = mergeItemsByName(ELEC.items.map((i) => ({ ...i, discipline: "Electrical" } as RateMasterItem)), []);
const CONFIGS = new Map<string, RateCategoryConfig>(ELEC.category_configs.map((c) => [c.category_id, { ...c, discipline: "Electrical" }]));
const DB = "db_switchgear";
const GOLDEN = (CONFIGS.get(DB) as unknown as { goldens: Array<{ id: string; attrs: Record<string, unknown> }> }).goldens.find((g) => g.id === "dbu1")!.attrs;
const KINDS = ["supply_rate", "install_rate", "combined_rate"];
const ROW = 12;
const D_CURVE = String(GOLDEN.mcb1_item); // what the golden row reads
const C_CURVE = "63A DP MCB C CURVE"; // another MCB (2,316 against the golden's 4,010): a price-visible change

function helperOver(attrs: Record<string, unknown>) {
  const cells = Object.fromEntries(Object.entries(attrs).map(([k, v]) => [k, { value: v, confidence: 0.9 }]));
  const row = { excelRow: ROW, description: "", attributes: cells } as unknown as ExtractionRow;
  return makePricingSheetHelper({ configsByCategory: CONFIGS, items: ITEMS, extractionByRow: new Map([[ROW, row]]) });
}
const ctx = { excelRow: ROW, description: "", nodeType: "Line Item", category: DB, discipline: "Electrical", rateKinds: KINDS, headings: [], ownNotes: [], unit: "Nos" } as RateHelperRowContext;
const figures = (r: unknown) => (r as Suggestion).values;

describe("BCS-4 a current saved edit outranks the extraction (the compute's own override precedence)", () => {
  const saved: SavedHelperEdits = { mcb1_item: { value: C_CURVE, from_kind: "supply" } };
  const seed = seededOverrides(saved)[PRICING_SHEET_HELPER_ID];

  it("(+) the seed beats the extraction: the figures are the edited value's, not the extraction's", () => {
    const helper = helperOver(GOLDEN);
    const edited = figures(helper.compute(ctx, seed));
    const ownC = figures(helperOver({ ...GOLDEN, mcb1_item: C_CURVE }).compute(ctx, {}));
    const ownD = figures(helper.compute(ctx, {}));
    expect(edited.supply_rate).toBe(ownC.supply_rate);
    expect(edited.install_rate).toBe(ownC.install_rate);
    expect(edited.supply_rate).not.toBe(ownD.supply_rate);
  });

  it("(+) the same seed beats a NEW extraction that reads the field differently", () => {
    const newer = helperOver({ ...GOLDEN, mcb1_item: "63A SP MCB D CURVE" });
    const edited = figures(newer.compute(ctx, seed));
    const ownC = figures(helperOver({ ...GOLDEN, mcb1_item: C_CURVE }).compute(ctx, {}));
    expect(edited.supply_rate).toBe(ownC.supply_rate);
    expect(figures(newer.compute(ctx, {})).supply_rate).not.toBe(ownC.supply_rate);
  });

  it("(-) no current edit (a run replaced it, R-BCS-140): nothing is seeded and the figures are the extraction's own", () => {
    const helper = helperOver(GOLDEN);
    expect(seededOverrides(undefined)).toEqual({});
    expect(seededOverrides({})).toEqual({});
    expect(figures(helper.compute(ctx, seededOverrides(undefined)[PRICING_SHEET_HELPER_ID])).supply_rate)
      .toBe(figures(helper.compute(ctx, {})).supply_rate);
    expect(D_CURVE).not.toBe(C_CURVE);
  });
});

describe("BCS-4 the page's overlay over the one read (helperEditsForRow)", () => {
  const read: Record<string, SavedHelperEdits> = { "12": { curve: { value: "D", from_kind: "supply" } } };

  it("(+) nothing laid over: the read's own object; a row with nothing: undefined", () => {
    expect(helperEditsForRow(read, {}, 12)).toBe(read["12"]);
    expect(helperEditsForRow(read, {}, 13)).toBeUndefined();
    expect(helperEditsForRow(undefined, {}, 12)).toBeUndefined();
  });

  it("(+) a change made this session lays over the read; (-) a cleared field drops its key, a cleared row drops the read", () => {
    expect(helperEditsForRow(read, { 12: { fields: { poles: { value: "TP", from_kind: "install" } } } }, 12))
      .toEqual({ curve: { value: "D", from_kind: "supply" }, poles: { value: "TP", from_kind: "install" } });
    expect(helperEditsForRow(read, { 12: { fields: { curve: null } } }, 12)).toBeUndefined();
    expect(helperEditsForRow(read, { 12: { cleared: true, fields: {} } }, 12)).toBeUndefined();
    expect(helperEditsForRow(read, { 12: { cleared: true, fields: { poles: { value: "TP", from_kind: "bcs_supply" } } } }, 12))
      .toEqual({ poles: { value: "TP", from_kind: "bcs_supply" } });
  });
});
