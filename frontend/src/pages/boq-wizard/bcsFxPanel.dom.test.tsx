// @vitest-environment jsdom
//
// BCS-FX K2 / K3 -- the sheet Summary panel (owner R-BCS-174, 175, 178 - 181), rendered by the real SummaryPanel:
//   K2 point 5:  (+) a row with a BoQ supply amount and a blank BCS supply is listed; (+) a typed-0 BCS supply is listed;
//                (-) an install-only row is not listed; (-) a point-3 row is not listed; (-) a row with a BCS supply is not;
//                (+) shown as "5." with the list style (count, row links); (+) "none on this sheet" when empty;
//                (-) not shown without the cost axis (no BCS input: a caller without cost access, or BCS off).
//   K2 "*":      (+) on the Grand total and each group holding a listed row, with the footnote line; (-) none, and no line, when
//                point 5 is empty; (+) the figures themselves unchanged.
//   K2 heading:  (+) "Exceptions, listed by row:" with no number.
//   K3:          W3 (+) point 1 ends '(you chose "Keep document"):'; E1 (+) a "BoQ amount" column only on a sheet with no Amount
//                (Total) column, = supply + install; E2 (+) Indian grouping; E4 (+) a ticked sheet's margin header labelled
//                "before the BoQ's installation", (-) not on an unticked sheet.
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ role: "Nirmaan PMO Executive Profile", summary: undefined as unknown }));
vi.mock("@/hooks/useUserData", () => ({ useUserData: () => ({ role: state.role, user_id: "someone@example.invalid" }) }));
vi.mock("react-router-dom", async (orig) => ({ ...(await orig<typeof import("react-router-dom")>()), useParams: () => ({ boqId: "BOQ-X", sheetName: "A" }) }));
vi.mock("@/lib/frappe", async () => {
  const { createContext } = await import("react");
  return {
    FrappeContext: createContext({ call: { get: vi.fn(async () => ({ message: {} })) } }),
    useFrappeGetCall: () => ({ data: state.summary ? { message: state.summary } : undefined, mutate: vi.fn() }),
    useFrappePostCall: () => ({ call: vi.fn() }),
  };
});
import SummaryPanel, { MARGIN_BEFORE_INSTALL } from "./SummaryPanel";
import { NOT_FINAL_LINE, POINT5_TEXT } from "./bcsPoint5";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const d = (col: string, vf: string) => ({ col, role: vf, area: null, value_field: vf, value_key: null, rate_subkey: null });
const ref = (vf: string) => ({ ref: { value_field: vf, value_key: null, rate_subkey: null } });
const fm = (target: string, formula: unknown) => ({ target_value_field: target, target_value_key: null, target_rate_subkey: null, formula });
const DESCS_TOTAL = [d("D", "qty_total"), d("E", "rate_supply"), d("F", "rate_install"), d("G", "amount_supply"), d("H", "amount_install"), d("I", "amount_total")];
const DESCS_NO_TOTAL = DESCS_TOTAL.filter((x) => x.value_field !== "amount_total");
const FORMULAS = [
  fm("amount_supply", { op: "*", operands: [ref("qty_total"), ref("rate_supply")] }),
  fm("amount_install", { op: "*", operands: [ref("qty_total"), ref("rate_install")] }),
  fm("amount_total", { op: "+", operands: [ref("amount_supply"), ref("amount_install")] }),
];
const row = (idx: number, er: number, parent: number | null, p: Record<string, unknown>) => ({ row_index: idx, source_row_number: er,
  effective_parent_index: parent, effective_classification: parent === null ? "preamble" : "line_item", description: `row ${er}`,
  node_type: parent === null ? "Preamble" : "Line Item", ...p });
const priced = { priced_rate_supply: true, priced_rate_install: true };
const ROWS = [
  row(0, 10, null, {}),
  row(1, 11, 0, { qty_total: 1000, rate_supply: 100, rate_install: 20, ...priced }), // supply 1,00,000, no BCS -> listed
  row(2, 12, 0, { qty_total: 5, rate_supply: 40, rate_install: 10 }),               // file rates, no BCS -> listed
  row(3, 13, 0, { qty_total: 2, rate_supply: 0, rate_install: 0 }),                 // no rate anywhere -> point 3, never point 5
  row(4, 14, 0, { qty_total: 3, rate_supply: 0, rate_install: 50, priced_rate_install: true }), // install-only -> not listed
  row(5, 15, 0, { qty_total: 2, rate_supply: 10, rate_install: 0, ...priced }),      // BCS supply typed 0 -> listed
  row(6, 16, null, {}),
  row(7, 17, 6, { qty_total: 4, rate_supply: 10, rate_install: 5, ...priced }),      // BCS supply 6 -> not listed
];
const rate = (er: number, s: number | null, i: number | null) => [er, { excel_row: er, supply_rate: s, install_rate: i, combined_rate: null }] as const;
const BCS = { ratesByExcelRow: new Map([rate(13, 30, 0), rate(15, 0, 0), rate(17, 6, 2), rate(14, 0, 30)]),
  kinds: ["supply", "install"] as const, qtySource: null, amountSource: null };
// every supply row costed -> point 5 empty
const BCS_FULL = { ...BCS, ratesByExcelRow: new Map([rate(11, 50, 5), rate(12, 20, 2), rate(15, 3, 0), rate(17, 6, 2), rate(14, 0, 30)]) };

let root: Root | null = null;
let host: HTMLDivElement | null = null;
async function mount(bcs: unknown, descs = DESCS_TOTAL) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => root!.render(<SummaryPanel rows={ROWS as never} columnDescriptors={descs} columnFormulas={FORMULAS as never}
    reconChoices={[]} bcs={bcs as never} sheetName="A" onClose={() => {}} onJumpToRow={() => {}} />));
}
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; state.role = "Nirmaan PMO Executive Profile"; state.summary = undefined; });
const p5 = () => host!.querySelector("[data-exception='no-bcs-supply']");
const headers = () => [...host!.querySelectorAll("thead th")].map((t) => t.textContent);
const grand = () => [...host!.querySelectorAll("tfoot td")].map((t) => t.textContent);
const expandAll = () => {
  const b = [...host!.querySelectorAll("button")].find((x) => x.textContent === "Expand all");
  if (b) act(() => b.dispatchEvent(new MouseEvent("click", { bubbles: true })));
};
const rowCells = (label: string) => {
  expandAll();
  const tr = [...host!.querySelectorAll("tbody tr")].find((t) => t.textContent?.includes(label));
  return [...(tr?.querySelectorAll("td") ?? [])].map((t) => t.textContent);
};

describe("BCS-FX K2 note point 5", () => {
  it("(+) lists rows with a BoQ supply amount and a blank or 0 BCS supply, as point 5 in the list style; (-) install-only, point-3, costed rows", async () => {
    await mount(BCS);
    expect(p5()).not.toBeNull();
    expect(p5()!.getAttribute("value")).toBe("5");
    expect(p5()!.textContent).toBe(`${POINT5_TEXT} 3 rows: 11-12, 15`);
    const links = [...p5()!.querySelectorAll("button[aria-label^='Go to row']")].map((b) => b.getAttribute("aria-label"));
    expect(links).toEqual(["Go to row 11", "Go to row 12", "Go to row 15"]);
  });
  it("(+) 'none on this sheet' when every supply row has a BCS supply", async () => {
    await mount(BCS_FULL);
    expect(p5()!.textContent).toBe(`${POINT5_TEXT} none on this sheet`);
  });
  it("(-) not shown without the cost axis (no BCS input)", async () => {
    await mount(null);
    expect(p5()).toBeNull();
    expect(host!.textContent).not.toContain(POINT5_TEXT);
  });
  it("(+) the note's first line has no count", async () => {
    await mount(BCS);
    const text = host!.querySelector("[data-note='how-boq-amount-taken']")!.textContent!;
    expect(text).toContain("Every row: quantity x the rate you chose, as shown in the Amount column. Exceptions, listed by row:");
    expect(text).not.toContain("Three exceptions");
  });
  it("(+) W3: point 1 ends with (you chose \"Keep document\"):", async () => {
    await mount(BCS);
    expect(host!.querySelector("[data-exception='kept-document']")!.textContent).toContain('(you chose "Keep document"): ');
  });
});

describe("BCS-FX K2 the margin's asterisk", () => {
  it("(+) '*' on the Grand total and on the group holding a listed row, with the footnote; (-) not on a group without one", async () => {
    await mount(BCS);
    const g = grand();
    expect(g[g.length - 1]).toMatch(/^\d+\.\d%\*$/);
    expect(rowCells("row 10").at(-1)).toMatch(/\*$/);
    expect(rowCells("row 16").at(-1)).not.toMatch(/\*$/);
    expect(host!.querySelector("[data-note='not-final']")!.textContent).toBe(NOT_FINAL_LINE);
  });
  it("(-) no '*' and no footnote when point 5 is empty; (+) the figures are the same with and without the mark", async () => {
    await mount(BCS_FULL);
    expect(grand().join("|")).not.toContain("*");
    expect(host!.querySelector("[data-note='not-final']")).toBeNull();
    const without = grand().at(-1);
    act(() => root?.unmount()); host?.remove();
    await mount({ ...BCS_FULL, ratesByExcelRow: new Map([...BCS_FULL.ratesByExcelRow, rate(12, 0, 22)]) });
    // row 12's supply now 0 (install 22 keeps the cost total the same): listed, marked -- the margin figure itself does not move
    expect(grand().at(-1)).toBe(`${without}*`);
  });
});

describe("BCS-FX K3 the panel's display fixes", () => {
  it("(+) E2 Indian grouping in the panel", async () => {
    await mount(BCS);
    expect(rowCells("row 11")).toContain("1,00,000");
  });
  it("(+) E1 a 'BoQ amount' column on a sheet with no Amount (Total) column = supply + install; (-) not when the column exists", async () => {
    await mount(BCS, DESCS_NO_TOTAL);
    const h = headers();
    expect(h).toContain("BoQ amount");
    expect(h.indexOf("BoQ amount")).toBe(h.indexOf("BCS Total Amount") - 1);
    const cells = rowCells("row 11");
    expect(cells[h.indexOf("BoQ amount")]).toBe("1,20,000");
    act(() => root?.unmount()); host?.remove();
    await mount(BCS, DESCS_TOTAL);
    expect(headers()).not.toContain("BoQ amount");
  });
  it("(-) E4 an unticked sheet's margin header is the plain '% Margin'", async () => {
    await mount(BCS);
    expect(headers()).toContain("% Margin");
    expect(headers()).not.toContain(MARGIN_BEFORE_INSTALL);
  });
  it("(+) E4 a ticked sheet's own panel labels the margin 'before the BoQ's installation'", async () => {
    state.role = "Nirmaan Admin Profile";
    state.summary = { boq: "BOQ-X", has_record: true, area_sqft: null, covered_sheets: ["A"], carpet_area: null,
      rates: { install_per_sqft: 42, tray_cutting: 100 }, sheets: [{ sheet_name: "A", sheet_order: 1, committed_version: 1, ticked: true }],
      ticked: ["A"], floor: { caught: [], mentioned: [], no_reading_rows: 0, metres: 0, system_amount: null },
      installation: { area_part_system: null, area_part: null, area_part_changed: false, floor_part_system: null, floor_part: null,
        floor_part_changed: false, total: null } };
    await mount(BCS);
    expect(headers()).toContain(MARGIN_BEFORE_INSTALL);
    expect(MARGIN_BEFORE_INSTALL).toBe("% Margin (before the BoQ's installation)");
  });
});
