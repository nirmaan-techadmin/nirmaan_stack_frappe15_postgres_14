// @vitest-environment jsdom
//
// BCS-5 -- THE BoQ SUMMARY BLOCK ON THE BoQ'S MAIN PAGE (owner R1 - R8; the approved mockup).
//   (+) it renders for a cost user (Admin / Estimates), at the top of the hub (under the header, above the general-spec box);
//   (-) for anyone else nothing renders and NO cost read fires (the summary read's key is null, no per-sheet read is made);
//   (+) the clubbed block: ONE installation figure and ONE margin across the ticked sheets; a "Ticked block" sub-total;
//   (+) a ticked sheet's typed installation is not counted; an unticked sheet's is (BCS-6a: no "typed" label after it, owner R6);
//   (+) BCS-6a: the grey exception lines under a sheet's name (row links to the pricing route's ?row=) and the yellow box;
//   (+) blank (never 0) where there is no value; the BoQ total's margin blank until every listed sheet has a cost;
//   (+) "- enter the area" with no area; (+) edit / remove show "changed by user" and "Back to system figure" and save the right
//       values; (+) the carpet-area hint copies its figure into the save.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BoqSummaryResponse } from "./BoqSummaryBlock";

const h = vi.hoisted(() => ({
  role: "Nirmaan Admin Profile",
  summary: null as unknown,
  calls: [] as { method: string; key: unknown }[],
  call: { get: vi.fn() },
  save: vi.fn(),
  mutate: vi.fn(),
}));
vi.mock("@/hooks/useUserData", () => ({ useUserData: () => ({ role: h.role, user_id: "someone@example.invalid" }) }));
vi.mock("@/lib/frappe", async () => {
  const { createContext } = await import("react");
  return {
    FrappeContext: createContext({ call: h.call }),
    useFrappeGetCall: (method: string, _args: unknown, key: unknown) => {
      h.calls.push({ method, key });
      return { data: key === null ? undefined : { message: h.summary }, mutate: h.mutate };
    },
    useFrappePostCall: () => ({ call: h.save }),
  };
});
import { BoqSummaryBlock, ENTER_AREA, SheetExceptionLines } from "./BoqSummaryBlock";
import { MemoryRouter } from "react-router-dom";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const d = (col: string, vf: string) => ({ col, role: vf, area: null, value_field: vf, value_key: null, rate_subkey: null });
const DESCS = [d("D", "qty_total"), d("E", "rate_supply"), d("F", "rate_install"), d("G", "amount_supply"), d("H", "amount_install")];
/** One line item per sheet: qty, supply rate, install rate; and its stored BCS supply / install (null = no BCS row). */
const SHEETS: Record<string, [number, number, number, number | null, number | null]> = {
  A: [10, 100, 20, 70, 5], B: [5, 200, 0, 150, 0], C: [2, 500, 100, 300, 50], D: [1, 500, 0, null, null], E: [10, 100, 20, 70, 14],
};
// Sheet E is ELV-style (Question 4): a BOQ Total formula on amount_total = G + H, the document printing 999 in I, and a
// take_formula reconciliation choice on I - its BoQ amount must follow the choice (1,200), as the sheet's Summary shows it.
const ref = (vf: string) => ({ ref: { value_field: vf, value_key: null, rate_subkey: null } });
const E_EXTRA = {
  descriptors: [...DESCS, d("I", "amount_total")],
  formulas: [{ target_value_field: "amount_total", target_value_key: null, target_rate_subkey: null, target_col: "I",
    formula: { op: "+", operands: [ref("amount_supply"), ref("amount_install")] } },
  { target_value_field: "boq_total", target_value_key: null, target_rate_subkey: null, target_col: null, formula: ref("amount_total") }],
  choices: [{ excel_row: 5, col_letter: "I", choice: "take_formula" }],
};
function fakeServer(method: string, args: { sheet_name: string }) {
  const [qty, s, i, bs, bi] = SHEETS[args.sheet_name];
  const e = args.sheet_name === "E";
  if (method.endsWith("get_priced_rows")) return { message: { commit_version: 1, column_descriptors: e ? E_EXTRA.descriptors : DESCS,
    column_formulas: e ? E_EXTRA.formulas : [], reconciliation_choices: e ? E_EXTRA.choices : [],
    rows: [{ row_index: 0, effective_parent_index: null, effective_classification: "line_item", description: "item",
      // BCS-6a (moved checks, third table): the rate is marked as entered in the app, so the Amount on screen is qty x rate.
      source_row_number: 5, qty_total: qty, rate_supply: s, rate_install: i, priced_rate_supply: s !== 0, priced_rate_install: i !== 0,
      node_type: "Line Item", ...(e ? { amount_supply: 1000, amount_install: 200, amount_total: 999 } : {}) }] } };
  if (method.endsWith("get_bcs_state")) return { message: { is_ready: true, bcs_qty_source: null, bcs_amount_source: null } };
  return { message: { rows: bs === null ? [] : [{ excel_row: 5, supply_rate: bs, install_rate: bi, combined_rate: 0 }] } };
}
function summary(over: Partial<BoqSummaryResponse> = {}, sheets = ["A", "B", "C"], ticked = ["A", "B"]): BoqSummaryResponse {
  return {
    boq: "BOQ-X", has_record: true, area_sqft: 5, covered_sheets: ticked, carpet_area: 13765,
    rates: { install_per_sqft: 42, tray_cutting: 200 },
    sheets: sheets.map((n, k) => ({ sheet_name: n, sheet_order: k + 1, committed_version: 1, default_ticked: ticked.includes(n), ticked: ticked.includes(n) })),
    ticked,
    floor: { caught: [{ sheet_name: "A", excel_row: 7, text: "floor trunking", qty: 0.25, unit: "Mtrs." }],
      mentioned: [{ sheet_name: "A", excel_row: 8, text: "junction box", qty: 4, unit: "Nos.", reason: "its unit (Nos.) is not a length" }],
      no_reading_rows: 0, metres: 0.25, system_amount: 50 },
    installation: { area_part_system: 210, area_part: 250, area_part_changed: true, floor_part_system: 50, floor_part: 50,
      floor_part_changed: false, total: 300 },
    ...over,
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
const cells = (rowText: string) => [...host!.querySelectorAll("tr")].find((tr) => tr.textContent?.startsWith(rowText))!
  .querySelectorAll("td");
const click = async (text: string) => {
  const b = [...host!.querySelectorAll("button")].find((x) => x.textContent === text)!;
  await act(async () => b.dispatchEvent(new MouseEvent("click", { bubbles: true })));
};

beforeEach(() => {
  h.role = "Nirmaan Admin Profile"; h.calls = []; h.call.get.mockReset(); h.save.mockReset(); h.mutate.mockReset();
  h.call.get.mockImplementation((m: string, a: { sheet_name: string }) => Promise.resolve(fakeServer(m, a)));
  h.save.mockResolvedValue({ message: summary() });
});
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });

describe("BCS-5 the BoQ summary block", () => {
  it("(+) renders for a cost user", async () => {
    await mount(summary());
    expect(host!.querySelector("section[aria-label='BoQ summary']")?.textContent).toContain("BoQ summary · our cost and margin");
    expect(h.calls.find((c) => c.method.endsWith("get_boq_summary_inputs"))?.key).toBeUndefined(); // the read is live
  });
  it("(-) a non-cost user: nothing renders and no cost read fires", async () => {
    h.role = "Nirmaan PMO Executive Profile";
    await mount(summary());
    expect(host!.innerHTML).toBe("");
    expect(h.calls.every((c) => c.key === null)).toBe(true);
    expect(h.call.get).not.toHaveBeenCalled();
  });
  it("(+) the clubbed block: one installation and one margin; (+) a ticked sheet's typed install is not counted", async () => {
    await mount(summary());
    const a = cells("[x] A");
    expect(a[3].getAttribute("rowspan")).toBe("2");
    expect(a[3].textContent).toBe("300"); // the installation figure, not A's typed 50
    expect(a[5].textContent).toBe("20.5%"); // 1 - (700 + 750 + 300) / 2,200
    expect(cells("[x] B")).toHaveLength(4); // B shares the spanned installation and margin
    expect([...cells("Ticked block")].map((c) => c.textContent)).toEqual(["Ticked block", "2,200", "1,450", "300", "2 of 2", "20.5%"]);
    // BCS-6a MOVED CHECK (owner R6, 27 Nov 00:12, board 1: "nop label is needed for that"): the figure, no "typed" after it.
    expect(cells("C")[3].textContent).toBe("100"); // an unticked sheet: its typed install counts
    expect(cells("C")[5].textContent).toBe("41.7%");
  });
  it("(+) blank (never 0) where no value; (+) total margin blank until every listed sheet has a cost", async () => {
    await mount(summary({}, ["A", "B", "C", "D"]));
    expect([cells("D")[2].textContent, cells("D")[3].textContent, cells("D")[5].textContent]).toEqual(["", "", ""]);
    expect(cells("BoQ total")[5].textContent).toBe("");
    act(() => root?.unmount()); host?.remove();
    await mount(summary());
    expect(cells("BoQ total")[5].textContent).toBe("27.9%"); // 1 - (2,050 + 300 + 100) / 3,400
  });
  it("(+) an ELV-style sheet with a reconciliation choice: its BoQ amount follows the choice (1,200, not the printed 999)", async () => {
    await mount(summary({}, ["A", "B", "E"]));
    expect(cells("E")[1].textContent).toBe("1,200");
    expect(cells("E")[5].textContent).toBe("30.0%"); // 1 - 840 / 1,200 (supply 700 + typed install 140)
  });
  it("(+) no area: installation, block margin and total margin read '- enter the area'", async () => {
    await mount(summary({ area_sqft: null, installation: { area_part_system: null, area_part: null, area_part_changed: false,
      floor_part_system: 50, floor_part: 50, floor_part_changed: false, total: null } }));
    expect(cells("[x] A")[3].textContent).toBe(ENTER_AREA);
    expect(cells("Ticked block")[5].textContent).toBe(ENTER_AREA);
    expect(cells("BoQ total")[5].textContent).toBe(ENTER_AREA);
  });
  it("(+) an edited part shows 'changed by user' and 'Back to system figure'; Remove / Back save the right values", async () => {
    await mount(summary());
    expect(host!.textContent).toContain("changed by user");
    expect([...host!.querySelectorAll("button")].filter((b) => b.textContent === "Back to system figure")).toHaveLength(1);
    await click("Back to system figure");
    expect(h.save).toHaveBeenLastCalledWith({ boq: "BOQ-X", area_cost_override: "" });
    await click("Remove");
    expect(h.save).toHaveBeenLastCalledWith({ boq: "BOQ-X", area_cost_override: "0" });
  });
  it("(+) the carpet-area hint copies its figure", async () => {
    await mount(summary());
    expect(host!.textContent).toContain("Project carpet area: 13,765 sq ft");
    await click("use it");
    expect(h.save).toHaveBeenLastCalledWith({ boq: "BOQ-X", area_sqft: "13765" });
  });
  it("(+) the block sits at the top of the hub: under the header, above the removed-sheet advisory and the general-spec box", () => {
    const src = readFileSync(resolve(process.cwd(), "src/pages/boq-wizard/BoqHubPage.tsx"), "utf8"); // vitest runs in frontend/
    const at = (s: string) => src.indexOf(s);
    expect(at("<BoqSummaryBlock boqId={boqId} />")).toBeGreaterThan(at("Header strip (M2.18)"));
    expect(at("<BoqSummaryBlock boqId={boqId} />")).toBeLessThan(at("Removed-sheet advisory (ADR-0014 D4)"));
    expect(at("Removed-sheet advisory (ADR-0014 D4)")).toBeLessThan(at("Declare General Specification sheets"));
  });
});

describe("BCS-6a the BoQ summary's exception lines and the yellow box (mockup board 1)", () => {
  it("(+) the yellow box 'How these figures are worked out' under the table, with the board's lines", async () => {
    await mount(summary());
    const box = host!.querySelector("[data-box='how-worked-out']")!;
    expect(box.textContent).toContain("How these figures are worked out");
    expect(box.textContent).toContain("BoQ amount = the amount shown on each row (qty x the chosen rate; a row priced on one side only counts its one amount).");
    expect(box.textContent).toContain("The exceptions are listed by row under each sheet’s name.");
    expect(box.textContent).toContain("Margin = 1 - (BCS supply + BCS installation) / BoQ amount.");
    expect(box.textContent).toContain("A blank means no value yet (never 0).");
    expect(host!.querySelector("table")!.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
  it("(+) a grey line per exception that applies, in the long-list form, each row a link to that row", async () => {
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    const ex = { keptDocument: [], fileRate: [4, 5, 6, 9], leftOut: [30] };
    await act(async () => root!.render(<MemoryRouter><SheetExceptionLines ex={ex} boqId="BOQ-X" sheet="ELV BOQ" /></MemoryRouter>));
    expect(host!.textContent).toBe("Not priced in the app yet - the uploaded file's rate used: 4 rows: 4-6, 9"
      + "No rate anywhere - left out: 1 row: 30");
    expect(host!.textContent).not.toContain("amount kept"); // (-) no line where the exception does not apply
    expect(host!.querySelector("a[aria-label='Go to row 30']")!.getAttribute("href")).toBe("/upload-boq/hub/BOQ-X/pricing/ELV%20BOQ?row=30");
  });
  it("(-) no lines on a sheet with BCS off (no margin shown there)", async () => {
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    await act(async () => root!.render(<MemoryRouter><SheetExceptionLines ex={null} boqId="BOQ-X" sheet="A" /></MemoryRouter>));
    expect(host!.textContent).toBe("");
  });
});
