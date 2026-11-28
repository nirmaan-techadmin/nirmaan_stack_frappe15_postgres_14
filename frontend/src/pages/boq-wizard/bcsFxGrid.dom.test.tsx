// @vitest-environment jsdom
//
// BCS-FX K3 on the REAL grid (owner R-BCS-180 ODD-7 / ODD-8; QR-FORMAT (a)) - the call sites of the pure helpers:
//   E3 (+) a rate-only row's quantity cell shows the file's text ("RO") instead of 0; (-) a normal 0-quantity row still shows 0.
//   E2 (+) the BCS Total Amount cell is in the one Indian style (1,20,000); (-) the grid's other cells keep their formatter.
//   K2 (BCSFX-26 Q11 / BCSFX-30 Q12): (+) "0" typed in a never-costed row's box is sent as {0, 0, 0} (a typed 0 stays 0);
//      (+) clearing a saved row's one typed box is sent as {null, 0, 0} (the server then removes the row's cost).
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PricingGrid } from "./PricingGrid";
import { bcsWidthKey } from "./bcsColumns";
import type { BcsRowRate, ColumnDescriptor, PricedRow } from "./boqTypes";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
class StubResizeObserver { observe() { /* no layout */ } unobserve() { /* no layout */ } disconnect() { /* no layout */ } }
if (!(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = StubResizeObserver;
}
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => { /* no layout */ };

let root: Root | null = null;
let host: HTMLDivElement | null = null;
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; vi.useRealTimers(); });

const row = (er: number, idx: number, p: Record<string, unknown>) => ({
  name: `n${er}`, boq: "B", sheet_name: "S", source_row_number: er, row_index: idx, classification: "Line Item", level: 1, parent_index: null,
  path: null, attached_to_index: null, attached_notes: null, promoted_from_line_item: 0, preamble_level_override: null,
  preamble_candidate_score: null, preamble_candidate_signals: null, needs_classification_review: 0, review_reason: null, sl_no_value: String(er),
  description: `row ${er}`, description_parts_raw: null, unit: "Nos", make_model: null, is_rate_only: 0, is_synthetic: 0, qty_total: 0,
  qty_by_area: null, rate_supply: null, rate_install: null, node_type: "Line Item", ...p,
}) as unknown as PricedRow;
const QTY: ColumnDescriptor = { col: "D", role: "Quantity", area: null, value_field: "qty_total", value_key: null, rate_subkey: null };
const SUPPLY: ColumnDescriptor = { col: "F", role: "Rate (Supply)", area: null, value_field: "rate_supply", value_key: null, rate_subkey: null };

function mount(rows: PricedRow[], rates?: Map<number, BcsRowRate>) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(<PricingGrid rows={rows} columnDescriptors={[QTY, SUPPLY]} bcsKinds={["supply"]} bcsRatesByExcelRow={rates}
    bcsQtySource={{ mode: "", columns: [QTY as never] }} />));
}
const cellOf = (er: number, col: string) => {
  const tr = [...host!.querySelectorAll("tr")].find((t) => t.textContent?.includes(`row ${er}`))!;
  return tr.querySelector(`td[data-colkey$='${col}']`) as HTMLTableCellElement | null;
};

describe("BCS-FX K3 the grid's quantity cell and BCS Total", () => {
  it("(+) E3 a rate-only row shows the file's text; (-) a normal 0-quantity row still shows 0", () => {
    mount([row(16, 0, { is_rate_only: 0, qty_cell_text: "RO", rate_supply: 300 }), row(28, 1, { qty_cell_text: null, rate_supply: 300 }),
      row(17, 2, { is_rate_only: 1, qty_cell_text: null, rate_supply: 300 })]);
    expect(cellOf(16, "D")?.textContent).toBe("RO");
    expect(cellOf(17, "D")?.textContent).toBe("RO");
    expect(cellOf(28, "D")?.textContent).toBe("0");
  });
  it("(+) E2 the BCS Total Amount cell in the one Indian style", () => {
    const rates = new Map<number, BcsRowRate>([[40, { excel_row: 40, supply_rate: 1200, install_rate: 0, combined_rate: 0, is_filled: 1 } as unknown as BcsRowRate]]);
    mount([row(40, 0, { qty_total: 100, rate_supply: 1500 })], rates);
    const texts = [...host!.querySelectorAll("td")].map((t) => t.textContent);
    expect(texts).toContain("1,20,000");
    expect(texts).not.toContain("120000");
  });
});

function mountEditable(rates?: Map<number, BcsRowRate>) {
  const onSaveBcsRates = vi.fn(() => Promise.resolve());
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(<PricingGrid rows={[row(50, 0, { qty_total: 2, rate_supply: 100 })]} columnDescriptors={[QTY, SUPPLY]}
    bcsKinds={["supply", "install"]} bcsRatesByExcelRow={rates} onSaveRate={vi.fn(() => Promise.resolve())} onSaveBcsRates={onSaveBcsRates} />));
  return onSaveBcsRates;
}
function typeAndBlur(input: HTMLInputElement, text: string) {
  // the grid's own auto-save path: the typed draft schedules the debounced save (as bcs3GridUse's "Use" test drives it)
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  act(() => { setter.call(input, text); input.dispatchEvent(new Event("input", { bubbles: true })); });
  act(() => { vi.advanceTimersByTime(1500); });
}
// the BCS supply box (not the BoQ rate cell, which is also a decimal input on an editable grid)
const costInputs = () => [host!.querySelector(`td[data-colkey='${bcsWidthKey("supply")}'] input`) as HTMLInputElement];
const sent = (fn: ReturnType<typeof vi.fn>) => (fn.mock.calls.at(-1) as unknown as [{ rates: Record<string, number | null> }])[0].rates;

describe("BCS-FX K2 the grid's cost payload (typed 0, cleared box)", () => {
  it("(+) '0' typed in a never-costed row's supply box is sent as {0, 0, 0}", () => {
    vi.useFakeTimers();
    const save = mountEditable();
    typeAndBlur(costInputs()[0], "0");
    expect(save).toHaveBeenCalled();
    expect(sent(save)).toEqual({ supply_rate: 0, install_rate: 0, combined_rate: 0 });
  });
  it("(+) clearing a saved row's one typed box is sent as {null, 0, 0}", () => {
    vi.useFakeTimers();
    const save = mountEditable(new Map([[50, { excel_row: 50, supply_rate: 10000, install_rate: 0, combined_rate: 0, is_filled: 1 } as unknown as BcsRowRate]]));
    typeAndBlur(costInputs()[0], "");
    expect(save).toHaveBeenCalled();
    expect(sent(save)).toEqual({ supply_rate: null, install_rate: 0, combined_rate: 0 });
  });
});
