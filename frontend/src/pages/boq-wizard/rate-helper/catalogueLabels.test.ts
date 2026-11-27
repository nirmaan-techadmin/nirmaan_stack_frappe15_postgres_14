/**
 * CAT-3 (owner 2026-11-26 00:11 / 00:53): the TS side of the catalogue labels -- it READS the served labels, never makes them.
 *  + valueCarrying finds the catalogue's own spelling from the SKUs' labels (one distinct value); - none / two spellings -> undefined.
 *  + LABEL_VALUES equals the fixture's label values (the Python rule's own list; test_catalogue_labels proves the fixture).
 *  + readCableKindWords reads the BoQ words as LABEL values; the cable SKUs' labels give their spelling.
 *  + clothFacingCladding reads the cladding from the insulation SKUs' labels; - no SKU carries it -> nothing to price it as.
 *  + the harness labels raw rate-file items exactly as the fixture says; an item that already carries labels keeps them.
 */
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import fixture from "./__fixtures__/catalogueLabels.json";
import { LABEL_VALUES, labelValue, valueCarrying } from "./catalogueLabels";
import { withLabels, fixtureLabels } from "./labelsOverlay.harness";
import { clothFacingCladding, readCableKindWords, type ItemListPricingSpec } from "./itemListPricing";

const DATA = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
const newest = (prefix: string) => {
  const f = fs.readdirSync(DATA).filter((n) => n.startsWith(prefix)).sort((a, b) => Number(a.match(/_v(\d+)/)![1]) - Number(b.match(/_v(\d+)/)![1])).pop()!;
  return JSON.parse(fs.readFileSync(path.join(DATA, f), "utf8")) as { items: Array<{ kind: string; attributes: Record<string, unknown>; labels?: Record<string, string> }> };
};

describe("CAT-3 catalogue labels (TS reads the served labels)", () => {
  const elec = withLabels(newest("rate_master_electrical_all_v").items);
  const hvac = withLabels(newest("rate_master_hvac_all_v").items);
  const cables = elec.filter((i) => i.kind === "cable");
  const insulation = hvac.filter((i) => i.kind === "hvac_insulation_item");

  it("+ LABEL_VALUES = the rule's label values (the fixture)", () => {
    const ts = Object.fromEntries(Object.entries(LABEL_VALUES).map(([k, v]) => [k, [...v].sort()]));
    expect(ts).toEqual((fixture as { label_values: Record<string, string[]> }).label_values);
  });

  it("+ valueCarrying gives the SKUs' own spelling; - none or two spellings give undefined", () => {
    const armoured = valueCarrying(cables, { armour: labelValue("armour", "armoured") }, "insulation");
    expect(armoured).toBeDefined();
    expect(cables.filter((c) => c.attributes.insulation === armoured).every((c) => c.labels?.armour === "armoured")).toBe(true);
    expect(valueCarrying([], { armour: "armoured" }, "insulation")).toBeUndefined();
    const two = [{ labels: { armour: "armoured" }, attributes: { insulation: "A1" } }, { labels: { armour: "armoured" }, attributes: { insulation: "A2" } }];
    expect(valueCarrying(two, { armour: "armoured" }, "insulation")).toBeUndefined();
  });

  it("+ readCableKindWords reads label values; the cable SKUs give their spelling", () => {
    expect(readCableKindWords("4C x 16 sqmm AL armoured", { abbrev: true })).toEqual({ armour: "armoured", conductor: "al" });
    expect(readCableKindWords("copper unarmoured")).toEqual({ armour: "unarmoured", conductor: "cu" });
    expect(readCableKindWords("4C x 16 sqmm")).toEqual({});
    const cond = valueCarrying(cables, { conductor: "al" }, "material");
    expect(cond).toBeDefined();
    expect(cables.some((c) => c.attributes.material === cond)).toBe(true);
  });

  it("+ clothFacingCladding reads the cladding from the SKUs' labels; - no carrier, nothing to price", () => {
    const spec = { choice_text: [{ attr: "cladding", from_attr: "cladding_text", line: "BoQ says {from} -> priced as {to}", unlisted_line: "no {from}" }] } as unknown as ItemListPricingSpec;
    const item = { attributes: { cladding_text: { value: "reinforced glass cloth" } } } as never;
    const alu = { attributes: { cladding_text: { value: "24G aluminium with glass cloth facing" } } } as never;
    const cloth = clothFacingCladding(spec, "cladding", item, insulation);
    expect(cloth && "to" in cloth ? insulation.find((i) => i.attributes.cladding === cloth.to)?.labels?.cloth_cladding : null).toBe("cloth");
    const onAlu = clothFacingCladding(spec, "cladding", alu, insulation);
    const sku = onAlu && "to" in onAlu ? insulation.find((i) => i.attributes.cladding === onAlu.to) : undefined;
    expect([sku?.labels?.cloth_cladding, sku?.labels?.cladding_gauge]).toEqual(["cloth_on_aluminium", "24"]);
    expect(clothFacingCladding(spec, "cladding", item, [])).toBeNull();
    const g22 = { attributes: { cladding_text: { value: "22G aluminium with glass cloth" } } } as never;
    expect(clothFacingCladding(spec, "cladding", g22, insulation)).toEqual({ refuse: "no 22G aluminium with glass cloth" });
  });

  it("+ the harness labels raw items as the fixture says; an item with labels keeps its own", () => {
    expect(fixtureLabels({ kind: "cable", attributes: { material: "nothing-like-this" } })).toEqual({});
    const own = [{ kind: "cable", attributes: {}, labels: { conductor: "cu" } }];
    expect(withLabels(own)[0].labels).toEqual({ conductor: "cu" });
    expect(cables.length).toBeGreaterThan(0);
    expect(cables.every((c) => c.labels?.conductor !== undefined && c.labels?.armour !== undefined)).toBe(true);
  });
});
