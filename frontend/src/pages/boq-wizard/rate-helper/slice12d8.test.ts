/**
 * SLICE 12d-8 (owner rulings R1-R6 + U7 / U8, 2026-10-09) -- THE 12d-7 FINDINGS AND THE 12d-6 LEFTOVERS,
 * every one tested from the PANEL'S ENTRY POINT (`makePricingSheetHelper(...).compute`) on the LIVE v33
 * asset, read at runtime (never `import`ed -- a JSON import makes tsc infer a structural type for the file).
 *
 *   R1  a value the SYSTEM clears (a stale pick, 12c-S) stays BLANK and the row REFUSES; a default fills only
 *       what the BoQ or the user never gave (12d-7 F-1: the cleared pick was read as "not mentioned" and the
 *       9 mm / absent-as-none default re-priced the row beside a "choose again" note).
 *   R2  a NUMBER-matched model value keeps the reader's own line in the note ("states several values -- the
 *       highest, 25, is taken", "20 cm read as 200 mm", the range reader); the select still shows the option;
 *       no figure moves (12d-7 F-2: the match rewrote the value before the pricer and the line was lost).
 *   R3  a size typed into an "Other..." box the MODEL opened is typing through "Other..." -- never cleared.
 *   R4b "Aluminium Foil" is OFFERED on Nitrile Rubber and Tubular PUF (derived from `value_map`), priced as
 *       26G with its own line; Acoustic Nitrile (foil refuses) and the sheet families (glass cloth) unchanged.
 *   R5/R6 Derivation tab: line 9 says a range takes its top value; ADP gains the outer-size line.
 *   U7  the typed-refusal note carries the unit once.  U8  unicode vulgar fractions read as inches.
 */
import { describe, expect, it } from "vitest";
import type { RateCategoryConfig, RateMasterItem } from "@/pages/pricing/rate-master/rateMasterTypes";
import type { ExtractionRow, RateHelperRowContext } from "./rateHelperTypes";
import { isSuggestion } from "./rateHelperTypes";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";
import { itemListRuleOrder } from "@/pages/pricing/rate-master/itemListRuleOrder";
import {
  ITEM_LIST_OVERRIDE_KEY, ROW_UNIT_OVERRIDE_KEY, makePricingSheetHelper, type ItemListSuggestion, type ItemBlockView,
} from "./pricingSheetHelper";
import {
  fieldOptionsFromSkus, itemListPricingSpec, matchStatedToOption, matchStatedToOptionDetailed, readNumber, unicodeFractions,
} from "./itemListPricing";

const ASSET = readJsonFixture<{ discipline: string; items: Array<Omit<RateMasterItem, "discipline">>; category_configs: RateCategoryConfig[] }>(
  new URL("../../../../../nirmaan_stack/services/boq_rate_master/data/rate_master_hvac_all_v33.json", import.meta.url),
);
const INS = ASSET.category_configs.find((c) => c.category_id === "hvac_insulation")!;
const ADP = ASSET.category_configs.find((c) => c.category_id === "hvac_adp")!;
const CONFIGS = new Map<string, RateCategoryConfig>([["hvac_insulation", INS], ["hvac_adp", ADP]]);
const ITEMS: RateMasterItem[] = ASSET.items.map((it) => ({ ...it, discipline: ASSET.discipline } as RateMasterItem));
const SPEC = itemListPricingSpec(INS)!;
const NR = "Nitrile Rubber Insulation";
const PUF = "Tubular Puf Insulation";
const KINDS = ["supply_rate", "install_rate", "combined_rate"] as const;

type Cells = ExtractionRow["attributes"];
const cells = (a: Record<string, string>): Cells =>
  Object.fromEntries(Object.entries(a).map(([k, v]) => [k, { value: v, confidence: 0.9 }]));
type Edit = { base: number | null; family: string | null; attrs: Record<string, string>; other?: string[]; qty?: string };

/** The PANEL path: a stored answer through `extractionByRow`; optional session edits over it. */
function panel(category: string, answer: Record<string, string>, unit: string, edit?: Edit) {
  const row = { excelRow: 1, description: "", attributes: {}, items: [{ attributes: cells(answer) }] } as ExtractionRow;
  const h = makePricingSheetHelper({ configsByCategory: CONFIGS, items: ITEMS, extractionByRow: new Map([[1, row]]) });
  const ctx: RateHelperRowContext & { unit?: string } = {
    excelRow: 1, description: "", nodeType: "Line Item", category, discipline: "HVAC", rateKinds: [...KINDS], unit,
  };
  const r = h.compute(ctx, edit ? { [ITEM_LIST_OVERRIDE_KEY]: JSON.stringify({ items: [edit] }) } : {});
  if (!isSuggestion(r)) throw new Error("expected a suggestion");
  const v = (r as ItemListSuggestion).itemList!;
  return { r: r as ItemListSuggestion, v, block: v.items[0] as ItemBlockView };
}

/** The CALCULATOR path: an empty extraction map, every value through the edit state. */
function calculator(category: string, family: string, attrs: Record<string, string>, unit: string, other: string[] = []) {
  const h = makePricingSheetHelper({ configsByCategory: CONFIGS, items: ITEMS, extractionByRow: new Map() });
  const edits = { items: [{ base: null, family, attrs, other }] };
  const r = h.compute(
    { excelRow: 1, description: "", nodeType: "Line Item", category, discipline: "HVAC", rateKinds: [...KINDS] },
    { [ITEM_LIST_OVERRIDE_KEY]: JSON.stringify(edits), [ROW_UNIT_OVERRIDE_KEY]: unit },
  );
  if (!isSuggestion(r)) throw new Error("expected a suggestion");
  const v = (r as ItemListSuggestion).itemList!;
  return { r: r as ItemListSuggestion, v, block: v.items[0] as ItemBlockView };
}

const field = (b: ItemBlockView, id: string) => b.fields.find((f) => f.id === id)!;
const NIT = { item: NR, cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: "50" };

// ═══════════════════════════════════════════════════════════════════════════════════════════════════════
describe("SLICE 12d-8 / R1 -- a value the system clears stays blank and the row refuses", () => {
  it("calculator, PUF, pipe 100 + a PICKED thickness 25 (pipe 100 stocks 65): cleared, blank, refused -- and NOT priced at the 9 mm default (12d-7 F-1)", () => {
    const { r, v, block } = calculator("hvac_insulation", PUF, { cladding: "No", pipe_size_mm: "100", thickness_mm: "25" }, "mts");
    expect(v.rowPriced).toBe(false);
    expect(r.values).toEqual({});
    expect(block.state).toBe("blank");
    expect(field(block, "thickness_mm").value).toBe("");
    expect(field(block, "thickness_mm").note).toBe("25 mm is not stocked with the other answers on this item -- choose again");
    expect(v.reason).toBe("choose again: thickness -- the value picked is not stocked with the other answers on this item");
    // the NEGATIVE half of the 12d-7 defect: no default fired, no price
    expect(block.working.join("\n")).not.toMatch(/not mentioned -> 9/);
    expect(block.working.join("\n")).not.toMatch(/-> 65/);
  });

  it("calculator, Nitrile, pipe 6.35 + a PICKED 25 (stocks 13 / 19): refused -- where the pure pricer would COMPOSE 13 + 13, the panel must not price a cleared pick either way", () => {
    const { r, v, block } = calculator("hvac_insulation", NR, { cladding: "26G Aluminium", pipe_size_mm: "6.35", thickness_mm: "25" }, "mts", ["pipe_size_mm"]);
    expect(v.rowPriced).toBe(false);
    expect(r.values).toEqual({});
    expect(field(block, "thickness_mm").value).toBe("");
    expect(field(block, "thickness_mm").note).toMatch(/^25 mm is not stocked with the other answers/);
    expect(block.working.join("\n")).not.toMatch(/not mentioned -> 9|-> 13/);
  });

  it("calculator, ADP fire damper, motorised + a PICKED UL yes (the motorised SKU is non-UL): ul cleared, blank, refused -- NOT priced as the non-UL SKU", () => {
    const { r, v, block } = calculator("hvac_adp", "fire damper", { variant: "motorised", ul: "yes", size_mm: "600x600" }, "nos");
    expect(v.rowPriced).toBe(false);
    expect(r.values).toEqual({});
    expect(field(block, "ul").value).toBe("");
    expect(field(block, "ul").note).toBe("yes is not stocked with the other answers on this item -- choose again");
    expect(v.reason).toBe("choose again: whether it is UL listed -- the value picked is not stocked with the other answers on this item");
    expect(block.working.join("\n")).not.toMatch(/ul not mentioned -> no/);
  });

  it("the UL variant picked DIRECTLY still prices the UL 555 SKU: 7830 / 692 (unchanged path)", () => {
    const { r } = calculator("hvac_adp", "fire damper", { variant: "UL", ul: "yes", size_mm: "600x600" }, "nos");
    expect(r.values).toEqual({ supply_rate: 7830, install_rate: 692, combined_rate: 8522 });
  });

  it("a typed PANEL edit: the model's pipe 6.35 + a picked 25 -> the same refusal on the panel path", () => {
    const { r, v, block } = panel("hvac_insulation", { ...NIT, pipe_size_mm: "6.35" }, "RMT", { base: 0, family: null, attrs: { thickness_mm: "25" } });
    expect(v.rowPriced).toBe(false);
    expect(r.values).toEqual({});
    expect(field(block, "thickness_mm").note).toMatch(/^25 mm is not stocked with the other answers/);
    expect(block.working.join("\n")).not.toMatch(/not mentioned -> 9/);
  });

  it("NEGATIVE: a thickness NEVER given still takes the 9 mm default on the calculator (the default is for what nobody gave)", () => {
    const { r, block } = calculator("hvac_insulation", NR, { cladding: "26G Aluminium", pipe_size_mm: "50" }, "mts", ["pipe_size_mm"]);
    expect(block.state).toBe("priced");
    expect(block.working).toContain("thickness_mm not mentioned -> 9 (thickness not mentioned -> 9 mm, then the ladder)");
    expect(r.values).toEqual({ supply_rate: 556, install_rate: 224, combined_rate: 780 });
  });

  it("NEGATIVE: a damper NEVER given still defaults on the calculator (ADP absent_as_none)", () => {
    const { r, block } = calculator("hvac_adp", "round diffuser", { dia_mm: "200" }, "nos");
    expect(block.state).toBe("priced");
    expect(block.working).toContain("damper not mentioned -> without (damper not mentioned (or not answered) = without)");
    expect(r.values).toEqual({ supply_rate: 986, install_rate: 400, combined_rate: 1386 });
  });

  it("NEGATIVE: a thickness TYPED through Other... at an unstocked size is never cleared -- the ladder has it (25 at pipe 100 -> 65)", () => {
    const { r, block } = calculator("hvac_insulation", PUF, { cladding: "No", pipe_size_mm: "100", thickness_mm: "25" }, "mts", ["thickness_mm"]);
    expect(block.state).toBe("priced");
    expect(field(block, "thickness_mm").value).toBe("65");
    expect(r.values).toEqual({ supply_rate: 412, install_rate: 14, combined_rate: 426 });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════════════════════
describe("SLICE 12d-8 / R2 -- a number-matched model value keeps the reader's own line; the select shows the option; no figure moves", () => {
  it("\"13 / 19 / 25\" (several -> highest): select 25, note carries the reader's line, working too, 643 / 224 unchanged", () => {
    const { r, block } = panel("hvac_insulation", { ...NIT, thickness_mm: "13 / 19 / 25" }, "RMT");
    expect(r.values).toEqual({ supply_rate: 643, install_rate: 224, combined_rate: 867 });
    const th = field(block, "thickness_mm");
    expect(th.value).toBe("25");
    expect(th.otherMode).toBe(false);
    expect(th.note).toBe("BoQ says 13 / 19 / 25 -> 25 mm (states several values -- the highest, 25, is taken)");
    expect(block.working).toContain("thickness: '13 / 19 / 25' states several values -- the highest, 25, is taken");
    expect(th.note).not.toMatch(/own spelling/);
  });

  it("\"20 cm\" (PUF pipe): select 200, note \"20 cm read as 200 mm\", 986 / 14 unchanged", () => {
    const { r, block } = panel("hvac_insulation", { item: PUF, cladding: "No", thickness_mm: "25", pipe_size_mm: "20 cm" }, "RMT");
    expect(r.values).toEqual({ supply_rate: 986, install_rate: 14, combined_rate: 1000 });
    const ps = field(block, "pipe_size_mm");
    expect(ps.value).toBe("200");
    expect(ps.note).toBe("BoQ says 20 cm -> 200 mm (20 cm read as 200 mm)");
    expect(block.working).toContain("pipe size: 20 cm read as 200 mm");
  });

  it("\"25 to 50\" (PUF thickness, the range reader): the range line, then the ladder hop, 412 / 14 unchanged", () => {
    const { r, block } = panel("hvac_insulation", { item: PUF, cladding: "No", thickness_mm: "25 to 50", pipe_size_mm: "100" }, "RMT");
    expect(r.values).toEqual({ supply_rate: 412, install_rate: 14, combined_rate: 426 });
    const th = field(block, "thickness_mm");
    expect(th.value).toBe("65");
    expect(th.note).toBe("BoQ says 25 to 50 -> 50 mm (range '25 to 50' -> its top value 50) -> priced as 65 mm (next size up)");
    expect(block.working).toContain("thickness: range '25 to 50' -> its top value 50");
  });

  it("NEGATIVE: a plain match (\"19 mm\" -> 19) keeps today's note", () => {
    const { r, block } = panel("hvac_insulation", { ...NIT, thickness_mm: "19 mm" }, "RMT");
    expect(r.values).toEqual({ supply_rate: 615, install_rate: 224, combined_rate: 839 });
    expect(field(block, "thickness_mm").note).toBe("BoQ says 19 mm -> 19 mm (the sheet's own spelling of this value)");
  });

  it("NEGATIVE: a TEXT match (\"gi rectangular\" -> \"GI rectangular\") is still rewritten for pricing -- the pure pricer over the raw text would refuse", () => {
    const { r, block } = panel("hvac_adp", { family: "VCD", variant: "gi rectangular" }, "sqm");
    expect(r.values).toEqual({ supply_rate: 7830, install_rate: 1920, combined_rate: 9750 });
    expect(field(block, "variant").note).toBe("BoQ says gi rectangular -> GI rectangular (the sheet's own spelling of this value)");
    expect(matchStatedToOptionDetailed("gi rectangular", ["GI rectangular", "motorised"], undefined)).toEqual({ to: "GI rectangular", by: "text" });
    expect(matchStatedToOptionDetailed("13 / 19 / 25", ["13", "19", "25"], SPEC.numbers.thickness_mm)).toEqual({ to: "25", by: "number" });
    expect(matchStatedToOption("13 / 19 / 25", ["13", "19", "25"], SPEC.numbers.thickness_mm)).toBe("25");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════════════════════
describe("SLICE 12d-8 / R3 -- typing into an Other... box the MODEL opened is typing through Other...", () => {
  it("CERT-FOUND (C5): the box the model opened STAYS OPEN while the pricer types -- otherMode true, typedValue the typed text, select on Other...", () => {
    // the 12d-8 cert typed "50" into the model-opened pipe-size box and the box unmounted after "5": the
    // field read userEdited and dropped otherMode, the select jumped to 6.35, the "0" was lost
    const r = panel("hvac_insulation", { ...NIT, pipe_size_mm: "250 NB" }, "RMT", { base: 0, family: null, attrs: { pipe_size_mm: "5" } });
    const f = field(r.block, "pipe_size_mm");
    expect(f.otherMode).toBe(true);
    expect(f.typedValue).toBe("5");
    expect(f.value).toBe("6.35");       // the ladder's answer still shows beside the box (C-R4)
    expect(f.note).toBe("You typed 5 mm -> priced as 6.35 mm (next size up)");
    const r2 = panel("hvac_insulation", { ...NIT, pipe_size_mm: "250 NB" }, "RMT", { base: 0, family: null, attrs: { pipe_size_mm: "50" } });
    expect(field(r2.block, "pipe_size_mm").otherMode).toBe(true);
    expect(field(r2.block, "pipe_size_mm").typedValue).toBe("50");
    expect([r2.r.values.supply_rate, r2.r.values.install_rate]).toEqual([615, 224]);
  });
  it("NEGATIVE: a value typed into the model-opened box that IS an option closes the box, exactly as a pick would", () => {
    const r = panel("hvac_insulation", { ...NIT, pipe_size_mm: "250 NB" }, "RMT", { base: 0, family: null, attrs: { pipe_size_mm: "53.98" } });
    expect(field(r.block, "pipe_size_mm").otherMode).toBe(false);
    expect(field(r.block, "pipe_size_mm").value).toBe("53.98");
  });
  it("NEGATIVE: a field the model did NOT open (its value was an option) and the pricer edits without Other... is a pick -- the box does not open", () => {
    const r = panel("hvac_insulation", { ...NIT, pipe_size_mm: "53.98" }, "RMT", { base: 0, family: null, attrs: { pipe_size_mm: "50" } });
    expect(field(r.block, "pipe_size_mm").otherMode).toBe(false);
  });
  it("the model's \"250 NB\" opened the box; 50 typed into it WITHOUT re-selecting Other... is kept and ladders: 615 / 224", () => {
    const { r, v, block } = panel("hvac_insulation", { ...NIT, pipe_size_mm: "250 NB" }, "RMT", { base: 0, family: null, attrs: { pipe_size_mm: "50" } });
    expect(v.rowPriced).toBe(true);
    expect(r.values).toEqual({ supply_rate: 615, install_rate: 224, combined_rate: 839 });
    const ps = field(block, "pipe_size_mm");
    expect(ps.note).toBe("You typed 50 mm -> priced as 53.98 mm (next size up)");
    expect(ps.note).not.toMatch(/not stocked with the other answers/);
  });

  it("the 12d-6 C6 shape: a model-read double layer at 250 NB, pipe retyped 50 in the model-opened box -> two layers, 991 / 238", () => {
    const { r, block } = panel("hvac_insulation", { ...NIT, pipe_size_mm: "250 NB", thickness_mm: "Double layer of 19mm thick" }, "RMT", { base: 0, family: null, attrs: { pipe_size_mm: "50" } });
    expect(r.values).toEqual({ supply_rate: 991, install_rate: 238, combined_rate: 1229 });
    expect(block.working.filter((w) => /^Layer \d of 2/.test(w))).toHaveLength(2);
  });

  it("NEGATIVE: a pick made from a CLOSED list (the model's value was an option) is still a pick and still clears", () => {
    // the model said 100 (an option, box closed); the pricer PICKS 25 from the thickness list at that pipe -> cleared
    const { v, block } = panel("hvac_insulation", { item: PUF, cladding: "No", pipe_size_mm: "100", thickness_mm: "65" }, "RMT", { base: 0, family: null, attrs: { thickness_mm: "25" } });
    expect(v.rowPriced).toBe(false);
    expect(field(block, "thickness_mm").note).toMatch(/^25 mm is not stocked with the other answers/);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════════════════════
describe("SLICE 12d-8 / R4 option (b) -- Aluminium Foil is offered on the pipe families, derived from value_map", () => {
  it("the cladding list for Nitrile Rubber and Tubular PUF carries \"Aluminium Foil\"; Acoustic Nitrile does not; the sheet families carry no glass cloth", () => {
    expect(fieldOptionsFromSkus(SPEC, ITEMS, NR, "length", "cladding", {})).toContain("Aluminium Foil");
    expect(fieldOptionsFromSkus(SPEC, ITEMS, PUF, "length", "cladding", {})).toContain("Aluminium Foil");
    expect(fieldOptionsFromSkus(SPEC, ITEMS, "Acoustic Nitrile Insulation", "area", "cladding", {})).not.toContain("Aluminium Foil");
    for (const fam of ["Thermal Nitrile Insulation", "Acoustic Nitrile Insulation", " Fiberglass Rigid Board Insulation, Density 48Kg/m3"]) {
      expect(fieldOptionsFromSkus(SPEC, ITEMS, fam, "area", "cladding", {}).some((o) => /glass cloth/i.test(o))).toBe(false);
    }
    // DERIVED: the word comes from the config's own value_map entry, never from code
    const rule = (SPEC.value_map ?? []).find((m) => m.attr === "cladding" && m.to !== undefined)!;
    expect(rule.from).toBe("Aluminium Foil");
    expect(rule.families).toEqual([NR, PUF]);
  });

  it("calculator: Foil picked on Nitrile (pipe 50, 19 mm) prices exactly as 26G -- 615 / 224 -- with the value_map line, and is NOT cleared", () => {
    const foil = calculator("hvac_insulation", NR, { cladding: "Aluminium Foil", thickness_mm: "19", pipe_size_mm: "50" }, "mts", ["pipe_size_mm"]);
    const g26 = calculator("hvac_insulation", NR, { cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: "50" }, "mts", ["pipe_size_mm"]);
    expect(foil.r.values).toEqual({ supply_rate: 615, install_rate: 224, combined_rate: 839 });
    expect(foil.r.values).toEqual(g26.r.values);
    expect(foil.block.working).toContain("foil on a pipe is priced as 26G cladding");
    expect(field(foil.block, "cladding").options).toContain("Aluminium Foil");
    expect(field(foil.block, "cladding").note ?? "").not.toMatch(/not stocked/);
  });

  it("calculator: Foil picked on PUF (pipe 100, 65 mm) prices exactly as 26G with the line", () => {
    const foil = calculator("hvac_insulation", PUF, { cladding: "Aluminium Foil", thickness_mm: "65", pipe_size_mm: "100" }, "mts", ["pipe_size_mm"]);
    const g26 = calculator("hvac_insulation", PUF, { cladding: "26G Aluminium", thickness_mm: "65", pipe_size_mm: "100" }, "mts", ["pipe_size_mm"]);
    expect(foil.block.state).toBe("priced");
    expect(foil.r.values).toEqual(g26.r.values);
    expect(foil.block.working).toContain("foil on a pipe is priced as 26G cladding");
  });

  it("panel: the model's Foil on Nitrile still maps, and the panel's cladding list offers it too", () => {
    const { r, block } = panel("hvac_insulation", { ...NIT, cladding: "Aluminium Foil" }, "RMT");
    expect(r.values).toEqual({ supply_rate: 615, install_rate: 224, combined_rate: 839 });
    expect(field(block, "cladding").options).toContain("Aluminium Foil");
  });

  it("NEGATIVE (EXCLUDED by R4, 'not offered by design'): Foil on Acoustic Nitrile and glass cloth on Thermal Nitrile are not offered, so a pick is cleared and the row refuses", () => {
    const aco = calculator("hvac_insulation", "Acoustic Nitrile Insulation", { cladding: "Aluminium Foil", thickness_mm: "19" }, "sqm");
    expect(aco.v.rowPriced).toBe(false);
    expect(field(aco.block, "cladding").options).not.toContain("Aluminium Foil");
    expect(field(aco.block, "cladding").note).toBe("Aluminium Foil is not stocked with the other answers on this item -- choose again");
    const thm = calculator("hvac_insulation", "Thermal Nitrile Insulation", { cladding: "Glass Cloth with paint", thickness_mm: "19" }, "sqm");
    expect(thm.v.rowPriced).toBe(false);
    expect((field(thm.block, "cladding").options ?? []).some((o) => /glass cloth/i.test(o))).toBe(false);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════════════════════
describe("SLICE 12d-8 / R5 + R6 -- the Derivation tab, generated from config", () => {
  it("Insulation: 24 lines; line 9 says a range takes its top value (a comma list and a tolerance still refuse)", () => {
    const lines = itemListRuleOrder(INS, ITEMS);
    expect(lines).toHaveLength(24);
    const several = lines.find((l) => /^Several thickness values stated take the highest$/.test(l.title))!;
    expect(several.n).toBe(9);
    expect(several.detail).toBe("a bare slash list ('19 / 25 / 32'); a size range ('25 to 50') takes its top value; a comma list and a tolerance ('25 +/- 2') still refuse");
    expect(several.detail).not.toMatch(/\('25 to 50'\), a comma list and a tolerance .* still refuse/);
  });

  it("ADP: 18 lines; the outer-size match has its own line, before the ladders, in the config's own words", () => {
    const lines = itemListRuleOrder(ADP, ITEMS);
    expect(lines).toHaveLength(18);
    const outer = lines.find((l) => /outer size/.test(l.title))!;
    expect(outer.title).toBe("A stated outer size is matched beside the neck size on square diffuser");
    expect(outer.detail).toBe("both stated: the outer size narrows the products the neck size then fits; outer size only: the one product behind it is used as it stands, else the largest neck size behind it; an outer size the catalogue does not stock is set aside and the neck size prices the row; the catalogue's alternative wording of the same size counts as that size");
    const ladder = lines.find((l) => /^Fitting the stated diameter/.test(l.title))!;
    expect(outer.n).toBeLessThan(ladder.n);
  });

  it("NEGATIVE: a config without second_key gains no line (Insulation), and a key with no name / primary is skipped", () => {
    expect(itemListRuleOrder(INS, ITEMS).some((l) => /outer size|matched beside/.test(l.title))).toBe(false);
    const broken = { ...ADP, list_spec: { ...(ADP as any).list_spec, pricing: { ...(ADP as any).list_spec.pricing, second_key: [{ families: ["square diffuser"] }] } } };
    expect(itemListRuleOrder(broken, ITEMS)).toHaveLength(17);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════════════════════
describe("SLICE 12d-8 / U7 + U8 -- the 12d-6 leftovers", () => {
  it("U7: the typed-refusal note carries the unit once -- \"You typed Double layer of 19 mm thick: Type the thickness as a single number in mm\"", () => {
    const { block } = calculator("hvac_insulation", NR, { cladding: "26G Aluminium", thickness_mm: "Double layer of 19 mm thick", pipe_size_mm: "50" }, "mts", ["thickness_mm", "pipe_size_mm"]);
    expect(field(block, "thickness_mm").note).toBe("You typed Double layer of 19 mm thick: Type the thickness as a single number in mm");
    expect(field(block, "thickness_mm").note).not.toMatch(/thick mm/);
  });

  it("U7 NEGATIVE: a bare typed number keeps its unit in the note (\"You typed 22.2 mm -> priced as 22.23 mm ...\")", () => {
    const { block } = calculator("hvac_insulation", NR, { cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: "22.2" }, "mts", ["pipe_size_mm"]);
    expect(field(block, "pipe_size_mm").note).toBe("You typed 22.2 mm -> priced as 22.23 mm (the sheet's own spelling of this size)");
  });

  it.each([
    ["1¼\"", 31.75], ["1½\"", 38.1], ["¾\"", 19.05], ["⅝\"", 15.875], ["⅜\"", 9.525], ["⅞\"", 22.225], ["2⅛\"", 53.975],
  ])("U8: the unicode inch %s reads as %s mm on the pipe-size reader", (text, mm) => {
    const r = readNumber(text, SPEC.numbers.pipe_size_mm);
    expect(r && "value" in r ? Number(r.value.toFixed(3)) : r).toBe(mm);
  });

  it("U8: the normaliser and the ASCII forms are byte-identical where no such character occurs", () => {
    expect(unicodeFractions("1¼\"")).toBe("1-1/4\"");
    expect(unicodeFractions("¾\"")).toBe("3/4\"");
    expect(unicodeFractions("1-1/4\"")).toBe("1-1/4\"");
    expect(unicodeFractions("50 NB")).toBe("50 NB");
    for (const t of ["1-1/4\"", "1 1/4\"", "5/8\"", "1\"", "100 mm NB"]) {
      const r = readNumber(t, SPEC.numbers.pipe_size_mm);
      expect(r && "value" in r ? r.value : r).toBe(readNumber(unicodeFractions(t), SPEC.numbers.pipe_size_mm) && (readNumber(t, SPEC.numbers.pipe_size_mm) as any).value);
    }
  });

  it("U8 on the panel: pipe 1¼\" with 13 mm -> 31.75 -> 34.93 (next size up), 408 / 224 (the 12d-6 C4 figure)", () => {
    const { r, block } = panel("hvac_insulation", { ...NIT, thickness_mm: "13", pipe_size_mm: "1¼\"" }, "RMT");
    expect(r.values).toEqual({ supply_rate: 408, install_rate: 224, combined_rate: 632 });
    expect(field(block, "pipe_size_mm").note).toBe("BoQ says 31.75 mm -> priced as 34.93 mm (next size up)");
  });

  it("U8 NEGATIVE: a vulgar fraction on the thickness reader (inches: false) still refuses as inches", () => {
    const r = readNumber("¾\"", SPEC.numbers.thickness_mm);
    expect(r && "blank" in r ? r.blank : r).toBe("thickness stated in inches ('¾\"')");
  });
});
