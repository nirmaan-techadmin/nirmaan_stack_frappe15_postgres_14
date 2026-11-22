/**
 * BCS-2 -- Electrical v73's cost rules through the product's interpreter: the worked examples, the refusals (never 0), and
 * NOTHING HARDCODED (owner 2026-11-22: "the discount % should change if the user changes it ... dont hardcode it").
 */
import { describe, expect, it } from "vitest";
import { allAgree, cfgOf, clone, inputValue, PAIRS, readAsset, served, verdicts, withInput, type Cfg, type Golden } from "./electricalBcs.harness";
import { noneRefusalOf, runPipeline } from "./rate-master/ratePipelineInterpreter";
import { isSummaryInput, panelShapeOf } from "./rate-master/pricingInputImpact";
import { pricingInputUsedBy, pricingInputUsedByText } from "./rate-master/rateMasterSpec";

const V73 = readAsset(73);
const V72 = readAsset(72);
const ITEMS = served(V73);
const golden = (cat: string, id: string): Golden => (cfgOf(V73, cat).goldens ?? []).find((g) => g.id === id)!;
const run = (cat: string, pid: string, sel: Golden["attrs"], items = ITEMS, cfg: Cfg = cfgOf(V73, cat)) => runPipeline(pid, cfg.pipelines[pid], items, sel);

describe("(+) the worked examples", () => {
  for (const c of V73.category_configs) for (const g of c.goldens ?? []) for (const [pid, exp] of Object.entries(g.expect)) {
    it(`${c.category_id} / ${g.id} / ${pid}`, () => {
      const r = run(c.category_id, pid, g.attrs);
      expect(r.status).toBe("ok");
      for (const [k, v] of Object.entries(exp)) expect(r.finals[k], k).toBeCloseTo(v, 6);
    });
  }
  it("a cable's conduit is added to its cost once, with no wastage on it: g6 - g7 = conduit list x (1 - its discount)", () => {
    const diff = run("wiring_cabling", "cable_bcs", golden("wiring_cabling", "g6").attrs).finals.bcs_supply_per_mtr
      - run("wiring_cabling", "cable_bcs", golden("wiring_cabling", "g7").attrs).finals.bcs_supply_per_mtr;
    const list = ITEMS.find((i) => i.kind === "conduit" && i.attributes.conduit_type === "PVC" && i.attributes.size_mm === 25)!.rates.list_price_per_mtr;
    expect(diff).toBeCloseTo(list * (1 - inputValue(ITEMS, "conduit", "discount")), 9);
  });
  it("(-) no conduit: the cable's cost is exactly v72's", () => {
    const sel = golden("wiring_cabling", "g7").attrs;
    expect(run("wiring_cabling", "cable_bcs", sel).finals).toEqual(runPipeline("cable_bcs", cfgOf(V72, "wiring_cabling").pipelines.cable_bcs, served(V72), sel).finals);
  });
  it("(-) a box with no modules costs exactly what v72 said: the box only", () => {
    const sel = golden("popup_boxes", "p3").attrs;
    expect(run("popup_boxes", "popup_bcs", sel).finals).toEqual(runPipeline("popup_bcs", cfgOf(V72, "popup_boxes").pipelines.popup_bcs, served(V72), sel).finals);
  });
  it("(-) a socket with no breaker has no breaker in its cost", () => {
    expect(run("industrial_sockets", "indsock_bcs", golden("industrial_sockets", "i6").attrs).finals.bcs_supply).toBeCloseTo(8771, 6);
    const r = run("industrial_sockets", "indsock_bcs", golden("industrial_sockets", "i7").attrs);
    expect(r.steps.filter((s) => s.produced?.key === "paired_mcb").map((s) => s.produced!.value)).toEqual([expect.closeTo(1203.6, 6)]);
  });
});

describe("(owner 3a) the corrected point-wiring examples: rows with no circuit wiring are charged nothing for it", () => {
  for (const id of ["pw1", "pw2", "pw3", "pw4"]) for (const pid of ["pw_boq_supply", "pw_boq_install", "pw_bcs"])
    it(`(+) ${id} / ${pid}: both circuit wires contribute 0`, () => {
      const r = run("point_wiring", pid, golden("point_wiring", id).attrs);
      expect(r.status).toBe("ok");
      for (const n of ["circuit_wire1", "circuit_wire2"]) expect(r.steps.filter((s) => s.produced?.key === n).map((s) => s.produced!.value)).toEqual([0]);
    });
  it("(-) pw5, which HAS circuit wiring, is charged for it", () => {
    const r = run("point_wiring", "pw_boq_supply", golden("point_wiring", "pw5").attrs);
    expect(r.steps.find((s) => s.produced?.key === "circuit_wire1")!.produced!.value).toBeGreaterThan(0);
  });
});

describe("(-) where the price refuses the cost refuses, in the same words, and is never 0", () => {
  const NONE_DB = Object.fromEntries([1, 2, 3, 4, 5].flatMap((n) => [[`mcb${n}_item`, "None"], [`mcb${n}_qty`, 0]]));
  const DB = { ...NONE_DB, db_shell_item: "None", db_shell_qty: 0, enclosure_item: "None", enclosure_qty: 0 };
  const SS = { ...golden("switches_sockets", "s1").attrs, socket1_item: "None", socket1_qty: 0 };
  const PW = { ...golden("point_wiring", "pw1").attrs, wire1_core: "None", wire1_thickness_sqmm: "None", wire2_core: "None", wire2_thickness_sqmm: "None",
    conduit_type: "None", switch_item: "None", switch_qty: 0, socket_item: "None", socket_qty: 0, plate_item: "None", plate_qty: 0, back_box: "No" };
  for (const [cat, price, cost, sel] of [
    ["db_switchgear", "db_buildup_supply", "db_buildup_bcs", DB], ["switches_sockets", "swsock_boq", "swsock_bcs", SS],
  ] as Array<[string, string, string, Golden["attrs"]]>) {
    it(`${cat}: every part None`, () => {
      const p = run(cat, price, sel);
      const c = run(cat, cost, sel);
      expect(noneRefusalOf(p)).toMatch(/price it by hand/);
      expect(noneRefusalOf(c)).toBe(noneRefusalOf(p));
      expect(c.finals).toEqual({});
    });
    it(`${cat}: v72 gave 0 there -- the change this pins`, () => {
      expect(Math.abs(runPipeline(cost, cfgOf(V72, cat).pipelines[cost], served(V72), sel).finals.bcs_supply)).toBe(0);
    });
  }
  it("point_wiring: every part None -- both sides stop at the same step with the same words (v72 already did)", () => {
    const p = run("point_wiring", "pw_boq_supply", PW);
    const c = run("point_wiring", "pw_bcs", PW);
    expect(p.status).toBe("no_match");
    expect(c.status).toBe("no_match");
    expect([c.steps.at(-1)!.step, c.steps.at(-1)!.label]).toEqual([p.steps.at(-1)!.step, p.steps.at(-1)!.label]);
    expect(c.finals).toEqual({});
  });
  it("junction box: a size outside the catalogue has no price and no cost", () => {
    expect(run("junction_box_raceway", "jb_boq", { face_mm: 9999 }).finals).toEqual({});
    expect(run("junction_box_raceway", "jb_bcs", { face_mm: 9999 }).finals).toEqual({});
  });
  it("industrial socket: a breaker the catalogue cannot supply refuses on both sides", () => {
    const sel = { ...golden("industrial_sockets", "i4").attrs, mcb_amp_a: 999 };
    expect(run("industrial_sockets", "indsock_boq", sel).status).toBe("no_match");
    expect(run("industrial_sockets", "indsock_bcs", sel).finals).toEqual({});
  });
  it("miscellaneous: an item with no stored supply has no supply price and no cost", () => {
    const it0 = ITEMS.find((i) => i.kind === "misc_item" && typeof i.rates.boq_supply !== "number")!;
    const sel = { description: it0.attributes.description };
    expect(run("miscellaneous", "misc_boq", sel).finals.supply).toBeUndefined();
    expect(run("miscellaneous", "misc_bcs", sel).finals.bcs_supply).toBeUndefined();
  });
});

describe("NOTHING HARDCODED -- one input changed on a fixture copy moves the cost AND the check line", () => {
  const moves: Array<[string, string, string, number, string, Golden["attrs"]]> = [
    ["industrial-socket discount", "indsock", "discount", 0.5, "indsock_bcs", golden("industrial_sockets", "i6").attrs],
    ["switchgear discount (the paired breaker)", "switchgear", "discount", 0.5, "indsock_bcs", golden("industrial_sockets", "i7").attrs],
    ["junction-box discount", "jb_discount", "discount", 0.2, "jb_bcs", { face_mm: 300 }],
    ["conduit discount (the cable's conduit)", "conduit", "discount", 0.25, "cable_bcs", golden("wiring_cabling", "g6").attrs],
    ["cable wastage", "cable_unarm", "wastage", 0.2, "cable_bcs", golden("wiring_cabling", "g6").attrs],
    ["switch & socket discount (the box's modules)", "swsock", "discount", 0.5, "popup_bcs", golden("popup_boxes", "p2").attrs],
    ["pop-up box ratio", "popup_supply", "ratio", 0.5, "popup_bcs", golden("popup_boxes", "p2").attrs],
  ];
  for (const [label, id, field, value, cost, sel] of moves) {
    it(`(+) ${label}: the cost moves and still agrees`, () => {
      const pair = PAIRS.find((p) => p.cost === cost)!;
      const moved = withInput(ITEMS, id, field, value);
      expect(run(pair.cat, cost, sel, moved).finals[pair.costOut]).not.toBeCloseTo(run(pair.cat, cost, sel).finals[pair.costOut], 2);
      expect(allAgree(verdicts(cfgOf(V73, pair.cat), pair, moved, sel))).toBe(true);
    });
  }
  it("(+) a supply margin: the COST stays, the check line's margin and price move with it, and they still agree", () => {
    const pair = PAIRS.find((p) => p.cost === "jb_bcs")!;
    const moved = withInput(ITEMS, "jb_supply", "supply_markup", 0.9);
    const before = verdicts(cfgOf(V73, pair.cat), pair, ITEMS, { face_mm: 300 })![0];
    const after = verdicts(cfgOf(V73, pair.cat), pair, moved, { face_mm: 300 })![0];
    expect([before.margin, after.margin]).toEqual([inputValue(ITEMS, "jb_supply", "supply_markup"), 0.9]);
    expect(after.cost).toBe(before.cost);
    expect(after.price).not.toBe(before.price);
    expect(allAgree([after])).toBe(true);
  });
  it("(-) a pipeline with a TYPED number in place of the reference fails it: the cost does not move, and stops agreeing", () => {
    const pair = PAIRS.find((p) => p.cost === "indsock_bcs")!;
    const sel = golden("industrial_sockets", "i6").attrs;
    const typed = clone(cfgOf(V73, pair.cat));
    for (const s of typed.pipelines.indsock_bcs.steps as unknown as Array<{ step: string; target?: string; formula?: string }>)
      if (s.step === "scale" && s.target === "pi_indsock_discount") s.formula = `1-${inputValue(ITEMS, "indsock", "discount")}`;
    const moved = withInput(ITEMS, "indsock", "discount", 0.5);
    expect(run(pair.cat, "indsock_bcs", sel, ITEMS, typed).finals).toEqual(run(pair.cat, "indsock_bcs", sel).finals);   // right today ...
    expect(run(pair.cat, "indsock_bcs", sel, moved, typed).finals).toEqual(run(pair.cat, "indsock_bcs", sel, ITEMS, typed).finals); // ... and frozen
    expect(allAgree(verdicts(typed, pair, moved, sel))).toBe(false);
  });
  it("(-) no cost pipeline of v73 carries a typed discount, margin, wastage or amount", () => {
    const bad: string[] = [];
    for (const c of V73.category_configs) for (const [pid, p] of Object.entries(c.pipelines)) {
      if (!/bcs/i.test(pid)) continue;
      for (const s of p.steps as unknown as Array<Record<string, unknown>>) {
        // a formula may carry only the structural 1; a parameter may carry only a 0 / 1 switch, round-up digits or a lookup table
        for (const n of String(s.formula ?? "").match(/(?<![A-Za-z_0-9.])\d+(\.\d+)?/g) ?? []) if (n !== "1") bad.push(`${pid}: formula ${String(s.formula)}`);
        for (const st of (s.rate_stages ?? []) as Array<{ mult?: number }>) if (st.mult !== undefined && st.mult !== 1) bad.push(`${pid}: rate stage x${st.mult}`);
        const params = [s.params, ...((s.conditions ?? []) as Array<{ params?: unknown }>).map((x) => x.params)].filter(Boolean) as Array<Record<string, unknown>>;
        if (!["roundup", "map_attribute", "module_fit", "catalog_fit", "circuit_fit", "derive_attribute"].includes(String(s.step)))
          for (const q of params) for (const [k, v] of Object.entries(q)) if (typeof v === "number" && v !== 0 && v !== 1) bad.push(`${pid}: ${k}=${v}`);
      }
    }
    expect(bad).toEqual([]);
  });
  it("(-) no explain line of an edited cost pipeline carries a percentage", () => {
    for (const [cat, pid] of [["wiring_cabling", "cable_bcs"], ["popup_boxes", "popup_bcs"], ["junction_box_raceway", "jb_bcs"], ["industrial_sockets", "indsock_bcs"]])
      expect(JSON.stringify(cfgOf(V73, cat).pipelines[pid]), pid).not.toMatch(/\d+ ?%/);
  });
});

describe("the Rs 42 input", () => {
  const ID = "elec_bcs_install_per_sqft";
  const row = ITEMS.find((i) => i.attributes.item === ID)!;
  it("(+) its exact name, its value, and its mark for the BoQ summary", () => {
    expect([row.attributes.name, row.rates]).toEqual(["Electrical installation cost per sq ft (BCS)", { amount: 42 }]);
    expect(cfgOf(V73, "electrical_pricing_inputs").summary_inputs).toEqual([ID]);
  });
  it('(+) its used-by line reads exactly "BoQ summary"', () => {
    const u = pricingInputUsedBy(V73.category_configs as never);
    expect(pricingInputUsedByText(u[ID])).toBe("BoQ summary");
  });
  it("(-) without the mark it would read not used, and an input a rule reads keeps its categories", () => {
    const noMark = clone(V73.category_configs);
    delete noMark.find((c) => c.category_id === "electrical_pricing_inputs")!.summary_inputs;
    expect(pricingInputUsedByText(pricingInputUsedBy(noMark as never)[ID])).toBe("not used");
    expect(pricingInputUsedByText(pricingInputUsedBy(V73.category_configs as never).jb_discount)).toMatch(/^junction_box_raceway \(\d+ uses?\)$/);
  });
  it("(+) its impact panel is the summary-only shape; (-) every other input keeps its own", () => {
    const configs = Object.fromEntries(V73.category_configs.map((c) => [c.category_id, c]));
    expect(isSummaryInput(configs as never, ID)).toBe(true);
    expect(panelShapeOf(row.rates, null, isSummaryInput(configs as never, ID))).toBe("summary_only");
    const others = ITEMS.filter((i) => i.kind === "electrical_pricing_input" && i.attributes.item !== ID);
    expect(others.filter((i) => isSummaryInput(configs as never, String(i.attributes.item)))).toEqual([]);
    expect(isSummaryInput(configs as never, "")).toBe(false);
  });
});

describe("the margin each category is checked with", () => {
  it("(+) every category that prices names one, and the names resolve to a live number", () => {
    const pricing = V73.category_configs.filter((c) => Object.keys(c.pipelines).length > 0);
    expect(pricing).toHaveLength(12);
    for (const c of pricing) expect((c.bcs_default_margin?.entries ?? []).length, c.category_id).toBeGreaterThan(0);
  });
  it("(-) no margin entry carries a number", () => {
    expect(JSON.stringify(V73.category_configs.map((c) => c.bcs_default_margin ?? null))).not.toMatch(/:\s*\d/);
  });
});
