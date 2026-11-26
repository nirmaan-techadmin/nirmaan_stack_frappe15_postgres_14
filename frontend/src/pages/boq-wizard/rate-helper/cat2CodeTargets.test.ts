/**
 * CAT-2 (2026-11-27; owner 2026-11-26 00:06 / 00:10 / 01:16; ANSWER to CAT2-4 QR-FORM) -- THE CODE TARGETS AND THE FAMILY PICKER FROM
 * ITEMS. Every check has a NEGATIVE. The catalogue values are read from the committed newest HVAC asset (its SKUs and its configs), never
 * typed here.
 *   HELPER  `codeTarget` / `codeTargetRef` / `codeTargetValues` read `list_spec.code_targets.<role>` through `itemListPricingSpec`; a
 *           missing or malformed role gives nothing (the rule does not fire) -- never a guessed value.
 *   T3      `familyChoices(spec, items)`: + every item-list category keeps every family today (0 dropped, CAT-D1 E8); - a family whose
 *           SKUs are removed (a scratch copy) leaves the picker; an offered alias follows its target (kept while the target is carried,
 *           gone with it); with no items, every declared family as before.
 *   T1      (K13) each moved rule reads its target from the config: the newest asset names every role the code reads, each carried by
 *           an SKU of its scope; - a config without a role leaves the rule off; a renamed value is followed.
 *   T2      (K13) none of the referenced values is typed as a string literal in the three moved files; - a planted one is found.
 */
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import type { RateCategoryConfig, RateMasterItem } from "../../pricing/rate-master/rateMasterTypes";
import { readJsonFixture } from "../../pricing/calculatorPanelParity.harness";
import { codeTarget, codeTargetRef, codeTargetValues, drainPipeDefault, familyAttr, familyChoices, giFrameworkCladding, itemListPricingSpec, kindIn, type ItemListPricingSpec } from "./itemListPricing";
import { offeredFamilies, VALVE_TARGET_ROLES, valveTargets } from "./pricingSheetHelper";
import { itemListRuleOrder } from "../../pricing/rate-master/itemListRuleOrder";

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

// ═════════════════════════════════════════════════════════════════════════════════════════════════════
// CAT-2 K13 -- the readers read the references; the constants are gone (T1 / T2 / T4)
// ═════════════════════════════════════════════════════════════════════════════════════════════════════
const cfgOf = (id: string) => LIVE.category_configs.find((c) => c.category_id === id)!;
const specOf = (id: string) => itemListPricingSpec(cfgOf(id))!;
const targetsOf = (id: string) => ((cfgOf(id) as unknown as { list_spec: { code_targets?: Record<string, { attr: string; value?: string; values?: string[] }> } }).list_spec.code_targets ?? {});
const withoutRole = (id: string, role: string) => {
  const c = structuredClone(cfgOf(id)) as unknown as { list_spec: { code_targets: Record<string, unknown> } };
  delete c.list_spec.code_targets[role];
  return itemListPricingSpec(c as unknown as RateCategoryConfig)!;
};

describe("CAT-2 T1 -- each moved rule reads its target from the config", () => {
  it("POSITIVE: the newest asset names every role the code reads, and each is carried by an SKU of its scope", () => {
    const need: Record<string, string[]> = {
      hvac_valve_package: [...VALVE_TARGET_ROLES, "gauge_valve_families", "modulating", "dual_plate"],
      hvac_vrf: ["frame_families", "onoff_controller"], hvac_insulation: ["gi_framework"], hvac_piping: ["cpvc", "pvc"],
    };
    for (const [id, roles] of Object.entries(need)) {
      const t = targetsOf(id);
      expect(Object.keys(t).sort(), id).toEqual([...roles].sort());
      for (const r of roles) {
        const sec = (t[r] as { section?: string }).section;
        const scopeId = sec ? ((cfgOf(id) as unknown as { list_spec: { sections: Array<{ id: string; category_id?: string }> } }).list_spec.sections.find((s) => s.id === sec)!.category_id!) : id;
        const kinds = new Set((cfgOf(scopeId) as unknown as { item_kinds: string[] }).item_kinds);
        for (const v of t[r].values ?? [t[r].value!]) {
          expect(LIVE.items.some((it) => kinds.has(it.kind) && it.attributes[t[r].attr] === v), `${id} ${r} '${v}'`).toBe(true);
        }
      }
    }
    expect(valveTargets(specOf("hvac_valve_package"))).not.toBeNull();
  });
  it("NEGATIVE: a config without a role leaves that rule off -- never a typed fallback", () => {
    expect(valveTargets(withoutRole("hvac_valve_package", "pibcv"))).toBeNull();
    expect(valveTargets(withoutRole("hvac_valve_package", "dual_plate"))).toBeNull();
    const ins = withoutRole("hvac_insulation", "gi_framework");
    const attr = targetsOf("hvac_insulation").gi_framework.attr;
    const item = { attributes: { [attr]: { value: null } } } as never;
    expect(giFrameworkCladding(specOf("hvac_insulation"), attr, item, "GI framework with perforated aluminium sheet")?.to).toBe(targetsOf("hvac_insulation").gi_framework.value);
    expect(giFrameworkCladding(ins, attr, item, "GI framework with perforated aluminium sheet")).toBeNull();
    expect(drainPipeDefault(withoutRole("hvac_piping", "cpvc"), "condensate drain pipe 25 mm", "")).toBeNull();
    expect(drainPipeDefault(specOf("hvac_piping"), "condensate drain pipe 25 mm", "")?.family).toBe(targetsOf("hvac_piping").cpvc.value);
  });
  it("a renamed value: the rule follows the config's new name (the gate keeps config and catalogue together)", () => {
    const c = structuredClone(cfgOf("hvac_piping")) as unknown as { list_spec: { code_targets: Record<string, { value: string }>; pricing: { families: Record<string, unknown> } } };
    const old = c.list_spec.code_targets.cpvc.value;
    c.list_spec.pricing.families[old + " (renamed)"] = c.list_spec.pricing.families[old];
    delete c.list_spec.pricing.families[old];
    c.list_spec.code_targets.cpvc.value = old + " (renamed)";
    expect(drainPipeDefault(itemListPricingSpec(c as unknown as RateCategoryConfig)!, "condensate drain pipe 25 mm", "")).toEqual({
      family: old + " (renamed)", line: `drain pipe, no material stated -> priced as ${old} (renamed)` });
  });
});

describe("CAT-2 T2 -- no moved constant is typed in the moved files any more", () => {
  const files = ["../../boq-wizard/rate-helper/pricingSheetHelper.ts", "../../boq-wizard/rate-helper/itemListPricing.ts", "../../pricing/rate-master/itemListRuleOrder.ts"]
    // code lines only: a comment line (// or a JSDoc / block line) may quote a word as it is written, as C1 allows
    .map((f) => readFileSync(new URL(f, import.meta.url), "utf-8").split("\n").filter((l) => !/^\s*(?:\/\/|\/\*|\*)/.test(l)).join("\n"));
  const values = new Set<string>();
  for (const id of ["hvac_valve_package", "hvac_vrf", "hvac_insulation", "hvac_piping"]) for (const t of Object.values(targetsOf(id))) for (const v of t.values ?? [t.value!]) values.add(v);
  values.add(String((cfgOf("hvac_ducting") as unknown as { list_spec: { pricing: { paint_row: { family: string } } } }).list_spec.pricing.paint_row.family));
  const typed = (src: string) => [...values].filter((v) => src.includes(`"${v}"`) || src.includes(`'${v}'`) || src.includes(`?? "${v}"`));
  it("POSITIVE: none of the 20 distinct referenced values appears as a typed string literal in the three files", () => {
    expect(values.size).toBe(20);   // the 20 code-target values less the repeated one, + paint_row.family
    for (const src of files) expect(typed(src)).toEqual([]);
  });
  it("NEGATIVE: a planted typed value is found", () => {
    const one = [...values][0];
    expect(typed(`${files[0]}\nconst X = "${one}";`)).toEqual([one]);
  });
});

describe("CAT-2 T4 -- the rules page reads the same references (E8 P3)", () => {
  const lines = (cfg: unknown) => itemListRuleOrder(cfg, LIVE.items).map((r) => `${r.title} -- ${r.detail ?? ""}`).join("\n");
  const paintFamily = () => String((cfgOf("hvac_ducting") as unknown as { list_spec: { pricing: { paint_row: { family: string } } } }).list_spec.pricing.paint_row.family);
  it("POSITIVE: today's lines name the referenced values (Paint, the GI framework, CPVC)", () => {
    expect(lines(cfgOf("hvac_ducting"))).toContain(`and state no gauge is priced as ${paintFamily()}`);
    expect(lines(cfgOf("hvac_insulation"))).toContain(`prices as ${targetsOf("hvac_insulation").gi_framework.value}`);
    expect(lines(cfgOf("hvac_piping"))).toContain(`A drain pipe whose material the BoQ does not name prices as ${targetsOf("hvac_piping").cpvc.value}`);
  });
  it("a renamed value shows its new name; a missing reference leaves its line out", () => {
    const duct = structuredClone(cfgOf("hvac_ducting")) as unknown as { list_spec: { pricing: { paint_row: { family: string } } } };
    duct.list_spec.pricing.paint_row.family = paintFamily() + " (renamed)";
    expect(lines(duct)).toContain(`and state no gauge is priced as ${paintFamily()} (renamed)`);
    const ins = structuredClone(cfgOf("hvac_insulation")) as unknown as { list_spec: { code_targets: Record<string, unknown> } };
    delete ins.list_spec.code_targets.gi_framework;
    expect(lines(ins)).not.toContain("A GI frame or framework with perforated aluminium sheet");
    expect(lines(cfgOf("hvac_insulation"))).toContain("A GI frame or framework with perforated aluminium sheet");
  });
});
