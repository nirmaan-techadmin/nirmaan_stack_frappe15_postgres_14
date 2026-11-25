// @vitest-environment jsdom
//
// BCS-3 -- THE HELPER PANEL AND THE CALCULATOR WITH BOTH SECTIONS, on the REAL panel and the REAL helper over the newest
// Electrical rate file (a latest-asset reader by file prefix: rate_master_electrical_all_v) and the newest HVAC file.
//
// What each case protects (owner R2 "1a", R3, R5, R6):
//   (+) opened from a Supply box: the BoQ section is open and emphasised, the BCS section folded to one line with its figure;
//       the headline and the final value are the BoQ supply.
//   (+) the folded line opens on a tap.
//   (+) opened from the BCS box: the reverse -- BCS open, BoQ folded; headline and final value = the BCS supply; "Use this value"
//       hands the BCS supply up as kind "bcs_supply" (the page writes it through the cost path).
//   (-) a viewer without cost access: no BCS section, no folded line, no BCS figure anywhere in the panel.
//   (-) an HVAC panel: the BoQ section with its tag, nothing else, never foldable.
//   (+/-) the calculator: the BCS section under the BoQ boxes for an allowed viewer, none for another.
import path from "path";
import { readdirSync } from "fs";
import { pathToFileURL } from "url";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RateHelperPanel } from "./RateHelperPanel";
import { SECTION_TAG } from "./PriceSection";
import { bcsExactText, bcsFigureText } from "./bcsSide";
import { makePricingSheetHelper, type ItemListSuggestion } from "./pricingSheetHelper";
import { mergeItemsByName } from "./rateHelperPlumbing";
import type { ExtractionRow, RateHelperRowContext, Suggestion } from "./rateHelperTypes";
import type { RateCategoryConfig, RateMasterItem } from "@/pages/pricing/rate-master/rateMasterTypes";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";

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
const load = (prefix: string) => readJsonFixture<Asset>(pathToFileURL(path.join(DATA_DIR, newest(prefix))));
const ELEC = load("rate_master_electrical_all_v");
const HVAC = load("rate_master_hvac_all_v");
const ITEMS: RateMasterItem[] = mergeItemsByName(
  ELEC.items.map((i) => ({ ...i, discipline: "Electrical" } as RateMasterItem)),
  HVAC.items.map((i) => ({ ...i, discipline: "HVAC" } as RateMasterItem)),
);
const CONFIGS = new Map<string, RateCategoryConfig>([
  ...ELEC.category_configs.map((c) => [c.category_id, { ...c, discipline: "Electrical" }] as [string, RateCategoryConfig]),
  ...HVAC.category_configs.map((c) => [c.category_id, { ...c, discipline: "HVAC" }] as [string, RateCategoryConfig]),
]);
const KINDS = ["supply_rate", "install_rate", "combined_rate"];
const CABLE = { material: "COPPER", insulation: "UNARMOURED", core: 2, runs: 1, thickness_sqmm: 1.5, conduit_included: "Yes", conduit_type: "MS", size_mm: 20 };

let root: Root | null = null;
let host: HTMLDivElement | null = null;
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });

function setup(category: string, attrs: Record<string, unknown>, discipline = "Electrical", items?: unknown[]) {
  const cells = (a: Record<string, unknown>) => Object.fromEntries(Object.entries(a).map(([k, v]) => [k, { value: v, confidence: 0.9 }]));
  const row = items ? { excelRow: 7, description: "", attributes: {}, items: items.map((a) => ({ attributes: cells(a as Record<string, unknown>) })) }
    : { excelRow: 7, description: "", attributes: cells(attrs) };
  const helper = makePricingSheetHelper({ configsByCategory: CONFIGS, items: ITEMS, extractionByRow: new Map([[7, row as unknown as ExtractionRow]]) });
  const ctx = { excelRow: 7, description: "", nodeType: "Line Item", category, discipline, rateKinds: KINDS, headings: [], ownNotes: [], unit: "Mtr" } as RateHelperRowContext;
  return { helper, ctx, result: helper.compute(ctx, {}) as Suggestion };
}

function mount(node: JSX.Element, open = true) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(node));
  if (open) {
    const header = [...host.querySelectorAll("button")].find((b) => !b.getAttribute("aria-label") && b.querySelector(".text-sm.font-medium"));
    act(() => header!.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  }
  return host;
}
const q = (sel: string) => host!.querySelector(sel);
const finalBox = () => (q("input[aria-label='Final value']") as HTMLInputElement).value;
const click = (el: Element | null) => act(() => el!.dispatchEvent(new MouseEvent("click", { bubbles: true })));

describe("BCS-3 the helper panel: both sections, the clicked column's open", () => {
  it("(+) from the Supply box: BoQ open and emphasised, BCS folded to one line with its figure; headline / final value = BoQ", () => {
    const { helper, ctx, result } = setup("wiring_cabling", CABLE);
    mount(<RateHelperPanel variant="embedded" excelRow={7} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} showCost />);
    expect(q("[data-testid='price-section-boq']")?.getAttribute("data-emphasised")).toBe("1");
    expect(q("[data-testid='price-section-boq']")?.textContent).toContain(SECTION_TAG.boq);
    const folded = q("[data-testid='price-section-bcs-folded']");
    expect(folded?.textContent).toContain(SECTION_TAG.bcs);
    // MOVED at BCS-W (owner R5 "1a"; Question 2 answer 1a, 2026-11-25): a BCS figure prints in whole rupees, rounded up. BEFORE:
    // toContain(String(result.bcs!.values.supply_rate))
    expect(folded?.textContent).toContain(bcsFigureText(result.bcs!.values.supply_rate!));
    expect(q("[data-testid='price-section-bcs']")).toBeNull();
    expect(finalBox()).toBe(String(result.values.supply_rate));
  });
  it("(+) the folded line opens on a tap", () => {
    const { helper, ctx } = setup("wiring_cabling", CABLE);
    mount(<RateHelperPanel variant="embedded" excelRow={7} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} showCost />);
    click(q("[data-testid='price-section-bcs-folded']"));
    expect(q("[data-testid='price-section-bcs']")?.getAttribute("data-emphasised")).toBe("0");
    expect(q("[data-testid='price-section-bcs']")?.textContent).toContain("BCS conduit supply");
  });
  it("(+) from the BCS box: BCS open, BoQ folded; final value = BCS supply; Use hands it up as bcs_supply", () => {
    const { helper, ctx, result } = setup("wiring_cabling", CABLE);
    const onUse = vi.fn();
    mount(<RateHelperPanel variant="embedded" excelRow={7} col="BCS" kind="supply_rate" target="bcs" ctx={ctx} helpers={[helper]} onUse={onUse} showCost />);
    expect(q("[data-testid='price-section-bcs']")?.getAttribute("data-emphasised")).toBe("1");
    expect(q("[data-testid='price-section-boq-folded']")?.textContent).toContain(String(result.values.supply_rate));
    // MOVED at BCS-W (Question 2 answer 1a): the box shows the exact cost it will write, to the paisa. BEFORE: toBe(String(result.bcs!.values.supply_rate))
    expect(finalBox()).toBe(bcsExactText(result.bcs!.values.supply_rate!));
    click([...host!.querySelectorAll("button")].find((b) => b.textContent === "Use this value")!);
    expect(onUse).toHaveBeenCalledTimes(1);
    expect(onUse.mock.calls[0][0]).toBe("BCS");
    expect(onUse.mock.calls[0][1]).toBe(result.bcs!.values.supply_rate);
    expect(onUse.mock.calls[0][2].kind).toBe("bcs_supply");
  });
  it("(-) a viewer without cost access: no BCS section, no folded line, no BCS figure anywhere", () => {
    const { helper, ctx } = setup("wiring_cabling", CABLE);
    mount(<RateHelperPanel variant="embedded" excelRow={7} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} />);
    expect(q("[data-testid='price-section-bcs']")).toBeNull();
    expect(q("[data-testid='price-section-bcs-folded']")).toBeNull();
    expect(host!.textContent).not.toContain("BCS");
    expect(q("[data-testid='price-section-boq']")?.textContent).toContain(SECTION_TAG.boq);
  });
  it("(-) an HVAC panel: the BoQ section with its tag only, never foldable, no BCS anywhere", () => {
    const box = { vav_item: "VAV box", shape: "Rectangular", vav_type: "Nothing specific mentioned", integrator_included: "No", airflow_cfm: "700", scope: "Supply only" };
    const { helper, ctx, result } = setup("hvac_vav_box", {}, "HVAC", [box]);
    expect((result as unknown as ItemListSuggestion).bcs).toBeUndefined();
    mount(<RateHelperPanel variant="embedded" excelRow={7} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} showCost />);
    expect(q("[data-testid='price-section-boq']")?.textContent).toContain(SECTION_TAG.boq);
    expect(q("[data-testid='price-section-boq'] [aria-label^='Fold']")).toBeNull();
    expect(q("[data-testid^='price-section-bcs']")).toBeNull();
    expect(host!.textContent).not.toContain(SECTION_TAG.bcs);
  });
});

describe("BCS-3 owner answer 2 'b': an HVAC Cables row (an alias of Electrical wiring) is unchanged but for the tag", () => {
  it("(-) no conduit line and no BCS section, even for a viewer who may see cost; the BoQ tag is there", () => {
    const { helper, ctx } = setup("hvac_cables", CABLE, "HVAC");
    mount(<RateHelperPanel variant="embedded" excelRow={7} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} showCost />);
    expect(q("[data-testid='price-section-boq']")?.textContent).toContain(SECTION_TAG.boq);
    expect(q("[data-testid^='price-section-bcs']")).toBeNull();
    expect(host!.textContent).not.toMatch(/Conduit supply/);
  });
});

describe("BCS-3 the calculator: the BCS section under the BoQ boxes, Admin and Estimates only", () => {
  it("(+) an allowed viewer: both sections open, the BCS figure row shows the supply only", () => {
    const { helper, ctx, result } = setup("wiring_cabling", CABLE);
    mount(<RateHelperPanel variant="calculator" excelRow={7} col="calculator" kind="supply_rate" ctx={ctx} helpers={[helper]} showCost />, false);
    const bcs = q("[data-testid='price-section-bcs']");
    expect(q("[data-testid='price-section-boq']")).not.toBeNull();
    // MOVED at BCS-W (Question 2 answer 1a): whole rupees, rounded up. BEFORE: toContain(String(result.bcs!.values.supply_rate))
    expect(bcs?.textContent).toContain(bcsFigureText(result.bcs!.values.supply_rate!));
    const labels = [...bcs!.querySelectorAll("span")].map((x) => x.textContent);
    expect(labels).toContain("Supply");
    expect(labels).not.toContain("Install");
    expect(labels).not.toContain("Combined");
    expect(q("[data-testid$='-folded']")).toBeNull();
  });
  it("(-) a viewer without cost access: no BCS section", () => {
    const { helper, ctx } = setup("wiring_cabling", CABLE);
    mount(<RateHelperPanel variant="calculator" excelRow={7} col="calculator" kind="supply_rate" ctx={ctx} helpers={[helper]} />, false);
    expect(q("[data-testid^='price-section-bcs']")).toBeNull();
    expect(q("[data-testid='price-section-boq']")).not.toBeNull();
  });
});
