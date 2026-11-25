// @vitest-environment jsdom
//
// BCS-W -- THE HELPER PANEL AND THE CALCULATOR, ELECTRICAL: how BCS figures print, the exact write, the scope line, the
// installation line once, the pop-up default words. The REAL panel and the REAL helper over the newest Electrical rate file
// (a latest-asset reader by file prefix: rate_master_electrical_all_v) and the newest HVAC file.
//
// What each case protects (owner R5 21:54 / 21:56 "1a"; R6 20:09 "ok"; Question 1 answer 4a; the approved mockup boards 3 / 4):
//   (+) every BCS figure on screen is whole rupees, ROUNDED UP, thousands separated: the industrial socket's 1,568 + 441.6 =
//       2,009.6 shows "1,568", "442" and "2,010" -- the folded line, the headline, the block's lines and its figures row;
//   (+) "Use this value" from the BCS box writes 2009.6 EXACTLY, and the box beside it shows the exact 2,009.60;
//   (+) opened from the BCS box the scope line reads "Row <n> · BCS supply cost"; from the Supply box "Supply rate" as before;
//   (+) the installation line shows ONCE, below the sections, on a two-block panel (the cable) and in the calculator;
//   (-) BoQ figures print as before (2,925 stays "2925" in the headline, the BoQ lines as the helper writes them) -- MOVED BY BCS-W2
//       (owner R2 "2. yes"): a BoQ figure now prints thousands separated, "2,925" (bcsw2Separators.dom.test.tsx); the box and the
//       written value stay "2925";
//   (+/-) the pop-up "never asked" default reads "Plate qty = 1 (not read from the BoQ; the usual default)" on an Electrical
//       row; any other discipline keeps the old words (unit-level, the line's own function).
import path from "path";
import { readdirSync } from "fs";
import { pathToFileURL } from "url";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RateHelperPanel } from "./RateHelperPanel";
import { BCS_INSTALL_NOTE, bcsExactText, bcsFigureText, bcsLine, parseBcsValue } from "./bcsSide";
import { NEVER_ASKED_LEAD, makePricingSheetHelper, neverAskedDisplay } from "./pricingSheetHelper";
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
// the cert row's own answers (BOQ-26-00217 "ELE-2F" row 73, BCS-S1 W3a): socket 1,568 + paired MCB 441.6 = 2,009.6
const SOCKET = { item: "Plug + Socket in Enclosure Box", enclosure: "IP44/54 - Splash Proof", rating: "16/20A", pole: "3 Pin / 2P+E", paired_mcb: "25A DP MCB C CURVE", mcb_present: "Yes" };
const CABLE = { material: "COPPER", insulation: "UNARMOURED", core: 2, runs: 1, thickness_sqmm: 1.5, conduit_included: "Yes", conduit_type: "MS", size_mm: 20 };

let root: Root | null = null;
let host: HTMLDivElement | null = null;
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });

function setup(category: string, attrs: Record<string, unknown>) {
  const cells = Object.fromEntries(Object.entries(attrs).map(([k, v]) => [k, { value: v, confidence: 0.9 }]));
  const helper = makePricingSheetHelper({ configsByCategory: CONFIGS, items: ITEMS, extractionByRow: new Map([[73, { excelRow: 73, description: "", attributes: cells } as unknown as ExtractionRow]]) });
  const ctx = { excelRow: 73, description: "", nodeType: "Line Item", category, discipline: "Electrical", rateKinds: KINDS, headings: [], ownNotes: [], unit: "Nos" } as RateHelperRowContext;
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
const qa = (sel: string) => [...host!.querySelectorAll(sel)];
const click = (el: Element | null) => act(() => el!.dispatchEvent(new MouseEvent("click", { bubbles: true })));
const finalBox = () => (q("input[aria-label='Final value']") as HTMLInputElement).value;

describe("BCS-W the figure formats", () => {
  it("(+) whole rupees, rounded up, thousands separated; held to the paisa first", () => {
    expect(bcsFigureText(2009.6)).toBe("2,010");
    expect(bcsFigureText(441.6)).toBe("442");
    expect(bcsFigureText(6090.6)).toBe("6,091");
    expect(bcsFigureText(1568)).toBe("1,568");
    expect(bcsFigureText(1568.0000000002)).toBe("1,568");
    expect(bcsExactText(2009.6)).toBe("2,009.60");
    expect(parseBcsValue("2,009.60")).toBe(2009.6);
    expect(bcsLine("Paired MCB: Switchgear 25A DP MCB C CURVE x 1 = 441.6")).toBe("Paired MCB: Switchgear 25A DP MCB C CURVE x 1 = 442");
    expect(bcsLine("Industrial socket discount = 30%")).toBe("Industrial socket discount = 30%");
    expect(bcsLine("Cable + conduit = 125.3, rounded up to the rupee")).toBe("Cable + conduit = 126, rounded up to the rupee");
  });
});

describe("BCS-W the helper panel, Electrical", () => {
  it("(+) from the Supply box: the folded BCS line shows 2,010; the BoQ box is unchanged; scope line 'Supply rate'", () => {
    const { helper, ctx, result } = setup("industrial_sockets", SOCKET);
    expect(result.bcs!.values.supply_rate).toBeCloseTo(2009.6, 9);
    mount(<RateHelperPanel variant="embedded" excelRow={73} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} showCost />);
    expect(q("[data-testid='price-section-bcs-folded']")?.textContent).toContain("2,010");
    expect(host!.textContent).toContain("Row 73 · Supply rate");
    expect(finalBox()).toBe(String(result.values.supply_rate)); // (-) BoQ: as before
    click(q("[data-testid='price-section-bcs-folded']"));
    const bcs = q("[data-testid='price-section-bcs']")!.textContent!;
    expect(bcs).toContain("= 1,568");
    expect(bcs).toContain("= 442");
    expect(bcs).toContain("BCS supply = 2,010");
    expect(bcs).not.toContain("441.6");
    expect(bcs).not.toContain("2009.6");
    expect(bcs).not.toContain(BCS_INSTALL_NOTE);                // not inside the block any more
    expect(qa("[data-testid='bcs-install-note']").length).toBe(1); // once, below the sections
    expect(host!.textContent!.split(BCS_INSTALL_NOTE).length - 1).toBe(1);
  });
  it("(+) from the BCS box: scope line 'BCS supply cost', headline 2,010, the box shows 2,009.60 and Use writes 2009.6 exactly", () => {
    const { helper, ctx, result } = setup("industrial_sockets", SOCKET);
    const onUse = vi.fn();
    mount(<RateHelperPanel variant="embedded" excelRow={73} col="BCS" kind="supply_rate" target="bcs" ctx={ctx} helpers={[helper]} onUse={onUse} showCost />);
    expect(host!.textContent).toContain("Row 73 · BCS supply cost");
    expect(host!.textContent).not.toContain("Row 73 · Supply rate");
    expect(finalBox()).toBe("2,009.60");
    const headline = [...host!.querySelectorAll("button span.text-sm.font-semibold")].map((s) => s.textContent);
    expect(headline).toContain("2,010");
    click([...host!.querySelectorAll("button")].find((b) => b.textContent === "Use this value")!);
    // the exact cost, to the paisa (the box's own figure, as before BCS-W: ELR-4c "money to 2 decimals") -- never the rounded 2,010
    expect(onUse.mock.calls[0][1]).toBe(Number(result.bcs!.values.supply_rate!.toFixed(2)));
    expect(onUse.mock.calls[0][1]).toBe(2009.6);
    expect(onUse.mock.calls[0][2].kind).toBe("bcs_supply");
    // BCS-W2 (owner R2 "2. yes"; was "(-) the BoQ side's folded figure prints as before", toContain("2925")): the BoQ side's
    // folded figure prints thousands separated -- and never the bare figure
    expect(q("[data-testid='price-section-boq-folded']")?.textContent).toContain("2,925");
    expect(q("[data-testid='price-section-boq-folded']")?.textContent).not.toContain(String(result.values.supply_rate));
  });
  it("(+) the cable's two blocks: the installation line once, below both", () => {
    const { helper, ctx } = setup("wiring_cabling", CABLE);
    mount(<RateHelperPanel variant="embedded" excelRow={73} col="BCS" kind="supply_rate" target="bcs" ctx={ctx} helpers={[helper]} onUse={() => undefined} showCost />);
    expect(host!.textContent!.split(BCS_INSTALL_NOTE).length - 1).toBe(1);
    const note = q("[data-testid='bcs-install-note']")!;
    const section = q("[data-testid='price-section-bcs']")!;
    expect(section.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
  it("(+) the calculator: BCS figures whole rupees and the installation line once", () => {
    const { helper, ctx } = setup("industrial_sockets", SOCKET);
    mount(<RateHelperPanel variant="calculator" excelRow={73} col="calculator" kind="supply_rate" ctx={ctx} helpers={[helper]} showCost />, false);
    const bcs = q("[data-testid='price-section-bcs']")!.textContent!;
    expect(bcs).toContain("BCS supply = 2,010");
    expect(host!.textContent!.split(BCS_INSTALL_NOTE).length - 1).toBe(1);
  });
});

describe("BCS-W the pop-up default words (answer 4a: Electrical rows only, as drawn)", () => {
  it("(+) an Electrical row: 'Plate qty = 1 (not read from the BoQ; the usual default)'", () => {
    expect(neverAskedDisplay(`${NEVER_ASKED_LEAD}Plate qty=1`, "Electrical")).toBe("Plate qty = 1 (not read from the BoQ; the usual default)");
    expect(neverAskedDisplay(`${NEVER_ASKED_LEAD}Switch qty=1, Plate qty=1`, "Electrical")).toBe("Switch qty = 1, Plate qty = 1 (not read from the BoQ; the usual defaults)");
  });
  it("(-) any other discipline, and any other line, as it is", () => {
    expect(neverAskedDisplay(`${NEVER_ASKED_LEAD}Plate qty=1`, "HVAC")).toBe(`${NEVER_ASKED_LEAD}Plate qty=1`);
    expect(neverAskedDisplay("Supply = 2925", "Electrical")).toBe("Supply = 2925");
  });
  it("(+) on the panel: an Electrical pop-up row with a never-asked plate shows the new words, not the old lead", () => {
    const { helper, ctx } = setup("popup_boxes", { module_count: 3, has_modules: "Yes", switch_item: "16A 1 WAY SWITCH", switch_qty: 1, socket1_item: "None", socket2_item: "None", socket3_item: "None", socket4_item: "None", blank_item: "None", plate_item: "Grid and Face Plates 3M", colour: "White" });
    mount(<RateHelperPanel variant="embedded" excelRow={73} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} showCost />);
    expect(host!.textContent).not.toContain("never asked at extraction");
    expect(host!.textContent).toMatch(/Plate qty = \d+ \(not read from the BoQ; the usual default\)/);
  });
});
