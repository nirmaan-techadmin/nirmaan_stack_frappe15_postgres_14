// @vitest-environment jsdom
//
// BCS-5 -- THE ONE LINE ON A TICKED SHEET'S OWN SUMMARY (owner, mockup point B), rendered by the real SummaryPanel.
//   (+) on a ticked sheet, for a cost user: the line under the summary table, with the live Rs per sq ft and the live block margin;
//   (-) absent on an unticked sheet; (-) absent for a non-cost user, and no cost read fires.
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  role: "Nirmaan Estimates Executive Profile",
  params: { boqId: "BOQ-X", sheetName: "A" } as Record<string, string>,
  calls: [] as { method: string; key: unknown }[],
  call: { get: vi.fn() },
}));
vi.mock("@/hooks/useUserData", () => ({ useUserData: () => ({ role: h.role, user_id: "someone@example.invalid" }) }));
vi.mock("react-router-dom", async (orig) => ({ ...(await orig<typeof import("react-router-dom")>()), useParams: () => h.params }));
vi.mock("@/lib/frappe", async () => {
  const { createContext } = await import("react");
  return {
    FrappeContext: createContext({ call: h.call }),
    useFrappeGetCall: (method: string, _args: unknown, key: unknown) => {
      h.calls.push({ method, key });
      return { data: key === null ? undefined : { message: SUMMARY }, mutate: vi.fn() };
    },
    useFrappePostCall: () => ({ call: vi.fn() }),
  };
});
import SummaryPanel from "./SummaryPanel";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const SUMMARY = {
  boq: "BOQ-X", has_record: true, area_sqft: 5, covered_sheets: ["A"], carpet_area: null,
  rates: { install_per_sqft: 42, tray_cutting: 200 },
  sheets: [{ sheet_name: "A", sheet_order: 1, committed_version: 1, default_ticked: true, ticked: true },
    { sheet_name: "C", sheet_order: 2, committed_version: 1, default_ticked: false, ticked: false }],
  ticked: ["A"], floor: { caught: [], mentioned: [], no_reading_rows: 0, metres: 0, system_amount: 0 },
  installation: { area_part_system: 210, area_part: 210, area_part_changed: false, floor_part_system: 0, floor_part: 0,
    floor_part_changed: false, total: 210 },
};
const DESCS = ["qty_total", "rate_supply", "amount_supply"].map((vf, k) => ({ col: "DEF"[k], role: vf, area: null, value_field: vf,
  value_key: null, rate_subkey: null }));
const ROW = { row_index: 0, effective_parent_index: null, effective_classification: "line_item", description: "item",
  source_row_number: 5, qty_total: 10, rate_supply: 100, node_type: "Line Item",
  // BCS-6a (moved checks, third table): the rate is marked as entered in the app, so the Amount on screen is qty x rate.
  priced_rate_supply: true };
const fake = (m: string) => Promise.resolve(m.endsWith("get_priced_rows")
  ? { message: { commit_version: 1, column_descriptors: DESCS, column_formulas: [], reconciliation_choices: [], rows: [ROW] } }
  : m.endsWith("get_bcs_state") ? { message: { is_ready: true, bcs_qty_source: null, bcs_amount_source: null } }
    : { message: { rows: [{ excel_row: 5, supply_rate: 60, install_rate: 0, combined_rate: 0 }] } });

let root: Root | null = null;
let host: HTMLDivElement | null = null;
async function mount() {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => root!.render(
    <SummaryPanel rows={[ROW] as never} columnDescriptors={DESCS} columnFormulas={[]} reconChoices={[]} sheetName="A" onClose={() => {}} />,
  ));
  for (let k = 0; k < 20; k++) await act(() => new Promise((r) => setTimeout(r, 5)));
}
beforeEach(() => { h.role = "Nirmaan Estimates Executive Profile"; h.params = { boqId: "BOQ-X", sheetName: "A" }; h.calls = [];
  h.call.get.mockReset(); h.call.get.mockImplementation(fake); });
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });

describe("BCS-5 the sheet-summary line", () => {
  it("(+) a ticked sheet, a cost user: the line under the table with the live Rs per sq ft and the block margin", async () => {
    await mount();
    const line = [...host!.querySelectorAll("p")].find((p) => p.textContent?.startsWith("This sheet"));
    expect(line?.textContent).toBe("This sheet’s margin counts installation typed on its rows. The BoQ’s installation cost (area x Rs "
      + "42 + floor cutting) is in the BoQ summary on the BoQ’s main page: margin there 19.0% for the ticked sheets.");
    expect(host!.querySelector("table")!.compareDocumentPosition(line!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
  it("(-) an unticked sheet: no line", async () => {
    h.params = { boqId: "BOQ-X", sheetName: "C" };
    await mount();
    expect(host!.textContent).not.toContain("This sheet’s margin counts");
  });
  it("(-) a non-cost user: no line and no cost read", async () => {
    h.role = "Nirmaan PMO Executive Profile";
    await mount();
    expect(host!.textContent).not.toContain("This sheet’s margin counts");
    expect(h.calls.filter((c) => c.method.endsWith("get_boq_summary_inputs")).every((c) => c.key === null)).toBe(true);
    expect(h.call.get).not.toHaveBeenCalled();
  });
});
