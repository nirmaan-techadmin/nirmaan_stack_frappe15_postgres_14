// BCS-FX K1 (owner R-BCS-182; QR-SRS-BCS (a)) -- the SERVER PRICING STEP's record carries the helper's SUGGESTED BCS supply
// (`rec.bcs_supply`), from the same compute as its BoQ values, on the newest Electrical rate file (latest-asset reader by prefix):
//   (+) a priced Electrical row: rec.bcs_supply = the panel's own figure (`makePricingSheetHelper(...).compute(...).bcs.values.supply_rate`,
//       what RateHelperPanel draws as the suggested BCS supply), and the BoQ values are the panel's values;
//   (-) a row whose fields are not filled: no BCS supply (null), never 0;
//   (-) the signature does not carry it (matching is unchanged by K1).
import path from "path";
import { readdirSync } from "fs";
import { pathToFileURL } from "url";
import { describe, expect, it } from "vitest";
import { priceRowsForMatching } from "./serverPricingStep";
import { makePricingSheetHelper } from "./pricingSheetHelper";
import type { ExtractionRow, RateHelperRowContext, Suggestion } from "./rateHelperTypes";
import type { RateCategoryConfig, RateMasterItem } from "@/pages/pricing/rate-master/rateMasterTypes";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";

type Asset = { discipline: string; items: Array<RateMasterItem & { brand?: string }>; category_configs: RateCategoryConfig[] };
const DATA_DIR = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
const newest = (prefix: string) => readdirSync(DATA_DIR).filter((f) => new RegExp(`^${prefix}\\d+\\.json$`).test(f))
  .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
const ELEC = readJsonFixture<Asset>(pathToFileURL(path.join(DATA_DIR, newest("rate_master_electrical_all_v"))));
const ITEMS = ELEC.items.map((i) => ({ ...i, discipline: "Electrical" } as RateMasterItem));
const CONFIGS: Record<string, RateCategoryConfig> = Object.fromEntries(ELEC.category_configs.map((c) => [c.category_id, { ...c, discipline: "Electrical" }]));
const CABLE = { material: "COPPER", insulation: "UNARMOURED", core: 2, runs: 1, thickness_sqmm: 1.5, conduit_included: "Yes", conduit_type: "MS", size_mm: 20 };
const cells = (a: Record<string, unknown>) => Object.fromEntries(Object.entries(a).map(([k, v]) => [k, { value: v, confidence: 0.9 }]));

function stepRows(rows: Array<{ excel_row: number; attrs: Record<string, unknown> }>) {
  const g = globalThis as unknown as { __pricingStepRecording?: boolean; __pl?: unknown[]; __il?: unknown[] };
  g.__pricingStepRecording = true;
  try {
    return priceRowsForMatching({
      configs: CONFIGS, itemsByDiscipline: { Electrical: ITEMS }, pageRows: {},
      rows: rows.map((r) => ({ boq: "B", sheet_name: "S", excel_row: r.excel_row, category_id: "wiring_cabling", resolved_category: "wiring_cabling",
        discipline: "Electrical", description: "", unit: "Mtr", headings: [], attributes: cells(r.attrs) })),
    } as never).rows as unknown as Array<{ key: string; rec: Record<string, unknown> }>;
  } finally {
    delete g.__pricingStepRecording; delete g.__pl; delete g.__il;
  }
}

function panelFigure(attrs: Record<string, unknown>) {
  const helper = makePricingSheetHelper({ configsByCategory: new Map(Object.entries(CONFIGS)), items: ITEMS,
    extractionByRow: new Map([[7, { excelRow: 7, description: "", attributes: cells(attrs) } as unknown as ExtractionRow]]) });
  const ctx = { excelRow: 7, description: "", nodeType: "Line Item", category: "wiring_cabling", discipline: "Electrical",
    rateKinds: ["supply_rate", "install_rate", "combined_rate"], headings: [], ownNotes: [], unit: "Mtr" } as RateHelperRowContext;
  return helper.compute(ctx, {}) as Suggestion;
}

describe("BCS-FX K1 the server step's suggested BCS supply", () => {
  it("(+) a priced row: rec.bcs_supply = the panel's suggested BCS supply, from the same compute as the BoQ values", () => {
    const [rec] = stepRows([{ excel_row: 7, attrs: CABLE }]).map((r) => r.rec);
    const panel = panelFigure(CABLE);
    expect(typeof panel.bcs?.values.supply_rate).toBe("number");
    expect(rec.bcs_supply).toBe(panel.bcs!.values.supply_rate);
    expect(rec.values).toEqual(panel.values);
  });
  it("(-) fields not filled: no BCS supply (null), never 0; (-) the signature does not carry it", () => {
    const [blank, priced] = stepRows([{ excel_row: 8, attrs: {} }, { excel_row: 7, attrs: CABLE }]).map((r) => r.rec);
    expect(blank.bcs_supply).toBeNull();
    expect(String(priced.signature ?? "")).not.toContain("bcs");
  });
});
