// @vitest-environment jsdom
/**
 * CAT-3 K5b (cert D1 / D2, ANSWER 14 - the approved mockup: "This is the only active Automatic Air Vent."):
 *  + the Deactivate box's head and the note editor's title name the row by its OWN item name (here a non-spec Valve Package grid,
 *    where the dialog's old label is the kind) - and, since K5c (ANSWER 18), the RM-4a first line names it too;
 *  + each distinct plain line shows once in the box; the Admin fold still lists every raw place;
 *  + usageRowName's order: item_name, item, the config's identity value, then the fallback.
 * jsdom + react-dom/client only, like cat3RateMasterScreen.dom.test.tsx. Data: the HVAC v92 rate file's Automatic Air Vent row.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { describe, expect, it } from "vitest";
import { RateMasterDataViewer } from "./RateMasterDataViewer";
import { distinctLines, usageRowName, type ItemUsage } from "./ItemUsageBox";
import type { RateCategoryConfig, RateMasterItem } from "./rateMasterTypes";
import { readJsonFixture } from "../calculatorPanelParity.harness";
import path from "path";
import { pathToFileURL } from "url";

class StubResizeObserver { observe() {} unobserve() {} disconnect() {} }
if (!(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = StubResizeObserver;
}

type Asset = { discipline: string; items: Array<{ item_uid: string; kind: string; brand?: string | null; unit?: string | null; attributes: Record<string, string | number>; rates: Record<string, number>; item_notes?: string; labels?: Record<string, string> }>; category_configs: RateCategoryConfig[] };
const H92 = readJsonFixture<Asset>(pathToFileURL(path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data/rate_master_hvac_all_v92.json")));
const VALVE = H92.category_configs.find((c) => c.category_id === "hvac_valve_package")!;
const aav = H92.items.find((i) => i.kind === "hvac_valve_item" && i.attributes.item_name === "Automatic Air Vent")!;
const item: RateMasterItem = {
  name: aav.item_uid, item_uid: aav.item_uid, discipline: "HVAC", kind: aav.kind, unit: aav.unit ?? undefined,
  attributes: aav.attributes, rates: aav.rates, item_notes: aav.item_notes, labels: aav.labels ?? {}, label_flags: [],
} as RateMasterItem;

const LINE = "Valve Package: the working note \"One price for an automatic air vent of any size\"";
const USAGE: ItemUsage = { action: "deactivate", still_works: 3, also: [], will_stop: [
  { config: "hvac_valve_package", path: "list_spec.text_notes[3].line", message: "a working note names it", line: LINE },
  { config: "hvac_valve_package", path: "list_spec.pricing.families.Automatic Air Vent.note", message: "a working note names it", line: LINE },
  { config: "hvac_valve_package", path: "list_spec.pricing.families.Automatic Air Vent", message: "a price rule names it", line: "Valve Package: the price rule for \"Automatic Air Vent\"" },
] };

function render(extra: Partial<Parameters<typeof RateMasterDataViewer>[0]> = {}) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  act(() => {
    root.render(<StrictMode><RateMasterDataViewer items={[item]} config={VALVE} disciplineLabel="HVAC" categoryLabel="Valve Package" isAdmin
      onSaveItem={async () => undefined} onDeactivateItem={async () => undefined} onSaveNote={async () => undefined} onItemUsage={async () => USAGE} {...extra} /></StrictMode>);
  });
  return { host, cleanup: () => { act(() => root.unmount()); host.remove(); } };
}
const flush = async (ms = 0) => { await act(async () => { await new Promise((r) => setTimeout(r, ms)); }); };
const button = (root: ParentNode, text: string) => Array.from(root.querySelectorAll("button")).find((b) => (b.textContent ?? "").trim() === text);

describe("CAT-3 K5b - the row named by its own item name; each plain line once", () => {
  it("the fixture is the v92 Automatic Air Vent on a non-spec grid (the old label is the kind)", () => {
    expect(aav.item_notes).toMatch(/^One price for an automatic air vent of any size/);
    expect(VALVE.identity_attribute_id ?? null).not.toBe("item_name");
  });

  it("+ Deactivate: the head names 'Automatic Air Vent' (the mockup); the RM-4a first line names it too (K5c); one line shown once, the fold keeps both", async () => {
    const { host, cleanup } = render();
    try {
      act(() => { (host.querySelector('[aria-label="Deactivate row"]') as HTMLButtonElement).click(); });
      await flush();
      const dialog = document.querySelector('[role="alertdialog"]') as HTMLElement;
      const box = dialog.querySelector('[data-testid="deactivate-usage-box"]') as HTMLElement;
      expect(box.textContent).toContain("This is the only active Automatic Air Vent. These stop working");
      expect(box.textContent).not.toContain("hvac_valve_item");
      // PIN P-K5c3 (ANSWER 18 point 3): the RM-4a line names the row too - BEFORE (ANSWER 14): "hvac_valve_item will drop ..."
      expect(dialog.textContent).toMatch(/Automatic Air Vent will drop from the active list/);
      expect(dialog.textContent).not.toContain("hvac_valve_item");
      const items = Array.from(box.querySelectorAll(":scope > ul > li")).map((li) => li.textContent);
      expect(items.filter((t) => t === LINE).length).toBe(1);
      expect(items.length).toBe(2);
      const fold = Array.from(box.querySelectorAll('[data-testid="deactivate-usage-box-fold"] li')).map((li) => li.textContent ?? "");
      expect(fold.length).toBe(3);                                                                 // every raw place stays in the fold
      expect(fold.filter((t) => t.includes("a working note names it")).length).toBe(2);
      act(() => { button(dialog, "Cancel")!.click(); });
    } finally { cleanup(); }
  });

  it("+ the note editor's title names the item", async () => {
    const { host, cleanup } = render();
    try {
      act(() => { (host.querySelector('[aria-label="Edit note"]') as HTMLButtonElement).click(); });
      await flush();
      const dialog = document.querySelector('[role="dialog"]') as HTMLElement;
      expect(dialog.textContent).toContain("Note on Automatic Air Vent");
      expect(dialog.textContent).not.toContain("Note on hvac_valve_item");
      act(() => { button(dialog, "Cancel")!.click(); });
    } finally { cleanup(); }
  });

  it("usageRowName: item_name, then item, then the identity value, then the fallback; distinctLines keeps first-seen order", () => {
    expect(usageRowName({ item_name: "A", item: "B", valve_type: "C" }, "valve_type", "kind")).toBe("A");
    expect(usageRowName({ item: "B", valve_type: "C" }, "valve_type", "kind")).toBe("B");
    expect(usageRowName({ valve_type: "C" }, "valve_type", "kind")).toBe("C");
    expect(usageRowName({ item_name: "  " }, null, "hvac_valve_item ")).toBe("hvac_valve_item");
    expect(distinctLines(USAGE.will_stop)).toEqual([LINE, "Valve Package: the price rule for \"Automatic Air Vent\""]);
  });
});
