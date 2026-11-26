/**
 * CAT-2 (2026-11-27; owner 2026-11-26 00:06 / 00:10 / 01:16; ANSWER to CAT2-4 QR-FORM) -- THE CODE TARGETS AND THE FAMILY PICKER FROM
 * ITEMS. Every check has a NEGATIVE. The catalogue values are read from the committed newest HVAC asset (its SKUs and its configs), never
 * typed here.
 *   HELPER  `codeTarget` / `codeTargetRef` / `codeTargetValues` read `list_spec.code_targets.<role>` through `itemListPricingSpec`; a
 *           missing or malformed role gives nothing (the rule does not fire) -- never a guessed value.
 *   T3      `familyChoices(spec, items)`: + every item-list category keeps every family today (0 dropped, CAT-D1 E8); - a family whose
 *           SKUs are removed (a scratch copy) leaves the picker; an offered alias follows its target (kept while the target is carried,
 *           gone with it); with no items, every declared family as before.
 */
import { describe, expect, it } from "vitest";
import { readdirSync } from "node:fs";
import type { RateCategoryConfig, RateMasterItem } from "../../pricing/rate-master/rateMasterTypes";
import { readJsonFixture } from "../../pricing/calculatorPanelParity.harness";
import { codeTarget, codeTargetRef, codeTargetValues, familyAttr, familyChoices, itemListPricingSpec, kindIn, type ItemListPricingSpec } from "./itemListPricing";
import { offeredFamilies } from "./pricingSheetHelper";

type Asset = { category_configs: RateCategoryConfig[]; items: RateMasterItem[] };
const DATA_DIR = new URL("../../../../../nirmaan_stack/services/boq_rate_master/data/", import.meta.url);
const latestHvac = (): Asset => {
  const files = readdirSync(DATA_DIR).filter((f) => /^rate_master_hvac_all_v\d+\.json$/.test(f));
  files.sort((x, y) => Number(x.match(/_v(\d+)/)![1]) - Number(y.match(/_v(\d+)/)![1]));
  return readJsonFixture<Asset>(new URL(files[files.length - 1], DATA_DIR));
};
const LIVE = latestHvac();
const listCategories = LIVE.category_configs.map((c) => ({ c, spec: itemListPricingSpec(c) })).filter((x): x is { c: RateCategoryConfig; spec: ItemListPricingSpec } => x.spec !== null);
const withTargets = (c: RateCategoryConfig, code_targets: unknown): RateCategoryConfig =>
  ({ ...c, list_spec: { ...(c as unknown as { list_spec: object }).list_spec, code_targets } } as unknown as RateCategoryConfig);

describe("CAT-2 HELPER -- the code targets ride in from list_spec and are read by role", () => {
  const { c, spec } = listCategories[0];
  const carried = [...new Set(LIVE.items.filter((it) => kindIn(spec, it.kind)).map((it) => String(it.attributes[familyAttr(spec)])))].sort();
  it("POSITIVE: a value, a values list and the {attr, value} pair come back exactly as the config names them", () => {
    const s = itemListPricingSpec(withTargets(c, { one: { attr: familyAttr(spec), value: carried[0] }, two: { attr: familyAttr(spec), values: carried.slice(0, 2) } }))!;
    expect(codeTarget(s, "one")).toBe(carried[0]);
    expect(codeTargetRef(s, "one")).toEqual({ attr: familyAttr(spec), value: carried[0] });
    expect(codeTargetValues(s, "two")).toEqual(carried.slice(0, 2));
    expect(codeTargetValues(s, "one")).toEqual([carried[0]]);
  });
  it("NEGATIVE: a missing role, a missing block, a blank value or a missing attribute gives nothing (the rule does not fire)", () => {
    const s = itemListPricingSpec(withTargets(c, { blank: { attr: familyAttr(spec), value: "" }, noattr: { value: carried[0] } }))!;
    for (const role of ["absent", "blank", "noattr"]) {
      expect(codeTarget(s, role)).toBeUndefined();
      expect(codeTargetRef(s, role)).toBeNull();
    }
    expect(codeTargetValues(s, "absent")).toEqual([]);
    expect(codeTarget(spec, "no_such_role_anywhere")).toBeUndefined();
    expect(codeTarget(null, "one")).toBeUndefined();
    expect(itemListPricingSpec(withTargets(c, ["not", "an", "object"]))!.code_targets).toBeUndefined();
  });
});

describe("CAT-2 T3 -- the 'Change to...' family picker follows the catalogue (P1)", () => {
  it("POSITIVE: today every item-list category keeps every family (0 dropped) -- the owner sees no change", () => {
    expect(listCategories.length).toBeGreaterThanOrEqual(9);
    for (const { c, spec } of listCategories) {
      expect(familyChoices(spec, LIVE.items), c.category_id).toEqual(familyChoices(spec));
      expect(offeredFamilies(spec, LIVE.items), c.category_id).toEqual(offeredFamilies(spec));
    }
  });
  it("NEGATIVE: a family whose SKUs are all removed (scratch copy) leaves the picker; the others stay", () => {
    for (const { c, spec } of listCategories) {
      const fa = familyAttr(spec);
      const gone = familyChoices(spec).find((f) => !(spec.family_alias_offered ?? []).includes(f.family))!.family;
      const items = LIVE.items.filter((it) => !(kindIn(spec, it.kind) && it.attributes[fa] === gone));
      const left = familyChoices(spec, items).map((f) => f.family);
      expect(left, c.category_id).not.toContain(gone);
      expect(left.length, c.category_id).toBe(familyChoices(spec).length - 1 - (familyChoices(spec).filter((f) => spec.family_alias?.[f.family] === gone).length));
    }
  });
  it("an offered alias follows its target: kept while the target is carried, gone with it", () => {
    const withAlias = listCategories.filter(({ spec }) => (spec.family_alias_offered ?? []).some((a) => spec.family_alias?.[a] && spec.families[spec.family_alias[a]]));
    expect(withAlias.length).toBeGreaterThan(0);
    for (const { spec } of withAlias) {
      const fa = familyAttr(spec);
      const alias = (spec.family_alias_offered ?? []).find((a) => spec.family_alias?.[a] && spec.families[spec.family_alias[a]])!;
      const target = spec.family_alias![alias];
      expect(familyChoices(spec, LIVE.items).map((f) => f.family)).toContain(alias);
      const items = LIVE.items.filter((it) => !(kindIn(spec, it.kind) && it.attributes[fa] === target));
      const left = familyChoices(spec, items).map((f) => f.family);
      expect(left).not.toContain(target);
      expect(left).not.toContain(alias);
    }
  });
  it("an empty catalogue offers nothing; no catalogue given (the old call) offers every declared family", () => {
    for (const { spec } of listCategories) expect(familyChoices(spec, []).length).toBe(0);
    for (const { spec } of listCategories) expect(familyChoices(spec).length).toBeGreaterThan(0);
  });
});
