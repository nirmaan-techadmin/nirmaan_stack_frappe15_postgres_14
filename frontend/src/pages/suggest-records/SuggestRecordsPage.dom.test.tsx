// @vitest-environment jsdom
//
// SRS-2 T5 (page) -- the "AI Suggest Records" page rendered with the server faked at the SDK hooks:
//   + "No records yet." when the store holds nothing for the filters;
//   + a priced row shows its figures; a pending / not-priced / not-computed row shows "-" (never 0), with its chip;
//   + clicking a row opens the detail below, whose shared AI question starts FOLDED and whose input / reply / final
//     values / rates start open; the BCS supply figure is the text, never a number;
//   + the list asks the server for the applied filters (the default 30-day window) and page 1.
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { parseJson } from "@/lib/parseJson";

import { SuggestRecordsPage } from "./SuggestRecordsPage";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  replies: {} as Record<string, unknown>,
  calls: [] as { method: string; params: unknown; key: unknown }[],
  post: vi.fn(),
}));

vi.mock("@/lib/frappe", () => ({
  useFrappeGetCall: (method: string, params: unknown, key: unknown) => {
    h.calls.push({ method, params, key });
    if (key === null) return { data: undefined, isLoading: false, error: undefined };
    return { data: { message: h.replies[method.split(".").pop() ?? ""] }, isLoading: false, error: undefined };
  },
  useFrappePostCall: () => ({ call: h.post }),
}));

const ROW = (name: string, excel_row: number, status: string, rates: [number | null, number | null, number | null]) => ({
  name, run_date: "2026-11-27 15:45:39", project_name: "Test Project", boq: "BOQ-26-00375", sheet_name: "ELE Lowside",
  excel_row, description: `row ${excel_row}`, category_id: "conduit_piping", first_values: "conduit_type = PVC; size_mm = 25",
  supply_rate: rates[0], install_rate: rates[1], combined_rate: rates[2],
  bcs_supply_rate: "not yet - added when the BCS branch merges", rates_status: status,
});

const DETAIL = {
  name: "r1", project_name: "Test Project", boq: "BOQ-26-00375", committed_version: 1, sheet_name: "ELE Lowside",
  excel_row: 43, boq_node: "BOQN-26-153620", description: "row 43", discipline: "Electrical", category_id: "conduit_piping",
  // the REAL stored shape: each call's tokens under `usage` (services/boq_suggest_store/split.py) - cert D2
  run_date: "2026-11-27 15:45:41", run_id: "rid", batch_rows: 2,
  batch: { calls: [{ usage: { input_tokens: 1516, output_tokens: 69, cache_read_input_tokens: 0 } }] },
  catalogue_stamp: "8c3f78be1315ef61", ai_input: '{"id": 43}', raw_reply: '{"id": 43, "attributes": {}}',
  final_attributes: [{ attribute: "conduit_type", value: "PVC", confidence: 0.97 }],
  rates: { supply_rate: null, install_rate: null, combined_rate: null, bcs_supply_rate: "not yet - added when the BCS branch merges",
    rates_status: "pending", pricing_stamp: null },
  question: { name: "0342c0450319325d9c9c", text: "THE SHARED QUESTION TEXT", bytes: 3024, category_id: "conduit_piping" },
  run: { pass_kind: "selected_rows", run_by: "Administrator", model: "m", suggestion_run: "shgapetnb1" },
};

let root: Root | null = null;
let host: HTMLDivElement;

async function render() {
  host = document.createElement("div");
  document.body.appendChild(host);
  await act(async () => {
    root = createRoot(host);
    root.render(<SuggestRecordsPage />);
  });
}

const text = (sel: string) => Array.from(host.querySelectorAll(sel)).map((e) => (e.textContent ?? "").trim());

beforeEach(() => {
  h.replies = { filter_options: { projects: [], boqs: [], sheets: [], disciplines: [], categories: [], run_by: [], rates_statuses: [] } };
  h.calls = [];
});

afterEach(async () => {
  await act(async () => root?.unmount());
  root = null;
  host.remove();
});

describe("SRS-2 AI Suggest Records page", () => {
  it("says 'No records yet.' when nothing matches", async () => {
    h.replies.list_records = { rows: [], total: 0, page: 1, page_size: 50 };
    await render();
    expect(host.querySelector('[data-testid="suggest-records-empty"]')?.textContent).toBe("No records yet.");
    expect(host.querySelectorAll('[data-testid="suggest-record-row"]').length).toBe(0);
  });

  it("asks for the default 30-day window, page 1", async () => {
    h.replies.list_records = { rows: [], total: 0, page: 1, page_size: 50 };
    await render();
    const list = h.calls.find((c) => c.method.endsWith(".list_records"));
    const params = list?.params as { filters: string; page: number };
    expect(params.page).toBe(1);
    expect(Object.keys(parseJson(params.filters) as object).sort()).toEqual(["date_from", "date_to"]);
  });

  it("shows figures only for a priced row; pending / not priced / not computed show '-' with their chip", async () => {
    h.replies.list_records = {
      rows: [ROW("a", 24, "priced", [162, 34, 196]), ROW("b", 43, "pending", [null, null, null]),
        ROW("c", 45, "not priced: size_mm", [null, null, null]), ROW("d", 46, "rates not computed: pricing step bundle missing", [null, null, null]),
        ROW("e", 47, "priced", [5, null, 9])],
      total: 5, page: 1, page_size: 50,
    };
    await render();
    expect(text('[data-testid="row-supply"]')).toEqual(["₹162", "-", "-", "-", "₹5"]);
    expect(text('[data-testid="row-install"]')).toEqual(["₹34", "-", "-", "-", "-"]);
    expect(text('[data-testid="row-combined"]')).toEqual(["₹196", "-", "-", "-", "₹9"]);
    expect(host.textContent).not.toContain("₹0");
    const chips = Array.from(host.querySelectorAll('[data-testid="suggest-record-row"] .bg-green-100, [data-testid="suggest-record-row"] .bg-amber-100, [data-testid="suggest-record-row"] .bg-red-100, [data-testid="suggest-record-row"] .bg-gray-100'))
      .map((e) => `${e.className.match(/bg-(\w+)-100/)?.[1]}:${e.textContent}`);
    expect(chips).toEqual(["green:priced", "gray:pending", "amber:not priced: size_mm",
      "red:rates not computed: pricing step bundle missing", "green:priced"]);
    expect(host.textContent).toContain("Showing 1 - 5 of 5 records. 50 per page.");
  });

  it("opens the detail below a clicked row; the shared question starts folded; a pending row shows no figure", async () => {
    h.replies.list_records = { rows: [ROW("r1", 43, "pending", [null, null, null])], total: 1, page: 1, page_size: 50 };
    h.replies.get_record = DETAIL;
    await render();
    expect(host.querySelector('[data-testid="suggest-record-detail"]')).toBeNull();
    const detailCall = h.calls.find((c) => c.method.endsWith(".get_record"));
    expect(detailCall?.key).toBeNull(); // nothing fetched before a row is chosen
    await act(async () => (host.querySelector('[data-testid="suggest-record-row"]') as HTMLElement).click());
    const detail = host.querySelector('[data-testid="suggest-record-detail"]');
    expect(detail).not.toBeNull();
    const open = (id: string) => (host.querySelector(`[data-testid="${id}"]`) as HTMLDetailsElement).open;
    expect(open("detail-question")).toBe(false);
    for (const id of ["detail-input", "detail-reply", "detail-final", "detail-rates"]) expect(open(id), id).toBe(true);
    expect(text('[data-testid="detail-supply"]')).toEqual(["-"]);
    expect(text('[data-testid="detail-install"]')).toEqual(["-"]);
    expect(text('[data-testid="detail-combined"]')).toEqual(["-"]);
    expect(detail?.textContent).toContain("not yet - added when the BCS branch merges");
    expect(detail?.textContent).toContain("tokens in 1516 / out 69");
    expect(detail?.textContent).not.toContain("tokens in 0 / out 0");
    expect(detail?.textContent).toContain("THE SHARED QUESTION TEXT"); // present, folded
  });

  it("has nothing that edits or deletes a record", async () => {
    h.replies.list_records = { rows: [ROW("a", 24, "priced", [1, 2, 3])], total: 1, page: 1, page_size: 50 };
    await render();
    const buttons = text("button");
    for (const b of buttons) expect(b).not.toMatch(/save|delete|edit|use this value|freeze|suggest$/i);
  });
});
