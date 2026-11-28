// @vitest-environment jsdom
//
// BCS-3 -- THE BCS BOX ON THE REAL GRID (owner R6, R8; P3b / P3e).
//   (+) the BCS supply box carries the opener; a click opens the panel on the BCS side for THAT row.
//   (+) "Use this value" from the BCS box (`applyBcsRate`) writes the row's BCS SUPPLY through the cost save path
//       (`onSaveBcsRates`, the whole row gathered) -- on a combined-only sheet, the single box.
//   (-) it NEVER calls the rate save (`onSaveRate` -> save_cell_price).
//   (-) the installation box opens nothing; on an Electrical row it reads "On the BoQ summary" and stays editable.
//   (-) without the opener prop (a viewer who may not see cost) there is no opener.
import { createRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PricingGrid, type PricingGridHandle, BCS_INSTALL_ON_SUMMARY, BCS_INSTALL_ON_SUMMARY_SHORT } from "./PricingGrid";
import type { ColumnDescriptor, PricedRow } from "./boqTypes";
import type { BcsRateKind } from "./bcsColumns";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
class StubResizeObserver { observe() { /* no layout */ } unobserve() { /* no layout */ } disconnect() { /* no layout */ } }
if (!(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = StubResizeObserver;
}
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => { /* no layout */ };

let root: Root | null = null;
let host: HTMLDivElement | null = null;
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; vi.useRealTimers(); });

const ROW = {
  name: "n1", boq: "B", sheet_name: "S", source_row_number: 124, row_index: 3, classification: "Line Item", level: 1, parent_index: null,
  path: null, attached_to_index: null, attached_notes: null, promoted_from_line_item: 0, preamble_level_override: null,
  preamble_candidate_score: null, preamble_candidate_signals: null, needs_classification_review: 0, review_reason: null, sl_no_value: "1.19",
  description: "Industrial socket", description_parts_raw: null, unit: "Nos", make_model: null, is_rate_only: 0, is_synthetic: 0, qty_total: 2,
  qty_by_area: null, rate_supply: null, rate_install: null, node_type: "Line Item",
} as unknown as PricedRow;
const SUPPLY: ColumnDescriptor = { col: "F", role: "Rate (Supply)", area: null, value_field: "rate_supply", value_key: null, rate_subkey: null };

function mount(kinds: BcsRateKind[], withOpener = true, onSummary = true) {
  const ref = createRef<PricingGridHandle>();
  const onSaveRate = vi.fn(() => Promise.resolve());
  const onSaveBcsRates = vi.fn(() => Promise.resolve());
  const onBcsHelperClick = vi.fn();
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(
    <PricingGrid
      ref={ref}
      rows={[ROW]}
      columnDescriptors={[SUPPLY]}
      onSaveRate={onSaveRate}
      bcsKinds={kinds}
      onSaveBcsRates={onSaveBcsRates}
      onBcsHelperClick={withOpener ? onBcsHelperClick : undefined}
      bcsInstallOnSummaryRows={onSummary ? new Set([124]) : undefined}
    />,
  ));
  return { ref, onSaveRate, onSaveBcsRates, onBcsHelperClick };
}

describe("BCS-3 the BCS box on the grid", () => {
  it("(+) the supply box's opener opens the panel for that row", () => {
    const { onBcsHelperClick } = mount(["supply", "install"]);
    const openers = host!.querySelectorAll("[data-testid='bcs-helper-open']");
    expect(openers.length).toBe(1);
    act(() => openers[0].dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onBcsHelperClick).toHaveBeenCalledWith(124);
  });
  it("(+) Use from the BCS box writes the BCS supply through the cost save path; (-) never the rate save", () => {
    vi.useFakeTimers();
    const { ref, onSaveRate, onSaveBcsRates } = mount(["supply", "install"]);
    act(() => ref.current!.applyBcsRate(124, 2009.6));
    act(() => { vi.advanceTimersByTime(1500); });
    expect(onSaveBcsRates).toHaveBeenCalledTimes(1);
    const arg = (onSaveBcsRates.mock.calls[0] as unknown as [{ excelRow: number; rates: Record<string, number> }])[0];
    expect(arg.excelRow).toBe(124);
    expect(arg.rates.supply_rate).toBe(2009.6);
    expect(arg.rates.install_rate).toBe(0);
    expect(onSaveRate).not.toHaveBeenCalled();
  });
  it("(+) a combined-only sheet: the single box carries the opener and takes the BCS supply", () => {
    vi.useFakeTimers();
    const { ref, onSaveBcsRates } = mount(["combined"]);
    expect(host!.querySelectorAll("[data-testid='bcs-helper-open']").length).toBe(1);
    act(() => ref.current!.applyBcsRate(124, 6173.5));
    act(() => { vi.advanceTimersByTime(1500); });
    const arg = (onSaveBcsRates.mock.calls[0] as unknown as [{ rates: Record<string, number> }])[0];
    expect(arg.rates.combined_rate).toBe(6173.5);
  });
  it("(-) the installation box opens nothing and reads 'On the BoQ summary' on an Electrical row, still editable", () => {
    mount(["supply", "install"]);
    const inputs = [...host!.querySelectorAll("input[inputmode='decimal']")] as HTMLInputElement[];
    // BCS-FX moved check T2-5 (R-BCS-180 ODD-11 / W15): the short placeholder, the full sentence in the cell's tooltip
    const install = inputs.find((i) => i.placeholder === BCS_INSTALL_ON_SUMMARY_SHORT);
    expect(install).toBeTruthy();
    expect(install!.closest("td")!.getAttribute("title")).toBe(BCS_INSTALL_ON_SUMMARY);
    expect(install!.disabled).toBe(false);
    expect(install!.closest("td")!.querySelector("[data-testid='bcs-helper-open']")).toBeNull();
  });
  it("(-) not an Electrical row: no hint; no opener prop: no opener", () => {
    mount(["supply", "install"], false, false);
    expect(host!.querySelector("[data-testid='bcs-helper-open']")).toBeNull();
    expect([...host!.querySelectorAll("input")].some((i) => (i as HTMLInputElement).placeholder === BCS_INSTALL_ON_SUMMARY_SHORT)).toBe(false); // T2-5
  });
});
