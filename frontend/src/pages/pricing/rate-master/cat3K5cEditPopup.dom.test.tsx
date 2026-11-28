// @vitest-environment jsdom
/**
 * CAT-3 K5c (the owner's review, ANSWER 18):
 *  point 2 - the EDIT warning is a pop-up of the Deactivate dialog's form, asked when Save is pressed:
 *    + a change that leaves a value without a carrier -> "Save this change?", the amber box (Admin fold), Cancel / "Save anyway";
 *      "Save anyway" saves the change; the row's own button stays the plain check (no "Save anyway" in the grid);
 *    - nothing would stop working -> it saves at once, no pop-up; a failed check never blocks (it saves);
 *  point 3 - no code name: the pop-up names the row by its item name; the CSV preview shows each lost value under its column
 *    heading ("Item: ..."), never the attribute key.
 * Data: the HVAC v92 Automatic Air Vent (a non-spec Valve Package grid). jsdom + react-dom/client only.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { describe, expect, it } from "vitest";
import { RateMasterDataViewer } from "./RateMasterDataViewer";
import { UploadValuesLost, type ItemUsage } from "./ItemUsageBox";
import type { RateCategoryConfig, RateMasterItem } from "./rateMasterTypes";
import { readJsonFixture } from "../calculatorPanelParity.harness";
import path from "path";
import { pathToFileURL } from "url";

class StubResizeObserver { observe() {} unobserve() {} disconnect() {} }
if (!(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = StubResizeObserver;
}

type Asset = { items: Array<{ item_uid: string; kind: string; unit?: string | null; attributes: Record<string, string | number>; rates: Record<string, number>; item_notes?: string; labels?: Record<string, string> }>; category_configs: RateCategoryConfig[] };
const H92 = readJsonFixture<Asset>(pathToFileURL(path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data/rate_master_hvac_all_v92.json")));
const VALVE = H92.category_configs.find((c) => c.category_id === "hvac_valve_package")!;
const aav = H92.items.find((i) => i.kind === "hvac_valve_item" && i.attributes.item_name === "Automatic Air Vent")!;
const item = {
  name: aav.item_uid, item_uid: aav.item_uid, discipline: "HVAC", kind: aav.kind, unit: aav.unit ?? undefined,
  attributes: aav.attributes, rates: aav.rates, item_notes: aav.item_notes, labels: aav.labels ?? {}, label_flags: [],
} as RateMasterItem;

const STOPS: ItemUsage = { action: "edit", still_works: 3, also: [], will_stop: [
  { config: "hvac_valve_package", path: "list_spec.attribute_definitions[valve_type].values", message: "x", line: "Valve Package: the Valve type list offers it" },
] };
const NOTHING: ItemUsage = { action: "edit", still_works: 2, also: [], will_stop: [] };

function render(onItemUsage: (n: string, p?: Record<string, unknown>) => Promise<ItemUsage>, saves: unknown[]) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  act(() => {
    root.render(<StrictMode><RateMasterDataViewer items={[item]} config={VALVE} disciplineLabel="HVAC" categoryLabel="Valve Package" isAdmin
      onSaveItem={async (_n: string, patch: unknown) => { saves.push(patch); return undefined; }} onItemUsage={onItemUsage} /></StrictMode>);
  });
  return { host, cleanup: () => { act(() => root.unmount()); host.remove(); } };
}
const flush = async (ms = 0) => { await act(async () => { await new Promise((r) => setTimeout(r, ms)); }); };
const button = (root: ParentNode, text: string) => Array.from(root.querySelectorAll("button")).find((b) => (b.textContent ?? "").trim() === text);
function editValveType(host: HTMLElement) {
  act(() => { (host.querySelector('[aria-label="Edit row"]') as HTMLButtonElement).click(); });
  const input = host.querySelector('input[aria-label="Valve type value"]') as HTMLInputElement;
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  act(() => { setter.call(input, `${input.value} X`); input.dispatchEvent(new Event("input", { bubbles: true })); });
}

describe("CAT-3 K5c - the Edit pop-up; plain names", () => {
  it("+ Save on a warning change opens the pop-up naming the item; 'Save anyway' saves the change", async () => {
    const saves: unknown[] = [];
    const { host, cleanup } = render(async () => STOPS, saves);
    try {
      editValveType(host);
      expect(button(host, "Save anyway")).toBeUndefined();                       // the grid row keeps its plain check button
      act(() => { (host.querySelector('[aria-label="Save row"]') as HTMLButtonElement).click(); });
      await flush();
      const dialog = document.querySelector('[role="alertdialog"]') as HTMLElement;
      expect(dialog.textContent).toMatch(/Save this change\?/);
      expect(dialog.textContent).toContain("The change to Automatic Air Vent is not saved yet.");
      expect(dialog.textContent).not.toContain("hvac_valve_item");
      const box = dialog.querySelector('[data-testid="edit-usage-box"]') as HTMLElement;
      expect(box.textContent).toMatch(/This change leaves something without a row that carries it/);
      expect(box.querySelector('[data-testid="edit-usage-box-fold"]')).not.toBeNull();
      expect(saves).toEqual([]);
      act(() => { button(dialog, "Save anyway")!.click(); });
      await flush();
      expect(saves.length).toBe(1);
      expect(JSON.stringify(saves[0])).toContain("Automatic Air Vent X");
      expect(document.querySelector('[role="alertdialog"]')).toBeNull();
    } finally { cleanup(); }
  });

  it("- nothing would stop working: Save saves at once (no pop-up); a failed check never blocks", async () => {
    for (const usage of [async () => NOTHING, async () => { throw new Error("check failed"); }]) {
      const saves: unknown[] = [];
      const { host, cleanup } = render(usage as () => Promise<ItemUsage>, saves);
      try {
        editValveType(host);
        act(() => { (host.querySelector('[aria-label="Save row"]') as HTMLButtonElement).click(); });
        await flush();
        expect(document.querySelector('[role="alertdialog"]')).toBeNull();
        expect(saves.length).toBe(1);
      } finally { cleanup(); }
    }
  });

  it("+ the CSV preview shows each lost value under its column heading, never the attribute key", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => { root.render(<UploadValuesLost lost={{ values: [["item_name", "Automatic Air Vent", "Item"]], will_stop: [] }} />); });
    try {
      const li = host.querySelector('[data-testid="upload-values-lost"] li') as HTMLElement;
      expect(li.textContent).toBe("Item: \"Automatic Air Vent\"");
      expect(host.textContent).not.toContain("item_name");
    } finally { act(() => root.unmount()); host.remove(); }
  });
});
