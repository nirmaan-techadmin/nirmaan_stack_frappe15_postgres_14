/**
 * BCS-2 -- every worked example's COST agrees with BoQ supply / (1 + supply margin), on the NEWEST Electrical asset.
 * What it protects: a later rate-file version that drops a cost part, or changes a price and not its cost, turns red here.
 */
import { describe, expect, it } from "vitest";
import { allAgree, cfgOf, clone, newestVersion, PAIRS, readAsset, served, verdicts } from "./electricalBcs.harness";

const ASSET = readAsset(newestVersion());
const ITEMS = served(ASSET);

describe("every worked example's cost agrees, part by part", () => {
  let judged = 0;
  for (const pair of PAIRS) {
    const cfg = cfgOf(ASSET, pair.cat);
    for (const g of cfg.goldens ?? []) {
      const v = verdicts(cfg, pair, ITEMS, g.attrs);
      if (v === null) continue;                        // the price refuses this example (a cable example has no termination, ...)
      judged += 1;
      it(`(+) ${pair.cat} / ${g.id} / ${pair.cost}`, () => {
        expect(v.map((x) => `${x.part}:${x.cls}`).filter((x) => /:[DE]$/.test(x))).toEqual([]);
        expect(allAgree(v)).toBe(true);
      });
    }
  }
  it("(+) all 13 price / cost pairs are judged by at least one example, 40 or more in all", () => {
    const seen = PAIRS.filter((p) => (cfgOf(ASSET, p.cat).goldens ?? []).some((g) => verdicts(cfgOf(ASSET, p.cat), p, ITEMS, g.attrs) !== null));
    expect(seen.map((p) => p.cost).sort()).toEqual(PAIRS.map((p) => p.cost).sort());
    expect(judged).toBeGreaterThanOrEqual(40);
  });
});

describe("a fixture with a part taken out is classed as disagreeing", () => {
  const wiring = PAIRS.find((p) => p.cost === "cable_bcs")!;
  const popup = PAIRS.find((p) => p.cost === "popup_bcs")!;
  const golden = (cat: string, id: string) => (cfgOf(ASSET, cat).goldens ?? []).find((g) => g.id === id)!;

  it("(-) the conduit part removed from cable_bcs: the conduit is E, the example does not agree", () => {
    const cfg = clone(cfgOf(ASSET, "wiring_cabling"));
    const p = cfg.pipelines.cable_bcs as unknown as { steps: Array<{ step: string; name?: string }> };
    p.steps = p.steps.filter((s) => !(s.step === "component_ref" && s.name === "conduit"));
    const v = verdicts(cfg, wiring, ITEMS, golden("wiring_cabling", "g6").attrs)!;
    expect(v.map((x) => [x.part, x.cls])).toEqual([["cable", "C"], ["conduit", "E"]]);
    expect(allAgree(v)).toBe(false);
  });
  it("(+) the same example, untouched, agrees: cable by its wastage, conduit exactly", () => {
    const v = verdicts(cfgOf(ASSET, "wiring_cabling"), wiring, ITEMS, golden("wiring_cabling", "g6").attrs)!;
    expect(v.map((x) => [x.part, x.cls])).toEqual([["cable", "C"], ["conduit", "A"]]);
  });
  it("(-) the modules removed from popup_bcs: the modules are E", () => {
    const cfg = clone(cfgOf(ASSET, "popup_boxes"));
    const p = cfg.pipelines.popup_bcs as unknown as { steps: Array<{ result?: string; params?: Record<string, unknown> }> };
    // BCS-2b (v74): the generated popup_bcs makes its modules as "module_supply"; v73's made them as "module_cost" - both taken out
    p.steps = p.steps.filter((s) => s.result !== "module_cost" && s.result !== "module_supply" && !s.params?.modules_from_ctx);
    const v = verdicts(cfg, popup, ITEMS, golden("popup_boxes", "p2").attrs)!;
    expect(v.map((x) => [x.part, x.cls])).toEqual([["box", "A"], ["modules", "E"]]);
  });
  it("(-) a cost one discount point off does not agree", () => {
    const cfg = clone(cfgOf(ASSET, "junction_box_raceway"));
    const p = cfg.pipelines.jb_bcs as unknown as { steps: Array<{ step: string; formula?: string }> };
    for (const s of p.steps) if (s.step === "scale") s.formula = "base*(1-discount)*0.9";
    const jb = PAIRS.find((x) => x.cost === "jb_bcs")!;
    expect(allAgree(verdicts(cfg, jb, ITEMS, { face_mm: 300 }))).toBe(false);
    expect(allAgree(verdicts(cfgOf(ASSET, "junction_box_raceway"), jb, ITEMS, { face_mm: 300 }))).toBe(true);
  });
  it("(-) a margin the config does not name is an error, never a silent pass", () => {
    const cfg = clone(cfgOf(ASSET, "junction_box_raceway"));
    delete cfg.bcs_default_margin;
    expect(() => verdicts(cfg, PAIRS.find((x) => x.cost === "jb_bcs")!, ITEMS, { face_mm: 300 })).toThrow(/no margin/);
  });
});
