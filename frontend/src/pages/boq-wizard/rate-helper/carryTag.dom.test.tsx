// @vitest-environment jsdom
//
// BCS-4 (mockup screen 2, rule 3; UI CHANGE CONTROL 2) -- THE TAG ON A CARRIED FIELD. The REAL panel and helper over the newest
// rate files (latest-asset readers by file prefix: rate_master_electrical_all_v, rate_master_hvac_all_v).
//
// What each case protects:
//   (+) a field changed in the Supply view reads "carried from the Supply helper" in the Install view and in the BCS view.
//   (-) the same field reads "changed by you" in the Supply view itself -- never "carried from".
//   (+) a change made in the BCS view reads "carried from the BCS helper" elsewhere (the BCS box's own name).
//   (-) a field nobody changed carries no edit tag.
//   (+) Revert clears the row's saved change (handed up to the page) and the field goes back to the extraction, untagged.
//   (+) a `__shares__` edit (a VAV row's shared-item blocks) is saved like any key -- handed up with its view -- and seeded
//       like any key: a fresh mount from the saved edits shows the share it added.
import path from "path";
import { readdirSync } from "fs";
import { pathToFileURL } from "url";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RateHelperPanel, carryTagText, helperViewOf, helperViewLabel, seededOverrides, type SavedHelperEdits } from "./RateHelperPanel";
import { makePricingSheetHelper, PRICING_SHEET_HELPER_ID } from "./pricingSheetHelper";
import { mergeItemsByName } from "./rateHelperPlumbing";
import { SHARES_OVERRIDE_KEY } from "./vavSheetShares";
import { calculatorCtx } from "../../pricing/PricingCalculator";
import { withV79Items, withV79Keys } from "./vav2b1Keys.harness";
import type { ExtractionRow, RateHelperRowContext } from "./rateHelperTypes";
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
const newest = (prefix: string) => readdirSync(DATA_DIR).filter((f) => new RegExp(`^${prefix}\\d+\\.json$`).test(f))
  .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
const ELEC = readJsonFixture<Asset>(pathToFileURL(path.join(DATA_DIR, newest("rate_master_electrical_all_v"))));
const HVAC = readJsonFixture<Asset>(pathToFileURL(path.join(DATA_DIR, newest("rate_master_hvac_all_v"))));
const ITEMS: RateMasterItem[] = mergeItemsByName(ELEC.items.map((i) => ({ ...i, discipline: "Electrical" } as RateMasterItem)), []);
const CONFIGS = new Map<string, RateCategoryConfig>(ELEC.category_configs.map((c) => [c.category_id, { ...c, discipline: "Electrical" }]));
const DB = "db_switchgear";
const GOLDEN = (CONFIGS.get(DB) as unknown as { goldens: Array<{ id: string; attrs: Record<string, unknown> }> }).goldens.find((g) => g.id === "dbu1")!.attrs;
const KINDS = ["supply_rate", "install_rate", "combined_rate"];
const ROW = 12;
const CHANGED = "63A DP MCB C CURVE"; // lists at 2,316 against the golden's 63A FP MCB D CURVE at 4,010

function dbSetup() {
  const cells = Object.fromEntries(Object.entries(GOLDEN).map(([k, v]) => [k, { value: v, confidence: 0.9 }]));
  const row = { excelRow: ROW, description: "", attributes: cells } as unknown as ExtractionRow;
  const helper = makePricingSheetHelper({ configsByCategory: CONFIGS, items: ITEMS, extractionByRow: new Map([[ROW, row]]) });
  const ctx = { excelRow: ROW, description: "", nodeType: "Line Item", category: DB, discipline: "Electrical", rateKinds: KINDS, headings: [], ownNotes: [], unit: "Nos" } as RateHelperRowContext;
  return { helper, ctx };
}

let root: Root | null = null;
let host: HTMLDivElement | null = null;
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });

function mount(node: JSX.Element, open = true) {
  act(() => root?.unmount());
  host?.remove();
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(node));
  if (open) {
    const header = [...host.querySelectorAll("button")].find((b) => !b.getAttribute("aria-label") && b.querySelector(".text-sm.font-medium"));
    if (header) act(() => header.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  }
  return host;
}
const mcb1 = () => host!.querySelector("select[id$='-attr-mcb1_item']") as HTMLSelectElement;
/** The edit tag beside a plain attribute's label (the label row holds the label, its chips and the undo icon). */
function tagOf(attrId: string): string | null {
  const select = host!.querySelector(`[id$='-attr-${attrId}']`)!;
  const label = host!.querySelector(`label[for='${select.id}']`)!;
  return label.parentElement!.querySelector("[data-testid='helper-edit-tag']")?.textContent ?? null;
}
const click = (el: Element | null | undefined) => act(() => el!.dispatchEvent(new MouseEvent("click", { bubbles: true })));

describe("BCS-4 the carry tag -- exact words, beside the existing tags", () => {
  const savedFromSupply: SavedHelperEdits = { mcb1_item: { value: CHANGED, from_kind: "supply" } };

  it("(+) the Install view: 'carried from the Supply helper'", () => {
    const { helper, ctx } = dbSetup();
    mount(<RateHelperPanel variant="embedded" excelRow={ROW} col="G" kind="install_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} savedEdits={savedFromSupply} />);
    expect(mcb1().value).toBe(CHANGED);
    expect(tagOf("mcb1_item")).toBe("carried from the Supply helper");
  });

  it("(+) the BCS view: 'carried from the Supply helper'", () => {
    const { helper, ctx } = dbSetup();
    mount(<RateHelperPanel variant="embedded" excelRow={ROW} col="BCS" kind="supply_rate" target="bcs" showCost ctx={ctx} helpers={[helper]} onUse={() => undefined} savedEdits={savedFromSupply} />);
    expect(tagOf("mcb1_item")).toBe("carried from the Supply helper");
  });

  it("(-) the Supply view itself: 'changed by you', never 'carried from'", () => {
    const { helper, ctx } = dbSetup();
    mount(<RateHelperPanel variant="embedded" excelRow={ROW} col="F" kind="supply_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} savedEdits={savedFromSupply} />);
    expect(tagOf("mcb1_item")).toBe("changed by you");
    expect(host!.textContent).not.toContain("carried from");
  });

  it("(+) a change made in the BCS view reads 'carried from the BCS helper' in the Combined view; (-) an unchanged field has no edit tag", () => {
    const { helper, ctx } = dbSetup();
    const fromBcs: SavedHelperEdits = { mcb1_item: { value: CHANGED, from_kind: "bcs_supply" } };
    mount(<RateHelperPanel variant="embedded" excelRow={ROW} col="H" kind="combined_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} savedEdits={fromBcs} />);
    expect(tagOf("mcb1_item")).toBe("carried from the BCS helper");
    expect(tagOf("mcb2_item")).toBeNull();
  });

  it("(+) a change made here is tagged 'changed by you' at once, and handed up with this view", () => {
    const { helper, ctx } = dbSetup();
    const onSaveEdit = vi.fn();
    mount(<RateHelperPanel variant="embedded" excelRow={ROW} col="G" kind="install_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} onSaveEdit={onSaveEdit} />);
    expect(tagOf("mcb1_item")).toBeNull();
    const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
    act(() => { set.call(mcb1(), CHANGED); mcb1().dispatchEvent(new Event("change", { bubbles: true })); });
    expect(tagOf("mcb1_item")).toBe("changed by you");
    expect(onSaveEdit).toHaveBeenCalledWith("mcb1_item", CHANGED, "install");
  });

  it("(+) Revert clears the row's saved change (handed up) and the field is back to the extraction, untagged", () => {
    const { helper, ctx } = dbSetup();
    const onClearEdits = vi.fn();
    mount(<RateHelperPanel variant="embedded" excelRow={ROW} col="G" kind="install_rate" ctx={ctx} helpers={[helper]} onUse={() => undefined} savedEdits={savedFromSupply} onClearEdits={onClearEdits} />);
    expect(mcb1().value).toBe(CHANGED);
    click([...host!.querySelectorAll("button")].find((b) => b.textContent === "Revert"));
    expect(onClearEdits).toHaveBeenCalledTimes(1);
    expect(onClearEdits.mock.calls[0]).toEqual([]);
    expect(mcb1().value).toBe(GOLDEN.mcb1_item);
    expect(tagOf("mcb1_item")).toBeNull();
  });

  it("(+) the words come from the panel's own labels: Supply / Install / Combined / BCS", () => {
    expect(helperViewOf("supply_rate")).toBe("supply");
    expect(helperViewOf("install_rate")).toBe("install");
    expect(helperViewOf("combined_rate")).toBe("combined");
    expect(helperViewOf("supply_rate", "bcs")).toBe("bcs_supply");
    expect(["supply", "install", "combined", "bcs_supply"].map(helperViewLabel)).toEqual(["Supply", "Install", "Combined", "BCS"]);
    expect(carryTagText("install", "supply")).toBe("carried from the Install helper");
    expect(carryTagText("supply", "supply")).toBe("changed by you");
  });
});

describe("BCS-4 a __shares__ edit is saved and seeded like any key", () => {
  const VAV = "hvac_vav_box";
  function vavSetup() {
    const m = new Map<string, RateCategoryConfig>(HVAC.category_configs.map((c) => [c.category_id, c]));
    m.set(VAV, withV79Keys(m.get(VAV)!));
    const items = withV79Items(HVAC.items.map((i) => ({ ...i, discipline: "HVAC" } as RateMasterItem)));
    const helper = makePricingSheetHelper({ configsByCategory: m, items, extractionByRow: new Map() });
    return { helper, ctx: calculatorCtx("HVAC", VAV) };
  }

  it("(+) adding a share hands up the __shares__ key with the view; a fresh mount from it shows the share", () => {
    const { helper, ctx } = vavSetup();
    const onSaveEdit = vi.fn();
    mount(<RateHelperPanel variant="calculator" excelRow={ctx.excelRow} col="calculator" kind="supply_rate" ctx={ctx} helpers={[helper]} calculatorBlocks={[]} fieldColumns={1} blockColumns={1} onSaveEdit={onSaveEdit} />, false);
    click(host!.querySelector("[data-testid='share-add-bacnet']"));
    const call = onSaveEdit.mock.calls.find((c) => c[0] === SHARES_OVERRIDE_KEY)!;
    expect(call).toBeTruthy();
    expect(call[2]).toBe("supply");
    expect(JSON.parse(call[1]).bacnet).toBeTruthy();
    const saved: SavedHelperEdits = { [SHARES_OVERRIDE_KEY]: { value: call[1], from_kind: "supply" } };
    expect(seededOverrides(saved)[PRICING_SHEET_HELPER_ID][SHARES_OVERRIDE_KEY]).toBe(call[1]);
    mount(<RateHelperPanel variant="calculator" excelRow={ctx.excelRow} col="calculator" kind="supply_rate" ctx={ctx} helpers={[helper]} calculatorBlocks={[]} fieldColumns={1} blockColumns={1} savedEdits={saved} />, false);
    expect(host!.querySelector("[data-testid='share-block-bacnet']")).not.toBeNull();
  });
});
