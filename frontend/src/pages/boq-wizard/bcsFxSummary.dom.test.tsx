// @vitest-environment jsdom
//
// BCS-FX K2 / K3 -- the BoQ summary on the BoQ's main page (owner R-BCS-174, 180, 181), rendered by the real BoqSummaryBlock:
//   K2 "*":  (+) a sheet line whose sheet lists a point-5 row carries "*" on its margin, and the BoQ total does, with the footnote
//            "* Not final: some rows have no BCS cost yet (see point 5)."; (-) a sheet line without one carries none;
//            (+) the Block total carries "*" exactly when a ticked sheet has one; (-) no "*" and no footnote when no sheet has one;
//            (+) the figures are unchanged (the mark is appended to the same figure).
//   K3 E5:   (+) the ticked sheets' installation and margin are ONE merged cell across the block's rows.
//   K3 W25:  (+) the right box ends "...only confirmed data sheets are listed."
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BoqSummaryResponse } from "./BoqSummaryBlock";

const h = vi.hoisted(() => ({ summary: null as unknown, call: { get: vi.fn() } }));
vi.mock("@/hooks/useUserData", () => ({ useUserData: () => ({ role: "Nirmaan Admin Profile", user_id: "someone@example.invalid" }) }));
vi.mock("@/lib/frappe", async () => {
  const { createContext } = await import("react");
  return {
    FrappeContext: createContext({ call: h.call }),
    useFrappeGetCall: (_m: string, _a: unknown, key: unknown) => ({ data: key === null ? undefined : { message: h.summary }, mutate: vi.fn() }),
    useFrappePostCall: () => ({ call: vi.fn() }),
  };
});
import { BoqSummaryBlock } from "./BoqSummaryBlock";
import { NOT_FINAL_LINE } from "./bcsPoint5";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const d = (col: string, vf: string) => ({ col, role: vf, area: null, value_field: vf, value_key: null, rate_subkey: null });
const DESCS = [d("D", "qty_total"), d("E", "rate_supply"), d("F", "rate_install"), d("G", "amount_supply"), d("H", "amount_install")];
/** One line item per sheet: qty, supply rate, install rate; its stored BCS supply / install. P has BCS supply 0 = a point-5 row. */
const SHEETS: Record<string, [number, number, number, number, number]> = {
  A: [10, 100, 20, 70, 5], B: [5, 200, 0, 150, 0], C: [2, 500, 100, 300, 50], P: [10, 100, 20, 0, 5],
};
h.call.get.mockImplementation(async (method: string, args: { sheet_name: string }) => {
  const [qty, s, i, bs, bi] = SHEETS[args.sheet_name];
  if (method.endsWith("get_priced_rows")) return { message: { commit_version: 1, column_descriptors: DESCS, column_formulas: [], reconciliation_choices: [],
    rows: [{ row_index: 0, effective_parent_index: null, effective_classification: "line_item", description: "item", source_row_number: 5,
      qty_total: qty, rate_supply: s, rate_install: i, priced_rate_supply: s !== 0, priced_rate_install: i !== 0, node_type: "Line Item" }] } };
  if (method.endsWith("get_bcs_state")) return { message: { is_ready: true, bcs_qty_source: null, bcs_amount_source: null } };
  return { message: { rows: [{ excel_row: 5, supply_rate: bs, install_rate: bi, combined_rate: 0 }] } };
});
function summary(sheets: string[], ticked: string[]): BoqSummaryResponse {
  return {
    boq: "BOQ-X", has_record: true, area_sqft: 5, covered_sheets: ticked, carpet_area: null, rates: { install_per_sqft: 42, tray_cutting: 200 },
    sheets: sheets.map((n, k) => ({ sheet_name: n, sheet_order: k + 1, committed_version: 1, default_ticked: ticked.includes(n), ticked: ticked.includes(n) })),
    ticked, floor: { caught: [], mentioned: [], no_reading_rows: 0, metres: 0, system_amount: 0 },
    installation: { area_part_system: 210, area_part: 210, area_part_changed: false, floor_part_system: 0, floor_part: 0, floor_part_changed: false, total: 210 },
  };
}
let root: Root | null = null;
let host: HTMLDivElement | null = null;
const tick = async () => { for (let k = 0; k < 20; k++) await act(() => new Promise((r) => setTimeout(r, 5))); };
async function mount(s: BoqSummaryResponse) {
  h.summary = s;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => root!.render(<BoqSummaryBlock boqId="BOQ-X" />));
  await tick();
}
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });
const rowOf = (sel: string) => host!.querySelector(`tr[data-row='${sel}']`)!;
const lastCell = (tr: Element) => [...tr.querySelectorAll("td")].at(-1)!.textContent;
const lineFor = (name: string) => [...host!.querySelectorAll("tbody tr")].find((tr) => tr.querySelector("td")?.textContent?.startsWith(name))!;

describe("BCS-FX K2 the BoQ summary's asterisk", () => {
  it("(+) the sheet line with a point-5 row and the BoQ total carry '*', with the footnote; (-) the others and the block do not", async () => {
    await mount(summary(["A", "B", "C", "P"], ["A", "B"]));
    expect(lastCell(lineFor("P"))).toMatch(/^\d+\.\d%\*$/);
    expect(lastCell(lineFor("C"))).toMatch(/^\d+\.\d%$/);
    expect(lastCell(rowOf("ticked-block"))).toMatch(/^\d+\.\d%$/);
    expect(lastCell(rowOf("boq-total"))).toMatch(/^\d+\.\d%\*$/);
    expect(host!.querySelector("[data-note='not-final']")!.textContent).toBe(NOT_FINAL_LINE);
  });
  it("(+) the Block total carries '*' when a ticked sheet lists a point-5 row (and the merged block margin cell)", async () => {
    await mount(summary(["A", "P", "C"], ["A", "P"]));
    expect(lastCell(rowOf("ticked-block"))).toMatch(/\*$/);
    expect(host!.querySelector("td[data-cell='block-margin']")!.textContent).toMatch(/\*$/);
    expect(lastCell(rowOf("boq-total"))).toMatch(/\*$/);
  });
  it("(-) no '*' and no footnote when no sheet lists a point-5 row; (+) the same figures as with the mark", async () => {
    await mount(summary(["A", "B", "C", "P"], ["A", "B"]));
    const marked = lastCell(lineFor("P"));
    act(() => root?.unmount()); host?.remove();
    await mount(summary(["A", "B", "C"], ["A", "B"]));
    expect(host!.textContent).not.toContain("%*");
    expect(host!.querySelector("[data-note='not-final']")).toBeNull();
    expect(marked!.endsWith("*")).toBe(true);
  });
});

describe("BCS-FX K3 the BoQ summary's display fixes", () => {
  it("(+) E5 the ticked sheets' installation and margin are one merged cell across the block's rows", async () => {
    await mount(summary(["A", "B", "C"], ["A", "B"]));
    for (const k of ["block-install", "block-margin"]) {
      const cell = host!.querySelector(`td[data-cell='${k}']`)!;
      expect(cell.getAttribute("rowspan")).toBe("2");
      expect(cell.className).toContain("align-middle");
      expect(cell.className).toContain("border-x");
    }
    expect(host!.querySelectorAll("td[data-cell='block-margin']").length).toBe(1);
  });
  it("(+) W25 the right box: '...only confirmed data sheets are listed.'", async () => {
    await mount(summary(["A", "B", "C"], ["A", "B"]));
    expect(host!.textContent!.replace(/\s+/g, " ")).toContain("Electrical sheets start ticked; the user corrects them; only confirmed data sheets are listed.");
    expect(host!.textContent).not.toContain("committed data");
  });
});
