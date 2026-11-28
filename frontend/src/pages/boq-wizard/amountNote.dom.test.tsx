// @vitest-environment jsdom
//
// BCS-6a P2g -- THE NOTE "How the BoQ amount was taken on this sheet" on the sheet's Summary panel (owner R-BCS-156 / 158 / 159,
// R3 / R5 / R6; mockup board 2), rendered by the real SummaryPanel, wording verbatim.
//   (+) each exception lists its rows: (1) "keep the document's amount" chosen, (2) a rate taken from the uploaded file,
//       (3) no rate anywhere and no amount;
//   (+) an exception with no row reads "none on this sheet";
//   (+) a long list: the count first, the rows joined into ranges, "show all" opens the full list;
//   (+) a row number takes the user to that row (the page's grid jump);
//   (-) not rendered without the cost axis (a non-cost user: the page passes no BCS input);
//   (+) the panel's expand / collapse by row level is unchanged (R-BCS-159).
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useUserData", () => ({ useUserData: () => ({ role: "Nirmaan PMO Executive Profile", user_id: "someone@example.invalid" }) }));
vi.mock("react-router-dom", async (orig) => ({ ...(await orig<typeof import("react-router-dom")>()), useParams: () => ({ boqId: "BOQ-X", sheetName: "A" }) }));
vi.mock("@/lib/frappe", async () => {
  const { createContext } = await import("react");
  return {
    FrappeContext: createContext({ call: { get: vi.fn() } }),
    useFrappeGetCall: () => ({ data: undefined, mutate: vi.fn() }),
    useFrappePostCall: () => ({ call: vi.fn() }),
  };
});
import SummaryPanel from "./SummaryPanel";
import { RowRangeList } from "./BoqSummaryBlock";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const d = (col: string, vf: string) => ({ col, role: vf, area: null, value_field: vf, value_key: null, rate_subkey: null });
// D qty, E supply rate, F install rate, G Amount (Supply) = D x E, H Amount (Install) = D x F, I Amount (Total) = G + H.
const DESCS = [d("D", "qty_total"), d("E", "rate_supply"), d("F", "rate_install"), d("G", "amount_supply"), d("H", "amount_install"), d("I", "amount_total")];
const ref = (vf: string) => ({ ref: { value_field: vf, value_key: null, rate_subkey: null } });
const fm = (target: string, formula: unknown) => ({ target_value_field: target, target_value_key: null, target_rate_subkey: null, formula });
const FORMULAS = [
  fm("amount_supply", { op: "*", operands: [ref("qty_total"), ref("rate_supply")] }),
  fm("amount_install", { op: "*", operands: [ref("qty_total"), ref("rate_install")] }),
  fm("amount_total", { op: "+", operands: [ref("amount_supply"), ref("amount_install")] }),
];
const row = (idx: number, er: number, parent: number | null, p: Record<string, unknown>) => ({ row_index: idx, source_row_number: er,
  effective_parent_index: parent, effective_classification: parent === null ? "preamble" : "line_item", description: `row ${er}`,
  node_type: parent === null ? "Preamble" : "Line Item", ...p });
const ROWS = [
  row(0, 10, null, {}),
  // row 11: priced in the app, the file's I (999) differs from 10 x (100 + 20) = 1,200 and the user CHOSE "keep document"
  row(1, 11, 0, { qty_total: 10, rate_supply: 100, rate_install: 20, priced_rate_supply: true, priced_rate_install: true, amount_total: 999 }),
  // row 12: rates written in the uploaded file, never entered in the app
  row(2, 12, 0, { qty_total: 5, rate_supply: 40, rate_install: 10 }),
  // row 13: no rate in the app or the file, and no amount -> left out
  row(3, 13, 0, { qty_total: 2, rate_supply: 0, rate_install: 0 }),
];
const RECON = [{ excel_row: 11, col_letter: "I", choice: "keep_document" }];
const BCS = { ratesByExcelRow: new Map([[13, { excel_row: 13, supply_rate: 30, install_rate: 0, combined_rate: null }]]),
  kinds: ["supply", "install"] as const, qtySource: null, amountSource: null };

let root: Root | null = null;
let host: HTMLDivElement | null = null;
async function mount(node: React.ReactNode) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => root!.render(node));
}
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });
const note = () => host!.querySelector("[data-note='how-boq-amount-taken']");
const item = (k: string) => host!.querySelector(`[data-exception='${k}']`)!.textContent;

describe("BCS-6a the note on the sheet's Summary panel", () => {
  it("(+) the three lines verbatim, each listing its rows", async () => {
    await mount(<SummaryPanel rows={ROWS as never} columnDescriptors={DESCS} columnFormulas={FORMULAS as never} reconChoices={RECON as never}
      bcs={BCS as never} sheetName="A" onClose={() => {}} />);
    expect(note()!.querySelector("p")!.textContent).toBe("How the BoQ amount was taken on this sheet");
    expect(note()!.textContent).toContain("Every row: quantity x the rate you chose, as shown in the Amount column. Exceptions, listed by row:"); // BCS-FX moved check T2-1 (R-BCS-178 / W2)
    expect(item("kept-document")).toBe("Priced in the app, but the uploaded file’s amount was kept instead of quantity x your rate (you chose "
      + '"Keep document"): 1 row: 11'); // BCS-FX moved check T2-1 (W3)
    expect(item("file-rate")).toBe("Not priced in the app yet (no rate entered here), so the rate written in the uploaded file is used: 1 row: 12");
    expect(item("left-out")).toBe("No rate in the app or in the uploaded file, so left out of the margin (amount and cost): 1 row: 13");
  });

  it("(+) an exception with no row reads \"none on this sheet\"", async () => {
    await mount(<SummaryPanel rows={ROWS.slice(0, 2) as never} columnDescriptors={DESCS} columnFormulas={FORMULAS as never} reconChoices={[]}
      bcs={BCS as never} sheetName="A" onClose={() => {}} />);
    expect(item("kept-document")).toMatch(/: none on this sheet$/);
    expect(item("left-out")).toMatch(/: none on this sheet$/);
  });

  it("(+) a row number takes the user to that row (the page's grid jump)", async () => {
    const jump = vi.fn();
    await mount(<SummaryPanel rows={ROWS as never} columnDescriptors={DESCS} columnFormulas={FORMULAS as never} reconChoices={RECON as never}
      bcs={BCS as never} sheetName="A" onClose={() => {}} onJumpToRow={jump} />);
    const b = host!.querySelector("button[aria-label='Go to row 12']") as HTMLButtonElement;
    await act(async () => b.click());
    expect(jump).toHaveBeenCalledWith(12);
  });

  it("(-) not rendered without the cost axis (a non-cost user gets no BCS input from the page)", async () => {
    await mount(<SummaryPanel rows={ROWS as never} columnDescriptors={DESCS} columnFormulas={FORMULAS as never} reconChoices={RECON as never}
      sheetName="A" onClose={() => {}} />);
    expect(note()).toBeNull();
    expect(host!.textContent).not.toContain("How the BoQ amount was taken");
  });

  it("(+) the expand / collapse by row level is unchanged: a section folds and opens", async () => {
    await mount(<SummaryPanel rows={ROWS as never} columnDescriptors={DESCS} columnFormulas={FORMULAS as never} reconChoices={RECON as never}
      bcs={BCS as never} sheetName="A" onClose={() => {}} />);
    const bodyRows = () => host!.querySelectorAll("tbody tr").length;
    expect(bodyRows()).toBe(1); // opens folded to the shallowest preamble tier (defaultCollapsedSet), as before BCS-6a
    await act(async () => (host!.querySelector("tbody button[aria-label='Expand']") as HTMLButtonElement).click());
    expect(bodyRows()).toBe(4); // the section + its 3 lines
    await act(async () => (host!.querySelector("tbody button[aria-label='Collapse']") as HTMLButtonElement).click());
    expect(bodyRows()).toBe(1);
    expect(note()).not.toBeNull(); // the note stays below the table whatever is folded
  });
});

describe("BCS-6a K2c the note's 4th point (owner ANSWER 12)", () => {
  // Row 14: no quantity but a rate (the 00012 row 48 shape); row 15: an amount read into the install rate (the 00186 row 49 shape).
  const suspectRows = [...ROWS,
    row(4, 14, 0, { rate_supply: 3600, rate_install: 360 }),
    row(5, 15, 0, { qty_total: 460, rate_supply: 945, rate_install: 434700 })];

  it("(+) wording exact, the rows listed, numbered 4 by the list", async () => {
    const jump = vi.fn();
    await mount(<SummaryPanel rows={suspectRows as never} columnDescriptors={DESCS} columnFormulas={FORMULAS as never} reconChoices={RECON as never}
      bcs={BCS as never} sheetName="A" onClose={() => {}} onJumpToRow={jump} />);
    const li = host!.querySelector("[data-exception='suspect']")!;
    expect(li.textContent).toBe("The rates/amounts on these rows appear incorrect. Please review them and change if required. 2 rows: 14-15");
    expect([...note()!.querySelectorAll("ol > li")].indexOf(li)).toBe(3); // the 4th item of the numbered list
    await act(async () => (host!.querySelector("button[aria-label='Go to row 15']") as HTMLButtonElement).click());
    expect(jump).toHaveBeenCalledWith(15);
  });

  it("(-) no such row: no point 4 at all", async () => {
    await mount(<SummaryPanel rows={ROWS as never} columnDescriptors={DESCS} columnFormulas={FORMULAS as never} reconChoices={RECON as never}
      bcs={BCS as never} sheetName="A" onClose={() => {}} />);
    expect(host!.querySelector("[data-exception='suspect']")).toBeNull();
    // BCS-FX moved check T2-2 (R-BCS-174): points 1 - 3 and point 5 (always with the cost note) - still no point 4
    const items = [...note()!.querySelectorAll("ol > li")];
    expect(items.length).toBe(4);
    expect(items[3].getAttribute("data-exception")).toBe("no-bcs-supply");
    expect(items[3].getAttribute("value")).toBe("5");
  });
});

describe("BCS-6a K2d point 4 on every sheet, for every Summary viewer (owner ANSWER 13)", () => {
  const suspectRows = [...ROWS,
    row(4, 14, 0, { rate_supply: 3600, rate_install: 360 }),
    row(5, 15, 0, { qty_total: 460, rate_supply: 945, rate_install: 434700 })];
  const SENTENCE = "The rates/amounts on these rows appear incorrect. Please review them and change if required.";

  it("(+) without the cost axis (a role without cost access, or BCS off): point 4 shows, points 1-3 do not", async () => {
    await mount(<SummaryPanel rows={suspectRows as never} columnDescriptors={DESCS} columnFormulas={FORMULAS as never} reconChoices={RECON as never}
      sheetName="A" onClose={() => {}} />);
    expect(note()).toBeNull(); // the cost note (points 1-3) is absent
    const block = host!.querySelector("[data-note='rates-appear-incorrect']")!;
    // BCS-6b moved check K3-5 (owner R4, 27 Nov 14:22): shown ALONE, point 4 carries no number "4." (no list at all)
    expect(block.querySelector("ol")).toBeNull();
    expect(block.textContent).not.toMatch(/^\s*4\./);
    // (-) no cost figure leaks: the block is the fixed sentence and row numbers only
    expect(block.textContent).toBe(`${SENTENCE} 2 rows: 14-15`);
    expect(host!.textContent).not.toContain("left out of the margin");
  });

  it("(+) a cost viewer with BCS on sees points 1-4 in the one note, and no separate point-4 block", async () => {
    await mount(<SummaryPanel rows={suspectRows as never} columnDescriptors={DESCS} columnFormulas={FORMULAS as never} reconChoices={RECON as never}
      bcs={BCS as never} sheetName="A" onClose={() => {}} />);
    expect(note()!.querySelectorAll("ol > li").length).toBe(5); // BCS-FX moved check T2-3 (R-BCS-174): points 1 - 5
    expect(host!.querySelector("[data-note='rates-appear-incorrect']")).toBeNull();
  });

  it("(-) without the cost axis and no such rows: nothing at all", async () => {
    await mount(<SummaryPanel rows={ROWS as never} columnDescriptors={DESCS} columnFormulas={FORMULAS as never} reconChoices={RECON as never}
      sheetName="A" onClose={() => {}} />);
    expect(host!.querySelector("[data-note='rates-appear-incorrect']")).toBeNull();
    expect(note()).toBeNull();
  });
});

describe("BCS-6a the long-list form (RowRangeList)", () => {
  it("(+) the count first, the rows joined into ranges, \"show all\" opens the full list", async () => {
    // 40 rows in 20 separate ranges: 1-2, 4-5, 7-8, ...
    const rows = Array.from({ length: 20 }, (_, k) => [3 * k + 1, 3 * k + 2]).flat();
    await mount(<RowRangeList rows={rows} onJump={() => {}} />);
    expect(host!.textContent).toMatch(/^40 rows: 1-2, 4-5, 7-8, 10-11, 13-14, 16-17, 19-20, 22-23 \.\.\. show all$/);
    await act(async () => ([...host!.querySelectorAll("button")].find((x) => x.textContent === "show all") as HTMLButtonElement).click());
    expect(host!.textContent).toContain("55-56, 58-59 show fewer");
    expect(host!.querySelectorAll("button[aria-label^='Go to row']").length).toBe(40);
  });

  it("(+) a single row and a short list need no \"show all\"", async () => {
    await mount(<RowRangeList rows={[7]} />);
    expect(host!.textContent).toBe("1 row: 7");
  });
});
