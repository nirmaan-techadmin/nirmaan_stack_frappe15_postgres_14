// BCS-3 -- THE COST SIDE OF THE HELPER, THE TWO SPLIT LINES, AND THE BoQ SUGGESTION UNCHANGED. Pure: the newest Electrical rate
// file (a latest-asset reader by file prefix: rate_master_electrical_all_v) through the product's own helper and interpreter.
//
// What each block protects:
//   pairing          the cost block of each price block is read from the rate file (a supply output pairs its bcs_ twin), and
//                    equals the 13 pairs the mint generated the costs for -- no typed table in the product.
//   cost = pipeline  the cost the helper shows IS the cost pipeline's output for the same selection (no second arithmetic).
//   no typed figure  moving a Pricing Input moves the figure (owner R9 "dont hardcode it").
//   split lines      cable + conduit and the pop-up box + its modules as their own lines, price AND cost, adding up to the
//                    block's own figure (owner R4); no conduit line on a cable without conduit.
//   BoQ unchanged    on every worked example of every Electrical category the BoQ `values` are byte-equal with the cost side
//                    switched off (the config served without its cost pipelines), and no cost output ever enters `values`.
import path from "path";
import { readdirSync } from "fs";
import { pathToFileURL } from "url";
import { describe, expect, it } from "vitest";

import { bcsSideFor, costPipelineIds, isBcsPipelineId, makePricingSheetHelper } from "./pricingSheetHelper";
import { addedParts, costSupplyOutputOf, pairedCostPipelineId, BCS_INSTALL_NOTE } from "./bcsSide";
import { mergeItemsByName } from "./rateHelperPlumbing";
import type { ExtractionRow, RateHelperRowContext, Suggestion } from "./rateHelperTypes";
import { runPipeline } from "@/pages/pricing/rate-master/ratePipelineInterpreter";
import type { Pipeline, RateCategoryConfig, RateMasterItem } from "@/pages/pricing/rate-master/rateMasterTypes";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";

type Asset = { discipline: string; items: Array<RateMasterItem & { brand?: string }>; category_configs: RateCategoryConfig[]; goldens?: Record<string, Array<{ id: string; attrs: Record<string, string | number> }>> };
const DATA_DIR = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
const latest = readdirSync(DATA_DIR).filter((f) => /^rate_master_electrical_all_v\d+\.json$/.test(f))
  .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
const ELEC = readJsonFixture<Asset>(pathToFileURL(path.join(DATA_DIR, latest)));
const ITEMS: RateMasterItem[] = mergeItemsByName(ELEC.items.map((i) => ({ ...i, discipline: ELEC.discipline } as RateMasterItem)));
const CONFIGS = new Map<string, RateCategoryConfig>(ELEC.category_configs.map((c) => [c.category_id, { ...c, discipline: "Electrical" } as RateCategoryConfig]));
const KINDS = ["supply_rate", "install_rate", "combined_rate"];
const cfg = (id: string) => CONFIGS.get(id)!;
/** the config as a viewer without cost access receives it: the cost pipelines taken out */
const withoutCost = (c: RateCategoryConfig): RateCategoryConfig =>
  ({ ...c, pipelines: Object.fromEntries(Object.entries(c.pipelines ?? {}).filter(([id]) => !isBcsPipelineId(id))) }) as RateCategoryConfig;

function compute(configs: Map<string, RateCategoryConfig>, category: string, attrs: Record<string, string | number>, description = "", items = ITEMS): Suggestion {
  const cells = Object.fromEntries(Object.entries(attrs).map(([k, v]) => [k, { value: v, confidence: 0.9 }]));
  const ext = new Map<number, ExtractionRow>([[9, { excelRow: 9, description, attributes: cells } as unknown as ExtractionRow]]);
  const helper = makePricingSheetHelper({ configsByCategory: configs, items, extractionByRow: ext });
  const ctx = { excelRow: 9, description, nodeType: "Line Item", category, discipline: "Electrical", rateKinds: KINDS, headings: [], ownNotes: [], unit: "Nos" } as RateHelperRowContext;
  const r = helper.compute(ctx, {});
  expect(r.kind, `${category} prices`).toBe("suggestion");
  return r as Suggestion;
}

const CABLE = { material: "COPPER", insulation: "UNARMOURED", core: 2, runs: 1, thickness_sqmm: 1.5 };
const WITH_CONDUIT = { ...CABLE, conduit_included: "Yes", conduit_type: "MS", size_mm: 20 };
const NO_CONDUIT = { ...CABLE, conduit_included: "No", conduit_type: "None", size_mm: "None" };
const POPUP = {
  module_count: 8, has_modules: "Yes", switch_item: "16A 1 WAY SWITCH", switch_qty: 1, socket1_item: "6A/16A 3-Pin Socket", socket1_qty: 2,
  socket2_item: "USB Charger - A+C Type", socket2_qty: 1, socket3_item: "None", socket3_qty: 0, socket4_item: "None", socket4_qty: 0,
  blank_item: "None", blank_qty: 0, plate_item: "8M", plate_qty: 1, colour: "White",
};

describe("BCS-3 pairing: a price block's cost block is read from the rate file", () => {
  it("(+) every Electrical price block with a supply output pairs exactly the cost pipeline the mint generated for it", () => {
    // the mint's PAIRS (bcs_derive.py), as the expectation -- the product holds no such table
    const expected = [
      ["cabletray_raceway", "tray_boq_supply", "tray_bcs"], ["conduit_piping", "conduit_boq", "conduit_bcs"],
      ["db_switchgear", "db_buildup_supply", "db_buildup_bcs"], ["earthing", "earthing_boq", "earthing_bcs"],
      ["industrial_sockets", "indsock_boq", "indsock_bcs"], ["junction_box_raceway", "jb_boq", "jb_bcs"],
      ["lighting_mgmt_system", "lms_boq", "lms_bcs"], ["miscellaneous", "misc_boq", "misc_bcs"],
      ["point_wiring", "pw_boq_supply", "pw_bcs"], ["popup_boxes", "popup_boq", "popup_bcs"],
      ["switches_sockets", "swsock_boq", "swsock_bcs"], ["wiring_cabling", "cable_boq", "cable_bcs"],
      ["wiring_cabling", "termination_boq", "termination_bcs"],
    ];
    const derived: string[][] = [];
    for (const c of CONFIGS.values()) {
      for (const pid of Object.keys(c.pipelines ?? {}).filter((id) => !isBcsPipelineId(id))) {
        const cid = pairedCostPipelineId(c, pid, costPipelineIds(c));
        if (cid) derived.push([c.category_id, pid, cid]);
      }
    }
    expect(derived.sort()).toEqual(expected.sort());
  });
  it("(-) an installation-only price block has no cost block (the cost is supply only)", () => {
    expect(pairedCostPipelineId(cfg("industrial_sockets"), "indsock_install", costPipelineIds(cfg("industrial_sockets")))).toBeNull();
    expect(pairedCostPipelineId(cfg("cabletray_raceway"), "tray_boq_install", costPipelineIds(cfg("cabletray_raceway")))).toBeNull();
  });
});

describe("BCS-3 the cost the helper shows is the cost pipeline's own output", () => {
  it("(+) cable with conduit: the BCS supply = cable_bcs's output for the same selection; one cost block per price block", () => {
    const s = compute(CONFIGS, "wiring_cabling", WITH_CONDUIT);
    const pl = cfg("wiring_cabling").pipelines!.cable_bcs as Pipeline;
    const direct = runPipeline("cable_bcs", pl, ITEMS, WITH_CONDUIT).finals[costSupplyOutputOf(pl)!];
    expect(s.bcs?.values.supply_rate).toBe(direct);
    expect(s.bcs?.sections.map((g) => g.label)).toEqual(s.workings.sections!.map((g) => g.label));
    expect(s.bcs?.sections.every((g) => g.derivation.includes(BCS_INSTALL_NOTE))).toBe(true);
    expect(s.bcs?.headlines?.length).toBe(2);
  });
  it("(-) no figure is typed in: moving the conduit discount (a Pricing Input) moves the BCS figure and the conduit line", () => {
    const before = compute(CONFIGS, "wiring_cabling", WITH_CONDUIT).bcs!;
    const moved = ITEMS.map((i) => (i.kind === "electrical_pricing_input" && (i.attributes as Record<string, unknown>)?.item === "conduit"
      ? ({ ...i, rates: { ...i.rates, discount: Number((i.rates as Record<string, number>).discount) + 0.05 } } as RateMasterItem) : i));
    const after = compute(CONFIGS, "wiring_cabling", WITH_CONDUIT, "", moved).bcs!;
    expect(after.values.supply_rate).not.toBe(before.values.supply_rate);
    expect(after.sections[0].derivation.find((l) => l.startsWith("BCS conduit supply"))).not.toBe(before.sections[0].derivation.find((l) => l.startsWith("BCS conduit supply")));
  });
  it("(-) a config without its cost pipelines (a viewer without cost access) gives no cost side at all", () => {
    const stripped = new Map([...CONFIGS].map(([k, c]) => [k, withoutCost(c)]));
    expect(compute(stripped, "wiring_cabling", WITH_CONDUIT).bcs).toBeUndefined();
    expect(bcsSideFor(withoutCost(cfg("popup_boxes")), ITEMS, POPUP, [{ pid: "popup_boq", label: "x" }], "popup_boq")).toBeUndefined();
  });
});

describe("BCS-3 the two lines (owner R4): display only, they add up to the block's own figure", () => {
  it("(+) cable with conduit: cable and conduit lines, price and cost, summing to the total (the price's own round-up shown)", () => {
    const s = compute(CONFIGS, "wiring_cabling", WITH_CONDUIT);
    const cable = s.workings.sections![0];
    const line = (lines: string[], lead: string) => Number(lines.find((l) => l.startsWith(lead))!.split("= ").pop());
    const base = line(cable.derivation, "Cable supply = ");
    const part = line(cable.derivation, "Conduit supply = ");
    expect(cable.derivation).toContain(`Cable + conduit = ${Number((base + part).toFixed(2))}, rounded up to the rupee`);
    expect(Math.ceil(base + part - 1e-9)).toBe(cable.figures!.supply_rate);
    expect(line(cable.derivation, "Cable install = ") + line(cable.derivation, "Conduit install = ")).toBe(cable.figures!.install_rate);
    const cost = s.bcs!.sections[0];
    expect(line(cost.derivation, "BCS cable supply = ") + line(cost.derivation, "BCS conduit supply = ")).toBeCloseTo(cost.figures!.supply_rate!, 9);
  });
  it("(-) cable without conduit: no conduit line in either section, and the block reads as before", () => {
    const s = compute(CONFIGS, "wiring_cabling", NO_CONDUIT);
    const all = [...s.workings.sections!.flatMap((g) => g.derivation), ...s.bcs!.sections.flatMap((g) => g.derivation)];
    expect(all.some((l) => /conduit/i.test(l))).toBe(false);
    expect(s.workings.sections![0].derivation[0]).toBe(`Supply = ${s.values.supply_rate}`);
  });
  it("(+) pop-up: the box itself leads the block (before the modules), price and cost; box + modules = the supply", () => {
    const s = compute(CONFIGS, "popup_boxes", POPUP);
    const g = s.workings.sections![0];
    expect(g.matchedRows![0]).toMatch(/^Box supply = \d/);
    const num = (l: string) => Number(l.split("= ").pop());
    const box = num(g.matchedRows![0]);
    const modules = num(g.derivation.find((l) => l.startsWith("Modules supply = "))!);
    expect(box + modules).toBe(g.figures!.supply_rate);
    const cost = s.bcs!.sections[0].derivation;
    expect(num(cost.find((l) => l.startsWith("BCS box supply = "))!) + num(cost.find((l) => l.startsWith("BCS modules supply = "))!)).toBeCloseTo(s.bcs!.values.supply_rate!, 9);
    // P4c: the box line leads the COST block too -- before every module line (found in the cert, C3)
    expect(cost[0]).toMatch(/^BCS box supply = \d/);
    const firstModule = cost.findIndex((l) => /^(Switch|Socket \d|Blank plate|Frame\/Face plate): /.test(l));
    expect(firstModule).toBeGreaterThan(0);
  });
  it("(-) addedParts reads only `base + <part>` outputs: a plain output gives null", () => {
    const pl = cfg("industrial_sockets").pipelines!.indsock_boq as Pipeline;
    const golden = (cfg("industrial_sockets") as unknown as { goldens: Array<{ attrs: Record<string, string | number> }> }).goldens[0];
    const res = runPipeline("indsock_boq", pl, ITEMS, golden.attrs);
    expect(addedParts(pl, res, "supply", "Supply")).toBeNull();
  });
});

describe("BCS-3 P6d: the BoQ suggestion is byte-equal with the cost side switched off", () => {
  const stripped = new Map([...CONFIGS].map(([k, c]) => [k, withoutCost(c)]));
  const cases: Array<[string, string, Record<string, string | number>]> = [];
  for (const c of CONFIGS.values()) for (const g of ((c as unknown as Asset).goldens ?? []) as Array<{ id: string; attrs: Record<string, string | number> }>) cases.push([c.category_id, g.id, g.attrs]);
  it("has worked examples to check (the population is not empty)", () => expect(cases.length).toBeGreaterThan(20));
  it.each(cases)("(+) %s %s: values equal, no bcs_* output in values", (category, _id, attrs) => {
    const on = compute(CONFIGS, category, attrs);
    const off = compute(stripped, category, attrs);
    expect(JSON.stringify(on.values)).toBe(JSON.stringify(off.values));
    expect(JSON.stringify(on.workings)).toBe(JSON.stringify(off.workings));
    expect(Object.keys(on.values).some((k) => /bcs/i.test(k))).toBe(false);
  });
});

describe("BCS-3 owner answer 2 'b': an ALIAS category (HVAC Cables -> Electrical wiring) keeps its panel but for the tag", () => {
  const hvacFile = readdirSync(DATA_DIR).filter((f) => /^rate_master_hvac_all_v\d+\.json$/.test(f))
    .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
  const HVAC = readJsonFixture<Asset>(pathToFileURL(path.join(DATA_DIR, hvacFile)));
  const cables = HVAC.category_configs.find((c) => c.category_id === "hvac_cables")!;
  const both = new Map<string, RateCategoryConfig>([...CONFIGS, ["hvac_cables", { ...cables, discipline: "HVAC" } as RateCategoryConfig]]);
  it("the HVAC Cables config is an alias of the Electrical wiring config (the premise, read from the rate file)", () => {
    expect((cables as unknown as { alias_of?: { category_id: string } }).alias_of?.category_id).toBe("wiring_cabling");
  });
  it("(-) an HVAC Cables row with a conduit: the same prices, NO conduit line and NO cost side", () => {
    const hv = compute(both, "hvac_cables", WITH_CONDUIT);
    const el = compute(both, "wiring_cabling", WITH_CONDUIT);
    expect(hv.values).toEqual(el.values);
    expect(hv.bcs).toBeUndefined();
    expect(hv.workings.sections!.flatMap((g) => g.derivation).some((l) => /conduit/i.test(l))).toBe(false);
    expect(hv.workings.sections![0].derivation[0]).toBe(`Supply = ${hv.values.supply_rate}`);
  });
  it("(+) the same reading on an Electrical cable row: the conduit line and the cost side", () => {
    const el = compute(both, "wiring_cabling", WITH_CONDUIT);
    expect(el.bcs).toBeDefined();
    expect(el.workings.sections![0].derivation.some((l) => l.startsWith("Conduit supply = "))).toBe(true);
  });
});
