// ELR-1 AC6 (owner R-DERIV 2026-09-27: the rules "in plain English ... in run order", "reason not recorded" where none
// exists; R-ELR0 "1 ok", 2026-10-27; ADP-4b D1 / D8): wiring & cabling's Derivation rules list, written from its config.
import { describe, expect, it } from "vitest";
import path from "path";
import { pathToFileURL } from "url";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";
import { attributeRuleOrder, itemListRuleOrder, type RuleOrderItem } from "./itemListRuleOrder";

type RuleItems = RuleOrderItem[];

const DATA = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
// READ, never imported (tsc and a whole asset); the asset this slice minted, named -- the lines quote its numbers
type AssetFile = { items: RuleItems; category_configs: Cfg[] };
const elec = readJsonFixture<AssetFile>(pathToFileURL(path.join(DATA, "rate_master_electrical_all_v67.json")));
const hvac = readJsonFixture<AssetFile>(pathToFileURL(path.join(DATA, "rate_master_hvac_all_v54.json")));
type Cfg = { category_id: string; pipelines?: Record<string, { steps: Array<Record<string, unknown>> }> };
const cfgOf = (a: { category_configs: Cfg[] }, id: string): Cfg => structuredClone(a.category_configs.find((c) => c.category_id === id)!);
const wiring = () => cfgOf(elec, "wiring_cabling");
const lines = (cfg: unknown) => attributeRuleOrder(cfg, elec.items);
const text = (cfg: unknown) => lines(cfg).map((l) => `${l.title} -- ${l.detail ?? ""}`).join("\n");

describe("ELR-1 AC6: wiring & cabling's rules list", () => {
  it("POSITIVE: thirteen lines, in run order, each a rule of the config", () => {
    expect(lines(wiring()).map((l) => l.title)).toEqual([
      "Every row shows both blocks, Cable and Termination",
      "The cable and the termination are each matched in the catalogue",
      "Conduit included: the BoQ's answer",
      "Conduit type: the BoQ's answer, never assumed",
      "Conduit size (mm): the size the BoQ states",
      "Cable supply per metre = list price x (1 - discount) x (1 + supply markup), rounded up to the next 10",
      "Parallel runs multiply the rounded supply",
      "Cable install per metre = install base x (1 + 'Cable installation markup'), rounded up to the rupee",
      "The conduit is priced as its own category prices it: list price x (1 - discount) x (1 + supply markup), from 'Conduit discount & supply markup', not rounded",
      "The conduit install = its supply x 'Conduit installation share', rounded up to the next 10",
      "Supply = the cable supply + the conduit supply, rounded up to the rupee",
      "Termination supply per set = the lug + the gland, each list price x (1 - discount) x (1 + supply markup), rounded up to the next 10, x runs",
      "Termination install = its supply (already x runs) x 'Termination installation share', rounded up to the next 10",
    ]);
  });

  it("every line ends with its reason: a ruling quoted with its date, or 'reason not recorded'", () => {
    const ls = lines(wiring());
    for (const l of ls) expect(l.detail, l.title).toMatch(/(^|-- )why: (.*\(owner[^)]*\d{4}-\d{2}-\d{2}\)|.*reason not recorded)/);
    expect(ls.filter((l) => l.reason === "reason not recorded").map((l) => l.n)).toEqual([6]);
    expect(ls[11].reason).toContain("the gland sizes and the rounding -- reason not recorded");
    expect(ls[2].reason).toContain("default to not include it");
  });

  it("the numbers are the config's own: 25 mm, one install unit per 3 runs, the 35 sqmm gland split, the Pricing Inputs by name", () => {
    const t = text(wiring());
    expect(t).toContain("where a conduit type is named and no size, 25 mm");
    expect(t).toContain("one install unit per 3 runs (1 to 3 runs = 1, 4 to 6 = 2, and so on)");
    expect(t).toContain("below 35 the smaller one, from 35 the larger one");
    expect(t).toContain("'Armoured cable discount, supply markup & wastage' when Insulation is ARMOURED");
  });

  it("NEGATIVE: no internal name, raw rule id or snake_case token reaches the tab", () => {
    const all = lines(wiring()).map((l) => `${l.title} ${l.detail}`).join("\n");
    expect(all).not.toMatch(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/);   // pi_cable_arm_discount, runs_step_divisor, size_mm
    expect(all).not.toMatch(/\bR1[01]\b/);                           // the extraction rules' ids
    expect(all).not.toMatch(/\bpi\b|ctx|from_attr|match_master_row/);
  });

  it("STRUCTURAL VACUITY: delete a step and its line goes; change a number and the line follows", () => {
    const cfg = wiring();
    const term = cfg.pipelines!.termination_boq.steps;
    cfg.pipelines!.termination_boq.steps = term.filter((s) => s.step !== "install_as_ratio");
    expect(lines(cfg).map((l) => l.title).join("\n")).not.toContain("Termination install");
    const cable = cfg.pipelines!.cable_boq.steps;
    const size = cable.find((s) => (s.params as { result_attr?: string })?.result_attr === "size_mm")!;
    (size.params as { table: Record<string, number> }).table = { MS: 32, PVC: 32 };
    expect(text(cfg)).toContain("no size, 32 mm");
    cfg.pipelines!.cable_boq.steps = cable.filter((s) => (s.params as { result_attr?: string })?.result_attr !== "size_mm");
    expect(text(cfg)).not.toContain("Conduit size (mm)");
    const stepped = cable.find((s) => (s.params as { runs_step_divisor?: number })?.runs_step_divisor);
    delete (stepped!.params as { runs_step_divisor?: number }).runs_step_divisor;
    expect(text(cfg)).not.toContain("install unit per");
  });

  it("UNCHANGED: the other eight Electrical categories, the HVAC aliases and every HVAC category get no attribute list", () => {
    const others = elec.category_configs.map((c: Cfg) => c.category_id).filter((id: string) => id !== "wiring_cabling");
    expect(others.sort()).toEqual(["cabletray_raceway", "conduit_piping", "db_switchgear", "earthing", "electrical_pricing_inputs",
      "industrial_sockets", "junction_box_raceway", "lighting_mgmt_system", "miscellaneous", "point_wiring", "popup_boxes",
      "switches_sockets"]);
    // ELR-4a (owner R-APPROVE, 2026-10-29) INVERTED: WAS every one of these eleven -> []; NOW point wiring, switches &
    // sockets and pop-up boxes list their own rules (pinned line by line in attributeRuleOrder.elr4a.test.ts) and the
    // other eight still get none
    const elr4a = ["point_wiring", "popup_boxes", "switches_sockets"];
    for (const id of others) {
      if (elr4a.includes(id)) expect(lines(cfgOf(elec, id)).length, id).toBeGreaterThan(0);
      else expect(lines(cfgOf(elec, id)), id).toEqual([]);
    }
    for (const c of hvac.category_configs as Cfg[]) expect(attributeRuleOrder(c, hvac.items), c.category_id).toEqual([]);
    // and the item-list builder still returns [] for wiring: one list per category, never two
    expect(itemListRuleOrder(wiring(), elec.items)).toEqual([]);
  });
});
