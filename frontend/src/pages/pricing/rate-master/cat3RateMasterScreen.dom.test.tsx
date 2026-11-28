// @vitest-environment jsdom
/**
 * CAT-3 T6 (owner 2026-11-26 01:14 "1 approved" -- the mockup; R5 / R6; ANSWER 2): the Rate Master screen parts, rendered.
 *  + the Notes and Labels columns; label chips in the row's OWN words ("Conductor: ..." from its material), never an internal value;
 *  + the amber "could not label" chip and, for Admin, the line above the grid that filters to those rows -- absent at 0;
 *  + Deactivate: the amber box, its details fold (Admin), the green "still works" line, "Deactivate anyway"; no box when nothing stops;
 *  + Edit: as soon as a changed value would leave something without a carrier, the box shows and the button reads "Save anyway";
 *  + the CSV preview section "Values no row will carry after this upload";
 *  - a non-Admin sees no note pencil and no actions (so no fold).
 * jsdom + react-dom/client only (no @testing-library), like RateMasterDataViewer.dom.test.tsx.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { describe, expect, it } from "vitest";
import { RateMasterDataViewer } from "./RateMasterDataViewer";
import { UploadValuesLost, type ItemUsage } from "./ItemUsageBox";
import { LABEL_VALUES } from "@/pages/boq-wizard/rate-helper/catalogueLabels";
import type { RateCategoryConfig, RateMasterItem } from "./rateMasterTypes";
import { readJsonFixture } from "../calculatorPanelParity.harness";
import path from "path";
import { pathToFileURL } from "url";

class StubResizeObserver { observe() {} unobserve() {} disconnect() {} }
if (!(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = StubResizeObserver;
}

type Asset = { discipline: string; items: Array<{ item_uid: string; kind: string; brand?: string | null; unit?: string | null; attributes: Record<string, string | number>; rates: Record<string, number>; source?: { sheet?: string; row?: number }; labels?: Record<string, string> }>; category_configs: RateCategoryConfig[] };
const E72 = readJsonFixture<Asset>(pathToFileURL(path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data/rate_master_electrical_all_v72.json")));
const WIRING = E72.category_configs.find((c) => c.category_id === "wiring_cabling")!;
const cables = E72.items.filter((i) => i.kind === "cable").slice(0, 3);
const toItem = (it: Asset["items"][number], extra: Partial<RateMasterItem> = {}): RateMasterItem => ({
  name: it.item_uid, item_uid: it.item_uid, discipline: E72.discipline, kind: it.kind, brand: it.brand ?? undefined, unit: it.unit ?? undefined,
  attributes: it.attributes, rates: it.rates, source_sheet: it.source?.sheet, source_row: it.source?.row,
  labels: it.labels ?? {}, label_flags: [], ...extra,
});
// a pretend new SKU the rule could not label (the mockup's scratch row): saved and priced as before, flagged
const flagged = toItem(cables[0], {
  name: "cat3-flagged", item_uid: "rmi-cat3-flagged", attributes: { ...cables[0].attributes, material: "MYSTERY METAL" },
  labels: { armour: cables[0].labels?.armour ?? "" }, label_flags: [{ label: "conductor", value: "MYSTERY METAL", reason: "no case matches" }],
});

const STOPS: ItemUsage = { action: "deactivate", still_works: 4, also: [], will_stop: [
  { config: "wiring_cabling", path: "list_spec.pricing.families.X", message: "names material = 'X' - no active SKU carries it", line: "Wiring: the price rule for \"X\" - its rows will show no SKU and must be priced by hand" },
] };
const NOTHING: ItemUsage = { action: "deactivate", still_works: 2, also: [], will_stop: [] };

function render(items: RateMasterItem[], extra: Partial<Parameters<typeof RateMasterDataViewer>[0]> = {}) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  act(() => {
    root.render(<StrictMode><RateMasterDataViewer items={items} config={WIRING} disciplineLabel="Electrical" categoryLabel="Wiring" {...extra} /></StrictMode>);
  });
  return { host, cleanup: () => { act(() => root.unmount()); host.remove(); } };
}
const headers = (host: HTMLElement) => Array.from(host.querySelectorAll("th")).map((th) => (th.textContent ?? "").trim());
const flush = async (ms = 0) => { await act(async () => { await new Promise((r) => setTimeout(r, ms)); }); };
const button = (root: ParentNode, text: string) => Array.from(root.querySelectorAll("button")).find((b) => (b.textContent ?? "").trim() === text);

describe("CAT-3 the Rate Master screen", () => {
  it("+ Notes and Labels columns; chips in the row's own words, never an internal label value", () => {
    const { host, cleanup } = render(cables.map((c) => toItem(c)), { isAdmin: true, onSaveItem: async () => undefined, onSaveNote: async () => undefined });
    try {
      expect(headers(host)).toEqual(expect.arrayContaining(["Notes", "Labels"]));
      const chips = Array.from(host.querySelectorAll('[data-testid="label-chip"]')).map((c) => c.textContent ?? "");
      expect(chips.length).toBeGreaterThan(0);
      expect(chips.some((c) => /^Conductor: [A-Z][a-z]+$/.test(c))).toBe(true);
      const internal = [...LABEL_VALUES.conductor, ...LABEL_VALUES.armour];
      for (const c of chips) expect(internal.some((v) => c.endsWith(`: ${v}`))).toBe(false);
      expect(host.querySelectorAll('[aria-label="Edit note"]').length).toBe(3);          // Admin: a pencil per row
      expect(host.querySelector('[data-testid="flagged-rows-filter"]')).toBeNull();      // nobody flagged: no line
    } finally { cleanup(); }
  });

  it("+ the amber chip and the Admin line that filters to the flagged rows", () => {
    const { host, cleanup } = render([...cables.map((c) => toItem(c)), flagged], { isAdmin: true, onSaveItem: async () => undefined });
    try {
      const amber = host.querySelectorAll('[data-testid="label-flag-chip"]');
      expect(amber.length).toBe(1);
      expect(amber[0].textContent).toBe("could not label: conductor");
      expect((amber[0] as HTMLElement).title).toMatch(/saved and priced as before/);
      const line = host.querySelector('[data-testid="flagged-rows-filter"]') as HTMLButtonElement;
      expect(line.textContent).toMatch(/^1 row could not be labelled/);
      act(() => { line.click(); });
      expect(host.querySelectorAll('[data-testid="item-labels"]').length).toBe(1);    // only the flagged row is shown
    } finally { cleanup(); }
  });

  it("- a non-Admin sees no note pencil, no actions (no fold), and no Admin line; the chip still shows", () => {
    const { host, cleanup } = render([...cables.map((c) => toItem(c, { item_notes: "a fact" })), flagged], { isAdmin: false });
    try {
      expect(host.querySelectorAll('[aria-label="Edit note"]').length).toBe(0);
      expect(host.querySelectorAll('[aria-label="Deactivate row"]').length).toBe(0);
      expect(host.querySelector('[data-testid="flagged-rows-filter"]')).toBeNull();
      expect(host.querySelectorAll('[data-testid="label-flag-chip"]').length).toBe(1);
      expect(Array.from(host.querySelectorAll('[data-testid="item-note"]')).some((n) => n.textContent === "a fact")).toBe(true);
    } finally { cleanup(); }
  });

  it("+ Deactivate shows what stops, the fold and 'Deactivate anyway'; no box when nothing stops", async () => {
    for (const [usage, warns] of [[STOPS, true], [NOTHING, false]] as const) {
      const { host, cleanup } = render(cables.map((c) => toItem(c)), {
        isAdmin: true, onSaveItem: async () => undefined, onDeactivateItem: async () => undefined, onItemUsage: async () => usage,
      });
      try {
        act(() => { (host.querySelector('[aria-label="Deactivate row"]') as HTMLButtonElement).click(); });
        await flush();
        const dialog = document.querySelector('[role="alertdialog"]') as HTMLElement;
        expect(dialog).not.toBeNull();
        expect(dialog.textContent).toMatch(/Deactivate this rate row\?/);
        if (warns) {
          expect(dialog.querySelector('[data-testid="deactivate-usage-box"]')).not.toBeNull();
          expect(dialog.querySelector('[data-testid="deactivate-usage-box-fold"]')).not.toBeNull();
          expect(dialog.querySelector('[data-testid="deactivate-usage-box-still"]')?.textContent).toMatch(/^4 other settings/);
          expect(button(dialog, "Deactivate anyway")).toBeDefined();
          expect(dialog.textContent).toMatch(/the price rule for "X"/);
        } else {
          expect(dialog.querySelector('[data-testid="deactivate-usage-box"]')).toBeNull();
          expect(dialog.querySelector('[data-testid="deactivate-usage-box-nothing"]')).not.toBeNull();
          expect(button(dialog, "Deactivate")).toBeDefined();
          expect(button(dialog, "Deactivate anyway")).toBeUndefined();
        }
        act(() => { button(dialog, "Cancel")!.click(); });
      } finally { cleanup(); }
    }
  });

  // PIN P-K5c2 (owner review point 2, ANSWER 18): the Edit warning is a POP-UP of the Deactivate dialog's form, asked on Save -
  // BEFORE: an inline box in the actions column while typing (debounced) and the row button reading "Save anyway".
  it("+ Edit: Save on a change that leaves a value without a carrier opens the pop-up (Cancel / 'Save anyway'); Cancel saves nothing", async () => {
    const asked: Array<Record<string, unknown> | undefined> = [];
    let saved = 0;
    const { host, cleanup } = render(cables.map((c) => toItem(c)), {
      isAdmin: true, onSaveItem: async () => { saved += 1; return undefined; },
      onItemUsage: async (_n, proposed) => { asked.push(proposed); return { ...STOPS, action: "edit" }; },
    });
    try {
      act(() => { (host.querySelector('[aria-label="Edit row"]') as HTMLButtonElement).click(); });
      const input = host.querySelector("tbody input") as HTMLInputElement;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      act(() => { setter.call(input, `${input.value}-renamed`); input.dispatchEvent(new Event("input", { bubbles: true })); });
      await flush(500);
      expect(asked).toEqual([]);                                                       // typing asks nothing
      expect(host.querySelector('[data-testid="edit-usage-box"]')).toBeNull();          // no inline box any more
      act(() => { (host.querySelector('[aria-label="Save row"]') as HTMLButtonElement).click(); });
      await flush();
      expect(asked.length).toBe(1);
      const dialog = document.querySelector('[role="alertdialog"]') as HTMLElement;
      expect(dialog.textContent).toMatch(/Save this change\?/);
      expect(dialog.querySelector('[data-testid="edit-usage-box"]')).not.toBeNull();
      expect(button(dialog, "Save anyway")).toBeDefined();
      act(() => { button(dialog, "Cancel")!.click(); });
      await flush();
      expect(document.querySelector('[role="alertdialog"]')).toBeNull();
      expect(saved).toBe(0);
    } finally { cleanup(); }
  });

  it("+ the CSV preview lists the values no row will carry; nothing when none", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => { root.render(<UploadValuesLost lost={{ values: [["valve_type", "Dual Plate"]], will_stop: STOPS.will_stop }} />); });
    expect(host.textContent).toMatch(/Values no row will carry after this upload \(1\)/);
    expect(host.textContent).toMatch(/valve_type: "Dual Plate"/);
    expect(host.textContent).toMatch(/The upload itself is not blocked/);
    act(() => { root.render(<UploadValuesLost lost={{ values: [], will_stop: [] }} />); });
    expect(host.textContent).toBe("");
    act(() => root.unmount()); host.remove();
  });
});
