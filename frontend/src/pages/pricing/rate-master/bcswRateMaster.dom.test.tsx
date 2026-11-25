// @vitest-environment jsdom
//
// BCS-W -- RATE MASTER, ELECTRICAL: the FORMULA row's BoQ / BCS sections, the explanation line once, and the Pricing Input
// remarks worked out from the row's values in their two sections. The REAL Data Viewer over the newest Electrical and HVAC
// rate files (latest-asset readers by file prefix).
//
// What each case protects (owner R2 13:12, R4 23:31, Question 1 answer 1a; the approved mockup boards 1 / 2):
//   (+) an Electrical FORMULA cell with cost lines: ONE green "BoQ - what we quote the customer" header over the price lines and
//       ONE blue "BCS - our cost" header over the cost lines; plain words (no "ruling", "none_skips", "x 0.7", "thickness_sqmm");
//   (-) a cell with no cost line shows the BoQ section only;
//   (+) the explanation-row line shows once on an Electrical FORMULA row;
//   (-) an HVAC FORMULA row is unchanged: no section, the explanation line under both formula columns;
//   (+) a Pricing Input remark: its price sentence in the BoQ section, its cost sentence in the BCS section, the example worked
//       out from the row's CURRENT value -- a fixture value changed -> the example changed;
//   (-) an HVAC Pricing Input remark is drawn as stored.
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import { pathToFileURL } from "url";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";

import { RateMasterDataViewer } from "./RateMasterDataViewer";
import { DERIVED_COPY } from "./rateMasterSpec";
import { columnNoteSections } from "./rateMasterFormulaSections";
import { categoryItemKinds } from "./rateMasterStructure";
import { SECTION_TAG } from "@/pages/boq-wizard/rate-helper/PriceSection";
import type { RateCategoryConfig, RateMasterItem } from "./rateMasterTypes";

class StubResizeObserver { observe() { /* no layout */ } unobserve() { /* no layout */ } disconnect() { /* no layout */ } }
if (!(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = StubResizeObserver;
}
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const DATA_DIR = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
const newest = (prefix: string) => path.join(DATA_DIR, fs.readdirSync(DATA_DIR).filter((f) => new RegExp(`^${prefix}\\d+\\.json$`).test(f))
  .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!);
type Asset = { discipline: string; category_configs: RateCategoryConfig[]; items: Array<Record<string, unknown> & { kind: string; item_uid: string; rates: Record<string, number>; attributes: Record<string, string | number> }> };
const ELEC = readJsonFixture<Asset>(pathToFileURL(newest("rate_master_electrical_all_v")));
const HVAC = readJsonFixture<Asset>(pathToFileURL(newest("rate_master_hvac_all_v")));
const cfgOf = (a: Asset, id: string) => ({ ...a.category_configs.find((c) => c.category_id === id)!, discipline: a.discipline }) as RateCategoryConfig;
const itemsOf = (a: Asset, kinds: string[], limit = 30): RateMasterItem[] => a.items.filter((i) => kinds.includes(i.kind)).slice(0, limit)
  .map((i) => ({ name: i.item_uid, item_uid: i.item_uid, discipline: a.discipline, kind: i.kind, attributes: i.attributes, rates: i.rates } as RateMasterItem));

let root: Root | null = null;
let host: HTMLDivElement | null = null;
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });
function render(items: RateMasterItem[], config: RateCategoryConfig, discipline: string) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(<RateMasterDataViewer items={items} config={config} disciplineLabel={discipline} categoryLabel={config.category_id} />));
  return host;
}
const count = (text: string, needle: string) => text.split(needle).length - 1;

describe("BCS-W Rate Master FORMULA row, Electrical", () => {
  it("(+) Wiring's List price per mtr: one BoQ header over the price lines, one BCS header over the cost lines, plain words", () => {
    const cfg = cfgOf(ELEC, "wiring_cabling");
    const h = render(itemsOf(ELEC, categoryItemKinds(cfg), 2000), cfg, "Electrical");
    const cell = h.querySelector("[data-testid='formula-note-list_price_per_mtr']")!;
    expect(count(cell.textContent!, SECTION_TAG.boq)).toBe(1);
    expect(count(cell.textContent!, SECTION_TAG.bcs)).toBe(1);
    const boq = cell.querySelector("[data-testid='price-section-boq']")!.textContent!;
    const bcs = cell.querySelector("[data-testid='price-section-bcs']")!.textContent!;
    expect(boq).toContain("Cable: list price less the supplier discount, plus our supply markup.");
    expect(bcs).toContain("Cable at list less the supplier discount, plus wastage instead of markup");
    expect(bcs).not.toContain("BCS:");
    for (const bad of ["ruling", "none_skips", "x 0.7", "thickness_sqmm"]) expect(cell.textContent).not.toContain(bad);
    const gland = h.querySelector("[data-testid='formula-note-gland_band1_list']")!;
    expect(gland.querySelector("[data-testid='price-section-boq']")!.textContent).toContain("Used when the cable is under 35 sq mm.");
    expect(gland.querySelector("[data-testid='price-section-bcs']")!.textContent).toContain("The gland at list less its discount, no markup.");
  });
  it("(-) a cell with no cost line shows the BoQ section only", () => {
    const h = render(itemsOf(ELEC, ["db_switchgear_item", "db_shell"]), cfgOf(ELEC, "db_switchgear"), "Electrical");
    const cell = h.querySelector("[data-testid='formula-note-list_price']")!;
    expect(cell.querySelector("[data-testid='price-section-boq']")).not.toBeNull();
    expect(cell.querySelector("[data-testid='price-section-bcs']")).toBeNull();
    expect(columnNoteSections(cfgOf(ELEC, "db_switchgear"), "list_price").bcs).toEqual([]);
  });
  it("(+) the explanation-row line once per Electrical FORMULA row", () => {
    const h = render(itemsOf(ELEC, ["industrial_socket"]), cfgOf(ELEC, "industrial_sockets"), "Electrical");
    expect(count(h.querySelector("[data-testid='formula-row']")!.textContent!, DERIVED_COPY.formulaRowHint)).toBe(1);
    // the pop-up / socket cost line no longer repeats its price line
    const cell = h.querySelector("[data-testid='formula-note-list_price']")!;
    expect(cell.querySelector("[data-testid='price-section-bcs']")!.textContent).toContain("Paired MCB at list less the switchgear discount");
    expect(cell.textContent).not.toMatch(/\bx[01]\b/);
  });
  it("(-) an HVAC FORMULA row is unchanged: no section, the explanation line under both formula columns", () => {
    const cfg = HVAC.category_configs.find((c) => c.category_id === "hvac_insulation")!; // the reference DOM test's HVAC category
    const kinds = categoryItemKinds(cfg);
    const h = render(itemsOf(HVAC, kinds), { ...cfg, discipline: "HVAC" } as RateCategoryConfig, "HVAC");
    const row = h.querySelector("[data-testid='formula-row']")!;
    expect(row.querySelector("[data-testid^='price-section']")).toBeNull();
    expect(count(row.textContent!, DERIVED_COPY.formulaRowHint)).toBe(2);
  });
});

describe("BCS-W Rate Master Pricing Inputs, Electrical: the live remarks", () => {
  const PI = cfgOf(ELEC, "electrical_pricing_inputs");
  const pis = itemsOf(ELEC, ["electrical_pricing_input"], 100);
  const rowText = (h: HTMLElement, name: string) => [...h.querySelectorAll("tr")].find((tr) => tr.textContent!.includes(name))!;
  it("(+) Armoured cable: the price sentence in the BoQ section, the cost sentence in the BCS section, today's figures", () => {
    const h = render(pis, PI, "Electrical");
    const tr = rowText(h, "Armoured cable discount, supply markup & wastage");
    const cell = tr.querySelector("[data-testid='pi-remark-sections']")!;
    expect(cell.querySelector("[data-testid='price-section-boq']")!.textContent).toContain("quoted at Rs 411/m");
    expect(cell.querySelector("[data-testid='price-section-bcs']")!.textContent).toContain("It costs us Rs 319/m");
    expect(cell.textContent).not.toContain("{");
  });
  it("(+) the example follows the row's value: discount 0.75 -> 0.70 in the fixture moves Rs 411 to Rs 493", () => {
    const moved = pis.map((i) => (i.attributes?.item === "cable_arm" ? { ...i, rates: { ...i.rates, discount: 0.7 } } : i));
    const h = render(moved, PI, "Electrical");
    const cell = rowText(h, "Armoured cable discount, supply markup & wastage").querySelector("[data-testid='pi-remark-sections']")!;
    expect(cell.textContent).toContain("quoted at Rs 493/m");
    expect(cell.textContent).not.toContain("Rs 411/m");
  });
  it("(+) Switchgear and the Pop-up box supply BCS ratio show their two sections", () => {
    const h = render(pis, PI, "Electrical");
    const sw = rowText(h, "Switchgear discount & supply markup").querySelector("[data-testid='pi-remark-sections']")!;
    expect(sw.querySelector("[data-testid='price-section-boq']")!.textContent).toContain("quoted at Rs 3,113");
    expect(sw.querySelector("[data-testid='price-section-bcs']")!.textContent).toContain("It costs us Rs 1,886");
    const pop = rowText(h, "Pop-up box supply BCS ratio").querySelector("[data-testid='pi-remark-sections']")!;
    expect(pop.querySelector("[data-testid='price-section-bcs']")!.textContent).toContain("costs us Rs 720");
  });
  it("(-) an HVAC Pricing Input remark is drawn as stored (no section)", () => {
    const hpi = HVAC.category_configs.find((c) => c.category_id === "hvac_pricing_inputs")!;
    const kinds = (hpi as unknown as { item_kinds?: string[] }).item_kinds ?? ["hvac_pricing_input"];
    const h = render(itemsOf(HVAC, kinds, 100), { ...hpi, discipline: "HVAC" } as RateCategoryConfig, "HVAC");
    expect(h.querySelector("[data-testid='pi-remark-sections']")).toBeNull();
  });
});
