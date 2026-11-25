// @vitest-environment jsdom
//
// BCS-W2 -- THOUSANDS SEPARATORS ON BoQ FIGURES IN THE HELPER PANEL AND THE CALCULATOR (owner R2, 25 Nov 13:08 "2. yes"). The REAL
// panel and the REAL helper over the newest Electrical and HVAC rate files (a latest-asset reader by file prefix:
// rate_master_electrical_all_v / rate_master_hvac_all_v), the cert row BOQ-26-00217 "ELE-2F" row 73 (industrial socket 2,196 + its
// paired MCB 729 = 2,925; install 1,030).
//
// What each case protects:
//   (+) a BoQ figure prints with the separator BCS figures already carry (en-IN grouping), its decimals exactly as before: 2925 ->
//       "2,925", 1377.5 -> "1,377.5"; a working line's result likewise ("Supply = 2,925"; "..., rounded up to the rupee: 1,378");
//   (+) on the panel: the headline, the BoQ lines' results, the figures row and the folded BoQ line read 2,925 / 1,030; and in
//       the calculator;
//   (-) the box beside "Use this value" still shows 2925, "Use this value" writes 2925 exactly, and a figure's copy icon still
//       copies the bare 2925 -- no separator anywhere a value leaves the screen;
//   (-) the helper's own output is untouched: its values and lines carry no separator (the separator is drawn, never computed).
import path from "path";
import { readdirSync } from "fs";
import { pathToFileURL } from "url";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RateHelperPanel } from "./RateHelperPanel";
import { bcsFigureText, boqFigureText, boqLine } from "./bcsSide";
import { makePricingSheetHelper } from "./pricingSheetHelper";
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
// the cert row's own answers (BOQ-26-00217 "ELE-2F" row 73, as bcswPanel.dom.test.tsx): socket 2,196 + paired MCB 729 = 2,925
const SOCKET = { item: "Plug + Socket in Enclosure Box", enclosure: "IP44/54 - Splash Proof", rating: "16/20A", pole: "3 Pin / 2P+E", paired_mcb: "25A DP MCB C CURVE", mcb_present: "Yes" };

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
const click = (el: Element | null) => act(() => el!.dispatchEvent(new MouseEvent("click", { bubbles: true })));
const finalBox = () => (q("input[aria-label='Final value']") as HTMLInputElement).value;
const headlines = () => [...host!.querySelectorAll("button span.text-sm.font-semibold")].map((s) => s.textContent);
/** every helper string, deep: the output object as the helper returns it */
const strings = (o: unknown): string[] =>
  typeof o === "string" ? [o] : Array.isArray(o) ? o.flatMap(strings) : o && typeof o === "object" ? Object.values(o).flatMap(strings) : [];

describe("BCS-W2 the BoQ figure format", () => {
  it("(+) thousands separated, the same grouping as a BCS figure; decimals exactly as before", () => {
    expect(boqFigureText(2925)).toBe("2,925");
    expect(boqFigureText(8638)).toBe("8,638");
    expect(boqFigureText(1030)).toBe("1,030");
    expect(boqFigureText(729)).toBe("729");
    expect(boqFigureText(1377.5)).toBe("1,377.5");
    expect(boqFigureText(216.04999999999998)).toBe("216.05");   // to the paisa, as String(moneyValue(v)) printed it
    expect(boqFigureText(-1234.5)).toBe("-1,234.5");
    expect(boqFigureText(123456)).toBe(bcsFigureText(123456));  // en-IN, as the BCS figures: "1,23,456"
    expect(boqFigureText(123456)).toBe("1,23,456");
  });
  it("(+) a working line's result figure; nothing else on the line", () => {
    expect(boqLine("Supply = 2925")).toBe("Supply = 2,925");
    expect(boqLine("Combined = supply + install = 3955")).toBe("Combined = supply + install = 3,955");
    expect(boqLine("Cable + conduit = 1499.5, rounded up to the rupee")).toBe("Cable + conduit = 1,499.5, rounded up to the rupee");
    expect(boqLine("supply: cost x (1 + the SKU's supply markup) = 1377.5, rounded up to the rupee: 1378"))
      .toBe("supply: cost x (1 + the SKU's supply markup) = 1,377.5, rounded up to the rupee: 1,378");
  });
  it("(-) a line with no result figure, a percentage, a small or an already-separated figure is unchanged", () => {
    for (const line of ["Industrial socket discount = 30%", "Paired MCB: Switchgear 25A DP MCB C CURVE x 1 = 729",
      "Socket: Plug + Socket x 1 = 2,196", "Industrial socket supply markup = 40%", "Plate qty = 1 (not read from the BoQ; the usual default)",
      "supply: 1230 x 2 x (375 x 375) / 1,000,000 + 150 = 1,049.44", "factor = 0.333"]) {
      expect(boqLine(line)).toBe(line);
    }
  });
});

describe("BCS-W2 the helper panel and the calculator, Electrical row 73", () => {
  it("(+) from the Supply box: headline, the BoQ lines' results and the figures row read 2,925 and 1,030", () => {
    const { helper, ctx, result } = setup("industrial_sockets", SOCKET);
    expect(result.values.supply_rate).toBe(2925);
    expect(result.values.install_rate).toBe(1030);
    mount(<RateHelperPanel variant="embedded" excelRow={73} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} showCost />);
    expect(headlines()).toContain("2,925");
    expect(headlines()).not.toContain("2925");
    const boq = q("[data-testid='price-section-boq']")!.textContent!;
    expect(boq).toContain("Supply = 2,925");
    expect(boq).toContain("Install = 1,030");
    expect(boq).toContain("x 1 = 2,196");
    expect(boq).toContain("x 1 = 729");
    expect(boq).toContain("Supply2,925");   // the figures row: label then figure
    expect(boq).not.toMatch(/(^|[^\d,])2925([^\d]|$)/);
    expect(boq).not.toMatch(/(^|[^\d,])1030([^\d]|$)/);
  });
  it("(-) the box beside 'Use this value' shows 2925, and Use writes 2925 exactly", () => {
    const { helper, ctx } = setup("industrial_sockets", SOCKET);
    const onUse = vi.fn();
    mount(<RateHelperPanel variant="embedded" excelRow={73} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={onUse} showCost />);
    expect(finalBox()).toBe("2925");
    click([...host!.querySelectorAll("button")].find((b) => b.textContent === "Use this value")!);
    expect(onUse.mock.calls[0][1]).toBe(2925);
    expect(onUse.mock.calls[0][2].kind).toBe("supply_rate");
  });
  it("(-) a figure's copy icon copies the bare number, no separator", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(globalThis.navigator, "clipboard", { value: { writeText }, configurable: true });
    const { helper, ctx } = setup("industrial_sockets", SOCKET);
    mount(<RateHelperPanel variant="embedded" excelRow={73} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} showCost />);
    const copy = q("[data-testid='price-section-boq'] button[aria-label='Copy supply figure']")!;
    await act(async () => { copy.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(writeText).toHaveBeenCalledWith("2925");
  });
  it("(+) from the BCS box: the folded BoQ line reads 2,925", () => {
    const { helper, ctx } = setup("industrial_sockets", SOCKET);
    mount(<RateHelperPanel variant="embedded" excelRow={73} col="BCS" kind="supply_rate" target="bcs" ctx={ctx} helpers={[helper]} onUse={() => undefined} showCost />);
    const folded = q("[data-testid='price-section-boq-folded']")!.textContent!;
    expect(folded).toContain("2,925");
    expect(folded).not.toContain("2925");
  });
  it("(+) the calculator: the BoQ figures separated too", () => {
    const { helper, ctx } = setup("industrial_sockets", SOCKET);
    mount(<RateHelperPanel variant="calculator" excelRow={73} col="calculator" kind="supply_rate" ctx={ctx} helpers={[helper]} showCost />, false);
    const boq = q("[data-testid='price-section-boq']")!.textContent!;
    expect(boq).toContain("Supply = 2,925");
    expect(boq).toContain("Supply2,925");
    expect(boq).not.toMatch(/(^|[^\d,])2925([^\d]|$)/);
  });
  it("(-) the helper's own output carries no separator: values exact, lines as the helper writes them", () => {
    const { result } = setup("industrial_sockets", SOCKET);
    expect(result.values).toMatchObject({ supply_rate: 2925, install_rate: 1030 });
    const all = strings(result.workings);
    expect(all).toContain("Supply = 2925");
    expect(all.some((s) => s.includes("2,925"))).toBe(false);
  });
});
