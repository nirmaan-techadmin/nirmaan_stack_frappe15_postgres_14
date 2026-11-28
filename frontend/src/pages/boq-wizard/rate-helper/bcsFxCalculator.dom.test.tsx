// @vitest-environment jsdom
//
// BCS-FX K3 -- the Calculator (owner R-BCS-180 ODD-12 / ODD-13, R-BCS-181 W39), on the REAL panel and the REAL helper over the
// newest Electrical rate file (a latest-asset reader by file prefix: rate_master_electrical_all_v):
//   E7 (+) a cost viewer on a category with a cost calculation, fields not filled: the blue section folded, reading
//      "BCS - our cost: fill the fields to see it"; (+) once the fields are filled, the real BCS section, no placeholder;
//      (-) a viewer without cost access: nothing; (-) a category without a cost calculation (costHint false): nothing.
//   E8 (-) "Pricing Inputs" is not offered (a config holding only Pricing Input kinds); (+) it stays in the registry and on the Rate
//      Master page; (+) the Electrical list holds more categories than fit, so the scroll cue shows.
//   W39 (+) the line word for word.
import path from "path";
import { readdirSync } from "fs";
import { pathToFileURL } from "url";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it } from "vitest";

import { RateHelperPanel } from "./RateHelperPanel";
import { BCS_FILL_FIELDS_TEXT } from "./PriceSection";
import { makePricingSheetHelper } from "./pricingSheetHelper";
import { mergeItemsByName } from "./rateHelperPlumbing";
import type { ExtractionRow, RateHelperRowContext } from "./rateHelperTypes";
import type { RateCategoryConfig, RateMasterItem } from "@/pages/pricing/rate-master/rateMasterTypes";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";
import { CALCULATOR_LINE, PICKER_VISIBLE, offeredCount, offeredInCalculator } from "@/pages/pricing/calculatorPicker";
import { RATE_MASTER_DISCIPLINES, calculatorEntry, rateMasterPageEntry } from "@/pages/pricing/rate-master/rateMasterRegistry";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
class StubResizeObserver { observe() { /* no layout */ } unobserve() { /* no layout */ } disconnect() { /* no layout */ } }
if (!(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = StubResizeObserver;
}
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => { /* no layout */ };

type Asset = { discipline: string; items: Array<RateMasterItem & { brand?: string }>; category_configs: RateCategoryConfig[] };
const DATA_DIR = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
const newest = (prefix: string) => readdirSync(DATA_DIR).filter((f) => new RegExp(`^${prefix}\\d+\\.json$`).test(f))
  .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
const ELEC = readJsonFixture<Asset>(pathToFileURL(path.join(DATA_DIR, newest("rate_master_electrical_all_v"))));
const ITEMS: RateMasterItem[] = mergeItemsByName(ELEC.items.map((i) => ({ ...i, discipline: "Electrical" } as RateMasterItem)));
const CONFIGS = new Map<string, RateCategoryConfig>(ELEC.category_configs.map((c) => [c.category_id, { ...c, discipline: "Electrical" }] as [string, RateCategoryConfig]));
const KINDS = ["supply_rate", "install_rate", "combined_rate"];
const CABLE = { material: "COPPER", insulation: "UNARMOURED", core: 2, runs: 1, thickness_sqmm: 1.5, conduit_included: "Yes", conduit_type: "MS", size_mm: 20 };

let root: Root | null = null;
let host: HTMLDivElement | null = null;
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });
function panel(attrs: Record<string, unknown>, showCost: boolean, costHint: boolean) {
  const cells = Object.fromEntries(Object.entries(attrs).map(([k, v]) => [k, { value: v, confidence: 0.9 }]));
  const row = { excelRow: 7, description: "", attributes: cells };
  const helper = makePricingSheetHelper({ configsByCategory: CONFIGS, items: ITEMS, extractionByRow: new Map([[7, row as unknown as ExtractionRow]]) });
  const ctx = { excelRow: 7, description: "", nodeType: "Line Item", category: "wiring_cabling", discipline: "Electrical", rateKinds: KINDS,
    headings: [], ownNotes: [], unit: "Mtr" } as RateHelperRowContext;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(<RateHelperPanel variant="calculator" excelRow={7} col="calculator" kind="supply_rate" ctx={ctx} helpers={[helper]}
    showCost={showCost} costHint={costHint} />));
}
const q = (sel: string) => host!.querySelector(sel);

describe("BCS-FX E7 the Calculator's folded BCS section", () => {
  it("(+) a cost viewer, fields not filled: the folded line 'BCS - our cost: fill the fields to see it'", () => {
    panel({}, true, true);
    expect(q("[data-testid='price-section-bcs-fill-fields']")?.textContent).toBe(BCS_FILL_FIELDS_TEXT);
    expect(BCS_FILL_FIELDS_TEXT).toBe("BCS - our cost: fill the fields to see it");
    expect(q("[data-testid='price-section-bcs']")).toBeNull();
  });
  it("(+) fields filled: the real BCS section, no placeholder", () => {
    panel(CABLE, true, true);
    expect(q("[data-testid='price-section-bcs']")).not.toBeNull();
    expect(q("[data-testid='price-section-bcs-fill-fields']")).toBeNull();
  });
  it("(-) a viewer without cost access, or a category with no cost calculation: nothing", () => {
    panel({}, false, true);
    expect(q("[data-testid^='price-section-bcs']")).toBeNull();
    act(() => root?.unmount()); host?.remove();
    panel({}, true, false);
    expect(q("[data-testid^='price-section-bcs']")).toBeNull();
  });
});

describe("BCS-FX E8 the category picker and W39", () => {
  const elec = RATE_MASTER_DISCIPLINES.find((d) => d.discipline === "Electrical")!;
  const offered = (calculatorEntry(elec)?.categories ?? []).filter((c) => offeredInCalculator(CONFIGS.get(c.category_id)));
  it("(-) Pricing Inputs is not offered; (+) every other Electrical category still is", () => {
    expect(offered.map((c) => c.category_id)).not.toContain("electrical_pricing_inputs");
    expect(offered.length).toBe((calculatorEntry(elec)?.categories ?? []).length - 1);
    expect(offeredInCalculator(undefined)).toBe(true);
  });
  it("(+) Pricing Inputs stays in the registry and on the Rate Master page", () => {
    expect(elec.categories.map((c) => c.category_id)).toContain("electrical_pricing_inputs");
    expect((rateMasterPageEntry(elec)?.categories ?? []).map((c) => c.category_id)).toContain("electrical_pricing_inputs");
  });
  it("(+) the list holds more categories than fit, so the scroll cue shows", () => {
    expect(offered.length).toBeGreaterThan(PICKER_VISIBLE);
    expect(offeredCount(calculatorEntry(elec)?.categories ?? [], CONFIGS)).toBe(offered.length);
  });
  it("(+) W39 word for word", () => {
    expect(CALCULATOR_LINE).toBe("Every field starts blank. No price shows until the needed fields are filled. Nothing here is saved.");
  });
});
