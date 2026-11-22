/** BCS-2 -- the shared cost rules. What it protects: a cost agrees with BoQ supply / (1 + margin) exactly as BCS-R1 tested it,
 *  and a margin is read live from its Pricing Input, never typed. */
import { describe, expect, it } from "vitest";
import { agrees, bcsAgrees, defaultBcsSupply, resolveBcsMargin, type BcsDefaultMargin } from "./bcsCost";
import type { RateMasterItem } from "../../pricing/rate-master/rateMasterTypes";

const input = (item: string, rates: Record<string, number>): RateMasterItem =>
  ({ discipline: "Electrical", kind: "electrical_pricing_input", attributes: { item }, rates }) as RateMasterItem;

describe("defaultBcsSupply", () => {
  it("(+) junction box 300 mm: 920 / (1 + 45%) = 634.48, unrounded", () => {
    expect(defaultBcsSupply(920, 0.45)).toBeCloseTo(634.4828, 4);
  });
  it("(-) it does not round", () => {
    expect(Number.isInteger(defaultBcsSupply(920, 0.45))).toBe(false);
  });
});

describe("bcsAgrees -- BCS-R1's cases", () => {
  it("(+) A: equal within half a paisa", () => {
    expect(bcsAgrees(2652.3, 4376.295, 0.65, null)).toBe("A");
  });
  it("(+) B: the price's own round-up only (junction box 300 mm: 630 x 1.45 = 913.5 -> 920)", () => {
    expect(bcsAgrees(630, 920, 0.45, -1)).toBe("B");
  });
  it("(+) B: rounding on the COST side also counts (BOQ-26-00157 row 326: 6,873.30 -> 6,880, BoQ 11,350)", () => {
    expect(bcsAgrees(6880, 11350, 0.65, -1, 0, 6873.3)).toBe("B");
  });
  it("(-) without the cost before its round-up the same row does NOT agree", () => {
    expect(bcsAgrees(6880, 11350, 0.65, -1, 0)).toBe("D");
  });
  it("(+) C: wastage (BOQ-26-00157 row 130: 2,465 with 5%, BoQ 3,290)", () => {
    expect(bcsAgrees(2465, 3290, 0.4, -1, 0.05, 2464.7385)).toBe("C");
  });
  it("(-) the same cable without the wastage does not agree", () => {
    expect(bcsAgrees(2465, 3290, 0.4, -1, 0)).toBe("D");
  });
  it("(-) one rupee beyond rounding is NOT agreement", () => {
    expect(bcsAgrees(634.48 + 1, 920, 0.45, null)).toBe("D");
    expect(bcsAgrees(2652.3 + 1, 4376.295, 0.65, null)).toBe("D");
    expect(bcsAgrees(635, 920, 0.45, -1)).toBe("D"); // 635 x 1.45 = 920.75 -> 930
  });
  it("(-) no stated cost is E, and only A / B / C agree", () => {
    expect(bcsAgrees(null, 920, 0.45, -1)).toBe("E");
    expect((["A", "B", "C", "D", "E"] as const).map(agrees)).toEqual([true, true, true, false, false]);
  });
});

describe("resolveBcsMargin", () => {
  const ref = (item: string, field: string, extra: object = {}) => ({ ref: { kind: "electrical_pricing_input", item }, field, ...extra });
  const cfg: { bcs_default_margin: BcsDefaultMargin } = { bcs_default_margin: { entries: [
    ref("conduit", "supply_markup", { components: ["conduit"] }),
    ref("cable_arm", "supply_markup", { when: { insulation: "ARMOURED" } }),
    ref("cable_unarm", "supply_markup", { when: { insulation: "UNARMOURED" } }),
  ] } };
  const items = [input("conduit", { supply_markup: 0.4 }), input("cable_arm", { supply_markup: 0.35 }), input("cable_unarm", { supply_markup: 0.42 }), input("misc_supply", { ratio: 0.8 })];
  it("(+) picks the margin by component, then by the selection", () => {
    expect(resolveBcsMargin(cfg, items, "conduit", { insulation: "ARMOURED" })).toBe(0.4);
    expect(resolveBcsMargin(cfg, items, null, { insulation: "ARMOURED" })).toBe(0.35);
    expect(resolveBcsMargin(cfg, items, null, { insulation: "UNARMOURED" })).toBe(0.42);
  });
  it("(+) LIVE: changing the input changes the margin", () => {
    const moved = items.map((i) => (i.attributes.item === "conduit" ? input("conduit", { supply_markup: 0.9 }) : i));
    expect(resolveBcsMargin(cfg, moved, "conduit")).toBe(0.9);
  });
  it("(+) a ratio is our share of the quote: 0.8 means a 25% margin", () => {
    expect(resolveBcsMargin({ bcs_default_margin: { entries: [ref("misc_supply", "ratio")] } }, items, null)).toBeCloseTo(0.25, 12);
  });
  it("(-) no margin named, an input that is missing, or a zero ratio gives null, never a number", () => {
    expect(resolveBcsMargin({}, items, null)).toBeNull();
    expect(resolveBcsMargin({ bcs_default_margin: { entries: [ref("no_such", "supply_markup")] } }, items, null)).toBeNull();
    expect(resolveBcsMargin({ bcs_default_margin: { entries: [ref("z", "ratio")] } }, [input("z", { ratio: 0 })], null)).toBeNull();
  });
});
