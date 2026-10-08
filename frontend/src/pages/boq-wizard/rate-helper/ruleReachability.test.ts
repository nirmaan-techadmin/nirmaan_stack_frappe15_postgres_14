/**
 * SLICE 12d-8 / T1 + T3 (owner standing rules 1 and 3, approved 2026-10-08; built in 12d-7 Phase 1, made
 * permanent here) -- EVERY RULE FIRES FROM THE PANEL'S ENTRY POINT.
 *
 * 12d-6 found a rule (the double-layer reader) that worked in the inner pricer and in its tests and never
 * fired on the panel, because an EARLIER step on the path (option matching) rewrote the wording first. So:
 *
 *   T1  one named case per Derivation-tab rule of Insulation and ADP -- model-read, typed where a control
 *       exists, and its negative -- run through `makePricingSheetHelper(...).compute` on the LIVE v33 asset
 *       (read at runtime). PASS = the rule's OWN line / note / refusal appears AND the figure equals the
 *       pure pricer's over the same assembled inputs. EXCLUDED = an owner ruling forbids it on that path
 *       (T6 / U4 for a typed layered or slash thickness; R4 for a cladding the family does not offer).
 *
 *   THE GUARD: the set of rules this file names must EQUAL the set `itemListRuleOrder` generates from the
 *   config at runtime. A new rule with no case fails the suite; a case naming a rule that no longer exists
 *   fails it too. Two tab lines are declared NOT panel-path rules by name (the derived catalogue cells) and
 *   are checked to exist.
 *
 *   T3  the rewriter x rule matrix (12d-7 S4) kept as tests, with the 12d-7 findings F-1 / F-2 / F-3 as
 *       regression pins.
 */
import { describe, expect, it } from "vitest";
import type { RateCategoryConfig, RateMasterItem } from "@/pages/pricing/rate-master/rateMasterTypes";
import type { ExtractionRow, RateHelperRowContext } from "./rateHelperTypes";
import { isSuggestion } from "./rateHelperTypes";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";
import { itemListRuleOrder } from "@/pages/pricing/rate-master/itemListRuleOrder";
import {
  ITEM_LIST_OVERRIDE_KEY, ROW_UNIT_OVERRIDE_KEY, assembleItems, decodeItemEdits, makePricingSheetHelper,
  type ItemListSuggestion,
} from "./pricingSheetHelper";
import { familyAttr, itemListPricingSpec, priceItemList } from "./itemListPricing";

const ASSET = readJsonFixture<{ discipline: string; items: Array<Omit<RateMasterItem, "discipline">>; category_configs: RateCategoryConfig[] }>(
  new URL("../../../../../nirmaan_stack/services/boq_rate_master/data/rate_master_hvac_all_v33.json", import.meta.url),
);
const CFG: Record<string, RateCategoryConfig> = Object.fromEntries(ASSET.category_configs.map((c) => [c.category_id, c]));
const CONFIGS = new Map<string, RateCategoryConfig>(Object.entries(CFG));
const ITEMS: RateMasterItem[] = ASSET.items.map((it) => ({ ...it, discipline: ASSET.discipline } as RateMasterItem));
const INS = "hvac_insulation";
const ADP = "hvac_adp";

// ── the cases ───────────────────────────────────────────────────────────────────────────────────────
type Edit = { base: number | null; family: string | null; attrs: Record<string, string>; other?: string[]; qty?: string };
interface Case {
  id: string;
  /** the Derivation-tab line this case fires -- its exact generated TITLE (the guard matches on it) */
  rule: string;
  cat: string;
  path: "panel" | "calc" | "ptyped";
  kind: "pos" | "neg" | "excluded";
  excludedBy?: string;
  unit?: string;                              // the row's unit (panel); undefined => pickable
  rowUnit?: string;                           // the calculator's unit pick
  model?: Array<Record<string, string>>;      // the stored extraction's items (panel / ptyped)
  edits?: Edit[];                             // session edits (calc / ptyped)
  description?: string; headings?: string[]; ownNotes?: string[];
  /** the rule's OWN line(s): every regex must appear in the panel's lines; none of `not` may */
  re: Array<string | RegExp>; not?: Array<string | RegExp>;
  /** lines that must appear in a block's WORKING -- the pricer's own output, never a display note (F-2: the reader's line must reach the pricer) */
  working?: Array<string | RegExp>;
  priced?: boolean;
  /** compare the panel's figures to the pure pricer's over the same assembled inputs (default true) */
  pure?: boolean;
}
const NR = "Nitrile Rubber Insulation", PUF = "Tubular Puf Insulation", THM = "Thermal Nitrile Insulation",
  ACO = "Acoustic Nitrile Insulation", FGB = " Fiberglass Rigid Board Insulation, Density 48Kg/m3", CLO = "Cladding Only";
const NIT = { item: NR, cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: "50" };
const PUFI = { item: PUF, cladding: "No", thickness_mm: "25", pipe_size_mm: "100" };
const THMI = { item: THM, cladding: "No", thickness_mm: "19" };
const m = (base: Record<string, string>, over: Record<string, string | undefined>): Record<string, string> => {
  const d: Record<string, string> = { ...base };
  for (const [k, v] of Object.entries(over)) { if (v === undefined) delete d[k]; else d[k] = v; }
  return d;
};
const calc = (family: string, attrs: Record<string, string>, other: string[] = [], qty?: string): Edit[] => [{ base: null, family, attrs, other, ...(qty !== undefined ? { qty } : {}) }];
const ptyped = (attrs: Record<string, string>, other: string[] = [], qty?: string): Edit[] => [{ base: 0, family: null, attrs, other, ...(qty !== undefined ? { qty } : {}) }];

// the exact TITLES `itemListRuleOrder` generates (verified by the guard below; a typo here fails the suite)
const T = {
  unit: "The row's unit decides which kind of rate applies",
  kind: "The item's own kind decides which products can price it",
  famNone: "A row that names no material takes the kind its row implies",
  noSku: "A material the model could not match to any kind refuses",
  unstocked: "A material the catalogue does not stock refuses by name, whatever kind was picked",
  ruleForUnit: "That kind's rule for that unit",
  notOffered: "A kind the catalogue does not price in the row's unit",
  needs: "The facts that rule needs before it can price",
  layers: "A thickness the model writes as layers is priced as those layers",
  several: "Several thickness values stated take the highest",
  inches: "A pipe size written in inches is converted to millimetres",
  defaults: "A fact the row does not mention takes its ruled value",
  override: "A ruling that replaces a value the row DID state",
  foilPipe: "Aluminium Foil as the cladding on Nitrile Rubber Insulation, Tubular Puf Insulation is priced as 26G Aluminium",
  foilAco: "Aluminium Foil as the cladding on Acoustic Nitrile Insulation refuses",
  glassSheet: "Glass Cloth as the cladding on a per-sq.m row of Thermal Nitrile Insulation, Acoustic Nitrile Insulation, Fiberglass Rigid Board Insulation, Density 48Kg/m3 refuses",
  namedInRow: "A cladding named in the row's own text but read as not mentioned refuses",
  readNotes: "A Fiberglass Rigid Board Insulation, Density 48Kg/m3 row stating its own figure in the insulation material as written carries a line saying what was priced",
  outer: "A stated outer size is matched beside the neck size on square diffuser",
  fitPipe: "Fitting the stated pipe size to the catalogue",
  fitThk: "Fitting the stated thickness to the catalogue",
  fitDia: "Fitting the stated diameter to the catalogue",
  fitNeck: "Fitting the stated neck size to the catalogue",
  fitTorque: "Fitting the stated torque to the catalogue",
  fitRatio: "Fitting the stated panel ratio to the catalogue",
  fitPlenum: "Fitting the stated plenum thickness to the catalogue",
  steps: "Then the priced steps below, in their own order",
  crossRow: "A rate read live from another catalogue row",
  computed: "A cost the rules compute from the Pricing Inputs and the row's own geometry is shown greyed, never typed",
  derived: "A catalogue cell derived from another row's cell follows its base",
  convert: "The rate converts to the unit the row is written in",
  qty: "Multiplied by how many of the item one unit of the row pays for",
};
/** Tab lines that are NOT panel-path rules (a catalogue / rate-master rule the pricer never reads), by name. */
const NOT_PANEL_RULES: Record<string, string> = {
  [T.derived]: "config.derived_rates is consumed by csv_exporter / the loader / RateMasterDataViewer, never by priceItemList",
};

const CASES: Case[] = [
  // ── INSULATION ──────────────────────────────────────────────────────────────────────────────────
  { id: "I1a", rule: T.unit, cat: INS, path: "panel", kind: "pos", unit: "sqft", model: [THMI], re: ["per sq.ft: sq.m rate x 0.0929"], priced: true },
  { id: "I1a-calc", rule: T.unit, cat: INS, path: "calc", kind: "pos", edits: calc(THM, { cladding: "No", thickness_mm: "19" }), rowUnit: "sqft", re: ["per sq.ft: sq.m rate x 0.0929"], priced: true },
  { id: "I1b", rule: T.unit, cat: INS, path: "panel", kind: "pos", unit: "", model: [NIT], re: ["No unit on the BoQ row -> priced per metre"], priced: true },
  { id: "I1c", rule: T.unit, cat: INS, path: "panel", kind: "pos", unit: "R/O", model: [NIT], re: ["BoQ says R/O (rate only) -> priced per metre"], priced: true },
  { id: "I1d", rule: T.unit, cat: INS, path: "panel", kind: "pos", unit: "QRO - Sqm.", model: [THMI], re: ["BoQ says QRO - Sqm. (rate only) -> priced per sq.m"], priced: true },
  { id: "I1e", rule: T.unit, cat: INS, path: "panel", kind: "pos", unit: "", model: [{ item: CLO, cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: "50" }], re: ["No unit on the BoQ row - this item is priced per metre or per sq.m; set the unit"], priced: false },
  { id: "I1f-neg", rule: T.unit, cat: INS, path: "panel", kind: "neg", unit: "nos", model: [NIT], re: ["unit 'nos' is not a count, area or length unit"], priced: false },
  { id: "I2a", rule: T.kind, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [NIT], re: [], priced: true },
  { id: "I2b-neg", rule: T.kind, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { item: "Foo Insulation" })], re: ["no SKU in the catalogue for 'Foo Insulation' -- the user decides"], priced: false },
  { id: "I3a", rule: T.famNone, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { item: "None" })], re: ["item not mentioned -> Nitrile Rubber Insulation ("], priced: true },
  { id: "I3b", rule: T.famNone, cat: INS, path: "panel", kind: "pos", unit: "sqm", model: [m(THMI, { item: "None" })], re: ["item not mentioned -> Thermal Nitrile Insulation ("], priced: true },
  { id: "I3c", rule: T.famNone, cat: INS, path: "panel", kind: "pos", unit: "sqm", model: [m(THMI, { item: "None" })], headings: ["Acoustic lining of AHU room"], re: ["item not mentioned -> Acoustic Nitrile Insulation ("], priced: true },
  { id: "I3c-neg", rule: T.famNone, cat: INS, path: "panel", kind: "neg", unit: "sqm", model: [THMI], headings: ["Acoustic lining"], re: ["family:Thermal Nitrile Insulation"], not: ["not mentioned ->"], priced: true },
  { id: "I3a-calc", rule: T.famNone, cat: INS, path: "calc", kind: "pos", edits: [{ base: null, family: null, attrs: { cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: "50" }, other: ["pipe_size_mm"] }], rowUnit: "mts", re: ["item not mentioned -> Nitrile Rubber Insulation ("] },
  { id: "I4a", rule: T.noSku, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { item: "none of these", material_as_written: "XLPE foam" })], re: ["No SKU in the catalogue for XLPE foam - price this row by hand"], priced: false },
  { id: "I4b-neg", rule: T.noSku, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { item: "none of these" })], re: ["no SKU in the catalogue for 'none of these' -- the user decides"], not: ["price this row by hand"], priced: false },
  { id: "I5a", rule: T.unstocked, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { material_as_written: "EPDM closed cell" })], re: ["No SKU in the catalogue for EPDM closed cell - price this row by hand"], priced: false },
  { id: "I5b", rule: T.unstocked, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [NIT], ownNotes: ["Rockwool as per spec"], re: ["No SKU in the catalogue for ROCKWOOL - price this row by hand"], priced: false },
  { id: "I5c-neg", rule: T.unstocked, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [NIT], headings: ["Rockwool section"], re: [], not: ["No SKU in the catalogue"], priced: true },
  { id: "I6a", rule: T.ruleForUnit, cat: INS, path: "panel", kind: "pos", unit: "sqm", model: [NIT], re: ["no SKU per sq.m for Nitrile Rubber Insulation"], priced: false },
  { id: "I6b-neg", rule: T.ruleForUnit, cat: INS, path: "panel", kind: "neg", unit: "sqm", model: [{ item: CLO, cladding: "26G Aluminium" }], re: [], not: ["no SKU per"], priced: true },
  { id: "I7a", rule: T.needs, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { pipe_size_mm: undefined })], re: ["no pipe size stated"], priced: false },
  { id: "I7b-neg", rule: T.needs, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [NIT], re: [], not: [/no (pipe size|thickness|cladding) stated/], priced: true },
  { id: "I7a-calc", rule: T.needs, cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "26G Aluminium", thickness_mm: "19" }), rowUnit: "mts", re: ["no pipe size stated"], priced: false },
  { id: "I8a", rule: T.layers, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { thickness_mm: "Double layer of 19mm thick" })], re: ["priced as two layers, 19 + 19 mm (38 mm); cladding on the outer layer only", "Layer 1 of 2", "Layer 2 of 2"], priced: true },
  { id: "I8b", rule: T.layers, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { thickness_mm: "13 + 19 mm" })], re: ["priced as two layers, 13 + 19 mm (32 mm)"], priced: true },
  { id: "I8c", rule: T.layers, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(PUFI, { thickness_mm: "25 mm - 2 Layers" })], re: ["priced as two layers, 25 + 25 mm (50 mm)"], priced: true },
  { id: "I8e-neg", rule: T.layers, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { thickness_mm: "19 mm" })], re: [], not: ["priced as two layers", "Layer 1 of"], priced: true },
  { id: "I8x-calc", rule: T.layers, cat: INS, path: "calc", kind: "excluded", excludedBy: "T6 (12d-1b) + U4 (12d-6): a typed thickness is never parsed as layers; a non-number typed thickness refuses", edits: calc(NR, { cladding: "26G Aluminium", thickness_mm: "Double layer of 19 mm", pipe_size_mm: "50" }, ["thickness_mm", "pipe_size_mm"]), rowUnit: "mts", re: ["Type the thickness as a single number in mm"], priced: false },
  { id: "I8x-ptyped", rule: T.layers, cat: INS, path: "ptyped", kind: "excluded", excludedBy: "T6 + U4", unit: "RMT", model: [NIT], edits: ptyped({ thickness_mm: "Double layer of 19 mm" }, ["thickness_mm"]), re: ["Type the thickness as a single number in mm"], priced: false },
  { id: "I9a", rule: T.several, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { thickness_mm: "13 / 19 / 25" })], re: ["states several values -- the highest, 25, is taken", "BoQ says 13 / 19 / 25 -> 25 mm (states several values -- the highest, 25, is taken)"], not: ["own spelling"], priced: true },
  { id: "I9b-neg", rule: T.several, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { thickness_mm: "13, 19, 25" })], re: ["several values stated for thickness"], priced: false },
  { id: "I9c-neg", rule: T.several, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { thickness_mm: "25 +/- 2" })], re: ["several values stated for thickness"], priced: false },
  { id: "I9d", rule: T.several, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(PUFI, { thickness_mm: "25 to 50" })], re: ["range '25 to 50' -> its top value 50", "BoQ says 25 to 50 -> 50 mm (range"], priced: true },
  { id: "I9x-calc", rule: T.several, cat: INS, path: "calc", kind: "excluded", excludedBy: "U4", edits: calc(NR, { cladding: "26G Aluminium", thickness_mm: "13 / 19 / 25", pipe_size_mm: "50" }, ["thickness_mm", "pipe_size_mm"]), rowUnit: "mts", re: ["Type the thickness as a single number in mm"], priced: false },
  { id: "I10a", rule: T.inches, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { pipe_size_mm: '5/8"' })], re: ["15.88"], priced: true },
  { id: "I10b", rule: T.inches, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { pipe_size_mm: '1-1/4"' })], re: ["31.75", "34.93"], priced: true },
  { id: "I10u", rule: T.inches, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { pipe_size_mm: "1¼\"" })], re: ["31.75", "34.93"], priced: true },
  { id: "I10b-calc", rule: T.inches, cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: '1-1/4"' }, ["pipe_size_mm"]), rowUnit: "mts", re: ["31.75", "34.93"], priced: true },
  { id: "I10c-neg", rule: T.inches, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { thickness_mm: '3/4"' })], re: ["thickness stated in inches"], priced: false },
  { id: "I11a", rule: T.defaults, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { cladding: "None" })], re: ["cladding not mentioned -> No ("], priced: true },
  { id: "I11b", rule: T.defaults, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { thickness_mm: undefined })], re: ["thickness_mm not mentioned -> 9 (", "thickness 9 is not on the sheet -> 13"], priced: true },
  { id: "I11c-neg", rule: T.defaults, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { thickness_mm: "as per specification" })], re: ["no number in 'as per specification' for thickness"], not: ["not mentioned -> 9"], priced: false },
  { id: "I11a-calc", rule: T.defaults, cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "None", thickness_mm: "19", pipe_size_mm: "50" }, ["pipe_size_mm"]), rowUnit: "mts", re: ["cladding not mentioned -> No ("], priced: true },
  { id: "I11b-calc", rule: T.defaults, cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "26G Aluminium", pipe_size_mm: "50" }, ["pipe_size_mm"]), rowUnit: "mts", re: ["thickness_mm not mentioned -> 9 ("], priced: true },
  { id: "I12a", rule: T.foilPipe, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { cladding: "Aluminium Foil" })], re: ["foil on a pipe is priced as 26G cladding"], priced: true },
  { id: "I12a-calc", rule: T.foilPipe, cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "Aluminium Foil", thickness_mm: "19", pipe_size_mm: "50" }, ["pipe_size_mm"]), rowUnit: "mts", re: ["foil on a pipe is priced as 26G cladding"], not: ["not stocked with the other answers"], priced: true },
  { id: "I12b-neg", rule: T.foilPipe, cat: INS, path: "panel", kind: "neg", unit: "sqm", model: [m(THMI, { cladding: "Aluminium Foil" })], re: [], not: ["foil on a pipe"], priced: true },
  { id: "I13a", rule: T.foilAco, cat: INS, path: "panel", kind: "pos", unit: "sqm", model: [{ item: ACO, cladding: "Aluminium Foil", thickness_mm: "19" }], re: ["foil on an acoustic row"], priced: false },
  { id: "I13a-calc", rule: T.foilAco, cat: INS, path: "calc", kind: "excluded", excludedBy: "not offered by design - owner R4, 2026-10-09", edits: calc(ACO, { cladding: "Aluminium Foil", thickness_mm: "19" }), rowUnit: "sqm", re: ["Aluminium Foil is not stocked with the other answers on this item -- choose again", "choose again: cladding"], not: ["foil on a pipe"], priced: false, pure: false },
  { id: "I13b-neg", rule: T.foilAco, cat: INS, path: "panel", kind: "neg", unit: "sqm", model: [{ item: ACO, cladding: "No", thickness_mm: "19" }], re: [], not: ["foil on an acoustic row"], priced: true },
  { id: "I14a", rule: T.glassSheet, cat: INS, path: "panel", kind: "pos", unit: "sqm", model: [m(THMI, { cladding: "Glass Cloth with paint" })], re: ["glass cloth is not offered on sheet insulation"], priced: false },
  { id: "I14b", rule: T.glassSheet, cat: INS, path: "panel", kind: "pos", unit: "sqm", model: [m(THMI, { cladding: "None" })], description: "Thermal insulation with glass cloth finish", re: ["glass cloth is not offered on sheet insulation"], priced: false },
  { id: "I14c-neg", rule: T.glassSheet, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { cladding: "Glass Cloth with paint" })], re: [], not: ["glass cloth is not offered"], priced: true },
  { id: "I14d-neg", rule: T.glassSheet, cat: INS, path: "panel", kind: "neg", unit: "sqm", model: [m(THMI, { cladding: "None" })], headings: ["Glass cloth finish section"], re: [], not: ["glass cloth is not offered"], priced: true },
  { id: "I14a-calc", rule: T.glassSheet, cat: INS, path: "calc", kind: "excluded", excludedBy: "not offered by design - owner R4, 2026-10-09", edits: calc(THM, { cladding: "Glass Cloth with paint", thickness_mm: "19" }), rowUnit: "sqm", re: ["Glass Cloth with paint is not stocked with the other answers on this item -- choose again"], priced: false, pure: false },
  { id: "I15a", rule: T.namedInRow, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { cladding: "None" })], description: "Nitrile insulation with 26G aluminium cladding", re: ["cladding named in this row but not read - set the cladding"], priced: false },
  { id: "I15b-neg", rule: T.namedInRow, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { cladding: "None" })], headings: ["Aluminium cladding section"], re: ["cladding not mentioned -> No ("], not: ["cladding named in this row"], priced: true },
  { id: "I15c-neg", rule: T.namedInRow, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [NIT], description: "with 26G aluminium cladding", re: [], not: ["cladding named in this row"], priced: true },
  { id: "I16a", rule: T.readNotes, cat: INS, path: "panel", kind: "pos", unit: "sqm", model: [{ item: FGB, cladding: "No", thickness_mm: "25", material_as_written: "Fiberglass rigid board 32 kg/m3" }], re: ["BoQ says 32 kg/m3 -> priced as the 48 kg/m3 board"], priced: true },
  { id: "I16b-neg", rule: T.readNotes, cat: INS, path: "panel", kind: "neg", unit: "sqm", model: [{ item: FGB, cladding: "No", thickness_mm: "25", material_as_written: "Fiberglass board 48 kg/m3" }], re: [], not: ["priced as the 48 kg/m3 board"], priced: true },
  { id: "I17a", rule: T.fitPipe, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [NIT], re: ["pipe size 50 is not on the sheet -> 53.98 (next size up"], priced: true },
  { id: "I17a-calc", rule: T.fitPipe, cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: "50" }, ["pipe_size_mm"]), rowUnit: "mts", re: ["pipe size 50 is not on the sheet -> 53.98 (next size up"], priced: true },
  { id: "I17b", rule: T.fitPipe, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { pipe_size_mm: "22.2" })], re: ["pipe size 22.2 is 22.23 on the sheet"], priced: true },
  { id: "I17c-neg", rule: T.fitPipe, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { pipe_size_mm: "65" })], re: ["pipe size 65 is above the largest size on the sheet (53.98)"], priced: false },
  { id: "I18a", rule: T.fitThk, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { pipe_size_mm: "19.05", thickness_mm: "20" })], re: ["thickness 20 is not on the sheet -> 25 (next size up"], priced: true },
  { id: "I18b", rule: T.fitThk, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { pipe_size_mm: "19.05", thickness_mm: "30" })], re: ["-> priced as 13 + 19 mm (32 mm, +2) -- above the largest stocked size (25 mm)"], priced: true },
  { id: "I18b-calc", rule: T.fitThk, cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "26G Aluminium", thickness_mm: "30", pipe_size_mm: "19.05" }, ["thickness_mm"]), rowUnit: "mts", re: ["You typed 30 mm -> priced as 13 + 19 mm (32 mm, +2) -- above the largest stocked size (25 mm)"], priced: true },
  { id: "I18c-neg", rule: T.fitThk, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { pipe_size_mm: "19.05", thickness_mm: "200" })], re: ["thickness 200 is above the largest size on the sheet (25)"], priced: false },
  { id: "I19a", rule: T.steps, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [NIT], re: ["supply: pricing input: Aluminium sheet 26G (rate) = 450"], priced: true },
  { id: "I19b-neg", rule: T.steps, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { pipe_size_mm: "65" })], re: [], not: ["supply: pricing input"], priced: false },
  { id: "I20a", rule: T.crossRow, cat: INS, path: "panel", kind: "pos", unit: "sqm", model: [{ item: CLO, cladding: "26G Aluminium" }], re: ["the cladding-only SKU's own"], priced: true },
  { id: "I20b-neg", rule: T.crossRow, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [NIT], re: [], not: ["cladding-only SKU's own"], priced: true },
  { id: "I21a", rule: T.computed, cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [NIT], re: ["supply: cladding: (aluminium sheet x overlap + glass cloth) x girth ="], priced: true },
  { id: "I21b-neg", rule: T.computed, cat: INS, path: "panel", kind: "neg", unit: "RMT", model: [m(NIT, { cladding: "No" })], re: ["supply: cladding: (aluminium sheet x overlap + glass cloth) x girth = 0"], priced: true },
  { id: "I23a", rule: T.convert, cat: INS, path: "panel", kind: "pos", unit: "sqft", model: [THMI], re: ["per sq.ft: sq.m rate x 0.0929"], priced: true },
  { id: "I23b-neg", rule: T.convert, cat: INS, path: "panel", kind: "neg", unit: "sqm", model: [THMI], re: [], not: ["per sq.ft"], priced: true },
  { id: "I24a-ptyped", rule: T.qty, cat: INS, path: "ptyped", kind: "pos", unit: "RMT", model: [NIT], edits: ptyped({}, [], "2"), re: ["x 2 per row unit"], priced: true },
  { id: "I24b-ptyped-neg", rule: T.qty, cat: INS, path: "ptyped", kind: "neg", unit: "RMT", model: [NIT], edits: ptyped({}, [], "0"), re: ["quantity per row unit '0' is not a positive number"], priced: false },
  { id: "I24a-calc", rule: T.qty, cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: "50" }, ["pipe_size_mm"], "2"), rowUnit: "mts", re: ["x 2 per row unit"], priced: true },

  // ── ADP ─────────────────────────────────────────────────────────────────────────────────────────
  { id: "A1a", rule: T.unit, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "VCD", variant: "GI rectangular", size_mm: "600x600" }], re: ["per-number row: per-sq.m rate x W x H"], priced: true },
  { id: "A1b", rule: T.unit, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "VCD", variant: "GI rectangular", area_band: "0.5 to 1 sqm" }], re: ["area band: per-sq.m rate x the band's maximum area"], priced: true },
  { id: "A1c", rule: T.unit, cat: ADP, path: "panel", kind: "pos", unit: "", model: [{ family: "VCD", variant: "GI rectangular", size_mm: "600x600" }], re: ["No unit on the BoQ row - this item is priced per sq.m or per number; set the unit"], priced: false },
  { id: "A1d", rule: T.unit, cat: ADP, path: "panel", kind: "pos", unit: "", model: [{ family: "actuator", ul: "no", torque: "10" }], re: ["No unit on the BoQ row -> priced per number"], priced: true },
  { id: "A1f-neg", rule: T.unit, cat: ADP, path: "panel", kind: "neg", unit: "kg", model: [{ family: "actuator", ul: "no", torque: "10" }], re: ["unit 'kg' is not a count, area or length unit"], priced: false },
  { id: "A1a-calc", rule: T.unit, cat: ADP, path: "calc", kind: "pos", edits: calc("VCD", { variant: "GI rectangular", size_mm: "600x600" }), rowUnit: "nos", re: ["per-number row: per-sq.m rate x W x H"], priced: true },
  { id: "A1h", rule: T.unit, cat: ADP, path: "panel", kind: "pos", unit: "rmt", model: [{ family: "linear grille", damper: "with", size_mm: "600x150" }], re: ["per-metre grille: per-sq.m rate x height in metres"], priced: true },
  { id: "A1i", rule: T.unit, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "flexible duct", insulated: "with", dia_mm: "200" }], re: ["per piece: per-metre rate x 2.5 m standard length"], priced: true },
  { id: "A1j", rule: T.unit, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "mixing box / LP plenum", insulated: "with", size_mm: "750x150x350" }], re: ["per-number mixing box at any size"], priced: true },
  { id: "A2a", rule: T.kind, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "grille, type not stated", damper: "with", size_mm: "600x150" }], re: ["'grille, type not stated' prices as linear grille"], priced: true },
  { id: "A2b-neg", rule: T.kind, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "linear grille", damper: "with", size_mm: "600x150" }], re: [], not: ["prices as"], priced: true },
  { id: "A3a", rule: T.noSku, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "none of these", damper: "with", dia_mm: "200" }], re: ["no SKU in the catalogue for 'none of these' -- the user decides"], priced: false },
  { id: "A3b-neg", rule: T.noSku, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "round diffuser", damper: "with", dia_mm: "200" }], re: [], not: ["the user decides"], priced: true },
  { id: "A4a", rule: T.ruleForUnit, cat: ADP, path: "panel", kind: "pos", unit: "rmt", model: [{ family: "spigot", dia_mm: "200" }], re: ["no SKU per metre for spigot"], priced: false },
  { id: "A4b-neg", rule: T.ruleForUnit, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "spigot", dia_mm: "200" }], re: [], not: ["no SKU per"], priced: true },
  { id: "A6a", rule: T.needs, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "actuator", ul: "no" }], re: ["no torque stated"], priced: false },
  { id: "A6b", rule: T.needs, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "round diffuser", damper: "with" }], re: ["no diameter stated"], priced: false },
  { id: "A6c-neg", rule: T.needs, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "actuator", ul: "no", torque: "10" }], re: [], not: [/no (torque|diameter|neck size|size) stated/], priced: true },
  { id: "A6a-calc", rule: T.needs, cat: ADP, path: "calc", kind: "pos", edits: calc("actuator", { ul: "no" }), rowUnit: "nos", re: ["no torque stated"], priced: false },
  { id: "A7a", rule: T.defaults, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "round diffuser", damper: "None", dia_mm: "200" }], re: ["damper not mentioned -> without ("], priced: true },
  { id: "A7b", rule: T.defaults, cat: ADP, path: "panel", kind: "pos", unit: "rmt", model: [{ family: "flexible duct", dia_mm: "200" }], re: ["insulated not mentioned -> with ("], priced: true },
  { id: "A7c", rule: T.defaults, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "actuator", torque: "10" }], re: ["ul not mentioned -> no ("], priced: true },
  { id: "A7d", rule: T.defaults, cat: ADP, path: "panel", kind: "pos", unit: "sqm", model: [{ family: "VCD" }], re: ["variant not mentioned -> GI rectangular ("], priced: true },
  { id: "A7e", rule: T.defaults, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "linear grille", damper: "None", air: "supply", size_mm: "600x150" }], re: ["damper not mentioned -> with (supply-air linear / plain grille = with damper)"], priced: true },
  { id: "A7e-neg", rule: T.defaults, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "linear grille", damper: "None", air: "return", size_mm: "600x150" }], re: ["damper not mentioned -> without ("], not: ["supply-air linear"], priced: true },
  { id: "A7f-neg", rule: T.defaults, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "round diffuser", damper: "with", dia_mm: "200" }], re: [], not: ["damper not mentioned"], priced: true },
  { id: "A7a-calc", rule: T.defaults, cat: ADP, path: "calc", kind: "pos", edits: calc("round diffuser", { damper: "None", dia_mm: "200" }), rowUnit: "nos", re: ["damper not mentioned -> without ("], priced: true },
  { id: "A8a", rule: T.override, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "fire damper", variant: "motorised", ul: "yes", size_mm: "600x600" }], re: ["UL stated, so the UL 555 SKU is used"], priced: true },
  { id: "A8b-neg", rule: T.override, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "fire damper", variant: "motorised", ul: "no", size_mm: "600x600" }], re: [], not: ["UL stated, so"], priced: true },
  { id: "A8a-calc", rule: T.override, cat: ADP, path: "calc", kind: "excluded", excludedBy: "owner R1 (12d-8): on the calculator a picked ul=yes beside a non-UL variant is cleared by the stale-pick rule and the row refuses; the UL variant picked directly prices the UL SKU without the rule", edits: calc("fire damper", { variant: "motorised", ul: "yes", size_mm: "600x600" }), rowUnit: "nos", re: ["yes is not stocked with the other answers on this item -- choose again", "choose again: whether it is UL listed"], not: ["ul not mentioned -> no"], priced: false, pure: false },
  { id: "A10c", rule: T.outer, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "square diffuser", damper: "with", size_mm: "595x595" }], re: ["matched on the outer size 595x595; largest neck size behind it is 450"], priced: true },
  { id: "A10d", rule: T.outer, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "square diffuser", damper: "with", size_mm: "600x600" }], re: ["the outer size 600x600 is the sheet's 595x595"], priced: true },
  { id: "A10e", rule: T.outer, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "square diffuser", damper: "with", neck_mm: "300", size_mm: "700x700" }], re: ["did not match the catalogue -- matched on the neck size instead"], priced: true },
  { id: "A10f-neg", rule: T.outer, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "square diffuser", damper: "with", neck_mm: "300" }], re: [], not: ["outer size"], priced: true },
  { id: "A9a", rule: T.fitDia, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "round diffuser", damper: "with", dia_mm: "220" }], re: ["diameter 220 is not on the sheet -> 250 (next size up"], priced: true },
  { id: "A9b-neg", rule: T.fitDia, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "round diffuser", damper: "with", dia_mm: "500" }], re: ["diameter 500 is above the largest size on the sheet (400)"], priced: false },
  { id: "A9a-calc", rule: T.fitDia, cat: ADP, path: "calc", kind: "pos", edits: calc("round diffuser", { damper: "with", dia_mm: "220" }, ["dia_mm"]), rowUnit: "nos", re: ["diameter 220 is not on the sheet -> 250 (next size up"], priced: true },
  { id: "A10a", rule: T.fitNeck, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "square diffuser", damper: "with", neck_mm: "320" }], re: ["neck size 320 is not on the sheet -> 375 (next size up"], priced: true },
  { id: "A10b-neg", rule: T.fitNeck, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "square diffuser", damper: "with", neck_mm: "500" }], re: ["neck size 500 is above the largest size on the sheet (450)"], priced: false },
  { id: "A11a", rule: T.fitTorque, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "actuator", ul: "no", torque: "12" }], re: ["torque 12 is not on the sheet -> 20 (next size up"], priced: true },
  { id: "A11b-neg", rule: T.fitTorque, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "actuator", ul: "no", torque: "25" }], re: ["torque 25 is above the largest size on the sheet (20)"], priced: false },
  { id: "A12a", rule: T.fitRatio, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "control panel", panel_ratio: "5" }], re: ["panel ratio 5 is not on the sheet -> 6 (next size up"], priced: true },
  { id: "A12b-neg", rule: T.fitRatio, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "control panel", panel_ratio: "13" }], re: ["panel ratio 13 is above the largest size on the sheet (12)"], priced: false },
  { id: "A13a", rule: T.fitPlenum, cat: ADP, path: "panel", kind: "pos", unit: "sqm", model: [{ family: "double-skin plenum", thickness_mm: "30" }], re: ["plenum thickness 30 is not on the sheet -> 50 (next size up"], priced: true },
  { id: "A13b-neg", rule: T.fitPlenum, cat: ADP, path: "panel", kind: "neg", unit: "sqm", model: [{ family: "double-skin plenum", thickness_mm: "60" }], re: ["plenum thickness 60 is above the largest size on the sheet (50)"], priced: false },
  { id: "A13a-calc", rule: T.fitPlenum, cat: ADP, path: "calc", kind: "pos", edits: calc("double-skin plenum", { thickness_mm: "30" }, ["thickness_mm"]), rowUnit: "sqm", re: ["plenum thickness 30 is not on the sheet -> 50 (next size up"], priced: true },
  { id: "A14a", rule: T.steps, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "round diffuser", damper: "with", dia_mm: "200" }], re: ["item supply:"], priced: true },
  { id: "A14b-neg", rule: T.steps, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "round diffuser", damper: "with", dia_mm: "500" }], re: [], not: ["item supply:"], priced: false },
  { id: "A16a", rule: T.convert, cat: ADP, path: "panel", kind: "pos", unit: "sqft", model: [{ family: "VCD", variant: "GI rectangular" }], re: ["per sq.ft: sq.m rate x 0.0929"], priced: true },
  { id: "A16b-neg", rule: T.convert, cat: ADP, path: "panel", kind: "neg", unit: "sqm", model: [{ family: "VCD", variant: "GI rectangular" }], re: [], not: ["per sq.ft"], priced: true },
  { id: "A17a", rule: T.qty, cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "round diffuser", damper: "with", dia_mm: "200", qty_per_row_unit: "2" }], re: ["x 2 per row unit"], priced: true },
  { id: "A17b-neg", rule: T.qty, cat: ADP, path: "panel", kind: "neg", unit: "nos", model: [{ family: "round diffuser", damper: "with", dia_mm: "200", qty_per_row_unit: "None" }], re: [], not: ["per row unit"], priced: true },
  { id: "A17c-ptyped", rule: T.qty, cat: ADP, path: "ptyped", kind: "pos", unit: "nos", model: [{ family: "round diffuser", damper: "with", dia_mm: "200", qty_per_row_unit: "2" }], edits: ptyped({}, [], "3"), re: ["x 3 per row unit"], not: ["x 2 per row unit"], priced: true },
];

/** ADP line 5 (`units_not_offered`) acts on the CALCULATOR'S UNIT PICKER, not on a row's price: it is covered
 *  by the unit-choices check below (a BoQ row arriving in a hidden unit prices exactly as before, by design). */
const PICKER_CASES: Array<{ rule: string; family: string; offered: string[]; notOffered: string[] }> = [
  { rule: T.notOffered, family: "double-skin plenum", offered: ["sqm"], notOffered: ["nos"] },
  { rule: T.notOffered, family: "VCD", offered: ["nos", "sqm"], notOffered: [] },
];

// ── the runner: the panel's entry point on each path, beside the pure pricer ────────────────────────
const cells = (a: Record<string, string>) => Object.fromEntries(Object.entries(a).map(([k, v]) => [k, { value: v, confidence: 0.9 }]));
function run(c: Case) {
  const modelItems = (c.model ?? []).map((a) => ({ attributes: cells(a) }));
  const ext = new Map<number, ExtractionRow>();
  if (c.path !== "calc") ext.set(1, { excelRow: 1, description: c.description ?? "", attributes: {}, items: modelItems } as unknown as ExtractionRow);
  const overrides: Record<string, string> = {};
  if (c.edits) overrides[ITEM_LIST_OVERRIDE_KEY] = JSON.stringify({ items: c.edits });
  if (c.rowUnit !== undefined) overrides[ROW_UNIT_OVERRIDE_KEY] = c.rowUnit;
  const h = makePricingSheetHelper({ configsByCategory: CONFIGS, items: ITEMS, extractionByRow: ext });
  const ctx: RateHelperRowContext & { unit?: string } = {
    excelRow: 1, description: c.path === "calc" ? "" : (c.description ?? ""), nodeType: "Line Item", category: c.cat, discipline: "HVAC",
    rateKinds: ["supply_rate", "install_rate", "combined_rate"], headings: c.path === "calc" ? [] : (c.headings ?? []), ownNotes: c.path === "calc" ? [] : (c.ownNotes ?? []),
  };
  if (c.path !== "calc" && c.unit !== undefined) ctx.unit = c.unit;
  const r = h.compute(ctx, overrides);
  if (!isSuggestion(r)) throw new Error(`${c.id}: expected a suggestion`);
  const s = r as ItemListSuggestion;
  const v = s.itemList!;
  const lines: string[] = [];
  if (v.reason) lines.push(v.reason);
  if (v.unitNote) lines.push(v.unitNote);
  lines.push(...(s.workings.derivation ?? []));
  for (const b of v.items) {
    if (b.family) lines.push(`family:${b.family}`);
    if (b.reason) lines.push(b.reason);
    if (b.skuLine) lines.push(b.skuLine);
    if (b.familyDefaulted) lines.push(b.familyDefaulted.rule);
    lines.push(...b.working);
    for (const f of b.fields) {
      if (f.note) lines.push(`${f.id}:${f.note}`);
      if (f.rule) lines.push(`${f.id}:${f.rule}`);
      if (f.otherMode) lines.push(`${f.id}:otherMode=true typed=${f.typedValue}`);
    }
  }
  // the pure pricer over the SAME assembled inputs
  const spec = itemListPricingSpec(CFG[c.cat])!;
  const edits = decodeItemEdits(overrides[ITEM_LIST_OVERRIDE_KEY], modelItems.length);
  const assembled = assembleItems(edits, modelItems, familyAttr(spec));
  const unitForPure = c.path === "calc" ? v.unit : (c.unit ?? v.unit);
  const rowText = c.path === "calc" ? "" : [c.description ?? "", ...(c.headings ?? [])].join(" | ");
  const ownText = c.path === "calc" ? "" : [c.description ?? "", ...(c.ownNotes ?? [])].join(" | ");
  const pure = priceItemList(spec, ITEMS, unitForPure, assembled, rowText, ownText);
  const working = v.items.flatMap((b) => b.working);
  return { s, v, lines, text: lines.join("\n"), working, pure };
}
const matches = (text: string, p: string | RegExp) => (typeof p === "string" ? text.includes(p) : p.test(text));

// ── T1 ──────────────────────────────────────────────────────────────────────────────────────────────
describe("T1 -- every Derivation-tab rule of Insulation and ADP fires from the panel's entry point (live v33)", () => {
  const titles = (cat: string) => itemListRuleOrder(CFG[cat], ITEMS).map((l) => l.title);

  it("THE GUARD: the rules this file names EQUAL the rules the config generates (Insulation 24, ADP 18); a new rule without a case, or a case naming a dead rule, fails here", () => {
    for (const cat of [INS, ADP]) {
      const generated = new Set(titles(cat));
      const named = new Set([...CASES.filter((c) => c.cat === cat).map((c) => c.rule), ...PICKER_CASES.filter(() => cat === ADP).map((p) => p.rule), ...Object.keys(NOT_PANEL_RULES).filter((t) => generated.has(t))]);
      const uncovered = [...generated].filter((t) => !named.has(t));
      const dead = [...named].filter((t) => !generated.has(t));
      expect({ cat, uncovered, dead }).toEqual({ cat, uncovered: [], dead: [] });
    }
    expect(titles(INS)).toHaveLength(24);
    expect(titles(ADP)).toHaveLength(18);
    // every NOT-panel rule is a REAL tab line (never a stale excuse)
    for (const t of Object.keys(NOT_PANEL_RULES)) expect(titles(INS).includes(t) || titles(ADP).includes(t)).toBe(true);
  });

  it("every panel-path rule has a POSITIVE model-read case and a NEGATIVE (near-miss) case", () => {
    for (const cat of [INS, ADP]) {
      for (const t of titles(cat)) {
        if (t in NOT_PANEL_RULES || t === T.notOffered) continue;
        const mine = CASES.filter((c) => c.cat === cat && c.rule === t);
        expect({ cat, rule: t, positive: mine.some((c) => c.kind === "pos" && c.path !== "calc") }).toEqual({ cat, rule: t, positive: true });
        expect({ cat, rule: t, negative: mine.some((c) => c.kind === "neg") }).toEqual({ cat, rule: t, negative: true });
      }
    }
  });

  it.each(CASES.map((c) => [c.id, c] as const))("%s", (_, c) => {
    const { s, v, text, pure } = run(c);
    for (const p of c.re) expect({ id: c.id, has: p, text }).toMatchObject({ has: p, text: expect.stringMatching(typeof p === "string" ? new RegExp(p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) : p) });
    for (const p of c.not ?? []) expect({ id: c.id, forbidden: p, hit: matches(text, p) }).toEqual({ id: c.id, forbidden: p, hit: false });
    if (c.priced !== undefined) expect({ id: c.id, priced: v.rowPriced }).toEqual({ id: c.id, priced: c.priced });
    if (c.pure !== false) {
      if (v.rowPriced) {
        expect({ id: c.id, panel: [s.values.supply_rate, s.values.install_rate], pure: [pure.supply, pure.install] })
          .toEqual({ id: c.id, panel: [pure.supply, pure.install], pure: [pure.supply, pure.install] });
      } else {
        expect({ id: c.id, pureRefuses: !pure.priced }).toEqual({ id: c.id, pureRefuses: true });
      }
    }
  });

  it("every EXCLUDED case cites its ruling", () => {
    for (const c of CASES.filter((c) => c.kind === "excluded")) expect({ id: c.id, excludedBy: c.excludedBy ?? "" }).not.toEqual({ id: c.id, excludedBy: "" });
    expect(CASES.filter((c) => c.kind === "excluded").map((c) => c.id).sort()).toEqual(["A8a-calc", "I13a-calc", "I14a-calc", "I8x-calc", "I8x-ptyped", "I9x-calc"]);
  });

  it.each(PICKER_CASES)("ADP line 5: the calculator's unit picker for $family offers $offered and not $notOffered", ({ family, offered, notOffered }) => {
    const h = makePricingSheetHelper({ configsByCategory: CONFIGS, items: ITEMS, extractionByRow: new Map() });
    const r = h.compute({ excelRow: 1, description: "", nodeType: "Line Item", category: ADP, discipline: "HVAC", rateKinds: ["supply_rate", "install_rate", "combined_rate"] },
      { [ITEM_LIST_OVERRIDE_KEY]: JSON.stringify({ items: [{ base: null, family, attrs: {}, other: [] }] }) });
    const choices = (r as ItemListSuggestion).itemList!.unitChoices;
    for (const u of offered) expect(choices).toContain(u);
    for (const u of notOffered) expect(choices).not.toContain(u);
  });

  it("a fake rule in an in-memory config copy is reported as UNCOVERED (the guard is not vacuous)", () => {
    const fake = { ...CFG[INS], list_spec: { ...(CFG[INS] as any).list_spec, pricing: { ...(CFG[INS] as any).list_spec.pricing,
      value_map: [...(CFG[INS] as any).list_spec.pricing.value_map, { attr: "cladding", families: [NR], from: "Canvas", refuse: "a fake rule for the vacuity proof" }] } } } as RateCategoryConfig;
    const generated = itemListRuleOrder(fake, ITEMS).map((l) => l.title);
    const named = new Set([...CASES.filter((c) => c.cat === INS).map((c) => c.rule), ...Object.keys(NOT_PANEL_RULES)]);
    const uncovered = generated.filter((t) => !named.has(t));
    expect(uncovered).toEqual(["Canvas as the cladding on Nitrile Rubber Insulation refuses"]);
  });
});

// ── T3: the rewriter x rule matrix (12d-7 S4), with F-1 / F-2 / F-3 as regression pins ───────────────
describe("T3 -- rewriter x rule: no step between a stored value / a typed entry and the pricer discards what a rule needs or shows", () => {
  const MATRIX: Case[] = [
    { id: "R4xLayers", rule: "matchStatedToOption x compose (12d-6 guard)", cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { thickness_mm: "Double layer of 19mm thick" })], re: ["priced as two layers"], priced: true },
    { id: "R4xSeveral (F-2)", rule: "matchStatedToOption x several=highest", cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { thickness_mm: "13 / 19 / 25" })], re: ["the highest, 25, is taken"], not: ["own spelling"], working: ["states several values -- the highest, 25, is taken"], priced: true },
    { id: "R4xCm (F-2)", rule: "matchStatedToOption x the cm reader", cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(PUFI, { pipe_size_mm: "20 cm" })], re: ["20 cm read as 200 mm"], not: ["own spelling"], working: ["20 cm read as 200 mm"], priced: true },
    { id: "R4xRange (F-2)", rule: "matchStatedToOption x the range reader", cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(PUFI, { thickness_mm: "25 to 50" })], re: ["-> its top value 50"], working: ["its top value 50"], priced: true },
    { id: "R4xInch", rule: "matchStatedToOption x inches (not an option: left alone)", cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { pipe_size_mm: '5/8"' })], re: ["15.88"], priced: true },
    { id: "R4xSizeMatch", rule: "matchStatedToOption x size_match", cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(NIT, { pipe_size_mm: "22.2" })], re: ["pipe size 22.2 is 22.23 on the sheet"], priced: true },
    { id: "R4xText", rule: "matchStatedToOption x a choice spelled differently (the intended rewrite)", cat: ADP, path: "panel", kind: "pos", unit: "sqm", model: [{ family: "VCD", variant: "gi rectangular" }], re: ["BoQ says gi rectangular -> GI rectangular (the sheet's own spelling of this value)"], priced: true, pure: false },
    { id: "R5xDefault (F-1)", rule: "unstockedPicks x number_defaults", cat: INS, path: "calc", kind: "pos", edits: calc(PUF, { cladding: "No", pipe_size_mm: "100", thickness_mm: "25" }), rowUnit: "mts", re: ["25 mm is not stocked with the other answers on this item -- choose again", "choose again: thickness"], not: ["not mentioned -> 9"], priced: false, pure: false },
    { id: "R5xCompose (F-1)", rule: "unstockedPicks x composition (a cleared pick must not price EITHER way)", cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "26G Aluminium", pipe_size_mm: "6.35", thickness_mm: "25" }, ["pipe_size_mm"]), rowUnit: "mts", re: ["choose again: thickness"], not: ["not mentioned -> 9"], priced: false, pure: false },
    { id: "R5xAbsentAsNone (F-1)", rule: "unstockedPicks x absent_as_none + override_when", cat: ADP, path: "calc", kind: "pos", edits: calc("fire damper", { variant: "motorised", ul: "yes", size_mm: "600x600" }), rowUnit: "nos", re: ["choose again: whether it is UL listed"], not: ["ul not mentioned -> no"], priced: false, pure: false },
    { id: "R5xOther", rule: "unstockedPicks x a value typed through Other... (never cleared)", cat: INS, path: "calc", kind: "pos", edits: calc(PUF, { cladding: "No", pipe_size_mm: "100", thickness_mm: "25" }, ["thickness_mm"]), rowUnit: "mts", re: ["thickness 25 is not on the sheet -> 65 (next size up"], priced: true },
    { id: "R5xModel", rule: "unstockedPicks x a model value (never cleared)", cat: INS, path: "panel", kind: "pos", unit: "RMT", model: [m(PUFI, { thickness_mm: "25" })], re: ["thickness 25 is not on the sheet -> 65 (next size up"], priced: true },
    { id: "R5xModelOpenedBox (F-3)", rule: "unstockedPicks x a size typed into a MODEL-opened Other... box", cat: INS, path: "ptyped", kind: "pos", unit: "RMT", model: [m(NIT, { pipe_size_mm: "250 NB" })], edits: ptyped({ pipe_size_mm: "50" }), re: ["pipe size 50 is not on the sheet -> 53.98", "pipe_size_mm:otherMode=true typed=50"], not: ["not stocked with the other answers"], priced: true },
    { id: "R5xFoil (R4b)", rule: "unstockedPicks x value_map (an offered mapped value is a stocked pick)", cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "Aluminium Foil", thickness_mm: "19", pipe_size_mm: "50" }, ["pipe_size_mm"]), rowUnit: "mts", re: ["foil on a pipe is priced as 26G cladding"], not: ["not stocked"], priced: true },
    { id: "R2xU4decimal", rule: "assembleItems typed marker x U4 (a decimal typed thickness is accepted)", cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "26G Aluminium", thickness_mm: "12.5", pipe_size_mm: "50" }, ["thickness_mm", "pipe_size_mm"]), rowUnit: "mts", re: ["thickness 12.5 is not on the sheet -> 13 (next size up"], priced: true },
    { id: "R2xU4pipe", rule: "assembleItems typed marker x U4 (the pipe-size box is untouched)", cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: "50 NB" }, ["pipe_size_mm"]), rowUnit: "mts", re: ["53.98"], priced: true },
    { id: "R2xAdded", rule: "assembleItems x needs (an added item starts from its family alone)", cat: INS, path: "ptyped", kind: "pos", unit: "RMT", model: [NIT], edits: [{ base: 0, family: null, attrs: {}, other: [] }, { base: null, family: PUF, attrs: {}, other: [] }], re: ["could not tell cladding"], priced: false },
    { id: "R1xBadBase", rule: "decodeItemEdits x family_when_none (an out-of-range base is dropped, never priced silently)", cat: INS, path: "ptyped", kind: "pos", unit: "RMT", model: [NIT], edits: [{ base: 5, family: null, attrs: {}, other: [] }], re: ["could not tell cladding"], priced: false },
    { id: "R3xUnitStale", rule: "the row-unit override x unit rules (a pick no longer offered falls to the first offered class)", cat: INS, path: "calc", kind: "pos", edits: calc(NR, { cladding: "26G Aluminium", thickness_mm: "19", pipe_size_mm: "50" }, ["pipe_size_mm"]), rowUnit: "sqm", re: [], priced: true },
    { id: "R6xHeadings", rule: "row text x family_when_none (headings reach it) and x named_in_row (headings never do)", cat: INS, path: "panel", kind: "pos", unit: "sqm", model: [m(THMI, { item: "None", cladding: "None" })], headings: ["Acoustic lining with aluminium cladding"], re: ["item not mentioned -> Acoustic Nitrile Insulation (", "cladding not mentioned -> No ("], not: ["cladding named in this row"], priced: true },
    { id: "R8xUnshowable", rule: "fieldCannotShowValue x the pricer (the pricer refuses an unshowable value first)", cat: ADP, path: "panel", kind: "pos", unit: "nos", model: [{ family: "round diffuser", damper: "yes", dia_mm: "200" }], re: ["no SKU for this combination (round diffuser: damper yes)"], priced: false },
  ];
  it("the matrix names every rewriter x rule pair it covers", () => {
    expect(MATRIX.map((c) => c.id)).toEqual([
      "R4xLayers", "R4xSeveral (F-2)", "R4xCm (F-2)", "R4xRange (F-2)", "R4xInch", "R4xSizeMatch", "R4xText",
      "R5xDefault (F-1)", "R5xCompose (F-1)", "R5xAbsentAsNone (F-1)", "R5xOther", "R5xModel", "R5xModelOpenedBox (F-3)", "R5xFoil (R4b)",
      "R2xU4decimal", "R2xU4pipe", "R2xAdded", "R1xBadBase", "R3xUnitStale", "R6xHeadings", "R8xUnshowable",
    ]);
  });
  it.each(MATRIX.map((c) => [c.id, c] as const))("%s", (_, c) => {
    const { s, v, text, working, pure } = run(c);
    for (const p of c.re) expect({ id: c.id, has: p, hit: matches(text, p) }).toEqual({ id: c.id, has: p, hit: true });
    for (const p of c.working ?? []) expect({ id: c.id, inWorking: p, hit: working.some((w) => matches(w, p)) }).toEqual({ id: c.id, inWorking: p, hit: true });
    for (const p of c.not ?? []) expect({ id: c.id, forbidden: p, hit: matches(text, p) }).toEqual({ id: c.id, forbidden: p, hit: false });
    if (c.priced !== undefined) expect({ id: c.id, priced: v.rowPriced }).toEqual({ id: c.id, priced: c.priced });
    if (c.pure !== false && v.rowPriced) expect([s.values.supply_rate, s.values.install_rate]).toEqual([pure.supply, pure.install]);
  });
});
