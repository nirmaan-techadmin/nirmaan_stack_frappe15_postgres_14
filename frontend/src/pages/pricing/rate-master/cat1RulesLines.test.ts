/**
 * CAT-1 (HVAC v89, 2026-11-26) -- the frontend half:
 *  T9  the four ruled rules-page lines (owner 2026-11-26 01:14 "2 ok"; CAT-D0 D8), word for word, on the ADP and Piping rules pages
 *      (read from the newest HVAC asset); ADP and Piping read MISSING / ORPHAN / WRONG = 0; NEGATIVE: a line taken out of the config is
 *      MISSING again; no "{{" on either page.
 *  T8  the VAV shares by item_uid (owner 2026-11-26 00:06 / 00:10): `shareSkuOf` finds the SKU by uid, `shareSkuName` reads its name
 *      LIVE, the rules page's share line names the live name -- a renamed SKU (same uid) shows its new name; the typed form still works.
 */
import { readdirSync } from "fs";
import path from "path";
import { pathToFileURL } from "url";
import { describe, expect, it } from "vitest";
import { derivationCoverage } from "./derivationCoverage";
import { itemListRuleOrder } from "./itemListRuleOrder";
import { RATE_MASTER_DISCIPLINES } from "./rateMasterRegistry";
import { readJsonFixture } from "../calculatorPanelParity.harness";
import { shareSkuName, shareSkuOf } from "../../boq-wizard/rate-helper/vavShareSums";
import type { RateMasterItem } from "./rateMasterTypes";

type Cfg = { category_id: string; list_spec: { sections?: Array<{ category_id?: string }>; pricing: Record<string, unknown> } };
type Asset = { items: RateMasterItem[]; category_configs: Cfg[] };
const DATA = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
// the latest HVAC asset by version number (a latest-asset reader by file prefix: rate_master_hvac_all_v)
const latest = readdirSync(DATA).filter((f) => /^rate_master_hvac_all_v\d+\.json$/.test(f))
  .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
const A = readJsonFixture<Asset>(pathToFileURL(path.join(DATA, latest)));
const C: Record<string, Cfg> = Object.fromEntries(A.category_configs.map((c) => [c.category_id, c]));
const borrowOnly = RATE_MASTER_DISCIPLINES.flatMap((d) => d.categories.filter((c) => c.fetch_only === true).map((c) => c.category_id));
const sectionsOf = (cfg: Cfg): Record<string, Cfg> => Object.fromEntries((cfg?.list_spec?.sections ?? [])
  .map((s) => String(s?.category_id ?? "")).filter((id) => id && borrowOnly.includes(id) && C[id]).map((id) => [id, C[id]]));
const linesOf = (cfg: Cfg, items: RateMasterItem[] = A.items) => itemListRuleOrder(cfg, items, sectionsOf(cfg));
const texts = (cfg: Cfg, items?: RateMasterItem[]) => linesOf(cfg, items).map((l) => [l.title, l.detail ?? ""].join(" | "));

// R6, word for word (the brief's R6 block; owner 2026-11-26 01:14 "2 ok")
const L_A = "A neck size written as two equal numbers ('300 x 300') is one square neck of that size. Two different numbers are not a neck size: the item is not priced until a person sets the neck size.";
const L_B = "When the heading just above names both supply and return air, and this row names neither and no damper, the damper is set to the item's usual setting, and the working says so - unless the heading itself gives the damper to both streams or to neither (owner 2026-10-23 23:24; 2026-10-24).";
const L_C = "A cross-talk row that says 'return air baffle' also pays for one return air grille without damper - 300 x 300 where no grille size is stated - one per unit of the row; its supply and installation are added to the cross-talk's. If that grille cannot be priced, the working says so and it must be added by hand (owner 2026-10-23 23:28 / 23:29; 2026-10-24).";
const L_D = "When a pipe row's heading mentions valves: if this sheet prices valves on their own rows, a note lists those rows (the first 10, then 'and N more') and says valves are not in this pipe price; if no valve row exists, the note says valves are not included and should be added on their own rows (owner 2026-11-12 23:59; 11-13 00:09, 00:33).";

describe(`CAT-1 T9 the ruled lines on ${latest}`, () => {
  it("ADP shows L-a, L-b, L-c and Piping shows L-d, each as written and on its own line, with no detail added", () => {
    const adp = linesOf(C.hvac_adp);
    for (const t of [L_A, L_B, L_C]) {
      const l = adp.filter((x) => x.title === t);
      expect(l.length, t.slice(0, 40)).toBe(1);
      expect(l[0].detail).toBeUndefined();
    }
    const pip = linesOf(C.hvac_piping).filter((x) => x.title === L_D);
    expect(pip.length).toBe(1);
    expect(pip[0].detail).toBeUndefined();
  });
  it("the lines are added LAST: every earlier ADP / Piping line keeps its number", () => {
    const adp = linesOf(C.hvac_adp);
    expect(adp.slice(-3).map((l) => l.title)).toEqual([L_A, L_B, L_C]);
    expect(linesOf(C.hvac_piping).slice(-1)[0].title).toBe(L_D);
  });
  it("ADP and Piping: MISSING / ORPHAN / WRONG = 0", () => {
    for (const id of ["hvac_adp", "hvac_piping"]) {
      const r = derivationCoverage(C[id], A.items, sectionsOf(C[id]));
      expect(r.missing, id).toEqual([]);
      expect(r.orphan, id).toEqual([]);
      expect(r.wrong, id).toEqual([]);
    }
  });
  it("NEGATIVE: each line taken out of the config is MISSING again", () => {
    const cases: Array<[string, (c: Cfg) => void, string]> = [
      ["hvac_adp", (c) => { delete (c.list_spec.pricing.numbers as Record<string, Record<string, unknown>>).neck_mm.rules_page_line; }, "numbers.neck_mm"],
      ["hvac_adp", (c) => { delete (c.list_spec.pricing.stream_heading_default as Array<Record<string, unknown>>)[0].rules_page_line; }, "stream_heading_default"],
      ["hvac_adp", (c) => { delete (c.list_spec.pricing.companion_items as Array<Record<string, unknown>>)[0].rules_page_line; }, "companion_items"],
      ["hvac_piping", (c) => { delete (c.list_spec.pricing.sheet_heading_notes as Array<Record<string, unknown>>)[0].rules_page_line; }, "sheet_heading_notes"],
    ];
    for (const [id, cut, key] of cases) {
      const cfg = structuredClone(C[id]);
      cut(cfg);
      const m = derivationCoverage(cfg, A.items, sectionsOf(cfg)).missing;
      expect(m.some((x) => x.includes(key)), `${id} ${key}: ${JSON.stringify(m)}`).toBe(true);
    }
  });
  it("no placeholder braces on either page", () => {
    for (const id of ["hvac_adp", "hvac_piping", "hvac_vav_box", "hvac_valve_package"]) expect(texts(C[id]).join("\n")).not.toContain("{{");
  });
});

describe("CAT-1 T8 the VAV shares by item_uid", () => {
  const vav = C.hvac_vav_box;
  type Part = { sku: { item_uid?: string; attr: string; kind?: string; value?: string } };
  const parts = (vav.list_spec.pricing.sheet_shares as { shares: Array<{ parts: Part[] }> }).shares.flatMap((s) => s.parts);
  it("every part names its SKU by uid and resolves to exactly the SKU, the name read live", () => {
    expect(parts.length).toBe(5);
    for (const p of parts) {
      expect(Object.keys(p.sku).sort()).toEqual(["attr", "item_uid"]);
      const it = shareSkuOf(A.items, p.sku as never);
      expect(it?.item_uid).toBe(p.sku.item_uid);
      expect(shareSkuName(A.items, p.sku as never)).toBe(String(it?.attributes?.[p.sku.attr]));
    }
    expect(shareSkuName(A.items, parts[0].sku as never)).toBe("DDC Panel/ Controller");
  });
  it("a renamed SKU (same uid) still resolves and the rules page names the NEW name", () => {
    const uid = parts[0].sku.item_uid!;
    const renamed = A.items.map((i) => (i.item_uid === uid ? { ...i, attributes: { ...i.attributes, vav_item: "DDC Panel / Controller (renamed)" } } : i));
    expect(shareSkuOf(renamed, parts[0].sku as never)?.item_uid).toBe(uid);
    expect(shareSkuName(renamed, parts[0].sku as never)).toBe("DDC Panel / Controller (renamed)");
    expect(texts(vav).join("\n")).toContain("(the DDC Panel/ Controller SKU's supply)");
    const after = texts(vav, renamed).join("\n");
    expect(after).toContain("(the DDC Panel / Controller (renamed) SKU's supply)");
    expect(after).not.toContain("(the DDC Panel/ Controller SKU's supply)");
  });
  it("NEGATIVE: a uid no SKU has resolves to nothing; the typed form of the older files still resolves", () => {
    expect(shareSkuOf(A.items, { item_uid: "rmi-cat1-none", attr: "vav_item" } as never)).toBeNull();
    const typed = { kind: "hvac_vav_item", attr: "vav_item", value: "DDC Panel/ Controller" };
    expect(shareSkuOf(A.items, typed as never)?.item_uid).toBe(parts[0].sku.item_uid);
    expect(shareSkuName(A.items, typed as never)).toBe("DDC Panel/ Controller");
  });
});
