// @vitest-environment jsdom
//
// BCS-6b K1 -- THE PRICING PAGES (owner R-BCS-152 Q2 b / Q3 a / Q5 a; board 4; Answer 1 Q1-D).
//   (+) Electrical Pricing opens straight on the Calculator: NO tab strip, and the sheet is never mounted (no workbook read
//       is even prepared, no Sandbox button) - so the Electrical workbook and its Sandbox cannot be opened;
//   (+) HVAC Pricing keeps its tab strip (Spreadsheet + Calculator) and opens on the Spreadsheet;
//   (+) ELV Pricing is unchanged: the Spreadsheet alone, no strip (it has no Calculator);
//   (+) the switch is ONE value: Electrical with `spreadsheet: true` gets its strip back, opening on the Spreadsheet;
//   (+) THE CARRY-OVER: Calculator chosen on HVAC -> Electrical -> back to HVAC opens HVAC on ITS default (the Spreadsheet);
//       before BCS-6b the three routes shared one page instance and the chosen tab came along.
// The sheet's data calls never resolve here (the loader is stubbed), so the sheet stays in its loading state: what is
// asserted is WHICH component mounts and which workbook reads it prepares - never a workbook's content.
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";

const h = vi.hoisted(() => ({
  methods: [] as string[],
  electricalSpreadsheet: false,
}));
vi.mock("frappe-react-sdk", () => ({
  useFrappePostCall: (method: string) => {
    h.methods.push(method);
    return { call: () => new Promise(() => {}) };
  },
}));
vi.mock("@/hooks/useUserData", () => ({
  useUserData: () => ({ full_name: "Test", user_id: "someone@example.invalid", role: "Nirmaan Admin Profile" }),
}));
vi.mock("./pricingLibs", async (orig) => ({ ...(await orig<typeof import("./pricingLibs")>()), loadPricingLibs: () => new Promise(() => {}) }));
vi.mock("./PricingCalculator", async (orig) => ({
  ...(await orig<typeof import("./PricingCalculator")>()),
  PricingCalculator: ({ discipline }: { discipline: string }) => <div data-testid="calculator">Calculator for {discipline}</div>,
}));
vi.mock("./pricingWorkbooks", async (orig) => {
  const real = await orig<typeof import("./pricingWorkbooks")>();
  // A test seam ONLY for the "one value brings it back" case: the registry is read through these two functions.
  const entries = () => real.PRICING_WORKBOOKS.map((w) => (w.path === "/electrical-pricing" && h.electricalSpreadsheet ? { ...w, spreadsheet: true } : w));
  const workbookForPath = (p: string) => {
    const first = `/${(p || "").split("/").filter(Boolean)[0] ?? ""}`;
    return entries().find((w) => w.path === first);
  };
  return {
    ...real,
    workbookForPath,
    spreadsheetOnForPath: (p: string, hasCalculator: boolean) => {
      const e = workbookForPath(p);
      return !hasCalculator || !e || e.spreadsheet;
    },
  };
});
import { PricingWorkbookPage } from "./PricingWorkbookPage";
import { PRICING_WORKBOOKS, spreadsheetOnForPath } from "./pricingWorkbooks";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
let nav: (p: string) => void = () => {};
function Nav() {
  nav = useNavigate();
  return null;
}
async function mount(path: string) {
  // The same shape as routesConfig.tsx: three sibling routes, the same element at the same place.
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <Nav />
        <Routes>
          {["hvac-pricing", "electrical-pricing", "elv-pricing"].map((p) => (
            <Route key={p} path={p} element={<PricingWorkbookPage />} />
          ))}
        </Routes>
      </MemoryRouter>,
    );
  });
}
const strip = () => host.querySelector('[role="tablist"][aria-label="Pricing views"]');
const tabs = () => Array.from(host.querySelectorAll('[role="tab"]')).map((t) => `${t.textContent}${t.getAttribute("aria-selected") === "true" ? "*" : ""}`);
const calc = () => host.querySelector('[data-testid="calculator"]')?.textContent ?? null;
const sheetReads = () => h.methods.filter((m) => /\.(list_workbooks|get_workbook|checkout)$/.test(m));

beforeEach(() => {
  h.methods = [];
  h.electricalSpreadsheet = false;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("BCS-6b - the Spreadsheet switch (one value per discipline)", () => {
  it("the registry: Electrical off, HVAC and ELV on", () => {
    expect(Object.fromEntries(PRICING_WORKBOOKS.map((w) => [w.path, w.spreadsheet]))).toEqual({
      "/hvac-pricing": true, "/electrical-pricing": false, "/elv-pricing": true,
    });
  });
  it("(-) a page without a Calculator always shows its Spreadsheet, whatever the switch says", () => {
    expect(spreadsheetOnForPath("/elv-pricing", false)).toBe(true);
    expect(spreadsheetOnForPath("/electrical-pricing", false)).toBe(true);
    expect(spreadsheetOnForPath("/electrical-pricing", true)).toBe(false);
    expect(spreadsheetOnForPath("/hvac-pricing", true)).toBe(true);
  });
});

describe("BCS-6b - Electrical Pricing opens on the Calculator", () => {
  it("(+) Electrical: the Calculator, NO tab strip, the sheet never mounted (no workbook read prepared, no Sandbox)", async () => {
    await mount("/electrical-pricing");
    expect(calc()).toBe("Calculator for Electrical");
    expect(strip()).toBeNull();
    expect(host.textContent).not.toMatch(/Spreadsheet|Sandbox/);
    expect(sheetReads()).toEqual([]);
  });
  it("(+) HVAC: the strip (Spreadsheet + Calculator), opening on the Spreadsheet, the sheet mounted", async () => {
    await mount("/hvac-pricing");
    expect(strip()).not.toBeNull();
    expect(tabs()).toEqual(["Spreadsheet*", "Calculator"]);
    expect(calc()).toBeNull();
    expect(sheetReads().length).toBeGreaterThan(0);
  });
  it("(+) ELV unchanged: the Spreadsheet alone, no strip, no Calculator", async () => {
    await mount("/elv-pricing");
    expect(strip()).toBeNull();
    expect(calc()).toBeNull();
    expect(sheetReads().length).toBeGreaterThan(0);
  });
  it("(+) the one value back on: Electrical gets its strip again, opening on the Spreadsheet", async () => {
    h.electricalSpreadsheet = true;
    await mount("/electrical-pricing");
    expect(tabs()).toEqual(["Spreadsheet*", "Calculator"]);
    expect(calc()).toBeNull();
  });
});

describe("BCS-6b - the chosen tab is not carried across Pricing pages", () => {
  it("(+) Calculator on HVAC -> Electrical -> HVAC: HVAC opens on its own default, the Spreadsheet", async () => {
    await mount("/hvac-pricing");
    const calcTab = Array.from(host.querySelectorAll('[role="tab"]')).find((t) => t.textContent === "Calculator") as HTMLElement;
    await act(async () => calcTab.click());
    expect(tabs()).toEqual(["Spreadsheet", "Calculator*"]);
    expect(calc()).toBe("Calculator for HVAC");
    await act(async () => nav("/electrical-pricing"));
    expect(strip()).toBeNull();
    expect(calc()).toBe("Calculator for Electrical");
    await act(async () => nav("/hvac-pricing"));
    expect(tabs()).toEqual(["Spreadsheet*", "Calculator"]);
    expect(calc()).toBeNull();
  });
  it("(+) Calculator on HVAC -> ELV -> HVAC: HVAC opens on the Spreadsheet again (no page carries the tab)", async () => {
    await mount("/hvac-pricing");
    const calcTab = Array.from(host.querySelectorAll('[role="tab"]')).find((t) => t.textContent === "Calculator") as HTMLElement;
    await act(async () => calcTab.click());
    await act(async () => nav("/elv-pricing"));
    expect(strip()).toBeNull();
    await act(async () => nav("/hvac-pricing"));
    expect(tabs()).toEqual(["Spreadsheet*", "Calculator"]);
  });
});
