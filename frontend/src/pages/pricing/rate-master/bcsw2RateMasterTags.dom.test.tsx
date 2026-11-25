// @vitest-environment jsdom
//
// BCS-W2 -- RATE MASTER'S COLUMN-HEADER TAGS, AS THE OWNER RULED (Question 1 answer, 2026-11-25 16:16 "ok for both"):
//   point 1 (a) the five grey words ("List price", "BCS price", "BCS price (install)", "BoQ price", "BoQ price (install)") are
//   REMOVED from the Data Viewer's column headers on screen, on all 22 Electrical columns; the title and the code name under it
//   stay; HVAC (no words today) unchanged. Point 2 (a) the download keeps its words: the deriver the exporter's twin pins is untouched.
// The REAL viewer over the newest rate files (a latest-asset reader by file prefix: rate_master_electrical_all_v /
// rate_master_hvac_all_v), every category with rows. It also PRINTS, per category, every header's grey word (P5c's tag list).
//
// What each case protects:
//   (+) no Electrical or HVAC header carries a grey word beside its title (none of the five, nor any other);
//   (-) the code name under every rate column's title is still drawn, one per column, equal to the column's key (every grid that
//       draws code names: all of Electrical, ADP; the other HVAC grids never drew them);
//   (-) the derived kind itself is unchanged where the download reads it (the TypeScript twin of the exporter's deriver):
//       Pop up Boxes' supply_per_module still derives "BCS price" and its install_per_module "BoQ price (install)".
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { describe, expect, it } from "vitest";
import path from "path";
import { readdirSync } from "fs";
import { pathToFileURL } from "url";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";

import { RateMasterDataViewer } from "./RateMasterDataViewer";
import { columnOrderForFile, deriveRateColumnLabels, isPricingInputConfig, pricingInputUsedBy, rateColumnLabel } from "./rateMasterSpec";
import { categoryItemKinds, isCategoryDataScopeEmpty } from "./rateMasterStructure";
import type { RateCategoryConfig, RateMasterItem } from "./rateMasterTypes";

class StubResizeObserver { observe() { /* no layout */ } unobserve() { /* no layout */ } disconnect() { /* no layout */ } }
if (!(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = StubResizeObserver;
}
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

interface Asset {
  discipline: string;
  category_configs: RateCategoryConfig[];
  items: Array<{ kind: string; brand?: string | null; unit?: string | null; attributes: Record<string, unknown>;
                 rates: Record<string, number>; item_uid: string; source?: { sheet?: string; row?: number } }>;
}
const DATA_DIR = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
const newest = (prefix: string) => readdirSync(DATA_DIR).filter((f) => new RegExp(`^${prefix}\\d+\\.json$`).test(f))
  .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
const load = (prefix: string) => readJsonFixture<never>(pathToFileURL(path.join(DATA_DIR, newest(prefix)))) as Asset;
const ASSETS: Asset[] = [load("rate_master_electrical_all_v"), load("rate_master_hvac_all_v")];
const THE_FIVE = ["List price", "BCS price", "BCS price (install)", "BoQ price", "BoQ price (install)"];

/** The items as `get_rate_master_items` hands them to the page (as RateMasterDataViewer.file.dom.test.tsx). */
function feed(asset: Asset): RateMasterItem[] {
  return asset.items.map((it) => ({
    name: it.item_uid, item_uid: it.item_uid, discipline: asset.discipline, kind: it.kind,
    brand: it.brand ?? undefined, unit: it.unit ?? undefined,
    attributes: { ...(it.brand ? { brand: it.brand } : {}), ...(it.attributes ?? {}) } as RateMasterItem["attributes"],
    rates: it.rates ?? {}, source_sheet: it.source?.sheet, source_row: it.source?.row,
  }));
}

/** Every header cell as drawn: its grey word(s) beside the title (the header's `note` span) and its code name. */
function headers(asset: Asset, config: RateCategoryConfig): Array<{ note: string; id: string }> {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const names: Record<string, string> = {};
  for (const c of asset.category_configs) names[c.category_id] = String(c.category_display || c.category_id);
  act(() => {
    root.render(
      <RateMasterDataViewer items={feed(asset)} config={config} disciplineLabel={asset.discipline}
        categoryLabel={names[config.category_id]} derivedUsedBy={pricingInputUsedBy(asset.category_configs as never)}
        categoryNameById={names} />,
    );
  });
  const out = Array.from(host.querySelectorAll("thead tr th")).map((th) => ({
    note: Array.from(th.querySelectorAll("span")).filter((s) => s.className.includes("whitespace-nowrap") && s.className.includes("text-[10px]"))
      .map((s) => s.textContent ?? "").join(" | "),
    id: th.querySelector('[data-testid="file-column-id"]')?.textContent ?? "",
  }));
  act(() => root.unmount());
  host.remove();
  return out;
}

const CATEGORIES = ASSETS.flatMap((a) => a.category_configs
  .filter((c) => !isCategoryDataScopeEmpty(c) && a.items.some((it) => categoryItemKinds(c).includes(it.kind)))
  .map((c) => ({ asset: a, config: { ...c, discipline: a.discipline } as RateCategoryConfig })));

describe("BCS-W2 Rate Master header tags, as the owner ruled (1a, 2a)", () => {
  it("the newest files hold Electrical and HVAC categories with rows", () => {
    expect(CATEGORIES.some((c) => c.asset.discipline === "Electrical")).toBe(true);
    expect(CATEGORIES.some((c) => c.asset.discipline === "HVAC")).toBe(true);
  });
  for (const { asset, config } of CATEGORIES) {
    it(`(+) ${asset.discipline} / ${config.category_id}: no header carries a grey word beside its title`, () => {
      const hs = headers(asset, config);
      const notes = hs.filter((h) => h.note !== "");
      // P5c: the tag list after P3, printed per category (captured in the run's log)
      console.log(`TAGS\t${asset.discipline}\t${config.category_id}\theaders=${hs.length}\ttagged=${notes.length}\t${notes.map((h) => `${h.id}=${h.note}`).join(", ") || "-"}`);
      expect(notes).toEqual([]);
      for (const w of THE_FIVE) expect(hs.some((h) => h.note.includes(w))).toBe(false);
    });
    it(`(-) ${asset.discipline} / ${config.category_id}: each rate column's code name is still drawn under its title`, () => {
      if (isPricingInputConfig(config)) return; // a Pricing Input grid carries its own fixed columns (no SKU rate keys)
      const scoped = asset.items.filter((it) => categoryItemKinds(config).includes(it.kind)) as unknown as RateMasterItem[];
      const rates = (columnOrderForFile(config, scoped) as { rates: string[] }).rates;
      const ids = headers(asset, config).map((h) => h.id);
      // only the grids that draw a code name under their titles (every Electrical grid, ADP, the Pricing Inputs: they follow the
      // download's layout); the other HVAC grids never drew one, before or after this slice
      if (asset.discipline === "Electrical") expect(ids.some((i) => i !== ""), `${config.category_id} draws code names`).toBe(true);
      if (!ids.some((i) => i !== "")) return;
      for (const k of rates) expect(ids.filter((i) => i === k).length, `${config.category_id} ${k}`).toBe(1);
    });
  }
  it("(-) the derived kind the download writes is unchanged (the exporter's TypeScript twin)", () => {
    const elec = ASSETS[0];
    const popup = { ...elec.category_configs.find((c) => c.category_id === "popup_boxes")!, discipline: "Electrical" } as RateCategoryConfig;
    const L = deriveRateColumnLabels({ popup_boxes: popup }, "Electrical");
    expect(rateColumnLabel(L, "popup_box_module", "supply_per_module")).toBe("BCS price");
    expect(rateColumnLabel(L, "popup_box_module", "install_per_module")).toBe("BoQ price (install)");
  });
});
