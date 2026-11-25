// @vitest-environment jsdom
//
// BCS-4 (owner R1 / R2, design BCS-D0 P3, mockup screen 2) -- A CHANGE CARRIES TO THE ROW'S OTHER HELPERS, AND ONLY THE
// SUGGESTION MOVES. The REAL panel and the REAL helper over the newest Electrical rate file (a latest-asset reader by file
// prefix: rate_master_electrical_all_v), on a DB build-up row (the rate file's own golden "dbu1": MCB 1 = 63A FP MCB D CURVE).
//
// What each case protects:
//   (+) a change of MCB 1 in the SUPPLY view is handed to the page to save -- ("mcb1_item", the new value, "supply") -- and
//       the Supply suggestion is worked again.
//   (+) the INSTALL view of the same row, seeded from that saved change, works its suggestion with it: the Install figure
//       moves from the no-edit figure to the figure the helper gives with the change.
//   (+) a reload = a fresh mount from the saved edits: the change is there before anything is clicked.
//   (-) the cell's own value (4,150 in the drawn example) is never touched: the panel never calls "Use this value"
//       (onUse -> the page's applyRate) for an edit, in either view -- red if it ever does.
//   (-) a typed final value is never handed to the page to save (R2): only the helper's inputs are.
import path from "path";
import { readdirSync } from "fs";
import { pathToFileURL } from "url";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RateHelperPanel, type SavedHelperEdits } from "./RateHelperPanel";
import { makePricingSheetHelper, PRICING_SHEET_HELPER_ID } from "./pricingSheetHelper";
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

type Asset = { discipline: string; items: RateMasterItem[]; category_configs: RateCategoryConfig[] };
const DATA_DIR = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
const newest = readdirSync(DATA_DIR).filter((f) => /^rate_master_electrical_all_v\d+\.json$/.test(f))
  .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
const ELEC = readJsonFixture<Asset>(pathToFileURL(path.join(DATA_DIR, newest)));
const ITEMS: RateMasterItem[] = mergeItemsByName(ELEC.items.map((i) => ({ ...i, discipline: "Electrical" } as RateMasterItem)), []);
const CONFIGS = new Map<string, RateCategoryConfig>(ELEC.category_configs.map((c) => [c.category_id, { ...c, discipline: "Electrical" }]));
const DB = "db_switchgear";
// The rate file's own golden row for this category (read, never typed): its attributes are the row's extraction.
const GOLDEN = (CONFIGS.get(DB) as unknown as { goldens: Array<{ id: string; attrs: Record<string, unknown> }> }).goldens.find((g) => g.id === "dbu1")!.attrs;
const KINDS = ["supply_rate", "install_rate", "combined_rate"];
const ROW = 12;
const CHANGED = "63A DP MCB C CURVE"; // the golden reads 63A FP MCB D CURVE (list 4,010); this MCB lists at 2,316, so the figures move

function setup() {
  const cells = Object.fromEntries(Object.entries(GOLDEN).map(([k, v]) => [k, { value: v, confidence: 0.9 }]));
  const row = { excelRow: ROW, description: "", attributes: cells } as unknown as ExtractionRow;
  const helper = makePricingSheetHelper({ configsByCategory: CONFIGS, items: ITEMS, extractionByRow: new Map([[ROW, row]]) });
  const ctx = { excelRow: ROW, description: "", nodeType: "Line Item", category: DB, discipline: "Electrical", rateKinds: KINDS, headings: [], ownNotes: [], unit: "Nos" } as RateHelperRowContext;
  return { helper, ctx };
}

let root: Root | null = null;
let host: HTMLDivElement | null = null;
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });

function mount(node: JSX.Element) {
  if (!host) {
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
  }
  act(() => root!.render(node));
  const header = [...host.querySelectorAll("button")].find((b) => !b.getAttribute("aria-label") && b.querySelector(".text-sm.font-medium"));
  if (header && !host.querySelector("[id$='-attr-mcb1_item']")) act(() => header.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  return host;
}
function remount(node: JSX.Element) {
  act(() => root?.unmount());
  host?.remove();
  root = null;
  host = null;
  return mount(node);
}
const mcb1 = () => host!.querySelector("select[id$='-attr-mcb1_item']") as HTMLSelectElement;
const finalBox = () => (host!.querySelector("input[aria-label='Final value']") as HTMLInputElement).value;
function choose(select: HTMLSelectElement, value: string) {
  const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
  act(() => { set.call(select, value); select.dispatchEvent(new Event("change", { bubbles: true })); });
}
function typeFinal(value: string) {
  const input = host!.querySelector("input[aria-label='Final value']") as HTMLInputElement;
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  act(() => { set.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); });
}

describe("BCS-4 a change in one view of a row carries to its other views -- only the suggestion moves", () => {
  it("(+) Supply view: the change is handed up to save with its view, the Supply suggestion is worked again; (-) no Use", () => {
    const { helper, ctx } = setup();
    const onSaveEdit = vi.fn();
    const onUse = vi.fn();
    let cell = 4150; // the row's Install cell -- only "Use this value" could change it
    mount(<RateHelperPanel variant="embedded" excelRow={ROW} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]}
      onUse={(...a) => { onUse(...a); cell = a[1]; }} onSaveEdit={onSaveEdit} />);
    const before = finalBox();
    expect(mcb1().value).toBe(GOLDEN.mcb1_item);
    expect([...mcb1().options].map((o) => o.value)).toContain(CHANGED);
    choose(mcb1(), CHANGED);
    expect(onSaveEdit).toHaveBeenCalledWith("mcb1_item", CHANGED, "supply");
    const withChange = (helper.compute(ctx, { mcb1_item: CHANGED }) as Suggestion).values.supply_rate;
    expect(finalBox()).toBe(String(withChange));
    expect(finalBox()).not.toBe(before);
    expect(onUse).not.toHaveBeenCalled();
    expect(cell).toBe(4150);
  });

  it("(+) Install view seeded from the saved change: the Install suggestion moves; (-) the cell value 4,150 is unchanged, no Use", () => {
    const { helper, ctx } = setup();
    const saved: SavedHelperEdits = { mcb1_item: { value: CHANGED, from_kind: "supply" } };
    const onUse = vi.fn();
    let cell = 4150;
    const noEdit = (helper.compute(ctx, {}) as Suggestion).values.install_rate;
    const withEdit = (helper.compute(ctx, { mcb1_item: CHANGED }) as Suggestion).values.install_rate;
    expect(withEdit).not.toBe(noEdit); // the fixture is a row whose Install figure depends on the field
    mount(<RateHelperPanel variant="embedded" excelRow={ROW} col="G" kind="install_rate" ctx={ctx} helpers={[helper]}
      onUse={(...a) => { onUse(...a); cell = a[1]; }} savedEdits={saved} />);
    expect(mcb1().value).toBe(CHANGED);
    expect(finalBox()).toBe(String(withEdit));
    expect(onUse).not.toHaveBeenCalled();
    expect(cell).toBe(4150);
  });

  it("(+) a reload (a fresh mount) seeds the saved change before anything is clicked; the page's seed is the pricing-sheet helper's", () => {
    const { helper, ctx } = setup();
    const saved: SavedHelperEdits = { mcb1_item: { value: CHANGED, from_kind: "supply" } };
    mount(<RateHelperPanel variant="embedded" excelRow={ROW} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} />);
    expect(mcb1().value).toBe(GOLDEN.mcb1_item);
    remount(<RateHelperPanel variant="push" excelRow={ROW} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} savedEdits={saved} />);
    expect(mcb1().value).toBe(CHANGED);
    expect(helper.id).toBe(PRICING_SHEET_HELPER_ID);
  });

  it("(-) a typed final value is never handed up to save (R2): only the helper's inputs are", () => {
    const { helper, ctx } = setup();
    const onSaveEdit = vi.fn();
    mount(<RateHelperPanel variant="embedded" excelRow={ROW} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} onSaveEdit={onSaveEdit} />);
    typeFinal("12345");
    expect(onSaveEdit).not.toHaveBeenCalled();
  });
});
