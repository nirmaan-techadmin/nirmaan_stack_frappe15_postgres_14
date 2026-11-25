// BCS-W -- THE ELECTRICAL PRICING INPUT REMARKS, WORKED OUT FROM THE ROW'S OWN CURRENT VALUES (owner Question 1 answer 1a,
// 2026-11-25 00:20; the standing rule that no explanatory text carries a figure that goes stale when an input is edited).
// Reads the newest Electrical rate file (a latest-asset reader by file prefix: rate_master_electrical_all_v) and v74 (the last
// file with the remarks typed in).
//
// What each case protects:
//   (+) P6d: every template remark, worked out at today's values, shows the SAME rupee figures as today's (v74's) written
//       sentence -- except the stale figures named here (the lug's "quoted at Rs 60.19" was written at an older markup; today's
//       40% off / +55% give Rs 66.64). A new difference fails this test, by name.
//   (+) the example follows the value: move discount / markup / share / ratio / amount and the worked figure moves with it.
//   (+) the price sentence and the cost sentence come apart at the {bcs} mark.
//   (-) a sum naming a column the row does not have reads "-", never a made-up figure; a remark with no mark is not a template.
import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import { pathToFileURL } from "url";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";
import { evalSum, isTemplate, markText, remarkSections, draftValues } from "./pricingInputRemarks";

const DATA_DIR = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
const newest = readdirNewest("rate_master_electrical_all_v");
function readdirNewest(prefix: string): string {
  const f = fs.readdirSync(DATA_DIR).filter((n) => new RegExp(`^${prefix}\\d+\\.json$`).test(n))
    .sort((a, b) => Number(a.match(/v(\d+)/)![1]) - Number(b.match(/v(\d+)/)![1])).pop()!;
  return path.join(DATA_DIR, f);
}
type Item = { kind: string; attributes: Record<string, string>; rates: Record<string, number | null> };
const read = (f: string) => readJsonFixture<{ items: Item[] }>(pathToFileURL(f)).items.filter((i) => i.kind === "electrical_pricing_input");
const NOW = read(newest);
const V74 = new Map(read(path.join(DATA_DIR, "rate_master_electrical_all_v74.json")).map((i) => [i.attributes.item, i.attributes.remarks]));
const rupees = (s: string) => (s.match(/Rs \d[\d,]*(?:\.\d+)?/g) ?? []).map((x) => x.replace(/,/g, "")).sort();
/** the figures today's sentence carries that today's values no longer give (named, never fixed silently: answer 1a) */
const STALE: Record<string, { written: string; today: string }> = { lug: { written: "Rs 60.19", today: "Rs 66.64" } };

describe("BCS-W P6d: the live examples equal today's written figures", () => {
  const templates = NOW.filter((i) => isTemplate(i.attributes.remarks));
  it("(+) every rupee example is a template (33), plus the cost-only and the two discount remarks", () => {
    expect(templates.filter((i) => /\{rs\d*:/.test(i.attributes.remarks)).length).toBe(33);
  });
  for (const it_ of templates) {
    const id = it_.attributes.item;
    it(`(+) ${id}: worked out at today's values, the rupee figures equal v74's sentence${STALE[id] ? " but for the named stale figure" : ""}`, () => {
      const s = remarkSections(it_.attributes.remarks, it_.rates);
      let want = rupees(V74.get(id) ?? "");
      if (STALE[id]) want = want.map((x) => (x === STALE[id].written ? STALE[id].today : x)).sort();
      expect(rupees(`${s.boq} ${s.bcs}`)).toEqual(want);
    });
  }
});

describe("BCS-W the example follows the row's value", () => {
  const byId = new Map(NOW.map((i) => [i.attributes.item, i]));
  it("(+) armoured cable: 75% -> 70% off moves the quoted and the cost figures; the % in the words moves too", () => {
    const it_ = byId.get("cable_arm")!;
    const today = remarkSections(it_.attributes.remarks, it_.rates);
    expect(today.boq).toContain("at 75% off list and quote at +35%");
    expect(today.boq).toContain("quoted at Rs 411/m");
    expect(today.bcs).toContain("It costs us Rs 319/m");
    const moved = remarkSections(it_.attributes.remarks, draftValues(it_.rates, { discount: "0.7" }));
    expect(moved.boq).toContain("at 70% off list");
    expect(moved.boq).toContain("quoted at Rs 493/m"); // 1217 x 0.30 x 1.35 = 492.885
    expect(moved.bcs).toContain("It costs us Rs 383/m"); // 1217 x 0.30 x 1.05 = 383.355
  });
  it("(+) a share, a ratio and an amount move their examples", () => {
    const share = byId.get("pw_accessory_share")!;
    expect(remarkSections(share.attributes.remarks, share.rates).boq).toContain("A Rs 146 accessory gives Rs 29.20");
    expect(remarkSections(share.attributes.remarks, { share: 0.25 }).boq).toContain("gives Rs 36.50");
    const ratio = byId.get("popup_supply")!;
    expect(remarkSections(ratio.attributes.remarks, ratio.rates).bcs).toContain("costs us Rs 720");
    expect(remarkSections(ratio.attributes.remarks, { ratio: 0.75 }).bcs).toContain("costs us Rs 675");
    const amt = byId.get("tray_accessories")!;
    expect(remarkSections(amt.attributes.remarks, { amount: 110 }).boq).toContain("adds Rs 1,100");
  });
  it("(+) the price sentence and the cost sentence come apart at the {bcs} mark", () => {
    const s = remarkSections("Quote {%supply_markup}.{bcs}Costs Rs {rs:100*(1-discount)}.", { supply_markup: 0.4, discount: 0.5 });
    expect(s).toEqual({ boq: "Quote 40%.", bcs: "Costs Rs 50." });
  });
  it("(-) a column the row does not have reads '-'; a plain remark is not a template", () => {
    expect(markText("rs:100*(1-nothing_here)", { discount: 0.5 })).toBe("-");
    expect(evalSum("100*(1-discount", { discount: 0.5 })).toBeNull();
    expect(evalSum("100*discount; alert(1)", { discount: 0.5 })).toBeNull();
    expect(isTemplate("How full a PVC 25 mm conduit may be.")).toBe(false);
    expect(markText("rs2:165.5*share", { share: 0.25 })).toBe("41.38"); // half up, as the sentence wrote it
    expect(markText("rs10:24500*(1+supply_markup)", { supply_markup: 0.33 })).toBe("32,590");
  });
});
