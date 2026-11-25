// BCS-W -- NO INTERNAL LABEL ON THE ELECTRICAL RULES PAGE (Derivation) OR THE FORMULA ROW (owner R1 / R7, 2026-11-24; Question 1
// answer 2a: main's label kinds, scripts/pricer_text_labels.json, UNTOUCHED, read together with the Electrical list beside it,
// scripts/electrical_text_labels.json). Reads the newest Electrical rate file (a latest-asset reader by file prefix:
// rate_master_electrical_all_v) through the product's own text code: the rules page's lines (`itemListRuleOrder` /
// `attributeRuleOrder`, as RateMasterDerivation draws them) and the FORMULA row's sections (`columnNoteSections`).
//
// What each case protects:
//   (+) every Electrical rules-page line and FORMULA line passes both label lists; the owner's own quoted words and dates stay
//       (Earthing's "no positive bus-bar mention -> Without" (owner, 2026-07-30), answer 3a);
//   (-) a line with "ruling (iv)", "none_skips", "2 v1", "ruling (a)" or "the D26 adder" is caught.
import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import { pathToFileURL } from "url";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";
import { attributeRuleOrder, itemListRuleOrder } from "./itemListRuleOrder";
import { columnNoteSections } from "./rateMasterFormulaSections";
import type { RateCategoryConfig, RateMasterItem } from "./rateMasterTypes";

const APP = path.resolve(__dirname, "../../../../..");
const DATA_DIR = path.join(APP, "nirmaan_stack/services/boq_rate_master/data");
const file = fs.readdirSync(DATA_DIR).filter((f) => /^rate_master_electrical_all_v\d+\.json$/.test(f))
  .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
const ASSET = readJsonFixture<{ category_configs: RateCategoryConfig[]; items: RateMasterItem[] }>(pathToFileURL(path.join(DATA_DIR, file)));
const ITEMS = ASSET.items.map((i) => ({ ...i, discipline: "Electrical" })) as RateMasterItem[];
type Kind = { id: string; re: string };
const kinds = (f: string) => readJsonFixture<{ kinds: Kind[] }>(pathToFileURL(path.join(APP, "scripts", f))).kinds;
const NOT_LABELS = new Set(["QRO", "R-410", "R-410A", "R410A", "R-32", "R32", "R-22", "R22"]);
const MAIN = kinds("pricer_text_labels.json").map((k) => ({ id: k.id, re: new RegExp(k.re, "g") }));
const ELEC = kinds("electrical_text_labels.json").map((k) => ({ id: k.id, re: new RegExp(k.re, "g") }));
/** main's `labels` (scripts/pricer_texts.py) in TypeScript, plus the Electrical kinds */
function labels(t: string): string[] {
  const out: string[] = [];
  for (const k of MAIN) for (const m of t.matchAll(k.re)) {
    const s = m[0].trim();
    if (NOT_LABELS.has(s) || (k.id === "key" && t[(m.index ?? 0) - 1] === "{")) continue;
    out.push(`${k.id}:${s}`);
  }
  for (const k of ELEC) for (const m of t.matchAll(k.re)) out.push(`${k.id}:${m[0]}`);
  return out;
}
const rulesLines = (c: RateCategoryConfig): string[] => {
  const list = itemListRuleOrder(c, ITEMS as never);
  return (list.length ? list : attributeRuleOrder(c, ITEMS as never)).map((l) => `${l.title}${l.detail ? ` — ${l.detail}` : ""}`);
};
const cats = ASSET.category_configs.filter((c) => c.category_id !== "electrical_pricing_inputs").map((c) => ({ ...c, discipline: "Electrical" }) as RateCategoryConfig);

describe("BCS-W no internal label on an Electrical screen text", () => {
  it("(+) every Electrical rules-page line passes main's kinds and the Electrical list", () => {
    const found = cats.flatMap((c) => rulesLines(c).filter((l) => labels(l).length).map((l) => `${c.category_id}: ${labels(l).join(", ")}`));
    expect(found).toEqual([]);
    expect(cats.flatMap(rulesLines).length).toBeGreaterThan(50); // 77 on v75, over 12 categories
  });
  it("(+) every Electrical FORMULA line passes both lists (each rate column of each category)", () => {
    const found: string[] = [];
    for (const c of cats) {
      // the columns the grid shows: the rate keys of the category's own rows (wiring carries no item_kinds: cable + termination)
      const kindsOf = (c as unknown as { item_kinds?: string[] }).item_kinds ?? (c.category_id === "wiring_cabling" ? ["cable", "termination"] : []);
      const keys = new Set(ITEMS.filter((i) => kindsOf.includes(i.kind)).flatMap((i) => Object.keys(i.rates ?? {}).filter((k) => (i.rates as Record<string, unknown>)[k] != null)));
      for (const k of keys) {
        const s = columnNoteSections(c, k);
        for (const l of [...s.boq, ...s.bcs]) if (labels(l).length) found.push(`${c.category_id}/${k}: ${labels(l).join(", ")}`);
      }
    }
    expect(found).toEqual([]);
  });
  it("(+) the owner's own words stay: Earthing's bus-bar reason keeps his second quote and both dates", () => {
    const line = rulesLines(cats.find((c) => c.category_id === "earthing")!).find((l) => l.includes("With Bus bar"))!;
    expect(line).toContain("\"no positive bus-bar mention -> Without\" (owner, 2026-07-30)");
    expect(line).toContain("a bus bar is added only when one is stated (owner, 2026-07-29)");
    expect(line).not.toContain("D26");
  });
  it("(-) the labels board 1 names are caught", () => {
    for (const t of ["ruling (iv) conduit prices as its own category does", "none_skips (type None)", "clearing None (owner, 2026-10-27, \"2 v1\")",
      "the wire install, ruling (a) 2026-08-10", "\"the D26 adder means ADD A BUS BAR\"", "paired MCB added x1 UNLESS", "used when thickness_sqmm <35"]) {
      expect(labels(t).length, t).toBeGreaterThan(0);
    }
  });
});
