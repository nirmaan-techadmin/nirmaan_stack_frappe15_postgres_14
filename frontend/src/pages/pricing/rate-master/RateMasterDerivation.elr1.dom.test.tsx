// @vitest-environment jsdom
//
// ELR-1 AC6 / Q4 (owner 2026-10-27): the Derivation TAB as rendered -- wiring & cabling shows its rules list and NO
// extraction Rules card (no raw ids); the other eleven Electrical categories keep today's pointer line and card.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { describe, expect, it } from "vitest";
import path from "path";
import { pathToFileURL } from "url";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";
import { RateMasterDerivation } from "./RateMasterDerivation";
import type { RateCategoryConfig, RateMasterItem } from "./rateMasterTypes";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const DATA = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
const asset = readJsonFixture<never>(pathToFileURL(path.join(DATA, "rate_master_electrical_all_v67.json"))) as
  { items: RateMasterItem[]; category_configs: RateCategoryConfig[] };
const PAGE = "Electrical Pricing";

function tab(categoryId: string): HTMLElement {
  const host = document.createElement("div");
  const root = createRoot(host);
  const config = asset.category_configs.find((c) => c.category_id === categoryId)!;
  act(() => { root.render(<StrictMode><RateMasterDerivation items={asset.items} config={config} calculatorPage={PAGE} /></StrictMode>); });
  return host;
}

describe("ELR-1: the Derivation tab", () => {
  it("wiring_cabling: 'How a row is priced', thirteen lines, no pointer line, no extraction Rules card", () => {
    const host = tab("wiring_cabling");
    expect(host.querySelector('[data-testid="rate-master-item-list-order"]')).not.toBeNull();
    expect(host.querySelectorAll('[data-testid="rate-master-item-list-order"] li').length).toBe(13);
    expect(host.querySelector('[data-testid="rate-master-derivation-notice"]')).toBeNull();
    expect(host.querySelector('[data-testid="rate-master-rules-panel"]')).toBeNull();
    // NEGATIVE: the card's raw ids and field names are gone from the tab
    for (const raw of ["R10", "R11", "conduit_included", "size_mm", "applies_to"]) expect(host.textContent, raw).not.toContain(raw);
  });

  // ELR-4a (owner R-APPROVE + R-Q4, 2026-10-29) INVERTED: WAS the eleven other categories all kept the pointer line and
  // card; NOW point wiring, switches & sockets and pop-up boxes show their rules list, no pointer line and no card,
  // and the other eight are unchanged (the negative half below)
  it("ELR-4a: point wiring, switches & sockets and pop-up boxes show 'How a row is priced', no pointer line, no extraction Rules card", () => {
    for (const id of ["point_wiring", "switches_sockets", "popup_boxes"]) {
      const host = tab(id);
      expect(host.querySelectorAll('[data-testid="rate-master-item-list-order"] li').length, id).toBeGreaterThan(0);
      expect(host.querySelector('[data-testid="rate-master-derivation-notice"]'), id).toBeNull();
      expect(host.querySelector('[data-testid="rate-master-rules-panel"]'), id).toBeNull();
      for (const raw of ["R9", "R12", "R13", "S4", "P1", "applies_to", "blank_item", "conduit_handoff"]) expect(host.textContent, `${id} ${raw}`).not.toContain(raw);
    }
  });

  it("UNCHANGED: every other Electrical category shows the pointer line, and its extraction card exactly where it had one", () => {
    const line = `This category's rules are not listed yet. To see how a row is priced, open ${PAGE} -> Calculator.`;
    const listed = ["wiring_cabling", "point_wiring", "switches_sockets", "popup_boxes"];
    for (const c of asset.category_configs.filter((x) => !listed.includes(x.category_id))) {
      const host = tab(c.category_id);
      expect(host.querySelector('[data-testid="rate-master-item-list-order"]'), c.category_id).toBeNull();
      const notice = host.querySelector('[data-testid="rate-master-derivation-notice"]')?.textContent;
      if (c.category_id === "electrical_pricing_inputs") expect(notice, c.category_id).toContain("Pricing Inputs hold shared numbers");
      else expect(notice, c.category_id).toBe(line);
      const hasRules = Array.isArray((c as { rules?: unknown[] }).rules) && (c as { rules: unknown[] }).rules.length > 0;
      expect(!!host.querySelector('[data-testid="rate-master-rules-panel"]'), c.category_id).toBe(hasRules);
    }
  });
});
